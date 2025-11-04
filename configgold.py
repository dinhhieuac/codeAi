"""
Configuration file cho Auto Trader - Gold (XAUUSD) Optimized v3
Giảm nhiễu, tránh cắt lỗ sớm, tối ưu cho chạy 24/7
"""

# ============================================
# MT5 Connection Settings
# ============================================
# Thông tin đăng nhập vào tài khoản MetaTrader5
MT5_LOGIN = 272736909  # Số tài khoản MT5 của bạn (số nguyên)
MT5_PASSWORD = "@Dinhhieu273"  # Mật khẩu đăng nhập MT5 (chuỗi)
MT5_SERVER = "Exness-MT5Trial14"  # Tên server MT5 (copy chính xác từ MT5: Tools → Options → Server)

# ============================================
# Trading Symbol
# ============================================ 
# Symbol công cụ tài chính muốn giao dịch
SYMBOL = "XAUUSD"  # Symbol để giao dịch: "XAUUSD" (Vàng/Gold)
# Lưu ý: Kiểm tra symbol có sẵn trong Market Watch của MT5 trước khi chạy

# ============================================
# Timeframe Settings
# ============================================
# Khung thời gian để phân tích biểu đồ
TIMEFRAME = "M15"  # Các giá trị: "M1", "M5", "M15", "M30", "H1", "H4", "D1"
# M15 = 15 phút, H1 = 1 giờ, D1 = 1 ngày
# Timeframe nhỏ hơn (M1, M5) = nhiều tín hiệu hơn nhưng nhiều nhiễu
# Timeframe lớn hơn (H1, H4) = ít tín hiệu hơn nhưng chính xác hơn

# ============================================
# Risk Management Settings
# ============================================
# Quản lý rủi ro - Các tham số quan trọng để bảo vệ tài khoản
RISK_PER_TRADE = 0.01          # Tỷ lệ rủi ro mỗi lệnh (0.01 = 1% vốn)
                                # Bot sẽ tự động tính lot size dựa trên % này
                                # Khuyến nghị: 0.01-0.02 (1-2%) cho conservative, 0.03-0.05 (3-5%) cho aggressive

MIN_LOT_SIZE = 0.01            # Lot size tối thiểu cho phép (0.01 = minimum lot)
                                # Lot size = số lượng đơn vị giao dịch (1 lot XAUUSD = 100 oz vàng)

MAX_LOT_SIZE = 0.01            # Lot size tối đa cho phép mỗi lệnh
                                # Giới hạn này ngăn bot mở lệnh quá lớn
                                # Với XAUUSD, thường đặt 0.01-0.1 tùy vốn

MAX_POSITIONS = 3              # Số lượng vị thế tối đa cùng lúc (mở bao nhiêu lệnh cùng thời điểm)
                                # Bot sẽ không mở lệnh mới nếu đã có MAX_POSITIONS lệnh mở
                                # Khuyến nghị: 3-5 cho Gold vì volatility cao

MAX_DAILY_TRADES = 50         # Giới hạn số lệnh trong 1 ngày (reset lúc 0h mỗi ngày)
                                # Ngăn bot giao dịch quá nhiều (tránh overtrading)
                                # Với M15 timeframe, 300 lệnh/ngày là hợp lý

MIN_EQUITY_RATIO = 0.9         # Tỷ lệ Equity tối thiểu so với Balance ban đầu (0.9 = 90%)
                                # Nếu Equity < MIN_EQUITY_RATIO * Balance, bot sẽ dừng giao dịch
                                # Ví dụ: Balance ban đầu = 1000, MIN_EQUITY_RATIO = 0.9 → Dừng khi Equity < 900
                                # Đây là circuit breaker để bảo vệ tài khoản khỏi drawdown quá lớn

# ============================================
# Trading Time Rules - Quy tắc về thời gian giao dịch
# ============================================
MIN_TIME_BETWEEN_SAME_DIRECTION = 30 * 60  # Thời gian tối thiểu giữa 2 lệnh cùng chiều (30 phút = 1800 giây)
                                            # Ví dụ: Đã mở BUY lúc 10:00 → Chỉ mở BUY tiếp theo sau 10:30
                                            # Giúp tránh mở quá nhiều lệnh cùng chiều trong thời gian ngắn

