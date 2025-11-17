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
EMA_SHORT = 9
EMA_MEDIUM = 21
EMA_D1_H4_FAST = 50  # Lọc xu hướng nhanh trên D1/H4
EMA_D1_H4_SLOW = 200 # Lọc xu hướng chậm trên D1/H4
ATR_PERIOD = 14

# Thông số Quản lý Lệnh (Tính bằng points, 10 points = 1 pip)
SL_POINTS = 500                    # Cắt lỗ cố định (50 pips)
TP_FACTOR = 2.0                    # Chốt lời = SL * TP_FACTOR
BREAK_EVEN_START_POINTS = 500      # Hòa vốn khi lời 50 pips
TS_START_FACTOR = 1.3              # Bắt đầu Trailing Stop khi lời 1.3 * SL
TS_STEP_POINTS = 250               # Bước Trailing Stop (25 pips)

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

def check_multi_timeframe_bias():
    """Kiểm tra xu hướng lớn trên D1 và H4."""
    
    bias_up = 0
    bias_down = 0
    
    print("  📊 [MULTI-TIMEFRAME] Kiểm tra xu hướng D1 & H4...")
    
    # Lọc trên D1 (EMA 50 & 200)
    df_d1 = get_rates(mt5.TIMEFRAME_D1)
    if df_d1 is not None and len(df_d1) >= EMA_D1_H4_SLOW:
        ema_50_d1 = calculate_ema(df_d1, EMA_D1_H4_FAST).iloc[-1]
        ema_200_d1 = calculate_ema(df_d1, EMA_D1_H4_SLOW).iloc[-1]
        close_d1 = df_d1['close'].iloc[-1]
        
        print(f"    [D1] Giá: {close_d1:.5f} | EMA50: {ema_50_d1:.5f} | EMA200: {ema_200_d1:.5f}")
        
        if close_d1 > ema_50_d1 and ema_50_d1 > ema_200_d1:
            bias_up += 1
            print(f"    [D1] ✅ XU HƯỚNG MUA (Giá > EMA50 > EMA200)")
        elif close_d1 < ema_50_d1 and ema_50_d1 < ema_200_d1:
            bias_down += 1
            print(f"    [D1] ✅ XU HƯỚNG BÁN (Giá < EMA50 < EMA200)")
        else:
            print(f"    [D1] ⚠️ SIDEWAYS (Không rõ xu hướng)")
    else:
        print(f"    [D1] ❌ Không đủ dữ liệu để tính EMA")
            
    # Lọc trên H4 (EMA 50 & 200)
    df_h4 = get_rates(mt5.TIMEFRAME_H4)
    if df_h4 is not None and len(df_h4) >= EMA_D1_H4_SLOW:
        ema_50_h4 = calculate_ema(df_h4, EMA_D1_H4_FAST).iloc[-1]
        ema_200_h4 = calculate_ema(df_h4, EMA_D1_H4_SLOW).iloc[-1]
        close_h4 = df_h4['close'].iloc[-1]
        
        print(f"    [H4] Giá: {close_h4:.5f} | EMA50: {ema_50_h4:.5f} | EMA200: {ema_200_h4:.5f}")
        
        if close_h4 > ema_50_h4 and ema_50_h4 > ema_200_h4:
            bias_up += 1
            print(f"    [H4] ✅ XU HƯỚNG MUA (Giá > EMA50 > EMA200)")
        elif close_h4 < ema_50_h4 and ema_50_h4 < ema_200_h4:
            bias_down += 1
            print(f"    [H4] ✅ XU HƯỚNG BÁN (Giá < EMA50 < EMA200)")
        else:
            print(f"    [H4] ⚠️ SIDEWAYS (Không rõ xu hướng)")
    else:
        print(f"    [H4] ❌ Không đủ dữ liệu để tính EMA")
    
    print(f"  📊 [MULTI-TIMEFRAME] Tổng kết: bias_up={bias_up}, bias_down={bias_down}")
            
    if bias_up >= 2:
        print(f"  📊 [MULTI-TIMEFRAME] KẾT QUẢ: BUY (≥2 khung thời gian đồng ý MUA)")
        return 'BUY'
    elif bias_down >= 2:
        print(f"  📊 [MULTI-TIMEFRAME] KẾT QUẢ: SELL (≥2 khung thời gian đồng ý BÁN)")
        return 'SELL'
    else:
        print(f"  📊 [MULTI-TIMEFRAME] KẾT QUẢ: SIDEWAYS (Không đủ đồng thuận)")
        return 'SIDEWAYS'

