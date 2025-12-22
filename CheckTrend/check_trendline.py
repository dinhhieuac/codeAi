"""
Bot Check Trendline - 5 Bước Xác Định Long/Short
Dựa trên tài liệu: 5_buoc_xac_dinh_long_short_BTC.md

B1: Xác định Trendline (swing high/low)
B2: Xác định Mô hình giá (Flag, Triangle, Channel, H&S, Double Top/Bottom, Wedge)
B3: Kẻ Fibonacci (0.382-0.618 cho entry, 1.0-1.618 cho TP)
B4: Vẽ Hỗ trợ/Kháng cự (Supply/Demand zones)
B5: Tổng hợp quyết định Long/Short
"""

import MetaTrader5 as mt5
import pandas as pd
import json
import os
import requests
import time
import numpy as np
from datetime import datetime
from typing import List, Tuple, Optional, Dict

# ==============================================================================
# 1. CẤU HÌNH
# ==============================================================================

def load_config(filename="CheckTrend/mt5_account.json"):
    if not os.path.exists(filename):
        return None
    with open(filename, 'r') as f:
        return json.load(f)

config = load_config()
if not config:
    print("Config not found")
    quit()

MT5_LOGIN = config.get("ACCOUNT_NUMBER")
MT5_PASSWORD = config.get("PASSWORD")
MT5_SERVER = config.get("SERVER")
MT5_PATH = config.get("PATH")

# Telegram Configuration
TELEGRAM_TOKEN = config.get("TELEGRAM_TOKEN", "6398751744:AAGp7VH7B00_kzMqdaFB59xlqAXnlKTar-g")
CHAT_ID = config.get("CHAT_ID", "1887610382")

# Symbols để check (ưu tiên BTC, ETH)
SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "BNBUSD"]

# ==============================================================================
# 2. KẾT NỐI MT5
# ==============================================================================

def initialize_mt5():
    """Khởi tạo và kết nối MT5."""
    print("\n--- Bắt đầu kết nối MT5 ---")
    
    if not mt5.initialize(path=MT5_PATH, 
                         login=MT5_LOGIN, 
                         password=MT5_PASSWORD, 
                         server=MT5_SERVER):
        print(f"Lần 1 thất bại ({mt5.last_error()}). Thử lại không dùng PATH...")
        if not mt5.initialize(login=MT5_LOGIN, 
                               password=MT5_PASSWORD, 
                               server=MT5_SERVER):
            print(f"❌ KHỞI TẠO THẤT BẠI. Lỗi: {mt5.last_error()}")
            return False
        else:
            print("✅ Kết nối MT5 thành công (Sử dụng phiên MT5 đang chạy sẵn).")
    else:
        print(f"✅ Đăng nhập tài khoản {MT5_LOGIN} trên server {MT5_SERVER} thành công.")
    
    account_info = mt5.account_info()
    if account_info is None:
        print(f"❌ Không thể lấy thông tin tài khoản. Lỗi: {mt5.last_error()}")
        return False
    
    print(f"✅ Tài khoản: {account_info.login}, Server: {account_info.server}")
    return True

# ==============================================================================
# 3. B1: TÌM SWING HIGH/LOW VÀ VẼ TRENDLINE
# ==============================================================================

def find_swing_points(df, lookback=5, min_swing_size=None):
    """
    Tìm swing high và swing low
    
    Args:
        df: DataFrame với OHLC data
        lookback: Số nến để xác định swing (mặc định 5)
        min_swing_size: Kích thước tối thiểu của swing (tính bằng ATR)
    
    Returns:
        swing_highs: List of (index, price) tuples
        swing_lows: List of (index, price) tuples
    """
    swing_highs = []
    swing_lows = []
    
    if len(df) < lookback * 2 + 1:
        return swing_highs, swing_lows
    
    # Tính ATR để filter swing nhỏ
    if min_swing_size is None:
        # Tính ATR đơn giản
        high_low = df['high'] - df['low']
        atr = high_low.rolling(window=14).mean().iloc[-1]
        min_swing_size = atr * 0.5 if not pd.isna(atr) else 0
    
    for i in range(lookback, len(df) - lookback):
        # Kiểm tra swing high
        is_swing_high = True
        current_high = df.iloc[i]['high']
        
        # Kiểm tra tất cả nến trong lookback window
        for j in range(i - lookback, i + lookback + 1):
            if j != i and df.iloc[j]['high'] >= current_high:
                is_swing_high = False
                break
        
        if is_swing_high:
            # Kiểm tra kích thước swing
            if min_swing_size > 0:
                # Tìm đáy gần nhất trước swing high
                for k in range(i - 1, max(0, i - lookback * 2), -1):
                    if df.iloc[k]['low'] < current_high - min_swing_size:
                        swing_highs.append((i, current_high))
                        break
            else:
                swing_highs.append((i, current_high))
        
        # Kiểm tra swing low
        is_swing_low = True
        current_low = df.iloc[i]['low']
        
        for j in range(i - lookback, i + lookback + 1):
            if j != i and df.iloc[j]['low'] <= current_low:
                is_swing_low = False
                break
        
        if is_swing_low:
            # Kiểm tra kích thước swing
            if min_swing_size > 0:
                # Tìm đỉnh gần nhất trước swing low
                for k in range(i - 1, max(0, i - lookback * 2), -1):
                    if df.iloc[k]['high'] > current_low + min_swing_size:
                        swing_lows.append((i, current_low))
                        break
            else:
                swing_lows.append((i, current_low))
    
    return swing_highs, swing_lows

def calculate_trendline(swing_points: List[Tuple[int, float]], current_index: int) -> Optional[Dict]:
    """
    Tính trendline từ các swing points
    
    Args:
        swing_points: List of (index, price) tuples
        current_index: Index hiện tại để tính giá trị trendline
    
    Returns:
        Dict với slope, intercept, direction, hoặc None nếu không đủ điểm
    """
    if len(swing_points) < 2:
        return None
    
    # Lấy 2 điểm gần nhất
    recent_points = sorted(swing_points, key=lambda x: x[0], reverse=True)[:2]
    if len(recent_points) < 2:
        return None
    
    point1_idx, point1_price = recent_points[1]  # Điểm cũ hơn
    point2_idx, point2_price = recent_points[0]  # Điểm mới hơn
    
    # Tính slope và intercept
    if point2_idx == point1_idx:
        return None
    
    slope = (point2_price - point1_price) / (point2_idx - point1_idx)
    intercept = point1_price - slope * point1_idx
    
    # Tính giá trị trendline tại current_index
    trendline_value = slope * current_index + intercept
    
    # Xác định hướng
    direction = "UP" if slope > 0 else "DOWN" if slope < 0 else "HORIZONTAL"
    
    return {
        'slope': slope,
        'intercept': intercept,
        'direction': direction,
        'value_at_current': trendline_value,
        'point1': (point1_idx, point1_price),
        'point2': (point2_idx, point2_price),
        'strength': abs(slope)  # Độ dốc càng lớn, trendline càng mạnh
    }

