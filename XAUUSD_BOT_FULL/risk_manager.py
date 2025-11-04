import pandas as pd
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import logging
from config_xauusd import *

class XAUUSD_RiskManager:
    def __init__(self):
        self.consecutive_losses = 0
        self.daily_stats = {
            'trades_count': 0,
            'total_loss': 0,
            'last_trade_time': None,
            'daily_start_balance': 0
        }
        self.trade_history = []
        self.load_daily_stats()
        
    def load_daily_stats(self):
        """Tải thống kê hàng ngày"""
        try:
            account_info = mt5.account_info()
            if account_info:
                self.daily_stats['daily_start_balance'] = account_info.balance
        except:
            pass
            
    def can_open_trade(self, trade_type):
        """Kiểm tra có thể mở lệnh không"""
        checks = [
            self.check_account_conditions(),
            self.check_daily_limits(),
            self.check_consecutive_losses(),
            self.check_trading_time(),
            self.check_positions_count(),
            self.check_drawdown()
        ]
        
        for check, message in checks:
            if not check:
                logging.warning(f"❌ Không thể mở lệnh: {message}")
                return False
                
        return True
        
    def check_account_conditions(self):
        """Kiểm tra điều kiện tài khoản"""
        account_info = mt5.account_info()
        if not account_info:
            return False, "Không lấy được thông tin tài khoản"
            
        equity = account_info.equity
        balance = account_info.balance
        
        # Kiểm tra equity an toàn
        safe_equity = balance * SAFE_EQUITY_RATIO
        if equity < safe_equity:
            return False, f"Equity {equity:.2f} < Safe {safe_equity:.2f}"
            
        # Kiểm tra margin
        if account_info.margin_free < 100:
            return False, "Free margin quá thấp"
            
        return True, "OK"
        
    def check_daily_limits(self):
        """Kiểm tra giới hạn hàng ngày"""
        today = datetime.now().date()
        
        # Đếm số lệnh hôm nay
        today_trades = [t for t in self.trade_history 
                       if t['time'].date() == today]
        
        if len(today_trades) >= MAX_DAILY_TRADES:
            return False, f"Đạt max {MAX_DAILY_TRADES} lệnh/ngày"
            
        # Kiểm tra lệnh trong 1 giờ
        hour_ago = datetime.now() - timedelta(hours=1)
        recent_trades = [t for t in self.trade_history 
                        if t['time'] > hour_ago]
        
        if len(recent_trades) >= MAX_HOURLY_TRADES:
            return False, f"Đạt max {MAX_HOURLY_TRADES} lệnh/giờ"
            
        return True, "OK"
        
    def check_consecutive_losses(self):
        """Kiểm tra số lệnh thua liên tiếp"""
        if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            return False, f"Thua {self.consecutive_losses} lệnh liên tiếp"
        return True, "OK"
        
    def check_trading_time(self):
        """Kiểm tra thời gian giao dịch"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # Kiểm tra session cấm
        for start, end in NO_TRADE_SESSIONS:
            if start <= current_time <= end:
                return False, f"Trong session cấm {start}-{end}"
        
        # Kiểm tra thứ 6
        if now.weekday() == 4 and current_time >= NO_TRADE_FRIDAY_AFTER:
            return False, "Cuối tuần (sau 20:00 thứ 6)"
            
        # Kiểm tra nghỉ sau thua
        if self.consecutive_losses > 0 and self.daily_stats['last_trade_time']:
            time_since_last = now - self.daily_stats['last_trade_time']
            if time_since_last < timedelta(minutes=BREAK_AFTER_LOSS_MINUTES):
                return False, f"Đang nghỉ sau thua ({BREAK_AFTER_LOSS_MINUTES} phút)"
                
        return True, "OK"
        
    def check_positions_count(self):
        """Kiểm tra số lượng vị thế đang mở"""
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions is None:
            positions = []
            
        if len(positions) >= MAX_POSITIONS:
            return False, f"Đã có {len(positions)} vị thế"
            
        return True, "OK"
        
    def check_drawdown(self):
        """Kiểm tra drawdown"""
        account_info = mt5.account_info()
        if not account_info:
            return True, "OK"  # Bỏ qua nếu không lấy được info
            
        balance = account_info.balance
        equity = account_info.equity
        
        if balance > 0:
            drawdown_percent = (balance - equity) / balance * 100
            if drawdown_percent > MAX_DRAWDOWN_PERCENT:
                return False, f"Drawdown {drawdown_percent:.1f}% vượt quá {MAX_DRAWDOWN_PERCENT}%"
                
        return True, "OK"
        
    def record_trade(self, success=True, profit=0):
        """Ghi nhận kết quả giao dịch"""
        trade_record = {
            'time': datetime.now(),
            'success': success,
            'profit': profit
        }
        
        self.trade_history.append(trade_record)
        self.daily_stats['last_trade_time'] = datetime.now()
        self.daily_stats['trades_count'] += 1
        
        if not success or profit < 0:
            self.consecutive_losses += 1
            self.daily_stats['total_loss'] += abs(profit)
        else:
            self.consecutive_losses = 0
            
        logging.info(f"📝 Ghi nhận trade: {'Thắng' if success else 'Thua'} - Consecutive losses: {self.consecutive_losses}")