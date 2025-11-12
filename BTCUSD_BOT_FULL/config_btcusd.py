"""
CẤU HÌNH BOT BTCUSD
===================
File này chứa tất cả các tham số cấu hình cho bot giao dịch Bitcoin tự động.
Tất cả các giá trị có thể được điều chỉnh tùy theo chiến lược và điều kiện thị trường.
"""

# ============================================================================
# SYMBOL VÀ TIMEFRAME - Cấu hình cặp tiền tệ và khung thời gian
# ============================================================================

# Symbol để giao dịch (BTCUSD = Bitcoin/USD)
SYMBOL = "BTCUSDc"

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
MAX_POSITIONS = 1

# Số lượng lệnh tối đa có thể mở trong 1 ngày
# Mục đích: Tránh over-trading
MAX_DAILY_TRADES = 50

# Số lượng lệnh tối đa có thể mở trong 1 giờ
# Mục đích: Tránh mở quá nhiều lệnh trong thời gian ngắn
# Tăng từ 1 lên 2 để tăng cơ hội giao dịch
MAX_HOURLY_TRADES = 2

# Lot size tối thiểu và tối đa cho phép (đơn vị: lots)
# Bot sẽ tự động tính lot size dựa trên risk, nhưng sẽ giới hạn trong khoảng này
MIN_LOT_SIZE = 0.01  # Lot size tối thiểu (0.01 = minimum lot)
MAX_LOT_SIZE = 1.0   # Lot size tối đa cho phép mỗi lệnh

# ============================================================================
# STOP LOSS & TAKE PROFIT - Cấu hình SL/TP
# ============================================================================

# Stop Loss tối thiểu (đơn vị: pips)
# SL sẽ không nhỏ hơn giá trị này để đảm bảo có đủ không gian cho biến động giá
# Với BTCUSD (Bitcoin), biến động lớn nên cần SL tối thiểu 250 pips để tránh bị "quét" bởi biến động ngẫu nhiên
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
ATR_SL_TP_MODE = "ATR_FREE"  # Các giá trị: "ATR_FREE", "ATR_BOUNDED"

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
# ⚠️ Tăng từ 150 lên 500 pips để cho lệnh có thời gian phát triển trước khi bắt đầu trailing
# Với BTCUSD (1 pip = 1 USD), 500 pips = $5 với 0.01 lot
# Cần thời gian để lệnh phát triển, tránh trailing quá sớm
TRAIL_START_PIPS = 500  # Đơn vị: pips (tăng từ 150 lên 500 để tránh trailing quá sớm)

# Khoảng cách giữa giá hiện tại và SL khi trailing
# ⚠️ Tăng từ 100 lên 400 pips để tránh bị quét bởi biến động ngẫu nhiên
# Với BTCUSD (1 pip = 1 USD), 400 pips = $4 với 0.01 lot
# BTCUSD biến động rất lớn nên cần khoảng cách xa hơn để tránh bị "quét" bởi noise
TRAIL_DISTANCE_PIPS = 400  # Đơn vị: pips (tăng từ 100 lên 400 để tránh bị quét)

# Nếu lợi nhuận > TRAIL_HARD_LOCK_PIPS thì chốt cứng (đảm bảo không mất lời)
# ⚠️ Tăng từ 250 lên 800 pips để hard lock muộn hơn, cho phép lệnh phát triển
# Với BTCUSD (1 pip = 1 USD), 800 pips = $8 với 0.01 lot
TRAIL_HARD_LOCK_PIPS = 800  # Đơn vị: pips (tăng từ 250 lên 800 để hard lock muộn hơn)

# ============================================================================
# BREAK-EVEN & ATR TRAILING - Cấu hình dời SL thông minh
# ============================================================================

# Khi lợi nhuận đạt bao nhiêu pips thì bắt đầu break-even (dời SL về entry + buffer)
# ⚠️ Giảm từ 1500 xuống 500 pips để break-even sớm hơn, bảo vệ lợi nhuận khi đạt ~$5
# Với BTCUSD: 500 pips = $5 với 0.01 lot (đủ để bảo vệ lợi nhuận sớm)
BREAK_EVEN_START_PIPS = 500  # Đơn vị: pips (Với BTCUSD: 500 pips = $5 với 0.01 lot, giảm từ 1500)

# Buffer khi dời SL về break-even (đơn vị: pips)
# SL sẽ được dời về entry + buffer để tránh bị quét bởi noise
# ⚠️ BTCUSD biến động rất lớn trên M15, cần buffer lớn hơn XAUUSD
# Tăng từ 50 lên 200 pips để đủ xa, tránh bị quét bởi biến động ngẫu nhiên
BREAK_EVEN_BUFFER_PIPS = 200  # Đơn vị: pips (Với BTCUSD: 200 pips = $2 với 0.01 lot, tăng từ 50)