def check_trendline_break(df, trendline: Dict, tolerance=0.001) -> Tuple[bool, bool, str]:
    """
    Kiểm tra giá có phá vỡ trendline không (V2 - Rule Cứng)
    
    Returns:
        (is_broken, is_invalidated, message)
        - is_broken: Giá đã phá trendline
        - is_invalidated: Trendline mất hiệu lực (giá đóng nến phá)
    """
    if trendline is None:
        return False, False, "Không có trendline"
    
    # Lấy nến đã đóng cửa (nến cuối cùng đã hoàn thành)
    if len(df) < 2:
        current_price = df.iloc[-1]['close']
    else:
        current_price = df.iloc[-2]['close']  # Nến đã đóng cửa
    
    trendline_value = trendline['value_at_current']
    direction = trendline['direction']
    
    # Kiểm tra break (giá đóng nến phá trendline)
    is_broken = False
    is_invalidated = False
    
    if direction == "UP":
        # Uptrend: giá phá xuống dưới trendline
        if current_price < trendline_value * (1 - tolerance):
            is_broken = True
            is_invalidated = True  # Rule cứng: giá đóng nến phá → mất hiệu lực
            return True, True, f"⛔ Trendline TĂNG đã bị PHÁ (mất hiệu lực) - Giá: {current_price:.5f} < Trendline: {trendline_value:.5f} - KHÔNG trade BUY theo hướng cũ"
    elif direction == "DOWN":
        # Downtrend: giá phá lên trên trendline
        if current_price > trendline_value * (1 + tolerance):
            is_broken = True
            is_invalidated = True  # Rule cứng: giá đóng nến phá → mất hiệu lực
            return True, True, f"⛔ Trendline GIẢM đã bị PHÁ (mất hiệu lực) - Giá: {current_price:.5f} > Trendline: {trendline_value:.5f} - KHÔNG trade SELL theo hướng cũ"
    
    return False, False, f"✅ Giá vẫn trong trendline ({direction})"

# ==============================================================================
# 4. B2: PHÁT HIỆN MÔ HÌNH GIÁ
# ==============================================================================

def detect_price_patterns(df, swing_highs, swing_lows, trendline_direction=None):
    """
    Phát hiện các mô hình giá (V2):
    - Tiếp diễn: Flag, Triangle, Channel → Trade theo hướng trendline
    - Đảo chiều: Head & Shoulders, Double Top/Bottom, Falling/Rising Wedge
      → Ngược trend → độ tin cậy thấp, chỉ dùng khi trùng Supply/Demand mạnh
    """
    patterns = []
    
    if len(df) < 20:
        return patterns
    
    # 1. Double Top / Double Bottom
    if len(swing_highs) >= 2:
        last_two_highs = sorted(swing_highs, key=lambda x: x[0], reverse=True)[:2]
        if len(last_two_highs) == 2:
            idx1, price1 = last_two_highs[1]
            idx2, price2 = last_two_highs[0]
            price_diff = abs(price1 - price2) / max(price1, price2)
            
            if price_diff < 0.01:  # 2 đỉnh gần bằng nhau (< 1%)
                # V2: Kiểm tra nếu ngược trend → giảm confidence
                confidence = 'HIGH' if price_diff < 0.005 else 'MEDIUM'
                if trendline_direction == "DOWN":
                    # Đảo chiều ngược trend → độ tin cậy thấp
                    confidence = 'LOW'
                
                patterns.append({
                    'type': 'DOUBLE_TOP',
                    'pattern': 'Đảo chiều',
                    'signal': 'BEARISH',
                    'confidence': confidence,
                    'price1': price1,
                    'price2': price2,
                    'neckline': min(df.iloc[idx1]['low'], df.iloc[idx2]['low'])
                })
    
    if len(swing_lows) >= 2:
        last_two_lows = sorted(swing_lows, key=lambda x: x[0], reverse=True)[:2]
        if len(last_two_lows) == 2:
            idx1, price1 = last_two_lows[1]
            idx2, price2 = last_two_lows[0]
            price_diff = abs(price1 - price2) / max(price1, price2)
            
            if price_diff < 0.01:  # 2 đáy gần bằng nhau
                # V2: Kiểm tra nếu ngược trend → giảm confidence
                confidence = 'HIGH' if price_diff < 0.005 else 'MEDIUM'
                if trendline_direction == "UP":
                    # Đảo chiều ngược trend → độ tin cậy thấp
                    confidence = 'LOW'
                
                patterns.append({
                    'type': 'DOUBLE_BOTTOM',
                    'pattern': 'Đảo chiều',
                    'signal': 'BULLISH',
                    'confidence': confidence,
                    'price1': price1,
                    'price2': price2,
                    'neckline': max(df.iloc[idx1]['high'], df.iloc[idx2]['high'])
                })
    
    # 2. Triangle (Ascending/Descending/Symmetrical)
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        recent_highs = sorted(swing_highs, key=lambda x: x[0], reverse=True)[:2]
        recent_lows = sorted(swing_lows, key=lambda x: x[0], reverse=True)[:2]
        
        if len(recent_highs) == 2 and len(recent_lows) == 2:
            high1, high2 = recent_highs[1][1], recent_highs[0][1]
            low1, low2 = recent_lows[1][1], recent_lows[0][1]
            
            # Ascending Triangle: highs ngang, lows tăng
            if abs(high1 - high2) / max(high1, high2) < 0.01 and low2 > low1:
                patterns.append({
                    'type': 'ASCENDING_TRIANGLE',
                    'pattern': 'Tiếp diễn',
                    'signal': 'BULLISH',
                    'confidence': 'MEDIUM'
                })
            
            # Descending Triangle: lows ngang, highs giảm
            elif abs(low1 - low2) / max(low1, low2) < 0.01 and high2 < high1:
                patterns.append({
                    'type': 'DESCENDING_TRIANGLE',
                    'pattern': 'Tiếp diễn',
                    'signal': 'BEARISH',
                    'confidence': 'MEDIUM'
                })
    
    # 3. Channel (Uptrend/Downtrend Channel)
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        recent_highs = sorted(swing_highs, key=lambda x: x[0], reverse=True)[:3]
        recent_lows = sorted(swing_lows, key=lambda x: x[0], reverse=True)[:3]
        
        if len(recent_highs) >= 2 and len(recent_lows) >= 2:
            # Tính slope của highs và lows
            high_slope = (recent_highs[0][1] - recent_highs[1][1]) / (recent_highs[0][0] - recent_highs[1][0])
            low_slope = (recent_lows[0][1] - recent_lows[1][1]) / (recent_lows[0][0] - recent_lows[1][0])
            
            # Nếu cả 2 đều tăng và song song → Uptrend Channel
            if high_slope > 0 and low_slope > 0 and abs(high_slope - low_slope) / max(abs(high_slope), abs(low_slope)) < 0.3:
                patterns.append({
                    'type': 'UPTREND_CHANNEL',
                    'pattern': 'Tiếp diễn',
                    'signal': 'BULLISH',
                    'confidence': 'MEDIUM'
                })
            
            # Nếu cả 2 đều giảm và song song → Downtrend Channel
            elif high_slope < 0 and low_slope < 0 and abs(high_slope - low_slope) / max(abs(high_slope), abs(low_slope)) < 0.3:
                patterns.append({
                    'type': 'DOWNTREND_CHANNEL',
                    'pattern': 'Tiếp diễn',
                    'signal': 'BEARISH',
                    'confidence': 'MEDIUM'
                })
    
    # 4. Wedge (Falling/Rising)
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        recent_highs = sorted(swing_highs, key=lambda x: x[0], reverse=True)[:2]
        recent_lows = sorted(swing_lows, key=lambda x: x[0], reverse=True)[:2]
        
        if len(recent_highs) == 2 and len(recent_lows) == 2:
            high_slope = (recent_highs[0][1] - recent_highs[1][1]) / (recent_highs[0][0] - recent_highs[1][0])
            low_slope = (recent_lows[0][1] - recent_lows[1][1]) / (recent_lows[0][0] - recent_lows[1][0])
            
            # Rising Wedge: cả 2 đều tăng nhưng highs tăng nhanh hơn → Bearish
            if high_slope > 0 and low_slope > 0 and high_slope > low_slope * 1.2:
                patterns.append({
                    'type': 'RISING_WEDGE',
                    'pattern': 'Đảo chiều',
                    'signal': 'BEARISH',
                    'confidence': 'MEDIUM'
                })
            
            # Falling Wedge: cả 2 đều giảm nhưng lows giảm nhanh hơn → Bullish
            elif high_slope < 0 and low_slope < 0 and abs(low_slope) > abs(high_slope) * 1.2:
                patterns.append({
                    'type': 'FALLING_WEDGE',
                    'pattern': 'Đảo chiều',
                    'signal': 'BULLISH',
                    'confidence': 'MEDIUM'
                })
    
    return patterns