def check_m5_entry_signals(ema_short, ema_medium, prev_ema_short, prev_ema_medium):
    """Kiểm tra tín hiệu giao cắt EMA trên M5."""
    
    print("  📈 [M5 SIGNAL] Kiểm tra giao cắt EMA...")
    print(f"    EMA9 (hiện tại): {ema_short:.5f} | EMA21 (hiện tại): {ema_medium:.5f}")
    print(f"    EMA9 (trước đó): {prev_ema_short:.5f} | EMA21 (trước đó): {prev_ema_medium:.5f}")
    
    # Kiểm tra vị trí hiện tại
    current_position = "EMA9 > EMA21" if ema_short > ema_medium else "EMA9 < EMA21"
    prev_position = "EMA9 > EMA21" if prev_ema_short > prev_ema_medium else "EMA9 < EMA21"
    print(f"    Vị trí trước: {prev_position} | Vị trí hiện tại: {current_position}")
    
    # Giao cắt Mua (EMA ngắn cắt lên EMA dài)
    is_buy_cross = (prev_ema_short < prev_ema_medium) and (ema_short > ema_medium)
    
    # Giao cắt Bán (EMA ngắn cắt xuống EMA dài)
    is_sell_cross = (prev_ema_short > prev_ema_medium) and (ema_short < ema_medium)
    
    if is_buy_cross:
        print(f"    ✅ [M5 SIGNAL] PHÁT HIỆN GIAO CẮT MUA! (EMA9 cắt lên EMA21)")
        return 'BUY'
    elif is_sell_cross:
        print(f"    ✅ [M5 SIGNAL] PHÁT HIỆN GIAO CẮT BÁN! (EMA9 cắt xuống EMA21)")
        return 'SELL'
    else:
        print(f"    ⚠️ [M5 SIGNAL] Chưa có giao cắt (NONE)")
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

