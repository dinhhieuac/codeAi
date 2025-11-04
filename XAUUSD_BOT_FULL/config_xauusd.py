# CẤU HÌNH BOT XAUUSD

# Symbol và Timeframe
SYMBOL = "XAUUSD"
TIMEFRAME = "M30"  # M30, H1, H4
TIMEFRAME_MT5 = {
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240
}

# Quản lý rủi ro
RISK_PER_TRADE = 0.5  # 0.5% mỗi lệnh
SAFE_EQUITY_RATIO = 0.92  # 92% balance
MAX_POSITIONS = 2
MAX_DAILY_TRADES = 30
MAX_HOURLY_TRADES = 1

# Stop Loss & Take Profit
MIN_SL_PIPS = 150
MIN_TP_PIPS = 200
MIN_RR_RATIO = 1.5  # Risk/Reward

# Bảo vệ
MAX_CONSECUTIVE_LOSSES = 3
MAX_DRAWDOWN_PERCENT = 8
MAX_DAILY_LOSS_PERCENT = 4
MAX_LOSS_PER_TRADE = 2.0  # %

# Thời gian giao dịch (GMT)
NO_TRADE_SESSIONS = [
    ("20:00", "22:00"),  # NY Open
    ("14:30", "15:30"),  # US News
    ("00:00", "01:00")   # Asian session
]
NO_TRADE_FRIDAY_AFTER = "20:00"
BREAK_AFTER_LOSS_MINUTES = 60

# Điều kiện thị trường
MAX_SPREAD = 50  # pips
NEWS_BUFFER_MINUTES = 30

# Cài đặt bot
CHECK_INTERVAL = 30  # seconds
LOG_TRADES = True

# Tài khoản MT5
ACCOUNT_NUMBER = 272736909
SERVER = "Exness-MT5Trial7"
PASSWORD = ""  # Để trống, MT5 sẽ sử dụng saved password