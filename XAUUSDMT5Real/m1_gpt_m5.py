import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime, timedelta
import json
import os
import requests
import logging

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
# Chiến thuật M1: "BÁM THEO M5 – ĂN 5–10 PHÚT"
EMA_H1 = 50  # EMA50 trên H1 để xác định xu hướng dài hạn
EMA_M5 = 50  # EMA50 trên M5 để xác định trend (thay H1)
EMA_M1 = 20  # EMA20 trên M1 để tìm điểm retest
ATR_PERIOD = 14
ADX_PERIOD = 14  # Chu kỳ tính ADX
ADX_MIN_THRESHOLD = 20  # ADX tối thiểu để giao dịch (tránh thị trường đi ngang)
ADX_M5_BREAKOUT_THRESHOLD = 35  # ADX(M5) > 35 để breakout (thay vì ADX M1)

# H1 Trend Filter
ENABLE_H1_TREND_FILTER = True  # Bật/tắt lọc theo trend H1 (Chỉ trade khi M5 cùng chiều H1)

# Momentum Confirmation (Sniper Entry)
ENABLE_MOMENTUM_CONFIRMATION = True  # Bật/tắt xác nhận momentum (chờ phá đỉnh/đáy nến tín hiệu)
MOMENTUM_BUFFER_POINTS = 0  # Buffer khoảng cách (points) để xác nhận phá vỡ (0 = phá qua là vào)

# Lọc ATR - chỉ vào lệnh khi ATR đủ lớn (thị trường có biến động)
ENABLE_ATR_FILTER = True  # Bật/tắt lọc ATR
ATR_MIN_THRESHOLD = 40    # ATR tối thiểu: 40 pips ($0.4)
ATR_MAX_THRESHOLD = 500   # ATR tối đa: 500 pips ($5) - Nới rộng để phù hợp với biến động $3-$4 hiện tại

# Thông số Quản lý Lệnh (Tính bằng points, 10 points = 1 pip)
# Chiến thuật M1: SL/TP theo nến M5
SL_ATR_MULTIPLIER = 1.5  # SL = ATR(M5) × 1.5
TP_ATR_MULTIPLIER = 2.0  # TP = ATR(M5) × 2.0
SL_POINTS_MIN = 50   # SL tối thiểu: 5 pips (50 points) - bảo vệ
SL_POINTS_MAX = 50000  # SL tối đa: 5000 pips (50000 points) - cho phép SL lớn theo ATR
TP_POINTS_MIN = 80   # TP tối thiểu: 8 pips (80 points) - bảo vệ
TP_POINTS_MAX = 50000  # TP tối đa: 5000 pips (50000 points) - cho phép TP lớn theo ATR

# Fix SL theo giá trị USD cố định
ENABLE_FIXED_SL_USD = False  # Bật/tắt fix SL theo USD
FIXED_SL_USD = 5.0  # SL cố định tính bằng USD (ví dụ: 5 USD)
SL_MAX_USD = 10.0    # SL tối đa cho phép (USD) - Dùng để giới hạn SL khi tính theo ATR


ENABLE_BREAK_EVEN = False           # Bật/tắt chức năng di chuyển SL về hòa vốn
BREAK_EVEN_START_POINTS = 100      # Hòa vốn khi lời 10 pips

# Trailing Stop khi lời 1/2 TP để lock profit
ENABLE_TRAILING_STOP = True        # Bật/tắt chức năng Trailing Stop
TRAILING_START_TP_RATIO = 0.5  # Bắt đầu trailing khi lời 1/2 TP
TRAILING_STEP_ATR_MULTIPLIER = 0.5  # Bước trailing = ATR × 0.5

# Cooldown sau lệnh thua
ENABLE_LOSS_COOLDOWN = True         # Bật/tắt cooldown sau lệnh thua
LOSS_COOLDOWN_MINUTES = 10         # Thời gian chờ sau lệnh thua (phút)
LOSS_COOLDOWN_MODE = 2              # Mode cooldown: 1 = 1 lệnh cuối thua, 2 = 2 lệnh cuối đều thua

# Cooldown sau 3 lệnh thua liên tiếp
ENABLE_LOSS_COOLDOWN_3LOSS = True   # Bật/tắt cooldown sau 3 lệnh thua liên tiếp
LOSS_COOLDOWN_3LOSS_MINUTES = 60   # Thời gian chờ sau 3 lệnh thua liên tiếp (phút): 60 = 1h, 300 = 5h

# Tạm dừng sau khi gửi lệnh lỗi nhiều lần liên tiếp
ENABLE_ERROR_COOLDOWN = True         # Bật/tắt tạm dừng sau lỗi gửi lệnh
ERROR_COOLDOWN_COUNT = 5            # Số lần lỗi liên tiếp để kích hoạt cooldown
ERROR_COOLDOWN_MINUTES = 1          # Thời gian tạm dừng sau khi lỗi (phút)

# Biến đếm lỗi (sẽ được reset khi thành công)
error_count = 0                     # Số lần lỗi liên tiếp hiện tại
error_cooldown_start = None         # Thời gian bắt đầu cooldown (None nếu không có)

# Telegram Bot Configuration
 # Chat ID sẽ được lấy từ JSON config hoặc để None nếu không dùng Telegram
TELEGRAM_TOKEN = "6398751744:AAGp7VH7B00_kzMqdaFB59xlqAXnlKTar-g"         # Token của Telegram Bot (lấy từ @BotFather)
                                # Ví dụ: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
                                # Hướng dẫn: https://core.telegram.org/bots/tutorial

CHAT_ID = "1887610382"      
# Khoảng cách retest EMA20 trên M1 (points)
# Giá chạm EMA20 trong vùng 0-20 pips (0-200 points) - Theo yêu cầu m1_gpt.md
RETEST_DISTANCE_MIN = 0   # Tối thiểu 0 pips (chạm hoặc gần chạm)
RETEST_DISTANCE_MAX = 200  # Tối đa 20 pips (200 points) từ EMA20

# Chiến thuật BREAKOUT (khi giá không retest) - CHỈ DÙNG KHI ĐIỀU KIỆN NGHIÊM NGẶT
ENABLE_BREAKOUT = False  # Tắt breakout mặc định (M1 nhiễu)
BREAKOUT_DISTANCE_MIN = 100  # Khoảng cách tối thiểu từ EMA20: 10 pips (100 points)
BREAKOUT_DISTANCE_MAX = 200  # Khoảng cách tối đa từ EMA20: 20 pips (200 points)

# Spread Filter
ENABLE_SPREAD_FILTER = True  # Bật/tắt lọc spread
SPREAD_MAX_POINTS = 200  # Spread tối đa: 50 points (5 pips) - XAUUSD thông thường 2-5 pips

# Momentum Candle Filter
ENABLE_MOMENTUM_FILTER = True  # Bật/tắt lọc nến momentum
MOMENTUM_CANDLE_MAX_PIPS = 50  # Không trade sau nến > 50 pips ($5)

# Bad Candle Filter
ENABLE_BAD_CANDLE_FILTER = True  # Bật/tắt lọc nến xấu
BAD_CANDLE_SHADOW_RATIO = 0.6  # Bóng > 60% thân → bỏ

# Time Filter (Tránh giờ tin tức)
ENABLE_TIME_FILTER = False  # Bật/tắt lọc giờ tin tức (Mặc định: OFF)
TIME_FILTER_BUFFER_MINUTES = 15  # Tránh giao dịch 15 phút trước/sau tin tức
# Danh sách giờ tin tức quan trọng (UTC): [hour, minute]
# NFP: Thứ 6 đầu tháng, 12:30 UTC
# FOMC: Thường 18:00 hoặc 19:00 UTC
# CPI: Thường 12:30 UTC
IMPORTANT_NEWS_HOURS = [
    (12, 30),  # NFP, CPI (12:30 UTC)
    (18, 0),   # FOMC (18:00 UTC)
    (19, 0),   # FOMC (19:00 UTC)
]

# RSI Filter (Tránh quá mua/quá bán)
ENABLE_RSI_FILTER = True  # Bật/tắt lọc RSI
RSI_PERIOD = 14  # Chu kỳ tính RSI
RSI_OVERBOUGHT = 70  # RSI > 70 → Quá mua (không BUY)
RSI_OVERSOLD = 30  # RSI < 30 → Quá bán (không SELL)

# Volume Confirmation (Xác nhận volume tăng)
ENABLE_VOLUME_CONFIRMATION = True  # Bật/tắt xác nhận volume
VOLUME_INCREASE_RATIO = 1.2  # Volume phải tăng ít nhất 20% so với nến trước

# ==============================================================================
# 2. HÀM THIẾT LẬP LOGGING
# ==============================================================================

def setup_logging():
    """
    Thiết lập logging để ghi log vào file theo tên bot.
    File log sẽ được tạo trong thư mục XAUUSDMT5Real/logs/
    """
    # Tạo thư mục logs nếu chưa có (trong thư mục chứa bot)
    bot_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(bot_dir, "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Lấy tên file bot (ví dụ: m1_gpt_m5.py -> m1_gpt_m5)
    bot_name = os.path.splitext(os.path.basename(__file__))[0]
    log_file = os.path.join(log_dir, f"{bot_name}.log")
    
    # Cấu hình logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # Vẫn in ra console
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"=" * 70)
    logger.info(f"BOT: {bot_name.upper()}")
    logger.info(f"LOG FILE: {log_file}")
    logger.info(f"=" * 70)
    
    return logger

# ==============================================================================
# 3. HÀM TẢI CẤU HÌNH (CONFIG LOADING)
# ==============================================================================

def load_config(filename="XAUUSDMT5Real/mt5_account.json"):
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

def check_h1_trend():
    """
    Kiểm tra xu hướng H1 bằng EMA50
    
    Returns:
        'BUY', 'SELL', hoặc 'SIDEWAYS'
    """
    if not ENABLE_H1_TREND_FILTER:
        return 'SIDEWAYS' # Nếu tắt filter thì coi như không có trend cản trở
        
    print("  📊 [H1 TREND] Kiểm tra xu hướng H1 bằng EMA50...")
    
    df_h1 = get_rates(mt5.TIMEFRAME_H1)
    if df_h1 is None or len(df_h1) < EMA_H1:
        print(f"    [H1] ❌ Không đủ dữ liệu để tính EMA50")
        return 'SIDEWAYS'
    
    ema_50_h1 = calculate_ema(df_h1, EMA_H1).iloc[-1]
    close_h1 = df_h1['close'].iloc[-1]
    
    print(f"    [H1] Giá: {close_h1:.5f} | EMA50: {ema_50_h1:.5f}")
    
    if close_h1 > ema_50_h1:
        print(f"    [H1] ✅ XU HƯỚNG MUA (Giá > EMA50)")
        return 'BUY'
    elif close_h1 < ema_50_h1:
        print(f"    [H1] ✅ XU HƯỚNG BÁN (Giá < EMA50)")
        return 'SELL'
    else:
        print(f"    [H1] ⚠️ SIDEWAYS (Giá ≈ EMA50)")
        return 'SIDEWAYS'

def check_m5_trend():
    """
    Kiểm tra xu hướng M5 bằng EMA50
    
    Chiến thuật: "BÁM THEO M5 – ĂN 5–10 PHÚT"
    - Giá > EMA50 → CHỈ BUY
    - Giá < EMA50 → CHỈ SELL
    
    Returns:
        'BUY', 'SELL', hoặc 'SIDEWAYS'
    """
    print("  📊 [M5 TREND] Kiểm tra xu hướng M5 bằng EMA50...")
    
    df_m5 = get_rates(mt5.TIMEFRAME_M5)
    if df_m5 is None or len(df_m5) < EMA_M5:
        print(f"    [M5] ❌ Không đủ dữ liệu để tính EMA50")
        return 'SIDEWAYS'
    
    ema_50_m5 = calculate_ema(df_m5, EMA_M5).iloc[-1]
    close_m5 = df_m5['close'].iloc[-1]
    
    print(f"    [M5] Giá: {close_m5:.5f} | EMA50: {ema_50_m5:.5f}")
    
    if close_m5 > ema_50_m5:
        print(f"    [M5] ✅ XU HƯỚNG MUA (Giá > EMA50) → CHỈ BUY")
        return 'BUY'
    elif close_m5 < ema_50_m5:
        print(f"    [M5] ✅ XU HƯỚNG BÁN (Giá < EMA50) → CHỈ SELL")
        return 'SELL'
    else:
        print(f"    [M5] ⚠️ SIDEWAYS (Giá ≈ EMA50)")
        return 'SIDEWAYS'

