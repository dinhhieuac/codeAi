"""
CẤU HÌNH BOT GBPUSD
===================
File này chứa tất cả các tham số cấu hình cho bot giao dịch GBP/USD tự động.
Tất cả các giá trị có thể được điều chỉnh tùy theo chiến lược và điều kiện thị trường.
"""

# ============================================================================
# SYMBOL VÀ TIMEFRAME - Cấu hình cặp tiền tệ và khung thời gian
# ============================================================================

# Symbol để giao dịch (GBPUSD = British Pound/USD)
SYMBOL = "GBPUSDc"

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
# Với GBPUSD (Forex), biến động nhỏ hơn XAUUSD nên cần SL tối thiểu 20-30 pips
MIN_SL_PIPS = 30  # 30 pips cho GBPUSD (1 pip = 0.0001)

# Take Profit tối thiểu (đơn vị: pips)
# TP sẽ không nhỏ hơn giá trị này
MIN_TP_PIPS = 25  # 25 pips cho GBPUSD

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

# ============================================================================
# BREAK-EVEN STEP - Dời SL về hòa vốn khi đạt ngưỡng lợi nhuận
# ============================================================================

# Khi lợi nhuận đạt ngưỡng này → Dời SL về entry + buffer (Break-even)
# XAUUSD: 600 pips (≈ $6 với 0.01 lot)
BREAK_EVEN_START_PIPS = 60  # Đơn vị: pips (GBPUSD: 60 pips ≈ $6 với 0.01 lot, tương đương 600 pips XAUUSD)

# Buffer khi dời SL về break-even (tránh bị quét do nhiễu)
# BUY: SL = entry + buffer, SELL: SL = entry - buffer
BREAK_EVEN_BUFFER_PIPS = 5  # Đơn vị: pips (GBPUSD: 5 pips buffer)

# ============================================================================
# ATR-BASED TRAILING - Dời SL theo biến động thị trường
# ============================================================================

# Hệ số nhân ATR để tính khoảng cách trailing
# trail_distance = ATR × ATR_K
# XAUUSD: 1.5 (phù hợp với độ biến động của vàng)
ATR_TRAILING_K = 1.5  # Hệ số nhân ATR (1.2-1.8)

# Khoảng cách tối thiểu giữa SL và giá (tính bằng pips)
# Đảm bảo SL không quá gần giá do nhiễu
ATR_TRAILING_MIN_DISTANCE_PIPS = 10  # Đơn vị: pips (GBPUSD: 10 pips minimum distance)

# ============================================================================
# PARTIAL CLOSE - Chốt một phần lợi nhuận
# ============================================================================

# Bật/tắt tính năng Partial Close
ENABLE_PARTIAL_CLOSE = True  # True: Bật partial close, False: Tắt

# Mốc TP1: Khi đạt mức lợi nhuận này → Đóng 30-50% volume
PARTIAL_CLOSE_TP1_PIPS = 100  # Đơn vị: pips (GBPUSD: 100 pips ≈ $10 với 0.01 lot)
PARTIAL_CLOSE_TP1_PERCENT = 40  # Đóng bao nhiêu % volume (30-50%)

# Mốc TP2: Khi đạt mức lợi nhuận này → Đóng thêm 25-30% volume
PARTIAL_CLOSE_TP2_PIPS = 200  # Đơn vị: pips (GBPUSD: 200 pips ≈ $20 với 0.01 lot)
PARTIAL_CLOSE_TP2_PERCENT = 30  # Đóng bao nhiêu % volume còn lại

# Mốc TP3: Khi đạt mức lợi nhuận này → Đóng thêm 25-30% volume
PARTIAL_CLOSE_TP3_PIPS = 300  # Đơn vị: pips (GBPUSD: 300 pips ≈ $30 với 0.01 lot)
PARTIAL_CLOSE_TP3_PERCENT = 30  # Đóng bao nhiêu % volume còn lại

