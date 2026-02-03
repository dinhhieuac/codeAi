# Phân Tích: Sóng Hồi Hợp Lệ Theo Bot

## 📋 Điều Kiện Sóng Hồi Hợp Lệ (Theo Code)

### 🔴 **BUY Signal - Sóng Hồi Sau Swing High**

Bot kiểm tra các điều kiện sau trong `check_valid_pullback_buy()`:

#### ✅ **Điều Kiện 1: Giá Không Tạo Đỉnh Cao Hơn Swing High**
```python
max_high_after_swing = pullback_candles['high'].max()
if max_high_after_swing > swing_high_price:
    return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** Sau swing high, giá không được tạo đỉnh mới cao hơn swing high
- **Mục đích:** Đảm bảo đây là sóng hồi (pullback), không phải tiếp tục tăng

#### ✅ **Điều Kiện 2: Số Nến Hồi ≤ 30**
```python
if len(pullback_candles) > max_candles:  # max_candles = 30
    return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** Sóng hồi không được quá dài (tối đa 30 nến M1)
- **Mục đích:** Tránh sóng hồi quá dài, mất tính hiệu quả

#### ✅ **Điều Kiện 3: RSI Trong Quá Trình Hồi > 32**
```python
min_rsi_during_pullback = pullback_rsi.min()
if min_rsi_during_pullback <= 32:
    return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** RSI trong toàn bộ quá trình hồi phải > 32
- **Mục đích:** Đảm bảo không quá oversold (nếu RSI < 32, có thể là tiếp tục giảm)

#### ✅ **Điều Kiện 3b: Không Có Nến Giảm Lớn**
```python
# Không có nến giảm nào có body >= 1.2 × ATR(14)_M1
for candle in candles_to_check:
    if candle['close'] < candle['open']:  # Nến giảm
        body_size = abs(candle['close'] - candle['open'])
        if body_size >= 1.2 * atr_val:
            return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** Không có nến giảm nào có body >= 1.2 × ATR
- **Mục đích:** Đảm bảo sóng hồi nhẹ nhàng, không có nến giảm mạnh

#### ✅ **Điều Kiện 4: RSI Hồi Về Vùng 40-50**
```python
last_rsi = pullback_candles.iloc[-1].get('rsi')
if not (40 <= last_rsi <= 50):
    # Kiểm tra xem có nến nào trong vùng target không
    rsi_in_target = pullback_rsi[(pullback_rsi >= 40) & (pullback_rsi <= 50)]
    if len(rsi_in_target) == 0:
        return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** RSI phải hồi về vùng 40-50 (hoặc ít nhất có nến nào đó trong vùng này)
- **Mục đích:** Đảm bảo RSI đã hồi đủ, sẵn sàng cho tín hiệu BUY

#### ✅ **Điều Kiện 5: Giá Không Phá Cấu Trúc Xu Hướng Tăng**
```python
prev_swing_low = before_swing['low'].min()
pullback_low = pullback_candles['low'].min()
if pullback_low < prev_swing_low * 0.9999:  # 0.1 pip buffer
    return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** Pullback low không được thấp hơn swing low trước đó
- **Mục đích:** Đảm bảo xu hướng tăng chính không bị phá vỡ

---

### 🔴 **SELL Signal - Sóng Hồi Sau Swing Low**

Bot kiểm tra các điều kiện sau trong `check_valid_pullback_sell()`:

#### ✅ **Điều Kiện 1: Giá Không Tạo Đáy Thấp Hơn Swing Low**
```python
min_low_after_swing = pullback_candles['low'].min()
if min_low_after_swing < swing_low_price:
    return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** Sau swing low, giá không được tạo đáy mới thấp hơn swing low
- **Mục đích:** Đảm bảo đây là sóng hồi (pullback), không phải tiếp tục giảm

#### ✅ **Điều Kiện 2: Số Nến Hồi ≤ 30**
```python
if len(pullback_candles) > max_candles:  # max_candles = 30
    return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** Sóng hồi không được quá dài (tối đa 30 nến M1)
- **Mục đích:** Tránh sóng hồi quá dài, mất tính hiệu quả

#### ✅ **Điều Kiện 3: RSI Trong Quá Trình Hồi < 68**
```python
max_rsi_during_pullback = pullback_rsi.max()
if max_rsi_during_pullback >= 68:
    return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** RSI trong toàn bộ quá trình hồi phải < 68
- **Mục đích:** Đảm bảo không quá overbought (nếu RSI >= 68, có thể là tiếp tục tăng)

#### ✅ **Điều Kiện 3b: Không Có Nến Tăng Lớn**
```python
# Không có nến tăng nào có body >= 1.2 × ATR(14)_M1
for candle in candles_to_check:
    if candle['close'] > candle['open']:  # Nến tăng
        body_size = abs(candle['close'] - candle['open'])
        if body_size >= 1.2 * atr_val:
            return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** Không có nến tăng nào có body >= 1.2 × ATR
- **Mục đích:** Đảm bảo sóng hồi nhẹ nhàng, không có nến tăng mạnh

