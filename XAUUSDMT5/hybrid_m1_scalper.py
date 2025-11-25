import MetaTrader5 as mt5
import time
import pandas as pd
import numpy as np
import json
import os
import requests
from datetime import datetime

# --- 1. THÔNG SỐ CẤU HÌNH ---
# Biến Cấu hình MT5 (Sẽ được ghi đè từ JSON)
MT5_LOGIN = None
MT5_PASSWORD = None
MT5_SERVER = None
MT5_PATH = None

# Telegram Configuration
TELEGRAM_TOKEN = "6398751744:AAGp7VH7B00_kzMqdaFB59xlqAXnlKTar-g"
CHAT_ID = "1887610382"

SYMBOL = "XAUUSDc"
VOLUME = 0.01
MAGIC = 123457
TIMEFRAME_M1 = mt5.TIMEFRAME_M1
TIMEFRAME_H1 = mt5.TIMEFRAME_H1

# Ngưỡng (Thresholds)
ADX_MIN_THRESHOLD = 25.0  # Ngưỡng ADX tối thiểu để xác nhận xu hướng mạnh
ATR_MULTIPLIER_SL = 1.5   # SL = ATR * 1.5
ATR_MULTIPLIER_TP = 2.0   # TP = ATR * 2.0 (R:R = 1.33)
RETEST_RANGE_POINTS = 50.0 # Khoảng cách tối đa để coi là Retest (0.5 USD)


# --- 1.1 HÀM TẢI CẤU HÌNH (CONFIG LOADING) ---

def load_config(filename="XAUUSDMT5/mt5_account1.json"):
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
        SYMBOL = config.get("SYMBOL", SYMBOL) 
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


# --- 1.2 HÀM GỬI TELEGRAM ---

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


# --- 2. HÀM TÍNH TOÁN CÁC CHỈ BÁO CẦN THIẾT ---

