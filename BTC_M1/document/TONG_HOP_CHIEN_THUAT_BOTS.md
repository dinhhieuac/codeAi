# 📊 TỔNG HỢP CHIẾN THUẬT CÁC BOT BTC_M1

## 🤖 Strategy 1: Trend HA (Heiken Ashi Trend Following)

### 🎯 Mục đích
Chiến thuật theo xu hướng sử dụng nến Heiken Ashi kết hợp với breakout channel trên khung thời gian M1.

### 📈 Khung thời gian
- **M1**: Phân tích chính (Heiken Ashi, SMA55, Volume)
- **M5**: Trend filter (EMA 200)
- **H1**: Trend confirmation (EMA 200)

### 🔧 Indicators
1. **M5 EMA 200**: Xác định xu hướng chính
2. **H1 EMA 200**: Xác nhận xu hướng (có thể bật/tắt)
3. **M5 ADX (14)**: Đo sức mạnh xu hướng (threshold: 20)
4. **M5 ATR (14)**: Lọc biến động (threshold: configurable)
5. **M1 SMA55 High/Low**: Channel breakout
6. **M1 Heiken Ashi**: Tín hiệu entry
7. **M1 RSI (14)**: Lọc momentum (BUY: >55, SELL: <45)
8. **M1 Volume MA (20)**: Xác nhận volume (threshold: 1.3x)

### 📊 Logic Entry

#### BUY Signal:
1. ✅ M5 Trend = BULLISH (Close > EMA200)
2. ✅ H1 Trend = BULLISH (nếu bật use_h1_trend)
3. ✅ M5 ADX >= threshold (mặc định 20)
4. ✅ M5 ATR >= threshold
5. ✅ HA nến xanh (HA Close > HA Open)
6. ✅ HA Close > SMA55 High (breakout channel)
7. ✅ Nến trước HA Close <= SMA55 High (fresh breakout)
8. ✅ Không phải Doji (body > 20% range)
9. ✅ Volume > 1.3x MA
10. ✅ RSI > 55

#### SELL Signal:
1. ✅ M5 Trend = BEARISH (Close < EMA200)
2. ✅ H1 Trend = BEARISH (nếu bật use_h1_trend)
3. ✅ M5 ADX >= threshold
4. ✅ M5 ATR >= threshold
5. ✅ HA nến đỏ (HA Close < HA Open)
6. ✅ HA Close < SMA55 Low (breakout channel)
7. ✅ Nến trước HA Close >= SMA55 Low (fresh breakout)
8. ✅ Không phải Doji
9. ✅ Volume > 1.3x MA
10. ✅ RSI < 45

### 🛡️ Risk Management
- **SL Mode**: `auto_m5` (dựa trên M5 High/Low) hoặc `fixed`
- **TP**: Risk:Reward = 1.5 (mặc định)
- **Min SL Distance**: 50,000 points ($500)
- **Spam Filter**: 300 giây (5 phút)
- **Consecutive Loss Guard**: Có
- **Session Filter**: Có (configurable)

### ⚙️ Parameters (Config)
- `adx_min_threshold`: 20
- `atr_min_threshold`: 0.0
- `use_h1_trend`: True
- `rsi_buy_threshold`: 55
- `rsi_sell_threshold`: 45
- `sl_mode`: 'auto_m5' hoặc 'fixed'
- `reward_ratio`: 1.5
- `spam_filter_seconds`: 300

---

## 🤖 Strategy 2: EMA ATR (EMA Crossover với ATR)

### 🎯 Mục đích
Chiến thuật giao dịch theo EMA crossover (EMA14/EMA28) kết hợp với ATR để quản lý risk.

### 📈 Khung thời gian
- **M1**: Phân tích chính (EMA14, EMA28, ATR, RSI)
- **H1**: Trend filter (EMA50, ADX)
- **M5**: Auto SL (optional)

### 🔧 Indicators
1. **H1 EMA50**: Xác định xu hướng chính
2. **H1 ADX (14)**: Đo sức mạnh xu hướng (threshold: 20)
3. **M1 EMA14**: Đường EMA ngắn hạn
4. **M1 EMA28**: Đường EMA dài hạn
5. **M1 ATR (14)**: Đo biến động, tính SL/TP
6. **M1 RSI (14)**: Lọc momentum (BUY: >55, SELL: <45)
7. **M1 Volume MA (20)**: Xác nhận volume (threshold: 1.3x)

