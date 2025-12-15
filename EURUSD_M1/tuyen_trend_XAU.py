import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# Import local modules
sys.path.append('..') 
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message

# Initialize Database
db = Database()

# Translation dictionary for Vietnamese/English logging
TRANSLATIONS = {
    'vi': {
        'analysis': '📊 [Phân Tích TuyenTrend]',
        'h1_bias': '🔍 [H1 Xu Hướng Lớn]',
        'h1_bias_value': 'H1 Bias',
        'no_structure': 'Không có cấu trúc rõ ràng',
        'supply_zones': 'Vùng Cung',
        'demand_zones': 'Vùng Cầu',
        'zones_found': 'vùng được tìm thấy',
        'freshness': 'Độ mới',
        'candles': 'nến',
        'm5_trend': '🔍 [Phân Tích Xu Hướng M5]',
        'trend': 'Xu hướng',
        'reason': 'Lý do',
        'price': 'Giá',
        'slope': 'Độ dốc',
        'up': 'LÊN',
        'down': 'XUỐNG',
        'flat': 'NGANG',
        'distance': 'Khoảng cách',
        'pips': 'pips',
        'm1_structure': '🔍 [Phân Tích Cấu Trúc M1]',
        'last_high': 'Đỉnh gần nhất',
        'prev_high': 'Đỉnh trước',
        'last_low': 'Đáy gần nhất',
        'prev_low': 'Đáy trước',
        'lower_high': '✅ Đỉnh thấp hơn',
        'not_lower': '❌ Không thấp hơn',
        'higher_high': '✅ Đỉnh cao hơn',
        'not_higher': '❌ Không cao hơn',
        'lower_low': '✅ Đáy thấp hơn',
        'higher_low': '✅ Đáy cao hơn',
        'structure_valid': '✅ Cấu trúc M1 hợp lệ',
        'strategy_1': '📈 [CHIẾN LƯỢC 1: Pullback + Cụm Doji/Pinbar]',
        'strategy_2': '📈 [CHIẾN LƯỢC 2: Tiếp Diễn + Cấu Trúc (M/W + Compression)]',
        'fibonacci': '🔍 [Kiểm Tra Fibonacci Retracement]',
        'swing_high': 'Đỉnh Swing',
        'swing_low': 'Đáy Swing',
        'current_price': 'Giá hiện tại',
        'in_zone': '✅ Giá trong vùng Fib',
        'not_in_zone': '❌ Giá KHÔNG trong vùng Fib',
        'required': 'Yêu cầu',
        'signal_candle': '🔍 [Kiểm Tra Nến Tín Hiệu]',
        'candle': 'Nến',
        'signal': '✅ Tín hiệu',
        'not_signal': '❌ Không phải tín hiệu',
        'ema_touch': '🔍 [Kiểm Tra Chạm EMA]',
        'touches': '✅ Có chạm',
        'not_touches': '❌ Không chạm',
        'smooth_pullback': '🔍 [Kiểm Tra Sóng Hồi Mượt]',
        'smooth': '✅ Sóng hồi mượt',
        'not_smooth': '❌ Sóng hồi không mượt',
        'large_candles': 'Nến lớn',
        'avg_range': 'Biên độ trung bình',
        'strategy_1_signal': '✅ [TÍN HIỆU CHIẾN LƯỢC 1]',
        'strategy_1_fail': '❌ [CHIẾN LƯỢC 1 THẤT BẠI]',
        'all_conditions_met': 'Tất cả điều kiện đạt',
        'missing_conditions': 'Thiếu điều kiện',
        'ema200_filter': '🔍 [Kiểm Tra Bộ Lọc EMA200]',
        'filter_passed': '✅ Bộ lọc đạt',
        'filter_failed': '❌ Bộ lọc không đạt',
        'breakout_retest': '🔍 [Kiểm Tra Breakout + Retest]',
        'looking_back': 'Đang tìm kiếm',
        'candles_back': 'nến trước',
        'breakout_found': '✅ Tìm thấy Breakout+Retest',
        'breakout_not_found': '❌ Không tìm thấy Breakout+Retest',
        'level': 'Mức',
        'shallow': 'Shallow',
        'shallow_detected': 'Phát hiện Shallow Breakout',
        'pullback_percent': 'Pullback',
        'in_range': '✅ Trong khoảng hợp lệ',
        'not_in_range': '❌ Không trong khoảng hợp lệ',
        'compression': '🔍 [Kiểm Tra Compression Block]',
        'compression_detected': '✅ Phát hiện Compression Block',
        'no_compression': '❌ Không có Compression Block',
        'block_range': 'Biên độ Block',
        'pattern': '🔍 [Kiểm Tra Pattern]',
        'pattern_detected': '✅ Phát hiện Pattern',
        'no_pattern': '❌ Không có Pattern',
        'signal_candle_compression': '🔍 [Kiểm Tra Nến Tín Hiệu trong Compression]',
        'valid_signal_candle': '✅ Nến tín hiệu hợp lệ',
        'invalid_signal_candle': '❌ Nến tín hiệu không hợp lệ',
        'close': 'Đóng cửa',
        'body': 'Thân',
        'range': 'Biên độ',
        'ema_breakout_touch': '🔍 [Kiểm Tra Chạm EMA/Breakout Level]',
        'block_touches': '✅ Block chạm EMA hoặc Breakout Level',
        'block_not_touches': '❌ Block không chạm EMA hoặc Breakout Level',
        'strategy_2_summary': '📊 [Tóm Tắt Chiến Lược 2]',
        'strategy_2_signal': '✅ [TÍN HIỆU CHIẾN LƯỢC 2]',
        'strategy_2_fail': '❌ [CHIẾN LƯỢC 2 THẤT BẠI]',
        'final_summary': '📊 [TÓM TẮT CUỐI CÙNG]',
        'no_signal': '❌ [KHÔNG CÓ TÍN HIỆU]',
        'signal_found': '✅ [TÌM THẤY TÍN HIỆU]',
        'reasons': 'Lý do',
        'entry_trigger': '🔍 [Kiểm Tra Điểm Vào Lệnh]',
        'trigger_high': 'Mức kích hoạt Cao',
        'trigger_low': 'Mức kích hoạt Thấp',
        'ready_execute': '✅ SẴN SÀNG THỰC HIỆN',
        'waiting_breakout': '⏳ Đang chờ breakout',
        'need': 'Cần thêm',
        'execution': '🚀 [THỰC HIỆN]',
        'spam_filter': '🔍 [Kiểm Tra Spam Filter]',
        'last_trade': 'Lệnh cuối',
        'seconds_ago': 'giây trước',
        'cooldown_passed': '✅ Đã qua thời gian chờ',
        'no_recent_trades': '✅ Không có lệnh gần đây',
        'signal_execute': '✅ [THỰC HIỆN TÍN HIỆU]',
        'filter_fail': '❌ [BỘ LỌC THẤT BẠI]',
        'h1_conflicts': 'H1 Bias xung đột với M5 Trend',
        'no_trend': 'Không có xu hướng',
        'too_close_zone': 'Giá quá gần vùng Supply/Demand ngược',
        'structure_unclear': 'Cấu trúc không rõ ràng',
        'aligns': '✅ H1 Bias phù hợp với M5 Trend',
        'no_bias': '⚠️ H1 Bias: None',
        'has_room': '✅ Giá có khoảng trống để di chuyển',
        'not_enough_swing': '❌ Không đủ swing points',
    },
    'en': {
        'analysis': '📊 [TuyenTrend Analysis]',
        'h1_bias': '🔍 [H1 Higher-timeframe Bias]',
        'h1_bias_value': 'H1 Bias',
        'no_structure': 'None (No clear structure)',
        'supply_zones': 'H1 Supply Zones',
        'demand_zones': 'H1 Demand Zones',
        'zones_found': 'zones found',
        'freshness': 'Freshness',
        'candles': 'candles',
        'm5_trend': '🔍 [M5 Trend Analysis]',
        'trend': 'Trend',
        'reason': 'Reason',
        'price': 'Price',
        'slope': 'EMA21 Slope',
        'up': 'UP',
        'down': 'DOWN',
        'flat': 'FLAT',
        'distance': 'Distance',
        'pips': 'pips',
        'm1_structure': '🔍 [M1 Structure Analysis]',
        'last_high': 'Last High',
        'prev_high': 'Prev High',
        'last_low': 'Last Low',
        'prev_low': 'Prev Low',
        'lower_high': '✅ Lower High',
        'not_lower': '❌ Not Lower',
        'higher_high': '✅ Higher High',
        'not_higher': '❌ Not Higher',
        'lower_low': '✅ Lower Low',
        'higher_low': '✅ Higher Low',
        'structure_valid': '✅ M1 Structure valid',
        'strategy_1': '📈 [STRATEGY 1: Pullback + Doji/Pinbar Cluster]',
        'strategy_2': '📈 [STRATEGY 2: Continuation + Structure (M/W + Compression)]',
        'fibonacci': '🔍 [Fibonacci Retracement Check]',
        'swing_high': 'Swing High',
        'swing_low': 'Swing Low',
        'current_price': 'Current Price',
        'in_zone': '✅ Price in Fib zone',
        'not_in_zone': '❌ Price NOT in Fib zone',
        'required': 'Required',
        'signal_candle': '🔍 [Signal Candle Check]',
        'candle': 'Candle',
        'signal': '✅ Signal',
        'not_signal': '❌ Not Signal',
        'ema_touch': '🔍 [EMA Touch Check]',
        'touches': '✅ Yes',
        'not_touches': '❌ No',
        'smooth_pullback': '🔍 [Smooth Pullback Check]',
        'smooth': '✅ Pullback is smooth',
        'not_smooth': '❌ Pullback not smooth',
        'large_candles': 'Large candles',
        'avg_range': 'Avg range',
        'strategy_1_signal': '✅ [STRATEGY 1 SIGNAL]',
        'strategy_1_fail': '❌ [STRATEGY 1 FAIL]',
        'all_conditions_met': 'All conditions met!',
        'missing_conditions': 'Missing conditions:',
        'ema200_filter': '🔍 [EMA200 Filter Check]',
        'filter_passed': '✅ Filter passed',
        'filter_failed': '❌ Filter failed',
        'breakout_retest': '🔍 [Breakout + Retest Check]',
        'looking_back': 'Looking back',
        'candles_back': 'candles for breakout',
        'breakout_found': '✅ Breakout+Retest found',
        'breakout_not_found': '❌ No Breakout+Retest found',
        'level': 'Level',
        'shallow': 'Shallow',
        'shallow_detected': 'Shallow Breakout detected',
        'pullback_percent': 'Pullback',
        'in_range': '✅ in valid range',
        'not_in_range': '❌ not in range',
        'compression': '🔍 [Compression Block Check]',
        'compression_detected': '✅ Compression Block detected',
        'no_compression': '❌ No Compression Block found',
        'block_range': 'Block Range',
        'pattern': '🔍 [Pattern Detection Check]',
        'pattern_detected': '✅ Pattern detected',
        'no_pattern': '❌ No Pattern found',
        'signal_candle_compression': '🔍 [Signal Candle in Compression Check]',
        'valid_signal_candle': '✅ Valid Signal Candle found',
        'invalid_signal_candle': '❌ Signal Candle conditions not met',
        'close': 'Close',
        'body': 'Body',
        'range': 'Range',
        'ema_breakout_touch': '🔍 [EMA/Breakout Level Touch Check]',
        'block_touches': '✅ Block touches EMA or Breakout Level',
        'block_not_touches': '❌ Block didn\'t touch',
        'strategy_2_summary': '📊 [Strategy 2 Summary]',
        'strategy_2_signal': '✅ [STRATEGY 2 SIGNAL]',
        'strategy_2_fail': '❌ [STRATEGY 2 FAIL]',
        'final_summary': '📊 [FINAL SUMMARY]',
        'no_signal': '❌ [NO SIGNAL]',
        'signal_found': '✅ [SIGNAL FOUND]',
        'reasons': 'Reasons',
        'entry_trigger': '🔍 [Entry Trigger Check]',
        'trigger_high': 'Trigger High',
        'trigger_low': 'Trigger Low',
        'ready_execute': '✅ READY TO EXECUTE',
        'waiting_breakout': '⏳ Waiting for breakout',
        'need': 'Need',
        'execution': '🚀 [EXECUTION]',
        'spam_filter': '🔍 [Spam Filter Check]',
        'last_trade': 'Last trade',
        'seconds_ago': 'seconds ago',
        'cooldown_passed': '✅ Cooldown passed',
        'no_recent_trades': '✅ No recent trades',
        'signal_execute': '✅ [SIGNAL EXECUTE]',
        'filter_fail': '❌ [FILTER FAIL]',
        'h1_conflicts': 'H1 Bias conflicts with M5 Trend',
        'no_trend': 'No Trend',
        'too_close_zone': 'Price too close to opposite Supply/Demand zone',
        'structure_unclear': 'M1 Structure không rõ ràng',
        'aligns': '✅ H1 Bias aligns with M5 Trend',
        'no_bias': '⚠️ H1 Bias: None',
        'has_room': '✅ Price has room to move',
        'not_enough_swing': '❌ Not enough swing points',
    }
}