# Buffer cho SL sau khi partial close (lớn hơn break-even buffer)
PARTIAL_CLOSE_SL_BUFFER_PIPS = 10  # Đơn vị: pips (GBPUSD: 10 pips buffer)

# Hệ số ATR cho SL sau partial close (chặt hơn khi đã chốt lời)
PARTIAL_CLOSE_ATR_K = 1.0  # Hệ số ATR (1.0 = chặt hơn, 1.5 = lỏng hơn)

# ============================================================================
# CẤU HÌNH TRAILING CŨ (Giữ lại để tương thích)
# ============================================================================

# Khi lợi nhuận đạt bao nhiêu pips thì bắt đầu kéo SL (legacy)
TRAIL_START_PIPS = 150  # Đơn vị: pips (ví dụ: 150 pips = 1.5% với Gold)

# Khoảng cách giữa giá hiện tại và SL khi trailing (legacy)
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
# ⚠️ LƯU Ý: GBPUSD là forex, ATR thường nhỏ hơn crypto (khoảng 50-200 pips)
MAX_ATR = 200  # Đơn vị: pips (≈ $20 với 1 lot, tránh volatility cực đại cho forex)

# ============================================================================
# ĐIỀU KIỆN THỊ TRƯỜNG - Các điều kiện về spread và tin tức
# ============================================================================

# Spread tối đa cho phép (đơn vị: pips)
# Nếu spread > MAX_SPREAD → Bot sẽ không mở lệnh (spread quá cao = chi phí cao)
# ⚠️ Tăng từ 5 lên 7 pips để có buffer nhỏ, nhưng vẫn giữ spread hợp lý cho forex
MAX_SPREAD = 7  # Đơn vị: pips (tăng từ 5 lên 7 để có buffer, GBPUSD thường có spread 1-3 pips)

# Độ lệch giá cho phép khi đặt lệnh (đơn vị: points)
# Khi giá thay đổi nhanh, MT5 cho phép trượt giá trong phạm vi này
# Với Gold dao động mạnh: 100-200 points (cho phép trượt nhiều hơn)
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
account_json_path = project_root / "GBPUSD_BOT_FULL/md5_accout.json"  # Lưu ý: file có tên "accout" (không phải "account")

# Giá trị mặc định (fallback)
DEFAULT_ACCOUNT_NUMBER=0
DEFAULT_SERVER = ""
DEFAULT_PASSWORD = ""

# Đọc từ file JSON nếu tồn tại
try:
    if account_json_path.exists():
        with open(account_json_path, 'r', encoding='utf-8') as f:
            account_data = json.load(f)
            ACCOUNT_NUMBER = account_data.get('ACCOUNT_NUMBER', DEFAULT_ACCOUNT_NUMBER)
            SERVER = account_data.get('SERVER', DEFAULT_SERVER)
            PASSWORD = account_data.get('PASSWORD', DEFAULT_PASSWORD)
            SYMBOL = account_data.get('SYMBOL', SYMBOL)
            PATH= account_data.get('PATH', "")  # Cập nhật SYMBOL nếu có trong file
            print(f"✅ Đã đọc thông tin tài khoản từ {account_json_path}")
    else:
        # File không tồn tại → dùng giá trị mặc định
        
        print(f"⚠️ File {account_json_path} không tồn tại, sử dụng giá trị mặc định")
except Exception as e:
    # Lỗi khi đọc file → dùng giá trị mặc định
    print(f"⚠️ Lỗi khi đọc file {account_json_path}: {e}")
    print(f"   → Sử dụng giá trị mặc định")
 

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

# Chọn config để sử dụng (0 = CONSERVATIVE, 1 = MODERATE, 2 = AGGRESSIVE, 3 = ULTRA_CONSERVATIVE, 4 = SCALPING, 5 = SWING_TRADING, 6 = LOW_LOSS)
# Hoặc dùng tên config: "CONSERVATIVE", "MODERATE", "AGGRESSIVE", "ULTRA_CONSERVATIVE", "SCALPING", "SWING_TRADING", "LOW_LOSS"
CONFIG_INDEX = 1  # 1 = MODERATE (config mặc định hiện tại)
# CONFIG_INDEX = "MODERATE"  # Hoặc dùng tên config

