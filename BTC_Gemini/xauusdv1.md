# 📋 TỔNG HỢP TẤT CẢ RULE - BOT XAUUSD V1

**File:** `bot_xauusd.py`  
**Version:** 1.0  
**Cập nhật:** 2025-11-04

---

## 📌 1. CẤU HÌNH CƠ BẢN

### Symbol & Timeframe
- **Symbol:** `XAUUSD` (Vàng/USD)
- **Timeframe:** `M15` (15 phút)
- **Check Interval:** `30 giây` (Bot kiểm tra tín hiệu mỗi 30 giây)

---

## 💰 2. QUẢN LÝ RỦI RO (Risk Management)

### 2.1 Rủi ro mỗi lệnh
- **RISK_PER_TRADE:** `0.5%` của balance
- **Ví dụ:** Balance $1000 → Risk $5 mỗi lệnh

### 2.2 Điều kiện tài khoản
- **SAFE_EQUITY_RATIO:** `0.92` (92%)
  - Nếu `Equity < Balance × 0.92` → Bot không mở lệnh mới
- **MIN_FREE_MARGIN:** `$50 USD`
  - Nếu `Free Margin < $50` → Bot không mở lệnh mới

### 2.3 Giới hạn số lệnh
- **MAX_POSITIONS:** `2` lệnh cùng lúc
- **MAX_DAILY_TRADES:** `10` lệnh/ngày
- **MAX_HOURLY_TRADES:** `20` lệnh/giờ

### 2.4 Lot size
- **MIN_LOT_SIZE:** `0.01` lots
- **MAX_LOT_SIZE:** `1.0` lots
- **Lot size tự động tính:** Dựa trên `RISK_PER_TRADE` và `SL pips`

---

## 🛑 3. STOP LOSS & TAKE PROFIT

### 3.1 Giới hạn SL/TP
- **MIN_SL_PIPS:** `250 pips` (tối thiểu)
- **MIN_TP_PIPS:** `200 pips` (tối thiểu)
- **MIN_RR_RATIO:** `1.5` (Risk:Reward = 1:1.5)
- **MAX_SL_USD:** `$10 USD` (giới hạn tối đa theo USD)

### 3.2 SL/TP động theo ATR
- **USE_ATR_BASED_SL_TP:** `True` (Bật)
- **ATR_SL_TP_MODE:** `ATR_BOUNDED` (Hoặc `ATR_FREE`)
  
#### Mode ATR_BOUNDED:
- **ATR_MIN_SL_USD:** `$5 USD` (SL tối thiểu)
- **ATR_MAX_SL_USD:** `$10 USD` (SL tối đa)
- Bot sẽ điều chỉnh `sl_pips` hoặc `lot_size` để đảm bảo SL nằm trong khoảng $5-$10
- **Ưu tiên MIN USD** hơn MIN_SL_PIPS khi không thể tăng lot_size

#### Mode ATR_FREE:
- SL/TP tự do theo ATR, không giới hạn theo USD (chỉ đảm bảo SL >= MIN_SL_PIPS)
- Điều chỉnh mềm nếu SL USD > 2×MAX_SL_USD (giảm lot_size)

### 3.3 Hệ số nhân ATR
- **ATR_MULTIPLIER_SL:** `2.5` (SL = ATR × 2.5)
- **ATR_MULTIPLIER_TP:** `3.5` (TP = ATR × 3.5)
- **ATR_PERIOD:** `14` chu kỳ
- **ATR_TIMEFRAME:** `M15`

### 3.4 TP Boost (Tăng TP khi trend mạnh)
- **ENABLE_TP_BOOST:** `True`
- **STRONG_TREND_TP_BOOST:** `+30%` TP khi trend mạnh
- **RSI_TREND_THRESHOLD_UP:** `65` (RSI > 65 = uptrend mạnh)
- **RSI_TREND_THRESHOLD_DOWN:** `35` (RSI < 35 = downtrend mạnh)

---

## 📊 4. PHÂN TÍCH KỸ THUẬT (Technical Analysis)

### 4.1 Chỉ báo sử dụng
- **RSI (14):** Relative Strength Index
- **EMA20 & EMA50:** Exponential Moving Average
- **MACD:** Moving Average Convergence Divergence
- **Bollinger Bands:** BB Upper, Middle, Lower
- **ATR (14):** Average True Range