def t(key, lang='en'):
    """Translation helper function"""
    return TRANSLATIONS.get(lang, TRANSLATIONS['en']).get(key, key)

def calculate_ema(series, span):
    """Calculate EMA"""
    return series.ewm(span=span, adjust=False).mean()

def find_swing_points(df, lookback=5):
    """Find swing highs and lows"""
    swing_highs = []
    swing_lows = []
    
    for i in range(lookback, len(df) - lookback):
        # Swing High: Higher than lookback candles on both sides
        is_swing_high = True
        for j in range(i - lookback, i + lookback + 1):
            if j != i and df.iloc[j]['high'] >= df.iloc[i]['high']:
                is_swing_high = False
                break
        if is_swing_high:
            swing_highs.append({'index': i, 'price': df.iloc[i]['high'], 'time': df.index[i]})
        
        # Swing Low: Lower than lookback candles on both sides
        is_swing_low = True
        for j in range(i - lookback, i + lookback + 1):
            if j != i and df.iloc[j]['low'] <= df.iloc[i]['low']:
                is_swing_low = False
                break
        if is_swing_low:
            swing_lows.append({'index': i, 'price': df.iloc[i]['low'], 'time': df.index[i]})
    
    return swing_highs, swing_lows

def find_supply_demand_zones(df, swing_highs, swing_lows, lookback=20):
    """Find Supply (resistance) and Demand (support) zones"""
    supply_zones = []
    demand_zones = []
    
    # Supply zones from swing highs
    for swing in swing_highs[-10:]:  # Last 10 swing highs
        idx = swing['index']
        if idx < len(df):
            zone_high = df.iloc[idx]['high']
            zone_low = df.iloc[idx]['low']
            # Check if price reacted to this zone
            reactions = 0
            for i in range(max(0, idx - lookback), min(len(df), idx + lookback)):
                if i != idx and df.iloc[i]['high'] >= zone_low and df.iloc[i]['high'] <= zone_high:
                    reactions += 1
            
            if reactions >= 1:  # At least 1 reaction
                supply_zones.append({
                    'high': zone_high,
                    'low': zone_low,
                    'price': zone_high,  # Entry level
                    'time': swing['time'],
                    'freshness': len(df) - idx  # How recent
                })
    
    # Demand zones from swing lows
    for swing in swing_lows[-10:]:  # Last 10 swing lows
        idx = swing['index']
        if idx < len(df):
            zone_high = df.iloc[idx]['high']
            zone_low = df.iloc[idx]['low']
            # Check if price reacted to this zone
            reactions = 0
            for i in range(max(0, idx - lookback), min(len(df), idx + lookback)):
                if i != idx and df.iloc[i]['low'] <= zone_high and df.iloc[i]['low'] >= zone_low:
                    reactions += 1
            
            if reactions >= 1:  # At least 1 reaction
                demand_zones.append({
                    'high': zone_high,
                    'low': zone_low,
                    'price': zone_low,  # Entry level
                    'time': swing['time'],
                    'freshness': len(df) - idx  # How recent
                })
    
    return supply_zones, demand_zones

def calculate_fibonacci_levels(high_price, low_price, trend='BULLISH'):
    """Calculate Fibonacci retracement levels"""
    diff = abs(high_price - low_price)
    
    if trend == 'BULLISH':
        # Retracement from high to low
        fib_236 = high_price - (diff * 0.236)
        fib_382 = high_price - (diff * 0.382)
        fib_500 = high_price - (diff * 0.500)
        fib_618 = high_price - (diff * 0.618)
        fib_786 = high_price - (diff * 0.786)
    else:  # BEARISH
        # Retracement from low to high
        fib_236 = low_price + (diff * 0.236)
        fib_382 = low_price + (diff * 0.382)
        fib_500 = low_price + (diff * 0.500)
        fib_618 = low_price + (diff * 0.618)
        fib_786 = low_price + (diff * 0.786)
    
    return {
        '236': fib_236,
        '382': fib_382,
        '500': fib_500,
        '618': fib_618,
        '786': fib_786
    }

def check_fibonacci_retracement(current_price, fib_levels, trend, min_level=0.382, max_level=0.786):
    """Check if price is in Fibonacci retracement zone"""
    if trend == 'BULLISH':
        # Price should be between fib_382 and fib_786 (38.2% - 78.6%)
        return fib_levels['786'] <= current_price <= fib_levels['382']
    else:  # BEARISH
        return fib_levels['382'] <= current_price <= fib_levels['786']

