"""
CẤU HÌNH BOT ETHUSD
===================
File này chứa tất cả các tham số cấu hình cho bot giao dịch Ethereum tự động.
Tất cả các giá trị có thể được điều chỉnh tùy theo chiến lược và điều kiện thị trường.
"""

# ============================================================================
# SYMBOL VÀ TIMEFRAME - Cấu hình cặp tiền tệ và khung thời gian
# ============================================================================

# Symbol để giao dịch (ETHUSD = Ethereum/USD)
SYMBOL = "ETHUSD"

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
# Điều chỉnh để giữ mức rủi ro $5-10 mỗi lệnh (phù hợp với vốn nhỏ)
RISK_PER_TRADE = 0.5  # Đơn vị: phần trăm (%) (Balance $1000 → Risk $5, Balance $2000 → Risk $10)

# Tỷ lệ equity an toàn tối thiểu so với balance (0.92 = 92%)
# Nếu equity < balance * SAFE_EQUITY_RATIO → Bot sẽ không mở lệnh mới
# Mục đích: Bảo vệ tài khoản khi có quá nhiều lệnh đang thua
SAFE_EQUITY_RATIO = 0.92  # Giá trị từ 0.0 đến 1.0

# Free margin tối thiểu (đơn vị: USD hoặc % của balance)
# Bot sẽ không mở lệnh mới nếu free margin < MIN_FREE_MARGIN
# Có 2 cách cấu hình:
# - Số dương (ví dụ: 50) → Tối thiểu $50 USD
# - Số âm (ví dụ: -0.1) → Tối thiểu 10% của balance
MIN_FREE_MARGIN = 50.0  # Đơn vị: USD (hoặc % nếu < 0, ví dụ: -0.1 = 10%)

# Số lượng vị thế tối đa có thể mở cùng lúc
# Nếu đã có MAX_POSITIONS lệnh mở → Bot sẽ không mở lệnh mới
MAX_POSITIONS = 2

# Số lượng lệnh tối đa có thể mở trong 1 ngày
# Mục đích: Tránh over-trading
MAX_DAILY_TRADES = 10

# Số lượng lệnh tối đa có thể mở trong 1 giờ
# Mục đích: Tránh mở quá nhiều lệnh trong thời gian ngắn
# Tăng từ 1 lên 2 để tăng cơ hội giao dịch
MAX_HOURLY_TRADES = 2

# Lot size tối thiểu và tối đa cho phép (đơn vị: lots)
# Bot sẽ tự động tính lot size dựa trên risk, nhưng sẽ giới hạn trong khoảng này
# ⚠️ LƯU Ý: ETH trên MT5 có lot size tối thiểu là 0.1 (không phải 0.01 như BTC hay XAUUSD)
MIN_LOT_SIZE = 0.1   # Lot size tối thiểu cho ETHUSD trên MT5 (0.1 = minimum lot)
MAX_LOT_SIZE = 1.0   # Lot size tối đa cho phép mỗi lệnh

# ============================================================================
# STOP LOSS & TAKE PROFIT - Cấu hình SL/TP
# ============================================================================

# Stop Loss tối thiểu (đơn vị: pips)
# SL sẽ không nhỏ hơn giá trị này để đảm bảo có đủ không gian cho biến động giá
# Với ETHUSD (Ethereum), biến động lớn nên cần SL tối thiểu 250 pips để tránh bị "quét" bởi biến động ngẫu nhiên
MIN_SL_PIPS = 250  # Tăng lên 250 pips để đủ xa, tránh bị quét bởi noise

# Take Profit tối thiểu (đơn vị: pips)
# TP sẽ không nhỏ hơn giá trị này
MIN_TP_PIPS = 200

# Tỷ lệ Risk/Reward tối thiểu (Risk:Reward)
# Ví dụ: MIN_RR_RATIO = 1.5 → Nếu risk $10, reward tối thiểu $15
# Giá trị cao hơn = an toàn hơn nhưng khó đạt TP
MIN_RR_RATIO = 1.5  # Khuyến nghị: 1.5 - 2.0

# Giới hạn Stop Loss tối đa (đơn vị: USD)
# Bot sẽ không đặt SL quá xa để tránh risk quá lớn
# Điều chỉnh để giữ mức rủi ro $5-10 mỗi lệnh (phù hợp với vốn nhỏ)
# Nếu SL tính toán vượt quá MAX_SL_USD, bot sẽ điều chỉnh lại SL và lot size
MAX_SL_USD = 5.0  # Đơn vị: USD (giảm từ 10 xuống 8 để giữ risk $5-10)

# ============================================================================
# SL/TP ĐỘNG THEO ATR - Tự động điều chỉnh theo biến động thị trường
# ============================================================================

