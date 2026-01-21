"""
Utility functions for Slideway New Trendline Strategy
Hỗ trợ nhiều cặp giao dịch: EURUSD, XAUUSD, BTCUSD, ETHUSD, etc.

Based on: botslideway_newtrendline.md
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


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI)
    
    Args:
        series: Price series (typically close)
        period: RSI period (default: 14)
    
    Returns:
        RSI series
    """
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


# ============================================================================
# SWING POINT DETECTION
# ============================================================================

def find_swing_high(df: pd.DataFrame, lookback: int = 5, current_idx: int = -1) -> Optional[Dict]:
    """
    Tìm swing high gần nhất
    
    Swing High: Đỉnh cao hơn lookback nến ở cả hai bên
    
    Args:
        df: DataFrame với OHLC
        lookback: Số nến lookback (default: 5)
        current_idx: Index hiện tại (default: -1 for last candle)
    
    Returns:
        Dict với {'index': int, 'price': float, 'rsi': float} hoặc None
    """
    if len(df) < lookback * 2 + 1:
        return None
    
    if current_idx < 0:
        current_idx = len(df) + current_idx
    
    # Tìm swing high trong lookback window
    for i in range(current_idx - lookback, max(lookback, current_idx - 50), -1):
        if i < lookback or i >= len(df) - lookback:
            continue
        
        is_swing_high = True
        current_high = df.iloc[i]['high']
        
        # Kiểm tra tất cả nến trong lookback window
        for j in range(i - lookback, i + lookback + 1):
            if j != i and df.iloc[j]['high'] >= current_high:
                is_swing_high = False
                break
        
        if is_swing_high:
            rsi = df.iloc[i].get('rsi', None)
            return {
                'index': i,
                'price': current_high,
                'rsi': rsi if pd.notna(rsi) else None,
                'time': df.index[i] if hasattr(df.index[i], 'to_pydatetime') else None
            }
    
    return None


def find_swing_low(df: pd.DataFrame, lookback: int = 5, current_idx: int = -1) -> Optional[Dict]:
    """
    Tìm swing low gần nhất
    
    Swing Low: Đáy thấp hơn lookback nến ở cả hai bên
    
    Args:
        df: DataFrame với OHLC
        lookback: Số nến lookback (default: 5)
        current_idx: Index hiện tại (default: -1 for last candle)
    
    Returns:
        Dict với {'index': int, 'price': float, 'rsi': float} hoặc None
    """
    if len(df) < lookback * 2 + 1:
        return None
    
    if current_idx < 0:
        current_idx = len(df) + current_idx
    
    # Tìm swing low trong lookback window
    for i in range(current_idx - lookback, max(lookback, current_idx - 50), -1):
        if i < lookback or i >= len(df) - lookback:
            continue
        
        is_swing_low = True
        current_low = df.iloc[i]['low']
        
        # Kiểm tra tất cả nến trong lookback window
        for j in range(i - lookback, i + lookback + 1):
            if j != i and df.iloc[j]['low'] <= current_low:
                is_swing_low = False
                break
        
        if is_swing_low:
            rsi = df.iloc[i].get('rsi', None)
            return {
                'index': i,
                'price': current_low,
                'rsi': rsi if pd.notna(rsi) else None,
                'time': df.index[i] if hasattr(df.index[i], 'to_pydatetime') else None
            }
    
    return None


# ============================================================================
# PULLBACK VALIDATION
# ============================================================================

