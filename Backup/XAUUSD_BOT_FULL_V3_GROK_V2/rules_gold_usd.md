
# 🟡 QUY TẮC GIAO DỊCH XAU/USD (GOLD/USD)

## ⚙️ I. THÔNG SỐ CƠ BẢN
| Mục | Giá trị khuyến nghị |
|-----|---------------------|
| Khung thời gian chính | M15 / H1 |
| Risk mỗi lệnh | 0.5–1% balance |
| Max lệnh cùng lúc | 2 |
| Max lệnh/ngày | 50 |
| Khoảng cách tối thiểu giữa 2 lệnh cùng chiều | 60 phút |
| Khoảng cách ngược chiều | 15 phút (nếu tín hiệu đảo mạnh) |

---

## 💰 II. QUẢN LÝ VỐN & RỦI RO

### 1. Giới hạn tổng thể:
- **Max loss/ngày:** 5%
- **Max drawdown:** 15%
- **Max consecutive losses:** 4
- **Tạm ngưng giao dịch khi:**
  - Equity < 85% Balance
  - Drawdown trong ngày > 5%
  - Winrate 10 lệnh gần nhất < 40%

### 2. Lot size linh động:
- Giảm **50% lot size sau 3 lệnh thua liên tiếp**
- Tăng **+25% lot size sau 2 lệnh thắng liên tiếp**, nhưng không vượt 1.5× lot ban đầu

---

## 🎯 III. STOP LOSS / TAKE PROFIT (SL/TP)

### 1. Theo ATR (biến động thật) - Theo grok.md:
```python
ATR = average_true_range(14)
SL = ATR × 1.5  # ATR_MULTIPLIER_SL (theo grok.md: ATR Momentum Breakout Scalping)
TP = Partial Close Strategy (TP1: +15 pips, TP2: +30 pips, TP3: trailing)
```
→ SL theo grok.md: **1.5×ATR** (thay vì 2.5×ATR cũ)
→ TP theo grok.md: **TP1: +15 pips (50%), TP2: +30 pips (30%), TP3: trailing**

### 2. Giới hạn SL/TP:
- **SL tối thiểu:** 250 pips (MIN_SL_PIPS)
- **SL giới hạn USD:** 4-5 USD (ATR_MIN_SL_USD = $4, ATR_MAX_SL_USD = $5)
- **TP tối thiểu:** 200 pips (MIN_TP_PIPS)
- **Risk/Reward tối thiểu:** 1.5:1 (MIN_RR_RATIO)
- **ATR tối thiểu:** 12 pips (theo grok.md - điều kiện bắt buộc để vào lệnh)

### 3. Quy tắc linh hoạt:
- Nếu giá đang ở **vùng kháng cự/ hỗ trợ mạnh**, giảm TP còn **1.0×ATR**, SL **0.8×ATR**
- Nếu **xác nhận trend mạnh (EMA9 > EMA21, RSI > 65 cho BUY hoặc RSI < 35 cho SELL)**, cho phép tăng TP thêm **30%** (TP Boost)

---

## 🕓 IV. QUY TẮC THỜI GIAN GIAO DỊCH

### 1. Giờ "ngon ăn" (High-probability) - Theo grok.md:
| Phiên | Giờ VN (+07) | Giờ US/Eastern | Ghi chú |
|--------|--------------|----------------|---------|
| Phiên London/US | **15:00–02:00** | 03:00–14:00 EST (winter) / 04:00–15:00 EDT (summer) | Theo grok.md: Thời gian trade tốt nhất |
| Phiên Âu | 14:00–17:30 | - | Vàng bắt đầu biến động mạnh |
| Phiên Mỹ | 19:30–23:30 | - | Giao dịch chính, nhiều cơ hội nhất |

### 2. Giờ tránh - Theo grok.md:
- ❌ **Asian session (19:00–04:00 EST)** – Thấp volume, tránh giao dịch (theo grok.md)
- ❌ **NY Open (08:00–10:00 EST/EDT)** – Volatility cao khi mở cửa (theo grok.md)
- ❌ **14:30–16:30** – Biến động hỗn loạn trước phiên Mỹ
- ❌ **20:30–21:30** – Tin tức Mỹ công bố (Nonfarm, CPI, FOMC…)
- ❌ Không trade **30 phút trước/sau tin mạnh** (NEWS_BUFFER_MINUTES = 30)

---

## 🧭 V. PHÂN TÍCH KỸ THUẬT - ATR MOMENTUM BREAKOUT SCALPING (grok.md)

### Chiến lược chính: ATR Momentum Breakout Scalping
Theo grok.md: Chiến lược tập trung vào breakout từ vùng supply/demand, sử dụng ATR để quản lý stop-loss và trailing.

### Điều kiện Entry (theo grok.md):

#### BUY Signal:
1. ✅ **Giá breakout trên EMA 9** (giá vừa vượt lên trên EMA 9)
2. ✅ **EMA 9 > EMA 21** (uptrend)
3. ✅ **RSI > 30** (theo grok.md: không cần quá bán, chỉ cần không quá mua)
4. ✅ **ATR > 12 pips** (độ biến động đủ)
5. ✅ **Volume tăng** khi breakout (xác nhận)
6. ✅ **Entry = Breakout + 0.5×ATR** (theo grok.md)