MIN_TIME_BETWEEN_OPPOSITE_DIRECTION = 15 * 60  # Thời gian tối thiểu giữa 2 lệnh ngược chiều (15 phút = 900 giây)
                                                # Ví dụ: Đã mở BUY lúc 10:00 → Có thể mở SELL sau 10:15 (nếu tín hiệu đảo mạnh)
                                                # Cho phép đảo chiều nhanh hơn khi có tín hiệu đảo mạnh

MAX_TRADES_PER_HOUR = 2        # Số lệnh tối đa trong 1 giờ (2 lệnh)
                                # Bot sẽ đếm số lệnh đã mở trong 1 giờ qua và chặn nếu >= 2
                                # Giúp kiểm soát tần suất giao dịch, tránh over-trading

COOLDOWN_AFTER_LOSS = 45 * 60  # Thời gian nghỉ sau khi thua 1 lệnh (45 phút = 2700 giây)
                                # Ví dụ: Đã thua 1 lệnh lúc 10:00 → Tạm dừng trade đến 10:45
                                # Giúp tránh revenge trading (giao dịch để "trả thù" sau khi thua)

# ============================================
# Stop Loss / Take Profit Settings
# ============================================
# Cài đặt Stop Loss và Take Profit - Bảo vệ lợi nhuận và giới hạn thua lỗ
USE_ATR_SL_TP = True           # True: Dùng ATR (Average True Range) để tính SL/TP động
                                # False: Dùng giá trị cố định (MIN_SL_POINTS, MIN_TP_POINTS)
                                # ATR phản ánh volatility, phù hợp với Gold vì giá dao động mạnh

# Hệ số nhân ATR để tính SL/TP (chỉ dùng khi USE_ATR_SL_TP = True)
# Với Gold, ATR thường nhỏ nên ta nhân hệ số lớn hơn so với forex
ATR_SL_MULTIPLIER = 6.0        # Hệ số nhân ATR cho Stop Loss: SL = 6.0 × ATR
                                # Giá trị cao hơn = SL xa hơn = ít bị stop loss sớm (whipsaw)
                                # Với Gold volatile: 6.0-8.0 là hợp lý

ATR_TP_MULTIPLIER = 10.0       # Hệ số nhân ATR cho Take Profit: TP = 10.0 × ATR
                                # Risk:Reward Ratio ≈ (10.0 / 6.0) = 1.67:1
                                # Tức là nếu risk $100 thì reward $167

# Giới hạn SL/TP bằng points (đơn vị nhỏ nhất của giá)
# Với XAUUSD: giá ~2,000 → 1 point = 0.01 USD (tùy broker)
# Ví dụ: SL 800 points = $8, TP 1600 points = $16 (cho 1 lot)
MIN_SL_POINTS = 800            # Stop Loss tối thiểu (points) - Áp dụng khi ATR tính ra quá nhỏ
                                # Nếu ATR × ATR_SL_MULTIPLIER < 800, sẽ dùng 800 points
                                # Đảm bảo SL không quá chặt, tránh bị cắt lỗ sớm

MAX_SL_POINTS = 5000           # Stop Loss tối đa (points) - Giới hạn trên
                                # Nếu ATR × ATR_SL_MULTIPLIER > 5000, sẽ dùng 5000 points
                                # Ngăn SL quá xa, risk quá lớn

MIN_TP_POINTS = 1600           # Take Profit tối thiểu (points)
                                # Nếu ATR × ATR_TP_MULTIPLIER < 1600, sẽ dùng 1600 points

MAX_TP_POINTS = 10000          # Take Profit tối đa (points)
                                # Giới hạn trên cho TP, tránh mục tiêu quá xa (khó đạt)

# Risk:Reward Ratio cố định (chỉ dùng khi USE_RISK_REWARD_RATIO = True)
USE_RISK_REWARD_RATIO = False  # True: Dùng RR cố định (TP = SL × RISK_REWARD_RATIO)
                                # False: Dùng ATR multipliers (linh hoạt hơn, khuyến nghị)
                                # Khi False, bot sẽ tính TP từ ATR_TP_MULTIPLIER

RISK_REWARD_RATIO = 2.0        # Tỷ lệ Risk:Reward nếu dùng cố định (ví dụ: 2.0 = risk $1, reward $2)
                                # Chỉ có hiệu lực khi USE_RISK_REWARD_RATIO = True

