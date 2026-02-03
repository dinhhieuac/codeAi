# 📋 REVIEW 7 ĐIỀU KIỆN BUY & SELL - M1 SCALP STRATEGY

## 🎯 TỔNG QUAN

Bot sẽ chỉ tạo signal khi **TẤT CẢ 7 điều kiện** đều được thỏa mãn. Entry được thực hiện tại **giá đóng cửa của nến phá vỡ trendline**.

---

## 📈 CHIẾN LƯỢC BUY (7 ĐIỀU KIỆN)

### ✅ **ĐIỀU KIỆN 1: EMA50 > EMA200**
- **Mục đích**: Xác nhận xu hướng tăng dài hạn
- **Kiểm tra**: EMA50 phải nằm trên EMA200
- **Thời điểm**: Kiểm tra trên nến M1 đã đóng gần nhất

---

### ✅ **ĐIỀU KIỆN 2: Swing High với RSI > 70**
- **Mục đích**: Tìm điểm đỉnh mạnh với momentum cao
- **Yêu cầu**:
  - Tìm Swing High (lookback = 5 nến)
  - RSI tại Swing High phải > 70
  - Lấy Swing High gần nhất
- **Thời điểm**: Kiểm tra trên dữ liệu M1

---

### ✅ **ĐIỀU KIỆN 3: Sóng hồi hợp lệ (Pullback hợp lệ)**
- **Mục đích**: Xác nhận giá hồi về một cách có kiểm soát, không phá vỡ cấu trúc

#### 3.1. Giá không tạo đỉnh cao hơn swing high
- Trong toàn bộ sóng hồi, giá không được vượt qua swing high

#### 3.2. Số nến hồi tối đa: ≤ 30 nến
- Sóng hồi không được quá dài

#### 3.3. RSI hồi về vùng 40 – 50
- RSI phải về được vùng 40-50 (có thể kiểm tra nến cuối hoặc bất kỳ nến nào trong pullback)

#### 3.4. Trong quá trình hồi: RSI > 32
- RSI tối thiểu trong quá trình hồi phải > 32 (không được quá thấp)

#### 3.5. **KHÔNG có nến giảm nào có body ≥ 1.2 × ATR(14)_M1**
- **Điều kiện mới**: Trong toàn bộ sóng hồi (từ swing high đến trước nến phá trendline)
- Không được có bất kỳ nến giảm (bearish: close < open) nào có body size ≥ 1.2 × ATR
- Body size = |Close - Open|
- Mục đích: Đảm bảo sóng hồi không quá mạnh, không có nến giảm lớn

#### 3.6. Giá không phá cấu trúc xu hướng tăng chính
- Pullback low không được thấp hơn swing low trước đó (có buffer 0.1 pip)

#### 3.7. Trendline sóng hồi (giảm) từ swing high qua các đỉnh thấp dần
- Vẽ được trendline nối từ swing high qua các đỉnh thấp dần trong pullback
- **Điều kiện 3b**: Phải vẽ được trendline (ít nhất 2 điểm)

---

### ✅ **ĐIỀU KIỆN 4: ATR 14 >= 0.00011**
- **Mục đích**: Đảm bảo thị trường có đủ volatility để trade
- **Yêu cầu**: ATR(14) trên M1 phải >= 0.00011 (tương đương 1.1 pips)
- **Lưu ý**: Đây là điều kiện chung cho cả BUY và SELL

---

### ✅ **ĐIỀU KIỆN 5: Nến xác nhận phá vỡ trendline**
- **Mục đích**: Xác nhận giá đã phá vỡ trendline sóng hồi và sẵn sàng tiếp tục xu hướng tăng

#### 5.1. Giá đóng cửa vượt lên trên trendline sóng hồi
- Close > trendline value tại vị trí nến hiện tại

#### 5.2. Giá đóng cửa ≥ EMA 50
- Close >= EMA50 (xác nhận vẫn trong xu hướng tăng)

#### 5.3. RSI đang hướng lên
- RSI hiện tại > RSI nến trước (momentum tăng)

---