# ==============================================================================
# 5. B3: TÍNH FIBONACCI
# ==============================================================================

def calculate_fibonacci_levels(swing_high, swing_low):
    """
    Tính Fibonacci retracement và extension levels
    
    Args:
        swing_high: (index, price) của swing high
        swing_low: (index, price) của swing low
    
    Returns:
        Dict với các mức Fibonacci
    """
    if swing_high is None or swing_low is None:
        return None
    
    high_idx, high_price = swing_high
    low_idx, low_price = swing_low
    
    # Xác định hướng (từ low lên high hay từ high xuống low)
    if high_idx > low_idx:
        # Uptrend: từ low lên high
        diff = high_price - low_price
        trend = "UP"
    else:
        # Downtrend: từ high xuống low
        diff = low_price - high_price
        trend = "DOWN"
        # Swap để luôn tính từ low lên high
        high_price, low_price = low_price, high_price
    
    # Fibonacci Retracement levels (cho entry)
    fib_levels = {
        '0.0': low_price,
        '0.236': low_price + diff * 0.236,
        '0.382': low_price + diff * 0.382,
        '0.5': low_price + diff * 0.5,
        '0.618': low_price + diff * 0.618,
        '0.786': low_price + diff * 0.786,
        '1.0': high_price,
        # Extension levels (cho TP)
        '1.272': high_price + diff * 0.272,
        '1.618': high_price + diff * 0.618,
        '2.0': high_price + diff * 1.0
    }
    
    fib_levels['trend'] = trend
    fib_levels['swing_high'] = swing_high
    fib_levels['swing_low'] = swing_low
    
    return fib_levels

def find_current_fib_level(current_price, fib_levels):
    """
    Tìm Fibonacci level gần nhất với giá hiện tại (V2)
    
    Returns:
        (level_name, distance, is_premium_zone)
        - is_premium_zone: True nếu trong vùng 0.5-0.618 (vùng đẹp nhất)
    """
    if fib_levels is None:
        return None, None, False
    
    min_distance = float('inf')
    closest_level = None
    is_premium_zone = False
    
    for level_name, level_price in fib_levels.items():
        if level_name in ['trend', 'swing_high', 'swing_low']:
            continue
        
        distance = abs(current_price - level_price)
        if distance < min_distance:
            min_distance = distance
            closest_level = level_name
            # V2: Vùng 0.5-0.618 là vùng đẹp nhất
            is_premium_zone = (level_name in ['0.5', '0.618'])
    
    return closest_level, min_distance, is_premium_zone

# ==============================================================================
# 6. B4: SUPPLY/DEMAND ZONES (Tái sử dụng từ check_trend.py)
# ==============================================================================

