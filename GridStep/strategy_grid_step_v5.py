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


def _fetch_closed_trades_with_account(account_cfg, symbol, magic, history_window=20, comment_prefix="GridStep", days_back=3):
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
    return _fetch_closed_trades(
        symbol, magic, history_window=history_window, comment_prefix=comment_prefix, days_back=days_back
    )


def _fetch_closed_trades(symbol, magic, history_window=20, comment_prefix="GridStep", days_back=3):
    """
    Lấy trade đã đóng (position-level) từ MT5 history:
    - gom DEAL_ENTRY_IN/OUT theo position_id
    - giữ đủ trường để tính điểm theo check_win.md
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
    return closed[: max(1, int(history_window))]


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


def _build_score_features(closed, current_mid_price, preferred_direction="SELL", min_gap_minutes=5):
    c5 = closed[:5]
    c10 = closed[:10]
    if not c5:
        return {"ready": False, "reason": "not_enough_closed_trades"}

    last_trade = c5[0]
    prev_trade = closed[1] if len(closed) > 1 else None
    sum5 = sum(t["net_profit"] for t in c5)
    sum10 = sum(t["net_profit"] for t in c10) if c10 else 0.0
    win5 = sum(1 for t in c5 if t["net_profit"] > 0)
    win10 = sum(1 for t in c10 if t["net_profit"] > 0) if c10 else 0
    gross_profit10 = sum(t["net_profit"] for t in c10 if t["net_profit"] > 0)
    gross_loss10 = abs(sum(t["net_profit"] for t in c10 if t["net_profit"] <= 0))
    pf10 = (gross_profit10 / gross_loss10) if gross_loss10 > 0 else float("inf")
    win_streak, loss_streak = _calc_streak(closed)

    same_direction_as_prev = bool(prev_trade and last_trade["type"] == prev_trade["type"])
    reverse_direction_from_prev = bool(prev_trade and last_trade["type"] != prev_trade["type"])
    gap_minutes_from_prev_signal = (
        (last_trade["open_time"] - prev_trade["open_time"]) / 60.0 if prev_trade else 999.0
    )
    previous_open_price = float(prev_trade["open_price"]) if prev_trade else float(last_trade["open_price"])
    current_open_below_prev_open = float(current_mid_price) < previous_open_price
    current_open_above_prev_open = float(current_mid_price) > previous_open_price
    last_trade_result = "Win" if last_trade["net_profit"] > 0 else "Loss"
    signal_type = last_trade["type"]
    min_gap_ok = gap_minutes_from_prev_signal >= float(min_gap_minutes)

    return {
        "ready": True,
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
        "same_direction_as_prev": same_direction_as_prev,
        "reverse_direction_from_prev": reverse_direction_from_prev,
        "gap_minutes_from_prev_signal": gap_minutes_from_prev_signal,
        "previous_open_price": previous_open_price,
        "current_open_below_prev_open": current_open_below_prev_open,
        "current_open_above_prev_open": current_open_above_prev_open,
        "signal_type": signal_type,
        "preferred_direction": preferred_direction,
        "min_gap_ok": min_gap_ok,
    }


def _score_signal(features):
    if not features or not features.get("ready"):
        return None
    score = 0
    if features["gap_minutes_from_prev_signal"] >= 5:
        score += 2
    if features["sum_last_5_net_profit"] >= 15:
        score += 2
    if features["win_count_last_5"] >= 3:
        score += 1
    if features["sum_last_10_net_profit"] > 0:
        score += 1
    if features["win_rate_last_10"] >= 0.5:
        score += 1
    if features["last_trade_result"] == "Win":
        score += 1
    if features["same_direction_as_prev"]:
        score += 1
    if features["signal_type"] == "SELL":
        score += 1
    if features["current_open_below_prev_open"]:
        score += 1

    if features["last_trade_result"] == "Loss" and features["same_direction_as_prev"]:
        score -= 3
    if features["loss_streak"] >= 2:
        score -= 2
    if features["sum_last_5_net_profit"] < 0:
        score -= 2
    if features["sum_last_10_net_profit"] < 0:
        score -= 1
    if features["reverse_direction_from_prev"]:
        score -= 1
    if features["current_open_above_prev_open"] and features["preferred_direction"] == "SELL":
        score -= 1

    return score


def _is_blocked(features, max_loss_streak=2):
    if features["loss_streak"] >= int(max_loss_streak):
        return True, "loss_streak"
    if features["sum_last_5_net_profit"] < 0:
        return True, "sum_last_5_net_profit<0"
    if features["sum_last_10_net_profit"] < 0:
        return True, "sum_last_10_net_profit<0"
    if not features["min_gap_ok"]:
        return True, "gap_minutes_from_prev_signal<min_gap"
    if features["last_trade_result"] == "Loss" and features["same_direction_as_prev"] and not features["current_open_below_prev_open"]:
        return True, "loss_same_direction_no_price_improve"
    return False, ""


def _v5_history_score_gate(config):
    params = config.get("parameters", {})
    v5_role = str(params.get("v5_role", "demo")).lower().strip()
    history_window = int(params.get("history_window", 20))
    history_days_back = int(params.get("history_days_back", 7))
    min_gap_minutes = float(params.get("min_gap_minutes", 5))
    entry_score_threshold = int(params.get("entry_score_threshold", 6))
    medium_score_threshold = int(params.get("medium_score_threshold", 5))
    max_loss_streak = int(params.get("max_loss_streak", 2))
    preferred_direction = str(params.get("preferred_direction", "SELL")).upper()
    allow_reverse_entry = bool(params.get("allow_reverse_entry", False))
    history_comment_prefix = str(params.get("history_comment_prefix", "") or "").strip() or None
    symbol = config["symbol"]
    magic = config["magic"]

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False, "tick_none", {}
    current_mid_price = (float(tick.bid) + float(tick.ask)) / 2.0

    # Live có thể đọc history từ demo account riêng.
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
            )
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
            closed = _fetch_closed_trades(
                symbol, magic, history_window=history_window, comment_prefix=history_comment_prefix, days_back=history_days_back
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
        )
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
        closed = _fetch_closed_trades(
            symbol, magic, history_window=history_window, comment_prefix=history_comment_prefix, days_back=history_days_back
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

    features = _build_score_features(
        closed, current_mid_price, preferred_direction=preferred_direction, min_gap_minutes=min_gap_minutes
    )
    if not features.get("ready"):
        return False, str(features.get("reason", "feature_not_ready")), features

    blocked, block_reason = _is_blocked(features, max_loss_streak=max_loss_streak)
    score = _score_signal(features)
    features["score"] = score
    features["blocked"] = blocked
    features["block_reason"] = block_reason

    # Demo: luôn cho chạy bot gốc, nhưng vẫn trả đủ feature/score để log quan sát.
    if v5_role != "live":
        return True, "demo_mode_no_gate", features

    if not allow_reverse_entry and features["signal_type"] != preferred_direction:
        return False, f"direction_gate:{features['signal_type']}!=preferred:{preferred_direction}", features
    if blocked:
        return False, f"blocked:{block_reason}", features
    if score < medium_score_threshold:
        return False, f"low_score:{score}<{medium_score_threshold}", features
    # score == medium_score_threshold: cho phép chạy base logic như normal lot (chưa tách risk-size trong v5)
    if score < entry_score_threshold:
        return True, f"medium_score:{score}", features
    return True, f"high_score:{score}", features


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
                    score_text = gate_features.get("score")
                    if score_text is None:
                        score_text = "N/A"
                    no_order_hint = None
                    if not allow_live:
                        no_order_hint = f"blocked_by_gate:{gate_reason}"
                    elif gate_reason.startswith("demo_insufficient_history"):
                        no_order_hint = "no_order_reason_from_gate:none (demo bypass)"
                    elif gate_reason.startswith("medium_score") or gate_reason.startswith("high_score"):
                        no_order_hint = "gate_passed -> check base strategy logs for place/skip reason"
                    else:
                        no_order_hint = f"gate_reason:{gate_reason}"
                    print(
                        f"🧮 [V5 Gate] eval allow={allow_live} reason={gate_reason} "
                        f"score={score_text} "
                        f"sum5={gate_features.get('sum_last_5_net_profit')} "
                        f"sum10={gate_features.get('sum_last_10_net_profit')} "
                        f"loss_streak={gate_features.get('loss_streak')} "
                        f"signal={gate_features.get('signal_type')} | {no_order_hint}"
                    )
                    run._last_gate_eval_log = (gate_sig, now_m)
                if not allow_live:
                    # throttle log để tránh spam mỗi giây
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
                        print(f"⏸️ [V5 Gate] skip live entry: {gate_reason} | features={gate_features}")
                        run._last_gate_log = (sig, now_m)
                    time.sleep(1)
                    continue

                params = config.get("parameters", {})
                v5_role = str(params.get("v5_role", "demo")).lower().strip()
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
                        time.sleep(1)
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
                    # Gate pass nhưng không có lệnh mới: log rõ để đọc nhanh lý do.
                    print(
                        "ℹ️ [V5] no new order this loop | "
                        f"role={v5_role} score={gate_features.get('score', 'N/A')} reason={gate_reason} "
                        f"pending_before/after={len(pre_pending)}/{len(post_pending)} "
                        f"positions_before/after={len(pre_positions)}/{len(post_positions)}"
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
                        "conditions": {
                            "min_gap_ok": gate_features.get("min_gap_ok"),
                            "same_direction_as_prev": gate_features.get("same_direction_as_prev"),
                            "signal_type": gate_features.get("signal_type"),
                            "preferred_direction": gate_features.get("preferred_direction"),
                            "sum_last_5_net_profit": gate_features.get("sum_last_5_net_profit"),
                            "sum_last_10_net_profit": gate_features.get("sum_last_10_net_profit"),
                            "win_count_last_5": gate_features.get("win_count_last_5"),
                            "win_rate_last_10": gate_features.get("win_rate_last_10"),
                            "loss_streak": gate_features.get("loss_streak"),
                            "last_trade_result": gate_features.get("last_trade_result"),
                            "current_open_below_prev_open": gate_features.get("current_open_below_prev_open"),
                            "reverse_direction_from_prev": gate_features.get("reverse_direction_from_prev"),
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

                time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 Grid Step Bot V5 Stopped")
            mt5.shutdown()


if __name__ == "__main__":
    run()