### ✅ **ĐIỀU KIỆN 6: Không có Bearish Divergence**
- **Mục đích**: Tránh vào lệnh khi có dấu hiệu đảo chiều
- **Yêu cầu**: 
  - Giá không tạo Higher High (HH) với RSI Lower High (LH)
  - Hoặc giá tạo HH nhưng RSI không tạo HH (RSI bằng hoặc thấp hơn)
- **Lookback**: 50 nến gần nhất

---

### ✅ **ĐIỀU KIỆN 7: RSI(14)_M5 >= 55 và <= 65**
- **Mục đích**: Xác nhận momentum trên khung thời gian cao hơn
- **Yêu cầu**: 
  - RSI(14) trên khung M5 phải nằm trong khoảng 55-65
  - Sử dụng RSI của nến M5 đã đóng gần nhất (nến -2)
- **Lưu ý**: Đây là điều kiện mới được thêm vào

---

## 📉 CHIẾN LƯỢC SELL (7 ĐIỀU KIỆN)

### ✅ **ĐIỀU KIỆN 1: EMA50 < EMA200**
- **Mục đích**: Xác nhận xu hướng giảm dài hạn
- **Kiểm tra**: EMA50 phải nằm dưới EMA200
- **Thời điểm**: Kiểm tra trên nến M1 đã đóng gần nhất

---

### ✅ **ĐIỀU KIỆN 2: Swing Low với RSI < 30**
- **Mục đích**: Tìm điểm đáy mạnh với momentum thấp (oversold)
- **Yêu cầu**:
  - Tìm Swing Low (lookback = 5 nến)
  - RSI tại Swing Low phải < 30
  - Lấy Swing Low gần nhất
- **Thời điểm**: Kiểm tra trên dữ liệu M1

---

### ✅ **ĐIỀU KIỆN 3: Sóng hồi hợp lệ (Pullback hợp lệ)**
- **Mục đích**: Xác nhận giá hồi về một cách có kiểm soát, không phá vỡ cấu trúc

#### 3.1. Giá không tạo đáy thấp hơn swing low
- Trong toàn bộ sóng hồi, giá không được thấp hơn swing low

#### 3.2. Số nến hồi tối đa: ≤ 30 nến
- Sóng hồi không được quá dài

#### 3.3. RSI hồi về vùng 50 – 60
- RSI phải về được vùng 50-60 (có thể kiểm tra nến cuối hoặc bất kỳ nến nào trong pullback)

#### 3.4. Trong quá trình hồi: RSI < 68
- RSI tối đa trong quá trình hồi phải < 68 (không được quá cao)

#### 3.5. **KHÔNG có nến tăng nào có body ≥ 1.2 × ATR(14)_M1**
- **Điều kiện mới**: Trong toàn bộ sóng hồi (từ swing low đến trước nến phá trendline)
- Không được có bất kỳ nến tăng (bullish: close > open) nào có body size ≥ 1.2 × ATR
- Body size = |Close - Open|
- Mục đích: Đảm bảo sóng hồi không quá mạnh, không có nến tăng lớn

#### 3.6. Giá không phá cấu trúc xu hướng giảm chính
- Pullback high không được cao hơn swing high trước đó (có buffer 0.1 pip)

#### 3.7. Trendline sóng hồi (tăng) từ swing low qua các đáy cao dần
- Vẽ được trendline nối từ swing low qua các đáy cao dần trong pullback
- **Điều kiện 3b**: Phải vẽ được trendline (ít nhất 2 điểm)

---

### ✅ **ĐIỀU KIỆN 4: ATR 14 >= 0.00011**
- **Mục đích**: Đảm bảo thị trường có đủ volatility để trade
- **Yêu cầu**: ATR(14) trên M1 phải >= 0.00011 (tương đương 1.1 pips)
- **Lưu ý**: Đây là điều kiện chung cho cả BUY và SELL

---

### ✅ **ĐIỀU KIỆN 5: Nến xác nhận phá vỡ trendline**
- **Mục đích**: Xác nhận giá đã phá vỡ trendline sóng hồi và sẵn sàng tiếp tục xu hướng giảm