def find_supply_demand_zones(df, lookback=100, fib_levels=None, trendline=None):
    """
    Tìm vùng supply và demand (V2)
    Tín hiệu mạnh nhất khi trùng Fibo hoặc trùng trendline retest
    """
    supply_zones = []
    demand_zones = []
    
    if len(df) < lookback:
        lookback = len(df)
    
    recent_data = df.iloc[-lookback:].copy()
    recent_data = recent_data.reset_index(drop=True)
    
    # Tính ATR
    high_low = recent_data['high'] - recent_data['low']
    atr = high_low.rolling(window=14).mean().iloc[-1]
    min_zone_size = atr * 0.5 if not pd.isna(atr) else 0
    
    avg_volume = recent_data['tick_volume'].mean()
    
    # Tìm supply zones (đỉnh với volume cao)
    for i in range(7, len(recent_data) - 7):
        is_peak = True
        for j in range(i-5, i+6):
            if j != i and j >= 0 and j < len(recent_data):
                if recent_data.iloc[j]['high'] >= recent_data.iloc[i]['high']:
                    is_peak = False
                    break
        
        if is_peak:
            high_price = recent_data.iloc[i]['high']
            low_price = recent_data.iloc[i]['low']
            zone_size = high_price - low_price
            
            if zone_size >= min_zone_size:
                volume = recent_data.iloc[i]['tick_volume']
                if volume > avg_volume * 1.2:
                    zone_info = {
                        'price': high_price,
                        'zone_low': low_price,
                        'volume_ratio': volume / avg_volume if avg_volume > 0 else 0,
                        'index': i,
                        'strength': 1.0  # Base strength
                    }
                    
                    # V2: Tín hiệu mạnh nhất khi trùng Fibo hoặc trendline
                    if fib_levels:
                        # Check if zone trùng với Fibo levels
                        for level_name, fib_price in fib_levels.items():
                            if level_name not in ['trend', 'swing_high', 'swing_low']:
                                if abs(high_price - fib_price) / high_price < 0.01:  # Trùng trong 1%
                                    zone_info['strength'] = 2.0
                                    zone_info['fib_level'] = level_name
                                    break
                    
                    if trendline:
                        # Check if zone trùng với trendline retest
                        trendline_value = trendline.get('value_at_current', 0)
                        if abs(high_price - trendline_value) / high_price < 0.01:
                            zone_info['strength'] = max(zone_info['strength'], 2.0)
                            zone_info['trendline_retest'] = True
                    
                    supply_zones.append(zone_info)
    
    # Tìm demand zones (đáy với volume cao)
    for i in range(7, len(recent_data) - 7):
        is_trough = True
        for j in range(i-5, i+6):
            if j != i and j >= 0 and j < len(recent_data):
                if recent_data.iloc[j]['low'] <= recent_data.iloc[i]['low']:
                    is_trough = False
                    break
        
        if is_trough:
            low_price = recent_data.iloc[i]['low']
            high_price = recent_data.iloc[i]['high']
            zone_size = high_price - low_price
            
            if zone_size >= min_zone_size:
                volume = recent_data.iloc[i]['tick_volume']
                if volume > avg_volume * 1.2:
                    zone_info = {
                        'price': low_price,
                        'zone_high': high_price,
                        'volume_ratio': volume / avg_volume if avg_volume > 0 else 0,
                        'index': i,
                        'strength': 1.0  # Base strength
                    }
                    
                    # V2: Tín hiệu mạnh nhất khi trùng Fibo hoặc trendline
                    if fib_levels:
                        # Check if zone trùng với Fibo levels
                        for level_name, fib_price in fib_levels.items():
                            if level_name not in ['trend', 'swing_high', 'swing_low']:
                                if abs(low_price - fib_price) / low_price < 0.01:  # Trùng trong 1%
                                    zone_info['strength'] = 2.0
                                    zone_info['fib_level'] = level_name
                                    break
                    
                    if trendline:
                        # Check if zone trùng với trendline retest
                        trendline_value = trendline.get('value_at_current', 0)
                        if abs(low_price - trendline_value) / low_price < 0.01:
                            zone_info['strength'] = max(zone_info['strength'], 2.0)
                            zone_info['trendline_retest'] = True
                    
                    demand_zones.append(zone_info)
    
    # Sắp xếp theo index (gần nhất)
    supply_zones.sort(key=lambda x: x['index'], reverse=True)
    demand_zones.sort(key=lambda x: x['index'], reverse=True)
    
    return supply_zones[:3], demand_zones[:3]

# ==============================================================================
# 7. B5: TỔNG HỢP QUYẾT ĐỊNH LONG/SHORT
# ==============================================================================