def check_momentum_confirmation(df_m1, signal_direction):
    """
    Kiểm tra xác nhận Momentum (Sniper Entry)
    
    - BUY: Giá hiện tại > Đỉnh nến tín hiệu + Buffer
    - SELL: Giá hiện tại < Đáy nến tín hiệu - Buffer
    
    Args:
        df_m1: DataFrame M1
        signal_direction: 'BUY' hoặc 'SELL'
        
    Returns:
        Tuple (bool, str): (confirmed, message)
    """
    if not ENABLE_MOMENTUM_CONFIRMATION:
        return True, "Momentum confirmation đã tắt"
        
    if len(df_m1) < 2:
        return False, "Không đủ dữ liệu M1"
        
    # Nến tín hiệu là nến vừa đóng (iloc[-1])
    signal_candle = df_m1.iloc[-1]
    signal_high = signal_candle['high']
    signal_low = signal_candle['low']
    
    # Lấy giá hiện tại (Realtime)
    tick = mt5.symbol_info_tick(SYMBOL)
    current_ask = tick.ask
    current_bid = tick.bid
    point = get_symbol_info()
    
    buffer_points = MOMENTUM_BUFFER_POINTS * point
    
    if signal_direction == 'BUY':
        confirmation_price = signal_high + buffer_points
        if current_ask > confirmation_price:
            return True, f"✅ Momentum Confirmed: Giá ({current_ask:.5f}) > Đỉnh nến tín hiệu ({signal_high:.5f})"
        else:
            distance = confirmation_price - current_ask
            distance_pips = (distance / point) / 10
            return False, f"⏳ Waiting for Momentum: Cần phá {confirmation_price:.5f} (Còn {distance_pips:.1f} pips)"
            
    elif signal_direction == 'SELL':
        confirmation_price = signal_low - buffer_points
        if current_bid < confirmation_price:
            return True, f"✅ Momentum Confirmed: Giá ({current_bid:.5f}) < Đáy nến tín hiệu ({signal_low:.5f})"
        else:
            distance = current_bid - confirmation_price
            distance_pips = (distance / point) / 10
            return False, f"⏳ Waiting for Momentum: Cần phá {confirmation_price:.5f} (Còn {distance_pips:.1f} pips)"
            
    return False, "Invalid direction"

def check_m1_retest_ema20(df_m1, m5_trend):
    """
    Kiểm tra điểm vào ở M1 khi giá RETEST lại EMA20
    
    Chiến thuật: "BÁM THEO M5 – ĂN 5–10 PHÚT"
    - Trend BUY → chờ giá M1 retest EMA20 trong vùng 10-20 pips → BUY
    - Trend SELL → chờ giá M1 retest EMA20 trong vùng 10-20 pips → SELL
    
    Args:
        df_m1: DataFrame M1
        m5_trend: 'BUY', 'SELL', hoặc 'SIDEWAYS'
        
    Returns:
        'BUY', 'SELL', hoặc 'NONE'
    """
    if m5_trend == 'SIDEWAYS':
        print("  📈 [M1 RETEST] M5 trend là SIDEWAYS → Không có tín hiệu")
        return 'NONE'
    
    if len(df_m1) < EMA_M1:
        print("  📈 [M1 RETEST] Không đủ dữ liệu để tính EMA20")
        return 'NONE'
    
    # Tính EMA20 trên M1
    ema_20_m1 = calculate_ema(df_m1, EMA_M1)
    ema_20_current = ema_20_m1.iloc[-1]
    
    # Lấy giá hiện tại
    tick = mt5.symbol_info_tick(SYMBOL)
    current_price = tick.bid  # Dùng bid cho cả BUY và SELL (để tính khoảng cách)
    
    point = get_symbol_info()
    if point is None:
        return 'NONE'
    
    # Tính khoảng cách từ giá hiện tại đến EMA20 (points)
    distance_points = abs(current_price - ema_20_current) / point
    
    # Lấy thông tin nến hiện tại để confirm (tránh bắt dao rơi)
    current_candle = df_m1.iloc[-1]
    is_green_candle = current_candle['close'] > current_candle['open']
    is_red_candle = current_candle['close'] < current_candle['open']
    
    print(f"  📈 [M1 RETEST] Giá hiện tại: {current_price:.5f} | EMA20: {ema_20_current:.5f}")
    print(f"    Khoảng cách: {distance_points:.1f} points ({distance_points/10:.1f} pips)")
    print(f"    Vùng retest: {RETEST_DISTANCE_MIN/10:.1f}-{RETEST_DISTANCE_MAX/10:.1f} pips")
    
    if m5_trend == 'BUY':
        # Trend BUY → giá phải trong vùng retest (gần EMA20)
        if RETEST_DISTANCE_MIN <= distance_points <= RETEST_DISTANCE_MAX:
            # QUAN TRỌNG: Chỉ BUY khi CẢ HAI điều kiện:
            # 1. Nến hiện tại là NẾN XANH (đã bật lên)
            # 2. Giá > EMA20 (xác nhận momentum tăng)
            # Để tránh mua khi giá đang cắm đầu xuống hoặc pullback
            if is_green_candle and current_price > ema_20_current:
                print(f"    ✅ [M1 RETEST] Giá trong vùng retest & có tín hiệu bật lên (Nến xanh VÀ Trên EMA)")
                return 'BUY'
            else:
                if not is_green_candle:
                    print(f"    ⚠️ [M1 RETEST] Giá trong vùng retest nhưng nến đỏ - Chờ nến xanh")
                elif current_price <= ema_20_current:
                    print(f"    ⚠️ [M1 RETEST] Giá trong vùng retest nhưng giá <= EMA20 - Chờ giá vượt EMA20")
                return 'NONE'
        else:
            print(f"    ⚠️ [M1 RETEST] Giá ngoài vùng retest ({distance_points/10:.1f} pips) - Chờ retest")
            return 'NONE'
    
    elif m5_trend == 'SELL':
        # Trend SELL → giá phải trong vùng retest (gần EMA20)
        if RETEST_DISTANCE_MIN <= distance_points <= RETEST_DISTANCE_MAX:
            # QUAN TRỌNG: Chỉ SELL khi CẢ HAI điều kiện:
            # 1. Nến hiện tại là NẾN ĐỎ (đã bật xuống)
            # 2. Giá < EMA20 (xác nhận momentum giảm)
            # Để tránh bán khi giá đang tăng hoặc pullback
            if is_red_candle and current_price < ema_20_current:
                print(f"    ✅ [M1 RETEST] Giá trong vùng retest & có tín hiệu bật xuống (Nến đỏ VÀ Dưới EMA)")
                return 'SELL'
            else:
                if not is_red_candle:
                    print(f"    ⚠️ [M1 RETEST] Giá trong vùng retest nhưng nến xanh - Chờ nến đỏ")
                elif current_price >= ema_20_current:
                    print(f"    ⚠️ [M1 RETEST] Giá trong vùng retest nhưng giá >= EMA20 - Chờ giá xuống dưới EMA20")
                return 'NONE'
        else:
            print(f"    ⚠️ [M1 RETEST] Giá ngoài vùng retest ({distance_points/10:.1f} pips) - Chờ retest")
            return 'NONE'
    
    return 'NONE'

def check_m1_breakout(df_m1, df_m5, m5_trend, adx_m5_current, spread_points):
    """
    Kiểm tra điểm vào BREAKOUT khi giá không retest EMA20
    CHỈ DÙNG KHI ĐIỀU KIỆN NGHIÊM NGẶT (M1 nhiễu)
    
    Điều kiện:
    - ADX(M5) > 35
    - Volume tăng liên tục (kiểm tra tick volume)
    - Spread nhỏ (< 20-25 points)
    - M5 trend rõ ràng
    
    Args:
        df_m1: DataFrame M1
        df_m5: DataFrame M5
        m5_trend: 'BUY', 'SELL', hoặc 'SIDEWAYS'
        adx_m5_current: Giá trị ADX(M5) hiện tại
        spread_points: Spread hiện tại (points)
        
    Returns:
        'BUY', 'SELL', hoặc 'NONE'
    """
    if not ENABLE_BREAKOUT:
        return 'NONE'
    
    if m5_trend == 'SIDEWAYS':
        return 'NONE'
    
    # Kiểm tra ADX(M5) > 35
    if adx_m5_current <= ADX_M5_BREAKOUT_THRESHOLD:
        print(f"  🚀 [M1 BREAKOUT] ADX(M5)={adx_m5_current:.2f} <= {ADX_M5_BREAKOUT_THRESHOLD} → Không đủ điều kiện")
        return 'NONE'
    
    # Kiểm tra spread nhỏ
    if spread_points > SPREAD_MAX_POINTS:
        print(f"  🚀 [M1 BREAKOUT] Spread={spread_points:.1f} points > {SPREAD_MAX_POINTS} → Spread quá lớn")
        return 'NONE'
    
    # Kiểm tra volume tăng (so sánh volume 3 nến gần nhất)
    if len(df_m1) < 5:
        return 'NONE'
    
    recent_volumes = df_m1['tick_volume'].iloc[-3:].values
    if len(recent_volumes) < 3:
        return 'NONE'
    
    # Volume phải tăng (ít nhất 2/3 nến cuối tăng)
    volume_increasing = (recent_volumes[-1] > recent_volumes[-2]) and (recent_volumes[-2] > recent_volumes[-3])
    if not volume_increasing:
        print(f"  🚀 [M1 BREAKOUT] Volume không tăng liên tục → Không đủ điều kiện")
        return 'NONE'
    
    if len(df_m1) < EMA_M1 + 20:  # Cần ít nhất 20 nến để tìm đáy/đỉnh
        return 'NONE'
    
    # Tính EMA20 trên M1
    ema_20_m1 = calculate_ema(df_m1, EMA_M1)
    ema_20_current = ema_20_m1.iloc[-1]
    
    # Lấy giá hiện tại
    tick = mt5.symbol_info_tick(SYMBOL)
    current_price = tick.bid if m5_trend == 'SELL' else tick.ask
    
    point = get_symbol_info()
    if point is None:
        return 'NONE'
    
    # Tính khoảng cách từ giá hiện tại đến EMA20 (points)
    if m5_trend == 'SELL':
        distance_points = (ema_20_current - current_price) / point
    else:  # BUY
        distance_points = (current_price - ema_20_current) / point
    
    # Kiểm tra khoảng cách > 10-20 point
    if distance_points < BREAKOUT_DISTANCE_MIN or distance_points > BREAKOUT_DISTANCE_MAX:
        return 'NONE'
    
    # Tìm đáy/đỉnh gần nhất (20 nến gần nhất)
    lookback = 20
    recent_lows = df_m1['low'].iloc[-lookback:].min()
    recent_highs = df_m1['high'].iloc[-lookback:].max()
    
    print(f"  🚀 [M1 BREAKOUT] Giá hiện tại: {current_price:.5f} | EMA20: {ema_20_current:.5f}")
    print(f"    Khoảng cách đến EMA20: {distance_points:.1f} points ({distance_points/10:.1f} pips)")
    print(f"    Đáy gần nhất: {recent_lows:.5f} | Đỉnh gần nhất: {recent_highs:.5f}")
    print(f"    ADX(M5): {adx_m5_current:.2f} > {ADX_M5_BREAKOUT_THRESHOLD} ✓")
    print(f"    Spread: {spread_points:.1f} points < {SPREAD_MAX_POINTS} ✓")
    print(f"    Volume: Tăng liên tục ✓")
    
    if m5_trend == 'SELL':
        # SELL: Giá phá đáy gần nhất
        if current_price < recent_lows:
            print(f"    ✅ [M1 BREAKOUT] Giá phá đáy gần nhất ({recent_lows:.5f}) → SELL BREAKOUT")
            return 'SELL'
    
    elif m5_trend == 'BUY':
        # BUY: Giá phá đỉnh gần nhất
        if current_price > recent_highs:
            print(f"    ✅ [M1 BREAKOUT] Giá phá đỉnh gần nhất ({recent_highs:.5f}) → BUY BREAKOUT")
            return 'BUY'
    
    return 'NONE'

