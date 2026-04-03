"""
Grid Step BTC V5.

Reuse engine của strategy_grid_step_v5 nhưng:
- base strategy = strategy_grid_step_btc
- score = BTCUSD Grid Step 200.0 từ scores.py
- file state/log riêng cho BTC v5

Gate / history (strategy_grid_step_v5):
- v5_rescore_only_on_new_close: chỉ tính lại score khi có lệnh đóng mới (trên session/account lấy history).
- Nếu chưa có đóng mới: một dòng `📚 [V5 Gate] chưa có lệnh đóng mới` + giữ cache score; với account hiện tại
  dùng peek deal OUT để không tải full history.
- v5_quiet_structured_when_no_new_close (mặc định true): không in block [V5]/[SIGNAL]/[SCORE]... khi đang tái dùng
  score (tránh spam); đặt false nếu cần xem full log mỗi vòng.

Console log (cùng format V5):
- Dòng đầu: [V5] RESULT=... | MAIN_REASON=...
- [SCORE]: profile= bucket trong scores.py (EXECUTE/PROBE/...); live_entry_gate= so với
  entry_score_threshold (khác profile: PROBE chỉ là vùng 1–2 điểm).
- [LIVE_CHECK] (demo): equivalent QUALIFIED/REJECT theo ngưỡng entry.
- parameters: v5_structured_log, v5_compact_cycle_log; v5_verbose_no_order_log khi tắt structured.

Relay Demo → Live:
- gọi core.configure_grid_step_v5_paths(...) ngay sau import → cùng v5_relay_signal.json / v5_relay_state.json / v5_relay_signal_history.jsonl với XAU V5;
  inverse demo chỉ ghi **btc_v5_relay_demo.json** (và lịch sử base btc_v5_relay_demo_history.jsonl → btc_v5_relay_demo_history_BTCUSD.jsonl), không ghi đè v5_relay_demo.json của XAU.
- sign_inverse: đặt `relay_demo_file` trong config trỏ tới btc_v5_relay_demo.json khi mirror BTC.
- Demo: kết_luận=đạt (strategy_grid_step_v5) thì ghi relay sớm; dedup theo zone; thử lại khi có lệnh MT5 mới.
- Live: chỉ mirror relay từ demo; không đọc history/score trên account live (zone check = mid giá vs zone_key relay nếu không blind).
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

import strategy_grid_step_v5 as core

core.configure_grid_step_v5_paths(
    relay_signal_file=os.path.join(SCRIPT_DIR, "v5_relay_signal.json"),
    relay_state_file=os.path.join(SCRIPT_DIR, "v5_relay_state.json"),
    relay_history_log_file=os.path.join(SCRIPT_DIR, "v5_relay_signal_history.jsonl"),
    relay_demo_file=os.path.join(SCRIPT_DIR, "btc_v5_relay_demo.json"),
    relay_demo_history_log_file=os.path.join(SCRIPT_DIR, "btc_v5_relay_demo_history.jsonl"),
    live_log_file=os.path.join(SCRIPT_DIR, "btc_v5_live_entry_log.jsonl"),
    live_state_file=os.path.join(SCRIPT_DIR, "btc_v5_live_state.json"),
)
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

def _btc_is_blocked(features, max_loss_streak=2, **kwargs):
    """
    BTC: không hard-block chỉ vì sum10<0; chỉ khi sum10 < -10 và không strong reversal.
    Không dùng hard-block sum5<0 (phù hợp reversal sau nền xấu ngắn).

    Nhận thêm keyword từ core V5 (vd `hard_block_sum10_negative` cho XAU) — **bỏ qua**;
    gate BTC dùng SUM10_HARD_BLOCK_THRESHOLD, không rule sum10<0 kiểu XAU.
    `hard_block_min_gap` từ config `v5_hard_block_min_gap` (mặc định True).
    """
    kwargs.pop("hard_block_sum10_negative", None)
    hard_block_min_gap = bool(kwargs.pop("hard_block_min_gap", True))
    cur = str(features.get("current_signal_type") or features.get("signal_type") or "SELL").upper()
    if features["loss_streak"] >= int(max_loss_streak):
        return True, "loss_streak"
    sum10 = float(features.get("sum_last_10_net_profit") or 0)
    if sum10 < float(SUM10_HARD_BLOCK_THRESHOLD) and not btc_strong_reversal_signal(features):
        return True, "sum_last_10_net_profit_deep_negative_no_strong_reversal"
    if hard_block_min_gap and not features.get("min_gap_ok", True):
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