# Bật/tắt tính năng SL/TP động theo ATR
USE_ATR_BASED_SL_TP = True  # True: Tính SL/TP theo ATR, False: Dùng công thức cố định

# Chế độ tính SL/TP theo ATR:
# - "ATR_FREE": SL/TP tự do theo ATR, KHÔNG giới hạn theo USD (chỉ đảm bảo SL >= MIN_SL_PIPS)
#              → SL có thể $20, $50, $100 tùy theo ATR và lot size
# - "ATR_BOUNDED": SL/TP theo ATR nhưng ĐIỀU CHỈNH để giới hạn MIN_SL_USD ≤ SL ≤ MAX_SL_USD
#                 → SL luôn nằm trong khoảng $5-$10 (điều chỉnh sl_pips hoặc lot_size)
ATR_SL_TP_MODE = "ATR_BOUNDED"  # Các giá trị: "ATR_FREE", "ATR_BOUNDED"

# Giới hạn SL theo USD cho mode ATR_BOUNDED
# Bot sẽ điều chỉnh SL để nằm trong khoảng MIN_SL_USD ≤ SL ≤ MAX_SL_USD
ATR_MIN_SL_USD = 4.0   # SL tối thiểu: $5 (cho mode ATR_BOUNDED)
ATR_MAX_SL_USD = 5.0  # SL tối đa: $10 (cho mode ATR_BOUNDED)

# Hệ số nhân ATR để tính SL và TP
# Ví dụ: ATR = 100 pips, ATR_MULTIPLIER_SL = 2.0 → SL = 200 pips
# Tự động điều chỉnh theo biến động (ATR càng lớn → SL/TP càng xa)
# Tăng ATR_MULTIPLIER_SL lên 2.0-2.5 để SL đủ xa, tránh bị "quét" bởi biến động ngẫu nhiên
ATR_MULTIPLIER_SL = 2.5  # Hệ số nhân ATR cho Stop Loss (tăng từ 1.5 lên 2.0 để đủ xa)
ATR_MULTIPLIER_TP = 3.5  # Hệ số nhân ATR cho Take Profit (tăng từ 2.5 lên 3.0 để tăng RR ratio)

# Sử dụng ATR timeframe riêng (thường là M15 hoặc H1)
# Nếu None, sẽ dùng cùng timeframe với phân tích kỹ thuật
ATR_TIMEFRAME = "M15"  # Các giá trị: "M15", "M30", "H1", "H4", None (dùng TIMEFRAME)

# Số chu kỳ để tính ATR (chuẩn: 14)
ATR_PERIOD = 14

# ============================================================================
# TRAILING STOP THÔNG MINH - Bảo vệ lợi nhuận tự động
# ============================================================================

# Bật/tắt tính năng Smart Trailing Stop
ENABLE_TRAILING_STOP = True  # True: Bật trailing stop, False: Tắt

# Khi lợi nhuận đạt bao nhiêu pips thì bắt đầu kéo SL
TRAIL_START_PIPS = 150  # Đơn vị: pips (ví dụ: 150 pips = 1.5% với ETH)

# Khoảng cách giữa giá hiện tại và SL khi trailing
TRAIL_DISTANCE_PIPS = 100  # Đơn vị: pips (SL sẽ cách giá hiện tại 100 pips)

# Nếu lợi nhuận > TRAIL_HARD_LOCK_PIPS thì chốt cứng (đảm bảo không mất lời)
TRAIL_HARD_LOCK_PIPS = 250  # Đơn vị: pips (khi đạt >250 pips lời, SL sẽ được "khóa" ở mức an toàn)

# ============================================================================
# TP ĐỘNG THEO SỨC MẠNH XU HƯỚNG - Tăng TP khi trend mạnh
# ============================================================================

# Bật/tắt tính năng tăng TP khi trend mạnh
ENABLE_TP_BOOST = True  # True: Tăng TP khi trend mạnh, False: Tắt

# Nếu RSI vượt ngưỡng trend mạnh → tăng TP thêm %
STRONG_TREND_TP_BOOST = 0.3  # +30% TP nếu trend mạnh (ví dụ: 0.3 = +30%)

# Ngưỡng RSI để xác định trend mạnh
RSI_TREND_THRESHOLD_UP = 65   # RSI > 65 = uptrend mạnh (BUY)
RSI_TREND_THRESHOLD_DOWN = 35 # RSI < 35 = downtrend mạnh (SELL)

# ============================================================================
# THOÁT LỆNH THÔNG MINH - Đóng lệnh sớm khi tín hiệu đảo chiều
# ============================================================================

# Bật/tắt tính năng Smart Exit (thoát lệnh thông minh)
ENABLE_SMART_EXIT = True  # True: Bật smart exit, False: Tắt

