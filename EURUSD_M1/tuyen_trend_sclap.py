import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# Import local modules
sys.path.append('..') 
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message, calculate_rsi

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

def check_valid_pullback_buy(df_m1, swing_high_idx, max_candles=30, rsi_target_min=40, rsi_target_max=50, rsi_min_during_pullback=32):
    """
    Kiểm tra sóng hồi hợp lệ cho BUY:
    - Giá không tạo đỉnh cao hơn swing high
    - Số nến hồi tối đa: ≤ max_candles (default 30)
    - RSI hồi về vùng rsi_target_min - rsi_target_max (default 40-50)
    - Trong quá trình hồi: RSI > rsi_min_during_pullback (default 32)
    - Giá không phá cấu trúc xu hướng tăng chính
    
    Returns: (is_valid, pullback_end_idx, pullback_candles, message)
    """
    if swing_high_idx >= len(df_m1) - 1:
        return False, None, None, "Swing high quá gần cuối"
    
    swing_high_price = df_m1.iloc[swing_high_idx]['high']
    
    # Tìm điểm kết thúc sóng hồi (từ swing high đến hiện tại hoặc max_candles)
    pullback_start = swing_high_idx + 1
    pullback_end = min(pullback_start + max_candles, len(df_m1) - 1)
    
    pullback_candles = df_m1.iloc[pullback_start:pullback_end + 1]
    
    if len(pullback_candles) == 0:
        return False, None, None, "Không có nến sau swing high"
    
    # 1. Kiểm tra: Giá không tạo đỉnh cao hơn swing high
    max_high_after_swing = pullback_candles['high'].max()
    if max_high_after_swing > swing_high_price:
        return False, None, None, f"Giá tạo đỉnh cao hơn swing high: {max_high_after_swing:.5f} > {swing_high_price:.5f}"
    
    # 2. Kiểm tra số nến hồi ≤ max_candles
    if len(pullback_candles) > max_candles:
        return False, None, None, f"Số nến hồi ({len(pullback_candles)}) > {max_candles}"
    
    # 3. Kiểm tra RSI trong quá trình hồi > rsi_min_during_pullback
    pullback_rsi = pullback_candles.get('rsi', pd.Series())
    if len(pullback_rsi) > 0:
        min_rsi_during_pullback = pullback_rsi.min()
        if min_rsi_during_pullback <= rsi_min_during_pullback:
            return False, None, None, f"RSI trong quá trình hồi ({min_rsi_during_pullback:.1f}) <= {rsi_min_during_pullback}"
    
    # 4. Kiểm tra RSI hồi về vùng target (40-50) - kiểm tra nến cuối hoặc gần cuối
    last_rsi = pullback_candles.iloc[-1].get('rsi', None)
    if pd.notna(last_rsi):
        if not (rsi_target_min <= last_rsi <= rsi_target_max):
            # Có thể RSI chưa về vùng target nhưng vẫn đang hồi
            # Kiểm tra xem có nến nào trong vùng target không
            rsi_in_target = pullback_rsi[(pullback_rsi >= rsi_target_min) & (pullback_rsi <= rsi_target_max)]
            if len(rsi_in_target) == 0:
                return False, None, None, f"RSI không hồi về vùng {rsi_target_min}-{rsi_target_max} (hiện tại: {last_rsi:.1f})"
    
    # 5. Kiểm tra giá không phá cấu trúc xu hướng tăng (kiểm tra Lower Lows)
    if swing_high_idx > 10:
        before_swing = df_m1.iloc[swing_high_idx - 20:swing_high_idx]
        if len(before_swing) > 0:
            prev_swing_low = before_swing['low'].min()
            pullback_low = pullback_candles['low'].min()
            if pullback_low < prev_swing_low * 0.9999:  # 0.1 pip buffer
                return False, None, None, f"Giá phá cấu trúc: Pullback low {pullback_low:.5f} < Prev swing low {prev_swing_low:.5f}"
    
    pullback_end_idx = pullback_end
    
    return True, pullback_end_idx, pullback_candles, "Sóng hồi hợp lệ"