### 📊 Logic Entry

#### BUY Signal:
1. ✅ H1 Trend = BULLISH (Close > EMA50)
2. ✅ H1 ADX >= threshold (mặc định 20)
3. ✅ EMA14 cắt lên trên EMA28 (crossover confirmation)
4. ✅ Price không quá xa EMA14 (< 1.5x ATR)
5. ✅ Volume > 1.3x MA
6. ✅ RSI > 55 và đang tăng

#### SELL Signal:
1. ✅ H1 Trend = BEARISH (Close < EMA50)
2. ✅ H1 ADX >= threshold
3. ✅ EMA14 cắt xuống dưới EMA28 (crossover confirmation)
4. ✅ Price không quá xa EMA14 (< 1.5x ATR)
5. ✅ Volume > 1.3x MA
6. ✅ RSI < 45 và đang giảm

### 🔄 Crossover Confirmation
- **Mode 1**: Crossover xảy ra 2 nến trước, trend tiếp tục
- **Mode 2**: Crossover ngay lập tức, EMA14 vẫn tăng/giảm

### 🛡️ Risk Management
- **SL Mode**: `atr` (mặc định) hoặc `auto_m5`
- **ATR SL Multiplier**: 2.0x
- **TP**: Risk:Reward = 1.5 (mặc định)
- **Min SL Distance**: 50,000 points ($500)
- **Spam Filter**: 300 giây (5 phút)
- **Consecutive Loss Guard**: Có
- **Session Filter**: Có

### ⚙️ Parameters (Config)
- `h1_adx_threshold`: 20
- `rsi_buy_threshold`: 55
- `rsi_sell_threshold`: 45
- `crossover_confirmation`: True
- `extension_multiplier`: 1.5
- `volume_multiplier`: 1.3
- `sl_mode`: 'atr' hoặc 'auto_m5'
- `reward_ratio`: 1.5

---

## 🤖 Strategy 3: PA Volume (Price Action với Volume)

### 🎯 Mục đích
Chiến thuật scalping dựa trên pinbar (rejection candle) kết hợp với volume spike và mean reversion về SMA9.

### 📈 Khung thời gian
- **M1**: Phân tích chính (SMA9, Pinbar, Volume, ATR, RSI)
- **M5**: Trend filter (EMA200)

### 🔧 Indicators
1. **M5 EMA200**: Xác định xu hướng chính
2. **M1 SMA9**: Điểm mean reversion
3. **M1 ATR (14)**: Lọc biến động (5-30 pips)
4. **M1 RSI (14)**: Lọc momentum (BUY: >50, SELL: <50)
5. **M1 Volume MA (20)**: Phát hiện volume spike (threshold: 1.5x)
6. **Pinbar Detection**: Nến rejection (nose < 1.5x body)

### 📊 Logic Entry

#### BUY Signal:
1. ✅ M5 Trend = BULLISH
2. ✅ Price gần SMA9 (trong 50,000 points = $500)
3. ✅ Volume > 1.5x MA
4. ✅ ATR trong khoảng 5-30 pips
5. ✅ Spread < 30,000 pips ($300)
6. ✅ Bullish Pinbar (lower shadow > 1.5x body)
7. ✅ Close > SMA9
8. ✅ RSI > 50

#### SELL Signal:
1. ✅ M5 Trend = BEARISH
2. ✅ Price gần SMA9
3. ✅ Volume > 1.5x MA
4. ✅ ATR trong khoảng 5-30 pips
5. ✅ Spread < 30,000 pips
6. ✅ Bearish Pinbar (upper shadow > 1.5x body)
7. ✅ Close < SMA9
8. ✅ RSI < 50

### 🛡️ Risk Management
- **SL Mode**: `pinbar` (mặc định), `atr`, hoặc `auto_m5`
- **Pinbar SL**: Dưới Low (BUY) hoặc trên High (SELL) + buffer 2,000 points
- **ATR SL**: 2.0x ATR
- **TP**: Risk:Reward = 2.0 (mặc định cho pinbar)
- **Min SL Distance**: 5,000 points ($50)
- **Spam Filter**: 300 giây (5 phút)
- **Session Filter**: Không

### ⚙️ Parameters (Config)
- `sl_mode`: 'pinbar', 'atr', hoặc 'auto_m5'
- `reward_ratio`: 2.0
- `sl_atr_multiplier`: 2.0
- `tp_atr_multiplier`: 4.0
- `volume_threshold`: 1.5