def make_decision(df, trendline, patterns, fib_levels, supply_zones, demand_zones, current_price):
    """
    Tổng hợp tất cả thông tin để đưa ra quyết định Long/Short (V2 - Checklist A+)
    
    Returns:
        Dict với signal, confidence, và lý do
    """
    decision = {
        'signal': 'NEUTRAL',
        'confidence': 'LOW',
        'reasons': [],
        'entry_levels': [],
        'tp_levels': [],
        'sl_levels': [],
        'checklist_buy': [],
        'checklist_sell': []
    }
    
    buy_score = 0
    sell_score = 0
    reasons_buy = []
    reasons_sell = []
    checklist_buy = []
    checklist_sell = []
    
    # V2: Rule cứng - Kiểm tra trendline break trước
    trendline_invalidated = False
    trendline_broken = False
    
    # 1. Trendline (V2 - Rule Cứng)
    if trendline:
        # Kiểm tra break (giá đóng nến phá trendline)
        is_broken, is_invalidated, break_msg = check_trendline_break(df, trendline)
        trendline_broken = is_broken
        trendline_invalidated = is_invalidated
        
        if is_invalidated:
            # Rule cứng: Trendline mất hiệu lực → KHÔNG trade theo hướng cũ
            if trendline['direction'] == "UP":
                reasons_sell.append("⛔ " + break_msg)
                checklist_sell.append("❌ Trendline TĂNG đã bị phá - CẤM SELL")
            elif trendline['direction'] == "DOWN":
                reasons_buy.append("⛔ " + break_msg)
                checklist_buy.append("❌ Trendline GIẢM đã bị phá - CẤM BUY")
        else:
            # Trendline còn hiệu lực
            if trendline['direction'] == "UP":
                buy_score += 3  # Tăng điểm vì là điều kiện quan trọng
                reasons_buy.append("✅ Trendline TĂNG (chưa bị phá)")
                checklist_buy.append("✅ Trendline TĂNG hoặc breakout + retest thành công")
            elif trendline['direction'] == "DOWN":
                sell_score += 3
                reasons_sell.append("✅ Trendline GIẢM (chưa bị phá)")
                checklist_sell.append("✅ Trendline GIẢM (chưa bị phá)")
    
    # 2. Mô hình giá (V2 - Phân biệt tiếp diễn/đảo chiều)
    for pattern in patterns:
        pattern_type = pattern.get('pattern', '')
        is_continuation = pattern_type == 'Tiếp diễn'
        is_reversal = pattern_type == 'Đảo chiều'
        
        if pattern['signal'] == 'BULLISH':
            if is_continuation:
                # Mô hình tiếp diễn tăng → điểm cao hơn
                buy_score += 3 if pattern['confidence'] == 'HIGH' else 2
                reasons_buy.append(f"✅ {pattern['type']} ({pattern_type} - tăng)")
                checklist_buy.append(f"✅ Mô hình tiếp diễn tăng / đảo chiều tăng tại Demand")
            elif is_reversal:
                # Mô hình đảo chiều → chỉ điểm nếu confidence cao hoặc trùng Supply/Demand
                if pattern['confidence'] == 'HIGH':
                    buy_score += 2
                    reasons_buy.append(f"✅ {pattern['type']} ({pattern_type} - tăng)")
                    checklist_buy.append(f"✅ Mô hình đảo chiều tăng tại Demand")
                else:
                    buy_score += 1
                    reasons_buy.append(f"⚠️ {pattern['type']} ({pattern_type} - độ tin cậy thấp)")
        elif pattern['signal'] == 'BEARISH':
            if is_continuation:
                # Mô hình tiếp diễn giảm → điểm cao hơn
                sell_score += 3 if pattern['confidence'] == 'HIGH' else 2
                reasons_sell.append(f"✅ {pattern['type']} ({pattern_type} - giảm)")
                checklist_sell.append(f"✅ Mô hình tiếp diễn giảm / đảo chiều giảm tại Supply")
            elif is_reversal:
                # Mô hình đảo chiều → chỉ điểm nếu confidence cao hoặc trùng Supply/Demand
                if pattern['confidence'] == 'HIGH':
                    sell_score += 2
                    reasons_sell.append(f"✅ {pattern['type']} ({pattern_type} - giảm)")
                    checklist_sell.append(f"✅ Mô hình đảo chiều giảm tại Supply")
                else:
                    sell_score += 1
                    reasons_sell.append(f"⚠️ {pattern['type']} ({pattern_type} - độ tin cậy thấp)")
    
    # 3. Fibonacci (V2 - Ưu tiên 0.5-0.618, Rule cứng TP)
    if fib_levels:
        closest_level, distance, is_premium_zone = find_current_fib_level(current_price, fib_levels)
        
        # Entry levels cho LONG: 0.382, 0.5, 0.618 (V2: ưu tiên 0.5-0.618)
        if closest_level in ['0.382', '0.5', '0.618']:
            if fib_levels['trend'] == "UP":
                if is_premium_zone:
                    buy_score += 3  # Vùng đẹp nhất
                    reasons_buy.append(f"🔥 Giá tại Fibo {closest_level} (vùng đẹp nhất 0.5-0.618)")
                    checklist_buy.append(f"✅ Giá hồi về Fibo 0.382-0.618 (hiện tại: {closest_level})")
                else:
                    buy_score += 2
                    reasons_buy.append(f"✅ Giá tại Fibo {closest_level} (entry tốt cho LONG)")
                    checklist_buy.append(f"✅ Giá hồi về Fibo 0.382-0.618 (hiện tại: {closest_level})")
                decision['entry_levels'].append(f"Fibo {closest_level}: {fib_levels[closest_level]:.5f}")
                
                # V2: Rule cứng - TP PHẢI > Entry cho BUY
                entry_price = fib_levels[closest_level]
                tp1 = fib_levels.get('1.0', entry_price)
                tp2 = fib_levels.get('1.272', entry_price)
                tp3 = fib_levels.get('1.618', entry_price)
                
                if tp1 > entry_price:
                    decision['tp_levels'].append(f"Fibo 1.0: {tp1:.5f} ✅")
                if tp2 > entry_price:
                    decision['tp_levels'].append(f"Fibo 1.272: {tp2:.5f} ✅")
                if tp3 > entry_price:
                    decision['tp_levels'].append(f"Fibo 1.618: {tp3:.5f} ✅")
                
                # SL: dưới Demand hoặc dưới 0.786
                sl_fib786 = fib_levels.get('0.786', entry_price * 0.99)
                decision['sl_levels'].append(f"Fibo 0.786: {sl_fib786:.5f} (dưới entry)")
        
        # Entry levels cho SHORT: 0.382, 0.5, 0.618 (V2: ưu tiên 0.5-0.618)
        if closest_level in ['0.382', '0.5', '0.618']:
            if fib_levels['trend'] == "DOWN":
                if is_premium_zone:
                    sell_score += 3  # Vùng đẹp nhất
                    reasons_sell.append(f"🔥 Giá tại Fibo {closest_level} (vùng đẹp nhất 0.5-0.618)")
                    checklist_sell.append(f"✅ Giá hồi lên Fibo 0.5-0.618 (hiện tại: {closest_level})")
                else:
                    sell_score += 2
                    reasons_sell.append(f"✅ Giá tại Fibo {closest_level} (entry tốt cho SHORT)")
                    checklist_sell.append(f"✅ Giá hồi lên Fibo 0.5-0.618 (hiện tại: {closest_level})")
                decision['entry_levels'].append(f"Fibo {closest_level}: {fib_levels[closest_level]:.5f}")
                
                # V2: Rule cứng - TP PHẢI < Entry cho SELL
                entry_price = fib_levels[closest_level]
                tp1 = fib_levels.get('1.0', entry_price)
                tp2 = fib_levels.get('1.272', entry_price)
                tp3 = fib_levels.get('1.618', entry_price)
                
                if tp1 < entry_price:
                    decision['tp_levels'].append(f"Fibo 1.0: {tp1:.5f} ✅")
                if tp2 < entry_price:
                    decision['tp_levels'].append(f"Fibo 1.272: {tp2:.5f} ✅")
                if tp3 < entry_price:
                    decision['tp_levels'].append(f"Fibo 1.618: {tp3:.5f} ✅")
                
                # SL: trên Supply hoặc trên đỉnh gần nhất
                sl_fib786 = fib_levels.get('0.786', entry_price * 1.01)
                decision['sl_levels'].append(f"Fibo 0.786: {sl_fib786:.5f} (trên entry)")
    
    # 4. Supply/Demand zones (V2 - Mạnh nhất khi trùng Fibo/trendline)
    # Kiểm tra giá có nằm trong zone không
    for zone in demand_zones:
        # Demand zone: price là low, zone_high là high
        zone_low = zone['price']
        zone_high = zone.get('zone_high', zone_low * 1.01)
        if zone_low <= current_price <= zone_high:
            zone_strength = zone.get('strength', 1.0)
            # V2: Tín hiệu mạnh nhất khi trùng Fibo hoặc trendline
            if zone_strength >= 2.0:
                buy_score += 4  # Tăng điểm khi trùng Fibo/trendline
                if 'fib_level' in zone:
                    reasons_buy.append(f"🔥 Giá trong Demand Zone TRÙNG Fibo {zone['fib_level']} ({zone_low:.5f} - {zone_high:.5f})")
                if zone.get('trendline_retest', False):
                    reasons_buy.append(f"🔥 Giá trong Demand Zone TRÙNG Trendline Retest ({zone_low:.5f} - {zone_high:.5f})")
                checklist_buy.append(f"✅ Nằm trong Demand Zone (trùng Fibo/trendline)")
            else:
                buy_score += 2
                reasons_buy.append(f"✅ Giá trong Demand Zone ({zone_low:.5f} - {zone_high:.5f})")
                checklist_buy.append(f"✅ Nằm trong Demand Zone")
            decision['entry_levels'].append(f"Demand Zone: {zone_low:.5f}")
    
    for zone in supply_zones:
        # Supply zone: price là high, zone_low là low
        zone_high = zone['price']
        zone_low = zone.get('zone_low', zone_high * 0.99)
        if zone_low <= current_price <= zone_high:
            zone_strength = zone.get('strength', 1.0)
            # V2: Tín hiệu mạnh nhất khi trùng Fibo hoặc trendline
            if zone_strength >= 2.0:
                sell_score += 4  # Tăng điểm khi trùng Fibo/trendline
                if 'fib_level' in zone:
                    reasons_sell.append(f"🔥 Giá trong Supply Zone TRÙNG Fibo {zone['fib_level']} ({zone_low:.5f} - {zone_high:.5f})")
                if zone.get('trendline_retest', False):
                    reasons_sell.append(f"🔥 Giá trong Supply Zone TRÙNG Trendline Retest ({zone_low:.5f} - {zone_high:.5f})")
                checklist_sell.append(f"✅ Chạm Supply Zone (trùng Fibo/trendline)")
            else:
                sell_score += 2
                reasons_sell.append(f"✅ Giá trong Supply Zone ({zone_low:.5f} - {zone_high:.5f})")
                checklist_sell.append(f"✅ Chạm Supply Zone")
            decision['entry_levels'].append(f"Supply Zone: {zone_high:.5f}")
    
    # 5. Nến xác nhận (V2 - Pin bar / Engulfing / BOS)
    if len(df) >= 2:
        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2] if len(df) >= 2 else None
        
        # Phát hiện Bullish Engulfing
        if prev_candle is not None:
            prev_bearish = prev_candle['close'] < prev_candle['open']
            curr_bullish = last_candle['close'] > last_candle['open']
            engulfs = (last_candle['open'] < prev_candle['close']) and (last_candle['close'] > prev_candle['open'])
            if prev_bearish and curr_bullish and engulfs:
                buy_score += 2
                reasons_buy.append("✅ Bullish Engulfing")
                checklist_buy.append("✅ Có nến xác nhận tăng (Engulfing)")
        
        # Phát hiện Bearish Engulfing
        if prev_candle is not None:
            prev_bullish = prev_candle['close'] > prev_candle['open']
            curr_bearish = last_candle['close'] < last_candle['open']
            engulfs = (last_candle['open'] > prev_candle['close']) and (last_candle['close'] < prev_candle['open'])
            if prev_bullish and curr_bearish and engulfs:
                sell_score += 2
                reasons_sell.append("✅ Bearish Engulfing")
                checklist_sell.append("✅ Có nến xác nhận giảm (Engulfing)")
        
        # Phát hiện Pin bar (Bullish)
        if len(df) >= 1:
            candle_range = last_candle['high'] - last_candle['low']
            if candle_range > 0:
                body = abs(last_candle['close'] - last_candle['open'])
                lower_wick = min(last_candle['open'], last_candle['close']) - last_candle['low']
                upper_wick = last_candle['high'] - max(last_candle['open'], last_candle['close'])
                
                # Bullish Pin bar: Lower wick >= 60% range, small body
                if lower_wick / candle_range >= 0.6 and body / candle_range < 0.3:
                    buy_score += 2
                    reasons_buy.append("✅ Bullish Pin bar")
                    checklist_buy.append("✅ Có nến xác nhận tăng (Pin bar)")
                
                # Bearish Pin bar: Upper wick >= 60% range, small body
                if upper_wick / candle_range >= 0.6 and body / candle_range < 0.3:
                    sell_score += 2
                    reasons_sell.append("✅ Bearish Pin bar")
                    checklist_sell.append("✅ Có nến xác nhận giảm (Pin bar)")
        
        # BOS (Break of Structure) - Giá phá vỡ cấu trúc
        if len(df) >= 5:
            recent_highs = df.iloc[-5:]['high'].values
            recent_lows = df.iloc[-5:]['low'].values
            prev_high = max(recent_highs[:-1])
            prev_low = min(recent_lows[:-1])
            
            # Bullish BOS: Giá phá vỡ đỉnh trước
            if last_candle['close'] > prev_high:
                buy_score += 2
                reasons_buy.append("✅ BOS (Break of Structure) - Phá đỉnh")
                checklist_buy.append("✅ Có nến xác nhận tăng (BOS)")
            
            # Bearish BOS: Giá phá vỡ đáy trước
            if last_candle['close'] < prev_low:
                sell_score += 2
                reasons_sell.append("✅ BOS (Break of Structure) - Phá đáy")
                checklist_sell.append("✅ Có nến xác nhận giảm (BOS)")
    
    # V2: Rule cứng - NO TRADE nếu trendline bị phá nhưng chưa retest
    if trendline_broken and not any([z.get('trendline_retest', False) for z in demand_zones + supply_zones]):
        decision['signal'] = 'NO_TRADE'
        decision['confidence'] = 'LOW'
        decision['reasons'] = ["🚫 Trendline bị phá nhưng chưa retest - BỎ QUA"]
        return decision
    
    # V2: Rule cứng - NO TRADE nếu BUY & SELL cùng xuất hiện
    if buy_score >= 3 and sell_score >= 3:
        decision['signal'] = 'NO_TRADE'
        decision['confidence'] = 'LOW'
        decision['reasons'] = ["🚫 BUY & SELL cùng xuất hiện - BỎ QUA"]
        return decision
    
    # V2: Rule cứng - NO TRADE nếu TP nằm sai phía entry
    if decision['tp_levels']:
        # Kiểm tra xem có TP hợp lệ không
        valid_tp_count = len([tp for tp in decision['tp_levels'] if '✅' in tp])
        if valid_tp_count == 0:
            decision['signal'] = 'NO_TRADE'
            decision['confidence'] = 'LOW'
            decision['reasons'] = ["🚫 TP nằm sai phía entry - BỎ QUA"]
            return decision
    
    # Quyết định cuối cùng (V2 - Checklist A+)
    # BUY A+: Cần đủ các điều kiện trong checklist
    buy_checklist_count = len([c for c in checklist_buy if c.startswith('✅')])
    sell_checklist_count = len([c for c in checklist_sell if c.startswith('✅')])
    
    if buy_score > sell_score and buy_score >= 5 and buy_checklist_count >= 4:
        decision['signal'] = 'BUY'
        decision['confidence'] = 'A+' if buy_checklist_count >= 5 else 'HIGH' if buy_score >= 8 else 'MEDIUM'
        decision['reasons'] = reasons_buy
        decision['checklist_buy'] = checklist_buy
    elif sell_score > buy_score and sell_score >= 5 and sell_checklist_count >= 4:
        decision['signal'] = 'SELL'
        decision['confidence'] = 'A+' if sell_checklist_count >= 5 else 'HIGH' if sell_score >= 8 else 'MEDIUM'
        decision['reasons'] = reasons_sell
        decision['checklist_sell'] = checklist_sell
    else:
        decision['signal'] = 'NEUTRAL'
        decision['reasons'] = reasons_buy + reasons_sell if reasons_buy or reasons_sell else ["⚠️ Không đủ tín hiệu rõ ràng (chưa đạt checklist A+)"]
        decision['checklist_buy'] = checklist_buy
        decision['checklist_sell'] = checklist_sell
    
    return decision