# ============================================================================
# ARRAY CÁC CẤU HÌNH
# ============================================================================

CONFIGS = [
    # ========================================================================
    # CONFIG 0: CONSERVATIVE (Bảo thủ - Tỉ lệ thua thấp)
    # ========================================================================
    {
        "name": "CONSERVATIVE",
        "description": "Cấu hình bảo thủ - Tỉ lệ thua thấp, ít lệnh nhưng an toàn",
        
        # Risk Management
        "RISK_PER_TRADE": 0.3,  # Giảm risk xuống 0.3%
        "MIN_SL_PIPS": 300,  # SL xa hơn để tránh bị quét
        "MIN_TP_PIPS": 300,
        "MIN_RR_RATIO": 2.0,  # Risk:Reward cao hơn (1:2)
        "MAX_SL_USD": 3.0,  # Giảm max SL xuống $3
        "MAX_POSITIONS": 1,  # Chỉ 1 lệnh cùng lúc
        "MAX_DAILY_TRADES": 10,  # Giảm số lệnh/ngày
        "MAX_HOURLY_TRADES": 1,
        
        # Signal Strength
        "MIN_SIGNAL_STRENGTH": 3,  # Yêu cầu 3 tín hiệu (cao hơn)
        
        # ATR Settings
        "ATR_MULTIPLIER_SL": 3.0,  # SL xa hơn
        "ATR_MULTIPLIER_TP": 4.0,  # TP xa hơn
        "ATR_SL_TP_MODE": "ATR_BOUNDED",
        "ATR_MIN_SL_USD": 3.0,
        "ATR_MAX_SL_USD": 4.0,
        
        # Time Rules
        "MIN_TIME_BETWEEN_SAME_DIRECTION": 120,  # 2 giờ giữa 2 lệnh cùng chiều
        "BREAK_AFTER_LOSS_MINUTES": 60,  # Nghỉ 1 giờ sau khi thua
        
        # Trailing Stop
        "BREAK_EVEN_START_PIPS": 800,  # Break-even muộn hơn
        "ATR_TRAILING_K": 2.0,  # Trailing xa hơn
    },
    
    # ========================================================================
    # CONFIG 1: MODERATE (Cân bằng - Mặc định hiện tại)
    # ========================================================================
    {
        "name": "MODERATE",
        "description": "Cấu hình cân bằng - Cân bằng giữa số lệnh và tỉ lệ thắng",
        
        # Risk Management
        "RISK_PER_TRADE": 0.5,
        "MIN_SL_PIPS": 250,
        "MIN_TP_PIPS": 200,
        "MIN_RR_RATIO": 1.5,
        "MAX_SL_USD": 5.0,
        "MAX_POSITIONS": 1,
        "MAX_DAILY_TRADES": 50,
        "MAX_HOURLY_TRADES": 2,
        
        # Signal Strength
        "MIN_SIGNAL_STRENGTH": 2,
        
        # ATR Settings
        "ATR_MULTIPLIER_SL": 2.5,
        "ATR_MULTIPLIER_TP": 3.5,
        "ATR_SL_TP_MODE": "ATR_BOUNDED",
        "ATR_MIN_SL_USD": 4.0,
        "ATR_MAX_SL_USD": 5.0,
        
        # Time Rules
        "MIN_TIME_BETWEEN_SAME_DIRECTION": 60,
        "BREAK_AFTER_LOSS_MINUTES": 30,
        
        # Trailing Stop
        "BREAK_EVEN_START_PIPS": 600,
        "ATR_TRAILING_K": 1.5,
    },
    
    # ========================================================================
    # CONFIG 2: AGGRESSIVE (Tích cực - Nhiều lệnh, tỉ lệ thua cao hơn)
    # ========================================================================
    {
        "name": "AGGRESSIVE",
        "description": "Cấu hình tích cực - Nhiều lệnh hơn, chấp nhận tỉ lệ thua cao hơn",
        
        # Risk Management
        "RISK_PER_TRADE": 0.5,
        "MIN_SL_PIPS": 200,  # SL gần hơn
        "MIN_TP_PIPS": 150,
        "MIN_RR_RATIO": 1.2,  # Risk:Reward thấp hơn
        "MAX_SL_USD": 5.0,
        "MAX_POSITIONS": 2,
        "MAX_DAILY_TRADES": 50,
        "MAX_HOURLY_TRADES": 3,  # Tăng lên 3
        
        # Signal Strength
        "MIN_SIGNAL_STRENGTH": 2,  # Giữ nguyên
        
        # ATR Settings
        "ATR_MULTIPLIER_SL": 2.0,  # SL gần hơn
        "ATR_MULTIPLIER_TP": 3.0,  # TP gần hơn
        "ATR_SL_TP_MODE": "ATR_BOUNDED",
        "ATR_MIN_SL_USD": 4.0,
        "ATR_MAX_SL_USD": 5.0,
        
        # Time Rules
        "MIN_TIME_BETWEEN_SAME_DIRECTION": 45,  # Giảm xuống 45 phút
        "BREAK_AFTER_LOSS_MINUTES": 20,  # Nghỉ ít hơn
        
        # Trailing Stop
        "BREAK_EVEN_START_PIPS": 500,  # Break-even sớm hơn
        "ATR_TRAILING_K": 1.2,  # Trailing gần hơn
    },
    
    # ========================================================================
    # CONFIG 3: ULTRA CONSERVATIVE (Cực bảo thủ - Rất ít lệnh, rất an toàn)
    # ========================================================================
    {
        "name": "ULTRA_CONSERVATIVE",
        "description": "Cấu hình cực bảo thủ - Rất ít lệnh, tỉ lệ thắng cao",
        
        # Risk Management
        "RISK_PER_TRADE": 0.2,  # Risk rất thấp
        "MIN_SL_PIPS": 400,  # SL rất xa
        "MIN_TP_PIPS": 400,
        "MIN_RR_RATIO": 2.5,  # Risk:Reward rất cao (1:2.5)
        "MAX_SL_USD": 2.0,  # Max SL rất thấp
        "MAX_POSITIONS": 1,
        "MAX_DAILY_TRADES": 5,  # Rất ít lệnh
        "MAX_HOURLY_TRADES": 1,
        
        # Signal Strength
        "MIN_SIGNAL_STRENGTH": 4,  # Yêu cầu 4 tín hiệu
        
        # ATR Settings
        "ATR_MULTIPLIER_SL": 3.5,  # SL rất xa
        "ATR_MULTIPLIER_TP": 5.0,  # TP rất xa
        "ATR_SL_TP_MODE": "ATR_BOUNDED",
        "ATR_MIN_SL_USD": 2.0,
        "ATR_MAX_SL_USD": 3.0,
        
        # Time Rules
        "MIN_TIME_BETWEEN_SAME_DIRECTION": 180,  # 3 giờ
        "BREAK_AFTER_LOSS_MINUTES": 120,  # Nghỉ 2 giờ
        
        # Trailing Stop
        "BREAK_EVEN_START_PIPS": 1000,  # Break-even rất muộn
        "ATR_TRAILING_K": 2.5,  # Trailing rất xa
    },
    
    # ========================================================================
    # CONFIG 4: SCALPING (Scalping - Nhiều lệnh nhỏ, SL/TP gần)
    # ========================================================================
    {
        "name": "SCALPING",
        "description": "Cấu hình scalping - Nhiều lệnh nhỏ, SL/TP gần, chốt lời nhanh",
        
        # Risk Management
        "RISK_PER_TRADE": 0.3,  # Risk thấp cho mỗi lệnh
        "MIN_SL_PIPS": 150,  # SL gần
        "MIN_TP_PIPS": 100,
        "MIN_RR_RATIO": 1.0,  # Risk:Reward 1:1
        "MAX_SL_USD": 3.0,
        "MAX_POSITIONS": 2,
        "MAX_DAILY_TRADES": 50,
        "MAX_HOURLY_TRADES": 4,  # Nhiều lệnh hơn
        
        # Signal Strength
        "MIN_SIGNAL_STRENGTH": 2,
        
        # ATR Settings
        "ATR_MULTIPLIER_SL": 1.5,  # SL gần
        "ATR_MULTIPLIER_TP": 2.0,  # TP gần
        "ATR_SL_TP_MODE": "ATR_BOUNDED",
        "ATR_MIN_SL_USD": 2.0,
        "ATR_MAX_SL_USD": 3.0,
        
        # Time Rules
        "MIN_TIME_BETWEEN_SAME_DIRECTION": 30,  # 30 phút
        "BREAK_AFTER_LOSS_MINUTES": 15,  # Nghỉ ít
        
        # Trailing Stop
        "BREAK_EVEN_START_PIPS": 300,  # Break-even sớm
        "ATR_TRAILING_K": 1.0,  # Trailing gần
    },
    
    # ========================================================================
    # CONFIG 5: SWING TRADING (Swing - Ít lệnh, SL/TP xa, giữ lâu)
    # ========================================================================
    {
        "name": "SWING_TRADING",
        "description": "Cấu hình swing trading - Ít lệnh, SL/TP xa, giữ lâu",
        
        # Risk Management
        "RISK_PER_TRADE": 0.5,
        "MIN_SL_PIPS": 500,  # SL rất xa
        "MIN_TP_PIPS": 500,
        "MIN_RR_RATIO": 2.0,
        "MAX_SL_USD": 8.0,  # Cho phép SL lớn hơn
        "MAX_POSITIONS": 1,
        "MAX_DAILY_TRADES": 5,
        "MAX_HOURLY_TRADES": 1,
        
        # Signal Strength
        "MIN_SIGNAL_STRENGTH": 3,
        
        # ATR Settings
        "ATR_MULTIPLIER_SL": 4.0,  # SL rất xa
        "ATR_MULTIPLIER_TP": 6.0,  # TP rất xa
        "ATR_SL_TP_MODE": "ATR_FREE",  # Không giới hạn USD
        "ATR_MIN_SL_USD": 5.0,
        "ATR_MAX_SL_USD": 10.0,
        
        # Time Rules
        "MIN_TIME_BETWEEN_SAME_DIRECTION": 240,  # 4 giờ
        "BREAK_AFTER_LOSS_MINUTES": 90,  # Nghỉ 1.5 giờ
        
        # Trailing Stop
        "BREAK_EVEN_START_PIPS": 1200,  # Break-even rất muộn
        "ATR_TRAILING_K": 2.0,
    },
    
    # ========================================================================
    # CONFIG 6: OPTIMIZED FOR LOW LOSS (Tối ưu để giảm tỉ lệ thua)
    # ========================================================================
    {
        "name": "LOW_LOSS",
        "description": "Tối ưu để giảm tỉ lệ thua - SL xa, signal mạnh, ít lệnh",
        
        # Risk Management
        "RISK_PER_TRADE": 0.4,
        "MIN_SL_PIPS": 350,  # SL rất xa để tránh bị quét
        "MIN_TP_PIPS": 350,
        "MIN_RR_RATIO": 1.8,  # Risk:Reward tốt
        "MAX_SL_USD": 4.0,
        "MAX_POSITIONS": 1,
        "MAX_DAILY_TRADES": 20,
        "MAX_HOURLY_TRADES": 1,
        
        # Signal Strength
        "MIN_SIGNAL_STRENGTH": 3,  # Yêu cầu 3 tín hiệu
        
        # ATR Settings
        "ATR_MULTIPLIER_SL": 3.0,  # SL xa
        "ATR_MULTIPLIER_TP": 4.5,  # TP xa
        "ATR_SL_TP_MODE": "ATR_BOUNDED",
        "ATR_MIN_SL_USD": 3.0,
        "ATR_MAX_SL_USD": 4.0,
        
        # Time Rules
        "MIN_TIME_BETWEEN_SAME_DIRECTION": 90,  # 1.5 giờ
        "BREAK_AFTER_LOSS_MINUTES": 45,  # Nghỉ 45 phút
        
        # Trailing Stop
        "BREAK_EVEN_START_PIPS": 700,  # Break-even muộn
        "ATR_TRAILING_K": 1.8,  # Trailing xa
    },
]

