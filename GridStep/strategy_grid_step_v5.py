"""
Grid Step Trading Bot V5.

V5 tái sử dụng toàn bộ logic từ strategy_grid_step.py, nhưng:
- dùng file config riêng: configs/config_grid_step_v5.json
- tách file cooldown/pause riêng cho phiên bản v5
"""
import os
import sys
import time
import json
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone

import strategy_grid_step as base


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
base.COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown_v5.json")
base.PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause_v5.json")
LIVE_LOG_FILE = os.path.join(SCRIPT_DIR, "v5_live_entry_log.jsonl")
LIVE_STATE_FILE = os.path.join(SCRIPT_DIR, "v5_live_state.json")


def _fetch_closed_trades_with_account(
    account_cfg,
    symbol,
    magic,
    history_window=20,
    comment_prefix="GridStep",
    days_back=3,
    max_positions=None,
):
    """
    Đổi login sang account_cfg để đọc history, rồi caller tự chịu trách nhiệm restore account trước đó.
    account_cfg: {account,password,server,mt5_path}
    """
    mt5_path = account_cfg.get("mt5_path")
    if mt5_path:
        mt5.shutdown()
        if not mt5.initialize(path=mt5_path):
            print(f"⚠️ [V5 Gate] initialize fail for history account path={mt5_path}")
            return []
    ok = mt5.login(
        int(account_cfg.get("account", 0) or 0),
        password=str(account_cfg.get("password", "") or ""),
        server=str(account_cfg.get("server", "") or ""),
    )
    if not ok:
        print(f"⚠️ [V5 Gate] login fail for history account={account_cfg.get('account')}")
        return []
    cap = int(max_positions) if max_positions is not None else max(int(history_window), 100)
    return _fetch_closed_positions_list(
        symbol, magic, comment_prefix=comment_prefix, days_back=days_back, max_positions=cap
    )


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


def _normalize_preferred_direction(raw, default="SELL"):
    """BUY | SELL | BOTH (BOTH = không ép hướng, không cộng match_preferred). Chuỗi lạ → BOTH."""
    p = str(raw if raw is not None else default).strip().upper()
    if p in ("BUY", "SELL", "BOTH"):
        return p
    return "BOTH"


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

    pref = str(preferred_direction or "SELL").upper()
    if pref not in ("BUY", "SELL"):
        pref = "SELL"

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
        "min_gap_ok": min_gap_ok,
        "current_open_below_prev_open": cur_below_prev,
        "current_open_above_prev_open": cur_above_prev,
        "grid_preview": preview,
        "entry_signal_meta": {
            "nearest_stop_rule": entry_signal.get("nearest_stop_rule"),
            "mid_price": entry_signal.get("mid_price"),
        },
    }


def _score_signal_detailed(features):
    """
    Chấm điểm: state (lệnh đóng) + entry (tín hiệu hiện tại vs tín hiệu trước).
    Các điều kiện đã là hard block (loss_streak, sum5/10 âm, gap, loss+same_dir không cải thiện giá)
    không trừ điểm lặp — chỉ dùng _is_blocked.
    """
    if not features or not features.get("ready"):
        return None, {"add": [], "sub": [], "note": "not_ready"}
    score = 0
    add, sub = [], []
    pref = _normalize_preferred_direction(features.get("preferred_direction"))
    min_gap_cfg = float(features.get("min_gap_minutes", 5))

    def ap(rule, pts):
        nonlocal score
        score += pts
        add.append(f"{rule}:+{pts}")

    def sp(rule, pts):
        nonlocal score
        score -= pts
        sub.append(f"{rule}:-{pts}")

    if features["gap_minutes_from_prev_signal"] >= min_gap_cfg:
        ap(f"gap>={min_gap_cfg}m", 2)
    if features["sum_last_5_net_profit"] >= 15:
        ap("sum5>=15", 2)
    if features["win_count_last_5"] >= 3:
        ap("win5>=3", 1)
    if features["sum_last_10_net_profit"] > 0:
        ap("sum10>0", 1)
    if features["win_rate_last_10"] >= 0.5:
        ap("winrate10>=0.5", 1)
    if features["last_trade_result"] == "Win":
        ap("last_closed=Win", 1)
    if features.get("same_direction_as_prev_signal"):
        ap("same_dir_as_prev_signal", 1)
    st = features.get("current_signal_type") or features.get("signal_type")
    if pref in ("BUY", "SELL") and st == pref:
        ap(f"match_preferred({pref})", 1)
    cur = str(features.get("current_signal_type") or features.get("signal_type") or "SELL").upper()
    if cur == "SELL" and features["current_open_below_prev_open"]:
        ap("sell_continuation_price_improved", 1)
    elif cur == "BUY" and features["current_open_above_prev_open"]:
        ap("buy_continuation_price_improved", 1)

    # Mềm: không trùng hard block
    if features.get("reverse_direction_from_prev_signal"):
        sp("reverse_vs_prev_signal", 1)
    if cur == "SELL" and features["current_open_above_prev_open"]:
        sp("sell_continuation_price_worse", 1)
    elif cur == "BUY" and features["current_open_below_prev_open"]:
        sp("buy_continuation_price_worse", 1)

    breakdown = {"add": add, "sub": sub, "preferred_direction": pref}
    return score, breakdown


