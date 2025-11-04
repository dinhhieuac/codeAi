"""
CẤU HÌNH BOT XAUUSD
===================
File này chứa tất cả các tham số cấu hình cho bot giao dịch vàng tự động.
Tất cả các giá trị có thể được điều chỉnh tùy theo chiến lược và điều kiện thị trường.
"""

# ============================================================================
# SYMBOL VÀ TIMEFRAME - Cấu hình cặp tiền tệ và khung thời gian
# ============================================================================

# Symbol để giao dịch (XAUUSD = Vàng/USD)
SYMBOL = "XAUUSD"

# Khung thời gian để phân tích (M15 = 15 phút, M30 = 30 phút, H1 = 1 giờ, H4 = 4 giờ)
# Khuyến nghị: M15 cho scalping, H1/H4 cho swing trading
TIMEFRAME = "M15"  # Các giá trị có thể: "M15", "M30", "H1", "H4"

# Dictionary chuyển đổi tên timeframe sang mã MT5 (số phút)
TIMEFRAME_MT5 = {
    "M15": 15,   # 15 phút
    "M30": 30,   # 30 phút
    "H1": 60,    # 1 giờ (60 phút)
    "H4": 240    # 4 giờ (240 phút)
}

# ============================================================================
# QUẢN LÝ RỦI RO - Kiểm soát rủi ro và giới hạn giao dịch
# ============================================================================

# Phần trăm rủi ro cho mỗi lệnh (0.5 = 0.5% của balance)
# Ví dụ: Balance $1000, RISK_PER_TRADE = 0.5 → Risk $5 mỗi lệnh
RISK_PER_TRADE = 0.5  # Đơn vị: phần trăm (%)

# Tỷ lệ equity an toàn tối thiểu so với balance (0.92 = 92%)
# Nếu equity < balance * SAFE_EQUITY_RATIO → Bot sẽ không mở lệnh mới
# Mục đích: Bảo vệ tài khoản khi có quá nhiều lệnh đang thua
SAFE_EQUITY_RATIO = 0.92  # Giá trị từ 0.0 đến 1.0

# Số lượng vị thế tối đa có thể mở cùng lúc
# Nếu đã có MAX_POSITIONS lệnh mở → Bot sẽ không mở lệnh mới
MAX_POSITIONS = 2

# Số lượng lệnh tối đa có thể mở trong 1 ngày
# Mục đích: Tránh over-trading
MAX_DAILY_TRADES = 30

# Số lượng lệnh tối đa có thể mở trong 1 giờ
# Mục đích: Tránh mở quá nhiều lệnh trong thời gian ngắn
# Tăng từ 1 lên 2 để tăng cơ hội giao dịch
MAX_HOURLY_TRADES = 2

# ============================================================================
# STOP LOSS & TAKE PROFIT - Cấu hình SL/TP
# ============================================================================

# Stop Loss tối thiểu (đơn vị: pips)
# SL sẽ không nhỏ hơn giá trị này để đảm bảo có đủ không gian cho biến động giá
MIN_SL_PIPS = 150

# Take Profit tối thiểu (đơn vị: pips)
# TP sẽ không nhỏ hơn giá trị này
MIN_TP_PIPS = 200

# Tỷ lệ Risk/Reward tối thiểu (Risk:Reward)
# Ví dụ: MIN_RR_RATIO = 1.5 → Nếu risk $10, reward tối thiểu $15
# Giá trị cao hơn = an toàn hơn nhưng khó đạt TP
MIN_RR_RATIO = 1.5  # Khuyến nghị: 1.5 - 2.0

# ============================================================================
# BẢO VỆ - Các quy tắc bảo vệ tài khoản
# ============================================================================

# Số lệnh thua liên tiếp tối đa trước khi bot tự động dừng
# Nếu thua MAX_CONSECUTIVE_LOSSES lệnh liên tiếp → Bot sẽ tạm dừng giao dịch
MAX_CONSECUTIVE_LOSSES = 3

# Drawdown tối đa cho phép (đơn vị: phần trăm)
# Drawdown = (Balance - Equity) / Balance * 100
# Nếu drawdown > MAX_DRAWDOWN_PERCENT → Bot sẽ không mở lệnh mới
MAX_DRAWDOWN_PERCENT = 8  # Đơn vị: %

# Mức lỗ tối đa trong 1 ngày (đơn vị: phần trăm của balance)
# Nếu tổng lỗ trong ngày > balance * MAX_DAILY_LOSS_PERCENT / 100 → Bot dừng
MAX_DAILY_LOSS_PERCENT = 4  # Đơn vị: %

# Mức lỗ tối đa cho mỗi lệnh (đơn vị: phần trăm của balance)
# Nếu 1 lệnh thua > balance * MAX_LOSS_PER_TRADE / 100 → Cần kiểm tra lại
MAX_LOSS_PER_TRADE = 2.0  # Đơn vị: %