# ============================================================================
# CONFIG MẶC ĐỊNH (Index trong array)
# ============================================================================

# Config mặc định sẽ được sử dụng (index trong array CONFIGS)
# Có thể thay đổi bằng cách set biến môi trường CONFIG_INDEX hoặc command line argument
DEFAULT_CONFIG_INDEX = 1  # MODERATE (config hiện tại)

# ============================================================================
# HÀM HELPER ĐỂ LẤY CONFIG
# ============================================================================

def get_config(index=None):
    """
    Lấy config từ array CONFIGS
    
    Args:
        index: Index của config trong array (số) hoặc tên config (string)
               None = dùng CONFIG_INDEX hoặc DEFAULT_CONFIG_INDEX
               
    Returns:
        dict: Config được chọn
    """
    if index is None:
        # Thử lấy từ biến CONFIG_INDEX (có thể là số hoặc string)
        try:
            index = CONFIG_INDEX
        except NameError:
            index = DEFAULT_CONFIG_INDEX
    
    # Nếu index là string (tên config), tìm index tương ứng
    if isinstance(index, str):
        for i, config in enumerate(CONFIGS):
            if config["name"].upper() == index.upper():
                index = i
                break
        else:
            print(f"⚠️ Không tìm thấy config với tên '{index}', dùng config mặc định (index {DEFAULT_CONFIG_INDEX})")
            index = DEFAULT_CONFIG_INDEX
    
    # Validate index
    if not isinstance(index, int) or index < 0 or index >= len(CONFIGS):
        print(f"⚠️ Config index {index} không hợp lệ, dùng config mặc định (index {DEFAULT_CONFIG_INDEX})")
        index = DEFAULT_CONFIG_INDEX
    
    config = CONFIGS[index]
    print(f"✅ Đã chọn config: {config['name']} (index {index}) - {config['description']}")
    return config

