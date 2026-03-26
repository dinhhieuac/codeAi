"""
Grid Step Trading Bot V5.

V5 tái sử dụng toàn bộ logic từ strategy_grid_step.py, nhưng:
- dùng file config riêng: configs/config_grid_step_v5.json
- tách file cooldown/pause riêng cho phiên bản v5
"""
import os
import sys
import time
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone

import strategy_grid_step as base


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
base.COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown_v5.json")
base.PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause_v5.json")


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
    history_window = int(params.get("history_window", 20))
    min_gap_minutes = float(params.get("min_gap_minutes", 5))
    entry_score_threshold = int(params.get("entry_score_threshold", 6))
    medium_score_threshold = int(params.get("medium_score_threshold", 5))
    max_loss_streak = int(params.get("max_loss_streak", 2))
    preferred_direction = str(params.get("preferred_direction", "SELL")).upper()
    allow_reverse_entry = bool(params.get("allow_reverse_entry", False))
    symbol = config["symbol"]
    magic = config["magic"]

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False, "tick_none", {}
    current_mid_price = (float(tick.bid) + float(tick.ask)) / 2.0

    closed = _fetch_closed_trades(
        symbol, magic, history_window=history_window, comment_prefix="GridStep", days_back=3
    )
    if len(closed) < 5:
        return False, f"need>=5_closed_trades, got={len(closed)}", {"closed_count": len(closed)}

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

                loop_count += 1
                if loop_count % 30 == 0:
                    sym = config["symbol"]
                    mag = config["magic"]
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