# ============================================
# Advanced SL/TP Methods - Các phương pháp tính SL/TP từ chỉ báo kỹ thuật
# ============================================
# Bổ sung thêm các phương pháp tính SL/TP dựa trên các chỉ báo kỹ thuật khác

# Phương pháp tính SL/TP (ưu tiên từ trên xuống)
USE_SR_BASED_SL_TP = False      # True: Dùng Support/Resistance làm SL/TP
                                # Ví dụ: BUY → SL tại Support gần nhất, TP tại Resistance gần nhất
                                # False: Dùng ATR (mặc định)

USE_BB_BASED_SL_TP = False     # True: Dùng Bollinger Bands làm SL/TP
                                # Ví dụ: BUY → SL tại BB lower, TP tại BB middle hoặc upper
                                # False: Dùng ATR (mặc định)

USE_FIB_BASED_SL_TP = False    # True: Dùng Fibonacci levels làm SL/TP
                                # Ví dụ: BUY tại FIB_618 → SL tại FIB_786, TP tại FIB_382
                                # False: Dùng ATR (mặc định)

USE_RECENT_HL_SL_TP = False    # True: Dùng Recent High/Low làm SL/TP
                                # Ví dụ: BUY → SL tại Low của nến trước, TP tại High của nến trước
                                # False: Dùng ATR (mặc định)

# Lưu ý: Các phương pháp trên chỉ hoạt động khi USE_ATR_SL_TP = True
# Nếu USE_ATR_SL_TP = False, sẽ dùng giá trị cố định (FIXED_SL_POINTS, FIXED_TP_POINTS)

# ============================================
# Technical Analysis Settings
# ============================================
# Cài đặt các chỉ báo kỹ thuật để phân tích thị trường

# RSI (Relative Strength Index) - Đo lường momentum, phát hiện overbought/oversold
RSI_PERIOD = 14                # Chu kỳ tính RSI (số nến để tính trung bình)
                                # Giá trị chuẩn: 14 (có thể 9 cho nhạy, 21 cho chậm)

RSI_OVERSOLD = 30              # Ngưỡng RSI oversold (quá bán) → Tín hiệu BUY
                                # RSI < 30 = thị trường có thể phục hồi tăng

RSI_OVERBOUGHT = 70            # Ngưỡng RSI overbought (quá mua) → Tín hiệu SELL
                                # RSI > 70 = thị trường có thể điều chỉnh giảm

# MACD (Moving Average Convergence Divergence) - Phát hiện xu hướng và momentum
MACD_FAST = 12                 # Chu kỳ EMA nhanh (phản ứng nhanh với biến động giá)
MACD_SLOW = 26                 # Chu kỳ EMA chậm (xu hướng dài hạn)
MACD_SIGNAL = 9                # Chu kỳ đường tín hiệu (signal line)
                                # MACD crossover: MACD vượt signal = tín hiệu mua/bán

# Moving Average (Trung bình động) - Xác định xu hướng
MA_TYPE = "EMA"                # Loại MA: "EMA" (Exponential - nhạy hơn) hoặc "SMA" (Simple - mượt hơn)
                                # EMA phản ứng nhanh hơn với giá mới, phù hợp cho Gold volatile

MA_PERIODS = [20, 50, 200]     # Danh sách chu kỳ MA để tính toán [MA20, MA50, MA200]
                                # MA20: xu hướng ngắn hạn, MA50: trung hạn, MA200: dài hạn
                                # Uptrend: Giá > MA20 > MA50 > MA200
                                # Downtrend: Giá < MA20 < MA50 < MA200

# Bollinger Bands - Đo lường volatility, phát hiện giá cực trị
BB_PERIOD = 20                 # Chu kỳ tính Bollinger Bands (số nến)
BB_STD_DEV = 2.0               # Độ lệch chuẩn (Standard Deviation) để tính biên trên/dưới
                                # Giá trị chuẩn: 2.0 (95% giá nằm trong band)
                                # Giá chạm biên trên = overbought, biên dưới = oversold

# ATR (Average True Range) - Đo lường volatility để tính SL/TP
ATR_PERIOD = 14                # Chu kỳ tính ATR (số nến để tính trung bình true range)
                                # ATR cao = thị trường biến động mạnh → cần SL/TP xa hơn