def list_configs():
    """
    Liệt kê tất cả các config có sẵn
    
    Returns:
        list: Danh sách các config với index và mô tả
    """
    result = []
    for i, config in enumerate(CONFIGS):
        result.append({
            "index": i,
            "name": config["name"],
            "description": config["description"]
        })
    return result

# ============================================================================
# TỰ ĐỘNG LOAD CONFIG VÀ OVERRIDE CÁC BIẾN GLOBAL
# ============================================================================

# Lấy config được chọn (sử dụng CONFIG_INDEX nếu đã được định nghĩa, nếu không dùng DEFAULT_CONFIG_INDEX)
try:
    config_index_to_use = CONFIG_INDEX
except NameError:
    config_index_to_use = DEFAULT_CONFIG_INDEX

selected_config = get_config(config_index_to_use)

# Override tất cả các biến từ config được chọn
# Chỉ override các biến có trong config, giữ nguyên các biến khác (như SYMBOL, TIMEFRAME, etc.)
print(f"\n📋 Đang load config '{selected_config['name']}':")
for key, value in selected_config.items():
    if key not in ["name", "description"]:  # Bỏ qua các key metadata
        globals()[key] = value
        print(f"   • {key} = {value}")

print("=" * 60)
print(f"✅ Đã load config '{selected_config['name']}' thành công!")
print("=" * 60)