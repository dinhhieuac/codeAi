# 📋 HƯỚNG DẪN CHI TIẾT CÁC PARAMETERS TRONG CONFIG

## 🎯 **TỔNG QUAN**

File config có 2 sections chính:
- **`parameters`**: Các tham số cho SL/TP và indicators
- **`filters`**: Các bộ lọc để điều chỉnh độ khắt khe của bot

---

## ⚙️ **SECTION 1: PARAMETERS**

### **1. `sl_mode`** (String)
- **Mặc định:** `"atr"`
- **Giá trị có thể:** `"atr"`, `"fixed"`, `"auto_m5"`
- **Mô tả:** Chế độ tính Stop Loss
- **Chi tiết:**
  - `"atr"`: SL = ATR × multiplier (dynamic theo volatility)
  - `"fixed"`: SL cố định (pips)
  - `"auto_m5"`: SL tự động dựa trên M5 structure
- **Ví dụ:**
  ```json
  "sl_mode": "atr"  // SL = 2.0 × ATR(14)
  ```

---

### **2. `reward_ratio`** (Float)
- **Mặc định:** `2.0`
- **Giá trị:** `1.0`, `1.5`, `2.0`, `2.5`, `3.0`, ...
- **Mô tả:** Tỷ lệ Risk:Reward (R:R)
- **Chi tiết:**
  - `2.0` = Risk $1 để kiếm $2 (R:R = 1:2)
  - `1.5` = Risk $1 để kiếm $1.5 (R:R = 1:1.5)
  - `3.0` = Risk $1 để kiếm $3 (R:R = 1:3)
- **Công thức:** `TP = Entry + (SL × reward_ratio)`
- **Ví dụ:**
  ```json
  "reward_ratio": 2.0  // TP = Entry + (SL × 2.0)
  ```

---

### **3. `atr_period`** (Integer)
- **Mặc định:** `14`
- **Giá trị:** `10`, `14`, `20`, `21`, ...
- **Mô tả:** Period (chu kỳ) để tính ATR (Average True Range)
- **Chi tiết:**
  - ATR đo lường volatility của thị trường
  - Period càng nhỏ → ATR nhạy cảm hơn với biến động ngắn hạn
  - Period càng lớn → ATR mượt hơn, ít nhạy cảm hơn
- **Khuyến nghị:**
  - `14`: Chuẩn (mặc định)
  - `10`: Nhạy cảm hơn (cho M1)
  - `21`: Mượt hơn (cho M5/H1)
- **Ví dụ:**
  ```json
  "atr_period": 14  // ATR(14) - chuẩn
  ```

---

### **4. `atr_multiplier`** (Float)
- **Mặc định:** `2.0`
- **Giá trị:** `1.5`, `2.0`, `2.5`, `3.0`, ...
- **Mô tả:** Hệ số nhân ATR để tính SL
- **Chi tiết:**
  - Khi `sl_mode = "atr"`: `SL = Entry ± (ATR × atr_multiplier)`
  - Multiplier càng lớn → SL xa hơn → ít bị stop loss hơn nhưng risk lớn hơn
  - Multiplier càng nhỏ → SL gần hơn → dễ bị stop loss hơn nhưng risk nhỏ hơn
- **Công thức:**
  - BUY: `SL = Entry - (ATR × atr_multiplier)`
  - SELL: `SL = Entry + (ATR × atr_multiplier)`
- **Khuyến nghị:**
  - `2.0`: Cân bằng (mặc định)
  - `1.5`: Tight SL (cho scalping)
  - `2.5-3.0`: Wide SL (cho swing)
- **Ví dụ:**
  ```json
  "atr_multiplier": 2.0  // SL = 2.0 × ATR
  ```

---

### **5. `ema_fast`** (Integer)
- **Mặc định:** `21`
- **Giá trị:** `10`, `21`, `50`, `100`, ...
- **Mô tả:** Period của EMA nhanh (Fast EMA)
- **Chi tiết:**
  - EMA nhanh phản ứng nhanh với biến động giá
  - Period nhỏ → Nhạy cảm hơn, nhiều tín hiệu hơn
  - Period lớn → Mượt hơn, ít tín hiệu hơn
- **Sử dụng:**
  - Dùng để xác định trend ngắn hạn
  - Kết hợp với `ema_slow` để tạo EMA crossover
- **Khuyến nghị:**
  - `21`: Chuẩn (mặc định)
  - `10`: Nhạy cảm hơn
  - `50`: Mượt hơn
- **Ví dụ:**
  ```json
  "ema_fast": 21  // EMA21 - chuẩn
  ```

