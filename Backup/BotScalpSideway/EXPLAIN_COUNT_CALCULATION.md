# Giải Thích Cách Tính BUY_Count và SELL_Count

## 📊 Tổng Quan

Count là số lượng **nến M1 liên tiếp** có Delta hợp lệ. Cần **Count ≥ 2** để trigger signal.

---

## 🔴 SELL_Count - Cách Tính

### Điều Kiện Để Count Tăng

**SELL_Count** tăng khi **tất cả** các điều kiện sau đều thỏa:

1. **ATR_Ratio ∈ [0.8; 1.6]** ✅
2. **Range ≥ q × ATR** ✅
3. **DeltaHigh > 0** ✅
4. **DeltaHigh < k × ATR** ✅
5. **DeltaLow ≤ 0** (khóa hướng) ✅

→ **SELL_Count = SELL_Count + 1**

### Điều Kiện Để Count Reset

**SELL_Count** reset về **0** khi **bất kỳ** điều kiện nào sau không thỏa:

1. **ATR_Ratio ∉ [0.8; 1.6]** ❌
2. **Range < q × ATR** ❌
3. **DeltaHigh ≤ 0** ❌
4. **DeltaHigh ≥ k × ATR** ❌
5. **DeltaLow > 0** (không khóa hướng) ❌
6. **Nến không liên tiếp** (bị gián đoạn) ❌

→ **SELL_Count = 0**

---

## 🟢 BUY_Count - Cách Tính

### Điều Kiện Để Count Tăng

**BUY_Count** tăng khi **tất cả** các điều kiện sau đều thỏa:

1. **ATR_Ratio ∈ [0.8; 1.6]** ✅
2. **Range ≥ q × ATR** ✅
3. **DeltaLow > 0** ✅
4. **DeltaLow < k × ATR** ✅
5. **DeltaHigh ≤ 0** (khóa hướng) ✅

→ **BUY_Count = BUY_Count + 1**

### Điều Kiện Để Count Reset

**BUY_Count** reset về **0** khi **bất kỳ** điều kiện nào sau không thỏa:

1. **ATR_Ratio ∉ [0.8; 1.6]** ❌
2. **Range < q × ATR** ❌
3. **DeltaLow ≤ 0** ❌
4. **DeltaLow ≥ k × ATR** ❌
5. **DeltaHigh > 0** (không khóa hướng) ❌
6. **Nến không liên tiếp** (bị gián đoạn) ❌

→ **BUY_Count = 0**

---

## 🔄 Logic Count Tracker

### Class: DeltaCountTrackerSupper

```python
class DeltaCountTrackerSupper:
    def __init__(self, min_count: int = 2):
        self.count = 0                    # Count hiện tại
        self.min_count = 2                # Cần Count >= 2 để trigger
        self.last_valid_idx = None        # Index của nến hợp lệ cuối cùng
    
    def update(self, is_valid: bool, current_idx: int):
        if is_valid:
            # Kiểm tra liên tiếp
            if self.last_valid_idx is not None and current_idx != self.last_valid_idx + 1:
                # Không liên tiếp → Reset
                self.count = 0
            
            # Tăng Count
            self.count += 1
            self.last_valid_idx = current_idx
        else:
            # Reset Count
            self.count = 0
            self.last_valid_idx = None
        
        # Trigger nếu Count >= 2
        is_triggered = self.count >= self.min_count
        return self.count, is_triggered
```

---

## 📈 Ví Dụ Cụ Thể

### Ví Dụ 1: SELL_Count Tăng Thành Công

```
11:04:00 (Nến 1, idx=298)
├─ ATR_Ratio = 0.900 ✅
├─ Range = 2.35000 ≥ 1.36129 ✅
├─ DeltaHigh = 0.39000 > 0 ✅
├─ DeltaHigh = 0.39000 < 0.69112 (k×ATR) ✅
└─ DeltaLow = -0.62400 ≤ 0 ✅
→ SELL_Count = 1/2

11:05:00 (Nến 2, idx=299) - LIÊN TIẾP
├─ ATR_Ratio = 0.920 ✅
├─ Range = 2.10000 ≥ 1.36129 ✅
├─ DeltaHigh = 0.25000 > 0 ✅
├─ DeltaHigh = 0.25000 < 0.69112 ✅
└─ DeltaLow = -0.30000 ≤ 0 ✅
→ SELL_Count = 2/2 → ✅ SIGNAL TRIGGERED!
```

### Ví Dụ 2: SELL_Count Reset (Delta Không Hợp Lệ)

```
11:04:00 (Nến 1, idx=298)
├─ DeltaHigh = 0.39000 OK ✅
└─ SELL_Count = 1/2

11:05:00 (Nến 2, idx=299)
├─ DeltaHigh = -0.10000 < 0 ❌ (DeltaHigh phải > 0)
└─ SELL_Count = 0/2 (RESET)
```

### Ví Dụ 3: SELL_Count Reset (Không Liên Tiếp)