# Nếu có bao nhiêu tín hiệu ngược chiều liên tiếp → đóng lệnh sớm
OPPOSITE_SIGNAL_COUNT_TO_EXIT = 2  # Số tín hiệu ngược chiều cần để thoát lệnh

# Nếu RSI quay đầu vượt vùng trung tính → đóng lệnh sớm
ENABLE_RSI_EXIT = True  # Bật/tắt RSI exit
RSI_EXIT_THRESHOLD = 50  # RSI vượt 50 (vùng trung tính) → thoát lệnh

# Nếu lợi nhuận giảm quá nhanh (drawdown từ đỉnh > X%) → thoát lệnh bảo toàn
ENABLE_PROFIT_DRAWDOWN_EXIT = True  # Bật/tắt profit drawdown exit
PROFIT_DRAWDOWN_EXIT_PERCENT = 40   # Thoát nếu lợi nhuận giảm >40% so với đỉnh

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
# THỜI GIAN GIAO DỊCH - Các khung giờ không được giao dịch (US/Eastern Time)
# ============================================================================

# Timezone cho thị trường USA (New York)
# Sử dụng US/Eastern để tự động xử lý EST/EDT (Daylight Saving Time)
TRADING_TIMEZONE = "US/Eastern"  # EST/EDT (New York time)

# Danh sách các khung giờ không được giao dịch (format: "HH:MM" theo giờ US/Eastern)
# Bot sẽ tự động chuyển đổi sang giờ US/Eastern để so sánh
# Giảm số session cấm để tăng cơ hội giao dịch (chỉ giữ lại session rủi ro cao nhất)
NO_TRADE_SESSIONS = [
    ("08:00", "10:00"),  # NY Open - Giờ mở cửa thị trường New York (8:00 AM - 10:00 AM EST/EDT)
    # ("14:30", "15:30"),  # US News - Tạm thời bỏ để tăng cơ hội giao dịch
    # ("00:00", "01:00")   # Asian session - Tạm thời bỏ để tăng cơ hội giao dịch
]

# Thời gian sau khi không được giao dịch vào thứ 6 (format: "HH:MM" theo giờ US/Eastern)
# Bot sẽ dừng giao dịch sau thời điểm này vào thứ 6 để tránh rủi ro cuối tuần
NO_TRADE_FRIDAY_AFTER = "17:00"  # 5:00 PM EST/EDT (thường là 5:00 PM NY time)

# Thời gian nghỉ sau khi thua 1 lệnh (đơn vị: phút)
# Sau khi thua 1 lệnh, bot sẽ đợi BREAK_AFTER_LOSS_MINUTES phút trước khi tìm tín hiệu mới
# Mục đích: Tránh revenge trading (giao dịch trả thù)
# Giảm từ 60 xuống 30 phút để tăng cơ hội giao dịch
BREAK_AFTER_LOSS_MINUTES = 30

# Thời gian tối thiểu giữa 2 lệnh cùng chiều (đơn vị: phút)
# Bot sẽ không mở lệnh BUY nếu đã có lệnh BUY mở trong vòng MIN_TIME_BETWEEN_SAME_DIRECTION phút
# Tương tự với SELL
# Mục đích: Tránh mở quá nhiều lệnh cùng chiều trong thời gian ngắn
MIN_TIME_BETWEEN_SAME_DIRECTION = 60  # Đơn vị: phút

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
# ⚠️ LƯU Ý: ETHUSD có spread cao hơn XAUUSD (thường 500-2000 pips)
# Với giá ETH ~$100,000, spread 1000-2000 pips = $10-$20 USD là bình thường
MAX_SPREAD = 1500  # Đơn vị: pips (tăng từ 35 lên 1500 cho ETHUSD)

# Độ lệch giá cho phép khi đặt lệnh (đơn vị: points)
# Khi giá thay đổi nhanh, MT5 cho phép trượt giá trong phạm vi này
# Với ETH dao động mạnh: 100-200 points (cho phép trượt nhiều hơn)
DEVIATION = 100  # Đơn vị: points

# Thời gian buffer trước/sau tin tức quan trọng (đơn vị: phút)
# Bot sẽ tránh giao dịch trong khoảng thời gian này quanh tin tức quan trọng
# (Hiện tại chưa được triển khai đầy đủ)
NEWS_BUFFER_MINUTES = 30

# ============================================================================
# CÀI ĐẶT BOT - Các thông số vận hành của bot
# ============================================================================

# Khoảng thời gian giữa các lần kiểm tra tín hiệu (đơn vị: giây)
# Bot sẽ kiểm tra thị trường mỗi CHECK_INTERVAL giây
CHECK_INTERVAL = 30  # Đơn vị: giây (seconds) - Đã tăng từ 30s lên 60s để giảm tải

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