# ==============================================================================
# 8. PHÂN TÍCH SYMBOL
# ==============================================================================

def analyze_symbol(symbol_base):
    """Phân tích một symbol theo 5 bước"""
    print(f"\n{'='*70}")
    print(f"📊 Đang phân tích: {symbol_base}")
    print(f"{'='*70}")
    
    # Tìm symbol thực tế
    symbol = find_symbol(symbol_base)
    if symbol is None:
        return None
    
    # Lấy dữ liệu H4 (khung tốt cho trendline)
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 200)
        if rates is None or len(rates) == 0:
            print(f"  ❌ Không lấy được dữ liệu H4")
            return None
    except Exception as e:
        print(f"  ❌ Lỗi khi lấy dữ liệu: {e}")
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    
    current_price = df.iloc[-1]['close']
    
    # B1: Tìm swing points và trendline
    print("  🔍 B1: Tìm swing points và trendline...")
    swing_highs, swing_lows = find_swing_points(df, lookback=5)
    
    trendline_support = calculate_trendline(swing_lows, len(df) - 1) if swing_lows else None
    trendline_resistance = calculate_trendline(swing_highs, len(df) - 1) if swing_highs else None
    
    # Chọn trendline chính (support cho uptrend, resistance cho downtrend)
    trendline = trendline_support if trendline_support else trendline_resistance
    
    # B2: Phát hiện mô hình giá
    print("  🔍 B2: Phát hiện mô hình giá...")
    trendline_direction = trendline['direction'] if trendline else None
    patterns = detect_price_patterns(df, swing_highs, swing_lows, trendline_direction)
    
    # B3: Tính Fibonacci
    print("  🔍 B3: Tính Fibonacci levels...")
    fib_levels = None
    if swing_highs and swing_lows:
        # Lấy swing high và low gần nhất
        recent_high = sorted(swing_highs, key=lambda x: x[0], reverse=True)[0] if swing_highs else None
        recent_low = sorted(swing_lows, key=lambda x: x[0], reverse=True)[0] if swing_lows else None
        fib_levels = calculate_fibonacci_levels(recent_high, recent_low)
    
    # B4: Tìm Supply/Demand zones
    print("  🔍 B4: Tìm Supply/Demand zones...")
    supply_zones, demand_zones = find_supply_demand_zones(df, lookback=100, fib_levels=fib_levels, trendline=trendline)
    
    # B5: Tổng hợp quyết định
    print("  🔍 B5: Tổng hợp quyết định...")
    decision = make_decision(df, trendline, patterns, fib_levels, supply_zones, demand_zones, current_price)
    
    return {
        'symbol': symbol,
        'current_price': current_price,
        'trendline': trendline,
        'patterns': patterns,
        'fib_levels': fib_levels,
        'supply_zones': supply_zones,
        'demand_zones': demand_zones,
        'decision': decision,
        'swing_highs': swing_highs,
        'swing_lows': swing_lows
    }