---

## 🤖 Strategy 4: UT Bot (ATR Trailing Stop)

### 🎯 Mục đích
Chiến thuật sử dụng UT Bot (ATR Trailing Stop logic) để phát hiện đảo chiều xu hướng.

### 📈 Khung thời gian
- **M1**: Phân tích chính (UT Bot, RSI, ADX, Volume)
- **H1**: Trend filter (EMA50, ADX)

### 🔧 Indicators
1. **H1 EMA50**: Xác định xu hướng chính
2. **H1 ADX (14)**: Đo sức mạnh xu hướng (threshold: 20)
3. **M1 UT Bot**: ATR Trailing Stop (sensitivity=2, period=10)
4. **M1 RSI (14)**: Lọc momentum (BUY: >55, SELL: <45)
5. **M1 ADX (14)**: Lọc thị trường có xu hướng (threshold: 25)
6. **M1 Volume MA (20)**: Xác nhận volume (threshold: 1.3x)

### 📊 Logic Entry

#### BUY Signal:
1. ✅ H1 Trend = BULLISH (Close > EMA50)
2. ✅ H1 ADX >= threshold (20)
3. ✅ M1 ADX >= 25 (tránh thị trường sideways)
4. ✅ UT Bot flip từ SELL (-1) sang BUY (+1)
5. ✅ UT confirmation: Flip 1-2 nến trước, position tiếp tục
6. ✅ Volume > 1.3x MA
7. ✅ RSI > 55 và đang tăng

#### SELL Signal:
1. ✅ H1 Trend = BEARISH (Close < EMA50)
2. ✅ H1 ADX >= threshold
3. ✅ M1 ADX >= 25
4. ✅ UT Bot flip từ BUY (+1) sang SELL (-1)
5. ✅ UT confirmation: Flip 1-2 nến trước, position tiếp tục
6. ✅ Volume > 1.3x MA
7. ✅ RSI < 45 và đang giảm

### 🔄 UT Bot Logic
- Tính ATR Trailing Stop dựa trên ATR
- Position = +1 (BUY) khi Close > Trailing Stop
- Position = -1 (SELL) khi Close < Trailing Stop
- Signal khi position flip

### 🛡️ Risk Management
- **SL Mode**: `fixed` (mặc định) hoặc `auto_m5`
- **Fixed SL**: 2.0 points (BUY) hoặc +2.0 points (SELL)
- **TP**: Risk:Reward = 1.5 (mặc định)
- **Spam Filter**: 300 giây (5 phút)
- **Consecutive Loss Guard**: Có
- **Session Filter**: Không

### ⚙️ Parameters (Config)
- `h1_adx_threshold`: 20
- `rsi_buy_threshold`: 55
- `rsi_sell_threshold`: 45
- `ut_confirmation`: True
- `sl_mode`: 'fixed' hoặc 'auto_m5'
- `reward_ratio`: 1.5

---

## 🤖 Strategy 5: Filter First (Donchian Breakout)

### 🎯 Mục đích
Chiến thuật breakout theo Donchian Channel (High/Low của N periods) với nhiều filter để tránh false breakout.

### 📈 Khung thời gian
- **M1**: Phân tích chính (Donchian, ATR, ADX, RSI)
- **M5**: Trend filter (EMA200, ADX)

### 🔧 Indicators
1. **M5 EMA200**: Xác định xu hướng chính
2. **M5 ADX (14)**: Đo sức mạnh xu hướng (threshold: 20)
3. **M1 Donchian Channel (50)**: Upper/Lower band
4. **M1 ATR (14)**: Lọc biến động (100-20,000 pips)
5. **M1 ADX (14)**: Lọc thị trường có xu hướng (threshold: 25)
6. **M1 RSI (14)**: Lọc momentum (BUY: >55, SELL: <45)
7. **M1 Volume MA (20)**: Xác nhận volume (threshold: 1.5x)

### 📊 Logic Entry

#### BUY Signal:
1. ✅ M5 Trend = BULLISH (Close > EMA200)
2. ✅ M5 ADX >= threshold (20)
3. ✅ M1 ADX >= 25
4. ✅ ATR trong khoảng 100-20,000 pips
5. ✅ Breakout Upper Donchian (Close > Upper + buffer)
6. ✅ Breakout confirmation: 2 nến liên tiếp trên Upper hoặc breakout mạnh (1.5x buffer)
7. ✅ Không phải false breakout (nến trước không đóng ngược lại)
8. ✅ Volume > 1.5x MA
9. ✅ RSI > 55 và đang tăng