def check_valid_pullback_sell(df_m1, swing_low_idx, max_candles=30, rsi_target_min=50, rsi_target_max=60, rsi_max_during_pullback=68):
    """
    Kiểm tra sóng hồi hợp lệ cho SELL:
    - Giá không tạo đáy thấp hơn swing low
    - Số nến hồi tối đa: ≤ max_candles (default 30)
    - RSI hồi về vùng rsi_target_min - rsi_target_max (default 50-60)
    - Trong quá trình hồi: RSI < rsi_max_during_pullback (default 68)
    - Giá không phá cấu trúc xu hướng giảm chính
    
    Returns: (is_valid, pullback_end_idx, pullback_candles, message)
    """
    if swing_low_idx >= len(df_m1) - 1:
        return False, None, None, "Swing low quá gần cuối"
    
    swing_low_price = df_m1.iloc[swing_low_idx]['low']
    
    # Tìm điểm kết thúc sóng hồi (từ swing low đến hiện tại hoặc max_candles)
    pullback_start = swing_low_idx + 1
    pullback_end = min(pullback_start + max_candles, len(df_m1) - 1)
    
    pullback_candles = df_m1.iloc[pullback_start:pullback_end + 1]
    
    if len(pullback_candles) == 0:
        return False, None, None, "Không có nến sau swing low"
    
    # 1. Kiểm tra: Giá không tạo đáy thấp hơn swing low
    min_low_after_swing = pullback_candles['low'].min()
    if min_low_after_swing < swing_low_price:
        return False, None, None, f"Giá tạo đáy thấp hơn swing low: {min_low_after_swing:.5f} < {swing_low_price:.5f}"
    
    # 2. Kiểm tra số nến hồi ≤ max_candles
    if len(pullback_candles) > max_candles:
        return False, None, None, f"Số nến hồi ({len(pullback_candles)}) > {max_candles}"
    
    # 3. Kiểm tra RSI trong quá trình hồi < rsi_max_during_pullback
    pullback_rsi = pullback_candles.get('rsi', pd.Series())
    if len(pullback_rsi) > 0:
        max_rsi_during_pullback = pullback_rsi.max()
        if max_rsi_during_pullback >= rsi_max_during_pullback:
            return False, None, None, f"RSI trong quá trình hồi ({max_rsi_during_pullback:.1f}) >= {rsi_max_during_pullback}"
    
    # 4. Kiểm tra RSI hồi về vùng target (50-60) - kiểm tra nến cuối hoặc gần cuối
    last_rsi = pullback_candles.iloc[-1].get('rsi', None)
    if pd.notna(last_rsi):
        if not (rsi_target_min <= last_rsi <= rsi_target_max):
            # Có thể RSI chưa về vùng target nhưng vẫn đang hồi
            # Kiểm tra xem có nến nào trong vùng target không
            rsi_in_target = pullback_rsi[(pullback_rsi >= rsi_target_min) & (pullback_rsi <= rsi_target_max)]
            if len(rsi_in_target) == 0:
                return False, None, None, f"RSI không hồi về vùng {rsi_target_min}-{rsi_target_max} (hiện tại: {last_rsi:.1f})"
    
    # 5. Kiểm tra giá không phá cấu trúc xu hướng giảm (kiểm tra Higher Highs)
    if swing_low_idx > 10:
        before_swing = df_m1.iloc[swing_low_idx - 20:swing_low_idx]
        if len(before_swing) > 0:
            prev_swing_high = before_swing['high'].max()
            pullback_high = pullback_candles['high'].max()
            if pullback_high > prev_swing_high * 1.0001:  # 0.1 pip buffer
                return False, None, None, f"Giá phá cấu trúc: Pullback high {pullback_high:.5f} > Prev swing high {prev_swing_high:.5f}"
    
    pullback_end_idx = pullback_end
    
    return True, pullback_end_idx, pullback_candles, "Sóng hồi hợp lệ"

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
    
    # Tìm các đáy (local minima) trong pullback
    lows = pullback_candles['low'].values
    
    local_mins = []
    for i in range(1, len(lows) - 1):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            idx_in_df = pullback_candles.index[i]
            pos_in_df = df_m1.index.get_loc(idx_in_df) if hasattr(df_m1.index, 'get_loc') else i + swing_low_idx
            local_mins.append({'pos': pos_in_df, 'price': lows[i], 'idx': idx_in_df})
    
    # Thêm swing low vào đầu
    swing_low_pos = swing_low_idx
    swing_low_price = df_m1.iloc[swing_low_idx]['low']
    local_mins.insert(0, {'pos': swing_low_pos, 'price': swing_low_price, 'idx': df_m1.index[swing_low_idx] if hasattr(df_m1.index[swing_low_idx], '__iter__') else swing_low_idx})
    
    local_mins = sorted(local_mins, key=lambda x: x['pos'])
    
    # Lọc các đáy cao dần
    filtered_mins = [local_mins[0]]
    for i in range(1, len(local_mins)):
        if local_mins[i]['price'] >= filtered_mins[-1]['price']:
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
    
    return True, f"Break confirmed: Close {current_candle['close']:.5f} > Trendline {trendline_value:.5f}, Close >= EMA50 {ema50_val:.5f}, RSI rising {prev_rsi:.1f} -> {current_rsi:.1f}"

