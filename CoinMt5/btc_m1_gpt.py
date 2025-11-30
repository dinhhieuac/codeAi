from pickle import NONE
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
OPEN_POSITION=NONE

VOLUME = 0.01  # Khối lượng mặc định (Có thể ghi đè trong JSON)
# ⚠️ LƯU Ý: Với BTCUSD, 1 lot = 0.01 BTC (khác với forex: 1 lot = 100,000)
MAGIC = 20251118

# Thông số Chỉ báo & Lọc
# Chiến thuật M1: Price Action - Momentum + Pullback + Break
ATR_PERIOD = 14

# Thông số Price Action
TREND_LOOKBACK = 20  # Số nến để xác định trend (đỉnh/đáy)
MOMENTUM_CANDLE_BODY_RATIO = 0.6  # Tỷ lệ thân nến momentum (thân/tổng nến) >= 60%
PULLBACK_CANDLES_MAX = 3  # Số nến pullback tối đa (1-3 nến)
PULLBACK_BODY_RATIO_MAX = 0.4  # Thân nến pullback nhỏ (thân/tổng nến) <= 40%

# Thông số Quản lý Lệnh (Tính bằng USD, 1 pip = 1 USD cho BTCUSD)
# Chiến thuật M1: Price Action - SL ngắn và bám sát cấu trúc
# ⚠️ VỚI BTCUSD: 1 pip = 1 USD = 1 point (khác với XAUUSD: 1 pip = 10 points)
# Theo btc.md: SL 4-8 USD (market mạnh: 8-10 USD, market yếu: 4-6 USD)
SL_USD_MIN = 4.0   # SL tối thiểu: 4 USD
SL_USD_MAX = 12.0  # SL tối đa: 12 USD (không vượt quá để giữ R:R)
SL_BUFFER_USD = 3.0  # Buffer cho SL: 2-4 USD (đặt trên đỉnh nến hồi cuối)

# TP theo R:R ratio (0.8R - 1.2R, momentum mạnh: 1.5R)
TP_RATIO_MIN = 0.8  # TP tối thiểu: 0.8R
TP_RATIO_MAX = 1.2  # TP tối đa: 1.2R (thông thường)
TP_RATIO_MOMENTUM = 1.5  # TP khi momentum mạnh: 1.5R

# Quản lý lệnh theo R:R
# Khi đạt 0.5R → dời SL lên -0.1R
MANAGE_SL_AT_RATIO = 0.5  # Quản lý SL khi đạt 0.5R
MANAGE_SL_TO_RATIO = -0.1  # Dời SL lên -0.1R
# Khi đạt 0.8R → dời SL về Entry (BE)
BREAK_EVEN_AT_RATIO = 0.8  # Hòa vốn khi đạt 0.8R
# Khi đạt 1R → chốt 50%, phần còn lại trailing
PARTIAL_CLOSE_AT_RATIO = 1.0  # Chốt 50% khi đạt 1R
PARTIAL_CLOSE_PERCENT = 0.5  # Chốt 50% volume

ENABLE_BREAK_EVEN = True           # Bật/tắt chức năng di chuyển SL về hòa vốn
ENABLE_TRAILING_STOP = True        # Bật/tắt chức năng Trailing Stop (sau khi chốt 50%)
TRAILING_STEP_ATR_MULTIPLIER = 0.5  # Bước trailing = ATR × 0.5

# Cooldown sau lệnh thua
ENABLE_LOSS_COOLDOWN = True         # Bật/tắt cooldown sau lệnh thua
LOSS_COOLDOWN_MINUTES = 10         # Thời gian chờ sau lệnh thua (phút)
LOSS_COOLDOWN_MODE = 2              # Mode cooldown: 1 = 1 lệnh cuối thua, 2 = 2 lệnh cuối đều thua

# Tạm dừng sau khi gửi lệnh lỗi nhiều lần liên tiếp
ENABLE_ERROR_COOLDOWN = True         # Bật/tắt tạm dừng sau lỗi gửi lệnh
ERROR_COOLDOWN_COUNT = 5            # Số lần lỗi liên tiếp để kích hoạt cooldown
ERROR_COOLDOWN_MINUTES = 5          # Thời gian tạm dừng sau khi lỗi (phút)

# Biến đếm lỗi (sẽ được reset khi thành công)
error_count = 0                     # Số lần lỗi liên tiếp hiện tại
error_cooldown_start = None         # Thời gian bắt đầu cooldown (None nếu không có)

# Telegram Bot Configuration
 # Chat ID sẽ được lấy từ JSON config hoặc để None nếu không dùng Telegram
TELEGRAM_TOKEN = "6398751744:AAGp7VH7B00_kzMqdaFB59xlqAXnlKTar-g"         # Token của Telegram Bot (lấy từ @BotFather)
                                # Ví dụ: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
                                # Hướng dẫn: https://core.telegram.org/bots/tutorial

CHAT_ID = "1887610382"

# ==============================================================================
# 2. HÀM THIẾT LẬP LOGGING
# ==============================================================================

def setup_logging():
    """
    Thiết lập logging để ghi log vào file theo tên bot.
    File log sẽ được tạo trong thư mục XAUUSDMT5/logs/
    """
    # Tạo thư mục logs nếu chưa có (trong thư mục chứa bot)
    bot_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(bot_dir, "logs")
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

def load_config(filename=None):
    """
    Đọc thông tin cấu hình từ tệp JSON và gán vào biến toàn cục.
    
    Args:
        filename: Đường dẫn đến file config. Nếu None, tự động tìm mt5_account.json 
                  trong thư mục chứa bot.
    """
    global MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, SYMBOL, MT5_PATH, VOLUME, CHAT_ID
    
    # Nếu không có filename, tự động tìm file mt5_account.json trong thư mục chứa bot
    if filename is None:
        # Lấy thư mục chứa file bot hiện tại
        bot_dir = os.path.dirname(os.path.abspath(__file__))
        filename = os.path.join(bot_dir, "mt5_account.json")
    else:
        bot_dir = os.path.dirname(os.path.abspath(__file__))
        filename = os.path.join(bot_dir, filename)
    if not os.path.exists(filename):
        print(f"❌ Lỗi: Không tìm thấy tệp cấu hình '{filename}'. Vui lòng tạo file này.")
        return False
        
    try:
        with open(filename, 'r') as f:
            config = json.load(f)
        
        MT5_LOGIN = config.get("ACCOUNT_NUMBER")
        MT5_PASSWORD = config.get("PASSWORD")
        MT5_SERVER = config.get("SERVER")
        SYMBOL = config.get("SYMBOL", "BTCUSDm") 
        MT5_PATH = config.get("PATH")
        VOLUME = config.get("VOLUME", VOLUME) # Ghi đè Volume nếu có
        CHAT_ID = config.get("CHAT_ID", CHAT_ID)  # Lấy CHAT_ID từ JSON nếu có
        OPEN_POSITION = config.get("OPEN_POSITION", 1)
        
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