# Stochastic Oscillator - Xác nhận tín hiệu overbought/oversold
STOCH_K_PERIOD = 14            # Chu kỳ tính đường %K (phản ứng nhanh)
STOCH_D_PERIOD = 3             # Chu kỳ tính đường %D (làm mượt của %K)
                                # Stochastic = (%K - low_min) / (high_max - low_min) × 100

STOCH_OVERSOLD = 20            # Ngưỡng Stochastic oversold → Xác nhận tín hiệu BUY
STOCH_OVERBOUGHT = 80          # Ngưỡng Stochastic overbought → Xác nhận tín hiệu SELL

# Logic quyết định tín hiệu - CÂN BẰNG GIỮA CHẤT LƯỢNG VÀ SỐ LƯỢNG
MIN_SIGNAL_STRENGTH = 3        # ⚠️ ĐIỀU CHỈNH: Số lượng chỉ báo tối thiểu phải đồng thuận để mở lệnh (GIẢM xuống 3)
                                # Ví dụ: 3 = cần ít nhất 3 chỉ báo cùng BUY mới mở lệnh BUY
                                # Giá trị 3 = cân bằng giữa chất lượng và số lượng tín hiệu ✅
                                # Giá trị cao hơn (4-5) = rất ít lệnh (có thể không có tín hiệu trong 2-3 giờ)
                                # Giá trị thấp hơn (1-2) = nhiều lệnh nhưng nhiều false signal ❌
                                # ⚠️ ĐẶT = 3 để có đủ tín hiệu nhưng vẫn giữ chất lượng (kết hợp với ADX và Volume filter)

REQUIRE_TREND_CONFIRMATION = True  # True: Yêu cầu xu hướng từ MA phải đồng thuận
                                    # Ví dụ: BUY signal chỉ được chấp nhận nếu Price > MA20 > MA50
                                    # Giảm false signal nhưng có thể bỏ lỡ cơ hội trong sideways

REQUIRE_MOMENTUM_CONFIRMATION = True  # True: Yêu cầu MACD momentum phải đồng thuận
                                       # MACD histogram phải tăng (bullish) cho BUY
                                       # Giúp xác nhận momentum trước khi vào lệnh

REQUIRE_BOTH_TREND_AND_MOMENTUM = False  # ⚠️ ĐIỀU CHỈNH: False = Chỉ cần 1 trong 2 (OR logic) để có nhiều tín hiệu hơn
                                          # True = CẦN CẢ trend VÀ momentum (AND logic) - quá strict
                                          # False = Nhiều cơ hội hơn, vẫn giữ chất lượng nhờ MIN_SIGNAL_STRENGTH=3
                                          # Kết hợp với ADX filter (28) và Volume filter để giữ chất lượng

USE_STOCH_CONFIRM = True       # Có sử dụng Stochastic để xác nhận tín hiệu không
                                # Stochastic giúp xác nhận RSI oversold/overbought

USE_BB_CONFIRM = True          # Có sử dụng Bollinger Bands để xác nhận không
                                # Giá chạm BB biên = signal mạnh

# ============================================
# Advanced Trend/Momentum Analysis - Phân tích Trend/Momentum nâng cao cho M15 Aggressive
# ============================================
USE_MA_SLOPE = True            # True: Kiểm tra slope (độ dốc) của MA - MA đang tăng hay giảm
                                # MA slope dương = trend đang tăng mạnh
                                # MA slope âm = trend đang giảm mạnh

MA_SLOPE_PERIODS = 5           # Số nến để tính slope của MA (5 nến = slope ngắn hạn)
                                # Slope = (MA hiện tại - MA 5 nến trước) / 5

MA_SLOPE_THRESHOLD = 0.001     # Ngưỡng tối thiểu của slope để coi là có trend (0.1% giá)
                                # Ví dụ: giá $2000, slope >= $2 = trend mạnh

USE_MACD_MAGNITUDE = True      # True: Kiểm tra magnitude (độ lớn) của MACD histogram
                                # MACD magnitude cao = momentum mạnh

MACD_MAGNITUDE_THRESHOLD = 0.3 # Ngưỡng tối thiểu MACD histogram để coi là momentum mạnh
                                # Giá trị tùy thuộc vào symbol (Gold thường nhỏ hơn BTC)

USE_MACD_PERSISTENCE = True    # True: Kiểm tra persistence (tính bền vững) của MACD
                                # MACD histogram tăng/giảm liên tục trong N nến = momentum bền vững

MACD_PERSISTENCE_PERIODS = 3   # Số nến liên tục MACD phải cùng chiều để coi là persistent

