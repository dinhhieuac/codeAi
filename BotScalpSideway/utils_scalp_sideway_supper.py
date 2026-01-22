"""
Utility functions for Scalp Sideway Supper Strategy
Hỗ trợ nhiều cặp giao dịch: EURUSD, XAUUSD, BTCUSD, ETHUSD, etc.

Based on: botsupper.md
"""

import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, List


# ============================================================================
# INDICATOR CALCULATIONS
# ============================================================================

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


# ============================================================================
# ATR RATIO FILTER
# ============================================================================

def check_atr_ratio_supper(df_m1: pd.DataFrame, current_idx: int = -1, lookback: int = 20) -> Tuple[bool, float, str]:
    """
    Kiểm tra ATR ratio cho bot supper
    
    Điều kiện: ATR_current / ATR_avg(20) ∈ [0.8; 1.6]
    
    Nếu ATR ratio ∉ [0.8; 1.6]:
    → KHÔNG xét Delta
    → Count = 0
    
    Args:
        df_m1: DataFrame M1 với ATR
        current_idx: Index của nến hiện tại (default: -1)
        lookback: Số nến để tính ATR average (default: 20)
    
    Returns:
        (is_valid, atr_ratio, message)
        - is_valid: True nếu ATR ratio ∈ [0.8; 1.6]
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
    
    if 0.8 <= atr_ratio <= 1.6:
        return True, atr_ratio, f"ATR_ratio ({atr_ratio:.3f}) ∈ [0.8; 1.6] → Hợp lệ"
    else:
        return False, atr_ratio, f"ATR_ratio ({atr_ratio:.3f}) ∉ [0.8; 1.6] → KHÔNG xét Delta, Count = 0"


# ============================================================================
# DELTA CALCULATION WITH DIRECTION LOCK
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


def is_valid_delta_sell_supper(
    delta_high: float,
    delta_low: float,
    atr_m1: float,
    threshold: float = 0.3
) -> Tuple[bool, str]:
    """
    Kiểm tra Delta hợp lệ cho SELL signal (với điều kiện khóa hướng)
    
    Điều kiện hợp lệ:
    - DeltaHigh > 0
    - DeltaHigh < k × ATR(M1)
    - DeltaLow ≤ 0 (khóa hướng)
    
    Nếu không thỏa → Count = 0
    
    Args:
        delta_high: Giá trị DeltaHigh
        delta_low: Giá trị DeltaLow (để khóa hướng)
        atr_m1: ATR của M1
        threshold: Hệ số nhân ATR k (default: 0.3)
    
    Returns:
        (is_valid, message)
        - is_valid: True nếu Delta hợp lệ
        - message: Thông báo kết quả
    """
    if delta_high is None or pd.isna(delta_high):
        return False, "DeltaHigh không có giá trị"
    
    if delta_low is None or pd.isna(delta_low):
        return False, "DeltaLow không có giá trị"
    
    if pd.isna(atr_m1) or atr_m1 is None or atr_m1 <= 0:
        return False, "ATR_M1 không hợp lệ"
    
    threshold_value = threshold * atr_m1
    
    # Điều kiện 1: DeltaHigh > 0
    if delta_high <= 0:
        return False, f"DeltaHigh ({delta_high:.5f}) <= 0 → Count = 0"
    
    # Điều kiện 2: DeltaHigh < k × ATR
    if delta_high >= threshold_value:
        return False, f"DeltaHigh ({delta_high:.5f}) >= {threshold} × ATR ({threshold_value:.5f}) → Count = 0"
    
    # Điều kiện 3: DeltaLow ≤ 0 (khóa hướng)
    if delta_low > 0:
        return False, f"DeltaLow ({delta_low:.5f}) > 0 → Không khóa hướng, Count = 0"
    
    return True, f"DeltaHigh ({delta_high:.5f}) hợp lệ: > 0, < {threshold_value:.5f}, DeltaLow ({delta_low:.5f}) ≤ 0 → Count + 1"


def is_valid_delta_buy_supper(
    delta_low: float,
    delta_high: float,
    atr_m1: float,
    threshold: float = 0.3
) -> Tuple[bool, str]:
    """
    Kiểm tra Delta hợp lệ cho BUY signal (với điều kiện khóa hướng)
    
    Điều kiện hợp lệ:
    - DeltaLow > 0
    - DeltaLow < k × ATR(M1)
    - DeltaHigh ≤ 0 (khóa hướng)
    
    Nếu không thỏa → Count = 0
    
    Args:
        delta_low: Giá trị DeltaLow
        delta_high: Giá trị DeltaHigh (để khóa hướng)
        atr_m1: ATR của M1
        threshold: Hệ số nhân ATR k (default: 0.3)
    
    Returns:
        (is_valid, message)
        - is_valid: True nếu Delta hợp lệ
        - message: Thông báo kết quả
    """
    if delta_low is None or pd.isna(delta_low):
        return False, "DeltaLow không có giá trị"
    
    if delta_high is None or pd.isna(delta_high):
        return False, "DeltaHigh không có giá trị"
    
    if pd.isna(atr_m1) or atr_m1 is None or atr_m1 <= 0:
        return False, "ATR_M1 không hợp lệ"
    
    threshold_value = threshold * atr_m1
    
    # Điều kiện 1: DeltaLow > 0
    if delta_low <= 0:
        return False, f"DeltaLow ({delta_low:.5f}) <= 0 → Count = 0"
    
    # Điều kiện 2: DeltaLow < k × ATR
    if delta_low >= threshold_value:
        return False, f"DeltaLow ({delta_low:.5f}) >= {threshold} × ATR ({threshold_value:.5f}) → Count = 0"
    
    # Điều kiện 3: DeltaHigh ≤ 0 (khóa hướng)
    if delta_high > 0:
        return False, f"DeltaHigh ({delta_high:.5f}) > 0 → Không khóa hướng, Count = 0"
    
    return True, f"DeltaLow ({delta_low:.5f}) hợp lệ: > 0, < {threshold_value:.5f}, DeltaHigh ({delta_high:.5f}) ≤ 0 → Count + 1"


# ============================================================================
# RANGE FILTER
# ============================================================================

def check_range_filter(
    df_m1: pd.DataFrame,
    current_idx: int = -1,
    atr_m1: float = None,
    q_multiplier: float = 0.55
) -> Tuple[bool, float, str]:
    """
    Kiểm tra Range filter cho nến delta hợp lệ
    
    Điều kiện: Range ≥ q × ATR
    Range = High - Low
    
    Nếu Range < q × ATR → Count = 0
    
    Args:
        df_m1: DataFrame M1 với OHLC
        current_idx: Index của nến hiện tại (default: -1)
        atr_m1: ATR của M1 (nếu None sẽ lấy từ df_m1)
        q_multiplier: Hệ số nhân ATR q (default: 0.55)
    
    Returns:
        (is_valid, range_value, message)
        - is_valid: True nếu Range ≥ q × ATR
        - range_value: Giá trị Range
        - message: Thông báo kết quả
    """
    if len(df_m1) < 1:
        return False, 0.0, "Không có dữ liệu"
    
    if current_idx < 0:
        current_idx = len(df_m1) + current_idx
    
    if current_idx < 0 or current_idx >= len(df_m1):
        return False, 0.0, "Index không hợp lệ"
    
    current_candle = df_m1.iloc[current_idx]
    
    # Tính Range
    range_value = current_candle['high'] - current_candle['low']
    
    # Lấy ATR
    if atr_m1 is None:
        atr_m1 = current_candle.get('atr', None)
        if pd.isna(atr_m1) or atr_m1 is None:
            return False, range_value, "ATR_M1 không có giá trị"
    
    threshold = q_multiplier * atr_m1
    
    if range_value >= threshold:
        return True, range_value, f"Range ({range_value:.5f}) ≥ {q_multiplier} × ATR ({threshold:.5f}) → Hợp lệ"
    else:
        return False, range_value, f"Range ({range_value:.5f}) < {q_multiplier} × ATR ({threshold:.5f}) → Count = 0"


# ============================================================================
# COUNT TRACKING
# ============================================================================

class DeltaCountTrackerSupper:
    """
    Class để theo dõi Count cho DeltaHigh/DeltaLow (bot supper)
    
    Logic: Count chỉ tăng khi nến M1 ĐÓNG, không tăng trong khi nến đang hình thành
    """
    
    def __init__(self, min_count: int = 2):
        """
        Args:
            min_count: Số Count tối thiểu để trigger signal (default: 2)
        """
        self.count = 0
        self.min_count = min_count
        self.last_valid_idx = None
        self.last_processed_idx = None  # Track nến đã xử lý để tránh tăng Count nhiều lần
    
    def update(self, is_valid: bool, current_idx: int) -> Tuple[int, bool]:
        """
        Cập nhật Count - CHỈ tăng khi có nến M1 mới đóng
        
        Logic:
        - 0-60s: Theo dõi nến liên tục, KHÔNG tăng Count
        - Khi nến đóng: Mới tăng Count nếu Delta hợp lệ
        
        Args:
            is_valid: True nếu Delta hợp lệ
            current_idx: Index của nến hiện tại (nến đã đóng)
        
        Returns:
            (count, is_triggered)
            - count: Giá trị Count hiện tại
            - is_triggered: True nếu Count >= min_count
        """
        # Chỉ xử lý khi có nến M1 mới đóng (current_idx thay đổi)
        if self.last_processed_idx is not None and current_idx == self.last_processed_idx:
            # Cùng nến → Không tăng Count (nến đang hình thành hoặc đã xử lý)
            is_triggered = self.count >= self.min_count
            return self.count, is_triggered
        
        # Có nến mới → Đánh dấu đã xử lý
        self.last_processed_idx = current_idx
        
        if is_valid:
            # Kiểm tra xem có liên tiếp không
            if self.last_valid_idx is not None and current_idx != self.last_valid_idx + 1:
                # Không liên tiếp → Reset
                self.count = 0
            
            # Tăng Count khi nến đóng và Delta hợp lệ
            self.count += 1
            self.last_valid_idx = current_idx
        else:
            # Reset Count khi Delta không hợp lệ
            self.count = 0
            self.last_valid_idx = None
        
        is_triggered = self.count >= self.min_count
        return self.count, is_triggered
    
    def reset(self):
        """Reset Count về 0"""
        self.count = 0
        self.last_valid_idx = None
        self.last_processed_idx = None  # Reset cả processed index
    
    def get_count(self) -> int:
        """Lấy giá trị Count hiện tại"""
        return self.count


# ============================================================================
# SL/TP CALCULATION
# ============================================================================

def calculate_sl_tp_supper(
    entry_price: float,
    signal_type: str,
    atr_m1: float,
    symbol_info: Optional[mt5.SymbolInfo] = None
) -> Tuple[float, float, Dict]:
    """
    Tính SL và TP cho lệnh (bot supper)
    
    Công thức:
    - SL = 2 × ATR
    - TP = 2 × SL = 4 × ATR
    
    Args:
        entry_price: Giá entry
        signal_type: "BUY" hoặc "SELL"
        atr_m1: ATR của M1
        symbol_info: MT5 symbol info để normalize digits
    
    Returns:
        (sl, tp, info_dict)
        - sl: Stop Loss
        - tp: Take Profit
        - info_dict: Dict chứa thông tin chi tiết
    """
    sl_distance = 2.0 * atr_m1
    tp_distance = 2.0 * sl_distance  # TP = 2 × SL = 4 × ATR
    
    if signal_type.upper() == "BUY":
        sl = entry_price - sl_distance
        tp = entry_price + tp_distance
    else:  # SELL
        sl = entry_price + sl_distance
        tp = entry_price - tp_distance
    
    # Normalize to symbol digits
    if symbol_info is not None:
        digits = symbol_info.digits
        sl = round(sl, digits)
        tp = round(tp, digits)
        entry_price = round(entry_price, digits)
    
    info = {
        'sl_distance': sl_distance,
        'tp_distance': tp_distance,
        'atr_multiplier_sl': 2.0,
        'sl_multiplier_tp': 2.0,
        'r_ratio': 1.0  # 1R = SL distance
    }
    
    return sl, tp, info


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_delta_threshold_multiplier_supper(symbol: str, config: Optional[Dict] = None) -> float:
    """
    Get delta threshold multiplier (k) based on symbol type
    
    Args:
        symbol: Trading symbol (EURUSD, XAUUSD, BTCUSD, etc.)
        config: Config dict (optional, to override with custom value)
    
    Returns:
        k: Delta threshold multiplier
        - Forex (EURUSD, etc.): 0.3
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
    
    # Forex (EURUSD, GBPUSD, USDJPY, AUDUSD, etc.): 0.3 (default)
    return 0.3


