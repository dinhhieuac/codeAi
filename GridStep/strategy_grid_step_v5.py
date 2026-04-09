"""
Grid Step Trading Bot V5.

V5 tái sử dụng toàn bộ logic từ strategy_grid_step.py, nhưng:
- chấm điểm XAUUSD: scores.py (`xauusd_grid_step_v5_score_detailed`, `xauusd_grid_step_v5_is_blocked`)
- dùng file config riêng: configs/config_grid_step_v5.json
- tách file cooldown/pause riêng cho phiên bản v5
- wrapper (vd strategy_grid_step_btc_v5) gọi configure_grid_step_v5_paths() để tách relay/live log.
- parameters: v5_log_debug (alias logDebug, default false) — false: một dòng score/rules/kết luận; true: full [SIGNAL][SCORE]...
- v5_role=live: không đọc history / không chấm điểm trên account live — chỉ đăng nhập MT5 (account trong config),
  đọc file relay do demo ghi; flat → mirror relay; có grid → chỉ chạy base strategy (stub gate, không score).
  Kiểm tra zone (nếu không blind) = so giá mid với zone_key trong relay, không dựng lại grid preview trên live.
"""
import copy
import os
import sys
import time
import json
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone

import strategy_grid_step as base
import signal_relay
from scores import (
    normalize_preferred_direction_v5,
    xauusd_grid_step_v5_is_blocked,
    xauusd_grid_step_v5_score_detailed,
)

_normalize_preferred_direction = normalize_preferred_direction_v5
_score_signal_detailed = xauusd_grid_step_v5_score_detailed


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
base.COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown_v5.json")
base.PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause_v5.json")
LIVE_LOG_FILE = os.path.join(SCRIPT_DIR, "v5_live_entry_log.jsonl")
LIVE_STATE_FILE = os.path.join(SCRIPT_DIR, "v5_live_state.json")


def configure_grid_step_v5_paths(
    *,
    relay_signal_file=None,
    relay_state_file=None,
    relay_history_log_file=None,
    relay_demo_file=None,
    relay_demo_history_log_file=None,
    live_log_file=None,
    live_state_file=None,
):
    """
    Trỏ file relay + live entry log/state (dùng trong strategy_grid_step_btc_v5).
    Gọi ngay sau `import strategy_grid_step_v5`.
    relay_demo_history_log_file: base path (vd v5_relay_demo_history.jsonl); append thực tế vào
    v5_relay_demo_history_<SYMBOL>.jsonl theo payload.symbol.
    """
    global LIVE_LOG_FILE, LIVE_STATE_FILE
    if relay_signal_file is not None:
        signal_relay.RELAY_SIGNAL_FILE = relay_signal_file
    if relay_state_file is not None:
        signal_relay.RELAY_STATE_FILE = relay_state_file
    if relay_history_log_file is not None:
        signal_relay.RELAY_SIGNAL_HISTORY_LOG = relay_history_log_file
    if relay_demo_file is not None:
        signal_relay.RELAY_DEMO_FILE = relay_demo_file
    if relay_demo_history_log_file is not None:
        signal_relay.RELAY_DEMO_HISTORY_LOG = relay_demo_history_log_file
    if live_log_file is not None:
        LIVE_LOG_FILE = live_log_file
    if live_state_file is not None:
        LIVE_STATE_FILE = live_state_file


def _relay_zone_matches_current(config, relay_payload):
    """
    Live (không blind): zone của giá thị trường (mid bid/ask) phải khớp zone_key trong relay từ demo.
    Không tính entry/grid preview trên account live — chỉ so giá với cùng relay_zone_points như demo.
    """
    params = config.get("parameters", {})
    zp = float(params.get("relay_zone_points") or 200)
    tick = mt5.symbol_info_tick(config["symbol"])
    if tick is None:
        return False
    mid = (float(tick.bid) + float(tick.ask)) / 2.0
    want = int(relay_payload.get("zone_key") or 0)
    got = signal_relay.price_zone_key(mid, zp)
    return want == got


def _fetch_closed_positions_list(
    symbol, magic, comment_prefix="GridStep", days_back=3, max_positions=500
):
    """
    Lấy trade đã đóng (position-level) từ MT5 history.
    Sort theo close_time giảm dần; cắt max_positions (không dùng slice này cho chuỗi tín hiệu — chỉ cho state).
    """
    to_date = datetime.now()
    from_date = to_date - timedelta(days=max(1, int(days_back)))
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*")
    if not deals:
        return []

    by_pos = {}
    for d in deals:
        if getattr(d, "magic", 0) != magic:
            continue
        if getattr(d, "symbol", "") != symbol:
            continue
        c = (getattr(d, "comment", "") or "").strip()
        if comment_prefix and not c.startswith(comment_prefix):
            continue
        pid = getattr(d, "position_id", None) or getattr(d, "position", None)
        if not pid:
            continue
        row = by_pos.setdefault(pid, {"in": None, "out": None})
        if d.entry == mt5.DEAL_ENTRY_IN:
            t = getattr(d, "time", None)
            prev = row["in"]
            if prev is None or (t is not None and t <= prev["time"]):
                row["in"] = {
                    "time": t,
                    "price": float(getattr(d, "price", 0) or 0),
                    "type": "BUY" if int(getattr(d, "type", -1)) == int(mt5.DEAL_TYPE_BUY) else "SELL",
                    "volume": float(getattr(d, "volume", 0) or 0),
                }
        elif d.entry == mt5.DEAL_ENTRY_OUT:
            t = getattr(d, "time", None)
            prev = row["out"]
            if prev is None or (t is not None and t >= prev["time"]):
                row["out"] = {
                    "time": t,
                    "price": float(getattr(d, "price", 0) or 0),
                    "profit": float(getattr(d, "profit", 0) or 0),
                    "commission": float(getattr(d, "commission", 0) or 0),
                    "swap": float(getattr(d, "swap", 0) or 0),
                }

    closed = []
    for pid, r in by_pos.items():
        if not r["in"] or not r["out"]:
            continue
        net_profit = r["out"]["profit"] + r["out"]["commission"] + r["out"]["swap"]
        closed.append(
            {
                "position_id": int(pid),
                "type": r["in"]["type"],
                "volume": r["in"]["volume"],
                "open_time": int(r["in"]["time"] or 0),
                "open_price": float(r["in"]["price"]),
                "close_time": int(r["out"]["time"] or 0),
                "close_price": float(r["out"]["price"]),
                "profit": float(r["out"]["profit"]),
                "commission": float(r["out"]["commission"]),
                "swap": float(r["out"]["swap"]),
                "net_profit": float(net_profit),
            }
        )
    closed.sort(key=lambda x: x["close_time"], reverse=True)
    cap = max(1, int(max_positions))
    return closed[:cap]


def _fetch_closed_trades(symbol, magic, history_window=20, comment_prefix="GridStep", days_back=3):
    """Tương thích cũ: chỉ lấy history_window bản ghi đầu (theo close_time)."""
    raw = _fetch_closed_positions_list(
        symbol, magic, comment_prefix=comment_prefix, days_back=days_back, max_positions=max(int(history_window), 1)
    )
    return raw[: max(1, int(history_window))]


def _calc_streak(closed):
    win_streak = 0
    loss_streak = 0
    for tr in closed:
        if tr["net_profit"] > 0:
            if loss_streak == 0:
                win_streak += 1
            else:
                break
        else:
            if win_streak == 0:
                loss_streak += 1
            else:
                break
    return win_streak, loss_streak


def _v5_gate_step_val(config):
    p = config.get("parameters", {})
    steps = p.get("steps")
    if steps is not None:
        if isinstance(steps, list) and len(steps) > 0:
            return float(steps[0])
        return float(steps)
    return float(p.get("step", 5) or 5)


def _v5_preview_grid_levels(config):
    """
    Giá BUY_STOP / SELL_STOP dự kiến (cùng công thức anchor + ref như strategy_grid_step),
    không hủy pending — chỉ đọc giá để chấm entry score.
    """
    symbol = config["symbol"]
    magic = config["magic"]
    step_val = _v5_gate_step_val(config)
    step_filter = step_val
    info = mt5.symbol_info(symbol)
    if not info:
        return None
    current_price = base.get_grid_anchor_price(symbol, magic, step_filter)
    ref = round(current_price / step_val) * step_val
    ref = round(ref, info.digits)
    buy_price = round(ref + step_val, info.digits)
    sell_price = round(ref - step_val, info.digits)
    return {
        "buy_price": buy_price,
        "sell_price": sell_price,
        "ref": ref,
        "step": step_val,
        "anchor": float(current_price),
    }


