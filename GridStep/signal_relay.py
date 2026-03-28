"""
Demo → Live relay: demo phát tín hiệu sau khi gửi lệnh thành công; live chỉ mirror theo relay.

File:
- v5_relay_signal.json — payload mới nhất chờ live
- v5_relay_state.json — zone đã relay (demo) + relay_id đã consume (live)
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RELAY_SIGNAL_FILE = os.path.join(SCRIPT_DIR, "v5_relay_signal.json")
RELAY_STATE_FILE = os.path.join(SCRIPT_DIR, "v5_relay_state.json")


def _default_state() -> Dict[str, Any]:
    return {"demo_relayed_zones": [], "live_consumed_relay_ids": []}


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
    Gọi sau khi demo có pending/position mới. Mỗi zone chỉ relay 1 lần (demo_relayed_zones).
    Trả về (relay_id hoặc None, mã lý do cho log [RELAY]).
    """
    del verbose  # log cấu trúc do strategy_grid_step_v5 in
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
    state = _load_json(RELAY_STATE_FILE, _default_state())
    demo_zones: List = list(state.get("demo_relayed_zones") or [])
    if zone in demo_zones:
        return None, "RELAY_ALREADY_SENT_IN_ZONE"
    relay_id = str(uuid.uuid4())
    now = time.time()
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
    demo_zones.append(zone)
    state["demo_relayed_zones"] = demo_zones
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