### 4.2 Điều kiện tín hiệu
- **MIN_SIGNAL_STRENGTH:** `2 điểm` (tối thiểu)
- **Dữ liệu tối thiểu:** `50 nến` để tính toán chính xác

### 4.3 Hệ thống điểm tín hiệu

#### Tín hiệu BUY (Mua):
| Chỉ báo | Điều kiện | Điểm |
|---------|-----------|------|
| **RSI** | Cắt từ trên xuống dưới 30 (Quá bán) | **+2 điểm** |
| **RSI** | Đang ở vùng quá bán (< 35) | **+1 điểm** |
| **EMA** | EMA20 cắt EMA50 từ dưới lên (Uptrend mới) | **+1 điểm** |
| **EMA** | EMA20 đang trên EMA50 (Uptrend) | **+1 điểm** |
| **MACD** | MACD cắt Signal từ dưới lên (Momentum tăng) | **+1 điểm** |
| **MACD** | MACD đang trên Signal (Momentum tăng) | **+1 điểm** |
| **BB** | Giá chạm/ở dưới BB Lower (Quá bán) | **+1 điểm** |

#### Tín hiệu SELL (Bán):
| Chỉ báo | Điều kiện | Điểm |
|---------|-----------|------|
| **RSI** | Cắt từ dưới lên trên 70 (Quá mua) | **+2 điểm** |
| **RSI** | Đang ở vùng quá mua (> 65) | **+1 điểm** |
| **EMA** | EMA20 cắt EMA50 từ trên xuống (Downtrend mới) | **+1 điểm** |
| **EMA** | EMA20 đang dưới EMA50 (Downtrend) | **+1 điểm** |
| **MACD** | MACD cắt Signal từ trên xuống (Momentum giảm) | **+1 điểm** |
| **MACD** | MACD đang dưới Signal (Momentum giảm) | **+1 điểm** |
| **BB** | Giá chạm/ở trên BB Upper (Quá mua) | **+1 điểm** |

### 4.4 Quyết định lệnh
- **BUY:** Khi `buy_signals >= MIN_SIGNAL_STRENGTH (2)` và `buy_signals > sell_signals`
- **SELL:** Khi `sell_signals >= MIN_SIGNAL_STRENGTH (2)` và `sell_signals > buy_signals`
- **HOLD:** Khi không đủ tín hiệu hoặc mâu thuẫn

---

## ⏰ 5. THỜI GIAN GIAO DỊCH

### 5.1 Timezone
- **TRADING_TIMEZONE:** `US/Eastern` (New York time)
- Bot tự động xử lý EST/EDT (Daylight Saving Time)

### 5.2 Session cấm giao dịch
- **NO_TRADE_SESSIONS:**
  - `08:00 - 10:00` (US/Eastern): NY Open
  - ~~14:30 - 15:30~~ (Đã tắt)
  - ~~00:00 - 01:00~~ (Đã tắt)

### 5.3 Thứ 6 (Friday)
- **NO_TRADE_FRIDAY_AFTER:** `17:00` (5:00 PM US/Eastern)
- Bot dừng giao dịch sau 17:00 thứ 6 để tránh rủi ro cuối tuần

### 5.4 Thời gian nghỉ sau thua
- **BREAK_AFTER_LOSS_MINUTES:** `30 phút`
- Sau khi thua 1 lệnh, bot đợi 30 phút trước khi tìm tín hiệu mới

### 5.5 Thời gian giữa các lệnh
- **MIN_TIME_BETWEEN_SAME_DIRECTION:** `10 phút`
- Bot không mở lệnh BUY nếu đã có lệnh BUY trong vòng 10 phút (tương tự với SELL)
- **Lấy thời gian từ MT5:** Bot kiểm tra thời gian mở lệnh thực tế trên MT5 (không phụ thuộc vào bot restart)

---

## 📈 6. TRAILING STOP THÔNG MINH

### 6.1 Cấu hình
- **ENABLE_TRAILING_STOP:** `True` (Bật)
- **TRAIL_START_PIPS:** `150 pips` (Kích hoạt khi profit ≥ 150 pips)
- **TRAIL_DISTANCE_PIPS:** `100 pips` (SL cách giá hiện tại 100 pips)
- **TRAIL_HARD_LOCK_PIPS:** `250 pips` (Chốt cứng khi profit > 250 pips)