def check_price_action_trend(df_m1):
    """
    Xác định trend bằng Price Action (đỉnh/đáy)
    
    Theo btc.md:
    - Xu hướng giảm rõ rệt: Đỉnh sau thấp hơn đỉnh trước, Đáy sau thấp hơn đáy trước
    - Xu hướng tăng rõ rệt: Đỉnh sau cao hơn đỉnh trước, Đáy sau cao hơn đáy trước
    
    Args:
        df_m1: DataFrame M1
        
    Returns:
        'BUY', 'SELL', hoặc 'SIDEWAYS'
    """
    if df_m1 is None or len(df_m1) < TREND_LOOKBACK:
        return 'SIDEWAYS'
    
    # Lấy TREND_LOOKBACK nến gần nhất
    recent_df = df_m1.tail(TREND_LOOKBACK)
    
    # Tìm các đỉnh và đáy cục bộ
    highs = recent_df['high']
    lows = recent_df['low']
    
    # Tìm 2 đỉnh gần nhất và 2 đáy gần nhất
    # Đỉnh: high lớn hơn 2 nến trước và 2 nến sau
    peaks = []
    for i in range(2, len(highs) - 2):
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i-2] and \
           highs.iloc[i] > highs.iloc[i+1] and highs.iloc[i] > highs.iloc[i+2]:
            peaks.append((i, highs.iloc[i]))
    
    # Đáy: low nhỏ hơn 2 nến trước và 2 nến sau
    troughs = []
    for i in range(2, len(lows) - 2):
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i-2] and \
           lows.iloc[i] < lows.iloc[i+1] and lows.iloc[i] < lows.iloc[i+2]:
            troughs.append((i, lows.iloc[i]))
    
    # Kiểm tra xu hướng
    if len(peaks) >= 2 and len(troughs) >= 2:
        # Lấy 2 đỉnh gần nhất
        peaks_sorted = sorted(peaks, key=lambda x: x[0], reverse=True)[:2]
        # Lấy 2 đáy gần nhất
        troughs_sorted = sorted(troughs, key=lambda x: x[0], reverse=True)[:2]
        
        peak1_val = peaks_sorted[0][1]
        peak2_val = peaks_sorted[1][1]
        trough1_val = troughs_sorted[0][1]
        trough2_val = troughs_sorted[1][1]
        
        # Xu hướng giảm: Đỉnh sau < Đỉnh trước và Đáy sau < Đáy trước
        if peak1_val < peak2_val and trough1_val < trough2_val:
            print(f"  📊 [TREND] XU HƯỚNG GIẢM (Đỉnh: {peak1_val:.5f} < {peak2_val:.5f}, Đáy: {trough1_val:.5f} < {trough2_val:.5f})")
            return 'SELL'
        # Xu hướng tăng: Đỉnh sau > Đỉnh trước và Đáy sau > Đáy trước
        elif peak1_val > peak2_val and trough1_val > trough2_val:
            print(f"  📊 [TREND] XU HƯỚNG TĂNG (Đỉnh: {peak1_val:.5f} > {peak2_val:.5f}, Đáy: {trough1_val:.5f} > {trough2_val:.5f})")
            return 'BUY'
    
    print(f"  📊 [TREND] SIDEWAYS (Không rõ xu hướng)")
    return 'SIDEWAYS'

def check_momentum_candle(df_m1, trend='SELL'):
    """
    Phát hiện nến momentum
    
    Theo btc.md:
    - SELL: Nến thân dài, đóng cửa gần đáy, phá đáy gần nhất
    - BUY: Nến thân dài, đóng cửa gần đỉnh, phá đỉnh gần nhất
    
    Args:
        df_m1: DataFrame M1
        trend: 'SELL' hoặc 'BUY' để kiểm tra momentum tương ứng
        
    Returns:
        Tuple (bool, dict): (has_momentum, info_dict)
            - has_momentum: True nếu có nến momentum
            - info_dict: Thông tin nến momentum (index, high, low, close, body_ratio, direction)
    """
    if df_m1 is None or len(df_m1) < 5:
        return False, None
    
    # Kiểm tra nến gần nhất (có thể là nến momentum)
    last_candle = df_m1.iloc[-1]
    high = last_candle['high']
    low = last_candle['low']
    close = last_candle['close']
    open_price = last_candle['open']
    
    # Tính thân nến và tổng nến
    body = abs(close - open_price)
    total_range = high - low
    
    if total_range == 0:
        return False, None
    
    body_ratio = body / total_range
    
    if trend == 'SELL':
        # Kiểm tra nến momentum SELL: thân dài (>= 60%), đóng cửa gần đáy
        # Đóng cửa gần đáy: (close - low) / total_range <= 0.3
        close_to_low_ratio = (close - low) / total_range if total_range > 0 else 0
        
        if body_ratio >= MOMENTUM_CANDLE_BODY_RATIO and close_to_low_ratio <= 0.3:
            # Kiểm tra phá vỡ cấu trúc: giá phá đáy gần nhất
            if len(df_m1) >= 10:
                recent_low = df_m1['low'].iloc[-10:-1].min()
                if low < recent_low:
                    info = {
                        'index': len(df_m1) - 1,
                        'high': high,
                        'low': low,
                        'close': close,
                        'open': open_price,
                        'body_ratio': body_ratio,
                        'close_to_low_ratio': close_to_low_ratio,
                        'direction': 'SELL'
                    }
                    print(f"  🔥 [MOMENTUM] Phát hiện nến momentum SELL:")
                    print(f"     - Thân nến: {body_ratio:.1%} (>= {MOMENTUM_CANDLE_BODY_RATIO:.1%})")
                    print(f"     - Đóng cửa gần đáy: {close_to_low_ratio:.1%} (<= 30%)")
                    print(f"     - Phá đáy gần nhất: {low:.5f} < {recent_low:.5f}")
                    return True, info
    
    elif trend == 'BUY':
        # Kiểm tra nến momentum BUY: thân dài (>= 60%), đóng cửa gần đỉnh
        # Đóng cửa gần đỉnh: (high - close) / total_range <= 0.3
        close_to_high_ratio = (high - close) / total_range if total_range > 0 else 0
        
        if body_ratio >= MOMENTUM_CANDLE_BODY_RATIO and close_to_high_ratio <= 0.3:
            # Kiểm tra phá vỡ cấu trúc: giá phá đỉnh gần nhất
            if len(df_m1) >= 10:
                recent_high = df_m1['high'].iloc[-10:-1].max()
                if high > recent_high:
                    info = {
                        'index': len(df_m1) - 1,
                        'high': high,
                        'low': low,
                        'close': close,
                        'open': open_price,
                        'body_ratio': body_ratio,
                        'close_to_high_ratio': close_to_high_ratio,
                        'direction': 'BUY'
                    }
                    print(f"  🔥 [MOMENTUM] Phát hiện nến momentum BUY:")
                    print(f"     - Thân nến: {body_ratio:.1%} (>= {MOMENTUM_CANDLE_BODY_RATIO:.1%})")
                    print(f"     - Đóng cửa gần đỉnh: {close_to_high_ratio:.1%} (<= 30%)")
                    print(f"     - Phá đỉnh gần nhất: {high:.5f} > {recent_high:.5f}")
                    return True, info
    
    return False, None