def _v5_step_filter_for_gate(config):
    """Cùng kênh step đầu với preview grid (GridStep_N hoặc None)."""
    p = config.get("parameters", {})
    steps = p.get("steps")
    if steps is not None:
        if isinstance(steps, list) and len(steps) > 0:
            return float(steps[0])
        return float(steps)
    return None


def _open_positions_as_signals(symbol, magic, step_filter):
    """Vị thế đang mở — tín hiệu đã khớp, có open_time thật."""
    positions = base.get_positions_for_step(symbol, magic, step_filter)
    out = []
    for p in positions or []:
        out.append(
            {
                "position_id": int(getattr(p, "ticket", 0) or 0),
                "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                "open_time": int(getattr(p, "time", 0) or 0),
                "open_price": float(p.price_open),
                "close_time": 0,
                "source": "open_position",
            }
        )
    return out


def _merge_signal_history(open_signals, closed_positions, signal_window):
    """
    Merge tín hiệu thật: position đang mở + lịch sử đóng (theo open_time).
    Không sort theo close_time trước; closed_positions là từ _fetch_closed_positions_list (đã sort close_time).
    """
    merged = []
    seen = set()
    for s in open_signals:
        pid = s["position_id"]
        if pid and pid not in seen:
            seen.add(pid)
            merged.append(s)
    for c in closed_positions:
        pid = int(c.get("position_id", 0) or 0)
        if pid and pid not in seen:
            seen.add(pid)
            merged.append(
                {
                    "position_id": pid,
                    "type": c["type"],
                    "open_time": int(c["open_time"]),
                    "open_price": float(c["open_price"]),
                    "close_time": int(c.get("close_time") or 0),
                    "source": "closed_history",
                }
            )
    merged.sort(key=lambda x: x["open_time"], reverse=True)
    win = max(1, int(signal_window))
    return merged[:win]


def _find_previous_signal(
    signal_history,
    current_signal_type,
    current_signal_open_price,
    price_tolerance,
    grid_step=None,
    open_same_dir_grid_step_mult=None,
):
    """
    Tín hiệu đứng trước current_entry (không lấy nhầm leg đang mở trùng chu kỳ hiện tại).

    Bỏ qua phần tử đầu khi:
    - cùng hướng và |giá - current| <= price_tolerance (trùng mức stop); hoặc
    - source=open_position, cùng hướng, và giá trong ~một bước lưới so với current stop
      (vì tolerance theo point có thể << grid_step, ví dụ XAU step=5).
    """
    if not signal_history:
        return None, 0
    cur_type = str(current_signal_type or "").upper()
    cur_px = float(current_signal_open_price)
    tol = float(price_tolerance)
    gs = float(grid_step) if grid_step is not None and float(grid_step) > 0 else None
    mult = (
        float(open_same_dir_grid_step_mult)
        if open_same_dir_grid_step_mult is not None and float(open_same_dir_grid_step_mult) > 0
        else 1.05
    )
    open_same_dir_max_dist = (max(tol, gs * mult) if gs is not None else tol)

    i = 0
    while i < len(signal_history):
        s = signal_history[i]
        st = str(s.get("type", "")).upper()
        opx = float(s.get("open_price", 0) or 0)
        src = str(s.get("source", "") or "")
        dist = abs(opx - cur_px)

        if st != cur_type:
            break

        if dist <= tol:
            i += 1
            continue

        if src == "open_position" and gs is not None and dist <= open_same_dir_max_dist:
            i += 1
            continue

        break

    prev = signal_history[i] if i < len(signal_history) else None
    return prev, i


def _compute_grid_entry_signal(preview, tick, pendings):
    """
    Tín hiệu vào lưới gần nhất (cùng logic với base: 2 stop; chọn phía gần mid).
    Thời gian: time_setup của pending (lúc grid được treo) nếu có; không thì tick.time.
    """
    bid = float(tick.bid)
    ask = float(tick.ask)
    mid = (bid + ask) / 2.0
    buy_price = float(preview["buy_price"])
    sell_price = float(preview["sell_price"])
    if abs(mid - buy_price) <= abs(mid - sell_price):
        cur_type = "BUY"
        cur_px = buy_price
    else:
        cur_type = "SELL"
        cur_px = sell_price
    ts = int(getattr(tick, "time", 0) or 0) or int(time.time())
    ts_src = "tick_time"
    if pendings:
        setups = []
        for o in pendings:
            t = int(getattr(o, "time_setup", 0) or 0)
            if t > 0:
                setups.append(t)
        if setups:
            ts = min(setups)
            ts_src = "pending_time_setup_min"
    return {
        "current_signal_type": cur_type,
        "current_signal_open_price": cur_px,
        "current_signal_open_ts": ts,
        "current_signal_ts_source": ts_src,
        "nearest_stop_rule": "min_distance_to_mid",
        "mid_price": mid,
    }


def _build_v5_features(
    closed_state,
    signal_history,
    prev_signal,
    entry_signal,
    preferred_direction,
    min_gap_minutes,
    preview,
):
    """
    State: từ closed_state (đã sort theo close_time — slice từ history_window).
    Entry: tín hiệu hiện tại từ _compute_grid_entry_signal; prev từ _find_previous_signal (bỏ trùng entry hiện tại).
    """
    c5 = closed_state[:5]
    c10 = closed_state[:10]
    if not c5:
        return {"ready": False, "reason": "not_enough_closed_trades"}

    last_closed = c5[0]
    sum5 = sum(t["net_profit"] for t in c5)
    sum10 = sum(t["net_profit"] for t in c10) if c10 else 0.0
    win5 = sum(1 for t in c5 if t["net_profit"] > 0)
    win10 = sum(1 for t in c10 if t["net_profit"] > 0) if c10 else 0
    gross_profit10 = sum(t["net_profit"] for t in c10 if t["net_profit"] > 0)
    gross_loss10 = abs(sum(t["net_profit"] for t in c10 if t["net_profit"] <= 0))
    pf10 = (gross_profit10 / gross_loss10) if gross_loss10 > 0 else float("inf")
    win_streak, loss_streak = _calc_streak(closed_state)

    last_trade_result = "Win" if last_closed["net_profit"] > 0 else "Loss"

    pref = _normalize_preferred_direction(preferred_direction)

    cur_type = str(entry_signal.get("current_signal_type") or "SELL").upper()
    cur_px = float(entry_signal["current_signal_open_price"])
    cur_ts = int(entry_signal.get("current_signal_open_ts") or 0)

    prev_sig = prev_signal
    prev_type = prev_sig["type"] if prev_sig else None
    prev_open = float(prev_sig["open_price"]) if prev_sig else cur_px
    prev_open_ts = int(prev_sig["open_time"]) if prev_sig else 0
    prev_src = prev_sig.get("source") if prev_sig else None

    same_dir = bool(prev_type and cur_type == prev_type)
    reverse_dir = bool(prev_type and cur_type != prev_type)
    gap_min = (float(cur_ts) - float(prev_open_ts)) / 60.0 if prev_sig and prev_open_ts else 999.0
    min_gap_ok = gap_min >= float(min_gap_minutes)

    prev_close_ts = int(prev_sig.get("close_time") or 0) if prev_sig else 0
    if prev_sig and prev_open_ts:
        if prev_close_ts > 0:
            prev_duration_min = max(0.0, (float(prev_close_ts) - float(prev_open_ts)) / 60.0)
            gap_from_prev_close_min = max(0.0, (float(cur_ts) - float(prev_close_ts)) / 60.0)
        else:
            prev_duration_min = max(0.0, (float(cur_ts) - float(prev_open_ts)) / 60.0)
            gap_from_prev_close_min = None
    else:
        prev_duration_min = None
        gap_from_prev_close_min = None

    cur_below_prev = cur_px < prev_open
    cur_above_prev = cur_px > prev_open

    return {
        "ready": True,
        "min_gap_minutes": float(min_gap_minutes),
        "last_trade_result": last_trade_result,
        "sum_last_5_net_profit": sum5,
        "avg_last_5_net_profit": (sum5 / len(c5)),
        "win_count_last_5": win5,
        "loss_count_last_5": len(c5) - win5,
        "sum_last_10_net_profit": sum10,
        "avg_last_10_net_profit": (sum10 / len(c10)) if c10 else 0.0,
        "win_rate_last_10": (win10 / len(c10)) if c10 else 0.0,
        "profit_factor_last_10": pf10,
        "win_streak": win_streak,
        "loss_streak": loss_streak,
        "signal_type": cur_type,
        "preferred_direction": pref,
        "current_signal_type": cur_type,
        "current_signal_open_price": cur_px,
        "current_signal_open_ts": cur_ts,
        "current_signal_ts_source": entry_signal.get("current_signal_ts_source"),
        "prev_signal_type": prev_type,
        "prev_signal_open_price": prev_open,
        "prev_signal_open_ts": prev_open_ts,
        "prev_signal_source": prev_src,
        "signal_history_len": len(signal_history),
        "same_direction_as_prev_signal": same_dir,
        "reverse_direction_from_prev_signal": reverse_dir,
        "gap_minutes_from_prev_signal": gap_min,
        "gap_from_prev_signal_min": gap_min,
        "prev_duration_min": prev_duration_min,
        "gap_from_prev_close_min": gap_from_prev_close_min,
        "min_gap_ok": min_gap_ok,
        "current_open_below_prev_open": cur_below_prev,
        "current_open_above_prev_open": cur_above_prev,
        "grid_preview": preview,
        "entry_signal_meta": {
            "nearest_stop_rule": entry_signal.get("nearest_stop_rule"),
            "mid_price": entry_signal.get("mid_price"),
        },
    }