ALLOW_ADX_OVERRIDE = True      # True: Cho phép override ADX filter khi momentum rất mạnh
                                # ADX thấp nhưng MACD magnitude cao + persistent = cho phép trade

ADX_OVERRIDE_MACD_MAGNITUDE = 2.0  # MACD magnitude tối thiểu để override ADX (2x threshold)
                                    # Chỉ override khi momentum RẤT mạnh

ALLOW_COUNTER_TREND = True      # True: Cho phép counter-trend trade (ngược trend chính)
                                # Counter-trend: Trend down nhưng momentum up mạnh → BUY
                                # Chỉ cho phép khi có volume + BB proximity

COUNTER_TREND_MIN_VOLUME = 1.5  # Volume ratio tối thiểu để cho phép counter-trend (1.5x MA)
                                 # Counter-trend cần volume cao để xác nhận

COUNTER_TREND_BB_PROXIMITY = 0.02  # Giá phải gần BB band (2% BB) để cho phép counter-trend
                                    # Ví dụ: Counter-trend BUY khi giá gần BB lower (oversold)

COUNTER_TREND_MIN_SIGNALS = 3   # Số signals tối thiểu để cho phép counter-trend (3 signals)
                                 # Cần nhiều signals hơn để justify counter-trend risk

# ============================================
# Fibonacci Retracement Settings
# ============================================
USE_FIBONACCI = True           # Có sử dụng Fibonacci Retracement không
                                # Fibonacci giúp xác định vùng hỗ trợ/kháng cự mạnh

FIBONACCI_LOOKBACK = 100       # Số nến để tìm swing high/low cho Fibonacci (100 nến)
                                # Tìm đỉnh/cao nhất và đáy/thấp nhất trong khoảng này

FIBONACCI_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786]  # Các mức Fibonacci quan trọng
                                # 0.236, 0.382 = retracement nhẹ
                                # 0.5 = mức giữa (50%)
                                # 0.618 = Golden Ratio (quan trọng nhất)
                                # 0.786 = retracement sâu

FIBONACCI_TOLERANCE = 0.02     # Độ dung sai khi xác định giá có chạm Fibonacci (2%)
                                # Ví dụ: Giá cách Fibonacci 0.618 là 2% = coi như chạm

# ============================================
# Volume Analysis Settings
# ============================================
USE_VOLUME_ANALYSIS = True     # Có phân tích khối lượng giao dịch không
                                # Volume cao = xác nhận tín hiệu mạnh, Volume thấp = tín hiệu yếu

VOLUME_MA_PERIOD = 20          # Chu kỳ MA để so sánh volume (20 nến)
                                # Volume hiện tại > MA(volume) = volume cao (khối lượng tăng)

VOLUME_HIGH_THRESHOLD = 1.3    # ⚠️ ĐIỀU CHỈNH: Hệ số để xác định volume cao (GIẢM xuống 1.3)
                                # Volume / MA(volume) > 1.3 = volume cao (yêu cầu volume trên mức trung bình 30%)
                                # Điều chỉnh để có nhiều tín hiệu hơn nhưng vẫn xác nhận được signal
                                # Kết hợp với MIN_SIGNAL_STRENGTH=3 để giữ chất lượng

VOLUME_LOW_THRESHOLD = 0.5     # Hệ số để xác định volume thấp (0.5 = thấp hơn MA 50%)
                                # Volume / MA(volume) < 0.5 = volume thấp

REQUIRE_VOLUME_CONFIRMATION = True  # ⚠️ BẮT BUỘC: True = Yêu cầu volume cao để xác nhận tín hiệu
                                     # False: Không yêu cầu volume (có thể trade volume thấp) ❌ KHÔNG KHUYẾN NGHỊ
                                     # Volume thấp thường đi kèm với false signals → Tăng tỷ lệ thua
                                     # ⚠️ GIỮ = True để giảm tỷ lệ thua

# ============================================
# Support & Resistance Settings
# ============================================
USE_SUPPORT_RESISTANCE = True  # Có sử dụng vùng hỗ trợ/kháng cự không
                                # Khi giá không theo Fibonacci, dùng S/R zones

SR_LOOKBACK = 200              # Số nến để tìm support/resistance (200 nến)
                                # Càng nhiều = tìm được nhiều vùng S/R hơn