def _score_signal(features):
    s, _ = _score_signal_detailed(features)
    return s


def _is_blocked(features, max_loss_streak=2):
    cur = str(features.get("current_signal_type") or features.get("signal_type") or "SELL").upper()
    if features["loss_streak"] >= int(max_loss_streak):
        return True, "loss_streak"
    if features["sum_last_5_net_profit"] < 0:
        return True, "sum_last_5_net_profit<0"
    if features["sum_last_10_net_profit"] < 0:
        return True, "sum_last_10_net_profit<0"
    if not features["min_gap_ok"]:
        return True, "gap_minutes_from_prev_signal<min_gap"
    if features["last_trade_result"] == "Loss" and features.get("same_direction_as_prev_signal"):
        if cur == "SELL" and not features["current_open_below_prev_open"]:
            return True, "loss_same_dir_no_price_improve_SELL"
        if cur == "BUY" and not features["current_open_above_prev_open"]:
            return True, "loss_same_dir_no_price_improve_BUY"
    return False, ""


def _v5_history_score_gate(config):
    params = config.get("parameters", {})
    v5_role = str(params.get("v5_role", "demo")).lower().strip()
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
    entry_score_threshold = int(params.get("entry_score_threshold", 6))
    medium_score_threshold = int(params.get("medium_score_threshold", 5))
    max_loss_streak = int(params.get("max_loss_streak", 2))
    preferred_direction = _normalize_preferred_direction(params.get("preferred_direction", "SELL"))
    allow_reverse_entry = bool(params.get("allow_reverse_entry", False))
    history_comment_prefix = str(params.get("history_comment_prefix", "") or "").strip() or None
    symbol = config["symbol"]
    magic = config["magic"]

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False, "tick_none", {}

    # Live có thể đọc history từ demo account riêng.
    state_from_demo_account = False
    demo_history_enabled = bool(params.get("demo_history_enabled", False))
    demo_history_config_file = str(params.get("demo_history_config_file", "") or "").strip()
    demo_history_account = params.get("demo_history_account")
    demo_history_password = params.get("demo_history_password")
    demo_history_server = params.get("demo_history_server")
    demo_history_magic = int(params.get("demo_history_magic", magic) or magic)
    demo_history_symbol = str(params.get("demo_history_symbol", symbol) or symbol)
    demo_history_mt5_path = str(params.get("demo_history_mt5_path", config.get("mt5_path")) or config.get("mt5_path"))

    # Ưu tiên đọc account demo từ một file config riêng (vd config_grid_step_v5.json).
    if v5_role == "live" and demo_history_enabled and demo_history_config_file:
        demo_cfg_path = os.path.join(SCRIPT_DIR, "configs", demo_history_config_file)
        demo_cfg_raw = base.load_config(demo_cfg_path) or {}
        demo_cfg = {
            "account": demo_cfg_raw.get("account"),
            "password": demo_cfg_raw.get("password"),
            "server": demo_cfg_raw.get("server"),
            "mt5_path": demo_cfg_raw.get("mt5_path", demo_history_mt5_path),
        }
        demo_symbol = str(demo_cfg_raw.get("symbol", demo_history_symbol) or demo_history_symbol)
        demo_magic = int(demo_cfg_raw.get("magic", demo_history_magic) or demo_history_magic)
        # Cho phép override tại live config nếu user muốn.
        if params.get("demo_history_symbol"):
            demo_symbol = str(params.get("demo_history_symbol"))
        if params.get("demo_history_magic") is not None:
            demo_magic = int(params.get("demo_history_magic") or demo_magic)
        if params.get("demo_history_mt5_path"):
            demo_cfg["mt5_path"] = str(params.get("demo_history_mt5_path"))

        if demo_cfg.get("account") and demo_cfg.get("password") and demo_cfg.get("server"):
            live_cfg = {
                "account": config.get("account"),
                "password": config.get("password"),
                "server": config.get("server"),
                "mt5_path": config.get("mt5_path"),
            }
            closed = _fetch_closed_trades_with_account(
                demo_cfg,
                demo_symbol,
                demo_magic,
                history_window=history_window,
                comment_prefix=history_comment_prefix,
                days_back=history_days_back,
                max_positions=max_closed_fetch,
            )
            state_from_demo_account = True
            # restore live session để phần đặt lệnh luôn chạy trên live
            _ = _fetch_closed_trades_with_account(
                live_cfg,
                symbol,
                magic,
                history_window=1,
                comment_prefix=history_comment_prefix,
                days_back=1,
            )
            print(
                f"📚 [V5 Gate] history source=demo_config file={demo_history_config_file} "
                f"account={demo_cfg.get('account')} symbol={demo_symbol} magic={demo_magic} "
                f"window={history_window} days_back={history_days_back}"
            )
        else:
            print(
                f"⚠️ [V5 Gate] demo_history_config_file='{demo_history_config_file}' thiếu account/password/server, fallback current account."
            )
            closed = _fetch_closed_positions_list(
                symbol,
                magic,
                comment_prefix=history_comment_prefix,
                days_back=history_days_back,
                max_positions=max_closed_fetch,
            )
            print(
                f"📚 [V5 Gate] history source=current account={config.get('account')} "
                f"symbol={symbol} magic={magic} window={history_window} days_back={history_days_back}"
            )
    elif v5_role == "live" and demo_history_enabled and demo_history_account and demo_history_password and demo_history_server:
        live_cfg = {
            "account": config.get("account"),
            "password": config.get("password"),
            "server": config.get("server"),
            "mt5_path": config.get("mt5_path"),
        }
        demo_cfg = {
            "account": demo_history_account,
            "password": demo_history_password,
            "server": demo_history_server,
            "mt5_path": demo_history_mt5_path,
        }
        closed = _fetch_closed_trades_with_account(
            demo_cfg,
            demo_history_symbol,
            demo_history_magic,
            history_window=history_window,
            comment_prefix=history_comment_prefix,
            days_back=history_days_back,
            max_positions=max_closed_fetch,
        )
        state_from_demo_account = True
        # restore live session để phần đặt lệnh luôn chạy trên live
        _ = _fetch_closed_trades_with_account(
            live_cfg,
            symbol,
            magic,
            history_window=1,
            comment_prefix=history_comment_prefix,
            days_back=1,
        )
        print(
            f"📚 [V5 Gate] history source=demo account={demo_history_account} "
            f"symbol={demo_history_symbol} magic={demo_history_magic} "
            f"window={history_window} days_back={history_days_back}"
        )
    else:
        closed = _fetch_closed_positions_list(
            symbol,
            magic,
            comment_prefix=history_comment_prefix,
            days_back=history_days_back,
            max_positions=max_closed_fetch,
        )
        print(
            f"📚 [V5 Gate] history source=current account={config.get('account')} "
            f"symbol={symbol} magic={magic} window={history_window} days_back={history_days_back} role={v5_role}"
        )
    # Log quá trình lấy history đóng
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
    if len(closed) < 5:
        if v5_role != "live":
            # Demo luôn chạy bot gốc; chưa đủ history chỉ để quan sát log, không được chặn lệnh.
            return True, f"demo_insufficient_history:{len(closed)}", {"closed_count": len(closed), "role": v5_role}
        return False, f"need>=5_closed_trades, got={len(closed)}", {"closed_count": len(closed), "role": v5_role}

    closed_state = closed[: max(1, history_window)]

    step_filter = _v5_step_filter_for_gate(config)
    if state_from_demo_account:
        signal_closed_for_merge = _fetch_closed_positions_list(
            symbol,
            magic,
            comment_prefix=history_comment_prefix,
            days_back=history_days_back,
            max_positions=max_closed_fetch,
        )
    else:
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
    features["state_history_source"] = "demo_account" if state_from_demo_account else "current_account"
    features["signal_closed_merge_source"] = (
        "live_account" if state_from_demo_account else "same_as_state_fetch"
    )
    features["signal_history_window"] = signal_history_window
    features["prev_signal_price_tolerance"] = price_tol
    features["prev_signal_leading_overlap_skipped"] = prev_leading_skipped
    _om = float(open_mult) if open_mult is not None and float(open_mult) > 0 else 1.05
    features["prev_signal_open_same_dir_max_dist"] = (
        max(price_tol, float(grid_step) * _om) if grid_step is not None and float(grid_step) > 0 else None
    )
    if not features.get("ready"):
        return False, str(features.get("reason", "feature_not_ready")), features

    blocked, block_reason = _is_blocked(features, max_loss_streak=max_loss_streak)
    score, score_breakdown = _score_signal_detailed(features)
    features["score"] = score
    features["score_breakdown"] = score_breakdown
    features["blocked"] = blocked
    features["block_reason"] = block_reason

    # Demo: luôn cho chạy bot gốc, nhưng vẫn trả đủ feature/score để log quan sát.
    if v5_role != "live":
        return True, "demo_mode_no_gate", features

    cur_sig = str(features.get("current_signal_type") or features.get("signal_type") or "").upper()
    if (
        not allow_reverse_entry
        and preferred_direction in ("BUY", "SELL")
        and cur_sig != preferred_direction
    ):
        return False, f"direction_gate:{cur_sig}!=preferred:{preferred_direction}", features
    if blocked:
        return False, f"blocked:{block_reason}", features
    if score < medium_score_threshold:
        return False, f"low_score:{score}<{medium_score_threshold}", features
    # Live: chỉ coi tín hiệu đủ đẹp khi đạt entry_score_threshold (demo không dùng nhánh này).
    if score < entry_score_threshold:
        return False, f"below_entry_score:{score}<{entry_score_threshold}", features
    return True, f"qualified:{score}", features


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