def check_pullback_buy(
    df_m1: pd.DataFrame,
    swing_high: Dict,
    current_idx: int = -1,
    max_candles: int = 30
) -> Tuple[bool, str]:
    """
    Kiểm tra sóng hồi hợp lệ cho BUY
    
    Điều kiện:
    - Sau khi hình thành swing high
    - Giá không tạo đỉnh cao hơn swing high
    - Số nến hồi tối đa: ≤ 30 nến
    - RSI hồi về vùng 35 – 50
    - Trong quá trình hồi: Giá không phá cấu trúc xu hướng tăng chính
    
    Args:
        df_m1: DataFrame M1 với OHLC và RSI
        swing_high: Dict chứa thông tin swing high
        current_idx: Index hiện tại (default: -1)
        max_candles: Số nến hồi tối đa (default: 30)
    
    Returns:
        (is_valid, message)
    """
    if current_idx < 0:
        current_idx = len(df_m1) + current_idx
    
    swing_idx = swing_high['index']
    swing_price = swing_high['price']
    
    # Kiểm tra số nến hồi
    candles_since_swing = current_idx - swing_idx
    if candles_since_swing > max_candles:
        return False, f"Số nến hồi ({candles_since_swing}) > {max_candles} nến"
    
    # Kiểm tra giá không tạo đỉnh cao hơn swing high
    for i in range(swing_idx + 1, current_idx + 1):
        if i >= len(df_m1):
            break
        if df_m1.iloc[i]['high'] > swing_price:
            return False, f"Giá đã tạo đỉnh cao hơn swing high tại index {i}"
    
    # Kiểm tra RSI hồi về vùng 35-50
    current_rsi = df_m1.iloc[current_idx].get('rsi', None)
    if pd.notna(current_rsi):
        if not (35 <= current_rsi <= 50):
            return False, f"RSI ({current_rsi:.2f}) không trong vùng 35-50"
    else:
        return False, "RSI không có giá trị"
    
    # Kiểm tra giá không phá cấu trúc xu hướng tăng chính
    # (Có thể kiểm tra EMA50 > EMA200 hoặc giá không break below swing low trước đó)
    # Tạm thời bỏ qua điều kiện này vì cần thêm logic phức tạp
    
    return True, f"Pullback hợp lệ: {candles_since_swing} nến, RSI: {current_rsi:.2f}"


def check_pullback_sell(
    df_m1: pd.DataFrame,
    swing_low: Dict,
    current_idx: int = -1,
    max_candles: int = 30
) -> Tuple[bool, str]:
    """
    Kiểm tra sóng hồi hợp lệ cho SELL
    
    Điều kiện:
    - Sau khi hình thành swing low
    - Giá không tạo đáy thấp hơn swing low
    - Số nến hồi tối đa: ≤ 30 nến
    - RSI hồi về vùng 50 – 65
    - Trong quá trình hồi: Giá không phá cấu trúc xu hướng giảm chính
    
    Args:
        df_m1: DataFrame M1 với OHLC và RSI
        swing_low: Dict chứa thông tin swing low
        current_idx: Index hiện tại (default: -1)
        max_candles: Số nến hồi tối đa (default: 30)
    
    Returns:
        (is_valid, message)
    """
    if current_idx < 0:
        current_idx = len(df_m1) + current_idx
    
    swing_idx = swing_low['index']
    swing_price = swing_low['price']
    
    # Kiểm tra số nến hồi
    candles_since_swing = current_idx - swing_idx
    if candles_since_swing > max_candles:
        return False, f"Số nến hồi ({candles_since_swing}) > {max_candles} nến"
    
    # Kiểm tra giá không tạo đáy thấp hơn swing low
    for i in range(swing_idx + 1, current_idx + 1):
        if i >= len(df_m1):
            break
        if df_m1.iloc[i]['low'] < swing_price:
            return False, f"Giá đã tạo đáy thấp hơn swing low tại index {i}"
    
    # Kiểm tra RSI hồi về vùng 50-65
    current_rsi = df_m1.iloc[current_idx].get('rsi', None)
    if pd.notna(current_rsi):
        if not (50 <= current_rsi <= 65):
            return False, f"RSI ({current_rsi:.2f}) không trong vùng 50-65"
    else:
        return False, "RSI không có giá trị"
    
    return True, f"Pullback hợp lệ: {candles_since_swing} nến, RSI: {current_rsi:.2f}"