# ==============================================================================
# 5.5. CÁC HÀM FILTER MỚI
# ==============================================================================

def check_bad_candle(df_m1):
    """
    Kiểm tra nến M1 xấu (Bad Candle Filter)
    
    Bỏ tín hiệu nếu nến M1 có:
    - Bóng dưới > 60% thân (không BUY)
    - Bóng trên > 60% thân (không SELL)
    - Doji, pin bar, spinning top → bỏ
    
    Args:
        df_m1: DataFrame M1
        
    Returns:
        Tuple (bool, str): (is_bad, reason)
            - is_bad: True nếu nến xấu, False nếu OK
            - reason: Lý do nến xấu
    """
    if not ENABLE_BAD_CANDLE_FILTER:
        return False, "Bad candle filter đã tắt"
    
    if len(df_m1) < 1:
        return False, "Không đủ dữ liệu"
    
    # Lấy nến cuối cùng
    last_candle = df_m1.iloc[-1]
    open_price = last_candle['open']
    high_price = last_candle['high']
    low_price = last_candle['low']
    close_price = last_candle['close']
    
    # Tính thân nến (body)
    body = abs(close_price - open_price)
    
    # Tính bóng trên và bóng dưới
    upper_shadow = high_price - max(open_price, close_price)
    lower_shadow = min(open_price, close_price) - low_price
    
    # Tính tổng range
    total_range = high_price - low_price
    
    if total_range == 0:
        return False, "Nến không có range"
    
    # Kiểm tra Doji (thân < 20% range)
    if body < total_range * 0.2:
        return True, f"Doji (thân={body:.5f}, range={total_range:.5f})"
    
    # Kiểm tra bóng dưới > 60% thân (không BUY)
    if body > 0 and lower_shadow > body * BAD_CANDLE_SHADOW_RATIO:
        return True, f"Bóng dưới quá lớn ({lower_shadow:.5f} > {body * BAD_CANDLE_SHADOW_RATIO:.5f}, {lower_shadow/body*100:.1f}% thân)"
    
    # Kiểm tra bóng trên > 60% thân (không SELL)
    if body > 0 and upper_shadow > body * BAD_CANDLE_SHADOW_RATIO:
        return True, f"Bóng trên quá lớn ({upper_shadow:.5f} > {body * BAD_CANDLE_SHADOW_RATIO:.5f}, {upper_shadow/body*100:.1f}% thân)"
    
    return False, "Nến OK"

def check_momentum_candle(df_m1, direction):
    """
    Kiểm tra nến momentum (quá lớn) - không trade sau nến lớn
    
    Không BUY ngay sau 1 nến tăng mạnh > 40-60 pips
    Không SELL ngay sau 1 nến giảm mạnh > 40-60 pips
    QUAN TRỌNG: Không BUY sau nến bearish lớn, không SELL sau nến bullish lớn
    CẢI THIỆN: Check 2-3 nến gần nhất để tránh vào sau nhiều nến momentum liên tiếp
    
    Args:
        df_m1: DataFrame M1
        direction: 'BUY' hoặc 'SELL'
        
    Returns:
        Tuple (bool, str): (has_momentum, reason)
            - has_momentum: True nếu có nến momentum (không nên trade), False nếu OK
            - reason: Lý do
    """
    if not ENABLE_MOMENTUM_FILTER:
        return False, "Momentum filter đã tắt"
    
    if len(df_m1) < 3:
        return False, "Không đủ dữ liệu (cần ít nhất 3 nến)"
    
    point = get_symbol_info()
    if point is None:
        return False, "Không lấy được point"
    
    # Lấy 3 nến gần nhất để kiểm tra
    last_candle = df_m1.iloc[-1]
    prev_candle = df_m1.iloc[-2] if len(df_m1) >= 2 else None
    prev2_candle = df_m1.iloc[-3] if len(df_m1) >= 3 else None
    
    # Kiểm tra nến cuối cùng
    last_open = last_candle['open']
    last_close = last_candle['close']
    last_candle_size_pips = abs(last_close - last_open) / point / 10
    
    if direction == 'BUY':
        # BUY: Kiểm tra nến tăng mạnh (nến cuối cùng)
        if last_close > last_open and last_candle_size_pips > MOMENTUM_CANDLE_MAX_PIPS:
            return True, f"Nến cuối tăng quá mạnh ({last_candle_size_pips:.1f} pips > {MOMENTUM_CANDLE_MAX_PIPS} pips) - Chờ pullback"
        
        # BUY: Kiểm tra 2-3 nến bearish lớn gần nhất (không nên BUY sau nến bearish lớn)
        bearish_count = 0
        bearish_sizes = []
        
        if prev_candle is not None:
            prev_open = prev_candle['open']
            prev_close = prev_candle['close']
            prev_candle_size_pips = abs(prev_close - prev_open) / point / 10
            
            if prev_close < prev_open and prev_candle_size_pips > MOMENTUM_CANDLE_MAX_PIPS:
                bearish_count += 1
                bearish_sizes.append(prev_candle_size_pips)
        
        if prev2_candle is not None:
            prev2_open = prev2_candle['open']
            prev2_close = prev2_candle['close']
            prev2_candle_size_pips = abs(prev2_close - prev2_open) / point / 10
            
            if prev2_close < prev2_open and prev2_candle_size_pips > MOMENTUM_CANDLE_MAX_PIPS:
                bearish_count += 1
                bearish_sizes.append(prev2_candle_size_pips)
        
        # Nếu có 2/3 nến bearish lớn liên tiếp → chặn
        if bearish_count >= 2:
            sizes_str = ", ".join([f"{s:.1f}" for s in bearish_sizes])
            return True, f"Có {bearish_count} nến bearish lớn liên tiếp ({sizes_str} pips) - Không BUY sau nhiều nến giảm mạnh"
        elif bearish_count == 1:
            return True, f"Nến trước đó là bearish lớn ({bearish_sizes[0]:.1f} pips > {MOMENTUM_CANDLE_MAX_PIPS} pips) - Không BUY sau nến giảm mạnh"
    
    elif direction == 'SELL':
        # SELL: Kiểm tra nến giảm mạnh (nến cuối cùng)
        if last_close < last_open and last_candle_size_pips > MOMENTUM_CANDLE_MAX_PIPS:
            return True, f"Nến cuối giảm quá mạnh ({last_candle_size_pips:.1f} pips > {MOMENTUM_CANDLE_MAX_PIPS} pips) - Chờ pullback"
        
        # SELL: Kiểm tra 2-3 nến bullish lớn gần nhất (không nên SELL sau nến bullish lớn)
        bullish_count = 0
        bullish_sizes = []
        
        if prev_candle is not None:
            prev_open = prev_candle['open']
            prev_close = prev_candle['close']
            prev_candle_size_pips = abs(prev_close - prev_open) / point / 10
            
            if prev_close > prev_open and prev_candle_size_pips > MOMENTUM_CANDLE_MAX_PIPS:
                bullish_count += 1
                bullish_sizes.append(prev_candle_size_pips)
        
        if prev2_candle is not None:
            prev2_open = prev2_candle['open']
            prev2_close = prev2_candle['close']
            prev2_candle_size_pips = abs(prev2_close - prev2_open) / point / 10
            
            if prev2_close > prev2_open and prev2_candle_size_pips > MOMENTUM_CANDLE_MAX_PIPS:
                bullish_count += 1
                bullish_sizes.append(prev2_candle_size_pips)
        
        # Nếu có 2/3 nến bullish lớn liên tiếp → chặn
        if bullish_count >= 2:
            sizes_str = ", ".join([f"{s:.1f}" for s in bullish_sizes])
            return True, f"Có {bullish_count} nến bullish lớn liên tiếp ({sizes_str} pips) - Không SELL sau nhiều nến tăng mạnh"
        elif bullish_count == 1:
            return True, f"Nến trước đó là bullish lớn ({bullish_sizes[0]:.1f} pips > {MOMENTUM_CANDLE_MAX_PIPS} pips) - Không SELL sau nến tăng mạnh"
    
    return False, "Không có nến momentum"

def check_m1_structure(df_m1, direction):
    """
    Kiểm tra cấu trúc M1 (đỉnh/đáy)
    
    - Đỉnh sau cao hơn → BUY
    - Đáy sau thấp hơn → SELL
    - Nếu M1 đang giảm → bot không được BUY, dù M5 tăng
    
    Args:
        df_m1: DataFrame M1
        direction: 'BUY' hoặc 'SELL'
        
    Returns:
        Tuple (bool, str): (structure_ok, reason)
            - structure_ok: True nếu cấu trúc OK, False nếu không phù hợp
            - reason: Lý do
    """
    # CẢI THIỆN: Yêu cầu ít nhất 20 nến để có đủ dữ liệu phân tích
    if len(df_m1) < 20:
        return False, "Không đủ dữ liệu để kiểm tra cấu trúc (cần ít nhất 20 nến)"
    
    # Tìm 2 đỉnh và 2 đáy gần nhất (10 nến gần nhất)
    lookback = 10
    recent_data = df_m1.iloc[-lookback:]
    
    # Tìm đỉnh (high)
    peaks = []
    for i in range(1, len(recent_data) - 1):
        if (recent_data.iloc[i]['high'] > recent_data.iloc[i-1]['high'] and 
            recent_data.iloc[i]['high'] > recent_data.iloc[i+1]['high']):
            peaks.append((i, recent_data.iloc[i]['high']))
    
    # Tìm đáy (low)
    troughs = []
    for i in range(1, len(recent_data) - 1):
        if (recent_data.iloc[i]['low'] < recent_data.iloc[i-1]['low'] and 
            recent_data.iloc[i]['low'] < recent_data.iloc[i+1]['low']):
            troughs.append((i, recent_data.iloc[i]['low']))
    
    if direction == 'BUY':
        # BUY: Cần đỉnh sau cao hơn đỉnh trước (higher highs)
        if len(peaks) >= 2:
            last_peak = peaks[-1][1]
            prev_peak = peaks[-2][1]
            if last_peak > prev_peak:
                return True, f"Cấu trúc BUY OK (Đỉnh sau {last_peak:.5f} > đỉnh trước {prev_peak:.5f})"
            else:
                return False, f"Cấu trúc BUY không OK (Đỉnh sau {last_peak:.5f} <= đỉnh trước {prev_peak:.5f})"
        
        # Nếu không có đủ đỉnh, kiểm tra xu hướng giá
        if len(recent_data) >= 3:
            recent_closes = recent_data['close'].iloc[-3:].values
            if recent_closes[-1] < recent_closes[-2] < recent_closes[-3]:
                return False, "M1 đang giảm (3 nến cuối giảm) - Không BUY"
        
        # CẢI THIỆN: Nếu không có đủ đỉnh để xác định → chặn
        return False, f"Cấu trúc BUY không rõ ràng (chỉ có {len(peaks)} đỉnh, cần ít nhất 2 đỉnh)"
    
    elif direction == 'SELL':
        # SELL: Cần đáy sau thấp hơn đáy trước (lower lows)
        if len(troughs) >= 2:
            last_trough = troughs[-1][1]
            prev_trough = troughs[-2][1]
            if last_trough < prev_trough:
                return True, f"Cấu trúc SELL OK (Đáy sau {last_trough:.5f} < đáy trước {prev_trough:.5f})"
            else:
                return False, f"Cấu trúc SELL không OK (Đáy sau {last_trough:.5f} >= đáy trước {prev_trough:.5f})"
        
        # Nếu không có đủ đáy, kiểm tra xu hướng giá
        if len(recent_data) >= 3:
            recent_closes = recent_data['close'].iloc[-3:].values
            if recent_closes[-1] > recent_closes[-2] > recent_closes[-3]:
                return False, "M1 đang tăng (3 nến cuối tăng) - Không SELL"
        
        # CẢI THIỆN: Nếu không có đủ đáy để xác định → chặn
        return False, f"Cấu trúc SELL không rõ ràng (chỉ có {len(troughs)} đáy, cần ít nhất 2 đáy)"