#### ✅ **Điều Kiện 4: RSI Hồi Về Vùng 50-60**
```python
last_rsi = pullback_candles.iloc[-1].get('rsi')
if not (50 <= last_rsi <= 60):
    # Kiểm tra xem có nến nào trong vùng target không
    rsi_in_target = pullback_rsi[(pullback_rsi >= 50) & (pullback_rsi <= 60)]
    if len(rsi_in_target) == 0:
        return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** RSI phải hồi về vùng 50-60 (hoặc ít nhất có nến nào đó trong vùng này)
- **Mục đích:** Đảm bảo RSI đã hồi đủ, sẵn sàng cho tín hiệu SELL

#### ✅ **Điều Kiện 5: Giá Không Phá Cấu Trúc Xu Hướng Giảm**
```python
prev_swing_high = before_swing['high'].max()
pullback_high = pullback_candles['high'].max()
if pullback_high > prev_swing_high * 1.0001:  # 0.1 pip buffer
    return False  # ❌ Không hợp lệ
```
- **Yêu cầu:** Pullback high không được cao hơn swing high trước đó
- **Mục đích:** Đảm bảo xu hướng giảm chính không bị phá vỡ

---

## 🔍 Phân Tích Hình Ảnh

### **Mô Tả Hình Ảnh:**
- Có **2 đường trendline màu đỏ:**
  - 1 đường **đi lên** (upward-sloping) từ phần dưới bên trái, đi qua vùng consolidation
  - 1 đường **đi xuống** (downward-sloping) từ phần trên bên phải
- Có các **swing high** và **swing low** được đánh dấu
- Có **1 đường ngang màu trắng** (horizontal line) - có thể là support/resistance
- Giá có vẻ đang trong **vùng consolidation** (sideways movement)

### **Phân Tích:**

#### **1. Đường Trendline Đi Lên (Upward-Sloping)**
- **Có thể là:** Trendline sóng hồi cho **SELL signal** (nối các đáy cao dần sau swing low)
- **Để hợp lệ:**
  - ✅ Giá không tạo đáy thấp hơn swing low
  - ❓ Số nến hồi ≤ 30? (cần đếm nến)
  - ❓ RSI trong quá trình hồi < 68? (cần dữ liệu RSI)
  - ❓ Không có nến tăng lớn (body >= 1.2 × ATR)? (cần dữ liệu ATR)
  - ❓ RSI hồi về vùng 50-60? (cần dữ liệu RSI)
  - ❓ Giá không phá cấu trúc xu hướng giảm? (cần so sánh với swing high trước đó)

#### **2. Đường Trendline Đi Xuống (Downward-Sloping)**
- **Có thể là:** Trendline sóng hồi cho **BUY signal** (nối các đỉnh thấp dần sau swing high)
- **Để hợp lệ:**
  - ✅ Giá không tạo đỉnh cao hơn swing high
  - ❓ Số nến hồi ≤ 30? (cần đếm nến)
  - ❓ RSI trong quá trình hồi > 32? (cần dữ liệu RSI)
  - ❓ Không có nến giảm lớn (body >= 1.2 × ATR)? (cần dữ liệu ATR)
  - ❓ RSI hồi về vùng 40-50? (cần dữ liệu RSI)
  - ❓ Giá không phá cấu trúc xu hướng tăng? (cần so sánh với swing low trước đó)

---

## ⚠️ Kết Luận

### **Không Thể Xác Định Chắc Chắn Từ Hình Ảnh:**

Để xác định chính xác sóng hồi có hợp lệ hay không, bot cần:

1. **Dữ liệu giá (OHLC):** Để kiểm tra:
   - Giá có tạo đỉnh/đáy mới không?
   - Số nến hồi là bao nhiêu?
   - Có nến lớn (body >= 1.2 × ATR) không?
   - Giá có phá cấu trúc không?

2. **Dữ liệu RSI:** Để kiểm tra:
   - RSI trong quá trình hồi có nằm trong khoảng cho phép không?
   - RSI có hồi về vùng target không?

3. **Dữ liệu ATR:** Để kiểm tra:
   - Body của các nến có >= 1.2 × ATR không?

### **Những Gì Có Thể Thấy Từ Hình:**

✅ **Có vẻ hợp lệ:**
- Có swing high và swing low rõ ràng
- Có trendline được vẽ
- Giá có vẻ không phá vỡ swing point (cần xác nhận)

❓ **Cần xác nhận:**
- Số nến hồi có ≤ 30 không?
- RSI có đạt các điều kiện không?
- Có nến lớn (body >= 1.2 × ATR) không?
- Giá có phá cấu trúc không?

---

## 💡 Gợi Ý

Để kiểm tra chính xác, bạn có thể:

1. **Xem log của bot:** Bot sẽ log chi tiết từng điều kiện khi kiểm tra sóng hồi
2. **Kiểm tra trong code:** Chạy bot với dữ liệu thực tế và xem log
3. **Cung cấp thêm thông tin:** 
   - Số nến trong sóng hồi
   - Giá trị RSI tại các điểm quan trọng
   - Giá trị ATR
   - Vị trí swing high/low trước đó

**Tóm lại:** Từ hình ảnh, **không thể xác định chắc chắn** sóng hồi có hợp lệ hay không vì thiếu dữ liệu RSI, ATR, và số nến chính xác. Nhưng **có vẻ hợp lệ** về mặt hình ảnh (có swing point, có trendline, giá không phá vỡ rõ ràng).
