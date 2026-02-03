import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# Import local modules
sys.path.append('..') 
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message, calculate_rsi, log_to_file, calculate_adx, log_debug_indicators

# Initialize Database
db = Database()

def calculate_ema(series, span):
    """Calculate EMA"""
    return series.ewm(span=span, adjust=False).mean()

def calculate_atr(df, period=14):
    """Calculate ATR"""
    df = df.copy()
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift(1))
    df['tr2'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=period).mean()
    return df['atr']

def get_min_atr_threshold(symbol, config=None):
    """
    Get minimum ATR threshold based on symbol type
    Returns appropriate ATR threshold for different symbols
    
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
    if 'EURUSD' in symbol_upper or 'GBPUSD' in symbol_upper or 'USDJPY' in symbol_upper:
        return 0.00011
    
    # XAUUSD (Gold): Typically ATR is 0.1-2.0 USD, threshold ~0.1 (equivalent to ~1 pip for gold)
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        return 0.1
    
    # BTCUSD: Typically ATR is 50-500 USD, threshold ~50 (equivalent to ~0.5% of typical BTC price ~10000)
    if 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
        return 50.0
    
    # ETHUSD: Similar to BTC but smaller scale
    if 'ETHUSD' in symbol_upper or 'ETH' in symbol_upper:
        return 5.0
    
    # Default: Use EURUSD threshold
    return 0.00011

def get_pip_value_per_lot(symbol, symbol_info=None):
    """
    Get pip value per lot for a symbol - lấy từ MT5 nếu có (chính xác hơn)
    EURUSD: 1 pip = $10 per lot (standard)
    XAUUSD: 1 pip = $1 per lot (standard, but may vary by broker)
    """
    if symbol_info is None:
        symbol_info = mt5.symbol_info(symbol)
    
    if symbol_info:
        # Lấy từ MT5 symbol_info (chính xác nhất)
        tick_value = getattr(symbol_info, 'trade_tick_value', None)
        tick_size = getattr(symbol_info, 'trade_tick_size', None)
        point = getattr(symbol_info, 'point', 0.0001)
        contract_size = getattr(symbol_info, 'trade_contract_size', 100000)
        
        # Tính pip size
        symbol_upper = symbol.upper()
        if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
            pip_size = 0.1 if point < 0.01 else point
        elif 'JPY' in symbol_upper:
            pip_size = 0.01
        else:
            pip_size = 0.0001
        
        # Tính pip value từ tick_value và tick_size
        if tick_value is not None and tick_size is not None and tick_size > 0:
            pip_value = tick_value * (pip_size / tick_size)
            if pip_value > 0:
                return pip_value
        
        # Fallback: tính từ contract_size
        if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
            if contract_size == 100:
                return 1.0
            else:
                return contract_size / 100
        elif 'EURUSD' in symbol_upper or 'GBPUSD' in symbol_upper:
            return 10.0
        else:
            return 10.0
    
    # Default fallback nếu không lấy được từ MT5
    symbol_upper = symbol.upper()
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        return 1.0
    else:
        return 10.0

def calculate_lot_size(account_balance, risk_percent, sl_pips, symbol, symbol_info=None):
    """
    Calculate lot size based on risk management formula:
    Lot size = RiskMoney / (SL pips × Pip Value per Lot)
    
    Args:
        account_balance: Account balance in USD
        risk_percent: Risk percentage (e.g., 1.0 for 1%)
        sl_pips: Stop Loss in pips
        symbol: Trading symbol (EURUSD, XAUUSD, etc.)
        symbol_info: MT5 symbol info (optional)
    
    Returns:
        lot_size: Calculated lot size
    """
    # Calculate risk money
    risk_money = account_balance * (risk_percent / 100.0)
    
    # Get pip value per lot (từ MT5 nếu có)
    pip_value_per_lot = get_pip_value_per_lot(symbol, symbol_info)
    
    # Calculate lot size
    if sl_pips > 0 and pip_value_per_lot > 0:
        lot_size = risk_money / (sl_pips * pip_value_per_lot)
    else:
        lot_size = 0.01  # Default minimum
    
    # Round to 2 decimal places (standard lot step is 0.01)
    lot_size = round(lot_size, 2)
    
    # Ensure minimum lot size
    if lot_size < 0.01:
        lot_size = 0.01
    
    return lot_size

def is_bullish_engulfing(prev_candle, curr_candle):
    """
    Bullish Engulfing Pattern:
    - Previous candle is bearish (close < open)
    - Current candle is bullish (close > open)
    - Current open < previous close
    - Current close > previous open
    """
    prev_bearish = prev_candle['close'] < prev_candle['open']
    curr_bullish = curr_candle['close'] > curr_candle['open']
    engulfs = (curr_candle['open'] < prev_candle['close']) and (curr_candle['close'] > prev_candle['open'])
    return prev_bearish and curr_bullish and engulfs

def is_bearish_engulfing(prev_candle, curr_candle):
    """
    Bearish Engulfing Pattern:
    - Previous candle is bullish (close > open)
    - Current candle is bearish (close < open)
    - Current open > previous close
    - Current close < previous open
    """
    prev_bullish = prev_candle['close'] > prev_candle['open']
    curr_bearish = curr_candle['close'] < curr_candle['open']
    engulfs = (curr_candle['open'] > prev_candle['close']) and (curr_candle['close'] < prev_candle['open'])
    return prev_bullish and curr_bearish and engulfs

def check_rsi_reversal_up(rsi_series, lookback=10):
    """
    Check if RSI is turning up (quay đầu lên)
    RSI current > RSI previous
    """
    if len(rsi_series) < 2:
        return False
    current_rsi = rsi_series.iloc[-1]
    prev_rsi = rsi_series.iloc[-2]
    return current_rsi > prev_rsi

def check_rsi_reversal_down(rsi_series, lookback=10):
    """
    Check if RSI is turning down (quay đầu xuống)
    RSI current < RSI previous
    """
    if len(rsi_series) < 2:
        return False
    current_rsi = rsi_series.iloc[-1]
    prev_rsi = rsi_series.iloc[-2]
    return current_rsi < prev_rsi

def find_swing_high_with_rsi(df_m1, lookback=5, min_rsi=70):
    """
    Tìm swing high với RSI > min_rsi (default 70)
    Returns: list of dicts với {'index': i, 'price': high, 'time': time, 'rsi': rsi_value}
    """
    swing_highs = []
    
    for i in range(lookback, len(df_m1) - lookback):
        # Check if it's a swing high
        is_swing_high = True
        for j in range(i - lookback, i + lookback + 1):
            if j != i and df_m1.iloc[j]['high'] >= df_m1.iloc[i]['high']:
                is_swing_high = False
                break
        
        if is_swing_high:
            # Check RSI at swing high
            rsi_val = df_m1.iloc[i].get('rsi', None)
            if pd.notna(rsi_val) and rsi_val > min_rsi:
                swing_highs.append({
                    'index': i,
                    'price': df_m1.iloc[i]['high'],
                    'time': df_m1.index[i] if hasattr(df_m1.index[i], '__iter__') else i,
                    'rsi': rsi_val
                })
    
    return swing_highs

def find_swing_low_with_rsi(df_m1, lookback=5, min_rsi=30):
    """
    Tìm swing low với RSI < min_rsi (default 30)
    Returns: list of dicts với {'index': i, 'price': low, 'time': time, 'rsi': rsi_value}
    """
    swing_lows = []
    
    for i in range(lookback, len(df_m1) - lookback):
        # Check if it's a swing low
        is_swing_low = True
        for j in range(i - lookback, i + lookback + 1):
            if j != i and df_m1.iloc[j]['low'] <= df_m1.iloc[i]['low']:
                is_swing_low = False
                break
        
        if is_swing_low:
            # Check RSI at swing low
            rsi_val = df_m1.iloc[i].get('rsi', None)
            if pd.notna(rsi_val) and rsi_val < min_rsi:
                swing_lows.append({
                    'index': i,
                    'price': df_m1.iloc[i]['low'],
                    'time': df_m1.index[i] if hasattr(df_m1.index[i], '__iter__') else i,
                    'rsi': rsi_val
                })
    
    return swing_lows

def check_swing_high_upperwick(df_m1, swing_high_idx):
    """
    Kiểm tra UpperWick ≥ 1.3 ATR tại vùng swing high (±2 nến quanh swing high = 5 nến tổng)
    Nếu UpperWick ≥ 1.3 ATR → bỏ cả con sóng hồi
    
    Returns: (is_valid, message)
    """
    if swing_high_idx < 2 or swing_high_idx >= len(df_m1) - 2:
        return False, "Swing high quá gần đầu/cuối, không đủ nến để kiểm tra"
    
    # Lấy 5 nến: ±2 nến quanh swing high
    start_idx = max(0, swing_high_idx - 2)
    end_idx = min(len(df_m1), swing_high_idx + 3)  # +3 vì iloc là exclusive
    swing_zone = df_m1.iloc[start_idx:end_idx]
    
    # Lấy ATR từ swing high
    atr_val = df_m1.iloc[swing_high_idx].get('atr', None)
    if pd.isna(atr_val) or atr_val is None:
        # Tính ATR nếu không có
        atr_series = calculate_atr(df_m1.iloc[max(0, swing_high_idx - 14):swing_high_idx + 1], period=14)
        if len(atr_series) > 0:
            atr_val = atr_series.iloc[-1]
    
    if atr_val is None or pd.isna(atr_val) or atr_val <= 0:
        return False, "Không thể lấy ATR để kiểm tra UpperWick"
    
    threshold = 1.3 * atr_val
    
    # Kiểm tra UpperWick của từng nến trong vùng swing high
    for idx, candle in swing_zone.iterrows():
        upperwick = candle['high'] - max(candle['open'], candle['close'])
        if upperwick >= threshold:
            return False, f"UpperWick ({upperwick:.5f}) ≥ 1.3 ATR ({threshold:.5f}) tại index {idx} trong vùng swing high"
    
    return True, "UpperWick hợp lệ (< 1.3 ATR)"

def find_first_pullback_candle_buy(df_m1, swing_high_idx):
    """
    Tìm nến bắt đầu sóng hồi giảm (nến đầu tiên đi ngược lại xu hướng tăng chính)
    Điều kiện: Close ≤ Low của nến liền trước
    Nến này chỉ hợp lệ khi xuất hiện sau giai đoạn giá đã ngừng tạo Higher high, hoặc trải qua pha sideway/nén biên độ
    
    Returns: (pb1_idx, message) hoặc (None, message) nếu không tìm thấy
    """
    if swing_high_idx >= len(df_m1) - 1:
        return None, "Swing high quá gần cuối"
    
    # Tìm nến đầu tiên thỏa điều kiện Close ≤ Low của nến liền trước
    for i in range(swing_high_idx + 1, len(df_m1)):
        if i == 0:
            continue
        
        prev_candle = df_m1.iloc[i - 1]
        curr_candle = df_m1.iloc[i]
        
        # Điều kiện: Close ≤ Low của nến liền trước
        if curr_candle['close'] <= prev_candle['low']:
            # Kiểm tra xem có phải sau giai đoạn ngừng tạo Higher high hoặc sideway không
            # (Có thể kiểm tra thêm logic này nếu cần)
            return i, f"Nến hồi giảm đầu tiên tại index {i}"
    
    return None, "Không tìm thấy nến hồi giảm đầu tiên"

def calculate_slope_pullback_down(df_m1, swing_high_idx, pb1_idx):
    """
    Tính Slope_Pullback_Down theo công thức:
    Slope_Pullback_Down = (max(High_Pre[3] ∪ High_PB[1]) - min(Low_PB[1..6])) / Σ(ATR_14,i) với i từ 1 đến 6
    
    Trong đó:
    - PB[1..6] là 6 nến hồi giảm đầu tiên tính từ nến đầu tiên đi ngược lại xu hướng tăng chính
    - Pre[3] là 3 nến ngay trước nến hồi giảm đầu tiên
    - PB[1] là nến hồi giảm đầu tiên
    - ATR_14,i là giá trị ATR(14) của từng nến trong tập 6 nến hồi giảm đầu tiên
    
    Returns: (slope_value, message) hoặc (None, message) nếu không đủ dữ liệu
    """
    if pb1_idx is None or pb1_idx >= len(df_m1):
        return None, "Không có nến hồi giảm đầu tiên"
    
    # Kiểm tra có đủ 6 nến hồi giảm không
    if pb1_idx + 5 >= len(df_m1):
        return None, f"Không đủ 6 nến hồi giảm (chỉ có {len(df_m1) - pb1_idx} nến từ index {pb1_idx})"
    
    # Lấy Pre[3]: 3 nến ngay trước PB[1]
    if pb1_idx < 3:
        return None, f"Không đủ 3 nến trước PB[1] (chỉ có {pb1_idx} nến)"
    
    pre_3_start = pb1_idx - 3
    pre_3_end = pb1_idx
    pre_3_candles = df_m1.iloc[pre_3_start:pre_3_end]
    
    # Lấy PB[1..6]: 6 nến hồi giảm đầu tiên
    pb_1_to_6 = df_m1.iloc[pb1_idx:pb1_idx + 6]
    
    # Tính max(High_Pre[3] ∪ High_PB[1])
    high_pre_3 = pre_3_candles['high'].max()
    high_pb_1 = pb_1_to_6.iloc[0]['high']
    max_high = max(high_pre_3, high_pb_1)
    
    # Tính min(Low_PB[1..6])
    min_low = pb_1_to_6['low'].min()
    
    # Tính Σ(ATR_14,i) với i từ 1 đến 6
    atr_sum = 0
    for i in range(6):
        idx = pb1_idx + i
        atr_val = df_m1.iloc[idx].get('atr', None)
        if pd.isna(atr_val) or atr_val is None:
            # Tính ATR nếu không có
            atr_series = calculate_atr(df_m1.iloc[max(0, idx - 14):idx + 1], period=14)
            if len(atr_series) > 0:
                atr_val = atr_series.iloc[-1]
        
        if atr_val is None or pd.isna(atr_val) or atr_val <= 0:
            return None, f"Không thể lấy ATR tại index {idx}"
        
        atr_sum += atr_val
    
    if atr_sum <= 0:
        return None, "Tổng ATR không hợp lệ"
    
    # Tính Slope_Pullback_Down
    numerator = max_high - min_low
    slope = numerator / atr_sum
    
    return slope, f"Slope_Pullback_Down = {slope:.2f} (max_high={max_high:.5f}, min_low={min_low:.5f}, atr_sum={atr_sum:.5f})"

def check_swing_low_lowerwick(df_m1, swing_low_idx):
    """
    Kiểm tra LowerWick ≥ 1.3 ATR tại vùng swing low (±2 nến quanh swing low = 5 nến tổng)
    Nếu LowerWick ≥ 1.3 ATR → bỏ cả con sóng hồi
    
    Returns: (is_valid, message)
    """
    if swing_low_idx < 2 or swing_low_idx >= len(df_m1) - 2:
        return False, "Swing low quá gần đầu/cuối, không đủ nến để kiểm tra"
    
    # Lấy 5 nến: ±2 nến quanh swing low
    start_idx = max(0, swing_low_idx - 2)
    end_idx = min(len(df_m1), swing_low_idx + 3)  # +3 vì iloc là exclusive
    swing_zone = df_m1.iloc[start_idx:end_idx]
    
    # Lấy ATR từ swing low
    atr_val = df_m1.iloc[swing_low_idx].get('atr', None)
    if pd.isna(atr_val) or atr_val is None:
        # Tính ATR nếu không có
        atr_series = calculate_atr(df_m1.iloc[max(0, swing_low_idx - 14):swing_low_idx + 1], period=14)
        if len(atr_series) > 0:
            atr_val = atr_series.iloc[-1]
    
    if atr_val is None or pd.isna(atr_val) or atr_val <= 0:
        return False, "Không thể lấy ATR để kiểm tra LowerWick"
    
    threshold = 1.3 * atr_val
    
    # Kiểm tra LowerWick của từng nến trong vùng swing low
    for idx, candle in swing_zone.iterrows():
        lowerwick = min(candle['open'], candle['close']) - candle['low']
        if lowerwick >= threshold:
            return False, f"LowerWick ({lowerwick:.5f}) ≥ 1.3 ATR ({threshold:.5f}) tại index {idx} trong vùng swing low"
    
    return True, "LowerWick hợp lệ (< 1.3 ATR)"

def find_first_pullback_candle_sell(df_m1, swing_low_idx):
    """
    Tìm nến bắt đầu sóng hồi tăng (nến đầu tiên đi ngược lại xu hướng giảm chính)
    Điều kiện: Close ≥ High của nến liền trước
    Nến này chỉ hợp lệ khi xuất hiện sau giai đoạn giá đã ngừng tạo Lower Low, hoặc trải qua pha sideway/nén biên độ
    
    Returns: (pb1_idx, message) hoặc (None, message) nếu không tìm thấy
    """
    if swing_low_idx >= len(df_m1) - 1:
        return None, "Swing low quá gần cuối"
    
    # Tìm nến đầu tiên thỏa điều kiện Close ≥ High của nến liền trước
    for i in range(swing_low_idx + 1, len(df_m1)):
        if i == 0:
            continue
        
        prev_candle = df_m1.iloc[i - 1]
        curr_candle = df_m1.iloc[i]
        
        # Điều kiện: Close ≥ High của nến liền trước
        if curr_candle['close'] >= prev_candle['high']:
            # Kiểm tra xem có phải sau giai đoạn ngừng tạo Lower Low hoặc sideway không
            # (Có thể kiểm tra thêm logic này nếu cần)
            return i, f"Nến hồi tăng đầu tiên tại index {i}"
    
    return None, "Không tìm thấy nến hồi tăng đầu tiên"

def calculate_slope_pullback_up(df_m1, swing_low_idx, pb1_idx):
    """
    Tính Slope_Pullback_Up theo công thức:
    Slope_Pullback_Up = (max(High_PB[1..6]) - min(Low_Pre[3] ∪ Low_PB[1])) / Σ(ATR_14,i) với i từ 1 đến 6
    
    Trong đó:
    - PB[1..6] là 6 nến hồi tăng đầu tiên tính từ nến đầu tiên đi ngược lại xu hướng giảm chính
    - Pre[3] là 3 nến ngay trước nến hồi tăng đầu tiên
    - PB[1] là nến hồi tăng đầu tiên
    - ATR_14,i là giá trị ATR(14) của từng nến trong tập 6 nến hồi tăng đầu tiên
    
    Returns: (slope_value, message) hoặc (None, message) nếu không đủ dữ liệu
    """
    if pb1_idx is None or pb1_idx >= len(df_m1):
        return None, "Không có nến hồi tăng đầu tiên"
    
    # Kiểm tra có đủ 6 nến hồi tăng không
    if pb1_idx + 5 >= len(df_m1):
        return None, f"Không đủ 6 nến hồi tăng (chỉ có {len(df_m1) - pb1_idx} nến từ index {pb1_idx})"
    
    # Lấy Pre[3]: 3 nến ngay trước PB[1]
    if pb1_idx < 3:
        return None, f"Không đủ 3 nến trước PB[1] (chỉ có {pb1_idx} nến)"
    
    pre_3_start = pb1_idx - 3
    pre_3_end = pb1_idx
    pre_3_candles = df_m1.iloc[pre_3_start:pre_3_end]
    
    # Lấy PB[1..6]: 6 nến hồi tăng đầu tiên
    pb_1_to_6 = df_m1.iloc[pb1_idx:pb1_idx + 6]
    
    # Tính max(High_PB[1..6])
    max_high = pb_1_to_6['high'].max()
    
    # Tính min(Low_Pre[3] ∪ Low_PB[1])
    low_pre_3 = pre_3_candles['low'].min()
    low_pb_1 = pb_1_to_6.iloc[0]['low']
    min_low = min(low_pre_3, low_pb_1)
    
    # Tính Σ(ATR_14,i) với i từ 1 đến 6
    atr_sum = 0
    for i in range(6):
        idx = pb1_idx + i
        atr_val = df_m1.iloc[idx].get('atr', None)
        if pd.isna(atr_val) or atr_val is None:
            # Tính ATR nếu không có
            atr_series = calculate_atr(df_m1.iloc[max(0, idx - 14):idx + 1], period=14)
            if len(atr_series) > 0:
                atr_val = atr_series.iloc[-1]
        
        if atr_val is None or pd.isna(atr_val) or atr_val <= 0:
            return None, f"Không thể lấy ATR tại index {idx}"
        
        atr_sum += atr_val
    
    if atr_sum <= 0:
        return None, "Tổng ATR không hợp lệ"
    
    # Tính Slope_Pullback_Up
    numerator = max_high - min_low
    slope = numerator / atr_sum
    
    return slope, f"Slope_Pullback_Up = {slope:.2f} (max_high={max_high:.5f}, min_low={min_low:.5f}, atr_sum={atr_sum:.5f})"

def check_pullback_upperwick(df_m1, swing_high_idx, pullback_end_idx):
    """
    Kiểm tra UpperWick trong toàn bộ sóng hồi (từ swing high đến trước nến phá trendline)
    Điều kiện 4: Trong toàn bộ sóng hồi không tồn tại bất kỳ nến nào có UpperWick ≥ 1.3 ATR
    
    Args:
        swing_high_idx: Index của swing high
        pullback_end_idx: Index của nến cuối cùng trong sóng hồi (trước nến phá trendline)
    
    Returns: (is_valid, message)
    """
    if swing_high_idx >= pullback_end_idx or swing_high_idx >= len(df_m1) - 1:
        return False, "Swing high index không hợp lệ"
    
    # Lấy toàn bộ sóng hồi (từ swing high + 1 đến pullback_end_idx, không bao gồm nến phá trendline)
    pullback_start = swing_high_idx + 1
    pullback_end = min(pullback_end_idx + 1, len(df_m1))  # +1 vì iloc là exclusive
    
    if pullback_start >= pullback_end:
        return False, "Không có nến trong sóng hồi để kiểm tra"
    
    pullback_candles = df_m1.iloc[pullback_start:pullback_end]
    
    if len(pullback_candles) == 0:
        return False, "Không có nến trong sóng hồi"
    
    # Kiểm tra từng nến trong sóng hồi
    for idx, candle in pullback_candles.iterrows():
        # Lấy ATR của nến hiện tại
        atr_val = candle.get('atr', None)
        if pd.isna(atr_val) or atr_val is None:
            # Tính ATR nếu không có
            candle_idx = pullback_candles.index.get_loc(idx)
            actual_idx = pullback_start + candle_idx
            atr_series = calculate_atr(df_m1.iloc[max(0, actual_idx - 14):actual_idx + 1], period=14)
            if len(atr_series) > 0:
                atr_val = atr_series.iloc[-1]
        
        if atr_val is None or pd.isna(atr_val) or atr_val <= 0:
            continue  # Bỏ qua nến không có ATR
        
        # Tính UpperWick
        upperwick = candle['high'] - max(candle['open'], candle['close'])
        threshold = 1.3 * atr_val
        
        # Kiểm tra UpperWick ≥ 1.3 ATR
        if upperwick >= threshold:
            return False, f"UpperWick ({upperwick:.5f}) ≥ 1.3 ATR ({threshold:.5f}) tại index {idx} trong sóng hồi"
    
    return True, "Không có nến nào trong sóng hồi có UpperWick ≥ 1.3 ATR"

def check_pullback_lowerwick(df_m1, swing_low_idx, pullback_end_idx):
    """
    Kiểm tra LowerWick trong toàn bộ sóng hồi (từ swing low đến trước nến phá trendline)
    Điều kiện 4: Trong toàn bộ sóng hồi không tồn tại bất kỳ nến nào có LowerWick ≥ 1.3 ATR
    
    Args:
        swing_low_idx: Index của swing low
        pullback_end_idx: Index của nến cuối cùng trong sóng hồi (trước nến phá trendline)
    
    Returns: (is_valid, message)
    """
    if swing_low_idx >= pullback_end_idx or swing_low_idx >= len(df_m1) - 1:
        return False, "Swing low index không hợp lệ"
    
    # Lấy toàn bộ sóng hồi (từ swing low + 1 đến pullback_end_idx, không bao gồm nến phá trendline)
    pullback_start = swing_low_idx + 1
    pullback_end = min(pullback_end_idx + 1, len(df_m1))  # +1 vì iloc là exclusive
    
    if pullback_start >= pullback_end:
        return False, "Không có nến trong sóng hồi để kiểm tra"
    
    pullback_candles = df_m1.iloc[pullback_start:pullback_end]
    
    if len(pullback_candles) == 0:
        return False, "Không có nến trong sóng hồi"
    
    # Kiểm tra từng nến trong sóng hồi
    for idx, candle in pullback_candles.iterrows():
        # Lấy ATR của nến hiện tại
        atr_val = candle.get('atr', None)
        if pd.isna(atr_val) or atr_val is None:
            # Tính ATR nếu không có
            candle_idx = pullback_candles.index.get_loc(idx)
            actual_idx = pullback_start + candle_idx
            atr_series = calculate_atr(df_m1.iloc[max(0, actual_idx - 14):actual_idx + 1], period=14)
            if len(atr_series) > 0:
                atr_val = atr_series.iloc[-1]
        
        if atr_val is None or pd.isna(atr_val) or atr_val <= 0:
            continue  # Bỏ qua nến không có ATR
        
        # Tính LowerWick
        lowerwick = min(candle['open'], candle['close']) - candle['low']
        threshold = 1.3 * atr_val
        
        # Kiểm tra LowerWick ≥ 1.3 ATR
        if lowerwick >= threshold:
            return False, f"LowerWick ({lowerwick:.5f}) ≥ 1.3 ATR ({threshold:.5f}) tại index {idx} trong sóng hồi"
    
    return True, "Không có nến nào trong sóng hồi có LowerWick ≥ 1.3 ATR"

def check_valid_pullback_buy(df_m1, swing_high_idx, max_candles=30, rsi_target_min=40, rsi_target_max=50, rsi_min_during_pullback=32):
    """
    Kiểm tra sóng hồi hợp lệ cho BUY (Điều kiện 3 mới):
    
    A. Swing high hợp lệ:
    - Kiểm tra UpperWick ≥ 1.3 ATR tại vùng swing high (±2 nến = 5 nến tổng)
    - Nếu UpperWick ≥ 1.3 ATR → bỏ cả con sóng hồi
    
    B. Slope Pullback giảm:
    - 18 ≤ Slope_Pullback_Down ≤ 48 → Pullback hợp lệ, tiếp tục điều kiện 4
    - 48 < Slope_Pullback_Down ≤ 62 → Pullback hơi dốc, không entry ngay, cần cấu trúc hồi rõ ràng
    - Slope_Pullback_Down > 62 → Pullback quá mạnh, loại bỏ toàn bộ sóng hồi
    
    Returns: (is_valid, pullback_end_idx, pullback_candles, slope_category, message)
    slope_category: 'valid' (18-48), 'steep' (48-62), 'too_steep' (>62), None nếu không hợp lệ
    """
    if swing_high_idx >= len(df_m1) - 1:
        return False, None, None, None, "Swing high quá gần cuối"
    
    # A. Kiểm tra Swing high hợp lệ: UpperWick < 1.3 ATR tại vùng swing high (±2 nến)
    upperwick_ok, upperwick_msg = check_swing_high_upperwick(df_m1, swing_high_idx)
    if not upperwick_ok:
        return False, None, None, None, f"ĐK3A: {upperwick_msg}"
    
    # B. Tìm nến bắt đầu sóng hồi giảm (PB[1])
    pb1_idx, pb1_msg = find_first_pullback_candle_buy(df_m1, swing_high_idx)
    if pb1_idx is None:
        return False, None, None, None, f"ĐK3B: {pb1_msg}"
    
    # C. Tính Slope_Pullback_Down
    slope_value, slope_msg = calculate_slope_pullback_down(df_m1, swing_high_idx, pb1_idx)
    if slope_value is None:
        return False, None, None, None, f"ĐK3C: {slope_msg}"
    
    # D. Phân loại slope và xử lý
    slope_category = None
    if 18 <= slope_value <= 48:
        # Pullback hợp lệ → Tiếp tục kiểm tra điều kiện 4
        slope_category = 'valid'
        # Lấy pullback candles từ PB[1] đến ít nhất 6 nến (hoặc đến khi có đủ dữ liệu)
        pullback_end_idx = min(pb1_idx + 5, len(df_m1) - 1)
        pullback_candles = df_m1.iloc[pb1_idx:pullback_end_idx + 1]
        return True, pullback_end_idx, pullback_candles, slope_category, f"ĐK3: Pullback hợp lệ (Slope={slope_value:.2f}, 18-48)"
    
    elif 48 < slope_value <= 62:
        # Pullback hơi dốc → KHÔNG ENTRY NGAY
        # Cần cấu trúc hồi rõ ràng (đáy - đỉnh) và vẽ lại trendline
        slope_category = 'steep'
        # Vẫn trả về True nhưng với category 'steep' để xử lý đặc biệt
        pullback_end_idx = min(pb1_idx + 5, len(df_m1) - 1)
        pullback_candles = df_m1.iloc[pb1_idx:pullback_end_idx + 1]
        return True, pullback_end_idx, pullback_candles, slope_category, f"ĐK3: Pullback hơi dốc (Slope={slope_value:.2f}, 48-62) - Cần cấu trúc hồi rõ ràng"
    
    else:  # slope_value > 62
        # Pullback quá mạnh → Loại bỏ toàn bộ sóng hồi
        slope_category = 'too_steep'
        return False, None, None, slope_category, f"ĐK3: Pullback quá mạnh (Slope={slope_value:.2f} > 62) - Loại bỏ sóng hồi"

def check_valid_pullback_sell(df_m1, swing_low_idx, max_candles=30, rsi_target_min=50, rsi_target_max=60, rsi_max_during_pullback=68):
    """
    Kiểm tra sóng hồi hợp lệ cho SELL (Điều kiện 3 mới):
    
    A. Swing low hợp lệ:
    - Kiểm tra LowerWick ≥ 1.3 ATR tại vùng swing low (±2 nến = 5 nến tổng)
    - Nếu LowerWick ≥ 1.3 ATR → bỏ cả con sóng hồi
    
    B. Slope Pullback tăng:
    - 18 ≤ Slope_Pullback_Up ≤ 48 → Pullback hợp lệ, tiếp tục điều kiện 4
    - 48 < Slope_Pullback_Up ≤ 62 → Pullback hơi dốc, không entry ngay, cần cấu trúc hồi rõ ràng
    - Slope_Pullback_Up > 62 → Pullback quá mạnh, loại bỏ toàn bộ sóng hồi
    
    Returns: (is_valid, pullback_end_idx, pullback_candles, slope_category, message)
    slope_category: 'valid' (18-48), 'steep' (48-62), 'too_steep' (>62), None nếu không hợp lệ
    """
    if swing_low_idx >= len(df_m1) - 1:
        return False, None, None, None, "Swing low quá gần cuối"
    
    # A. Kiểm tra Swing low hợp lệ: LowerWick < 1.3 ATR tại vùng swing low (±2 nến)
    lowerwick_ok, lowerwick_msg = check_swing_low_lowerwick(df_m1, swing_low_idx)
    if not lowerwick_ok:
        return False, None, None, None, f"ĐK3A: {lowerwick_msg}"
    
    # B. Tìm nến bắt đầu sóng hồi tăng (PB[1])
    pb1_idx, pb1_msg = find_first_pullback_candle_sell(df_m1, swing_low_idx)
    if pb1_idx is None:
        return False, None, None, None, f"ĐK3B: {pb1_msg}"
    
    # C. Tính Slope_Pullback_Up
    slope_value, slope_msg = calculate_slope_pullback_up(df_m1, swing_low_idx, pb1_idx)
    if slope_value is None:
        return False, None, None, None, f"ĐK3C: {slope_msg}"
    
    # D. Phân loại slope và xử lý
    slope_category = None
    if 18 <= slope_value <= 48:
        # Pullback hợp lệ → Tiếp tục kiểm tra điều kiện 4
        slope_category = 'valid'
        # Lấy pullback candles từ PB[1] đến ít nhất 6 nến (hoặc đến khi có đủ dữ liệu)
        pullback_end_idx = min(pb1_idx + 5, len(df_m1) - 1)
        pullback_candles = df_m1.iloc[pb1_idx:pullback_end_idx + 1]
        return True, pullback_end_idx, pullback_candles, slope_category, f"ĐK3: Pullback hợp lệ (Slope={slope_value:.2f}, 18-48)"
    
    elif 48 < slope_value <= 62:
        # Pullback hơi dốc → KHÔNG ENTRY NGAY
        # Cần cấu trúc hồi rõ ràng (đỉnh - đáy) và vẽ lại trendline
        slope_category = 'steep'
        # Vẫn trả về True nhưng với category 'steep' để xử lý đặc biệt
        pullback_end_idx = min(pb1_idx + 5, len(df_m1) - 1)
        pullback_candles = df_m1.iloc[pb1_idx:pullback_end_idx + 1]
        return True, pullback_end_idx, pullback_candles, slope_category, f"ĐK3: Pullback hơi dốc (Slope={slope_value:.2f}, 48-62) - Cần cấu trúc hồi rõ ràng"
    
    else:  # slope_value > 62
        # Pullback quá mạnh → Loại bỏ toàn bộ sóng hồi
        slope_category = 'too_steep'
        return False, None, None, slope_category, f"ĐK3: Pullback quá mạnh (Slope={slope_value:.2f} > 62) - Loại bỏ sóng hồi"

def calculate_pullback_trendline_buy(df_m1, swing_high_idx, pullback_end_idx):
    """
    Vẽ trendline sóng hồi (giảm) nối từ swing high qua các đỉnh thấp dần
    
    Returns: dict với {'slope', 'intercept', 'func', 'points'} hoặc None
    """
    if swing_high_idx >= pullback_end_idx or pullback_end_idx >= len(df_m1):
        return None
    
    pullback_candles = df_m1.iloc[swing_high_idx:pullback_end_idx + 1]
    
    # Tìm các đỉnh (local maxima) trong pullback
    highs = pullback_candles['high'].values
    
    local_maxs = []
    for i in range(1, len(highs) - 1):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            idx_in_df = pullback_candles.index[i]
            pos_in_df = df_m1.index.get_loc(idx_in_df) if hasattr(df_m1.index, 'get_loc') else i + swing_high_idx
            local_maxs.append({'pos': pos_in_df, 'price': highs[i], 'idx': idx_in_df})
    
    # Thêm swing high vào đầu
    swing_high_pos = swing_high_idx
    swing_high_price = df_m1.iloc[swing_high_idx]['high']
    local_maxs.insert(0, {'pos': swing_high_pos, 'price': swing_high_price, 'idx': df_m1.index[swing_high_idx] if hasattr(df_m1.index[swing_high_idx], '__iter__') else swing_high_idx})
    
    local_maxs = sorted(local_maxs, key=lambda x: x['pos'])
    
    # Lọc các đỉnh thấp dần
    filtered_maxs = [local_maxs[0]]
    for i in range(1, len(local_maxs)):
        if local_maxs[i]['price'] <= filtered_maxs[-1]['price']:
            filtered_maxs.append(local_maxs[i])
    
    if len(filtered_maxs) < 2:
        return None
    
    # Linear regression
    x_values = np.array([m['pos'] for m in filtered_maxs])
    y_values = np.array([m['price'] for m in filtered_maxs])
    
    n = len(x_values)
    sum_x = x_values.sum()
    sum_y = y_values.sum()
    sum_xy = (x_values * y_values).sum()
    sum_x2 = (x_values * x_values).sum()
    
    denominator = n * sum_x2 - sum_x * sum_x
    if abs(denominator) < 1e-10:
        return None
    
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    
    def trendline_func(pos):
        return slope * pos + intercept
    
    return {
        'slope': slope,
        'intercept': intercept,
        'func': trendline_func,
        'points': filtered_maxs
    }

def calculate_pullback_trendline(df_m1, swing_low_idx, pullback_end_idx):
    """
    Vẽ trendline sóng hồi (tăng) nối từ swing low qua các đáy cao dần
    
    Returns: dict với {'slope', 'intercept', 'func', 'points'} hoặc None
    """
    if swing_low_idx >= pullback_end_idx or pullback_end_idx >= len(df_m1):
        return None
    
    pullback_candles = df_m1.iloc[swing_low_idx:pullback_end_idx + 1]
    
    # Tìm các đáy (local minima) trong pullback - Cải thiện: Tìm với lookback lớn hơn
    lows = pullback_candles['low'].values
    
    local_mins = []
    lookback = 2  # So sánh với 2 nến trước và sau (thay vì 1)
    for i in range(lookback, len(lows) - lookback):
        # Kiểm tra xem đây có phải là local minimum không (thấp hơn lookback nến trước và sau)
        is_local_min = True
        for j in range(i - lookback, i + lookback + 1):
            if j != i and lows[j] <= lows[i]:
                is_local_min = False
                break
        
        if is_local_min:
            idx_in_df = pullback_candles.index[i]
            pos_in_df = df_m1.index.get_loc(idx_in_df) if hasattr(df_m1.index, 'get_loc') else i + swing_low_idx
            local_mins.append({'pos': pos_in_df, 'price': lows[i], 'idx': idx_in_df})
    
    # Thêm swing low vào đầu
    swing_low_pos = swing_low_idx
    swing_low_price = df_m1.iloc[swing_low_idx]['low']
    local_mins.insert(0, {'pos': swing_low_pos, 'price': swing_low_price, 'idx': df_m1.index[swing_low_idx] if hasattr(df_m1.index[swing_low_idx], '__iter__') else swing_low_idx})
    
    local_mins = sorted(local_mins, key=lambda x: x['pos'])
    
    # Lọc các đáy cao dần - Logic cải thiện: Cho phép đáy thấp hơn một chút nhưng vẫn cao hơn swing low
    # và đảm bảo xu hướng tổng thể vẫn là tăng (higher lows)
    filtered_mins = [local_mins[0]]  # Swing low (điểm đầu)
    swing_low_price = local_mins[0]['price']
    
    for i in range(1, len(local_mins)):
        current_price = local_mins[i]['price']
        last_price = filtered_mins[-1]['price']
        
        # Chấp nhận đáy nếu:
        # 1. Cao hơn đáy trước (higher low), HOẶC
        # 2. Thấp hơn đáy trước một chút (cho phép pullback nhẹ) nhưng:
        #    - Vẫn cao hơn swing low (đảm bảo không phá swing low)
        #    - Và đáy tiếp theo (nếu có) sẽ cao hơn đáy hiện tại (đảm bảo xu hướng tăng)
        
        # Điều kiện 1: Cao hơn đáy trước (higher low)
        if current_price >= last_price:
            filtered_mins.append(local_mins[i])
        # Điều kiện 2: Thấp hơn đáy trước nhưng vẫn cao hơn swing low và có xu hướng tăng
        elif current_price >= swing_low_price:
            # Kiểm tra xem có đáy nào sau đáy này cao hơn không (đảm bảo xu hướng tăng)
            has_higher_low_after = False
            for j in range(i + 1, len(local_mins)):
                if local_mins[j]['price'] > current_price:
                    has_higher_low_after = True
                    break
            
            # Nếu có đáy cao hơn sau đó, hoặc đây là đáy cuối cùng, chấp nhận
            if has_higher_low_after or i == len(local_mins) - 1:
                # Chỉ chấp nhận nếu không quá thấp so với đáy trước (tối đa 0.1% pullback)
                max_pullback = last_price * 0.999  # Cho phép pullback tối đa 0.1%
                if current_price >= max_pullback:
                    filtered_mins.append(local_mins[i])
    
    if len(filtered_mins) < 2:
        return None
    
    # Linear regression
    x_values = np.array([m['pos'] for m in filtered_mins])
    y_values = np.array([m['price'] for m in filtered_mins])
    
    n = len(x_values)
    sum_x = x_values.sum()
    sum_y = y_values.sum()
    sum_xy = (x_values * y_values).sum()
    sum_x2 = (x_values * x_values).sum()
    
    denominator = n * sum_x2 - sum_x * sum_x
    if abs(denominator) < 1e-10:
        return None
    
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    
    def trendline_func(pos):
        return slope * pos + intercept
    
    return {
        'slope': slope,
        'intercept': intercept,
        'func': trendline_func,
        'points': filtered_mins
    }

def check_trendline_break_buy(df_m1, trendline_info, current_candle_idx, ema50_val):
    """
    Kiểm tra nến phá vỡ trendline sóng hồi cho BUY:
    ✅ Giá đóng cửa vượt lên trên trendline sóng hồi
    ✅ Giá đóng cửa ≥ EMA 50
    ✅ RSI đang hướng lên (RSI hiện tại > RSI nến trước)
    ✅ ADX ≥ 20 (Điều kiện 5: Nến xác nhận)
    
    Returns: (is_break, message)
    """
    if trendline_info is None:
        return False, "Không có trendline"
    
    if current_candle_idx >= len(df_m1):
        return False, "Index vượt quá"
    
    current_candle = df_m1.iloc[current_candle_idx]
    prev_candle = df_m1.iloc[current_candle_idx - 1] if current_candle_idx > 0 else None
    
    trendline_value = trendline_info['func'](current_candle_idx)
    
    # 1. Giá đóng cửa vượt lên trên trendline
    close_above_trendline = current_candle['close'] > trendline_value
    if not close_above_trendline:
        return False, f"Close ({current_candle['close']:.5f}) không vượt lên trên trendline ({trendline_value:.5f})"
    
    # 2. Giá đóng cửa ≥ EMA 50
    if ema50_val is None or pd.isna(ema50_val):
        return False, "EMA50 không có giá trị"
    
    close_above_ema50 = current_candle['close'] >= ema50_val
    if not close_above_ema50:
        return False, f"Close ({current_candle['close']:.5f}) < EMA50 ({ema50_val:.5f})"
    
    # 3. RSI đang hướng lên
    current_rsi = current_candle.get('rsi', None)
    if prev_candle is not None:
        prev_rsi = prev_candle.get('rsi', None)
        if pd.notna(current_rsi) and pd.notna(prev_rsi):
            rsi_rising = current_rsi > prev_rsi
            if not rsi_rising:
                return False, f"RSI không hướng lên: {current_rsi:.1f} <= {prev_rsi:.1f}"
        else:
            return False, "RSI không có giá trị"
    else:
        return False, "Không có nến trước để so sánh RSI"
    
    # 4. ADX ≥ 18 (Điều kiện 5: Nến xác nhận)
    current_adx = current_candle.get('adx', None)
    if pd.isna(current_adx) or current_adx is None:
        return False, "ADX không có giá trị"
    
    adx_ok = current_adx >= 18
    if not adx_ok:
        return False, f"ADX ({current_adx:.1f}) < 18"
    
    return True, f"Break confirmed: Close {current_candle['close']:.5f} > Trendline {trendline_value:.5f}, Close >= EMA50 {ema50_val:.5f}, RSI rising {prev_rsi:.1f} -> {current_rsi:.1f}, ADX {current_adx:.1f} >= 18"

def check_bearish_divergence(df_m1, lookback=50):
    """
    Kiểm tra Bearish Divergence:
    - Giá tạo Higher High (HH) nhưng RSI tạo Lower High (LH) hoặc không tạo Higher High
    
    Returns: (has_divergence, message)
    """
    if len(df_m1) < lookback:
        return False, "Không đủ dữ liệu để kiểm tra divergence"
    
    recent_df = df_m1.iloc[-lookback:]
    recent_rsi = recent_df['rsi']
    
    # Tìm các đỉnh (peaks) trong giá và RSI
    peaks = []
    for i in range(2, len(recent_df) - 2):
        if (recent_df.iloc[i]['high'] > recent_df.iloc[i-1]['high'] and 
            recent_df.iloc[i]['high'] > recent_df.iloc[i+1]['high']):
            rsi_val = recent_rsi.iloc[i]
            if pd.notna(rsi_val):
                peaks.append({
                    'idx': i,
                    'price': recent_df.iloc[i]['high'],
                    'rsi': rsi_val
                })
    
    # Cần ít nhất 2 đỉnh để so sánh
    if len(peaks) < 2:
        return False, "Không đủ đỉnh để kiểm tra divergence"
    
    # So sánh 2 đỉnh gần nhất
    last_peak = peaks[-1]
    prev_peak = peaks[-2]
    
    # Bearish Divergence: Giá tạo HH nhưng RSI tạo LH hoặc không tạo HH
    price_higher = last_peak['price'] > prev_peak['price']
    rsi_lower = last_peak['rsi'] < prev_peak['rsi']
    
    if price_higher and rsi_lower:
        return True, f"Bearish Divergence: Giá HH ({prev_peak['price']:.5f} → {last_peak['price']:.5f}), RSI LH ({prev_peak['rsi']:.1f} → {last_peak['rsi']:.1f})"
    
    # Nếu giá tạo HH nhưng RSI không tạo HH (RSI bằng hoặc thấp hơn)
    if price_higher and last_peak['rsi'] <= prev_peak['rsi']:
        return True, f"Bearish Divergence: Giá HH ({prev_peak['price']:.5f} → {last_peak['price']:.5f}), RSI không tạo HH ({prev_peak['rsi']:.1f} → {last_peak['rsi']:.1f})"
    
    return False, "Không có Bearish Divergence"

def check_bullish_divergence(df_m1, lookback=50):
    """
    Kiểm tra Bullish Divergence:
    - Giá tạo Lower Low (LL) nhưng RSI tạo Higher Low (HL) hoặc không tạo Lower Low
    
    Returns: (has_divergence, message)
    """
    if len(df_m1) < lookback:
        return False, "Không đủ dữ liệu để kiểm tra divergence"
    
    recent_df = df_m1.iloc[-lookback:]
    recent_rsi = recent_df['rsi']
    
    # Tìm các đáy (troughs) trong giá và RSI
    troughs = []
    for i in range(2, len(recent_df) - 2):
        if (recent_df.iloc[i]['low'] < recent_df.iloc[i-1]['low'] and 
            recent_df.iloc[i]['low'] < recent_df.iloc[i+1]['low']):
            rsi_val = recent_rsi.iloc[i]
            if pd.notna(rsi_val):
                troughs.append({
                    'idx': i,
                    'price': recent_df.iloc[i]['low'],
                    'rsi': rsi_val
                })
    
    # Cần ít nhất 2 đáy để so sánh
    if len(troughs) < 2:
        return False, "Không đủ đáy để kiểm tra divergence"
    
    # So sánh 2 đáy gần nhất
    last_trough = troughs[-1]
    prev_trough = troughs[-2]
    
    # Bullish Divergence: Giá tạo LL nhưng RSI tạo HL hoặc không tạo LL
    price_lower = last_trough['price'] < prev_trough['price']
    rsi_higher = last_trough['rsi'] > prev_trough['rsi']
    
    if price_lower and rsi_higher:
        return True, f"Bullish Divergence: Giá LL ({prev_trough['price']:.5f} → {last_trough['price']:.5f}), RSI HL ({prev_trough['rsi']:.1f} → {last_trough['rsi']:.1f})"
    
    # Nếu giá tạo LL nhưng RSI không tạo LL (RSI bằng hoặc cao hơn)
    if price_lower and last_trough['rsi'] >= prev_trough['rsi']:
        return True, f"Bullish Divergence: Giá LL ({prev_trough['price']:.5f} → {last_trough['price']:.5f}), RSI không tạo LL ({prev_trough['rsi']:.1f} → {last_trough['rsi']:.1f})"
    
    return False, "Không có Bullish Divergence"

def check_trendline_break_sell(df_m1, trendline_info, current_candle_idx, ema50_val):
    """
    Kiểm tra nến phá vỡ trendline sóng hồi cho SELL:
    ✅ Giá đóng cửa phá xuống dưới trendline sóng hồi
    ✅ Giá đóng cửa ≤ EMA 50
    ✅ RSI đang hướng xuống (RSI hiện tại < RSI nến trước)
    ✅ ADX ≥ 20 (Điều kiện 5: Nến xác nhận)
    
    Returns: (is_break, message)
    """
    if trendline_info is None:
        return False, "Không có trendline"
    
    if current_candle_idx >= len(df_m1):
        return False, "Index vượt quá"
    
    current_candle = df_m1.iloc[current_candle_idx]
    prev_candle = df_m1.iloc[current_candle_idx - 1] if current_candle_idx > 0 else None
    
    trendline_value = trendline_info['func'](current_candle_idx)
    
    # 1. Giá đóng cửa phá xuống dưới trendline
    close_below_trendline = current_candle['close'] < trendline_value
    if not close_below_trendline:
        return False, f"Close ({current_candle['close']:.5f}) không phá xuống dưới trendline ({trendline_value:.5f})"
    
    # 2. Giá đóng cửa ≤ EMA 50
    if ema50_val is None or pd.isna(ema50_val):
        return False, "EMA50 không có giá trị"
    
    close_below_ema50 = current_candle['close'] <= ema50_val
    if not close_below_ema50:
        return False, f"Close ({current_candle['close']:.5f}) > EMA50 ({ema50_val:.5f})"
    
    # 3. RSI đang hướng xuống
    current_rsi = current_candle.get('rsi', None)
    if prev_candle is not None:
        prev_rsi = prev_candle.get('rsi', None)
        if pd.notna(current_rsi) and pd.notna(prev_rsi):
            rsi_declining = current_rsi < prev_rsi
            if not rsi_declining:
                return False, f"RSI không hướng xuống: {current_rsi:.1f} >= {prev_rsi:.1f}"
        else:
            return False, "RSI không có giá trị"
    else:
        return False, "Không có nến trước để so sánh RSI"
    
    # 4. ADX ≥ 18 (Điều kiện 5: Nến xác nhận)
    current_adx = current_candle.get('adx', None)
    if pd.isna(current_adx) or current_adx is None:
        return False, "ADX không có giá trị"
    
    adx_ok = current_adx >= 18
    if not adx_ok:
        return False, f"ADX ({current_adx:.1f}) < 18"
    
    return True, f"Break confirmed: Close {current_candle['close']:.5f} < Trendline {trendline_value:.5f}, Close <= EMA50 {ema50_val:.5f}, RSI declining {prev_rsi:.1f} -> {current_rsi:.1f}, ADX {current_adx:.1f} >= 18"

def m1_scalp_logic(config, error_count=0):
    """
    M1 Scalp Strategy Logic - Swing High/Low + Pullback + Trendline Break
    BUY: EMA50 > EMA200, Swing High với RSI > 70, Pullback hợp lệ, Trendline break, ATR >= threshold (dynamic)
    SELL: EMA50 < EMA200, Swing Low với RSI < 30, Pullback hợp lệ, Trendline break, ATR >= threshold (dynamic)
    Entry: Close của nến phá vỡ trendline
    SL = 2ATR + 6 point, TP = 2SL
    """
    try:
        symbol = config['symbol']
        volume = config.get('volume', 0.01)
        magic = config['magic']
        max_positions = config.get('max_positions', 1)
        
        # --- 1. Manage Existing Positions ---
        # Chỉ quản lý positions do bot này mở (theo magic number)
        all_positions = mt5.positions_get(symbol=symbol)
        positions = [pos for pos in (all_positions or []) if pos.magic == magic]
        if positions:
            for pos in positions:
                manage_position(pos.ticket, symbol, magic, config)
            if len(positions) >= max_positions:
                return error_count, 0

        # --- 2. Data Fetching ---
        df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 300)
        if df_m1 is None:
            print(f"⚠️ Không thể lấy dữ liệu M1 cho {symbol}")
            return error_count, 0

        # Fetch M5 data for RSI condition
        df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 100)
        if df_m5 is None:
            print(f"⚠️ Không thể lấy dữ liệu M5 cho {symbol}")
            return error_count, 0

        # --- 3. Calculate Indicators ---
        df_m1['ema50'] = calculate_ema(df_m1['close'], 50)
        df_m1['ema200'] = calculate_ema(df_m1['close'], 200)
        df_m1['atr'] = calculate_atr(df_m1, 14)
        df_m1['rsi'] = calculate_rsi(df_m1['close'], 14)
        df_m1 = calculate_adx(df_m1, period=14)  # Calculate ADX for condition 5
        
        # Calculate RSI(14) on M5
        df_m5['rsi'] = calculate_rsi(df_m5['close'], 14)
        
        # Volume MA (10 candles)
        df_m1['vol_ma'] = df_m1['tick_volume'].rolling(window=10).mean()
        
        # Get current and previous candles (completed candles)
        if len(df_m1) < 3:
            return error_count, 0
        
        curr_candle = df_m1.iloc[-2]  # Last completed candle
        prev_candle = df_m1.iloc[-3]   # Previous completed candle
        current_rsi = df_m1['rsi'].iloc[-2]  # RSI of last completed candle
        prev_rsi = df_m1['rsi'].iloc[-3]     # RSI of previous candle
        
        # Get current price for entry
        tick = mt5.symbol_info_tick(symbol)
        current_price = tick.ask  # Will be updated based on signal
        
        # Get point size
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            print(f"⚠️ Không thể lấy thông tin symbol {symbol}")
            return error_count, 0
        
        point = symbol_info.point
        
        # --- 4. Check ATR Condition (Điều kiện 4) ---
        atr_val = curr_candle['atr']
        min_atr = get_min_atr_threshold(symbol, config)  # Dynamic ATR threshold based on symbol
        atr_ok = pd.notna(atr_val) and atr_val >= min_atr
        
        signal_type = None
        reason = ""
        log_details = []
        
        # Log ATR condition
        log_details.append(f"{'='*80}")
        log_details.append(f"🔍 [ĐIỀU KIỆN CHUNG] Kiểm tra ATR...")
        log_details.append(f"{'='*80}")
        if atr_ok:
            # Format ATR display based on symbol type
            symbol_upper = symbol.upper()
            if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                log_details.append(f"✅ ĐK4 (Chung): ATR ({atr_val:.2f} USD) >= {min_atr:.2f} USD")
            elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                log_details.append(f"✅ ĐK4 (Chung): ATR ({atr_val:.2f} USD) >= {min_atr:.2f} USD")
            else:
                atr_pips = atr_val / 0.0001
                log_details.append(f"✅ ĐK4 (Chung): ATR ({atr_pips:.1f} pips = {atr_val:.5f}) >= {min_atr:.5f}")
        else:
            if pd.isna(atr_val):
                log_details.append(f"❌ ĐK4 (Chung): ATR không có giá trị (NaN)")
            else:
                # Format ATR display based on symbol type
                symbol_upper = symbol.upper()
                if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                    log_details.append(f"❌ ĐK4 (Chung): ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD")
                elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                    log_details.append(f"❌ ĐK4 (Chung): ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD")
                else:
                    atr_pips = atr_val / 0.0001
                    log_details.append(f"❌ ĐK4 (Chung): ATR ({atr_pips:.1f} pips = {atr_val:.5f}) < {min_atr:.5f}")
        
        # Nếu ATR không đạt, vẫn tiếp tục kiểm tra các điều kiện khác để log đầy đủ
        # nhưng sẽ không có signal
        if not atr_ok:
            log_details.append(f"   ⚠️ ATR không đạt → Sẽ không có signal (nhưng vẫn kiểm tra các điều kiện khác để log)")
        
        # Track BUY conditions status
        buy_dk1_ok = False
        buy_dk2_ok = False
        buy_dk3_ok = False
        buy_dk3b_ok = False
        buy_dk4_ok = False
        buy_dk5_ok = False
        buy_dk6_ok = False  # Điều kiện 6: Không có Bearish Divergence
        buy_dk7_ok = False  # Điều kiện 7: RSI(14)_M5 >= 55 và <= 65
        buy_fail_reason = ""
        
        # Track SELL conditions status
        sell_dk1_ok = False
        sell_dk2_ok = False
        sell_dk3_ok = False
        sell_dk3b_ok = False
        sell_dk4_ok = False
        sell_dk5_ok = False
        sell_dk6_ok = False  # Điều kiện 6: Không có Bullish Divergence
        sell_dk7_ok = False  # Điều kiện 7: RSI(14)_M5 >= 35 và <= 45
        sell_fail_reason = ""
        
        ema50_val = curr_candle['ema50']
        ema200_val = curr_candle['ema200']
        current_candle_idx = len(df_m1) - 2  # Last completed candle index
        
        # --- 5. BUY Signal Check ---
        log_details.append(f"{'='*80}")
        log_details.append(f"🔍 [BUY] Kiểm tra điều kiện BUY...")
        log_details.append(f"{'='*80}")
        
        # Điều kiện 1: EMA50 > EMA200
        buy_condition1 = ema50_val > ema200_val
        buy_dk1_ok = buy_condition1
        log_details.append(f"{'✅' if buy_condition1 else '❌'} [BUY] ĐK1: EMA50 ({ema50_val:.5f}) > EMA200 ({ema200_val:.5f})")
        
        if buy_condition1:
            # Điều kiện 2: Tìm Swing High với RSI > 70
            log_details.append(f"\n🔍 [BUY] ĐK2: Tìm Swing High với RSI > 70")
            swing_highs_with_rsi = find_swing_high_with_rsi(df_m1, lookback=5, min_rsi=70)
            
            if len(swing_highs_with_rsi) == 0:
                log_details.append(f"   ❌ Không tìm thấy swing high với RSI > 70")
                buy_fail_reason = "Không tìm thấy Swing High với RSI > 70"
            else:
                buy_dk2_ok = True
                # Lấy swing high gần nhất
                latest_swing_high = swing_highs_with_rsi[-1]
                swing_high_idx = latest_swing_high['index']
                swing_high_price = latest_swing_high['price']
                swing_high_rsi = latest_swing_high['rsi']
                
                log_details.append(f"   ✅ Tìm thấy swing high: Index={swing_high_idx}, Price={swing_high_price:.5f}, RSI={swing_high_rsi:.1f}")
                
                # Điều kiện 3: Kiểm tra sóng hồi hợp lệ (Logic mới)
                log_details.append(f"\n🔍 [BUY] ĐK3: Kiểm tra sóng hồi hợp lệ (Logic mới)")
                pullback_valid, pullback_end_idx, pullback_candles, slope_category, pullback_msg = check_valid_pullback_buy(
                    df_m1, swing_high_idx, max_candles=30, rsi_target_min=40, rsi_target_max=50, rsi_min_during_pullback=32
                )
                
                if not pullback_valid:
                    log_details.append(f"   ❌ {pullback_msg}")
                    buy_fail_reason = f"ĐK3: {pullback_msg}"
                elif slope_category == 'steep':
                    # Pullback hơi dốc → KHÔNG ENTRY NGAY, cần cấu trúc hồi rõ ràng
                    log_details.append(f"   ⚠️ {pullback_msg}")
                    log_details.append(f"   ⚠️ Pullback hơi dốc - KHÔNG ENTRY NGAY")
                    log_details.append(f"   ⚠️ Cần chờ cấu trúc hồi rõ ràng (đáy - đỉnh) và vẽ lại trendline")
                    buy_fail_reason = f"ĐK3: {pullback_msg} - Cần cấu trúc hồi rõ ràng"
                else:
                    # slope_category == 'valid' (18-48)
                    buy_dk3_ok = True
                    log_details.append(f"   ✅ {pullback_msg}")
                    
                    # Vẽ trendline sóng hồi
                    log_details.append(f"\n🔍 [BUY] ĐK3b: Vẽ trendline sóng hồi")
                    # QUAN TRỌNG: Vẽ trendline với dữ liệu mới nhất đến current_candle_idx (hoặc pullback_end_idx nếu gần hơn)
                    # Đảm bảo trendline được vẽ với tất cả dữ liệu có sẵn trước khi kiểm tra phá vỡ
                    trendline_end_idx = min(pullback_end_idx, current_candle_idx)
                    # Nhưng nếu current_candle_idx > pullback_end_idx, vẽ lại trendline đến current_candle_idx để có dữ liệu mới nhất
                    if current_candle_idx > pullback_end_idx:
                        # Vẽ lại trendline với dữ liệu mới nhất (đến current_candle_idx)
                        trendline_end_idx = current_candle_idx
                        log_details.append(f"   ⚠️ pullback_end_idx ({pullback_end_idx}) < current_candle_idx ({current_candle_idx})")
                        log_details.append(f"   🔄 Vẽ lại trendline với dữ liệu mới nhất đến index {trendline_end_idx}")
                    
                    trendline_info = calculate_pullback_trendline_buy(df_m1, swing_high_idx, trendline_end_idx)
                    
                    if trendline_info is None:
                        log_details.append(f"   ❌ Không thể vẽ trendline")
                        buy_fail_reason = "ĐK3b: Không thể vẽ trendline (không đủ đỉnh thấp dần)"
                    else:
                        buy_dk3b_ok = True
                        log_details.append(f"   ✅ Trendline đã vẽ: Slope={trendline_info['slope']:.8f}, Số điểm: {len(trendline_info['points'])}")
                        log_details.append(f"   📍 Trendline được vẽ từ index {swing_high_idx} đến {trendline_end_idx}")
                        
                        # Điều kiện 4: ATR (đã check ở trên) và UpperWick trong sóng hồi
                        log_details.append(f"\n🔍 [BUY] ĐK4: Kiểm tra ATR và UpperWick trong sóng hồi")
                        buy_dk4_ok = atr_ok
                        if not buy_dk4_ok:
                            if pd.notna(atr_val):
                                symbol_upper = symbol.upper()
                                if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                                    buy_fail_reason = f"ĐK4: ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD"
                                elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                                    buy_fail_reason = f"ĐK4: ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD"
                                else:
                                    buy_fail_reason = f"ĐK4: ATR ({atr_val:.5f}) < {min_atr:.5f}"
                            else:
                                buy_fail_reason = "ĐK4: ATR không có giá trị (NaN)"
                        else:
                            # Kiểm tra UpperWick trong toàn bộ sóng hồi
                            upperwick_ok, upperwick_msg = check_pullback_upperwick(df_m1, swing_high_idx, pullback_end_idx)
                            if not upperwick_ok:
                                log_details.append(f"   ❌ {upperwick_msg}")
                                buy_dk4_ok = False
                                buy_fail_reason = f"ĐK4: {upperwick_msg}"
                            else:
                                log_details.append(f"   ✅ {upperwick_msg}")
                                buy_dk4_ok = True
                        
                        # Điều kiện 5: Nến xác nhận phá vỡ trendline
                        log_details.append(f"\n🔍 [BUY] ĐK5: Kiểm tra nến phá vỡ trendline")
                        log_details.append(f"   📍 Kiểm tra tại current_candle_idx: {current_candle_idx}, trendline_end_idx: {trendline_end_idx}")
                        break_ok, break_msg = check_trendline_break_buy(df_m1, trendline_info, current_candle_idx, ema50_val)
                        
                        if not break_ok:
                            log_details.append(f"   ❌ {break_msg}")
                            buy_fail_reason = f"ĐK5: {break_msg}"
                        else:
                            buy_dk5_ok = True
                            log_details.append(f"   ✅ {break_msg}")
                            
                            # Điều kiện 6: Không có Bearish Divergence
                            log_details.append(f"\n🔍 [BUY] ĐK6: Kiểm tra Bearish Divergence")
                            has_bearish_div, bearish_div_msg = check_bearish_divergence(df_m1, lookback=50)
                            
                            if has_bearish_div:
                                log_details.append(f"   ❌ {bearish_div_msg}")
                                buy_fail_reason = f"ĐK6: {bearish_div_msg}"
                            else:
                                buy_dk6_ok = True
                                log_details.append(f"   ✅ {bearish_div_msg}")
                                
                                # Điều kiện 7: RSI(14)_M5 >= 55 và <= 65
                                log_details.append(f"\n🔍 [BUY] ĐK7: Kiểm tra RSI(14)_M5 >= 55 và <= 65")
                                if len(df_m5) < 2:
                                    log_details.append(f"   ❌ Không đủ dữ liệu M5 để tính RSI")
                                    buy_fail_reason = "ĐK7: Không đủ dữ liệu M5"
                                else:
                                    rsi_m5 = df_m5['rsi'].iloc[-2]  # RSI của nến M5 đã đóng gần nhất
                                    if pd.notna(rsi_m5):
                                        rsi_m5_ok = 55 <= rsi_m5 <= 65
                                        buy_dk7_ok = rsi_m5_ok
                                        if rsi_m5_ok:
                                            log_details.append(f"   ✅ RSI(14)_M5 = {rsi_m5:.1f} (55 ≤ {rsi_m5:.1f} ≤ 65)")
                                        else:
                                            log_details.append(f"   ❌ RSI(14)_M5 = {rsi_m5:.1f} (không trong khoảng 55-65)")
                                            buy_fail_reason = f"ĐK7: RSI(14)_M5 ({rsi_m5:.1f}) không trong khoảng 55-65"
                                    else:
                                        log_details.append(f"   ❌ RSI(14)_M5 không có giá trị (NaN)")
                                        buy_fail_reason = "ĐK7: RSI(14)_M5 không có giá trị"
                                
                                # Tất cả điều kiện đã thỏa (bao gồm ATR, không có Bearish Divergence và RSI M5)
                                if buy_dk1_ok and buy_dk2_ok and buy_dk3_ok and buy_dk3b_ok and buy_dk4_ok and buy_dk5_ok and buy_dk6_ok and buy_dk7_ok:
                                    signal_type = "BUY"
                                    reason = "M1_Scalp_SwingHigh_Pullback_TrendlineBreak"
                                    current_price = curr_candle['close']  # Entry tại close của nến phá vỡ
                                    
                                    log_details.append(f"\n🚀 [BUY SIGNAL] Tất cả điều kiện đã thỏa!")
                                    log_details.append(f"   Entry: {current_price:.5f} (giá đóng cửa nến phá vỡ)")
                                else:
                                    if not buy_dk4_ok:
                                        if pd.notna(atr_val):
                                            symbol_upper = symbol.upper()
                                            if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                                                buy_fail_reason = f"ĐK4: ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD"
                                            elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                                                buy_fail_reason = f"ĐK4: ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD"
                                            else:
                                                buy_fail_reason = f"ĐK4: ATR ({atr_val:.5f}) < {min_atr:.5f}"
                                        else:
                                            buy_fail_reason = "ĐK4: ATR không có giá trị (NaN)"
                                    elif not buy_dk6_ok:
                                        buy_fail_reason = f"ĐK6: {bearish_div_msg}"
                                    elif not buy_dk7_ok:
                                        # buy_fail_reason already set above
                                        pass
        else:
            log_details.append(f"   ⏭️ [BUY] ĐK1 không thỏa → Bỏ qua các điều kiện còn lại")
        
        # --- 6. SELL Signal Check ---
        if signal_type is None:
            log_details.append(f"\n{'='*80}")
            log_details.append(f"🔍 [SELL] Kiểm tra điều kiện SELL...")
            log_details.append(f"{'='*80}")
            
            # Điều kiện 1: EMA50 < EMA200
            sell_condition1 = ema50_val < ema200_val
            sell_dk1_ok = sell_condition1
            log_details.append(f"{'✅' if sell_condition1 else '❌'} [SELL] ĐK1: EMA50 ({ema50_val:.5f}) < EMA200 ({ema200_val:.5f})")
            
            if sell_condition1:
                # Điều kiện 2: Tìm Swing Low với RSI < 30
                log_details.append(f"\n🔍 [SELL] ĐK2: Tìm Swing Low với RSI < 30")
                swing_lows_with_rsi = find_swing_low_with_rsi(df_m1, lookback=5, min_rsi=30)
                
                if len(swing_lows_with_rsi) == 0:
                    log_details.append(f"   ❌ Không tìm thấy swing low với RSI < 30")
                    sell_fail_reason = "Không tìm thấy Swing Low với RSI < 30"
                else:
                    sell_dk2_ok = True
                    # Lấy swing low gần nhất
                    latest_swing_low = swing_lows_with_rsi[-1]
                    swing_low_idx = latest_swing_low['index']
                    swing_low_price = latest_swing_low['price']
                    swing_low_rsi = latest_swing_low['rsi']
                    
                    log_details.append(f"   ✅ Tìm thấy swing low: Index={swing_low_idx}, Price={swing_low_price:.5f}, RSI={swing_low_rsi:.1f}")
                    
                    # Điều kiện 3: Kiểm tra sóng hồi hợp lệ (Logic mới)
                    log_details.append(f"\n🔍 [SELL] ĐK3: Kiểm tra sóng hồi hợp lệ (Logic mới)")
                    pullback_valid, pullback_end_idx, pullback_candles, slope_category, pullback_msg = check_valid_pullback_sell(
                        df_m1, swing_low_idx, max_candles=30, rsi_target_min=50, rsi_target_max=60, rsi_max_during_pullback=68
                    )
                    
                    if not pullback_valid:
                        log_details.append(f"   ❌ {pullback_msg}")
                        sell_fail_reason = f"ĐK3: {pullback_msg}"
                    elif slope_category == 'steep':
                        # Pullback hơi dốc → KHÔNG ENTRY NGAY, cần cấu trúc hồi rõ ràng
                        log_details.append(f"   ⚠️ {pullback_msg}")
                        log_details.append(f"   ⚠️ Pullback hơi dốc - KHÔNG ENTRY NGAY")
                        log_details.append(f"   ⚠️ Cần chờ cấu trúc hồi rõ ràng (đỉnh - đáy) và vẽ lại trendline")
                        sell_fail_reason = f"ĐK3: {pullback_msg} - Cần cấu trúc hồi rõ ràng"
                    else:
                        # slope_category == 'valid' (18-48)
                        sell_dk3_ok = True
                        log_details.append(f"   ✅ {pullback_msg}")
                        
                        # Vẽ trendline sóng hồi
                        log_details.append(f"\n🔍 [SELL] ĐK3b: Vẽ trendline sóng hồi")
                        # QUAN TRỌNG: Vẽ trendline với dữ liệu mới nhất đến current_candle_idx (hoặc pullback_end_idx nếu gần hơn)
                        # Đảm bảo trendline được vẽ với tất cả dữ liệu có sẵn trước khi kiểm tra phá vỡ
                        trendline_end_idx = min(pullback_end_idx, current_candle_idx)
                        # Nhưng nếu current_candle_idx > pullback_end_idx, vẽ lại trendline đến current_candle_idx để có dữ liệu mới nhất
                        if current_candle_idx > pullback_end_idx:
                            # Vẽ lại trendline với dữ liệu mới nhất (đến current_candle_idx)
                            trendline_end_idx = current_candle_idx
                            log_details.append(f"   ⚠️ pullback_end_idx ({pullback_end_idx}) < current_candle_idx ({current_candle_idx})")
                            log_details.append(f"   🔄 Vẽ lại trendline với dữ liệu mới nhất đến index {trendline_end_idx}")
                        
                        trendline_info = calculate_pullback_trendline(df_m1, swing_low_idx, trendline_end_idx)
                        
                        if trendline_info is None:
                            log_details.append(f"   ❌ Không thể vẽ trendline")
                            sell_fail_reason = "ĐK3b: Không thể vẽ trendline (không đủ đáy cao dần)"
                        else:
                            sell_dk3b_ok = True
                            log_details.append(f"   ✅ Trendline đã vẽ: Slope={trendline_info['slope']:.8f}, Số điểm: {len(trendline_info['points'])}")
                            log_details.append(f"   📍 Trendline được vẽ từ index {swing_low_idx} đến {trendline_end_idx}")
                            
                            # Điều kiện 4: ATR (đã check ở trên) và LowerWick trong sóng hồi
                            log_details.append(f"\n🔍 [SELL] ĐK4: Kiểm tra ATR và LowerWick trong sóng hồi")
                            sell_dk4_ok = atr_ok
                            if not sell_dk4_ok:
                                if pd.notna(atr_val):
                                    symbol_upper = symbol.upper()
                                    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                                        sell_fail_reason = f"ĐK4: ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD"
                                    elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                                        sell_fail_reason = f"ĐK4: ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD"
                                    else:
                                        sell_fail_reason = f"ĐK4: ATR ({atr_val:.5f}) < {min_atr:.5f}"
                                else:
                                    sell_fail_reason = "ĐK4: ATR không có giá trị (NaN)"
                            else:
                                # Kiểm tra LowerWick trong toàn bộ sóng hồi
                                lowerwick_ok, lowerwick_msg = check_pullback_lowerwick(df_m1, swing_low_idx, pullback_end_idx)
                                if not lowerwick_ok:
                                    log_details.append(f"   ❌ {lowerwick_msg}")
                                    sell_dk4_ok = False
                                    sell_fail_reason = f"ĐK4: {lowerwick_msg}"
                                else:
                                    log_details.append(f"   ✅ {lowerwick_msg}")
                                    sell_dk4_ok = True
                            
                            # Điều kiện 5: Nến xác nhận phá vỡ trendline
                            log_details.append(f"\n🔍 [SELL] ĐK5: Kiểm tra nến phá vỡ trendline")
                            log_details.append(f"   📍 Kiểm tra tại current_candle_idx: {current_candle_idx}, trendline_end_idx: {trendline_end_idx}")
                            break_ok, break_msg = check_trendline_break_sell(df_m1, trendline_info, current_candle_idx, ema50_val)
                            
                            if not break_ok:
                                log_details.append(f"   ❌ {break_msg}")
                                sell_fail_reason = f"ĐK5: {break_msg}"
                            else:
                                sell_dk5_ok = True
                                log_details.append(f"   ✅ {break_msg}")
                                
                                # Điều kiện 6: Không có Bullish Divergence
                                log_details.append(f"\n🔍 [SELL] ĐK6: Kiểm tra Bullish Divergence")
                                has_bullish_div, bullish_div_msg = check_bullish_divergence(df_m1, lookback=50)
                                
                                if has_bullish_div:
                                    log_details.append(f"   ❌ {bullish_div_msg}")
                                    sell_fail_reason = f"ĐK6: {bullish_div_msg}"
                                else:
                                    sell_dk6_ok = True
                                    log_details.append(f"   ✅ {bullish_div_msg}")
                                    
                                    # Điều kiện 7: RSI(14)_M5 >= 35 và <= 45
                                    log_details.append(f"\n🔍 [SELL] ĐK7: Kiểm tra RSI(14)_M5 >= 35 và <= 45")
                                    if len(df_m5) < 2:
                                        log_details.append(f"   ❌ Không đủ dữ liệu M5 để tính RSI")
                                        sell_fail_reason = "ĐK7: Không đủ dữ liệu M5"
                                    else:
                                        rsi_m5 = df_m5['rsi'].iloc[-2]  # RSI của nến M5 đã đóng gần nhất
                                        if pd.notna(rsi_m5):
                                            rsi_m5_ok = 35 <= rsi_m5 <= 45
                                            sell_dk7_ok = rsi_m5_ok
                                            if rsi_m5_ok:
                                                log_details.append(f"   ✅ RSI(14)_M5 = {rsi_m5:.1f} (35 ≤ {rsi_m5:.1f} ≤ 45)")
                                            else:
                                                log_details.append(f"   ❌ RSI(14)_M5 = {rsi_m5:.1f} (không trong khoảng 35-45)")
                                                sell_fail_reason = f"ĐK7: RSI(14)_M5 ({rsi_m5:.1f}) không trong khoảng 35-45"
                                        else:
                                            log_details.append(f"   ❌ RSI(14)_M5 không có giá trị (NaN)")
                                            sell_fail_reason = "ĐK7: RSI(14)_M5 không có giá trị"
                                    
                                    # Tất cả điều kiện đã thỏa (bao gồm ATR, không có Bullish Divergence và RSI M5)
                                    if sell_dk1_ok and sell_dk2_ok and sell_dk3_ok and sell_dk3b_ok and sell_dk4_ok and sell_dk5_ok and sell_dk6_ok and sell_dk7_ok:
                                        signal_type = "SELL"
                                        reason = "M1_Scalp_SwingLow_Pullback_TrendlineBreak"
                                        current_price = curr_candle['close']  # Entry tại close của nến phá vỡ
                                        
                                        log_details.append(f"\n🚀 [SELL SIGNAL] Tất cả điều kiện đã thỏa!")
                                        log_details.append(f"   Entry: {current_price:.5f} (giá đóng cửa nến phá vỡ)")
                                    else:
                                        if not sell_dk4_ok:
                                            if pd.notna(atr_val):
                                                symbol_upper = symbol.upper()
                                                if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                                                    sell_fail_reason = f"ĐK4: ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD"
                                                elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                                                    sell_fail_reason = f"ĐK4: ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD"
                                                else:
                                                    sell_fail_reason = f"ĐK4: ATR ({atr_val:.5f}) < {min_atr:.5f}"
                                            else:
                                                sell_fail_reason = "ĐK4: ATR không có giá trị (NaN)"
                                        elif not sell_dk6_ok:
                                            sell_fail_reason = f"ĐK6: {bullish_div_msg}"
                                        elif not sell_dk7_ok:
                                            # sell_fail_reason already set above
                                            pass
            else:
                log_details.append(f"   ⏭️ [SELL] ĐK1 không thỏa → Bỏ qua các điều kiện còn lại")
        
        # --- 7. No Signal - Print Detailed Log ---
        if signal_type is None:
            print(f"\n{'='*80}")
            print(f"📊 [M1 Scalp] Không có tín hiệu - Chi tiết điều kiện:")
            print(f"{'='*80}")
            
            # Print all log details
            for detail in log_details:
                print(f"   {detail}")
            
            # Summary of why no signal
            print(f"\n{'─'*80}")
            print(f"📋 TÓM TẮT LÝ DO KHÔNG CÓ LỆNH:")
            print(f"{'─'*80}")
            
            # Check ATR first (common condition)
            if not atr_ok:
                if pd.notna(atr_val):
                    symbol_upper = symbol.upper()
                    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                        print(f"   ❌ ĐK4 (Chung): ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD")
                    elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                        print(f"   ❌ ĐK4 (Chung): ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD")
                    else:
                        atr_pips = atr_val / 0.0001
                        print(f"   ❌ ĐK4 (Chung): ATR ({atr_pips:.1f} pips = {atr_val:.5f}) < {min_atr:.5f}")
                else:
                    print(f"   ❌ ĐK4 (Chung): ATR (N/A) < {min_atr}")
            
            # BUY Summary
            print(f"\n   🔴 [BUY] Trạng thái điều kiện:")
            print(f"      {'✅' if buy_dk1_ok else '❌'} ĐK1: EMA50 > EMA200")
            if buy_dk1_ok:
                print(f"      {'✅' if buy_dk2_ok else '❌'} ĐK2: Tìm thấy Swing High với RSI > 70")
                if buy_dk2_ok:
                    print(f"      {'✅' if buy_dk3_ok else '❌'} ĐK3: Sóng hồi hợp lệ")
                    if buy_dk3_ok:
                        print(f"      {'✅' if buy_dk3b_ok else '❌'} ĐK3b: Vẽ được trendline")
                        if buy_dk3b_ok:
                            symbol_upper = symbol.upper()
                            if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                                print(f"      {'✅' if buy_dk4_ok else '❌'} ĐK4: ATR >= {min_atr:.2f} USD")
                            elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                                print(f"      {'✅' if buy_dk4_ok else '❌'} ĐK4: ATR >= {min_atr:.2f} USD")
                            else:
                                print(f"      {'✅' if buy_dk4_ok else '❌'} ĐK4: ATR >= {min_atr:.5f}")
                            if buy_dk4_ok:
                                print(f"      {'✅' if buy_dk5_ok else '❌'} ĐK5: Nến phá vỡ trendline")
                                if buy_dk5_ok:
                                    print(f"      {'✅' if buy_dk6_ok else '❌'} ĐK6: Không có Bearish Divergence")
                                    if buy_dk6_ok:
                                        print(f"      {'✅' if buy_dk7_ok else '❌'} ĐK7: RSI(14)_M5 >= 55 và <= 65")
            if buy_fail_reason:
                print(f"      💡 Lý do chính: {buy_fail_reason}")
            
            # SELL Summary
            print(f"\n   🔴 [SELL] Trạng thái điều kiện:")
            print(f"      {'✅' if sell_dk1_ok else '❌'} ĐK1: EMA50 < EMA200")
            if sell_dk1_ok:
                print(f"      {'✅' if sell_dk2_ok else '❌'} ĐK2: Tìm thấy Swing Low với RSI < 30")
                if sell_dk2_ok:
                    print(f"      {'✅' if sell_dk3_ok else '❌'} ĐK3: Sóng hồi hợp lệ")
                    if sell_dk3_ok:
                        print(f"      {'✅' if sell_dk3b_ok else '❌'} ĐK3b: Vẽ được trendline")
                        if sell_dk3b_ok:
                            symbol_upper = symbol.upper()
                            if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                                print(f"      {'✅' if sell_dk4_ok else '❌'} ĐK4: ATR >= {min_atr:.2f} USD")
                            elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                                print(f"      {'✅' if sell_dk4_ok else '❌'} ĐK4: ATR >= {min_atr:.2f} USD")
                            else:
                                print(f"      {'✅' if sell_dk4_ok else '❌'} ĐK4: ATR >= {min_atr:.5f}")
                            if sell_dk4_ok:
                                print(f"      {'✅' if sell_dk5_ok else '❌'} ĐK5: Nến phá vỡ trendline")
                                if sell_dk5_ok:
                                    print(f"      {'✅' if sell_dk6_ok else '❌'} ĐK6: Không có Bullish Divergence")
                                    if sell_dk6_ok:
                                        print(f"      {'✅' if sell_dk7_ok else '❌'} ĐK7: RSI(14)_M5 >= 35 và <= 45")
            if sell_fail_reason:
                print(f"      💡 Lý do chính: {sell_fail_reason}")
            
            # Current indicators
            current_rsi_display = curr_candle.get('rsi', 0)
            rsi_m5_display = df_m5['rsi'].iloc[-2] if len(df_m5) >= 2 else None
            current_adx_display = curr_candle.get('adx', None)
            print(f"\n📈 [Indicators Hiện Tại]")
            print(f"   💱 Price: {curr_candle['close']:.5f}")
            print(f"   📊 EMA50: {ema50_val:.5f}")
            print(f"   📊 EMA200: {ema200_val:.5f}")
            if pd.notna(current_rsi_display):
                print(f"   📊 RSI(M1): {current_rsi_display:.1f}")
            else:
                print(f"   📊 RSI(M1): N/A")
            if pd.notna(rsi_m5_display):
                print(f"   📊 RSI(14)_M5: {rsi_m5_display:.1f}")
            else:
                print(f"   📊 RSI(14)_M5: N/A")
            if pd.notna(current_adx_display):
                print(f"   📊 ADX: {current_adx_display:.1f}")
            else:
                print(f"   📊 ADX: N/A")
            if pd.notna(atr_val):
                symbol_upper = symbol.upper()
                if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                    print(f"   📊 ATR: {atr_val:.2f} USD")
                elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                    print(f"   📊 ATR: {atr_val:.2f} USD")
                else:
                    print(f"   📊 ATR: {atr_val:.5f}")
                    print(f"   📊 ATR Pips: {(atr_val / 0.0001):.1f} pips")
            else:
                print(f"   📊 ATR: N/A")
            
            print(f"\n{'='*80}\n")
            return error_count, 0
        
        # --- 8. Calculate SL and TP ---
        # Entry: Close của nến phá vỡ trendline (đã set ở trên)
        # SL = 2ATR + 6 point, TP = 2SL
        sl_distance = (2 * atr_val) + (6 * point)
        tp_distance = 2 * sl_distance
        
        if signal_type == "BUY":
            sl = current_price - sl_distance
            tp = current_price + tp_distance
        else:  # SELL
            sl = current_price + sl_distance
            tp = current_price - tp_distance
        
        # Normalize to symbol digits
        digits = symbol_info.digits
        current_price = round(current_price, digits)
        sl = round(sl, digits)
        tp = round(tp, digits)
        
        # --- 8b. Calculate lot size based on risk management (if enabled) ---
        use_risk_based_lot = config.get('use_risk_based_lot', False)  # Default: OFF
        if use_risk_based_lot:
            # Get account balance
            account_info = mt5.account_info()
            if account_info is None:
                print("   ⚠️ Không thể lấy account balance, sử dụng volume từ config")
            else:
                account_balance = account_info.balance
                risk_percent = config.get('risk_percent', 1.0)  # Default 1%
                
                # Calculate SL in pips
                # Determine pip size
                symbol_upper = symbol.upper()
                if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                    pip_size = 0.1 if point < 0.01 else point
                elif 'JPY' in symbol_upper:
                    pip_size = 0.01
                else:
                    pip_size = 0.0001
                
                sl_pips = abs(sl_distance / pip_size)
                
                # Calculate lot size
                calculated_volume = calculate_lot_size(
                    account_balance, 
                    risk_percent, 
                    sl_pips, 
                    symbol, 
                    symbol_info
                )
                
                # Use calculated volume if valid
                if calculated_volume > 0:
                    volume = calculated_volume
                    log_details.append(f"\n💰 [Risk-Based Lot Calculation]")
                    log_details.append(f"   Account Balance: ${account_balance:.2f}")
                    log_details.append(f"   Risk Percent: {risk_percent}%")
                    log_details.append(f"   Risk Money: ${account_balance * (risk_percent / 100.0):.2f}")
                    log_details.append(f"   SL Distance: {sl_distance:.5f} ({sl_pips:.1f} pips)")
                    log_details.append(f"   Calculated Lot: {volume:.2f}")
                else:
                    print("   ⚠️ Calculated lot size invalid, sử dụng volume từ config")
        
        # Get current market price for order execution
        tick = mt5.symbol_info_tick(symbol)
        if signal_type == "BUY":
            execution_price = tick.ask
        else:  # SELL
            execution_price = tick.bid
        
        # --- 9. Spam Filter (60s) ---
        # Chỉ kiểm tra positions do bot này mở (theo magic number)
        all_strat_positions = mt5.positions_get(symbol=symbol)
        strat_positions = [pos for pos in (all_strat_positions or []) if pos.magic == magic]
        if strat_positions:
            strat_positions = sorted(strat_positions, key=lambda x: x.time, reverse=True)
            tick = mt5.symbol_info_tick(symbol)
            if (tick.time - strat_positions[0].time) < 60:
                print("   ⏳ Trade taken recently. Waiting.")
                return error_count, 0
        
        # --- 10. Print Log Details ---
        print(f"\n{'='*80}")
        print(f"🚀 [M1 SCALP SIGNAL] {signal_type} @ {current_price:.5f}")
        print(f"{'='*80}")
        for detail in log_details:
            print(f"   {detail}")
        print(f"\n   💰 [Risk Management]")
        print(f"   🛑 SL: {sl:.5f} (2ATR + 6pt = {sl_distance:.5f})")
        print(f"   🎯 TP: {tp:.5f} (2SL = {tp_distance:.5f})")
        print(f"   📊 Volume: {volume:.2f} lot")
        print(f"{'='*80}\n")
        
        # --- 11. Send Order ---
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal_type == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": execution_price,  # Use current market price for execution
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        # Pre-order validation
        if not mt5.terminal_info():
            error_msg = "MT5 Terminal không kết nối"
            print(f"❌ {error_msg}")
            log_to_file(symbol, "ERROR", f"MT5 Terminal không kết nối")
            telegram_sent = send_telegram(
                f"❌ <b>M1 Scalp Bot - Lỗi</b>\n{error_msg}",
                config.get('telegram_token'),
                config.get('telegram_chat_id'),
                symbol=symbol
            )
            if not telegram_sent:
                print(f"⚠️ Không thể gửi thông báo Telegram lỗi.")
                # Log Telegram error to file
                log_to_file(symbol, "TELEGRAM_ERROR", f"Không thể gửi thông báo Telegram lỗi: {error_msg}")
            return error_count + 1, 0
        
        if symbol_info.visible == False:
            error_msg = f"Symbol {symbol} không khả dụng"
            print(f"❌ {error_msg}")
            return error_count + 1, 0
        
        # Check stops_level
        stops_level = symbol_info.trade_stops_level
        if stops_level > 0:
            if signal_type == "BUY":
                if abs(execution_price - sl) < stops_level * point:
                    error_msg = f"SL quá gần (cần >= {stops_level} points)"
                    print(f"❌ {error_msg}")
                    return error_count + 1, 0
            else:  # SELL
                if abs(sl - execution_price) < stops_level * point:
                    error_msg = f"SL quá gần (cần >= {stops_level} points)"
                    print(f"❌ {error_msg}")
                    return error_count + 1, 0
        
        # Check account balance and margin before sending order
        account_info = mt5.account_info()
        if account_info:
            account_balance = account_info.balance
            account_equity = account_info.equity
            account_margin = account_info.margin
            account_free_margin = account_info.margin_free
            
            print(f"   💰 Account Balance: ${account_balance:.2f}")
            print(f"   💰 Account Equity: ${account_equity:.2f}")
            print(f"   💰 Used Margin: ${account_margin:.2f}")
            print(f"   💰 Free Margin: ${account_free_margin:.2f}")
        
        # Validate order
        print(f"   🔍 Đang validate request...")
        check_result = mt5.order_check(request)
        if check_result is None:
            error = mt5.last_error()
            print(f"   ⚠️ order_check() trả về None. Lỗi: {error}")
            print(f"   ⚠️ Vẫn thử gửi lệnh...")
        elif hasattr(check_result, 'retcode') and check_result.retcode != 0:
            # Improved error handling for "No money" error
            retcode = check_result.retcode
            error_comment = check_result.comment if hasattr(check_result, 'comment') else 'Unknown'
            
            if retcode == 10019:  # TRADE_RETCODE_NO_MONEY
                error_msg = "Không đủ tiền trong tài khoản (No Money)"
                error_detail = f"{error_comment} (Retcode: {retcode})"
                
                # Get account info for detailed error message
                account_info = mt5.account_info()
                if account_info:
                    account_balance = account_info.balance
                    account_equity = account_info.equity
                    account_margin = account_info.margin
                    account_free_margin = account_info.margin_free
                    
                    error_detail += f"\n💰 Balance: ${account_balance:.2f}"
                    error_detail += f"\n💰 Equity: ${account_equity:.2f}"
                    error_detail += f"\n💰 Used Margin: ${account_margin:.2f}"
                    error_detail += f"\n💰 Free Margin: ${account_free_margin:.2f}"
                    error_detail += f"\n📊 Volume yêu cầu: {volume:.2f} lot"
                    error_detail += f"\n💵 Entry Price: {execution_price:.5f}"
                    error_detail += f"\n🛑 SL: {sl:.5f} | 🎯 TP: {tp:.5f}"
            else:
                error_msg = f"order_check() không hợp lệ"
                error_detail = f"{error_comment} (Retcode: {retcode})"
            
            print(f"   ❌ {error_msg}: {error_detail}")
            
            # Lấy account_info nếu chưa có (cho các lỗi khác ngoài 10019)
            if retcode != 10019:
                account_info = mt5.account_info()
                if account_info:
                    account_balance = account_info.balance
                    account_equity = account_info.equity
                    account_margin = account_info.margin
                    account_free_margin = account_info.margin_free
            
            # Log chi tiết thông tin lệnh bị lỗi vào file
            error_log_detail = f"order_check() không hợp lệ: {error_detail}\n"
            error_log_detail += f"📋 Chi tiết lệnh bị lỗi:\n"
            error_log_detail += f"   • Signal Type: {signal_type}\n"
            error_log_detail += f"   • Symbol: {symbol}\n"
            error_log_detail += f"   • Volume: {volume:.2f} lot\n"
            error_log_detail += f"   • Entry Price: {execution_price:.5f}\n"
            error_log_detail += f"   • SL: {sl:.5f}\n"
            error_log_detail += f"   • TP: {tp:.5f}\n"
            if account_info:
                error_log_detail += f"   • Account Balance: ${account_balance:.2f}\n"
                error_log_detail += f"   • Account Equity: ${account_equity:.2f}\n"
                error_log_detail += f"   • Used Margin: ${account_margin:.2f}\n"
                error_log_detail += f"   • Free Margin: ${account_free_margin:.2f}\n"
            error_log_detail += f"   • Retcode: {retcode}\n"
            error_log_detail += f"   • Error Comment: {error_comment}"
            log_to_file(symbol, "ERROR", error_log_detail)
            
            # Enhanced Telegram message for "No money" error
            telegram_msg = f"❌ <b>M1 Scalp Bot - Lỗi Gửi Lệnh</b>\n"
            telegram_msg += f"💱 Symbol: {symbol} ({signal_type})\n"
            telegram_msg += f"❌ Lỗi: {error_msg}\n"
            telegram_msg += f"📝 Chi tiết: {error_detail}"
            
            telegram_sent = send_telegram(
                telegram_msg,
                config.get('telegram_token'),
                config.get('telegram_chat_id'),
                symbol=symbol
            )
            if not telegram_sent:
                print(f"⚠️ Không thể gửi thông báo Telegram lỗi.")
                # Log Telegram error to file
                log_to_file(symbol, "TELEGRAM_ERROR", f"Không thể gửi thông báo Telegram lỗi: {error_msg} - {error_detail}")
            return error_count + 1, retcode
        else:
            print(f"   ✅ Request hợp lệ")
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(result.order, "M1_Scalp_XAUUSD", symbol, signal_type, volume, current_price, sl, tp, reason, account_id=config.get('account'))
            
            # Log to file: SIGNAL
            signal_log_content = (
                f"✅ {signal_type} SIGNAL - Ticket: {result.order} | "
                f"Entry: {current_price:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | "
                f"Volume: {volume:.2f} lot | ATR: {atr_val:.5f}"
            )
            log_to_file(symbol, "SIGNAL", signal_log_content)
            
            # Detailed Telegram Message
            msg_parts = []
            msg_parts.append(f"✅ <b>M1 Scalp Bot - Lệnh Đã Được Thực Hiện</b>\n")
            msg_parts.append(f"{'='*50}\n")
            msg_parts.append(f"🆔 <b>Ticket:</b> {result.order}\n")
            msg_parts.append(f"💱 <b>Symbol:</b> {symbol} ({signal_type})\n")
            msg_parts.append(f"💵 <b>Entry Price:</b> {current_price:.5f} (Close của nến phá vỡ)\n")
            msg_parts.append(f"🛑 <b>SL:</b> {sl:.5f} (2ATR + 6pt = {sl_distance:.5f})\n")
            msg_parts.append(f"🎯 <b>TP:</b> {tp:.5f} (2SL = {tp_distance:.5f})\n")
            msg_parts.append(f"📊 <b>Volume:</b> {volume:.2f} lot")
            use_risk_based_lot = config.get('use_risk_based_lot', False)
            if use_risk_based_lot:
                msg_parts.append(f" (Risk-Based)\n")
            else:
                msg_parts.append(f"\n")
            msg_parts.append(f"\n")
            msg_parts.append(f"📈 <b>Điều Kiện Đã Thỏa:</b>\n")
            for detail in log_details:
                # Remove ✅ emoji for Telegram
                clean_detail = detail.replace("✅ ", "").replace("   ", "   • ")
                msg_parts.append(f"{clean_detail}\n")
            msg_parts.append(f"\n")
            msg_parts.append(f"📊 <b>Indicators:</b>\n")
            msg_parts.append(f"   • EMA50: {ema50_val:.5f}\n")
            msg_parts.append(f"   • EMA200: {ema200_val:.5f}\n")
            current_rsi_val = curr_candle.get('rsi', 0)
            if pd.notna(current_rsi_val):
                msg_parts.append(f"   • RSI(M1): {current_rsi_val:.1f}\n")
            rsi_m5_val = df_m5['rsi'].iloc[-2] if len(df_m5) >= 2 else None
            if pd.notna(rsi_m5_val):
                msg_parts.append(f"   • RSI(14)_M5: {rsi_m5_val:.1f}\n")
            current_adx_val = curr_candle.get('adx', None)
            if pd.notna(current_adx_val):
                msg_parts.append(f"   • ADX: {current_adx_val:.1f}\n")
            msg_parts.append(f"   • ATR: {atr_val:.5f}\n")
            msg_parts.append(f"\n")
            msg_parts.append(f"{'='*50}\n")
            msg_parts.append(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            msg = "".join(msg_parts)
            telegram_sent = send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'), symbol=symbol)
            if not telegram_sent:
                print(f"⚠️ Không thể gửi thông báo Telegram. Kiểm tra token và chat_id trong config.")
                # Log Telegram error to file
                log_to_file(symbol, "TELEGRAM_ERROR", f"Không thể gửi thông báo Telegram cho signal {signal_type} - Ticket: {result.order}")
            return 0, 0
        else:
            error_msg = f"Order Failed: Retcode {result.retcode}"
            error_detail = f"{result.comment if hasattr(result, 'comment') else 'Unknown error'}"
            print(f"❌ {error_msg} - {error_detail}")
            
            # Log to file: ERROR
            error_log_content = (
                f"❌ ORDER ERROR - {signal_type} | "
                f"Entry: {current_price:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | "
                f"Error: {error_msg} | Detail: {error_detail}"
            )
            log_to_file(symbol, "ERROR", error_log_content)
            
            telegram_sent = send_telegram(
                f"❌ <b>M1 Scalp Bot - Lỗi Gửi Lệnh</b>\n"
                f"💱 Symbol: {symbol} ({signal_type})\n"
                f"💵 Entry: {current_price:.5f}\n"
                f"🛑 SL: {sl:.5f} | 🎯 TP: {tp:.5f}\n"
                f"❌ Lỗi: {error_msg}\n"
                f"📝 Chi tiết: {error_detail}",
                config.get('telegram_token'),
                config.get('telegram_chat_id'),
                symbol=symbol
            )
            if not telegram_sent:
                print(f"⚠️ Không thể gửi thông báo Telegram lỗi.")
            return error_count + 1, result.retcode
        
    except Exception as e:
        error_msg = f"❌ Lỗi trong m1_scalp_logic: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        
        # Log to file: ERROR
        symbol = config.get('symbol', 'UNKNOWN')
        log_to_file(symbol, "ERROR", f"Exception trong m1_scalp_logic: {str(e)}")
        
        return error_count + 1, 0

def log_initial_conditions(config):
    """
    Log tất cả các điều kiện và parameters của bot trước khi bắt đầu chạy
    """
    print("\n" + "="*100)
    print("📋 [CHI TIẾT ĐIỀU KIỆN VÀ THAM SỐ CỦA BOT - M1 SCALP]")
    print("="*100)
    
    # Basic Config
    print("\n🔧 [CẤU HÌNH CƠ BẢN]")
    print(f"   💱 Symbol: {config.get('symbol', 'N/A')}")
    print(f"   📊 Volume: {config.get('volume', 'N/A')} lot")
    use_risk_based_lot = config.get('use_risk_based_lot', False)
    print(f"   💰 Use Risk-Based Lot: {use_risk_based_lot} (Default: OFF)")
    if use_risk_based_lot:
        risk_percent = config.get('risk_percent', 1.0)
        print(f"   📊 Risk Percent: {risk_percent}%")
    print(f"   🆔 Magic Number: {config.get('magic', 'N/A')}")
    print(f"   📈 Max Positions: {config.get('max_positions', 1)}")
    
    # ATR Condition
    print("\n📊 [ĐIỀU KIỆN ATR]")
    symbol = config.get('symbol', 'EURUSD')
    min_atr = get_min_atr_threshold(symbol, config)
    symbol_upper = symbol.upper()
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        print(f"   ✅ ATR 14 >= {min_atr} USD (cho XAUUSD)")
    elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
        print(f"   ✅ ATR 14 >= {min_atr} USD (cho BTCUSD)")
    else:
        print(f"   ✅ ATR 14 >= {min_atr} (1.1 pips cho Forex)")
    print(f"   ⚠️ Nếu ATR < {min_atr}, bot sẽ không có signal")
    
    # BUY Strategy Conditions
    print("\n📈 [CHIẾN LƯỢC BUY]")
    print("   ✅ Điều kiện 1: EMA50 > EMA200")
    print("   ✅ Điều kiện 2: Giá phá vỡ đỉnh trước đó tạo Swing High với RSI > 70")
    print("   ✅ Điều kiện 3: Sóng hồi hợp lệ (Pullback hợp lệ)")
    print("      A. Swing high hợp lệ:")
    print("         - UpperWick < 1.3 ATR tại vùng swing high (±2 nến = 5 nến tổng)")
    print("         - Nếu UpperWick ≥ 1.3 ATR → bỏ cả con sóng hồi")
    print("      B. Slope Pullback giảm:")
    print("         - 18 ≤ Slope_Pullback_Down ≤ 48 → Pullback hợp lệ, tiếp tục điều kiện 4")
    print("         - 48 < Slope_Pullback_Down ≤ 62 → Pullback hơi dốc, KHÔNG ENTRY NGAY")
    print("           → Cần cấu trúc hồi rõ ràng (đáy - đỉnh) và vẽ lại trendline")
    print("         - Slope_Pullback_Down > 62 → Pullback quá mạnh, loại bỏ toàn bộ sóng hồi")
    print("      Công thức: Slope = (max(High_Pre[3] ∪ High_PB[1]) - min(Low_PB[1..6])) / Σ(ATR_14,i)")
    symbol = config.get('symbol', 'EURUSD')
    min_atr = get_min_atr_threshold(symbol, config)
    symbol_upper = symbol.upper()
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        print(f"   ✅ Điều kiện 4: Sóng hồi hợp lệ (Pullback hợp lệ)")
        print(f"      - ATR 14 >= {min_atr} USD (cho XAUUSD)")
        print(f"      - Trong toàn bộ sóng hồi (từ swing high đến trước nến phá trendline)")
        print(f"        không tồn tại bất kỳ nến nào có UpperWick ≥ 1.3 ATR")
    elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
        print(f"   ✅ Điều kiện 4: Sóng hồi hợp lệ (Pullback hợp lệ)")
        print(f"      - ATR 14 >= {min_atr} USD (cho BTCUSD)")
        print(f"      - Trong toàn bộ sóng hồi (từ swing high đến trước nến phá trendline)")
        print(f"        không tồn tại bất kỳ nến nào có UpperWick ≥ 1.3 ATR")
    else:
        print(f"   ✅ Điều kiện 4: Sóng hồi hợp lệ (Pullback hợp lệ)")
        print(f"      - ATR 14 >= {min_atr} (cho Forex)")
        print(f"      - Trong toàn bộ sóng hồi (từ swing high đến trước nến phá trendline)")
        print(f"        không tồn tại bất kỳ nến nào có UpperWick ≥ 1.3 ATR")
    print("   ✅ Điều kiện 5: Nến xác nhận phá vỡ trendline")
    print("      - Giá đóng cửa vượt lên trên trendline sóng hồi")
    print("      - Giá đóng cửa ≥ EMA 50")
    print("      - RSI đang hướng lên (RSI hiện tại > RSI nến trước)")
    print("      - ADX ≥ 18 (Nến xác nhận)")
    print("   ✅ Điều kiện 6: Không có Bearish Divergence")
    print("      - Giá không tạo Higher High với RSI Lower High")
    print("   ✅ Điều kiện 7: RSI(14)_M5 >= 55 và <= 65")
    print("      - RSI trên khung thời gian M5 phải nằm trong khoảng 55-65")
    print("   🎯 Entry: Giá đóng cửa của nến phá vỡ trendline")
    
    # SELL Strategy Conditions
    print("\n📉 [CHIẾN LƯỢC SELL]")
    print("   ✅ Điều kiện 1: EMA50 < EMA200")
    print("   ✅ Điều kiện 2: Giá phá vỡ đáy trước đó tạo Swing Low với RSI < 30")
    print("   ✅ Điều kiện 3: Sóng hồi hợp lệ (Pullback hợp lệ)")
    print("      A. Swing low hợp lệ:")
    print("         - LowerWick < 1.3 ATR tại vùng swing low (±2 nến = 5 nến tổng)")
    print("         - Nếu LowerWick ≥ 1.3 ATR → bỏ cả con sóng hồi")
    print("      B. Slope Pullback tăng:")
    print("         - 18 ≤ Slope_Pullback_Up ≤ 48 → Pullback hợp lệ, tiếp tục điều kiện 4")
    print("         - 48 < Slope_Pullback_Up ≤ 62 → Pullback hơi dốc, KHÔNG ENTRY NGAY")
    print("           → Cần cấu trúc hồi rõ ràng (đỉnh - đáy) và vẽ lại trendline")
    print("         - Slope_Pullback_Up > 62 → Pullback quá mạnh, loại bỏ toàn bộ sóng hồi")
    print("      Công thức: Slope = (max(High_PB[1..6]) - min(Low_Pre[3] ∪ Low_PB[1])) / Σ(ATR_14,i)")
    symbol = config.get('symbol', 'EURUSD')
    min_atr = get_min_atr_threshold(symbol, config)
    symbol_upper = symbol.upper()
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        print(f"   ✅ Điều kiện 4: Sóng hồi hợp lệ (Pullback hợp lệ)")
        print(f"      - ATR 14 >= {min_atr} USD (cho XAUUSD)")
        print(f"      - Trong toàn bộ sóng hồi (từ swing low đến trước nến phá trendline)")
        print(f"        không tồn tại bất kỳ nến nào có LowerWick ≥ 1.3 ATR")
    elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
        print(f"   ✅ Điều kiện 4: Sóng hồi hợp lệ (Pullback hợp lệ)")
        print(f"      - ATR 14 >= {min_atr} USD (cho BTCUSD)")
        print(f"      - Trong toàn bộ sóng hồi (từ swing low đến trước nến phá trendline)")
        print(f"        không tồn tại bất kỳ nến nào có LowerWick ≥ 1.3 ATR")
    else:
        print(f"   ✅ Điều kiện 4: Sóng hồi hợp lệ (Pullback hợp lệ)")
        print(f"      - ATR 14 >= {min_atr} (cho Forex)")
        print(f"      - Trong toàn bộ sóng hồi (từ swing low đến trước nến phá trendline)")
        print(f"        không tồn tại bất kỳ nến nào có LowerWick ≥ 1.3 ATR")
    print("   ✅ Điều kiện 5: Nến xác nhận phá vỡ trendline")
    print("      - Giá đóng cửa phá xuống dưới trendline sóng hồi")
    print("      - Giá đóng cửa ≤ EMA 50")
    print("      - RSI đang hướng xuống (RSI hiện tại < RSI nến trước)")
    print("      - ADX ≥ 18 (Nến xác nhận)")
    print("   ✅ Điều kiện 6: Không có Bullish Divergence")
    print("      - Giá không tạo Lower Low với RSI Higher Low")
    print("   ✅ Điều kiện 7: RSI(14)_M5 >= 35 và <= 45")
    print("      - RSI trên khung thời gian M5 phải nằm trong khoảng 35-45")
    print("   🎯 Entry: Giá đóng cửa của nến phá vỡ trendline")
    
    # SL/TP Calculation
    print("\n🎯 [TÍNH TOÁN SL/TP]")
    print("   🛑 SL = 2 × ATR + 6 × point")
    print("   🎯 TP = 2 × SL distance")
    print("   📊 R:R Ratio = 1:2")
    
    # Spam Filter
    print("\n⏱️ [SPAM FILTER]")
    print("   ⏳ Cooldown: 60 giây giữa các lệnh")
    
    # Position Management
    print("\n📊 [QUẢN LÝ VỊ THẾ]")
    print(f"   📈 Max Positions: {config.get('max_positions', 1)}")
    print("   🔄 Auto Trailing SL: Enabled (nếu có)")
    
    # Swing Detection Parameters
    print("\n🔍 [THAM SỐ PHÁT HIỆN SWING]")
    print("   📊 Swing High Lookback: 5 nến")
    print("   📊 Swing High Min RSI: 70")
    print("   📊 Swing Low Lookback: 5 nến")
    print("   📊 Swing Low Max RSI: 30")
    
    # Pullback Parameters
    print("\n📉 [THAM SỐ SÓNG HỒI]")
    print("   📊 Max Pullback Candles: 30 nến")
    print("   📊 BUY Pullback RSI Target: 40-50")
    print("   📊 BUY Pullback Min RSI During: > 32")
    print("   📊 SELL Pullback RSI Target: 50-60")
    print("   📊 SELL Pullback Max RSI During: < 68")
    
    print("\n" + "="*100)
    print("⏳ Đang chờ 20 giây trước khi bắt đầu...")
    print("="*100 + "\n")

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_tuyen_xau.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    if config and connect_mt5(config):
        print("\n" + "="*80)
        print(f"✅ M1 Scalp Bot - Started")
        print(f"💱 Symbol: {config.get('symbol', 'N/A')}")
        print(f"📊 Volume: {config.get('volume', 'N/A')}")
        print("="*80 + "\n")
        
        try:
            # Verify MT5 connection is still active
            if not mt5.terminal_info():
                print("❌ MT5 Terminal không còn kết nối sau khi khởi động")
                sys.exit(1)
            
            # Test Telegram connection
            print("\n📤 [Telegram] Đang kiểm tra kết nối Telegram...")
            test_msg = f"✅ <b>M1 Scalp Bot - XAUUSD</b>\n\nBot đã khởi động thành công!\n💱 Symbol: {config.get('symbol', 'N/A')}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            telegram_ok = send_telegram(test_msg, config.get('telegram_token'), config.get('telegram_chat_id'), symbol=config.get('symbol'))
            if telegram_ok:
                print("✅ [Telegram] Kết nối Telegram thành công!")
            else:
                print("⚠️ [Telegram] Không thể gửi thông báo test. Kiểm tra lại token và chat_id trong config.")
            
            # Log tất cả điều kiện trước khi bắt đầu
            log_initial_conditions(config)
            
            # Sleep 20 giây
            for i in range(20, 0, -1):
                print(f"   ⏳ Còn {i} giây...", end='\r')
                time.sleep(1)
            print("\n")
            
            print("🔄 Bắt đầu vòng lặp chính...\n")
            
            loop_count = 0
            last_debug_log_time = 0
            while True:
                try:
                    loop_count += 1
                    if loop_count % 60 == 0:  # Print every 60 iterations (~1 minute)
                        print(f"⏳ Bot đang chạy... (vòng lặp #{loop_count})")
                    
                    # Log debug indicators mỗi 1 phút (60 giây)
                    current_time = time.time()
                    if current_time - last_debug_log_time >= 60:
                        try:
                            # Fetch data for debug logging
                            symbol = config.get('symbol')
                            df_m1_debug = get_data(symbol, mt5.TIMEFRAME_M1, 300)
                            df_m5_debug = get_data(symbol, mt5.TIMEFRAME_M5, 100)
                            
                            if df_m1_debug is not None:
                                # Calculate indicators for debug
                                df_m1_debug['ema50'] = calculate_ema(df_m1_debug['close'], 50)
                                df_m1_debug['ema200'] = calculate_ema(df_m1_debug['close'], 200)
                                df_m1_debug['atr'] = calculate_atr(df_m1_debug, 14)
                                df_m1_debug['rsi'] = calculate_rsi(df_m1_debug['close'], 14)
                                df_m1_debug = calculate_adx(df_m1_debug, period=14)
                                df_m1_debug['vol_ma'] = df_m1_debug['tick_volume'].rolling(window=10).mean()
                                
                                if df_m5_debug is not None:
                                    df_m5_debug['rsi'] = calculate_rsi(df_m5_debug['close'], 14)
                                
                                # Log debug indicators
                                from utils import log_debug_indicators
                                result = log_debug_indicators(symbol, df_m1_debug, df_m5_debug, config)
                                last_debug_log_time = current_time
                        except Exception as e:
                            print(f"⚠️ Lỗi khi log debug indicators: {e}")
                    
                    consecutive_errors, last_error = m1_scalp_logic(config, consecutive_errors)
                    if consecutive_errors >= 5:
                        print("⚠️ Too many errors. Pausing...")
                        time.sleep(120)
                        consecutive_errors = 0
                    time.sleep(1)
                except Exception as e:
                    print(f"❌ Lỗi trong m1_scalp_logic: {e}")
                    import traceback
                    traceback.print_exc()
                    consecutive_errors += 1
                    if consecutive_errors >= 5:
                        print("⚠️ Too many errors. Pausing...")
                        time.sleep(120)
                        consecutive_errors = 0
                    time.sleep(5)  # Wait longer on error
        except KeyboardInterrupt:
            print("\n\n⚠️ Bot stopped by user")
            mt5.shutdown()
        except Exception as e:
            print(f"\n❌ Lỗi nghiêm trọng trong bot: {e}")
            import traceback
            traceback.print_exc()
            mt5.shutdown()
            sys.exit(1)
    else:
        print("❌ Không thể kết nối MT5. Vui lòng kiểm tra lại.")
        sys.exit(1)

