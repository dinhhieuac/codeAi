# 📋 HƯỚNG DẪN CẤU HÌNH FILTERS

## 🎯 **TỔNG QUAN**

Bot hiện hỗ trợ **8 config options** để điều chỉnh độ khắt khe của các filters, giúp bạn tùy chỉnh bot theo nhu cầu (tăng số lượng signals hoặc giữ chất lượng cao).

---

## ⚙️ **CÁC CONFIG OPTIONS**

### **1. `m1_structure_require_both`** (Boolean)
- **Mặc định:** `true`
- **Mô tả:** Yêu cầu M1 structure phải có cả Higher/Lower Highs VÀ Lows, hay chỉ cần 1 trong 2
- **Giá trị:**
  - `true`: Cần **CẢ 2** (Higher Highs **VÀ** Higher Lows) → **Khắt khe hơn**
  - `false`: Chỉ cần **1 trong 2** (Higher Highs **HOẶC** Higher Lows) → **Linh hoạt hơn**
- **Tác động:** 
  - `true`: Giảm số lượng signals nhưng tăng chất lượng
  - `false`: Tăng số lượng signals nhưng có thể giảm chất lượng

**Ví dụ:**
```json
"m1_structure_require_both": false  // Chỉ cần Higher Highs HOẶC Higher Lows
```

---

### **2. `signal_cluster_count`** (Integer)
- **Mặc định:** `2`
- **Mô tả:** Số lượng nến tín hiệu tối thiểu cần có trong window
- **Giá trị:** `1`, `2`, `3`, ...
- **Tác động:**
  - `1`: Chỉ cần 1 nến signal → **Rất linh hoạt**
  - `2`: Cần 2 nến signal (mặc định) → **Cân bằng**
  - `3`: Cần 3 nến signal → **Rất khắt khe**

**Ví dụ:**
```json
"signal_cluster_count": 1  // Chỉ cần 1 nến signal
```

---

### **3. `signal_cluster_window`** (Integer)
- **Mặc định:** `3`
- **Mô tả:** Số lượng nến gần nhất để kiểm tra signal cluster
- **Giá trị:** `2`, `3`, `4`, `5`, ...
- **Tác động:**
  - `2`: Chỉ check 2 nến gần nhất → **Khắt khe hơn**
  - `3`: Check 3 nến gần nhất (mặc định) → **Cân bằng**
  - `5`: Check 5 nến gần nhất → **Linh hoạt hơn**

**Ví dụ:**
```json
"signal_cluster_window": 5  // Check trong 5 nến gần nhất
```

---

### **4. `min_zone_distance_pips`** (Integer)
- **Mặc định:** `10`
- **Mô tả:** Khoảng cách tối thiểu (pips) đến Supply/Demand zone ngược để có thể trade
- **Giá trị:** `5`, `10`, `15`, `20`, ...
- **Tác động:**
  - `5`: Cho phép trade khi cách zone 5 pips → **Linh hoạt hơn**
  - `10`: Cho phép trade khi cách zone 10 pips (mặc định) → **Cân bằng**
  - `20`: Chỉ trade khi cách zone 20 pips → **Khắt khe hơn**

**Ví dụ:**
```json
"min_zone_distance_pips": 15  // Cần cách zone ít nhất 15 pips
```

---

### **5. `breakout_lookback_candles`** (Integer)
- **Mặc định:** `100`
- **Mô tả:** Số lượng nến để lookback tìm breakout + retest
- **Giá trị:** `50`, `100`, `150`, `200`, ...
- **Tác động:**
  - `50`: Chỉ tìm trong 50 nến gần nhất → **Có thể bỏ lỡ breakout xa**
  - `100`: Tìm trong 100 nến (mặc định) → **Cân bằng**
  - `200`: Tìm trong 200 nến → **Tìm được nhiều breakout hơn**

**Ví dụ:**
```json
"breakout_lookback_candles": 150  // Tìm breakout trong 150 nến gần nhất
```

---

### **6. `signal_candle_min_criteria`** (Integer)
- **Mặc định:** `6`
- **Mô tả:** Số lượng điều kiện tối thiểu (trong 8 điều kiện) để signal candle trong compression hợp lệ
- **Giá trị:** `4`, `5`, `6`, `7`, `8`
- **Tác động:**
  - `4`: Chỉ cần 4/8 điều kiện → **Rất linh hoạt**
  - `6`: Cần 6/8 điều kiện (mặc định) → **Cân bằng**
  - `8`: Cần tất cả 8 điều kiện → **Rất khắt khe**

**8 điều kiện:**
1. Range < avg 3-5 nến trước
2. Thân nến nhỏ
3. Râu nến ngắn
4. Close gần đỉnh/đáy khối
5. Close >/< EMA50
6. Close >/< EMA200
7. Không phá vỡ block
8. Không phải momentum

**Ví dụ:**
```json
"signal_candle_min_criteria": 5  // Chỉ cần 5/8 điều kiện
```

---

### **7. `smooth_pullback_max_candle_multiplier`** (Float)
- **Mặc định:** `2.0`
- **Mô tả:** Multiplier để xác định nến "lớn" trong smooth pullback check
- **Giá trị:** `1.5`, `2.0`, `2.5`, `3.0`, ...
- **Tác động:**
  - `1.5`: Nến > 1.5x avg range = lớn → **Khắt khe hơn**
  - `2.0`: Nến > 2.0x avg range = lớn (mặc định) → **Cân bằng**
  - `2.5`: Nến > 2.5x avg range = lớn → **Linh hoạt hơn**