def check_spread_filter(spread_points):
    """
    Kiểm tra Spread Filter
    
    Spread > 50 points (5 pips) → bỏ lệnh M1
    
    Args:
        spread_points: Spread hiện tại (points)
        
    Returns:
        Tuple (bool, str): (spread_ok, reason)
            - spread_ok: True nếu spread OK, False nếu quá lớn
            - reason: Lý do
    """
    if not ENABLE_SPREAD_FILTER:
        return True, "Spread filter đã tắt"
    
    # Chuyển đổi sang pips để hiển thị rõ ràng (1 pip = 10 points cho XAUUSD)
    spread_pips = spread_points / 10
    max_pips = SPREAD_MAX_POINTS / 10
    
    if spread_points > SPREAD_MAX_POINTS:
        return False, f"Spread quá lớn ({spread_points:.1f} points = {spread_pips:.1f} pips > {SPREAD_MAX_POINTS} points = {max_pips:.1f} pips)"
    
    return True, f"Spread OK ({spread_points:.1f} points = {spread_pips:.1f} pips <= {SPREAD_MAX_POINTS} points = {max_pips:.1f} pips)"

def check_time_filter():
    """
    Kiểm tra Time Filter (Tránh giờ tin tức)
    
    Tránh giao dịch trong vùng TIME_FILTER_BUFFER_MINUTES phút trước/sau tin tức quan trọng.
    
    Returns:
        Tuple (bool, str): (time_ok, reason)
            - time_ok: True nếu OK (không trong giờ tin tức), False nếu trong giờ tin tức
            - reason: Lý do
    """
    if not ENABLE_TIME_FILTER:
        return True, "Time filter đã tắt"
    
    # Lấy thời gian hiện tại (UTC)
    now_utc = datetime.utcnow()
    current_hour = now_utc.hour
    current_minute = now_utc.minute
    current_time_minutes = current_hour * 60 + current_minute
    
    # Kiểm tra từng giờ tin tức
    for news_hour, news_minute in IMPORTANT_NEWS_HOURS:
        news_time_minutes = news_hour * 60 + news_minute
        
        # Tính khoảng cách (phút)
        time_diff = abs(current_time_minutes - news_time_minutes)
        
        # Nếu trong vùng buffer → chặn
        if time_diff <= TIME_FILTER_BUFFER_MINUTES:
            # Tính thời gian còn lại
            if current_time_minutes < news_time_minutes:
                remaining = news_time_minutes - current_time_minutes
                return False, f"Trong vùng tin tức (Còn {remaining} phút đến tin tức lúc {news_hour:02d}:{news_minute:02d} UTC)"
            else:
                elapsed = current_time_minutes - news_time_minutes
                return False, f"Trong vùng tin tức (Đã qua {elapsed} phút sau tin tức lúc {news_hour:02d}:{news_minute:02d} UTC)"
    
    return True, f"Không trong giờ tin tức (Hiện tại: {current_hour:02d}:{current_minute:02d} UTC)"

def calculate_rsi(prices, period=14):
    """
    Tính Relative Strength Index (RSI)
    
    Args:
        prices: Series giá đóng cửa (close prices)
        period: Chu kỳ tính RSI (mặc định: 14)
        
    Returns:
        Series RSI với giá trị từ 0-100
    """
    # Tính độ thay đổi giá (delta)
    delta = prices.diff()
    
    # Tách thành gain (tăng) và loss (giảm)
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    
    # Tính trung bình gain và loss trong chu kỳ
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    # Tính Relative Strength (RS) = avg_gain / avg_loss
    # Tránh chia cho 0
    rs = avg_gain / (avg_loss + 1e-10)
    
    # Tính RSI = 100 - (100 / (1 + RS))
    rsi = 100 - (100 / (1 + rs))
    return rsi

def check_rsi_filter(df_m5, direction):
    """
    Kiểm tra RSI Filter (Tránh quá mua/quá bán)
    
    - RSI > 70 → Quá mua (không BUY)
    - RSI < 30 → Quá bán (không SELL)
    
    Args:
        df_m5: DataFrame M5 (để tính RSI trên timeframe trend)
        direction: 'BUY' hoặc 'SELL'
        
    Returns:
        Tuple (bool, str): (rsi_ok, reason)
            - rsi_ok: True nếu OK, False nếu quá mua/quá bán
            - reason: Lý do
    """
    if not ENABLE_RSI_FILTER:
        return True, "RSI filter đã tắt"
    
    if df_m5 is None or len(df_m5) < RSI_PERIOD:
        return True, "Không đủ dữ liệu để tính RSI"
    
    # Tính RSI trên M5
    rsi_values = calculate_rsi(df_m5['close'], RSI_PERIOD)
    rsi_current = rsi_values.iloc[-1]
    
    if pd.isna(rsi_current):
        return True, "RSI chưa tính được (thiếu dữ liệu)"
    
    if direction == 'BUY':
        if rsi_current > RSI_OVERBOUGHT:
            return False, f"RSI quá mua ({rsi_current:.2f} > {RSI_OVERBOUGHT}) - Không BUY"
        else:
            return True, f"RSI OK ({rsi_current:.2f} <= {RSI_OVERBOUGHT})"
    
    elif direction == 'SELL':
        if rsi_current < RSI_OVERSOLD:
            return False, f"RSI quá bán ({rsi_current:.2f} < {RSI_OVERSOLD}) - Không SELL"
        else:
            return True, f"RSI OK ({rsi_current:.2f} >= {RSI_OVERSOLD})"
    
    return True, "RSI OK"

def check_volume_confirmation(df_m1):
    """
    Kiểm tra Volume Confirmation (Xác nhận volume tăng)
    
    Volume của nến hiện tại phải tăng ít nhất VOLUME_INCREASE_RATIO so với nến trước.
    
    Args:
        df_m1: DataFrame M1
        
    Returns:
        Tuple (bool, str): (volume_ok, reason)
            - volume_ok: True nếu volume tăng, False nếu không
            - reason: Lý do
    """
    if not ENABLE_VOLUME_CONFIRMATION:
        return True, "Volume confirmation đã tắt"
    
    if len(df_m1) < 2:
        return True, "Không đủ dữ liệu để so sánh volume"
    
    # Lấy volume của nến cuối và nến trước
    last_volume = df_m1.iloc[-1]['tick_volume']
    prev_volume = df_m1.iloc[-2]['tick_volume']
    
    if prev_volume == 0:
        return True, "Volume nến trước = 0 (không so sánh được)"
    
    # Tính tỷ lệ tăng
    volume_ratio = last_volume / prev_volume
    
    if volume_ratio >= VOLUME_INCREASE_RATIO:
        return True, f"Volume tăng ({volume_ratio:.2f}x >= {VOLUME_INCREASE_RATIO}x) - OK"
    else:
        return False, f"Volume không tăng đủ ({volume_ratio:.2f}x < {VOLUME_INCREASE_RATIO}x) - Cần volume tăng ít nhất {VOLUME_INCREASE_RATIO}x"

# ==============================================================================
# 6. HÀM KIỂM TRA COOLDOWN SAU LỆNH THUA
# ==============================================================================

