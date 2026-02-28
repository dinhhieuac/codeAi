# Bot Update Log

---

## Ngày: 28/02/2026

**Bot:** Strategy 1 Trend HA  
**File:** `XAU_M1_V2/strategy_1_trend_ha.py`  
**Config:** `XAU_M1_V2/configs/config_1.json`

---

### Nội dung update

1. **Chặn mở lệnh mới theo thời gian (spam filter)**  
   - Chặn mở lệnh mới nếu `(now - last_trade_time) < 120s` (mặc định, config: `spam_filter_seconds`).  
   - Lưu `last_trade_time` vào file `last_trade_time.json` (ổn định, không phụ thuộc position, không bị reset khi đóng lệnh).

2. **Chống repaint / vào theo nến chưa đóng**  
   - Thêm config `use_closed_candles` (mặc định `false`).  
   - Khi `use_closed_candles=true`: toàn bộ điều kiện signal/trend/ADX/RSI dùng **nến đã đóng** (idx -2, -3) thay vì nến đang hình thành (-1, -2).

3. **Doji filter đúng Heiken Ashi**  
   - Thay `is_doji()` (nến thường) → `is_doji_ha()` trong `utils.py` (dùng `ha_open`, `ha_close`, `ha_high`, `ha_low`).  
   - Strategy dùng `is_doji_ha(last_ha, threshold=0.2)` cho điều kiện Solid Candle.

4. **SL auto_m5 bớt cứng: buffer theo ATR M5**  
   - Buffer và khoảng cách SL (min/max) tính theo **ATR M5**.  
   - Config (tùy chọn): `atr_period`, `atr_buffer_multiplier`, `atr_buffer_min_pips`, `atr_buffer_max_pips`, `min_sl_distance_pips`, `max_sl_distance_pips`.

5. **Breakeven/Trailing “auto” chuẩn hơn**  
   - Khi vào lệnh, bot lưu **initial SL distance** theo ticket vào file `initial_sl_map.json`.  
   - `manage_position()` trong `utils.py` nhận thêm tham số `initial_sl_map`; ưu tiên dùng initial SL thật từ map để tính breakeven/trailing trigger, không còn ước lượng kiểu “&lt;5 pips thì cho 100”.

---

### File thay đổi

| File | Mô tả |
|------|--------|
| `XAU_M1_V2/strategy_1_trend_ha.py` | Logic use_closed_candles, is_doji_ha, SL ATR M5, last_trade_time + initial_sl_map |
| `XAU_M1_V2/utils.py` | Thêm `is_doji_ha()`, `manage_position(..., initial_sl_map=None)` và đọc initial SL từ map |

### File dữ liệu tạo ra khi chạy

- `XAU_M1_V2/last_trade_time.json` — thời điểm mở lệnh gần nhất (spam filter).  
- `XAU_M1_V2/initial_sl_map.json` — map ticket → initial_sl_pips (phục vụ breakeven/trailing).
