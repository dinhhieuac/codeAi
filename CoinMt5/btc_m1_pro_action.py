import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime, timedelta
import json
import os
import requests
import logging

# ==============================================================================
# 1. CẤU HÌNH CHIẾN THUẬT "PRO ACTION" (LIQUIDITY SWEEP)
# ==============================================================================

# Biến Cấu hình MT5 (Sẽ được ghi đè từ JSON)
MT5_LOGIN = None
MT5_PASSWORD = None
MT5_SERVER = None
SYMBOL = None
MT5_PATH = None
VOLUME = 0.01
MAGIC = 20251130 # Magic number mới

# --- THAM SỐ CHIẾN THUẬT ---
LOOKBACK_PERIOD = 20      # Số nến để xác định Đỉnh/Đáy gần nhất
MIN_SWEEP_PIPS = 1.0      # Giá phải quét qua cản ít nhất bao nhiêu USD (1 USD = 1 pip BTC)
MAX_BODY_RATIO = 0.6      # Thân nến không được quá lớn (ưu tiên Pinbar/Rút chân)
WICK_RATIO_MIN = 0.3      # Râu nến (phần quét) phải chiếm ít nhất 30% chiều dài nến

# --- QUẢN LÝ VỐN ---
SL_BUFFER = 2.0           # Buffer cho SL (USD)
RR_RATIO = 2.0            # Tỷ lệ Lời/Lỗ mục tiêu (2R)
MAX_SL_USD = 15.0         # SL tối đa chấp nhận được (USD)

# Telegram
TELEGRAM_TOKEN = "6398751744:AAGp7VH7B00_kzMqdaFB59xlqAXnlKTar-g"
CHAT_ID = "1887610382"

# ==============================================================================
# 2. HỆ THỐNG LOGGING & KẾT NỐI
# ==============================================================================

def setup_logging():
    bot_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(bot_dir, "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    bot_name = os.path.splitext(os.path.basename(__file__))[0]
    log_file = os.path.join(log_dir, f"{bot_name}.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.FileHandler(log_file, encoding='utf-8'), logging.StreamHandler()]
    )
    return logging.getLogger(__name__)

def load_config(filename=None):
    global MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, SYMBOL, MT5_PATH, VOLUME, CHAT_ID
    
    # Lấy đường dẫn thư mục chứa file bot
    bot_dir = os.path.dirname(os.path.abspath(__file__))
    
    if filename is None:
        filename = os.path.join(bot_dir, "mt5_account.json")
    elif not os.path.isabs(filename):
        # Nếu filename là đường dẫn tương đối, ghép với thư mục bot
        filename = os.path.join(bot_dir, filename)
    
    if not os.path.exists(filename):
        print(f"❌ Không tìm thấy config: {filename}")
        return False
        
    try:
        with open(filename, 'r') as f:
            config = json.load(f)
        MT5_LOGIN = config.get("ACCOUNT_NUMBER")
        MT5_PASSWORD = config.get("PASSWORD")
        MT5_SERVER = config.get("SERVER")
        SYMBOL = config.get("SYMBOL", "BTCUSDm")
        MT5_PATH = config.get("PATH")
        VOLUME = config.get("VOLUME", VOLUME)
        CHAT_ID = config.get("CHAT_ID", CHAT_ID)
        
        print(f"✅ Đã tải config từ: {filename}")
        return True
    except Exception as e:
        print(f"❌ Lỗi đọc config: {e}")
        return False

def initialize_mt5():
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            print(f"❌ Init thất bại: {mt5.last_error()}")
            return False
    print(f"✅ Đã kết nối MT5: {MT5_LOGIN} trên {MT5_SERVER}")
    mt5.symbol_select(SYMBOL, True)
    return True

def send_telegram(message):
    if not CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=5)
    except: pass

# ==============================================================================
# 3. LOGIC CHIẾN THUẬT: LIQUIDITY SWEEP (SĂN THANH KHOẢN)
# ==============================================================================

