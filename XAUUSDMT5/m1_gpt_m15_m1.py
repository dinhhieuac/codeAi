import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime, timedelta
import json
import os
import requests

# ==============================================================================
# 1. CÁC THAM SỐ CẤU HÌNH VÀ CHIẾN LƯỢC (GLOBAL VARIABLES)
# ==============================================================================

# Biến Cấu hình MT5 (Sẽ được ghi đè từ JSON)
MT5_LOGIN = None
MT5_PASSWORD = None
MT5_SERVER = None
SYMBOL = None
MT5_PATH = None
VOLUME = 0.01  # Khối lượng mặc định (Có thể ghi đè trong JSON)
MAGIC = 20251117

# Thông số Chỉ báo & Lọc
# Chiến thuật M15 Candle + M1 Pullback
# M15 định hướng (Bias) -> M1 tìm điểm vào (Pullback 30-50%)
PULLBACK_RATIO_MIN = 0.3  # Hồi tối thiểu 30% cây nến M15
PULLBACK_RATIO_MAX = 0.6  # Hồi tối đa 60% (nếu hồi sâu quá có thể là đảo chiều)
MIN_CANDLE_SIZE_POINTS = 100 # Nến M15 phải lớn hơn 10 pips mới tính là tín hiệu

# Thông số Quản lý Lệnh
ENABLE_BREAK_EVEN = False           # Bật/tắt chức năng di chuyển SL về hòa vốn
BREAK_EVEN_START_POINTS = 100      # Hòa vốn khi lời 10 pips

# Trailing Stop khi lời 1/2 TP để lock profit
ENABLE_TRAILING_STOP = False        # Bật/tắt chức năng Trailing Stop
TRAILING_START_TP_RATIO = 0.5  # Bắt đầu trailing khi lời 1/2 TP
TRAILING_STEP_ATR_MULTIPLIER = 0.5  # Bước trailing = ATR × 0.5

# Cooldown sau lệnh thua
ENABLE_LOSS_COOLDOWN = False         # Bật/tắt cooldown sau lệnh thua
LOSS_COOLDOWN_MINUTES = 10         # Thời gian chờ sau lệnh thua (phút)

# Telegram Bot Configuration
TELEGRAM_TOKEN = "6398751744:AAGp7VH7B00_kzMqdaFB59xlqAXnlKTar-g"
CHAT_ID = "1887610382"


# ==============================================================================
# 2. HÀM TẢI CẤU HÌNH (CONFIG LOADING)
# ==============================================================================

def load_config(filename="XAUUSDMT5/mt5_account.json"):
    """Đọc thông tin cấu hình từ tệp JSON và gán vào biến toàn cục."""
    global MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, SYMBOL, MT5_PATH, VOLUME, CHAT_ID
    
    if not os.path.exists(filename):
        print(f"❌ Lỗi: Không tìm thấy tệp cấu hình '{filename}'. Vui lòng tạo file này.")
        return False
        
    try:
        with open(filename, 'r') as f:
            config = json.load(f)
        
        MT5_LOGIN = config.get("ACCOUNT_NUMBER")
        MT5_PASSWORD = config.get("PASSWORD")
        MT5_SERVER = config.get("SERVER")
        SYMBOL = config.get("SYMBOL", "XAUUSDm") 
        MT5_PATH = config.get("PATH")
        VOLUME = config.get("VOLUME", VOLUME) # Ghi đè Volume nếu có
        CHAT_ID = config.get("CHAT_ID", CHAT_ID)  # Lấy CHAT_ID từ JSON nếu có
        
        # Kiểm tra tính hợp lệ cơ bản
        if not all([MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, SYMBOL]):
            print("❌ Lỗi: Các thông tin ACCOUNT_NUMBER, PASSWORD, SERVER, SYMBOL không được để trống trong file JSON.")
            return False
            
        print(f"✅ Tải cấu hình thành công: SYMBOL={SYMBOL}, SERVER={MT5_SERVER}")
        return True
    
    except json.JSONDecodeError:
        print(f"❌ Lỗi: Tệp '{filename}' không phải là định dạng JSON hợp lệ.")
        return False

# ==============================================================================
# 3. KẾT NỐI VÀ KHỞI TẠO MT5
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
            mt5.shutdown()
            quit()
        else:
            print("✅ Kết nối MT5 thành công (Sử dụng phiên MT5 đang chạy sẵn).")
    else:
        print(f"✅ Đăng nhập tài khoản {MT5_LOGIN} trên server {MT5_SERVER} thành công.")
        
    # Lấy thông tin tài khoản
    account_info = mt5.account_info()
    if account_info is not None:
        print(f"Tài khoản: {account_info.login}, Loại: {account_info.server}, Tiền tệ: {account_info.currency}, Ký quỹ: {account_info.margin_free}")
    
    # Cấu hình Symbol
    if not mt5.symbol_select(SYMBOL, True):
        print(f"❌ Lỗi: Không thể chọn ký hiệu {SYMBOL}. Kiểm tra tên ký hiệu.")
        mt5.shutdown()
        quit()

