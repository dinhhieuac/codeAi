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
# Chiến thuật M1: "BÁM THEO H1 – ĂN 5–10 PHÚT"
EMA_H1 = 50  # EMA50 trên H1 để xác định trend
EMA_M1 = 20  # EMA20 trên M1 để tìm điểm retest
ATR_PERIOD = 14
ADX_PERIOD = 14  # Chu kỳ tính ADX
ADX_MIN_THRESHOLD = 25  # ADX tối thiểu để giao dịch (tránh thị trường đi ngang)

# Thông số Quản lý Lệnh (Tính bằng points, 10 points = 1 pip)
# Chiến thuật M1: SL/TP theo nến M1
SL_ATR_MULTIPLIER = 1.5  # SL = ATR(M1) × 1.5
TP_ATR_MULTIPLIER = 2.0  # TP = ATR(M1) × 2.0
SL_POINTS_MIN = 50   # SL tối thiểu: 5 pips (50 points) - bảo vệ
SL_POINTS_MAX = 200  # SL tối đa: 20 pips (200 points) - giới hạn rủi ro
TP_POINTS_MIN = 80   # TP tối thiểu: 8 pips (80 points) - bảo vệ
TP_POINTS_MAX = 300  # TP tối đa: 30 pips (300 points) - giới hạn
BREAK_EVEN_START_POINTS = 100      # Hòa vốn khi lời 10 pips
TS_START_FACTOR = 1.3              # Bắt đầu Trailing Stop khi lời 1.3 * SL
TS_STEP_POINTS = 50                # Bước Trailing Stop (5 pips)

# Khoảng cách retest EMA20 trên M1 (points)
# Giá chạm EMA20 hoặc dưới 3-6 pip (30-60 points)
RETEST_DISTANCE_MAX = 60  # Tối đa 6 pips (60 points) từ EMA20