# ============================================================================
# DELTA CALCULATION
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
    
    Điều kiện: 0 < DeltaHigh < k × ATR(M1)
    
    Args:
        delta_high: Giá trị DeltaHigh
        atr_m1: ATR của M1
        threshold: Hệ số nhân ATR k (default: 0.3)
    
    Returns:
        (is_valid, message)
    """
    if delta_high is None or pd.isna(delta_high):
        return False, "DeltaHigh không có giá trị"
    
    if pd.isna(atr_m1) or atr_m1 is None or atr_m1 <= 0:
        return False, "ATR_M1 không hợp lệ"
    
    threshold_value = threshold * atr_m1
    
    if delta_high <= 0:
        return False, f"DeltaHigh ({delta_high:.5f}) ≤ 0 → RESET"
    
    if delta_high >= threshold_value:
        return False, f"DeltaHigh ({delta_high:.5f}) ≥ {threshold} × ATR ({threshold_value:.5f}) → RESET"
    
    return True, f"DeltaHigh ({delta_high:.5f}) hợp lệ (0 < {delta_high:.5f} < {threshold_value:.5f})"


def is_valid_delta_low(delta_low: float, atr_m1: float, threshold: float = 0.3) -> Tuple[bool, str]:
    """
    Kiểm tra DeltaLow hợp lệ
    
    Điều kiện: 0 < DeltaLow < k × ATR(M1)
    
    Args:
        delta_low: Giá trị DeltaLow
        atr_m1: ATR của M1
        threshold: Hệ số nhân ATR k (default: 0.3)
    
    Returns:
        (is_valid, message)
    """
    if delta_low is None or pd.isna(delta_low):
        return False, "DeltaLow không có giá trị"
    
    if pd.isna(atr_m1) or atr_m1 is None or atr_m1 <= 0:
        return False, "ATR_M1 không hợp lệ"
    
    threshold_value = threshold * atr_m1
    
    if delta_low <= 0:
        return False, f"DeltaLow ({delta_low:.5f}) ≤ 0 → RESET"
    
    if delta_low >= threshold_value:
        return False, f"DeltaLow ({delta_low:.5f}) ≥ {threshold} × ATR ({threshold_value:.5f}) → RESET"
    
    return True, f"DeltaLow ({delta_low:.5f}) hợp lệ (0 < {delta_low:.5f} < {threshold_value:.5f})"


# ============================================================================
# DIVERGENCE DETECTION
# ============================================================================

def check_bearish_divergence(df_m1: pd.DataFrame, lookback: int = 50, max_idx: int = None) -> Tuple[bool, str]:
    """
    Kiểm tra Bearish Divergence
    
    Bearish Divergence: Giá tạo Higher High (HH) nhưng RSI tạo Lower High (LH)
    
    Args:
        df_m1: DataFrame M1 với OHLC và RSI
        lookback: Số nến lookback (default: 50)
        max_idx: Index tối đa để kiểm tra (default: None = current)
    
    Returns:
        (has_divergence, message)
    """
    if len(df_m1) < lookback:
        return False, "Không đủ dữ liệu để kiểm tra divergence"
    
    if max_idx is None:
        max_idx = len(df_m1) - 1
    
    recent_df = df_m1.iloc[max(0, max_idx - lookback):max_idx + 1]
    recent_rsi = recent_df['rsi']
    
    # Tìm các đỉnh (peaks) trong giá và RSI
    peaks = []
    for i in range(2, len(recent_df) - 2):
        idx = recent_df.index[i]
        if (recent_df.iloc[i]['high'] > recent_df.iloc[i-1]['high'] and 
            recent_df.iloc[i]['high'] > recent_df.iloc[i+1]['high']):
            rsi_val = recent_rsi.iloc[i]
            if pd.notna(rsi_val):
                peaks.append({
                    'idx': idx,
                    'price': recent_df.iloc[i]['high'],
                    'rsi': rsi_val
                })
    
    # Cần ít nhất 2 đỉnh để so sánh
    if len(peaks) < 2:
        return False, "Không đủ đỉnh để kiểm tra divergence"
    
    # So sánh 2 đỉnh gần nhất
    last_peak = peaks[-1]
    prev_peak = peaks[-2]
    
    # Bearish Divergence: Giá tạo HH nhưng RSI tạo LH
    price_higher = last_peak['price'] > prev_peak['price']
    rsi_lower = last_peak['rsi'] < prev_peak['rsi']
    
    if price_higher and rsi_lower:
        return True, f"Bearish Divergence: Giá HH ({prev_peak['price']:.5f} → {last_peak['price']:.5f}), RSI LH ({prev_peak['rsi']:.1f} → {last_peak['rsi']:.1f})"
    
    return False, "Không có Bearish Divergence"


def check_bullish_divergence(df_m1: pd.DataFrame, lookback: int = 50, max_idx: int = None) -> Tuple[bool, str]:
    """
    Kiểm tra Bullish Divergence
    
    Bullish Divergence: Giá tạo Lower Low (LL) nhưng RSI tạo Higher Low (HL)
    
    Args:
        df_m1: DataFrame M1 với OHLC và RSI
        lookback: Số nến lookback (default: 50)
        max_idx: Index tối đa để kiểm tra (default: None = current)
    
    Returns:
        (has_divergence, message)
    """
    if len(df_m1) < lookback:
        return False, "Không đủ dữ liệu để kiểm tra divergence"
    
    if max_idx is None:
        max_idx = len(df_m1) - 1
    
    recent_df = df_m1.iloc[max(0, max_idx - lookback):max_idx + 1]
    recent_rsi = recent_df['rsi']
    
    # Tìm các đáy (troughs) trong giá và RSI
    troughs = []
    for i in range(2, len(recent_df) - 2):
        idx = recent_df.index[i]
        if (recent_df.iloc[i]['low'] < recent_df.iloc[i-1]['low'] and 
            recent_df.iloc[i]['low'] < recent_df.iloc[i+1]['low']):
            rsi_val = recent_rsi.iloc[i]
            if pd.notna(rsi_val):
                troughs.append({
                    'idx': idx,
                    'price': recent_df.iloc[i]['low'],
                    'rsi': rsi_val
                })
    
    # Cần ít nhất 2 đáy để so sánh
    if len(troughs) < 2:
        return False, "Không đủ đáy để kiểm tra divergence"
    
    # So sánh 2 đáy gần nhất
    last_trough = troughs[-1]
    prev_trough = troughs[-2]
    
    # Bullish Divergence: Giá tạo LL nhưng RSI tạo HL
    price_lower = last_trough['price'] < prev_trough['price']
    rsi_higher = last_trough['rsi'] > prev_trough['rsi']
    
    if price_lower and rsi_higher:
        return True, f"Bullish Divergence: Giá LL ({prev_trough['price']:.5f} → {last_trough['price']:.5f}), RSI HL ({prev_trough['rsi']:.1f} → {last_trough['rsi']:.1f})"
    
    return False, "Không có Bullish Divergence"


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
# SL/TP CALCULATION
# ============================================================================

def calculate_sl_tp_newtrendline(
    entry_price: float,
    signal_type: str,
    atr_m1: float,
    symbol_info: Optional[mt5.SymbolInfo] = None,
    point_adjustment: float = 6.0
) -> Tuple[float, float, Dict]:
    """
    Tính SL và TP cho lệnh (bot newtrendline)
    
    Công thức:
    - SL = 2 × ATR + 6 point
    - TP = 2 × SL
    
    Args:
        entry_price: Giá entry
        signal_type: "BUY" hoặc "SELL"
        atr_m1: ATR của M1
        symbol_info: MT5 symbol info để normalize digits và lấy point
        point_adjustment: Điều chỉnh point (default: 6.0)
    
    Returns:
        (sl, tp, info_dict)
    """
    if symbol_info is not None:
        point = symbol_info.point
        digits = symbol_info.digits
    else:
        point = 0.0001  # Default for forex
        digits = 5
    
    sl_distance = (2.0 * atr_m1) + (point_adjustment * point)
    tp_distance = 2.0 * sl_distance  # TP = 2 × SL
    
    if signal_type.upper() == "BUY":
        sl = entry_price - sl_distance
        tp = entry_price + tp_distance
    else:  # SELL
        sl = entry_price + sl_distance
        tp = entry_price - tp_distance
    
    # Normalize to symbol digits
    sl = round(sl, digits)
    tp = round(tp, digits)
    entry_price = round(entry_price, digits)
    
    info = {
        'sl_distance': sl_distance,
        'tp_distance': tp_distance,
        'atr_multiplier': 2.0,
        'point_adjustment': point_adjustment,
        'r_ratio': 1.0  # 1R = SL distance
    }
    
    return sl, tp, info


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_delta_threshold_multiplier(symbol: str, config: Optional[Dict] = None) -> float:
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
    
    # Default: Use EURUSD threshold
    return 0.00011