def calculate_atr(df, period=14):
    """Calculate ATR - Returns Series that can be assigned to DataFrame"""
    df = df.copy()
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift(1))
    df['tr2'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    atr_series = df['tr'].rolling(window=period).mean()
    return atr_series

def is_doji(row, body_percent=0.1):
    """Body is less than 10% of total range"""
    rng = row['high'] - row['low']
    if rng == 0: return True
    body = abs(row['close'] - row['open'])
    return (body / rng) <= body_percent

def is_pinbar(row, tail_percent=0.6, type='buy'):
    """
    Buy Pinbar: Lower tail is long (>= 60% of range), closing near top.
    Sell Pinbar: Upper tail is long, closing near bottom.
    """
    rng = row['high'] - row['low']
    if rng == 0: return False
    
    body = abs(row['close'] - row['open'])
    upper_wick = row['high'] - max(row['open'], row['close'])
    lower_wick = min(row['open'], row['close']) - row['low']
    
    if type == 'buy':
        # Long lower wick, small body near top
        return (lower_wick / rng) >= tail_percent
    elif type == 'sell':
        # Long upper wick, small body near bottom
        return (upper_wick / rng) >= tail_percent
    return False

def is_hammer(row):
    """Hammer (Nến búa): Long lower wick, small body, small upper wick"""
    rng = row['high'] - row['low']
    if rng == 0: return False
    
    body = abs(row['close'] - row['open'])
    upper_wick = row['high'] - max(row['close'], row['open'])
    lower_wick = min(row['close'], row['open']) - row['low']
    
    # Lower wick >= 2x body, upper wick < body
    return (lower_wick >= 2 * body) and (upper_wick < body) and (body < rng * 0.3)

def is_inverted_hammer(row):
    """Inverted Hammer (Búa ngược): Long upper wick, small body, small lower wick"""
    rng = row['high'] - row['low']
    if rng == 0: return False
    
    body = abs(row['close'] - row['open'])
    upper_wick = row['high'] - max(row['close'], row['open'])
    lower_wick = min(row['close'], row['open']) - row['low']
    
    # Upper wick >= 2x body, lower wick < body
    return (upper_wick >= 2 * body) and (lower_wick < body) and (body < rng * 0.3)

def check_signal_candle(row, trend):
    """
    Return True if candle is Doji, Pinbar, Hammer, or Inverted Hammer conforming to trend
    """
    if is_doji(row, 0.2): return True # Allow slightly fatter Doji
    
    if trend == "BULLISH":
        if is_pinbar(row, type='buy'): return True
        if is_hammer(row): return True  # Hammer is bullish reversal
        if is_inverted_hammer(row): return True  # Inverted hammer can be bullish
    elif trend == "BEARISH":
        if is_pinbar(row, type='sell'): return True
        if is_hammer(row): return True  # Hammer can be bearish if at top
        if is_inverted_hammer(row): return True  # Inverted hammer is bearish reversal
        
    return False

def check_signal_candle_in_compression(df_slice, trend, ema50_val=None, ema200_val=None):
    """
    Check Signal Candle at end of Compression Block (Strategy 2)
    Document requirements (dòng 138-159):
    
    BUY (tiếp diễn tăng):
    - Nằm ở cuối khối hành vi giá
    - Giá đóng cửa gần đỉnh của khối
    - Giá đóng cửa >EMA 50, 200
    - Thân nến nhỏ
    - Tổng biên độ (high-low) nhỏ hơn trung bình 3-5 nến trước
    - Râu nến ngắn hoặc cân bằng
    - Không phá vỡ đỉnh khối
    - Không phải nến momentum tăng mạnh
    
    SELL (tiếp diễn giảm):
    - Nằm ở cuối khối hành vi giá
    - Giá đóng cửa gần đáy của khối
    - Giá đóng cửa <EMA50, 200
    - Thân nến nhỏ
    - Tổng biên độ (high-low) nhỏ hơn trung bình 3-5 nến trước
    - Râu nến ngắn hoặc cân bằng
    - Không phá vỡ đáy khối
    - Không phải nến momentum giảm mạnh
    """
    if len(df_slice) < 3: return False
    
    # Get last candle (signal candle)
    signal_candle = df_slice.iloc[-1]
    block_high = df_slice['high'].max()
    block_low = df_slice['low'].min()
    
    # Check range < avg 3-5 nến trước
    if len(df_slice) >= 5:
        prev_3_5 = df_slice.iloc[-5:-1] if len(df_slice) > 5 else df_slice.iloc[:-1]
        avg_prev_range = (prev_3_5['high'] - prev_3_5['low']).mean()
        signal_range = signal_candle['high'] - signal_candle['low']
        if signal_range >= avg_prev_range:
            return False  # Range not smaller than previous
    
    # Check body size (thân nến nhỏ)
    body = abs(signal_candle['close'] - signal_candle['open'])
    signal_range = signal_candle['high'] - signal_candle['low']
    if signal_range == 0 or (body / signal_range) > 0.4:
        return False  # Body too big
    
    # Check wicks (râu nến ngắn hoặc cân bằng)
    upper_wick = signal_candle['high'] - max(signal_candle['close'], signal_candle['open'])
    lower_wick = min(signal_candle['close'], signal_candle['open']) - signal_candle['low']
    if upper_wick > signal_range * 0.5 or lower_wick > signal_range * 0.5:
        return False  # Wick too long (bị đạp mạnh)
    
    if trend == "BULLISH":
        # Close gần đỉnh của khối
        block_range = block_high - block_low
        if block_range == 0:
            return False
        close_position = (signal_candle['close'] - block_low) / block_range
        if close_position < 0.6:  # Not near top (should be > 60% of block range)
            return False
        
        # Close > EMA50, 200
        if ema50_val and signal_candle['close'] <= ema50_val:
            return False
        if ema200_val and signal_candle['close'] <= ema200_val:
            return False
        
        # Không phá vỡ đỉnh khối
        if signal_candle['high'] > block_high * 1.0001:
            return False
        
        # Không phải nến momentum tăng mạnh (body không quá lớn, không có gap)
        if body > signal_range * 0.6:
            return False
        
        return True
        
    elif trend == "BEARISH":
        # Close gần đáy của khối
        block_range = block_high - block_low
        if block_range == 0:
            return False
        close_position = (signal_candle['close'] - block_low) / block_range
        if close_position > 0.4:  # Not near bottom (should be < 40% of block range)
            return False
        
        # Close < EMA50, 200
        if ema50_val and signal_candle['close'] >= ema50_val:
            return False
        if ema200_val and signal_candle['close'] >= ema200_val:
            return False
        
        # Không phá vỡ đáy khối
        if signal_candle['low'] < block_low * 0.9999:
            return False
        
        # Không phải nến momentum giảm mạnh
        if body > signal_range * 0.6:
            return False
        
        return True
    
    return False

def check_compression_block(df_slice):
    """
    Check for Price Action Compression (Block of 3+ candles)
    Criteria from document:
    1. Cụm ≥ 3 nến
    2. Biên độ dao động thu hẹp dần
    3. Thân nến nhỏ dần
    4. Râu nến ngắn dần
    5. High thấp dần hoặc Low cao dần
    """
    if len(df_slice) < 3: return False
    
    # Calculate ranges, bodies, wicks
    ranges = df_slice['high'] - df_slice['low']
    bodies = abs(df_slice['close'] - df_slice['open'])
    upper_wicks = df_slice['high'] - df_slice[['open', 'close']].max(axis=1)
    lower_wicks = df_slice[['open', 'close']].min(axis=1) - df_slice['low']
    
    # 1. Check if any candle is "Huge" (Momentum) - we want compression, not expansion
    avg_range = ranges.mean()
    if (ranges > avg_range * 2.0).any():
        return False
    
    # 2. Check range contraction (biên độ thu hẹp dần)
    # Compare first half vs second half
    mid = len(ranges) // 2
    first_half_avg = ranges[:mid].mean() if mid > 0 else ranges.mean()
    second_half_avg = ranges[mid:].mean() if mid < len(ranges) else ranges.mean()
    range_contracting = second_half_avg < first_half_avg * 1.1  # Second half smaller or similar
    
    # 3. Check body shrinking (thân nến nhỏ dần)
    first_half_body = bodies[:mid].mean() if mid > 0 else bodies.mean()
    second_half_body = bodies[mid:].mean() if mid < len(bodies) else bodies.mean()
    body_shrinking = second_half_body < first_half_body * 1.1
    
    # 4. Check wick shortening (râu nến ngắn dần)
    first_half_wick = (upper_wicks[:mid] + lower_wicks[:mid]).mean() if mid > 0 else (upper_wicks + lower_wicks).mean()
    second_half_wick = (upper_wicks[mid:] + lower_wicks[mid:]).mean() if mid < len(upper_wicks) else (upper_wicks + lower_wicks).mean()
    wick_shortening = second_half_wick < first_half_wick * 1.1
    
    # 5. Check high lowering or low raising (High thấp dần hoặc Low cao dần)
    highs = df_slice['high'].values
    lows = df_slice['low'].values
    first_half_high = highs[:mid].max() if mid > 0 else highs.max()
    second_half_high = highs[mid:].max() if mid < len(highs) else highs.max()
    first_half_low = lows[:mid].min() if mid > 0 else lows.min()
    second_half_low = lows[mid:].min() if mid < len(lows) else lows.min()
    
    high_lowering = second_half_high < first_half_high
    low_raising = second_half_low > first_half_low
    
    # At least 3 out of 5 criteria should be met
    criteria_met = sum([range_contracting, body_shrinking, wick_shortening, high_lowering, low_raising])
    
    # Also check: Avg Body Size should be small relative to Avg Range
    avg_body = bodies.mean()
    if avg_body > (avg_range * 0.6):  # Bodies too big = directional, not compressed
        return False
    
    return criteria_met >= 3  # At least 3 compression criteria met

def detect_pattern(df_slice, type='W', ema50_val=None, ema200_val=None):
    """
    Improved Pattern Detection for M (Sell) or W (Buy) with all 7 conditions from document.
    
    W Pattern (BUY) conditions:
    1. Xuất hiện sau đáy thứ 2
    2. Nằm trong khối hành vi giá
    3. Không phá đáy Low 2
    4. Thân nến nhỏ (nén)
    5. Đỉnh nến là mức phá
    6. Nằm gần neckline
    7. Giá đóng cửa > EMA50, 200
    """
    if len(df_slice) < 5: return False
    
    lows = df_slice['low'].values
    highs = df_slice['high'].values
    closes = df_slice['close'].values
    opens = df_slice['open'].values
    
    if type == 'W':  # BUY
        # Find two distinct lows (đáy thứ 1 và đáy thứ 2)
        # Look for local minima
        local_mins = []
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                local_mins.append({'index': i, 'price': lows[i]})
        
        if len(local_mins) < 2:
            return False
        
        # Sort by index to get first and second low
        local_mins = sorted(local_mins, key=lambda x: x['index'])
        low1 = local_mins[0]
        low2 = local_mins[-1]  # Last low (đáy thứ 2)
        
        # Condition 1: Xuất hiện sau đáy thứ 2
        if low2['index'] >= len(df_slice) - 2:  # Too recent, not enough candles after
            return False
        
        # Condition 3: Không phá đáy Low 2 (current price should not break below low2)
        current_low = df_slice.iloc[-1]['low']
        if current_low < low2['price'] * 0.9999:
            return False
        
        # Condition 2: Min2 should be >= Min1 (Higher Low or Double Bottom)
        if low2['price'] < low1['price'] * 0.9999:  # Lower low, not W pattern
            return False
        
        # Condition 4: Thân nến nhỏ (nén) - last candle body should be small
        last_body = abs(closes[-1] - opens[-1])
        last_range = highs[-1] - lows[-1]
        if last_range == 0 or (last_body / last_range) > 0.4:  # Body too big
            return False
        
        # Condition 5: Đỉnh nến là mức phá - high should be near top
        current_high = df_slice.iloc[-1]['high']
        range_high = np.max(highs)
        if current_high < range_high * 0.995:  # Not near top
            return False
        
        # Condition 6: Nằm gần neckline (middle of the range between low2 and high)
        neckline = (low2['price'] + range_high) / 2
        current_close = closes[-1]
        if abs(current_close - neckline) / neckline > 0.002:  # More than 0.2% away
            return False
        
        # Condition 7: Giá đóng cửa > EMA50, 200
        if ema50_val and current_close <= ema50_val:
            return False
        if ema200_val and current_close <= ema200_val:
            return False
        
        return True
        
    elif type == 'M':  # SELL
        # Find two distinct highs (đỉnh thứ 1 và đỉnh thứ 2)
        local_maxs = []
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                local_maxs.append({'index': i, 'price': highs[i]})
        
        if len(local_maxs) < 2:
            return False
        
        # Sort by index
        local_maxs = sorted(local_maxs, key=lambda x: x['index'])
        high1 = local_maxs[0]
        high2 = local_maxs[-1]  # Last high (đỉnh thứ 2)
        
        # Condition 1: Xuất hiện sau đỉnh thứ 2
        if high2['index'] >= len(df_slice) - 2:
            return False
        
        # Condition 3: Không phá đỉnh High 2
        current_high = df_slice.iloc[-1]['high']
        if current_high > high2['price'] * 1.0001:
            return False
        
        # Condition 2: Max2 should be <= Max1 (Lower High or Double Top)
        if high2['price'] > high1['price'] * 1.0001:  # Higher high, not M pattern
            return False
        
        # Condition 4: Thân nến nhỏ
        last_body = abs(closes[-1] - opens[-1])
        last_range = highs[-1] - lows[-1]
        if last_range == 0 or (last_body / last_range) > 0.4:
            return False
        
        # Condition 5: Đáy nến là mức phá
        current_low = df_slice.iloc[-1]['low']
        range_low = np.min(lows)
        if current_low > range_low * 1.005:  # Not near bottom
            return False
        
        # Condition 6: Nằm gần neckline
        neckline = (high2['price'] + range_low) / 2
        current_close = closes[-1]
        if abs(current_close - neckline) / neckline > 0.002:
            return False
        
        # Condition 7: Giá đóng cửa < EMA50, 200
        if ema50_val and current_close >= ema50_val:
            return False
        if ema200_val and current_close >= ema200_val:
            return False
        
        return True
                 
    return False

def tuyen_trend_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    # Language setting (Vietnamese or English)
    lang = config.get('language', 'en').lower()  # 'vi' for Vietnamese, 'en' for English
    
    # --- 1. Manage Existing Positions ---
    positions = mt5.positions_get(symbol=symbol, magic=magic)
    if positions:
        for pos in positions:
            manage_position(pos.ticket, symbol, magic, config)
        if len(positions) >= max_positions:
            return error_count, 0

    # --- 2. Data Fetching ---
    df_h1 = get_data(symbol, mt5.TIMEFRAME_H1, 200)  # H1 for higher-timeframe bias
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 300) 
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 300)
    
    if df_m1 is None or df_m5 is None: return error_count, 0
    if df_h1 is None: df_h1 = df_m5  # Fallback to M5 if H1 not available

    # --- 3. H1 Higher-timeframe Bias (Supply/Demand) ---
    h1_bias = None
    h1_swing_highs, h1_swing_lows = find_swing_points(df_h1, lookback=3)
    h1_supply_zones, h1_demand_zones = find_supply_demand_zones(df_h1, h1_swing_highs, h1_swing_lows)
    
    current_h1_price = df_h1.iloc[-1]['close']
    # Check if price is near Supply (bearish) or Demand (bullish) zone
    near_supply = False
    near_demand = False
    
    for zone in h1_supply_zones[-5:]:  # Check last 5 supply zones
        if zone['low'] <= current_h1_price <= zone['high'] * 1.001:  # Within or very close
            near_supply = True
            h1_bias = "SELL"
            break
    
    for zone in h1_demand_zones[-5:]:  # Check last 5 demand zones
        if zone['high'] >= current_h1_price >= zone['low'] * 0.999:  # Within or very close
            near_demand = True
            h1_bias = "BUY"
            break
    
    # If not near zones, determine bias from structure (Lower Highs/Lows = SELL, Higher Highs/Lows = BUY)
    if h1_bias is None and len(h1_swing_highs) >= 2 and len(h1_swing_lows) >= 2:
        last_high = h1_swing_highs[-1]['price']
        prev_high = h1_swing_highs[-2]['price']
        last_low = h1_swing_lows[-1]['price']
        prev_low = h1_swing_lows[-2]['price']
        
        if last_high < prev_high and last_low < prev_low:
            h1_bias = "SELL"  # Lower Highs, Lower Lows
        elif last_high > prev_high and last_low > prev_low:
            h1_bias = "BUY"  # Higher Highs, Higher Lows
    
    # --- 4. M5 Trend Detection + Supply/Demand ---
    df_m5['ema21'] = calculate_ema(df_m5['close'], 21)
    df_m5['ema50'] = calculate_ema(df_m5['close'], 50)
    
    last_m5 = df_m5.iloc[-1]
    
    # Check Slope
    ema21_slope_up = df_m5.iloc[-1]['ema21'] > df_m5.iloc[-2]['ema21'] > df_m5.iloc[-3]['ema21']
    ema21_slope_down = df_m5.iloc[-1]['ema21'] < df_m5.iloc[-2]['ema21'] < df_m5.iloc[-3]['ema21']
    
    m5_trend = "NEUTRAL"
    trend_reason = "Flat/Mixed"
    
    if last_m5['close'] > last_m5['ema21'] > last_m5['ema50']:
        if ema21_slope_up:
            m5_trend = "BULLISH"
            trend_reason = "Price > EMA21 > EMA50, Slope Up"
        else:
            trend_reason = "Price OK (Valid Stack), but Slope Flat/Down"
    elif last_m5['close'] < last_m5['ema21'] < last_m5['ema50']:
        if ema21_slope_down:
            m5_trend = "BEARISH"
            trend_reason = "Price < EMA21 < EMA50, Slope Down"
        else:
            trend_reason = "Price OK (Valid Stack), but Slope Flat/Up"
    else:
        trend_reason = "EMAs Crossed or Price Inside EMAs"
    
    # M5 Supply/Demand zones
    m5_swing_highs, m5_swing_lows = find_swing_points(df_m5, lookback=3)
    m5_supply_zones, m5_demand_zones = find_supply_demand_zones(df_m5, m5_swing_highs, m5_swing_lows)
    
    current_m5_price = df_m5.iloc[-1]['close']
    # Check if price is too close to opposite zone (should have room to move)
    too_close_to_opposite_zone = False
    if m5_trend == "BULLISH":
        # Check if near supply zone (resistance)
        for zone in m5_supply_zones[-5:]:
            distance = (zone['low'] - current_m5_price) / current_m5_price
            if distance < 0.0005:  # Less than 5 pips away
                too_close_to_opposite_zone = True
                break
    elif m5_trend == "BEARISH":
        # Check if near demand zone (support)
        for zone in m5_demand_zones[-5:]:
            distance = (current_m5_price - zone['high']) / current_m5_price
            if distance < 0.0005:  # Less than 5 pips away
                too_close_to_opposite_zone = True
                break
        
    # --- 4. M1 Setup Checks ---
    df_m1['ema21'] = calculate_ema(df_m1['close'], 21)
    df_m1['ema50'] = calculate_ema(df_m1['close'], 50)
    df_m1['ema200'] = calculate_ema(df_m1['close'], 200) 
    df_m1['atr'] = calculate_atr(df_m1, 14)
    
    # M1 Structure Detection (Lower Highs/Lows for SELL, Higher Highs/Lows for BUY)
    m1_swing_highs, m1_swing_lows = find_swing_points(df_m1, lookback=5)
    m1_structure_valid = True
    
    if len(m1_swing_highs) >= 2 and len(m1_swing_lows) >= 2:
        if m5_trend == "BEARISH":
            # Check Lower Highs and Lower Lows
            last_high = m1_swing_highs[-1]['price']
            prev_high = m1_swing_highs[-2]['price']
            last_low = m1_swing_lows[-1]['price']
            prev_low = m1_swing_lows[-2]['price']
            
            # Should have Lower Highs and Lower Lows
            if not (last_high < prev_high and last_low < prev_low):
                m1_structure_valid = False
                trend_reason += " | M1 Structure: Not Lower Highs/Lows"
        elif m5_trend == "BULLISH":
            # Check Higher Highs and Higher Lows
            last_high = m1_swing_highs[-1]['price']
            prev_high = m1_swing_highs[-2]['price']
            last_low = m1_swing_lows[-1]['price']
            prev_low = m1_swing_lows[-2]['price']
            
            # Should have Higher Highs and Higher Lows
            if not (last_high > prev_high and last_low > prev_low):
                m1_structure_valid = False
                trend_reason += " | M1 Structure: Not Higher Highs/Lows"
    
    # M1 Structure Analysis
    print(f"\n{t('m1_structure', lang)}")
    if len(m1_swing_highs) >= 2 and len(m1_swing_lows) >= 2:
        if m5_trend == "BEARISH":
            last_high = m1_swing_highs[-1]['price']
            prev_high = m1_swing_highs[-2]['price']
            last_low = m1_swing_lows[-1]['price']
            prev_low = m1_swing_lows[-2]['price']
            high_status = t('lower_high', lang) if last_high < prev_high else t('not_lower', lang)
            low_status = t('lower_low', lang) if last_low < prev_low else t('not_lower', lang)
            print(f"   {t('last_high', lang)}: {last_high:.5f} | {t('prev_high', lang)}: {prev_high:.5f} | {high_status}")
            print(f"   {t('last_low', lang)}: {last_low:.5f} | {t('prev_low', lang)}: {prev_low:.5f} | {low_status}")
        elif m5_trend == "BULLISH":
            last_high = m1_swing_highs[-1]['price']
            prev_high = m1_swing_highs[-2]['price']
            last_low = m1_swing_lows[-1]['price']
            prev_low = m1_swing_lows[-2]['price']
            high_status = t('higher_high', lang) if last_high > prev_high else t('not_higher', lang)
            low_status = t('higher_low', lang) if last_low > prev_low else t('not_higher', lang)
            print(f"   {t('last_high', lang)}: {last_high:.5f} | {t('prev_high', lang)}: {prev_high:.5f} | {high_status}")
            print(f"   {t('last_low', lang)}: {last_low:.5f} | {t('prev_low', lang)}: {prev_low:.5f} | {low_status}")
    else:
        print(f"   ⚠️ {t('not_enough_swing', lang)} ({len(m1_swing_highs)} highs, {len(m1_swing_lows)} lows)")
    
    if not m1_structure_valid:
        print(f"\n{t('filter_fail', lang)} {t('structure_unclear', lang)}. Bỏ qua.")
        return error_count, 0
    else:
        print(f"   {t('structure_valid', lang)}")
    
    # Recent completed candles (last 3-5)
    c1 = df_m1.iloc[-2] # Completed
    c2 = df_m1.iloc[-3]
    c3 = df_m1.iloc[-4]
    
    # Check for smooth pullback (sóng hồi chéo, mượt) - Strategy 1
    def is_smooth_pullback(df_slice, trend):
        """Check if pullback is smooth (no large candles, no gaps)"""
        if len(df_slice) < 3: return False
        
        ranges = df_slice['high'] - df_slice['low']
        avg_range = ranges.mean()
        
        # No candle should be > 2x average (no large impulsive move)
        if (ranges > avg_range * 2.0).any():
            return False
        
        # Check for gaps (large difference between consecutive candles)
        for i in range(1, len(df_slice)):
            prev_close = df_slice.iloc[i-1]['close']
            curr_open = df_slice.iloc[i]['open']
            gap = abs(curr_open - prev_close)
            if gap > avg_range * 0.5:  # Large gap
                return False
        
        return True
    
    def touches_ema(row):
        # Check simple intersection with EMA 21 or 50
        e21, e50 = row['ema21'], row['ema50']
        high, low = row['high'], row['low']
        return (low <= e21 <= high) or (low <= e50 <= high)

    signal_type = None
    reason = ""
    log_details = []
    
    price = mt5.symbol_info_tick(symbol).ask 
    
    # === DETAILED LOGGING ===
    print(f"\n{'='*80}")
    print(f"{t('analysis', lang)} {symbol} | {t('price', lang)}: {price:.5f}")
    print(f"{'='*80}")
    
    # H1 Analysis
    print(f"\n{t('h1_bias', lang)}")
    print(f"   {t('h1_bias_value', lang)}: {h1_bias if h1_bias else t('no_structure', lang)}")
    if h1_supply_zones:
        print(f"   {t('supply_zones', lang)}: {len(h1_supply_zones)} {t('zones_found', lang)}")
        for i, zone in enumerate(h1_supply_zones[-3:], 1):
            print(f"      Vùng {i}: {zone['low']:.5f} - {zone['high']:.5f} ({t('freshness', lang)}: {zone['freshness']} {t('candles', lang)})")
    if h1_demand_zones:
        print(f"   {t('demand_zones', lang)}: {len(h1_demand_zones)} {t('zones_found', lang)}")
        for i, zone in enumerate(h1_demand_zones[-3:], 1):
            print(f"      Vùng {i}: {zone['low']:.5f} - {zone['high']:.5f} ({t('freshness', lang)}: {zone['freshness']} {t('candles', lang)})")
    
    # M5 Analysis
    print(f"\n{t('m5_trend', lang)}")
    print(f"   {t('trend', lang)}: {m5_trend} | {t('reason', lang)}: {trend_reason}")
    print(f"   {t('price', lang)}: {last_m5['close']:.5f} | EMA21: {last_m5['ema21']:.5f} | EMA50: {last_m5['ema50']:.5f}")
    slope_text = t('up', lang) if ema21_slope_up else (t('down', lang) if ema21_slope_down else t('flat', lang))
    print(f"   {t('slope', lang)}: {slope_text}")
    if m5_supply_zones:
        print(f"   M5 {t('supply_zones', lang)}: {len(m5_supply_zones)} {t('zones_found', lang).split()[0]}")
        for i, zone in enumerate(m5_supply_zones[-3:], 1):
            distance = ((zone['low'] - current_m5_price) / current_m5_price * 10000) if m5_trend == "BULLISH" else 0
            print(f"      Vùng {i}: {zone['low']:.5f} - {zone['high']:.5f} ({t('distance', lang)}: {distance:.1f} {t('pips', lang)})")
    if m5_demand_zones:
        print(f"   M5 {t('demand_zones', lang)}: {len(m5_demand_zones)} {t('zones_found', lang).split()[0]}")
        for i, zone in enumerate(m5_demand_zones[-3:], 1):
            distance = ((current_m5_price - zone['high']) / current_m5_price * 10000) if m5_trend == "BEARISH" else 0
            print(f"      Vùng {i}: {zone['low']:.5f} - {zone['high']:.5f} ({t('distance', lang)}: {distance:.1f} {t('pips', lang)})")
    
    log_details.append(f"H1 Bias: {h1_bias} | M5 Trend: {m5_trend} ({trend_reason})")
    
    # Higher-timeframe bias filter: Only trade in direction of H1 bias
    if h1_bias is not None:
        if (h1_bias == "SELL" and m5_trend == "BULLISH") or (h1_bias == "BUY" and m5_trend == "BEARISH"):
            print(f"\n{t('filter_fail', lang)} {t('h1_conflicts', lang)}. Bỏ qua.")
            return error_count, 0
        else:
            print(f"   {t('aligns', lang)}")
    else:
        print(f"   {t('no_bias', lang)} (Không có cấu trúc rõ ràng, tiếp tục với M5 trend)")
    
    if m5_trend == "NEUTRAL":
        print(f"\n{t('filter_fail', lang)} {t('no_trend', lang)}. Chi tiết: {trend_reason}")
        return error_count, 0
    
    if too_close_to_opposite_zone:
        print(f"\n{t('filter_fail', lang)} {t('too_close_zone', lang)}.")
        return error_count, 0
    else:
        print(f"   {t('has_room', lang)}")

    # === STRATEGY 1: PULLBACK + DOJI/PINBAR CLUSTER ===
    print(f"\n{'='*80}")
    print(f"{t('strategy_1', lang)}")
    print(f"{'='*80}")
    
    is_strat1 = False
    
    # Calculate Fibonacci levels for pullback (38.2-62%)
    # Find recent swing high/low for Fibonacci calculation
    fib_levels = None
    pass_fib = False
    
    print(f"\n{t('fibonacci', lang)}")
    if m5_trend == "BULLISH" and len(m1_swing_highs) >= 1 and len(m1_swing_lows) >= 1:
        # Pullback from high to low
        swing_high = max([s['price'] for s in m1_swing_highs[-3:]])
        swing_low = min([s['price'] for s in m1_swing_lows[-3:]])
        fib_levels = calculate_fibonacci_levels(swing_high, swing_low, 'BULLISH')
        current_price = c1['close']
        print(f"   {t('swing_high', lang)}: {swing_high:.5f} | {t('swing_low', lang)}: {swing_low:.5f}")
        print(f"   Fib 38.2%: {fib_levels['382']:.5f} | Fib 61.8%: {fib_levels['618']:.5f}")
        print(f"   {t('current_price', lang)}: {current_price:.5f}")
        # Check if in 38.2-62% retracement zone
        pass_fib = check_fibonacci_retracement(current_price, fib_levels, 'BULLISH', min_level=0.382, max_level=0.618)
        if pass_fib:
            print(f"   {t('in_zone', lang)} 38.2-62%")
        else:
            print(f"   {t('not_in_zone', lang)} 38.2-62% ({t('required', lang)}: {fib_levels['618']:.5f} - {fib_levels['382']:.5f})")
    elif m5_trend == "BEARISH" and len(m1_swing_highs) >= 1 and len(m1_swing_lows) >= 1:
        # Pullback from low to high
        swing_high = max([s['price'] for s in m1_swing_highs[-3:]])
        swing_low = min([s['price'] for s in m1_swing_lows[-3:]])
        fib_levels = calculate_fibonacci_levels(swing_high, swing_low, 'BEARISH')
        current_price = c1['close']
        print(f"   {t('swing_high', lang)}: {swing_high:.5f} | {t('swing_low', lang)}: {swing_low:.5f}")
        print(f"   Fib 38.2%: {fib_levels['382']:.5f} | Fib 61.8%: {fib_levels['618']:.5f}")
        print(f"   {t('current_price', lang)}: {current_price:.5f}")
        # Check if in 38.2-62% retracement zone
        pass_fib = check_fibonacci_retracement(current_price, fib_levels, 'BEARISH', min_level=0.382, max_level=0.618)
        if pass_fib:
            print(f"   {t('in_zone', lang)} 38.2-62%")
        else:
            print(f"   {t('not_in_zone', lang)} 38.2-62% ({t('required', lang)}: {fib_levels['382']:.5f} - {fib_levels['618']:.5f})")
    else:
        print(f"   {t('not_enough_swing', lang)}")
    
    # Check cluster of 2 signals
    print(f"\n{t('signal_candle', lang)}")
    is_c1_sig = check_signal_candle(c1, m5_trend)
    is_c2_sig = check_signal_candle(c2, m5_trend)
    
    c1_type = "Doji" if is_doji(c1, 0.2) else ("Pinbar" if is_pinbar(c1, type='buy' if m5_trend == "BULLISH" else 'sell') else ("Hammer" if is_hammer(c1) else ("Inverted Hammer" if is_inverted_hammer(c1) else "Normal")))
    c2_type = "Doji" if is_doji(c2, 0.2) else ("Pinbar" if is_pinbar(c2, type='buy' if m5_trend == "BULLISH" else 'sell') else ("Hammer" if is_hammer(c2) else ("Inverted Hammer" if is_inverted_hammer(c2) else "Normal")))
    
    c1_status = t('signal', lang) if is_c1_sig else t('not_signal', lang)
    c2_status = t('signal', lang) if is_c2_sig else t('not_signal', lang)
    print(f"   {t('candle', lang)}-1: {c1_type} | {c1_status}")
    print(f"   {t('candle', lang)}-2: {c2_type} | {c2_status}")
    
    # Check EMA Touch
    is_touch = touches_ema(c1) or touches_ema(c2)
    print(f"\n{t('ema_touch', lang)}")
    print(f"   EMA21: {c1['ema21']:.5f} | EMA50: {c1['ema50']:.5f}")
    c1_touch = touches_ema(c1)
    c2_touch = touches_ema(c2)
    print(f"   {t('candle', lang)}-1 chạm EMA: {t('touches', lang) if c1_touch else t('not_touches', lang)}")
    print(f"   {t('candle', lang)}-2 chạm EMA: {t('touches', lang) if c2_touch else t('not_touches', lang)}")
    if is_touch:
        print(f"   ✅ Ít nhất một nến chạm EMA")
    else:
        print(f"   ❌ Không có nến nào chạm EMA")
    
    # Check smooth pullback (sóng hồi chéo, mượt)
    pullback_candles = df_m1.iloc[-6:-1]  # Last 5 completed candles
    is_smooth = is_smooth_pullback(pullback_candles, m5_trend)
    print(f"\n{t('smooth_pullback', lang)}")
    if is_smooth:
        print(f"   {t('smooth', lang)}")
    else:
        ranges = pullback_candles['high'] - pullback_candles['low']
        avg_range = ranges.mean()
        large_candles = (ranges > avg_range * 2.0).sum()
        print(f"   {t('not_smooth', lang)} ({t('large_candles', lang)}: {large_candles}, {t('avg_range', lang)}: {avg_range:.5f})")
    
    strat1_fail_reasons = []
    if not is_c1_sig: strat1_fail_reasons.append("Candle-1 Not Signal")
    if not is_c2_sig: strat1_fail_reasons.append("Candle-2 Not Signal")
    if not is_touch: strat1_fail_reasons.append("No EMA Touch")
    if not pass_fib: strat1_fail_reasons.append("Not in Fib 38.2-62% zone")
    if not is_smooth: strat1_fail_reasons.append("Pullback not smooth")
    
    if is_c1_sig and is_c2_sig and is_touch and pass_fib and is_smooth:
        signal_type = "BUY" if m5_trend == "BULLISH" else "SELL"
        is_strat1 = True
        reason = "Strat1_Pullback_Cluster_Fib"
        print(f"\n{t('strategy_1_signal', lang)} {signal_type} - {t('all_conditions_met', lang)}!")
        print(f"   {t('reason', lang)}: {reason}")
    else:
        print(f"\n{t('strategy_1_fail', lang)} {t('missing_conditions', lang)}:")
        for reason in strat1_fail_reasons:
            print(f"   - {reason}")
        log_details.append(f"Strat 1 Fail: {', '.join(strat1_fail_reasons)}")

    # === STRATEGY 2: CONTINUATION + STRUCTURE (M/W + COMPRESSION) ===
    print(f"\n{'='*80}")
    print(f"{t('strategy_2', lang)}")
    print(f"{'='*80}")
    
    is_strat2 = False
    strat2_fail_reasons = []
    
    if not is_strat1:
        # Check EMA 200 Filter
        print(f"\n{t('ema200_filter', lang)}")
        pass_ema200 = False
        ema200_val = c1['ema200']
        print(f"   {t('price', lang)}: {c1['close']:.5f} | EMA200: {ema200_val:.5f}")
        if m5_trend == "BULLISH":
             if c1['close'] > ema200_val: 
                 pass_ema200 = True
                 print(f"   {t('filter_passed', lang)} (Bullish)")
             else: 
                 strat2_fail_reasons.append(f"Price {c1['close']:.5f} < EMA200 {ema200_val:.5f}")
                 print(f"   {t('filter_failed', lang)} (Bullish)")
        elif m5_trend == "BEARISH":
             if c1['close'] < ema200_val: 
                 pass_ema200 = True
                 print(f"   {t('filter_passed', lang)} (Bearish)")
             else: 
                 strat2_fail_reasons.append(f"Price {c1['close']:.5f} > EMA200 {ema200_val:.5f}")
                 print(f"   {t('filter_failed', lang)} (Bearish)")
        
        if pass_ema200:
            # Check for previous breakout + retest (including shallow breakout)
            print(f"\n🔍 [Breakout + Retest Check]")
            breakout_level = None
            has_breakout_retest = False
            is_shallow_breakout = False
            
            # Look back 20-50 candles for previous breakout
            lookback_start = max(0, len(df_m1) - 50)
            lookback_end = len(df_m1) - 5
            print(f"   Looking back {lookback_end - lookback_start} candles for breakout")
            
            if m5_trend == "BULLISH":
                # Look for previous high breakout
                for i in range(lookback_start, lookback_end - 10):
                    prev_high = df_m1.iloc[i]['high']
                    breakout_candle_idx = None
                    # Check if price broke above this high
                    broke_above = False
                    for j in range(i + 1, min(i + 15, lookback_end)):
                        if df_m1.iloc[j]['close'] > prev_high:
                            broke_above = True
                            breakout_level = prev_high
                            breakout_candle_idx = j
                            
                            # Check if shallow breakout (impulsive yếu - didn't move far)
                            breakout_leg = df_m1.iloc[j]['close'] - prev_high
                            breakout_range = df_m1.iloc[j]['high'] - df_m1.iloc[j]['low']
                            # If breakout leg is small (< 50% of candle range), it's shallow
                            if breakout_leg < breakout_range * 0.5:
                                is_shallow_breakout = True
                            
                            # Check if price retested this level (came back to it)
                            for k in range(j + 1, min(j + 20, len(df_m1) - 2)):
                                if df_m1.iloc[k]['low'] <= breakout_level * 1.0001 and df_m1.iloc[k]['low'] >= breakout_level * 0.9999:
                                    has_breakout_retest = True
                                    
                                    # For shallow breakout: Check if pullback is 50-100% of breakout leg
                                    if is_shallow_breakout:
                                        pullback_depth = prev_high - df_m1.iloc[k]['low']
                                        pullback_percent = pullback_depth / breakout_leg if breakout_leg > 0 else 0
                                        print(f"   {t('shallow_detected', lang)}: Leg={breakout_leg:.5f}, {t('pullback_percent', lang)}={pullback_percent*100:.1f}%")
                                        if pullback_percent < 0.5 or pullback_percent > 1.0:
                                            has_breakout_retest = False  # Pullback not in 50-100% range
                                            print(f"   {t('not_in_range', lang)} 50-100%")
                                        else:
                                            print(f"   {t('in_range', lang)} (50-100%)")
                                    break
                            if has_breakout_retest:
                                print(f"   {t('breakout_found', lang)}: {t('level', lang)} {breakout_level:.5f} | {t('shallow', lang)}: {is_shallow_breakout}")
                                break
                    if has_breakout_retest:
                        break
            elif m5_trend == "BEARISH":
                # Look for previous low breakout
                for i in range(lookback_start, lookback_end - 10):
                    prev_low = df_m1.iloc[i]['low']
                    breakout_candle_idx = None
                    # Check if price broke below this low
                    broke_below = False
                    for j in range(i + 1, min(i + 15, lookback_end)):
                        if df_m1.iloc[j]['close'] < prev_low:
                            broke_below = True
                            breakout_level = prev_low
                            breakout_candle_idx = j
                            
                            # Check if shallow breakout (impulsive yếu)
                            breakout_leg = prev_low - df_m1.iloc[j]['close']
                            breakout_range = df_m1.iloc[j]['high'] - df_m1.iloc[j]['low']
                            if breakout_leg < breakout_range * 0.5:
                                is_shallow_breakout = True
                            
                            # Check if price retested this level
                            for k in range(j + 1, min(j + 20, len(df_m1) - 2)):
                                if df_m1.iloc[k]['high'] >= breakout_level * 0.9999 and df_m1.iloc[k]['high'] <= breakout_level * 1.0001:
                                    has_breakout_retest = True
                                    
                                    # For shallow breakout: Check pullback 50-100%
                                    if is_shallow_breakout:
                                        pullback_depth = df_m1.iloc[k]['high'] - prev_low
                                        pullback_percent = pullback_depth / breakout_leg if breakout_leg > 0 else 0
                                        print(f"   Shallow Breakout detected: Leg={breakout_leg:.5f}, Pullback={pullback_percent*100:.1f}%")
                                        if pullback_percent < 0.5 or pullback_percent > 1.0:
                                            has_breakout_retest = False
                                            print(f"   ❌ Pullback {pullback_percent*100:.1f}% not in 50-100% range")
                                        else:
                                            print(f"   ✅ Pullback {pullback_percent*100:.1f}% in valid range (50-100%)")
                                    break
                            if has_breakout_retest:
                                print(f"   {t('breakout_found', lang)}: {t('level', lang)} {breakout_level:.5f} | {t('shallow', lang)}: {is_shallow_breakout}")
                                break
                    if has_breakout_retest:
                        break
            
            if not has_breakout_retest:
                print(f"   {t('breakout_not_found', lang)}")
            
            # Calculate Fibonacci for Strategy 2 (38.2-79%)
            print(f"\n{t('fibonacci', lang)} (Strategy 2)")
            fib_levels_strat2 = None
            pass_fib_strat2 = False
            
            if m1_swing_highs and m1_swing_lows:
                if m5_trend == "BULLISH":
                    swing_high = max([s['price'] for s in m1_swing_highs[-3:]])
                    swing_low = min([s['price'] for s in m1_swing_lows[-3:]])
                    fib_levels_strat2 = calculate_fibonacci_levels(swing_high, swing_low, 'BULLISH')
                    current_price = c1['close']
                    print(f"   {t('swing_high', lang)}: {swing_high:.5f} | {t('swing_low', lang)}: {swing_low:.5f}")
                    print(f"   Fib 38.2%: {fib_levels_strat2['382']:.5f} | Fib 78.6%: {fib_levels_strat2['786']:.5f}")
                    print(f"   {t('current_price', lang)}: {current_price:.5f}")
                    pass_fib_strat2 = check_fibonacci_retracement(current_price, fib_levels_strat2, 'BULLISH', min_level=0.382, max_level=0.786)
                    if pass_fib_strat2:
                        print(f"   {t('in_zone', lang)} 38.2-79%")
                    else:
                        print(f"   {t('not_in_zone', lang)} 38.2-79% ({t('required', lang)}: {fib_levels_strat2['786']:.5f} - {fib_levels_strat2['382']:.5f})")
                elif m5_trend == "BEARISH":
                    swing_high = max([s['price'] for s in m1_swing_highs[-3:]])
                    swing_low = min([s['price'] for s in m1_swing_lows[-3:]])
                    fib_levels_strat2 = calculate_fibonacci_levels(swing_high, swing_low, 'BEARISH')
                    current_price = c1['close']
                    print(f"   {t('swing_high', lang)}: {swing_high:.5f} | {t('swing_low', lang)}: {swing_low:.5f}")
                    print(f"   Fib 38.2%: {fib_levels_strat2['382']:.5f} | Fib 78.6%: {fib_levels_strat2['786']:.5f}")
                    print(f"   {t('current_price', lang)}: {current_price:.5f}")
                    pass_fib_strat2 = check_fibonacci_retracement(current_price, fib_levels_strat2, 'BEARISH', min_level=0.382, max_level=0.786)
                    if pass_fib_strat2:
                        print(f"   {t('in_zone', lang)} 38.2-79%")
                    else:
                        print(f"   {t('not_in_zone', lang)} 38.2-79% ({t('required', lang)}: {fib_levels_strat2['382']:.5f} - {fib_levels_strat2['786']:.5f})")
            else:
                print(f"   {t('not_enough_swing', lang)}")
            
            # Check Compression
            print(f"\n{t('compression', lang)}")
            recent_block = df_m1.iloc[-5:-1]
            is_compressed = check_compression_block(recent_block)
            if is_compressed:
                print(f"   {t('compression_detected', lang)} ({len(recent_block)} {t('candles', lang)})")
            else:
                print(f"   {t('no_compression', lang)}")
            
            # Check Pattern (with EMA50 and EMA200 for condition 7)
            print(f"\n{t('pattern', lang)}")
            pattern_type = 'W' if m5_trend == "BULLISH" else 'M'
            is_pattern = detect_pattern(recent_block, type=pattern_type, 
                                       ema50_val=c1['ema50'], ema200_val=c1['ema200'])
            if is_pattern:
                print(f"   {t('pattern_detected', lang)} {pattern_type}")
            else:
                print(f"   {t('no_pattern', lang)} {pattern_type}")
            
            # Check Signal Candle in Compression Block (NEW - Document requirement)
            print(f"\n{t('signal_candle_compression', lang)}")
            has_signal_candle = False
            if is_compressed:
                has_signal_candle = check_signal_candle_in_compression(recent_block, m5_trend, 
                                                                       ema50_val=c1['ema50'], 
                                                                       ema200_val=c1['ema200'])
                if has_signal_candle:
                    signal_candle = recent_block.iloc[-1]
                    print(f"   {t('valid_signal_candle', lang)}")
                    print(f"      {t('close', lang)}: {signal_candle['close']:.5f} | {t('body', lang)}: {abs(signal_candle['close'] - signal_candle['open']):.5f}")
                    print(f"      {t('range', lang)}: {signal_candle['high']:.5f} - {signal_candle['low']:.5f}")
                else:
                    print(f"   {t('invalid_signal_candle', lang)}")
            else:
                print(f"   ⚠️ Không có compression block, bỏ qua kiểm tra Signal Candle")
            
            if not is_compressed and not is_pattern:
                strat2_fail_reasons.append("No Compression OR Pattern found")
            if is_compressed and not has_signal_candle:
                strat2_fail_reasons.append("Compression found but no valid Signal Candle")
            if not pass_fib_strat2:
                strat2_fail_reasons.append("Not in Fib 38.2-79% zone")
            if not has_breakout_retest:
                strat2_fail_reasons.append("No Breakout+Retest found")
            
            # Check EMA Touch (Retest) - Can be EMA or breakout level
            print(f"\n{t('ema_breakout_touch', lang)}")
            block_touch = False
            touch_details = []
            for idx, row in recent_block.iterrows():
                if touches_ema(row):
                    block_touch = True
                    touch_details.append(f"{t('candle', lang)} tại index {idx} chạm EMA")
                    break
                # Also check if touching breakout level
                if breakout_level and (row['low'] <= breakout_level * 1.0001 and row['high'] >= breakout_level * 0.9999):
                    block_touch = True
                    touch_details.append(f"{t('candle', lang)} tại index {idx} chạm {t('level', lang)} Breakout {breakout_level:.5f}")
                    break
            
            if block_touch:
                print(f"   {t('block_touches', lang)}")
                for detail in touch_details:
                    print(f"      - {detail}")
            else:
                print(f"   {t('block_not_touches', lang)}")
                strat2_fail_reasons.append("Block didn't touch EMA or Breakout Level")
            
            # For Compression: Need signal candle. For Pattern: Don't need signal candle.
            compression_valid = is_compressed and has_signal_candle and block_touch
            pattern_valid = is_pattern and block_touch
            
            print(f"\n{t('strategy_2_summary', lang)}")
            print(f"   Compression Block: {'✅' if is_compressed else '❌'}")
            print(f"   Signal Candle: {'✅' if has_signal_candle else '❌'}")
            print(f"   Pattern ({pattern_type}): {'✅' if is_pattern else '❌'}")
            print(f"   Fibonacci 38.2-79%: {'✅' if pass_fib_strat2 else '❌'}")
            print(f"   Breakout+Retest: {'✅' if has_breakout_retest else '❌'}")
            print(f"   EMA/Breakout Touch: {'✅' if block_touch else '❌'}")
            
            if (compression_valid or pattern_valid) and pass_fib_strat2:
                 signal_type = "BUY" if m5_trend == "BULLISH" else "SELL"
                 is_strat2 = True
                 reason = f"Strat2_Continuation_{'Compression' if is_compressed else 'Pattern'}_BreakoutRetest"
                 print(f"\n{t('strategy_2_signal', lang)} {signal_type} - {t('all_conditions_met', lang)}!")
                 print(f"   {t('reason', lang)}: {reason}")
            else:
                print(f"\n{t('strategy_2_fail', lang)} {t('missing_conditions', lang)}:")
                for reason in strat2_fail_reasons:
                    print(f"   - {reason}")
        else:
             strat2_fail_reasons.append("EMA200 Filter Fail")
             print(f"\n{t('strategy_2_fail', lang)} EMA200 Filter failed")

        if not is_strat2:
             log_details.append(f"Strat 2 Fail: {', '.join(strat2_fail_reasons)}")

    # --- Logging ---
    # Fix: Use signal_type only, not m5_trend (could be wrong if signal is SELL but trend is BULLISH)
    price = mt5.symbol_info_tick(symbol).ask if signal_type == "BUY" else mt5.symbol_info_tick(symbol).bid
    
    # Final Summary
    print(f"\n{'='*80}")
    print(f"📊 [FINAL SUMMARY]")
    print(f"{'='*80}")
    
    if not signal_type:
        print(f"❌ [NO SIGNAL] Price: {price:.5f}")
        print(f"   Reasons: { ' | '.join(log_details) }")
        return error_count, 0
    else:
        print(f"✅ [SIGNAL FOUND] {signal_type} | Reason: {reason}")
        print(f"   Price: {price:.5f}")
        
    # --- 5. Execution Trigger ---
    if is_strat1:
        trigger_high = max(c1['high'], c2['high'])
        trigger_low = min(c1['low'], c2['low'])
    else: # Strat 2
        recent_block = df_m1.iloc[-5:-1]
        trigger_high = recent_block['high'].max()
        trigger_low = recent_block['low'].min()
        
    execute = False
    sl = 0.0
    tp = 0.0
    # Fix: Check NaN for ATR, use default if NaN
    atr_val = c1['atr']
    if pd.isna(atr_val) or atr_val <= 0:
        # Default ATR fallback (use recent price range as estimate)
        recent_range = df_m1.iloc[-14:]['high'].max() - df_m1.iloc[-14:]['low'].min()
        atr_val = recent_range / 14 if recent_range > 0 else 0.0001
        print(f"   ⚠️ ATR is NaN, using fallback: {atr_val:.5f}")
    
    if signal_type == "BUY":
        if price > trigger_high:
            execute = True
            sl = price - (2 * atr_val)
            tp = price + (4 * atr_val)
        else:
            distance = trigger_high - price
            print(f"   {t('waiting_breakout', lang)} > {trigger_high:.5f} ({t('current_price', lang)}: {price:.5f}, {t('need', lang)}: {distance:.5f})")
    elif signal_type == "SELL":
        if price < trigger_low:
            execute = True
            sl = price + (2 * atr_val)
            tp = price - (4 * atr_val)
        else:
            distance = price - trigger_low
            print(f"   {t('waiting_breakout', lang)} < {trigger_low:.5f} ({t('current_price', lang)}: {price:.5f}, {t('need', lang)}: {distance:.5f})")
            
    if execute:
        print(f"\n{'='*80}")
        print(f"{t('execution', lang)}")
        print(f"{'='*80}")
        
        # Spam Filter (60s) - Fix: Convert datetime to timestamp
        print(f"\n{t('spam_filter', lang)}")
        strat_positions = mt5.positions_get(symbol=symbol, magic=magic)
        if strat_positions:
            strat_positions = sorted(strat_positions, key=lambda x: x.time, reverse=True)
            last_trade_time = strat_positions[0].time
            current_time = mt5.symbol_info_tick(symbol).time
            # Convert to timestamp if needed (MT5 returns datetime)
            if isinstance(last_trade_time, datetime):
                last_trade_timestamp = last_trade_time.timestamp()
            else:
                last_trade_timestamp = last_trade_time
            if isinstance(current_time, datetime):
                current_timestamp = current_time.timestamp()
            else:
                current_timestamp = current_time
            
            time_since_last = current_timestamp - last_trade_timestamp
            print(f"   {t('last_trade', lang)}: {time_since_last:.0f} {t('seconds_ago', lang)}")
            if time_since_last < 60:
                print(f"   ⏳ Lệnh gần đây ({time_since_last:.0f}s < 60s). Đang chờ.")
                return error_count, 0
            else:
                print(f"   {t('cooldown_passed', lang)} ({time_since_last:.0f}s >= 60s)")
        else:
            print(f"   {t('no_recent_trades', lang)}")

        print(f"\n{t('signal_execute', lang)} {signal_type} @ {price:.5f} | {reason}")
        print(f"   SL: {sl:.5f} (2x ATR) | TP: {tp:.5f} (4x ATR) | R:R = 1:2")
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal_type == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": reason,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(result.order, "Tuyen_Trend", symbol, signal_type, volume, price, sl, tp, reason, account_id=config['account'])
            
             # Telegram
            msg = (
                f"✅ <b>Tuyen Trend Bot Triggered</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal_type})\n"
                f"📋 <b>Reason:</b> {reason}\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.5f} | 🎯 <b>TP:</b> {tp:.5f}\n"
            )
            send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
            return 0, 0
        else:
            print(f"❌ Order Failed: {result.retcode} - {result.comment}")
            return error_count + 1, result.retcode

    return error_count, 0

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_tuyen_xau.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    if config and connect_mt5(config):
        print("✅ Tuyen Trend Bot (V2) - Started")
        try:
            while True:
                consecutive_errors, last_error = tuyen_trend_logic(config, consecutive_errors)
                if consecutive_errors >= 5:
                    print("⚠️ Too many errors. Pausing...")
                    time.sleep(120)
                    consecutive_errors = 0
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