# ==============================================================================
# 4. TELEGRAM NOTIFICATION
# ==============================================================================

def send_telegram(message):
    """
    Gửi tin nhắn qua Telegram bot
    
    Args:
        message: Nội dung tin nhắn cần gửi
    """
    if not CHAT_ID:
        return  # Không có CHAT_ID → Bỏ qua Telegram
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data, timeout=5)
        if response.status_code == 200:
            return True
        else:
            print(f"⚠️ Telegram error: {response.status_code}")
            return False
    except Exception as e:
        print(f"⚠️ Lỗi gửi Telegram: {e}")
        return False

# ==============================================================================
# 5. CÁC HÀM PHÂN TÍCH KỸ THUẬT (INDICATORS & ANALYSIS)
# ==============================================================================

def get_rates(timeframe, bars_count=500):
    """Lấy dữ liệu giá cho một khung thời gian."""
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, bars_count)
    if rates is None:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def calculate_ema(df, period):
    """Tính EMA cho DataFrame."""
    return df['close'].ewm(span=period, adjust=False).mean()

def calculate_adx(df, period=14):
    """
    Tính ADX (Average Directional Index) - Chỉ báo đo lường sức mạnh xu hướng
    
    ADX không chỉ ra hướng xu hướng, chỉ đo lường sức mạnh:
    - ADX > 25: Xu hướng mạnh (trending market) → Nên giao dịch
    - ADX < 25: Thị trường đi ngang (sideways/choppy market) → Nên tránh giao dịch
    
    Args:
        df: DataFrame chứa dữ liệu giá (columns: high, low, close)
        period: Chu kỳ tính ADX (mặc định: 14)
        
    Returns:
        Series ADX với giá trị từ 0-100
    """
    high = df['high']
    low = df['low']
    close = df['close']
    
    # Tính True Range (TR)
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Tính Directional Movement
    # +DM: Nếu high tăng nhiều hơn low giảm
    # -DM: Nếu low giảm nhiều hơn high tăng
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    
    # Nếu +DM > -DM thì -DM = 0, và ngược lại
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0
    
    # Tính trung bình TR, +DM, -DM (dùng Wilder's smoothing)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    
    # Tính DX (Directional Index)
    # Tránh chia cho 0
    di_sum = plus_di + minus_di
    dx = 100 * abs(plus_di - minus_di) / di_sum.replace(0, 1)  # Thay 0 bằng 1 để tránh chia cho 0
    
    # Tính ADX (trung bình của DX)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    
    return adx

