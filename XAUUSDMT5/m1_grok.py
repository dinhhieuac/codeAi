from math import fabs
import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
import json
import os

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
# Chiến thuật M1: EMA Crossover + ATR-based SL/TP (theo m1_grok.md)
EMA_FAST = 14  # EMA 14 (fast, màu xanh)
EMA_SLOW = 28  # EMA 28 (slow, màu đỏ)
ATR_PERIOD = 14  # ATR 14 để tính SL/TP động

# Thông số Quản lý Lệnh (Tính bằng points, 10 points = 1 pip)
# Chiến thuật M1: SL/TP theo ATR (theo m1_grok.md)
# Theo m1_grok.md: "Ví dụ, nếu ATR = 0.5, SL = 15 pips"
# → ATR = 0.5 pips → SL = 0.5 × 30 = 15 pips
# Với XAUUSD: 1 pip = 10 points, 100 pips = 1 USD (lot 0.01)
ATR_SL_MULTIPLIER = 30  # SL = ATR(pips) × 30 (ví dụ: ATR = 0.5 pips → SL = 15 pips)
ATR_TP_MULTIPLIER = 30  # TP = ATR(pips) × 30 (RR 1:1)
SL_POINTS_MIN = 30   # SL tối thiểu: 3 pips (30 points) - bảo vệ
SL_POINTS_MAX = 50000  # SL tối đa: 5000 pips (50000 points) - cho phép SL lớn theo ATR
TP_POINTS_MIN = 30   # TP tối thiểu: 3 pips (30 points) - bảo vệ
TP_POINTS_MAX = 50000  # TP tối đa: 5000 pips (50000 points) - cho phép TP lớn theo ATR

# Hòa vốn (Break-Even)
ENABLE_BREAK_EVEN = False           # Bật/tắt chức năng di chuyển SL về hòa vốn
BREAK_EVEN_START_POINTS = 100      # Hòa vốn khi lời 10 pips (100 points)

# Trailing Stop khi lời 1/2 TP để lock profit
TRAILING_START_TP_RATIO = 0.5  # Bắt đầu trailing khi lời 1/2 TP
TRAILING_STEP_ATR_MULTIPLIER = 0.5  # Bước trailing = ATR × 0.5

# Risk Management
RISK_PER_TRADE_PERCENT = 0.5  # Risk max 0.5-1% tài khoản per trade
MAX_TRADES_PER_DAY = 100  # Chỉ 2-5 trade/ngày, tránh overtrade trên M1


SESSION_ALLOW=False
# ==============================================================================
# 2. HÀM TẢI CẤU HÌNH (CONFIG LOADING)
# ==============================================================================

def load_config(filename="XAUUSDMT5/mt5_account.json"):
    """Đọc thông tin cấu hình từ tệp JSON và gán vào biến toàn cục."""
    global MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, SYMBOL, MT5_PATH, VOLUME
    
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
# 4. CÁC HÀM PHÂN TÍCH KỸ THUẬT (INDICATORS & ANALYSIS)
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

def check_trading_session():
    """
    Kiểm tra session giao dịch hiện tại
    
    Theo m1_grok.md: Chỉ trade nếu đang ở session volatile như London hoặc New York
    (tránh Asian range-bound)
    
    Returns:
        'LONDON', 'NEW_YORK', 'ASIAN', hoặc 'UNKNOWN'
    """
    from datetime import datetime
    if not SESSION_ALLOW:
        return "UNKNOWN"
    try:
        import pytz
    except ImportError:
        print("  ⚠️ [SESSION] pytz không được cài đặt, dùng timezone mặc định")
        return 'UNKNOWN'
    
    # Lấy thời gian hiện tại UTC
    now_utc = datetime.utcnow()
    
    # Chuyển sang giờ London (GMT)
    london_tz = pytz.timezone('Europe/London')
    now_london = now_utc.replace(tzinfo=pytz.UTC).astimezone(london_tz)
    hour_london = now_london.hour
    
    # Session Asian: 00:00 - 08:00 GMT (tránh)
    # Session London: 08:00 - 16:00 GMT (volatile, nên trade)
    # Session New York: 13:00 - 21:00 GMT (volatile, nên trade)
    
    if 0 <= hour_london < 8:
        return 'ASIAN'
    elif 8 <= hour_london < 13:
        return 'LONDON'
    elif 13 <= hour_london < 21:
        return 'NEW_YORK'  # Overlap với London (13:00-16:00) và New York riêng (16:00-21:00)
    else:
        return 'ASIAN'  # 21:00-24:00 GMT thuộc Asian session
    
