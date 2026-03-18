# Grid Step Trading Bot V12 – Tài liệu chiến lược

> Rule Start **không dùng Time Filter**. Áp dụng cho XAUUSD (symbol trong config).  
> Mục tiêu: chỉ dùng **vị trí start**, **trạng thái thị trường** và **biến động** để quyết định bật Grid Step hay không.

---

## 1. Tổng quan

- **File strategy:** `GridStep/strategy_grid_step_v12.py`
- **Config:** `GridStep/configs/config_grid_step_v12.json`
- **Magic:** 100012 (trong config, có thể đổi)
- **Strategy name (DB):** Mặc định `Grid_Step_V12`, override bằng `parameters.strategy_name` để phân biệt nhiều bot.

### Chạy bot

```bash
cd GridStep
python strategy_grid_step_v12.py
```

### Kiểm tra DB

```bash
python strategy_grid_step_v12.py --check-db
```

### Tắt rule (chạy grid thuần, step cố định)

Trong config đặt `"rule_start_step_enabled": false`. Khi đó step = `step_base`, không áp dụng Hard Block / Entry Score.

---

## 2. Tư duy lõi (không lọc theo giờ)

Quan trọng không phải “đang ở giờ nào”, mà là:

- Giá đang ở **mép range** hay **giữa range**
- Giá đã lệch đủ xa khỏi **vùng cân bằng** (EMA50 M15) chưa
- Thị trường đang **sideway** hay **breakout / trend mạnh**
- Volatility **bình thường** hay **quá nóng**
- Bot vừa đóng chu kỳ xong hay chưa (cooldown)

Rule V12 **không dùng time filter** (các key `hours_off`, `hours_on_strong`, `hours_on_weak` trong config **không được dùng** trong logic hiện tại).

---

## 2.1. Rule lệnh chờ (chỉ 1 BUY STOP + 1 SELL STOP)

- Bot **chỉ duy trì tối đa 1 lệnh BUY STOP và 1 lệnh SELL STOP** tại mỗi thời điểm.
- **Khi có một lệnh khớp** (thành position), bot **hủy ngay** lệnh pending còn lại (bên kia).
- Trên vòng lặp tiếp theo, bot đặt lại cặp lệnh chờ mới quanh giá neo (anchor) từ position vừa mở.

Logic thực hiện trong `sync_grid_pending_status`: khi phát hiện một lệnh trong DB ở trạng thái PENDING nhưng đã khớp trên MT5 (có position tương ứng), cập nhật DB sang FILLED và **gọi hủy toàn bộ lệnh chờ còn lại** của strategy đó.  
**Chỉ hủy lệnh của bot V12:** mọi thao tác lệnh chờ/position đều lọc theo `comment = "GridStep_V12"` (và magic), nên không cancel hay đụng đến pending của bot khác.

---

## 3. Biến đầu vào / Context

Bot tự lấy từ MT5:

| Biến | Mô tả |
|------|--------|
| `price` | Giá hiện tại (mid của nến M5 hiện tại) |
| `ema50_m15` | EMA(50) trên M15 |
| `ema50_slope` | Độ dốc EMA50 (ema50 - ema50_prev) để nhận diện trend |
| `atr_m5` | ATR(20) trên M5 |
| `median_atr_m5` | Trung vị ATR M5 trong lookback (mặc định 50 bar) |
| `range_high_3h`, `range_low_3h` | Đỉnh/đáy 3 giờ gần nhất (12 nến M15 đã đóng) |
| `last3_m15` | 3 nến M15 gần nhất đã đóng |
| `range_m5_current`, `range_m5_prev` | Biên độ nến M5 hiện tại và nến trước |
| `last_exit_time` | Thời điểm đóng chu kỳ gần nhất (basket TP), lưu trong `last_exit_time_v12.json` |
| `current_time` | Giờ hiện tại: ưu tiên **MT5 server** (tick.time), fallback **local UTC** |

---

## 4. Hard Block

Chỉ cần **1 điều kiện** thỏa → `ALLOW_START = false`, không tính Entry Score.

### Block 1: Giá đang ở giữa range

- `range_size = range_high_3h - range_low_3h`
- `mid_low = range_low_3h + range_size * 0.33`
- `mid_high = range_low_3h + range_size * 0.67`  
Nếu `mid_low < price < mid_high` → **Không start** (reason: `price_mid_range`).

### Block 2: Breakout mạnh

