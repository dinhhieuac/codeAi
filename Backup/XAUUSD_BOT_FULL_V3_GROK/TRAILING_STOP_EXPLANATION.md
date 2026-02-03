# 📋 ĐIỀU KIỆN KÍCH HOẠT TRAILING STOP

## 🔍 Phân tích từ Log

Từ log bạn cung cấp:
```
2025-11-06 10:49:15,322 - INFO - ✅ Smart Trailing Stop kích hoạt: Ticket 597314747, Profit: 194.3 pips (≥ 150 pips)
2025-11-06 10:49:15,500 - INFO - 📉 Smart Trailing Stop: Ticket 597314747, SL: 3993.01 → 3987.10 (Profit: 194.3 pips, Distance: 100 pips)
```

**⚠️ Lưu ý:** Log này có thể đến từ code cũ hoặc logic khác. Code hiện tại có logic khác.

---

## ✅ ĐIỀU KIỆN KÍCH HOẠT THEO CODE HIỆN TẠI

### 1. **BREAK-EVEN STEP** (Bước đầu tiên)

**Kích hoạt khi:**
- `profit_pips >= BREAK_EVEN_START_PIPS` (600 pips)
- Ticket chưa được kích hoạt break-even trước đó

**Hành động:**
- **BUY:** SL = Entry + 50 pips (buffer)
- **SELL:** SL = Entry - 50 pips (buffer)

**Config:**
- `BREAK_EVEN_START_PIPS = 600` pips
- `BREAK_EVEN_BUFFER_PIPS = 50` pips

**Log mẫu:**
```
✅ Break-Even kích hoạt: Ticket 597314747, SL: 3993.01 → 3988.04 (Profit: 600.0 pips ≥ 600 pips)
```

---

### 2. **ATR-BASED TRAILING** (Bước thứ hai)

**Kích hoạt khi:**
- ✅ Đã kích hoạt Break-Even (`ticket in self.breakeven_activated`)
- ✅ ATR có giá trị (`atr_value is not None`)
- ✅ Interval đã qua (ít nhất 10 giây kể từ lần trailing trước)

**Công thức:**
```
trail_distance_pips = max(ATR × ATR_TRAILING_K, ATR_TRAILING_MIN_DISTANCE_PIPS)
trail_distance_pips = max(ATR × 1.5, 100)  # Ví dụ
```

**Hành động:**
- **BUY:** `new_sl = current_price - trail_distance_pips`
- **SELL:** `new_sl = current_price + trail_distance_pips`

**Config:**
- `ATR_TRAILING_K = 1.5` (hệ số ATR)
- `ATR_TRAILING_MIN_DISTANCE_PIPS = 100` pips (khoảng cách tối thiểu)

**Log mẫu:**
```
📉 ATR Trailing: Ticket 597314747, SL: 3993.01 → 3987.10 (Profit: 194.3 pips, ATR: 66.7 pips, Distance: 100 pips)
```

---

### 3. **PARTIAL CLOSE** (Chốt một phần)

**Kích hoạt khi:**
- `profit_pips >= PARTIAL_CLOSE_TP1_PIPS` (1000 pips) → Đóng 40%
- `profit_pips >= PARTIAL_CLOSE_TP2_PIPS` (2000 pips) → Đóng 30% còn lại
- `profit_pips >= PARTIAL_CLOSE_TP3_PIPS` (3000 pips) → Đóng 30% còn lại

**Config:**
- `PARTIAL_CLOSE_TP1_PIPS = 1000` pips
- `PARTIAL_CLOSE_TP2_PIPS = 2000` pips
- `PARTIAL_CLOSE_TP3_PIPS = 3000` pips

---

## 🔄 FLOW HOẠT ĐỘNG

```
Lệnh mới vào
    ↓
Profit < 600 pips
    ↓ (Không có trailing)
Profit ≥ 600 pips
    ↓
✅ Break-Even kích hoạt
    → SL = Entry ± 50 pips
    ↓
ATR Trailing bắt đầu hoạt động
    → SL = Price ± (ATR × 1.5) hoặc tối thiểu 100 pips
    ↓
Profit ≥ 1000 pips → Partial Close TP1 (40%)
Profit ≥ 2000 pips → Partial Close TP2 (30%)
Profit ≥ 3000 pips → Partial Close TP3 (30%)
```

---

## ❓ TẠI SAO LOG HIỂN THỊ 194.3 PIPS ≥ 150 PIPS?

Log này có thể đến từ:
1. **Code cũ:** Trước khi implement professional trailing stop (dùng `TRAIL_START_PIPS = 150`)
2. **Logic khác:** Có thể có code khác đang sử dụng `TRAIL_START_PIPS` (legacy)

**Trong code hiện tại:**
- `TRAIL_START_PIPS = 150` vẫn tồn tại trong config nhưng **KHÔNG được sử dụng** trong logic trailing stop mới
- Logic mới chỉ dùng `BREAK_EVEN_START_PIPS = 600` pips

---

## 💡 KHUYẾN NGHỊ

Nếu bạn muốn trailing stop kích hoạt sớm hơn (ở 150 pips thay vì 600 pips), bạn có thể:

**Option 1:** Giảm `BREAK_EVEN_START_PIPS`
```python
BREAK_EVEN_START_PIPS = 150  # Thay vì 600
```

**Option 2:** Thêm logic trailing sớm (trước break-even)
- Trailing sớm: 150 pips (distance = 100 pips cố định)
- Break-even: 600 pips
- ATR Trailing: Sau break-even

---

## 📊 TÓM TẮT

| Giai đoạn | Điều kiện | Hành động |
|-----------|-----------|-----------|
| **Chưa có lời** | Profit < 600 pips | Không trailing |
| **Break-Even** | Profit ≥ 600 pips | SL = Entry ± 50 pips |
| **ATR Trailing** | Sau Break-Even | SL = Price ± (ATR × 1.5) |
| **Partial Close** | Profit ≥ 1000/2000/3000 pips | Đóng 40%/30%/30% |