def get_rates(bars=100):
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, bars)
    if rates is None: return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def check_liquidity_sweep(df):
    """
    Kiểm tra mô hình Quét Thanh Khoản (Fakeout)
    """
    if len(df) < LOOKBACK_PERIOD + 2:
        return False, None

    # Nến vừa đóng (Signal Candle)
    candle = df.iloc[-1]
    
    # Vùng dữ liệu quá khứ (không bao gồm nến signal)
    past_df = df.iloc[-(LOOKBACK_PERIOD+1):-1]
    
    # Xác định Đỉnh/Đáy gần nhất
    recent_high = past_df['high'].max()
    recent_low = past_df['low'].min()
    
    # Thông tin nến Signal
    open_price = candle['open']
    close_price = candle['close']
    high = candle['high']
    low = candle['low']
    body = abs(close_price - open_price)
    total_range = high - low
    
    if total_range == 0: return False, None
    
    # 1. KIỂM TRA TÍN HIỆU SELL (BULL TRAP)
    # Điều kiện: Giá High vượt đỉnh cũ, nhưng đóng nến thấp hơn đỉnh cũ
    if high > recent_high and close_price < recent_high:
        sweep_size = high - recent_high
        
        # Kiểm tra độ dài râu trên (Upper Wick)
        upper_wick = high - max(open_price, close_price)
        wick_ratio = upper_wick / total_range
        
        if sweep_size >= MIN_SWEEP_PIPS and wick_ratio >= WICK_RATIO_MIN:
            print(f"  🔻 [SWEEP DETECTED] Quét đỉnh: {high:.2f} > {recent_high:.2f} (Sweep: {sweep_size:.2f}$)")
            return True, {
                'direction': 'SELL',
                'entry': close_price,
                'sl': high + SL_BUFFER,
                'reason': f"Bull Trap: Swept High {recent_high:.2f}"
            }

    # 2. KIỂM TRA TÍN HIỆU BUY (BEAR TRAP)
    # Điều kiện: Giá Low thủng đáy cũ, nhưng đóng nến cao hơn đáy cũ
    if low < recent_low and close_price > recent_low:
        sweep_size = recent_low - low
        
        # Kiểm tra độ dài râu dưới (Lower Wick)
        lower_wick = min(open_price, close_price) - low
        wick_ratio = lower_wick / total_range
        
        if sweep_size >= MIN_SWEEP_PIPS and wick_ratio >= WICK_RATIO_MIN:
            print(f"  🔺 [SWEEP DETECTED] Quét đáy: {low:.2f} < {recent_low:.2f} (Sweep: {sweep_size:.2f}$)")
            return True, {
                'direction': 'BUY',
                'entry': close_price,
                'sl': low - SL_BUFFER,
                'reason': f"Bear Trap: Swept Low {recent_low:.2f}"
            }
            
    return False, None

# ==============================================================================
# 4. THỰC THI GIAO DỊCH
# ==============================================================================

def execute_trade(signal):
    if not signal: return
    
    direction = signal['direction']
    entry = signal['entry']
    sl = signal['sl']
    sl_dist = abs(entry - sl)
    
    # Kiểm tra SL tối đa
    if sl_dist > MAX_SL_USD:
        print(f"⚠️ SL quá lớn ({sl_dist:.2f} USD), bỏ qua lệnh.")
        return

    tp_dist = sl_dist * RR_RATIO
    tp = entry - tp_dist if direction == 'SELL' else entry + tp_dist
    
    trade_type = mt5.ORDER_TYPE_SELL if direction == 'SELL' else mt5.ORDER_TYPE_BUY
    
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": VOLUME,
        "type": trade_type,
        "price": entry,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": MAGIC,
        "comment": "ProAction_Sweep",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    res = mt5.order_send(req)
    if res.retcode == mt5.TRADE_RETCODE_DONE:
        msg = f"✅ <b>{direction} MATCHED!</b>\nEntry: {entry}\nSL: {sl} ({sl_dist:.2f}$)\nTP: {tp} ({tp_dist:.2f}$)\nReason: {signal['reason']}"
        print(msg)
        send_telegram(msg)
    else:
        print(f"❌ Lỗi vào lệnh: {res.retcode} - {mt5.last_error()}")

def run():
    logger = setup_logging()
    if not load_config("btc.json"): return
    if not initialize_mt5(): return
    
    print("\n--- BOT PRO ACTION: LIQUIDITY SWEEP STARTED ---")
    print(f"Strategy: Săn thanh khoản tại Đỉnh/Đáy {LOOKBACK_PERIOD} nến gần nhất")
    
    last_candle_time = None
    
    while True:
        try:
            # Chỉ chạy khi có nến mới đóng
            df = get_rates(LOOKBACK_PERIOD + 5)
            if df is None: 
                time.sleep(1)
                continue
                
            current_candle_time = df.index[-1]
            
            if last_candle_time != current_candle_time:
                last_candle_time = current_candle_time
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🕯️ Nến mới: {current_candle_time}")
                
                # Check lệnh đang mở
                positions = mt5.positions_get(symbol=SYMBOL)
                my_positions = [p for p in positions if p.magic == MAGIC] if positions else []
                
                if len(my_positions) == 0:
                    has_signal, signal = check_liquidity_sweep(df)
                    if has_signal:
                        execute_trade(signal)
                else:
                    print(f"  ⏸️ Đang có {len(my_positions)} lệnh, bỏ qua tín hiệu.")
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        mt5.shutdown()