SR_ZONES_COUNT = 5             # Số lượng vùng S/R tối đa để tìm (5 vùng)
                                # Chọn 5 vùng mạnh nhất (có nhiều lần chạm nhất)

SR_TOUCH_MIN = 2               # Số lần tối thiểu giá phải chạm để coi là S/R zone (2 lần)
                                # Vùng chạm ít nhất 2 lần = vùng S/R đáng tin

SR_TOLERANCE = 0.01            # Độ dung sai khi xác định giá có trong vùng S/R (1%)
                                # Giá cách vùng S/R < 1% = coi như ở trong vùng

USE_SR_WHEN_NO_FIB = True      # Chỉ dùng S/R khi không có tín hiệu Fibonacci
                                # True: Ưu tiên Fibonacci, fallback sang S/R
                                # False: Luôn dùng cả Fibonacci và S/R

# ============================================
# ADX Settings - Filter Sideways Market
# ============================================
USE_ADX_FILTER = True          # ⚠️ MỚI: Sử dụng ADX để lọc sideways market
                                # ADX (Average Directional Index) đo lường strength của trend
                                # ADX < 28 = Sideways/trend yếu (không có trend rõ ràng) → KHÔNG TRADE
                                # ADX >= 28 = Có trend mạnh → CHO PHÉP TRADE
                                # ⚠️ QUAN TRỌNG: Lọc sideways market nhưng không quá strict (ngưỡng 28)

ADX_PERIOD = 14                # Chu kỳ tính ADX (14 là chuẩn)

ADX_MIN_THRESHOLD = 28         # ⚠️ ĐIỀU CHỈNH: Ngưỡng ADX tối thiểu để cho phép trade (GIẢM xuống 28)
                                # ADX >= 28 = Trend mạnh, cho phép trade
                                # ADX < 28 = Sideways/trend yếu, chặn trade (giảm false signals)
                                # ⚠️ ĐẶT = 28 để cân bằng: vẫn lọc sideways nhưng không quá strict
                                # Kết hợp với MIN_SIGNAL_STRENGTH=3 và Volume filter để giữ chất lượng

ADX_STRONG_TREND = 40          # ADX >= 40 = Trend rất mạnh (ưu tiên cao hơn)
                                # Có thể điều chỉnh logic để ưu tiên khi ADX rất cao

# ============================================
# Trading Rules
# ============================================
# Cài đặt chu kỳ kiểm tra và số lượng dữ liệu lịch sử
INTERVAL_SECONDS = 30          # Thời gian chờ giữa các lần kiểm tra tín hiệu (giây)
                                # 30s = kiểm tra mỗi 30 giây (nhiều tín hiệu hơn)
                                # 60s = kiểm tra mỗi 1 phút (cân bằng)
                                # 300s = kiểm tra mỗi 5 phút (ít tín hiệu, tiết kiệm tài nguyên)
                                # Với M15 timeframe, 30-60s là hợp lý

HISTORICAL_BARS = 500          # Số lượng nến lịch sử để phân tích
                                # Càng nhiều = tính chỉ báo chính xác hơn nhưng chậm hơn
                                # 500 nến M15 = ~5 ngày dữ liệu
                                # Khuyến nghị: 200-500 cho M15, 1000+ cho H1/H4

# ============================================
# Magic Number & Comments
# ============================================
# Magic Number: Mã định danh để phân biệt lệnh của bot với lệnh thủ công
MAGIC_NUMBER = 888885          # Số nguyên, mỗi bot nên có magic number riêng
                                # Bot chỉ quản lý lệnh có magic number này
                                # Không trùng với magic number bot khác hoặc EA khác
                                # BTC: 888883, ETH: 888884, GOLD: 888885

BUY_COMMENT = "Gold Trader Buy v3"   # Comment hiển thị trong MT5 khi mở lệnh BUY
                                      # Giúp nhận biết lệnh từ bot khi xem trong MT5

SELL_COMMENT = "Gold Trader Sell v3" # Comment hiển thị trong MT5 khi mở lệnh SELL

# ============================================
# Logging Settings
# ============================================
# Cài đặt logging để theo dõi hoạt động bot
LOG_LEVEL = "INFO"             # Mức độ log: "DEBUG" (chi tiết nhất), "INFO" (bình thường), 
                                # "WARNING" (cảnh báo), "ERROR" (chỉ lỗi)
                                # DEBUG: Ghi mọi thứ, dùng khi debug lỗi
                                # INFO: Ghi hoạt động bình thường (khuyến nghị)