def check_pullback(df_m1, momentum_info):
    """
    Phát hiện pullback (hồi nhỏ) sau nến momentum
    
    Theo btc.md:
    - SELL: 1-3 nến hồi nhỏ, không phá đỉnh nến momentum
    - BUY: 1-3 nến hồi nhỏ, không phá đáy nến momentum
    
    Args:
        df_m1: DataFrame M1
        momentum_info: Dict thông tin nến momentum (có direction: 'SELL' hoặc 'BUY')
        
    Returns:
        Tuple (bool, dict): (has_pullback, info_dict)
            - has_pullback: True nếu có pullback hợp lệ
            - info_dict: Thông tin pullback (start_index, end_index, candles_count, last_pullback_high/low)
    """
    if momentum_info is None:
        return False, None
    
    momentum_index = momentum_info['index']
    momentum_high = momentum_info['high']
    momentum_low = momentum_info['low']
    direction = momentum_info.get('direction', 'SELL')
    
    # Kiểm tra các nến sau nến momentum (tối đa PULLBACK_CANDLES_MAX)
    pullback_candles = []
    start_index = momentum_index + 1
    
    if len(df_m1) < start_index + 1:
        return False, None
    
    # Kiểm tra từng nến sau momentum
    for i in range(start_index, min(start_index + PULLBACK_CANDLES_MAX, len(df_m1))):
        candle = df_m1.iloc[i]
        high = candle['high']
        low = candle['low']
        close = candle['close']
        open_price = candle['open']
        
        # Kiểm tra không phá cấu trúc momentum
        if direction == 'SELL':
            # SELL: Không phá đỉnh nến momentum
            if high > momentum_high:
                # Phá đỉnh → không phải pullback
                break
        else:  # BUY
            # BUY: Không phá đáy nến momentum
            if low < momentum_low:
                # Phá đáy → không phải pullback
                break
        
        # Tính thân nến
        body = abs(close - open_price)
        total_range = high - low
        
        if total_range == 0:
            continue
        
        body_ratio = body / total_range
        
        # Kiểm tra thân nến nhỏ (<= 40%)
        if body_ratio <= PULLBACK_BODY_RATIO_MAX:
            pullback_candles.append(i)
        else:
            # Thân nến lớn → không phải pullback
            break
    
    if 1 <= len(pullback_candles) <= PULLBACK_CANDLES_MAX:
        if direction == 'SELL':
            last_pullback_high = df_m1.iloc[pullback_candles[-1]]['high']
            info = {
                'start_index': start_index,
                'end_index': pullback_candles[-1],
                'candles_count': len(pullback_candles),
                'last_pullback_high': last_pullback_high,
                'direction': 'SELL'
            }
            print(f"  📉 [PULLBACK] Phát hiện {len(pullback_candles)} nến pullback SELL:")
            print(f"     - Không phá đỉnh momentum: {last_pullback_high:.5f} <= {momentum_high:.5f}")
        else:  # BUY
            last_pullback_low = df_m1.iloc[pullback_candles[-1]]['low']
            info = {
                'start_index': start_index,
                'end_index': pullback_candles[-1],
                'candles_count': len(pullback_candles),
                'last_pullback_low': last_pullback_low,
                'direction': 'BUY'
            }
            print(f"  📈 [PULLBACK] Phát hiện {len(pullback_candles)} nến pullback BUY:")
            print(f"     - Không phá đáy momentum: {last_pullback_low:.5f} >= {momentum_low:.5f}")
        return True, info
    
    return False, None

