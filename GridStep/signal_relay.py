"""
Demo → Live relay: demo phát tín hiệu sau khi gửi lệnh thành công; live chỉ mirror theo relay.

File:
- v5_relay_signal.json — payload mới nhất chờ live
- v5_relay_state.json — demo_relayed_zone_ts (zone → unix time relay cuối, dedupe theo TTL)
  + live_consumed_relay_ids
- v5_relay_signal_history.jsonl — base; khi payload có `symbol` → append vào **v5_relay_signal_history_<SYMBOL>.jsonl** (cùng quy tắc demo history); đổi path qua configure_grid_step_v5_paths
- v5_relay_demo.json — mỗi tín hiệu: **ghi đè** file (xóa data cũ), relay_id mới; không merge.
  `relay_id` = id lô (sign_inverse consume); `relay_id_buy_limit` / `relay_id_sell_limit` = id từng chân inverse; đổi path qua configure_grid_step_v5_paths
- v5_relay_demo_history_<SYMBOL>.jsonl — append mỗi lần ghi demo inverse (một file/symbol, từ base path v5_relay_demo_history.jsonl); đổi base qua configure_grid_step_v5_paths

Đặt BUY_LIMIT/SELL_LIMIT inverse trên MT5 do sign_inverse / btc_sign_inverser thực hiện; `demo_relay_order_relay_ids` +
`inverse_order_invgrid_comment` map đúng relay_id từng chân vào comment lệnh. Trùng giá: utils.has_same_price_inverse_duplicate.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RELAY_SIGNAL_FILE = os.path.join(SCRIPT_DIR, "v5_relay_signal.json")
RELAY_STATE_FILE = os.path.join(SCRIPT_DIR, "v5_relay_state.json")
RELAY_SIGNAL_HISTORY_LOG = os.path.join(SCRIPT_DIR, "v5_relay_signal_history.jsonl")
RELAY_DEMO_FILE = os.path.join(SCRIPT_DIR, "v5_relay_demo.json")
RELAY_DEMO_HISTORY_LOG = os.path.join(SCRIPT_DIR, "v5_relay_demo_history.jsonl")


def _default_state() -> Dict[str, Any]:
    return {"demo_relayed_zone_ts": {}, "live_consumed_relay_ids": []}


def _normalize_demo_zone_ts(state: Dict[str, Any]) -> Dict[str, float]:
    """
    demo_relayed_zone_ts: { "2645": 1730000000.0 } — lần relay gần nhất theo zone_key.
    Legacy: demo_relayed_zones = [2645, ...] → chuyển sang ts=0 (coi như hết hạn, cho relay lại).
    """
    raw = state.get("demo_relayed_zone_ts")
    if isinstance(raw, dict) and raw:
        out: Dict[str, float] = {}
        for k, v in raw.items():
            try:
                out[str(int(k))] = float(v)
            except (TypeError, ValueError):
                continue
        return out
    legacy = state.get("demo_relayed_zones")
    if isinstance(legacy, list) and legacy:
        out = {}
        for z in legacy:
            if z is None:
                continue
            try:
                out[str(int(float(z)))] = 0.0
            except (TypeError, ValueError):
                continue
        return out
    return {}


def _load_json(path: str, default: Any) -> Any:
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _atomic_write(path: str, obj: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _relay_signal_history_path_for_payload(payload: Dict[str, Any]) -> str:
    """
    Từ RELAY_SIGNAL_HISTORY_LOG (vd v5_relay_signal_history.jsonl) → v5_relay_signal_history_BTCUSD.jsonl
    (cùng cách với v5_relay_demo_history_*.jsonl). Symbol rỗng → file base.
    """
    base = RELAY_SIGNAL_HISTORY_LOG
    if not base:
        return ""
    sym = _symbol_safe_for_filename(str(payload.get("symbol") or ""))
    if not sym:
        return base
    dirname, basename = os.path.split(base)
    stem, ext = os.path.splitext(basename)
    if not ext:
        ext = ".jsonl"
    return os.path.join(dirname, f"{stem}_{sym}{ext}")


def _append_relay_signal_history(payload: Dict[str, Any]) -> None:
    """Một dòng JSON = một tín hiệu đã ghi khi demo publish relay (append-only), tách file theo symbol như demo history."""
    path = _relay_signal_history_path_for_payload(payload)
    if not path:
        return
    line = dict(payload)
    line["_history_logged_ts"] = time.time()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except IOError:
        pass


def _symbol_safe_for_filename(symbol: str) -> str:
    s = "".join(c if (c.isalnum() or c in "._-") else "_" for c in str(symbol).strip())
    return s or ""


def _relay_demo_history_path_for_payload(payload: Dict[str, Any]) -> str:
    """
    Từ RELAY_DEMO_HISTORY_LOG (vd .../v5_relay_demo_history.jsonl) → .../v5_relay_demo_history_BTCUSD.jsonl
    để XAU/BTC không trộn trong một file. Symbol rỗng → dùng path gốc.
    """
    base = RELAY_DEMO_HISTORY_LOG
    if not base:
        return ""
    sym = _symbol_safe_for_filename(str(payload.get("symbol") or ""))
    if not sym:
        return base
    dirname, basename = os.path.split(base)
    stem, ext = os.path.splitext(basename)
    if not ext:
        ext = ".jsonl"
    return os.path.join(dirname, f"{stem}_{sym}{ext}")


def _append_relay_demo_history(payload: Dict[str, Any]) -> None:
    """Một dòng JSON = một lần ghi v5_relay_demo (append-only), cùng schema payload với file snapshot."""
    path = _relay_demo_history_path_for_payload(payload)
    if not path:
        return
    line = dict(payload)
    line["_history_logged_ts"] = time.time()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except IOError:
        pass


def price_zone_key(price: float, zone_points: float) -> int:
    """Ví dụ zone_points=200, giá 66450 → zone 66400 (bucket theo bước lưới)."""
    try:
        z = float(zone_points)
        p = float(price)
        if z <= 0:
            return int(p)
        return int((p // z) * z)
    except Exception:
        return 0


def _overwrite_relay_demo_snapshot(out: Dict[str, Any]) -> None:
    """
    Thay thế hoàn toàn file snapshot demo inverse: ghi atomic (tmp → replace).
    Không xóa file trước — tránh cửa sổ race khi live đọc giữa lúc demo ghi (file rỗng / thiếu).
    Không merge — mỗi lần gọi là một bộ relay_id mới.
    """
    _atomic_write(RELAY_DEMO_FILE, out)


def demo_write_inverse_relay_file(config: Dict[str, Any], gate_features: Dict[str, Any]) -> None:
    """
    Ghi v5_relay_demo.json khi demo vừa đặt cặp pending stop (BUY_STOP + SELL_STOP).
    Hai tín hiệu ngược demo (cùng giá, đổi loại lệnh); grid_preview_inverse đổi buy_price/sell_price.
    Mỗi lần ghi: xóa snapshot cũ, ghi lại toàn bộ — relay_id / relay_id_buy_limit / relay_id_sell_limit là UUID mới.
    """
    gpr = gate_features.get("grid_preview") if isinstance(gate_features.get("grid_preview"), dict) else {}
    try:
        buy_demo = float(gpr.get("buy_price"))
        sell_demo = float(gpr.get("sell_price"))
    except (TypeError, ValueError):
        return
    step = float(gpr.get("step") or _step_from_config(config))
    symbol = str(config.get("symbol") or "")
    magic = int(config.get("magic") or 0)
    inv_gpr: Dict[str, Any] = {
        "buy_price": sell_demo,
        "sell_price": buy_demo,
        "step": step,
    }
    for key in ("ref", "anchor"):
        if gpr.get(key) is not None:
            try:
                inv_gpr[key] = float(gpr[key])
            except (TypeError, ValueError):
                pass
    # BUY_LIMIT @ inv buy_price (từ mức SELL_STOP demo); SELL_LIMIT @ inv sell_price (từ BUY_STOP demo).
    relay_id_buy_limit = str(uuid.uuid4())
    relay_id_sell_limit = str(uuid.uuid4())
    relay_id_batch = str(uuid.uuid4())
    out: Dict[str, Any] = {
        "relay_id": relay_id_batch,
        "relay_id_buy_limit": relay_id_buy_limit,
        "relay_id_sell_limit": relay_id_sell_limit,
        "created_ts": time.time(),
        "symbol": symbol,
        "magic": magic,
        "note": "inverse_of_demo_pending_stops",
        "demo_grid_preview": dict(gpr),
        "inverted_signals": [
            {
                "demo": "BUY_STOP",
                "demo_price": buy_demo,
                "inverse": "SELL_STOP",
                "inverse_price": buy_demo,
                "relay_id": relay_id_sell_limit,
            },
            {
                "demo": "SELL_STOP",
                "demo_price": sell_demo,
                "inverse": "BUY_STOP",
                "inverse_price": sell_demo,
                "relay_id": relay_id_buy_limit,
            },
        ],
        "grid_preview_inverse": inv_gpr,
    }
    _overwrite_relay_demo_snapshot(out)
    _append_relay_demo_history(out)


def demo_relay_order_relay_ids(payload: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Đọc payload v5_relay_demo.json / btc_v5_relay_demo.json → (relay_id lô, relay_id BUY_LIMIT, relay_id SELL_LIMIT).
    File cũ chỉ có relay_id: cả ba cùng giá trị (hoặc buy/sell fallback về lô).
    """
    batch = str(payload.get("relay_id") or "").strip()
    rb = str(payload.get("relay_id_buy_limit") or "").strip()
    rs = str(payload.get("relay_id_sell_limit") or "").strip()
    if not batch and (rb or rs):
        batch = rb or rs
    if not rb:
        rb = batch
    if not rs:
        rs = batch
    return batch, rb, rs


