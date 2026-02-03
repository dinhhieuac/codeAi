# 📊 Phân Tích Kỹ Thuật Trade BTC - Tài Liệu Kỹ Thuật

Tài liệu này mô tả chi tiết các kỹ thuật phân tích kỹ thuật được sử dụng trong bot auto trading BTC/USD.

---

## 📑 Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Chỉ báo kỹ thuật cơ bản](#2-chỉ-báo-kỹ-thuật-cơ-bản)
3. [Fibonacci Retracement](#3-fibonacci-retracement)
4. [Phân tích khối lượng (Volume Analysis)](#4-phân-tích-khối-lượng-volume-analysis)
5. [Vùng hỗ trợ và kháng cự (Support/Resistance)](#5-vùng-hỗ-trợ-và-kháng-cự-supportresistance)
6. [Logic quyết định tín hiệu](#6-logic-quyết-định-tín-hiệu)
7. [Risk Management](#7-risk-management)
8. [Tổng hợp tín hiệu](#8-tổng-hợp-tín-hiệu)

---

## 1. Tổng quan hệ thống

### 1.1 Cấu hình cơ bản

- **Symbol**: BTCUSD (Bitcoin/USD)
- **Timeframe**: M15 (15 phút) - có thể điều chỉnh
- **Risk per trade**: 1% vốn mỗi lệnh
- **Max positions**: 3 lệnh cùng lúc
- **Max daily trades**: 300 lệnh/ngày

### 1.2 Các chỉ báo được sử dụng

Bot sử dụng **8 nhóm chỉ báo** để phân tích:

1. ✅ RSI (Relative Strength Index)
2. ✅ MACD (Moving Average Convergence Divergence)
3. ✅ Moving Averages (MA 20, 50, 200)
4. ✅ Bollinger Bands
5. ✅ Stochastic Oscillator
6. ✅ **Fibonacci Retracement** (MỚI)
7. ✅ **Volume Analysis** (MỚI)
8. ✅ **Support/Resistance Zones** (MỚI)

---

## 2. Chỉ báo kỹ thuật cơ bản

### 2.1 RSI (Relative Strength Index)

#### Mô tả
RSI đo lường momentum, phát hiện tình trạng quá mua (overbought) hoặc quá bán (oversold).

#### Cấu hình
- **Period**: 14 nến
- **Oversold**: < 30 → Tín hiệu **BUY**
- **Overbought**: > 70 → Tín hiệu **SELL**

#### Logic
- RSI < 30: Thị trường oversold, khả năng phục hồi tăng → **BUY signal**
- RSI > 70: Thị trường overbought, khả năng điều chỉnh giảm → **SELL signal**

#### Ưu điểm
- Phát hiện điểm đảo chiều tiềm năng
- Dễ hiểu và phổ biến

#### Hạn chế
- Trong trend mạnh, RSI có thể ở vùng cực đoan lâu (oversold/overbought kéo dài)
- Cần kết hợp với chỉ báo khác để xác nhận

---

### 2.2 MACD (Moving Average Convergence Divergence)

#### Mô tả
MACD phát hiện xu hướng và momentum bằng cách so sánh 2 EMA.

#### Cấu hình
- **Fast EMA**: 12
- **Slow EMA**: 26
- **Signal line**: 9

#### Logic
- **Bullish crossover**: MACD vượt lên Signal line → **BUY signal**
- **Bearish crossover**: MACD vượt xuống Signal line → **SELL signal**
- **MACD Histogram > 0**: Momentum tăng → Xác nhận uptrend
- **MACD Histogram < 0**: Momentum giảm → Xác nhận downtrend

#### Ưu điểm
- Phát hiện xu hướng và momentum tốt
- Tránh false signal trong sideways market

#### Hạn chế
- Có độ trễ (lagging indicator)
- Cần kết hợp với trend confirmation

---

### 2.3 Moving Averages (MA)

#### Mô tả
Trung bình động xác định xu hướng dài hạn.

#### Cấu hình
- **Loại MA**: EMA (Exponential Moving Average) - nhạy hơn SMA
- **Chu kỳ**: [20, 50, 200]
  - MA20: Xu hướng ngắn hạn
  - MA50: Xu hướng trung hạn
  - MA200: Xu hướng dài hạn

#### Logic

**Uptrend (Xu hướng tăng)**:
```
Giá > MA20 > MA50 > MA200
```
→ Tín hiệu **BUY** khi giá ở trên MA và các MA xếp theo thứ tự tăng

**Downtrend (Xu hướng giảm)**:
```
Giá < MA20 < MA50 < MA200
```
→ Tín hiệu **SELL** khi giá ở dưới MA và các MA xếp theo thứ tự giảm

#### Ưu điểm
- Xác định xu hướng rõ ràng
- EMA phản ứng nhanh hơn SMA, phù hợp với BTC volatile

#### Hạn chế
- Lagging indicator (chậm phản ứng với biến động giá mới)
- Trong sideways market có thể cho nhiều false signal

---

### 2.4 Bollinger Bands

#### Mô tả
Đo lường volatility, phát hiện giá ở vùng cực trị (overbought/oversold).

#### Cấu hình
- **Period**: 20 nến
- **Standard Deviation**: 2.0 (95% giá nằm trong band)

#### Logic
- **Giá chạm band dưới**: Oversold → **BUY signal**
- **Giá chạm band trên**: Overbought → **SELL signal**
- **Band mở rộng**: Volatility cao, thị trường biến động mạnh
- **Band thu hẹp**: Volatility thấp, có thể chuẩn bị breakout

#### Ưu điểm
- Phát hiện vùng giá cực trị tốt
- Phản ánh volatility của thị trường

#### Hạn chế
- Trong trend mạnh, giá có thể chạm band và tiếp tục trend (không revert)
- Cần xác nhận với chỉ báo khác

---

### 2.5 Stochastic Oscillator

#### Mô tả
Xác nhận tín hiệu overbought/oversold, bổ sung cho RSI.

#### Cấu hình
- **%K Period**: 14
- **%D Period**: 3
- **Oversold**: < 20 → **BUY signal**
- **Overbought**: > 80 → **SELL signal**

#### Logic
- **Stochastic oversold + %K > %D**: Tín hiệu **BUY** (giá có thể phục hồi)
- **Stochastic overbought + %K < %D**: Tín hiệu **SELL** (giá có thể điều chỉnh)

#### Ưu điểm
- Xác nhận tín hiệu từ RSI
- Phản ứng nhanh với biến động giá

#### Hạn chế
- Có thể cho nhiều false signal trong trend mạnh
- Cần kết hợp với trend confirmation

---

## 3. Fibonacci Retracement

### 3.1 Mô tả

Fibonacci Retracement xác định các mức hỗ trợ/kháng cự quan trọng dựa trên tỷ lệ Fibonacci (Golden Ratio).

### 3.2 Cấu hình

- **Lookback**: 100 nến (tìm swing high/low trong 100 nến gần nhất)
- **Fibonacci Levels**: [0.236, 0.382, 0.5, 0.618, 0.786]
  - **0.236, 0.382**: Retracement nhẹ
  - **0.5**: Mức giữa (50%)
  - **0.618**: **Golden Ratio** (quan trọng nhất)
  - **0.786**: Retracement sâu
- **Tolerance**: 2% (giá cách Fibonacci < 2% = coi như chạm)

### 3.3 Logic phân tích

#### Xác định Swing High/Low

1. **Tìm swing high**: Giá cao nhất trong khoảng lookback
2. **Tìm swing low**: Giá thấp nhất trong khoảng lookback
3. **Xác định xu hướng**:
   - **Uptrend**: Swing high mới hơn swing low
   - **Downtrend**: Swing low mới hơn swing high

#### Tính Fibonacci Levels

**Trong Uptrend**:
```
Swing Low = Base
Swing High - Swing Low = Diff

Fibonacci Levels = Base + (Diff × Fibonacci Ratio)
```
- 0.618 level = Swing Low + 0.618 × (Swing High - Swing Low)
- 0.786 level = Swing Low + 0.786 × (Swing High - Swing Low)

**Trong Downtrend**:
```
Swing High = Base
Swing High - Swing Low = Diff

Fibonacci Levels = Base - (Diff × Fibonacci Ratio)
```
- 0.618 level = Swing High - 0.618 × (Swing High - Swing Low)
- 0.786 level = Swing High - 0.786 × (Swing High - Swing Low)

### 3.4 Tín hiệu giao dịch

#### Trong Uptrend
- **Giá chạm Fibonacci 0.618 hoặc 0.786**: 
  - → Đây là vùng **hỗ trợ mạnh** trong uptrend
  - → Tín hiệu **BUY** (kỳ vọng giá bounce lên tiếp tục uptrend)

#### Trong Downtrend
- **Giá chạm Fibonacci 0.618 hoặc 0.786**:
  - → Đây là vùng **kháng cự mạnh** trong downtrend
  - → Tín hiệu **SELL** (kỳ vọng giá reject xuống tiếp tục downtrend)

### 3.5 Ưu điểm

- ✅ Xác định vùng hỗ trợ/kháng cự có độ chính xác cao
- ✅ Fibonacci 0.618 (Golden Ratio) là mức quan trọng nhất, được nhiều trader theo dõi
- ✅ Phù hợp với BTC vì giá thường respect các mức Fibonacci

### 3.6 Hạn chế

- ⚠️ Cần xác định swing high/low chính xác (có thể thay đổi khi có swing mới)
- ⚠️ Trong sideways market, Fibonacci có thể không hiệu quả
- ⚠️ Cần kết hợp với volume và các chỉ báo khác để xác nhận

---

## 4. Phân tích khối lượng (Volume Analysis)

### 4.1 Mô tả

Phân tích khối lượng giao dịch để xác nhận tính xác thực của tín hiệu.

### 4.2 Cấu hình

- **Volume MA Period**: 20 nến
- **Volume High Threshold**: 1.5 (volume cao hơn MA 50%)
- **Volume Low Threshold**: 0.5 (volume thấp hơn MA 50%)
- **Require Volume Confirmation**: True/False

### 4.3 Logic phân tích

#### Tính toán

1. **Volume hiện tại**: `tick_volume` hoặc `volume` từ nến mới nhất
2. **Volume MA**: Trung bình volume của 20 nến gần nhất
3. **Volume Ratio**: `Volume Ratio = Current Volume / Volume MA`

#### Phân loại Volume

- **HIGH**: `Volume Ratio >= 1.5` → Volume cao, tín hiệu mạnh
- **NORMAL**: `0.5 < Volume Ratio < 1.5` → Volume bình thường
- **LOW**: `Volume Ratio <= 0.5` → Volume thấp, tín hiệu yếu

### 4.4 Tín hiệu giao dịch

#### Khi REQUIRE_VOLUME_CONFIRMATION = True

- ✅ **Volume HIGH**: Xác nhận tín hiệu → **Cho phép trade**
- ❌ **Volume LOW**: Tín hiệu không được xác nhận → **Chặn trade** (có thể là false signal)

#### Khi REQUIRE_VOLUME_CONFIRMATION = False

- Chỉ log volume status, không chặn trade
- Volume LOW sẽ được cảnh báo trong log

### 4.5 Ưu điểm

- ✅ Xác nhận tính xác thực của tín hiệu
- ✅ Volume cao thường đi kèm với biến động giá mạnh (breakout/breakdown)
- ✅ Tránh false signal khi volume thấp

### 4.6 Hạn chế

- ⚠️ Tick volume (volume từ MT5) có thể không phản ánh chính xác real volume của thị trường
- ⚠️ Một số broker không cung cấp real volume cho crypto

---

## 5. Vùng hỗ trợ và kháng cự (Support/Resistance)

### 5.1 Mô tả

Xác định các vùng giá có nhiều lần chạm (cluster analysis) để tìm support/resistance zones.

### 5.2 Cấu hình

- **Lookback**: 200 nến (phân tích 200 nến gần nhất)
- **Zones Count**: 5 vùng (chọn 5 vùng mạnh nhất)
- **Touch Minimum**: 2 lần (vùng phải có ít nhất 2 lần chạm)
- **Tolerance**: 1% (giá cách vùng < 1% = coi như trong vùng)

### 5.3 Logic phân tích

#### Tìm Support Zones

1. Thu thập tất cả các **low** giá trong 200 nến
2. **Cluster analysis**: Nhóm các giá gần nhau (trong phạm vi tolerance)
3. Tính **trung bình** của mỗi cluster
4. Đếm **số lần chạm** (số giá trong cluster)
5. Chọn các vùng có **≥ 2 lần chạm** và **sắp xếp theo strength** (số lần chạm)
6. Lấy **5 vùng mạnh nhất** làm Support zones

#### Tìm Resistance Zones

- Tương tự như Support, nhưng thu thập từ các **high** giá

### 5.4 Tín hiệu giao dịch

#### Giá gần Support Zone

- **Giá cách Support < 1%**:
  - → Kỳ vọng giá **bounce lên** từ vùng hỗ trợ
  - → Tín hiệu **BUY**

#### Giá gần Resistance Zone

- **Giá cách Resistance < 1%**:
  - → Kỳ vọng giá **reject xuống** từ vùng kháng cự
  - → Tín hiệu **SELL**

### 5.5 Khi nào sử dụng

- **USE_SR_WHEN_NO_FIB = True**: 
  - ✅ Ưu tiên Fibonacci
  - ✅ Chỉ dùng S/R khi **KHÔNG có** tín hiệu Fibonacci
  
- **USE_SR_WHEN_NO_FIB = False**:
  - ✅ Luôn dùng cả Fibonacci và S/R
  - ✅ Kết hợp cả 2 để có nhiều tín hiệu hơn

### 5.6 Ưu điểm

- ✅ Xác định vùng cản chính xác dựa trên dữ liệu thực tế
- ✅ Vùng có nhiều lần chạm = vùng mạnh, đáng tin cậy
- ✅ Fallback tốt khi Fibonacci không có tín hiệu

### 5.7 Hạn chế

- ⚠️ Cần đủ dữ liệu lịch sử (200+ nến) để tìm được vùng S/R tốt
- ⚠️ Vùng S/R có thể bị phá vỡ trong trend mạnh
- ⚠️ Cluster analysis có thể tốn tài nguyên tính toán

---

## 6. Logic quyết định tín hiệu

### 6.1 Yêu cầu tối thiểu

- **MIN_SIGNAL_STRENGTH**: 2 chỉ báo đồng thuận
- Ví dụ: Cần ít nhất 2 trong số 8 chỉ báo cùng cho tín hiệu BUY

### 6.2 Xác nhận bổ sung

#### 1. Trend Confirmation (REQUIRE_TREND_CONFIRMATION)

- **BUY signal**: Cần `Price > MA20 > MA50` (uptrend)
- **SELL signal**: Cần `Price < MA20 < MA50` (downtrend)

#### 2. Momentum Confirmation (REQUIRE_MOMENTUM_CONFIRMATION)

- **BUY signal**: Cần `MACD Histogram > 0` và `MACD > Signal` (bullish momentum)
- **SELL signal**: Cần `MACD Histogram < 0` và `MACD < Signal` (bearish momentum)

#### 3. Volume Confirmation (REQUIRE_VOLUME_CONFIRMATION)

- **BUY/SELL signal**: Cần `Volume Ratio >= 1.5` (volume cao)

### 6.3 Điều kiện vào lệnh

**Tín hiệu được chấp nhận khi**:

1. ✅ Có **≥ MIN_SIGNAL_STRENGTH** chỉ báo đồng thuận (mặc định: 2)
2. ✅ Có **ít nhất 1 trong 2**: Trend confirmation HOẶC Momentum confirmation
   - Không cần cả 2, chỉ cần 1 là đủ (logic OR, không phải AND)
3. ✅ **Volume confirmation** (nếu REQUIRE_VOLUME_CONFIRMATION = True)

### 6.4 Ví dụ quyết định

#### Ví dụ 1: BUY Signal mạnh

```
Chỉ báo đồng thuận:
✅ RSI oversold (28)
✅ MACD bullish crossover
✅ Fibonacci 0.618 support hit
✅ Price > MA20 > MA50 (Trend OK)
✅ MACD Histogram > 0 (Momentum OK)
✅ Volume HIGH (1.8x MA)

→ Signal: BUY (Strength = 3)
→ Điều kiện: ✅ 3 >= 2, ✅ Trend OK, ✅ Volume OK
→ KẾT QUẢ: MỞ LỆNH BUY
```

#### Ví dụ 2: HOLD (không đủ điều kiện)

```
Chỉ báo:
✅ RSI oversold (28)
✅ BB lower band hit
❌ Không có Fibonacci signal
❌ Không có S/R signal
✅ Price > MA20 > MA50 (Trend OK)
❌ MACD Histogram < 0 (Momentum NOT OK)
❌ Volume LOW (0.4x MA)

→ Signal: HOLD
→ Lý do: 
  - Chỉ có 2 signals (RSI + BB) = đủ MIN_SIGNAL_STRENGTH
  - Nhưng Volume LOW → Không được xác nhận
  - Không có Momentum → Thiếu điều kiện
```

---

## 7. Risk Management

### 7.1 Lot Size Tính toán

#### Công thức

```
Risk Amount = Equity × RISK_PER_TRADE (1%)

Lot Size = Risk Amount / (SL Points × Tick Value)

Ví dụ:
- Equity = 1000 USD
- Risk = 1% = 10 USD
- SL = 800 points
- Tick Value = 1 USD per point per lot
- Lot Size = 10 / (800 × 1) = 0.0125 → Làm tròn = 0.01 lot
```

### 7.2 Stop Loss / Take Profit

#### ATR-based SL/TP (Khuyến nghị)

- **SL**: `6.0 × ATR` (tối thiểu 800 points, tối đa 5000 points)
- **TP**: `10.0 × ATR` (tối thiểu 1600 points, tối đa 10000 points)
- **Risk:Reward**: ~1:1.67

#### Logic

- ATR cao (volatility cao) → SL/TP xa hơn → Tránh bị stop loss sớm
- ATR thấp (volatility thấp) → SL/TP gần hơn → Tận dụng biến động nhỏ

### 7.3 Giới hạn rủi ro

- **MAX_POSITIONS**: 3 lệnh cùng lúc (tránh overexposure)
- **MAX_DAILY_TRADES**: 300 lệnh/ngày (tránh overtrading)
- **MIN_EQUITY_RATIO**: 90% (circuit breaker khi Equity < 90% Balance)

---

## 8. Tổng hợp tín hiệu

### 8.1 Thứ tự ưu tiên

1. **Fibonacci** (nếu có tín hiệu)
   - Mức 0.618 và 0.786 là mạnh nhất
   - Trong uptrend: Fibonacci = Support → BUY
   - Trong downtrend: Fibonacci = Resistance → SELL

2. **Support/Resistance** (khi không có Fibonacci hoặc USE_SR_WHEN_NO_FIB = False)
   - Giá gần Support → BUY
   - Giá gần Resistance → SELL

3. **Volume Confirmation**
   - Volume HIGH → Xác nhận tín hiệu
   - Volume LOW → Cảnh báo (hoặc chặn nếu REQUIRE_VOLUME_CONFIRMATION = True)

4. **Các chỉ báo khác** (RSI, MACD, MA, BB, Stochastic)
   - Đếm số chỉ báo đồng thuận
   - Cần ≥ 2 chỉ báo cùng BUY/SELL

### 8.2 Ma trận quyết định

| Tình huống | Fibonacci | S/R | Volume | Other Signals | Kết quả |
|-----------|-----------|-----|--------|---------------|---------|
| 1 | ✅ Hit | - | HIGH | ≥2 | ✅ **BUY/SELL** |
| 2 | ✅ Hit | - | LOW | ≥2 | ❌ HOLD (Volume không xác nhận) |
| 3 | ❌ No | ✅ Near | HIGH | ≥2 | ✅ **BUY/SELL** |
| 4 | ❌ No | ✅ Near | LOW | ≥2 | ❌ HOLD (Volume không xác nhận) |
| 5 | ❌ No | ❌ No | HIGH | ≥2 | ✅ **BUY/SELL** (nếu có Trend/Momentum) |
| 6 | ❌ No | ❌ No | LOW | ≥2 | ❌ HOLD (Volume + không có S/R/Fib) |
| 7 | ❌ No | ❌ No | ANY | <2 | ❌ HOLD (Không đủ signals) |

### 8.3 Ví dụ thực tế

#### Scenario: BTC đang trong Uptrend

```
Dữ liệu:
- Price: 100,000
- Swing Low: 95,000
- Swing High: 105,000
- Fibonacci 0.618: 98,182
- Current Price: 98,200 (cách Fibonacci 0.618 là 0.02%)
- RSI: 35 (chưa oversold)
- MACD: Bullish
- MA: Price > MA20 > MA50 (Uptrend)
- Volume: 2.1x MA (HIGH)

Phân tích:
✅ Fibonacci 0.618 hit (trong uptrend = Support)
✅ Volume HIGH (xác nhận)
✅ MACD Bullish
✅ Uptrend confirmed

→ Signal: BUY (Strength = 3)
→ KẾT QUẢ: MỞ LỆNH BUY
```

#### Scenario: Giá không theo Fibonacci, dùng S/R

```
Dữ liệu:
- Price: 102,000
- Fibonacci: Không có level nào gần (cách > 2%)
- Support Zone: 101,500 (đã chạm 3 lần, strength = 3)
- Current Price: 101,600 (cách Support 0.1%)
- RSI: 45 (neutral)
- MACD: Neutral
- BB: Price ở middle band
- Volume: 1.2x MA (NORMAL)

Phân tích:
❌ Fibonacci: Không có signal
✅ Support Zone gần (0.1% cách)
⚠️ Volume NORMAL (không cao nhưng không thấp)
⚠️ Chỉ có 1 signal (S/R), cần ≥ 2

→ Signal: HOLD
→ Lý do: Không đủ MIN_SIGNAL_STRENGTH (cần ≥2 signals)
```

---

## 9. Tối ưu hóa và điều chỉnh

### 9.1 Khi nào điều chỉnh tham số

#### Tăng độ chính xác (ít lệnh hơn)
- `MIN_SIGNAL_STRENGTH`: 2 → 3 hoặc 4
- `REQUIRE_VOLUME_CONFIRMATION`: True (bắt buộc volume cao)
- `REQUIRE_TREND_CONFIRMATION`: True (bắt buộc trend)
- `REQUIRE_MOMENTUM_CONFIRMATION`: True (bắt buộc momentum)

#### Tăng số lượng lệnh (nhiều cơ hội hơn)
- `MIN_SIGNAL_STRENGTH`: 2 → 1
- `REQUIRE_VOLUME_CONFIRMATION`: False (không yêu cầu volume)
- `FIBONACCI_TOLERANCE`: 2% → 3% (dễ chạm Fibonacci hơn)
- `SR_TOLERANCE`: 1% → 1.5% (dễ chạm S/R hơn)

### 9.2 Điều chỉnh cho BTC

- **ATR multipliers cao hơn** (6.0, 10.0) vì BTC volatile
- **DEVIATION cao** (100 points) vì giá dao động mạnh
- **Timeframe M15** phù hợp cho scalping BTC
- **MAX_POSITIONS = 3** để tránh overexposure với volatility cao

---

## 10. Lưu ý quan trọng

### 10.1 Không có chỉ báo hoàn hảo

- ✅ Mỗi chỉ báo có ưu và nhược điểm
- ✅ Cần **kết hợp nhiều chỉ báo** để xác nhận tín hiệu
- ✅ **Volume confirmation** rất quan trọng để tránh false signal

### 10.2 Fibonacci và S/R

- ✅ **Fibonacci ưu tiên** vì có độ chính xác cao hơn
- ✅ **S/R là fallback** khi không có Fibonacci
- ✅ Cả 2 đều xác định vùng cản, nhưng Fibonacci dựa trên tỷ lệ toán học, S/R dựa trên dữ liệu thực tế

### 10.3 Volume Analysis

- ⚠️ Tick volume từ MT5 có thể không chính xác 100%
- ⚠️ Nhưng vẫn hữu ích để xác nhận tín hiệu
- ✅ Volume cao thường đi kèm với breakout mạnh

### 10.4 Risk Management

- ⚠️ **LUÔN đặt SL/TP** - không bao giờ trade không có SL
- ⚠️ **Giới hạn số lệnh** - tránh overtrading
- ⚠️ **Circuit breaker** - dừng bot khi Equity giảm quá nhiều

---

## 11. Checklist trước khi chạy

- [ ] Đã test trên demo account
- [ ] Đã cấu hình đúng Risk Management (1% per trade)
- [ ] Đã kiểm tra Fibonacci levels có hợp lý không
- [ ] Đã kiểm tra S/R zones có đúng không
- [ ] Đã bật Volume analysis
- [ ] Đã set MAX_POSITIONS phù hợp với vốn
- [ ] Đã set MIN_EQUITY_RATIO để bảo vệ tài khoản

---

**Cập nhật lần cuối**: 2024
**Version**: 3.0 (với Fibonacci + Volume + S/R)

---

> ⚠️ **Cảnh báo**: Tài liệu này chỉ mô tả logic của bot. Không đảm bảo lợi nhuận. Luôn test kỹ trên demo trước khi dùng real account!