def check_entry_signal(df_m1, trend, momentum_info, pullback_info):
    """
    Kiểm tra điểm vào lệnh khi giá phá cấu trúc
    
    Theo btc.md:
    - SELL: Giá phá đáy nến hồi cuối cùng
    - BUY: Giá phá đỉnh nến hồi cuối cùng
    - Không đoán đỉnh đáy
    - Không vào khi nến đang chạy
    
    Args:
        df_m1: DataFrame M1
        trend: 'BUY', 'SELL', hoặc 'SIDEWAYS'
        momentum_info: Dict thông tin nến momentum
        pullback_info: Dict thông tin pullback
        
    Returns:
        Tuple (bool, dict): (has_signal, signal_info)
            - has_signal: True nếu có tín hiệu vào lệnh
            - signal_info: Thông tin tín hiệu (entry_price, sl_price, tp_price, sl_usd, tp_usd, direction)
    """
    if trend not in ['SELL', 'BUY']:
        return False, None
    
    if momentum_info is None or pullback_info is None:
        return False, None
    
    direction = momentum_info.get('direction', trend)
    
    # Lấy giá hiện tại
    tick = mt5.symbol_info_tick(SYMBOL)
    
    if direction == 'SELL':
        # SELL: Kiểm tra giá phá đáy nến hồi cuối
        last_pullback_index = pullback_info['end_index']
        last_pullback_low = df_m1.iloc[last_pullback_index]['low']
        last_pullback_high = pullback_info.get('last_pullback_high', df_m1.iloc[last_pullback_index]['high'])
        current_price = tick.bid
        
        # Kiểm tra giá phá đáy nến hồi cuối
        if current_price < last_pullback_low:
            # Tính SL: Đặt trên đỉnh nến hồi cuối + buffer
            sl_price = last_pullback_high + SL_BUFFER_USD
            sl_usd = sl_price - current_price
            
            # Đảm bảo SL trong khoảng 4-12 USD
            if sl_usd < SL_USD_MIN:
                sl_usd = SL_USD_MIN
                sl_price = current_price + sl_usd
            elif sl_usd > SL_USD_MAX:
                sl_usd = SL_USD_MAX
                sl_price = current_price + sl_usd
            
            # Tính TP: 0.8R - 1.2R (nếu momentum mạnh thì 1.5R)
            momentum_strong = False
            if len(df_m1) >= 5:
                strong_candles = 0
                for i in range(max(0, len(df_m1) - 5), len(df_m1)):
                    candle = df_m1.iloc[i]
                    body = abs(candle['close'] - candle['open'])
                    total_range = candle['high'] - candle['low']
                    if total_range > 0 and body / total_range >= 0.6:
                        strong_candles += 1
                if strong_candles >= 3:
                    momentum_strong = True
            
            if momentum_strong:
                tp_ratio = TP_RATIO_MOMENTUM
            else:
                tp_ratio = TP_RATIO_MAX
            
            tp_usd = sl_usd * tp_ratio
            tp_price = current_price - tp_usd
            
            signal_info = {
                'entry_price': current_price,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'sl_usd': sl_usd,
                'tp_usd': tp_usd,
                'rr_ratio': tp_ratio,
                'momentum_strong': momentum_strong,
                'direction': 'SELL'
            }
            
            print(f"  ✅ [ENTRY SIGNAL] Tín hiệu SELL:")
            print(f"     - Giá phá đáy nến hồi cuối: {current_price:.5f} < {last_pullback_low:.5f}")
            print(f"     - SL: {sl_price:.5f} ({sl_usd:.2f} USD) - Trên đỉnh nến hồi cuối + buffer")
            print(f"     - TP: {tp_price:.5f} ({tp_usd:.2f} USD) - {tp_ratio:.1f}R")
            if momentum_strong:
                print(f"     - Momentum mạnh: TP = {tp_ratio:.1f}R")
            
            return True, signal_info
    
    else:  # BUY
        # BUY: Kiểm tra giá phá đỉnh nến hồi cuối
        last_pullback_index = pullback_info['end_index']
        last_pullback_high = df_m1.iloc[last_pullback_index]['high']
        last_pullback_low = pullback_info.get('last_pullback_low', df_m1.iloc[last_pullback_index]['low'])
        current_price = tick.ask
        
        # Kiểm tra giá phá đỉnh nến hồi cuối
        if current_price > last_pullback_high:
            # Tính SL: Đặt dưới đáy nến hồi cuối - buffer
            sl_price = last_pullback_low - SL_BUFFER_USD
            sl_usd = current_price - sl_price
            
            # Đảm bảo SL trong khoảng 4-12 USD
            if sl_usd < SL_USD_MIN:
                sl_usd = SL_USD_MIN
                sl_price = current_price - sl_usd
            elif sl_usd > SL_USD_MAX:
                sl_usd = SL_USD_MAX
                sl_price = current_price - sl_usd
            
            # Tính TP: 0.8R - 1.2R (nếu momentum mạnh thì 1.5R)
            momentum_strong = False
            if len(df_m1) >= 5:
                strong_candles = 0
                for i in range(max(0, len(df_m1) - 5), len(df_m1)):
                    candle = df_m1.iloc[i]
                    body = abs(candle['close'] - candle['open'])
                    total_range = candle['high'] - candle['low']
                    if total_range > 0 and body / total_range >= 0.6:
                        strong_candles += 1
                if strong_candles >= 3:
                    momentum_strong = True
            
            if momentum_strong:
                tp_ratio = TP_RATIO_MOMENTUM
            else:
                tp_ratio = TP_RATIO_MAX
            
            tp_usd = sl_usd * tp_ratio
            tp_price = current_price + tp_usd
            
            signal_info = {
                'entry_price': current_price,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'sl_usd': sl_usd,
                'tp_usd': tp_usd,
                'rr_ratio': tp_ratio,
                'momentum_strong': momentum_strong,
                'direction': 'BUY'
            }
            
            print(f"  ✅ [ENTRY SIGNAL] Tín hiệu BUY:")
            print(f"     - Giá phá đỉnh nến hồi cuối: {current_price:.5f} > {last_pullback_high:.5f}")
            print(f"     - SL: {sl_price:.5f} ({sl_usd:.2f} USD) - Dưới đáy nến hồi cuối - buffer")
            print(f"     - TP: {tp_price:.5f} ({tp_usd:.2f} USD) - {tp_ratio:.1f}R")
            if momentum_strong:
                print(f"     - Momentum mạnh: TP = {tp_ratio:.1f}R")
            
            return True, signal_info
    
    return False, None

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
    Tính giá trị pip cho BTCUSD
    
    ⚠️ VỚI BTCUSD: 
    - 1 lot = 0.01 BTC (khác với forex: 1 lot = 100,000)
    - 1 pip = 1 USD movement trong giá
    - Với lot 0.01 (tức 0.0001 BTC): pip value phụ thuộc vào contract size
    
    Lưu ý: Hàm này có thể không được sử dụng trực tiếp vì ATR được tính từ price movement.
    ATR đã là pips (USD movement) và không phụ thuộc vào lot size.
    
    Returns:
        pip_value: Giá trị 1 pip tính bằng USD (tham khảo)
    """
    # Với BTCUSD, 1 pip = 1 USD movement
    # Pip value thực tế phụ thuộc vào lot size và contract size của broker
    return 1.0  # 1 pip = 1 USD movement (tham khảo)

def calculate_atr_from_m1(df_m1, period=14):
    """
    Tính ATR từ nến M1
    
    ⚠️ VỚI BTCUSD: 1 pip = 1 USD = 1 point
    ATR được tính bằng giá (ví dụ: 5.5 USD), và đã là pips rồi
    Không cần chia cho 0.01 như XAUUSD
    
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
    
    # ⚠️ VỚI BTCUSD: 1 pip = 1 USD = 1 point
    # ATR đã là pips rồi (không cần chia cho 0.01 như XAUUSD)
    # Ví dụ: ATR = 5.5 USD → ATR = 5.5 pips
    atr_pips = atr_price  # ATR đã là pips
    
    return atr_pips

