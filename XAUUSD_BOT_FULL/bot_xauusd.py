import MetaTrader5 as mt5
import pandas as pd
import time
import json
import sys
import re
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
        
    def setup_directories(self):
        os.makedirs('logs', exist_ok=True)
        os.makedirs('data', exist_ok=True)
        
    def setup_mt5(self):
        if not mt5.initialize():
            logging.error("Không thể khởi tạo MT5")
            return False
            
        if not mt5.symbol_select(self.symbol, True):
            logging.error(f"Không thể chọn symbol {self.symbol}")
            return False
            
        logging.info(f"✅ MT5 khởi tạo thành công - {self.symbol}")
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
            return None
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df
        
    def check_market_conditions(self):
        """Kiểm tra điều kiện thị trường"""
        symbol_info = mt5.symbol_info(self.symbol)
        if not symbol_info:
            return False, "Không lấy được symbol info"
            
        # Kiểm tra spread
        spread = (symbol_info.ask - symbol_info.bid) / 0.01
        if spread > MAX_SPREAD:
            return False, f"Spread quá cao: {spread}pips"
            
        # Kiểm tra thời gian giao dịch
        if not self.risk_manager.check_trading_time():
            return False, "Ngoài giờ giao dịch cho phép"
            
        # Kiểm tra điều kiện tài khoản
        if not self.risk_manager.check_account_conditions():
            return False, "Không đủ điều kiện tài khoản"
            
        return True, "OK"
        
    def execute_trade(self, signal_type, sl_pips, tp_pips):
        """Thực hiện giao dịch"""
        
        # Kiểm tra điều kiện thị trường
        market_ok, message = self.check_market_conditions()
        if not market_ok:
            logging.warning(f"❌ Không giao dịch: {message}")
            return None
            
        symbol_info = mt5.symbol_info(self.symbol)
        if not symbol_info:
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
        
        result = mt5.order_send(request)
        return result
        
    def run_bot(self):
        """Vòng lặp chính của bot"""
        logging.info("🚀 BOT XAUUSD BẮT ĐẦU CHẠY")
        
        while True:
            try:
                # Lấy thông tin tài khoản
                account_info = self.get_account_info()
                if account_info:
                    logging.info(f"💵 Equity: {account_info['equity']:.2f} | Balance: {account_info['balance']:.2f}")
                
                # Lấy dữ liệu giá
                df = self.get_price_data(100)
                if df is None:
                    logging.error("Không lấy được dữ liệu giá")
                    time.sleep(30)
                    continue
                
                # Phân tích kỹ thuật
                signal = self.technical_analyzer.analyze(df)
                
                if signal and signal['action'] != 'HOLD':
                    logging.info(f"📈 Tín hiệu {signal['action']} - Strength: {signal['strength']}")
                    
                    # Thực hiện giao dịch
                    result = self.execute_trade(
                        signal['action'], 
                        signal['sl_pips'], 
                        signal['tp_pips']
                    )
                    
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        logging.info(f"✅ Lệnh {signal['action']} thành công - Ticket: {result.order}")
                        self.risk_manager.record_trade(success=True)
                    else:
                        error_msg = mt5.last_error() if result is None else result.comment
                        logging.error(f"❌ Lỗi lệnh: {error_msg}")
                        self.risk_manager.record_trade(success=False)
                
                # Chờ trước khi kiểm tra tiếp
                time.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logging.error(f"Lỗi trong vòng lặp chính: {e}")
                time.sleep(60)
                
    def stop(self):
        """Dừng bot"""
        mt5.shutdown()
        logging.info("🛑 Bot đã dừng")

def main():
    bot = XAUUSD_Bot()
    
    if not bot.setup_mt5():
        return
        
    try:
        bot.run_bot()
    except KeyboardInterrupt:
        logging.info("👋 Bot được dừng bởi người dùng")
    finally:
        bot.stop()

if __name__ == "__main__":
    main()