# Hệ số nhân ATR cho trailing stop (sau khi break-even)
# Khoảng cách trailing = ATR × ATR_TRAILING_K hoặc tối thiểu ATR_TRAILING_MIN_DISTANCE_PIPS
ATR_TRAILING_K = 1.5  # Hệ số nhân ATR (ví dụ: ATR = 200 pips → Distance = 300 pips)

# Khoảng cách trailing tối thiểu (đơn vị: pips)
# Đảm bảo trailing không quá gần, tránh bị quét bởi noise
ATR_TRAILING_MIN_DISTANCE_PIPS = 100  # Đơn vị: pips (Với BTCUSD: 100 pips = $1 với 0.01 lot)

# ============================================================================
# PARTIAL CLOSE - Chốt một phần lợi nhuận
# ============================================================================

# Bật/tắt tính năng Partial Close
ENABLE_PARTIAL_CLOSE = True  # True: Bật partial close, False: Tắt

# Mốc TP1: Khi đạt mức lợi nhuận này → Đóng 30-50% volume
PARTIAL_CLOSE_TP1_PIPS = 1000  # Đơn vị: pips (≈ $10 với 0.01 lot)
PARTIAL_CLOSE_TP1_PERCENT = 40  # Đóng bao nhiêu % volume (30-50%)

# Mốc TP2: Khi đạt mức lợi nhuận này → Đóng thêm 25-30% volume còn lại
PARTIAL_CLOSE_TP2_PIPS = 2000  # Đơn vị: pips (≈ $20 với 0.01 lot)
PARTIAL_CLOSE_TP2_PERCENT = 30  # Đóng bao nhiêu % volume còn lại

# Mốc TP3: Khi đạt mức lợi nhuận này → Đóng thêm 25-30% volume còn lại
PARTIAL_CLOSE_TP3_PIPS = 3000  # Đơn vị: pips (≈ $30 với 0.01 lot)
PARTIAL_CLOSE_TP3_PERCENT = 30  # Đóng bao nhiêu % volume còn lại

# Buffer khi dời SL sau partial close (đơn vị: pips)
# Sau mỗi lần partial close, SL sẽ được dời về entry + buffer lớn hơn
# ⚠️ BTCUSD biến động lớn, cần buffer lớn hơn để bảo vệ lợi nhuận đã khóa
PARTIAL_CLOSE_SL_BUFFER_PIPS = 300  # Đơn vị: pips (Với BTCUSD: 300 pips = $3 với 0.01 lot, tăng từ 100)

# Hệ số nhân ATR cho trailing sau khi partial close (chặt hơn để bảo vệ lợi nhuận đã khóa)
PARTIAL_CLOSE_ATR_K = 1.0  # Hệ số nhân ATR (nhỏ hơn ATR_TRAILING_K để trailing chặt hơn)

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
RSI_EXIT_THRESHOLD_BUY = 35  # BUY: RSI < 35 (oversold mạnh) → thoát lệnh (tăng từ 50 để tránh exit quá sớm)
RSI_EXIT_THRESHOLD_SELL = 65  # SELL: RSI > 65 (overbought mạnh) → thoát lệnh (tăng từ 50 để tránh exit quá sớm)
RSI_EXIT_MIN_PROFIT_PIPS = 200  # Profit tối thiểu (pips) trước khi exit theo RSI (tránh exit quá sớm khi chưa có lời)

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
# ⚠️ Tăng từ 60 lên 90 phút để tránh vào lệnh quá sớm, chờ tín hiệu rõ ràng hơn
# Mục đích: Tránh mở quá nhiều lệnh cùng chiều trong thời gian ngắn
MIN_TIME_BETWEEN_SAME_DIRECTION = 90  # Đơn vị: phút (tăng từ 60 lên 90 để tăng chất lượng)

# ============================================================================
# PHÂN TÍCH KỸ THUẬT - Cấu hình các chỉ báo và điều kiện tín hiệu
# ============================================================================

