"""
Bot đọc tín hiệu inverse từ v5_relay_demo.json (1 giây/lần), đặt cặp BUY_LIMIT + SELL_LIMIT theo grid_preview_inverse.

Clone luồng từ signal.py; khác:
- File relay: v5_relay_demo.json (do strategy_grid_step_v5 demo ghi khi đặt pending)
- Giá: **`buy_price`** → **BUY_LIMIT**; **`sell_price`** → **SELL_LIMIT**. SL/TP: BUY — SL=buy−step, TP=buy+step; SELL — SL=sell+step, TP=sell−step. MT5: BUY_LIMIT < ask, SELL_LIMIT > bid
- Comment lệnh: InvGrid_{step} — chỉ hủy lệnh chờ limit cùng prefix (tránh đụng GridStep_* của signal.py)
- Consumed: signal_inverse_consumed_relay_ids.json (tách signal.py)

- Login / volume: configs/config_grid_step_inverse_live.json (riêng; không dùng config của signal.py)
- Có thể trỏ file khác: python sign_inverse.py --config path/to/config.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, Optional, Set, Tuple

import MetaTrader5 as mt5

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(SCRIPT_DIR, "configs", "config_grid_step_inverse_live.json")
RELAY_DEMO_PATH = os.path.join(SCRIPT_DIR, "v5_relay_demo.json")
CONSUMED_IDS_PATH = os.path.join(SCRIPT_DIR, "signal_inverse_consumed_relay_ids.json")
POLL_SECONDS = 1.0
HEARTBEAT_EVERY_LOOPS = 30
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
            print(f"❌ [sign_inverse] MT5 init thất bại: {mt5.last_error()}")
            return False
        print(f"✅ [sign_inverse] Đã kết nối MT5 account={login}")
        return True
    except Exception as e:
        print(f"❌ [sign_inverse] Lỗi kết nối: {e}")
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


def _comment_inv(step: float) -> str:
    return f"InvGrid_{step}"


def cancel_inv_limit_pendings(symbol: str, magic: int) -> int:
    """Hủy BUY_LIMIT/SELL_LIMIT comment InvGrid* (không đụng GridStep*)."""
    orders = mt5.orders_get(symbol=symbol) or []
    n_ok = 0
    limit_types = (
        getattr(mt5, "ORDER_TYPE_BUY_LIMIT", 2),
        getattr(mt5, "ORDER_TYPE_SELL_LIMIT", 3),
    )
    for o in orders:
        if int(getattr(o, "magic", 0) or 0) != int(magic):
            continue
        if int(getattr(o, "type", -1)) not in limit_types:
            continue
        cmt = (getattr(o, "comment", "") or "").strip()
        if not cmt.startswith("InvGrid"):
            continue
        r = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": int(o.ticket)})
        if r is not None and r.retcode == mt5.TRADE_RETCODE_DONE:
            n_ok += 1
        elif r is not None:
            print(f"⚠️ [sign_inverse] Hủy pending #{o.ticket} thất bại: {r.retcode} {r.comment}")
    if n_ok:
        print(f"🧹 [sign_inverse] Đã hủy {n_ok} lệnh chờ limit (InvGrid) trên {symbol} magic={magic}")
    return n_ok


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


def place_pair_from_inverse_relay(payload: Dict[str, Any], volume: float) -> Tuple[bool, str, bool]:
    """
    BUY_LIMIT @ buy_price (SL=buy−step, TP=buy+step); SELL_LIMIT @ sell_price (SL=sell+step, TP=sell−step).
    """
    from utils import place_buy_limit, place_sell_limit

    symbol = str(payload.get("symbol") or "").strip()
    magic = int(payload.get("magic") or 0)
    relay_id = str(payload.get("relay_id") or "")

    gpr = payload.get("grid_preview") if isinstance(payload.get("grid_preview"), dict) else {}
    try:
        step_val = float(payload.get("step") or gpr.get("step") or 5)
    except (TypeError, ValueError):
        step_val = 5.0

    info = mt5.symbol_info(symbol)
    if not info:
        return False, f"symbol_info({symbol}) = None", False
    if not mt5.symbol_select(symbol, True):
        return False, f"symbol_select({symbol}) thất bại", False

    digits = int(getattr(info, "digits", 5) or 5)
    try:
        key_buy = round(float(gpr.get("buy_price")), digits)
        key_sell = round(float(gpr.get("sell_price")), digits)
    except (TypeError, ValueError):
        return False, "grid_preview_inverse thiếu buy_price/sell_price", False

    tick = mt5.symbol_info_tick(symbol)

    px_buy_lim = key_buy
    px_sell_lim = key_sell

    cancel_inv_limit_pendings(symbol, magic)

    volume_min = float(getattr(info, "volume_min", 0.01) or 0.01)
    volume_step = float(getattr(info, "volume_step", 0.01) or 0.01)
    vol = max(float(volume), volume_min)
    if volume_step > 0:
        vol = round(vol / volume_step) * volume_step
        vol = max(vol, volume_min)

    filling = mt5.ORDER_FILLING_IOC if (getattr(info, "filling_mode", 0) & 2) else mt5.ORDER_FILLING_FOK
    comment = _comment_inv(step_val)

    # BUY_LIMIT: SL dưới entry, TP trên; SELL_LIMIT: SL trên entry, TP dưới (cùng step).
    sl_buy = round(px_buy_lim - step_val, digits)
    tp_buy = round(px_buy_lim + step_val, digits)
    sl_sell = round(px_sell_lim + step_val, digits)
    tp_sell = round(px_sell_lim - step_val, digits)

    tick_hint = ""
    if tick is not None:
        tick_hint = f" | thị trường bid={tick.bid} ask={tick.ask}"
    print(
        f"📤 [sign_inverse] relay={relay_id[:8]}… | {symbol} | "
        f"BUY_LIMIT@{px_buy_lim} SL={sl_buy} TP={tp_buy} | "
        f"SELL_LIMIT@{px_sell_lim} SL={sl_sell} TP={tp_sell}"
        f" | step={step_val} | vol={vol} | {comment}{tick_hint}"
    )
    if tick is not None and (px_buy_lim >= float(tick.ask) or px_sell_lim <= float(tick.bid)):
        print(
            "⚠️ [sign_inverse] Giá có thể không hợp lệ MT5 (BUY_LIMIT phải < ask, SELL_LIMIT phải > bid) → 10015"
        )

    r1 = place_buy_limit(
        symbol, vol, px_buy_lim, sl_buy, tp_buy, magic, comment, digits=digits, type_filling=filling
    )
    r2 = place_sell_limit(
        symbol, vol, px_sell_lim, sl_sell, tp_sell, magic, comment, digits=digits, type_filling=filling
    )

    if r1 is None or r2 is None:
        return False, f"order_send None (buy={r1 is None}, sell={r2 is None})", False

    ok1 = r1.retcode == mt5.TRADE_RETCODE_DONE
    ok2 = r2.retcode == mt5.TRADE_RETCODE_DONE
    if ok1 and ok2:
        print(f"✅ [sign_inverse] Đã đặt cặp lệnh inverse relay_id={relay_id}")
        return True, "", False

    if not ok1:
        print(f"❌ [sign_inverse] BUY_LIMIT: {r1.retcode} {r1.comment}")
    if not ok2:
        print(f"❌ [sign_inverse] SELL_LIMIT: {r2.retcode} {r2.comment}")

    err_detail = f"BUY {getattr(r1, 'retcode', '?')} SELL {getattr(r2, 'retcode', '?')}"
    consume = _mark_consumed_after_pair_fail(r1, r2)
    if consume and (ok1 ^ ok2):
        cancel_inv_limit_pendings(symbol, magic)
        print(
            "🧹 [sign_inverse] Đã hủy lệnh chờ còn lại (partial fail) — đánh dấu consumed."
        )
    return False, err_detail, consume


def inverse_payload_ready(payload: Dict[str, Any], consumed: Set[str]) -> Optional[str]:
    rid = payload.get("relay_id")
    if not rid:
        return "no_relay_id"
    rid = str(rid)
    if rid in consumed:
        return "already_consumed"
    exp = payload.get("expires_ts")
    if exp is not None:
        try:
            if time.time() > float(exp):
                return "expired"
        except (TypeError, ValueError):
            return "bad_expires_ts"
    if not payload.get("symbol"):
        return "no_symbol"
    inv = payload.get("grid_preview_inverse")
    if not isinstance(inv, dict) or inv.get("buy_price") is None or inv.get("sell_price") is None:
        return "bad_grid_preview_inverse"
    return None


def _as_place_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """grid_preview = grid_preview_inverse (hai mức giá trong file)."""
    inv = raw.get("grid_preview_inverse") or {}
    step = float(inv.get("step") or raw.get("step") or 5)
    return {
        "relay_id": raw.get("relay_id"),
        "symbol": raw.get("symbol"),
        "magic": raw.get("magic"),
        "step": step,
        "grid_preview": dict(inv),
    }


def describe_inverse_wait_status(payload: Any, consumed: Set[str]) -> str:
    if not os.path.isfile(RELAY_DEMO_PATH):
        return "chưa có file (chờ demo ghi v5_relay_demo.json)"
    if payload is None:
        return "có file nhưng không parse được JSON"
    if not isinstance(payload, dict) or not payload:
        return "file trống hoặc JSON không phải object"
    rid = payload.get("relay_id")
    skip = inverse_payload_ready(payload, consumed)
    if skip is None:
        return f"relay_id={str(rid)[:8]}… — sẵn sàng đặt BUY_LIMIT/SELL_LIMIT"
    return f"relay_id={str(rid)[:8] if rid else '?'}… — bỏ qua: {skip}"


def run_loop(config_path: str) -> None:
    creds, volume = load_login_credentials(config_path)
    consumed = load_consumed_ids()
    print(f"📁 [sign_inverse] config login: {config_path}")
    print(f"📁 [sign_inverse] relay demo: {RELAY_DEMO_PATH}")
    print(f"📁 [sign_inverse] consumed ids: {CONSUMED_IDS_PATH} ({len(consumed)} id)")

    if not connect_mt5_login_only(creds):
        sys.exit(1)

    print(
        "🔄 [sign_inverse] Đọc v5_relay_demo.json mỗi 1 giây — BUY_LIMIT/SELL_LIMIT comment InvGrid_* "
        f"(không đụng GridStep_*). ~{HEARTBEAT_EVERY_LOOPS}s một dòng trạng thái. Ctrl+C dừng."
    )

    try:
        loop_n = 0
        payload: Any = None
        while True:
            loop_n += 1
            payload = _load_json(RELAY_DEMO_PATH, None)
            if isinstance(payload, dict) and payload:
                skip = inverse_payload_ready(payload, consumed)
                if skip is None:
                    place_payload = _as_place_payload(payload)
                    ok, err, mark_consumed = place_pair_from_inverse_relay(place_payload, volume)
                    if ok:
                        rid = str(payload["relay_id"])
                        save_consumed_id(rid, consumed)
                        consumed.add(rid)
                    elif mark_consumed and payload.get("relay_id"):
                        rid = str(payload["relay_id"])
                        save_consumed_id(rid, consumed)
                        consumed.add(rid)
                        if err and "thiếu" not in err:
                            print(f"⚠️ [sign_inverse] Bỏ qua (đã consumed): {err}")
                    elif err and "thiếu" not in err:
                        print(f"⚠️ [sign_inverse] Bỏ qua (sẽ thử lại): {err}")
            if loop_n % HEARTBEAT_EVERY_LOOPS == 0:
                st = describe_inverse_wait_status(payload, consumed)
                print(f"💓 [sign_inverse] #{loop_n} | {st}")

            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\n🛑 [sign_inverse] Dừng.")
    finally:
        mt5.shutdown()


def _parse_args() -> str:
    p = argparse.ArgumentParser(description="Bot inverse: đọc v5_relay_demo.json, đặt BUY_LIMIT/SELL_LIMIT InvGrid_*")
    p.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"JSON login/volume (mặc định: {DEFAULT_CONFIG_PATH})",
    )
    args = p.parse_args()
    return os.path.abspath(args.config)


if __name__ == "__main__":
    run_loop(_parse_args())