def _score_signal(features):
    s, _ = _score_signal_detailed(features)
    return s


def _is_blocked(features, max_loss_streak=2, hard_block_sum10_negative=True, hard_block_min_gap=True):
    return xauusd_grid_step_v5_is_blocked(
        features,
        max_loss_streak=max_loss_streak,
        hard_block_sum10_negative=hard_block_sum10_negative,
        hard_block_min_gap=hard_block_min_gap,
    )


def _closed_list_signature(closed):
    """Chữ ký lịch sử đóng: đổi khi có lệnh đóng mới (hoặc số bản ghi đổi)."""
    if not closed:
        return (0, 0, 0)
    top = closed[0]
    return (
        int(top.get("close_time", 0) or 0),
        int(top.get("position_id", 0) or 0),
        len(closed),
    )


def _v5_gate_cache_key(config, v5_role):
    return (
        str(v5_role),
        str(config.get("symbol") or ""),
        int(config.get("magic") or 0),
        int(config.get("account") or 0),
    )


def _v5_peek_any_out_deal_after(symbol, magic, comment_prefix, since_ts: int) -> bool:
    """
    True nếu có deal OUT (đóng) sau since_ts — cần build lại full closed list.
    Chỉ quét cửa sổ thời gian ngắn sau mốc since_ts (nhẹ hơn build toàn bộ by_pos).
    """
    if since_ts <= 0:
        return True
    try:
        from_dt = datetime.utcfromtimestamp(max(0, since_ts - 5))
        to_dt = datetime.now()
        deals = mt5.history_deals_get(from_dt, to_dt)
        if deals is None:
            deals = mt5.history_deals_get(from_dt, to_dt, group="*")
        for d in deals or []:
            if getattr(d, "magic", 0) != magic:
                continue
            if getattr(d, "symbol", "") != symbol:
                continue
            c = (getattr(d, "comment", "") or "").strip()
            if comment_prefix and not c.startswith(comment_prefix):
                continue
            if int(getattr(d, "entry", -1)) != int(mt5.DEAL_ENTRY_OUT):
                continue
            t = int(getattr(d, "time", 0) or 0)
            if t > since_ts:
                return True
    except Exception:
        return True
    return False


def _v5_try_return_cached_gate_without_full_fetch(
    config, v5_role, symbol, magic, history_comment_prefix
):
    """
    Khi đã có cache score và peek không thấy deal OUT mới → trả cache, không gọi _fetch_closed_positions_list.
    """
    params = config.get("parameters", {})
    if not bool(params.get("v5_rescore_only_on_new_close", False)):
        return None
    ck = _v5_gate_cache_key(config, v5_role)
    c = getattr(run, "_v5_gate_score_cache", None)
    if not isinstance(c, dict) or c.get("key") != ck:
        return None
    lc_ts = int(c.get("last_close_ts") or 0)
    if lc_ts <= 0:
        return None
    if _v5_peek_any_out_deal_after(symbol, magic, history_comment_prefix, lc_ts):
        return None
    _v5_log_gate_no_new_close_throttled()
    feat = copy.deepcopy(c["features"])
    feat["v5_score_reused_no_new_close"] = True
    feat["v5_gate_history_skip"] = "peek_no_new_out_deal"
    return c["allow"], c["gate_reason"], feat


def _v5_log_gate_no_new_close_throttled():
    """
    Rule: chỉ tính lại score khi có lệnh đóng mới (demo). Nếu không → một dòng log ngắn, throttle ~30s.
    """
    msg = "📚 [V5 Gate] chưa có lệnh đóng mới"
    now_m = time.monotonic()
    prev = getattr(run, "_v5_gate_no_close_log", None)
    if prev is not None and prev[0] == msg and (now_m - prev[1]) < 30.0:
        return
    print(msg)
    run._v5_gate_no_close_log = (msg, now_m)


def _v5_live_gate_features_no_relay():
    """Live đang có grid: không chấm điểm từ account; chỉ để base strategy quản lý lệnh."""
    return {
        "ready": True,
        "score": None,
        "score_breakdown": {"add": [], "sub": [], "note": "relay_only_live_has_grid"},
        "blocked": False,
        "block_reason": None,
        "min_gap_ok": True,
        "current_signal_type": None,
        "signal_type": None,
        "current_signal_open_price": None,
        "grid_preview": {},
        "relay_id": None,
    }