def check_ema_crossover(df_m1):
    """
    Kiểm tra EMA crossover trên M1
    
    Theo m1_grok.md:
    - Buy (Long): Khi EMA 14 cắt lên trên EMA 28
    - Sell (Short): Khi EMA 14 cắt xuống dưới EMA 28
    
    Args:
        df_m1: DataFrame M1
        
    Returns:
        'BUY', 'SELL', hoặc 'NONE'
    """
    if len(df_m1) < EMA_SLOW + 1:
        print("  📈 [EMA CROSSOVER] Không đủ dữ liệu để tính EMA")
        return 'NONE'
    
    # Tính EMA 14 và EMA 28
    ema_fast = calculate_ema(df_m1, EMA_FAST)
    ema_slow = calculate_ema(df_m1, EMA_SLOW)
    
    ema_fast_current = ema_fast.iloc[-1]
    ema_slow_current = ema_slow.iloc[-1]
    ema_fast_prev = ema_fast.iloc[-2]
    ema_slow_prev = ema_slow.iloc[-2]
    
    print(f"  📈 [EMA CROSSOVER] EMA14: {ema_fast_current:.5f} | EMA28: {ema_slow_current:.5f}")
    print(f"    EMA14 (trước): {ema_fast_prev:.5f} | EMA28 (trước): {ema_slow_prev:.5f}")
    
    # Giao cắt Mua (EMA 14 cắt lên EMA 28)
    is_buy_cross = (ema_fast_prev <= ema_slow_prev) and (ema_fast_current > ema_slow_current)
    
    # Giao cắt Bán (EMA 14 cắt xuống EMA 28)
    is_sell_cross = (ema_fast_prev >= ema_slow_prev) and (ema_fast_current < ema_slow_current)
    
    if is_buy_cross:
        print(f"    ✅ [EMA CROSSOVER] PHÁT HIỆN GIAO CẮT MUA! (EMA14 cắt lên EMA28)")
        return 'BUY'
    elif is_sell_cross:
        print(f"    ✅ [EMA CROSSOVER] PHÁT HIỆN GIAO CẮT BÁN! (EMA14 cắt xuống EMA28)")
        return 'SELL'
    else:
        print(f"    ⚠️ [EMA CROSSOVER] Chưa có giao cắt (NONE)")
        return 'NONE'

# ==============================================================================
# 5. HÀM GIAO DỊCH VÀ QUẢN LÝ LỆNH (TRADING & MANAGEMENT)
# ==============================================================================

def get_symbol_info():
    """Lấy thông tin ký hiệu giao dịch (spread, tick size, points)."""
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        return None
    
    point = symbol_info.point 
    return point

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
    
    # Tính SL và TP theo ATR của nến M1 (theo m1_grok.md: ATR × 30)
    # Lưu ý: Với XAUUSD, lot 0.01: 100 pips = 1 USD
    # ATR đã được tính trực tiếp trong pips từ calculate_atr_from_m1()
    if df_m1 is not None:
        atr_pips = calculate_atr_from_m1(df_m1)
        if atr_pips is not None:
            # ATR đã là pips, tính SL và TP trực tiếp
            sl_pips = atr_pips * ATR_SL_MULTIPLIER
            tp_pips = atr_pips * ATR_TP_MULTIPLIER
            
            # Chuyển pips sang points (1 pip = 10 points cho XAUUSD)
            sl_points = sl_pips * 10
            tp_points = tp_pips * 10
            
            # Giới hạn SL/TP trong khoảng min-max (đã là points)
            sl_points = max(SL_POINTS_MIN, min(sl_points, SL_POINTS_MAX))
            tp_points = max(TP_POINTS_MIN, min(tp_points, TP_POINTS_MAX))
            
            # Tính lại pips sau khi giới hạn (để hiển thị đúng)
            sl_pips_limited = sl_points / 10
            tp_pips_limited = tp_points / 10
            
            print(f"  📊 [ORDER] ATR(M1): {atr_pips:.2f} pips → SL: {sl_pips_limited:.1f} pips (ATR×{ATR_SL_MULTIPLIER}, giới hạn {SL_POINTS_MIN/10}-{SL_POINTS_MAX/10} pips), TP: {tp_pips_limited:.1f} pips (ATR×{ATR_TP_MULTIPLIER}, giới hạn {TP_POINTS_MIN/10}-{TP_POINTS_MAX/10} pips, RR 1:1)")
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
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }

    result = mt5.order_send(request)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ Lỗi gửi lệnh {'BUY' if trade_type == mt5.ORDER_TYPE_BUY else 'SELL'} - retcode: {result.retcode}")
        print(f"Chi tiết lỗi: {mt5.last_error()}")
    else:
        print(f"✅ Gửi lệnh {'BUY' if trade_type == mt5.ORDER_TYPE_BUY else 'SELL'} thành công! Order: {result.order}")

