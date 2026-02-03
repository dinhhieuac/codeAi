# Cách Tính SL/TP - Stop Loss và Take Profit

## Tổng quan

Bot hiện tại hỗ trợ **2 phương pháp chính** để tính SL/TP:

1. **Tự động theo ATR** (khuyến nghị) - `USE_ATR_SL_TP = True`
2. **Cố định** (Fixed) - `USE_ATR_SL_TP = False`

---

## 1. Phương pháp ATR-based (Tự động) ⭐ Khuyến nghị

### Cách hoạt động:

Bot tự động tính SL/TP dựa trên **volatility** (độ biến động) của thị trường qua chỉ báo **ATR (Average True Range)**.

### Công thức:

```
ATR = Average True Range (14 nến)
SL = ATR × ATR_SL_MULTIPLIER (6.0)
TP = ATR × ATR_TP_MULTIPLIER (9.0)
```

### Ví dụ:

- **ATR = 500 points**
- **SL = 500 × 6.0 = 3,000 points** (~$3,000 với BTC $80k)
- **TP = 500 × 9.0 = 4,500 points** (~$4,500)
- **Risk:Reward = 1:1.5** (risk $3,000 → reward $4,500)

### Ưu điểm:

✅ **Tự động điều chỉnh** theo volatility:
- Thị trường biến động mạnh (ATR cao) → SL/TP xa hơn → Tránh bị stop loss sớm
- Thị trường ít biến động (ATR thấp) → SL/TP gần hơn → Tận dụng biến động nhỏ

✅ **Phản ánh điều kiện thị trường thực tế**

✅ **Risk:Reward ratio tốt** (~1:1.5)

### Cấu hình trong `configbtc.py`:

```python
USE_ATR_SL_TP = True           # Bật tính SL/TP từ ATR
ATR_SL_MULTIPLIER = 6.0        # Hệ số nhân cho SL
ATR_TP_MULTIPLIER = 9.0        # Hệ số nhân cho TP

# Giới hạn min/max để tránh SL/TP quá gần hoặc quá xa
MIN_SL_POINTS = 1000           # SL tối thiểu (points)
MAX_SL_POINTS = 5000           # SL tối đa (points)
MIN_TP_POINTS = 1500           # TP tối thiểu (points)
MAX_TP_POINTS = 10000          # TP tối đa (points)

# SL tối thiểu dựa trên % giá (đảm bảo không quá gần)
MIN_SL_PERCENT = 0.012         # 1.2% giá (ví dụ: $80k → $960 tối thiểu)
```

---

## 2. Phương pháp Fixed (Cố định)

### Cách hoạt động:

Sử dụng giá trị SL/TP cố định không thay đổi theo thị trường.

### Cấu hình:

```python
USE_ATR_SL_TP = False          # Tắt ATR, dùng giá trị cố định
FIXED_SL_POINTS = 2000        # SL cố định: 2000 points
FIXED_TP_POINTS = 3000        # TP cố định: 3000 points
```

### Ưu điểm:

✅ Đơn giản, dễ hiểu
✅ Dự đoán được risk/reward trước

### Nhược điểm:

❌ Không thích ứng với volatility
❌ Có thể bị stop loss sớm trong thị trường biến động mạnh
❌ Hoặc bỏ lỡ profit trong thị trường ít biến động

---

## 3. Phương pháp nâng cao (Đang phát triển) 🚧

Bot đang được mở rộng để hỗ trợ tính SL/TP từ các chỉ báo kỹ thuật khác:

### 3.1 Support/Resistance-based

```python
USE_SR_BASED_SL_TP = True
```

**Logic:**
- **BUY**: 
  - SL tại **Support zone** gần nhất (dưới giá hiện tại)
  - TP tại **Resistance zone** gần nhất (trên giá hiện tại)
- **SELL**:
  - SL tại **Resistance zone** gần nhất (trên giá hiện tại)
  - TP tại **Support zone** gần nhất (dưới giá hiện tại)

**Ưu điểm:** SL/TP dựa trên các vùng giá quan trọng

### 3.2 Bollinger Bands-based

```python
USE_BB_BASED_SL_TP = True
```

**Logic:**
- **BUY**:
  - SL tại **BB Lower Band**
  - TP tại **BB Middle Band** hoặc **BB Upper Band**
- **SELL**:
  - SL tại **BB Upper Band**
  - TP tại **BB Middle Band** hoặc **BB Lower Band**

**Ưu điểm:** SL/TP theo volatility bands

### 3.3 Fibonacci-based

```python
USE_FIB_BASED_SL_TP = True
```

**Logic:**
- **BUY tại FIB_618** (61.8% retracement):
  - SL tại **FIB_786** (78.6% - retracement sâu hơn)
  - TP tại **FIB_382** (38.2% - retracement nhẹ hơn) hoặc swing high
- **SELL tại FIB_618**:
  - SL tại **FIB_786**
  - TP tại **FIB_382** hoặc swing low

**Ưu điểm:** SL/TP tại các mức Fibonacci quan trọng

### 3.4 Recent High/Low-based

