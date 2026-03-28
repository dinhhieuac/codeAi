"""
Grid Step BTC V5.

Reuse engine của strategy_grid_step_v5 nhưng:
- base strategy = strategy_grid_step_btc
- score = BTCUSD Grid Step 200.0 từ scores.py
- file state/log riêng cho BTC v5

Console log (cùng format V5, xem strategy_grid_step_v5):
- Dòng đầu: [V5] RESULT=... | MAIN_REASON=...
- Các block: [SIGNAL], [SCORE], [CONTEXT], [BLOCK], [GRID], [RELAY]; demo có thêm [LIVE_CHECK].
- parameters: v5_structured_log (mặc định true), v5_compact_cycle_log (mặc định false);
  nếu tắt structured và bật v5_verbose_no_order_log thì chỉ còn dòng no-order tối giản.

Relay Demo → Live (cùng logic engine V5):
- Phải import signal_relay *trước* strategy_grid_step_v5 để trỏ file relay riêng BTC
  (btc_v5_relay_signal.json / btc_v5_relay_state.json), không dùng chung với XAU V5.
- Demo (config_grid_step_btc_v5.json): signal_relay_enabled, chấm điểm + gate + grid;
  khi có lệnh mới thành công → phát relay (mỗi zone relay_zone_points chỉ 1 lần).
- Live (config_grid_step_btc_v5_live.json): live_execute_demo_signal_only=true → flat chỉ
  mirror theo relay; có position/pending thì vẫn bảo trì lưới.
"""
import os
import sys

# Trỏ đường dẫn relay TRƯỚC khi nạp engine (strategy_grid_step_v5 cũng import signal_relay).
import signal_relay

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
signal_relay.RELAY_SIGNAL_FILE = os.path.join(SCRIPT_DIR, "btc_v5_relay_signal.json")
signal_relay.RELAY_STATE_FILE = os.path.join(SCRIPT_DIR, "btc_v5_relay_state.json")

import strategy_grid_step_v5 as core
import strategy_grid_step_btc as btc_base
from scores import (
    SUM10_HARD_BLOCK_THRESHOLD,
    btc_strong_reversal_signal,
    btcusd_grid_step_200_score,
)

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
        "gap_for_reversal_min": detail.get("gap_for_reversal_min"),
        "gap_from_prev_signal_min": detail.get("gap_from_prev_signal_min"),
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
