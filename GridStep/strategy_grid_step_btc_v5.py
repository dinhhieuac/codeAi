"""
Grid Step BTC V5.

Reuse engine của strategy_grid_step_v5 nhưng:
- base strategy = strategy_grid_step_btc
- score = BTCUSD Grid Step 200.0 từ scores.py
- file state/log riêng cho BTC v5
"""
import os
import sys

import strategy_grid_step_v5 as core
import strategy_grid_step_btc as btc_base
from scores import (
    SUM10_HARD_BLOCK_THRESHOLD,
    btc_strong_reversal_signal,
    btcusd_grid_step_200_score,
)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Rebind base logic sang BTC clone.
core.base = btc_base
core.base.COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown_btc_v5.json")
core.base.PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause_btc_v5.json")

# Tách log/state live riêng cho BTC v5.
core.LIVE_LOG_FILE = os.path.join(SCRIPT_DIR, "btc_v5_live_entry_log.jsonl")
core.LIVE_STATE_FILE = os.path.join(SCRIPT_DIR, "btc_v5_live_state.json")


def _btc_is_blocked(features, max_loss_streak=2):
    """
    BTC: không hard-block chỉ vì sum10<0; chỉ khi sum10 < -10 và không strong reversal.
    Không dùng hard-block sum5<0 (phù hợp reversal sau nền xấu ngắn).
    """
    cur = str(features.get("current_signal_type") or features.get("signal_type") or "SELL").upper()
    if features["loss_streak"] >= int(max_loss_streak):
        return True, "loss_streak"
    sum10 = float(features.get("sum_last_10_net_profit") or 0)
    if sum10 < float(SUM10_HARD_BLOCK_THRESHOLD) and not btc_strong_reversal_signal(features):
        return True, "sum_last_10_net_profit_deep_negative_no_strong_reversal"
    if not features["min_gap_ok"]:
        return True, "gap_minutes_from_prev_signal<min_gap"
    if features["last_trade_result"] == "Loss" and features.get("same_direction_as_prev_signal"):
        if cur == "SELL" and not features["current_open_below_prev_open"]:
            return True, "loss_same_dir_no_price_improve_SELL"
        if cur == "BUY" and not features["current_open_above_prev_open"]:
            return True, "loss_same_dir_no_price_improve_BUY"
    return False, ""


def _btc_score_signal_detailed(features):
    if not features or not features.get("ready"):
        return None, {"add": [], "sub": [], "note": "not_ready"}
    score, detail, _decision = btcusd_grid_step_200_score(features)
    breakdown = {
        "add": detail.get("add", []),
        "sub": detail.get("sub", []),
        "profile": detail.get("symbol_profile"),
        "decision": detail.get("decision"),
        "strong_reversal": detail.get("strong_reversal"),
    }
    return score, breakdown


# Override scorer và block rules (BTC) trong engine V5.
core._score_signal_detailed = _btc_score_signal_detailed
core._score_signal = lambda f: _btc_score_signal_detailed(f)[0]
core._is_blocked = _btc_is_blocked


def run():
    # Nếu user không truyền config thì mặc định BTC V5.
    if len(sys.argv) == 1:
        sys.argv.extend(["--config", "config_grid_step_btc_v5.json"])
    core.run()


if __name__ == "__main__":
    run()
