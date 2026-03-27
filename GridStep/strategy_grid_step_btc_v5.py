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
from scores import btcusd_grid_step_200_score


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Rebind base logic sang BTC clone.
core.base = btc_base
core.base.COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown_btc_v5.json")
core.base.PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause_btc_v5.json")

# Tách log/state live riêng cho BTC v5.
core.LIVE_LOG_FILE = os.path.join(SCRIPT_DIR, "btc_v5_live_entry_log.jsonl")
core.LIVE_STATE_FILE = os.path.join(SCRIPT_DIR, "btc_v5_live_state.json")


def _btc_score_signal_detailed(features):
    if not features or not features.get("ready"):
        return None, {"add": [], "sub": [], "note": "not_ready"}
    score, detail, _decision = btcusd_grid_step_200_score(features)
    breakdown = {
        "add": detail.get("add", []),
        "sub": detail.get("sub", []),
        "profile": detail.get("symbol_profile"),
        "decision": detail.get("decision"),
    }
    return score, breakdown


# Override scorer trong engine V5.
core._score_signal_detailed = _btc_score_signal_detailed
core._score_signal = lambda f: _btc_score_signal_detailed(f)[0]


def run():
    # Nếu user không truyền config thì mặc định BTC V5.
    if len(sys.argv) == 1:
        sys.argv.extend(["--config", "config_grid_step_btc_v5.json"])
    core.run()


if __name__ == "__main__":
    run()