# ============================================================================
# THỜI GIAN GIAO DỊCH - Các khung giờ không được giao dịch (GMT)
# ============================================================================

# Danh sách các khung giờ không được giao dịch (format: "HH:MM")
# Bot sẽ tự động bỏ qua các tín hiệu trong các khung giờ này
# Giảm số session cấm để tăng cơ hội giao dịch (chỉ giữ lại session rủi ro cao nhất)
NO_TRADE_SESSIONS = [
    ("20:00", "22:00"),  # NY Open - Giờ mở cửa thị trường New York (thường biến động mạnh)
    # ("14:30", "15:30"),  # US News - Tạm thời bỏ để tăng cơ hội giao dịch
    # ("00:00", "01:00")   # Asian session - Tạm thời bỏ để tăng cơ hội giao dịch
]

# Thời gian sau khi không được giao dịch vào thứ 6 (format: "HH:MM")
# Bot sẽ dừng giao dịch sau thời điểm này vào thứ 6 để tránh rủi ro cuối tuần
NO_TRADE_FRIDAY_AFTER = "20:00"

# Thời gian nghỉ sau khi thua 1 lệnh (đơn vị: phút)
# Sau khi thua 1 lệnh, bot sẽ đợi BREAK_AFTER_LOSS_MINUTES phút trước khi tìm tín hiệu mới
# Mục đích: Tránh revenge trading (giao dịch trả thù)
# Giảm từ 60 xuống 30 phút để tăng cơ hội giao dịch
BREAK_AFTER_LOSS_MINUTES = 30

# ============================================================================
# PHÂN TÍCH KỸ THUẬT - Cấu hình các chỉ báo và điều kiện tín hiệu
# ============================================================================

# Số lượng tín hiệu tối thiểu cần có để mở lệnh
# Bot sẽ chỉ mở lệnh khi có ít nhất MIN_SIGNAL_STRENGTH tín hiệu đồng thuận
# Giá trị cao hơn = ít lệnh nhưng chính xác hơn
# Giá trị thấp hơn = nhiều lệnh nhưng có thể nhiều false signals
MIN_SIGNAL_STRENGTH = 2  # Khuyến nghị: 2-3 cho M15 timeframe

# ============================================================================
# ĐIỀU KIỆN THỊ TRƯỜNG - Các điều kiện về spread và tin tức
# ============================================================================

# Spread tối đa cho phép (đơn vị: pips)
# Nếu spread > MAX_SPREAD → Bot sẽ không mở lệnh (spread quá cao = chi phí cao)
MAX_SPREAD = 50  # Đơn vị: pips

# Thời gian buffer trước/sau tin tức quan trọng (đơn vị: phút)
# Bot sẽ tránh giao dịch trong khoảng thời gian này quanh tin tức quan trọng
# (Hiện tại chưa được triển khai đầy đủ)
NEWS_BUFFER_MINUTES = 30

# ============================================================================
# CÀI ĐẶT BOT - Các thông số vận hành của bot
# ============================================================================

# Khoảng thời gian giữa các lần kiểm tra tín hiệu (đơn vị: giây)
# Bot sẽ kiểm tra thị trường mỗi CHECK_INTERVAL giây
CHECK_INTERVAL = 60  # Đơn vị: giây (seconds) - Đã tăng từ 30s lên 60s để giảm tải

# Có ghi log các giao dịch hay không (True/False)
# Nếu True, bot sẽ ghi lại chi tiết mỗi giao dịch vào file log
LOG_TRADES = True

# ============================================================================
# TÀI KHOẢN MT5 - Thông tin đăng nhập MetaTrader 5
# ============================================================================

# Số tài khoản MT5
ACCOUNT_NUMBER = 270358962

# Tên server MT5 (tên broker)
SERVER = "Exness-MT5Trial17"

# Mật khẩu đăng nhập MT5
# Lưu ý: Nếu để trống, MT5 sẽ sử dụng mật khẩu đã lưu trong terminal
PASSWORD = "@Dinhhieu273"

# ============================================================================
# TELEGRAM NOTIFICATIONS - Cấu hình thông báo Telegram
# ============================================================================

# Có sử dụng Telegram để gửi thông báo hay không (True/False)
USE_TELEGRAM = True

# Token của Telegram Bot (lấy từ @BotFather trên Telegram)
# Để lấy token: Tạo bot mới hoặc xem bot hiện tại trên @BotFather
TELEGRAM_BOT_TOKEN = "6398751744:AAGp7VH7B00_kzMqdaFB59xlqAXnlKTar-g"

# Chat ID để nhận thông báo (ID của user hoặc group trên Telegram)
# Để lấy Chat ID: Gửi tin nhắn cho bot @userinfobot hoặc tìm trong bot logs
TELEGRAM_CHAT_ID = "1887610382"