**Ví dụ:**
```json
"smooth_pullback_max_candle_multiplier": 2.5  // Cho phép nến lớn hơn
```

---

### **8. `smooth_pullback_max_gap_multiplier`** (Float)
- **Mặc định:** `0.5`
- **Mô tả:** Multiplier để xác định "gap" lớn giữa các nến
- **Giá trị:** `0.3`, `0.5`, `0.7`, `1.0`, ...
- **Tác động:**
  - `0.3`: Gap > 0.3x avg range = lớn → **Khắt khe hơn**
  - `0.5`: Gap > 0.5x avg range = lớn (mặc định) → **Cân bằng**
  - `0.7`: Gap > 0.7x avg range = lớn → **Linh hoạt hơn**

**Ví dụ:**
```json
"smooth_pullback_max_gap_multiplier": 0.7  // Cho phép gap lớn hơn
```

---

## 📝 **VÍ DỤ CẤU HÌNH**

### **Cấu hình "STRICT" (Chất lượng cao, ít signals):**
```json
{
  "filters": {
    "m1_structure_require_both": true,
    "signal_cluster_count": 2,
    "signal_cluster_window": 2,
    "min_zone_distance_pips": 15,
    "breakout_lookback_candles": 100,
    "signal_candle_min_criteria": 7,
    "smooth_pullback_max_candle_multiplier": 1.8,
    "smooth_pullback_max_gap_multiplier": 0.4
  }
}
```

### **Cấu hình "NORMAL" (Cân bằng - Mặc định):**
```json
{
  "filters": {
    "m1_structure_require_both": true,
    "signal_cluster_count": 2,
    "signal_cluster_window": 3,
    "min_zone_distance_pips": 10,
    "breakout_lookback_candles": 100,
    "signal_candle_min_criteria": 6,
    "smooth_pullback_max_candle_multiplier": 2.0,
    "smooth_pullback_max_gap_multiplier": 0.5
  }
}
```

### **Cấu hình "RELAXED" (Nhiều signals, chất lượng vừa):**
```json
{
  "filters": {
    "m1_structure_require_both": false,
    "signal_cluster_count": 1,
    "signal_cluster_window": 5,
    "min_zone_distance_pips": 5,
    "breakout_lookback_candles": 150,
    "signal_candle_min_criteria": 5,
    "smooth_pullback_max_candle_multiplier": 2.5,
    "smooth_pullback_max_gap_multiplier": 0.7
  }
}
```

---

## 🎯 **KHUYẾN NGHỊ**

### **Nếu muốn tăng số lượng signals:**
1. ✅ `m1_structure_require_both: false`
2. ✅ `signal_cluster_count: 1`
3. ✅ `signal_cluster_window: 5`
4. ✅ `min_zone_distance_pips: 5`
5. ✅ `signal_candle_min_criteria: 5`

### **Nếu muốn giữ chất lượng cao:**
1. ✅ `m1_structure_require_both: true`
2. ✅ `signal_cluster_count: 2`
3. ✅ `signal_cluster_window: 2`
4. ✅ `min_zone_distance_pips: 15`
5. ✅ `signal_candle_min_criteria: 7`

### **Nếu muốn cân bằng:**
- ✅ Sử dụng **mặc định** (tất cả giá trị mặc định)

---

## ⚠️ **LƯU Ý**

1. **Test trước khi dùng:** Thay đổi config có thể ảnh hưởng lớn đến số lượng và chất lượng signals
2. **Backtest:** Nên backtest với config mới trước khi áp dụng live
3. **Điều chỉnh từng bước:** Không nên thay đổi tất cả cùng lúc, nên điều chỉnh từng filter một
4. **Monitor:** Theo dõi kết quả sau khi thay đổi config

---

## 📊 **TÁC ĐỘNG DỰ KIẾN**

| Config | Strict | Normal | Relaxed |
|--------|--------|--------|---------|
| **Số lượng signals/ngày** | 0-1 | 1-3 | 3-10 |
| **Chất lượng signals** | Rất cao | Cao | Vừa |
| **Win rate** | 60-70% | 55-65% | 50-60% |
| **Risk** | Thấp | Trung bình | Cao hơn |

---

## 🔧 **CÁCH THÊM VÀO CONFIG**

Thêm section `"filters"` vào file config JSON:

```json
{
  "account": 413011866,
  "symbol": "EURUSD",
  "volume": 0.01,
  "magic": 400006,
  "language": "vi",
  "parameters": {
    "sl_mode": "atr",
    "reward_ratio": 2.0
  },
  "filters": {
    "m1_structure_require_both": true,
    "signal_cluster_count": 2,
    "signal_cluster_window": 3,
    "min_zone_distance_pips": 10,
    "breakout_lookback_candles": 100,
    "signal_candle_min_criteria": 6,
    "smooth_pullback_max_candle_multiplier": 2.0,
    "smooth_pullback_max_gap_multiplier": 0.5
  }
}
```

---

## ✅ **KẾT LUẬN**

Bot hiện hỗ trợ **8 config options** để bạn có thể:
- ✅ **Tăng số lượng signals** (relaxed mode)
- ✅ **Giữ chất lượng cao** (strict mode)
- ✅ **Cân bằng** (normal mode - mặc định)

**Chúc bạn trading thành công!** 🚀

