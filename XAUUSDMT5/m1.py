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
# Chiến thuật M1: "BÁM THEO H1 – ĂN 5–10 PHÚT"
EMA_H1 = 50  # EMA50 trên H1 để xác định trend
EMA_M1 = 20  # EMA20 trên M1 để tìm điểm retest
ATR_PERIOD = 14
ADX_PERIOD = 14  # Chu kỳ tính ADX
ADX_MIN_THRESHOLD = 25  # ADX tối thiểu để giao dịch (tránh thị trường đi ngang)

# Lọc ATR - chỉ vào lệnh khi ATR đủ lớn (thị trường có biến động)
ENABLE_ATR_FILTER = True  # Bật/tắt lọc ATR
ATR_MIN_THRESHOLD = 100    # ATR tối thiểu (pips) để vào lệnh

# Thông số Quản lý Lệnh (Tính bằng points, 10 points = 1 pip)
# Chiến thuật M1: SL/TP theo nến M1
SL_ATR_MULTIPLIER = 1.5  # SL = ATR(M1) × 1.5
TP_ATR_MULTIPLIER = 2.0  # TP = ATR(M1) × 2.0
SL_POINTS_MIN = 50   # SL tối thiểu: 5 pips (50 points) - bảo vệ
SL_POINTS_MAX = 50000  # SL tối đa: 5000 pips (50000 points) - cho phép SL lớn theo ATR
TP_POINTS_MIN = 80   # TP tối thiểu: 8 pips (80 points) - bảo vệ
TP_POINTS_MAX = 50000  # TP tối đa: 5000 pips (50000 points) - cho phép TP lớn theo ATR

# Fix SL theo giá trị USD cố định
ENABLE_FIXED_SL_USD = False  # Bật/tắt fix SL theo USD
FIXED_SL_USD = 5.0  # SL cố định tính bằng USD (ví dụ: 5 USD)
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

# Tạm dừng sau khi gửi lệnh lỗi nhiều lần liên tiếp
ENABLE_ERROR_COOLDOWN = True         # Bật/tắt tạm dừng sau lỗi gửi lệnh
ERROR_COOLDOWN_COUNT = 5            # Số lần lỗi liên tiếp để kích hoạt cooldown
ERROR_COOLDOWN_MINUTES = 1          # Thời gian tạm dừng sau khi lỗi (phút)

# Biến đếm lỗi (sẽ được reset khi thành công)
error_count = 0                     # Số lần lỗi liên tiếp hiện tại
error_cooldown_start = None         # Thời gian bắt đầu cooldown (None nếu không có)

# Telegram Bot Configuration
 # Chat ID sẽ được lấy từ JSON config hoặc để None nếu không dùng Telegram
TELEGRAM_TOKEN = "6398751744:"         # Token của Telegram Bot (lấy từ @BotFather)
                                # Ví dụ: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
                                # Hướng dẫn: https://core.telegram.org/bots/tutorial

CHAT_ID = "1887610382222"  # ID của chat hoặc nhóm Telegram để gửi thông báo
# Khoảng cách retest EMA20 trên M1 (points)
# Giá chạm EMA20 hoặc dưới 3-6 pip (30-60 points)
RETEST_DISTANCE_MAX = 60  # Tối đa 6 pips (60 points) từ EMA20

# Chiến thuật BREAKOUT (khi giá không retest)
ADX_BREAKOUT_THRESHOLD = 28  # ADX > 28 để breakout
BREAKOUT_DISTANCE_MIN = 100  # Khoảng cách tối thiểu từ EMA20: 10 pips (100 points)
BREAKOUT_DISTANCE_MAX = 200  # Khoảng cách tối đa từ EMA20: 20 pips (200 points)
# Kỹ thuật "Sniper Entry" - Momentum Confirmation
ENABLE_MOMENTUM_CONFIRMATION = True  # Bật/tắt kỹ thuật "Momentum Confirmation"
MOMENTUM_BUFFER_POINTS = 20  # Buffer để xác nhận phá vỡ (2 pips = 20 points)

# Spread Filter
MAX_SPREAD_POINTS = 200  # Spread tối đa cho phép (200 points = 20 pips)

# --- NEW FILTERS (ANTI-CRASH) ---
# 1. Bearish Momentum Filter (Chống nến đỏ dài)
ENABLE_BEARISH_MOMENTUM_FILTER = True
MOMENTUM_BODY_RATIO = 2.0  # Thân nến > 2 lần trung bình

# 2. Retest Distance Filter (Chống xa bờ)
MAX_RETEST_DISTANCE_POINTS = 50  # 5 pips (50 points)