```python
USE_RECENT_HL_SL_TP = True
```

**Logic:**
- **BUY**:
  - SL tại **Low của nến trước** hoặc **Low của 3-5 nến gần nhất**
  - TP tại **High của nến trước** hoặc **High của 3-5 nến gần nhất**
- **SELL**:
  - SL tại **High của nến trước**
  - TP tại **Low của nến trước**

**Ưu điểm:** SL/TP theo swing points gần nhất

---

## So sánh các phương pháp

| Phương pháp | Độ chính xác | Độ phức tạp | Tính thích ứng | Khuyến nghị |
|------------|-------------|-------------|----------------|-------------|
| **ATR-based** | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ **Khuyến nghị** |
| **Fixed** | ⭐⭐ | ⭐ | ⭐ | ❌ Không khuyến nghị |
| **S/R-based** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ Tốt |
| **BB-based** | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ✅ Tốt |
| **Fib-based** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ✅ Tốt (cần Fibonacci) |
| **Recent HL** | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ✅ Đơn giản, hiệu quả |

---

## Khuyến nghị sử dụng

### 1. **Cho người mới bắt đầu:**

```python
USE_ATR_SL_TP = True           # Dùng ATR (tự động, đơn giản)
USE_SR_BASED_SL_TP = False     # Tắt các phương pháp nâng cao
USE_BB_BASED_SL_TP = False
USE_FIB_BASED_SL_TP = False
USE_RECENT_HL_SL_TP = False
```

### 2. **Cho trader có kinh nghiệm:**

```python
USE_ATR_SL_TP = True           # Luôn dùng ATR làm base
USE_SR_BASED_SL_TP = True      # Kết hợp với S/R (ưu tiên)
USE_BB_BASED_SL_TP = False
USE_FIB_BASED_SL_TP = True     # Nếu có Fibonacci signal
USE_RECENT_HL_SL_TP = True     # Kết hợp Recent HL
```

**Logic:** Bot sẽ tính SL/TP từ nhiều phương pháp và chọn giá trị **hợp lý nhất** (trong khoảng min/max).

---

## Cách điều chỉnh

### Nếu SL quá gần (bị stop loss sớm):

```python
ATR_SL_MULTIPLIER = 8.0        # Tăng từ 6.0 → 8.0
MIN_SL_POINTS = 1500           # Tăng từ 1000 → 1500
MIN_SL_PERCENT = 0.015         # Tăng từ 1.2% → 1.5%
```

### Nếu SL quá xa (risk quá lớn):

```python
ATR_SL_MULTIPLIER = 5.0        # Giảm từ 6.0 → 5.0
MAX_SL_POINTS = 4000           # Giảm từ 5000 → 4000
```

### Nếu TP quá gần (bỏ lỡ profit):

```python
ATR_TP_MULTIPLIER = 12.0       # Tăng từ 9.0 → 12.0
MAX_TP_POINTS = 15000          # Tăng từ 10000 → 15000
```

### Nếu TP quá xa (khó đạt được):

```python
ATR_TP_MULTIPLIER = 7.0        # Giảm từ 9.0 → 7.0
MAX_TP_POINTS = 8000           # Giảm từ 10000 → 8000
```

---

## Lưu ý quan trọng

1. **Bot luôn kiểm tra min/max:** Dù tính từ ATR hay chỉ báo nào, SL/TP sẽ được giới hạn trong:
   - `MIN_SL_POINTS` ≤ SL ≤ `MAX_SL_POINTS`
   - `MIN_TP_POINTS` ≤ TP ≤ `MAX_TP_POINTS`

2. **SL tối thiểu từ % giá:** Bot cũng kiểm tra `MIN_SL_PERCENT` để đảm bảo SL không quá gần (ví dụ: không nhỏ hơn 1.2% giá).

3. **Risk:Reward Ratio:** Với ATR multipliers hiện tại (6.0 và 9.0), Risk:Reward ≈ **1:1.5**, đây là tỷ lệ hợp lý.

4. **Backtesting:** Nên backtest với các tham số khác nhau để tìm giá trị tối ưu cho từng symbol và timeframe.

---

## Kết luận

**Câu trả lời cho câu hỏi "TP/SL có thể tính tự động theo thông số kỹ thuật không hay phải fix cứng?"**

✅ **CÓ THỂ TỰ ĐỘNG!** Bot hiện tại đã hỗ trợ tính SL/TP tự động từ:
- ✅ **ATR** (đang hoạt động) - Khuyến nghị
- 🚧 **Support/Resistance** (đang phát triển)
- 🚧 **Bollinger Bands** (đang phát triển)
- 🚧 **Fibonacci** (đang phát triển)
- 🚧 **Recent High/Low** (đang phát triển)

❌ **Không cần fix cứng** - ATR-based đã đủ tốt và tự động điều chỉnh theo thị trường.

**Khuyến nghị:** Giữ `USE_ATR_SL_TP = True` và điều chỉnh `ATR_SL_MULTIPLIER`, `ATR_TP_MULTIPLIER` theo kinh nghiệm giao dịch của bạn.
