"""
Bot đọc tín hiệu từ v5_relay_signal.json (1 giây/lần), đặt lệnh trên MT5.

- Login: chỉ dùng account / password / server / mt5_path từ configs/config_grid_step_v5_live.json
- Khối lượng: lấy key `volume` trong cùng file nếu có (không thuộc nhóm login), mặc định 0.01
- Symbol / magic / giá lệnh: lấy từ payload relay (do demo V5 ghi)
- Khi có tín hiệu mới (trước khi đặt cặp): hủy hết pending BUY_STOP/SELL_STOP cùng symbol+magic, comment GridStep*
- Sau khi đặt thành công cả BUY_STOP và SELL_STOP: lưu relay_id để không lặp lại cùng tín hiệu
- Khi đặt thất bại không thể thử lại cùng snapshot (vd 10015 Invalid price, hoặc chỉ 1/2 lệnh OK): đánh dấu consumed + bỏ qua; partial thì hủy lệnh chờ orphan
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, Optional, Set, Tuple

import MetaTrader5 as mt5

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "configs", "config_grid_step_v5_live.json")
RELAY_SIGNAL_PATH = os.path.join(SCRIPT_DIR, "v5_relay_signal.json")
CONSUMED_IDS_PATH = os.path.join(SCRIPT_DIR, "signal_consumed_relay_ids.json")
POLL_SECONDS = 1.0
HEARTBEAT_EVERY_LOOPS = 30  # 30s nếu poll=1s — log 1 dòng để biết bot không bị treo
MAX_STORED_IDS = 2000


def _load_json(path: str, default: Any) -> Any:
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _atomic_write(path: str, obj: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_login_credentials(config_path: str) -> Tuple[Dict[str, Any], float]:
    """
    Trả về dict chỉ dùng cho mt5.initialize (4 field) + volume phụ từ file (nếu có).
    """
    cfg = _load_json(config_path, None)
    if not isinstance(cfg, dict):
        raise FileNotFoundError(f"Không đọc được config: {config_path}")
    creds = {
        "account": int(cfg["account"]),
        "password": str(cfg["password"]),
        "server": str(cfg["server"]),
        "mt5_path": str(cfg.get("mt5_path") or "").strip(),
    }
    vol = float(cfg.get("volume") or 0.01)
    return creds, vol


def connect_mt5_login_only(creds: Dict[str, Any]) -> bool:
    """Chỉ login — không dùng symbol/magic từ config cho lệnh."""
    mt5.shutdown()
    login = creds["account"]
    password = creds["password"]
    server = creds["server"]
    path = creds.get("mt5_path") or ""
    try:
        if path:
            ok = mt5.initialize(path=path, login=login, password=password, server=server)
        else:
            ok = mt5.initialize(login=login, password=password, server=server)
        if not ok:
            print(f"❌ [signal] MT5 init thất bại: {mt5.last_error()}")
            return False
        print(f"✅ [signal] Đã kết nối MT5 account={login}")
        return True
    except Exception as e:
        print(f"❌ [signal] Lỗi kết nối: {e}")
        return False


def load_consumed_ids() -> Set[str]:
    data = _load_json(CONSUMED_IDS_PATH, {})
    if isinstance(data, dict):
        ids = data.get("consumed_relay_ids") or []
    elif isinstance(data, list):
        ids = data
    else:
        ids = []
    return {str(x) for x in ids if x}


def save_consumed_id(relay_id: str, existing: Set[str]) -> None:
    merged = set(existing)
    merged.add(relay_id)
    lst = sorted(merged)
    if len(lst) > MAX_STORED_IDS:
        lst = lst[-MAX_STORED_IDS:]
    _atomic_write(CONSUMED_IDS_PATH, {"consumed_relay_ids": lst})


def _comment_for_step(step: float) -> str:
    return f"GridStep_{step}"


def cancel_grid_stop_pendings_for_pair(symbol: str, magic: int) -> int:
    """
    Hủy mọi lệnh chờ BUY_STOP / SELL_STOP của cặp grid (cùng symbol + magic, comment GridStep*).
    Gọi trước khi đặt cặp mới theo relay để tránh chồng lệnh cũ.
    """
    orders = mt5.orders_get(symbol=symbol) or []
    n_ok = 0
    stop_types = (
        getattr(mt5, "ORDER_TYPE_BUY_STOP", 4),
        getattr(mt5, "ORDER_TYPE_SELL_STOP", 5),
    )
    for o in orders:
        if int(getattr(o, "magic", 0) or 0) != int(magic):
            continue
        if int(getattr(o, "type", -1)) not in stop_types:
            continue
        cmt = (getattr(o, "comment", "") or "").strip()
        if not cmt.startswith("GridStep"):
            continue
        r = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": int(o.ticket)})
        if r is not None and r.retcode == mt5.TRADE_RETCODE_DONE:
            n_ok += 1
        elif r is not None:
            print(f"⚠️ [signal] Hủy pending #{o.ticket} thất bại: {r.retcode} {r.comment}")
    if n_ok:
        print(f"🧹 [signal] Đã hủy {n_ok} lệnh chờ stop (GridStep) trên {symbol} magic={magic}")
    return n_ok


# Cả hai lệnh đều fail với các retcode này → có thể thử lại cùng relay (tick/mạng đổi).
_RELAY_RETRY_IF_BOTH_FAILED = frozenset(
    {
        getattr(mt5, "TRADE_RETCODE_REQUOTE", 10004),
        getattr(mt5, "TRADE_RETCODE_REJECT", 10006),
        getattr(mt5, "TRADE_RETCODE_TIMEOUT", 10012),
        getattr(mt5, "TRADE_RETCODE_CONNECTION", 10031),
        getattr(mt5, "TRADE_RETCODE_TOO_MANY_REQUESTS", 10024),
    }
)


def _mark_consumed_after_pair_fail(r1: Any, r2: Any) -> bool:
    """
    True → nên ghi consumed để không spam relay mỗi giây (invalid price, partial 1/2, v.v.).
    False → giữ relay để thử lại (hai lệnh đều fail với lỗi tạm).
    """
    if r1 is None or r2 is None:
        return False
    done = mt5.TRADE_RETCODE_DONE
    ok1 = r1.retcode == done
    ok2 = r2.retcode == done
    if ok1 and ok2:
        return False
    if ok1 ^ ok2:
        return True
    rc1, rc2 = int(r1.retcode), int(r2.retcode)
    return not (rc1 in _RELAY_RETRY_IF_BOTH_FAILED and rc2 in _RELAY_RETRY_IF_BOTH_FAILED)


def place_pair_from_relay(payload: Dict[str, Any], volume: float) -> Tuple[bool, str, bool]:
    """
    Đặt cặp BUY_STOP + SELL_STOP theo grid_preview trong relay.
    Trả (True, "", False) nếu cả hai TRADE_RETCODE_DONE.
    Trả (False, err, mark_consumed): mark_consumed=True → ghi consumed, bỏ qua relay (vd 10015, hoặc 1 lệnh DONE 1 lệnh lỗi).
    """
    from utils import place_buy_stop, place_sell_stop

    symbol = str(payload.get("symbol") or "").strip()
    magic = int(payload.get("magic") or 0)
    relay_id = str(payload.get("relay_id") or "")

    gpr = payload.get("grid_preview") if isinstance(payload.get("grid_preview"), dict) else {}
    try:
        buy_price = float(gpr.get("buy_price"))
        sell_price = float(gpr.get("sell_price"))
    except (TypeError, ValueError):
        return False, "grid_preview thiếu buy_price/sell_price", False

    try:
        step_val = float(payload.get("step") or gpr.get("step") or 5)
    except (TypeError, ValueError):
        step_val = 5.0

    info = mt5.symbol_info(symbol)
    if not info:
        return False, f"symbol_info({symbol}) = None", False
    if not mt5.symbol_select(symbol, True):
        return False, f"symbol_select({symbol}) thất bại", False

    cancel_grid_stop_pendings_for_pair(symbol, magic)

    digits = int(getattr(info, "digits", 5) or 5)
    volume_min = float(getattr(info, "volume_min", 0.01) or 0.01)
    volume_step = float(getattr(info, "volume_step", 0.01) or 0.01)
    vol = max(float(volume), volume_min)
    if volume_step > 0:
        vol = round(vol / volume_step) * volume_step
        vol = max(vol, volume_min)

    filling = mt5.ORDER_FILLING_IOC if (getattr(info, "filling_mode", 0) & 2) else mt5.ORDER_FILLING_FOK
    comment = _comment_for_step(step_val)

    sl_buy = round(buy_price - step_val, digits)
    tp_buy = round(buy_price + step_val, digits)
    sl_sell = round(sell_price + step_val, digits)
    tp_sell = round(sell_price - step_val, digits)

    print(
        f"📤 [signal] relay={relay_id[:8]}… | {symbol} | "
        f"BUY_STOP {buy_price} | SELL_STOP {sell_price} | step={step_val} | vol={vol}"
    )

    r1 = place_buy_stop(
        symbol, vol, buy_price, sl_buy, tp_buy, magic, comment, digits=digits, type_filling=filling
    )
    r2 = place_sell_stop(
        symbol, vol, sell_price, sl_sell, tp_sell, magic, comment, digits=digits, type_filling=filling
    )

    if r1 is None or r2 is None:
        return False, f"order_send None (buy={r1 is None}, sell={r2 is None})", False

    ok1 = r1.retcode == mt5.TRADE_RETCODE_DONE
    ok2 = r2.retcode == mt5.TRADE_RETCODE_DONE
    if ok1 and ok2:
        print(f"✅ [signal] Đã đặt cặp lệnh relay_id={relay_id}")
        return True, "", False

    if not ok1:
        print(f"❌ [signal] BUY_STOP: {r1.retcode} {r1.comment}")
    if not ok2:
        print(f"❌ [signal] SELL_STOP: {r2.retcode} {r2.comment}")

    err_detail = f"BUY {getattr(r1, 'retcode', '?')} SELL {getattr(r2, 'retcode', '?')}"
    consume = _mark_consumed_after_pair_fail(r1, r2)
    if consume and (ok1 ^ ok2):
        cancel_grid_stop_pendings_for_pair(symbol, magic)
        print(
            f"🧹 [signal] Đã hủy lệnh chờ còn lại (partial fail) để tránh orphan — relay sẽ đánh dấu consumed."
        )
    return False, err_detail, consume


def relay_payload_ready(payload: Dict[str, Any], consumed: Set[str]) -> Optional[str]:
    """Trả lý do skip hoặc None nếu có thể xử lý."""
    rid = payload.get("relay_id")
    if not rid:
        return "no_relay_id"
    rid = str(rid)
    if rid in consumed:
        return "already_consumed"
    exp = payload.get("expires_ts")
    try:
        if exp is not None and time.time() > float(exp):
            return "expired"
    except (TypeError, ValueError):
        return "bad_expires_ts"
    if not payload.get("symbol"):
        return "no_symbol"
    gpr = payload.get("grid_preview")
    if not isinstance(gpr, dict) or gpr.get("buy_price") is None or gpr.get("sell_price") is None:
        return "bad_grid_preview"
    return None


def describe_relay_wait_status(
    payload: Any, consumed: Set[str]
) -> str:
    """Một dòng trạng thái cho log nhịp (không spam mỗi giây)."""
    if not os.path.isfile(RELAY_SIGNAL_PATH):
        return "chưa có file (chờ demo ghi v5_relay_signal.json)"
    if payload is None:
        return "có file nhưng không parse được JSON"
    if not isinstance(payload, dict) or not payload:
        return "file trống hoặc JSON không phải object"
    rid = payload.get("relay_id")
    skip = relay_payload_ready(payload, consumed)
    if skip is None:
        return f"relay_id={str(rid)[:8]}… — sẵn sàng đặt lệnh"
    return f"relay_id={str(rid)[:8] if rid else '?'}… — bỏ qua: {skip}"


def run_loop() -> None:
    creds, volume = load_login_credentials(CONFIG_PATH)
    consumed = load_consumed_ids()
    print(f"📁 [signal] config login: {CONFIG_PATH}")
    print(f"📁 [signal] relay file: {RELAY_SIGNAL_PATH}")
    print(f"📁 [signal] consumed ids: {CONSUMED_IDS_PATH} ({len(consumed)} id)")

    if not connect_mt5_login_only(creds):
        sys.exit(1)

    print(
        "🔄 [signal] Đang chạy: đọc relay mỗi 1 giây — không có log mỗi giây là bình thường. "
        f"Cứ ~{HEARTBEAT_EVERY_LOOPS}s in 1 dòng trạng thái. Ctrl+C để dừng."
    )

    try:
        loop_n = 0
        while True:
            loop_n += 1
            payload = _load_json(RELAY_SIGNAL_PATH, None)
            if isinstance(payload, dict) and payload:
                skip = relay_payload_ready(payload, consumed)
                if skip is None:
                    ok, err, mark_consumed = place_pair_from_relay(payload, volume)
                    if ok:
                        rid = str(payload["relay_id"])
                        save_consumed_id(rid, consumed)
                        consumed.add(rid)
                    elif mark_consumed and payload.get("relay_id"):
                        rid = str(payload["relay_id"])
                        save_consumed_id(rid, consumed)
                        consumed.add(rid)
                        if err and err != "grid_preview thiếu buy_price/sell_price":
                            print(f"⚠️ [signal] Bỏ qua relay (đã đánh dấu consumed): {err}")
                    elif err and err != "grid_preview thiếu buy_price/sell_price":
                        print(f"⚠️ [signal] Bỏ qua relay (chưa đánh dấu consumed, sẽ thử lại): {err}")
            if loop_n % HEARTBEAT_EVERY_LOOPS == 0:
                st = describe_relay_wait_status(payload, consumed)
                print(f"💓 [signal] #{loop_n} | {st}")

            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\n🛑 [signal] Dừng.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    run_loop()
