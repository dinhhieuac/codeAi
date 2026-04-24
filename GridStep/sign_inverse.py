"""
Bot chỉ đọc **v5_relay_demo.json** đúng **1 lần/giây** (chu kỳ cố định: sau mỗi lần đọc + xử lý, chờ cho đủ `POLL_SECONDS`),
đặt cặp BUY_LIMIT + SELL_LIMIT theo grid_preview_inverse.

**Không** đọc v5_relay_signal.json — file đó dành cho bot signal.py / relay live V5.

Clone luồng từ signal.py; khác:
- File tín hiệu duy nhất: v5_relay_demo.json (do strategy_grid_step_v5 demo ghi khi đặt pending)
- Giá: **`buy_price`** → **BUY_LIMIT**; **`sell_price`** → **SELL_LIMIT**. SL/TP: BUY — SL=buy−step, TP=buy+step; SELL — SL=sell+step, TP=sell−step. MT5: BUY_LIMIT < ask, SELL_LIMIT > bid
- Comment lệnh: InvGrid_{step} — chỉ hủy lệnh chờ limit cùng prefix (tránh đụng GridStep_* của signal.py)
- Consumed: signal_inverse_consumed_relay_ids.json (tách signal.py)

- **`symbol` trong config** = tên symbol MT5 khi đặt BUY_LIMIT/SELL_LIMIT (vd XAUUSDm). Giá vẫn lấy từ relay; nếu chỉ có `symbol` (không dùng `inverse_allowed_symbols`) thì không chặn relay vì lệch tên broker so với demo.
- **spread_sl** (mặc định 0), **spread_tp** (mặc định −0.3): khi đặt BUY_LIMIT/SELL_LIMIT, `SL = SL + spread_sl`, `TP = TP + spread_tp` (sau công thức grid step).
- **`log/inverse_limit_pair_YYYY-MM-DD.jsonl`**: mỗi lần đặt cặp limit (thành công hoặc lỗi MT5) — tắt: `inverse_pair_log_enabled`: false.
- Có thể trỏ file khác: python sign_inverse.py --config path/to/config.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional, Set, Tuple

import MetaTrader5 as mt5

import signal_relay

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "log")
DEFAULT_CONFIG_PATH = os.path.join(SCRIPT_DIR, "configs", "config_grid_step_inverse_live.json")
# Chỉ nguồn tín hiệu inverse — không dùng v5_relay_signal.json (xem signal.py).
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


def _order_send_result_dict(r: Any) -> Optional[Dict[str, Any]]:
    if r is None:
        return None
    return {
        "retcode": int(getattr(r, "retcode", 0) or 0),
        "comment": str(getattr(r, "comment", "") or ""),
        "order": int(getattr(r, "order", 0) or 0),
    }


def _append_inverse_limit_daily_log(record: dict) -> None:
    """Một dòng JSON / ngày — cùng thư mục log với V5 (`GridStep/log/`)."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        return
    day = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(LOG_DIR, f"inverse_limit_pair_{day}.jsonl")
    line = dict(record)
    line["_logged_ts"] = time.time()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except IOError:
        pass


def _allowed_symbols_from_config(cfg: Dict[str, Any]) -> Optional[Set[str]]:
    """
    None = cho mọi symbol trong relay (không lọc).
    Set khác rỗng = chỉ relay có symbol thuộc set (so khớp không phân biệt hoa thường).
    Ưu tiên `inverse_allowed_symbols` (mảng); không có thì dùng một `symbol` (chuỗi) nếu có.
    """
    raw = cfg.get("inverse_allowed_symbols")
    if isinstance(raw, list) and len(raw) > 0:
        out = {str(x).strip().upper() for x in raw if str(x).strip()}
        return out if out else None
    one = cfg.get("symbol")
    if one is not None and str(one).strip():
        return {str(one).strip().upper()}
    return None


def load_sign_inverse_config(
    config_path: str,
) -> Tuple[Dict[str, Any], float, Optional[Set[str]], float, float, Optional[str], bool]:
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
    trade_symbol = str(cfg.get("symbol") or "").strip() or None
    allowed = _allowed_symbols_from_config(cfg)
    if trade_symbol is not None and not (
        isinstance(cfg.get("inverse_allowed_symbols"), list)
        and len(cfg.get("inverse_allowed_symbols") or []) > 0
    ):
        allowed = None
    raw_sl = cfg.get("spread_sl")
    raw_tp = cfg.get("spread_tp")
    spread_sl = 0.0 if raw_sl is None else float(raw_sl)
    spread_tp = -0.3 if raw_tp is None else float(raw_tp)
    raw_log = cfg.get("inverse_pair_log_enabled")
    pair_log_enabled = True if raw_log is None else bool(raw_log)
    return creds, vol, allowed, spread_sl, spread_tp, trade_symbol, pair_log_enabled


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