def _v5_history_score_gate(config):
    """
    Chỉ dùng cho v5_role=demo: đọc history session hiện tại, tính score/log, không chặn lệnh (demo_mode_no_gate).
    Live không gọi hàm này — live chỉ nhận tín hiệu qua relay.
    """
    params = config.get("parameters", {})
    v5_role = str(params.get("v5_role", "demo")).lower().strip()
    if v5_role != "demo":
        return False, "only_demo_uses_history_gate", {}
    history_window = int(params.get("history_window", 20))
    signal_history_window = int(params.get("signal_history_window", history_window))
    history_days_back = int(params.get("history_days_back", 7))
    max_closed_fetch = max(
        int(params.get("max_closed_fetch", 500)),
        history_window,
        signal_history_window,
        5,
    )
    min_gap_minutes = float(params.get("min_gap_minutes", 5))
    max_loss_streak = int(params.get("max_loss_streak", 2))
    preferred_direction = _normalize_preferred_direction(params.get("preferred_direction", "SELL"))
    history_comment_prefix = str(params.get("history_comment_prefix", "") or "").strip() or None
    symbol = config["symbol"]
    magic = config["magic"]

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False, "tick_none", {}

    gate_history_source_line = None
    _r = _v5_try_return_cached_gate_without_full_fetch(
        config, v5_role, symbol, magic, history_comment_prefix
    )
    if _r is not None:
        return _r
    closed = _fetch_closed_positions_list(
        symbol,
        magic,
        comment_prefix=history_comment_prefix,
        days_back=history_days_back,
        max_positions=max_closed_fetch,
    )
    gate_history_source_line = (
        f"📚 [V5 Gate] history source=current account={config.get('account')} "
        f"symbol={symbol} magic={magic} window={history_window} days_back={history_days_back}"
    )
    if len(closed) < 5:
        if gate_history_source_line:
            print(gate_history_source_line)
        try:
            last_closed_time = None
            if closed:
                ts = int(closed[0].get("close_time", 0) or 0)
                if ts > 0:
                    last_closed_time = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            print(
                f"📚 [V5 Gate] history loaded: closed_count={len(closed)} "
                f"(need>=5, window={history_window}) last_closed={last_closed_time}"
            )
        except Exception:
            pass
        return True, f"demo_insufficient_history:{len(closed)}", {"closed_count": len(closed), "role": v5_role}

    sig = _closed_list_signature(closed)
    cache_key = _v5_gate_cache_key(config, v5_role)
    rescore_only = bool(params.get("v5_rescore_only_on_new_close", False))

    def _cache_put(allow, gate_reason, features, closed_for_ts=None):
        if not rescore_only:
            return
        ts = 0
        if closed_for_ts and len(closed_for_ts) > 0:
            ts = int(closed_for_ts[0].get("close_time", 0) or 0)
        try:
            run._v5_gate_score_cache = {
                "key": cache_key,
                "sig": sig,
                "allow": allow,
                "gate_reason": gate_reason,
                "features": copy.deepcopy(features),
                "last_close_ts": ts,
            }
        except Exception:
            pass

    if rescore_only:
        c = getattr(run, "_v5_gate_score_cache", None)
        if isinstance(c, dict) and c.get("key") == cache_key and c.get("sig") == sig:
            _v5_log_gate_no_new_close_throttled()
            try:
                if (not c.get("last_close_ts")) and closed and closed[0].get("close_time"):
                    c2 = dict(c)
                    c2["last_close_ts"] = int(closed[0]["close_time"])
                    run._v5_gate_score_cache = c2
            except Exception:
                pass
            feat = copy.deepcopy(c["features"])
            feat["v5_score_reused_no_new_close"] = True
            return c["allow"], c["gate_reason"], feat

    if gate_history_source_line:
        print(gate_history_source_line)
    try:
        last_closed_time = None
        if closed:
            ts = int(closed[0].get("close_time", 0) or 0)
            if ts > 0:
                last_closed_time = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"📚 [V5 Gate] history loaded: closed_count={len(closed)} "
            f"(need>=5, window={history_window}) last_closed={last_closed_time}"
        )
    except Exception:
        pass

    closed_state = closed[: max(1, history_window)]

    step_filter = _v5_step_filter_for_gate(config)
    signal_closed_for_merge = closed

    open_sigs = _open_positions_as_signals(symbol, magic, step_filter)
    signal_history = _merge_signal_history(open_sigs, signal_closed_for_merge, signal_history_window)

    preview = _v5_preview_grid_levels(config)
    if preview is None:
        return False, "preview_grid_failed", {"closed_count": len(closed), "role": v5_role}

    pendings = base.get_pending_orders(symbol, magic, step_filter)
    entry_signal = _compute_grid_entry_signal(preview, tick, pendings)

    info = mt5.symbol_info(symbol)
    point = float(getattr(info, "point", 0.01) or 0.01) if info else 0.01
    digits = int(getattr(info, "digits", 5) or 5) if info else 5
    tol_cfg = params.get("prev_signal_price_tolerance")
    if tol_cfg is not None and float(tol_cfg) > 0:
        price_tol = float(tol_cfg)
    else:
        price_tol = max(2.0 * point, 10 ** (-digits) * 0.5)

    grid_step = preview.get("step")
    open_mult = params.get("prev_signal_open_same_dir_grid_step_mult")

    prev_signal, prev_leading_skipped = _find_previous_signal(
        signal_history,
        entry_signal["current_signal_type"],
        entry_signal["current_signal_open_price"],
        price_tol,
        grid_step=grid_step,
        open_same_dir_grid_step_mult=open_mult,
    )

    features = _build_v5_features(
        closed_state,
        signal_history,
        prev_signal,
        entry_signal,
        preferred_direction,
        min_gap_minutes,
        preview,
    )
    features["state_history_source"] = "current_account"
    features["signal_closed_merge_source"] = "same_as_state_fetch"
    features["signal_history_window"] = signal_history_window
    features["prev_signal_price_tolerance"] = price_tol
    features["prev_signal_leading_overlap_skipped"] = prev_leading_skipped
    _om = float(open_mult) if open_mult is not None and float(open_mult) > 0 else 1.05
    features["prev_signal_open_same_dir_max_dist"] = (
        max(price_tol, float(grid_step) * _om) if grid_step is not None and float(grid_step) > 0 else None
    )
    if not features.get("ready"):
        return False, str(features.get("reason", "feature_not_ready")), features

    hard_block_sum10 = bool(params.get("v5_hard_block_sum10_negative", True))
    hard_block_min_gap = bool(params.get("v5_hard_block_min_gap", True))
    blocked, block_reason = _is_blocked(
        features,
        max_loss_streak=max_loss_streak,
        hard_block_sum10_negative=hard_block_sum10,
        hard_block_min_gap=hard_block_min_gap,
    )
    score, score_breakdown = _score_signal_detailed(features)
    features["score"] = score
    features["score_breakdown"] = score_breakdown
    features["blocked"] = blocked
    features["block_reason"] = block_reason

    # Demo: luôn cho chạy bot gốc, nhưng vẫn trả đủ feature/score để log quan sát.
    _cache_put(True, "demo_mode_no_gate", features, closed_for_ts=closed)
    return True, "demo_mode_no_gate", features


def _v5_features_qualify_live_equivalent(features: dict, params: dict) -> bool:
    """
    Tiêu chí “đủ điểm như cổng live” để demo phát relay sớm: ready, không blocked,
    medium + entry score, preferred direction (nếu cấu hình).
    Dùng trên demo để phát relay ngay khi đủ điểm (không chờ MT5 đặt lệnh).
    """
    if not features or not features.get("ready"):
        return False
    if features.get("blocked"):
        return False
    try:
        sc = int(features.get("score")) if features.get("score") is not None else None
    except (TypeError, ValueError):
        sc = None
    if sc is None:
        return False
    medium_thr = int(params.get("medium_score_threshold", 5))
    entry_thr = int(params.get("entry_score_threshold", 6))
    if sc < medium_thr:
        return False
    if sc < entry_thr:
        return False
    allow_reverse = bool(params.get("allow_reverse_entry", True))
    preferred = str(params.get("preferred_direction", "BOTH") or "BOTH").upper()
    cur_sig = str(features.get("current_signal_type") or features.get("signal_type") or "").upper()
    if not allow_reverse and preferred in ("BUY", "SELL") and cur_sig != preferred:
        return False
    return True


