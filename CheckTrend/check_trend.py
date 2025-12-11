from threading import Thread
import MetaTrader5 as mt5
import pandas as pd
import json
import os
import requests
import time
from datetime import datetime

# ==============================================================================
# 1. CẤU HÌNH
# ==============================================================================

# Load Config
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

# Danh sách các cặp cần check (thử nhiều biến thể)
SYMBOLS_CONFIG = {
    "XAUUSD": ["XAUUSDm", "XAUUSD", "GOLD", "XAU/USD", "GOLDm"],
    "ETHUSD": ["ETHUSD", "ETHUSDm", "ETH/USD", "ETHUSDT", "ETHUSDTm", "ETH"],
    "BTCUSD": ["BTCUSD", "BTCUSDm", "BTC/USD", "BTCUSDT", "BTCUSDTm", "BTC"],
    "BNBUSD": ["BNBUSD", "BNBUSDm", "BNB/USD", "BNBUSDT", "BNBUSDTm", "BNB"]
}

# ==============================================================================
# 2. KẾT NỐI MT5
# ==============================================================================

def initialize_mt5():
    """Khởi tạo và kết nối MT5."""
    
    print("\n--- Bắt đầu kết nối MT5 ---")
    
    # 1. Thử kết nối với PATH và thông tin đăng nhập (khởi chạy MT5 nếu cần)
    if not mt5.initialize(path=MT5_PATH, 
                           login=MT5_LOGIN, 
                           password=MT5_PASSWORD, 
                           server=MT5_SERVER):
        
        # 2. Nếu thất bại, thử lại mà không dùng PATH (dùng phiên MT5 đang chạy)
        print(f"Lần 1 thất bại ({mt5.last_error()}). Thử lại không dùng PATH...")
        if not mt5.initialize(login=MT5_LOGIN, 
                               password=MT5_PASSWORD, 
                               server=MT5_SERVER):
            print(f"❌ KHỞI TẠO THẤT BẠI. Lỗi: {mt5.last_error()}")
            print("Vui lòng kiểm tra: 1. Đường dẫn PATH, 2. Thông tin đăng nhập, 3. Server Name.")
            return False
        else:
            print("✅ Kết nối MT5 thành công (Sử dụng phiên MT5 đang chạy sẵn).")
    else:
        print(f"✅ Đăng nhập tài khoản {MT5_LOGIN} trên server {MT5_SERVER} thành công.")
    
    # Kiểm tra kết nối bằng cách lấy thông tin tài khoản
    account_info = mt5.account_info()
    if account_info is None:
        print(f"❌ Không thể lấy thông tin tài khoản. Lỗi: {mt5.last_error()}")
        return False
    
    print(f"✅ Tài khoản: {account_info.login}, Server: {account_info.server}, Currency: {account_info.currency}")
    return True

# ==============================================================================
# 3. HÀM TÍNH TOÁN CHỈ BÁO
# ==============================================================================

def calculate_ema(prices, period):
    """Tính Exponential Moving Average"""
    return prices.ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    """Tính Average True Range"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    return atr

def calculate_adx(df, period=14):
    """Tính Average Directional Index"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    # Tính +DM và -DM
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    
    # Tính True Range
    tr = calculate_atr(df, period)
    
    # Tính +DI và -DI
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr)
    
    # Tính DX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    
    # Tính ADX
    adx = dx.rolling(window=period).mean()
    
    return adx

