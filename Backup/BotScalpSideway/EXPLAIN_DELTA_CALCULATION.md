# Giải Thích Cách Tính DeltaHigh và DeltaLow

## 📊 Công Thức Tính Delta

### SELL Signal - DeltaHigh

**Công thức:**
```
DeltaHigh = High[i] - High[i-1]
```

**Trong đó:**
- `High[i]` = High của nến hiện tại (current candle)
- `High[i-1]` = High của nến trước đó (previous candle)
- `i` = index của nến hiện tại (last completed M1 candle)

**Ví dụ với log:**
```
2026-01-21 11:04:59|XAUUSD|SELL_DeltaH=0.39000
```

**Giải thích:**
- Giả sử tại thời điểm 11:04:59 (M1 candle đã đóng):
  - Nến hiện tại (i): High = 4844.50000 USD
  - Nến trước đó (i-1): High = 4844.11000 USD
  - **DeltaHigh = 4844.50000 - 4844.11000 = 0.39000 USD**

**Ý nghĩa:**
- DeltaHigh > 0: Nến hiện tại có đỉnh cao hơn nến trước → Giá đang tăng
- DeltaHigh = 0: Đỉnh bằng nhau
- DeltaHigh < 0: Nến hiện tại có đỉnh thấp hơn nến trước → Giá đang giảm

---

### BUY Signal - DeltaLow

**Công thức:**
```
DeltaLow = Low[i-1] - Low[i]
```

**Trong đó:**
- `Low[i-1]` = Low của nến trước đó (previous candle)
- `Low[i]` = Low của nến hiện tại (current candle)

**Ví dụ với log:**
```
2026-01-21 11:04:59|XAUUSD|BUY_DeltaL=-0.62400
```

**Giải thích:**
- Giả sử tại thời điểm 11:04:59:
  - Nến trước đó (i-1): Low = 4842.20000 USD
  - Nến hiện tại (i): Low = 4842.82400 USD
  - **DeltaLow = 4842.20000 - 4842.82400 = -0.62400 USD**

**Ý nghĩa:**
- DeltaLow > 0: Nến trước có đáy thấp hơn nến hiện tại → Giá đang tăng
- DeltaLow = 0: Đáy bằng nhau
- DeltaLow < 0: Nến trước có đáy cao hơn nến hiện tại → Giá đang giảm

---

## 🔍 Điều Kiện Hợp Lệ cho SELL

Theo tài liệu `botsupper.md`, DeltaHigh hợp lệ cho SELL khi:

1. **DeltaHigh > 0** ✅
   - Nến hiện tại có đỉnh cao hơn nến trước
   - Ví dụ: SELL_DeltaH=0.39000 > 0 ✅

2. **DeltaHigh < k × ATR** ✅
   - k = 0.33 (cho XAUUSD)
   - ATR = 2.09429
   - Threshold = 0.33 × 2.09429 = 0.69112
   - 0.39000 < 0.69112 ✅

3. **DeltaLow ≤ 0** (khóa hướng) ✅
   - DeltaLow = -0.62400 ≤ 0 ✅
   - Đảm bảo giá không đi xuống (khóa hướng tăng)

**Kết quả:** Tất cả 3 điều kiện đều thỏa → DeltaHigh hợp lệ → Count + 1

---

## 🔍 Điều Kiện Hợp Lệ cho BUY

Theo tài liệu `botsupper.md`, DeltaLow hợp lệ cho BUY khi:

1. **DeltaLow > 0** ❌
   - DeltaLow = -0.62400 < 0 ❌
   - Nến trước có đáy cao hơn nến hiện tại → Giá đang giảm

2. **DeltaLow < k × ATR** (không cần check vì điều kiện 1 đã fail)

3. **DeltaHigh ≤ 0** (khóa hướng) (không cần check vì điều kiện 1 đã fail)

**Kết quả:** Điều kiện 1 không thỏa → DeltaLow không hợp lệ → Count = 0

---

## 📝 Ví Dụ Cụ Thể từ Log

```
2026-01-21 11:04:59|XAUUSD|ATR_Ratio=0.900 OK 
SELL_Range=2.35000 q=0.65 Th=1.36129 OK 
SELL_DeltaH=0.39000 DeltaL=-0.62400 k=0.33 ATR=2.09429 OK 
SELL_Count=1/2 Triggered=NO 
BUY_Range=2.35000 q=0.65 Th=1.36129 OK 
BUY_DeltaL=-0.62400 DeltaH=0.39000 k=0.33 ATR=2.09429 FAIL 
BUY_Count=0/2 Triggered=NO 
NO_SIGNAL Price=4844.02300 ATR=2.09429
```

### Phân tích:

**SELL Check:**
- ✅ ATR_Ratio = 0.900 ∈ [0.8; 1.6]
- ✅ Range = 2.35000 ≥ 1.36129 (q × ATR)
- ✅ DeltaHigh = 0.39000 > 0
- ✅ DeltaHigh = 0.39000 < 0.69112 (k × ATR)
- ✅ DeltaLow = -0.62400 ≤ 0 (khóa hướng)
- ✅ **Delta hợp lệ** → Count = 1/2 (cần thêm 1 nến nữa)

**BUY Check:**
- ✅ ATR_Ratio = 0.900 ∈ [0.8; 1.6]
- ✅ Range = 2.35000 ≥ 1.36129 (q × ATR)
- ❌ DeltaLow = -0.62400 < 0 (không hợp lệ)
- ❌ **Delta không hợp lệ** → Count = 0/2

---

## 💡 Lưu Ý Quan Trọng

1. **DeltaHigh và DeltaLow được tính từ cùng 2 nến:**
   - Nến hiện tại (i): Last completed M1 candle
   - Nến trước đó (i-1): Previous M1 candle

2. **DeltaHigh cho SELL:**
   - Đo sự tăng của đỉnh (high)
   - Cần > 0 để có xu hướng tăng

3. **DeltaLow cho BUY:**
   - Đo sự tăng của đáy (low) - nhưng công thức là Low[i-1] - Low[i]
   - Cần > 0 để có xu hướng tăng (nến trước đáy thấp hơn nến hiện tại)

4. **Khóa hướng:**
   - SELL: DeltaLow ≤ 0 (đảm bảo không có xu hướng giảm)
   - BUY: DeltaHigh ≤ 0 (đảm bảo không có xu hướng tăng)

---

## 🔧 Code Implementation

```python
def calculate_delta_high(df_m1, current_idx=-1):
    """
    DeltaHigh = High[i] - High[i-1]
    """
    current_candle = df_m1.iloc[current_idx]      # Nến hiện tại
    prev_candle = df_m1.iloc[current_idx - 1]     # Nến trước đó
    
    high_current = current_candle['high']          # High[i]
    high_prev = prev_candle['high']                # High[i-1]
    
    delta_high = high_current - high_prev          # DeltaHigh
    
    return delta_high
```

**Ví dụ với XAUUSD:**
- High[i] = 4844.50000
- High[i-1] = 4844.11000
- **DeltaHigh = 4844.50000 - 4844.11000 = 0.39000** ✅