---

### **6. `ema_slow`** (Integer)
- **Mặc định:** `50`
- **Giá trị:** `50`, `100`, `200`, ...
- **Mô tả:** Period của EMA chậm (Slow EMA)
- **Chi tiết:**
  - EMA chậm phản ứng chậm với biến động giá
  - Dùng để xác định trend dài hạn
  - Kết hợp với `ema_fast` để tạo EMA crossover
- **Sử dụng:**
  - Trend filter: Price > EMA50 = Uptrend, Price < EMA50 = Downtrend
  - EMA crossover: EMA21 > EMA50 = Bullish, EMA21 < EMA50 = Bearish
- **Khuyến nghị:**
  - `50`: Chuẩn (mặc định)
  - `100`: Dài hạn hơn
  - `200`: Rất dài hạn
- **Ví dụ:**
  ```json
  "ema_slow": 50  // EMA50 - chuẩn
  ```

---

## 🔍 **SECTION 2: FILTERS**

### **1. `m1_structure_require_both`** (Boolean)
- **Mặc định:** `true`
- **Giá trị:** `true`, `false`
- **Mô tả:** Yêu cầu M1 structure phải có cả Higher/Lower Highs VÀ Lows, hay chỉ cần 1 trong 2
- **Chi tiết:**
  - **`true`**: Cần **CẢ 2** điều kiện:
    - BEARISH: Lower Highs **VÀ** Lower Lows
    - BULLISH: Higher Highs **VÀ** Higher Lows
    - → **Khắt khe hơn**, ít signals hơn nhưng chất lượng cao hơn
  - **`false`**: Chỉ cần **1 trong 2** điều kiện:
    - BEARISH: Lower Highs **HOẶC** Lower Lows
    - BULLISH: Higher Highs **HOẶC** Higher Lows
    - → **Linh hoạt hơn**, nhiều signals hơn nhưng có thể giảm chất lượng
- **Khi nào dùng:**
  - `true`: Khi muốn đảm bảo cấu trúc rõ ràng, chất lượng cao
  - `false`: Khi muốn tăng số lượng signals, chấp nhận cấu trúc không hoàn hảo
- **Ví dụ:**
  ```json
  "m1_structure_require_both": true  // Cần cả 2 (Highs VÀ Lows)
  ```

---

### **2. `signal_cluster_count`** (Integer)
- **Mặc định:** `2`
- **Giá trị:** `1`, `2`, `3`, `4`, ...
- **Mô tả:** Số lượng nến tín hiệu tối thiểu cần có trong window
- **Chi tiết:**
  - Nến tín hiệu: Doji, Pinbar, Hammer, Inverted Hammer
  - Bot sẽ đếm số nến signal trong `signal_cluster_window` nến gần nhất
  - Yêu cầu: `signal_count >= signal_cluster_count`
- **Tác động:**
  - `1`: Chỉ cần 1 nến signal → **Rất linh hoạt**, nhiều signals
  - `2`: Cần 2 nến signal (mặc định) → **Cân bằng**
  - `3`: Cần 3 nến signal → **Khắt khe**, ít signals nhưng chất lượng cao
- **Khi nào dùng:**
  - `1`: Khi muốn nhiều signals, chấp nhận 1 nến signal
  - `2`: Cân bằng giữa số lượng và chất lượng (khuyến nghị)
  - `3+`: Khi muốn đảm bảo có nhiều confirmation
- **Ví dụ:**
  ```json
  "signal_cluster_count": 2  // Cần ít nhất 2 nến signal
  ```

---

### **3. `signal_cluster_window`** (Integer)
- **Mặc định:** `3`
- **Giá trị:** `2`, `3`, `4`, `5`, ...
- **Mô tả:** Số lượng nến gần nhất để kiểm tra signal cluster
- **Chi tiết:**
  - Bot sẽ check `signal_cluster_window` nến gần nhất
  - Đếm số nến signal trong window này
  - So sánh với `signal_cluster_count`
- **Tác động:**
  - `2`: Chỉ check 2 nến gần nhất → **Khắt khe hơn** (phải liên tiếp)
  - `3`: Check 3 nến gần nhất (mặc định) → **Cân bằng**
  - `5`: Check 5 nến gần nhất → **Linh hoạt hơn** (không cần liên tiếp)
- **Khi nào dùng:**
  - `2`: Khi muốn signals phải liên tiếp
  - `3`: Cân bằng (khuyến nghị)
  - `5+`: Khi muốn linh hoạt hơn, không cần liên tiếp