def calculate_rsi(prices, period=14):
    """Tính Relative Strength Index"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def find_peaks_troughs(df, lookback=20):
    """Tìm đỉnh và đáy trong dữ liệu"""
    peaks = []
    troughs = []
    
    recent_data = df.iloc[-lookback:] if len(df) >= lookback else df
    
    for i in range(1, len(recent_data) - 1):
        # Đỉnh: high cao hơn 2 nến xung quanh
        if (recent_data.iloc[i]['high'] > recent_data.iloc[i-1]['high'] and 
            recent_data.iloc[i]['high'] > recent_data.iloc[i+1]['high']):
            peaks.append((i, recent_data.iloc[i]['high']))
        
        # Đáy: low thấp hơn 2 nến xung quanh
        if (recent_data.iloc[i]['low'] < recent_data.iloc[i-1]['low'] and 
            recent_data.iloc[i]['low'] < recent_data.iloc[i+1]['low']):
            troughs.append((i, recent_data.iloc[i]['low']))
    
    return peaks, troughs

def check_market_structure(peaks, troughs):
    """Kiểm tra cấu trúc thị trường"""
    if len(peaks) >= 2:
        last_peak = peaks[-1][1]
        prev_peak = peaks[-2][1]
        higher_highs = last_peak > prev_peak
    else:
        higher_highs = None
    
    if len(troughs) >= 2:
        last_trough = troughs[-1][1]
        prev_trough = troughs[-2][1]
        higher_lows = last_trough > prev_trough
    else:
        higher_lows = None
    
    return higher_highs, higher_lows

def check_ema_alignment(df, ema50, ema200):
    """Kiểm tra EMA alignment (EMA căn thẳng = xu hướng mạnh)"""
    if len(df) < 10:
        return False, "Không đủ dữ liệu"
    
    # Kiểm tra EMA50 và EMA200 có căn thẳng không
    ema50_values = ema50.iloc[-10:].values
    ema200_values = ema200.iloc[-10:].values
    
    # Nếu giá > EMA50 > EMA200 → Bullish alignment
    if df['close'].iloc[-1] > ema50.iloc[-1] > ema200.iloc[-1]:
        # Kiểm tra EMA có tăng đều không
        ema50_increasing = all(ema50_values[i] < ema50_values[i+1] for i in range(len(ema50_values)-1))
        ema200_increasing = all(ema200_values[i] < ema200_values[i+1] for i in range(len(ema200_values)-1))
        if ema50_increasing and ema200_increasing:
            return True, "Bullish Alignment (Giá > EMA50 > EMA200, EMA tăng đều)"
    
    # Nếu giá < EMA50 < EMA200 → Bearish alignment
    elif df['close'].iloc[-1] < ema50.iloc[-1] < ema200.iloc[-1]:
        # Kiểm tra EMA có giảm đều không
        ema50_decreasing = all(ema50_values[i] > ema50_values[i+1] for i in range(len(ema50_values)-1))
        ema200_decreasing = all(ema200_values[i] > ema200_values[i+1] for i in range(len(ema200_values)-1))
        if ema50_decreasing and ema200_decreasing:
            return True, "Bearish Alignment (Giá < EMA50 < EMA200, EMA giảm đều)"
    
    return False, "EMA không căn thẳng (rối)"

def check_volume_spike(df, threshold=2.0):
    """Kiểm tra volume spike (volume tăng bất thường)"""
    if len(df) < 5:
        return False, "Không đủ dữ liệu"
    
    recent_volumes = df['tick_volume'].iloc[-5:].values
    avg_volume = recent_volumes[:-1].mean()
    last_volume = recent_volumes[-1]
    
    if avg_volume == 0:
        return False, "Không tính được"
    
    ratio = last_volume / avg_volume
    if ratio > threshold:
        return True, f"Volume spike ({ratio:.2f}x trung bình) - Có thể false breakout"
    
    return False, f"Volume bình thường ({ratio:.2f}x)"

def check_atr_breakout(df, atr, threshold=2.0):
    """Kiểm tra ATR breakout (ATR tăng đột biến > 200% trung bình)"""
    if len(df) < 20:
        return False, "Không đủ dữ liệu"
    
    atr_values = atr.iloc[-20:].values
    avg_atr = atr_values[:-1].mean()
    current_atr = atr_values[-1]
    
    if avg_atr == 0:
        return False, "Không tính được"
    
    ratio = current_atr / avg_atr
    if ratio > threshold:
        return True, f"ATR breakout ({ratio:.2f}x trung bình) - Báo tin mạnh"
    
    return False, f"ATR bình thường ({ratio:.2f}x)"

def check_false_break(df, support_resistance_level):
    """Kiểm tra false break (giá phá vỡ nhưng đóng nến ngược lại)"""
    if len(df) < 2:
        return False, "Không đủ dữ liệu"
    
    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]
    
    # Kiểm tra nếu giá phá vỡ nhưng đóng nến ngược lại
    if prev_candle['high'] > support_resistance_level and last_candle['close'] < support_resistance_level:
        return True, "False break (phá vỡ lên nhưng đóng nến xuống)"
    elif prev_candle['low'] < support_resistance_level and last_candle['close'] > support_resistance_level:
        return True, "False break (phá vỡ xuống nhưng đóng nến lên)"
    
    return False, "Không có false break"

# ==============================================================================
# 4. PHÂN TÍCH XU HƯỚNG THEO KHUNG THỜI GIAN
# ==============================================================================

def analyze_timeframe(symbol, timeframe, timeframe_name):
    """Phân tích xu hướng cho một khung thời gian"""
    try:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 200)
        if rates is None:
            print(f"  ⚠️ {timeframe_name}: Không lấy được dữ liệu từ MT5 (rates = None)")
            return None
        if len(rates) == 0:
            print(f"  ⚠️ {timeframe_name}: Dữ liệu rỗng (len = 0)")
            return None
    except Exception as e:
        print(f"  ❌ {timeframe_name}: Lỗi khi lấy dữ liệu: {e}")
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    
    # Tính các chỉ báo
    ema20 = calculate_ema(df['close'], 20)
    ema50 = calculate_ema(df['close'], 50)
    ema200 = calculate_ema(df['close'], 200)
    adx = calculate_adx(df, 14)
    atr = calculate_atr(df, 14)
    rsi = calculate_rsi(df['close'], 14)
    
    # Lấy giá trị hiện tại
    current_price = df['close'].iloc[-1]
    ema20_current = ema20.iloc[-1] if not pd.isna(ema20.iloc[-1]) else current_price
    ema50_current = ema50.iloc[-1]
    ema200_current = ema200.iloc[-1]
    adx_current = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0
    atr_current = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0
    rsi_current = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    
    # Tìm đỉnh và đáy
    peaks, troughs = find_peaks_troughs(df)
    higher_highs, higher_lows = check_market_structure(peaks, troughs)
    
    # Xác định xu hướng
    trend = "SIDEWAYS"
    trend_strength = "WEAK"
    
    if current_price > ema50_current > ema200_current:
        if higher_highs is True and higher_lows is True:
            trend = "BULLISH"
            trend_strength = "STRONG" if adx_current > 25 else "MODERATE"
        elif higher_highs is True or higher_lows is True:
            trend = "BULLISH"
            trend_strength = "MODERATE"
        else:
            trend = "BULLISH"
            trend_strength = "WEAK"
    elif current_price < ema50_current < ema200_current:
        if higher_highs is False and higher_lows is False:
            trend = "BEARISH"
            trend_strength = "STRONG" if adx_current > 25 else "MODERATE"
        elif higher_highs is False or higher_lows is False:
            trend = "BEARISH"
            trend_strength = "MODERATE"
        else:
            trend = "BEARISH"
            trend_strength = "WEAK"
    
    # Kiểm tra EMA alignment
    ema_aligned, ema_alignment_msg = check_ema_alignment(df, ema50, ema200)
    
    # Kiểm tra volume spike
    volume_spike, volume_msg = check_volume_spike(df)
    
    # Kiểm tra ATR breakout
    atr_breakout, atr_msg = check_atr_breakout(df, atr)
    
    # Tính point để chuyển đổi ATR sang pips
    symbol_info = mt5.symbol_info(symbol)
    point = symbol_info.point if symbol_info else 0.001
    atr_pips = (atr_current / point) / 10 if point > 0 else 0
    
    # Lấy spread
    tick = mt5.symbol_info_tick(symbol)
    spread_points = (tick.ask - tick.bid) / point if point > 0 else 0
    spread_pips = spread_points / 10
    
    return {
        'timeframe': timeframe_name,
        'price': current_price,
        'ema20': ema20_current,
        'ema50': ema50_current,
        'ema200': ema200_current,
        'adx': adx_current,
        'atr': atr_current,
        'atr_pips': atr_pips,
        'rsi': rsi_current,
        'spread_pips': spread_pips,
        'trend': trend,
        'trend_strength': trend_strength,
        'higher_highs': higher_highs,
        'higher_lows': higher_lows,
        'ema_aligned': ema_aligned,
        'ema_alignment_msg': ema_alignment_msg,
        'volume_spike': volume_spike,
        'volume_msg': volume_msg,
        'atr_breakout': atr_breakout,
        'atr_msg': atr_msg,
        'peaks': peaks,
        'troughs': troughs,
        'df': df,  # Lưu dataframe để tính toán điểm vào
        'symbol': symbol  # Lưu symbol để tính toán
    }

# ==============================================================================
# 5. TÍNH TOÁN ĐIỂM VÀO CỤ THỂ
# ==============================================================================

def find_supply_demand_zones(df, lookback=50):
    """Tìm vùng supply (kháng cự) và demand (hỗ trợ) trên H4"""
    supply_zones = []  # Vùng kháng cự (cho SELL)
    demand_zones = []  # Vùng hỗ trợ (cho BUY)
    
    if len(df) < lookback:
        lookback = len(df)
    
    recent_data = df.iloc[-lookback:]
    
    # Tìm các vùng supply (đỉnh với volume cao)
    for i in range(5, len(recent_data) - 5):
        # Kiểm tra đỉnh
        is_peak = True
        for j in range(i-3, i+4):
            if j != i and recent_data.iloc[j]['high'] >= recent_data.iloc[i]['high']:
                is_peak = False
                break
        
        if is_peak:
            high_price = recent_data.iloc[i]['high']
            volume = recent_data.iloc[i]['tick_volume']
            # Supply zone: đỉnh với volume cao
            avg_volume = recent_data['tick_volume'].mean()
            if volume > avg_volume * 1.2:
                supply_zones.append({
                    'price': high_price,
                    'volume': volume,
                    'index': i
                })
    
    # Tìm các vùng demand (đáy với volume cao)
    for i in range(5, len(recent_data) - 5):
        # Kiểm tra đáy
        is_trough = True
        for j in range(i-3, i+4):
            if j != i and recent_data.iloc[j]['low'] <= recent_data.iloc[i]['low']:
                is_trough = False
                break
        
        if is_trough:
            low_price = recent_data.iloc[i]['low']
            volume = recent_data.iloc[i]['tick_volume']
            # Demand zone: đáy với volume cao
            avg_volume = recent_data['tick_volume'].mean()
            if volume > avg_volume * 1.2:
                demand_zones.append({
                    'price': low_price,
                    'volume': volume,
                    'index': i
                })
    
    # Sắp xếp và lấy vùng gần nhất
    supply_zones.sort(key=lambda x: x['index'], reverse=True)
    demand_zones.sort(key=lambda x: x['index'], reverse=True)
    
    return supply_zones[:3], demand_zones[:3]  # Trả về 3 vùng gần nhất

def calculate_entry_prices(analysis_m15, analysis_h1, analysis_h4, analysis_d1):
    """Tính toán điểm vào cụ thể dựa trên phân tích"""
    entry_details = []
    
    # M15: Pullback về EMA20/EMA50
    if analysis_m15 and 'ema20' in analysis_m15 and 'ema50' in analysis_m15:
        ema20 = analysis_m15['ema20']
        ema50 = analysis_m15['ema50']
        current_price = analysis_m15['price']
        
        if analysis_m15['trend'] == 'BULLISH':
            # BUY: Pullback về EMA20 hoặc EMA50
            entry_ema20 = ema20
            entry_ema50 = ema50
            # Chọn EMA gần giá hơn
            if abs(current_price - ema20) < abs(current_price - ema50):
                entry_price = entry_ema20
                entry_type = "EMA20"
            else:
                entry_price = entry_ema50
                entry_type = "EMA50"
            
            atr_value = analysis_m15.get('atr', 0)
            distance_atr = abs(current_price - entry_price) / atr_value if atr_value > 0 else 0
            
            entry_details.append({
                'timeframe': 'M15',
                'type': 'BUY',
                'strategy': f'Pullback về {entry_type}',
                'entry_price': entry_price,
                'current_price': current_price,
                'distance_atr': distance_atr,
                'distance_pips': analysis_m15.get('atr_pips', 0) * distance_atr if distance_atr > 0 else 0
            })
        elif analysis_m15['trend'] == 'BEARISH':
            # SELL: Pullback về EMA20 hoặc EMA50
            entry_ema20 = ema20
            entry_ema50 = ema50
            # Chọn EMA gần giá hơn
            if abs(current_price - ema20) < abs(current_price - ema50):
                entry_price = entry_ema20
                entry_type = "EMA20"
            else:
                entry_price = entry_ema50
                entry_type = "EMA50"
            
            atr_value = analysis_m15.get('atr', 0)
            distance_atr = abs(current_price - entry_price) / atr_value if atr_value > 0 else 0
            
            entry_details.append({
                'timeframe': 'M15',
                'type': 'SELL',
                'strategy': f'Pullback về {entry_type}',
                'entry_price': entry_price,
                'current_price': current_price,
                'distance_atr': distance_atr,
                'distance_pips': analysis_m15.get('atr_pips', 0) * distance_atr if distance_atr > 0 else 0
            })
    
    # H4: Supply/Demand zones
    if analysis_h4 and 'df' in analysis_h4:
        df_h4 = analysis_h4['df']
        supply_zones, demand_zones = find_supply_demand_zones(df_h4)
        current_price = analysis_h4['price']
        
        if analysis_h4['trend'] == 'BEARISH' and supply_zones:
            # SELL: Vùng supply gần nhất
            nearest_supply = supply_zones[0]
            entry_price = nearest_supply['price']
            atr_value = analysis_h4.get('atr', 0)
            distance_atr = abs(current_price - entry_price) / atr_value if atr_value > 0 else 0
            
            entry_details.append({
                'timeframe': 'H4',
                'type': 'SELL',
                'strategy': 'Vùng supply mạnh',
                'entry_price': entry_price,
                'current_price': current_price,
                'distance_atr': distance_atr,
                'distance_pips': analysis_h4.get('atr_pips', 0) * distance_atr if distance_atr > 0 else 0,
                'zone_volume': nearest_supply['volume']
            })
        elif analysis_h4['trend'] == 'BULLISH' and demand_zones:
            # BUY: Vùng demand gần nhất
            nearest_demand = demand_zones[0]
            entry_price = nearest_demand['price']
            atr_value = analysis_h4.get('atr', 0)
            distance_atr = abs(current_price - entry_price) / atr_value if atr_value > 0 else 0
            
            entry_details.append({
                'timeframe': 'H4',
                'type': 'BUY',
                'strategy': 'Vùng demand mạnh',
                'entry_price': entry_price,
                'current_price': current_price,
                'distance_atr': distance_atr,
                'distance_pips': analysis_h4.get('atr_pips', 0) * distance_atr if distance_atr > 0 else 0,
                'zone_volume': nearest_demand['volume']
            })
    
    # H1: Retest vùng hỗ trợ/kháng cự (dựa trên peaks/troughs)
    if analysis_h1 and 'peaks' in analysis_h1 and 'troughs' in analysis_h1:
        peaks = analysis_h1['peaks']
        troughs = analysis_h1['troughs']
        current_price = analysis_h1['price']
        
        if analysis_h1['trend'] == 'BEARISH' and peaks:
            # SELL: Retest đỉnh gần nhất (kháng cự)
            nearest_peak = sorted(peaks, key=lambda x: x[1], reverse=True)[0]
            entry_price = nearest_peak[1]
            atr_value = analysis_h1.get('atr', 0)
            distance_atr = abs(current_price - entry_price) / atr_value if atr_value > 0 else 0
            
            entry_details.append({
                'timeframe': 'H1',
                'type': 'SELL',
                'strategy': 'Retest vùng kháng cự',
                'entry_price': entry_price,
                'current_price': current_price,
                'distance_atr': distance_atr,
                'distance_pips': analysis_h1.get('atr_pips', 0) * distance_atr if distance_atr > 0 else 0
            })
        elif analysis_h1['trend'] == 'BULLISH' and troughs:
            # BUY: Retest đáy gần nhất (hỗ trợ)
            nearest_trough = sorted(troughs, key=lambda x: x[1])[0]
            entry_price = nearest_trough[1]
            atr_value = analysis_h1.get('atr', 0)
            distance_atr = abs(current_price - entry_price) / atr_value if atr_value > 0 else 0
            
            entry_details.append({
                'timeframe': 'H1',
                'type': 'BUY',
                'strategy': 'Retest vùng hỗ trợ',
                'entry_price': entry_price,
                'current_price': current_price,
                'distance_atr': distance_atr,
                'distance_pips': analysis_h1.get('atr_pips', 0) * distance_atr if distance_atr > 0 else 0
            })
    
    return entry_details

# ==============================================================================
# 6. GỢI Ý ĐIỂM VÀO LỆNH
# ==============================================================================

def get_entry_suggestions(analysis_m15, analysis_h1, analysis_h4, analysis_d1):
    """Gợi ý điểm vào lệnh dựa trên phân tích đa khung thời gian với điểm vào cụ thể"""
    suggestions = []
    entry_details = calculate_entry_prices(analysis_m15, analysis_h1, analysis_h4, analysis_d1)
    
    # Multi-timeframe confluence: H1 cùng hướng, M15 cho điểm entry
    if analysis_h1 and analysis_m15:
        if analysis_h1['trend'] == 'BULLISH' and analysis_m15['trend'] == 'BULLISH':
            suggestions.append({
                'text': "✅ BUY Signal: H1 & M15 đều BULLISH - Có thể vào lệnh BUY",
                'entry': None
            })
        elif analysis_h1['trend'] == 'BEARISH' and analysis_m15['trend'] == 'BEARISH':
            suggestions.append({
                'text': "✅ SELL Signal: H1 & M15 đều BEARISH - Có thể vào lệnh SELL",
                'entry': None
            })
        elif analysis_h1['trend'] != analysis_m15['trend']:
            suggestions.append({
                'text': "⚠️ Không có confluence: H1 và M15 khác hướng - Tránh giao dịch",
                'entry': None
            })
    
    # M15: Pullback về EMA20/EMA50
    if analysis_m15:
        m15_entry = [e for e in entry_details if e['timeframe'] == 'M15']
        if analysis_m15['trend'] == 'BULLISH':
            if m15_entry:
                entry = m15_entry[0]
                suggestions.append({
                    'text': f"📊 M15: Pullback về {entry['strategy']} để BUY | 💰 Entry: {entry['entry_price']:.5f} (Giá hiện tại: {entry['current_price']:.5f})",
                    'entry': entry
                })
            else:
                suggestions.append({
                    'text': "📊 M15: Tìm pullback về EMA20/EMA50 để BUY",
                    'entry': None
                })
        elif analysis_m15['trend'] == 'BEARISH':
            if m15_entry:
                entry = m15_entry[0]
                suggestions.append({
                    'text': f"📊 M15: Pullback về {entry['strategy']} để SELL | 💰 Entry: {entry['entry_price']:.5f} (Giá hiện tại: {entry['current_price']:.5f})",
                    'entry': entry
                })
            else:
                suggestions.append({
                    'text': "📊 M15: Tìm pullback về EMA20/EMA50 để SELL",
                    'entry': None
                })
    
    # H1: Retest vùng hỗ trợ/kháng cự
    if analysis_h1:
        h1_entry = [e for e in entry_details if e['timeframe'] == 'H1']
        if analysis_h1['trend'] == 'BULLISH':
            if h1_entry:
                entry = h1_entry[0]
                suggestions.append({
                    'text': f"📊 H1: {entry['strategy']} để BUY | 💰 Entry: {entry['entry_price']:.5f} (Giá hiện tại: {entry['current_price']:.5f})",
                    'entry': entry
                })
            else:
                suggestions.append({
                    'text': "📊 H1: Retest vùng hỗ trợ để BUY",
                    'entry': None
                })
        elif analysis_h1['trend'] == 'BEARISH':
            if h1_entry:
                entry = h1_entry[0]
                suggestions.append({
                    'text': f"📊 H1: {entry['strategy']} để SELL | 💰 Entry: {entry['entry_price']:.5f} (Giá hiện tại: {entry['current_price']:.5f})",
                    'entry': entry
                })
            else:
                suggestions.append({
                    'text': "📊 H1: Retest vùng kháng cự để SELL",
                    'entry': None
                })
    
    # H4: Supply/Demand zones
    if analysis_h4:
        h4_entry = [e for e in entry_details if e['timeframe'] == 'H4']
        if analysis_h4['trend'] == 'BULLISH':
            if h4_entry:
                entry = h4_entry[0]
                suggestions.append({
                    'text': f"📊 H4: Tìm vùng {entry['strategy']} để BUY | 💰 Entry: {entry['entry_price']:.5f} (Giá hiện tại: {entry['current_price']:.5f})",
                    'entry': entry
                })
            else:
                suggestions.append({
                    'text': "📊 H4: Tìm vùng demand mạnh để BUY",
                    'entry': None
                })
        elif analysis_h4['trend'] == 'BEARISH':
            if h4_entry:
                entry = h4_entry[0]
                suggestions.append({
                    'text': f"📊 H4: Tìm vùng {entry['strategy']} để SELL | 💰 Entry: {entry['entry_price']:.5f} (Giá hiện tại: {entry['current_price']:.5f})",
                    'entry': entry
                })
            else:
                suggestions.append({
                    'text': "📊 H4: Tìm vùng supply mạnh để SELL",
                    'entry': None
                })
    
    # D1: Bias chính
    if analysis_d1:
        if analysis_d1['trend'] == 'BULLISH':
            suggestions.append({
                'text': "📊 D1: Bias BULLISH - Chỉ BUY, tránh SELL",
                'entry': None
            })
        elif analysis_d1['trend'] == 'BEARISH':
            suggestions.append({
                'text': "📊 D1: Bias BEARISH - Chỉ SELL, tránh BUY",
                'entry': None
            })
        else:
            suggestions.append({
                'text': "📊 D1: Bias SIDEWAYS - Cẩn thận giao dịch",
                'entry': None
            })
    
    return suggestions

# ==============================================================================
# 6. GỬI TELEGRAM
# ==============================================================================

def split_message(message, max_length=4096):
    """Chia message thành nhiều phần nếu quá dài"""
    if len(message) <= max_length:
        return [message]
    
    parts = []
    current_part = ""
    
    # Chia theo dòng để tránh cắt giữa chữ
    lines = message.split('\n')
    
    for line in lines:
        # Nếu thêm dòng này vượt quá giới hạn, lưu phần hiện tại và bắt đầu phần mới
        if len(current_part) + len(line) + 1 > max_length:
            if current_part:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                # Dòng quá dài, phải cắt
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
            # Thêm header cho phần tiếp theo
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
                    break  # Thành công, chuyển sang phần tiếp theo
                else:
                    # Log chi tiết lỗi
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
                        time.sleep(2)  # Đợi 2 giây trước khi retry
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

def format_telegram_message_compact(symbol, analysis_m15, analysis_h1, analysis_h4, analysis_d1, suggestions):
    """Định dạng tin nhắn Telegram rút gọn (cho BTC, ETH)"""
    msg = f"<b>📊 {symbol}</b>\n"
    msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    # Chỉ hiển thị H1, H4, D1 (bỏ M15)
    timeframes = [
        ("H1", analysis_h1),
        ("H4", analysis_h4),
        ("D1", analysis_d1)
    ]
    
    for tf_name, analysis in timeframes:
        if analysis:
            trend_emoji = "🟢" if analysis['trend'] == 'BULLISH' else "🔴" if analysis['trend'] == 'BEARISH' else "🟡"
            strength_emoji = "💪" if analysis['trend_strength'] == 'STRONG' else "⚡" if analysis['trend_strength'] == 'MODERATE' else "💤"
            
            msg += f"<b>{tf_name}</b>: {trend_emoji} {analysis['trend']} {strength_emoji}\n"
            msg += f"💰 {analysis['price']:.2f} | ADX: {analysis['adx']:.1f} | ATR: {analysis['atr_pips']:.1f}p\n"
            
            # Chỉ hiển thị cảnh báo quan trọng
            if analysis['atr_breakout']:
                msg += "⚠️ ATR breakout\n"
            
            msg += "\n"
    
    # Gợi ý vào lệnh (chỉ 2-3 gợi ý đầu tiên)
    if suggestions:
        msg += "<b>💡 GỢI Ý:</b>\n"
        for suggestion in suggestions[:3]:  # Chỉ lấy 3 gợi ý đầu
            if isinstance(suggestion, dict):
                msg += f"• {suggestion['text']}\n"
            else:
                msg += f"• {suggestion}\n"
    
    return msg

def format_telegram_message(symbol, analysis_m15, analysis_h1, analysis_h4, analysis_d1, suggestions):
    """Định dạng tin nhắn Telegram đầy đủ (cho XAUUSD, BNBUSD)"""
    msg = f"<b>📊 TREND ANALYSIS - {symbol}</b>\n"
    msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    msg += "=" * 40 + "\n\n"
    
    # Phân tích từng khung thời gian
    timeframes = [
        ("M15", analysis_m15),
        ("H1", analysis_h1),
        ("H4", analysis_h4),
        ("D1", analysis_d1)
    ]
    
    for tf_name, analysis in timeframes:
        if analysis:
            trend_emoji = "🟢" if analysis['trend'] == 'BULLISH' else "🔴" if analysis['trend'] == 'BEARISH' else "🟡"
            strength_emoji = "💪" if analysis['trend_strength'] == 'STRONG' else "⚡" if analysis['trend_strength'] == 'MODERATE' else "💤"
            
            msg += f"<b>{tf_name} ({trend_emoji} {analysis['trend']} {strength_emoji})</b>\n"
            msg += f"💰 Giá: {analysis['price']:.5f}\n"
            msg += f"📈 EMA50: {analysis['ema50']:.5f} | EMA200: {analysis['ema200']:.5f}\n"
            msg += f"📊 ADX: {analysis['adx']:.2f} | ATR: {analysis['atr_pips']:.2f} pips\n"
            msg += f"📉 RSI: {analysis['rsi']:.2f} | Spread: {analysis['spread_pips']:.2f} pips\n"
            
            if analysis['ema_aligned']:
                msg += f"✅ {analysis['ema_alignment_msg']}\n"
            else:
                msg += f"⚠️ {analysis['ema_alignment_msg']}\n"
            
            if analysis['volume_spike']:
                msg += f"⚠️ {analysis['volume_msg']}\n"
            
            if analysis['atr_breakout']:
                msg += f"⚠️ {analysis['atr_msg']}\n"
            
            msg += "\n"
    
    # Gợi ý vào lệnh
    if suggestions:
        msg += "<b>💡 GỢI Ý VÀO LỆNH:</b>\n"
        for suggestion in suggestions:
            if isinstance(suggestion, dict):
                msg += f"• {suggestion['text']}\n"
                # Hiển thị thêm thông tin chi tiết nếu có entry
                if suggestion.get('entry'):
                    entry = suggestion['entry']
                    if entry.get('distance_pips'):
                        msg += f"  📏 Khoảng cách: {entry['distance_pips']:.1f} pips ({entry.get('distance_atr', 0):.2f} ATR)\n"
            else:
                msg += f"• {suggestion}\n"
        msg += "\n"
    
    # Cảnh báo
    warnings = []
    if analysis_h1 and analysis_h1['atr_breakout']:
        warnings.append("⚠️ CẢNH BÁO: ATR breakout - Có thể có tin mạnh")
    if analysis_h1 and analysis_h1['volume_spike']:
        warnings.append("⚠️ CẢNH BÁO: Volume spike - Có thể false breakout")
    if analysis_d1 and analysis_d1['trend'] == 'SIDEWAYS':
        warnings.append("⚠️ CẢNH BÁO: D1 SIDEWAYS - Tránh giao dịch ngược trend lớn")
    
    if warnings:
        msg += "<b>⚠️ CẢNH BÁO:</b>\n"
        for warning in warnings:
            msg += f"{warning}\n"
    
    return msg

def format_all_symbols_message(all_results):
    """Định dạng tin nhắn Telegram cho tất cả các cặp (chi tiết đầy đủ)"""
    msg = f"<b>📊 TREND ANALYSIS - TẤT CẢ CẶP</b>\n"
    msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    msg += "=" * 50 + "\n\n"
    
    for symbol, result in all_results.items():
        if result is None:
            msg += f"<b>❌ {symbol}</b>: Không lấy được dữ liệu\n"
            msg += f"   ⚠️ Kiểm tra: Symbol có tồn tại và được enable trong MT5 không?\n\n"
            continue
        
        analysis_m15, analysis_h1, analysis_h4, analysis_d1, suggestions, actual_symbol = result
        
        # Dùng format compact cho BTC và ETH trong message tổng hợp
        if symbol in ["BTCUSD", "ETHUSD"]:
            msg += f"<b>📊 {symbol} ({actual_symbol})</b>\n"
            # Chỉ hiển thị H1, H4, D1
            timeframes = [
                ("H1", analysis_h1),
                ("H4", analysis_h4),
                ("D1", analysis_d1)
            ]
            
            for tf_name, analysis in timeframes:
                if analysis:
                    trend_emoji = "🟢" if analysis['trend'] == 'BULLISH' else "🔴" if analysis['trend'] == 'BEARISH' else "🟡"
                    strength_emoji = "💪" if analysis['trend_strength'] == 'STRONG' else "⚡" if analysis['trend_strength'] == 'MODERATE' else "💤"
                    
                    msg += f"<b>{tf_name}</b>: {trend_emoji} {analysis['trend']} {strength_emoji} | "
                    msg += f"💰 {analysis['price']:.2f} | ADX: {analysis['adx']:.1f} | ATR: {analysis['atr_pips']:.1f}p\n"
            
            # Gợi ý (chỉ 2 đầu tiên)
            if suggestions:
                first_suggestion = suggestions[0]
                if isinstance(first_suggestion, dict):
                    msg += f"💡 {first_suggestion['text']}\n"
                else:
                    msg += f"💡 {first_suggestion}\n"
            
            msg += "\n"
        else:
            # Format đầy đủ cho XAUUSD, BNBUSD
            msg += f"<b>📊 {symbol} ({actual_symbol})</b>\n"
            msg += "=" * 40 + "\n\n"
            
            # Phân tích từng khung thời gian
            timeframes = [
                ("M15", analysis_m15),
                ("H1", analysis_h1),
                ("H4", analysis_h4),
                ("D1", analysis_d1)
            ]
            
            for tf_name, analysis in timeframes:
                if analysis:
                    trend_emoji = "🟢" if analysis['trend'] == 'BULLISH' else "🔴" if analysis['trend'] == 'BEARISH' else "🟡"
                    strength_emoji = "💪" if analysis['trend_strength'] == 'STRONG' else "⚡" if analysis['trend_strength'] == 'MODERATE' else "💤"
                    
                    msg += f"<b>{tf_name} ({trend_emoji} {analysis['trend']} {strength_emoji})</b>\n"
                    msg += f"💰 Giá: {analysis['price']:.5f}\n"
                    msg += f"📈 EMA50: {analysis['ema50']:.5f} | EMA200: {analysis['ema200']:.5f}\n"
                    msg += f"📊 ADX: {analysis['adx']:.2f} | ATR: {analysis['atr_pips']:.2f} pips\n"
                    msg += f"📉 RSI: {analysis['rsi']:.2f} | Spread: {analysis['spread_pips']:.2f} pips\n"
                    
                    if analysis['ema_aligned']:
                        msg += f"✅ {analysis['ema_alignment_msg']}\n"
                    else:
                        msg += f"⚠️ {analysis['ema_alignment_msg']}\n"
                    
                    if analysis['volume_spike']:
                        msg += f"⚠️ {analysis['volume_msg']}\n"
                    
                    if analysis['atr_breakout']:
                        msg += f"⚠️ {analysis['atr_msg']}\n"
                    
                    msg += "\n"
            
            # Gợi ý vào lệnh
            if suggestions:
                msg += "<b>💡 GỢI Ý VÀO LỆNH:</b>\n"
                for suggestion in suggestions:
                    if isinstance(suggestion, dict):
                        msg += f"• {suggestion['text']}\n"
                        # Hiển thị thêm thông tin chi tiết nếu có entry
                        if suggestion.get('entry'):
                            entry = suggestion['entry']
                            if entry.get('distance_pips'):
                                msg += f"  📏 Khoảng cách: {entry['distance_pips']:.1f} pips ({entry.get('distance_atr', 0):.2f} ATR)\n"
                    else:
                        msg += f"• {suggestion}\n"
                msg += "\n"
            
            # Cảnh báo
            warnings = []
            if analysis_h1 and analysis_h1['atr_breakout']:
                warnings.append("⚠️ CẢNH BÁO: ATR breakout - Có thể có tin mạnh")
            if analysis_h1 and analysis_h1['volume_spike']:
                warnings.append("⚠️ CẢNH BÁO: Volume spike - Có thể false breakout")
            if analysis_d1 and analysis_d1['trend'] == 'SIDEWAYS':
                warnings.append("⚠️ CẢNH BÁO: D1 SIDEWAYS - Tránh giao dịch ngược trend lớn")
            
            if warnings:
                msg += "<b>⚠️ CẢNH BÁO:</b>\n"
                for warning in warnings:
                    msg += f"{warning}\n"
            
            msg += "\n" + "=" * 50 + "\n\n"
    
    return msg

# ==============================================================================
# 7. MAIN
# ==============================================================================

def find_symbol(base_name):
    """Tìm symbol thực tế trong MT5"""
    print(f"  🔍 Đang tìm symbol cho: {base_name}")
    
    # Danh sách các biến thể để thử (theo thứ tự ưu tiên)
    variants = []
    
    # Thêm các biến thể từ SYMBOLS_CONFIG nếu có
    if base_name in SYMBOLS_CONFIG:
        variants.extend(SYMBOLS_CONFIG[base_name])
        print(f"  📝 Sẽ thử {len(SYMBOLS_CONFIG[base_name])} biến thể từ config: {', '.join(SYMBOLS_CONFIG[base_name][:3])}...")
    
    # Thêm các biến thể mặc định
    default_variants = [
        base_name + "m",  # XAUUSDm
        base_name,         # XAUUSD
        base_name.upper(),  # XAUUSD
        base_name.lower(),  # xauusd
        base_name.replace("USD", "/USD"),  # XAU/USD
        base_name.replace("USD", "USDm"),  # XAUUSDm (nếu chưa có m)
    ]
    
    # Thêm các biến thể USDT cho crypto
    if "BTC" in base_name or "ETH" in base_name or "BNB" in base_name:
        default_variants.extend([
            base_name.replace("USD", "USDT"),  # BTCUSDT
            base_name.replace("USD", "USDT") + "m",  # BTCUSDTm
        ])
    
    variants.extend(default_variants)
    
    # Loại bỏ trùng lặp nhưng giữ thứ tự
    seen = set()
    unique_variants = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique_variants.append(v)
    
    print(f"  📝 Tổng cộng {len(unique_variants)} biến thể để thử")
    
    # Thử từng biến thể
    for variant in unique_variants:
        symbol_info = mt5.symbol_info(variant)
        if symbol_info is not None:
            print(f"  ✅ Symbol {variant} tồn tại!")
            # Kiểm tra symbol có được enable không
            if not symbol_info.visible:
                print(f"  ⚠️ Symbol {variant} chưa được enable, đang enable...")
                if mt5.symbol_select(variant, True):
                    print(f"  ✅ Đã enable symbol {variant}")
                else:
                    print(f"  ❌ Không thể enable symbol {variant}, bỏ qua...")
                    continue
            
            # Test lấy dữ liệu
            test_rates = mt5.copy_rates_from_pos(variant, mt5.TIMEFRAME_H1, 0, 1)
            if test_rates is None or len(test_rates) == 0:
                print(f"  ⚠️ Symbol {variant} tồn tại nhưng không lấy được dữ liệu, thử tiếp...")
                continue
            
            print(f"  ✅ Tìm thấy và có thể lấy dữ liệu: {variant}")
            return variant
    
    # Nếu không tìm thấy, thử tìm trong danh sách tất cả symbols
    print(f"  ⚠️ Không tìm thấy trong biến thể, đang tìm trong danh sách symbols...")
    all_symbols = mt5.symbols_get()
    if all_symbols:
        matches = []
        for sym in all_symbols:
            sym_name = sym.name
            # Tìm symbol có chứa base_name (không phân biệt hoa thường)
            if base_name.upper() in sym_name.upper():
                matches.append((sym_name, sym.visible))
        
        if matches:
            print(f"  📌 Tìm thấy {len(matches)} symbol tương tự:")
            for sym_name, is_visible in matches[:5]:  # Chỉ hiển thị 5 đầu tiên
                status = "✅ Enabled" if is_visible else "❌ Disabled"
                print(f"     - {sym_name} ({status})")
            
            # Thử symbol đầu tiên
            for sym_name, is_visible in matches:
                if not is_visible:
                    if mt5.symbol_select(sym_name, True):
                        print(f"  ✅ Đã enable {sym_name}")
                    else:
                        continue
                
                # Test lấy dữ liệu
                test_rates = mt5.copy_rates_from_pos(sym_name, mt5.TIMEFRAME_H1, 0, 1)
                if test_rates is not None and len(test_rates) > 0:
                    print(f"  ✅ Tìm thấy và có thể lấy dữ liệu: {sym_name}")
                    return sym_name
    
    print(f"  ❌ Không tìm thấy symbol cho {base_name}")
    return None

def analyze_symbol(symbol_base):
    """Phân tích một cặp tiền tệ"""
    print(f"\n{'='*70}")
    print(f"📊 Đang phân tích: {symbol_base}")
    print(f"{'='*70}")
    
    # Tìm symbol thực tế
    symbol = find_symbol(symbol_base)
    if symbol is None:
        return None
    
    # Phân tích các khung thời gian
    print("Đang phân tích các khung thời gian...")
    analysis_m15 = analyze_timeframe(symbol, mt5.TIMEFRAME_M15, "M15")
    analysis_h1 = analyze_timeframe(symbol, mt5.TIMEFRAME_H1, "H1")
    analysis_h4 = analyze_timeframe(symbol, mt5.TIMEFRAME_H4, "H4")
    analysis_d1 = analyze_timeframe(symbol, mt5.TIMEFRAME_D1, "D1")
    
    # Gợi ý vào lệnh
    suggestions = get_entry_suggestions(analysis_m15, analysis_h1, analysis_h4, analysis_d1)
    
    # In ra console
    print("\n" + "="*70)
    print(f"KẾT QUẢ PHÂN TÍCH: {symbol}")
    print("="*70)
    
    for analysis in [analysis_m15, analysis_h1, analysis_h4, analysis_d1]:
        if analysis:
            print(f"\n{analysis['timeframe']}: {analysis['trend']} ({analysis['trend_strength']})")
            print(f"  Giá: {analysis['price']:.5f} | EMA50: {analysis['ema50']:.5f} | EMA200: {analysis['ema200']:.5f}")
            print(f"  ADX: {analysis['adx']:.2f} | ATR: {analysis['atr_pips']:.2f} pips | RSI: {analysis['rsi']:.2f}")
            if analysis['ema_aligned']:
                print(f"  ✅ {analysis['ema_alignment_msg']}")
            if analysis['volume_spike']:
                print(f"  ⚠️ {analysis['volume_msg']}")
            if analysis['atr_breakout']:
                print(f"  ⚠️ {analysis['atr_msg']}")
    
    print("\n" + "="*70)
    print("GỢI Ý VÀO LỆNH:")
    print("="*70)
    for suggestion in suggestions:
        if isinstance(suggestion, dict):
            print(f"  {suggestion['text']}")
            if suggestion.get('entry'):
                entry = suggestion['entry']
            print(f"    📊 Entry Price: {entry['entry_price']:.5f}")
            print(f"    📊 Current Price: {entry['current_price']:.5f}")
            if entry.get('distance_pips'):
                print(f"    📏 Distance: {entry['distance_pips']:.1f} pips ({entry.get('distance_atr', 0):.2f} ATR)")
        else:
            print(f"  {suggestion}")
    
    return (analysis_m15, analysis_h1, analysis_h4, analysis_d1, suggestions, symbol)

def list_available_symbols(search_terms=None):
    """Liệt kê các symbol có sẵn trong MT5"""
    print(f"\n{'='*70}")
    print("📋 ĐANG TÌM CÁC SYMBOL CÓ SẴN TRONG MT5...")
    print(f"{'='*70}")
    
    all_symbols = mt5.symbols_get()
    if not all_symbols:
        print("❌ Không lấy được danh sách symbols từ MT5")
        return []
    
    print(f"✅ Tìm thấy {len(all_symbols)} symbols trong MT5")
    
    if search_terms:
        print(f"\n🔍 Tìm symbols chứa: {', '.join(search_terms)}")
        found_symbols = []
        for term in search_terms:
            matches = [s.name for s in all_symbols if term.upper() in s.name.upper()]
            if matches:
                found_symbols.extend(matches)
                print(f"\n  📌 Symbols chứa '{term}':")
                for sym in matches[:10]:  # Chỉ hiển thị 10 đầu tiên
                    symbol_info = mt5.symbol_info(sym)
                    status = "✅ Enabled" if symbol_info.visible else "❌ Disabled"
                    print(f"     - {sym} ({status})")
        return list(set(found_symbols))
    
    return [s.name for s in all_symbols]

def main():
    print(f"\n{'='*70}")
    print(f"📊 BOT CHECK TREND - TẤT CẢ CẶP")
    print(f"{'='*70}\n")
    
    # Khởi tạo và kết nối MT5
    if not initialize_mt5():
        print("\n❌ Không thể kết nối MT5. Dừng bot.")
        mt5.shutdown()
        return
    
    # Liệt kê symbols có sẵn cho các cặp cần check
    search_terms = ["XAU", "GOLD", "ETH", "BTC", "BNB"]
    available_symbols = list_available_symbols(search_terms)
    
    all_results = {}
    
    # Phân tích và gửi Telegram từng cặp ngay sau khi phân tích xong
    print("\n" + "="*70)
    print("PHÂN TÍCH VÀ GỬI TELEGRAM TỪNG CẶP...")
    print("="*70)
    
    for symbol_base in SYMBOLS_CONFIG.keys():
        # Phân tích cặp này
        result = analyze_symbol(symbol_base)
        all_results[symbol_base] = result
        
        # Gửi Telegram ngay sau khi phân tích xong
        if result:
            analysis_m15, analysis_h1, analysis_h4, analysis_d1, suggestions, actual_symbol = result
            
            # Đưa ra kết luận
            print("\n" + "="*70)
            print(f"📋 KẾT LUẬN: {symbol_base} ({actual_symbol})")
            print("="*70)
            
            # Kết luận dựa trên H1 (khung chính)
            if analysis_h1:
                trend_emoji = "🟢" if analysis_h1['trend'] == 'BULLISH' else "🔴" if analysis_h1['trend'] == 'BEARISH' else "🟡"
                strength_emoji = "💪" if analysis_h1['trend_strength'] == 'STRONG' else "⚡" if analysis_h1['trend_strength'] == 'MODERATE' else "💤"
                
                print(f"📊 Xu hướng chính (H1): {trend_emoji} {analysis_h1['trend']} {strength_emoji}")
                print(f"💰 Giá: {analysis_h1['price']:.5f}")
                print(f"📈 ADX: {analysis_h1['adx']:.2f} | ATR: {analysis_h1['atr_pips']:.2f} pips")
                
                # Đánh giá tổng thể
                if analysis_h1['trend'] == 'BULLISH' and analysis_h1['trend_strength'] == 'STRONG':
                    print("✅ KẾT LUẬN: Xu hướng TĂNG MẠNH - Có thể BUY")
                elif analysis_h1['trend'] == 'BEARISH' and analysis_h1['trend_strength'] == 'STRONG':
                    print("✅ KẾT LUẬN: Xu hướng GIẢM MẠNH - Có thể SELL")
                elif analysis_h1['trend'] == 'BULLISH':
                    print("⚠️ KẾT LUẬN: Xu hướng TĂNG YẾU - Cẩn thận khi BUY")
                elif analysis_h1['trend'] == 'BEARISH':
                    print("⚠️ KẾT LUẬN: Xu hướng GIẢM YẾU - Cẩn thận khi SELL")
                else:
                    print("⚠️ KẾT LUẬN: SIDEWAYS - Tránh giao dịch")
                
                # Cảnh báo
                if analysis_h1['atr_breakout']:
                    print("⚠️ CẢNH BÁO: ATR breakout - Có thể có tin mạnh")
                if analysis_h1['volume_spike']:
                    print("⚠️ CẢNH BÁO: Volume spike - Có thể false breakout")
            
            # Gửi Telegram (dùng actual_symbol để hiển thị)
            # Dùng format compact cho BTC và ETH để tránh lỗi 400
            if symbol_base in ["BTCUSD", "ETHUSD"]:
                telegram_msg = format_telegram_message_compact(actual_symbol, analysis_m15, analysis_h1, analysis_h4, analysis_d1, suggestions)
            else:
                telegram_msg = format_telegram_message(actual_symbol, analysis_m15, analysis_h1, analysis_h4, analysis_d1, suggestions)
            print(f"\n📤 Đang gửi Telegram cho {symbol_base} ({actual_symbol})...")
            if send_telegram(telegram_msg):
                print(f"✅ Đã gửi log {symbol_base} ({actual_symbol}) về Telegram")
            else:
                print(f"❌ Không thể gửi Telegram cho {symbol_base} sau 3 lần thử")
        else:
            print(f"\n⚠️ Không có dữ liệu để gửi cho {symbol_base}")
        
        print("\n" + "="*70)
        
        # Sleep 10 giây trước khi check cặp tiếp theo
        if symbol_base != list(SYMBOLS_CONFIG.keys())[-1]:  # Không sleep sau cặp cuối cùng
            print("⏳ Đợi 10 giây trước khi check cặp tiếp theo...")
            time.sleep(10)
    
    print("\n" + "="*70)
    print("HOÀN TẤT!")
    print("="*70)

mt5.shutdown()

if __name__ == "__main__":
    main()