### 6.2 Logic hoạt động
1. **Kích hoạt:** Khi `profit_pips >= TRAIL_START_PIPS (150)`
2. **Trailing:** SL di chuyển theo giá, luôn cách giá hiện tại `TRAIL_DISTANCE_PIPS (100) pips`
3. **Hard Lock:** Khi `profit_pips > TRAIL_HARD_LOCK_PIPS (250)`
   - BUY: Đảm bảo SL không thấp hơn entry + (profit - 250) pips
   - SELL: Đảm bảo SL không cao hơn entry - (profit - 250) pips
4. **Breakeven:** SL không được thấp hơn entry (BUY) hoặc cao hơn entry (SELL)

---

## 🧠 7. SMART EXIT (Thoát lệnh thông minh)

### 7.1 Cấu hình
- **ENABLE_SMART_EXIT:** `True` (Bật)
- **OPPOSITE_SIGNAL_COUNT_TO_EXIT:** `2` tín hiệu ngược chiều
- **ENABLE_RSI_EXIT:** `True`
- **RSI_EXIT_THRESHOLD:** `50`
- **ENABLE_PROFIT_DRAWDOWN_EXIT:** `True`
- **PROFIT_DRAWDOWN_EXIT_PERCENT:** `40%`

### 7.2 Điều kiện thoát lệnh

#### 1. Tín hiệu ngược chiều
- Đếm số tín hiệu ngược chiều liên tiếp
- Nếu có `≥ 2` tín hiệu ngược chiều → Đóng lệnh sớm
- Reset counter khi tín hiệu cùng chiều

#### 2. RSI quay đầu
- **BUY:** Nếu `RSI < 50` (Momentum giảm) → Đóng lệnh
- **SELL:** Nếu `RSI > 50` (Momentum giảm) → Đóng lệnh
- Chỉ áp dụng khi đang lời (`profit_pips > 0`)

#### 3. Profit Drawdown
- Theo dõi đỉnh profit của mỗi lệnh
- Nếu lợi nhuận giảm `> 40%` so với đỉnh → Đóng lệnh bảo toàn

---

## 🛡️ 8. BẢO VỆ TÀI KHOẢN

### 8.1 Giới hạn lỗ
- **MAX_CONSECUTIVE_LOSSES:** `3` lệnh thua liên tiếp
  - Nếu thua 3 lệnh liên tiếp → Bot tạm dừng giao dịch
- **MAX_DRAWDOWN_PERCENT:** `8%`
  - Nếu `Drawdown > 8%` → Bot không mở lệnh mới
- **MAX_DAILY_LOSS_PERCENT:** `4%` của balance
  - Nếu tổng lỗ trong ngày > 4% balance → Bot dừng
- **MAX_LOSS_PER_TRADE:** `2%` của balance
  - Nếu 1 lệnh thua > 2% balance → Cần kiểm tra lại

### 8.2 Điều kiện tài khoản
- **Equity Ratio:** `Equity >= Balance × 0.92`
- **Free Margin:** `Free Margin >= $50 USD`
- **Drawdown:** `Drawdown <= 8%`

---

## ✅ 9. QUY TRÌNH KIỂM TRA TRƯỚC KHI MỞ LỆNH

### 9.1 Kiểm tra điều kiện thị trường
1. ✅ **Spread:** `Spread <= MAX_SPREAD (50 pips)`
2. ✅ **Thời gian giao dịch:** Không trong session cấm, không phải thứ 6 sau 17:00
3. ✅ **Điều kiện tài khoản:** Equity, Free Margin đủ

### 9.2 Kiểm tra giới hạn số lệnh
1. ✅ **Số vị thế:** `Current Positions < MAX_POSITIONS (2)`
2. ✅ **Lệnh trong ngày:** `Daily Trades < MAX_DAILY_TRADES (10)`
3. ✅ **Lệnh trong giờ:** `Hourly Trades < MAX_HOURLY_TRADES (20)`

### 9.3 Kiểm tra thời gian
1. ✅ **Nghỉ sau thua:** Đã đợi `≥ BREAK_AFTER_LOSS_MINUTES (30 phút)` sau lệnh thua cuối
2. ✅ **Thời gian cùng chiều:** Đã đợi `≥ MIN_TIME_BETWEEN_SAME_DIRECTION (10 phút)` kể từ lệnh cùng chiều cuối
   - Lấy thời gian thực tế từ MT5 (không phụ thuộc bot restart)