#### 5.1. Giá đóng cửa phá xuống dưới trendline sóng hồi
- Close < trendline value tại vị trí nến hiện tại

#### 5.2. Giá đóng cửa ≤ EMA 50
- Close <= EMA50 (xác nhận vẫn trong xu hướng giảm)

#### 5.3. RSI đang hướng xuống
- RSI hiện tại < RSI nến trước (momentum giảm)

---

### ✅ **ĐIỀU KIỆN 6: Không có Bullish Divergence**
- **Mục đích**: Tránh vào lệnh khi có dấu hiệu đảo chiều
- **Yêu cầu**: 
  - Giá không tạo Lower Low (LL) với RSI Higher Low (HL)
  - Hoặc giá tạo LL nhưng RSI không tạo LL (RSI bằng hoặc cao hơn)
- **Lookback**: 50 nến gần nhất

---

### ✅ **ĐIỀU KIỆN 7: RSI(14)_M5 >= 35 và <= 45**
- **Mục đích**: Xác nhận momentum trên khung thời gian cao hơn
- **Yêu cầu**: 
  - RSI(14) trên khung M5 phải nằm trong khoảng 35-45
  - Sử dụng RSI của nến M5 đã đóng gần nhất (nến -2)
- **Lưu ý**: Đây là điều kiện mới được thêm vào

---

## 🔄 SO SÁNH BUY vs SELL

| Điều kiện | BUY | SELL |
|-----------|-----|------|
| **ĐK1** | EMA50 > EMA200 | EMA50 < EMA200 |
| **ĐK2** | Swing High, RSI > 70 | Swing Low, RSI < 30 |
| **ĐK3 - RSI Target** | 40-50 | 50-60 |
| **ĐK3 - RSI During** | RSI > 32 | RSI < 68 |
| **ĐK3 - Body Check** | Không có nến **giảm** body ≥ 1.2×ATR | Không có nến **tăng** body ≥ 1.2×ATR |
| **ĐK3 - Trendline** | Giảm (đỉnh thấp dần) | Tăng (đáy cao dần) |
| **ĐK4** | ATR >= 0.00011 (chung) | ATR >= 0.00011 (chung) |
| **ĐK5 - Break** | Close > Trendline | Close < Trendline |
| **ĐK5 - EMA** | Close >= EMA50 | Close <= EMA50 |
| **ĐK5 - RSI Direction** | RSI tăng | RSI giảm |
| **ĐK6** | Không Bearish Divergence | Không Bullish Divergence |
| **ĐK7 - RSI M5** | 55 ≤ RSI ≤ 65 | 35 ≤ RSI ≤ 45 |

---

## 📊 THÔNG SỐ KỸ THUẬT

### Risk Management
- **SL**: 2 × ATR + 6 × point
- **TP**: 2 × SL distance
- **R:R Ratio**: 1:2

### Entry
- **Entry Price**: Giá đóng cửa của nến phá vỡ trendline
- **Execution**: Market price tại thời điểm gửi lệnh

### Spam Filter
- **Cooldown**: 60 giây giữa các lệnh

---

## ⚠️ LƯU Ý QUAN TRỌNG

1. **Tất cả 7 điều kiện phải thỏa**: Bot chỉ tạo signal khi TẤT CẢ điều kiện đều OK
2. **Điều kiện 3.5 mới**: Kiểm tra body của nến trong pullback (BUY: nến giảm, SELL: nến tăng)
3. **Điều kiện 7 mới**: Kiểm tra RSI trên khung M5 (BUY: 55-65, SELL: 35-45)
4. **Điều kiện 4 chung**: ATR phải >= 0.00011 cho cả BUY và SELL
5. **Entry timing**: Entry tại close của nến phá vỡ, không phải tại thời điểm real-time

---

## 📝 GHI CHÚ

- File này được tạo tự động từ code review
- Các điều kiện được implement trong file `tuyen_trend_sclap.py`
- Tất cả điều kiện đều có logging chi tiết để debug