def check_trendline_break_sell(df_m1, trendline_info, current_candle_idx, ema50_val):
    """
    Kiểm tra nến phá vỡ trendline sóng hồi cho SELL:
    ✅ Giá đóng cửa phá xuống dưới trendline sóng hồi
    ✅ Giá đóng cửa ≤ EMA 50
    ✅ RSI đang hướng xuống (RSI hiện tại < RSI nến trước)
    
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
    
    return True, f"Break confirmed: Close {current_candle['close']:.5f} < Trendline {trendline_value:.5f}, Close <= EMA50 {ema50_val:.5f}, RSI declining {prev_rsi:.1f} -> {current_rsi:.1f}"

def m1_scalp_logic(config, error_count=0):
    """
    M1 Scalp Strategy Logic - Swing High/Low + Pullback + Trendline Break
    BUY: EMA50 > EMA200, Swing High với RSI > 70, Pullback hợp lệ, Trendline break, ATR ≥ 0.00011
    SELL: EMA50 < EMA200, Swing Low với RSI < 30, Pullback hợp lệ, Trendline break, ATR ≥ 0.00011
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

        # --- 3. Calculate Indicators ---
        df_m1['ema50'] = calculate_ema(df_m1['close'], 50)
        df_m1['ema200'] = calculate_ema(df_m1['close'], 200)
        df_m1['atr'] = calculate_atr(df_m1, 14)
        df_m1['rsi'] = calculate_rsi(df_m1['close'], 14)
        
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
        min_atr = 0.00011  # ATR 14 ≥ 0.00011
        atr_ok = pd.notna(atr_val) and atr_val >= min_atr
        
        signal_type = None
        reason = ""
        log_details = []
        
        # Log ATR condition
        log_details.append(f"{'='*80}")
        log_details.append(f"🔍 [ĐIỀU KIỆN CHUNG] Kiểm tra ATR...")
        log_details.append(f"{'='*80}")
        if atr_ok:
            atr_pips = atr_val / 0.0001
            log_details.append(f"✅ ĐK4 (Chung): ATR ({atr_pips:.1f} pips = {atr_val:.5f}) >= {min_atr:.5f}")
        else:
            if pd.isna(atr_val):
                log_details.append(f"❌ ĐK4 (Chung): ATR không có giá trị (NaN)")
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
        buy_fail_reason = ""
        
        # Track SELL conditions status
        sell_dk1_ok = False
        sell_dk2_ok = False
        sell_dk3_ok = False
        sell_dk3b_ok = False
        sell_dk4_ok = False
        sell_dk5_ok = False
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
                
                # Điều kiện 3: Kiểm tra sóng hồi hợp lệ
                log_details.append(f"\n🔍 [BUY] ĐK3: Kiểm tra sóng hồi hợp lệ")
                pullback_valid, pullback_end_idx, pullback_candles, pullback_msg = check_valid_pullback_buy(
                    df_m1, swing_high_idx, max_candles=30, rsi_target_min=40, rsi_target_max=50, rsi_min_during_pullback=32
                )
                
                if not pullback_valid:
                    log_details.append(f"   ❌ {pullback_msg}")
                    buy_fail_reason = f"ĐK3: {pullback_msg}"
                else:
                    buy_dk3_ok = True
                    log_details.append(f"   ✅ {pullback_msg}")
                    
                    # Vẽ trendline sóng hồi
                    log_details.append(f"\n🔍 [BUY] ĐK3b: Vẽ trendline sóng hồi")
                    trendline_info = calculate_pullback_trendline_buy(df_m1, swing_high_idx, pullback_end_idx)
                    
                    if trendline_info is None:
                        log_details.append(f"   ❌ Không thể vẽ trendline")
                        buy_fail_reason = "ĐK3b: Không thể vẽ trendline (không đủ đỉnh thấp dần)"
                    else:
                        buy_dk3b_ok = True
                        log_details.append(f"   ✅ Trendline đã vẽ: Slope={trendline_info['slope']:.8f}, Số điểm: {len(trendline_info['points'])}")
                        
                        # Điều kiện 4: ATR (đã check ở trên)
                        buy_dk4_ok = atr_ok
                        if not buy_dk4_ok:
                            if pd.notna(atr_val):
                                buy_fail_reason = f"ĐK4: ATR ({atr_val:.5f}) < 0.00011"
                            else:
                                buy_fail_reason = "ĐK4: ATR không có giá trị (NaN)"
                        
                        # Điều kiện 5: Nến xác nhận phá vỡ trendline
                        log_details.append(f"\n🔍 [BUY] ĐK5: Kiểm tra nến phá vỡ trendline")
                        break_ok, break_msg = check_trendline_break_buy(df_m1, trendline_info, current_candle_idx, ema50_val)
                        
                        if not break_ok:
                            log_details.append(f"   ❌ {break_msg}")
                            buy_fail_reason = f"ĐK5: {break_msg}"
                        else:
                            buy_dk5_ok = True
                            log_details.append(f"   ✅ {break_msg}")
                            
                            # Tất cả điều kiện đã thỏa (bao gồm ATR)
                            if buy_dk1_ok and buy_dk2_ok and buy_dk3_ok and buy_dk3b_ok and buy_dk4_ok and buy_dk5_ok:
                                signal_type = "BUY"
                                reason = "M1_Scalp_SwingHigh_Pullback_TrendlineBreak"
                                current_price = curr_candle['close']  # Entry tại close của nến phá vỡ
                                
                                log_details.append(f"\n🚀 [BUY SIGNAL] Tất cả điều kiện đã thỏa!")
                                log_details.append(f"   Entry: {current_price:.5f} (giá đóng cửa nến phá vỡ)")
                            else:
                                if not buy_dk4_ok:
                                    if pd.notna(atr_val):
                                        buy_fail_reason = f"ĐK4: ATR ({atr_val:.5f}) < 0.00011"
                                    else:
                                        buy_fail_reason = "ĐK4: ATR không có giá trị (NaN)"
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
                    
                    # Điều kiện 3: Kiểm tra sóng hồi hợp lệ
                    log_details.append(f"\n🔍 [SELL] ĐK3: Kiểm tra sóng hồi hợp lệ")
                    pullback_valid, pullback_end_idx, pullback_candles, pullback_msg = check_valid_pullback_sell(
                        df_m1, swing_low_idx, max_candles=30, rsi_target_min=50, rsi_target_max=60, rsi_max_during_pullback=68
                    )
                    
                    if not pullback_valid:
                        log_details.append(f"   ❌ {pullback_msg}")
                        sell_fail_reason = f"ĐK3: {pullback_msg}"
                    else:
                        sell_dk3_ok = True
                        log_details.append(f"   ✅ {pullback_msg}")
                        
                        # Vẽ trendline sóng hồi
                        log_details.append(f"\n🔍 [SELL] ĐK3b: Vẽ trendline sóng hồi")
                        trendline_info = calculate_pullback_trendline(df_m1, swing_low_idx, pullback_end_idx)
                        
                        if trendline_info is None:
                            log_details.append(f"   ❌ Không thể vẽ trendline")
                            sell_fail_reason = "ĐK3b: Không thể vẽ trendline (không đủ đáy cao dần)"
                        else:
                            sell_dk3b_ok = True
                            log_details.append(f"   ✅ Trendline đã vẽ: Slope={trendline_info['slope']:.8f}, Số điểm: {len(trendline_info['points'])}")
                            
                            # Điều kiện 4: ATR (đã check ở trên)
                            sell_dk4_ok = atr_ok
                            if not sell_dk4_ok:
                                if pd.notna(atr_val):
                                    sell_fail_reason = f"ĐK4: ATR ({atr_val:.5f}) < 0.00011"
                                else:
                                    sell_fail_reason = "ĐK4: ATR không có giá trị (NaN)"
                            
                            # Điều kiện 5: Nến xác nhận phá vỡ trendline
                            log_details.append(f"\n🔍 [SELL] ĐK5: Kiểm tra nến phá vỡ trendline")
                            break_ok, break_msg = check_trendline_break_sell(df_m1, trendline_info, current_candle_idx, ema50_val)
                            
                            if not break_ok:
                                log_details.append(f"   ❌ {break_msg}")
                                sell_fail_reason = f"ĐK5: {break_msg}"
                            else:
                                sell_dk5_ok = True
                                log_details.append(f"   ✅ {break_msg}")
                                
                                # Tất cả điều kiện đã thỏa (bao gồm ATR)
                                if sell_dk1_ok and sell_dk2_ok and sell_dk3_ok and sell_dk3b_ok and sell_dk4_ok and sell_dk5_ok:
                                    signal_type = "SELL"
                                    reason = "M1_Scalp_SwingLow_Pullback_TrendlineBreak"
                                    current_price = curr_candle['close']  # Entry tại close của nến phá vỡ
                                    
                                    log_details.append(f"\n🚀 [SELL SIGNAL] Tất cả điều kiện đã thỏa!")
                                    log_details.append(f"   Entry: {current_price:.5f} (giá đóng cửa nến phá vỡ)")
                                else:
                                    if not sell_dk4_ok:
                                        if pd.notna(atr_val):
                                            sell_fail_reason = f"ĐK4: ATR ({atr_val:.5f}) < 0.00011"
                                        else:
                                            sell_fail_reason = "ĐK4: ATR không có giá trị (NaN)"
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
                    atr_pips = atr_val / 0.0001
                    print(f"   ❌ ĐK4 (Chung): ATR ({atr_pips:.1f} pips = {atr_val:.5f}) < {min_atr:.5f}")
                else:
                    print(f"   ❌ ĐK4 (Chung): ATR (N/A pips = N/A) < {min_atr:.5f}")
            
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
                            print(f"      {'✅' if buy_dk4_ok else '❌'} ĐK4: ATR >= 0.00011")
                            if buy_dk4_ok:
                                print(f"      {'✅' if buy_dk5_ok else '❌'} ĐK5: Nến phá vỡ trendline")
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
                            print(f"      {'✅' if sell_dk4_ok else '❌'} ĐK4: ATR >= 0.00011")
                            if sell_dk4_ok:
                                print(f"      {'✅' if sell_dk5_ok else '❌'} ĐK5: Nến phá vỡ trendline")
            if sell_fail_reason:
                print(f"      💡 Lý do chính: {sell_fail_reason}")
            
            # Current indicators
            current_rsi_display = curr_candle.get('rsi', 0)
            print(f"\n📈 [Indicators Hiện Tại]")
            print(f"   💱 Price: {curr_candle['close']:.5f}")
            print(f"   📊 EMA50: {ema50_val:.5f}")
            print(f"   📊 EMA200: {ema200_val:.5f}")
            if pd.notna(current_rsi_display):
                print(f"   📊 RSI: {current_rsi_display:.1f}")
            else:
                print(f"   📊 RSI: N/A")
            if pd.notna(atr_val):
                print(f"   📊 ATR: {atr_val:.5f}")
            else:
                print(f"   📊 ATR: N/A")
            if pd.notna(atr_val):
                print(f"   📊 ATR Pips: {(atr_val / 0.0001):.1f} pips")
            else:
                print(f"   📊 ATR Pips: N/A")
            
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
            send_telegram(
                f"❌ <b>M1 Scalp Bot - Lỗi</b>\n{error_msg}",
                config.get('telegram_token'),
                config.get('telegram_chat_id')
            )
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
        
        # Validate order
        check_result = mt5.order_check(request)
        if check_result.retcode != mt5.TRADE_RETCODE_DONE:
            error_msg = f"Order validation failed: {check_result.comment}"
            print(f"❌ {error_msg}")
            send_telegram(
                f"❌ <b>M1 Scalp Bot - Lỗi Gửi Lệnh</b>\n"
                f"💱 Symbol: {symbol} ({signal_type})\n"
                f"❌ Lỗi: {error_msg}",
                config.get('telegram_token'),
                config.get('telegram_chat_id')
            )
            return error_count + 1, 0
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(result.order, "M1_Scalp", symbol, signal_type, volume, current_price, sl, tp, reason, account_id=config.get('account'))
            
            # Detailed Telegram Message
            msg_parts = []
            msg_parts.append(f"✅ <b>M1 Scalp Bot - Lệnh Đã Được Thực Hiện</b>\n")
            msg_parts.append(f"{'='*50}\n")
            msg_parts.append(f"🆔 <b>Ticket:</b> {result.order}\n")
            msg_parts.append(f"💱 <b>Symbol:</b> {symbol} ({signal_type})\n")
            msg_parts.append(f"💵 <b>Entry Price:</b> {current_price:.5f} (Close của nến phá vỡ)\n")
            msg_parts.append(f"🛑 <b>SL:</b> {sl:.5f} (2ATR + 6pt = {sl_distance:.5f})\n")
            msg_parts.append(f"🎯 <b>TP:</b> {tp:.5f} (2SL = {tp_distance:.5f})\n")
            msg_parts.append(f"📊 <b>Volume:</b> {volume:.2f} lot\n")
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
                msg_parts.append(f"   • RSI: {current_rsi_val:.1f}\n")
            msg_parts.append(f"   • ATR: {atr_val:.5f}\n")
            msg_parts.append(f"\n")
            msg_parts.append(f"{'='*50}\n")
            msg_parts.append(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            msg = "".join(msg_parts)
            send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
            return 0, 0
        else:
            error_msg = f"Order Failed: Retcode {result.retcode}"
            error_detail = f"{result.comment if hasattr(result, 'comment') else 'Unknown error'}"
            print(f"❌ {error_msg} - {error_detail}")
            send_telegram(
                f"❌ <b>M1 Scalp Bot - Lỗi Gửi Lệnh</b>\n"
                f"💱 Symbol: {symbol} ({signal_type})\n"
                f"💵 Entry: {current_price:.5f}\n"
                f"🛑 SL: {sl:.5f} | 🎯 TP: {tp:.5f}\n"
                f"❌ Lỗi: {error_msg}\n"
                f"📝 Chi tiết: {error_detail}",
                config.get('telegram_token'),
                config.get('telegram_chat_id')
            )
            return error_count + 1, result.retcode
        
    except Exception as e:
        print(f"❌ Lỗi trong m1_scalp_logic: {e}")
        import traceback
        traceback.print_exc()
        return error_count + 1, 0

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_tuyen.json")
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
            
            print("🔄 Bắt đầu vòng lặp chính...\n")
            
            loop_count = 0
            while True:
                try:
                    loop_count += 1
                    if loop_count % 60 == 0:  # Print every 60 iterations (~1 minute)
                        print(f"⏳ Bot đang chạy... (vòng lặp #{loop_count})")
                    
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

