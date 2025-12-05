import MetaTrader5 as mt5
import pandas as pd
import json
import os
import requests
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
SYMBOL = config.get("SYMBOL", "XAUUSDm")
MT5_PATH = config.get("PATH")

# Telegram Configuration
TELEGRAM_TOKEN = config.get("TELEGRAM_TOKEN", "6398751744:AAGp7VH7B00_kzMqdaFB59xlqAXnlKTar-g")
CHAT_ID = config.get("CHAT_ID", "1887610382")

# ==============================================================================
# 2. KẾT NỐI MT5
# ==============================================================================

if not mt5.initialize(path=MT5_PATH,login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print("MT5 Init Failed")
    quit()

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
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 200)
    if rates is None or len(rates) == 0:
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    
    # Tính các chỉ báo
    ema50 = calculate_ema(df['close'], 50)
    ema200 = calculate_ema(df['close'], 200)
    adx = calculate_adx(df, 14)
    atr = calculate_atr(df, 14)
    rsi = calculate_rsi(df['close'], 14)
    
    # Lấy giá trị hiện tại
    current_price = df['close'].iloc[-1]
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
        'troughs': troughs
    }

# ==============================================================================
# 5. GỢI Ý ĐIỂM VÀO LỆNH
# ==============================================================================

def get_entry_suggestions(analysis_m15, analysis_h1, analysis_h4, analysis_d1):
    """Gợi ý điểm vào lệnh dựa trên phân tích đa khung thời gian"""
    suggestions = []
    
    # Multi-timeframe confluence: H1 cùng hướng, M15 cho điểm entry
    if analysis_h1 and analysis_m15:
        if analysis_h1['trend'] == 'BULLISH' and analysis_m15['trend'] == 'BULLISH':
            suggestions.append("✅ BUY Signal: H1 & M15 đều BULLISH - Có thể vào lệnh BUY")
        elif analysis_h1['trend'] == 'BEARISH' and analysis_m15['trend'] == 'BEARISH':
            suggestions.append("✅ SELL Signal: H1 & M15 đều BEARISH - Có thể vào lệnh SELL")
        elif analysis_h1['trend'] != analysis_m15['trend']:
            suggestions.append("⚠️ Không có confluence: H1 và M15 khác hướng - Tránh giao dịch")
    
    # M15: Pullback về EMA20/EMA50
    if analysis_m15:
        if analysis_m15['trend'] == 'BULLISH':
            suggestions.append("📊 M15: Tìm pullback về EMA20/EMA50 để BUY")
        elif analysis_m15['trend'] == 'BEARISH':
            suggestions.append("📊 M15: Tìm pullback về EMA20/EMA50 để SELL")
    
    # H1: Retest vùng hỗ trợ/kháng cự
    if analysis_h1:
        if analysis_h1['trend'] == 'BULLISH':
            suggestions.append("📊 H1: Retest vùng hỗ trợ để BUY")
        elif analysis_h1['trend'] == 'BEARISH':
            suggestions.append("📊 H1: Retest vùng kháng cự để SELL")
    
    # H4: Supply/Demand zones
    if analysis_h4:
        if analysis_h4['trend'] == 'BULLISH':
            suggestions.append("📊 H4: Tìm vùng demand mạnh để BUY")
        elif analysis_h4['trend'] == 'BEARISH':
            suggestions.append("📊 H4: Tìm vùng supply mạnh để SELL")
    
    # D1: Bias chính
    if analysis_d1:
        if analysis_d1['trend'] == 'BULLISH':
            suggestions.append("📊 D1: Bias BULLISH - Chỉ BUY, tránh SELL")
        elif analysis_d1['trend'] == 'BEARISH':
            suggestions.append("📊 D1: Bias BEARISH - Chỉ SELL, tránh BUY")
        else:
            suggestions.append("📊 D1: Bias SIDEWAYS - Cẩn thận giao dịch")
    
    return suggestions

# ==============================================================================
# 6. GỬI TELEGRAM
# ==============================================================================

def send_telegram(message):
    """Gửi tin nhắn qua Telegram"""
    if not CHAT_ID or not TELEGRAM_TOKEN:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"⚠️ Lỗi gửi Telegram: {e}")
        return False

def format_telegram_message(symbol, analysis_m15, analysis_h1, analysis_h4, analysis_d1, suggestions):
    """Định dạng tin nhắn Telegram"""
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
            msg += f"{suggestion}\n"
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

# ==============================================================================
# 7. MAIN
# ==============================================================================

def main():
    print(f"\n{'='*70}")
    print(f"📊 BOT CHECK TREND - {SYMBOL}")
    print(f"{'='*70}\n")
    
    # Phân tích các khung thời gian
    print("Đang phân tích các khung thời gian...")
    analysis_m15 = analyze_timeframe(SYMBOL, mt5.TIMEFRAME_M15, "M15")
    analysis_h1 = analyze_timeframe(SYMBOL, mt5.TIMEFRAME_H1, "H1")
    analysis_h4 = analyze_timeframe(SYMBOL, mt5.TIMEFRAME_H4, "H4")
    analysis_d1 = analyze_timeframe(SYMBOL, mt5.TIMEFRAME_D1, "D1")
    
    # Gợi ý vào lệnh
    suggestions = get_entry_suggestions(analysis_m15, analysis_h1, analysis_h4, analysis_d1)
    
    # In ra console
    print("\n" + "="*70)
    print("KẾT QUẢ PHÂN TÍCH:")
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
        print(f"  {suggestion}")
    
    # Gửi Telegram
    telegram_msg = format_telegram_message(SYMBOL, analysis_m15, analysis_h1, analysis_h4, analysis_d1, suggestions)
    if send_telegram(telegram_msg):
        print("\n✅ Đã gửi log về Telegram")
    else:
        print("\n⚠️ Không thể gửi Telegram")
    
    print("\n" + "="*70)

mt5.shutdown()

if __name__ == "__main__":
    main()