def get_range_multiplier_supper(symbol: str, config: Optional[Dict] = None) -> float:
    """
    Get range multiplier (q) based on symbol type
    
    Args:
        symbol: Trading symbol (EURUSD, XAUUSD, BTCUSD, etc.)
        config: Config dict (optional, to override with custom value)
    
    Returns:
        q: Range multiplier
        - Forex (EURUSD, etc.): 0.55
        - Gold (XAUUSD): 0.65
        - BTCUSD: 0.7
    """
    # Check if custom multiplier is provided in config
    if config is not None:
        custom_q = config.get('range_multiplier', None)
        if custom_q is not None:
            return float(custom_q)
    
    symbol_upper = symbol.upper()
    
    # XAUUSD (Gold): 0.65
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        return 0.65
    
    # BTCUSD: 0.7
    if 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
        return 0.7
    
    # Forex (EURUSD, GBPUSD, USDJPY, AUDUSD, etc.): 0.55 (default)
    return 0.55


def get_trailing_e_multiplier_supper(symbol: str, config: Optional[Dict] = None) -> float:
    """
    Get trailing E multiplier based on symbol type
    
    Args:
        symbol: Trading symbol (EURUSD, XAUUSD, BTCUSD, etc.)
        config: Config dict (optional, to override with custom value)
    
    Returns:
        E: Trailing E multiplier
        - Forex (EURUSD, etc.): 0.3
        - Gold (XAUUSD): 0.35
        - BTCUSD: 0.4
    """
    # Check if custom multiplier is provided in config
    if config is not None:
        custom_e = config.get('trailing_e_multiplier', None)
        if custom_e is not None:
            return float(custom_e)
    
    symbol_upper = symbol.upper()
    
    # XAUUSD (Gold): 0.35
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        return 0.35
    
    # BTCUSD: 0.4
    if 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
        return 0.4
    
    # Forex (EURUSD, GBPUSD, USDJPY, AUDUSD, etc.): 0.3 (default)
    return 0.3