def _print_v5_gate_detail(allow_live, gate_reason, gate_features, v5_role, medium_thr, entry_thr):
    """Log gate nhiều dòng: tổng điểm, từng rule cộng/trừ, entry/prev, ý nghĩa demo vs live."""
    gf = gate_features or {}
    sb = gf.get("score_breakdown") if isinstance(gf.get("score_breakdown"), dict) else {}
    adds = sb.get("add") or []
    subs = sb.get("sub") or []
    sc = gf.get("score")
    blk = gf.get("blocked")
    br = gf.get("block_reason") or "-"

    print("🧮 [V5 Gate] —— chi tiết chấm điểm / gate ——")
    print(f"  allow={allow_live}  |  role={v5_role}  |  reason: {gate_reason}")
    print(
        f"  Tổng điểm: {sc}  |  ngưỡng live: medium>={medium_thr} (lọc thấp), entry>={entry_thr} (đủ đẹp để qualified)"
    )
    if adds or subs:
        print("  Điểm cộng/trừ:")
        for ln in adds:
            print(f"      (+) {ln}")
        for ln in subs:
            print(f"      (−) {ln}")
    else:
        print("  Điểm cộng/trừ: (không có breakdown — có thể gate chưa ready)")

    gap = gf.get("gap_minutes_from_prev_signal")
    try:
        gap_s = f"{float(gap):.2f}"
    except (TypeError, ValueError):
        gap_s = str(gap)
    print(
        f"  State (lệnh đóng): sum5={gf.get('sum_last_5_net_profit')}  sum10={gf.get('sum_last_10_net_profit')}  "
        f"loss_streak={gf.get('loss_streak')}  last_closed={gf.get('last_trade_result')}"
    )
    print(
        f"  Entry đang chấm: {gf.get('current_signal_type')} @ {gf.get('current_signal_open_price')}  "
        f"| preferred={gf.get('preferred_direction')}"
    )
    print(
        f"  So với trước: prev={gf.get('prev_signal_type')} @ {gf.get('prev_signal_open_price')}  "
        f"| prev_src={gf.get('prev_signal_source')}  gap={gap_s} phút  min_gap_ok={gf.get('min_gap_ok')}"
    )
    print(
        f"  Thời gian entry: ts_src={gf.get('current_signal_ts_source')}  "
        f"| hard_block={blk}  | block_reason={br}"
    )
    if v5_role != "live":
        print(
            "  📌 Demo: score chỉ để quan sát — gate KHÔNG chặn. Có vào lệnh hay không do strategy grid "
            "(2 pending, position, spread, pause...), không do điểm."
        )
        try:
            s = int(sc) if sc is not None else 0
        except (TypeError, ValueError):
            s = 0
        if s < entry_thr:
            print(
                f"  📌 Nếu đây là live: với điểm {s} < entry ({entry_thr}) sẽ KHÔNG được coi qualified — chưa đủ đẹp."
            )
    else:
        if allow_live:
            print("  📌 Live: đã qualified / qua gate — strategy được gọi (trừ khi cooldown hoặc skip trùng pending).")
        else:
            print("  📌 Live: KHÔNG qualified — không chạy strategy theo gate (xem reason).")

    print("🧮 [V5 Gate] ————————————————————————")


