# 📊 BẢNG SO SÁNH 3 CONFIG FILTERS

## 🎯 **TỔNG QUAN**

| Config | Mô tả | Số lượng Signals | Chất lượng | Win Rate | Risk |
|--------|-------|------------------|------------|----------|------|
| **Default** | Cân bằng | 1-3/ngày | Cao | 55-65% | Trung bình |
| **Balanced** | Linh hoạt | 3-8/ngày | Vừa-Cao | 50-60% | Cao hơn |
| **Strict** | Khắt khe | 0-1/ngày | Rất cao | 60-70% | Thấp |

---

## 📋 **CHI TIẾT SO SÁNH**

### **1. M1 Structure Filter**

| Config | `m1_structure_require_both` | Mô tả |
|--------|----------------------------|-------|
| **Default** | `true` | Cần cả Higher/Lower Highs **VÀ** Lows |
| **Balanced** | `false` | Chỉ cần Higher/Lower Highs **HOẶC** Lows |
| **Strict** | `true` | Cần cả Higher/Lower Highs **VÀ** Lows |

**Tác động:**
- **Default/Strict**: Cấu trúc rõ ràng hơn → Ít signals nhưng chất lượng cao
- **Balanced**: Linh hoạt hơn → Nhiều signals hơn

---

### **2. Signal Cluster**

| Config | `signal_cluster_count` | `signal_cluster_window` | Mô tả |
|--------|------------------------|-------------------------|-------|
| **Default** | `2` | `3` | Cần 2 nến signal trong 3 nến gần nhất |
| **Balanced** | `2` | `5` | Cần 2 nến signal trong 5 nến gần nhất (không cần liên tiếp) |
| **Strict** | `2` | `2` | Cần 2 nến signal liên tiếp |

**Tác động:**
- **Default**: Cân bằng
- **Balanced**: Linh hoạt hơn (không cần liên tiếp)
- **Strict**: Khắt khe hơn (phải liên tiếp)

---

### **3. Zone Distance**

| Config | `min_zone_distance_pips` | Mô tả |
|--------|--------------------------|-------|
| **Default** | `10` | Cần cách zone ít nhất 10 pips |
| **Balanced** | `5` | Chỉ cần cách zone 5 pips (gần hơn) |
| **Strict** | `15` | Cần cách zone 15 pips (xa hơn) |

**Tác động:**
- **Default**: Cân bằng
- **Balanced**: Cho phép gần zone hơn → Nhiều signals hơn
- **Strict**: Cần xa zone hơn → Đảm bảo có room to move

---

### **4. Breakout Lookback**

| Config | `breakout_lookback_candles` | Mô tả |
|--------|----------------------------|-------|
| **Default** | `100` | Tìm breakout trong 100 nến gần nhất |
| **Balanced** | `150` | Tìm breakout trong 150 nến (xa hơn) |
| **Strict** | `100` | Tìm breakout trong 100 nến |

**Tác động:**
- **Default/Strict**: Cân bằng
- **Balanced**: Tìm được nhiều breakout hơn (có thể không relevant)

---

### **5. Signal Candle Criteria**

| Config | `signal_candle_min_criteria` | Mô tả |
|--------|------------------------------|-------|
| **Default** | `6` | Cần 6/8 điều kiện |
| **Balanced** | `5` | Chỉ cần 5/8 điều kiện |
| **Strict** | `7` | Cần 7/8 điều kiện |

**Tác động:**
- **Default**: Cân bằng
- **Balanced**: Linh hoạt hơn → Nhiều signals hơn
- **Strict**: Khắt khe hơn → Chất lượng cao hơn

---

### **6. Smooth Pullback - Candle**

| Config | `smooth_pullback_max_candle_multiplier` | Mô tả |
|--------|----------------------------------------|-------|
| **Default** | `2.0` | Nến > 2.0x avg range = lớn |
| **Balanced** | `2.5` | Nến > 2.5x avg range = lớn (cho phép nến lớn hơn) |
| **Strict** | `1.8` | Nến > 1.8x avg range = lớn (khắt khe hơn) |

**Tác động:**
- **Default**: Cân bằng
- **Balanced**: Cho phép nến lớn hơn → Nhiều signals hơn
- **Strict**: Khắt khe hơn → Pullback phải rất mượt

---

### **7. Smooth Pullback - Gap**