def inverse_order_invgrid_comment(
    step_val: float, leg_relay_id: str, *, max_len: int = 31
) -> str:
    """
    Comment MT5 cho một chân inverse: luôn bắt đầu InvGrid_* để cancel_inv_limit_pendings nhận diện.
    Gắn 8 ký tự đầu (không dấu gạch) của leg relay_id; cắt gọn nếu vượt max_len.
    """
    s = str(leg_relay_id or "").replace("-", "")
    tag = (s[:8] if len(s) >= 8 else s) or "________"
    base = f"InvGrid_{step_val:g}_"
    if len(base) + len(tag) > max_len:
        tag = tag[: max(4, max_len - len(base))]
    return base + tag


def _step_from_config(config: Dict[str, Any]) -> float:
    p = config.get("parameters", {})
    steps = p.get("steps")
    if steps is not None:
        if isinstance(steps, list) and len(steps) > 0:
            return float(steps[0])
        return float(steps)
    return float(p.get("step", 5) or 5)


def demo_try_publish_relay(
    config: Dict[str, Any],
    gate_features: Dict[str, Any],
    *,
    relay_zone_points: float,
    ttl_minutes: float,
    verbose: bool = False,
) -> Tuple[Optional[str], str]:
    """
    Dedupe theo zone + TTL (parameters.relay_zone_dedupe_ttl_minutes), không chặn vĩnh viễn:
    cùng zone sau khi hết TTL có thể ghi relay lại (giá đi xa rồi quay về zone cũ).
    ttl_minutes ở đây là TTL file signal; dedupe dùng relay_zone_dedupe_ttl_minutes riêng.
    """
    del verbose  # log cấu trúc do strategy_grid_step_v5 in
    params = config.get("parameters") or {}
    dedupe_ttl_min = float(params.get("relay_zone_dedupe_ttl_minutes", 120) or 0)
    if not gate_features:
        return None, "NO_GATE_FEATURES"
    symbol = config.get("symbol")
    magic = int(config.get("magic") or 0)
    entry = gate_features.get("current_signal_open_price")
    sig_type = gate_features.get("current_signal_type") or gate_features.get("signal_type")
    if entry is None or not symbol or not sig_type:
        return None, "MISSING_ENTRY_OR_SYMBOL"
    try:
        entry_f = float(entry)
    except (TypeError, ValueError):
        return None, "BAD_ENTRY_PRICE"
    zone = price_zone_key(entry_f, float(relay_zone_points))
    zone_s = str(int(zone))
    state = _load_json(RELAY_STATE_FILE, _default_state())
    zone_ts = _normalize_demo_zone_ts(state)
    now = time.time()
    last_ts = zone_ts.get(zone_s, 0.0)
    # dedupe_ttl_min <= 0 → không chặn trùng zone (dễ spam; chỉ dùng khi debug)
    if dedupe_ttl_min > 0 and last_ts > 0 and (now - last_ts) < dedupe_ttl_min * 60.0:
        return None, "RELAY_ALREADY_SENT_IN_ZONE"
    relay_id = str(uuid.uuid4())
    expires = now + float(ttl_minutes) * 60.0
    gpr = gate_features.get("grid_preview") or {}
    payload: Dict[str, Any] = {
        "relay_id": relay_id,
        "created_ts": now,
        "expires_ts": expires,
        "symbol": str(symbol),
        "magic": magic,
        "zone_key": zone,
        "zone_points": float(relay_zone_points),
        "entry_price": entry_f,
        "signal_type": str(sig_type).upper(),
        "step": float(gpr.get("step") or _step_from_config(config)),
        "grid_preview": gpr,
        "gate_score": gate_features.get("score"),
        "gate_reason_snapshot": gate_features.get("block_reason"),
    }
    _atomic_write(RELAY_SIGNAL_FILE, payload)
    _append_relay_signal_history(payload)
    zone_ts[zone_s] = now
    # Dọn bản ghi cũ: 7×TTL nếu có dedupe; không thì 7 ngày (tránh phình file khi TTL=0)
    span_sec = (dedupe_ttl_min * 60.0 * 7) if dedupe_ttl_min > 0 else (7 * 24 * 3600)
    cutoff = now - span_sec
    zone_ts = {k: v for k, v in zone_ts.items() if v >= cutoff}
    zone_ts[zone_s] = now
    state["demo_relayed_zone_ts"] = zone_ts
    state.pop("demo_relayed_zones", None)
    _atomic_write(RELAY_STATE_FILE, state)
    return relay_id, "DEMO_ORDER_SENT"


