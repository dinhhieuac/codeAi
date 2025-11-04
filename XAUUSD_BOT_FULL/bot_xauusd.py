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
        
    def calculate_position_size(self, stop_loss_pips):
        account_info = self.get_account_info()
        if not account_info:
            return 0.01
            
        balance = account_info['balance']
        risk_amount = balance * (RISK_PER_TRADE / 100)
        
        # 1 pip XAUUSD = $10 cho 1 lot
        pip_value = 10
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
        
        # Tính giá và kích thước lệnh
        if signal_type == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = symbol_info.ask
            sl_price = price - (sl_pips * 0.01)
            tp_price = price + (tp_pips * 0.01)
        else:  # SELL
            order_type = mt5.ORDER_TYPE_SELL
            price = symbol_info.bid
            sl_price = price + (sl_pips * 0.01)
            tp_price = price - (tp_pips * 0.01)
        
        # Tính lot size
        lot_size = self.calculate_position_size(sl_pips)
        
        # Lấy thông tin tài khoản
        account_info = self.get_account_info()
        
        # Log thông tin lệnh
        logging.info(f"📊 Thông tin lệnh:")
        logging.info(f"   - Loại: {signal_type}")
        logging.info(f"   - Giá vào: {price:.2f}")
        logging.info(f"   - SL: {sl_price:.2f} ({sl_pips} pips)")
        logging.info(f"   - TP: {tp_price:.2f} ({tp_pips} pips)")
        logging.info(f"   - Lot size: {lot_size}")
        logging.info(f"   - Risk: ${account_info['balance'] * (RISK_PER_TRADE / 100):.2f} ({RISK_PER_TRADE}%)")
        logging.info(f"   - Signal strength: {signal_strength}")
        
        # Gửi lệnh
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 20,
            "magic": 202411,
            "comment": f"XAUUSD_Bot_{signal_type}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        logging.info("📤 Đang gửi lệnh đến MT5...")
        result = mt5.order_send(request)
        
        if result:
            logging.info(f"📥 Response từ MT5: retcode={result.retcode}, comment={result.comment}")
        
        return result
        
    def run_bot(self):
        """Vòng lặp chính của bot"""
        logging.info("=" * 60)
        logging.info("🚀 BOT XAUUSD BẮT ĐẦU CHẠY")
        logging.info("=" * 60)
        
        # Gửi thông báo Telegram khi bot khởi động
        if self.use_telegram:
            start_message = (
                f"🚀 <b>BOT XAUUSD ĐÃ KHỞI ĐỘNG</b>\n\n"
                f"📊 Symbol: <code>{self.symbol}</code>\n"
                f"⏱️ Timeframe: <code>{TIMEFRAME}</code>\n"
                f"💰 Risk: <code>{RISK_PER_TRADE}%</code>\n"
                f"📈 Max positions: <code>{MAX_POSITIONS}</code>\n"
                f"📅 Max daily trades: <code>{MAX_DAILY_TRADES}</code>\n"
                f"⏰ Check interval: <code>{CHECK_INTERVAL}s</code>"
            )
            self.send_telegram_message(start_message)
        
        cycle_count = 0
        
        while True:
            try:
                cycle_count += 1
                logging.info("-" * 60)
                logging.info(f"🔄 CYCLE #{cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logging.info("-" * 60)
                
                # Lấy thông tin tài khoản
                account_info = self.get_account_info()
                num_positions = 0
                if account_info:
                    logging.info(f"💵 Tài khoản: Equity=${account_info['equity']:.2f} | Balance=${account_info['balance']:.2f} | Free Margin=${account_info['free_margin']:.2f}")
                    
                    # Kiểm tra số position đang mở
                    positions = mt5.positions_get(symbol=self.symbol)
                    if positions is None:
                        positions = []
                    num_positions = len(positions)
                    logging.info(f"📊 Vị thế đang mở: {num_positions}/{MAX_POSITIONS}")
                    
                    if num_positions > 0:
                        total_profit = sum(pos.profit for pos in positions)
                        logging.info(f"   - Tổng P&L: ${total_profit:.2f}")
                        for pos in positions:
                            order_type = "BUY" if pos.type == 0 else "SELL"
                            logging.info(f"   - {order_type} {pos.volume} lots @ {pos.price_open:.2f}, P&L: ${pos.profit:.2f}")
                else:
                    account_info = {'equity': 0, 'balance': 0, 'free_margin': 0}
                
                # Lấy dữ liệu giá
                df = self.get_price_data(100)
                if df is None:
                    logging.error("❌ Không lấy được dữ liệu giá, chờ 30s...")
                    time.sleep(30)
                    continue
                
                # Log giá hiện tại
                if len(df) > 0:
                    latest_price = df.iloc[-1]
                    tick = mt5.symbol_info_tick(self.symbol)
                    if tick:
                        logging.info(f"📈 Giá hiện tại: {latest_price['close']:.2f} (Bid/Ask: {tick.bid:.2f}/{tick.ask:.2f})")
                    else:
                        logging.info(f"📈 Giá hiện tại: {latest_price['close']:.2f}")
                
                # Phân tích kỹ thuật
                logging.info("🔍 Đang phân tích kỹ thuật...")
                signal = self.technical_analyzer.analyze(df)
                
                if signal:
                    action = signal.get('action', 'HOLD')
                    strength = signal.get('strength', 0)
                    
                    if action != 'HOLD':
                        logging.info("=" * 60)
                        logging.info(f"🎯 TÍN HIỆU GIAO DỊCH PHÁT HIỆN!")
                        logging.info("=" * 60)
                        logging.info(f"   - Action: {action}")
                        logging.info(f"   - Strength: {strength}")
                        logging.info(f"   - SL: {signal.get('sl_pips', 0)} pips")
                        logging.info(f"   - TP: {signal.get('tp_pips', 0)} pips")
                        logging.info("=" * 60)
                        
                        # Gửi thông báo Telegram về tín hiệu (chỉ khi tín hiệu mới hoặc thay đổi)
                        # Tạo signature của tín hiệu để so sánh
                        signal_signature = (action, strength, signal.get('sl_pips', 0), signal.get('tp_pips', 0))
                        now_time = datetime.now()
                        
                        # Kiểm tra xem tín hiệu có mới/khác không
                        signal_changed = (self.last_signal_sent != signal_signature)
                        cooldown_passed = (self.last_signal_time is None or 
                                          (now_time - self.last_signal_time).total_seconds() >= self.telegram_signal_cooldown)
                        
                        should_send_signal = signal_changed and cooldown_passed
                        
                        if self.use_telegram and should_send_signal:
                            signal_message = (
                                f"🎯 <b>TÍN HIỆU {action} {self.symbol}</b>\n\n"
                                f"📊 <b>Thông tin tín hiệu:</b>\n"
                                f"   • Strength: <b>{strength}</b>\n"
                                f"   • SL: <b>{signal.get('sl_pips', 0)}</b> pips\n"
                                f"   • TP: <b>{signal.get('tp_pips', 0)}</b> pips\n"
                                f"   • Timeframe: <code>{TIMEFRAME}</code>\n\n"
                                f"💰 <b>Thông tin tài khoản:</b>\n"
                                f"   • Equity: <b>${account_info['equity']:.2f}</b>\n"
                                f"   • Balance: <b>${account_info['balance']:.2f}</b>\n"
                                f"   • Positions: <b>{num_positions}/{MAX_POSITIONS}</b>\n\n"
                                f"⏰ {now_time.strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                            if self.send_telegram_message(signal_message):
                                # Chỉ cập nhật khi gửi thành công
                                self.last_signal_sent = signal_signature
                                self.last_signal_time = now_time
                                logging.debug(f"📱 Đã gửi thông báo Telegram về tín hiệu {action}")
                        elif self.use_telegram and not should_send_signal:
                            if not signal_changed:
                                logging.debug(f"📱 Tín hiệu {action} giống tín hiệu trước → Không gửi Telegram (tránh spam)")
                            elif not cooldown_passed:
                                remaining = int(self.telegram_signal_cooldown - (now_time - self.last_signal_time).total_seconds())
                                logging.debug(f"📱 Cooldown Telegram còn {remaining}s → Không gửi tín hiệu (tránh spam)")
                        
                        # Kiểm tra risk manager TRƯỚC KHI gọi execute_trade
                        if not self.risk_manager.can_open_trade(action):
                            logging.warning(f"❌ Risk Manager chặn: Không thể mở lệnh {action}")
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
                            logging.info(f"✅ LỆNH {action} THÀNH CÔNG!")
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
                                    f"✅ <b>LỆNH {action} THÀNH CÔNG</b>\n\n"
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
                        logging.debug(f"📊 Tín hiệu: HOLD (Strength: {strength})")
                else:
                    logging.debug("📊 Không có tín hiệu từ Technical Analyzer")
                
                # Chờ trước khi kiểm tra tiếp
                logging.info(f"⏳ Chờ {CHECK_INTERVAL} giây trước lần kiểm tra tiếp theo...")
                time.sleep(CHECK_INTERVAL)
                
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
        
        # Gửi thông báo Telegram khi bot dừng
        if self.use_telegram:
            stop_message = (
                f"🛑 <b>BOT XAUUSD ĐÃ DỪNG</b>\n\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.send_telegram_message(stop_message)
        
        mt5.shutdown()
        logging.info("✅ MT5 đã ngắt kết nối")
        logging.info("=" * 60)
        logging.info("👋 Bot đã dừng hoàn toàn")
        logging.info("=" * 60)

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