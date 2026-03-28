"""
BTCUSD scoring — Grid Step 200.0 (logic riêng, không copy XAU V5).

Bản cập nhật: tách hai loại gap:
- gap_from_prev_signal_min (mở→entry): continuation, SELL sau pause dài
- gap_from_prev_close_min (đóng→entry): reversal nhanh / strong reversal khi có close_time
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


# Ngưỡng dùng chung cho gate BTC (strategy_grid_step_btc_v5) và điểm trừ sum10 âm sâu.
SUM10_HARD_BLOCK_THRESHOLD = -10.0
STRONG_REVERSAL_GAP_LT_MIN = 3.0


def _gap_from_prev_signal_min(features: Dict[str, Any]) -> float:
    """Khoảng cách (phút) từ mở tín hiệu trước tới entry hiện tại (spacing / continuation)."""
    g = features.get("gap_from_prev_signal_min")
    if g is not None:
        return _f(g, 999.0)
    return _f(features.get("gap_minutes_from_prev_signal"), 999.0)


def _gap_for_reversal_min(features: Dict[str, Any]) -> float:
    """
    Gap cho reversal nhanh / strong reversal: ưu tiên thời gian từ khi lệnh trước *đóng*
    tới entry hiện tại; nếu không có (prev đang mở hoặc chưa sync close_time) thì dùng gap mở→mở.
    """
    g_close = features.get("gap_from_prev_close_min")
    if g_close is not None:
        return _f(g_close, 999.0)
    return _gap_from_prev_signal_min(features)


def btc_strong_reversal_signal(features: Dict[str, Any]) -> bool:
    """
    Strong reversal (BTC):
    - reverse_direction_from_prev_signal
    - _gap_for_reversal_min < 3
    - và (last_trade_result == Loss hoặc loss_streak >= 2)
    """
    rev = _b(features.get("reverse_direction_from_prev_signal"))
    gap = _gap_for_reversal_min(features)
    last = str(features.get("last_trade_result") or "").strip()
    loss_streak = _i(features.get("loss_streak"))
    if not rev or gap >= STRONG_REVERSAL_GAP_LT_MIN:
        return False
    return last == "Loss" or loss_streak >= 2


def btcusd_grid_step_200_score(features: Dict[str, Any]) -> Tuple[int, Dict[str, Any], str]:
    """
    Tính điểm BTCUSD (Grid Step 200.0) và bucket quyết định.
    """
    cur = _norm_side(features.get("current_signal_type") or features.get("signal_type"))
    gap_sig = _gap_from_prev_signal_min(features)
    gap_rev = _gap_for_reversal_min(features)
    same_dir = _b(features.get("same_direction_as_prev_signal"))
    rev = _b(features.get("reverse_direction_from_prev_signal"))
    sum10 = _f(features.get("sum_last_10_net_profit"))
    last = str(features.get("last_trade_result") or "").strip()

    pd_raw = features.get("prev_duration_min")
    prev_d: float | None
    if pd_raw is None:
        prev_d = None
    else:
        prev_d = _f(pd_raw, 0.0)

    strong = btc_strong_reversal_signal(features)

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

    # --- Điểm cộng (reversal dùng gap_rev = đóng→entry khi có close_time) ---
    if rev and gap_rev < STRONG_REVERSAL_GAP_LT_MIN:
        ap("reversal_fast_gap_lt_3m", 3)

    if strong:
        ap("strong_reversal", 2)

    if prev_d is not None and 1.0 <= prev_d < 3.0:
        ap("prev_duration_1_to_3m", 1)

    if cur == "SELL" and gap_sig >= 60:
        ap("sell_after_long_pause_ge_60m", 2)

    if sum10 >= 10:
        ap("state_sum10_ge_10", 1)

    if cur == "SELL" and last == "Win" and sum10 > 0:
        ap("sell_after_win_positive_sum10", 1)

    # --- Điểm trừ ---
    if same_dir and gap_sig >= 20:
        sp("continuation_slow_gap_ge_20m", 3)

    if cur == "BUY" and same_dir:
        sp("buy_continuation", 2)

    if rev and gap_sig < STRONG_REVERSAL_GAP_LT_MIN and prev_d is not None and prev_d < 1.0:
        sp("reversal_too_fast_after_prev_lt_1m", 2)

    if sum10 < SUM10_HARD_BLOCK_THRESHOLD and not strong:
        sp("sum10_deep_negative_no_strong_reversal", 2)

    decision = btcusd_grid_step_200_decision(score)
    detail = {
        "score": score,
        "decision": decision,
        "add": add,
        "sub": sub,
        "symbol_profile": "BTCUSD_GridStep200",
        "strong_reversal": strong,
        "gap_for_reversal_min": gap_rev,
        "gap_from_prev_signal_min": gap_sig,
    }
    return score, detail, decision


def btcusd_grid_step_200_decision(score: int) -> str:
    """
    - score <= 0     → REJECT
    - score 1..2     → PROBE
    - score == 3     → NEUTRAL
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
    """
    points, detail, decision = btcusd_grid_step_200_score(features)
    if decision == "EXECUTE":
        return True, decision, points, detail
    if decision == "PROBE" and allow_probe:
        return True, decision, points, detail
    if decision == "NEUTRAL" and allow_neutral:
        return True, decision, points, detail
    return False, decision, points, detail