def relay_read_valid(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Đọc relay còn hiệu lực, symbol/magic khớp, chưa consume."""
    params = config.get("parameters", {})
    if not bool(params.get("signal_relay_enabled", False)):
        return None
    if not os.path.isfile(RELAY_SIGNAL_FILE):
        return None
    try:
        with open(RELAY_SIGNAL_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None
    if not payload or not isinstance(payload, dict):
        return None
    relay_id = payload.get("relay_id")
    if not relay_id:
        return None
    state = _load_json(RELAY_STATE_FILE, _default_state())
    consumed = set(state.get("live_consumed_relay_ids") or [])
    if relay_id in consumed:
        return None
    if time.time() > float(payload.get("expires_ts") or 0):
        return None
    if str(payload.get("symbol")) != str(config.get("symbol")):
        return None
    if int(payload.get("magic") or -1) != int(config.get("magic") or 0):
        return None
    return payload


def relay_consume(relay_id: str, *, verbose: bool = False) -> None:
    """Live đã mirror xong — đánh dấu consume và xóa file signal nếu trùng id."""
    if not relay_id:
        return
    state = _load_json(RELAY_STATE_FILE, _default_state())
    consumed = list(state.get("live_consumed_relay_ids") or [])
    if relay_id not in consumed:
        consumed.append(relay_id)
    state["live_consumed_relay_ids"] = consumed
    _atomic_write(RELAY_STATE_FILE, state)
    try:
        if os.path.isfile(RELAY_SIGNAL_FILE):
            with open(RELAY_SIGNAL_FILE, "r", encoding="utf-8") as f:
                cur = json.load(f)
            if isinstance(cur, dict) and cur.get("relay_id") == relay_id:
                os.remove(RELAY_SIGNAL_FILE)
    except Exception:
        pass
    if verbose:
        print(f"📡 [Relay] live đã consume relay_id={relay_id[:8]}…")


def relay_to_gate_features(relay: Dict[str, Any]) -> Dict[str, Any]:
    """Features tối thiểu cho log / duplicate check (không chấm lại điểm)."""
    return {
        "ready": True,
        "score": relay.get("gate_score"),
        "current_signal_type": relay.get("signal_type"),
        "signal_type": relay.get("signal_type"),
        "current_signal_open_price": relay.get("entry_price"),
        "grid_preview": relay.get("grid_preview") or {},
        "relay_id": relay.get("relay_id"),
        "relay_zone_key": relay.get("zone_key"),
        "score_breakdown": {"add": [], "sub": [], "note": "from_demo_relay"},
        "blocked": False,
        "block_reason": None,
        "min_gap_ok": True,
    }