def manage_positions():
    """
    Quản lý các lệnh đang mở (Trailing Stop khi lời 1/2 TP).
    
    Theo m1_grok.md: Trail SL khi lời 1/2 TP để lock profit nếu trend mạnh.
    """
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
            new_sl_price = entry_price + pips_buffer if is_buy else entry_price - pips_buffer
            
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
        
        # --- LOGIC TRAILING STOP (theo m1_grok.md: trail SL khi lời 1/2 TP) ---
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
# 6. CHU TRÌNH CHÍNH (MAIN LOOP)
# ==============================================================================

def run_bot():
    """Chu trình chính của bot, lặp lại việc kiểm tra tín hiệu và quản lý lệnh."""
    
    # 0. Tải cấu hình
    if not load_config():
        return
        
    # 1. Khởi tạo MT5 và kết nối
    initialize_mt5()
    
    last_candle_time = datetime(1970, 1, 1)

    # Tracking số lệnh trong ngày
    daily_trades_count = 0
    last_trade_date = None
    
    print("\n--- Bắt đầu Chu Trình Giao Dịch M1 (Chiến thuật: EMA Crossover + ATR-based SL/TP) ---")
    print("📋 Chiến thuật (theo m1_grok.md):")
    print("   1. EMA 14 (fast) và EMA 28 (slow) trên M1")
    print("   2. Buy: EMA 14 cắt lên EMA 28 | Sell: EMA 14 cắt xuống EMA 28")
    print("   3. Chỉ trade trong session London hoặc New York (tránh Asian)")
    print("   4. SL/TP = ATR × 30 (RR 1:1)")
    print("   5. Trail SL khi lời 1/2 TP để lock profit")
    print("   6. Risk max 0.5-1% tài khoản per trade")
    print("   7. Chỉ 2-5 trade/ngày, tránh overtrade\n")
    
    while True:
        start_time = time.time() # Ghi lại thời gian bắt đầu chu kỳ
        current_time = datetime.now()
        
        # 2. Lấy dữ liệu M1
        df_m1 = get_rates(mt5.TIMEFRAME_M1)
        if df_m1 is None or len(df_m1) < EMA_SLOW + 1:
            print("Đang chờ dữ liệu M1...")
            time.sleep(5)
            continue
            
        # Nến cuối cùng (vừa đóng)
        current_candle_time = df_m1.index[-1].replace(tzinfo=None)
        
        # Reset daily trades count nếu sang ngày mới
        current_date = current_time.date()
        if last_trade_date is None or current_date != last_trade_date:
            daily_trades_count = 0
            last_trade_date = current_date
            print(f"📅 Ngày mới: {current_date} - Reset số lệnh trong ngày")
        
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
            
            # 1. Kiểm tra Trading Session (theo m1_grok.md)
            print(f"\n  ┌─ [BƯỚC 1] Kiểm tra Trading Session")
            session = check_trading_session()
            print(f"    Session hiện tại: {session}")
            
            if session == 'ASIAN':
                print(f"    ⚠️ [SESSION] Asian session (range-bound) → Tránh giao dịch")
                session_ok = False
            elif session in ['LONDON', 'NEW_YORK']:
                print(f"    ✅ [SESSION] {session} session (volatile) → Có thể giao dịch")
                session_ok = True
            else:
                print(f"    ⚠️ [SESSION] Unknown session → Tránh giao dịch")
                session_ok = False
            print(f"  └─ [BƯỚC 1] Kết quả: {'OK' if session_ok else 'BLOCKED'}")
            
            # 2. Kiểm tra EMA Crossover (theo m1_grok.md)
            print(f"\n  ┌─ [BƯỚC 2] Kiểm tra EMA Crossover (EMA14 vs EMA28)")
            ema_signal = check_ema_crossover(df_m1)
            print(f"  └─ [BƯỚC 2] Kết quả: {ema_signal}")

            # 3. Kiểm tra số lệnh trong ngày (theo m1_grok.md: chỉ 2-5 trade/ngày)
            print(f"\n  ┌─ [BƯỚC 3] Kiểm tra giới hạn số lệnh trong ngày")
            print(f"    Số lệnh hôm nay: {daily_trades_count}/{MAX_TRADES_PER_DAY}")
            
            if daily_trades_count >= MAX_TRADES_PER_DAY:
                daily_limit_ok = False
                print(f"    ⚠️ [DAILY LIMIT] Đã đạt giới hạn {MAX_TRADES_PER_DAY} lệnh/ngày → Tránh overtrade")
            else:
                daily_limit_ok = True
                print(f"    ✅ [DAILY LIMIT] Còn có thể giao dịch ({MAX_TRADES_PER_DAY - daily_trades_count} lệnh còn lại)")
            print(f"  └─ [BƯỚC 3] Kết quả: {'OK' if daily_limit_ok else 'BLOCKED'}")

            # 4. Kiểm tra vị thế đang mở
            open_positions = mt5.positions_total()
            print(f"\n  📋 [TRẠNG THÁI] Số lệnh đang mở: {open_positions}")
            
            print(f"\n  📊 [TÓM TẮT] Session={session} | EMA Signal={ema_signal} | Daily Trades={daily_trades_count}/{MAX_TRADES_PER_DAY}")

            if open_positions <=2:
                # Không có lệnh nào, tìm tín hiệu vào lệnh
                print(f"\n  🎯 [QUYẾT ĐỊNH] Không có lệnh đang mở, kiểm tra điều kiện vào lệnh...")
                
                # Kiểm tra tất cả điều kiện
                if not session_ok:
                    print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI SESSION FILTER:")
                    print(f"     - Session: {session} (Chỉ trade London/New York, tránh Asian)")
                elif not daily_limit_ok:
                    print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI DAILY LIMIT:")
                    print(f"     - Đã đạt {daily_trades_count}/{MAX_TRADES_PER_DAY} lệnh hôm nay → Tránh overtrade")
                elif ema_signal == 'BUY':
                    print(f"  ✅ [QUYẾT ĐỊNH] 🚀 TÍN HIỆU MUA!")
                    print(f"     - EMA Signal: {ema_signal} (EMA14 cắt lên EMA28)")
                    print(f"     - Session: {session} (Volatile)")
                    print(f"     - Volume: {VOLUME}")
                    send_order(mt5.ORDER_TYPE_BUY, VOLUME, df_m1)
                    daily_trades_count += 1
                    
                elif ema_signal == 'SELL':
                    print(f"  ✅ [QUYẾT ĐỊNH] 🔻 TÍN HIỆU BÁN!")
                    print(f"     - EMA Signal: {ema_signal} (EMA14 cắt xuống EMA28)")
                    print(f"     - Session: {session} (Volatile)")
                    print(f"     - Volume: {VOLUME}")
                    send_order(mt5.ORDER_TYPE_SELL, VOLUME, df_m1)
                    daily_trades_count += 1
                
                else:
                    print(f"  ⚠️ [QUYẾT ĐỊNH] Chưa có tín hiệu:")
                    if ema_signal == 'NONE':
                        print(f"     - EMA Signal: {ema_signal} (Chưa có crossover)")
            else:
                print(f"\n  ⏸️ [QUYẾT ĐỊNH] Đang có {open_positions} lệnh mở, bỏ qua tín hiệu mới.")
            
            print(f"{'='*70}\n")
            
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