```
11:04:00 (Nến 1, idx=298)
├─ DeltaHigh = 0.39000 OK ✅
└─ SELL_Count = 1/2

11:05:00 (Nến 2, idx=299)
├─ DeltaHigh = FAIL ❌
└─ SELL_Count = 0/2 (RESET)

11:06:00 (Nến 3, idx=300)
├─ DeltaHigh = 0.25000 OK ✅
└─ SELL_Count = 1/2 (KHÔNG liên tiếp với nến 1)
```

### Ví Dụ 4: SELL_Count Reset (Range Không Hợp Lệ)

```
11:04:00 (Nến 1, idx=298)
├─ Range = 2.35000 ≥ 1.36129 ✅
├─ DeltaHigh = 0.39000 OK ✅
└─ SELL_Count = 1/2

11:05:00 (Nến 2, idx=299)
├─ Range = 1.20000 < 1.36129 ❌ (Range không hợp lệ)
└─ SELL_Count = 0/2 (RESET)
```

### Ví Dụ 5: BUY_Count Tăng Thành Công

```
11:04:00 (Nến 1, idx=298)
├─ ATR_Ratio = 0.900 ✅
├─ Range = 2.35000 ≥ 1.36129 ✅
├─ DeltaLow = 0.50000 > 0 ✅
├─ DeltaLow = 0.50000 < 0.69112 ✅
└─ DeltaHigh = -0.20000 ≤ 0 ✅
→ BUY_Count = 1/2

11:05:00 (Nến 2, idx=299) - LIÊN TIẾP
├─ ATR_Ratio = 0.920 ✅
├─ Range = 2.10000 ≥ 1.36129 ✅
├─ DeltaLow = 0.30000 > 0 ✅
├─ DeltaLow = 0.30000 < 0.69112 ✅
└─ DeltaHigh = -0.15000 ≤ 0 ✅
→ BUY_Count = 2/2 → ✅ SIGNAL TRIGGERED!
```

---

## 🔍 Phân Tích Log

Từ log của bạn:
```
SELL_Count=1/2 Triggered=NO
```

**Giải thích:**
- **Count = 1**: Đã có **1 nến** với Delta hợp lệ
- **Cần = 2**: Cần thêm **1 nến nữa** (liên tiếp) với Delta hợp lệ
- **Triggered = NO**: Chưa đủ điều kiện để trigger signal

**Để có signal:**
1. Đợi nến M1 mới đóng (11:05:00, 11:06:00, ...)
2. Nến mới phải có Delta hợp lệ
3. Nến mới phải **liên tiếp** với nến trước (không bị gián đoạn)
4. Khi Count = 2/2 → Signal được trigger

---

## 📝 Tóm Tắt Logic

### SELL_Count

| Điều Kiện | Kết Quả |
|-----------|---------|
| Tất cả điều kiện OK + Liên tiếp | Count = Count + 1 |
| Bất kỳ điều kiện FAIL | Count = 0 |
| Không liên tiếp | Count = 0 |
| Count >= 2 | ✅ SIGNAL TRIGGERED |

### BUY_Count

| Điều Kiện | Kết Quả |
|-----------|---------|
| Tất cả điều kiện OK + Liên tiếp | Count = Count + 1 |
| Bất kỳ điều kiện FAIL | Count = 0 |
| Không liên tiếp | Count = 0 |
| Count >= 2 | ✅ SIGNAL TRIGGERED |

---

## 💡 Lưu Ý Quan Trọng

1. **Count phải liên tiếp**: Nếu có nến ở giữa không hợp lệ → Count reset về 0

2. **Count độc lập**: SELL_Count và BUY_Count là 2 tracker riêng biệt, không ảnh hưởng lẫn nhau

3. **Count reset khi ATR_Ratio không hợp lệ**: Nếu ATR_Ratio ∉ [0.8; 1.6] → Cả SELL_Count và BUY_Count đều reset về 0

4. **Count reset khi Range không hợp lệ**: Nếu Range < q × ATR → Count reset về 0

5. **Count chỉ tăng khi có nến M1 mới**: Bot check mỗi giây, nhưng Count chỉ tăng khi có nến M1 mới đóng (mỗi phút 1 lần)

---

## 🔧 Code Implementation

```python
# SELL Count Update
if is_valid_range:
    is_valid_delta = is_valid_delta_sell_supper(...)
    count, is_triggered = sell_count_tracker.update(is_valid_delta, current_idx)
    # count: 0, 1, hoặc 2
    # is_triggered: True nếu count >= 2

# BUY Count Update
if is_valid_range:
    is_valid_delta = is_valid_delta_buy_supper(...)
    count, is_triggered = buy_count_tracker.update(is_valid_delta, current_idx)
    # count: 0, 1, hoặc 2
    # is_triggered: True nếu count >= 2
```

---

## 📊 Flowchart

```
Start
  ↓
Check ATR_Ratio
  ↓ (OK)
Check Range
  ↓ (OK)
Check Delta
  ↓
Is Delta Valid?
  ├─ YES → Check Consecutive?
  │         ├─ YES → Count = Count + 1
  │         └─ NO → Count = 0
  └─ NO → Count = 0
  ↓
Is Count >= 2?
  ├─ YES → ✅ TRIGGER SIGNAL
  └─ NO → ⏳ Wait for next candle
```
