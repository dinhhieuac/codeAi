"""
time_check.py - Kiểm tra các quy tắc giao dịch mới trên MT5

Các quy tắc:
1. Tổng lỗ trong ngày vượt quá -10% tài khoản → Dừng giao dịch HẾT NGÀY (cho phép bật tắt)
2. Thắng 3 lệnh liên tiếp HOẶC đạt mục tiêu +10% lợi nhuận → Dừng giao dịch HẾT NGÀY hoặc giảm khối lượng 50% (cho phép bật tắt)
3. Vừa chốt lệnh xong, muốn vào lệnh mới ngay → Phải chờ tối thiểu 10 phút
4. Thua 2 lệnh liên tiếp → Nghỉ 45 phút
5. Chốt lệnh ≥ 3R → Nghỉ 45 phút
6. Trade ngoài 14h–23h VN → Cấm (cho phép bật tắt)
7. Tin đỏ (NFP, FOMC) → Không trade 1h trước + 2h sau (cho phép bật tắt)
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import pytz
import logging

# ========================== CẤU HÌNH ==========================
# Các quy tắc có thể bật/tắt
ENABLE_DAILY_LOSS_LIMIT = True  # Quy tắc 1: Dừng khi lỗ -10% trong ngày
ENABLE_WIN_STREAK_LIMIT = True  # Quy tắc 2: Dừng khi thắng 3 lệnh liên tiếp hoặc +10%
ENABLE_MIN_TIME_AFTER_CLOSE = True  # Quy tắc 3: Chờ 10 phút sau khi chốt lệnh
ENABLE_TWO_LOSSES_COOLDOWN = True  # Quy tắc 4: Nghỉ 45 phút sau 2 lệnh thua
ENABLE_BIG_WIN_COOLDOWN = True  # Quy tắc 5: Nghỉ 45 phút sau lệnh ≥ 3R
ENABLE_TRADING_HOURS_LIMIT = True  # Quy tắc 6: Chỉ trade 14h-23h VN
ENABLE_NEWS_FILTER = True  # Quy tắc 7: Tránh tin đỏ (NFP, FOMC)

# Tham số
DAILY_LOSS_LIMIT_PERCENT = -10.0  # -10% tài khoản
WIN_STREAK_LIMIT = 3  # 3 lệnh thắng liên tiếp
PROFIT_TARGET_PERCENT = 10.0  # +10% lợi nhuận
MIN_TIME_AFTER_CLOSE_MINUTES = 10  # 10 phút sau khi chốt lệnh
TWO_LOSSES_COOLDOWN_MINUTES = 45  # 45 phút sau 2 lệnh thua
BIG_WIN_COOLDOWN_MINUTES = 45  # 45 phút sau lệnh ≥ 3R
BIG_WIN_R_MULTIPLIER = 3.0  # ≥ 3R
TRADING_HOURS_START = 14  # 14h VN
TRADING_HOURS_END = 23  # 23h VN
NEWS_BLOCK_BEFORE_HOURS = 1  # 1h trước tin đỏ
NEWS_BLOCK_AFTER_HOURS = 2  # 2h sau tin đỏ

# Timezone
VN_TIMEZONE = pytz.timezone('Asia/Ho_Chi_Minh')

# Magic number để lọc lệnh (có thể thay đổi)
BOT_MAGIC = None  # None = lấy tất cả lệnh

# ========================== HÀM KIỂM TRA ==========================

def get_account_info():
    """Lấy thông tin tài khoản"""
    account_info = mt5.account_info()
    if account_info:
        return {
            'balance': account_info.balance,
            'equity': account_info.equity,
            'profit': account_info.profit,
            'login': account_info.login
        }
    return None

def get_daily_profit_loss(account_login=None):
    """
    Tính tổng lợi nhuận/lỗ trong ngày (từ 0h VN hôm nay đến bây giờ)
    
    Returns:
        dict: {
            'profit': float,  # Tổng profit/loss trong ngày
            'profit_percent': float,  # % profit/loss so với balance đầu ngày
            'balance_start': float,  # Balance đầu ngày
            'balance_current': float  # Balance hiện tại
        }
    """
    if not mt5.initialize():
        return None
    
    account_info = get_account_info()
    if not account_info:
        return None
    
    # Lấy thời gian đầu ngày (0h VN hôm nay)
    now_vn = datetime.now(VN_TIMEZONE)
    start_of_day = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day.astimezone(pytz.UTC)
    start_timestamp = int(start_of_day_utc.timestamp())
    
    # Lấy tất cả deals từ đầu ngày đến bây giờ
    deals = mt5.history_deals_get(start_timestamp, datetime.now().timestamp())
    
    if deals is None:
        deals = []
    
    # Lọc theo account login nếu có
    if account_login:
        deals = [d for d in deals if d.login == account_login]
    
    # Tính tổng profit trong ngày
    daily_profit = sum(d.profit for d in deals if d.entry == mt5.DEAL_ENTRY_OUT)
    
    # Balance đầu ngày = balance hiện tại - profit trong ngày
    balance_start = account_info['balance'] - daily_profit
    balance_current = account_info['balance']
    
    # Tính % profit/loss
    if balance_start > 0:
        profit_percent = (daily_profit / balance_start) * 100
    else:
        profit_percent = 0.0
    
    return {
        'profit': daily_profit,
        'profit_percent': profit_percent,
        'balance_start': balance_start,
        'balance_current': balance_current
    }

def check_daily_loss_limit():
    """
    Quy tắc 1: Kiểm tra tổng lỗ trong ngày có vượt quá -10% không
    
    Returns:
        dict: {
            'blocked': bool,
            'reason': str,
            'daily_loss_percent': float,
            'daily_loss': float
        }
    """
    if not ENABLE_DAILY_LOSS_LIMIT:
        return {'blocked': False, 'reason': 'Quy tắc tắt'}
    
    daily_info = get_daily_profit_loss()
    if not daily_info:
        return {'blocked': False, 'reason': 'Không lấy được thông tin'}
    
    daily_loss_percent = daily_info['profit_percent']
    daily_loss = daily_info['profit']
    
    if daily_loss_percent <= DAILY_LOSS_LIMIT_PERCENT:
        return {
            'blocked': True,
            'reason': f'Tổng lỗ trong ngày: {daily_loss_percent:.2f}% (${daily_loss:.2f}) ≤ {DAILY_LOSS_LIMIT_PERCENT}%',
            'daily_loss_percent': daily_loss_percent,
            'daily_loss': daily_loss
        }
    
    return {
        'blocked': False,
        'reason': f'Tổng lỗ trong ngày: {daily_loss_percent:.2f}% (${daily_loss:.2f})',
        'daily_loss_percent': daily_loss_percent,
        'daily_loss': daily_loss
    }

def get_last_closed_trades(count=10, magic=None):
    """
    Lấy các lệnh đã đóng gần nhất
    
    Args:
        count: Số lệnh cần lấy
        magic: Magic number để lọc (None = tất cả)
    
    Returns:
        list: Danh sách các deal đã đóng
    """
    # Lấy deals từ 30 ngày gần nhất
    from_timestamp = int((datetime.now() - timedelta(days=30)).timestamp())
    deals = mt5.history_deals_get(from_timestamp, datetime.now().timestamp())
    
    if deals is None:
        return []
    
    # Lọc chỉ lấy deals đóng lệnh (DEAL_ENTRY_OUT)
    closed_deals = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
    
    # Lọc theo magic nếu có
    if magic is not None:
        closed_deals = [d for d in closed_deals if d.magic == magic]
    
    # Sắp xếp theo thời gian (mới nhất trước)
    closed_deals.sort(key=lambda x: x.time, reverse=True)
    
    return closed_deals[:count]

def check_win_streak_and_profit_target():
    """
    Quy tắc 2: Kiểm tra thắng 3 lệnh liên tiếp HOẶC đạt mục tiêu +10% lợi nhuận
    
    Returns:
        dict: {
            'blocked': bool,
            'reason': str,
            'win_streak': int,
            'daily_profit_percent': float,
            'reduce_lot_size': bool  # True nếu chỉ giảm lot size 50%, False nếu dừng hẳn
        }
    """
    if not ENABLE_WIN_STREAK_LIMIT:
        return {'blocked': False, 'reason': 'Quy tắc tắt'}
    
    # Kiểm tra profit target
    daily_info = get_daily_profit_loss()
    if daily_info and daily_info['profit_percent'] >= PROFIT_TARGET_PERCENT:
        return {
            'blocked': True,
            'reason': f'Đạt mục tiêu lợi nhuận: {daily_info["profit_percent"]:.2f}% ≥ {PROFIT_TARGET_PERCENT}%',
            'win_streak': 0,
            'daily_profit_percent': daily_info['profit_percent'],
            'reduce_lot_size': False  # Dừng hẳn khi đạt mục tiêu
        }
    
    # Kiểm tra win streak
    closed_trades = get_last_closed_trades(count=WIN_STREAK_LIMIT, magic=BOT_MAGIC)
    
    if len(closed_trades) < WIN_STREAK_LIMIT:
        return {
            'blocked': False,
            'reason': f'Chưa đủ {WIN_STREAK_LIMIT} lệnh để kiểm tra',
            'win_streak': len(closed_trades),
            'daily_profit_percent': daily_info['profit_percent'] if daily_info else 0.0,
            'reduce_lot_size': False
        }
    
    # Kiểm tra xem có thắng liên tiếp không
    win_streak = 0
    for deal in closed_trades[:WIN_STREAK_LIMIT]:
        if deal.profit > 0:
            win_streak += 1
        else:
            break  # Nếu có lệnh thua thì break
    
    if win_streak >= WIN_STREAK_LIMIT:
        return {
            'blocked': True,
            'reason': f'Thắng {win_streak} lệnh liên tiếp ≥ {WIN_STREAK_LIMIT}',
            'win_streak': win_streak,
            'daily_profit_percent': daily_info['profit_percent'] if daily_info else 0.0,
            'reduce_lot_size': True  # Có thể chỉ giảm lot size 50%
        }
    
    return {
        'blocked': False,
        'reason': f'Win streak: {win_streak}/{WIN_STREAK_LIMIT}',
        'win_streak': win_streak,
        'daily_profit_percent': daily_info['profit_percent'] if daily_info else 0.0,
        'reduce_lot_size': False
    }

def check_min_time_after_close():
    """
    Quy tắc 3: Kiểm tra đã đủ 10 phút sau khi chốt lệnh cuối cùng chưa
    
    Returns:
        dict: {
            'blocked': bool,
            'reason': str,
            'time_elapsed_minutes': float,
            'remaining_minutes': float
        }
    """
    if not ENABLE_MIN_TIME_AFTER_CLOSE:
        return {'blocked': False, 'reason': 'Quy tắc tắt'}
    
    closed_trades = get_last_closed_trades(count=1, magic=BOT_MAGIC)
    
    if not closed_trades:
        return {
            'blocked': False,
            'reason': 'Chưa có lệnh nào đóng',
            'time_elapsed_minutes': 0,
            'remaining_minutes': 0
        }
    
    last_close_time = datetime.fromtimestamp(closed_trades[0].time)
    now = datetime.now()
    time_elapsed = (now - last_close_time).total_seconds() / 60  # phút
    
    if time_elapsed < MIN_TIME_AFTER_CLOSE_MINUTES:
        remaining = MIN_TIME_AFTER_CLOSE_MINUTES - time_elapsed
        return {
            'blocked': True,
            'reason': f'Chưa đủ {MIN_TIME_AFTER_CLOSE_MINUTES} phút sau khi chốt lệnh (còn {remaining:.1f} phút)',
            'time_elapsed_minutes': time_elapsed,
            'remaining_minutes': remaining
        }
    
    return {
        'blocked': False,
        'reason': f'Đã đủ {MIN_TIME_AFTER_CLOSE_MINUTES} phút sau khi chốt lệnh',
        'time_elapsed_minutes': time_elapsed,
        'remaining_minutes': 0
    }

def check_two_losses_cooldown():
    """
    Quy tắc 4: Kiểm tra có thua 2 lệnh liên tiếp không → Nghỉ 45 phút
    
    Returns:
        dict: {
            'blocked': bool,
            'reason': str,
            'last_loss_time': datetime,
            'remaining_minutes': float
        }
    """
    if not ENABLE_TWO_LOSSES_COOLDOWN:
        return {'blocked': False, 'reason': 'Quy tắc tắt'}
    
    closed_trades = get_last_closed_trades(count=2, magic=BOT_MAGIC)
    
    if len(closed_trades) < 2:
        return {
            'blocked': False,
            'reason': 'Chưa đủ 2 lệnh để kiểm tra',
            'last_loss_time': None,
            'remaining_minutes': 0
        }
    
    # Kiểm tra 2 lệnh cuối cùng có thua không
    last_two = closed_trades[:2]
    both_loss = all(d.profit < 0 for d in last_two)
    
    if not both_loss:
        return {
            'blocked': False,
            'reason': 'Không có 2 lệnh thua liên tiếp',
            'last_loss_time': None,
            'remaining_minutes': 0
        }
    
    # Có 2 lệnh thua liên tiếp → Kiểm tra thời gian
    last_loss_time = datetime.fromtimestamp(last_two[0].time)
    now = datetime.now()
    time_elapsed = (now - last_loss_time).total_seconds() / 60  # phút
    
    if time_elapsed < TWO_LOSSES_COOLDOWN_MINUTES:
        remaining = TWO_LOSSES_COOLDOWN_MINUTES - time_elapsed
        return {
            'blocked': True,
            'reason': f'Thua 2 lệnh liên tiếp → Nghỉ {TWO_LOSSES_COOLDOWN_MINUTES} phút (còn {remaining:.1f} phút)',
            'last_loss_time': last_loss_time,
            'remaining_minutes': remaining
        }
    
    return {
        'blocked': False,
        'reason': f'Đã hết thời gian nghỉ sau 2 lệnh thua ({time_elapsed:.1f} phút)',
        'last_loss_time': last_loss_time,
        'remaining_minutes': 0
    }

def calculate_r_multiple(deal, initial_balance=None):
    """
    Tính R-multiple của một lệnh
    
    R = Risk (số tiền rủi ro ban đầu)
    R-multiple = Profit / R
    
    Args:
        deal: MT5 deal object
        initial_balance: Balance ban đầu (để tính R, nếu None thì dùng balance hiện tại)
    
    Returns:
        float: R-multiple
    """
    if initial_balance is None:
        account_info = get_account_info()
        if account_info:
            initial_balance = account_info['balance'] - deal.profit  # Balance trước khi đóng lệnh
    
    # Tính R (risk) từ SL và lot size
    # Giả sử R = 1% balance (có thể điều chỉnh)
    if initial_balance:
        risk_percent = 0.01  # 1%
        r = initial_balance * risk_percent
    else:
        r = abs(deal.profit) / 3.0  # Ước tính R = profit/3 (giả sử 3R)
    
    if r == 0:
        return 0.0
    
    r_multiple = deal.profit / r
    return r_multiple

def check_big_win_cooldown():
    """
    Quy tắc 5: Kiểm tra có chốt lệnh ≥ 3R không → Nghỉ 45 phút
    
    Returns:
        dict: {
            'blocked': bool,
            'reason': str,
            'last_big_win_time': datetime,
            'r_multiple': float,
            'remaining_minutes': float
        }
    """
    if not ENABLE_BIG_WIN_COOLDOWN:
        return {'blocked': False, 'reason': 'Quy tắc tắt'}
    
    closed_trades = get_last_closed_trades(count=1, magic=BOT_MAGIC)
    
    if not closed_trades:
        return {
            'blocked': False,
            'reason': 'Chưa có lệnh nào đóng',
            'last_big_win_time': None,
            'r_multiple': 0.0,
            'remaining_minutes': 0
        }
    
    last_trade = closed_trades[0]
    
    # Chỉ kiểm tra lệnh thắng
    if last_trade.profit <= 0:
        return {
            'blocked': False,
            'reason': 'Lệnh cuối không phải lệnh thắng',
            'last_big_win_time': None,
            'r_multiple': 0.0,
            'remaining_minutes': 0
        }
    
    # Tính R-multiple
    r_multiple = calculate_r_multiple(last_trade)
    
    if r_multiple < BIG_WIN_R_MULTIPLIER:
        return {
            'blocked': False,
            'reason': f'Lệnh cuối: {r_multiple:.2f}R < {BIG_WIN_R_MULTIPLIER}R',
            'last_big_win_time': None,
            'r_multiple': r_multiple,
            'remaining_minutes': 0
        }
    
    # Có lệnh ≥ 3R → Kiểm tra thời gian
    last_big_win_time = datetime.fromtimestamp(last_trade.time)
    now = datetime.now()
    time_elapsed = (now - last_big_win_time).total_seconds() / 60  # phút
    
    if time_elapsed < BIG_WIN_COOLDOWN_MINUTES:
        remaining = BIG_WIN_COOLDOWN_MINUTES - time_elapsed
        return {
            'blocked': True,
            'reason': f'Chốt lệnh {r_multiple:.2f}R ≥ {BIG_WIN_R_MULTIPLIER}R → Nghỉ {BIG_WIN_COOLDOWN_MINUTES} phút (còn {remaining:.1f} phút)',
            'last_big_win_time': last_big_win_time,
            'r_multiple': r_multiple,
            'remaining_minutes': remaining
        }
    
    return {
        'blocked': False,
        'reason': f'Đã hết thời gian nghỉ sau lệnh {r_multiple:.2f}R ({time_elapsed:.1f} phút)',
        'last_big_win_time': last_big_win_time,
        'r_multiple': r_multiple,
        'remaining_minutes': 0
    }

def check_trading_hours():
    """
    Quy tắc 6: Kiểm tra có trong giờ giao dịch (14h-23h VN) không
    
    Returns:
        dict: {
            'blocked': bool,
            'reason': str,
            'current_hour': int,
            'vn_time': datetime
        }
    """
    if not ENABLE_TRADING_HOURS_LIMIT:
        return {'blocked': False, 'reason': 'Quy tắc tắt'}
    
    now_vn = datetime.now(VN_TIMEZONE)
    current_hour = now_vn.hour
    
    if TRADING_HOURS_START <= current_hour < TRADING_HOURS_END:
        return {
            'blocked': False,
            'reason': f'Trong giờ giao dịch: {current_hour}h ({TRADING_HOURS_START}h-{TRADING_HOURS_END}h VN)',
            'current_hour': current_hour,
            'vn_time': now_vn
        }
    
    return {
        'blocked': True,
        'reason': f'Ngoài giờ giao dịch: {current_hour}h (chỉ trade {TRADING_HOURS_START}h-{TRADING_HOURS_END}h VN)',
        'current_hour': current_hour,
        'vn_time': now_vn
    }

def get_news_events():
    """
    Lấy danh sách các tin đỏ (NFP, FOMC) trong tháng
    
    Returns:
        list: Danh sách các sự kiện tin đỏ với thời gian
    """
    # TODO: Có thể tích hợp với API lịch kinh tế thực tế
    # Hiện tại trả về danh sách rỗng (cần cập nhật thủ công hoặc dùng API)
    
    # Ví dụ: NFP thường vào thứ 6 đầu tiên của tháng lúc 20:30 VN
    # FOMC thường vào các ngày cụ thể trong tháng
    
    news_events = []
    
    # Có thể thêm logic để tính toán NFP, FOMC tự động
    # Hoặc đọc từ file/config
    
    return news_events

def check_news_filter():
    """
    Quy tắc 7: Kiểm tra có trong thời gian cấm trade do tin đỏ (NFP, FOMC) không
    
    Returns:
        dict: {
            'blocked': bool,
            'reason': str,
            'news_event': str,
            'news_time': datetime
        }
    """
    if not ENABLE_NEWS_FILTER:
        return {'blocked': False, 'reason': 'Quy tắc tắt'}
    
    news_events = get_news_events()
    now_vn = datetime.now(VN_TIMEZONE)
    
    for event in news_events:
        event_time = event.get('time')  # datetime object
        event_name = event.get('name', 'Unknown')
        
        if not event_time:
            continue
        
        # Kiểm tra xem có trong khoảng thời gian cấm không
        block_start = event_time - timedelta(hours=NEWS_BLOCK_BEFORE_HOURS)
        block_end = event_time + timedelta(hours=NEWS_BLOCK_AFTER_HOURS)
        
        if block_start <= now_vn <= block_end:
            return {
                'blocked': True,
                'reason': f'Trong thời gian cấm trade do {event_name} ({block_start.strftime("%H:%M")} - {block_end.strftime("%H:%M")} VN)',
                'news_event': event_name,
                'news_time': event_time
            }
    
    return {
        'blocked': False,
        'reason': 'Không có tin đỏ trong thời gian cấm',
        'news_event': None,
        'news_time': None
    }

def check_all_rules():
    """
    Kiểm tra tất cả các quy tắc
    
    Returns:
        dict: {
            'can_trade': bool,
            'blocked_rules': list,  # Danh sách các quy tắc chặn
            'reduce_lot_size': bool,  # Có cần giảm lot size 50% không
            'details': dict  # Chi tiết từng quy tắc
        }
    """
    results = {
        'can_trade': True,
        'blocked_rules': [],
        'reduce_lot_size': False,
        'details': {}
    }
    
    # Quy tắc 1: Daily loss limit
    rule1 = check_daily_loss_limit()
    results['details']['daily_loss_limit'] = rule1
    if rule1['blocked']:
        results['can_trade'] = False
        results['blocked_rules'].append('Daily Loss Limit')
    
    # Quy tắc 2: Win streak & profit target
    rule2 = check_win_streak_and_profit_target()
    results['details']['win_streak'] = rule2
    if rule2['blocked']:
        results['can_trade'] = False
        results['blocked_rules'].append('Win Streak/Profit Target')
        if rule2.get('reduce_lot_size', False):
            results['reduce_lot_size'] = True
    
    # Quy tắc 3: Min time after close
    rule3 = check_min_time_after_close()
    results['details']['min_time_after_close'] = rule3
    if rule3['blocked']:
        results['can_trade'] = False
        results['blocked_rules'].append('Min Time After Close')
    
    # Quy tắc 4: Two losses cooldown
    rule4 = check_two_losses_cooldown()
    results['details']['two_losses_cooldown'] = rule4
    if rule4['blocked']:
        results['can_trade'] = False
        results['blocked_rules'].append('Two Losses Cooldown')
    
    # Quy tắc 5: Big win cooldown
    rule5 = check_big_win_cooldown()
    results['details']['big_win_cooldown'] = rule5
    if rule5['blocked']:
        results['can_trade'] = False
        results['blocked_rules'].append('Big Win Cooldown')
    
    # Quy tắc 6: Trading hours
    rule6 = check_trading_hours()
    results['details']['trading_hours'] = rule6
    if rule6['blocked']:
        results['can_trade'] = False
        results['blocked_rules'].append('Trading Hours')
    
    # Quy tắc 7: News filter
    rule7 = check_news_filter()
    results['details']['news_filter'] = rule7
    if rule7['blocked']:
        results['can_trade'] = False
        results['blocked_rules'].append('News Filter')
    
    return results

# ========================== HÀM MAIN ĐỂ TEST ==========================

def main():
    """Hàm main để test các quy tắc"""
    print("=" * 60)
    print("🔍 KIỂM TRA CÁC QUY TẮC GIAO DỊCH")
    print("=" * 60)
    
    # Khởi tạo MT5
    if not mt5.initialize():
        print("❌ Không thể khởi tạo MT5")
        return
    
    print("✅ Đã kết nối MT5\n")
    
    # Kiểm tra tất cả quy tắc
    results = check_all_rules()
    
    print("📊 KẾT QUẢ KIỂM TRA:")
    print("-" * 60)
    print(f"✅ Có thể giao dịch: {'CÓ' if results['can_trade'] else 'KHÔNG'}")
    
    if results['blocked_rules']:
        print(f"🚫 Các quy tắc chặn: {', '.join(results['blocked_rules'])}")
    
    if results['reduce_lot_size']:
        print(f"⚠️ Giảm lot size 50%: CÓ")
    
    print("\n📋 CHI TIẾT TỪNG QUY TẮC:")
    print("-" * 60)
    
    for rule_name, rule_result in results['details'].items():
        status = "🚫 CHẶN" if rule_result.get('blocked', False) else "✅ OK"
        reason = rule_result.get('reason', 'N/A')
        print(f"{status} - {rule_name}: {reason}")
    
    print("\n" + "=" * 60)
    
    # Đóng MT5
    mt5.shutdown()

if __name__ == "__main__":
    main()