- Biên độ nến M5 hiện tại > `1.8 * atr_m5` → `breakout_m5`
- Hoặc tổng biên độ (thân) 3 nến M15 > `3.0 * step_base` → `breakout_3bars`
- Hoặc giá vượt `range_high_3h` hoặc `range_low_3h` với độ vượt > `0.5 * step_base` → `breakout_range`

### Block 3: Trend mạnh

- 3 nến M15 gần nhất **cùng màu**
- Và tổng thân 3 nến > `2.5 * step_base`
- Và **EMA50 M15 dốc cùng hướng** (slope cùng dấu với 3 nến, |slope| > 0.03×step_base)  
→ **Không start** (reason: `trend_strong`).

### Block 4: Chưa đủ cooldown sau exit

- `current_time - last_exit_time < cooldown_after_exit_minutes` (mặc định 20 phút)  
→ **Không start** (reason: `cooldown_after_exit`).

### Block 5: ATR quá nóng

- `atr_m5 > 1.5 * median_atr_m5`  
→ **Không start** (reason: `atr_quá_nóng`).

---

## 5. Entry Score (chỉ khi không Hard Block)

Khởi tạo `EntryScore = 0`. Các nhóm:

### A – Vị trí trong range

- Giá ở mép range: `price >= top_zone` hoặc `price <= bottom_zone` (top = range_low + 0.67×size, bottom = range_low + 0.33×size) → **+2**
- Giá rất sát mép: `price >= range_low + 0.85×size` hoặc `price <= range_low + 0.15×size` → **+1**

### B – Độ lệch khỏi EMA50 M15

- `distance_ema = |price - ema50_m15|`
- `distance_ema >= 1.0 * step_base` → **+1**
- `distance_ema >= 1.5 * step_base` → **+1** (cộng thêm)

### C – Dấu hiệu hụt lực (tối đa +2)

- Nến M5 hiện tại có biên độ < nến M5 trước → **+1**
- Nến M15 gần nhất có râu nến ngược hướng ≥ 35% tổng biên độ → **+1**  
Tổng nhóm C tối đa **+2**.

### D – Volatility

- `atr_m5 <= 1.2 * median_atr_m5` → **+1**
- `1.2 * median < atr_m5 <= 1.5 * median` → **+0**
- `atr_m5 > 1.5 * median` → **-1** (thường đã bị Block 5 chặn)

### E – Cấu trúc mean-reversion (tối đa +2)

- Giá ở mép range và nến M15 gần nhất có râu ≥ 35% biên độ (quay đầu) → **+1**
- Giá lệch EMA ≥ 1×step_base và nến M5 thu hẹp (biên độ hiện tại < trước) → **+1**  
Tổng nhóm E tối đa **+2**.

---

## 6. Ngưỡng quyết định start

- Có **Hard Block** → **Không start**.
- Không Hard Block, xét **EntryScore**:
  - **EntryScore >= entry_score_start** (mặc định 6) → **Start**.
  - **EntryScore = entry_score_probe** (mặc định 4 hoặc 5) → **Không start** (probe: có thể bật lot nhỏ sau).
  - **EntryScore <= 3** → **Không start** (reason: `score_low` hoặc `score_below_start`).

---

## 7. Step động

### Công thức gốc

- `step_raw = atr_m5 * k_atr` (mặc định `k_atr = 1.0`).
- Clamp: `step = max(step_min, min(step_max, step_raw))` với `step_min = step_base * 0.8`, `step_max = step_base * 1.8` (hoặc từ config).

### Điều chỉnh theo volatility (ratio = atr_m5 / median_atr_m5)

- `ratio < 0.9` → `step = max(step_min, step_raw * 0.9)` (vol thấp).
- `0.9 <= ratio <= 1.2` → `step = step_raw` (chuẩn).
- `1.2 < ratio <= 1.5` → `step = min(step_max, step_raw * 1.15)` (vol cao).
- `ratio > 1.5` → thường đã Hard Block; nếu vẫn tính step thì dùng `step_max`.

### Điều chỉnh theo cấu trúc thị trường

- **Trend nhẹ:** 3 nến M15 cùng màu và EMA50 dốc cùng hướng → `step *= 1.1` (tối đa step_max).
- **Sideway đẹp:** Giá ở mép range, ATR bình thường (ratio ≤ 1.2), 3 nến xen kẽ, có hụt lực (nến M5 thu hẹp) → `step *= 0.9` (tối thiểu step_min).

---

## 8. Config (`config_grid_step_v12.json`)

### Cấu hình MT5 / Telegram

- `account`, `password`, `server`, `mt5_path`, `symbol`, `volume`, `magic`, `max_positions`, `telegram_token`, `telegram_chat_id`.