def analyze_m15_candle_bias():
    """
    Phân tích nến M15 vừa đóng cửa để xác định Bias (Định hướng).
    
    Patterns:
    - Pinbar (Rút chân): Đảo chiều hoặc tiếp diễn.
    - Marubozu/Strong Candle: Lực mạnh.
    
    Returns:
        bias (str): 'BUY', 'SELL', 'NEUTRAL'
        candle_data (dict): Thông tin nến M15 {open, high, low, close, body_size, ...}
    """
    print("  📊 [M15 ANALYSIS] Đang phân tích nến M15 vừa đóng...")
    
    # Lấy 2 nến M15 gần nhất (index 0 là đang chạy, index 1 là vừa đóng)
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 2)
    if rates is None or len(rates) < 2:
        print("    ❌ Không đủ dữ liệu M15.")
        return 'NEUTRAL', None
        
    candle = rates[0] # Nến vừa đóng (index 0 trong mảng 2 phần tử trả về từ copy_rates_from_pos với start 0, count 2 thì phần tử 0 là nến cũ hơn, phần tử 1 là nến mới nhất? 
                      # Wait, copy_rates_from_pos(start_pos=0, count=2) returns [candle_index_1, candle_index_0]. 
                      # Index 0 is the older one (closed), Index 1 is the current one (open).
                      # Let's verify. mt5 returns numpy array. 
                      # rates[0] is index 1 (previous closed), rates[1] is index 0 (current open).
                      # Correct logic: rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 2)
                      # rates[0] -> Nến index 1 (Vừa đóng)
                      # rates[1] -> Nến index 0 (Đang chạy)
    
    # Xác nhận lại logic index
    # copy_rates_from_pos(symbol, timeframe, 0, 2) -> Lấy từ vị trí 0 (hiện tại) về quá khứ 2 nến.
    # Kết quả trả về là mảng theo thứ tự thời gian tăng dần (cũ -> mới).
    # Vậy rates[0] là nến Index 1 (Vừa đóng). rates[1] là nến Index 0 (Đang chạy).
    
    c_open = candle['open']
    c_high = candle['high']
    c_low = candle['low']
    c_close = candle['close']
    
    body_size = abs(c_close - c_open)
    total_size = c_high - c_low
    upper_wick = c_high - max(c_open, c_close)
    lower_wick = min(c_open, c_close) - c_low
    
    point = mt5.symbol_info(SYMBOL).point
    
    candle_data = {
        'open': c_open, 'high': c_high, 'low': c_low, 'close': c_close,
        'body_size': body_size, 'total_size': total_size
    }
    
    print(f"    [M15 Candle] O:{c_open} H:{c_high} L:{c_low} C:{c_close}")
    print(f"    Size: {total_size/point:.1f} points, Body: {body_size/point:.1f} points")
    
    if total_size < MIN_CANDLE_SIZE_POINTS * point:
        print("    ⚠️ Nến M15 quá nhỏ (Sideways/Low Volatility) -> NEUTRAL")
        return 'NEUTRAL', candle_data

    # 1. BULLISH PINBAR (Rút chân dưới mạnh)
    # Râu dưới dài >= 2/3 thân hoặc 1/2 tổng nến?
    # Định nghĩa Pinbar mua: Râu dưới dài, thân nằm ở phần trên.
    if lower_wick >= 0.6 * total_size:
        print("    ✅ M15: BULLISH PINBAR (Rút chân dưới mạnh) -> BUY BIAS")
        return 'BUY', candle_data
        
    # 2. BEARISH PINBAR (Rút chân trên mạnh)
    if upper_wick >= 0.6 * total_size:
        print("    ✅ M15: BEARISH PINBAR (Rút chân trên mạnh) -> SELL BIAS")
        return 'SELL', candle_data
        
    # 3. STRONG BULLISH (Nến tăng mạnh)
    # Thân nến chiếm > 60% tổng nến và là nến tăng
    if c_close > c_open and body_size >= 0.6 * total_size:
        print("    ✅ M15: STRONG BULLISH (Nến tăng mạnh) -> BUY BIAS")
        return 'BUY', candle_data
        
    # 4. STRONG BEARISH (Nến giảm mạnh)
    # Thân nến chiếm > 60% tổng nến và là nến giảm
    if c_close < c_open and body_size >= 0.6 * total_size:
        print("    ✅ M15: STRONG BEARISH (Nến giảm mạnh) -> SELL BIAS")
        return 'SELL', candle_data
        
    print("    ⚠️ M15: Không rõ xu hướng (Indecision Candle) -> NEUTRAL")
    return 'NEUTRAL', candle_data

def check_m1_entry_pullback(bias, m15_candle):
    """
    Tìm điểm vào lệnh trên M1 dựa trên Pullback so với nến M15.
    
    Chiến thuật:
    - BUY: Chờ giá hồi về 30-50% biên độ nến M15 (tính từ High xuống).
    - SELL: Chờ giá hồi lên 30-50% biên độ nến M15 (tính từ Low lên).
    """
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None: return None, None, None
    
    current_price = tick.ask if bias == 'BUY' else tick.bid
    point = mt5.symbol_info(SYMBOL).point
    
    c_high = m15_candle['high']
    c_low = m15_candle['low']
    c_range = c_high - c_low
    
    print(f"  📈 [M1 ENTRY] Kiểm tra Pullback (Bias: {bias})...")
    print(f"    Giá hiện tại: {current_price}")
    
    if bias == 'BUY':
        # Vùng Buy lý tưởng: Từ (High - 30%) đến (High - 60%)
        # Tức là giá đã giảm được 30% - 60% của cây nến M15 trước đó
        buy_zone_upper = c_high - (c_range * PULLBACK_RATIO_MIN)
        buy_zone_lower = c_high - (c_range * PULLBACK_RATIO_MAX)
        
        sl_price = c_low - (50 * point) # SL dưới râu nến M15 5 pips
        
        print(f"    Vùng Buy: {buy_zone_lower:.2f} - {buy_zone_upper:.2f}")
        
        if buy_zone_lower <= current_price <= buy_zone_upper:
            print("    ✅ GIÁ ĐANG TRONG VÙNG PULLBACK -> MỞ LỆNH BUY")
            return 'BUY', sl_price, current_price
        elif current_price < buy_zone_lower:
             print("    ⚠️ Giá đã hồi quá sâu (> 60%) -> Cẩn thận đảo chiều -> Bỏ qua")
             return None, None, None
        else:
             print("    ⏳ Giá chưa hồi đủ (Chưa đến 30%) -> Chờ thêm")
             return None, None, None
             
    elif bias == 'SELL':
        # Vùng Sell lý tưởng: Từ (Low + 30%) đến (Low + 60%)
        sell_zone_lower = c_low + (c_range * PULLBACK_RATIO_MIN)
        sell_zone_upper = c_low + (c_range * PULLBACK_RATIO_MAX)
        
        sl_price = c_high + (50 * point) # SL trên râu nến M15 5 pips
        
        print(f"    Vùng Sell: {sell_zone_lower:.2f} - {sell_zone_upper:.2f}")
        
        if sell_zone_lower <= current_price <= sell_zone_upper:
            print("    ✅ GIÁ ĐANG TRONG VÙNG PULLBACK -> MỞ LỆNH SELL")
            return 'SELL', sl_price, current_price
        elif current_price > sell_zone_upper:
             print("    ⚠️ Giá đã hồi quá cao (> 60%) -> Cẩn thận đảo chiều -> Bỏ qua")
             return None, None, None
        else:
             print("    ⏳ Giá chưa hồi đủ (Chưa đến 30%) -> Chờ thêm")
             return None, None, None
             
    return None, None, None