def send_order(trade_type, volume, signal_info=None, trend_info=None, momentum_info=None, pullback_info=None, atr_pips=None, deviation=20):
    """
    Gửi lệnh Market Execution với SL/TP từ Price Action signal.
    
    Args:
        trade_type: mt5.ORDER_TYPE_BUY hoặc mt5.ORDER_TYPE_SELL
        volume: Khối lượng giao dịch
        signal_info: Dict chứa thông tin SL/TP từ Price Action (entry_price, sl_price, tp_price, sl_usd, tp_usd)
        trend_info: Thông tin trend (str: 'BUY', 'SELL', 'SIDEWAYS')
        momentum_info: Dict thông tin nến momentum
        pullback_info: Dict thông tin pullback
        atr_pips: Giá trị ATR (pips)
        deviation: Độ lệch giá cho phép
    
    Returns:
        bool: True nếu gửi lệnh thành công, False nếu lỗi
    """
    global error_count, error_cooldown_start
    
    point = get_symbol_info()
    if point is None:
        print("❌ Lỗi: Không thể lấy thông tin ký hiệu để gửi lệnh.")
        return False
        
    tick_info = mt5.symbol_info_tick(SYMBOL)
    price = tick_info.ask if trade_type == mt5.ORDER_TYPE_BUY else tick_info.bid
    
    # Sử dụng SL/TP từ signal_info (Price Action)
    if signal_info is not None:
        sl = signal_info['sl_price']
        tp = signal_info['tp_price']
        sl_usd = signal_info['sl_usd']
        tp_usd = signal_info['tp_usd']
        entry_price = signal_info['entry_price']
        
        # Sử dụng entry_price từ signal_info hoặc giá hiện tại
        if abs(price - entry_price) > 10 * point:  # Nếu giá lệch quá nhiều, dùng giá hiện tại
            print(f"  ⚠️ [ORDER] Giá hiện tại ({price:.5f}) lệch nhiều so với entry signal ({entry_price:.5f}), dùng giá hiện tại")
            # Điều chỉnh SL/TP theo giá mới
            if trade_type == mt5.ORDER_TYPE_SELL:
                sl = price + sl_usd
                tp = price - tp_usd
            else:  # BUY
                sl = price - sl_usd
                tp = price + tp_usd
        else:
            price = entry_price  # Dùng entry_price từ signal
        
        print(f"  📊 [ORDER] Price Action Entry:")
        print(f"     Entry: {price:.5f} | SL: {sl:.5f} ({sl_usd:.2f} USD) | TP: {tp:.5f} ({tp_usd:.2f} USD)")
        print(f"     R:R = {tp_usd/sl_usd:.2f}:1")
    else:
        print("❌ Lỗi: Không có signal_info để gửi lệnh.")
        return False
    
    # Kiểm tra logic SL/TP
    if trade_type == mt5.ORDER_TYPE_BUY:
        if sl >= price or tp <= price:
            print(f"  ⚠️ [ORDER] LỖI LOGIC: BUY order - SL ({sl:.5f}) phải < Entry ({price:.5f}) và TP ({tp:.5f}) phải > Entry")
            return False
    else:  # SELL
        if sl <= price or tp >= price:
            print(f"  ⚠️ [ORDER] LỖI LOGIC: SELL order - SL ({sl:.5f}) phải > Entry ({price:.5f}) và TP ({tp:.5f}) phải < Entry")
            return False
    
    # Tính sl_points và tp_points để hiển thị
    sl_points = sl_usd  # Với BTCUSD: 1 pip = 1 USD
    tp_points = tp_usd  # Với BTCUSD: 1 pip = 1 USD
    
    # Tính risk/reward thực tế
    symbol_info_for_risk = get_symbol_info_full()
    contract_size = 0.01  # Mặc định: 1 lot = 0.01 BTC
    if symbol_info_for_risk is not None:
        contract_size = getattr(symbol_info_for_risk, 'trade_contract_size', 0.01)
    
    if contract_size > 0:
        pip_value_per_lot = contract_size  # pip_value = contract_size $/lot/pip
    else:
        pip_value_per_lot = 0.01  # Mặc định: 1 lot = 0.01 BTC → pip_value = $0.01/lot/pip
    
    risk_usd = volume * sl_usd * pip_value_per_lot
    reward_usd = volume * tp_usd * pip_value_per_lot
    
    print(f"  💰 [ORDER] Entry: {price:.5f} | SL: {sl:.5f} ({sl_usd:.2f} USD) | TP: {tp:.5f} ({tp_usd:.2f} USD)")
    print(f"  💵 [RISK] Volume: {volume} lot | Contract Size: {contract_size} BTC/lot | SL: {sl_usd:.2f} USD | Risk: ~${risk_usd:.2f} | Reward: ~${reward_usd:.2f} | RR: {tp_usd/sl_usd:.2f}:1")
        
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
        print(f"  Entry: {price:.5f} | SL: {sl:.5f} ({sl_usd:.2f} USD) | TP: {tp:.5f} ({tp_usd:.2f} USD)")
        
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
        logger.error(f"Entry: {price:.5f} | SL: {sl:.5f} ({sl_usd:.2f} USD) | TP: {tp:.5f} ({tp_usd:.2f} USD)")
        logger.error(f"Volume: {volume} | Symbol: {SYMBOL}")
        logger.error(f"Error Count: {error_count}/{ERROR_COOLDOWN_COUNT}")
        logger.error("=" * 70)
        
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
        rr_ratio = tp_usd / sl_usd if sl_usd > 0 else 0
        
        logger.info("=" * 70)
        logger.info(f"✅ VÀO LỆNH THÀNH CÔNG: {trade_direction}")
        logger.info(f"Order ID: {result.order}")
        logger.info(f"Symbol: {SYMBOL}")
        logger.info(f"Entry: {price:.5f}")
        logger.info(f"SL: {sl:.5f} ({sl_usd:.2f} USD)")
        logger.info(f"TP: {tp:.5f} ({tp_usd:.2f} USD)")
        logger.info(f"R:R = {rr_ratio:.2f}:1")
        logger.info(f"Volume: {volume}")
        
        # Ghi log các chỉ số chi tiết
        if trend_info:
            logger.info(f"Trend: {trend_info}")
        if momentum_info:
            logger.info(f"Momentum Candle: Index={momentum_info.get('index', 'N/A')}, Body Ratio={momentum_info.get('body_ratio', 0):.1%}, Close to Low={momentum_info.get('close_to_low_ratio', 0):.1%}")
        if pullback_info:
            logger.info(f"Pullback: {pullback_info.get('candles_count', 0)} candles, Last High={pullback_info.get('last_pullback_high', 0):.5f}")
        if atr_pips is not None:
            logger.info(f"ATR: {atr_pips:.2f} pips")
        if signal_info and signal_info.get('momentum_strong'):
            logger.info(f"Momentum Strong: TP = {signal_info.get('rr_ratio', 0):.1f}R")
        
        # Tính risk/reward
        symbol_info_for_risk = get_symbol_info_full()
        contract_size = 0.01  # Mặc định: 1 lot = 0.01 BTC
        if symbol_info_for_risk is not None:
            contract_size = getattr(symbol_info_for_risk, 'trade_contract_size', 0.01)
        if contract_size > 0:
            pip_value_per_lot = contract_size
        else:
            pip_value_per_lot = 0.01
        risk_usd = volume * sl_usd * pip_value_per_lot
        reward_usd = volume * tp_usd * pip_value_per_lot
        logger.info(f"Risk: ${risk_usd:.2f} | Reward: ${reward_usd:.2f} | Contract Size: {contract_size} BTC/lot")
        
        logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)
        
        # Gửi thông báo Telegram với thông tin chi tiết
        telegram_msg = f"""
<b>{trade_direction} LỆNH MỚI</b>

📊 <b>Symbol:</b> {SYMBOL}
💰 <b>Entry:</b> {price:.5f}
🛑 <b>SL:</b> {sl:.5f} ({sl_usd:.2f} USD)
🎯 <b>TP:</b> {tp:.5f} ({tp_usd:.2f} USD)
📊 <b>R:R:</b> {rr_ratio:.2f}:1
📦 <b>Volume:</b> {volume}
🆔 <b>Order ID:</b> {result.order}

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
        
        # Tính profit hiện tại (USD)
        if is_buy:
            profit_usd = current_price - entry_price
        else:  # SELL
            profit_usd = entry_price - current_price
        
        # Tính SL ban đầu (từ entry đến SL hiện tại)
        if is_buy:
            initial_sl_usd = entry_price - pos.sl if pos.sl > 0 else 0
        else:  # SELL
            initial_sl_usd = pos.sl - entry_price if pos.sl > 0 else 0
        
        if initial_sl_usd == 0:
            continue  # Không có SL ban đầu, bỏ qua
        
        # Tính R:R ratio hiện tại
        current_r_ratio = profit_usd / initial_sl_usd if initial_sl_usd > 0 else 0
        
        # --- QUẢN LÝ LỆNH THEO R:R (theo btc.md) ---
        # 1. Khi đạt 0.5R → dời SL lên -0.1R
        if current_r_ratio >= MANAGE_SL_AT_RATIO and current_r_ratio < BREAK_EVEN_AT_RATIO:
            # Tính SL mới = Entry - 0.1R
            new_sl_usd = initial_sl_usd * abs(MANAGE_SL_TO_RATIO)  # 0.1R
            if is_buy:
                new_sl_price = entry_price - new_sl_usd
            else:  # SELL
                new_sl_price = entry_price + new_sl_usd
            
            # Chỉ cập nhật nếu SL mới tốt hơn SL hiện tại
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
                    print(f"📊 Lệnh {pos.ticket}: Đạt {current_r_ratio:.2f}R → Dời SL lên -0.1R ({new_sl_price:.5f})")
        
        # 2. Khi đạt 0.8R → dời SL về Entry (BE)
        elif current_r_ratio >= BREAK_EVEN_AT_RATIO and current_r_ratio < PARTIAL_CLOSE_AT_RATIO:
            if ENABLE_BREAK_EVEN:
                # +1 pip để bù spread
                pips_buffer = 1 * point  # Với BTCUSD: 1 pip = 1 point
                new_sl_price = entry_price + pips_buffer if is_buy else entry_price - pips_buffer
                
                # Chỉ cập nhật nếu SL hiện tại chưa ở BE
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
                        print(f"🎯 Lệnh {pos.ticket}: Đạt {current_r_ratio:.2f}R → Dời SL về Hòa Vốn ({new_sl_price:.5f})")
        
        # 3. Khi đạt 1R → chốt 50%, phần còn lại trailing
        elif current_r_ratio >= PARTIAL_CLOSE_AT_RATIO:
            # Kiểm tra xem đã chốt 50% chưa (kiểm tra volume)
            if pos.volume >= pos.volume_initial * (1 - PARTIAL_CLOSE_PERCENT + 0.01):  # Chưa chốt (volume còn >= 50%)
                # Chốt 50% volume
                close_volume = pos.volume * PARTIAL_CLOSE_PERCENT
                if close_volume >= 0.001:  # Đảm bảo volume tối thiểu
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": SYMBOL,
                        "volume": close_volume,
                        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                        "position": pos.ticket,
                        "deviation": 20,
                        "magic": MAGIC,
                        "comment": f"Partial_Close_50pct",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    result = mt5.order_send(request)
                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"💰 Lệnh {pos.ticket}: Đạt {current_r_ratio:.2f}R → Chốt 50% ({close_volume:.3f} lot)")
            
            # Trailing stop cho phần còn lại (sau khi chốt 50%)
            if ENABLE_TRAILING_STOP and atr_pips is not None:
                trailing_step_pips = atr_pips * TRAILING_STEP_ATR_MULTIPLIER
                trailing_step_points = trailing_step_pips  # Với BTCUSD: 1 pip = 1 point
                
                if is_buy:
                    new_sl_ts = current_bid - (trailing_step_points * point)
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
                            print(f"⏫ Lệnh {pos.ticket} BUY: Trailing Stop ({new_sl_ts:.5f}) sau khi chốt 50%")
                else:  # SELL
                    new_sl_ts = current_ask + (trailing_step_points * point)
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
                            print(f"⏬ Lệnh {pos.ticket} SELL: Trailing Stop ({new_sl_ts:.5f}) sau khi chốt 50%")

# ==============================================================================
# 7. CHU TRÌNH CHÍNH (MAIN LOOP)
# ==============================================================================

def run_bot():
    """Chu trình chính của bot, lặp lại việc kiểm tra tín hiệu và quản lý lệnh."""
    
    # 0. Thiết lập logging
    logger = setup_logging()
    logger.info("Khởi động bot...")
    
    # 1. Tải cấu hình
    if not load_config("btc.json"):
        logger.error("Không thể tải cấu hình. Dừng bot.")
        return
        
    # 2. Khởi tạo MT5 và kết nối
    initialize_mt5()
    logger.info("Đã kết nối MT5 thành công")
    
    last_candle_time = datetime(1970, 1, 1)

    print("\n--- Bắt đầu Chu Trình Giao Dịch M1 (Chiến thuật: Price Action - Momentum + Pullback + Break) ---")
    print("📋 Chiến thuật (theo btc.md - mở rộng cho cả BUY và SELL):")
    print("   1. Xác định trend bằng Price Action (đỉnh/đáy)")
    print("      - BUY: Higher Highs + Higher Lows")
    print("      - SELL: Lower Highs + Lower Lows")
    print("   2. Phát hiện nến momentum:")
    print("      - SELL: Thân dài, đóng cửa gần đáy, phá đáy gần nhất")
    print("      - BUY: Thân dài, đóng cửa gần đỉnh, phá đỉnh gần nhất")
    print("   3. Phát hiện pullback (1-3 nến hồi nhỏ, không phá cấu trúc momentum)")
    print("   4. Điểm vào lệnh:")
    print("      - SELL: Giá phá đáy nến hồi cuối cùng")
    print("      - BUY: Giá phá đỉnh nến hồi cuối cùng")
    print("   5. SL: 4-8 USD (SELL: trên đỉnh nến hồi cuối + buffer | BUY: dưới đáy nến hồi cuối - buffer)")
    print("   6. TP: 0.8R-1.2R (momentum mạnh: 1.5R)")
    print("   7. Quản lý: 0.5R → -0.1R, 0.8R → BE, 1R → chốt 50% + trailing\n")
    
    while True:
        start_time = time.time() # Ghi lại thời gian bắt đầu chu kỳ
        current_time = datetime.now()
        
        # 2. Lấy dữ liệu M1
        df_m1 = get_rates(mt5.TIMEFRAME_M1)
        if df_m1 is None or len(df_m1) < TREND_LOOKBACK + 5:
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
        spread = current_ask - current_price
        print(f"  💰 Giá hiện tại: BID={current_price:.5f} | ASK={current_ask:.5f} | Spread={spread:.5f}")
        
        # Tính ATR để log
        atr_pips_log = calculate_atr_from_m1(df_m1)
        
        # Lấy logger để ghi log
        logger = logging.getLogger(__name__)
        
        # --- KIỂM TRA TÍN HIỆU VÀ LỌC (Price Action) ---
        print(f"\n  🔍 [KIỂM TRA TÍN HIỆU] Bắt đầu phân tích Price Action...")
        
        # 1. Xác định trend bằng Price Action (đỉnh/đáy)
        print(f"\n  ┌─ [BƯỚC 1] Kiểm tra xu hướng (Price Action)")
        trend = check_price_action_trend(df_m1)
        print(f"  └─ [BƯỚC 1] Kết quả: {trend}")
        
        # Kiểm tra momentum/pullback/signal cho cả BUY và SELL
        has_momentum = False
        momentum_info = None
        has_pullback = False
        pullback_info = None
        has_signal = False
        signal_info = None
        
        if trend in ['SELL', 'BUY']:
            # 2. Phát hiện nến momentum (cho SELL hoặc BUY)
            print(f"\n  ┌─ [BƯỚC 2] Phát hiện nến momentum ({trend})")
            has_momentum, momentum_info = check_momentum_candle(df_m1, trend)
            if has_momentum:
                print(f"  └─ [BƯỚC 2] Kết quả: ✅ Có nến momentum")
            else:
                print(f"  └─ [BƯỚC 2] Kết quả: ⚠️ Chưa có nến momentum")
            
            # 3. Phát hiện pullback (hồi nhỏ) - chỉ khi có momentum
            if has_momentum:
                print(f"\n  ┌─ [BƯỚC 3] Phát hiện pullback (hồi nhỏ)")
                has_pullback, pullback_info = check_pullback(df_m1, momentum_info)
                if has_pullback:
                    print(f"  └─ [BƯỚC 3] Kết quả: ✅ Có {pullback_info['candles_count']} nến pullback")
                else:
                    print(f"  └─ [BƯỚC 3] Kết quả: ⚠️ Chưa có pullback")
            else:
                print(f"\n  ┌─ [BƯỚC 3] Phát hiện pullback (hồi nhỏ)")
                print(f"  └─ [BƯỚC 3] Kết quả: ⚠️ Bỏ qua (chưa có momentum)")
            
            # 4. Kiểm tra điểm vào lệnh khi giá phá cấu trúc
            if has_momentum and has_pullback:
                print(f"\n  ┌─ [BƯỚC 4] Kiểm tra điểm vào lệnh {trend}")
                has_signal, signal_info = check_entry_signal(df_m1, trend, momentum_info, pullback_info)
                if has_signal:
                    print(f"  └─ [BƯỚC 4] Kết quả: ✅ Có tín hiệu {trend}")
                else:
                    print(f"  └─ [BƯỚC 4] Kết quả: ⚠️ Chưa có tín hiệu")
            else:
                print(f"\n  ┌─ [BƯỚC 4] Kiểm tra điểm vào lệnh {trend}")
                print(f"  └─ [BƯỚC 4] Kết quả: ⚠️ Bỏ qua (chưa có momentum/pullback)")
        else:
            # Trend không phải SELL hoặc BUY → bỏ qua các bước kiểm tra
            print(f"\n  ┌─ [BƯỚC 2-4] Kiểm tra momentum/pullback/signal")
            print(f"  └─ [BƯỚC 2-4] Kết quả: ⚠️ Bỏ qua (Trend={trend}, cần BUY hoặc SELL)")

        # 5. Kiểm tra vị thế đang mở
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions is None:
            open_positions = 0
        else:
            open_positions = len([pos for pos in positions if pos.magic == MAGIC])
        print(f"\n  📋 [TRẠNG THÁI] Số lệnh đang mở ({SYMBOL}): {open_positions}")
        
        print(f"\n  📊 [TÓM TẮT] Trend={trend} | Momentum={'✅' if has_momentum else '❌'} | Pullback={'✅' if has_pullback else '❌'} | Signal={'✅' if has_signal else '❌'}")

        if open_positions < OPEN_POSITION:
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
                    
                    # Không ghi log khi bị chặn bởi error cooldown (chỉ in ra console)
                    
                    print(f"{'='*70}\n")
                    continue
                else:
                    print(f"  ✅ [ERROR COOLDOWN] Đã hết thời gian tạm dừng ({minutes_elapsed:.1f} phút đã trôi qua)")
                    error_count = 0
                    error_cooldown_start = None
            
            # Kiểm tra điều kiện vào lệnh (BUY hoặc SELL)
            if has_signal and trend in ['SELL', 'BUY'] and has_momentum and has_pullback:
                trade_emoji = "🔻" if trend == 'SELL' else "🔺"
                trade_direction_text = "giảm" if trend == 'SELL' else "tăng"
                entry_text = "Giá phá đáy nến hồi cuối" if trend == 'SELL' else "Giá phá đỉnh nến hồi cuối"
                
                print(f"  ✅ [QUYẾT ĐỊNH] {trade_emoji} TÍN HIỆU {trend} (Price Action)!")
                print(f"     - Trend: {trend} (Xu hướng {trade_direction_text})")
                print(f"     - Momentum: ✅ Có nến momentum")
                print(f"     - Pullback: ✅ Có {pullback_info['candles_count']} nến hồi nhỏ")
                print(f"     - Entry: {entry_text}")
                print(f"     - SL: {signal_info['sl_usd']:.2f} USD | TP: {signal_info['tp_usd']:.2f} USD ({signal_info['rr_ratio']:.1f}R)")
                if signal_info['momentum_strong']:
                    print(f"     - Momentum mạnh: TP = {signal_info['rr_ratio']:.1f}R")
                print(f"     - Volume: {VOLUME}")
                
                # Kiểm tra cooldown sau lệnh thua
                print(f"\n  ┌─ [COOLDOWN] Kiểm tra cooldown sau lệnh thua")
                cooldown_allowed, cooldown_message = check_last_loss_cooldown()
                print(f"    {cooldown_message}")
                print(f"  └─ [COOLDOWN] Kết quả: {'OK' if cooldown_allowed else 'BLOCKED'}")
                
                if not cooldown_allowed:
                    print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI COOLDOWN SAU LỆNH THUA:")
                    print(f"     - {cooldown_message}")
                    
                    # Không ghi log khi bị chặn bởi loss cooldown (chỉ in ra console)
                else:
                    # Xác định loại lệnh
                    trade_type = mt5.ORDER_TYPE_SELL if trend == 'SELL' else mt5.ORDER_TYPE_BUY
                    trade_direction = "SELL" if trend == 'SELL' else "BUY"
                    
                    # Ghi log trước khi gửi lệnh
                    logger.info("=" * 70)
                    logger.info(f"🎯 TÍN HIỆU {trade_direction} - CHUẨN BỊ GỬI LỆNH")
                    logger.info(f"Trend: {trend}")
                    if momentum_info:
                        logger.info(f"Momentum: Index={momentum_info.get('index', 'N/A')}, High={momentum_info.get('high', 0):.5f}, Low={momentum_info.get('low', 0):.5f}, Body Ratio={momentum_info.get('body_ratio', 0):.1%}")
                    if pullback_info:
                        if pullback_info.get('direction') == 'SELL':
                            logger.info(f"Pullback: {pullback_info.get('candles_count', 0)} candles, Last High={pullback_info.get('last_pullback_high', 0):.5f}")
                        else:
                            logger.info(f"Pullback: {pullback_info.get('candles_count', 0)} candles, Last Low={pullback_info.get('last_pullback_low', 0):.5f}")
                    if atr_pips_log is not None:
                        logger.info(f"ATR: {atr_pips_log:.2f} pips")
                    logger.info(f"Entry Signal: {signal_info.get('entry_price', 0):.5f} | SL: {signal_info.get('sl_usd', 0):.2f} USD | TP: {signal_info.get('tp_usd', 0):.2f} USD ({signal_info.get('rr_ratio', 0):.1f}R)")
                    logger.info("=" * 70)
                    
                    send_order(trade_type, VOLUME, signal_info, trend_info=trend, momentum_info=momentum_info, pullback_info=pullback_info, atr_pips=atr_pips_log)
            else:
                # Không ghi log khi không vào lệnh (chỉ in ra console)
                print(f"  ⚠️ [QUYẾT ĐỊNH] Chưa đủ điều kiện vào lệnh:")
                if trend not in ['SELL', 'BUY']:
                    print(f"     - Trend: {trend} (Cần xu hướng rõ ràng: BUY hoặc SELL)")
                elif not has_momentum:
                    print(f"     - Momentum: ❌ Chưa có nến momentum {trend}")
                elif not has_pullback:
                    print(f"     - Pullback: ❌ Chưa có pullback sau momentum")
                elif not has_signal:
                    if trend == 'SELL':
                        print(f"     - Signal: ❌ Giá chưa phá đáy nến hồi cuối")
                    else:
                        print(f"     - Signal: ❌ Giá chưa phá đỉnh nến hồi cuối")
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