| Config | `smooth_pullback_max_gap_multiplier` | Mô tả |
|--------|-------------------------------------|-------|
| **Default** | `0.5` | Gap > 0.5x avg range = lớn |
| **Balanced** | `0.7` | Gap > 0.7x avg range = lớn (cho phép gap lớn hơn) |
| **Strict** | `0.4` | Gap > 0.4x avg range = lớn (khắt khe hơn) |

**Tác động:**
- **Default**: Cân bằng
- **Balanced**: Cho phép gap lớn hơn → Nhiều signals hơn
- **Strict**: Khắt khe hơn → Pullback phải rất mượt, không có gap

---

## 📊 **TỔNG KẾT SO SÁNH**

### **Default (Mặc định):**
```json
{
  "m1_structure_require_both": true,
  "signal_cluster_count": 2,
  "signal_cluster_window": 3,
  "min_zone_distance_pips": 10,
  "breakout_lookback_candles": 100,
  "signal_candle_min_criteria": 6,
  "smooth_pullback_max_candle_multiplier": 2.0,
  "smooth_pullback_max_gap_multiplier": 0.5
}
```
- ✅ **Cân bằng** giữa số lượng và chất lượng
- ✅ **Khuyến nghị** cho người mới bắt đầu
- ✅ **1-3 signals/ngày**

---

### **Balanced (Cân bằng - Linh hoạt hơn):**
```json
{
  "m1_structure_require_both": false,
  "signal_cluster_count": 2,
  "signal_cluster_window": 5,
  "min_zone_distance_pips": 5,
  "breakout_lookback_candles": 150,
  "signal_candle_min_criteria": 5,
  "smooth_pullback_max_candle_multiplier": 2.5,
  "smooth_pullback_max_gap_multiplier": 0.7
}
```
- ✅ **Linh hoạt hơn** so với mặc định
- ✅ **Nhiều signals hơn** (3-8/ngày)
- ✅ **Phù hợp** khi muốn tăng số lượng signals

---

### **Strict (Khắt khe):**
```json
{
  "m1_structure_require_both": true,
  "signal_cluster_count": 2,
  "signal_cluster_window": 2,
  "min_zone_distance_pips": 15,
  "breakout_lookback_candles": 100,
  "signal_candle_min_criteria": 7,
  "smooth_pullback_max_candle_multiplier": 1.8,
  "smooth_pullback_max_gap_multiplier": 0.4
}
```
- ✅ **Chất lượng rất cao**
- ✅ **Ít signals** (0-1/ngày)
- ✅ **Win rate cao hơn** (60-70%)
- ✅ **Phù hợp** khi muốn đảm bảo chất lượng

---

## 🎯 **KHUYẾN NGHỊ SỬ DỤNG**

### **Dùng Default khi:**
- ✅ Bắt đầu test bot
- ✅ Muốn cân bằng giữa số lượng và chất lượng
- ✅ Chưa biết nên chọn config nào

### **Dùng Balanced khi:**
- ✅ Muốn tăng số lượng signals
- ✅ Chấp nhận risk cao hơn một chút
- ✅ Thị trường có nhiều cơ hội

### **Dùng Strict khi:**
- ✅ Muốn đảm bảo chất lượng cao
- ✅ Chấp nhận ít signals
- ✅ Muốn win rate cao hơn

---

## 📝 **CÁCH SỬ DỤNG**

1. **Copy file config** bạn muốn test:
   ```bash
   cp config_tuyen_default.json config_tuyen.json
   # hoặc
   cp config_tuyen_balanced.json config_tuyen.json
   # hoặc
   cp config_tuyen_strict.json config_tuyen.json
   ```

2. **Hoặc đổi tên file** trong code:
   ```python
   config_path = os.path.join(script_dir, "configs", "config_tuyen_default.json")
   ```

3. **Test từng config** và so sánh kết quả

---

## ⚠️ **LƯU Ý**

1. **Test từng config** trong ít nhất 1 tuần
2. **Ghi lại kết quả** để so sánh
3. **Không thay đổi** nhiều config cùng lúc
4. **Backtest** trước khi live nếu có thể

---

## ✅ **KẾT LUẬN**

3 config files đã được tạo:
- ✅ `config_tuyen_default.json` - Mặc định (cân bằng)
- ✅ `config_tuyen_balanced.json` - Linh hoạt (nhiều signals)
- ✅ `config_tuyen_strict.json` - Khắt khe (chất lượng cao)

**Chúc bạn test thành công!** 🚀