def place_pair_from_inverse_relay(
    payload: Dict[str, Any],
    volume: float,
    *,
    spread_sl: float = 0.0,
    spread_tp: float = -0.3,
    order_symbol: Optional[str] = None,
    pair_log_enabled: bool = True,
) -> Tuple[bool, str, bool]:
    """
    BUY_LIMIT @ buy_price (SL=buy−step, TP=buy+step); SELL_LIMIT @ sell_price (SL=sell+step, TP=sell−step).
    SL/TP sau đó cộng spread_sl / spread_tp từ config.
    order_symbol: từ config `symbol` — dùng cho MT5; nếu None thì dùng payload.symbol từ relay.
    """
    from utils import (
        cancel_all_bot_limit_pendings,
        has_same_price_inverse_duplicate,
        normalize_inverse_limit_prices,
        place_buy_limit,
        place_sell_limit,
    )

    symbol = str(order_symbol or payload.get("symbol") or "").strip()
    magic = int(payload.get("magic") or 0)
    relay_batch, relay_id_buy_leg, relay_id_sell_leg = signal_relay.demo_relay_order_relay_ids(payload)

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
    nb, ns, norm_note = normalize_inverse_limit_prices(info, tick, px_buy_lim, px_sell_lim, digits)
    if nb is None or ns is None:
        msg = norm_note or "không chuẩn hóa được giá limit"
        print(f"⏭️ [sign_inverse] Bỏ qua — {msg}")
        return False, msg, False
    px_buy_lim, px_sell_lim = nb, ns
    if norm_note:
        print(f"🔧 [sign_inverse] Chuẩn hóa giá relay: {norm_note}")

    n_rm = cancel_all_bot_limit_pendings(symbol, magic)
    if n_rm:
        print(
            f"🧹 [sign_inverse] Đã hủy {n_rm} lệnh LIMIT cũ ({symbol} magic={magic}) — tín hiệu demo mới."
        )

    dup, dup_reason = has_same_price_inverse_duplicate(
        symbol, magic, px_buy_lim, px_sell_lim, digits, check_positions=False
    )
    if dup:
        print(
            f"⏭️ [sign_inverse] Bỏ qua — {dup_reason} (vẫn trùng sau khi hủy LIMIT). "
            f"Không đánh dấu relay consumed — thử lại vòng sau."
        )
        return False, dup_reason, False

    volume_min = float(getattr(info, "volume_min", 0.01) or 0.01)
    volume_step = float(getattr(info, "volume_step", 0.01) or 0.01)
    vol = max(float(volume), volume_min)
    if volume_step > 0:
        vol = round(vol / volume_step) * volume_step
        vol = max(vol, volume_min)

    filling = mt5.ORDER_FILLING_IOC if (getattr(info, "filling_mode", 0) & 2) else mt5.ORDER_FILLING_FOK
    comment_buy = signal_relay.inverse_order_invgrid_comment(step_val, relay_id_buy_leg)
    comment_sell = signal_relay.inverse_order_invgrid_comment(step_val, relay_id_sell_leg)

    # BUY_LIMIT: SL dưới entry, TP trên; SELL_LIMIT: SL trên entry, TP dưới (cùng step); + spread_sl/spread_tp.
    sl_buy = round(px_buy_lim - step_val + spread_sl, digits)
    tp_buy = round(px_buy_lim + step_val + spread_tp, digits)
    sl_sell = round(px_sell_lim + step_val + spread_sl, digits)
    tp_sell = round(px_sell_lim - step_val + spread_tp, digits)

    tick_hint = ""
    if tick is not None:
        tick_hint = f" | thị trường bid={tick.bid} ask={tick.ask}"
    print(
        f"📤 [sign_inverse] batch={relay_batch[:8]}… buy_id={relay_id_buy_leg[:8]}… sell_id={relay_id_sell_leg[:8]}… | {symbol} | "
        f"BUY_LIMIT@{px_buy_lim} SL={sl_buy} TP={tp_buy} ({comment_buy}) | "
        f"SELL_LIMIT@{px_sell_lim} SL={sl_sell} TP={tp_sell} ({comment_sell})"
        f" | step={step_val} | vol={vol}{tick_hint}"
    )

    def _base_log_common() -> Dict[str, Any]:
        return {
            "source": "sign_inverse",
            "symbol": symbol,
            "magic": magic,
            "relay_batch": relay_batch,
            "relay_id_buy_leg": relay_id_buy_leg,
            "relay_id_sell_leg": relay_id_sell_leg,
            "step": step_val,
            "volume": vol,
            "px_buy_limit": px_buy_lim,
            "px_sell_limit": px_sell_lim,
            "sl_buy": sl_buy,
            "tp_buy": tp_buy,
            "sl_sell": sl_sell,
            "tp_sell": tp_sell,
            "grid_preview": gpr,
        }

    def _mt5_last_err() -> Optional[Dict[str, Any]]:
        le = mt5.last_error()
        if le and len(le) >= 2:
            return {"code": int(le[0]), "message": str(le[1])}
        return None

    r1 = place_buy_limit(
        symbol, vol, px_buy_lim, sl_buy, tp_buy, magic, comment_buy, digits=digits, type_filling=filling
    )
    r2 = place_sell_limit(
        symbol, vol, px_sell_lim, sl_sell, tp_sell, magic, comment_sell, digits=digits, type_filling=filling
    )

    if r1 is None or r2 is None:
        if pair_log_enabled:
            if r1 is None and r2 is None:
                fail = "both_none"
            elif r1 is None:
                fail = "buy_none"
            else:
                fail = "sell_none"
            _append_inverse_limit_daily_log(
                {
                    "event": "inverse_limit_pair_error",
                    "ok": False,
                    "failure": fail,
                    **_base_log_common(),
                    "buy_limit": _order_send_result_dict(r1),
                    "sell_limit": _order_send_result_dict(r2),
                    "mt5_last_error": _mt5_last_err(),
                }
            )
        return False, f"order_send None (buy={r1 is None}, sell={r2 is None})", False

    ok1 = r1.retcode == mt5.TRADE_RETCODE_DONE
    ok2 = r2.retcode == mt5.TRADE_RETCODE_DONE
    if ok1 and ok2:
        print(
            f"✅ [sign_inverse] Đã đặt cặp lệnh inverse batch={relay_batch} | "
            f"BUY_LIMIT relay_id={relay_id_buy_leg} | SELL_LIMIT relay_id={relay_id_sell_leg}"
        )
        if pair_log_enabled:
            _append_inverse_limit_daily_log(
                {
                    "event": "inverse_limit_pair",
                    "ok": True,
                    **_base_log_common(),
                    "buy_limit": _order_send_result_dict(r1),
                    "sell_limit": _order_send_result_dict(r2),
                }
            )
        return True, "", False

    if not ok1:
        print(f"❌ [sign_inverse] BUY_LIMIT: {r1.retcode} {r1.comment}")
    if not ok2:
        print(f"❌ [sign_inverse] SELL_LIMIT: {r2.retcode} {r2.comment}")

    if pair_log_enabled:
        if ok1 and not ok2:
            fail = "sell_retcode"
        elif not ok1 and ok2:
            fail = "buy_retcode"
        else:
            fail = "both_retcode"
        _append_inverse_limit_daily_log(
            {
                "event": "inverse_limit_pair_error",
                "ok": False,
                "failure": fail,
                **_base_log_common(),
                "buy_limit": _order_send_result_dict(r1),
                "sell_limit": _order_send_result_dict(r2),
                "mt5_last_error": None,
            }
        )

    err_detail = f"BUY {getattr(r1, 'retcode', '?')} SELL {getattr(r2, 'retcode', '?')}"
    consume = _mark_consumed_after_pair_fail(r1, r2)
    if consume and (ok1 ^ ok2):
        n_cl = cancel_all_bot_limit_pendings(symbol, magic)
        if n_cl:
            print(
                f"🧹 [sign_inverse] Đã hủy {n_cl} LIMIT còn lại (partial fail) — đánh dấu consumed."
            )
    return False, err_detail, consume