def find_symbol(base_name):
    """Tìm symbol thực tế trong MT5"""
    variants = [
        base_name + "m",
        base_name,
        base_name.upper(),
        base_name.lower(),
        base_name.replace("USD", "/USD"),
    ]
    
    if "BTC" in base_name or "ETH" in base_name or "BNB" in base_name:
        variants.extend([
            base_name.replace("USD", "USDT"),
            base_name.replace("USD", "USDT") + "m",
        ])
    
    for variant in variants:
        symbol_info = mt5.symbol_info(variant)
        if symbol_info is not None:
            if not symbol_info.visible:
                mt5.symbol_select(variant, True)
            test_rates = mt5.copy_rates_from_pos(variant, mt5.TIMEFRAME_H4, 0, 1)
            if test_rates is not None and len(test_rates) > 0:
                return variant
    
    return None

# ==============================================================================
# 9. GỬI TELEGRAM
# ==============================================================================

def split_message(message, max_length=4096):
    """Chia message thành nhiều phần nếu quá dài"""
    if len(message) <= max_length:
        return [message]
    
    parts = []
    current_part = ""
    
    lines = message.split('\n')
    
    for line in lines:
        if len(current_part) + len(line) + 1 > max_length:
            if current_part:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                parts.append(line[:max_length])
                current_part = line[max_length:] + '\n'
        else:
            current_part += line + '\n'
    
    if current_part:
        parts.append(current_part)
    
    return parts