# 3. Structure Filter (Chống phá đáy)
ENABLE_STRUCTURE_FILTER = True
STRUCTURE_LOOKBACK = 10  # Số nến để tìm đáy gần nhất
# ==============================================================================
# 2. HÀM THIẾT LẬP LOGGING
# ==============================================================================

def setup_logging():
    """
    Thiết lập logging để ghi log vào file theo tên bot.
    File log sẽ được tạo trong thư mục XAUUSDMT5/logs/
    """
    # Tạo thư mục logs nếu chưa có
    log_dir = "XAUUSDMT5/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Lấy tên file bot (ví dụ: m1_gpt.py -> m1_gpt)
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

def load_config(filename="XAUUSDMT5/mt5_account1.json"):
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
        SYMBOL = config.get("SYMBOL", "XAUUSD") 
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
    
    Chiến thuật: "BÁM THEO H1 – ĂN 5–10 PHÚT"
    - Giá > EMA50 → CHỈ BUY
    - Giá < EMA50 → CHỈ SELL
    
    Returns:
        'BUY', 'SELL', hoặc 'SIDEWAYS'
    """
    print("  📊 [H1 TREND] Kiểm tra xu hướng H1 bằng EMA50...")
    
    df_h1 = get_rates(mt5.TIMEFRAME_H1)
    if df_h1 is None or len(df_h1) < EMA_H1:
        print(f"    [H1] ❌ Không đủ dữ liệu để tính EMA50")
        return 'SIDEWAYS'
    
    ema_50_h1 = calculate_ema(df_h1, EMA_H1).iloc[-1]
    close_h1 = df_h1['close'].iloc[-1]
    
    print(f"    [H1] Giá: {close_h1:.5f} | EMA50: {ema_50_h1:.5f}")
    
    if close_h1 > ema_50_h1:
        print(f"    [H1] ✅ XU HƯỚNG MUA (Giá > EMA50) → CHỈ BUY")
        return 'BUY'
    elif close_h1 < ema_50_h1:
        print(f"    [H1] ✅ XU HƯỚNG BÁN (Giá < EMA50) → CHỈ SELL")
        return 'SELL'
    else:
        print(f"    [H1] ⚠️ SIDEWAYS (Giá ≈ EMA50)")
        return 'SIDEWAYS'

def check_m1_retest_ema20(df_m1, h1_trend):
    """
    Kiểm tra điểm vào ở M1 khi giá RETEST lại EMA20
    
    Chiến thuật: "BÁM THEO H1 – ĂN 5–10 PHÚT"
    - Trend BUY → chờ giá M1 chạm EMA20 (hoặc dưới 3–6 pip) → BUY
    - Trend SELL → chờ giá M1 chạm EMA20 → SELL
    
    Args:
        df_m1: DataFrame M1
        h1_trend: 'BUY', 'SELL', hoặc 'SIDEWAYS'
        
    Returns:
        'BUY', 'SELL', hoặc 'NONE'
    """
    if h1_trend == 'SIDEWAYS':
        print("  📈 [M1 RETEST] H1 trend là SIDEWAYS → Không có tín hiệu")
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
    
    print(f"  📈 [M1 RETEST] Giá hiện tại: {current_price:.5f} | EMA20: {ema_20_current:.5f}")
    print(f"    Khoảng cách: {distance_points:.1f} points ({distance_points/10:.1f} pips)")
    
    if h1_trend == 'BUY':
        # Trend BUY → chờ giá M1 chạm EMA20 hoặc dưới 3–6 pip
        if current_price <= ema_20_current + (RETEST_DISTANCE_MAX * point):
            print(f"    ✅ [M1 RETEST] Giá đang retest EMA20 từ dưới lên (BUY signal)")
            return 'BUY'
        else:
            print(f"    ⚠️ [M1 RETEST] Giá còn xa EMA20 ({distance_points/10:.1f} pips) - Chờ retest")
            return 'NONE'
    
    elif h1_trend == 'SELL':
        # Trend SELL → chờ giá M1 chạm EMA20 hoặc trên 3–6 pip
        if current_price >= ema_20_current - (RETEST_DISTANCE_MAX * point):
            print(f"    ✅ [M1 RETEST] Giá đang retest EMA20 từ trên xuống (SELL signal)")
            return 'SELL'
        else:
            print(f"    ⚠️ [M1 RETEST] Giá còn xa EMA20 ({distance_points/10:.1f} pips) - Chờ retest")
            return 'NONE'
    
    return 'NONE'

def check_m1_breakout(df_m1, h1_trend, adx_current):
    """
    Kiểm tra điểm vào BREAKOUT khi giá không retest EMA20
    
    Chiến thuật: ENTRY BREAKOUT (KHI GIÁ KHÔNG RETEST)
    - ADX > 28
    - H1 trend SELL → Giá M1 phá đáy gần nhất trong khi còn cách EMA20 > 10–20 point
    - H1 trend BUY → Giá M1 phá đỉnh gần nhất trong khi còn cách EMA20 > 10–20 point
    - Không cần retest → Bot follow momentum
    
    Args:
        df_m1: DataFrame M1
        h1_trend: 'BUY', 'SELL', hoặc 'SIDEWAYS'
        adx_current: Giá trị ADX hiện tại
        
    Returns:
        'BUY', 'SELL', hoặc 'NONE'
    """
    if h1_trend == 'SIDEWAYS':
        return 'NONE'
    
    # Kiểm tra ADX > 28
    if adx_current <= ADX_BREAKOUT_THRESHOLD:
        return 'NONE'
    
    if len(df_m1) < EMA_M1 + 20:  # Cần ít nhất 20 nến để tìm đáy/đỉnh
        return 'NONE'
    
    # Tính EMA20 trên M1
    ema_20_m1 = calculate_ema(df_m1, EMA_M1)
    ema_20_current = ema_20_m1.iloc[-1]
    
    # Lấy giá hiện tại
    tick = mt5.symbol_info_tick(SYMBOL)
    current_price = tick.bid if h1_trend == 'SELL' else tick.ask
    
    point = get_symbol_info()
    if point is None:
        return 'NONE'
    
    # Tính khoảng cách từ giá hiện tại đến EMA20 (points)
    if h1_trend == 'SELL':
        distance_points = (ema_20_current - current_price) / point  # Khoảng cách từ giá đến EMA20 (phía trên)
    else:  # BUY
        distance_points = (current_price - ema_20_current) / point  # Khoảng cách từ giá đến EMA20 (phía dưới)
    
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
    
    if h1_trend == 'SELL':
        # SELL: Giá phá đáy gần nhất
        if current_price < recent_lows:
            print(f"    ✅ [M1 BREAKOUT] Giá phá đáy gần nhất ({recent_lows:.5f}) → SELL BREAKOUT")
            print(f"       - ADX: {adx_current:.2f} > {ADX_BREAKOUT_THRESHOLD} (Momentum mạnh)")
            print(f"       - Khoảng cách EMA20: {distance_points/10:.1f} pips (10-20 pips)")
            return 'SELL'
    
    elif h1_trend == 'BUY':
        # BUY: Giá phá đỉnh gần nhất
        if current_price > recent_highs:
            print(f"    ✅ [M1 BREAKOUT] Giá phá đỉnh gần nhất ({recent_highs:.5f}) → BUY BREAKOUT")
            print(f"       - ADX: {adx_current:.2f} > {ADX_BREAKOUT_THRESHOLD} (Momentum mạnh)")
            print(f"       - Khoảng cách EMA20: {distance_points/10:.1f} pips (10-20 pips)")
            return 'BUY'
    
    return 'NONE'

# ==============================================================================
# 5.5. HÀM KIỂM TRA "SNIPER ENTRY" - KỸ THUẬT MOMENTUM CONFIRMATION
# ==============================================================================

def check_momentum_confirmation(df_m1, signal_direction):
    """
    Kỹ thuật "Phá vỡ Đỉnh/Đáy" (Momentum Confirmation) - Tránh false breakout
    """
    if not ENABLE_MOMENTUM_CONFIRMATION:
        return True, "Momentum Confirmation đã tắt"
    
    if len(df_m1) < 2:
        return False, "Không đủ dữ liệu"
    
    signal_candle = df_m1.iloc[-2]  # Nến trước đó (đã đóng)
    point = get_symbol_info()
    if point is None: return False, "Không thể lấy point"
    
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None: return False, "Không thể lấy giá hiện tại"
    
    current_ask = tick.ask
    current_bid = tick.bid
    signal_high = signal_candle['high']
    signal_low = signal_candle['low']
    buffer = MOMENTUM_BUFFER_POINTS * point
    
    if signal_direction == 'BUY':
        confirmation_price = signal_high + buffer
        if current_ask > confirmation_price:
            return True, f"✅ Momentum Confirmed: Giá ({current_ask:.5f}) > Signal High ({signal_high:.5f}) + Buffer"
        else:
            distance = confirmation_price - current_ask
            distance_pips = (distance / point) / 10
            return False, f"⏳ Chờ Momentum BUY: Cần phá {confirmation_price:.5f} (Còn {distance_pips:.1f} pips)"
    
    elif signal_direction == 'SELL':
        confirmation_price = signal_low - buffer
        if current_bid < confirmation_price:
            return True, f"✅ Momentum Confirmed: Giá ({current_bid:.5f}) < Signal Low ({signal_low:.5f}) - Buffer"
        else:
            distance = current_bid - confirmation_price
            distance_pips = (distance / point) / 10
            return False, f"⏳ Chờ Momentum SELL: Cần phá {confirmation_price:.5f} (Còn {distance_pips:.1f} pips)"
    
    return False, "Signal direction không hợp lệ"

# ==============================================================================
# 5.6. CÁC BỘ LỌC BỔ SUNG (ANTI-CRASH FILTERS)
# ==============================================================================

def check_bearish_momentum(df_m1):
    """Kiểm tra xem nến vừa đóng có phải là nến giảm mạnh (Bearish Momentum) hay không."""
    if not ENABLE_BEARISH_MOMENTUM_FILTER: return False, "Filter OFF"
    if len(df_m1) < 12: return False, "Not enough data"
        
    last_candle = df_m1.iloc[-2]
    if last_candle['close'] >= last_candle['open']: return False, "Bullish candle"
        
    current_body = abs(last_candle['close'] - last_candle['open'])
    prev_candles = df_m1.iloc[-12:-2]
    avg_body = (prev_candles['close'] - prev_candles['open']).abs().mean()
    
    if current_body > MOMENTUM_BODY_RATIO * avg_body:
        return True, f"⚠️ Bearish Momentum: Body {current_body:.5f} > {MOMENTUM_BODY_RATIO}x Avg ({avg_body:.5f})"
    return False, "Normal momentum"

def check_structure_break(df_m1, direction):
    """Kiểm tra xem giá có đang phá vỡ cấu trúc không."""
    if not ENABLE_STRUCTURE_FILTER: return False, "Filter OFF"
    if len(df_m1) < STRUCTURE_LOOKBACK + 2: return False, "Not enough data"
        
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None: return False, "No tick data"
    current_price = tick.bid if direction == 'BUY' else tick.ask
    
    past_candles = df_m1.iloc[-(STRUCTURE_LOOKBACK+2):-2]
    
    if direction == 'BUY':
        recent_low = past_candles['low'].min()
        if current_price < recent_low:
             return True, f"⚠️ Structure Break: Price {current_price:.5f} < Recent Low {recent_low:.5f}"
    elif direction == 'SELL':
        recent_high = past_candles['high'].max()
        if current_price > recent_high:
            return True, f"⚠️ Structure Break: Price {current_price:.5f} > Recent High {recent_high:.5f}"
            
    return False, "Structure OK"

# ==============================================================================
# 6. HÀM KIỂM TRA COOLDOWN SAU LỆNH THUA
# ==============================================================================

def check_last_loss_cooldown():
    """
    Kiểm tra cooldown sau lệnh thua với 2 mode:
    - Mode 1: Nếu lệnh cuối cùng thua → nghỉ LOSS_COOLDOWN_MINUTES phút
    - Mode 2: Nếu 2 lệnh cuối cùng đều thua → nghỉ LOSS_COOLDOWN_MINUTES phút
    
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
        sl_points = sl_pips_fixed * 10  # Chuyển pips sang points (1 pip = 10 points)
        sl_pips_limited = sl_pips_fixed
        
        print(f"  📊 [ORDER] SL CỐ ĐỊNH: {FIXED_SL_USD} USD = {sl_pips_fixed:.1f} pips ({sl_points:.0f} points)")
        
        # Tính TP vẫn dựa trên ATR (nếu có) hoặc dùng giá trị mặc định
        if df_m1 is not None:
            atr_pips = calculate_atr_from_m1(df_m1)
            if atr_pips is not None:
                tp_pips = atr_pips * TP_ATR_MULTIPLIER
                tp_points = tp_pips * 10
                tp_points = max(TP_POINTS_MIN, min(tp_points, TP_POINTS_MAX))
                tp_pips_limited = tp_points / 10
                print(f"  📊 [ORDER] TP: {tp_pips_limited:.1f} pips (ATR×{TP_ATR_MULTIPLIER}, giới hạn {TP_POINTS_MIN/10}-{TP_POINTS_MAX/10} pips)")
            else:
                tp_points = (TP_POINTS_MIN + TP_POINTS_MAX) // 2
                tp_pips_limited = tp_points / 10
                print(f"  ⚠️ [ORDER] Không tính được ATR cho TP, dùng giá trị mặc định: TP: {tp_pips_limited:.1f} pips")
        else:
            tp_points = (TP_POINTS_MIN + TP_POINTS_MAX) // 2
            tp_pips_limited = tp_points / 10
            print(f"  ⚠️ [ORDER] Không có dữ liệu M1 cho TP, dùng giá trị mặc định: TP: {tp_pips_limited:.1f} pips")
    else:
        # Tính SL và TP theo ATR của nến M1 (logic cũ)
        # ATR đã được tính trực tiếp trong pips từ calculate_atr_from_m1()
        if df_m1 is not None:
            atr_pips = calculate_atr_from_m1(df_m1)
            if atr_pips is not None:
                # ATR đã là pips, tính SL và TP trực tiếp
                sl_pips = atr_pips * SL_ATR_MULTIPLIER
                tp_pips = atr_pips * TP_ATR_MULTIPLIER
                
                # Chuyển pips sang points (1 pip = 10 points cho XAUUSD)
                sl_points = sl_pips * 10
                tp_points = tp_pips * 10
                
                # Giới hạn SL/TP trong khoảng min-max (đã là points)
                sl_points = max(SL_POINTS_MIN, min(sl_points, SL_POINTS_MAX))
                tp_points = max(TP_POINTS_MIN, min(tp_points, TP_POINTS_MAX))
                
                # Tính lại pips sau khi giới hạn (để hiển thị đúng)
                sl_pips_limited = sl_points / 10
                tp_pips_limited = tp_points / 10
                
                print(f"  📊 [ORDER] ATR(M1): {atr_pips:.2f} pips → SL: {sl_pips_limited:.1f} pips (ATR×{SL_ATR_MULTIPLIER}, giới hạn {SL_POINTS_MIN/10}-{SL_POINTS_MAX/10} pips), TP: {tp_pips_limited:.1f} pips (ATR×{TP_ATR_MULTIPLIER}, giới hạn {TP_POINTS_MIN/10}-{TP_POINTS_MAX/10} pips)")
            else:
                # Fallback: Dùng giá trị trung bình nếu không tính được ATR
                sl_points = (SL_POINTS_MIN + SL_POINTS_MAX) // 2
                tp_points = (TP_POINTS_MIN + TP_POINTS_MAX) // 2
                print(f"  ⚠️ [ORDER] Không tính được ATR, dùng giá trị mặc định: SL: {sl_points/10:.1f} pips, TP: {tp_points/10:.1f} pips")
        else:
            # Fallback: Dùng giá trị trung bình nếu không có df_m1
            sl_points = (SL_POINTS_MIN + SL_POINTS_MAX) // 2
            tp_points = (TP_POINTS_MIN + TP_POINTS_MAX) // 2
            print(f"  ⚠️ [ORDER] Không có dữ liệu M1, dùng giá trị mặc định: SL: {sl_points/10:.1f} pips, TP: {tp_points/10:.1f} pips")
    
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
        
        # Ghi log thành công
        trade_direction = "🟢 BUY" if trade_type == mt5.ORDER_TYPE_BUY else "🔴 SELL"
        atr_display = f"{atr_pips:.2f}" if atr_pips is not None else "N/A"
        sl_atr_display = f"{sl_pips_limited:.1f}" if sl_pips_limited is not None else f"{sl_points/10:.1f}"
        tp_atr_display = f"{tp_pips_limited:.1f}" if tp_pips_limited is not None else f"{tp_points/10:.1f}"
        
        logger.info("=" * 70)
        logger.info(f"✅ VÀO LỆNH THÀNH CÔNG: {trade_direction}")
        logger.info(f"Order ID: {result.order}")
        logger.info(f"Symbol: {SYMBOL}")
        logger.info(f"Entry: {price:.5f}")
        logger.info(f"SL: {sl:.5f} ({sl_points/10:.1f} pips)")
        logger.info(f"TP: {tp:.5f} ({tp_points/10:.1f} pips)")
        logger.info(f"Volume: {volume}")
        logger.info(f"ATR: {atr_display} pips (SL: {sl_atr_display}p, TP: {tp_atr_display}p)")
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
        spread_points = (current_ask - current_price) / point
        print(f"  💰 Giá hiện tại: BID={current_price:.5f} | ASK={current_ask:.5f} | Spread={spread_points:.1f} points")
        
        # --- KIỂM TRA TÍN HIỆU VÀ LỌC ---
        print(f"\n  🔍 [KIỂM TRA TÍN HIỆU] Bắt đầu phân tích...")
        
        # 1. Xác định hướng H1 bằng EMA50
        print(f"\n  ┌─ [BƯỚC 1] Kiểm tra xu hướng H1 (EMA50)")
        h1_trend = check_h1_trend()
        print(f"  └─ [BƯỚC 1] Kết quả: {h1_trend}")
        
        # 2. Kiểm tra ADX (Bộ lọc tránh thị trường đi ngang)
        print(f"\n  ┌─ [BƯỚC 2] Kiểm tra ADX (Tránh thị trường đi ngang)")
        adx_values = calculate_adx(df_m1, ADX_PERIOD)
        adx_current = adx_values.iloc[-1] if not adx_values.empty else 0
        print(f"    ADX hiện tại: {adx_current:.2f} (Ngưỡng tối thiểu: {ADX_MIN_THRESHOLD}, Breakout: {ADX_BREAKOUT_THRESHOLD})")
        
        if adx_current >= ADX_MIN_THRESHOLD:
            adx_ok = True
            print(f"    ✅ [ADX] XU HƯỚNG MẠNH (ADX={adx_current:.2f} ≥ {ADX_MIN_THRESHOLD}) - Có thể giao dịch")
        else:
            adx_ok = False
            print(f"    ⚠️ [ADX] THỊ TRƯỜNG ĐI NGANG (ADX={adx_current:.2f} < {ADX_MIN_THRESHOLD}) - Tránh giao dịch")
        print(f"  └─ [BƯỚC 2] Kết quả: {'OK' if adx_ok else 'BLOCKED'}")
        
        # 2.5. Kiểm tra ATR (Bộ lọc biến động thị trường)
        atr_pips = None
        atr_ok = True  # Mặc định OK nếu không bật filter
        if ENABLE_ATR_FILTER:
            print(f"\n  ┌─ [BƯỚC 2.5] Kiểm tra ATR (Lọc biến động thị trường)")
            atr_pips = calculate_atr_from_m1(df_m1)
            if atr_pips is not None:
                print(f"    ATR hiện tại: {atr_pips:.2f} pips (Ngưỡng tối thiểu: {ATR_MIN_THRESHOLD} pips)")
                if atr_pips >= ATR_MIN_THRESHOLD:
                    atr_ok = True
                    print(f"    ✅ [ATR] BIẾN ĐỘNG ĐỦ LỚN (ATR={atr_pips:.2f} ≥ {ATR_MIN_THRESHOLD} pips) - Có thể giao dịch")
                else:
                    atr_ok = False
                    print(f"    ⚠️ [ATR] BIẾN ĐỘNG QUÁ NHỎ (ATR={atr_pips:.2f} < {ATR_MIN_THRESHOLD} pips) - Tránh giao dịch")
            else:
                atr_ok = False
                print(f"    ⚠️ [ATR] Không tính được ATR - Tránh giao dịch")
            print(f"  └─ [BƯỚC 2.5] Kết quả: {'OK' if atr_ok else 'BLOCKED'}")

        # 3. Kiểm tra điểm vào ở M1: RETEST hoặc BREAKOUT
        print(f"\n  ┌─ [BƯỚC 3] Kiểm tra tín hiệu M1 (Retest EMA20 hoặc Breakout)")
        
        # Ưu tiên 1: Kiểm tra RETEST EMA20
        m1_retest_signal = check_m1_retest_ema20(df_m1, h1_trend)
        
        # Ưu tiên 2: Nếu không có retest, kiểm tra BREAKOUT (khi ADX > 28)
        m1_breakout_signal = 'NONE'
        if m1_retest_signal == 'NONE' and adx_current > ADX_BREAKOUT_THRESHOLD:
            m1_breakout_signal = check_m1_breakout(df_m1, h1_trend, adx_current)
        
        # Kết hợp tín hiệu: Ưu tiên retest, nếu không có thì dùng breakout
        m1_signal = m1_retest_signal if m1_retest_signal != 'NONE' else m1_breakout_signal
        
        if m1_retest_signal != 'NONE':
            print(f"    ✅ [M1 SIGNAL] RETEST EMA20: {m1_retest_signal}")
        elif m1_breakout_signal != 'NONE':
            print(f"    ✅ [M1 SIGNAL] BREAKOUT: {m1_breakout_signal} (ADX={adx_current:.2f} > {ADX_BREAKOUT_THRESHOLD})")
        else:
            print(f"    ⚠️ [M1 SIGNAL] Chưa có tín hiệu (Retest: {m1_retest_signal}, Breakout: {m1_breakout_signal})")
        
        print(f"  └─ [BƯỚC 3] Kết quả: {m1_signal}")

        # 4. Kiểm tra vị thế đang mở (chỉ đếm lệnh của cặp XAUUSD)
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions is None:
            open_positions = 0
        else:
            # Chỉ đếm lệnh có magic number của bot này
            open_positions = len([pos for pos in positions if pos.magic == MAGIC])
        print(f"\n  📋 [TRẠNG THÁI] Số lệnh đang mở ({SYMBOL}): {open_positions}")
        
        signal_type = "RETEST" if m1_retest_signal != 'NONE' else ("BREAKOUT" if m1_breakout_signal != 'NONE' else "NONE")
        print(f"\n  📊 [TÓM TẮT] H1 Trend={h1_trend} | M1 Signal={m1_signal} ({signal_type}) | ADX={adx_current:.2f}")

        if open_positions <2:
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
            
            # ⚠️ QUAN TRỌNG: Kiểm tra ADX và ATR trước khi vào lệnh
            # - RETEST: ADX >= 25 (ADX_MIN_THRESHOLD)
            # - BREAKOUT: ADX > 28 (ADX_BREAKOUT_THRESHOLD) - đã check trong check_m1_breakout
            # - ATR: >= ATR_MIN_THRESHOLD (nếu bật ENABLE_ATR_FILTER)
            if signal_type == "RETEST" and not adx_ok:
                print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI ADX FILTER:")
                print(f"     - ADX: {adx_current:.2f} < {ADX_MIN_THRESHOLD} (Thị trường đi ngang)")
                print(f"     - Không giao dịch khi thị trường đi ngang để tránh false signals")
            elif ENABLE_ATR_FILTER and not atr_ok:
                print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI ATR FILTER:")
                atr_display = f"{atr_pips:.2f}" if atr_pips is not None else "N/A"
                print(f"     - ATR: {atr_display} pips < {ATR_MIN_THRESHOLD} pips (Biến động quá nhỏ)")
                print(f"     - Không giao dịch khi biến động thị trường quá nhỏ")
            elif m1_signal == 'BUY' and h1_trend == 'BUY':
                print(f"  ✅ [QUYẾT ĐỊNH] 🚀 TÍN HIỆU MUA MẠNH!")
                print(f"     - H1 Trend: {h1_trend} (Giá > EMA50)")
                print(f"     - M1 Signal: {m1_signal} ({signal_type})")
                if signal_type == "RETEST":
                    print(f"       → Giá retest EMA20 từ dưới lên")
                elif signal_type == "BREAKOUT":
                    print(f"       → Giá phá đỉnh gần nhất (Breakout momentum)")
                print(f"     - ADX: {adx_current:.2f} (Xu hướng mạnh)")
                if ENABLE_ATR_FILTER and atr_pips is not None:
                    print(f"     - ATR: {atr_pips:.2f} pips (Biến động đủ lớn)")
                print(f"     - Volume: {VOLUME}")
                
                # Kiểm tra cooldown sau lệnh thua (chỉ check khi có tín hiệu)
                print(f"\n  ┌─ [COOLDOWN] Kiểm tra cooldown sau lệnh thua")
                cooldown_allowed, cooldown_message = check_last_loss_cooldown()
                print(f"    {cooldown_message}")
                print(f"  └─ [COOLDOWN] Kết quả: {'OK' if cooldown_allowed else 'BLOCKED'}")
                
                if not cooldown_allowed:
                    print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI COOLDOWN SAU LỆNH THUA:")
                    print(f"     - {cooldown_message}")
                    print(f"     - Chờ đủ {LOSS_COOLDOWN_MINUTES} phút sau lệnh thua cuối cùng")
                else:
                    # --- NEW FILTERS CHECK (ANTI-CRASH) ---
                    is_bearish_momentum, bearish_msg = check_bearish_momentum(df_m1)
                    
                    ema_20_current = calculate_ema(df_m1, EMA_M1).iloc[-1]
                    dist_from_ema = (ema_20_current - current_price) / point
                    is_too_far = dist_from_ema > MAX_RETEST_DISTANCE_POINTS
                    
                    is_structure_break, structure_msg = check_structure_break(df_m1, 'BUY')
                    
                    if spread_points > MAX_SPREAD_POINTS:
                        print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI SPREAD FILTER:")
                        print(f"     - Spread: {spread_points:.1f} > {MAX_SPREAD_POINTS}")
                    elif is_bearish_momentum:
                        print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI BEARISH MOMENTUM:")
                        print(f"     - {bearish_msg}")
                    elif is_too_far:
                        print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI RETEST DISTANCE:")
                        print(f"     - Distance: {dist_from_ema:.1f} > {MAX_RETEST_DISTANCE_POINTS}")
                    elif is_structure_break:
                        print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI STRUCTURE BREAK:")
                        print(f"     - {structure_msg}")
                    else:
                        # --- MOMENTUM CONFIRMATION ---
                        print(f"\n  ┌─ [CONFIRMATION] Kiểm tra Momentum (Tránh bắt dao rơi)")
                        confirmed, confirm_msg = check_momentum_confirmation(df_m1, 'BUY')
                        print(f"    {confirm_msg}")
                        
                        if confirmed:
                            print(f"  └─ [CONFIRMATION] Kết quả: ✅ ĐÃ XÁC NHẬN -> VÀO LỆNH")
                            send_order(mt5.ORDER_TYPE_BUY, VOLUME, df_m1)
                        else:
                            print(f"  └─ [CONFIRMATION] Kết quả: ⏳ CHỜ XÁC NHẬN")
                
            elif m1_signal == 'SELL' and h1_trend == 'SELL':
                print(f"  ✅ [QUYẾT ĐỊNH] 🔻 TÍN HIỆU BÁN MẠNH!")
                print(f"     - H1 Trend: {h1_trend} (Giá < EMA50)")
                print(f"     - M1 Signal: {m1_signal} ({signal_type})")
                if signal_type == "RETEST":
                    print(f"       → Giá retest EMA20 từ trên xuống")
                elif signal_type == "BREAKOUT":
                    print(f"       → Giá phá đáy gần nhất (Breakout momentum)")
                print(f"     - ADX: {adx_current:.2f} (Xu hướng mạnh)")
                if ENABLE_ATR_FILTER and atr_pips is not None:
                    print(f"     - ATR: {atr_pips:.2f} pips (Biến động đủ lớn)")
                print(f"     - Volume: {VOLUME}")
                
                # Kiểm tra cooldown sau lệnh thua (chỉ check khi có tín hiệu)
                print(f"\n  ┌─ [COOLDOWN] Kiểm tra cooldown sau lệnh thua")
                cooldown_allowed, cooldown_message = check_last_loss_cooldown()
                print(f"    {cooldown_message}")
                print(f"  └─ [COOLDOWN] Kết quả: {'OK' if cooldown_allowed else 'BLOCKED'}")
                
                if not cooldown_allowed:
                    print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI COOLDOWN SAU LỆNH THUA:")
                    print(f"     - {cooldown_message}")
                    print(f"     - Chờ đủ {LOSS_COOLDOWN_MINUTES} phút sau lệnh thua cuối cùng")
                else:
                    if spread_points > MAX_SPREAD_POINTS:
                        print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI SPREAD FILTER:")
                        print(f"     - Spread: {spread_points:.1f} > {MAX_SPREAD_POINTS}")
                    else:
                        # --- MOMENTUM CONFIRMATION ---
                        print(f"\n  ┌─ [CONFIRMATION] Kiểm tra Momentum")
                        confirmed, confirm_msg = check_momentum_confirmation(df_m1, 'SELL')
                        print(f"    {confirm_msg}")
                        
                        if confirmed:
                            print(f"  └─ [CONFIRMATION] Kết quả: ✅ ĐÃ XÁC NHẬN -> VÀO LỆNH")
                            send_order(mt5.ORDER_TYPE_SELL, VOLUME, df_m1)
                        else:
                            print(f"  └─ [CONFIRMATION] Kết quả: ⏳ CHỜ XÁC NHẬN")
            
            else:
                print(f"  ⚠️ [QUYẾT ĐỊNH] Chưa đủ điều kiện vào lệnh:")
                if h1_trend == 'SIDEWAYS':
                    print(f"     - H1 Trend: {h1_trend} (Không rõ xu hướng)")
                elif m1_signal == 'NONE':
                    print(f"     - M1 Signal: {m1_signal} (Chưa có retest hoặc breakout)")
                elif m1_signal == 'BUY' and h1_trend != 'BUY':
                    print(f"     - M1 Signal: {m1_signal} nhưng H1 Trend: {h1_trend} (Không đồng ý)")
                elif m1_signal == 'SELL' and h1_trend != 'SELL':
                    print(f"     - M1 Signal: {m1_signal} nhưng H1 Trend: {h1_trend} (Không đồng ý)")
        else:
            print(f"\n  ⏸️ [QUYẾT ĐỊNH] Đang có {open_positions} lệnh mở, bỏ qua tín hiệu mới.")
        
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