#### SELL Signal:
1. ✅ **Giá breakout dưới EMA 9** (giá vừa vượt xuống dưới EMA 9)
2. ✅ **EMA 9 < EMA 21** (downtrend)
3. ✅ **RSI < 70** (theo grok.md: không cần quá mua, chỉ cần không quá bán)
4. ✅ **ATR > 12 pips** (độ biến động đủ)
5. ✅ **Volume tăng** khi breakout (xác nhận)

### Kết hợp các chỉ báo chính:
| Nhóm | Dấu hiệu BUY | Dấu hiệu SELL | Trọng số |
|------|---------------|----------------|----------|
| **EMA 9/21** | Giá breakout trên EMA 9, EMA9 > EMA21 | Giá breakout dưới EMA 9, EMA9 < EMA21 | 2 điểm (breakout) / 1 điểm (trend) |
| **RSI** | RSI > 30 (theo grok.md) | RSI < 70 (theo grok.md) | 1 điểm |
| **ATR** | ATR > 12 pips (điều kiện bắt buộc) | ATR > 12 pips (điều kiện bắt buộc) | Bắt buộc |
| **Volume** | Volume tăng khi breakout | Volume tăng khi breakout | Xác nhận |
| **MACD** | Cross lên, histogram dương | Cross xuống, histogram âm | 1 điểm |
| **Bollinger Bands** | Giá chạm band dưới | Giá chạm band trên | 1 điểm |

### Signal Strength:
- **MIN_SIGNAL_STRENGTH = 2** (tối thiểu 2 tín hiệu đồng thuận)
- **BUY:** Khi `buy_signals >= 2` và `buy_signals > sell_signals`
- **SELL:** Khi `sell_signals >= 2` và `sell_signals > buy_signals`

---

## 🧠 VI. CHIẾN LƯỢC DỜI SL BẢO TOÀN LỢI NHUẬN CHUYÊN NGHIỆP

### MỤC TIÊU CHIẾN LƯỢC
Bảo toàn lợi nhuận khi lệnh đang chạy có lời, nhưng vẫn duy trì cơ hội ăn trọn xu hướng. Giúp bot:
- Không bị cắt lỗ ngược khi giá đảo chiều mạnh
- Không bị quét SL sớm trong vùng nhiễu
- Giữ được lệnh chạy khi trend tiếp tục

---

### 1. GIAI ĐOẠN TRƯỚC KHI CÓ LỜI
**Khi lệnh mới vào:**
- Bot thiết lập SL ban đầu (initial stop-loss) trong khoảng **5–10 USD** tùy theo lot size và độ biến động
- SL này đảm bảo rủi ro ≤ **0.5–1%** tài khoản, phù hợp với nguyên tắc quản lý vốn
- Trước khi đặt SL, bot kiểm tra:
  - `symbol_info.trade_stops_level`: khoảng cách tối thiểu broker cho phép
  - `spread`: không được quá **50 pips** (nếu spread quá cao → không vào lệnh)

---

### 2. GIAI ĐOẠN BREAK-EVEN STEP (KHI LỆNH BẮT ĐẦU CÓ LỜI)
**💡 Mục tiêu:** Bảo vệ vốn, chuyển lệnh từ trạng thái rủi ro sang an toàn.

**🔧 Cách hoạt động:**
- Khi lợi nhuận đạt ngưỡng pip cố định (**Break-even Start**) — **600 pips** (≈ $6 với 0.01 lot)
- Bot dời SL từ vị trí ban đầu lên giá hòa vốn (entry) + buffer nhỏ (**50 pips**)
- Buffer giúp tránh bị quét do nhiễu
  - **BUY:** SL = entry + 50 pips
  - **SELL:** SL = entry - 50 pips
- Sau khi SL đã dời về hòa vốn, rủi ro chính thức = **0**

**📝 Lưu ý:** Break-even được kích hoạt sau khi lệnh đã có lời đủ lớn, đảm bảo không bị cắt lỗ ngược khi giá đảo chiều nhẹ.

**🧠 Lợi ích:**
- Không bị âm khi thị trường đảo chiều
- Tâm lý giao dịch ổn định hơn vì lệnh đã "miễn rủi ro"

---

### 3. GIAI ĐOẠN ATR-BASED TRAILING (DỜI SL THEO BIẾN ĐỘNG)
**💡 Mục tiêu:** Theo kịp xu hướng thật, tránh đặt SL quá chặt hay quá xa.

**🔧 Công thức tính:**
- Bot lấy ATR (Average True Range) của khung **M15**
- `trail_distance = ATR × hệ_số`
  - ATR: đo mức dao động trung bình trong **14 nến** gần nhất
  - Hệ số (ATR_K): **1.5** cho XAUUSD (phù hợp với độ nhiễu)

**🧩 Quy tắc dời SL:**
- Với lệnh **BUY:**
  - `new_SL = current_bid - (ATR × 1.5)`