def send_telegram(message, max_retries=3):
    """Gửi tin nhắn qua Telegram với retry logic và tự động chia message nếu quá dài"""
    if not CHAT_ID or not TELEGRAM_TOKEN:
        print("⚠️ Thiếu CHAT_ID hoặc TELEGRAM_TOKEN")
        return False
    
    # Kiểm tra độ dài message (Telegram giới hạn 4096 ký tự)
    message_parts = split_message(message, max_length=4096)
    
    if len(message_parts) > 1:
        print(f"⚠️ Message quá dài ({len(message)} ký tự), chia thành {len(message_parts)} phần")
    
    success_count = 0
    for part_idx, message_part in enumerate(message_parts):
        if len(message_parts) > 1:
            if part_idx > 0:
                message_part = f"<b>📄 Phần {part_idx + 1}/{len(message_parts)}</b>\n\n" + message_part
        
        for attempt in range(max_retries):
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                data = {
                    "chat_id": CHAT_ID,
                    "text": message_part,
                    "parse_mode": "HTML"
                }
                response = requests.post(url, data=data, timeout=15)
                
                if response.status_code == 200:
                    success_count += 1
                    if len(message_parts) > 1:
                        print(f"✅ Đã gửi phần {part_idx + 1}/{len(message_parts)}")
                    break
                else:
                    try:
                        error_data = response.json()
                        error_desc = error_data.get('description', 'Unknown error')
                        print(f"⚠️ Lỗi gửi Telegram (lần {attempt + 1}/{max_retries}): Status {response.status_code}")
                        print(f"   Chi tiết: {error_desc}")
                        print(f"   Độ dài message: {len(message_part)} ký tự")
                    except:
                        print(f"⚠️ Lỗi gửi Telegram (lần {attempt + 1}/{max_retries}): Status {response.status_code}")
                        print(f"   Response: {response.text[:200]}")
                    
                    if response.status_code == 429:  # Rate limit
                        retry_after = int(response.headers.get('Retry-After', 10))
                        print(f"⏳ Rate limit, đợi {retry_after} giây...")
                        time.sleep(retry_after)
                    elif attempt < max_retries - 1:
                        time.sleep(2)
            except requests.exceptions.Timeout:
                print(f"⚠️ Timeout khi gửi Telegram (lần {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2)
            except Exception as e:
                print(f"⚠️ Lỗi gửi Telegram (lần {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        
        # Đợi 1 giây giữa các phần để tránh rate limit
        if part_idx < len(message_parts) - 1:
            time.sleep(1)
    
    return success_count == len(message_parts)

def escape_html(text):
    """Escape các ký tự đặc biệt trong HTML"""
    if text is None:
        return ""
    text = str(text)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text

def format_telegram_message(symbol, analysis):
    """Định dạng tin nhắn Telegram"""
    if analysis is None:
        return f"❌ {symbol}: Không lấy được dữ liệu"
    
    msg = f"<b>📊 TRENDLINE ANALYSIS - {escape_html(symbol)}</b>\n"
    msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    msg += "=" * 50 + "\n\n"
    
    msg += f"💰 <b>Giá hiện tại:</b> {analysis['current_price']:.5f}\n\n"
    
    # B1: Trendline
    msg += "<b>📈 B1: TRENDLINE</b>\n"
    if analysis['trendline']:
        tl = analysis['trendline']
        direction_emoji = "🟢" if tl['direction'] == "UP" else "🔴" if tl['direction'] == "DOWN" else "🟡"
        msg += f"{direction_emoji} Hướng: {tl['direction']}\n"
        msg += f"📊 Giá trị trendline: {tl['value_at_current']:.5f}\n"
        # Tạo df tạm để check break (cần nến đã đóng cửa)
        temp_df = pd.DataFrame({'close': [analysis['current_price'], analysis['current_price']]})
        is_broken, is_invalidated, break_msg = check_trendline_break(temp_df, tl, 0.001)
        if is_invalidated:
            msg += f"⛔ {escape_html(break_msg)}\n"
        elif is_broken:
            msg += f"⚠️ {escape_html(break_msg)}\n"
    else:
        msg += "⚠️ Không tìm thấy trendline rõ ràng\n"
    msg += "\n"
    
    # B2: Mô hình giá
    msg += "<b>📐 B2: MÔ HÌNH GIÁ</b>\n"
    if analysis['patterns']:
        for pattern in analysis['patterns']:
            signal_emoji = "🟢" if pattern['signal'] == 'BULLISH' else "🔴"
            msg += f"{signal_emoji} {escape_html(pattern['type'])} ({escape_html(pattern['pattern'])}) - {escape_html(pattern['signal'])}\n"
    else:
        msg += "⚠️ Không phát hiện mô hình rõ ràng\n"
    msg += "\n"
    
    # B3: Fibonacci
    msg += "<b>📊 B3: FIBONACCI</b>\n"
    if analysis['fib_levels']:
        fib = analysis['fib_levels']
        closest_level, distance = find_current_fib_level(analysis['current_price'], fib)
        if closest_level:
            msg += f"📍 Level gần nhất: {escape_html(closest_level)}\n"
        msg += f"💰 Entry levels (0.382-0.618):\n"
        for level in ['0.382', '0.5', '0.618']:
            if level in fib:
                msg += f"   • {escape_html(level)}: {fib[level]:.5f}\n"
        msg += f"🎯 TP levels:\n"
        for level in ['1.0', '1.272', '1.618']:
            if level in fib:
                msg += f"   • {escape_html(level)}: {fib[level]:.5f}\n"
    else:
        msg += "⚠️ Không tính được Fibonacci\n"
    msg += "\n"
    
    # B4: Supply/Demand
    msg += "<b>📍 B4: SUPPLY/DEMAND ZONES</b>\n"
    if analysis['demand_zones']:
        msg += "🟢 Demand Zones:\n"
        for zone in analysis['demand_zones'][:2]:
            msg += f"   • {zone['price']:.5f} (Volume: {zone['volume_ratio']:.1f}x)\n"
    if analysis['supply_zones']:
        msg += "🔴 Supply Zones:\n"
        for zone in analysis['supply_zones'][:2]:
            msg += f"   • {zone['price']:.5f} (Volume: {zone['volume_ratio']:.1f}x)\n"
    if not analysis['demand_zones'] and not analysis['supply_zones']:
        msg += "⚠️ Không tìm thấy zone rõ ràng\n"
    msg += "\n"
    
    # B5: Quyết định
    msg += "<b>🎯 B5: QUYẾT ĐỊNH</b>\n"
    decision = analysis['decision']
    signal_emoji = "🟢" if decision['signal'] == 'BUY' else "🔴" if decision['signal'] == 'SELL' else "🟡"
    confidence_emoji = "💪" if decision['confidence'] == 'HIGH' else "⚡" if decision['confidence'] == 'MEDIUM' else "💤"
    
    msg += f"{signal_emoji} <b>Signal: {escape_html(decision['signal'])}</b> {confidence_emoji} ({escape_html(decision['confidence'])})\n\n"
    
    # V2: Hiển thị Checklist
    if decision.get('checklist_buy'):
        msg += "<b>📋 Checklist BUY:</b>\n"
        for item in decision['checklist_buy']:
            msg += f"• {escape_html(item)}\n"
        msg += "\n"
    
    if decision.get('checklist_sell'):
        msg += "<b>📋 Checklist SELL:</b>\n"
        for item in decision['checklist_sell']:
            msg += f"• {escape_html(item)}\n"
        msg += "\n"
    
    msg += "<b>Lý do:</b>\n"
    for reason in decision['reasons']:
        msg += f"• {escape_html(reason)}\n"
    
    if decision['entry_levels']:
        msg += "\n<b>💰 Entry Levels:</b>\n"
        for level in decision['entry_levels']:
            msg += f"• {escape_html(level)}\n"
    
    if decision['tp_levels']:
        msg += "\n<b>🎯 Take Profit Levels:</b>\n"
        for level in decision['tp_levels'][:3]:
            msg += f"• {escape_html(level)}\n"
    
    if decision.get('sl_levels'):
        msg += "\n<b>🛑 Stop Loss Levels:</b>\n"
        for level in decision['sl_levels']:
            msg += f"• {escape_html(level)}\n"
    
    return msg

# ==============================================================================
# 10. MAIN
# ==============================================================================

def main():
    print(f"\n{'='*70}")
    print(f"📊 BOT CHECK TRENDLINE - 5 BƯỚC XÁC ĐỊNH LONG/SHORT")
    print(f"{'='*70}\n")
    
    # Khởi tạo MT5
    if not initialize_mt5():
        print("\n❌ Không thể kết nối MT5. Dừng bot.")
        mt5.shutdown()
        return
    
    # Phân tích từng symbol
    for symbol_base in SYMBOLS:
        analysis = analyze_symbol(symbol_base)
        
        if analysis:
            # In ra console
            print("\n" + "="*70)
            print(f"KẾT QUẢ: {analysis['symbol']}")
            print("="*70)
            decision = analysis['decision']
            print(f"Signal: {decision['signal']} ({decision['confidence']})")
            print("Lý do:")
            for reason in decision['reasons']:
                print(f"  {reason}")
            
            # Gửi Telegram
            telegram_msg = format_telegram_message(analysis['symbol'], analysis)
            print(f"\n📤 Đang gửi Telegram...")
            print(f"   Độ dài message: {len(telegram_msg)} ký tự")
            if send_telegram(telegram_msg):
                print(f"✅ Đã gửi log về Telegram")
            else:
                print(f"❌ Không thể gửi Telegram sau 3 lần thử")
                # In một phần message để debug
                print(f"   Preview message (100 ký tự đầu): {telegram_msg[:100]}...")
        else:
            print(f"⚠️ Không có dữ liệu cho {symbol_base}")
        
        # Sleep giữa các symbol
        if symbol_base != SYMBOLS[-1]:
            print("\n⏳ Đợi 10 giây...")
            time.sleep(10)
    
    print("\n" + "="*70)
    print("HOÀN TẤT!")
    print("="*70)
    
    mt5.shutdown()

if __name__ == "__main__":
    main()