# Số lượng tín hiệu tối thiểu cần có để mở lệnh
# Bot sẽ chỉ mở lệnh khi có ít nhất MIN_SIGNAL_STRENGTH tín hiệu đồng thuận
# ⚠️ Tăng từ 2 lên 3 để tăng chất lượng tín hiệu, giảm tỷ lệ thua (cân bằng giữa chất lượng và số lượng)
# Với REQUIRE_STRONG_SIGNAL = True, đã yêu cầu ít nhất 1 tín hiệu mạnh → 3 điểm là hợp lý
# Giá trị cao hơn = ít lệnh nhưng chính xác hơn
# Giá trị thấp hơn = nhiều lệnh nhưng có thể nhiều false signals
MIN_SIGNAL_STRENGTH = 3  # Tăng từ 2 lên 3 để tăng chất lượng tín hiệu (khuyến nghị: 3 cho M15 timeframe)

# Yêu cầu ít nhất 1 tín hiệu mạnh (RSI cắt hoặc EMA cắt) để vào lệnh
# Tín hiệu mạnh = RSI cắt (từ trên xuống dưới 30 hoặc từ dưới lên trên 70) HOẶC EMA cắt (EMA20 cắt EMA50)
# Mục đích: Tránh vào lệnh khi chỉ có tín hiệu yếu (RSI đang ở vùng quá bán/mua nhưng chưa cắt)
REQUIRE_STRONG_SIGNAL = True  # True: Yêu cầu ít nhất 1 tín hiệu mạnh, False: Không yêu cầu

# ATR tối đa cho phép (đơn vị: pips)
# Nếu ATR > MAX_ATR → Bot sẽ không mở lệnh (volatility quá cao = rủi ro cao)
# Mục đích: Tránh vào lệnh khi thị trường quá biến động (tin tức, sự kiện lớn)
MAX_ATR = 2000  # Đơn vị: pips (≈ $2000 với 1 lot, tránh volatility cực đại)

# ============================================================================
# ĐIỀU KIỆN THỊ TRƯỜNG - Các điều kiện về spread và tin tức
# ============================================================================

# Spread tối đa cho phép (đơn vị: pips)
# Nếu spread > MAX_SPREAD → Bot sẽ không mở lệnh (spread quá cao = chi phí cao)
# ⚠️ Giảm từ 2000 xuống 1000 pips để tránh vào lệnh khi spread quá cao (chi phí cao)
# Với giá BTC ~$100,000, spread 1000 pips = $10 USD là hợp lý
MAX_SPREAD = 1000  # Đơn vị: pips (giảm từ 2000 xuống 1000 để tăng chất lượng entry)

# Độ lệch giá cho phép khi đặt lệnh (đơn vị: points)
# Khi giá thay đổi nhanh, MT5 cho phép trượt giá trong phạm vi này
# Với BTC dao động mạnh: 100-200 points (cho phép trượt nhiều hơn)
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

# Đọc thông tin tài khoản từ file md5_account.json (nếu có)
# Nếu file không tồn tại, sẽ dùng giá trị mặc định bên dưới
import json
import os
from pathlib import Path

# Tìm file md5_account.json (tìm trong thư mục gốc của project)
project_root = Path(__file__).parent.parent
account_json_path = project_root / "BTCUSD_BOT_FULL/md5_accout.json"  # Lưu ý: file có tên "accout" (không phải "account")

# Giá trị mặc định (fallback)
DEFAULT_ACCOUNT_NUMBER = 270358962
DEFAULT_SERVER = "Exness-MT5Trial17"
DEFAULT_PASSWORD = "@Dinhhieu273"

# Đọc từ file JSON nếu tồn tại
try:
    if account_json_path.exists():
        with open(account_json_path, 'r', encoding='utf-8') as f:
            account_data = json.load(f)
            ACCOUNT_NUMBER = account_data.get('ACCOUNT_NUMBER', DEFAULT_ACCOUNT_NUMBER)
            SERVER = account_data.get('SERVER', DEFAULT_SERVER)
            PASSWORD = account_data.get('PASSWORD', DEFAULT_PASSWORD)
            print(f"✅ Đã đọc thông tin tài khoản từ {account_json_path}")
    else:
        # File không tồn tại → dùng giá trị mặc định
        ACCOUNT_NUMBER = DEFAULT_ACCOUNT_NUMBER
        SERVER = DEFAULT_SERVER
        PASSWORD = DEFAULT_PASSWORD
        print(f"⚠️ File {account_json_path} không tồn tại, sử dụng giá trị mặc định")
except Exception as e:
    # Lỗi khi đọc file → dùng giá trị mặc định
    print(f"⚠️ Lỗi khi đọc file {account_json_path}: {e}")
    print(f"   → Sử dụng giá trị mặc định")
    ACCOUNT_NUMBER = DEFAULT_ACCOUNT_NUMBER
    SERVER = DEFAULT_SERVER
    PASSWORD = DEFAULT_PASSWORD

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