- Với lệnh **SELL:**
  - `new_SL = current_ask + (ATR × 1.5)`
- Chỉ cập nhật nếu:
  - SL mới "tốt hơn" SL cũ (tức là lợi nhuận bảo toàn cao hơn)
  - Và khoảng cách ≥ `minimal_stop_level` do broker quy định
  - Khoảng cách tối thiểu: **100 pips** (tránh nhiễu)

---

### 4. GIAI ĐOẠN PARTIAL CLOSE (CHỐT 1 PHẦN LỢI NHUẬN) - Theo grok.md
**💡 Mục tiêu:** Khóa lợi nhuận từng phần, giảm rủi ro khi thị trường đảo chiều mạnh.

**🔧 Quy tắc theo grok.md:**
- **TP1 (+15 pips):**
  - Bot đóng **50%** khối lượng hiện tại (theo grok.md)
  - Đồng thời, dời SL phần còn lại về Break-even + buffer lớn hơn (**100 pips**)
  
- **TP2 (+30 pips):**
  - Bot đóng thêm **30%** volume còn lại (theo grok.md)
  - Dời SL về Break-even + buffer (**100 pips**)
  
- **TP3 (Trailing Stop):**
  - Phần còn lại dùng **Trailing Stop** (theo grok.md)
  - Không partial close thêm, để trailing stop quản lý

**🧠 Kết quả:**
- Vẫn còn lệnh chạy khi giá tiếp tục trend
- Nhưng vốn gốc và một phần lợi nhuận đã được khóa chắc chắn
- Sau khi partial close: Trailing với ATR_K = **1.0** (chặt hơn) để bảo vệ lợi nhuận đã khóa

**📝 Lưu ý:** Theo grok.md, TP levels nhỏ hơn (15 pips, 30 pips) phù hợp với scalping strategy trên M15 timeframe.

---

### 5. QUẢN LÝ GIỚI HẠN SL (5–10 USD)
Để đảm bảo SL tối thiểu luôn nằm trong vùng này, bot thực hiện quy đổi ngược giữa pips ↔ USD theo khối lượng:
```
SL_pips = round( (target_usd / pip_value_per_lot) / lot_size )
```
**Ví dụ XAUUSD:**
- 1 lot = $1/pip
- Lot 0.01 → $0.01/pip
- Muốn SL = $5 → cần **500 pips** (vì 500 × 0.01 = $5)
- Bot đảm bảo SL không nhỏ hơn **500 pips** và không lớn hơn **1000 pips**, ngay cả khi ATR nhỏ

---

### 6. CƠ CHẾ BẢO VỆ & AN TOÀN

| Điều kiện | Hành động |
|-----------|-----------|
| **Spread < 50 pips** | Tránh giờ nhiễu hoặc tin tức |
| **symbol_info.trade_stops_level** | Tránh lỗi modify do SL quá gần |
| **new_SL > old_SL (BUY)** hoặc **new_SL < old_SL (SELL)** | Chỉ nâng, không hạ SL |
| **profit_pips > BREAK_EVEN_START_PIPS (600)** | Chỉ trailing khi có lời đủ lớn |
| **trailing_interval > 10s** | Tránh modify liên tục |
| **lot_size >= 0.01** | Đảm bảo partial close không lỗi volume nhỏ |

---

### 7. TÓM TẮT FLOW HOẠT ĐỘNG (Theo grok.md)

1. **Lệnh mới vào** → SL ban đầu = Entry ± (ATR × 1.5) (theo grok.md)
2. **Profit ≥ 600 pips** → Break-even: SL = entry ± 50 pips ✅
3. **Sau break-even** → ATR trailing: SL = price ± (ATR × 1.5)
4. **Profit ≥ +15 pips** → Partial close TP1: Đóng 50%, SL = entry ± 100 pips (theo grok.md)
5. **Profit ≥ +30 pips** → Partial close TP2: Đóng 30% còn lại, SL = entry ± 100 pips (theo grok.md)
6. **Sau TP2** → Trailing Stop cho phần còn lại (theo grok.md: TP3 dùng trailing)
7. **Sau partial close** → ATR trailing với ATR_K = 1.0 (chặt hơn) để bảo vệ lợi nhuận đã khóa

**📝 Lưu ý:** Flow này phù hợp với chiến lược ATR Momentum Breakout Scalping trên M15 timeframe (theo grok.md).

---

### 8. CÁC RULE KHÁC

- **Không mở thêm lệnh khi có vị thế âm > 2%**
- **Sau chuỗi thắng > 5 lệnh**, nghỉ 30 phút (tránh overconfidence)

---

## 📊 VII. THEO DÕI HIỆU SUẤT
| Metric | Ngưỡng cảnh báo |
|---------|----------------|
| Winrate (20 lệnh gần nhất) | < 45% → giảm lot |
| RR trung bình | < 1.2 → cần tối ưu SL/TP |
| Max drawdown | > 15% → dừng hệ thống |
| Profit factor | < 1.3 → tạm ngưng 1 ngày |