def check_last_loss_cooldown():
    """
    Kiểm tra cooldown sau lệnh thua với các mode:
    - Mode 1: Nếu lệnh cuối cùng thua → nghỉ LOSS_COOLDOWN_MINUTES phút
    - Mode 2: Nếu 2 lệnh cuối cùng đều thua → nghỉ LOSS_COOLDOWN_MINUTES phút
    - Mode 3 (nếu bật): Nếu 3 lệnh cuối cùng đều thua → nghỉ LOSS_COOLDOWN_3LOSS_MINUTES phút
    
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
        
        # MODE 3: Kiểm tra 3 lệnh cuối cùng đều thua (nếu bật) - ƯU TIÊN CAO NHẤT
        # Mode này chạy độc lập với mode 1 và 2, ưu tiên cao hơn
        if ENABLE_LOSS_COOLDOWN_3LOSS:
            # Cần ít nhất 3 lệnh để check
            if len(closed_deals) >= 3:
                # Lấy 3 lệnh cuối cùng
                last_deal = closed_deals[0]
                second_last_deal = closed_deals[1]
                third_last_deal = closed_deals[2]
                
                last_deal_profit = last_deal.profit
                second_last_deal_profit = second_last_deal.profit
                third_last_deal_profit = third_last_deal.profit
                last_deal_time = datetime.fromtimestamp(last_deal.time)
                
                # Kiểm tra nếu cả 3 lệnh cuối cùng đều thua
                if last_deal_profit < 0 and second_last_deal_profit < 0 and third_last_deal_profit < 0:
                    # Tính thời gian đã trôi qua từ khi đóng lệnh cuối cùng
                    time_elapsed = datetime.now() - last_deal_time
                    minutes_elapsed = time_elapsed.total_seconds() / 60
                    
                    if minutes_elapsed < LOSS_COOLDOWN_3LOSS_MINUTES:
                        remaining_minutes = LOSS_COOLDOWN_3LOSS_MINUTES - minutes_elapsed
                        hours_remaining = remaining_minutes / 60
                        if hours_remaining >= 1:
                            message = f"⏸️ Cooldown (3 lệnh thua): Còn {hours_remaining:.1f} giờ ({remaining_minutes:.1f} phút) - 3 lệnh cuối đều thua: {last_deal_profit:.2f} USD, {second_last_deal_profit:.2f} USD, {third_last_deal_profit:.2f} USD, đóng lúc {last_deal_time.strftime('%H:%M:%S')}"
                        else:
                            message = f"⏸️ Cooldown (3 lệnh thua): Còn {remaining_minutes:.1f} phút - 3 lệnh cuối đều thua: {last_deal_profit:.2f} USD, {second_last_deal_profit:.2f} USD, {third_last_deal_profit:.2f} USD, đóng lúc {last_deal_time.strftime('%H:%M:%S')}"
                        return False, message
                    else:
                        hours_elapsed = minutes_elapsed / 60
                        if hours_elapsed >= 1:
                            message = f"✅ Đã qua cooldown sau 3 lệnh thua ({hours_elapsed:.1f} giờ đã trôi qua)"
                        else:
                            message = f"✅ Đã qua cooldown sau 3 lệnh thua ({minutes_elapsed:.1f} phút đã trôi qua)"
                        return True, message
        
        # MODE 1: Kiểm tra 1 lệnh cuối cùng thua
        if LOSS_COOLDOWN_MODE == 1:
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
                    message = f"⏸️ Cooldown (Mode 1): Còn {remaining_minutes:.1f} phút (Lệnh cuối thua: {last_deal_profit:.2f} USD, đóng lúc {last_deal_time.strftime('%H:%M:%S')})"
                    return False, message
                else:
                    message = f"✅ Đã qua cooldown sau lệnh thua ({minutes_elapsed:.1f} phút đã trôi qua)"
                    return True, message
            else:
                # Lệnh cuối cùng là lệnh lời hoặc hòa vốn → Cho phép mở lệnh mới
                message = f"✅ Lệnh đóng cuối cùng là lệnh lời/hòa vốn (Profit: {last_deal_profit:.2f} USD)"
                return True, message
        
        # MODE 2: Kiểm tra 2 lệnh cuối cùng đều thua
        elif LOSS_COOLDOWN_MODE == 2:
            # Cần ít nhất 2 lệnh để check
            if len(closed_deals) < 2:
                if len(closed_deals) == 1:
                    last_deal = closed_deals[0]
                    if last_deal.profit < 0:
                        return True, "Chỉ có 1 lệnh đóng (Mode 2 cần 2 lệnh đều thua)"
                    else:
                        return True, f"Lệnh cuối cùng là lệnh lời/hòa vốn (Profit: {last_deal.profit:.2f} USD)"
                else:
                    return True, "Không đủ lệnh để kiểm tra (Mode 2 cần 2 lệnh)"
            
            # Lấy 2 lệnh cuối cùng
            last_deal = closed_deals[0]
            second_last_deal = closed_deals[1]
            
            last_deal_profit = last_deal.profit
            second_last_deal_profit = second_last_deal.profit
            last_deal_time = datetime.fromtimestamp(last_deal.time)
            
            # Kiểm tra nếu cả 2 lệnh cuối cùng đều thua
            if last_deal_profit < 0 and second_last_deal_profit < 0:
                # Tính thời gian đã trôi qua từ khi đóng lệnh cuối cùng
                time_elapsed = datetime.now() - last_deal_time
                minutes_elapsed = time_elapsed.total_seconds() / 60
                
                if minutes_elapsed < LOSS_COOLDOWN_MINUTES:
                    remaining_minutes = LOSS_COOLDOWN_MINUTES - minutes_elapsed
                    message = f"⏸️ Cooldown (Mode 2): Còn {remaining_minutes:.1f} phút (2 lệnh cuối đều thua: {last_deal_profit:.2f} USD, {second_last_deal_profit:.2f} USD, đóng lúc {last_deal_time.strftime('%H:%M:%S')})"
                    return False, message
                else:
                    message = f"✅ Đã qua cooldown sau 2 lệnh thua ({minutes_elapsed:.1f} phút đã trôi qua)"
                    return True, message
            else:
                # Không phải cả 2 lệnh đều thua → Cho phép mở lệnh mới
                if last_deal_profit >= 0:
                    message = f"✅ Lệnh cuối cùng là lệnh lời/hòa vốn (Profit: {last_deal_profit:.2f} USD) - Mode 2 không áp dụng"
                elif second_last_deal_profit >= 0:
                    message = f"✅ Lệnh thứ 2 là lệnh lời/hòa vốn (Profit: {second_last_deal_profit:.2f} USD) - Mode 2 không áp dụng"
                else:
                    message = f"✅ Không phải cả 2 lệnh cuối đều thua (Lệnh cuối: {last_deal_profit:.2f} USD, Lệnh thứ 2: {second_last_deal_profit:.2f} USD)"
                return True, message
        
        else:
            # Mode không hợp lệ
            return True, f"⚠️ LOSS_COOLDOWN_MODE không hợp lệ: {LOSS_COOLDOWN_MODE} (Chỉ hỗ trợ 1 hoặc 2)"
            
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

def calculate_atr_from_m5(df_m5, period=14):
    """
    Tính ATR từ nến M5
    
    Args:
        df_m5: DataFrame M5
        period: Chu kỳ ATR (mặc định: 14)
        
    Returns:
        ATR value (trong pips) hoặc None nếu không đủ dữ liệu
    """
    if df_m5 is None or len(df_m5) < period + 1:
        return None
    
    point = get_symbol_info()
    if point is None:
        return None
    
    high = df_m5['high']
    low = df_m5['low']
    close = df_m5['close']
    
    # Tính True Range (TR) - giá trị thực (USD)
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Tính ATR (trung bình của TR) - giá trị thực (USD)
    atr_price = tr.rolling(window=period).mean().iloc[-1]
    
    # Chuyển ATR từ giá trị thực sang pips
    # Với XAUUSD: 1 pip = 0.01 USD (User preference)
    # ATR(pips) = ATR(price) / 0.01 = ATR(price) * 100
    atr_pips = atr_price / 0.01  # = atr_price * 100
    
    return atr_pips

def send_order(trade_type, volume, df_m1=None, df_m5=None, m5_trend=None, m1_signal=None, signal_type=None, adx_m5_current=None, atr_pips=None, spread_points=None, deviation=20):
    """
    Gửi lệnh Market Execution với SL/TP theo nến M5 (ATR-based).
    
    Args:
        trade_type: mt5.ORDER_TYPE_BUY hoặc mt5.ORDER_TYPE_SELL
        volume: Khối lượng giao dịch
        df_m1: DataFrame M1 (không dùng cho ATR nữa)
        df_m5: DataFrame M5 để tính ATR (nếu None thì dùng giá trị cố định)
        m5_trend: Thông tin trend M5 ('BUY', 'SELL', 'SIDEWAYS')
        m1_signal: Tín hiệu M1 ('BUY', 'SELL', 'NONE')
        signal_type: Loại tín hiệu ('RETEST', 'BREAKOUT', 'NONE')
        adx_m5_current: Giá trị ADX(M5) hiện tại
        atr_pips: Giá trị ATR (pips) - nếu đã tính sẵn
        spread_points: Spread hiện tại (points)
        deviation: Độ lệch giá cho phép
    
    Returns:
        bool: True nếu gửi lệnh thành công, False nếu lỗi
    """
    global error_count, error_cooldown_start
    
    point = get_symbol_info()
    if point is None:
        print("❌ Lỗi: Không thể lấy thông tin ký hiệu để gửi lệnh.")
        return
        
    tick_info = mt5.symbol_info_tick(SYMBOL)
    price = tick_info.ask if trade_type == mt5.ORDER_TYPE_BUY else tick_info.bid
    
    # Tính SL và TP
    # Lưu ý: Với XAUUSD, lot 0.01: 100 pips = 1 USD
    atr_pips = None
    sl_pips_limited = None
    tp_pips_limited = None
    
    # Kiểm tra nếu bật fix SL theo USD
    if ENABLE_FIXED_SL_USD and FIXED_SL_USD > 0:
        # Tính SL từ USD cố định
        # Với XAUUSD, lot 0.01: 100 pips = 1 USD
        # SL (pips) = SL (USD) / 0.01 = SL (USD) × 100
        sl_pips_fixed = FIXED_SL_USD / 0.01  # Chuyển USD sang pips
        
        # Tính points dựa trên USD để chính xác với mọi loại point (2 digit hay 3 digit)
        # SL(points) = SL(USD) / point
        sl_points = FIXED_SL_USD / point
        
        sl_pips_limited = sl_pips_fixed
        
        print(f"  📊 [ORDER] SL CỐ ĐỊNH: {FIXED_SL_USD} USD = {sl_pips_fixed:.1f} pips ({sl_points:.0f} points)")
        
        # Tính TP vẫn dựa trên ATR (nếu có) hoặc dùng giá trị mặc định
        if df_m5 is not None:
            atr_pips = calculate_atr_from_m5(df_m5)
            if atr_pips is not None:
                tp_pips = atr_pips * TP_ATR_MULTIPLIER
                
                # Tính TP USD và Points
                tp_usd = tp_pips * 0.01
                tp_points = tp_usd / point
                
                # Giới hạn TP (points)
                tp_points = max(TP_POINTS_MIN, min(tp_points, TP_POINTS_MAX))
                
                # Tính lại pips hiển thị
                tp_pips_limited = (tp_points * point) / 0.01
                print(f"  📊 [ORDER] TP: {tp_pips_limited:.1f} pips (ATR×{TP_ATR_MULTIPLIER}, giới hạn {TP_POINTS_MIN*point/0.01:.0f}-{TP_POINTS_MAX*point/0.01:.0f} pips)")
            else:
                tp_points = (TP_POINTS_MIN + TP_POINTS_MAX) // 2
                tp_pips_limited = (tp_points * point) / 0.01
                print(f"  ⚠️ [ORDER] Không tính được ATR cho TP, dùng giá trị mặc định: TP: {tp_pips_limited:.1f} pips")
        else:
            tp_points = (TP_POINTS_MIN + TP_POINTS_MAX) // 2
            tp_pips_limited = (tp_points * point) / 0.01
            print(f"  ⚠️ [ORDER] Không có dữ liệu M5 cho TP, dùng giá trị mặc định: TP: {tp_pips_limited:.1f} pips")
    else:
        # Tính SL và TP theo ATR của nến M5
        # ATR đã được tính trực tiếp trong pips từ calculate_atr_from_m5()
        if df_m5 is not None:
            atr_pips = calculate_atr_from_m5(df_m5)
            if atr_pips is not None:
                # ATR đã là pips (1 cent), tính SL và TP trực tiếp
                sl_pips = atr_pips * SL_ATR_MULTIPLIER
                tp_pips = atr_pips * TP_ATR_MULTIPLIER
                
                # Chuyển đổi sang USD rồi sang Points để chính xác
                sl_usd = sl_pips * 0.01
                tp_usd = tp_pips * 0.01
                
                # Giới hạn SL theo USD (Max $5)
                if sl_usd > SL_MAX_USD:
                    print(f"  ⚠️ [ORDER] SL quá lớn ({sl_usd:.2f} USD), giới hạn về {SL_MAX_USD} USD")
                    sl_usd = SL_MAX_USD
                    sl_pips = sl_usd / 0.01 # Cập nhật lại pips để hiển thị đúng
                
                sl_points = sl_usd / point
                tp_points = tp_usd / point
                
                # Giới hạn SL/TP trong khoảng min-max (đã là points)
                sl_points = max(SL_POINTS_MIN, min(sl_points, SL_POINTS_MAX))
                tp_points = max(TP_POINTS_MIN, min(tp_points, TP_POINTS_MAX))
                
                # Tính lại pips sau khi giới hạn (để hiển thị đúng)
                sl_pips_limited = (sl_points * point) / 0.01
                tp_pips_limited = (tp_points * point) / 0.01
                
                print(f"  📊 [ORDER] ATR(M5): {atr_pips:.2f} pips → SL: {sl_pips_limited:.1f} pips (ATR×{SL_ATR_MULTIPLIER}), TP: {tp_pips_limited:.1f} pips (ATR×{TP_ATR_MULTIPLIER})")
            else:
                # Fallback: Dùng giá trị trung bình nếu không tính được ATR
                sl_points = (SL_POINTS_MIN + SL_POINTS_MAX) // 2
                tp_points = (TP_POINTS_MIN + TP_POINTS_MAX) // 2
                print(f"  ⚠️ [ORDER] Không tính được ATR, dùng giá trị mặc định: SL: {sl_points} points, TP: {tp_points} points")
        else:
            # Fallback: Dùng giá trị trung bình nếu không có df_m5
            sl_points = (SL_POINTS_MIN + SL_POINTS_MAX) // 2
            tp_points = (TP_POINTS_MIN + TP_POINTS_MAX) // 2
            print(f"  ⚠️ [ORDER] Không có dữ liệu M5, dùng giá trị mặc định: SL: {sl_points} points, TP: {tp_points} points")
    
    sl_distance = sl_points * point
    tp_distance = tp_points * point
    
    if trade_type == mt5.ORDER_TYPE_BUY:
        # BUY: SL dưới entry, TP trên entry
        sl = price - sl_distance
        tp = price + tp_distance
    else: # SELL
        # SELL: SL trên entry, TP dưới entry
        sl = price + sl_distance
        tp = price - tp_distance
    
    # Kiểm tra logic SL/TP
    if trade_type == mt5.ORDER_TYPE_BUY:
        if sl >= price or tp <= price:
            print(f"  ⚠️ [ORDER] LỖI LOGIC: BUY order - SL ({sl:.5f}) phải < Entry ({price:.5f}) và TP ({tp:.5f}) phải > Entry")
            return
    else:  # SELL
        if sl <= price or tp >= price:
            print(f"  ⚠️ [ORDER] LỖI LOGIC: SELL order - SL ({sl:.5f}) phải > Entry ({price:.5f}) và TP ({tp:.5f}) phải < Entry")
            return
    
    # ⚠️ VALIDATION: Kiểm tra stops level của broker
    symbol_info = get_symbol_info_full()
    if symbol_info is not None:
        stops_level = getattr(symbol_info, 'stops_level', 0)
        if stops_level > 0:
            # Tính khoảng cách từ entry đến SL/TP (points)
            sl_distance_points = abs(price - sl) / point
            tp_distance_points = abs(price - tp) / point
            
            # Kiểm tra xem SL/TP có đủ xa entry không (phải >= stops_level)
            if sl_distance_points < stops_level:
                print(f"  ⚠️ [ORDER] SL quá gần entry: {sl_distance_points:.1f} points < stops_level {stops_level} points")
                print(f"     → Điều chỉnh SL từ {sl:.5f} để đảm bảo khoảng cách >= {stops_level} points")
                # Điều chỉnh SL để đảm bảo khoảng cách >= stops_level
                if trade_type == mt5.ORDER_TYPE_BUY:
                    sl = price - (stops_level * point)
                else:  # SELL
                    sl = price + (stops_level * point)
                # Tính lại sl_points sau khi điều chỉnh
                sl_points = abs(price - sl) / point
                print(f"     → SL mới: {sl:.5f} ({sl_points/10:.1f} pips)")
            
            if tp_distance_points < stops_level:
                print(f"  ⚠️ [ORDER] TP quá gần entry: {tp_distance_points:.1f} points < stops_level {stops_level} points")
                print(f"     → Điều chỉnh TP từ {tp:.5f} để đảm bảo khoảng cách >= {stops_level} points")
                # Điều chỉnh TP để đảm bảo khoảng cách >= stops_level
                if trade_type == mt5.ORDER_TYPE_BUY:
                    tp = price + (stops_level * point)
                else:  # SELL
                    tp = price - (stops_level * point)
                # Tính lại tp_points sau khi điều chỉnh
                tp_points = abs(price - tp) / point
                print(f"     → TP mới: {tp:.5f} ({tp_points/10:.1f} pips)")
    
    print(f"  💰 [ORDER] Entry: {price:.5f} | SL: {sl:.5f} ({sl_points/10:.1f} pips) | TP: {tp:.5f} ({tp_points/10:.1f} pips)")
        
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
        "comment": f"Bot_Auto_{'BUY' if trade_type == mt5.ORDER_TYPE_BUY else 'SELL'}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    
    # Lấy logger để ghi log
    logger = logging.getLogger(__name__)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        error_info = mt5.last_error()
        error_msg = f"❌ Lỗi gửi lệnh {'BUY' if trade_type == mt5.ORDER_TYPE_BUY else 'SELL'} - retcode: {result.retcode}"
        print(error_msg)
        print(f"Chi tiết lỗi: {error_info}")
        print(f"  Entry: {price:.5f} | SL: {sl:.5f} ({sl_points/10:.1f} pips) | TP: {tp:.5f} ({tp_points/10:.1f} pips)")
        
        # Tăng đếm lỗi liên tiếp
        if ENABLE_ERROR_COOLDOWN:
            error_count += 1
            print(f"  ⚠️ [ERROR COUNT] Lỗi liên tiếp: {error_count}/{ERROR_COOLDOWN_COUNT}")
            
            # Nếu đạt ngưỡng lỗi, kích hoạt cooldown
            if error_count >= ERROR_COOLDOWN_COUNT:
                error_cooldown_start = datetime.now()
                print(f"  🛑 [ERROR COOLDOWN] Đã lỗi {error_count}/{ERROR_COOLDOWN_COUNT} lần liên tiếp → Tạm dừng {ERROR_COOLDOWN_MINUTES} phút")
                logger.warning(f"🛑 Tạm dừng {ERROR_COOLDOWN_MINUTES} phút do lỗi {error_count} lần liên tiếp")
                send_telegram(f"<b>🛑 TẠM DỪNG BOT</b>\nĐã lỗi {error_count}/{ERROR_COOLDOWN_COUNT} lần liên tiếp\nTạm dừng {ERROR_COOLDOWN_MINUTES} phút")
        
        # Ghi log lỗi
        logger.error("=" * 70)
        logger.error(f"❌ LỖI GỬI LỆNH {'BUY' if trade_type == mt5.ORDER_TYPE_BUY else 'SELL'}")
        logger.error(f"Retcode: {result.retcode}")
        logger.error(f"Chi tiết lỗi: {error_info}")
        logger.error(f"Entry: {price:.5f} | SL: {sl:.5f} ({sl_points/10:.1f} pips) | TP: {tp:.5f} ({tp_points/10:.1f} pips)")
        logger.error(f"ATR: {atr_pips:.2f} pips" if atr_pips is not None else "ATR: N/A")
        logger.error(f"Volume: {volume} | Symbol: {SYMBOL}")
        logger.error(f"Error Count: {error_count}/{ERROR_COOLDOWN_COUNT}")
        logger.error("=" * 70)
        
        # Giải thích lỗi retcode 10030 (Invalid stops)
        if result.retcode == 10030:
            print(f"  ⚠️ LỖI 10030: Invalid stops - SL/TP không hợp lệ")
            print(f"     - Có thể SL/TP quá gần hoặc quá xa entry")
            print(f"     - Hoặc vi phạm stops level của broker")
            if symbol_info is not None:
                stops_level = getattr(symbol_info, 'stops_level', 0)
                print(f"     - Broker stops_level: {stops_level} points ({stops_level/10:.1f} pips)")
                logger.error(f"Broker stops_level: {stops_level} points ({stops_level/10:.1f} pips)")
        
        send_telegram(f"<b>❌ LỖI GỬI LỆNH</b>\n{error_msg}\nChi tiết: {error_info}\nEntry: {price:.5f} | SL: {sl:.5f} | TP: {tp:.5f}")
        return False
    else:
        success_msg = f"✅ Gửi lệnh {'BUY' if trade_type == mt5.ORDER_TYPE_BUY else 'SELL'} thành công! Order: {result.order}"
        print(success_msg)
        
        # Reset đếm lỗi khi thành công
        if ENABLE_ERROR_COOLDOWN:
            if error_count > 0:
                print(f"  ✅ [ERROR COUNT] Reset đếm lỗi (Trước đó: {error_count} lần)")
            error_count = 0
            error_cooldown_start = None
        
        # Ghi log thành công với đầy đủ chi tiết
        trade_direction = "🟢 BUY" if trade_type == mt5.ORDER_TYPE_BUY else "🔴 SELL"
        atr_display = f"{atr_pips:.2f}" if atr_pips is not None else "N/A"
        sl_atr_display = f"{sl_pips_limited:.1f}" if sl_pips_limited is not None else f"{sl_points/10:.1f}"
        tp_atr_display = f"{tp_pips_limited:.1f}" if tp_pips_limited is not None else f"{tp_points/10:.1f}"
        
        # Tính Risk/Reward
        rr_ratio = (tp_points / sl_points) if sl_points > 0 else 0
        
        logger.info("=" * 70)
        logger.info(f"✅ VÀO LỆNH THÀNH CÔNG: {trade_direction}")
        logger.info(f"Order ID: {result.order}")
        logger.info(f"Symbol: {SYMBOL}")
        logger.info(f"Entry: {price:.5f}")
        logger.info(f"SL: {sl:.5f} ({sl_points/10:.1f} pips)")
        logger.info(f"TP: {tp:.5f} ({tp_points/10:.1f} pips)")
        logger.info(f"R:R = {rr_ratio:.2f}:1")
        logger.info(f"Volume: {volume}")
        logger.info(f"ATR: {atr_display} pips (SL: {sl_atr_display}p, TP: {tp_atr_display}p)")
        
        # Ghi log các chỉ số chi tiết
        logger.info("--- CHỈ SỐ PHÂN TÍCH ---")
        if signal_type is not None:
            logger.info(f"Signal Type: {signal_type}")
        if m5_trend is not None:
            logger.info(f"M5 Trend: {m5_trend}")
        if m1_signal is not None:
            logger.info(f"M1 Signal: {m1_signal}")
        if adx_m5_current is not None:
            logger.info(f"ADX(M5): {adx_m5_current:.2f}")
        if atr_pips is not None:
            logger.info(f"ATR: {atr_pips:.2f} pips")
        if spread_points is not None:
            logger.info(f"Spread: {spread_points:.1f} points ({spread_points/10:.1f} pips)")
        
        # Ghi log các filter đã pass
        logger.info("--- FILTER STATUS ---")
        if spread_points is not None:
            logger.info(f"Spread Filter: OK ({spread_points:.1f} points <= {SPREAD_MAX_POINTS} points)")
        if atr_pips is not None:
            logger.info(f"ATR Filter: OK ({atr_pips:.2f} pips trong khoảng {ATR_MIN_THRESHOLD}-{ATR_MAX_THRESHOLD} pips)")
        if adx_m5_current is not None:
            logger.info(f"ADX Filter: OK ({adx_m5_current:.2f} >= {ADX_MIN_THRESHOLD})")
        logger.info("Bad Candle Filter: OK")
        logger.info("Momentum Filter: OK")
        logger.info("Structure Filter: OK")
        
        logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)
        
        # Gửi thông báo Telegram với thông tin chi tiết
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
        return True

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
    
    # Lấy dữ liệu M5 để tính ATR cho trailing
    df_m5 = get_rates(mt5.TIMEFRAME_M5)
    atr_pips = None
    if df_m5 is not None:
        atr_pips = calculate_atr_from_m5(df_m5)  # ATR đã là pips

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
    
    # 0. Thiết lập logging
    logger = setup_logging()
    logger.info("Khởi động bot...")
    
    # 1. Tải cấu hình
    if not load_config():
        logger.error("Không thể tải cấu hình. Dừng bot.")
        return
        
    # 2. Khởi tạo MT5 và kết nối
    initialize_mt5()
    logger.info("Đã kết nối MT5 thành công")
    
    last_candle_time = datetime(1970, 1, 1)

    print("\n--- Bắt đầu Chu Trình Giao Dịch M1 (Chiến thuật: BÁM THEO M5 – ĂN 5–10 PHÚT) ---")
    print("📋 Chiến thuật:")
    print("   1. Xác định hướng M5 bằng EMA50 (Giá > EMA50 → CHỈ BUY, Giá < EMA50 → CHỈ SELL)")
    print("   2. Chọn điểm vào ở M1 khi giá RETEST lại EMA20 (vùng 10-20 pips)")
    print("   3. ATR Filter: 40-200 pips (tránh tin mạnh)")
    print("   4. Các filter: Bad Candle, Momentum, Structure, Spread")
    print("   5. Filter bổ sung: Time Filter (OFF), RSI Filter, Volume Confirmation\n")
    
    while True:
        start_time = time.time() # Ghi lại thời gian bắt đầu chu kỳ
        current_time = datetime.now()
        
        # 2. Lấy dữ liệu M1
        df_m1 = get_rates(mt5.TIMEFRAME_M1)
        if df_m1 is None or len(df_m1) < EMA_M1 + 1:
            print("Đang chờ dữ liệu M1...")
            time.sleep(5)
            continue
            
        # Nến cuối cùng (vừa đóng)
        current_candle_time = df_m1.index[-1].replace(tzinfo=None)
        
        # 3. CHỈ XỬ LÝ TÍN HIỆU KHI CÓ NẾN MỚI ĐÓNG
        # if current_candle_time > last_candle_time:
            # last_candle_time = current_candle_time
            
        print(f"\n{'='*70}")
        print(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] 🔔 XỬ LÝ NẾN MỚI M1: {current_candle_time}")
        print(f"{'='*70}")
        
        # Lấy giá hiện tại
        tick = mt5.symbol_info_tick(SYMBOL)
        current_price = tick.bid
        current_ask = tick.ask
        point = get_symbol_info()
        spread_points = (current_ask - current_price) / point if point else 0
        print(f"  💰 Giá hiện tại: BID={current_price:.5f} | ASK={current_ask:.5f} | Spread={spread_points:.1f} points ({spread_points/10:.1f} pips)")
        
        # --- KIỂM TRA TÍN HIỆU VÀ LỌC ---
        print(f"\n  🔍 [KIỂM TRA TÍN HIỆU] Bắt đầu phân tích...")
        
        # 0. Kiểm tra Spread Filter
        print(f"\n  ┌─ [BƯỚC 0] Kiểm tra Spread Filter")
        spread_ok, spread_reason = check_spread_filter(spread_points)
        print(f"    {spread_reason}")
        print(f"  └─ [BƯỚC 0] Kết quả: {'OK' if spread_ok else 'BLOCKED'}")
        
        if not spread_ok:
            print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI SPREAD FILTER - Bỏ qua chu kỳ này")
            print(f"{'='*70}\n")
            time.sleep(1)
            continue
        
        # 1. Xác định hướng M5 bằng EMA50
        print(f"\n  ┌─ [BƯỚC 1] Kiểm tra xu hướng (M5 & H1)")
        m5_trend = check_m5_trend()
        
        # Kiểm tra H1 Trend (nếu bật)
        h1_trend = 'SIDEWAYS'
        if ENABLE_H1_TREND_FILTER:
            h1_trend = check_h1_trend()
            
            # Nếu H1 khác M5 thì coi như không đồng thuận -> SIDEWAYS (để chặn lệnh)
            if m5_trend != 'SIDEWAYS' and h1_trend != 'SIDEWAYS' and m5_trend != h1_trend:
                print(f"    ⚠️ [TREND] M5 ({m5_trend}) ngược chiều H1 ({h1_trend}) → Chặn giao dịch")
                m5_trend = 'SIDEWAYS' # Chặn tín hiệu
            elif h1_trend == 'SIDEWAYS':
                 print(f"    ⚠️ [TREND] H1 là SIDEWAYS → Chặn giao dịch")
                 m5_trend = 'SIDEWAYS'
            else:
                print(f"    ✅ [TREND] Đồng thuận xu hướng: M5 ({m5_trend}) == H1 ({h1_trend})")
        
        print(f"  └─ [BƯỚC 1] Kết quả: {m5_trend}")


        
        # Lấy dữ liệu M5 cho ADX
        df_m5 = get_rates(mt5.TIMEFRAME_M5)
        
        # 2. Kiểm tra ADX M5 (Bộ lọc tránh thị trường đi ngang)
        print(f"\n  ┌─ [BƯỚC 2] Kiểm tra ADX M5 (Tránh thị trường đi ngang)")
        adx_m5_values = calculate_adx(df_m5, ADX_PERIOD) if df_m5 is not None and len(df_m5) >= ADX_PERIOD else None
        adx_m5_current = adx_m5_values.iloc[-1] if adx_m5_values is not None and not adx_m5_values.empty else 0
        print(f"    ADX(M5) hiện tại: {adx_m5_current:.2f} (Ngưỡng tối thiểu: {ADX_MIN_THRESHOLD}, Breakout: {ADX_M5_BREAKOUT_THRESHOLD})")
        
        if adx_m5_current >= ADX_MIN_THRESHOLD:
            adx_ok = True
            print(f"    ✅ [ADX] XU HƯỚNG MẠNH (ADX(M5)={adx_m5_current:.2f} ≥ {ADX_MIN_THRESHOLD}) - Có thể giao dịch")
        else:
            adx_ok = False
            print(f"    ⚠️ [ADX] THỊ TRƯỜNG ĐI NGANG (ADX(M5)={adx_m5_current:.2f} < {ADX_MIN_THRESHOLD}) - Tránh giao dịch")
        print(f"  └─ [BƯỚC 2] Kết quả: {'OK' if adx_ok else 'BLOCKED'}")
        
        # 2.5. Kiểm tra ATR (Bộ lọc biến động thị trường) - 40-200 pips
        atr_pips = None
        atr_ok = True  # Mặc định OK nếu không bật filter
        if ENABLE_ATR_FILTER:
            print(f"\n  ┌─ [BƯỚC 2.5] Kiểm tra ATR (Lọc biến động thị trường)")
            atr_pips = calculate_atr_from_m5(df_m5)
            if atr_pips is not None:
                print(f"    ATR hiện tại: {atr_pips:.2f} pips (Ngưỡng: {ATR_MIN_THRESHOLD}-{ATR_MAX_THRESHOLD} pips)")
                if ATR_MIN_THRESHOLD <= atr_pips <= ATR_MAX_THRESHOLD:
                    atr_ok = True
                    print(f"    ✅ [ATR] BIẾN ĐỘNG PHÙ HỢP ({ATR_MIN_THRESHOLD} ≤ ATR={atr_pips:.2f} ≤ {ATR_MAX_THRESHOLD} pips) - Có thể giao dịch")
                elif atr_pips < ATR_MIN_THRESHOLD:
                    atr_ok = False
                    print(f"    ⚠️ [ATR] BIẾN ĐỘNG QUÁ NHỎ (ATR={atr_pips:.2f} < {ATR_MIN_THRESHOLD} pips) - Tránh giao dịch")
                else:
                    atr_ok = False
                    print(f"    ⚠️ [ATR] BIẾN ĐỘNG QUÁ LỚN (ATR={atr_pips:.2f} > {ATR_MAX_THRESHOLD} pips) - Tránh tin mạnh")
            else:
                atr_ok = False
                print(f"    ⚠️ [ATR] Không tính được ATR - Tránh giao dịch")
            print(f"  └─ [BƯỚC 2.5] Kết quả: {'OK' if atr_ok else 'BLOCKED'}")

        # 3. Kiểm tra điểm vào ở M1: RETEST hoặc BREAKOUT
        print(f"\n  ┌─ [BƯỚC 3] Kiểm tra tín hiệu M1 (Retest EMA20 hoặc Breakout)")
        
        # Ưu tiên 1: Kiểm tra RETEST EMA20
        m1_retest_signal = check_m1_retest_ema20(df_m1, m5_trend)
        
        # Ưu tiên 2: Nếu không có retest, kiểm tra BREAKOUT (chỉ khi điều kiện nghiêm ngặt)
        m1_breakout_signal = 'NONE'
        if m1_retest_signal == 'NONE' and ENABLE_BREAKOUT:
            m1_breakout_signal = check_m1_breakout(df_m1, df_m5, m5_trend, adx_m5_current, spread_points)
        
        # Kết hợp tín hiệu: Ưu tiên retest, nếu không có thì dùng breakout
        m1_signal = m1_retest_signal if m1_retest_signal != 'NONE' else m1_breakout_signal
        
        if m1_retest_signal != 'NONE':
            print(f"    ✅ [M1 SIGNAL] RETEST EMA20: {m1_retest_signal}")
        elif m1_breakout_signal != 'NONE':
            print(f"    ✅ [M1 SIGNAL] BREAKOUT: {m1_breakout_signal} (ADX(M5)={adx_m5_current:.2f} > {ADX_M5_BREAKOUT_THRESHOLD})")
        else:
            print(f"    ⚠️ [M1 SIGNAL] Chưa có tín hiệu (Retest: {m1_retest_signal}, Breakout: {m1_breakout_signal})")
        
        print(f"  └─ [BƯỚC 3] Kết quả: {m1_signal}")
        
        # 3.5. Kiểm tra các filter bổ sung
        bad_candle_ok = True
        momentum_ok = True
        structure_ok = True
        time_ok = True
        rsi_ok = True
        volume_ok = True
        
        if m1_signal != 'NONE':
            print(f"\n  ┌─ [BƯỚC 3.5] Kiểm tra các filter bổ sung")
            
            # Time Filter (Tránh giờ tin tức)
            time_ok, time_reason = check_time_filter()
            print(f"    Time Filter: {'❌ ' + time_reason if not time_ok else '✅ ' + time_reason}")
            
            # Bad Candle Filter
            is_bad, bad_reason = check_bad_candle(df_m1)
            bad_candle_ok = not is_bad
            print(f"    Bad Candle: {'❌ ' + bad_reason if is_bad else '✅ OK'}")
            
            # Momentum Filter
            if m1_signal in ['BUY', 'SELL']:
                has_momentum, momentum_reason = check_momentum_candle(df_m1, m1_signal)
                momentum_ok = not has_momentum
                print(f"    Momentum: {'❌ ' + momentum_reason if has_momentum else '✅ OK'}")
            
            # Structure Filter
            if m1_signal in ['BUY', 'SELL']:
                structure_ok, structure_reason = check_m1_structure(df_m1, m1_signal)
                print(f"    Structure: {'❌ ' + structure_reason if not structure_ok else '✅ ' + structure_reason}")
            
            # RSI Filter (Tránh quá mua/quá bán)
            if m1_signal in ['BUY', 'SELL']:
                rsi_ok, rsi_reason = check_rsi_filter(df_m5, m1_signal)
                print(f"    RSI: {'❌ ' + rsi_reason if not rsi_ok else '✅ ' + rsi_reason}")
            
            # Volume Confirmation (Chỉ check cho Retest)
            if signal_type == "RETEST":
                volume_ok, volume_reason = check_volume_confirmation(df_m1)
                print(f"    Volume: {'❌ ' + volume_reason if not volume_ok else '✅ ' + volume_reason}")
            else:
                volume_ok = True  # Breakout đã check volume trong hàm check_m1_breakout
            
            print(f"  └─ [BƯỚC 3.5] Kết quả: {'OK' if (bad_candle_ok and momentum_ok and structure_ok and time_ok and rsi_ok and volume_ok) else 'BLOCKED'}")

        # 4. Kiểm tra vị thế đang mở (chỉ đếm lệnh của cặp XAUUSD)
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions is None:
            open_positions = 0
        else:
            # Chỉ đếm lệnh có magic number của bot này
            open_positions = len([pos for pos in positions if pos.magic == MAGIC])
        print(f"\n  📋 [TRẠNG THÁI] Số lệnh đang mở ({SYMBOL}): {open_positions}")
        
        signal_type = "RETEST" if m1_retest_signal != 'NONE' else ("BREAKOUT" if m1_breakout_signal != 'NONE' else "NONE")
        print(f"\n  📊 [TÓM TẮT] M5 Trend={m5_trend} | M1 Signal={m1_signal} ({signal_type}) | ADX(M5)={adx_m5_current:.2f} | ATR={atr_pips:.2f} pips" if atr_pips else f"\n  📊 [TÓM TẮT] M5 Trend={m5_trend} | M1 Signal={m1_signal} ({signal_type}) | ADX(M5)={adx_m5_current:.2f}")

        if open_positions <1:
            # Không có lệnh nào, tìm tín hiệu vào lệnh
            print(f"\n  🎯 [QUYẾT ĐỊNH] Không có lệnh đang mở, kiểm tra điều kiện vào lệnh...")
            
            # Kiểm tra cooldown sau lỗi gửi lệnh
            global error_count, error_cooldown_start
            if ENABLE_ERROR_COOLDOWN and error_cooldown_start is not None:
                time_elapsed = datetime.now() - error_cooldown_start
                minutes_elapsed = time_elapsed.total_seconds() / 60
                
                if minutes_elapsed < ERROR_COOLDOWN_MINUTES:
                    remaining_minutes = ERROR_COOLDOWN_MINUTES - minutes_elapsed
                    print(f"  🛑 [QUYẾT ĐỊNH] BỊ CHẶN BỞI ERROR COOLDOWN:")
                    print(f"     - Đã lỗi {error_count} lần liên tiếp")
                    print(f"     - Tạm dừng {ERROR_COOLDOWN_MINUTES} phút")
                    print(f"     - Còn {remaining_minutes:.1f} phút")
                    print(f"{'='*70}\n")
                    continue  # Bỏ qua chu kỳ này
                else:
                    # Hết cooldown, reset
                    print(f"  ✅ [ERROR COOLDOWN] Đã hết thời gian tạm dừng ({minutes_elapsed:.1f} phút đã trôi qua)")
                    error_count = 0
                    error_cooldown_start = None
            
            # ⚠️ QUAN TRỌNG: Kiểm tra tất cả filter trước khi vào lệnh
            filters_passed = True
            filter_reasons = []
            
            if signal_type == "RETEST" and not adx_ok:
                filters_passed = False
                filter_reasons.append(f"ADX(M5)={adx_m5_current:.2f} < {ADX_MIN_THRESHOLD}")
            
            if ENABLE_ATR_FILTER and not atr_ok:
                filters_passed = False
                atr_display = f"{atr_pips:.2f}" if atr_pips is not None else "N/A"
                if atr_pips and atr_pips < ATR_MIN_THRESHOLD:
                    filter_reasons.append(f"ATR={atr_display} pips < {ATR_MIN_THRESHOLD} pips")
                elif atr_pips and atr_pips > ATR_MAX_THRESHOLD:
                    filter_reasons.append(f"ATR={atr_display} pips > {ATR_MAX_THRESHOLD} pips (tin mạnh)")
            
            if not time_ok:
                filters_passed = False
                filter_reasons.append("Time Filter (Trong giờ tin tức)")
            
            if not bad_candle_ok:
                filters_passed = False
                filter_reasons.append("Bad Candle")
            
            if not momentum_ok:
                filters_passed = False
                filter_reasons.append("Momentum Candle")
            
            if not structure_ok:
                filters_passed = False
                filter_reasons.append("M1 Structure")
            
            if not rsi_ok:
                filters_passed = False
                filter_reasons.append("RSI Filter (Quá mua/quá bán)")
            
            if signal_type == "RETEST" and not volume_ok:
                filters_passed = False
                filter_reasons.append("Volume Confirmation (Volume không tăng)")
            
            if not filters_passed:
                print(f"\n  ⚠️ [QUYẾT ĐỊNH] KHÔNG VÀO LỆNH - BỊ CHẶN BỞI FILTER:")
                print(f"  {'='*65}")
                print(f"  📊 [PHÂN TÍCH CHI TIẾT]")
                print(f"     - M5 Trend: {m5_trend}")
                print(f"     - M1 Signal: {m1_signal} ({signal_type})")
                print(f"     - ADX(M5): {adx_m5_current:.2f}")
                if atr_pips is not None:
                    print(f"     - ATR: {atr_pips:.2f} pips")
                print(f"     - Spread: {spread_points:.1f} points ({spread_points/10:.1f} pips)")
                print(f"  ❌ [LÝ DO KHÔNG VÀO LỆNH]:")
                for reason in filter_reasons:
                    print(f"     - {reason}")
                print(f"  {'='*65}\n")
            elif m1_signal == 'BUY' and m5_trend == 'BUY':
                print(f"  ✅ [QUYẾT ĐỊNH] 🚀 TÍN HIỆU MUA MẠNH!")
                print(f"     - M5 Trend: {m5_trend} (Giá > EMA50)")
                print(f"     - M1 Signal: {m1_signal} ({signal_type})")
                if signal_type == "RETEST":
                    print(f"       → Giá retest EMA20 từ dưới lên (vùng 10-20 pips)")
                elif signal_type == "BREAKOUT":
                    print(f"       → Giá phá đỉnh gần nhất (Breakout momentum)")
                print(f"     - ADX(M5): {adx_m5_current:.2f} (Xu hướng mạnh)")
                if ENABLE_ATR_FILTER and atr_pips is not None:
                    print(f"     - ATR: {atr_pips:.2f} pips (Biến động phù hợp)")
                print(f"     - Spread: {spread_points:.1f} points ({spread_points/10:.1f} pips)")
                print(f"     - Volume: {VOLUME}")
                
                # Kiểm tra Momentum Confirmation (Sniper Entry)
                print(f"\n  ┌─ [CONFIRMATION] Kiểm tra Momentum Confirmation (Sniper Entry)")
                confirmed, confirm_msg = check_momentum_confirmation(df_m1, 'BUY')
                print(f"    {confirm_msg}")
                print(f"  └─ [CONFIRMATION] Kết quả: {'OK' if confirmed else 'WAITING'}")
                
                if not confirmed:
                    print(f"  ⏳ [QUYẾT ĐỊNH] CHỜ XÁC NHẬN MOMENTUM - Chưa vào lệnh")
                    time.sleep(1)
                    continue

                # Kiểm tra cooldown sau lệnh thua (chỉ check khi có tín hiệu)
                print(f"\n  ┌─ [COOLDOWN] Kiểm tra cooldown sau lệnh thua")
                cooldown_allowed, cooldown_message = check_last_loss_cooldown()
                print(f"    {cooldown_message}")
                print(f"  └─ [COOLDOWN] Kết quả: {'OK' if cooldown_allowed else 'BLOCKED'}")
                
                if not cooldown_allowed:
                    print(f"\n  ⚠️ [QUYẾT ĐỊNH] KHÔNG VÀO LỆNH - BỊ CHẶN BỞI COOLDOWN SAU LỆNH THUA:")
                    print(f"  {'='*65}")
                    print(f"  📊 [PHÂN TÍCH CHI TIẾT]")
                    print(f"     - M5 Trend: {m5_trend} (Giá > EMA50)")
                    print(f"     - M1 Signal: {m1_signal} ({signal_type})")
                    print(f"     - ADX(M5): {adx_m5_current:.2f} (Xu hướng mạnh)")
                    if ENABLE_ATR_FILTER and atr_pips is not None:
                        print(f"     - ATR: {atr_pips:.2f} pips (Biến động phù hợp)")
                    print(f"     - Spread: {spread_points:.1f} points ({spread_points/10:.1f} pips)")
                    print(f"     - Volume: {VOLUME}")
                    print(f"  ❌ [LÝ DO KHÔNG VÀO LỆNH]:")
                    print(f"     - {cooldown_message}")
                    print(f"     - Chờ đủ {LOSS_COOLDOWN_MINUTES} phút sau lệnh thua cuối cùng")
                    print(f"  {'='*65}\n")
                else:
                    send_order(mt5.ORDER_TYPE_BUY, VOLUME, df_m1=df_m1, df_m5=df_m5, m5_trend=m5_trend, m1_signal=m1_signal, signal_type=signal_type, adx_m5_current=adx_m5_current, atr_pips=atr_pips, spread_points=spread_points)
                
            elif m1_signal == 'SELL' and m5_trend == 'SELL':
                print(f"  ✅ [QUYẾT ĐỊNH] 🔻 TÍN HIỆU BÁN MẠNH!")
                print(f"     - M5 Trend: {m5_trend} (Giá < EMA50)")
                print(f"     - M1 Signal: {m1_signal} ({signal_type})")
                if signal_type == "RETEST":
                    print(f"       → Giá retest EMA20 từ trên xuống (vùng 10-20 pips)")
                elif signal_type == "BREAKOUT":
                    print(f"       → Giá phá đáy gần nhất (Breakout momentum)")
                print(f"     - ADX(M5): {adx_m5_current:.2f} (Xu hướng mạnh)")
                if ENABLE_ATR_FILTER and atr_pips is not None:
                    print(f"     - ATR: {atr_pips:.2f} pips (Biến động phù hợp)")
                print(f"     - Spread: {spread_points:.1f} points ({spread_points/10:.1f} pips)")
                print(f"     - Volume: {VOLUME}")
                
                # Kiểm tra Momentum Confirmation (Sniper Entry)
                print(f"\n  ┌─ [CONFIRMATION] Kiểm tra Momentum Confirmation (Sniper Entry)")
                confirmed, confirm_msg = check_momentum_confirmation(df_m1, 'SELL')
                print(f"    {confirm_msg}")
                print(f"  └─ [CONFIRMATION] Kết quả: {'OK' if confirmed else 'WAITING'}")
                
                if not confirmed:
                    print(f"  ⏳ [QUYẾT ĐỊNH] CHỜ XÁC NHẬN MOMENTUM - Chưa vào lệnh")
                    time.sleep(1)
                    continue

                # Kiểm tra cooldown sau lệnh thua (chỉ check khi có tín hiệu)
                print(f"\n  ┌─ [COOLDOWN] Kiểm tra cooldown sau lệnh thua")
                cooldown_allowed, cooldown_message = check_last_loss_cooldown()
                print(f"    {cooldown_message}")
                print(f"  └─ [COOLDOWN] Kết quả: {'OK' if cooldown_allowed else 'BLOCKED'}")
                
                if not cooldown_allowed:
                    print(f"\n  ⚠️ [QUYẾT ĐỊNH] KHÔNG VÀO LỆNH - BỊ CHẶN BỞI COOLDOWN SAU LỆNH THUA:")
                    print(f"  {'='*65}")
                    print(f"  📊 [PHÂN TÍCH CHI TIẾT]")
                    print(f"     - M5 Trend: {m5_trend} (Giá < EMA50)")
                    print(f"     - M1 Signal: {m1_signal} ({signal_type})")
                    print(f"     - ADX(M5): {adx_m5_current:.2f} (Xu hướng mạnh)")
                    if ENABLE_ATR_FILTER and atr_pips is not None:
                        print(f"     - ATR: {atr_pips:.2f} pips (Biến động phù hợp)")
                    print(f"     - Spread: {spread_points:.1f} points ({spread_points/10:.1f} pips)")
                    print(f"     - Volume: {VOLUME}")
                    print(f"  ❌ [LÝ DO KHÔNG VÀO LỆNH]:")
                    print(f"     - {cooldown_message}")
                    print(f"     - Chờ đủ {LOSS_COOLDOWN_MINUTES} phút sau lệnh thua cuối cùng")
                    print(f"  {'='*65}\n")
                else:
                    send_order(mt5.ORDER_TYPE_SELL, VOLUME, df_m1=df_m1, df_m5=df_m5, m5_trend=m5_trend, m1_signal=m1_signal, signal_type=signal_type, adx_m5_current=adx_m5_current, atr_pips=atr_pips, spread_points=spread_points)
            
            else:
                print(f"\n  ⚠️ [QUYẾT ĐỊNH] KHÔNG VÀO LỆNH - CHƯA ĐỦ ĐIỀU KIỆN:")
                print(f"  {'='*65}")
                print(f"  📊 [PHÂN TÍCH CHI TIẾT]")
                print(f"     - M5 Trend: {m5_trend}")
                print(f"     - M1 Signal: {m1_signal} ({signal_type})")
                print(f"     - ADX(M5): {adx_m5_current:.2f}")
                if atr_pips is not None:
                    print(f"     - ATR: {atr_pips:.2f} pips")
                print(f"     - Spread: {spread_points:.1f} points ({spread_points/10:.1f} pips)")
                print(f"  ❌ [LÝ DO KHÔNG VÀO LỆNH]:")
                if m5_trend == 'SIDEWAYS':
                    print(f"     - M5 Trend: {m5_trend} (Không rõ xu hướng - Giá ≈ EMA50)")
                elif m1_signal == 'NONE':
                    print(f"     - M1 Signal: {m1_signal} (Chưa có retest hoặc breakout)")
                    if m1_retest_signal == 'NONE':
                        # Lấy lại thông tin để log chi tiết
                        ema_20_m1 = calculate_ema(df_m1, EMA_M1)
                        ema_20_current = ema_20_m1.iloc[-1]
                        distance_points = abs(current_price - ema_20_current) / point
                        current_candle = df_m1.iloc[-1]
                        is_green = current_candle['close'] > current_candle['open']
                        is_red = current_candle['close'] < current_candle['open']
                        
                        print(f"       → Retest: Không thỏa mãn")
                        print(f"         * Khoảng cách: {distance_points/10:.1f} pips (Yêu cầu: {RETEST_DISTANCE_MIN/10}-{RETEST_DISTANCE_MAX/10} pips)")
                        if not (RETEST_DISTANCE_MIN <= distance_points <= RETEST_DISTANCE_MAX):
                             print(f"         * LÝ DO: Giá ngoài vùng retest")
                        else:
                             if m5_trend == 'BUY' and not (is_green or current_price > ema_20_current):
                                 print(f"         * LÝ DO: Trend BUY nhưng nến ĐỎ (đang giảm) - Cần nến XANH")
                             elif m5_trend == 'SELL' and not (is_red or current_price < ema_20_current):
                                 print(f"         * LÝ DO: Trend SELL nhưng nến XANH (đang tăng) - Cần nến ĐỎ")
                    
                    if m1_breakout_signal == 'NONE':
                        print(f"       → Breakout: Không có hoặc không đủ điều kiện (ADX, Volume, Spread)")
                elif m1_signal == 'BUY' and m5_trend != 'BUY':
                    print(f"     - M1 Signal: {m1_signal} nhưng M5 Trend: {m5_trend} (Không đồng ý)")
                    print(f"       → Cần M5 Trend = BUY để vào lệnh BUY")
                elif m1_signal == 'SELL' and m5_trend != 'SELL':
                    print(f"     - M1 Signal: {m1_signal} nhưng M5 Trend: {m5_trend} (Không đồng ý)")
                    print(f"       → Cần M5 Trend = SELL để vào lệnh SELL")
                print(f"  {'='*65}\n")
        else:
            print(f"\n  ⏸️ [QUYẾT ĐỊNH] KHÔNG VÀO LỆNH - ĐANG CÓ LỆNH MỞ:")
            print(f"  {'='*65}")
            print(f"  📊 [TRẠNG THÁI]")
            print(f"     - Số lệnh đang mở: {open_positions}")
            print(f"     - M5 Trend: {m5_trend}")
            print(f"     - M1 Signal: {m1_signal} ({signal_type})")
            print(f"  ❌ [LÝ DO KHÔNG VÀO LỆNH]:")
            print(f"     - Bot chỉ mở 1 lệnh tại một thời điểm")
            print(f"     - Chờ đóng lệnh hiện tại trước khi vào lệnh mới")
            print(f"  {'='*65}\n")
        
        print(f"{'='*70}\n")
            
        # 4. QUẢN LÝ LỆNH (CHẠY MỖI VÒNG LẶP ĐỂ BẮT BE/TS KỊP THỜI)
        manage_positions()
        
        # 5. ĐIỀU CHỈNH THỜI GIAN NGỦ ĐỂ ĐẠT CHU KỲ 10 GIÂY (M1 cần check thường xuyên hơn)
        elapsed_time = time.time() - start_time
        sleep_time = 2 - elapsed_time  # Check mỗi 10 giây cho M1
        sleep_time = 1
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