#### SELL Signal:
1. ✅ M5 Trend = BEARISH (Close < EMA200)
2. ✅ M5 ADX >= threshold
3. ✅ M1 ADX >= 25
4. ✅ ATR trong khoảng 100-20,000 pips
5. ✅ Breakout Lower Donchian (Close < Lower - buffer)
6. ✅ Breakout confirmation: 2 nến liên tiếp dưới Lower hoặc breakout mạnh
7. ✅ Không phải false breakout
8. ✅ Volume > 1.5x MA
9. ✅ RSI < 45 và đang giảm

### 🔄 Breakout Confirmation
- **Mode 1**: Breakout xảy ra 2 nến trước, giá tiếp tục
- **Mode 2**: Breakout mạnh (1.5x buffer) ngay lập tức

### 🛡️ False Breakout Check
- BUY: Nến trước High > Upper nhưng Close < Upper → False
- SELL: Nến trước Low < Lower nhưng Close > Lower → False

### 🛡️ Risk Management
- **SL Mode**: `atr` (mặc định) hoặc `auto_m5`
- **ATR SL Multiplier**: 2.0x
- **TP**: Risk:Reward = 1.5 (mặc định)
- **Min SL Distance**: 50,000 points ($500)
- **Spam Filter**: 300 giây (5 phút)
- **Consecutive Loss Guard**: Có
- **Session Filter**: Không

### ⚙️ Parameters (Config)
- `m5_adx_threshold`: 20
- `donchian_period`: 50
- `buffer_multiplier`: 100 (points)
- `atr_min_pips`: 100
- `atr_max_pips`: 20,000
- `rsi_buy_threshold`: 55
- `rsi_sell_threshold`: 45
- `volume_threshold`: 1.5
- `breakout_confirmation`: True
- `sl_mode`: 'atr' hoặc 'auto_m5'
- `reward_ratio`: 1.5

---

## 📋 TỔNG KẾT SO SÁNH

| Bot | Khung thời gian chính | Trend Filter | Entry Signal | Risk:Reward | Đặc điểm |
|-----|----------------------|--------------|--------------|-------------|----------|
| **Strat 1** | M1 | M5+H1 EMA200 | HA Breakout Channel | 1.5 | Nhiều filter nhất, an toàn |
| **Strat 2** | M1 | H1 EMA50 | EMA Crossover | 1.5 | Cân bằng, dễ hiểu |
| **Strat 3** | M1 | M5 EMA200 | Pinbar + Volume | 2.0 | Scalping, R:R cao |
| **Strat 4** | M1 | H1 EMA50 | UT Bot Flip | 1.5 | Đảo chiều xu hướng |
| **Strat 5** | M1 | M5 EMA200 | Donchian Breakout | 1.5 | Breakout mạnh, nhiều filter |

## 🔒 CÁC BẢO VỆ CHUNG

1. **Spam Filter**: Tất cả bot đều có cooldown 5 phút giữa các lệnh
2. **Consecutive Loss Guard**: Strat 1, 2, 4, 5 có bảo vệ sau nhiều lệnh thua liên tiếp
3. **Session Filter**: Strat 1, 2 có filter theo giờ giao dịch
4. **Volume Confirmation**: Tất cả bot đều yêu cầu volume > 1.3-1.5x MA
5. **RSI Momentum**: Yêu cầu RSI đang tăng (BUY) hoặc giảm (SELL)
6. **ADX Filter**: Yêu cầu xu hướng mạnh (ADX >= 20-25)

## 📊 ĐIỂM MẠNH TỪNG BOT

- **Strat 1**: An toàn nhất, nhiều filter, phù hợp thị trường có xu hướng rõ
- **Strat 2**: Cân bằng, dễ tối ưu, phù hợp nhiều điều kiện thị trường
- **Strat 3**: R:R cao (2.0), phù hợp scalping, cần thị trường có biến động vừa phải
- **Strat 4**: Phát hiện đảo chiều sớm, phù hợp thị trường range
- **Strat 5**: Bắt breakout mạnh, nhiều filter tránh false signal

---

*Tài liệu được tạo tự động từ code - Cập nhật: 2025-01-22*