### Parameters (rule & grid)

| Key | Mô tả | Mặc định / gợi ý |
|-----|--------|-------------------|
| `strategy_name` | Tên ghi DB (orders, grid_pending_orders) | `"Grid_Step_V12"` |
| `rule_start_step_enabled` | Bật/tắt rule (Hard Block + Entry Score + step động) | `true` |
| `step_base` | Step gốc | `5` |
| `k_atr` | Hệ số ATR cho step_raw | `1.0` |
| `step_min`, `step_max` | Giới hạn step | `4`, `9` |
| `cooldown_after_exit_minutes` | Cooldown sau khi đóng basket TP (phút) | `20` |
| `lookback_range_hours` | Số giờ lấy range (số nến M15 = ×4) | `3` |
| `atr_period_m5` | Chu kỳ ATR M5 | `20` |
| `ema_period_m15` | Chu kỳ EMA M15 | `50` |
| `median_atr_lookback` | Số bar lookback để tính median ATR M5 | `50` |
| `entry_score_start` | Ngưỡng start (>=) | `6` |
| `entry_score_probe` | Ngưỡng probe (4–5: hiện tại không start) | `5` |
| `min_distance_points` | Khoảng cách tối thiểu (point) giữa mức grid | `5` |
| `target_profit` | Basket TP (USD) | `50.0` |
| `spread_max` | Spread tối đa (giá) để đặt lệnh | `0.5` |
| `cooldown_minutes` | Cooldown mức grid (phút, 0 = tắt) | `0` |
| `consecutive_loss_pause_enabled` | Bật pause sau N lệnh thua liên tiếp | `true` |
| `consecutive_loss_count` | Số lệnh thua liên tiếp để pause | `2` |
| `consecutive_loss_pause_minutes` | Thời gian pause (phút) | `5` |

**Lưu ý:** `hours_off`, `hours_on_strong`, `hours_on_weak` trong config **không được sử dụng** trong rule V12 (rule không dùng time filter).

---

## 9. File state (V12 riêng)

- **`grid_cooldown_v12.json`** – Cooldown mức grid (khi `cooldown_minutes` > 0).
- **`grid_pause_v12.json`** – Pause do consecutive loss.
- **`last_exit_time_v12.json`** – Thời điểm đóng chu kỳ (basket TP) để áp dụng cooldown 20 phút.

Tất cả nằm trong thư mục chứa `strategy_grid_step_v12.py`.

---

## 10. Log

- **Giờ:** `Giờ=HH:MM(MT5_server)` hoặc `(local_UTC)` tùy nguồn thời gian (chỉ để tham khảo, không dùng cho điểm).
- **EntryScore:** `EntryScore=X (A=... B=... C=... D=... E=...)` với A=range, B=EMA, C=hụt lực, D=volatility, E=mean-reversion.
- **Step:** `Step(tính được)=...` kèm `step_raw`, `atr_m5`, `ratio`, `adj`, `[min, max]`.
- **Block:** Khi không start in lý do: `price_mid_range`, `breakout_m5`, `breakout_3bars`, `breakout_range`, `trend_strong`, `cooldown_after_exit`, `atr_quá_nóng`, `score_low`, `score_probe`, `score_below_start`, `no_data`.

---

## 11. DB & strategy name

- Bảng: `orders`, `grid_pending_orders` với `strategy_name` = giá trị từ config (`parameters.strategy_name`), mặc định `Grid_Step_V12`.
- Comment MT5: `GridStep_V12` (hoặc derived từ strategy_name).
- Để chạy nhiều instance (vd. symbol khác nhau), đặt `magic` và `strategy_name` khác nhau trong từng config.

---

## 12. Tóm tắt rule (bản ngắn)

- **Lệnh chờ:** Chỉ 1 BUY STOP + 1 SELL STOP; khi có lệnh khớp → hủy ngay lệnh pending còn lại.
- **Hard Block:** Giá giữa range; breakout mạnh; trend mạnh (3 nến cùng màu + EMA50 dốc cùng hướng); chưa hết cooldown; ATR quá nóng.
- **EntryScore:** A=range (+2/+1), B=EMA (+1/+1), C=hụt lực (max +2), D=vol (+1/0/-1), E=mean-reversion (max +2).
- **Start:** Score ≥ 6 (config `entry_score_start`); 4–5 = probe (hiện tại không start); ≤3 = không start.
- **Step:** `step_raw = atr_m5 * k_atr`, clamp [step_min, step_max], điều chỉnh theo volatility và (tùy chọn) trend/sideway.
