"""
BTCUSD scoring — Grid Step 200.0 (logic riêng, không copy XAU V5).

Dựa trên tài liệu: reversal nhanh sau chuỗi thua, SELL sau nghỉ dài,
hạn chế continuation cùng hướng (đặc biệt BUY continuation).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple, Union

Number = Union[int, float]


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def _b(x: Any) -> bool:
    return bool(x)


def _norm_side(x: Any) -> str:
    s = str(x or "").strip().upper()
    return s if s in ("BUY", "SELL") else ""


def btcusd_grid_step_200_score(features: Dict[str, Any]) -> Tuple[int, Dict[str, Any], str]:
    """
    Tính điểm BTCUSD (Grid Step 200.0) và bucket quyết định.

    `features` nên có các khóa (mục 2 tài liệu):
      current_signal_type, prev_signal_type, same_direction_as_prev_signal,
      reverse_direction_from_prev_signal, gap_minutes_from_prev_signal,
      sum_last_5_net_profit, sum_last_10_net_profit, win_rate_last_10,
      last_trade_result, loss_streak, win_streak

    Trả về:
      (score, detail, decision) với decision ∈ REJECT | PROBE | NEUTRAL | EXECUTE
    """
    cur = _norm_side(features.get("current_signal_type") or features.get("signal_type"))
    gap = _f(features.get("gap_minutes_from_prev_signal"), 999.0)
    same_dir = _b(features.get("same_direction_as_prev_signal"))
    rev = _b(features.get("reverse_direction_from_prev_signal"))
    loss_streak = _i(features.get("loss_streak"))
    win_streak = _i(features.get("win_streak"))
    sum5 = _f(features.get("sum_last_5_net_profit"))
    sum10 = _f(features.get("sum_last_10_net_profit"))
    win_rate10 = _f(features.get("win_rate_last_10"))
    last = str(features.get("last_trade_result") or "").strip()

    score = 0
    add: List[str] = []
    sub: List[str] = []

    def ap(rule: str, pts: int) -> None:
        nonlocal score
        score += pts
        add.append(f"{rule}:+{pts}")

    def sp(rule: str, pts: int) -> None:
        nonlocal score
        score -= pts
        sub.append(f"{rule}:-{pts}")

    # --- Điểm cộng (mục 3) ---
    if rev and gap < 3:
        ap("reversal_fast_gap_lt_3m", 3)

    if loss_streak >= 2 and gap < 3:
        ap("after_loss_streak_reversal_fast_lt_3m", 2)

    if cur == "SELL" and gap >= 60:
        ap("sell_after_long_rest_ge_60m", 2)

    if cur == "SELL" and win_rate10 >= 0.7 and last == "Win":
        ap("sell_strong_recent_state_winrate_ge_0.7_last_win", 1)

    if cur == "BUY" and sum5 >= 6:
        ap("buy_only_if_sum5_ge_6", 1)

    if sum10 >= 10:
        ap("state_sum10_ge_10", 1)

    # --- Điểm trừ (mục 4) ---
    if same_dir and last == "Loss":
        sp("same_dir_after_loss", 3)

    if same_dir and gap >= 20:
        sp("continuation_slow_gap_ge_20m", 2)

    if cur == "BUY" and same_dir:
        sp("buy_continuation", 2)

    if loss_streak >= 2 and gap >= 20:
        sp("after_loss_streak_signal_slow_ge_20m", 2)

    if win_streak >= 3 and gap < 3:
        sp("long_win_streak_reverse_too_fast_gap_lt_3m", 1)

    decision = btcusd_grid_step_200_decision(score)
    detail = {
        "score": score,
        "decision": decision,
        "add": add,
        "sub": sub,
        "symbol_profile": "BTCUSD_GridStep200",
    }
    return score, detail, decision


def btcusd_grid_step_200_decision(score: int) -> str:
    """
    Ngưỡng mục 5 tài liệu (ưu tiên mô tả text, không theo pseudocode cuối
    để score=3 không bị nhầm REJECT).

    - score <= 0     → REJECT
    - score 1..2     → PROBE
    - score == 3     → NEUTRAL (tránh / chỉ log)
    - score >= 4     → EXECUTE
    """
    if score >= 4:
        return "EXECUTE"
    if score == 3:
        return "NEUTRAL"
    if 1 <= score <= 2:
        return "PROBE"
    return "REJECT"


def btcusd_grid_step_200_should_trade(
    features: Dict[str, Any],
    *,
    allow_probe: bool = True,
    allow_neutral: bool = False,
) -> Tuple[bool, str, int, Dict[str, Any]]:
    """
    Wrapper tiện cho bot: có nên vào lệnh "chuẩn" hay "probe" hay không.

    - EXECUTE → True (chuẩn)
    - PROBE   → True nếu allow_probe
    - NEUTRAL → True chỉ nếu allow_neutral (mặc định False)
    - REJECT  → False
    """
    points, detail, decision = btcusd_grid_step_200_score(features)
    if decision == "EXECUTE":
        return True, decision, points, detail
    if decision == "PROBE" and allow_probe:
        return True, decision, points, detail
    if decision == "NEUTRAL" and allow_neutral:
        return True, decision, points, detail
    return False, decision, points, detail
