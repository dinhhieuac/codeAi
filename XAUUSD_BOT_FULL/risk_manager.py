"""
QUẢN LÝ RỦI RO - Risk Manager
==============================
Module này chứa các phương thức quản lý rủi ro và kiểm soát giao dịch.
Đảm bảo bot không giao dịch quá mức và bảo vệ tài khoản khỏi các rủi ro lớn.
"""

import pandas as pd
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import logging
from config_xauusd import *

class XAUUSD_RiskManager:
    """
    Lớp quản lý rủi ro cho bot giao dịch XAUUSD
    
    Chức năng:
    - Kiểm tra điều kiện tài khoản (equity, margin)
    - Kiểm tra giới hạn giao dịch (số lệnh/ngày, số lệnh/giờ)
    - Kiểm tra số lệnh thua liên tiếp
    - Kiểm tra thời gian giao dịch (tránh các session rủi ro)
    - Kiểm tra số lượng vị thế đang mở
    - Kiểm tra drawdown (mức độ lỗ)
    - Ghi nhận kết quả giao dịch
    """
    
    def __init__(self):
        """
        Khởi tạo Risk Manager
        
        Khởi tạo các biến theo dõi:
        - consecutive_losses: Số lệnh thua liên tiếp
        - daily_stats: Thống kê trong ngày (số lệnh, tổng lỗ, thời gian lệnh cuối, balance đầu ngày)
        - trade_history: Lịch sử các giao dịch
        """
        # Số lệnh thua liên tiếp (reset về 0 khi có 1 lệnh thắng)
        self.consecutive_losses = 0
        
        # Thống kê trong ngày
        self.daily_stats = {
            'trades_count': 0,              # Số lệnh đã mở trong ngày
            'total_loss': 0,                # Tổng số tiền lỗ trong ngày
            'last_trade_time': None,        # Thời gian lệnh cuối cùng
            'daily_start_balance': 0        # Balance đầu ngày (để tính drawdown)
        }
        
        # Lịch sử các giao dịch (list các dict chứa time, success, profit)
        self.trade_history = []
        
        # Tải thống kê ban đầu (lấy balance hiện tại)
        self.load_daily_stats()
        
    def load_daily_stats(self):
        """
        Tải thống kê hàng ngày từ tài khoản MT5
        
        Lấy balance hiện tại từ MT5 để làm balance đầu ngày.
        Được gọi khi khởi tạo và có thể gọi lại khi reset ngày mới.
        """
        try:
            account_info = mt5.account_info()
            if account_info:
                # Lưu balance hiện tại làm balance đầu ngày
                self.daily_stats['daily_start_balance'] = account_info.balance
        except:
            # Nếu không lấy được thông tin, bỏ qua (không ảnh hưởng đến bot)
            pass
            
    def can_open_trade(self, trade_type):
        """
        Kiểm tra tổng hợp xem có thể mở lệnh mới hay không
        
        Thực hiện tất cả các kiểm tra an toàn:
        1. Điều kiện tài khoản (equity, margin)
        2. Giới hạn giao dịch (số lệnh/ngày, số lệnh/giờ)
        3. Số lệnh thua liên tiếp
        4. Thời gian giao dịch (session cấm, thứ 6, nghỉ sau thua)
        5. Số lượng vị thế đang mở
        6. Drawdown (mức độ lỗ)
        
        Args:
            trade_type: Loại lệnh ('BUY' hoặc 'SELL') - hiện tại chưa sử dụng
        
        Returns:
            True nếu có thể mở lệnh, False nếu không
        """
        # Danh sách tất cả các kiểm tra cần thực hiện
        # Mỗi check trả về (True/False, message)
        checks = [
            self.check_account_conditions(),    # Kiểm tra equity, margin
            self.check_daily_limits(),          # Kiểm tra số lệnh/ngày, số lệnh/giờ
            self.check_consecutive_losses(),    # Kiểm tra số lệnh thua liên tiếp
            self.check_trading_time(),          # Kiểm tra thời gian giao dịch
            self.check_positions_count(),       # Kiểm tra số vị thế đang mở
            self.check_drawdown()               # Kiểm tra drawdown
        ]
        
        # Duyệt qua từng kiểm tra
        for check, message in checks:
            if not check:  # Nếu một trong các kiểm tra fail
                logging.warning(f"❌ Không thể mở lệnh: {message}")
                return False  # Không cho phép mở lệnh
                
        # Tất cả kiểm tra đều pass → Cho phép mở lệnh
        return True
        
    def check_account_conditions(self):
        """
        Kiểm tra điều kiện tài khoản
        
        Kiểm tra:
        - Equity có đủ an toàn không (so với balance)
        - Free margin có đủ để mở lệnh mới không
        
        Returns:
            Tuple (bool, str): (True/False, message)
        """
        account_info = mt5.account_info()
        if not account_info:
            return False, "Không lấy được thông tin tài khoản"
            
        equity = account_info.equity      # Equity = Balance + Floating P/L
        balance = account_info.balance    # Balance = Số dư tài khoản
        
        # Kiểm tra equity an toàn
        # Equity phải >= Balance * SAFE_EQUITY_RATIO (ví dụ: 92% balance)
        # Nếu equity < safe_equity → Có quá nhiều lệnh đang thua → Không mở lệnh mới
        safe_equity = balance * SAFE_EQUITY_RATIO
        if equity < safe_equity:
            return False, f"Equity {equity:.2f} < Safe {safe_equity:.2f}"
            
        # Kiểm tra free margin (margin còn lại)
        # Free margin phải >= $100 để đảm bảo có đủ để mở lệnh và chịu được biến động
        if account_info.margin_free < 100:
            return False, "Free margin quá thấp"
            
        return True, "OK"
        
    def check_daily_limits(self):
        """
        Kiểm tra giới hạn số lệnh trong ngày và trong giờ
        
        Kiểm tra:
        - Số lệnh đã mở trong ngày hôm nay có vượt MAX_DAILY_TRADES không
        - Số lệnh đã mở trong 1 giờ gần đây có vượt MAX_HOURLY_TRADES không
        
        Returns:
            Tuple (bool, str): (True/False, message)
        """
        today = datetime.now().date()
        
        # Đếm số lệnh đã mở trong ngày hôm nay
        today_trades = [t for t in self.trade_history 
                       if t['time'].date() == today]
        
        # Nếu đạt số lệnh tối đa trong ngày → Không cho mở thêm
        if len(today_trades) >= MAX_DAILY_TRADES:
            return False, f"Đạt max {MAX_DAILY_TRADES} lệnh/ngày"
            
        # Kiểm tra số lệnh trong 1 giờ gần đây
        hour_ago = datetime.now() - timedelta(hours=1)
        recent_trades = [t for t in self.trade_history 
                        if t['time'] > hour_ago]
        
        # Nếu đạt số lệnh tối đa trong 1 giờ → Không cho mở thêm
        if len(recent_trades) >= MAX_HOURLY_TRADES:
            return False, f"Đạt max {MAX_HOURLY_TRADES} lệnh/giờ"
            
        return True, "OK"
        
    def check_consecutive_losses(self):
        """
        Kiểm tra số lệnh thua liên tiếp
        
        Nếu thua quá nhiều lệnh liên tiếp → Bot tự động dừng để tránh rủi ro lớn.
        Đây là một cơ chế bảo vệ quan trọng để tránh "revenge trading" (giao dịch trả thù).
        
        Returns:
            Tuple (bool, str): (True/False, message)
        """
        # Nếu số lệnh thua liên tiếp >= MAX_CONSECUTIVE_LOSSES → Không cho mở lệnh mới
        if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            return False, f"Thua {self.consecutive_losses} lệnh liên tiếp"
        
        return True, "OK"
        
    def check_trading_time(self):
        """
        Kiểm tra thời gian giao dịch
        
        Kiểm tra:
        - Có đang trong các session cấm giao dịch không (NO_TRADE_SESSIONS)
        - Có phải thứ 6 sau giờ cấm không (NO_TRADE_FRIDAY_AFTER)
        - Có đang trong thời gian nghỉ sau khi thua lệnh không (BREAK_AFTER_LOSS_MINUTES)
        
        Returns:
            Tuple (bool, str): (True/False, message)
        """
        now = datetime.now()
        current_time = now.strftime("%H:%M")  # Format: "HH:MM"
        
        # Kiểm tra các session cấm giao dịch (từ config)
        # Ví dụ: ("20:00", "22:00") → Không giao dịch từ 20:00 đến 22:00
        for start, end in NO_TRADE_SESSIONS:
            if start <= current_time <= end:
                return False, f"Trong session cấm {start}-{end}"
        
        # Kiểm tra thứ 6 (weekday() = 4)
        # Sau giờ NO_TRADE_FRIDAY_AFTER (ví dụ: 20:00) → Không giao dịch (tránh rủi ro cuối tuần)
        if now.weekday() == 4 and current_time >= NO_TRADE_FRIDAY_AFTER:
            return False, "Cuối tuần (sau 20:00 thứ 6)"
            
        # Kiểm tra thời gian nghỉ sau khi thua lệnh
        # Nếu vừa thua lệnh → Đợi BREAK_AFTER_LOSS_MINUTES phút trước khi tìm tín hiệu mới
        if self.consecutive_losses > 0 and self.daily_stats['last_trade_time']:
            time_since_last = now - self.daily_stats['last_trade_time']
            if time_since_last < timedelta(minutes=BREAK_AFTER_LOSS_MINUTES):
                return False, f"Đang nghỉ sau thua ({BREAK_AFTER_LOSS_MINUTES} phút)"
                
        return True, "OK"
        
    def check_positions_count(self):
        """
        Kiểm tra số lượng vị thế đang mở
        
        Nếu đã có MAX_POSITIONS vị thế mở → Không cho mở thêm để tránh over-exposure.
        
        Returns:
            Tuple (bool, str): (True/False, message)
        """
        # Lấy danh sách tất cả vị thế đang mở cho symbol XAUUSD
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions is None:
            positions = []  # Nếu lỗi → Coi như không có vị thế nào
            
        # Nếu đã có MAX_POSITIONS vị thế → Không cho mở thêm
        if len(positions) >= MAX_POSITIONS:
            return False, f"Đã có {len(positions)} vị thế"
            
        return True, "OK"
        
    def check_drawdown(self):
        """
        Kiểm tra drawdown (mức độ lỗ) của tài khoản
        
        Drawdown = (Balance - Equity) / Balance * 100
        - Balance: Số dư tài khoản (không bao gồm floating P/L)
        - Equity: Số dư + Floating P/L (bao gồm cả lệnh đang mở)
        
        Nếu drawdown > MAX_DRAWDOWN_PERCENT → Không cho mở lệnh mới (bảo vệ tài khoản).
        
        Returns:
            Tuple (bool, str): (True/False, message)
        """
        account_info = mt5.account_info()
        if not account_info:
            return True, "OK"  # Nếu không lấy được info → Bỏ qua (không chặn)
            
        balance = account_info.balance  # Số dư tài khoản
        equity = account_info.equity   # Equity = Balance + Floating P/L
        
        if balance > 0:
            # Tính drawdown phần trăm
            drawdown_percent = (balance - equity) / balance * 100
            
            # Nếu drawdown vượt quá giới hạn → Không cho mở lệnh mới
            if drawdown_percent > MAX_DRAWDOWN_PERCENT:
                return False, f"Drawdown {drawdown_percent:.1f}% vượt quá {MAX_DRAWDOWN_PERCENT}%"
                
        return True, "OK"
        
    def record_trade(self, success=True, profit=0):
        """
        Ghi nhận kết quả giao dịch
        
        Cập nhật:
        - trade_history: Thêm giao dịch mới vào lịch sử
        - daily_stats: Cập nhật số lệnh, tổng lỗ, thời gian lệnh cuối
        - consecutive_losses: Tăng nếu thua, reset về 0 nếu thắng
        
        Args:
            success: True nếu lệnh thắng, False nếu thua
            profit: Số tiền lời/lỗ (dương nếu lời, âm nếu lỗ)
        """
        # Tạo record cho giao dịch này
        trade_record = {
            'time': datetime.now(),      # Thời gian giao dịch
            'success': success,          # Thắng hay thua
            'profit': profit             # Số tiền lời/lỗ
        }
        
        # Thêm vào lịch sử giao dịch
        self.trade_history.append(trade_record)
        
        # Cập nhật thống kê trong ngày
        self.daily_stats['last_trade_time'] = datetime.now()  # Thời gian lệnh cuối
        self.daily_stats['trades_count'] += 1                 # Tăng số lệnh đã mở
        
        # Xử lý kết quả thắng/thua
        if not success or profit < 0:
            # Nếu thua → Tăng số lệnh thua liên tiếp và cộng vào tổng lỗ
            self.consecutive_losses += 1
            self.daily_stats['total_loss'] += abs(profit)
        else:
            # Nếu thắng → Reset số lệnh thua liên tiếp về 0
            self.consecutive_losses = 0
            
        # Log kết quả
        logging.info(f"📝 Ghi nhận trade: {'Thắng' if success else 'Thua'} - Consecutive losses: {self.consecutive_losses}")