- **Ví dụ:**
  ```json
  "signal_cluster_window": 3  // Check trong 3 nến gần nhất
  ```

---

### **4. `min_zone_distance_pips`** (Integer)
- **Mặc định:** `10`
- **Giá trị:** `5`, `10`, `15`, `20`, `30`, ...
- **Mô tả:** Khoảng cách tối thiểu (pips) đến Supply/Demand zone ngược để có thể trade
- **Chi tiết:**
  - Bot sẽ check khoảng cách từ giá hiện tại đến zone ngược (Supply khi BULLISH, Demand khi BEARISH)
  - Nếu khoảng cách < `min_zone_distance_pips` → Reject (quá gần zone)
  - Nếu khoảng cách >= `min_zone_distance_pips` → Pass (có room to move)
- **Tác động:**
  - `5`: Cho phép trade khi cách zone 5 pips → **Linh hoạt hơn**, nhiều signals
  - `10`: Cho phép trade khi cách zone 10 pips (mặc định) → **Cân bằng**
  - `20`: Chỉ trade khi cách zone 20 pips → **Khắt khe hơn**, ít signals nhưng an toàn hơn
- **Khi nào dùng:**
  - `5`: Khi muốn nhiều signals, chấp nhận gần zone
  - `10`: Cân bằng (khuyến nghị)
  - `15-20`: Khi muốn đảm bảo có đủ room to move
- **Ví dụ:**
  ```json
  "min_zone_distance_pips": 10  // Cần cách zone ít nhất 10 pips
  ```

---

### **5. `breakout_lookback_candles`** (Integer)
- **Mặc định:** `100`
- **Giá trị:** `50`, `100`, `150`, `200`, ...
- **Mô tả:** Số lượng nến để lookback tìm breakout + retest
- **Chi tiết:**
  - Bot sẽ tìm kiếm breakout trong `breakout_lookback_candles` nến gần nhất
  - Tìm breakout level (previous high/low bị phá vỡ)
  - Check xem giá có retest level này không
- **Tác động:**
  - `50`: Chỉ tìm trong 50 nến gần nhất → **Có thể bỏ lỡ** breakout xa
  - `100`: Tìm trong 100 nến (mặc định) → **Cân bằng**
  - `200`: Tìm trong 200 nến → **Tìm được nhiều breakout hơn** nhưng có thể không relevant
- **Khi nào dùng:**
  - `50`: Khi chỉ quan tâm breakout gần đây
  - `100`: Cân bằng (khuyến nghị)
  - `150-200`: Khi muốn tìm breakout xa hơn
- **Ví dụ:**
  ```json
  "breakout_lookback_candles": 100  // Tìm breakout trong 100 nến gần nhất
  ```

---

### **6. `signal_candle_min_criteria`** (Integer)
- **Mặc định:** `6`
- **Giá trị:** `4`, `5`, `6`, `7`, `8`
- **Mô tả:** Số lượng điều kiện tối thiểu (trong 8 điều kiện) để signal candle trong compression hợp lệ
- **Chi tiết:**
  - Signal candle trong compression có **8 điều kiện**:
    1. Range < avg 3-5 nến trước
    2. Thân nến nhỏ (< 40% range)
    3. Râu nến ngắn (< 50% range)
    4. Close gần đỉnh/đáy khối (> 60% cho BUY, < 40% cho SELL)
    5. Close >/< EMA50
    6. Close >/< EMA200
    7. Không phá vỡ block high/low
    8. Không phải momentum candle
  - Yêu cầu: `criteria_met >= signal_candle_min_criteria`
- **Tác động:**
  - `4`: Chỉ cần 4/8 điều kiện → **Rất linh hoạt**, nhiều signals
  - `6`: Cần 6/8 điều kiện (mặc định) → **Cân bằng**
  - `8`: Cần tất cả 8 điều kiện → **Rất khắt khe**, ít signals nhưng chất lượng cao
- **Khi nào dùng:**
  - `4-5`: Khi muốn nhiều signals, chấp nhận signal candle không hoàn hảo
  - `6`: Cân bằng (khuyến nghị)
  - `7-8`: Khi muốn đảm bảo signal candle rất tốt
- **Ví dụ:**
  ```json
  "signal_candle_min_criteria": 6  // Cần ít nhất 6/8 điều kiện
  ```

---

### **7. `smooth_pullback_max_candle_multiplier`** (Float)
- **Mặc định:** `2.0`
- **Giá trị:** `1.5`, `2.0`, `2.5`, `3.0`, ...
- **Mô tả:** Multiplier để xác định nến "lớn" trong smooth pullback check
- **Chi tiết:**
  - Bot sẽ check pullback có "smooth" không (không có nến quá lớn)
  - Nến được coi là "lớn" nếu: `range > avg_range × multiplier`
  - Nếu có nến lớn → Pullback không smooth → Reject