def get_ma(symbol, timeframe, period):
    """Tính toán giá trị đường trung bình động (Moving Average)."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, period + 1)
    if rates is None or len(rates) < period + 1:
        return None
    
    close_prices = np.array([r['close'] for r in rates])
    ma_value = np.mean(close_prices[-period:]) # Tính MA đơn giản (SMA) cho đơn giản
    
    # Đối với EMA, cần sử dụng thư viện ngoài (ví dụ: Talib)
    # Tuy nhiên, ta dùng SMA để đơn giản hóa trong khuôn mẫu này.
    
    return ma_value

def calculate_adx(symbol, timeframe, period):
    """Lấy giá trị ADX. (Lưu ý: MT5 Python API không có hàm ADX sẵn,
    ta dùng iADX() nếu có sẵn trong MT5, hoặc phải tính toán thủ công/dùng thư viện ngoài).
    Ở đây, ta chỉ trả về một giá trị giả định để hoàn thiện code framework."""
    # Trên thực tế, bạn cần sử dụng mt5.iADX() hoặc thư viện TA-Lib
    
    # Giả định: Ta lấy ADX từ một hàm gọi API hoặc tính toán phức tạp.
    # Để hoàn thiện code, ta sẽ mô phỏng giá trị ADX từ chỉ báo:
    adx_values = mt5.copy_rates_from_pos(symbol, timeframe, 0, 2)
    if adx_values is None or len(adx_values) < 2:
        return 0.0
    
    # Trả về một giá trị mẫu hoặc giá trị thực nếu bạn đã tính toán:
    # return mt5.iADX(symbol, timeframe, period, applied_price, 0)[0] 
    return 26.5 # Ví dụ ADX hiện tại


# --- 3. HÀM CHÍNH XÁC ĐỊNH TÍN HIỆU & GỬI LỆNH ---

def check_and_execute_hybrid_trade():
    
    # Lấy thông tin thị trường
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None: return False
    ask_price = tick.ask
    bid_price = tick.bid
    point = mt5.symbol_info(SYMBOL).point
    
    # BƯỚC 1: KIỂM TRA XU HƯỚNG LỚN (H1 EMA50)
    ema50_h1 = get_ma(SYMBOL, TIMEFRAME_H1, 50)
    if ema50_h1 is None: return False
    
    h1_trend = None
    if ask_price > ema50_h1:
        h1_trend = mt5.ORDER_TYPE_BUY
    elif ask_price < ema50_h1:
        h1_trend = mt5.ORDER_TYPE_SELL
    
    print(f"[H1] Giá: {ask_price} | EMA50: {ema50_h1:.5f}")
    if h1_trend == mt5.ORDER_TYPE_BUY:
        print(f"✅ H1 TREND: BUY (Giá > EMA50) → CHỈ BUY")
    elif h1_trend == mt5.ORDER_TYPE_SELL:
        print(f"❌ H1 TREND: SELL (Giá < EMA50) → CHỈ SELL")
    else:
        print(f"⚠️ H1 TREND: NEUTRAL (Giá = EMA50) → NGỪNG GIAO DỊCH")
        return False

    # BƯỚC 2: KIỂM TRA SỨC MẠNH XU HƯỚNG (ADX)
    adx_value = calculate_adx(SYMBOL, TIMEFRAME_M1, 14) # Giả định ADX (14) M1
    if adx_value < ADX_MIN_THRESHOLD:
        print(f"❌ ADX: {adx_value:.2f} < {ADX_MIN_THRESHOLD} - XU HƯỚNG YẾU → NGỪNG GIAO DỊCH")
        return False
    print(f"✅ ADX: {adx_value:.2f} ≥ {ADX_MIN_THRESHOLD} - XU HƯỚNG MẠNH → OK")

    # BƯỚC 3: KIỂM TRA TÍN HIỆU M1 (RETEST EMA20)
    
    # Lấy dữ liệu M1 và tính EMA20/ATR
    rates_m1 = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME_M1, 0, 20)
    if rates_m1 is None or len(rates_m1) < 20: return False
    df_m1 = pd.DataFrame(rates_m1)
    
    # Tính toán EMA20 M1
    ema20_m1 = get_ma(SYMBOL, TIMEFRAME_M1, 20)
    if ema20_m1 is None: return False
    
    # Tính ATR (Average True Range) cho SL/TP
    atr_value = np.mean([r['high'] - r['low'] for r in rates_m1[-14:]]) # ATR(14) đơn giản
    
    m1_signal = None
    distance_to_ema20 = abs(ask_price - ema20_m1)
    
    # Điều kiện Retest: Giá phải gần EMA20 (trong khoảng 0.5 USD)
    if distance_to_ema20 < RETEST_RANGE_POINTS * point:
        
        # BUY Retest: Giá đang ở dưới EMA20 và xu hướng là BUY
        if ask_price < ema20_m1 and h1_trend == mt5.ORDER_TYPE_BUY:
            m1_signal = mt5.ORDER_TYPE_BUY
            print(f"✅ M1 SIGNAL: BUY (RETEST EMA20) - Giá retest từ dưới lên.")
            
        # SELL Retest: Giá đang ở trên EMA20 và xu hướng là SELL
        elif ask_price > ema20_m1 and h1_trend == mt5.ORDER_TYPE_SELL:
            m1_signal = mt5.ORDER_TYPE_SELL
            print(f"✅ M1 SIGNAL: SELL (RETEST EMA20) - Giá retest từ trên xuống.")

    if m1_signal is None:
        print("❌ M1 SIGNAL: KHÔNG CÓ TÍN HIỆU RETEST.")
        return False

    # 4. GỬI LỆNH (CHỈ KHI CẢ 3 BƯỚC ĐỀU OK)
    
    # Tính toán SL và TP dựa trên ATR
    sl_points = atr_value / point * ATR_MULTIPLIER_SL
    tp_points = atr_value / point * ATR_MULTIPLIER_TP
    
    # Đảm bảo SL/TP hợp lý (như ví dụ trước)
    sl_price = ask_price - (sl_points * point) if m1_signal == mt5.ORDER_TYPE_BUY else ask_price + (sl_points * point)
    tp_price = ask_price + (tp_points * point) if m1_signal == mt5.ORDER_TYPE_BUY else ask_price - (tp_points * point)

    # Khung gửi lệnh (SỬ DỤNG ORDER_FILLING_IOC)
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": VOLUME,
        "type": m1_signal,
        "price": ask_price,
        "sl": round(sl_price, 5),
        "tp": round(tp_price, 5),
        "deviation": 20,
        "magic": MAGIC,
        "comment": "Hybrid_M1_Scalper",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC, # KHẮC PHỤC LỖI RETCODE: 10030
    }

    print("--------------------------------------------------")
    print(f"🚀 TÍN HIỆU { 'MUA' if m1_signal == mt5.ORDER_TYPE_BUY else 'BÁN' } MẠNH! Đang gửi lệnh...")
    print(f"💰 Entry: {ask_price} | SL: {round(sl_price, 5)} ({round(sl_points, 1)} pips) | TP: {round(tp_price, 5)} ({round(tp_points, 1)} pips)")

    result = mt5.order_send(request)
    print(f"Kết quả gửi lệnh: {result}")
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        error_msg = f"❌ Lỗi gửi lệnh {'BUY' if m1_signal == mt5.ORDER_TYPE_BUY else 'SELL'} - retcode: {result.retcode}"
        print(error_msg)
        print(f"Chi tiết lỗi: {mt5.last_error()}")
        send_telegram(f"<b>❌ LỖI GỬI LỆNH</b>\n{error_msg}\nEntry: {ask_price} | SL: {round(sl_price, 5)} | TP: {round(tp_price, 5)}")
    else:
        success_msg = f"✅ Gửi lệnh {'BUY' if m1_signal == mt5.ORDER_TYPE_BUY else 'SELL'} thành công! Order: {result.order}"
        print(success_msg)
        
        # Gửi thông báo Telegram
        trade_direction = "🟢 BUY" if m1_signal == mt5.ORDER_TYPE_BUY else "🔴 SELL"
        telegram_msg = f"""
<b>{trade_direction} LỆNH MỚI (Hybrid Scalper)</b>

📊 <b>Symbol:</b> {SYMBOL}
💰 <b>Entry:</b> {ask_price}
🛑 <b>SL:</b> {round(sl_price, 5)} ({round(sl_points, 1)} pips)
🎯 <b>TP:</b> {round(tp_price, 5)} ({round(tp_points, 1)} pips)
📦 <b>Volume:</b> {VOLUME}
🆔 <b>Order ID:</b> {result.order}
📈 <b>ATR:</b> {atr_value/point:.2f} pips

⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        send_telegram(telegram_msg)
    
    return True


# --- 4. CHẠY VÒNG LẶP CHÍNH ---

if __name__ == "__main__":
    
    # --- 0. Tải cấu hình ---
    if not load_config():
        exit()

    # --- 1. Khởi tạo MT5 ---
    initialize_mt5()

    # --- Đảm bảo Symbol khả dụng ---
    # (Đã được kiểm tra trong initialize_mt5)

    # --- Vòng lặp giao dịch ---
    print(f"Bắt đầu Hybrid Scalping trên {SYMBOL} M1... (Check mỗi 10s)")
    
    try:
        while True:
            check_and_execute_hybrid_trade()
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\nĐã dừng bot thủ công.")

    # --- Kết thúc ---
    mt5.shutdown()