LOG_FILE = "logs/gold_trader.log"      # File log text (ghi mọi hoạt động, phân tích, lỗi)
                                        # Xem bằng: tail -f logs/gold_trader.log

CSV_LOG_FILE = "logs/trades_gold.csv"   # File log CSV (chỉ ghi lệnh đã mở/đóng)
                                        # Dùng để phân tích performance, backtest
                                        # Cột: Time, Type, Symbol, Volume, Price, SL, TP, Ticket, Equity, Balance, Profit

# ============================================
# Advanced Settings
# ============================================
# Cài đặt nâng cao cho việc đặt lệnh
DEVIATION = 100                # Độ lệch giá cho phép khi đặt lệnh (points)
                                # Khi giá thay đổi nhanh, MT5 cho phép trượt giá trong phạm vi này
                                # Với Gold dao động mạnh: 100-200 points (cho phép trượt nhiều hơn)
                                # Với forex: 10-20 points là đủ

ORDER_FILLING = "IOC"          # Loại điền lệnh: "IOC" (Immediate or Cancel - khớp ngay hoặc hủy)
                                # Hoặc "FOK" (Fill or Kill - khớp toàn bộ hoặc hủy)
                                # IOC: Khớp được bao nhiêu thì khớp, phần còn lại hủy
                                # Khuyến nghị: IOC cho market order

ORDER_TIME = "GTC"             # Thời gian hiệu lực lệnh: "GTC" (Good Till Cancel - đến khi hủy)
                                # Hoặc "DAY" (chỉ hiệu lực trong ngày)
                                # GTC: Lệnh tồn tại cho đến khi đóng thủ công hoặc đạt SL/TP

# ============================================
# Telegram Notification Settings
# ============================================
USE_TELEGRAM_NOTIFICATIONS = True  # True: Gửi thông báo Telegram khi mở/đóng lệnh
                                    # False: Tắt thông báo Telegram

TELEGRAM_BOT_TOKEN = "6398751744:AAGp7VH7B00_kzMqdaFB59xlqAXnlKTar-g"         # Token của Telegram Bot (lấy từ @BotFather)
                                # Ví dụ: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
                                # Hướng dẫn: https://core.telegram.org/bots/tutorial

TELEGRAM_CHAT_ID = "1887610382"           # Chat ID để nhận thông báo (có thể là user ID hoặc group ID)
                                # Lấy chat ID: Gửi message cho bot @userinfobot hoặc thêm bot vào group
                                # Ví dụ: "123456789" (user) hoặc "-1001234567890" (group)

# Format thông báo Telegram
TELEGRAM_SEND_ON_ORDER_OPEN = True      # Gửi thông báo khi mở lệnh
TELEGRAM_SEND_ON_ORDER_CLOSE = True    # Gửi thông báo khi đóng lệnh (có thể bật sau)

# ============================================
# Helper: Convert timeframe string sang MT5 constant
# ============================================
def get_timeframe_mt5():
    """
    Convert timeframe string (ví dụ: "M15") sang MT5 constant (mt5.TIMEFRAME_M15)
    
    Returns:
        MT5 timeframe constant (ví dụ: mt5.TIMEFRAME_M15)
        Nếu không tìm thấy, trả về mt5.TIMEFRAME_M5 (mặc định)
    
    Usage:
        timeframe = get_timeframe_mt5()  # Dùng trong mt5.copy_rates_from_pos()
    """
    import MetaTrader5 as mt5
    
    timeframe_str = TIMEFRAME.upper()  # Chuyển "m15" → "M15"
    mapping = {
        "M1": mt5.TIMEFRAME_M1,      # 1 phút
        "M5": mt5.TIMEFRAME_M5,      # 5 phút
        "M15": mt5.TIMEFRAME_M15,    # 15 phút
        "M30": mt5.TIMEFRAME_M30,    # 30 phút
        "H1": mt5.TIMEFRAME_H1,      # 1 giờ
        "H4": mt5.TIMEFRAME_H4,      # 4 giờ
        "D1": mt5.TIMEFRAME_D1,      # 1 ngày
    }
    return mapping.get(timeframe_str, mt5.TIMEFRAME_M5)  # Mặc định M5 nếu không tìm thấy