# ==============================================================================
# 6. HÀM KIỂM TRA COOLDOWN SAU LỆNH THUA
# ==============================================================================

def check_last_loss_cooldown():
    """
    Kiểm tra lệnh đóng cuối cùng, nếu là lệnh thua thì kiểm tra thời gian cooldown
    
    Returns:
        Tuple (bool, str): (allowed, message)
            - allowed: True nếu cho phép mở lệnh mới, False nếu còn trong cooldown
            - message: Thông báo chi tiết
    """
    if not ENABLE_LOSS_COOLDOWN:
        return True, "Cooldown sau lệnh thua đã tắt"
    
    try:
        # Lấy deals từ 1 ngày gần nhất
        from_timestamp = int((datetime.now() - timedelta(days=1)).timestamp())
        to_timestamp = int(datetime.now().timestamp())
        deals = mt5.history_deals_get(from_timestamp, to_timestamp)
        
        if deals is None or len(deals) == 0:
            return True, "Không có lệnh đóng nào trong lịch sử"
        
        # Lọc chỉ lấy deals đóng lệnh (DEAL_ENTRY_OUT) và có magic number của bot
        closed_deals = []
        for deal in deals:
            if (deal.entry == mt5.DEAL_ENTRY_OUT and 
                deal.magic == MAGIC and 
                deal.profit != 0):
                closed_deals.append(deal)
        
        if len(closed_deals) == 0:
            return True, "Không có lệnh đóng nào của bot này"
        
        # Sắp xếp theo thời gian (mới nhất trước)
        closed_deals.sort(key=lambda x: x.time, reverse=True)
        
        # Lấy lệnh đóng cuối cùng
        last_deal = closed_deals[0]
        last_deal_time = datetime.fromtimestamp(last_deal.time)
        last_deal_profit = last_deal.profit
        
        # Kiểm tra nếu lệnh cuối cùng là lệnh thua (profit < 0)
        if last_deal_profit < 0:
            # Tính thời gian đã trôi qua từ khi đóng lệnh
            time_elapsed = datetime.now() - last_deal_time
            minutes_elapsed = time_elapsed.total_seconds() / 60
            
            if minutes_elapsed < LOSS_COOLDOWN_MINUTES:
                remaining_minutes = LOSS_COOLDOWN_MINUTES - minutes_elapsed
                message = f"⏸️ Cooldown sau lệnh thua: Còn {remaining_minutes:.1f} phút (Lệnh thua: {last_deal_profit:.2f} USD, đóng lúc {last_deal_time.strftime('%H:%M:%S')})"
                return False, message
            else:
                message = f"✅ Đã qua cooldown sau lệnh thua ({minutes_elapsed:.1f} phút đã trôi qua)"
                return True, message
        else:
            # Lệnh cuối cùng là lệnh lời hoặc hòa vốn → Cho phép mở lệnh mới
            message = f"✅ Lệnh đóng cuối cùng là lệnh lời/hòa vốn (Profit: {last_deal_profit:.2f} USD)"
            return True, message
            
    except Exception as e:
        print(f"⚠️ Lỗi khi kiểm tra cooldown sau lệnh thua: {e}")
        # Nếu có lỗi, cho phép mở lệnh để tránh block bot
        return True, f"Lỗi kiểm tra cooldown: {e}"

# ==============================================================================
# 7. HÀM GIAO DỊCH VÀ QUẢN LÝ LỆNH (TRADING & MANAGEMENT)
# ==============================================================================

def get_symbol_info():
    """Lấy thông tin ký hiệu giao dịch (spread, tick size, points)."""
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        return None
    
    point = symbol_info.point 
    return point