def send_order(trade_type, volume, deviation=20):
    """Gửi lệnh Market Execution."""
    
    point = get_symbol_info()
    if point is None:
        print("❌ Lỗi: Không thể lấy thông tin ký hiệu để gửi lệnh.")
        return
        
    tick_info = mt5.symbol_info_tick(SYMBOL)
    price = tick_info.ask if trade_type == mt5.ORDER_TYPE_BUY else tick_info.bid
    
    # Tính SL và TP dựa trên SL_POINTS và TP_FACTOR
    sl_distance = SL_POINTS * point
    tp_distance = sl_distance * TP_FACTOR
    
    if trade_type == mt5.ORDER_TYPE_BUY:
        sl = price - sl_distance
        tp = price + tp_distance
    else: # SELL
        sl = price + sl_distance
        tp = price - tp_distance
        
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
        ts_start_level = SL_POINTS * TS_START_FACTOR 

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

    print("\n--- Bắt đầu Chu Trình Giao Dịch (Check 30s/lần) ---")
    
    while True:
        start_time = time.time() # Ghi lại thời gian bắt đầu chu kỳ
        current_time = datetime.now()
        
        # 2. Lấy dữ liệu M5
        df_m5 = get_rates(mt5.TIMEFRAME_M5)
        if df_m5 is None or len(df_m5) < EMA_MEDIUM + 1:
            print("Đang chờ dữ liệu M5...")
            time.sleep(5)
            continue
            
        # Nến cuối cùng (vừa đóng)
        current_candle_time = df_m5.index[-1].replace(tzinfo=None)
        
        # 3. CHỈ XỬ LÝ TÍN HIỆU KHI CÓ NẾN MỚI ĐÓNG
        if current_candle_time > last_candle_time:
            last_candle_time = current_candle_time
            print(f"\n{'='*70}")
            print(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] 🔔 XỬ LÝ NẾN MỚI M5: {current_candle_time}")
            print(f"{'='*70}")
            
            # Lấy giá hiện tại
            tick = mt5.symbol_info_tick(SYMBOL)
            current_price = tick.bid
            current_ask = tick.ask
            print(f"  💰 Giá hiện tại: BID={current_price:.5f} | ASK={current_ask:.5f} | Spread={(current_ask-current_price):.5f}")
            
            # --- TÍNH TOÁN CHỈ BÁO TRÊN M5 ---
            print(f"\n  📊 [M5] Tính toán chỉ báo EMA...")
            ema_short_values = calculate_ema(df_m5, EMA_SHORT)
            ema_medium_values = calculate_ema(df_m5, EMA_MEDIUM)
            
            ema_short = ema_short_values.iloc[-1]
            ema_medium = ema_medium_values.iloc[-1]
            prev_ema_short = ema_short_values.iloc[-2]
            prev_ema_medium = ema_medium_values.iloc[-2]
            
            close_m5 = df_m5['close'].iloc[-1]
            print(f"  📊 [M5] Giá đóng cửa nến cuối: {close_m5:.5f}")

            # --- KIỂM TRA TÍN HIỆU VÀ LỌC ---
            print(f"\n  🔍 [KIỂM TRA TÍN HIỆU] Bắt đầu phân tích...")
            
            # 1. Tín hiệu M5 (Giao cắt EMA)
            print(f"\n  ┌─ [BƯỚC 1] Kiểm tra tín hiệu M5 (Giao cắt EMA)")
            m5_signal = check_m5_entry_signals(ema_short, ema_medium, prev_ema_short, prev_ema_medium)
            print(f"  └─ [BƯỚC 1] Kết quả: {m5_signal}")
            
            # 2. Lọc Xu hướng Đa khung (H4/D1) - *Chiếm nhiều tài nguyên nhất*
            print(f"\n  ┌─ [BƯỚC 2] Kiểm tra xu hướng đa khung (D1 & H4)")
            multi_bias = check_multi_timeframe_bias()
            print(f"  └─ [BƯỚC 2] Kết quả: {multi_bias}")

            # 3. Kiểm tra vị thế đang mở
            open_positions = mt5.positions_total()
            print(f"\n  📋 [TRẠNG THÁI] Số lệnh đang mở: {open_positions}")
            
            print(f"\n  📊 [TÓM TẮT] EMA9={ema_short:.5f} | EMA21={ema_medium:.5f} | M5 Signal={m5_signal} | Multi-Bias={multi_bias}")

            if open_positions == 0:
                # Không có lệnh nào, tìm tín hiệu vào lệnh
                print(f"\n  🎯 [QUYẾT ĐỊNH] Không có lệnh đang mở, kiểm tra điều kiện vào lệnh...")
                
                if m5_signal == 'BUY' and multi_bias == 'BUY':
                    print(f"  ✅ [QUYẾT ĐỊNH] 🚀 TÍN HIỆU MUA MẠNH!")
                    print(f"     - M5 Signal: {m5_signal} (EMA9 cắt lên EMA21)")
                    print(f"     - Multi-Bias: {multi_bias} (Xu hướng lớn đồng ý MUA)")
                    print(f"     - Volume: {VOLUME}")
                    send_order(mt5.ORDER_TYPE_BUY, VOLUME)
                    
                elif m5_signal == 'SELL' and multi_bias == 'SELL':
                    print(f"  ✅ [QUYẾT ĐỊNH] 🔻 TÍN HIỆU BÁN MẠNH!")
                    print(f"     - M5 Signal: {m5_signal} (EMA9 cắt xuống EMA21)")
                    print(f"     - Multi-Bias: {multi_bias} (Xu hướng lớn đồng ý BÁN)")
                    print(f"     - Volume: {VOLUME}")
                    send_order(mt5.ORDER_TYPE_SELL, VOLUME)
                
                else:
                    print(f"  ⚠️ [QUYẾT ĐỊNH] Chưa đủ điều kiện vào lệnh:")
                    if m5_signal == 'NONE':
                        print(f"     - M5 Signal: {m5_signal} (Chưa có giao cắt EMA)")
                    elif m5_signal == 'BUY' and multi_bias != 'BUY':
                        print(f"     - M5 Signal: {m5_signal} nhưng Multi-Bias: {multi_bias} (Không đồng ý)")
                    elif m5_signal == 'SELL' and multi_bias != 'SELL':
                        print(f"     - M5 Signal: {m5_signal} nhưng Multi-Bias: {multi_bias} (Không đồng ý)")
            else:
                print(f"\n  ⏸️ [QUYẾT ĐỊNH] Đang có {open_positions} lệnh mở, bỏ qua tín hiệu mới.")
            
            print(f"{'='*70}\n")
            
        # 4. QUẢN LÝ LỆNH (CHẠY MỖI VÒNG LẶP ĐỂ BẮT BE/TS KỊP THỜI)
        manage_positions()
        
        # 5. ĐIỀU CHỈNH THỜI GIAN NGỦ ĐỂ ĐẠT CHU KỲ 30 GIÂY
        elapsed_time = time.time() - start_time
        sleep_time = 30 - elapsed_time
        
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            # Nếu thời gian xử lý quá 30s (ví dụ do mạng lag/MTF check quá lâu), thì không ngủ
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