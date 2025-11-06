import MetaTrader5 as mt5
import pandas as pd
import time
import json
import sys
import re
import requests
from datetime import datetime, timedelta
from config_xauusd import *
from risk_manager import XAUUSD_RiskManager
from technical_analyzer import TechnicalAnalyzer
import logging
import os

# Setup logging với encoding UTF-8 để hỗ trợ emoji
# Tạo custom StreamHandler để xử lý encoding errors trên Windows
class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler với error handling cho encoding trên Windows"""
    def __init__(self, stream=None):
        super().__init__(stream)
        # Thử cấu hình stdout/stderr để dùng UTF-8 (Python >= 3.7)
        if stream in (sys.stdout, sys.stderr):
            try:
                if hasattr(stream, 'reconfigure'):
                    stream.reconfigure(encoding='utf-8', errors='replace')
            except (AttributeError, ValueError):
                pass  # Không hỗ trợ reconfigure hoặc đã được cấu hình
    
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            # Thử write bình thường
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                # Nếu lỗi encoding, replace các ký tự không encode được
                # Giữ lại text tiếng Việt, chỉ thay thế emoji
                try:
                    # Thử encode với errors='replace' để thay thế emoji bằng ?
                    msg_bytes = msg.encode(stream.encoding if hasattr(stream, 'encoding') else 'cp1252', errors='replace')
                    msg_safe = msg_bytes.decode(stream.encoding if hasattr(stream, 'encoding') else 'cp1252', errors='replace')
                    stream.write(msg_safe + self.terminator)
                except Exception:
                    # Fallback: chỉ in text, bỏ emoji bằng regex
                    msg_no_emoji = re.sub(r'[^\x00-\x7F]+', '?', msg)
                    try:
                        stream.write(msg_no_emoji + self.terminator)
                    except:
                        # Cuối cùng: chỉ in ASCII safe
                        stream.write(msg_no_emoji.encode('ascii', 'ignore').decode('ascii') + self.terminator)
            stream.flush()
        except Exception:
            self.handleError(record)

# Cấu hình UTF-8 cho console (Windows)
if sys.platform == 'win32':
    try:
        # Thử set UTF-8 cho stdout/stderr (Python >= 3.7)
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass  # Không hỗ trợ hoặc không thể cấu hình

# Setup logging
log_file = os.path.join('logs', 'xauusd_bot.log') if os.path.exists('logs') else 'xauusd_bot.log'
os.makedirs('logs', exist_ok=True)
log_file = os.path.join('logs', 'xauusd_bot.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        SafeStreamHandler(sys.stdout)
    ]
)

class XAUUSD_Bot:
    def __init__(self):
        self.symbol = SYMBOL
        self.timeframe = TIMEFRAME_MT5[TIMEFRAME]
        self.risk_manager = XAUUSD_RiskManager()
        self.technical_analyzer = TechnicalAnalyzer()
        self.setup_directories()
        
        # Telegram settings
        self.use_telegram = USE_TELEGRAM if 'USE_TELEGRAM' in globals() else False
        self.telegram_bot_token = TELEGRAM_BOT_TOKEN if 'TELEGRAM_BOT_TOKEN' in globals() else ""
        self.telegram_chat_id = TELEGRAM_CHAT_ID if 'TELEGRAM_CHAT_ID' in globals() else ""
        
        # Theo dõi tín hiệu đã gửi để tránh spam
        self.last_signal_sent = None  # Lưu tín hiệu cuối cùng đã gửi Telegram
        self.last_signal_time = None  # Thời gian gửi tín hiệu cuối cùng
        self.telegram_signal_cooldown = 300  # Cooldown 5 phút giữa các lần gửi tín hiệu (giây)
        
        # Trailing stop tracking
        self.trailing_stop_activated = set()  # Set các ticket đã kích hoạt trailing stop
        self.breakeven_activated = set()  # Set các ticket đã kích hoạt break-even
        self.partial_close_done = {}  # Dict {ticket: [TP1_done, TP2_done, TP3_done]} để theo dõi partial close
        self.last_trailing_check = {}  # Dict {ticket: timestamp} để tránh modify quá thường xuyên
        self.atr_trailing_first_activation = set()  # Set các ticket đã gửi thông báo ATR Trailing lần đầu
        
        # Tracking để phát hiện TP/SL hit
        self.previous_positions = {}  # Dict {ticket: position_info} để theo dõi positions từ cycle trước
        
        logging.info(f"📱 Telegram Config: use_telegram={self.use_telegram}, token={'✅' if self.telegram_bot_token else '❌'}, chat_id={'✅' if self.telegram_chat_id else '❌'}")
        
    def setup_directories(self):
        os.makedirs('logs', exist_ok=True)
        os.makedirs('data', exist_ok=True)
        
    def setup_mt5(self):
        logging.info("=" * 60)
        logging.info("🚀 KHỞI TẠO BOT XAUUSD")
        logging.info("=" * 60)
        logging.info(f"📊 Symbol: {self.symbol}")
        logging.info(f"⏱️  Timeframe: {TIMEFRAME}")
        logging.info(f"💰 Risk per trade: {RISK_PER_TRADE}%")
        logging.info(f"📈 Max positions: {MAX_POSITIONS}")
        logging.info(f"📅 Max daily trades: {MAX_DAILY_TRADES}")
        logging.info(f"⏰ Check interval: {CHECK_INTERVAL} giây")
        
        # Log các rule thời gian
        logging.info("-" * 60)
        logging.info("⏰ QUY TẮC THỜI GIAN")
        logging.info("-" * 60)
        try:
            timezone = TRADING_TIMEZONE
        except NameError:
            timezone = "Local time"
        
        logging.info(f"   🌍 Timezone: {timezone}")
        logging.info(f"   ⏱️  Check interval: {CHECK_INTERVAL} giây")
        
        # Log NO_TRADE_SESSIONS
        try:
            if NO_TRADE_SESSIONS:
                logging.info(f"   🚫 Không giao dịch trong các session:")
                for start, end in NO_TRADE_SESSIONS:
                    logging.info(f"      • {start} - {end} ({timezone})")
            else:
                logging.info(f"   ✅ Không có session cấm giao dịch")
        except NameError:
            logging.info(f"   ✅ Không có session cấm giao dịch")
        
        # Log NO_TRADE_FRIDAY_AFTER
        try:
            if NO_TRADE_FRIDAY_AFTER:
                logging.info(f"   🚫 Không giao dịch sau {NO_TRADE_FRIDAY_AFTER} vào thứ 6 ({timezone})")
            else:
                logging.info(f"   ✅ Không có giới hạn thời gian cho thứ 6")
        except NameError:
            logging.info(f"   ✅ Không có giới hạn thời gian cho thứ 6")
        
        # Log BREAK_AFTER_LOSS_MINUTES
        try:
            logging.info(f"   ⏸️  Nghỉ {BREAK_AFTER_LOSS_MINUTES} phút sau khi thua lệnh")
        except NameError:
            logging.info(f"   ⏸️  Không có thời gian nghỉ sau khi thua")
        
        # Log MIN_TIME_BETWEEN_SAME_DIRECTION
        try:
            logging.info(f"   ⏳ Tối thiểu {MIN_TIME_BETWEEN_SAME_DIRECTION} phút giữa 2 lệnh cùng chiều")
        except NameError:
            logging.info(f"   ⏳ Không có giới hạn thời gian giữa 2 lệnh cùng chiều")
        
        # Log MAX_HOURLY_TRADES
        try:
            logging.info(f"   📊 Tối đa {MAX_HOURLY_TRADES} lệnh trong 1 giờ")
        except NameError:
            logging.info(f"   📊 Không có giới hạn số lệnh trong 1 giờ")
        
        logging.info("-" * 60)
        
        if not mt5.initialize():
            logging.error("❌ Không thể khởi tạo MT5")
            return False
        
        logging.info("✅ MT5 library đã khởi tạo")
        
        # Đăng nhập MT5
        if not mt5.login(login=ACCOUNT_NUMBER, password=PASSWORD, server=SERVER):
            error = mt5.last_error()
            logging.error(f"❌ Không thể đăng nhập MT5: {error}")
            mt5.shutdown()
            return False
            
        logging.info(f"✅ Đã đăng nhập MT5: Account {ACCOUNT_NUMBER}, Server: {SERVER}")
        
        # Kiểm tra symbol
        if not mt5.symbol_select(self.symbol, True):
            logging.error(f"❌ Không thể chọn symbol {self.symbol}")
            mt5.shutdown()
            return False
            
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info:
            logging.info(f"✅ Symbol {self.symbol} đã sẵn sàng")
            logging.info(f"   - Bid: {symbol_info.bid:.2f}, Ask: {symbol_info.ask:.2f}")
            logging.info(f"   - Spread: {(symbol_info.ask - symbol_info.bid) / 0.01:.1f} pips")
            logging.info(f"   - Point: {symbol_info.point}, Digits: {symbol_info.digits}")
        
        # Lấy thông tin tài khoản
        account_info = mt5.account_info()
        if account_info:
            logging.info("=" * 60)
            logging.info("📊 THÔNG TIN TÀI KHOẢN")
            logging.info("=" * 60)
            logging.info(f"   - Account: {account_info.login}")
            logging.info(f"   - Balance: ${account_info.balance:.2f}")
            logging.info(f"   - Equity: ${account_info.equity:.2f}")
            logging.info(f"   - Margin: ${account_info.margin:.2f}")
            logging.info(f"   - Free Margin: ${account_info.margin_free:.2f}")
            logging.info(f"   - Leverage: 1:{account_info.leverage}")
            logging.info("=" * 60)
        
        return True
        
    def get_account_info(self):
        account_info = mt5.account_info()
        if account_info:
            return {
                'balance': account_info.balance,
                'equity': account_info.equity,
                'margin': account_info.margin,
                'free_margin': account_info.margin_free
            }
        return None
        
    def send_telegram_message(self, message: str) -> bool:
        """
        Gửi thông báo qua Telegram
        
        Args:
            message: Nội dung tin nhắn cần gửi (có thể dùng HTML)
            
        Returns:
            True nếu gửi thành công, False nếu thất bại
        """
        if not self.use_telegram:
            return False
        
        if not self.telegram_bot_token or not self.telegram_chat_id:
            logging.warning("⚠️ Telegram chưa được cấu hình đầy đủ")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            
            # Thử gửi với HTML parse_mode
            payload = {
                "chat_id": str(self.telegram_chat_id).strip(),
                "text": message,
                "parse_mode": "HTML"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            
            if result.get('ok'):
                logging.info(f"✅ Đã gửi thông báo Telegram thành công")
                return True
            else:
                # Nếu lỗi HTML parsing, thử lại với plain text
                error_desc = result.get('description', 'Unknown error')
                if 'HTML' in error_desc or 'parse' in error_desc.lower():
                    logging.warning(f"⚠️ Lỗi HTML parsing, thử lại với plain text")
                    payload_plain = {
                        "chat_id": str(self.telegram_chat_id).strip(),
                        "text": message.replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>', '')
                    }
                    response2 = requests.post(url, json=payload_plain, timeout=10)
                    result2 = response2.json()
                    if result2.get('ok'):
                        logging.info(f"✅ Đã gửi thông báo Telegram (plain text)")
                        return True
                
                logging.error(f"❌ Telegram API lỗi: {error_desc}")
                return False
                
        except requests.exceptions.Timeout:
            logging.error(f"❌ Timeout khi gửi Telegram (quá 10 giây)")
            return False
        except Exception as e:
            logging.error(f"❌ Lỗi khi gửi Telegram: {e}")
            return False
        
    def get_filling_mode(self, symbol):
        """
        Tự động detect và trả về filling mode phù hợp với broker
        
        Args:
            symbol: Symbol cần kiểm tra (ví dụ: "XAUUSD")
            
        Returns:
            Filling mode constant từ MT5 (ORDER_FILLING_IOC, ORDER_FILLING_FOK, hoặc ORDER_FILLING_RETURN)
        """
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            logging.warning(f"⚠️ Không lấy được symbol info cho {symbol}, dùng ORDER_FILLING_RETURN mặc định")
            return mt5.ORDER_FILLING_RETURN
        
        # Kiểm tra filling modes được hỗ trợ
        # filling_mode là một bitmask:
        # - 1 = ORDER_FILLING_FOK (Fill or Kill)
        # - 2 = ORDER_FILLING_IOC (Immediate or Cancel)
        # - 4 = ORDER_FILLING_RETURN (Return)
        
        filling_mode = symbol_info.filling_mode
        
        # Ưu tiên: IOC > FOK > RETURN
        if filling_mode & mt5.ORDER_FILLING_IOC:
            logging.debug(f"✅ Broker hỗ trợ ORDER_FILLING_IOC cho {symbol}")
            return mt5.ORDER_FILLING_IOC
        elif filling_mode & mt5.ORDER_FILLING_FOK:
            logging.debug(f"✅ Broker hỗ trợ ORDER_FILLING_FOK cho {symbol}")
            return mt5.ORDER_FILLING_FOK
        elif filling_mode & mt5.ORDER_FILLING_RETURN:
            logging.debug(f"✅ Broker hỗ trợ ORDER_FILLING_RETURN cho {symbol}")
            return mt5.ORDER_FILLING_RETURN
        else:
            # Fallback: dùng RETURN (thường được hỗ trợ rộng rãi)
            logging.warning(f"⚠️ Không detect được filling mode phù hợp, dùng ORDER_FILLING_RETURN mặc định")
            return mt5.ORDER_FILLING_RETURN
        
    def calculate_position_size(self, stop_loss_pips):
        account_info = self.get_account_info()
        if not account_info:
            return 0.01
            
        balance = account_info['balance']
        risk_amount = balance * (RISK_PER_TRADE / 100)
        
        # 1 pip XAUUSD = $1 cho 1 lot (1 lot = 100 oz, 1 pip = 0.01 USD)
        # Ví dụ: Giá tăng từ 3985.00 → 3985.01 (1 pip) với 1 lot → Profit = 100 oz × 0.01 = $1.00
        pip_value = 1  # $1 cho 1 lot
        position_size = risk_amount / (stop_loss_pips * pip_value)
        
        # Làm tròn và giới hạn kích thước
        position_size = round(position_size, 2)
        position_size = max(0.01, min(1.0, position_size))
        
        logging.info(f"📊 Lot size: {position_size} (SL: {stop_loss_pips}pips, Risk: ${risk_amount:.2f})")
        return position_size
        
    def get_price_data(self, count=100):
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, count)
        if rates is None:
            logging.error(f"❌ Không thể lấy dữ liệu giá cho {self.symbol}")
            return None
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        if len(df) > 0:
            latest = df.iloc[-1]
            logging.debug(f"📊 Dữ liệu giá: {len(df)} nến, Giá mới nhất: {latest['close']:.2f} (Time: {latest['time']})")
        
        return df
        
    def check_market_conditions(self):
        """Kiểm tra điều kiện thị trường"""
        symbol_info = mt5.symbol_info(self.symbol)
        if not symbol_info:
            logging.warning("⚠️ Không lấy được symbol info")
            return False, "Không lấy được symbol info"
            
        # Kiểm tra spread
        spread = (symbol_info.ask - symbol_info.bid) / 0.01
        logging.debug(f"📊 Spread hiện tại: {spread:.1f} pips (Max: {MAX_SPREAD} pips)")
        if spread > MAX_SPREAD:
            logging.warning(f"⚠️ Spread quá cao: {spread:.1f} pips > {MAX_SPREAD} pips")
            return False, f"Spread quá cao: {spread:.1f}pips"
            
        # Kiểm tra thời gian giao dịch
        trading_time_ok, time_msg = self.risk_manager.check_trading_time()
        if not trading_time_ok:
            logging.debug(f"⏸️ {time_msg}")
            return False, time_msg
            
        # Kiểm tra điều kiện tài khoản
        account_ok, account_msg = self.risk_manager.check_account_conditions()
        if not account_ok:
            logging.warning(f"⚠️ {account_msg}")
            return False, account_msg
        
        logging.debug("✅ Điều kiện thị trường: OK")
        return True, "OK"
        
    def execute_trade(self, signal_type, sl_pips, tp_pips, signal_strength=0):
        """Thực hiện giao dịch"""
        
        # Kiểm tra điều kiện thị trường
        market_ok, message = self.check_market_conditions()
        if not market_ok:
            logging.warning(f"❌ Không giao dịch: {message}")
            return None
            
        # ⚠️ LƯU Ý: Kiểm tra risk manager đã được thực hiện trong run_bot() trước khi gọi execute_trade()
        # Kiểm tra lại ở đây để đảm bảo an toàn (phòng trường hợp được gọi từ nơi khác)
        if not self.risk_manager.can_open_trade(signal_type):
            logging.warning(f"❌ Risk Manager chặn (trong execute_trade): Không thể mở lệnh {signal_type}")
            return None
        
        # Chỉ log "CHUẨN BỊ MỞ LỆNH" khi đã pass tất cả các kiểm tra
        logging.info("=" * 60)
        logging.info(f"📈 CHUẨN BỊ MỞ LỆNH {signal_type}")
        logging.info("=" * 60)
            
        symbol_info = mt5.symbol_info(self.symbol)
        if not symbol_info:
            logging.error("❌ Không lấy được symbol info")
            return None
        
        # Lấy tick mới nhất (giống gold.py)
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            logging.error(f"❌ Không thể lấy tick cho {self.symbol}")
            return None
            
        # Tính giá (SL price sẽ được tính SAU khi điều chỉnh SL pips)
        if signal_type == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:  # SELL
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        
        # Tính lot size ban đầu dựa trên risk_per_trade
        lot_size = self.calculate_position_size(sl_pips)
        
        # Validate lot size trước (giống eth.py)
        lot_step = symbol_info.volume_step if symbol_info.volume_step and symbol_info.volume_step > 0 else 0.01
        min_lot_config = MIN_LOT_SIZE if 'MIN_LOT_SIZE' in globals() else 0.01
        max_lot_config = MAX_LOT_SIZE if 'MAX_LOT_SIZE' in globals() else 1.0
        lot_min = symbol_info.volume_min if symbol_info.volume_min and symbol_info.volume_min > 0 else min_lot_config
        lot_max = symbol_info.volume_max if symbol_info.volume_max and symbol_info.volume_max > 0 else max_lot_config
        
        # Đảm bảo lot_size đúng format
        lot_size = round(lot_size, 2)
        lot_size = max(lot_min, min(lot_size, lot_max))
        
        # Làm tròn theo lot_step
        if lot_step > 0:
            lot_size = round(lot_size / lot_step) * lot_step
            lot_size = round(lot_size, 2)
        
        # Đảm bảo lot_size vẫn trong khoảng hợp lệ sau khi làm tròn
        lot_size = max(lot_min, min(lot_size, lot_max))
        
        if lot_size < lot_min or lot_size > lot_max:
            logging.error(f"❌ Lot size không hợp lệ: {lot_size} (min: {lot_min}, max: {lot_max})")
            return None
        
        # ⚠️ QUAN TRỌNG: Kiểm tra giới hạn SL theo USD (SAU KHI validate lot_size)
        # Tính SL theo USD: 1 pip XAUUSD = $1 cho 1 lot (1 lot = 100 oz, 1 pip = 0.01 USD)
        # Ví dụ: Giá tăng từ 3985.00 → 3985.01 (1 pip) với 1 lot → Profit = 100 oz × 0.01 = $1.00
        pip_value_per_lot = 1  # $1 cho 1 lot (SAI: đã sửa từ 10 xuống 1)
        sl_usd = sl_pips * pip_value_per_lot * lot_size
        
        # Kiểm tra mode ATR SL/TP
        # Lấy từ config (đã được import từ config_xauusd.py)
        try:
            atr_sl_tp_mode = ATR_SL_TP_MODE
            logging.debug(f"🔍 ATR_SL_TP_MODE từ config: {atr_sl_tp_mode}")
        except NameError:
            # Fallback nếu không tìm thấy
            atr_sl_tp_mode = "ATR_FREE"
            logging.error(f"❌ ATR_SL_TP_MODE không tìm thấy trong config! Dùng mặc định: {atr_sl_tp_mode}")
        
        logging.info(f"🔧 ATR Mode: {atr_sl_tp_mode}, SL ban đầu: {sl_pips:.0f} pips, Lot: {lot_size:.2f}, SL USD: ${sl_usd:.2f}")
        
        if atr_sl_tp_mode == "ATR_BOUNDED":
            logging.info(f"✅ ATR_BOUNDED mode được kích hoạt - Bắt đầu điều chỉnh SL/TP...")
            # Mode ATR_BOUNDED: Điều chỉnh SL để nằm trong khoảng $5-$10
            # QUAN TRỌNG: Ưu tiên MIN_SL_PIPS (250 pips) trước, sau đó điều chỉnh lot_size để đạt MIN USD
            atr_min_sl_usd = ATR_MIN_SL_USD if 'ATR_MIN_SL_USD' in globals() else 5.0
            atr_max_sl_usd = ATR_MAX_SL_USD if 'ATR_MAX_SL_USD' in globals() else 10.0
            min_sl_pips_config = MIN_SL_PIPS if 'MIN_SL_PIPS' in globals() else 200
            
            sl_pips_original = sl_pips
            lot_size_original = lot_size
            adjusted = False
            
            # BƯỚC 1: Đảm bảo sl_pips >= MIN_SL_PIPS (ưu tiên cao nhất)
            if sl_pips < min_sl_pips_config:
                logging.info(f"📊 ATR_BOUNDED: SL pips {sl_pips:.0f} < MIN_SL_PIPS {min_sl_pips_config} → Tăng lên {min_sl_pips_config} pips")
                sl_pips = min_sl_pips_config
                adjusted = True
            
            # Tính lại SL USD sau khi đảm bảo MIN_SL_PIPS
            sl_usd = sl_pips * pip_value_per_lot * lot_size
            
            # BƯỚC 2: Nếu SL USD < MIN: Tăng lot_size để đạt MIN USD
            if sl_usd < atr_min_sl_usd:
                # Tính lot_size cần thiết để đạt MIN USD với sl_pips hiện tại (đã >= MIN_SL_PIPS)
                lot_size_needed = atr_min_sl_usd / (sl_pips * pip_value_per_lot)
                lot_size_needed = max(lot_min, lot_size_needed)
                
                # Làm tròn theo lot_step
                if lot_step > 0:
                    lot_size_needed = round(lot_size_needed / lot_step) * lot_step
                    lot_size_needed = round(lot_size_needed, 2)
                
                lot_size_needed = max(lot_min, lot_size_needed)
                
                # Tăng lot_size nếu cần
                if lot_size_needed > lot_size:
                    lot_size = lot_size_needed
                    adjusted = True
                    logging.info(f"📊 ATR_BOUNDED: SL USD ${sl_usd:.2f} < ${atr_min_sl_usd} → Tăng lot_size: {lot_size_original:.2f} → {lot_size:.2f} lots (SL pips: {sl_pips:.0f})")
                
                # Tính lại SL USD với lot_size mới
                sl_usd = sl_pips * pip_value_per_lot * lot_size
                
                # Nếu vẫn < MIN sau khi tăng lot_size (lot_size đã ở max) → Tăng sl_pips thêm
                if sl_usd < atr_min_sl_usd:
                    # Tính sl_pips cần thiết để đạt MIN USD với lot_size hiện tại
                    sl_pips_needed = int(atr_min_sl_usd / (pip_value_per_lot * lot_size)) + 1
                    # Đảm bảo vẫn >= MIN_SL_PIPS
                    sl_pips = max(min_sl_pips_config, sl_pips_needed)
                    sl_usd = sl_pips * pip_value_per_lot * lot_size
                    logging.warning(f"⚠️ ATR_BOUNDED: Đã tăng SL pips lên {sl_pips:.0f} để đạt MIN ${atr_min_sl_usd} (SL USD: ${sl_usd:.2f})")
                    adjusted = True
            
            # BƯỚC 3: Nếu SL USD > MAX: Giảm lot_size trước, sau đó mới giảm sl_pips (ưu tiên giảm rủi ro)
            if sl_usd > atr_max_sl_usd:
                logging.info(f"📊 ATR_BOUNDED: SL USD ${sl_usd:.2f} > ${atr_max_sl_usd} → Đang điều chỉnh...")
                
                # Thử giảm lot_size trước (giữ nguyên sl_pips >= MIN_SL_PIPS)
                lot_size_max = atr_max_sl_usd / (sl_pips * pip_value_per_lot)
                lot_size_max = max(lot_min, lot_size_max)
                
                # Làm tròn lot_size_max theo lot_step
                if lot_step > 0:
                    lot_size_max = round(lot_size_max / lot_step) * lot_step
                    lot_size_max = round(lot_size_max, 2)
                
                lot_size_max = max(lot_min, lot_size_max)
                
                # Tính lại SL USD với lot_size mới
                sl_usd_new = sl_pips * pip_value_per_lot * lot_size_max
                
                # Nếu giảm lot_size đạt MAX → Dùng lot_size mới
                if sl_usd_new <= atr_max_sl_usd:
                    lot_size = lot_size_max
                    sl_usd = sl_usd_new
                    adjusted = True
                    logging.info(f"📊 ATR_BOUNDED: SL USD ${sl_usd:.2f} > ${atr_max_sl_usd} → Giảm lot size: {lot_size_original:.2f} → {lot_size:.2f} lots (SL pips: {sl_pips:.0f})")
                else:
                    # Nếu vẫn > MAX sau khi giảm lot_size → Giảm sl_pips để đạt MAX
                    # Tính sl_pips để đạt MAX với lot_size hiện tại (làm tròn xuống để đảm bảo <= MAX)
                    sl_pips_for_max = atr_max_sl_usd / (pip_value_per_lot * lot_size)
                    sl_pips_for_max = int(sl_pips_for_max)  # Làm tròn xuống để đảm bảo SL USD <= MAX
                    
                    # Nếu sl_pips_for_max < MIN_SL_PIPS → Giảm xuống sl_pips_for_max để đạt MAX USD (ưu tiên giảm rủi ro)
                    # Cảnh báo rõ ràng về vi phạm MIN_SL_PIPS
                    if sl_pips_for_max < min_sl_pips_config:
                        sl_pips = sl_pips_for_max
                        sl_usd = sl_pips * pip_value_per_lot * lot_size
                        adjusted = True
                        logging.error(f"❌ ATR_BOUNDED: SL USD ${sl_usd:.2f} > ${atr_max_sl_usd} → Giảm SL pips: {sl_pips_original:.0f} → {sl_pips:.0f} pips (NHỎ HƠN MIN_SL_PIPS {min_sl_pips_config} để đạt MAX USD ${atr_max_sl_usd}, SL USD: ${sl_usd:.2f})")
                    else:
                        # Có thể giảm sl_pips xuống sl_pips_for_max mà vẫn >= MIN_SL_PIPS
                        sl_pips = sl_pips_for_max
                        sl_usd = sl_pips * pip_value_per_lot * lot_size
                        adjusted = True
                        logging.info(f"📊 ATR_BOUNDED: SL USD ${sl_usd:.2f} > ${atr_max_sl_usd} → Giảm SL pips: {sl_pips_original:.0f} → {sl_pips:.0f} pips (SL USD: ${sl_usd:.2f})")
            
            # Tính lại SL USD sau khi điều chỉnh (luôn tính lại)
            sl_usd = sl_pips * pip_value_per_lot * lot_size
            logging.info(f"🔧 ATR_BOUNDED sau điều chỉnh: SL pips={sl_pips:.0f}, Lot={lot_size:.2f}, SL USD=${sl_usd:.2f}")
            
            # KIỂM TRA CUỐI CÙNG: Verify và log cảnh báo (KHÔNG override nếu đã điều chỉnh)
            # Chỉ cảnh báo, không override lại vì đã điều chỉnh ở các bước trên
            if sl_pips < min_sl_pips_config:
                logging.warning(f"⚠️ ATR_BOUNDED: SL pips {sl_pips:.0f} < MIN_SL_PIPS {min_sl_pips_config} (đã điều chỉnh để đạt MAX USD ${atr_max_sl_usd})")
            
            if sl_usd < atr_min_sl_usd:
                logging.warning(f"⚠️ ATR_BOUNDED: SL USD ${sl_usd:.2f} < MIN ${atr_min_sl_usd} (SL pips: {sl_pips:.0f})")
            
            if sl_usd > atr_max_sl_usd:
                logging.error(f"❌ ATR_BOUNDED: SL USD ${sl_usd:.2f} > MAX ${atr_max_sl_usd} (SL pips: {sl_pips:.0f}) - ĐIỀU CHỈNH THẤT BẠI!")
            
            # Tính lại SL USD cuối cùng (đảm bảo chính xác)
            sl_usd = sl_pips * pip_value_per_lot * lot_size
            
            # Tính SL price SAU khi điều chỉnh xong
            if signal_type == "BUY":
                sl_price = price - (sl_pips * 0.01)
            else:  # SELL
                sl_price = price + (sl_pips * 0.01)
            
            # Tính TP price
            if signal_type == "BUY":
                tp_price = price + (tp_pips * 0.01)
            else:  # SELL
                tp_price = price - (tp_pips * 0.01)
            
            # Tính lại SL USD từ SL price thực tế để verify
            sl_pips_actual = abs(price - sl_price) / 0.01
            sl_usd_actual = sl_pips_actual * pip_value_per_lot * lot_size
            
            # Log kết quả cuối cùng
            if atr_min_sl_usd <= sl_usd_actual <= atr_max_sl_usd:
                logging.info(f"✅ ATR_BOUNDED: SL cuối cùng = {sl_pips:.0f} pips (${sl_usd_actual:.2f} USD, trong khoảng ${atr_min_sl_usd}-${atr_max_sl_usd})")
            else:
                logging.error(f"❌ ATR_BOUNDED: SL USD ${sl_usd_actual:.2f} KHÔNG trong khoảng ${atr_min_sl_usd}-${atr_max_sl_usd}!")
                logging.error(f"   - SL pips: {sl_pips:.0f}, Lot: {lot_size:.2f}, Price: {price:.2f}, SL price: {sl_price:.2f}")
                logging.error(f"   - SL pips ban đầu: {sl_pips_original:.0f}, SL pips sau điều chỉnh: {sl_pips:.0f}")
                logging.error(f"   - Đã điều chỉnh: {adjusted}")
        
        else:
            # Mode ATR_FREE hoặc không phải ATR_BOUNDED
            logging.info(f"ℹ️ Không dùng ATR_BOUNDED mode (mode: {atr_sl_tp_mode}) - Tính SL price với SL pips ban đầu")
            # Mode ATR_FREE: SL/TP tự động điều chỉnh theo ATR (đã có trong technical_analyzer)
            # + Điều chỉnh mềm để tránh rủi ro quá lớn (nhưng không bắt buộc như BOUNDED)
            
            # Tính SL price và TP price
            if signal_type == "BUY":
                sl_price = price - (sl_pips * 0.01)
                tp_price = price + (tp_pips * 0.01)
            else:  # SELL
                sl_price = price + (sl_pips * 0.01)
                tp_price = price - (tp_pips * 0.01)
            
            # SL đã được tự động tính theo ATR trong technical_analyzer.py:
            # sl_pips = max(MIN_SL_PIPS, ATR * ATR_MULTIPLIER_SL)
            # → ATR cao → SL xa, ATR thấp → SL gần (tự động điều chỉnh)
            
            # Điều chỉnh mềm: Nếu SL USD quá lớn (> MAX_SL_USD), có thể giảm lot_size
            # nhưng không bắt buộc (khác với BOUNDED là bắt buộc)
            max_sl_usd_soft = MAX_SL_USD if 'MAX_SL_USD' in globals() else 10.0
            
            if sl_usd > max_sl_usd_soft * 2:  # Nếu SL > 2x MAX_SL_USD (ví dụ: > $20)
                # Cảnh báo và có thể điều chỉnh lot_size (nhưng không bắt buộc)
                logging.warning(
                    f"⚠️ ATR_FREE: SL USD ${sl_usd:.2f} khá cao (> ${max_sl_usd_soft * 2:.0f}) "
                    f"→ Có thể giảm lot_size để giảm rủi ro (không bắt buộc)"
                )
                
                # Điều chỉnh mềm: Giảm lot_size nếu cần (tùy chọn)
                # Tính lot_size tối đa để SL ≈ MAX_SL_USD
                lot_size_max_soft = max_sl_usd_soft / (sl_pips * pip_value_per_lot)
                lot_size_max_soft = max(lot_min, lot_size_max_soft)
                
                # Làm tròn
                if lot_step > 0:
                    lot_size_max_soft = round(lot_size_max_soft / lot_step) * lot_step
                    lot_size_max_soft = round(lot_size_max_soft, 2)
                
                lot_size_max_soft = max(lot_min, lot_size_max_soft)
                
                # Nếu lot_size_max_soft < lot_size hiện tại → Giảm để giảm rủi ro
                if lot_size_max_soft < lot_size:
                    lot_size_original = lot_size
                    lot_size = lot_size_max_soft
                    sl_usd_new = sl_pips * pip_value_per_lot * lot_size
                    logging.info(
                        f"📊 ATR_FREE: Điều chỉnh mềm lot_size: {lot_size_original:.2f} → {lot_size:.2f} lots "
                        f"(SL USD: ${sl_usd:.2f} → ${sl_usd_new:.2f})"
                    )
                    sl_usd = sl_usd_new
            
            logging.info(f"📊 ATR_FREE: SL = {sl_pips:.0f} pips (${sl_usd:.2f} USD) - Tự động theo ATR")
        
        # Lấy thông tin tài khoản
        account_info = self.get_account_info()
        
        # Log thông tin lệnh (SAU khi điều chỉnh ATR_BOUNDED)
        logging.info(f"📊 Thông tin lệnh CUỐI CÙNG:")
        logging.info(f"   - Loại: {signal_type}")
        logging.info(f"   - Giá vào: {price:.2f}")
        logging.info(f"   - SL price: {sl_price:.2f}")
        logging.info(f"   - SL pips: {sl_pips:.2f} pips")
        sl_usd_final = sl_pips * pip_value_per_lot * lot_size
        logging.info(f"   - SL USD: ${sl_usd_final:.2f}")
        logging.info(f"   - TP: {tp_price:.2f} ({tp_pips} pips)")
        logging.info(f"   - Lot size: {lot_size} (đã validate: min={lot_min}, max={lot_max}, step={lot_step})")
        logging.info(f"   - Risk: ${account_info['balance'] * (RISK_PER_TRADE / 100):.2f} ({RISK_PER_TRADE}%)")
        logging.info(f"   - Signal strength: {signal_strength}")
        logging.info(f"   - ATR Mode: {atr_sl_tp_mode}")
        
        # Tạo request cơ bản (SAU khi điều chỉnh ATR_BOUNDED)
        # ⚠️ QUAN TRỌNG: sl_price và sl_pips đã được điều chỉnh trong ATR_BOUNDED mode (nếu có)
        logging.debug(f"🔍 Tạo request với: sl_price={sl_price:.2f}, sl_pips={sl_pips:.2f}, lot_size={lot_size:.2f}")
        sl_usd_verify = sl_pips * pip_value_per_lot * lot_size
        logging.debug(f"🔍 SL USD verify: ${sl_usd_verify:.2f}")
        
        request_base = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl_price,  # Đã được tính từ sl_pips đã điều chỉnh (nếu ATR_BOUNDED)
            "tp": tp_price,
            "deviation": DEVIATION if 'DEVIATION' in globals() else 100,
            "magic": 202411,
            "comment": f"XAUUSD_Bot_{signal_type}",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        
        # Thử các filling mode theo thứ tự: IOC -> FOK -> RETURN -> None (không có type_filling)
        filling_modes_to_try = [
            (mt5.ORDER_FILLING_IOC, "IOC"),
            (mt5.ORDER_FILLING_FOK, "FOK"),
            (mt5.ORDER_FILLING_RETURN, "RETURN"),
            (None, "AUTO")  # Không có type_filling, để MT5 tự chọn
        ]
        
        for filling_mode, mode_name in filling_modes_to_try:
            request = request_base.copy()
            if filling_mode is not None:
                request["type_filling"] = filling_mode
            
            logging.info(f"📤 Thử gửi lệnh với filling mode: {mode_name}...")
            
            # Validate request trước khi gửi (giống gold.py)
            check_result = mt5.order_check(request)
            if check_result is None:
                error = mt5.last_error()
                logging.warning(f"⚠️ order_check() trả về None: {error}")
                # Vẫn thử gửi lệnh
            elif hasattr(check_result, 'retcode') and check_result.retcode != 0:
                logging.warning(f"⚠️ order_check() không hợp lệ: {check_result.comment if hasattr(check_result, 'comment') else 'Unknown'}")
                # Thử mode tiếp theo
                continue
            
            # Gửi lệnh
            result = mt5.order_send(request)
            
            if result:
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    logging.info(f"✅ LỆNH {signal_type} THÀNH CÔNG với filling mode: {mode_name}!")
                    logging.info(f"   - Ticket: {result.order}")
                    logging.info(f"   - Volume: {lot_size} lots")
                    logging.info(f"   - Price: {price:.2f}")
                    logging.info(f"   - SL: {sl_price:.2f}, TP: {tp_price:.2f}")
                    return result
                else:
                    # Log lỗi nhưng thử mode tiếp theo
                    error_code = result.retcode
                    error_desc = result.comment if hasattr(result, 'comment') else 'Unknown error'
                    logging.warning(f"⚠️ Filling mode {mode_name} thất bại: {error_desc} (Code: {error_code})")
                    # Nếu không phải lỗi filling mode, không thử tiếp
                    if error_code != 10015 and 'filling' not in error_desc.lower():
                        logging.error(f"❌ LỆNH {signal_type} THẤT BẠI: {error_desc}")
                        return result
                    # Nếu là lỗi filling mode, thử mode tiếp theo
                    continue
            else:
                error = mt5.last_error()
                logging.warning(f"⚠️ Không nhận được response từ MT5 với {mode_name}: {error}")
                # Thử mode tiếp theo
                continue
        
        # Nếu tất cả filling modes đều thất bại
        logging.error(f"❌ Tất cả filling modes đều thất bại cho lệnh {signal_type}")
        return None
        
    def run_bot(self):
        """Vòng lặp chính của bot"""
        logging.info("=" * 60)
        logging.info("🚀 BOT XAUUSD BẮT ĐẦU CHẠY")
        logging.info("=" * 60)
        
        # Không gửi Telegram khi bot khởi động (chỉ gửi khi có kết quả lệnh)
        
        cycle_count = 0
        last_logged_account_info = None  # Lưu thông tin tài khoản lần log cuối để tránh log trùng
        last_logged_price = None  # Lưu giá lần log cuối
        last_logged_positions = None  # Lưu số positions lần log cuối
        pending_delay_info = None  # Lưu thông tin delay nếu có tín hiệu hợp lệ nhưng bị chặn
        
        def log_delay_and_sleep():
            """Helper function để log delay info và sleep trước khi continue"""
            if pending_delay_info:
                # Nếu có tín hiệu hợp lệ nhưng bị delay, log thông tin chi tiết
                delay_info = pending_delay_info
                logging.info("=" * 60)
                logging.info(f"⏸️ TÍN HIỆU HỢP LỆ ĐANG CHỜ ĐỦ ĐIỀU KIỆN THỜI GIAN")
                logging.info("=" * 60)
                logging.info(f"   📊 Tín hiệu đang chờ: {delay_info['action']} (Strength: {delay_info['strength']})")
                logging.info(f"   ⏱️ Cần đợi thêm: {delay_info['remaining_minutes']} phút {delay_info['remaining_seconds']} giây")
                logging.info(f"   ⏰ Thời gian check tiếp theo: {delay_info['next_check_time'].strftime('%Y-%m-%d %H:%M:%S')}")
                logging.info(f"   📋 Sẽ kiểm tra lại sau {CHECK_INTERVAL} giây (mỗi {CHECK_INTERVAL}s)")
                logging.info("=" * 60)
            
            logging.info(f"⏳ Chờ {CHECK_INTERVAL} giây trước lần kiểm tra tiếp theo...")
            time.sleep(CHECK_INTERVAL)
        
        while True:
            try:
                cycle_count += 1
                
                # Chỉ log cycle summary mỗi 10 cycles hoặc khi có thay đổi quan trọng
                should_log_summary = (cycle_count % 10 == 0) or (cycle_count == 1)
                
                if should_log_summary:
                    logging.info("-" * 60)
                    logging.info(f"🔄 CYCLE #{cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    logging.info("-" * 60)
                
                # Lấy thông tin tài khoản
                account_info = self.get_account_info()
                num_positions = 0
                if account_info:
                    # Chỉ log khi có thay đổi đáng kể (equity thay đổi > 1% hoặc số positions thay đổi)
                    account_changed = False
                    if last_logged_account_info is None:
                        account_changed = True
                    else:
                        equity_change_pct = abs(account_info['equity'] - last_logged_account_info['equity']) / last_logged_account_info['equity'] if last_logged_account_info['equity'] > 0 else 0
                        if equity_change_pct > 0.01:  # Thay đổi > 1%
                            account_changed = True
                    
                    # Kiểm tra số position đang mở
                    positions = mt5.positions_get(symbol=self.symbol)
                    if positions is None:
                        positions = []
                    num_positions = len(positions)
                    
                    positions_changed = (last_logged_positions is None or last_logged_positions != num_positions)
                    
                    if should_log_summary or account_changed or positions_changed:
                        logging.info(f"💵 Tài khoản: Equity=${account_info['equity']:.2f} | Balance=${account_info['balance']:.2f} | Free Margin=${account_info['free_margin']:.2f}")
                        logging.info(f"📊 Vị thế đang mở: {num_positions}/{MAX_POSITIONS}")
                        last_logged_account_info = account_info.copy()
                        last_logged_positions = num_positions
                    else:
                        logging.debug(f"💵 Tài khoản: Equity=${account_info['equity']:.2f} | Balance=${account_info['balance']:.2f} | Free Margin=${account_info['free_margin']:.2f}")
                        logging.debug(f"📊 Vị thế đang mở: {num_positions}/{MAX_POSITIONS}")
                    
                    if num_positions > 0 and (should_log_summary or positions_changed):
                        total_profit = sum(pos.profit for pos in positions)
                        logging.info(f"   - Tổng P&L: ${total_profit:.2f}")
                        for pos in positions:
                            order_type = "BUY" if pos.type == 0 else "SELL"
                            logging.info(f"   - {order_type} {pos.volume} lots @ {pos.price_open:.2f}, P&L: ${pos.profit:.2f}")
                    elif num_positions > 0:
                        total_profit = sum(pos.profit for pos in positions)
                        logging.debug(f"   - Tổng P&L: ${total_profit:.2f}")
                else:
                    account_info = {'equity': 0, 'balance': 0, 'free_margin': 0}
                
                # Quản lý Smart Trailing Stop và Smart Exit cho các lệnh đang mở
                self._manage_trailing_stops()
                self._manage_smart_exit()
                
                # Lấy dữ liệu giá
                df = self.get_price_data(100)
                if df is None:
                    logging.error("❌ Không lấy được dữ liệu giá, chờ 30s...")
                    time.sleep(30)
                    continue
                
                # Log giá hiện tại (chỉ khi thay đổi đáng kể hoặc mỗi 10 cycles)
                if len(df) > 0:
                    latest_price = df.iloc[-1]['close']
                    tick = mt5.symbol_info_tick(self.symbol)
                    
                    # Chỉ log khi giá thay đổi > 0.1% hoặc mỗi 10 cycles
                    price_changed = False
                    if last_logged_price is None:
                        price_changed = True
                    else:
                        price_change_pct = abs(latest_price - last_logged_price) / last_logged_price if last_logged_price > 0 else 0
                        if price_change_pct > 0.001:  # Thay đổi > 0.1%
                            price_changed = True
                    
                    if should_log_summary or price_changed:
                        if tick:
                            logging.info(f"📈 Giá hiện tại: {latest_price:.2f} (Bid/Ask: {tick.bid:.2f}/{tick.ask:.2f})")
                        else:
                            logging.info(f"📈 Giá hiện tại: {latest_price:.2f}")
                        last_logged_price = latest_price
                    else:
                        logging.debug(f"📈 Giá hiện tại: {latest_price:.2f}")
                
                # Phân tích kỹ thuật (chuyển sang debug để giảm log)
                logging.debug("🔍 Đang phân tích kỹ thuật...")
                signal = self.technical_analyzer.analyze(df)
                
                if signal:
                    action = signal.get('action', 'HOLD')
                    strength = signal.get('strength', 0)
                    
                    # Reset delay info khi có tín hiệu mới (không phải HOLD)
                    if action != 'HOLD':
                        # Nếu có tín hiệu mới khác với tín hiệu đang delay, reset delay info
                        if pending_delay_info and pending_delay_info['action'] != action:
                            pending_delay_info = None
                        # Tạo signature của tín hiệu để so sánh (làm tròn SL/TP để tránh thay đổi nhỏ do giá)
                        # Làm tròn SL/TP về 10 pips gần nhất để so sánh chính xác hơn
                        sl_pips_rounded = round(signal.get('sl_pips', 0) / 10) * 10
                        tp_pips_rounded = round(signal.get('tp_pips', 0) / 10) * 10
                        signal_signature = (action, strength, sl_pips_rounded, tp_pips_rounded)
                        now_time = datetime.now()
                        
                        # Kiểm tra xem tín hiệu có mới/khác không
                        signal_changed = (self.last_signal_sent != signal_signature)
                        cooldown_passed = (self.last_signal_time is None or 
                                          (now_time - self.last_signal_time).total_seconds() >= self.telegram_signal_cooldown)
                        
                        should_send_signal = signal_changed and cooldown_passed
                        
                        # Chỉ log "TÍN HIỆU GIAO DỊCH PHÁT HIỆN" khi tín hiệu mới hoặc thay đổi (tránh spam log)
                        if should_send_signal:
                            logging.info("=" * 60)
                            logging.info(f"🎯 TÍN HIỆU GIAO DỊCH PHÁT HIỆN!")
                            logging.info("=" * 60)
                            logging.info(f"   - Action: {action}")
                            logging.info(f"   - Strength: {strength}")
                            logging.info(f"   - SL: {signal.get('sl_pips', 0)} pips")
                            logging.info(f"   - TP: {signal.get('tp_pips', 0)} pips")
                            logging.info("=" * 60)
                        else:
                            # Log ngắn gọn khi tín hiệu giống (không spam)
                            if not signal_changed:
                                logging.debug(f"📊 Tín hiệu {action} (Strength: {strength}) - giống tín hiệu trước (đã log)")
                            else:
                                remaining = int(self.telegram_signal_cooldown - (now_time - self.last_signal_time).total_seconds())
                                logging.debug(f"📊 Tín hiệu {action} (Strength: {strength}) - cooldown còn {remaining}s")
                        
                        # Không gửi Telegram khi có tín hiệu (chỉ gửi khi có kết quả lệnh)
                        # Cập nhật tracking để tránh spam log
                        if should_send_signal:
                            self.last_signal_sent = signal_signature
                            self.last_signal_time = now_time
                            logging.debug(f"📊 Tín hiệu {action} mới - đang xử lý...")
                        else:
                            if not signal_changed:
                                logging.debug(f"📊 Tín hiệu {action} giống tín hiệu trước (đã log)")
                            elif not cooldown_passed:
                                remaining = int(self.telegram_signal_cooldown - (now_time - self.last_signal_time).total_seconds())
                                logging.debug(f"📊 Tín hiệu {action} - cooldown còn {remaining}s")
                        
                        # ⚠️ QUAN TRỌNG: Check lại lệnh đang mở trên MT5 trước khi mở lệnh mới
                        # Đảm bảo lấy số positions mới nhất từ MT5 để tránh vượt quá MAX_POSITIONS
                        current_positions = mt5.positions_get(symbol=self.symbol)
                        if current_positions is None:
                            current_positions = []
                        current_position_count = len(current_positions)
                        
                        if current_position_count >= MAX_POSITIONS:
                            logging.warning(f"❌ Không thể mở lệnh {action}: Đã có {current_position_count}/{MAX_POSITIONS} vị thế đang mở")
                            log_delay_and_sleep()
                            continue  # Bỏ qua lệnh này, chờ cycle tiếp theo
                        
                        # ⚠️ QUAN TRỌNG: Check thời gian giữa 2 lệnh cùng chiều
                        # Lấy lệnh cùng chiều mới nhất từ MT5 và check xem đã đủ 60 phút chưa
                        if current_position_count > 0:
                            # Xác định loại lệnh cần check (BUY = 0, SELL = 1 trong MT5)
                            check_order_type = 0 if action == "BUY" else 1  # 0 = BUY, 1 = SELL
                            
                            # Lọc các lệnh cùng chiều
                            same_direction_positions = [
                                pos for pos in current_positions 
                                if pos.type == check_order_type
                            ]
                            
                            if same_direction_positions:
                                # Lấy lệnh mới nhất cùng chiều (time lớn nhất)
                                latest_same_direction = max(same_direction_positions, key=lambda x: x.time)
                                
                                # Chuyển đổi time từ timestamp (seconds) sang datetime
                                latest_open_time = datetime.fromtimestamp(latest_same_direction.time)
                                now_time = datetime.now()
                                
                                # Tính thời gian đã trôi qua (timedelta)
                                time_elapsed = now_time - latest_open_time
                                time_elapsed_minutes = time_elapsed.total_seconds() / 60
                                
                                # Kiểm tra xem đã đủ MIN_TIME_BETWEEN_SAME_DIRECTION phút chưa
                                if time_elapsed_minutes < MIN_TIME_BETWEEN_SAME_DIRECTION:
                                    remaining_minutes = int(MIN_TIME_BETWEEN_SAME_DIRECTION - time_elapsed_minutes)
                                    remaining_seconds = int((MIN_TIME_BETWEEN_SAME_DIRECTION - time_elapsed_minutes) * 60) % 60
                                    remaining_total_seconds = int((MIN_TIME_BETWEEN_SAME_DIRECTION - time_elapsed_minutes) * 60)
                                    
                                    # Lưu thông tin delay để log sau
                                    pending_delay_info = {
                                        'action': action,
                                        'strength': strength,
                                        'remaining_minutes': remaining_minutes,
                                        'remaining_seconds': remaining_seconds,
                                        'remaining_total_seconds': remaining_total_seconds,
                                        'next_check_time': datetime.now() + timedelta(seconds=remaining_total_seconds)
                                    }
                                    
                                    # Log rõ ràng với format đẹp
                                    logging.info("=" * 60)
                                    logging.info(f"⏸️ TÍN HIỆU {action} {self.symbol} - KHÔNG ĐỦ ĐIỀU KIỆN THỜI GIAN")
                                    logging.info("=" * 60)
                                    logging.info(f"   📊 Tín hiệu: {action} (Strength: {strength})")
                                    logging.info(f"   ⏰ Lệnh {action} cuối cùng mở lúc: {latest_open_time.strftime('%Y-%m-%d %H:%M:%S')}")
                                    logging.info(f"   ⏱️ Thời gian đã trôi qua: {int(time_elapsed_minutes)} phút {int(time_elapsed.total_seconds() % 60)} giây")
                                    logging.info(f"   ⚠️ Cần đợi thêm: {remaining_minutes} phút {remaining_seconds} giây")
                                    logging.info(f"   📋 Rule: Tối thiểu {MIN_TIME_BETWEEN_SAME_DIRECTION} phút giữa 2 lệnh cùng chiều")
                                    logging.info("=" * 60)
                                    logging.info(f"   🔄 Bỏ qua tín hiệu này, chờ cycle tiếp theo...")
                                    logging.info("=" * 60)
                                    
                                    log_delay_and_sleep()
                                    continue  # Bỏ qua lệnh này, chờ cycle tiếp theo
                        
                        # Kiểm tra risk manager TRƯỚC KHI gọi execute_trade
                        if not self.risk_manager.can_open_trade(action):
                            logging.warning(f"❌ Risk Manager chặn: Không thể mở lệnh {action}")
                            log_delay_and_sleep()
                            continue  # Bỏ qua lệnh này, chờ cycle tiếp theo
                        
                        # Thực hiện giao dịch
                        result = self.execute_trade(
                                action, 
                                signal.get('sl_pips', 0), 
                                signal.get('tp_pips', 0),
                                strength
                        )
                        
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            ticket = result.order
                            logging.info("=" * 60)
                            logging.info(f"✅ LỆNH  {action} XAUUSD THÀNH CÔNG!")
                            logging.info("=" * 60)
                            logging.info(f"   - Ticket: {ticket}")
                            logging.info(f"   - Volume: {result.volume} lots")
                            logging.info(f"   - Price: {result.price:.2f}")
                            logging.info(f"   - SL: {result.request.sl:.2f}")
                            logging.info(f"   - TP: {result.request.tp:.2f}")
                            logging.info("=" * 60)
                            
                            # Gửi thông báo Telegram về lệnh thành công
                            if self.use_telegram:
                                success_message = (
                                    f"✅ <b>LỆNH {action} XAUUSD THÀNH CÔNG</b>\n\n"
                                    f"📊 <b>Thông tin lệnh:</b>\n"
                                    f"   • Ticket: <code>{ticket}</code>\n"
                                    f"   • Volume: <b>{result.volume}</b> lots\n"
                                    f"   • Giá vào: <b>{result.price:.2f}</b>\n"
                                    f"   • SL: <b>{result.request.sl:.2f}</b> ({signal.get('sl_pips', 0)} pips)\n"
                                    f"   • TP: <b>{result.request.tp:.2f}</b> ({signal.get('tp_pips', 0)} pips)\n"
                                    f"   • Risk: <b>${account_info['balance'] * (RISK_PER_TRADE / 100):.2f}</b> ({RISK_PER_TRADE}%)\n\n"
                                    f"💰 <b>Tài khoản:</b>\n"
                                    f"   • Equity: <b>${account_info['equity']:.2f}</b>\n"
                                    f"   • Balance: <b>${account_info['balance']:.2f}</b>\n"
                                    f"   • Positions: <b>{num_positions + 1}/{MAX_POSITIONS}</b>\n\n"
                                    f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                                )
                                self.send_telegram_message(success_message)
                            
                            self.risk_manager.record_trade(success=True)
                            
                            # Reset signal tracking khi mở lệnh thành công (để có thể gửi tín hiệu mới sau đó)
                            self.last_signal_sent = None
                            self.last_signal_time = None
                        elif result is None:
                            # result = None nghĩa là execute_trade() return None (do risk manager chặn hoặc lỗi khác)
                            # Đã log warning trong execute_trade(), không cần log lại lỗi ở đây
                            logging.debug(f"⚠️ execute_trade() trả về None - đã được xử lý trong execute_trade()")
                        else:
                            # result có giá trị nhưng retcode != DONE → Lỗi thực sự từ MT5
                            error_msg = result.comment if hasattr(result, 'comment') else str(mt5.last_error())
                            logging.error("=" * 60)
                            logging.error(f"❌ LỆNH {action} THẤT BẠI")
                            logging.error("=" * 60)
                            logging.error(f"   - Lỗi: {error_msg}")
                            logging.error(f"   - Retcode: {result.retcode if hasattr(result, 'retcode') else 'None'}")
                            logging.error("=" * 60)
                            
                            # Gửi thông báo Telegram về lỗi
                            if self.use_telegram:
                                error_message = (
                                    f"❌ <b>LỆNH {action} THẤT BẠI</b>\n\n"
                                    f"⚠️ <b>Lỗi:</b> {error_msg}\n\n"
                                    f"📊 Tín hiệu: Strength={strength}, SL={signal.get('sl_pips', 0)}pips, TP={signal.get('tp_pips', 0)}pips\n\n"
                                    f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                                )
                                self.send_telegram_message(error_message)
                            
                            self.risk_manager.record_trade(success=False)
                    else:
                        # action == 'HOLD'
                        logging.debug(f"📊 Tín hiệu: HOLD (Strength: {strength})")
                        # Reset delay info khi tín hiệu là HOLD
                        pending_delay_info = None
                else:
                    logging.debug("📊 Không có tín hiệu từ Technical Analyzer")
                    # Reset delay info khi không có tín hiệu
                    pending_delay_info = None
                
                # Chờ trước khi kiểm tra tiếp (chỉ khi không có continue nào được gọi)
                log_delay_and_sleep()
                
                # Reset delay info sau khi đã log (nếu có)
                if pending_delay_info:
                    pending_delay_info = None
                
            except KeyboardInterrupt:
                logging.info("=" * 60)
                logging.info("⏹️ Bot được dừng bởi người dùng (Ctrl+C)")
                logging.info("=" * 60)
                break
            except Exception as e:
                logging.error("=" * 60)
                logging.error(f"❌ LỖI TRONG VÒNG LẶP CHÍNH")
                logging.error("=" * 60)
                logging.error(f"   - Exception: {type(e).__name__}: {e}", exc_info=True)
                logging.error("=" * 60)
                time.sleep(60)
                
    def stop(self):
        """Dừng bot"""
        logging.info("=" * 60)
        logging.info("🛑 ĐANG DỪNG BOT...")
        logging.info("=" * 60)
        
        # Không gửi Telegram khi bot dừng (chỉ gửi khi có kết quả lệnh)
        
        mt5.shutdown()
        logging.info("✅ MT5 đã ngắt kết nối")
        logging.info("=" * 60)
        logging.info("👋 Bot đã dừng hoàn toàn")
        logging.info("=" * 60)
    
    def _manage_trailing_stops(self):
        """
        Quản lý Trailing Stop chuyên nghiệp với 3 giai đoạn:
        1. Break-Even Step: Dời SL về entry + buffer khi đạt BREAK_EVEN_START_PIPS
        2. ATR-Based Trailing: Dời SL theo ATR × ATR_K
        3. Partial Close: Chốt một phần lợi nhuận khi đạt TP1, TP2, TP3
        """
        # Kiểm tra xem có bật trailing stop không
        enable_trailing = ENABLE_TRAILING_STOP if 'ENABLE_TRAILING_STOP' in globals() else True
        if not enable_trailing:
            return
        
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None or len(positions) == 0:
            return
        
        # Lấy tham số từ config
        break_even_start_pips = BREAK_EVEN_START_PIPS if 'BREAK_EVEN_START_PIPS' in globals() else 600
        break_even_buffer_pips = BREAK_EVEN_BUFFER_PIPS if 'BREAK_EVEN_BUFFER_PIPS' in globals() else 50
        atr_trailing_k = ATR_TRAILING_K if 'ATR_TRAILING_K' in globals() else 1.5
        atr_min_distance_pips = ATR_TRAILING_MIN_DISTANCE_PIPS if 'ATR_TRAILING_MIN_DISTANCE_PIPS' in globals() else 100
        trailing_interval = 10  # Giây - tránh modify quá thường xuyên
        
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            return
        
        symbol_info = mt5.symbol_info(self.symbol)
        if not symbol_info:
            return
        
        # Lấy ATR cho ATR-based trailing
        df = self.get_price_data(100)
        if df is None or len(df) < 14:
            atr_value = None
        else:
            atr_series = self.technical_analyzer.calculate_atr(df['high'], df['low'], df['close'])
            atr_value = atr_series.iloc[-1] if not atr_series.empty else None
            if atr_value is not None:
                atr_value = atr_value / 0.01  # Convert to pips (XAUUSD: 1 pip = 0.01)
        
        # Kiểm tra broker's stops_level
        stops_level = symbol_info.trade_stops_level if hasattr(symbol_info, 'trade_stops_level') else 0
        stops_level_pips = stops_level / 0.01 if stops_level > 0 else 0
        
        current_time = time.time()
        
        for pos in positions:
            ticket = pos.ticket
            entry_price = pos.price_open
            current_sl = pos.sl
            current_volume = pos.volume
            
            # Kiểm tra interval để tránh modify quá thường xuyên
            if ticket in self.last_trailing_check:
                if current_time - self.last_trailing_check[ticket] < trailing_interval:
                    continue
            
            # Tính profit hiện tại (pips)
            if pos.type == mt5.ORDER_TYPE_BUY:
                current_price = tick.bid
                profit_pips = (current_price - entry_price) / 0.01
            else:  # SELL
                current_price = tick.ask
                profit_pips = (entry_price - current_price) / 0.01
            
            # ====================================================================
            # BƯỚC 1: BREAK-EVEN STEP
            # Kích hoạt khi: profit_pips >= BREAK_EVEN_START_PIPS (600 pips)
            # ====================================================================
            if profit_pips >= break_even_start_pips and ticket not in self.breakeven_activated:
                # Dời SL về entry + buffer
                if pos.type == mt5.ORDER_TYPE_BUY:
                    new_sl = entry_price + (break_even_buffer_pips * 0.01)
                    # Đảm bảo SL mới cao hơn SL hiện tại hoặc SL hiện tại < entry
                    if new_sl > current_sl or current_sl < entry_price:
                        if self._update_sl(ticket, new_sl, pos.tp, "Break-Even"):
                            self.breakeven_activated.add(ticket)
                            logging.info(f"✅ Break-Even kích hoạt: Ticket {ticket}, SL: {current_sl:.2f} → {new_sl:.2f} (Profit: {profit_pips:.1f} pips ≥ {break_even_start_pips} pips)")
                            
                            # Gửi Telegram notification
                            if self.use_telegram:
                                direction = "BUY"
                                pip_value_per_lot = 1  # XAUUSD: 1 pip = $1 cho 1 lot
                                protected_usd = break_even_buffer_pips * pip_value_per_lot * pos.volume
                                message = f"<b>🛡️ BREAK-EVEN KÍCH HOẠT - {self.symbol}</b>\n\n"
                                message += f"<b>Thông tin lệnh:</b>\n"
                                message += f"• Ticket: <code>{ticket}</code>\n"
                                message += f"• Loại: <b>{direction}</b>\n"
                                message += f"• Entry: <b>{entry_price:.2f}</b>\n"
                                message += f"• SL cũ: <b>{current_sl:.2f}</b>\n"
                                message += f"• SL mới: <b>{new_sl:.2f}</b> (Entry + {break_even_buffer_pips} pips)\n\n"
                                message += f"<b>Trạng thái:</b>\n"
                                message += f"• Giá hiện tại: <b>{current_price:.2f}</b>\n"
                                message += f"• Profit: <b>{profit_pips:.1f} pips</b> (≥ {break_even_start_pips} pips)\n"
                                message += f"• Protected: <b>${protected_usd:.2f}</b>\n"
                                message += f"• Volume: <b>{pos.volume:.2f} lots</b>\n\n"
                                message += f"✅ Lệnh đã được bảo vệ - Không còn rủi ro!"
                                self.send_telegram_message(message)
                else:  # SELL
                    new_sl = entry_price - (break_even_buffer_pips * 0.01)
                    # Đảm bảo SL mới thấp hơn SL hiện tại hoặc SL hiện tại > entry
                    if new_sl < current_sl or current_sl == 0 or current_sl > entry_price:
                        if self._update_sl(ticket, new_sl, pos.tp, "Break-Even"):
                            self.breakeven_activated.add(ticket)
                            logging.info(f"✅ Break-Even kích hoạt: Ticket {ticket}, SL: {current_sl:.2f} → {new_sl:.2f} (Profit: {profit_pips:.1f} pips ≥ {break_even_start_pips} pips)")
                            
                            # Gửi Telegram notification
                            if self.use_telegram:
                                direction = "SELL"
                                pip_value_per_lot = 1  # XAUUSD: 1 pip = $1 cho 1 lot
                                protected_usd = break_even_buffer_pips * pip_value_per_lot * pos.volume
                                message = f"<b>🛡️ BREAK-EVEN KÍCH HOẠT - {self.symbol}</b>\n\n"
                                message += f"<b>Thông tin lệnh:</b>\n"
                                message += f"• Ticket: <code>{ticket}</code>\n"
                                message += f"• Loại: <b>{direction}</b>\n"
                                message += f"• Entry: <b>{entry_price:.2f}</b>\n"
                                message += f"• SL cũ: <b>{current_sl:.2f}</b>\n"
                                message += f"• SL mới: <b>{new_sl:.2f}</b> (Entry - {break_even_buffer_pips} pips)\n\n"
                                message += f"<b>Trạng thái:</b>\n"
                                message += f"• Giá hiện tại: <b>{current_price:.2f}</b>\n"
                                message += f"• Profit: <b>{profit_pips:.1f} pips</b> (≥ {break_even_start_pips} pips)\n"
                                message += f"• Protected: <b>${protected_usd:.2f}</b>\n"
                                message += f"• Volume: <b>{pos.volume:.2f} lots</b>\n\n"
                                message += f"✅ Lệnh đã được bảo vệ - Không còn rủi ro!"
                                self.send_telegram_message(message)
            
            # ====================================================================
            # BƯỚC 2: PARTIAL CLOSE (nếu bật)
            # ====================================================================
            enable_partial = ENABLE_PARTIAL_CLOSE if 'ENABLE_PARTIAL_CLOSE' in globals() else True
            if enable_partial:
                self._manage_partial_close(pos, profit_pips, ticket)
            
            # ====================================================================
            # BƯỚC 3: ATR-BASED TRAILING
            # Kích hoạt khi: Đã break-even (profit >= 600 pips) VÀ ATR có giá trị
            # Khoảng cách trailing: ATR × ATR_TRAILING_K (1.5) hoặc tối thiểu 100 pips
            # ====================================================================
            if ticket in self.breakeven_activated and atr_value is not None:
                # Tính khoảng cách trailing dựa trên ATR
                trail_distance_pips = max(atr_value * atr_trailing_k, atr_min_distance_pips)
                
                # Áp dụng partial close ATR_K nếu đã chốt lời
                if ticket in self.partial_close_done:
                    partial_atr_k = PARTIAL_CLOSE_ATR_K if 'PARTIAL_CLOSE_ATR_K' in globals() else 1.0
                    trail_distance_pips = max(atr_value * partial_atr_k, atr_min_distance_pips)
                
                if pos.type == mt5.ORDER_TYPE_BUY:
                    new_sl = current_price - (trail_distance_pips * 0.01)
                    # SL mới phải cao hơn SL hiện tại và >= entry (breakeven)
                    if new_sl > current_sl and new_sl >= entry_price:
                        # Kiểm tra stops_level
                        if stops_level_pips > 0:
                            min_sl = current_price - (stops_level_pips * 0.01)
                            if new_sl < min_sl:
                                new_sl = min_sl
                        
                        if self._update_sl(ticket, new_sl, pos.tp, "ATR Trailing"):
                            self.last_trailing_check[ticket] = current_time
                            logging.info(f"📈 ATR Trailing: Ticket {ticket}, SL: {current_sl:.2f} → {new_sl:.2f} (Profit: {profit_pips:.1f} pips, ATR: {atr_value:.1f} pips, Distance: {trail_distance_pips:.1f} pips)")
                            
                            # Gửi Telegram notification lần đầu tiên ATR Trailing kích hoạt
                            if self.use_telegram and ticket not in self.atr_trailing_first_activation:
                                self.atr_trailing_first_activation.add(ticket)
                                direction = "BUY"
                                pip_value_per_lot = 1  # XAUUSD: 1 pip = $1 cho 1 lot
                                message = f"<b>📈 ATR TRAILING KÍCH HOẠT - {self.symbol}</b>\n\n"
                                message += f"<b>Thông tin lệnh:</b>\n"
                                message += f"• Ticket: <code>{ticket}</code>\n"
                                message += f"• Loại: <b>{direction}</b>\n"
                                message += f"• Entry: <b>{entry_price:.2f}</b>\n"
                                message += f"• SL mới: <b>{new_sl:.2f}</b>\n"
                                message += f"• TP: <b>{pos.tp:.2f}</b>\n\n"
                                message += f"<b>Thông số Trailing:</b>\n"
                                message += f"• ATR: <b>{atr_value:.1f} pips</b>\n"
                                message += f"• Khoảng cách: <b>{trail_distance_pips:.1f} pips</b> (ATR × {atr_trailing_k})\n"
                                message += f"• Giá hiện tại: <b>{current_price:.2f}</b>\n"
                                message += f"• Profit: <b>{profit_pips:.1f} pips</b>\n\n"
                                message += f"🔄 SL sẽ tự động dời theo giá để bảo vệ lợi nhuận!"
                                self.send_telegram_message(message)
                
                else:  # SELL
                    new_sl = current_price + (trail_distance_pips * 0.01)
                    # SL mới phải thấp hơn SL hiện tại và <= entry (breakeven)
                    if (new_sl < current_sl or current_sl == 0) and new_sl <= entry_price:
                        # Kiểm tra stops_level
                        if stops_level_pips > 0:
                            max_sl = current_price + (stops_level_pips * 0.01)
                            if new_sl > max_sl:
                                new_sl = max_sl
                        
                        if self._update_sl(ticket, new_sl, pos.tp, "ATR Trailing"):
                            self.last_trailing_check[ticket] = current_time
                            logging.info(f"📉 ATR Trailing: Ticket {ticket}, SL: {current_sl:.2f} → {new_sl:.2f} (Profit: {profit_pips:.1f} pips, ATR: {atr_value:.1f} pips, Distance: {trail_distance_pips:.1f} pips)")
                            
                            # Gửi Telegram notification lần đầu tiên ATR Trailing kích hoạt
                            if self.use_telegram and ticket not in self.atr_trailing_first_activation:
                                self.atr_trailing_first_activation.add(ticket)
                                direction = "SELL"
                                pip_value_per_lot = 1  # XAUUSD: 1 pip = $1 cho 1 lot
                                message = f"<b>📉 ATR TRAILING KÍCH HOẠT - {self.symbol}</b>\n\n"
                                message += f"<b>Thông tin lệnh:</b>\n"
                                message += f"• Ticket: <code>{ticket}</code>\n"
                                message += f"• Loại: <b>{direction}</b>\n"
                                message += f"• Entry: <b>{entry_price:.2f}</b>\n"
                                message += f"• SL mới: <b>{new_sl:.2f}</b>\n"
                                message += f"• TP: <b>{pos.tp:.2f}</b>\n\n"
                                message += f"<b>Thông số Trailing:</b>\n"
                                message += f"• ATR: <b>{atr_value:.1f} pips</b>\n"
                                message += f"• Khoảng cách: <b>{trail_distance_pips:.1f} pips</b> (ATR × {atr_trailing_k})\n"
                                message += f"• Giá hiện tại: <b>{current_price:.2f}</b>\n"
                                message += f"• Profit: <b>{profit_pips:.1f} pips</b>\n\n"
                                message += f"🔄 SL sẽ tự động dời theo giá để bảo vệ lợi nhuận!"
                                self.send_telegram_message(message)
    
    def _update_sl(self, ticket, new_sl, tp, reason=""):
        """
        Helper function để update SL với error handling
        Gửi Telegram notification khi thành công
        """
        # Lấy thông tin position trước khi update
        pos = mt5.positions_get(ticket=ticket)
        old_sl = None
        pos_type = None
        entry_price = None
        if pos and len(pos) > 0:
            old_sl = pos[0].sl
            pos_type = pos[0].type
            entry_price = pos[0].price_open
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": self.symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": tp
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            # Gửi Telegram notification
            if self.use_telegram and old_sl is not None:
                # Tính profit protected
                tick = mt5.symbol_info_tick(self.symbol)
                if tick:
                    if pos_type == mt5.ORDER_TYPE_BUY:
                        current_price = tick.bid
                        profit_pips = (current_price - entry_price) / 0.01
                        protected_pips = (new_sl - entry_price) / 0.01
                    else:  # SELL
                        current_price = tick.ask
                        profit_pips = (entry_price - current_price) / 0.01
                        protected_pips = (entry_price - new_sl) / 0.01
                    
                    # Tính SL USD
                    position = mt5.positions_get(ticket=ticket)
                    if position and len(position) > 0:
                        lot_size = position[0].volume
                        pip_value_per_lot = 1  # XAUUSD: 1 pip = $1 cho 1 lot
                        sl_usd = abs(new_sl - entry_price) / 0.01 * pip_value_per_lot * lot_size
                        
                        direction = "BUY" if pos_type == mt5.ORDER_TYPE_BUY else "SELL"
                        message = f"<b>📈 DỜI SL THÀNH CÔNG - {self.symbol}</b>\n\n"
                        message += f"<b>Thông tin lệnh:</b>\n"
                        message += f"• Ticket: <code>{ticket}</code>\n"
                        message += f"• Loại: <b>{direction}</b>\n"
                        message += f"• Entry: <b>{entry_price:.2f}</b>\n"
                        message += f"• SL cũ: <b>{old_sl:.2f}</b>\n"
                        message += f"• SL mới: <b>{new_sl:.2f}</b>\n"
                        message += f"• SL USD: <b>${sl_usd:.2f}</b>\n"
                        message += f"• Lý do: <b>{reason}</b>\n\n"
                        message += f"<b>Trạng thái:</b>\n"
                        message += f"• Giá hiện tại: <b>{current_price:.2f}</b>\n"
                        message += f"• Profit: <b>{profit_pips:.1f} pips</b>\n"
                        message += f"• Protected: <b>{protected_pips:.1f} pips</b>\n"
                        
                        self.send_telegram_message(message)
            
            return True
        else:
            if result:
                logging.debug(f"⚠️ Update SL thất bại ({reason}): {result.comment if hasattr(result, 'comment') else 'Unknown'}")
            return False
    
    def _manage_partial_close(self, pos, profit_pips, ticket):
        """
        Quản lý Partial Close: Chốt một phần lợi nhuận khi đạt TP1, TP2, TP3
        
        Logic:
        - TP1: Đóng 30-50% volume khi đạt PARTIAL_CLOSE_TP1_PIPS
        - TP2: Đóng thêm 25-30% volume còn lại khi đạt PARTIAL_CLOSE_TP2_PIPS
        - TP3: Đóng thêm 25-30% volume còn lại khi đạt PARTIAL_CLOSE_TP3_PIPS
        - Sau mỗi lần partial close, dời SL về break-even + buffer lớn hơn
        """
        # Khởi tạo tracking nếu chưa có
        if ticket not in self.partial_close_done:
            self.partial_close_done[ticket] = [False, False, False]
        
        tp1_done, tp2_done, tp3_done = self.partial_close_done[ticket]
        
        # Lấy tham số từ config
        tp1_pips = PARTIAL_CLOSE_TP1_PIPS if 'PARTIAL_CLOSE_TP1_PIPS' in globals() else 1000
        tp1_percent = PARTIAL_CLOSE_TP1_PERCENT if 'PARTIAL_CLOSE_TP1_PERCENT' in globals() else 40
        tp2_pips = PARTIAL_CLOSE_TP2_PIPS if 'PARTIAL_CLOSE_TP2_PIPS' in globals() else 2000
        tp2_percent = PARTIAL_CLOSE_TP2_PERCENT if 'PARTIAL_CLOSE_TP2_PERCENT' in globals() else 30
        tp3_pips = PARTIAL_CLOSE_TP3_PIPS if 'PARTIAL_CLOSE_TP3_PIPS' in globals() else 3000
        tp3_percent = PARTIAL_CLOSE_TP3_PERCENT if 'PARTIAL_CLOSE_TP3_PERCENT' in globals() else 30
        partial_buffer_pips = PARTIAL_CLOSE_SL_BUFFER_PIPS if 'PARTIAL_CLOSE_SL_BUFFER_PIPS' in globals() else 100
        
        entry_price = pos.price_open
        current_volume = pos.volume
        
        # Kiểm tra lot size tối thiểu
        symbol_info = mt5.symbol_info(self.symbol)
        if not symbol_info:
            return
        
        min_lot = symbol_info.volume_min if symbol_info.volume_min > 0 else 0.01
        
        # TP1: Đóng 30-50% volume
        if profit_pips >= tp1_pips and not tp1_done:
            close_volume = round(current_volume * (tp1_percent / 100), 2)
            close_volume = max(min_lot, close_volume)  # Đảm bảo >= min_lot
            
            if close_volume < current_volume:  # Đảm bảo không đóng hết
                if self._close_partial_position(pos, close_volume, "TP1"):
                    self.partial_close_done[ticket][0] = True
                    # Dời SL về break-even + buffer lớn hơn
                    new_sl = entry_price + (partial_buffer_pips * 0.01) if pos.type == mt5.ORDER_TYPE_BUY else entry_price - (partial_buffer_pips * 0.01)
                    self._update_sl(ticket, new_sl, pos.tp, "Partial Close TP1")
                    logging.info(f"💰 Partial Close TP1: Ticket {ticket}, Đóng {close_volume:.2f} lots ({tp1_percent}%), Dời SL về {new_sl:.2f}")
        
        # TP2: Đóng thêm 25-30% volume còn lại
        elif profit_pips >= tp2_pips and tp1_done and not tp2_done:
            # Lấy volume hiện tại lại (có thể đã thay đổi sau TP1)
            current_pos = mt5.positions_get(ticket=ticket)
            if current_pos and len(current_pos) > 0:
                remaining_volume = current_pos[0].volume
                close_volume = round(remaining_volume * (tp2_percent / 100), 2)
                close_volume = max(min_lot, close_volume)
                
                if close_volume < remaining_volume:
                    if self._close_partial_position(current_pos[0], close_volume, "TP2"):
                        self.partial_close_done[ticket][1] = True
                        new_sl = entry_price + (partial_buffer_pips * 0.01) if pos.type == mt5.ORDER_TYPE_BUY else entry_price - (partial_buffer_pips * 0.01)
                        self._update_sl(ticket, new_sl, pos.tp, "Partial Close TP2")
                        logging.info(f"💰 Partial Close TP2: Ticket {ticket}, Đóng {close_volume:.2f} lots ({tp2_percent}%), Dời SL về {new_sl:.2f}")
        
        # TP3: Đóng thêm 25-30% volume còn lại
        elif profit_pips >= tp3_pips and tp2_done and not tp3_done:
            current_pos = mt5.positions_get(ticket=ticket)
            if current_pos and len(current_pos) > 0:
                remaining_volume = current_pos[0].volume
                close_volume = round(remaining_volume * (tp3_percent / 100), 2)
                close_volume = max(min_lot, close_volume)
                
                if close_volume < remaining_volume:
                    if self._close_partial_position(current_pos[0], close_volume, "TP3"):
                        self.partial_close_done[ticket][2] = True
                        new_sl = entry_price + (partial_buffer_pips * 0.01) if pos.type == mt5.ORDER_TYPE_BUY else entry_price - (partial_buffer_pips * 0.01)
                        self._update_sl(ticket, new_sl, pos.tp, "Partial Close TP3")
                        logging.info(f"💰 Partial Close TP3: Ticket {ticket}, Đóng {close_volume:.2f} lots ({tp3_percent}%), Dời SL về {new_sl:.2f}")
    
    def _close_partial_position(self, pos, close_volume, reason=""):
        """
        Đóng một phần position
        
        Args:
            pos: MT5 position object
            close_volume: Volume cần đóng (lots)
            reason: Lý do đóng (TP1, TP2, TP3)
        
        Returns:
            True nếu thành công, False nếu thất bại
        """
        if close_volume >= pos.volume:
            logging.warning(f"⚠️ Partial Close: Volume đóng ({close_volume}) >= Volume hiện tại ({pos.volume}) → Bỏ qua")
            return False
        
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            return False
        
        # Xác định giá đóng
        if pos.type == mt5.ORDER_TYPE_BUY:
            close_price = tick.bid
            order_type = mt5.ORDER_TYPE_SELL
        else:  # SELL
            close_price = tick.ask
            order_type = mt5.ORDER_TYPE_BUY
        
        # Lấy filling mode phù hợp
        filling_mode = self.get_filling_mode(self.symbol)
        
        # Tạo request để đóng một phần
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": close_volume,
            "type": order_type,
            "position": pos.ticket,
            "price": close_price,
            "deviation": DEVIATION if 'DEVIATION' in globals() else 100,
            "magic": 888888,
            "comment": f"Partial Close {reason}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }
        
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            # Gửi Telegram notification
            if self.use_telegram:
                # Tính profit và lợi nhuận
                profit_usd = 0
                if pos.type == mt5.ORDER_TYPE_BUY:
                    profit_pips = (close_price - pos.price_open) / 0.01
                else:  # SELL
                    profit_pips = (pos.price_open - close_price) / 0.01
                
                pip_value_per_lot = 1  # XAUUSD: 1 pip = $1 cho 1 lot
                profit_usd = profit_pips * pip_value_per_lot * close_volume
                
                direction = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
                remaining_volume = pos.volume - close_volume
                
                message = f"<b>💰 PARTIAL CLOSE THÀNH CÔNG - {self.symbol}</b>\n\n"
                message += f"<b>Thông tin lệnh:</b>\n"
                message += f"• Ticket: <code>{ticket}</code>\n"
                message += f"• Loại: <b>{direction}</b>\n"
                message += f"• Entry: <b>{pos.price_open:.2f}</b>\n"
                message += f"• Close Price: <b>{close_price:.2f}</b>\n\n"
                message += f"<b>Partial Close:</b>\n"
                message += f"• Mốc: <b>{reason}</b>\n"
                message += f"• Volume đóng: <b>{close_volume:.2f} lots</b>\n"
                message += f"• Volume còn lại: <b>{remaining_volume:.2f} lots</b>\n\n"
                message += f"<b>Lợi nhuận:</b>\n"
                message += f"• Profit: <b>{profit_pips:.1f} pips</b>\n"
                message += f"• Profit USD: <b>${profit_usd:.2f}</b>\n"
                
                self.send_telegram_message(message)
            
            return True
        else:
            if result:
                logging.warning(f"⚠️ Partial Close {reason} thất bại: {result.comment if hasattr(result, 'comment') else 'Unknown'}")
            return False
    
    def _manage_smart_exit(self):
        """
        Quản lý Smart Exit: Đóng lệnh sớm khi tín hiệu đảo chiều hoặc mất động lượng
        
        Logic:
        - Đóng lệnh nếu có OPPOSITE_SIGNAL_COUNT_TO_EXIT tín hiệu ngược chiều
        - Đóng lệnh nếu RSI quay đầu vượt vùng trung tính
        - Đóng lệnh nếu lợi nhuận giảm quá nhanh (drawdown > %)
        """
        # Kiểm tra xem có bật smart exit không
        enable_smart_exit = ENABLE_SMART_EXIT if 'ENABLE_SMART_EXIT' in globals() else True
        if not enable_smart_exit:
            return
        
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None or len(positions) == 0:
            return
        
        # Lấy dữ liệu giá để phân tích
        df = self.get_price_data(100)
        if df is None or len(df) < 50:
            return
        
        # Phân tích tín hiệu hiện tại
        current_signal = self.technical_analyzer.analyze(df)
        if not current_signal:
            return
        
        current_action = current_signal.get('action', 'HOLD')
        current_rsi = df.iloc[-1]['rsi'] if 'rsi' in df.columns else 50
        
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            return
        
        # Lấy tham số từ config
        opposite_signal_count = OPPOSITE_SIGNAL_COUNT_TO_EXIT if 'OPPOSITE_SIGNAL_COUNT_TO_EXIT' in globals() else 2
        enable_rsi_exit = ENABLE_RSI_EXIT if 'ENABLE_RSI_EXIT' in globals() else True
        rsi_exit_threshold = RSI_EXIT_THRESHOLD if 'RSI_EXIT_THRESHOLD' in globals() else 50
        enable_profit_dd_exit = ENABLE_PROFIT_DRAWDOWN_EXIT if 'ENABLE_PROFIT_DRAWDOWN_EXIT' in globals() else True
        profit_dd_exit_percent = PROFIT_DRAWDOWN_EXIT_PERCENT if 'PROFIT_DRAWDOWN_EXIT_PERCENT' in globals() else 40
        
        # Track đỉnh profit cho mỗi lệnh
        if not hasattr(self, 'position_peak_profit'):
            self.position_peak_profit = {}  # {ticket: peak_profit_pips}
        
        for pos in positions:
            ticket = pos.ticket
            entry_price = pos.price_open
            
            # Tính profit hiện tại (pips)
            if pos.type == mt5.ORDER_TYPE_BUY:
                current_price = tick.bid
                profit_pips = (current_price - entry_price) / 0.01
            else:  # SELL
                current_price = tick.ask
                profit_pips = (entry_price - current_price) / 0.01
            
            # Cập nhật đỉnh profit
            if ticket not in self.position_peak_profit or profit_pips > self.position_peak_profit[ticket]:
                self.position_peak_profit[ticket] = profit_pips
            
            peak_profit_pips = self.position_peak_profit.get(ticket, profit_pips)
            
            # Kiểm tra 1: Tín hiệu ngược chiều
            if current_action != 'HOLD':
                position_type = 'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL'
                if current_action != position_type:
                    # Có tín hiệu ngược chiều
                    if not hasattr(self, 'opposite_signal_count'):
                        self.opposite_signal_count = {}
                    if ticket not in self.opposite_signal_count:
                        self.opposite_signal_count[ticket] = 0
                    
                    self.opposite_signal_count[ticket] += 1
                    
                    if self.opposite_signal_count[ticket] >= opposite_signal_count:
                        # Đóng lệnh vì có quá nhiều tín hiệu ngược chiều
                        logging.info(f"🔄 Smart Exit: Ticket {ticket} - {opposite_signal_count} tín hiệu ngược chiều ({current_action})")
                        self._close_position(ticket, "Smart Exit: Tín hiệu đảo chiều")
                        continue
                else:
                    # Reset counter nếu tín hiệu cùng chiều
                    if hasattr(self, 'opposite_signal_count') and ticket in self.opposite_signal_count:
                        self.opposite_signal_count[ticket] = 0
            
            # Kiểm tra 2: RSI quay đầu vượt vùng trung tính
            if enable_rsi_exit and profit_pips > 0:  # Chỉ exit khi đang lời
                if pos.type == mt5.ORDER_TYPE_BUY and current_rsi < rsi_exit_threshold:
                    # BUY nhưng RSI < 50 → Momentum giảm
                    logging.info(f"🔄 Smart Exit: Ticket {ticket} - RSI quay đầu ({current_rsi:.2f} < {rsi_exit_threshold})")
                    self._close_position(ticket, "Smart Exit: RSI quay đầu")
                    continue
                elif pos.type == mt5.ORDER_TYPE_SELL and current_rsi > rsi_exit_threshold:
                    # SELL nhưng RSI > 50 → Momentum giảm
                    logging.info(f"🔄 Smart Exit: Ticket {ticket} - RSI quay đầu ({current_rsi:.2f} > {rsi_exit_threshold})")
                    self._close_position(ticket, "Smart Exit: RSI quay đầu")
                    continue
            
            # Kiểm tra 3: Profit drawdown (lợi nhuận giảm quá nhanh)
            if enable_profit_dd_exit and peak_profit_pips > 0:
                profit_drawdown_percent = ((peak_profit_pips - profit_pips) / peak_profit_pips) * 100
                if profit_drawdown_percent > profit_dd_exit_percent:
                    logging.info(f"🔄 Smart Exit: Ticket {ticket} - Profit drawdown {profit_drawdown_percent:.1f}% (từ đỉnh {peak_profit_pips:.1f} → {profit_pips:.1f} pips)")
                    self._close_position(ticket, f"Smart Exit: Profit drawdown {profit_drawdown_percent:.1f}%")
                    continue
    
    def _close_position(self, ticket, reason):
        """
        Đóng lệnh với lý do cụ thể
        
        Args:
            ticket: Ticket của lệnh cần đóng
            reason: Lý do đóng lệnh
        """
        position = None
        positions = mt5.positions_get(symbol=self.symbol)
        if positions:
            for pos in positions:
                if pos.ticket == ticket:
                    position = pos
                    break
        
        if not position:
            logging.warning(f"⚠️ Không tìm thấy position với ticket {ticket}")
            return
        
        # Xác định loại lệnh đóng (ngược với loại mở)
        if position.type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(self.symbol).bid
        else:  # SELL
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(self.symbol).ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": DEVIATION if 'DEVIATION' in globals() else 100,
            "magic": 202411,
            "comment": f"Smart_Exit_{reason}",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logging.info(f"✅ Smart Exit thành công: Ticket {ticket}, Lý do: {reason}")
            
            # Cleanup tracking
            if hasattr(self, 'position_peak_profit') and ticket in self.position_peak_profit:
                del self.position_peak_profit[ticket]
            if hasattr(self, 'opposite_signal_count') and ticket in self.opposite_signal_count:
                del self.opposite_signal_count[ticket]
            # Cleanup tracking variables khi position đóng
            if ticket in self.trailing_stop_activated:
                self.trailing_stop_activated.remove(ticket)
            if ticket in self.breakeven_activated:
                self.breakeven_activated.remove(ticket)
            if ticket in self.partial_close_done:
                del self.partial_close_done[ticket]
            if ticket in self.last_trailing_check:
                del self.last_trailing_check[ticket]
            if ticket in self.atr_trailing_first_activation:
                self.atr_trailing_first_activation.remove(ticket)
        elif result:
            logging.warning(f"⚠️ Smart Exit thất bại: Ticket {ticket}, {result.comment if hasattr(result, 'comment') else 'Unknown'}")

def main():
    logging.info("=" * 60)
    logging.info("🚀 KHỞI ĐỘNG BOT XAUUSD")
    logging.info("=" * 60)
    
    bot = XAUUSD_Bot()
    
    if not bot.setup_mt5():
        logging.error("❌ Không thể khởi tạo MT5. Thoát chương trình.")
        return
        
    try:
        bot.run_bot()
    except KeyboardInterrupt:
        logging.info("👋 Bot được dừng bởi người dùng (KeyboardInterrupt)")
    except Exception as e:
        logging.error(f"❌ Lỗi không mong đợi: {e}", exc_info=True)
    finally:
        bot.stop()

if __name__ == "__main__":
    main()