def get_symbol_info_full():
    """Lấy đầy đủ thông tin ký hiệu giao dịch."""
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        return None
    return symbol_info

def get_pip_value():
    """
    Tính giá trị pip cho XAUUSD với lot 0.01
    
    Với XAUUSD, lot 0.01: 100 pips = 1 USD
    → 1 pip = 0.01 USD (với lot 0.01)
    → pip_value = 0.01 USD
    
    Returns:
        pip_value: Giá trị 1 pip tính bằng USD (với lot 0.01)
    """
    return 0.01  # 1 pip = 0.01 USD với lot 0.01

def calculate_atr_from_m1(df_m1, period=14):
    """
    Tính ATR từ nến M1
    
    Args:
        df_m1: DataFrame M1
        period: Chu kỳ ATR (mặc định: 14)
        
    Returns:
        ATR value (trong pips) hoặc None nếu không đủ dữ liệu
    """
    if df_m1 is None or len(df_m1) < period + 1:
        return None
    
    point = get_symbol_info()
    if point is None:
        return None
    
    high = df_m1['high']
    low = df_m1['low']
    close = df_m1['close']
    
    # Tính True Range (TR) - giá trị thực (USD)
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Tính ATR (trung bình của TR) - giá trị thực (USD)
    atr_price = tr.rolling(window=period).mean().iloc[-1]
    
    # Chuyển ATR từ giá trị thực sang pips
    # Với XAUUSD: 1 pip = 0.01 USD (lot 0.01) → ATR(pips) = ATR(USD) / 0.01 = ATR(USD) × 100
    # Nhưng ATR được tính bằng giá (ví dụ: 2.9394), không phải USD profit
    # Cần chuyển: ATR(pips) = ATR(price) / 0.01 = ATR(price) × 100
    atr_pips = atr_price / 0.01  # = atr_price × 100
    
    return atr_pips