### 9.4 Kiểm tra bảo vệ
1. ✅ **Consecutive Losses:** `Consecutive Losses < MAX_CONSECUTIVE_LOSSES (3)`
2. ✅ **Drawdown:** `Drawdown <= MAX_DRAWDOWN_PERCENT (8%)`
3. ✅ **Daily Loss:** `Daily Loss <= MAX_DAILY_LOSS_PERCENT (4%)`

### 9.5 Kiểm tra tín hiệu kỹ thuật
1. ✅ **Signal Strength:** `Buy/Sell Signals >= MIN_SIGNAL_STRENGTH (2)`
2. ✅ **Signal Direction:** `Buy Signals > Sell Signals` (BUY) hoặc `Sell Signals > Buy Signals` (SELL)

### 9.6 Tính toán SL/TP
1. ✅ **Tính SL/TP:** Dựa trên ATR và ATR_MULTIPLIER
2. ✅ **Validate SL/TP:** 
   - `SL >= MIN_SL_PIPS (250)`
   - `TP >= MIN_TP_PIPS (200)`
   - `RR Ratio >= MIN_RR_RATIO (1.5)`
3. ✅ **ATR_BOUNDED Mode:** Điều chỉnh để `$5 <= SL USD <= $10`
4. ✅ **TP Boost:** Tăng TP thêm 30% nếu trend mạnh (RSI > 65 hoặc < 35)

### 9.7 Tính toán Lot Size
1. ✅ **Tính lot size:** Dựa trên `RISK_PER_TRADE (0.5%)` và `SL pips`
2. ✅ **Validate lot size:**
   - `MIN_LOT_SIZE (0.01) <= Lot Size <= MAX_LOT_SIZE (1.0)`
   - Làm tròn theo `lot_step` của broker
3. ✅ **ATR_BOUNDED Mode:** Điều chỉnh lot_size nếu cần để đạt SL USD trong khoảng $5-$10

### 9.8 Gửi lệnh
1. ✅ **Filling Mode:** Thử theo thứ tự: IOC → FOK → RETURN → AUTO
2. ✅ **Validate Request:** Kiểm tra `order_check()` trước khi `order_send()`
3. ✅ **Retry:** Nếu lỗi filling mode, thử mode tiếp theo

---

## 📝 10. LOGIC SAU KHI MỞ LỆNH

### 10.1 Quản lý lệnh đang mở
- **Trailing Stop:** Tự động kích hoạt khi profit ≥ 150 pips
- **Smart Exit:** Kiểm tra mỗi cycle để đóng lệnh sớm nếu cần
- **Telegram Notification:** Gửi thông báo khi mở lệnh thành công/thất bại

### 10.2 Ghi nhận kết quả
- **Record Trade:** Lưu kết quả (thành công/thất bại) vào `risk_manager`
- **Update Stats:** Cập nhật `daily_stats`, `consecutive_losses`, `trade_history`

---

## 🔄 11. VÒNG LẶP CHÍNH (Main Loop)

### 11.1 Chu kỳ kiểm tra
1. **Lấy dữ liệu:** `get_price_data(100)` - 100 nến
2. **Phân tích kỹ thuật:** `technical_analyzer.analyze(df)`
3. **Kiểm tra điều kiện:** `risk_manager.can_open_trade()`
4. **Thực hiện giao dịch:** `execute_trade()` nếu có tín hiệu
5. **Quản lý lệnh:** `_manage_trailing_stops()`, `_manage_smart_exit()`
6. **Chờ:** `time.sleep(CHECK_INTERVAL)` = 30 giây

### 11.2 Logging
- **Cycle Summary:** Log mỗi 10 cycles hoặc khi có thay đổi quan trọng
- **Account Info:** Log khi equity thay đổi > 1% hoặc positions thay đổi
- **Price:** Log khi giá thay đổi > 0.1%
- **Technical Analysis:** Log ở mức DEBUG để giảm verbosity

---

## 📱 12. TELEGRAM NOTIFICATIONS

### 12.1 Cấu hình
- **USE_TELEGRAM:** `True`
- **TELEGRAM_BOT_TOKEN:** (Đã cấu hình)
- **TELEGRAM_CHAT_ID:** (Đã cấu hình)