def inverse_payload_ready(
    payload: Dict[str, Any],
    consumed: Set[str],
    allowed_symbols: Optional[Set[str]] = None,
) -> Optional[str]:
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
    sym = str(payload.get("symbol") or "").strip().upper()
    if allowed_symbols is not None and sym not in allowed_symbols:
        return "symbol_not_in_config"
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
        "relay_id_buy_limit": raw.get("relay_id_buy_limit"),
        "relay_id_sell_limit": raw.get("relay_id_sell_limit"),
        "symbol": raw.get("symbol"),
        "magic": raw.get("magic"),
        "step": step,
        "grid_preview": dict(inv),
    }


def describe_inverse_wait_status(
    payload: Any, consumed: Set[str], allowed_symbols: Optional[Set[str]] = None
) -> str:
    if not os.path.isfile(RELAY_DEMO_PATH):
        return "chưa có file (chờ demo ghi v5_relay_demo.json)"
    if payload is None:
        return "có file nhưng không parse được JSON"
    if not isinstance(payload, dict) or not payload:
        return "file trống hoặc JSON không phải object"
    rid = payload.get("relay_id")
    skip = inverse_payload_ready(payload, consumed, allowed_symbols)
    if skip is None:
        return f"relay_id={str(rid)[:8]}… — sẵn sàng đặt BUY_LIMIT/SELL_LIMIT"
    return f"relay_id={str(rid)[:8] if rid else '?'}… — bỏ qua: {skip}"