# Chiến thuật BREAKOUT (khi giá không retest)
ADX_BREAKOUT_THRESHOLD = 28  # ADX > 28 để breakout
BREAKOUT_DISTANCE_MIN = 100  # Khoảng cách tối thiểu từ EMA20: 10 pips (100 points)
BREAKOUT_DISTANCE_MAX = 200  # Khoảng cách tối đa từ EMA20: 20 pips (200 points)

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
        ATR value (points) hoặc None nếu không đủ dữ liệu
    """
    if df_m1 is None or len(df_m1) < period + 1:
        return None
    
    high = df_m1['high']
    low = df_m1['low']
    close = df_m1['close']
    
    # Tính True Range (TR)
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Tính ATR (trung bình của TR)
    atr = tr.rolling(window=period).mean().iloc[-1]
    
    return atr

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
    
    # Tính SL và TP theo ATR của nến M1
    if df_m1 is not None:
        atr_value = calculate_atr_from_m1(df_m1)
        if atr_value is not None:
            # Chuyển ATR từ giá sang points
            atr_points = atr_value / point
            
            # Tính SL và TP dựa trên ATR
            sl_points = atr_points * SL_ATR_MULTIPLIER
            tp_points = atr_points * TP_ATR_MULTIPLIER
            
            # Giới hạn SL/TP trong khoảng min-max
            sl_points = max(SL_POINTS_MIN, min(sl_points, SL_POINTS_MAX))
            tp_points = max(TP_POINTS_MIN, min(tp_points, TP_POINTS_MAX))
            
            print(f"  📊 [ORDER] ATR(M1): {atr_points/10:.1f} pips → SL: {sl_points/10:.1f} pips, TP: {tp_points/10:.1f} pips")
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
        sl = price - sl_distance
        tp = price + tp_distance
    else: # SELL
        sl = price + sl_distance
        tp = price - tp_distance
    
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

    for pos in positions:
        if pos.magic != MAGIC: # Chỉ quản lý lệnh của bot này
            continue
            
        is_buy = pos.type == mt5.POSITION_TYPE_BUY
        current_price = current_bid if is_buy else current_ask
        
        # Lợi nhuận hiện tại tính bằng điểm (points)
        profit_points = abs(current_price - pos.price_open) / point
        
        # --- LOGIC HÒA VỐN (BREAK EVEN) ---
        if BREAK_EVEN_START_POINTS > 0 and profit_points >= BREAK_EVEN_START_POINTS:
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

        # --- LOGIC TRAILING STOP (TS) ---
        sl_points_avg = (SL_POINTS_MIN + SL_POINTS_MAX) // 2  # ~12 pips
        ts_start_level = sl_points_avg * TS_START_FACTOR 

        if profit_points >= ts_start_level:
            
            if is_buy:
                # TS cho lệnh BUY: SL mới = current_bid - TS_STEP_POINTS (tính bằng point)
                new_sl_ts = current_bid - (TS_STEP_POINTS * point)
                # Chỉ cập nhật nếu SL mới cao hơn SL hiện tại (di chuyển lên)
                if new_sl_ts > pos.sl:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "sl": new_sl_ts,
                        "tp": pos.tp,
                        "magic": MAGIC,
                        "deviation": 20,
                    }
                    mt5.order_send(request)
                    print(f"⏫ Lệnh {pos.ticket} BUY: Trailing Stop cập nhật lên {new_sl_ts}.")
            else: # SELL
                # TS cho lệnh SELL: SL mới = current_ask + TS_STEP_POINTS (tính bằng point)
                new_sl_ts = current_ask + (TS_STEP_POINTS * point)
                # Chỉ cập nhật nếu SL mới thấp hơn SL hiện tại (di chuyển xuống)
                if new_sl_ts < pos.sl or pos.sl == 0.0:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "sl": new_sl_ts,
                        "tp": pos.tp,
                        "magic": MAGIC,
                        "deviation": 20,
                    }
                    mt5.order_send(request)
                    print(f"⏬ Lệnh {pos.ticket} SELL: Trailing Stop cập nhật xuống {new_sl_ts}.")

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

            # 4. Kiểm tra vị thế đang mở
            open_positions = mt5.positions_total()
            print(f"\n  📋 [TRẠNG THÁI] Số lệnh đang mở: {open_positions}")
            
            signal_type = "RETEST" if m1_retest_signal != 'NONE' else ("BREAKOUT" if m1_breakout_signal != 'NONE' else "NONE")
            print(f"\n  📊 [TÓM TẮT] H1 Trend={h1_trend} | M1 Signal={m1_signal} ({signal_type}) | ADX={adx_current:.2f}")

            if open_positions == 0:
                # Không có lệnh nào, tìm tín hiệu vào lệnh
                print(f"\n  🎯 [QUYẾT ĐỊNH] Không có lệnh đang mở, kiểm tra điều kiện vào lệnh...")
                
                # ⚠️ QUAN TRỌNG: Kiểm tra ADX trước khi vào lệnh
                # - RETEST: ADX >= 25 (ADX_MIN_THRESHOLD)
                # - BREAKOUT: ADX > 28 (ADX_BREAKOUT_THRESHOLD) - đã check trong check_m1_breakout
                if signal_type == "RETEST" and not adx_ok:
                    print(f"  ⚠️ [QUYẾT ĐỊNH] BỊ CHẶN BỞI ADX FILTER:")
                    print(f"     - ADX: {adx_current:.2f} < {ADX_MIN_THRESHOLD} (Thị trường đi ngang)")
                    print(f"     - Không giao dịch khi thị trường đi ngang để tránh false signals")
                elif m1_signal == 'BUY' and h1_trend == 'BUY':
                    print(f"  ✅ [QUYẾT ĐỊNH] 🚀 TÍN HIỆU MUA MẠNH!")
                    print(f"     - H1 Trend: {h1_trend} (Giá > EMA50)")
                    print(f"     - M1 Signal: {m1_signal} ({signal_type})")
                    if signal_type == "RETEST":
                        print(f"       → Giá retest EMA20 từ dưới lên")
                    elif signal_type == "BREAKOUT":
                        print(f"       → Giá phá đỉnh gần nhất (Breakout momentum)")
                    print(f"     - ADX: {adx_current:.2f} (Xu hướng mạnh)")
                    print(f"     - Volume: {VOLUME}")
                    send_order(mt5.ORDER_TYPE_BUY, VOLUME, df_m1)
                    
                elif m1_signal == 'SELL' and h1_trend == 'SELL':
                    print(f"  ✅ [QUYẾT ĐỊNH] 🔻 TÍN HIỆU BÁN MẠNH!")
                    print(f"     - H1 Trend: {h1_trend} (Giá < EMA50)")
                    print(f"     - M1 Signal: {m1_signal} ({signal_type})")
                    if signal_type == "RETEST":
                        print(f"       → Giá retest EMA20 từ trên xuống")
                    elif signal_type == "BREAKOUT":
                        print(f"       → Giá phá đáy gần nhất (Breakout momentum)")
                    print(f"     - ADX: {adx_current:.2f} (Xu hướng mạnh)")
                    print(f"     - Volume: {VOLUME}")
                    send_order(mt5.ORDER_TYPE_SELL, VOLUME, df_m1)
                
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