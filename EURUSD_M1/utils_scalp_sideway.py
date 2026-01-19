"""
Utility functions for Scalp Sideway Strategy
Hỗ trợ nhiều cặp giao dịch: EURUSD, XAUUSD, BTCUSD, ETHUSD, etc.

Based on: Bot-Scalp-sideway_v1.md
"""

import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, List


# ============================================================================
# INDICATOR CALCULATIONS
# ============================================================================

def calculate_ema(series: pd.Series, span: int) -> pd.Series:
    """
    Calculate Exponential Moving Average (EMA)
    
    Args:
        series: Price series (close, high, low, etc.)
        span: Period for EMA calculation
    
    Returns:
        EMA series
    """
    return series.ewm(span=span, adjust=False).mean()


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range (ATR)
    
    Args:
        df: DataFrame with OHLC data
        period: ATR period (default: 14)
    
    Returns:
        ATR series
    """
    df = df.copy()
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift(1))
    df['tr2'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=period).mean()
    return df['atr']


def calculate_body_size(candle: pd.Series) -> float:
    """
    Calculate candle body size
    
    Args:
        candle: Single candle row with 'open' and 'close'
    
    Returns:
        Body size (absolute value)
    """
    return abs(candle['close'] - candle['open'])


# ============================================================================
# SUPPLY/DEMAND ZONE DETECTION (M5)
# ============================================================================

def check_supply_m5(df_m5: pd.DataFrame, current_idx: int = -1) -> Tuple[bool, Optional[float], str]:
    """
    Xác định Supply zone trên M5
    
    Điều kiện:
    - High_M5_current < High_M5_prev
    - |High_M5_prev - High_M5_current| < 0.4 × ATR_M5
    
    Args:
        df_m5: DataFrame M5 với OHLC và ATR
        current_idx: Index của nến hiện tại (default: -1 for last candle)
    
    Returns:
        (is_supply, supply_price, message)
        - is_supply: True nếu là Supply zone
        - supply_price: Giá Supply (High_M5_prev) hoặc None
        - message: Thông báo kết quả
    """
    if len(df_m5) < 2:
        return False, None, "Không đủ dữ liệu M5"
    
    if current_idx < 0:
        current_idx = len(df_m5) + current_idx
    
    if current_idx < 1 or current_idx >= len(df_m5):
        return False, None, "Index không hợp lệ"
    
    current_candle = df_m5.iloc[current_idx]
    prev_candle = df_m5.iloc[current_idx - 1]
    
    # Lấy ATR_M5
    atr_m5 = current_candle.get('atr', None)
    if pd.isna(atr_m5) or atr_m5 is None:
        return False, None, "ATR_M5 không có giá trị"
    
    high_current = current_candle['high']
    high_prev = prev_candle['high']
    
    # Điều kiện 1: High_M5_current < High_M5_prev
    if high_current >= high_prev:
        return False, None, f"High_M5_current ({high_current:.5f}) >= High_M5_prev ({high_prev:.5f})"
    
    # Điều kiện 2: |High_M5_prev - High_M5_current| < 0.4 × ATR_M5
    high_diff = abs(high_prev - high_current)
    threshold = 0.4 * atr_m5
    
    if high_diff >= threshold:
        return False, None, f"|High_M5_prev - High_M5_current| ({high_diff:.5f}) >= 0.4 × ATR_M5 ({threshold:.5f})"
    
    # Supply zone hợp lệ
    supply_price = high_prev
    return True, supply_price, f"Supply zone: {supply_price:.5f} (High_M5_prev)"


def check_demand_m5(df_m5: pd.DataFrame, current_idx: int = -1) -> Tuple[bool, Optional[float], str]:
    """
    Xác định Demand zone trên M5
    
    Điều kiện:
    - Low_M5_current > Low_M5_prev
    - |Low_M5_current - Low_M5_prev| < 0.4 × ATR_M5
    
    Args:
        df_m5: DataFrame M5 với OHLC và ATR
        current_idx: Index của nến hiện tại (default: -1 for last candle)
    
    Returns:
        (is_demand, demand_price, message)
        - is_demand: True nếu là Demand zone
        - demand_price: Giá Demand (Low_M5_prev) hoặc None
        - message: Thông báo kết quả
    """
    if len(df_m5) < 2:
        return False, None, "Không đủ dữ liệu M5"
    
    if current_idx < 0:
        current_idx = len(df_m5) + current_idx
    
    if current_idx < 1 or current_idx >= len(df_m5):
        return False, None, "Index không hợp lệ"
    
    current_candle = df_m5.iloc[current_idx]
    prev_candle = df_m5.iloc[current_idx - 1]
    
    # Lấy ATR_M5
    atr_m5 = current_candle.get('atr', None)
    if pd.isna(atr_m5) or atr_m5 is None:
        return False, None, "ATR_M5 không có giá trị"
    
    low_current = current_candle['low']
    low_prev = prev_candle['low']
    
    # Điều kiện 1: Low_M5_current > Low_M5_prev
    if low_current <= low_prev:
        return False, None, f"Low_M5_current ({low_current:.5f}) <= Low_M5_prev ({low_prev:.5f})"
    
    # Điều kiện 2: |Low_M5_current - Low_M5_prev| < 0.4 × ATR_M5
    low_diff = abs(low_current - low_prev)
    threshold = 0.4 * atr_m5
    
    if low_diff >= threshold:
        return False, None, f"|Low_M5_current - Low_M5_prev| ({low_diff:.5f}) >= 0.4 × ATR_M5 ({threshold:.5f})"
    
    # Demand zone hợp lệ
    demand_price = low_prev
    return True, demand_price, f"Demand zone: {demand_price:.5f} (Low_M5_prev)"


# ============================================================================
# BAD MARKET CONDITIONS FILTER
# ============================================================================

def check_atr_ratio(df_m1: pd.DataFrame, current_idx: int = -1, lookback: int = 20) -> Tuple[bool, float, str]:
    """
    Kiểm tra ATR ratio để lọc thị trường xấu
    
    ATR_ratio = ATR_M1_current / ATR_M1_avg(lookback)
    
    Điều kiện:
    - ATR_ratio > 1.5 → Tạm dừng trade 40 phút
    - ATR_ratio < 0.5 → Không trade
    
    Args:
        df_m1: DataFrame M1 với ATR
        current_idx: Index của nến hiện tại (default: -1)
        lookback: Số nến để tính ATR average (default: 20)
    
    Returns:
        (is_valid, atr_ratio, message)
        - is_valid: True nếu ATR ratio hợp lệ (0.5 <= ratio <= 1.5)
        - atr_ratio: Giá trị ATR ratio
        - message: Thông báo kết quả
    """
    if len(df_m1) < lookback + 1:
        return False, 0.0, f"Không đủ dữ liệu (cần {lookback + 1} nến)"
    
    if current_idx < 0:
        current_idx = len(df_m1) + current_idx
    
    if current_idx < lookback or current_idx >= len(df_m1):
        return False, 0.0, "Index không hợp lệ"
    
    current_candle = df_m1.iloc[current_idx]
    current_atr = current_candle.get('atr', None)
    
    if pd.isna(current_atr) or current_atr is None:
        return False, 0.0, "ATR_M1_current không có giá trị"
    
    # Tính ATR average từ lookback nến trước
    atr_series = df_m1['atr'].iloc[current_idx - lookback:current_idx]
    atr_avg = atr_series.mean()
    
    if pd.isna(atr_avg) or atr_avg == 0:
        return False, 0.0, "ATR_M1_avg không có giá trị hoặc bằng 0"
    
    atr_ratio = current_atr / atr_avg
    
    if atr_ratio > 1.5:
        return False, atr_ratio, f"ATR_ratio ({atr_ratio:.3f}) > 1.5 → Tạm dừng trade 40 phút"
    elif atr_ratio < 0.5:
        return False, atr_ratio, f"ATR_ratio ({atr_ratio:.3f}) < 0.5 → Không trade"
    else:
        return True, atr_ratio, f"ATR_ratio ({atr_ratio:.3f}) hợp lệ (0.5 <= ratio <= 1.5)"


def check_atr_increasing(df_m1: pd.DataFrame, current_idx: int = -1, consecutive: int = 3) -> Tuple[bool, str]:
    """
    Kiểm tra ATR_M1 tăng liên tiếp và > ATR_M1_avg(20)
    
    Điều kiện:
    - ATR_M1 tăng liên tiếp 3 nến
    - ATR_M1 > ATR_M1_avg(20)
    → Dừng trade 40 phút
    
    Args:
        df_m1: DataFrame M1 với ATR
        current_idx: Index của nến hiện tại (default: -1)
        consecutive: Số nến tăng liên tiếp cần kiểm tra (default: 3)
    
    Returns:
        (should_pause, message)
        - should_pause: True nếu cần dừng trade 40 phút
        - message: Thông báo kết quả
    """
    if len(df_m1) < 20 + consecutive:
        return False, f"Không đủ dữ liệu (cần {20 + consecutive} nến)"
    
    if current_idx < 0:
        current_idx = len(df_m1) + current_idx
    
    if current_idx < 20 + consecutive - 1 or current_idx >= len(df_m1):
        return False, "Index không hợp lệ"
    
    # Kiểm tra ATR tăng liên tiếp
    atr_values = []
    for i in range(consecutive):
        idx = current_idx - i
        atr_val = df_m1.iloc[idx].get('atr', None)
        if pd.isna(atr_val) or atr_val is None:
            return False, f"ATR không có giá trị tại index {idx}"
        atr_values.append(atr_val)
    
    # Kiểm tra tăng liên tiếp (từ cũ đến mới)
    is_increasing = True
    for i in range(len(atr_values) - 1):
        if atr_values[i] >= atr_values[i + 1]:  # Không tăng
            is_increasing = False
            break
    
    if not is_increasing:
        return False, f"ATR không tăng liên tiếp {consecutive} nến"
    
    # Kiểm tra ATR_M1 > ATR_M1_avg(20)
    atr_series = df_m1['atr'].iloc[current_idx - 20:current_idx]
    atr_avg = atr_series.mean()
    
    if pd.isna(atr_avg):
        return False, "ATR_M1_avg(20) không có giá trị"
    
    current_atr = atr_values[-1]  # ATR của nến hiện tại
    
    if current_atr > atr_avg:
        return True, f"ATR tăng liên tiếp {consecutive} nến và ATR_M1 ({current_atr:.5f}) > ATR_M1_avg(20) ({atr_avg:.5f}) → Dừng trade 40 phút"
    else:
        return False, f"ATR tăng liên tiếp {consecutive} nến nhưng ATR_M1 ({current_atr:.5f}) <= ATR_M1_avg(20) ({atr_avg:.5f})"


def check_large_body(df_m1: pd.DataFrame, current_idx: int = -1, multiplier: float = 1.2) -> Tuple[bool, str]:
    """
    Kiểm tra body size lớn
    
    Điều kiện:
    - BodySize(M1) > 1.2 × ATR_M1 → Tạm dừng trade 15 phút
    
    Args:
        df_m1: DataFrame M1 với OHLC và ATR
        current_idx: Index của nến hiện tại (default: -1)
        multiplier: Hệ số nhân ATR (default: 1.2)
    
    Returns:
        (should_pause, message)
        - should_pause: True nếu cần tạm dừng trade 15 phút
        - message: Thông báo kết quả
    """
    if len(df_m1) < 1:
        return False, "Không có dữ liệu"
    
    if current_idx < 0:
        current_idx = len(df_m1) + current_idx
    
    if current_idx < 0 or current_idx >= len(df_m1):
        return False, "Index không hợp lệ"
    
    current_candle = df_m1.iloc[current_idx]
    
    body_size = calculate_body_size(current_candle)
    atr_m1 = current_candle.get('atr', None)
    
    if pd.isna(atr_m1) or atr_m1 is None:
        return False, "ATR_M1 không có giá trị"
    
    threshold = multiplier * atr_m1
    
    if body_size > threshold:
        return True, f"BodySize ({body_size:.5f}) > {multiplier} × ATR_M1 ({threshold:.5f}) → Tạm dừng trade 15 phút"
    else:
        return False, f"BodySize ({body_size:.5f}) <= {multiplier} × ATR_M1 ({threshold:.5f})"


def check_bad_market_conditions(df_m1: pd.DataFrame, current_idx: int = -1, enable_atr_increasing_check: bool = False) -> Tuple[bool, Dict, str]:
    """
    Tổng hợp kiểm tra tất cả điều kiện thị trường xấu
    
    Args:
        df_m1: DataFrame M1 với OHLC và ATR
        current_idx: Index của nến hiện tại (default: -1)
        enable_atr_increasing_check: Bật/tắt kiểm tra ATR tăng liên tiếp (default: False)
    
    Returns:
        (is_valid, conditions_dict, message)
        - is_valid: True nếu thị trường hợp lệ để trade
        - conditions_dict: Dict chứa kết quả từng điều kiện
        - message: Thông báo tổng hợp
    """
    conditions = {}
    messages = []
    
    # 1. Kiểm tra ATR ratio
    atr_ratio_valid, atr_ratio, atr_ratio_msg = check_atr_ratio(df_m1, current_idx)
    conditions['atr_ratio'] = {
        'valid': atr_ratio_valid,
        'value': atr_ratio,
        'message': atr_ratio_msg
    }
    if not atr_ratio_valid:
        messages.append(atr_ratio_msg)
    
    # 2. Kiểm tra ATR tăng liên tiếp (chỉ kiểm tra nếu enable)
    atr_increasing_pause = False
    if enable_atr_increasing_check:
        atr_increasing_pause, atr_increasing_msg = check_atr_increasing(df_m1, current_idx)
        conditions['atr_increasing'] = {
            'should_pause': atr_increasing_pause,
            'message': atr_increasing_msg,
            'enabled': True
        }
        if atr_increasing_pause:
            messages.append(atr_increasing_msg)
    else:
        conditions['atr_increasing'] = {
            'should_pause': False,
            'message': 'Kiểm tra ATR tăng liên tiếp đã tắt',
            'enabled': False
        }
    
    # 3. Kiểm tra body size lớn
    large_body_pause, large_body_msg = check_large_body(df_m1, current_idx)
    conditions['large_body'] = {
        'should_pause': large_body_pause,
        'message': large_body_msg
    }
    if large_body_pause:
        messages.append(large_body_msg)
    
    # Tổng hợp
    is_valid = atr_ratio_valid and not atr_increasing_pause and not large_body_pause
    
    if is_valid:
        message = "Thị trường hợp lệ để trade"
    else:
        message = " | ".join(messages)
    
    return is_valid, conditions, message


# ============================================================================
# SIDEWAY CONTEXT (M5)
# ============================================================================

def check_sideway_context(df_m5: pd.DataFrame, current_idx: int = -1, ema_period: int = 21, lookback: int = 3) -> Tuple[bool, str]:
    """
    Kiểm tra bối cảnh Sideway trên M5
    
    Điều kiện:
    - |EMA21_M5[i] - EMA21_M5[i-3]| < 0.2 × ATR_M5
    - |Close_M5 - EMA21_M5| < 0.5 × ATR_M5
    
    Args:
        df_m5: DataFrame M5 với OHLC, ATR và EMA21
        current_idx: Index của nến hiện tại (default: -1)
        ema_period: Period của EMA (default: 21)
        lookback: Số nến lookback để so sánh EMA (default: 3)
    
    Returns:
        (is_sideway, message)
        - is_sideway: True nếu là bối cảnh sideway
        - message: Thông báo kết quả
    """
    if len(df_m5) < lookback + 1:
        return False, f"Không đủ dữ liệu M5 (cần {lookback + 1} nến)"
    
    if current_idx < 0:
        current_idx = len(df_m5) + current_idx
    
    if current_idx < lookback or current_idx >= len(df_m5):
        return False, "Index không hợp lệ"
    
    current_candle = df_m5.iloc[current_idx]
    prev_candle = df_m5.iloc[current_idx - lookback]
    
    # Lấy ATR_M5
    atr_m5 = current_candle.get('atr', None)
    if pd.isna(atr_m5) or atr_m5 is None:
        return False, "ATR_M5 không có giá trị"
    
    # Lấy EMA21_M5
    ema_col = f'ema{ema_period}'
    ema_current = current_candle.get(ema_col, None)
    ema_prev = prev_candle.get(ema_col, None)
    
    if pd.isna(ema_current) or pd.isna(ema_prev):
        return False, f"EMA{ema_period}_M5 không có giá trị"
    
    # Điều kiện 1: |EMA21_M5[i] - EMA21_M5[i-3]| < 0.2 × ATR_M5
    ema_diff = abs(ema_current - ema_prev)
    threshold1 = 0.2 * atr_m5
    
    if ema_diff >= threshold1:
        return False, f"|EMA{ema_period}_M5[i] - EMA{ema_period}_M5[i-{lookback}]| ({ema_diff:.5f}) >= 0.2 × ATR_M5 ({threshold1:.5f})"
    
    # Điều kiện 2: |Close_M5 - EMA21_M5| < 0.5 × ATR_M5
    close_m5 = current_candle['close']
    close_ema_diff = abs(close_m5 - ema_current)
    threshold2 = 0.5 * atr_m5
    
    if close_ema_diff >= threshold2:
        return False, f"|Close_M5 - EMA{ema_period}_M5| ({close_ema_diff:.5f}) >= 0.5 × ATR_M5 ({threshold2:.5f})"
    
    # Bối cảnh sideway hợp lệ
    return True, f"Bối cảnh Sideway hợp lệ: EMA_diff={ema_diff:.5f}, Close_EMA_diff={close_ema_diff:.5f}"


# ============================================================================
# DELTA HIGH/LOW CALCULATION (M1)
# ============================================================================

def calculate_delta_high(df_m1: pd.DataFrame, current_idx: int = -1) -> Tuple[Optional[float], str]:
    """
    Tính DeltaHigh cho SELL signal
    
    DeltaHigh = High[i] - High[i-1]
    
    Args:
        df_m1: DataFrame M1 với OHLC
        current_idx: Index của nến hiện tại (default: -1)
    
    Returns:
        (delta_high, message)
        - delta_high: Giá trị DeltaHigh hoặc None nếu không tính được
        - message: Thông báo kết quả
    """
    if len(df_m1) < 2:
        return None, "Không đủ dữ liệu (cần ít nhất 2 nến)"
    
    if current_idx < 0:
        current_idx = len(df_m1) + current_idx
    
    if current_idx < 1 or current_idx >= len(df_m1):
        return None, "Index không hợp lệ"
    
    current_candle = df_m1.iloc[current_idx]
    prev_candle = df_m1.iloc[current_idx - 1]
    
    high_current = current_candle['high']
    high_prev = prev_candle['high']
    
    delta_high = high_current - high_prev
    
    return delta_high, f"DeltaHigh = {delta_high:.5f} (High[{current_idx}] - High[{current_idx-1}])"


def calculate_delta_low(df_m1: pd.DataFrame, current_idx: int = -1) -> Tuple[Optional[float], str]:
    """
    Tính DeltaLow cho BUY signal
    
    DeltaLow = Low[i-1] - Low[i]
    
    Args:
        df_m1: DataFrame M1 với OHLC
        current_idx: Index của nến hiện tại (default: -1)
    
    Returns:
        (delta_low, message)
        - delta_low: Giá trị DeltaLow hoặc None nếu không tính được
        - message: Thông báo kết quả
    """
    if len(df_m1) < 2:
        return None, "Không đủ dữ liệu (cần ít nhất 2 nến)"
    
    if current_idx < 0:
        current_idx = len(df_m1) + current_idx
    
    if current_idx < 1 or current_idx >= len(df_m1):
        return None, "Index không hợp lệ"
    
    current_candle = df_m1.iloc[current_idx]
    prev_candle = df_m1.iloc[current_idx - 1]
    
    low_current = current_candle['low']
    low_prev = prev_candle['low']
    
    delta_low = low_prev - low_current
    
    return delta_low, f"DeltaLow = {delta_low:.5f} (Low[{current_idx-1}] - Low[{current_idx}])"


def is_valid_delta_high(delta_high: float, atr_m1: float, threshold: float = 0.3) -> Tuple[bool, str]:
    """
    Kiểm tra DeltaHigh hợp lệ
    
    Điều kiện hợp lệ:
    - 0 < DeltaHigh < k × ATR(M1) (k = threshold, default: 0.3)
    
    Reset:
    - DeltaHigh ≤ 0 → RESET
    - DeltaHigh ≥ k × ATR → RESET
    
    Args:
        delta_high: Giá trị DeltaHigh
        atr_m1: ATR của M1
        threshold: Hệ số nhân ATR k (default: 0.3)
    
    Returns:
        (is_valid, message)
        - is_valid: True nếu DeltaHigh hợp lệ
        - message: Thông báo kết quả
    """
    if delta_high is None or pd.isna(delta_high):
        return False, "DeltaHigh không có giá trị"
    
    if pd.isna(atr_m1) or atr_m1 is None or atr_m1 <= 0:
        return False, "ATR_M1 không hợp lệ"
    
    threshold_value = threshold * atr_m1
    
    if delta_high <= 0:
        return False, f"DeltaHigh ({delta_high:.5f}) <= 0 → RESET"
    
    if delta_high >= threshold_value:
        return False, f"DeltaHigh ({delta_high:.5f}) >= {threshold} × ATR ({threshold_value:.5f}) → RESET"
    
    return True, f"DeltaHigh ({delta_high:.5f}) hợp lệ (0 < {delta_high:.5f} < {threshold_value:.5f})"


def is_valid_delta_low(delta_low: float, atr_m1: float, threshold: float = 0.3) -> Tuple[bool, str]:
    """
    Kiểm tra DeltaLow hợp lệ
    
    Điều kiện hợp lệ:
    - 0 < DeltaLow < k × ATR(M1) (k = threshold, default: 0.3)
    
    Reset:
    - DeltaLow ≤ 0 → RESET
    - DeltaLow >= k × ATR → RESET
    
    Args:
        delta_low: Giá trị DeltaLow
        atr_m1: ATR của M1
        threshold: Hệ số nhân ATR k (default: 0.3)
    
    Returns:
        (is_valid, message)
        - is_valid: True nếu DeltaLow hợp lệ
        - message: Thông báo kết quả
    """
    if delta_low is None or pd.isna(delta_low):
        return False, "DeltaLow không có giá trị"
    
    if pd.isna(atr_m1) or atr_m1 is None or atr_m1 <= 0:
        return False, "ATR_M1 không hợp lệ"
    
    threshold_value = threshold * atr_m1
    
    if delta_low <= 0:
        return False, f"DeltaLow ({delta_low:.5f}) <= 0 → RESET"
    
    if delta_low >= threshold_value:
        return False, f"DeltaLow ({delta_low:.5f}) >= {threshold} × ATR ({threshold_value:.5f}) → RESET"
    
    return True, f"DeltaLow ({delta_low:.5f}) hợp lệ (0 < {delta_low:.5f} < {threshold_value:.5f})"


# ============================================================================
# COUNT TRACKING
# ============================================================================

class DeltaCountTracker:
    """
    Class để theo dõi Count cho DeltaHigh/DeltaLow
    """
    
    def __init__(self, min_count: int = 2):
        """
        Args:
            min_count: Số Count tối thiểu để trigger signal (default: 2)
        """
        self.count = 0
        self.min_count = min_count
        self.last_valid_idx = None
    
    def update(self, is_valid: bool, current_idx: int) -> Tuple[int, bool]:
        """
        Cập nhật Count
        
        Args:
            is_valid: True nếu Delta hợp lệ
            current_idx: Index của nến hiện tại
        
        Returns:
            (count, is_triggered)
            - count: Giá trị Count hiện tại
            - is_triggered: True nếu Count >= min_count
        """
        if is_valid:
            # Kiểm tra xem có liên tiếp không
            if self.last_valid_idx is not None and current_idx != self.last_valid_idx + 1:
                # Không liên tiếp → Reset
                self.count = 0
            
            self.count += 1
            self.last_valid_idx = current_idx
        else:
            # Reset Count
            self.count = 0
            self.last_valid_idx = None
        
        is_triggered = self.count >= self.min_count
        return self.count, is_triggered
    
    def reset(self):
        """Reset Count về 0"""
        self.count = 0
        self.last_valid_idx = None
    
    def get_count(self) -> int:
        """Lấy giá trị Count hiện tại"""
        return self.count


# ============================================================================
# SIGNAL CONDITIONS
# ============================================================================

def check_sell_signal_condition(
    df_m1: pd.DataFrame,
    supply_price: float,
    df_m5: pd.DataFrame,
    current_idx: int = -1,
    buffer_multiplier: float = 0.2
) -> Tuple[bool, str]:
    """
    Kiểm tra điều kiện SELL signal
    
    Điều kiện:
    - High_M1_current < High_M5_supply + 0.2 × ATR_M5
    
    Args:
        df_m1: DataFrame M1 với OHLC
        supply_price: Giá Supply (High_M5_prev)
        df_m5: DataFrame M5 với ATR
        current_idx: Index của nến M1 hiện tại (default: -1)
        buffer_multiplier: Hệ số nhân ATR cho buffer (default: 0.2)
    
    Returns:
        (is_valid, message)
        - is_valid: True nếu điều kiện SELL hợp lệ
        - message: Thông báo kết quả
    """
    if len(df_m1) < 1:
        return False, "Không có dữ liệu M1"
    
    if current_idx < 0:
        current_idx = len(df_m1) + current_idx
    
    if current_idx < 0 or current_idx >= len(df_m1):
        return False, "Index không hợp lệ"
    
    # Lấy ATR_M5 (từ nến M5 hiện tại)
    if len(df_m5) < 1:
        return False, "Không có dữ liệu M5"
    
    m5_current = df_m5.iloc[-1]
    atr_m5 = m5_current.get('atr', None)
    
    if pd.isna(atr_m5) or atr_m5 is None:
        return False, "ATR_M5 không có giá trị"
    
    current_candle = df_m1.iloc[current_idx]
    high_m1_current = current_candle['high']
    
    threshold = supply_price + (buffer_multiplier * atr_m5)
    
    if high_m1_current < threshold:
        return True, f"High_M1_current ({high_m1_current:.5f}) < Supply + {buffer_multiplier}×ATR_M5 ({threshold:.5f})"
    else:
        return False, f"High_M1_current ({high_m1_current:.5f}) >= Supply + {buffer_multiplier}×ATR_M5 ({threshold:.5f})"


def check_buy_signal_condition(
    df_m1: pd.DataFrame,
    demand_price: float,
    df_m5: pd.DataFrame,
    current_idx: int = -1,
    buffer_multiplier: float = 0.2
) -> Tuple[bool, str]:
    """
    Kiểm tra điều kiện BUY signal
    
    Điều kiện:
    - Low_M1_current > Low_M5_demand + 0.2 × ATR_M5
    
    Args:
        df_m1: DataFrame M1 với OHLC
        demand_price: Giá Demand (Low_M5_prev)
        df_m5: DataFrame M5 với ATR
        current_idx: Index của nến M1 hiện tại (default: -1)
        buffer_multiplier: Hệ số nhân ATR cho buffer (default: 0.2)
    
    Returns:
        (is_valid, message)
        - is_valid: True nếu điều kiện BUY hợp lệ
        - message: Thông báo kết quả
    """
    if len(df_m1) < 1:
        return False, "Không có dữ liệu M1"
    
    if current_idx < 0:
        current_idx = len(df_m1) + current_idx
    
    if current_idx < 0 or current_idx >= len(df_m1):
        return False, "Index không hợp lệ"
    
    # Lấy ATR_M5 (từ nến M5 hiện tại)
    if len(df_m5) < 1:
        return False, "Không có dữ liệu M5"
    
    m5_current = df_m5.iloc[-1]
    atr_m5 = m5_current.get('atr', None)
    
    if pd.isna(atr_m5) or atr_m5 is None:
        return False, "ATR_M5 không có giá trị"
    
    current_candle = df_m1.iloc[current_idx]
    low_m1_current = current_candle['low']
    
    threshold = demand_price + (buffer_multiplier * atr_m5)
    
    if low_m1_current > threshold:
        return True, f"Low_M1_current ({low_m1_current:.5f}) > Demand + {buffer_multiplier}×ATR_M5 ({threshold:.5f})"
    else:
        return False, f"Low_M1_current ({low_m1_current:.5f}) <= Demand + {buffer_multiplier}×ATR_M5 ({threshold:.5f})"


# ============================================================================
# POSITION MANAGEMENT
# ============================================================================

def calculate_sl_tp(
    entry_price: float,
    signal_type: str,
    atr_m1: float,
    atr_multiplier: float = 2.0,
    tp_multiplier: float = 2.0,
    symbol_info: Optional[mt5.SymbolInfo] = None
) -> Tuple[float, float, float, Dict]:
    """
    Tính SL và TP cho lệnh
    
    Công thức:
    - SL = 2 × ATR = 1R
    - TP1 = +1R (chốt 50%, dời SL về BE)
    - TP2 = 2R
    
    Args:
        entry_price: Giá entry
        signal_type: "BUY" hoặc "SELL"
        atr_m1: ATR của M1
        atr_multiplier: Hệ số nhân ATR cho SL (default: 2.0)
        tp_multiplier: Hệ số nhân SL cho TP (default: 2.0)
        symbol_info: MT5 symbol info để normalize digits
    
    Returns:
        (sl, tp1, tp2, info_dict)
        - sl: Stop Loss
        - tp1: Take Profit 1 (1R)
        - tp2: Take Profit 2 (2R)
        - info_dict: Dict chứa thông tin chi tiết
    """
    sl_distance = atr_multiplier * atr_m1
    tp1_distance = sl_distance  # 1R
    tp2_distance = tp_multiplier * sl_distance  # 2R
    
    if signal_type.upper() == "BUY":
        sl = entry_price - sl_distance
        tp1 = entry_price + tp1_distance
        tp2 = entry_price + tp2_distance
    else:  # SELL
        sl = entry_price + sl_distance
        tp1 = entry_price - tp1_distance
        tp2 = entry_price - tp2_distance
    
    # Normalize to symbol digits
    if symbol_info is not None:
        digits = symbol_info.digits
        sl = round(sl, digits)
        tp1 = round(tp1, digits)
        tp2 = round(tp2, digits)
        entry_price = round(entry_price, digits)
    
    info = {
        'sl_distance': sl_distance,
        'tp1_distance': tp1_distance,
        'tp2_distance': tp2_distance,
        'atr_multiplier': atr_multiplier,
        'tp_multiplier': tp_multiplier,
        'r_ratio': 1.0  # 1R
    }
    
    return sl, tp1, tp2, info


def check_max_positions_per_zone(
    positions: List,
    zone_price: float,
    zone_type: str,
    max_positions: int = 2,
    tolerance: float = 0.0001
) -> Tuple[bool, int, str]:
    """
    Kiểm tra số lượng lệnh tối đa trong một vùng Supply/Demand
    
    Args:
        positions: List các positions hiện tại
        zone_price: Giá của vùng Supply/Demand
        zone_type: "SUPPLY" hoặc "DEMAND"
        max_positions: Số lệnh tối đa (default: 2)
        tolerance: Tolerance để so sánh giá (default: 0.0001)
    
    Returns:
        (is_valid, count, message)
        - is_valid: True nếu có thể mở thêm lệnh
        - count: Số lệnh hiện tại trong vùng
        - message: Thông báo kết quả
    """
    count = 0
    
    for pos in positions:
        if zone_type.upper() == "SUPPLY":
            # SELL positions gần Supply zone
            if pos.type == mt5.ORDER_TYPE_SELL:
                if abs(pos.price_open - zone_price) <= tolerance:
                    count += 1
        else:  # DEMAND
            # BUY positions gần Demand zone
            if pos.type == mt5.ORDER_TYPE_BUY:
                if abs(pos.price_open - zone_price) <= tolerance:
                    count += 1
    
    if count >= max_positions:
        return False, count, f"Đã đạt max {max_positions} lệnh trong vùng {zone_type} (hiện tại: {count})"
    else:
        return True, count, f"Số lệnh trong vùng {zone_type}: {count}/{max_positions}"


def check_m5_candle_change(
    df_m5: pd.DataFrame,
    last_trade_time: datetime,
    current_idx: int = -1
) -> Tuple[bool, str]:
    """
    Kiểm tra M5 đã đổi nến chưa
    
    Nếu 1 lệnh SL → không vào lại cho đến khi M5 đổi nến
    
    Args:
        df_m5: DataFrame M5
        last_trade_time: Thời gian lệnh cuối cùng
        current_idx: Index của nến M5 hiện tại (default: -1)
    
    Returns:
        (has_changed, message)
        - has_changed: True nếu M5 đã đổi nến
        - message: Thông báo kết quả
    """
    if len(df_m5) < 1:
        return False, "Không có dữ liệu M5"
    
    if current_idx < 0:
        current_idx = len(df_m5) + current_idx
    
    if current_idx < 0 or current_idx >= len(df_m5):
        return False, "Index không hợp lệ"
    
    current_candle_time = df_m5.index[current_idx]
    
    # So sánh thời gian
    if isinstance(current_candle_time, pd.Timestamp):
        current_candle_time = current_candle_time.to_pydatetime()
    
    if current_candle_time > last_trade_time:
        return True, f"M5 đã đổi nến (current: {current_candle_time}, last_trade: {last_trade_time})"
    else:
        return False, f"M5 chưa đổi nến (current: {current_candle_time}, last_trade: {last_trade_time})"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_min_atr_threshold(symbol: str, config: Optional[Dict] = None) -> float:
    """
    Get minimum ATR threshold based on symbol type
    
    Args:
        symbol: Trading symbol (EURUSD, XAUUSD, BTCUSD, etc.)
        config: Config dict (optional, to override with custom value)
    
    Returns:
        min_atr: Minimum ATR threshold value
    """
    # Check if custom threshold is provided in config
    if config is not None:
        custom_min_atr = config.get('min_atr', None)
        if custom_min_atr is not None:
            return custom_min_atr
    
    symbol_upper = symbol.upper()
    
    # EURUSD and similar forex pairs: 0.00011 (1.1 pips)
    if 'EURUSD' in symbol_upper or 'GBPUSD' in symbol_upper or 'USDJPY' in symbol_upper or 'AUDUSD' in symbol_upper:
        return 0.00011
    
    # XAUUSD (Gold): Typically ATR is 0.1-2.0 USD, threshold ~0.1
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        return 0.1
    
    # BTCUSD: Typically ATR is 50-500 USD, threshold ~50
    if 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
        return 50.0
    
    # ETHUSD: Similar to BTC but smaller scale
    if 'ETHUSD' in symbol_upper or 'ETH' in symbol_upper:
        return 5.0
    
    # Default: Use EURUSD threshold
    return 0.00011


def get_delta_threshold_multiplier(symbol: str, config: Optional[Dict] = None) -> float:
    """
    Get delta threshold multiplier (k) based on symbol type
    
    Công thức: DeltaHigh/DeltaLow hợp lệ khi: 0 < Delta < k × ATR(M1)
    
    Args:
        symbol: Trading symbol (EURUSD, XAUUSD, BTCUSD, etc.)
        config: Config dict (optional, to override with custom value)
    
    Returns:
        k: Delta threshold multiplier
        - Forex (EURUSD, etc.): 0.3 (default)
        - Gold (XAUUSD): 0.33
        - BTCUSD: 0.48
    """
    # Check if custom multiplier is provided in config
    if config is not None:
        custom_k = config.get('delta_threshold_multiplier', None)
        if custom_k is not None:
            return float(custom_k)
    
    symbol_upper = symbol.upper()
    
    # XAUUSD (Gold): 0.33
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        return 0.33
    
    # BTCUSD: 0.48
    if 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
        return 0.48
    
    # ETHUSD: Similar to BTC
    if 'ETHUSD' in symbol_upper or 'ETH' in symbol_upper:
        return 0.48
    
    # Forex (EURUSD, GBPUSD, USDJPY, AUDUSD, etc.): 0.3 (default)
    return 0.3