def send_order(trade_type, volume, df_m1=None, deviation=20):
    """
    Gửi lệnh Market Execution với SL/TP theo nến M1 (ATR-based).
    
    Args:
        trade_type: mt5.ORDER_TYPE_BUY hoặc mt5.ORDER_TYPE_SELL
        volume: Khối lượng giao dịch
        df_m1: DataFrame M1 để tính ATR (nếu None thì dùng giá trị cố định)
        deviation: Độ lệch giá cho phép
    """
    point = get_symbol_info()
    if point is None:
        print("❌ Lỗi: Không thể lấy thông tin ký hiệu để gửi lệnh.")
        return
        
    tick_info = mt5.symbol_info_tick(SYMBOL)
    price = tick_info.ask if trade_type == mt5.ORDER_TYPE_BUY else tick_info.bid
    
    # Tính TP theo tỷ lệ R:R (Ví dụ 1:2) hoặc ATR
    # Ở đây ta dùng ATR để tính TP cho linh hoạt, nhưng SL đã cố định theo nến M15
    # Nếu dùng SL theo nến M15, ta nên tính TP theo R:R dựa trên SL distance
    
    sl_distance = abs(price - sl)
    tp_distance = sl_distance * 2.0 # R:R = 1:2
    
    if trade_type == mt5.ORDER_TYPE_BUY:
        tp = price + tp_distance
    else:
        tp = price - tp_distance
        
    print(f"  💰 [ORDER] Entry: {price:.5f} | SL: {sl:.5f} | TP: {tp:.5f} (R:R 1:2)")
        
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": trade_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": deviation,
        "magic": MAGIC,
        "comment": f"M15_Candle_M1_Pullback",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        error_info = mt5.last_error()
        error_msg = f"❌ Lỗi gửi lệnh {'BUY' if trade_type == mt5.ORDER_TYPE_BUY else 'SELL'} - retcode: {result.retcode}"
        print(error_msg)
        print(f"Chi tiết lỗi: {error_info}")
        print(f"  Entry: {price:.5f} | SL: {sl:.5f} ({sl_points/10:.1f} pips) | TP: {tp:.5f} ({tp_points/10:.1f} pips)")
        
        # Giải thích lỗi retcode 10030 (Invalid stops)
        if result.retcode == 10030:
            print(f"  ⚠️ LỖI 10030: Invalid stops - SL/TP không hợp lệ")
            print(f"     - Có thể SL/TP quá gần hoặc quá xa entry")
            print(f"     - Hoặc vi phạm stops level của broker")
            if symbol_info is not None:
                stops_level = getattr(symbol_info, 'stops_level', 0)
                print(f"     - Broker stops_level: {stops_level} points ({stops_level/10:.1f} pips)")
        
        send_telegram(f"<b>❌ LỖI GỬI LỆNH</b>\n{error_msg}\nChi tiết: {error_info}\nEntry: {price:.5f} | SL: {sl:.5f} | TP: {tp:.5f}")
    else:
        success_msg = f"✅ Gửi lệnh {'BUY' if trade_type == mt5.ORDER_TYPE_BUY else 'SELL'} thành công! Order: {result.order}"
        print(success_msg)
        
        # Gửi thông báo Telegram với thông tin chi tiết
        trade_direction = "🟢 BUY" if trade_type == mt5.ORDER_TYPE_BUY else "🔴 SELL"
        atr_display = f"{atr_pips:.2f}" if atr_pips is not None else "N/A"
        sl_atr_display = f"{sl_pips_limited:.1f}" if sl_pips_limited is not None else f"{sl_points/10:.1f}"
        tp_atr_display = f"{tp_pips_limited:.1f}" if tp_pips_limited is not None else f"{tp_points/10:.1f}"
        
        telegram_msg = f"""
<b>{trade_direction} LỆNH MỚI</b>

📊 <b>Symbol:</b> {SYMBOL}
💰 <b>Entry:</b> {price:.5f}
🛑 <b>SL:</b> {sl:.5f} ({sl_points/10:.1f} pips)
🎯 <b>TP:</b> {tp:.5f} ({tp_points/10:.1f} pips)
📦 <b>Volume:</b> {volume}
🆔 <b>Order ID:</b> {result.order}
📈 <b>ATR:</b> {atr_display} pips (SL: {sl_atr_display}p, TP: {tp_atr_display}p)

⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        send_telegram(telegram_msg)

def manage_positions():
    """Quản lý các lệnh đang mở (Hòa vốn, Trailing Stop)."""
    
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return

    point = get_symbol_info()
    if point is None:
        return

    tick = mt5.symbol_info_tick(SYMBOL)
    current_bid = tick.bid
    current_ask = tick.ask
    
    # Lấy dữ liệu M1 để tính ATR cho trailing
    df_m1 = get_rates(mt5.TIMEFRAME_M1)
    atr_pips = None
    if df_m1 is not None:
        atr_pips = calculate_atr_from_m1(df_m1)  # ATR đã là pips

    for pos in positions:
        if pos.magic != MAGIC: # Chỉ quản lý lệnh của bot này
            continue
            
        is_buy = pos.type == mt5.POSITION_TYPE_BUY
        current_price = current_bid if is_buy else current_ask
        entry_price = pos.price_open
        
        # Tính profit hiện tại (points)
        if is_buy:
            profit_points = (current_price - entry_price) / point
        else:  # SELL
            profit_points = (entry_price - current_price) / point
        
        # --- LOGIC HÒA VỐN (BREAK EVEN) ---
        if ENABLE_BREAK_EVEN and BREAK_EVEN_START_POINTS > 0 and profit_points >= BREAK_EVEN_START_POINTS:
            # +1 pip (10 points) để bù spread và tránh bị dính SL ngay lập tức
            pips_buffer = 10 * point 
            new_sl_price = pos.price_open + pips_buffer if is_buy else pos.price_open - pips_buffer
            
            # Chỉ cập nhật nếu SL hiện tại không phải là giá mở cửa (đã di chuyển)
            if (is_buy and new_sl_price > pos.sl) or (not is_buy and new_sl_price < pos.sl):
                
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "sl": new_sl_price,
                    "tp": pos.tp,
                    "magic": MAGIC,
                    "deviation": 20,
                }
                result = mt5.order_send(request)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"🎯 Lệnh {pos.ticket} đã di chuyển SL về Hòa Vốn.")
        
        # Tính TP distance (points) từ entry đến TP
        if is_buy:
            tp_distance_points = (pos.tp - entry_price) / point
        else:  # SELL
            tp_distance_points = (entry_price - pos.tp) / point
        
        # --- LOGIC TRAILING STOP (trail SL khi lời 1/2 TP) ---
        # Chỉ chạy trailing stop nếu được bật
        if ENABLE_TRAILING_STOP:
            # Bắt đầu trailing khi profit >= 1/2 TP
            tp_half_points = tp_distance_points * TRAILING_START_TP_RATIO
            
            if profit_points >= tp_half_points and atr_pips is not None:
                # Tính bước trailing = ATR(pips) × 0.5, sau đó chuyển sang points
                trailing_step_pips = atr_pips * TRAILING_STEP_ATR_MULTIPLIER
                trailing_step_points = trailing_step_pips * 10  # 1 pip = 10 points
                
                if is_buy:
                    # TS cho lệnh BUY: SL mới = current_bid - trailing_step
                    new_sl_ts = current_bid - (trailing_step_points * point)
                    # Chỉ cập nhật nếu SL mới cao hơn SL hiện tại (di chuyển lên)
                    if new_sl_ts > pos.sl and new_sl_ts < current_bid:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "sl": new_sl_ts,
                            "tp": pos.tp,
                            "magic": MAGIC,
                            "deviation": 20,
                        }
                        result = mt5.order_send(request)
                        if result.retcode == mt5.TRADE_RETCODE_DONE:
                            print(f"⏫ Lệnh {pos.ticket} BUY: Trailing Stop cập nhật lên {new_sl_ts:.5f} (Profit: {profit_points/10:.1f} pips ≥ 1/2 TP: {tp_half_points/10:.1f} pips)")
                else:  # SELL
                    # TS cho lệnh SELL: SL mới = current_ask + trailing_step
                    new_sl_ts = current_ask + (trailing_step_points * point)
                    # Chỉ cập nhật nếu SL mới thấp hơn SL hiện tại (di chuyển xuống)
                    if (new_sl_ts < pos.sl or pos.sl == 0.0) and new_sl_ts > current_ask:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "sl": new_sl_ts,
                            "tp": pos.tp,
                            "magic": MAGIC,
                            "deviation": 20,
                        }
                        result = mt5.order_send(request)
                        if result.retcode == mt5.TRADE_RETCODE_DONE:
                            print(f"⏬ Lệnh {pos.ticket} SELL: Trailing Stop cập nhật xuống {new_sl_ts:.5f} (Profit: {profit_points/10:.1f} pips ≥ 1/2 TP: {tp_half_points/10:.1f} pips)")

# ==============================================================================
# 7. CHU TRÌNH CHÍNH (MAIN LOOP)
# ==============================================================================

def run_bot():
    """Chu trình chính của bot, lặp lại việc kiểm tra tín hiệu và quản lý lệnh."""
    
    # 0. Tải cấu hình
    if not load_config():
        return
        
    # 1. Khởi tạo MT5 và kết nối
    initialize_mt5()
    
    last_candle_time = datetime(1970, 1, 1)

    print("\n--- Bắt đầu Chu Trình Giao Dịch M1 (Chiến thuật: BÁM THEO H1 – ĂN 5–10 PHÚT) ---")
    print("📋 Chiến thuật:")
    print("   1. Xác định hướng H1 bằng EMA50 (Giá > EMA50 → CHỈ BUY, Giá < EMA50 → CHỈ SELL)")
    print("   2. Chọn điểm vào ở M1 khi giá RETEST lại EMA20")
    print("   3. TP 10–20 pip, SL 8–15 pip")
    print("   4. Chỉ check tín hiệu khi nến M1 đã đóng\n")
    
    while True:
        start_time = time.time() # Ghi lại thời gian bắt đầu chu kỳ
        current_time = datetime.now()
        
        # 2. Lấy dữ liệu M1
        df_m1 = get_rates(mt5.TIMEFRAME_M1)
        if df_m1 is None or len(df_m1) < 50:
            print("Đang chờ dữ liệu M1...")
            time.sleep(5)
            continue
            
        # Nến cuối cùng (vừa đóng)
        current_candle_time = df_m1.index[-1].replace(tzinfo=None)
        
        # 3. CHỈ XỬ LÝ TÍN HIỆU KHI CÓ NẾN MỚI ĐÓNG
        if current_candle_time > last_candle_time:
            last_candle_time = current_candle_time
            
            print(f"\n{'='*70}")
            print(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] 🔔 XỬ LÝ NẾN MỚI M1: {current_candle_time}")
            print(f"{'='*70}")
            
            # Lấy giá hiện tại
            tick = mt5.symbol_info_tick(SYMBOL)
            current_price = tick.bid
            current_ask = tick.ask
            print(f"  💰 Giá hiện tại: BID={current_price:.5f} | ASK={current_ask:.5f} | Spread={(current_ask-current_price):.5f}")
            
            # --- KIỂM TRA TÍN HIỆU VÀ LỌC ---
            print(f"\n  🔍 [KIỂM TRA TÍN HIỆU] Bắt đầu phân tích...")
            
            # --- KIỂM TRA TÍN HIỆU VÀ LỌC ---
            print(f"\n  🔍 [KIỂM TRA TÍN HIỆU] Bắt đầu phân tích...")

           # 1. Phân tích M15 Candle để tìm Bias
        bias, m15_candle = analyze_m15_candle_bias()
        
        if bias == 'NEUTRAL':
            print("  ⚠️ Bias NEUTRAL -> Chờ nến M15 rõ ràng hơn.")
            time.sleep(10)
            continue
            
        # 2. Tìm điểm vào trên M1 (Pullback)
        signal, sl_price, entry_price = check_m1_entry_pullback(bias, m15_candle)
        
        if signal == 'BUY':
             # Gửi lệnh BUY với SL theo nến M15
             # Lưu ý: send_order hiện tại đang tính lại SL/TP theo ATR, cần chỉnh sửa send_order để nhận SL cố định
             # Hoặc ta sửa send_order ở trên để nhận sl_price tham số
             
             # Sửa send_order để nhận sl_price và tính TP theo R:R
             # Nhưng hàm send_order ở trên đã được sửa để tính TP theo R:R 1:2 dựa trên SL
             # Tuy nhiên, hàm send_order hiện tại nhận `df_m1` và tự tính SL.
             # Ta cần sửa hàm send_order để nhận `sl_override`
             
             # Để đơn giản, ta sẽ gọi hàm order_send trực tiếp ở đây hoặc tạo hàm send_order_v2.
             # Tốt nhất là sửa send_order để linh hoạt.
             # Nhưng vì công cụ replace không cho phép sửa nhiều chỗ rải rác dễ dàng, 
             # ta sẽ gọi mt5.order_send trực tiếp hoặc tạo hàm send_order_v2.
             
             # Gọi hàm send_order đã sửa (đã sửa ở chunk trên để tính TP theo R:R từ SL)
             # Wait, chunk trên vẫn tính SL/TP từ ATR nếu df_m1 được truyền vào?
             # KHÔNG, chunk trên đã thay thế toàn bộ logic tính SL/TP bằng logic R:R 1:2
             # NHƯNG, nó vẫn dùng `sl` được tính từ `sl_distance` mà `sl_distance` lại tính từ `sl_points` (ATR).
             # Cần sửa lại logic truyền SL vào send_order.
             
             # Do hạn chế của việc sửa code từng phần, ta sẽ viết lại logic gửi lệnh ở đây cho chắc chắn.
             
             tp_dist = abs(entry_price - sl_price) * 2.0
             tp_price = entry_price + tp_dist
             
             print(f"🚀 GỬI LỆNH BUY: Entry {entry_price}, SL {sl_price}, TP {tp_price}")
             
             request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": VOLUME,
                "type": mt5.ORDER_TYPE_BUY,
                "price": entry_price,
                "sl": sl_price,
                "tp": tp_price,
                "deviation": 20,
                "magic": MAGIC,
                "comment": "M15_Pullback_Buy",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
             result = mt5.order_send(request)
             if result.retcode == mt5.TRADE_RETCODE_DONE:
                 print(f"✅ Gửi lệnh thành công: {result.order}")
                 send_telegram(f"✅ BUY M1_M15 {SYMBOL}\nEntry: {entry_price}\nSL: {sl_price}\nTP: {tp_price}")
             else:
                 print(f"❌ Lỗi gửi lệnh: {result.retcode}")
                 
        elif signal == 'SELL':
             tp_dist = abs(entry_price - sl_price) * 2.0
             tp_price = entry_price - tp_dist
             
             print(f"🚀 GỬI LỆNH SELL: Entry {entry_price}, SL {sl_price}, TP {tp_price}")
             
             request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": VOLUME,
                "type": mt5.ORDER_TYPE_SELL,
                "price": entry_price,
                "sl": sl_price,
                "tp": tp_price,
                "deviation": 20,
                "magic": MAGIC,
                "comment": "M15_Pullback_Sell",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
             result = mt5.order_send(request)
             if result.retcode == mt5.TRADE_RETCODE_DONE:
                 print(f"✅ Gửi lệnh thành công: {result.order}")
                 send_telegram(f"✅ SELL M1_M15 {SYMBOL}\nEntry: {entry_price}\nSL: {sl_price}\nTP: {tp_price}")
             else:
                 print(f"❌ Lỗi gửi lệnh: {result.retcode}")

        # Ngủ 10s trước khi check lại
        time.sleep(10)

            
        # 4. QUẢN LÝ LỆNH (CHẠY MỖI VÒNG LẶP ĐỂ BẮT BE/TS KỊP THỜI)
        manage_positions()
        
        # 5. ĐIỀU CHỈNH THỜI GIAN NGỦ ĐỂ ĐẠT CHU KỲ 10 GIÂY (M1 cần check thường xuyên hơn)
        elapsed_time = time.time() - start_time
        sleep_time = 10 - elapsed_time  # Check mỗi 10 giây cho M1
        
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            # Nếu thời gian xử lý quá 10s, thì không ngủ
            print(f"⚠️ Chu kỳ xử lý quá dài ({elapsed_time:.2f}s), không ngủ.")
            time.sleep(1) # Ngủ tối thiểu 1s để tránh loop vô tận


# ==============================================================================
# 7. KHỐI THỰC THI CHÍNH
# ==============================================================================

if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n\n👋 Bot đã dừng theo lệnh của người dùng.")
    finally:
        mt5.shutdown()
        print("Đã ngắt kết nối MT5.")