### 12.2 Khi nào gửi
- ✅ **Lệnh thành công:** Gửi thông báo khi mở lệnh thành công (BUY/SELL)
- ✅ **Lệnh thất bại:** Gửi thông báo khi mở lệnh thất bại (lỗi)
- ❌ **Không gửi:** Khi bot khởi động, khi có tín hiệu (chưa mở lệnh), khi bot dừng

### 12.3 Anti-spam
- **Signal Cooldown:** 300 giây (5 phút) giữa các lần gửi tín hiệu giống nhau
- **Reset:** Reset khi mở lệnh thành công

---

## ⚙️ 13. XỬ LÝ LỖI & RETRY

### 13.1 Filling Mode
- **Auto-detect:** Bot tự động detect filling mode được hỗ trợ (IOC, FOK, RETURN)
- **Retry:** Thử các filling mode theo thứ tự nếu lỗi
- **Fallback:** Dùng `ORDER_FILLING_RETURN` nếu không detect được

### 13.2 Lot Size Validation
- **Broker Constraints:** Validate theo `volume_min`, `volume_max`, `volume_step` của broker
- **Rounding:** Làm tròn theo `lot_step` và đảm bảo trong khoảng hợp lệ
- **Error Handling:** Trả về `None` nếu lot_size không hợp lệ (không gửi lệnh)

### 13.3 Unicode Encoding
- **Safe Stream Handler:** Xử lý lỗi encoding trên Windows
- **UTF-8:** Cấu hình console encoding UTF-8 với `errors='replace'`

---

## 📊 14. TÓM TẮT CÁC GIÁ TRỊ MẶC ĐỊNH

| Tham số | Giá trị | Mô tả |
|---------|---------|-------|
| **RISK_PER_TRADE** | 0.5% | Rủi ro mỗi lệnh |
| **MAX_POSITIONS** | 2 | Số lệnh cùng lúc |
| **MAX_DAILY_TRADES** | 10 | Lệnh/ngày |
| **MAX_HOURLY_TRADES** | 20 | Lệnh/giờ |
| **MIN_SL_PIPS** | 250 | SL tối thiểu |
| **MIN_TP_PIPS** | 200 | TP tối thiểu |
| **MIN_SIGNAL_STRENGTH** | 2 | Tín hiệu tối thiểu |
| **MIN_TIME_BETWEEN_SAME_DIRECTION** | 10 phút | Thời gian giữa lệnh cùng chiều |
| **BREAK_AFTER_LOSS_MINUTES** | 30 phút | Nghỉ sau thua |
| **CHECK_INTERVAL** | 30 giây | Thời gian kiểm tra |
| **MAX_SPREAD** | 50 pips | Spread tối đa |
| **ATR_MIN_SL_USD** | $5 | SL tối thiểu (ATR_BOUNDED) |
| **ATR_MAX_SL_USD** | $10 | SL tối đa (ATR_BOUNDED) |
| **TRAIL_START_PIPS** | 150 | Kích hoạt trailing stop |
| **TRAIL_DISTANCE_PIPS** | 100 | Khoảng cách trailing |
| **MAX_CONSECUTIVE_LOSSES** | 3 | Lệnh thua liên tiếp tối đa |
| **MAX_DRAWDOWN_PERCENT** | 8% | Drawdown tối đa |

---

## 🔍 15. LƯU Ý QUAN TRỌNG

1. **Thời gian cùng chiều:** Bot lấy thời gian thực tế từ MT5, không phụ thuộc vào bot restart
2. **ATR_BOUNDED Mode:** Ưu tiên MIN USD ($5) hơn MIN_SL_PIPS (250) khi không thể tăng lot_size
3. **Signal Strength:** RSI có trọng số x2 (2 điểm), các chỉ báo khác x1 (1 điểm)
4. **Telegram:** Chỉ gửi khi có kết quả lệnh (thành công/thất bại), không gửi khi có tín hiệu
5. **Timezone:** Bot tự động chuyển đổi sang US/Eastern time để so sánh thời gian
6. **Lot Size:** Bot tự động điều chỉnh để đảm bảo SL USD trong khoảng $5-$10 (ATR_BOUNDED mode)

---

**📌 Lưu ý:** Tất cả các rule này được implement trong `bot_xauusd.py`, `risk_manager.py`, `technical_analyzer.py`, và `config_xauusd.py`.  
**📝 Cập nhật:** File này được tạo tự động từ code hiện tại. Nếu có thay đổi rule, cần cập nhật lại file này.