def _print_v5_no_new_order_detail(
    v5_role,
    gate_reason,
    gate_features,
    pre_pending,
    post_pending,
    pre_positions,
    post_positions,
    max_positions,
):
    """Giải thích vì sao không có ticket pending/position mới sau một vòng strategy."""
    gf = gate_features or {}
    np_pre, np_post = len(pre_pending), len(post_pending)
    npos_pre, npos_post = len(pre_positions), len(post_positions)
    mx = int(max_positions or 5)

    print("ℹ️ [V5] —— không có lệnh mới trong vòng này ——")
    print(f"  role={v5_role}  score={gf.get('score')}  gate_reason={gate_reason}")
    print(f"  MT5: pending {np_pre}→{np_post}  |  positions {npos_pre}→{npos_post}")
    reasons = []
    if np_pre >= 2:
        reasons.append(
            "Grid (strategy_grid_step.py): len(pendings)==2 → bot CỐ TÌNH không đặt thêm cặp STOP; "
            "chờ một lệnh khớp (hoặc bạn hủy tay). Đây là đúng thiết kế, không phải lỗi V5 hay score."
        )
    if npos_pre >= mx:
        reasons.append(f"Đã đạt hoặc vượt max_positions={mx} → không mở thêm position.")
    if npos_pre > 0 and np_pre > 0:
        reasons.append("Có position và vẫn có pending → trạng thái lưới bình thường; có thể chờ TP basket hoặc điều kiện spread/min_distance/pause (xem log [step=...] phía trên nếu có).")
    if npos_pre > 0 and np_pre == 0:
        reasons.append("Có position nhưng không còn pending → base có thể vừa khớp một chân; vòng sau thường hủy/đặt lại cặp — xem log strategy.")
    if not reasons:
        reasons.append("Không đoán được chắc: xem log strategy_grid_step (spread_max, pause, min_distance_points, cooldown...).")

    for i, r in enumerate(reasons, 1):
        print(f"  {i}) {r}")
    if v5_role != "live":
        print("  (Demo: không có gate theo điểm; lý do không vào lệnh chủ yếu là điều kiện grid như trên.)")
    print("ℹ️ [V5] ————————————————————————")


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
                allow_live, gate_reason, gate_features = _v5_history_score_gate(config)
                params = config.get("parameters", {})
                v5_role = str(params.get("v5_role", "demo")).lower().strip()
                medium_thr = int(params.get("medium_score_threshold", 5))
                entry_thr = int(params.get("entry_score_threshold", 6))
                # Log tóm tắt kết quả kiểm tra gate (throttle để tránh spam)
                gate_sig = (
                    bool(allow_live),
                    gate_reason,
                    gate_features.get("score"),
                    round(float(gate_features.get("sum_last_5_net_profit", 0) or 0), 2),
                    round(float(gate_features.get("sum_last_10_net_profit", 0) or 0), 2),
                    gate_features.get("loss_streak"),
                    gate_features.get("signal_type"),
                )
                now_m = time.monotonic()
                prev_gate = getattr(run, "_last_gate_eval_log", None)
                if prev_gate is None or prev_gate[0] != gate_sig or (now_m - prev_gate[1]) > 10:
                    if bool(params.get("v5_verbose_gate_log", True)):
                        _print_v5_gate_detail(
                            allow_live, gate_reason, gate_features, v5_role, medium_thr, entry_thr
                        )
                    else:
                        sb = gate_features.get("score_breakdown") or {}
                        add_s = "; ".join(sb.get("add", [])) if isinstance(sb, dict) else ""
                        sub_s = "; ".join(sb.get("sub", [])) if isinstance(sb, dict) else ""
                        print(
                            f"🧮 [V5 Gate] allow={allow_live} reason={gate_reason} score={gate_features.get('score')} "
                            f"add=[{add_s}] sub=[{sub_s}]"
                        )
                    run._last_gate_eval_log = (gate_sig, now_m)
                if not allow_live:
                    # throttle log — cả demo cũng dừng tại đây nếu gate trả allow=False (tick_none, preview_grid_failed, feature_not_ready...)
                    sig = (
                        gate_reason,
                        gate_features.get("score"),
                        gate_features.get("closed_count"),
                        round(float(gate_features.get("sum_last_5_net_profit", 0) or 0), 2),
                        round(float(gate_features.get("sum_last_10_net_profit", 0) or 0), 2),
                    )
                    now_m = time.monotonic()
                    prev = getattr(run, "_last_gate_log", None)
                    if prev is None or prev[0] != sig or (now_m - prev[1]) > 15:
                        print(
                            f"⏸️ [V5 Gate] KHÔNG gọi strategy_grid_step — role={v5_role} | reason={gate_reason}"
                        )
                        if v5_role != "live":
                            print(
                                "   (Demo: thường gặp tick_none, preview_grid_failed, feature_not_ready — "
                                "không phải do điểm score.)"
                            )
                        run._last_gate_log = (sig, now_m)
                    time.sleep(loop_interval_seconds)
                    continue

                sym = config["symbol"]
                mag = config["magic"]
                live_min_entry_gap_seconds = int(float(params.get("live_min_entry_gap_minutes", 5)) * 60)
                pre_pending, pre_positions = _snapshot_bot_orders_positions(sym, mag)
                if v5_role == "live":
                    remain_cd = _live_entry_cooldown_remaining_seconds(sym, mag, live_min_entry_gap_seconds)
                    # Chỉ chặn mở mới khi hệ thống đang flat (không position, không pending).
                    # Nếu đang có lệnh, để base strategy quản lý vòng đời bình thường.
                    if remain_cd > 0 and (len(pre_pending) == 0 and len(pre_positions) == 0):
                        prev_cd = getattr(run, "_last_live_cd_log", None)
                        now_m = time.monotonic()
                        sig_cd = (remain_cd // 5, len(pre_pending), len(pre_positions))
                        if prev_cd is None or prev_cd[0] != sig_cd or (now_m - prev_cd[1]) > 10:
                            print(
                                f"⏸️ [V5 Live] entry cooldown: còn {remain_cd}s "
                                f"(min_gap={live_min_entry_gap_seconds}s), skip mở lệnh mới."
                            )
                            run._last_live_cd_log = (sig_cd, now_m)
                        time.sleep(loop_interval_seconds)
                        continue

                # Live: tín hiệu demo đủ điểm nhưng đã có cặp pending khớp tín hiệu → không gọi strategy (tránh thừa).
                live_skip_dup = bool(params.get("live_skip_if_equivalent", True))
                if v5_role == "live" and live_skip_dup and allow_live:
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
                        now_m = time.monotonic()
                        prev_sk = getattr(run, "_last_live_dup_skip_log", None)
                        sig_sk = (str(sig_type), round(spx, 2), round(dthr, 4))
                        if prev_sk is None or prev_sk[0] != sig_sk or (now_m - prev_sk[1]) > 15:
                            print(
                                "ℹ️ [V5 Live] tín hiệu đạt ngưỡng nhưng live đã có pending tương đương "
                                f"({sig_type} @ ~{spx}, thr={dthr}); bỏ qua gọi strategy."
                            )
                            run._last_live_dup_skip_log = (sig_sk, now_m)
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
                if not new_pending and not new_positions:
                    if bool(params.get("v5_verbose_no_order_log", True)):
                        _print_v5_no_new_order_detail(
                            v5_role,
                            gate_reason,
                            gate_features,
                            pre_pending,
                            post_pending,
                            pre_positions,
                            post_positions,
                            config.get("max_positions", 5),
                        )
                    else:
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