- **Tác động:**
  - `1.5`: Nến > 1.5x avg range = lớn → **Khắt khe hơn**, ít signals
  - `2.0`: Nến > 2.0x avg range = lớn (mặc định) → **Cân bằng**
  - `2.5`: Nến > 2.5x avg range = lớn → **Linh hoạt hơn**, nhiều signals
- **Khi nào dùng:**
  - `1.5-1.8`: Khi muốn pullback rất mượt, không có nến lớn
  - `2.0`: Cân bằng (khuyến nghị)
  - `2.5-3.0`: Khi chấp nhận pullback có 1-2 nến lớn
- **Ví dụ:**
  ```json
  "smooth_pullback_max_candle_multiplier": 2.0  // Nến > 2.0x avg = lớn
  ```

---

### **8. `smooth_pullback_max_gap_multiplier`** (Float)
- **Mặc định:** `0.5`
- **Giá trị:** `0.3`, `0.5`, `0.7`, `1.0`, ...
- **Mô tả:** Multiplier để xác định "gap" lớn giữa các nến
- **Chi tiết:**
  - Bot sẽ check pullback có gap lớn không (khoảng cách giữa close và open của nến liên tiếp)
  - Gap được coi là "lớn" nếu: `gap > avg_range × multiplier`
  - Nếu có gap lớn → Pullback không smooth → Reject
- **Tác động:**
  - `0.3`: Gap > 0.3x avg range = lớn → **Khắt khe hơn**, ít signals
  - `0.5`: Gap > 0.5x avg range = lớn (mặc định) → **Cân bằng**
  - `0.7`: Gap > 0.7x avg range = lớn → **Linh hoạt hơn**, nhiều signals
- **Khi nào dùng:**
  - `0.3-0.4`: Khi muốn pullback rất mượt, không có gap
  - `0.5`: Cân bằng (khuyến nghị)
  - `0.7-1.0`: Khi chấp nhận pullback có gap nhỏ
- **Ví dụ:**
  ```json
  "smooth_pullback_max_gap_multiplier": 0.5  // Gap > 0.5x avg = lớn
  ```

---

## 📊 **TỔNG KẾT CÁC GIÁ TRỊ MẶC ĐỊNH**

### **Parameters:**
```json
{
  "sl_mode": "atr",
  "reward_ratio": 2.0,
  "atr_period": 14,
  "atr_multiplier": 2.0,
  "ema_fast": 21,
  "ema_slow": 50
}
```

### **Filters:**
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

---

## 🎯 **KHUYẾN NGHỊ THEO MỤC ĐÍCH**

### **Scalping (Nhiều signals, R:R nhỏ):**
```json
{
  "parameters": {
    "atr_multiplier": 1.5,
    "reward_ratio": 1.5
  },
  "filters": {
    "m1_structure_require_both": false,
    "signal_cluster_count": 1,
    "min_zone_distance_pips": 5
  }
}
```

### **Swing Trading (Ít signals, R:R lớn):**
```json
{
  "parameters": {
    "atr_multiplier": 3.0,
    "reward_ratio": 3.0
  },
  "filters": {
    "m1_structure_require_both": true,
    "signal_cluster_count": 3,
    "min_zone_distance_pips": 20
  }
}
```

### **Balanced (Cân bằng - Mặc định):**
```json
{
  "parameters": {
    "atr_multiplier": 2.0,
    "reward_ratio": 2.0
  },
  "filters": {
    "m1_structure_require_both": true,
    "signal_cluster_count": 2,
    "min_zone_distance_pips": 10
  }
}
```

---

## ⚠️ **LƯU Ý QUAN TRỌNG**

1. **Test trước khi dùng:** Thay đổi config có thể ảnh hưởng lớn đến performance
2. **Backtest:** Nên backtest với config mới trước khi live
3. **Điều chỉnh từng bước:** Không nên thay đổi tất cả cùng lúc
4. **Monitor:** Theo dõi kết quả sau khi thay đổi
5. **Documentation:** Ghi lại config đã test và kết quả

---

## ✅ **KẾT LUẬN**

Tài liệu này giải thích chi tiết **tất cả 14 parameters** trong config:
- **6 parameters**: SL/TP và indicators
- **8 filters**: Điều chỉnh độ khắt khe của bot

**Chúc bạn trading thành công!** 🚀