def _append_live_entry_log(record):
    try:
        with open(LIVE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except IOError:
        pass


def _snapshot_bot_orders_positions(symbol, magic):
    orders = mt5.orders_get(symbol=symbol) or []
    orders = [o for o in orders if getattr(o, "magic", 0) == magic]
    positions = mt5.positions_get(symbol=symbol) or []
    positions = [p for p in positions if getattr(p, "magic", 0) == magic]
    pending_tickets = sorted(int(getattr(o, "ticket", 0) or 0) for o in orders)
    position_tickets = sorted(int(getattr(p, "ticket", 0) or 0) for p in positions)
    return pending_tickets, position_tickets


def _live_has_equivalent_order(symbol, magic, step_filter, signal_type, entry_price, price_threshold):
    """
    Live đã có lệnh/position tương ứng tín hiệu: cùng symbol/magic (đã lọc), cùng chiều,
    giá vào gần entry_price trong price_threshold.
    """
    st = str(signal_type or "").upper()
    if st not in ("BUY", "SELL"):
        return False
    try:
        ep = float(entry_price)
    except (TypeError, ValueError):
        return False
    thr = float(price_threshold)

    for p in base.get_positions_for_step(symbol, magic, step_filter) or []:
        ptype = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
        if ptype == st and abs(float(p.price_open) - ep) <= thr:
            return True

    for o in base.get_pending_orders(symbol, magic, step_filter) or []:
        ot = int(getattr(o, "type", -1))
        opr = float(getattr(o, "price_open", 0) or 0)
        if st == "BUY" and ot == mt5.ORDER_TYPE_BUY_STOP and abs(opr - ep) <= thr:
            return True
        if st == "SELL" and ot == mt5.ORDER_TYPE_SELL_STOP and abs(opr - ep) <= thr:
            return True
    return False


def _load_live_state():
    if not os.path.exists(LIVE_STATE_FILE):
        return {}
    try:
        with open(LIVE_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_live_state(state):
    try:
        with open(LIVE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except IOError:
        pass


def _live_entry_cooldown_remaining_seconds(symbol, magic, min_gap_seconds):
    if min_gap_seconds <= 0:
        return 0
    state = _load_live_state()
    key = f"{symbol}:{magic}"
    ts = state.get(key, {}).get("last_entry_ts_utc")
    if not ts:
        return 0
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        remain = int(min_gap_seconds - (now - dt).total_seconds())
        return max(0, remain)
    except (ValueError, TypeError):
        return 0


def _mark_live_entry_now(symbol, magic):
    state = _load_live_state()
    key = f"{symbol}:{magic}"
    state[key] = {
        "last_entry_ts_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    _save_live_state(state)


def _v5_signal_relation(gf):
    """REVERSAL | CONTINUATION | FIRST_SIGNAL"""
    if not gf or not gf.get("ready"):
        return "FIRST_SIGNAL"
    pt = gf.get("prev_signal_type")
    ct = gf.get("current_signal_type") or gf.get("signal_type")
    if not pt or not ct:
        return "FIRST_SIGNAL"
    if str(pt).upper() == str(ct).upper():
        return "CONTINUATION"
    return "REVERSAL"


def _v5_score_decision_label(gf, entry_thr):
    sb = gf.get("score_breakdown") if isinstance(gf.get("score_breakdown"), dict) else {}
    d = sb.get("decision")
    if d in ("EXECUTE", "NEUTRAL", "PROBE", "REJECT"):
        return d
    try:
        sc = int(gf.get("score")) if gf.get("score") is not None else 0
    except (TypeError, ValueError):
        sc = 0
    if sc >= int(entry_thr):
        return "EXECUTE"
    if sc == 3:
        return "NEUTRAL"
    if 1 <= sc <= 2:
        return "PROBE"
    return "REJECT"


def _v5_live_entry_gate_label(score, entry_thr):
    """Chỉ theo điểm vs entry_threshold: QUALIFIED | REJECT (chưa tính hard_block)."""
    try:
        s = int(score) if score is not None else 0
    except (TypeError, ValueError):
        return "?"
    return "QUALIFIED" if s >= int(entry_thr) else "REJECT"


def _v5_effective_live_gate_label(score, entry_thr, blocked):
    """Cổng thực tế cho log: đủ điểm nhưng hard_block → BLOCKED (tránh QUALIFIED + kết_luận không đạt)."""
    if blocked:
        return "BLOCKED"
    return _v5_live_entry_gate_label(score, entry_thr)


def _v5_gate_main_reason_code(gate_reason):
    """Map gate_reason -> MAIN_REASON mã ngắn."""
    gr = str(gate_reason or "")
    if not gr:
        return "UNKNOWN"
    if gr.startswith("blocked:"):
        br = gr.replace("blocked:", "", 1)
        if "loss_streak" in br:
            return "HARD_BLOCK_LOSS_STREAK"
        if "sum_last_10" in br or "deep_negative" in gr:
            return "HARD_BLOCK_SUM10_DEEP_NEGATIVE"
        if "sum_last_5" in br:
            return "HARD_BLOCK_SUM5"
        if "gap" in br:
            return "HARD_BLOCK_MIN_GAP"
        return "HARD_BLOCK"
    if "below_entry_score" in gr or "low_score" in gr:
        return "SCORE_REJECT"
    if gr in ("tick_none", "preview_grid_failed", "feature_not_ready"):
        return "NO_SIGNAL"
    if "need>=" in gr or "closed_trades" in gr:
        return "INSUFFICIENT_HISTORY"
    if gr.startswith("live_maintenance"):
        return "LIVE_MAINTENANCE"
    if gr == "live_relay_ok":
        return "RELAY_OK"
    if "direction_gate" in gr:
        return "DIRECTION_GATE"
    return "GATE_" + gr[:24].replace(" ", "_")


def _v5_grid_action_reason(pre_np, pre_npos, new_p, new_pos, mx, v5_role=None):
    """action, reason_code cho [GRID] khi không có lệnh mới."""
    mx = int(mx or 5)
    if pre_np >= 2 and not new_p:
        # Demo: không dùng mã GRID_FULL_2_PENDING (dễ nhầm với “không đủ điều kiện” score); live giữ mã cũ.
        if str(v5_role or "").lower().strip() == "demo":
            return "NO_NEW_ORDER", "DEMO_SCORE_OK_NO_FILL"
        return "NO_NEW_ORDER", "GRID_FULL_2_PENDING"
    if pre_npos >= mx and not new_pos:
        return "NO_NEW_ORDER", "MAX_POSITIONS_REACHED"
    if new_p or new_pos:
        return "PLACE_ORDER", "NEW_TICKETS"
    return "NO_NEW_ORDER", "GRID_NO_CHANGE"


def _v5_compute_result_main(ctx):
    """(RESULT, MAIN_REASON) cho [V5] dòng đầu."""
    exit_kind = ctx.get("exit_kind") or "normal"
    gate_reason = str(ctx.get("gate_reason") or "")
    if exit_kind == "no_relay_flat":
        return "SKIP", "NO_RELAY"
    if exit_kind == "relay_zone_mismatch":
        return "SKIP", "RELAY_ZONE_MISMATCH"
    if exit_kind == "gate_blocked":
        return "BLOCKED", _v5_gate_main_reason_code(gate_reason)
    if exit_kind == "live_cooldown":
        return "SKIP", "LIVE_COOLDOWN"
    if exit_kind == "dup_skip":
        return "SKIP", "DUPLICATE_PENDING"
    if ctx.get("new_pending") or ctx.get("new_positions"):
        return "NEW_ORDER", "ORDER_PLACED"
    g_act, g_reason = _v5_grid_action_reason(
        ctx.get("pre_np", 0),
        ctx.get("pre_npos", 0),
        ctx.get("new_pending") or [],
        ctx.get("new_positions") or [],
        ctx.get("max_positions", 5),
        ctx.get("v5_role"),
    )
    if g_act == "PLACE_ORDER":
        return "NEW_ORDER", "ORDER_PLACED"
    return "NO_ORDER", g_reason


def _v5_gate_pass_for_log(ctx) -> bool:
    """Cổng tín hiệu (điểm + không hard_block) — dùng để ghi chú log, độc lập với có đặt lệnh hay không."""
    gf = ctx.get("gate_features") or {}
    entry_thr = int(ctx.get("entry_thr") or 6)
    return _v5_ket_luan_dat(gf, entry_thr)


def _v5_ket_luan_dat(gate_features: dict, entry_thr: int) -> bool:
    """
    Khớp kết_luận=đạt trên log demo (_v5_emit_minimal_cycle_log):
    score >= entry_score_threshold và không hard_block.
    Dùng để ghi v5_relay_signal.json khi relay bật.
    """
    if not gate_features:
        return False
    if bool(gate_features.get("blocked")):
        return False
    sc = gate_features.get("score")
    try:
        si = int(sc) if sc is not None else None
    except (TypeError, ValueError):
        return False
    return si is not None and si >= int(entry_thr)


def _v5_param_log_debug(params):
    """True = full block [SIGNAL][SCORE]...; False (default) = một dòng điểm + kết luận. Alias JSON: logDebug."""
    return bool(params.get("v5_log_debug", params.get("logDebug", False)))


def _v5_emit_minimal_cycle_log(ctx, params):
    """
    Chế độ ngắn: điểm, plus/minus rules, live_gate, kết luận đạt/không đạt, RESULT.
    kết_luận=đạt khi score>=entry_threshold và không hard_block (điểm cao vẫn có thể bị block, vd min_gap).
    """
    if not bool(params.get("v5_structured_log", True)):
        return
    gf = ctx.get("gate_features") or {}
    sb = gf.get("score_breakdown") if isinstance(gf.get("score_breakdown"), dict) else {}
    adds = sb.get("add") or []
    subs = sb.get("sub") or []
    entry_thr = int(ctx.get("entry_thr") or 6)
    sc = gf.get("score")
    result, main = _v5_compute_result_main(ctx)
    blocked = bool(gf.get("blocked"))
    lg = _v5_effective_live_gate_label(sc, entry_thr, blocked)
    prof = sb.get("decision") if sb.get("decision") else _v5_score_decision_label(gf, entry_thr)
    plus_s = ",".join(str(x) for x in adds) if adds else "-"
    minus_s = ",".join(str(x) for x in subs) if subs else "-"
    try:
        si = int(sc) if sc is not None else None
    except (TypeError, ValueError):
        si = None
    ok = si is not None and si >= entry_thr and not blocked
    concl = "đạt" if ok else "không đạt"
    blk = ""
    if blocked:
        blk = f" | block={gf.get('block_reason') or 'yes'}"
    print(
        f"[V5] score={sc} | profile={prof} | +[{plus_s}] | -[{minus_s}] | "
        f"live_gate={lg}{blk} | kết_luận={concl} | RESULT={result} | {main}"
    )
    print("")


def _v5_emit_structured_cycle_log(ctx, params):
    """
    Log một vòng: RESULT / MAIN_REASON + [SIGNAL][SCORE][CONTEXT][BLOCK][GRID][RELAY][LIVE_CHECK].
    ctx: dict từ run loop (exit_kind, gate_*, grid_*, relay_*, ...).
    """
    if not bool(params.get("v5_structured_log", True)):
        return
    compact = bool(params.get("v5_compact_cycle_log", False))
    gf = ctx.get("gate_features") or {}
    sb = gf.get("score_breakdown") if isinstance(gf.get("score_breakdown"), dict) else {}
    adds = sb.get("add") or []
    subs = sb.get("sub") or []
    entry_thr = int(ctx.get("entry_thr") or 6)
    sc = gf.get("score")
    v5_role = str(ctx.get("v5_role") or "demo")

    result, main = _v5_compute_result_main(ctx)
    g_act, g_reason = _v5_grid_action_reason(
        ctx.get("pre_np", 0),
        ctx.get("pre_npos", 0),
        ctx.get("new_pending") or [],
        ctx.get("new_positions") or [],
        ctx.get("max_positions", 5),
        ctx.get("v5_role"),
    )

    if compact:
        rel = _v5_signal_relation(gf)
        side = gf.get("current_signal_type") or gf.get("signal_type") or "-"
        ep = gf.get("current_signal_open_price")
        ps = f"{gf.get('prev_signal_type')} {gf.get('prev_signal_open_price')}"
        minus_rules = ",".join(subs) if subs else "none"
        print(f"[V5] RESULT={result} | MAIN_REASON={main}")
        print(f"[SIGNAL] {side} {ep} | prev={ps} | relation={rel}")
        lg = _v5_effective_live_gate_label(sc, entry_thr, bool(gf.get("blocked")))
        prof = sb.get("decision") if sb.get("decision") else _v5_score_decision_label(gf, entry_thr)
        print(
            f"[SCORE] score={sc} | profile={prof} | live_entry_gate={lg} | minus={minus_rules}"
        )
        print(f"[BLOCK] hard_block={gf.get('blocked')} | reason={gf.get('block_reason') or '-'}")
        print(
            f"[GRID] positions={ctx.get('pre_npos')} | pendings={ctx.get('pre_np')} | "
            f"action={g_act} | reason={g_reason}"
        )
        ren = ctx.get("relay_enabled", False)
        rs = ctx.get("relay_sent", False)
        rr = ctx.get("relay_reason") or "-"
        print(f"[RELAY] sent={rs} | reason={rr}" if ren else "[RELAY] enabled=False")
        return

    print(f"[V5] RESULT={result} | MAIN_REASON={main}")
    print("[SIGNAL]")
    print(f"- side={gf.get('current_signal_type') or gf.get('signal_type') or '-'}")
    print(f"- entry={gf.get('current_signal_open_price')}")
    print(f"- prev_side={gf.get('prev_signal_type')}")
    print(f"- prev_open={gf.get('prev_signal_open_price')}")
    print(f"- relation={_v5_signal_relation(gf)}")
    print(f"- preferred={gf.get('preferred_direction')}")

    print("[SCORE]")
    print(f"- score={sc}")
    print(f"- profile={sb.get('decision') or _v5_score_decision_label(gf, entry_thr)}")
    print(f"- live_entry_gate={_v5_effective_live_gate_label(sc, entry_thr, bool(gf.get('blocked')))}")
    print(f"- add={len(adds)}")
    print(f"- sub={len(subs)}")
    plus_rules = ", ".join(adds) if adds else "none"
    minus_rules = ", ".join(subs) if subs else "none"
    print(f"- plus_rules={plus_rules}")
    print(f"- minus_rules={minus_rules}")

    print("[CONTEXT]")
    gsm = gf.get("gap_from_prev_signal_min")
    if gsm is None:
        gsm = gf.get("gap_minutes_from_prev_signal")
    print(f"- gap_signal_min={gsm}")
    gc = gf.get("gap_from_prev_close_min")
    print(f"- gap_from_prev_close_min={gc if gc is not None else '-'}")
    pd = gf.get("prev_duration_min")
    print(f"- prev_duration_min={pd if pd is not None else '-'}")
    print(f"- ts_src={gf.get('current_signal_ts_source')}")

    print("[BLOCK]")
    print(f"- hard_block={gf.get('blocked')}")
    print(f"- block_reason={gf.get('block_reason') or '-'}")
    print(f"- min_gap_ok={gf.get('min_gap_ok')}")
    print(f"- loss_streak={gf.get('loss_streak')}")
    print(f"- last_closed={gf.get('last_trade_result')}")
    print(f"- sum5={gf.get('sum_last_5_net_profit')}")
    print(f"- sum10={gf.get('sum_last_10_net_profit')}")

    print("[GRID]")
    print(f"- positions={ctx.get('pre_npos')}")
    print(f"- pendings={ctx.get('pre_np')}")
    print(f"- action={g_act}")
    print(f"- reason={g_reason}")

    ren = bool(ctx.get("relay_enabled", False))
    print("[RELAY]")
    print(f"- enabled={ren}")
    if ren:
        print(f"- sent={bool(ctx.get('relay_sent'))}")
        if ctx.get("relay_zone") is not None:
            print(f"- zone={ctx.get('relay_zone')}")
        if ctx.get("relay_side"):
            print(f"- side={ctx.get('relay_side')}")
        print(f"- reason={ctx.get('relay_reason') or '-'}")
    else:
        print("- reason=RELAY_DISABLED")

    if v5_role != "live":
        blk_demo = bool(gf.get("blocked"))
        try:
            s_int = int(sc) if sc is not None else 0
        except (TypeError, ValueError):
            s_int = None
        if blk_demo:
            eq = "BLOCKED"
        elif s_int is None:
            eq = "?"
        else:
            eq = "QUALIFIED" if s_int >= entry_thr else "REJECT"
        print("[LIVE_CHECK]")
        print(f"- equivalent={eq}")
        print(f"- entry_threshold={entry_thr}")
        print(f"- score={sc}")
        if eq == "REJECT":
            print("- note=score < entry_threshold; profile=PROBE chỉ là bucket 1–2 điểm (scores.py), không phải đủ cổng live")
        elif eq == "BLOCKED":
            print(f"- note=đủ điểm nhưng hard_block (vd min_gap) — block_reason={gf.get('block_reason') or '-'}")
    print("")


def _v5_try_emit_cycle_log(ctx, params):
    """Throttle ~10s khi cùng (RESULT, MAIN, score, pendings, positions)."""
    if not bool(params.get("v5_structured_log", True)):
        return
    gf = ctx.get("gate_features") or {}
    if gf.get("v5_score_reused_no_new_close") and bool(params.get("v5_quiet_structured_when_no_new_close", True)):
        return
    r, m = _v5_compute_result_main(ctx)
    sig = (r, m, gf.get("score"), ctx.get("pre_np"), ctx.get("pre_npos"))
    now_m = time.monotonic()
    prev = getattr(run, "_last_v5_struct_log", None)
    if prev is not None and prev[0] == sig and (now_m - prev[1]) < 10.0:
        return
    if _v5_param_log_debug(params):
        _v5_emit_structured_cycle_log(ctx, params)
    else:
        _v5_emit_minimal_cycle_log(ctx, params)
    run._last_v5_struct_log = (sig, now_m)


def run():
    args = sys.argv[1:]
    if args and args[0].strip() == "--check-db":
        base.check_grid_step_db()
        sys.exit(0)

    config_name = "config_grid_step_v5.json"
    if args:
        if args[0].strip() == "--config" and len(args) >= 2:
            config_name = args[1].strip()
        elif args[0].strip().endswith(".json"):
            # tiện chạy nhanh: python strategy_grid_step_v5.py config_grid_step_v5_live.json
            config_name = args[0].strip()
    config_path = os.path.join(SCRIPT_DIR, "configs", config_name)
    print(f"📁 [V5] using config: {config_path}")
    config = base.load_config(config_path)

    consecutive_errors = 0
    if config and base.connect_mt5(config):
        params = config.get("parameters", {})
        loop_interval_seconds = max(1.0, float(params.get("loop_interval_seconds", 10)))
        if "steps" in params and params["steps"] is not None:
            steps_config = params["steps"]
            if not isinstance(steps_config, list):
                steps_config = [steps_config]
            steps_list = [float(s) for s in steps_config]
        else:
            steps_list = None

        label = f"steps: {steps_list}" if steps_list is not None else "single step (legacy)"
        consecutive_loss_pause_enabled = params.get("consecutive_loss_pause_enabled", True)
        print(f"✅ Grid Step Bot V5 - Started ({label})")
        loop_count = 0

        try:
            while True:
                params = config.get("parameters", {})
                v5_role = str(params.get("v5_role", "demo")).lower().strip()
                entry_thr = int(params.get("entry_score_threshold", 6))
                relay_verbose = bool(params.get("relay_verbose_log", True))
                sym = config["symbol"]
                mag = config["magic"]
                pre_pending, pre_positions = _snapshot_bot_orders_positions(sym, mag)
                has_grid = len(pre_pending) > 0 or len(pre_positions) > 0
                live_relay_blind = bool(params.get("live_relay_blind_follow", False))
                active_relay_id = None

                if v5_role == "live":
                    if not has_grid:
                        relay_payload = (
                            signal_relay.relay_read_valid(config)
                            if bool(params.get("signal_relay_enabled", False))
                            else None
                        )
                        if not relay_payload:
                            _v5_try_emit_cycle_log(
                                {
                                    "exit_kind": "no_relay_flat",
                                    "v5_role": v5_role,
                                    "entry_thr": entry_thr,
                                    "max_positions": config.get("max_positions", 5),
                                    "pre_np": len(pre_pending),
                                    "pre_npos": len(pre_positions),
                                    "gate_reason": "no_relay",
                                    "gate_features": {},
                                    "relay_enabled": bool(params.get("signal_relay_enabled", False)),
                                    "relay_sent": False,
                                    "relay_reason": "NO_RELAY",
                                },
                                params,
                            )
                            time.sleep(loop_interval_seconds)
                            continue
                        if not live_relay_blind and not _relay_zone_matches_current(config, relay_payload):
                            _v5_try_emit_cycle_log(
                                {
                                    "exit_kind": "relay_zone_mismatch",
                                    "v5_role": v5_role,
                                    "entry_thr": entry_thr,
                                    "max_positions": config.get("max_positions", 5),
                                    "pre_np": len(pre_pending),
                                    "pre_npos": len(pre_positions),
                                    "gate_reason": "relay_zone_mismatch",
                                    "gate_features": signal_relay.relay_to_gate_features(relay_payload),
                                    "relay_enabled": bool(params.get("signal_relay_enabled", False)),
                                    "relay_sent": False,
                                    "relay_reason": "RELAY_ZONE_MISMATCH",
                                },
                                params,
                            )
                            time.sleep(loop_interval_seconds)
                            continue
                        allow_live = True
                        gate_reason = "live_relay_ok"
                        gate_features = signal_relay.relay_to_gate_features(relay_payload)
                        active_relay_id = relay_payload.get("relay_id")
                    else:
                        allow_live = True
                        gate_reason = "live_grid_maintenance"
                        gate_features = _v5_live_gate_features_no_relay()
                else:
                    allow_live, gate_reason, gate_features = _v5_history_score_gate(config)

                if not allow_live:
                    _v5_try_emit_cycle_log(
                        {
                            "exit_kind": "gate_blocked",
                            "v5_role": v5_role,
                            "entry_thr": entry_thr,
                            "max_positions": config.get("max_positions", 5),
                            "pre_np": len(pre_pending),
                            "pre_npos": len(pre_positions),
                            "gate_reason": gate_reason,
                            "gate_features": gate_features or {},
                            "relay_enabled": bool(params.get("signal_relay_enabled", False)),
                            "relay_sent": False,
                            "relay_reason": "NO_DEMO_ORDER",
                        },
                        params,
                    )
                    time.sleep(loop_interval_seconds)
                    continue

                # Demo: kết_luận=đạt (score>=entry, không block) → ghi v5_relay_signal.json (zone trùng thì signal_relay bỏ qua).
                relay_early_sent = False
                relay_early_reason = "NO_DEMO_ORDER"
                relay_early_zone = None
                relay_early_side = None
                if (
                    v5_role == "demo"
                    and bool(params.get("signal_relay_enabled", False))
                    and gate_features
                    and _v5_ket_luan_dat(gate_features, entry_thr)
                ):
                    _rid_er, relay_early_reason = signal_relay.demo_try_publish_relay(
                        config,
                        gate_features,
                        relay_zone_points=float(params.get("relay_zone_points") or 200),
                        ttl_minutes=float(params.get("relay_signal_ttl_minutes") or 180),
                        verbose=False,
                    )
                    relay_early_sent = _rid_er is not None
                    if relay_early_sent:
                        try:
                            ep = float(gate_features.get("current_signal_open_price") or 0)
                            relay_early_zone = signal_relay.price_zone_key(
                                ep, float(params.get("relay_zone_points") or 200)
                            )
                            relay_early_side = str(
                                gate_features.get("current_signal_type")
                                or gate_features.get("signal_type")
                                or ""
                            ).upper()
                        except (TypeError, ValueError):
                            pass

                live_min_entry_gap_seconds = int(float(params.get("live_min_entry_gap_minutes", 5)) * 60)
                if v5_role == "live":
                    remain_cd = _live_entry_cooldown_remaining_seconds(sym, mag, live_min_entry_gap_seconds)
                    # Chỉ chặn mở mới khi hệ thống đang flat (không position, không pending).
                    # Nếu đang có lệnh, để base strategy quản lý vòng đời bình thường.
                    skip_live_cd = live_relay_blind and str(gate_reason) == "live_relay_ok"
                    if (
                        remain_cd > 0
                        and (len(pre_pending) == 0 and len(pre_positions) == 0)
                        and not skip_live_cd
                    ):
                        _v5_try_emit_cycle_log(
                            {
                                "exit_kind": "live_cooldown",
                                "v5_role": v5_role,
                                "entry_thr": entry_thr,
                                "max_positions": config.get("max_positions", 5),
                                "pre_np": len(pre_pending),
                                "pre_npos": len(pre_positions),
                                "gate_reason": gate_reason,
                                "gate_features": gate_features or {},
                                "relay_enabled": bool(params.get("signal_relay_enabled", False)),
                                "relay_sent": False,
                                "relay_reason": "LIVE_COOLDOWN",
                            },
                            params,
                        )
                        time.sleep(loop_interval_seconds)
                        continue

                # Live: tín hiệu demo đủ điểm nhưng đã có cặp pending khớp tín hiệu → không gọi strategy (tránh thừa).
                live_skip_dup = bool(params.get("live_skip_if_equivalent", True))
                if live_relay_blind and str(gate_reason) == "live_relay_ok":
                    live_skip_dup = False
                if (
                    v5_role == "live"
                    and live_skip_dup
                    and allow_live
                    and gate_reason != "live_grid_maintenance"
                ):
                    step_f = _v5_step_filter_for_gate(config)
                    sig_type = gate_features.get("current_signal_type") or gate_features.get("signal_type")
                    sig_px = gate_features.get("current_signal_open_price")
                    gpr = gate_features.get("grid_preview") or {}
                    step_val = float(gpr.get("step") or _v5_gate_step_val(config))
                    info_lp = mt5.symbol_info(sym)
                    pt = float(getattr(info_lp, "point", 0.01) or 0.01) if info_lp else 0.01
                    dthr_raw = params.get("live_duplicate_price_threshold")
                    if dthr_raw is not None and float(dthr_raw) > 0:
                        dthr = float(dthr_raw)
                    else:
                        dthr = max(2.0 * pt, step_val * 1.05)
                    try:
                        spx = float(sig_px) if sig_px is not None else 0.0
                    except (TypeError, ValueError):
                        spx = 0.0
                    has_eq = _live_has_equivalent_order(sym, mag, step_f, sig_type, spx, dthr)
                    npos_ct = len(pre_positions)
                    npen_ct = len(pre_pending)
                    if has_eq and npos_ct == 0 and npen_ct == 2:
                        _v5_try_emit_cycle_log(
                            {
                                "exit_kind": "dup_skip",
                                "v5_role": v5_role,
                                "entry_thr": entry_thr,
                                "max_positions": config.get("max_positions", 5),
                                "pre_np": len(pre_pending),
                                "pre_npos": len(pre_positions),
                                "gate_reason": gate_reason,
                                "gate_features": gate_features or {},
                                "relay_enabled": bool(params.get("signal_relay_enabled", False)),
                                "relay_sent": False,
                                "relay_reason": "DUPLICATE_PENDING",
                            },
                            params,
                        )
                        time.sleep(loop_interval_seconds)
                        continue

                if consecutive_loss_pause_enabled:
                    if steps_list is not None:
                        for step_val in steps_list:
                            base.sync_closed_orders_from_mt5(config, strategy_name=f"Grid_Step_{step_val}")
                    else:
                        base.sync_closed_orders_from_mt5(config, strategy_name="Grid_Step")

                if steps_list is not None:
                    for step_val in steps_list:
                        consecutive_errors, last_error_code = base.strategy_grid_step_logic(
                            config, consecutive_errors, step=step_val
                        )
                else:
                    consecutive_errors, last_error_code = base.strategy_grid_step_logic(
                        config, consecutive_errors, step=None
                    )

                post_pending, post_positions = _snapshot_bot_orders_positions(sym, mag)
                new_pending = [t for t in post_pending if t not in pre_pending]
                new_positions = [t for t in post_positions if t not in pre_positions]

                # Demo: vừa đặt cặp pending stop → ghi v5_relay_demo.json (signal_relay: relay_id lô +
                # relay_id_buy_limit / relay_id_sell_limit riêng từng chân).
                if v5_role == "demo" and (new_pending or new_positions) and isinstance(
                    gate_features, dict
                ):
                    gpr = gate_features.get("grid_preview")
                    if isinstance(gpr, dict) and gpr.get("buy_price") is not None and gpr.get(
                        "sell_price"
                    ) is not None:
                        signal_relay.demo_write_inverse_relay_file(config, gate_features)

                relay_sent = relay_early_sent
                relay_reason = relay_early_reason
                relay_zone = relay_early_zone
                relay_side = relay_early_side
                # Chỉ ghi relay khi kết_luận=đạt (giống publish sớm). Grid vẫn có thể đặt lệnh khi gate chặn điểm
                # (demo_mode) — không mirror lên live nếu không đủ điều kiện score.
                if v5_role == "demo" and bool(params.get("signal_relay_enabled", False)) and (
                    new_pending or new_positions
                ):
                    if gate_features and _v5_ket_luan_dat(gate_features, entry_thr):
                        _rid, rsn_ord = signal_relay.demo_try_publish_relay(
                            config,
                            gate_features,
                            relay_zone_points=float(params.get("relay_zone_points") or 200),
                            ttl_minutes=float(params.get("relay_signal_ttl_minutes") or 180),
                            verbose=False,
                        )
                        if _rid is not None:
                            relay_sent = True
                            relay_reason = rsn_ord
                            try:
                                ep = float(gate_features.get("current_signal_open_price") or 0)
                                relay_zone = signal_relay.price_zone_key(
                                    ep, float(params.get("relay_zone_points") or 200)
                                )
                                relay_side = str(
                                    gate_features.get("current_signal_type")
                                    or gate_features.get("signal_type")
                                    or ""
                                ).upper()
                            except (TypeError, ValueError):
                                pass
                        elif not relay_early_sent:
                            relay_reason = rsn_ord
                    elif not relay_early_sent:
                        relay_reason = "SKIP_RELAY_NOT_QUALIFIED"

                if v5_role == "live" and active_relay_id and (new_pending or new_positions):
                    signal_relay.relay_consume(active_relay_id, verbose=relay_verbose)

                rr_out = relay_reason
                if v5_role != "demo" and relay_reason == "NO_DEMO_ORDER":
                    rr_out = "NOT_DEMO_ROLE"

                _v5_try_emit_cycle_log(
                    {
                        "exit_kind": "normal",
                        "v5_role": v5_role,
                        "entry_thr": entry_thr,
                        "max_positions": config.get("max_positions", 5),
                        "pre_np": len(pre_pending),
                        "pre_npos": len(pre_positions),
                        "gate_reason": gate_reason,
                        "gate_features": gate_features or {},
                        "new_pending": new_pending,
                        "new_positions": new_positions,
                        "relay_enabled": bool(params.get("signal_relay_enabled", False)),
                        "relay_sent": relay_sent,
                        "relay_reason": rr_out,
                        "relay_zone": relay_zone,
                        "relay_side": relay_side or None,
                    },
                    params,
                )

                if not new_pending and not new_positions:
                    if not bool(params.get("v5_structured_log", True)) and bool(
                        params.get("v5_verbose_no_order_log", True)
                    ):
                        print(
                            "ℹ️ [V5] no new order | "
                            f"role={v5_role} score={gate_features.get('score')} pending="
                            f"{len(pre_pending)}/{len(post_pending)} pos={len(pre_positions)}/{len(post_positions)}"
                        )
                if v5_role == "live" and (new_pending or new_positions):
                    _mark_live_entry_now(sym, mag)
                    now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    record = {
                        "ts_utc": now_utc,
                        "role": v5_role,
                        "symbol": sym,
                        "magic": mag,
                        "demo_relay_id": gate_features.get("relay_id"),
                        "gate_reason": gate_reason,
                        "score": gate_features.get("score"),
                        "score_breakdown": gate_features.get("score_breakdown"),
                        "conditions": {
                            "min_gap_ok": gate_features.get("min_gap_ok"),
                            "min_gap_minutes": gate_features.get("min_gap_minutes"),
                            "same_direction_as_prev_signal": gate_features.get("same_direction_as_prev_signal"),
                            "signal_type": gate_features.get("signal_type"),
                            "current_signal_open_price": gate_features.get("current_signal_open_price"),
                            "current_signal_ts_source": gate_features.get("current_signal_ts_source"),
                            "prev_signal_open_price": gate_features.get("prev_signal_open_price"),
                            "prev_signal_source": gate_features.get("prev_signal_source"),
                            "state_history_source": gate_features.get("state_history_source"),
                            "signal_closed_merge_source": gate_features.get("signal_closed_merge_source"),
                            "preferred_direction": gate_features.get("preferred_direction"),
                            "sum_last_5_net_profit": gate_features.get("sum_last_5_net_profit"),
                            "sum_last_10_net_profit": gate_features.get("sum_last_10_net_profit"),
                            "win_count_last_5": gate_features.get("win_count_last_5"),
                            "win_rate_last_10": gate_features.get("win_rate_last_10"),
                            "loss_streak": gate_features.get("loss_streak"),
                            "last_trade_result": gate_features.get("last_trade_result"),
                            "current_open_below_prev_open": gate_features.get("current_open_below_prev_open"),
                            "reverse_direction_from_prev_signal": gate_features.get(
                                "reverse_direction_from_prev_signal"
                            ),
                            "blocked": gate_features.get("blocked"),
                            "block_reason": gate_features.get("block_reason"),
                        },
                        "new_pending_tickets": new_pending,
                        "new_position_tickets": new_positions,
                        "pending_count_after": len(post_pending),
                        "position_count_after": len(post_positions),
                    }
                    _append_live_entry_log(record)
                    print(
                        f"📝 [V5 Live] logged entry event: pending={new_pending} positions={new_positions} "
                        f"score={gate_features.get('score')} -> {LIVE_LOG_FILE}"
                    )

                loop_count += 1
                if loop_count % 30 == 0:
                    pos = mt5.positions_get(symbol=sym, magic=mag) or []
                    ords = mt5.orders_get(symbol=sym) or []
                    ords = [o for o in ords if o.magic == mag]
                    tick = mt5.symbol_info_tick(sym)
                    spread = (tick.ask - tick.bid) if tick else 0
                    steps_info = steps_list if steps_list else "1"
                    print(
                        f"🔄 Grid Step V5 | Steps: {steps_info} | Positions: {len(pos)} | "
                        f"Pending: {len(ords)} | Spread: {spread:.2f} | Loop #{loop_count}"
                    )

                if consecutive_errors >= 5:
                    error_msg = base.get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Grid Step V5] 5 lỗi liên tiếp. Last: {error_msg}. Tạm dừng 2 phút..."
                    print(msg)
                    base.send_telegram(msg, config.get("telegram_token"), config.get("telegram_chat_id"))
                    time.sleep(120)
                    consecutive_errors = 0
                    continue

                time.sleep(loop_interval_seconds)
        except KeyboardInterrupt:
            print("🛑 Grid Step Bot V5 Stopped")
            mt5.shutdown()


if __name__ == "__main__":
    run()