def run_loop(config_path: str) -> None:
    creds, volume, allowed_symbols, spread_sl, spread_tp, trade_symbol, pair_log_enabled = (
        load_sign_inverse_config(config_path)
    )
    consumed = load_consumed_ids()
    print(f"📁 [sign_inverse] config login: {config_path}")
    print(f"📁 [sign_inverse] relay demo: {RELAY_DEMO_PATH}")
    print(f"📁 [sign_inverse] consumed ids: {CONSUMED_IDS_PATH} ({len(consumed)} id)")
    print(f"📌 [sign_inverse] spread_sl={spread_sl} spread_tp={spread_tp} (SL+=spread_sl, TP+=spread_tp)")
    print(
        f"📌 [sign_inverse] Ghi log cặp limit: {'bật' if pair_log_enabled else 'tắt'} "
        f"(log/inverse_limit_pair_YYYY-MM-DD.jsonl)"
    )
    if trade_symbol:
        print(
            f"📌 [sign_inverse] Đặt BUY_LIMIT/SELL_LIMIT trên symbol MT5: {trade_symbol} "
            "(theo config; giá từ relay)"
        )
    if allowed_symbols is not None:
        print(f"📌 [sign_inverse] Chỉ relay có symbol: {sorted(allowed_symbols)} (khác → bỏ qua)")
    elif not trade_symbol:
        print("📌 [sign_inverse] Không lọc symbol — mọi symbol trong v5_relay_demo.json đều xử lý")

    if not connect_mt5_login_only(creds):
        sys.exit(1)

    print(
        f"🔄 [sign_inverse] Kiểm tra file tín hiệu mỗi {POLL_SECONDS:g}s (1 lần đọc v5_relay_demo.json / chu kỳ) — "
        "BUY_LIMIT/SELL_LIMIT comment InvGrid_* (không đụng GridStep_*). "
        f"~{HEARTBEAT_EVERY_LOOPS * POLL_SECONDS:g}s một dòng trạng thái. Ctrl+C dừng."
    )

    try:
        loop_n = 0
        payload: Any = None
        while True:
            t_cycle = time.monotonic()
            loop_n += 1
            payload = _load_json(RELAY_DEMO_PATH, None)
            if isinstance(payload, dict) and payload:
                skip = inverse_payload_ready(payload, consumed, allowed_symbols)
                if skip is None:
                    place_payload = _as_place_payload(payload)
                    ok, err, mark_consumed = place_pair_from_inverse_relay(
                        place_payload,
                        volume,
                        spread_sl=spread_sl,
                        spread_tp=spread_tp,
                        order_symbol=trade_symbol,
                        pair_log_enabled=pair_log_enabled,
                    )
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
                st = describe_inverse_wait_status(payload, consumed, allowed_symbols)
                print(f"💓 [sign_inverse] #{loop_n} | {st}")

            elapsed = time.monotonic() - t_cycle
            time.sleep(max(0.0, float(POLL_SECONDS) - elapsed))
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
