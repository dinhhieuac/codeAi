# Grid Step XAU - Rule Scoring Entry và Rule Tính Step

> Áp dụng cho XAUUSD, khung giờ trong file gốc là UTC+0.  
> Mục tiêu: chỉ cho bot start khi vị trí đẹp và tự điều chỉnh Step theo biến động.

---

## 1) Biến đầu vào cần có

- `hour_utc`: giờ hiện tại theo UTC+0
- `price`: giá hiện tại
- `ema50_m15`: EMA50 trên M15
- `atr_m5`: ATR(20) trên M5
- `atr_m15`: ATR(20) trên M15
- `range_high_3h`: đỉnh của 3 giờ gần nhất
- `range_low_3h`: đáy của 3 giờ gần nhất
- `last3_m15_bars`: 3 nến M15 gần nhất
- `last_exit_time`: thời gian bot vừa đóng chu kỳ gần nhất
- `step_base`: step gốc
- `pip_value`: đơn vị pip của sản phẩm đang dùng

---

## 2) Khung giờ ON/OFF cho XAU (UTC+0)

### Khung ON mạnh
- 10:00-11:59
- 14:00-14:59
- 17:00-18:59

### Khung ON phụ
- 02:00-02:59
- 23:00-23:59

### Khung OFF mạnh
- 13:00-13:59
- 15:00-16:59
- 19:00-19:59
- 08:00-09:59
- 22:00-22:59

### Khung trung tính
- Các giờ còn lại

---

## 3) Hard Block - Dính là không được start

Chỉ cần dính 1 điều kiện dưới đây thì `ALLOW_START = false`.

### Block 1: Giờ OFF mạnh
Nếu `hour_utc` nằm trong:
- 13:00-13:59
- 15:00-16:59
- 19:00-19:59
- 08:00-09:59
- 22:00-22:59

=> Không start.

### Block 2: Breakout mạnh
Nếu 1 trong các điều kiện sau đúng:
- Nến M5 hiện tại có biên độ > `1.8 * atr_m5`
- Hoặc tổng biên độ 3 nến M15 gần nhất > `3.0 * step_base`
- Hoặc giá vừa phá `range_high_3h` hoặc `range_low_3h` với độ vượt > `0.5 * step_base`

=> Không start.

### Block 3: Đang trend mạnh
Nếu:
- 3 nến M15 gần nhất cùng màu
- Và tổng thân nến 3 cây > `2.5 * step_base`

=> Không start.

### Block 4: Giá ở giữa range
Tính:
- `range_size = range_high_3h - range_low_3h`
- `upper_zone = range_low_3h + range_size * 0.67`
- `lower_zone = range_low_3h + range_size * 0.33`

Nếu:
- `price > lower_zone`
- và `price < upper_zone`

=> Giá đang ở giữa range, không start.

### Block 5: Chưa đủ cooldown sau chu kỳ trước
Nếu:
- `current_time - last_exit_time < 20 phút`

=> Không start.

---

## 4) Entry Score - Bộ chấm điểm vào lệnh

Khởi tạo:
- `EntryScore = 0`

### Nhóm A - Điểm theo giờ

#### A1. Giờ ON mạnh
Nếu `hour_utc` thuộc:
- 10:00-11:59
- 14:00-14:59
- 17:00-18:59

=> `EntryScore += 2`

#### A2. Giờ ON phụ
Nếu `hour_utc` thuộc:
- 02:00-02:59
- 23:00-23:59

=> `EntryScore += 1`

#### A3. Giờ trung tính
=> `EntryScore += 0`

---

### Nhóm B - Điểm theo vị trí trong range

Tính:
- `range_size = range_high_3h - range_low_3h`
- `top_zone = range_low_3h + range_size * 0.67`
- `bottom_zone = range_low_3h + range_size * 0.33`

#### B1. Giá ở mép trên hoặc mép dưới range
Nếu:
- `price >= top_zone`
- hoặc `price <= bottom_zone`

=> `EntryScore += 2`

#### B2. Giá ở rất sát mép range
Nếu:
- `price >= range_low_3h + range_size * 0.85`
- hoặc `price <= range_low_3h + range_size * 0.15`

=> `EntryScore += 1` thêm

---

### Nhóm C - Điểm theo độ lệch khỏi vùng cân bằng

Tính:
- `distance_ema = abs(price - ema50_m15)`

#### C1. Lệch đủ xa
Nếu:
- `distance_ema >= 1.0 * step_base`

=> `EntryScore += 1`

#### C2. Lệch đẹp
Nếu:
- `distance_ema >= 1.5 * step_base`

=> `EntryScore += 1` thêm

---

### Nhóm D - Điểm theo dấu hiệu hụt lực

#### D1. Nến hiện tại nhỏ lại
Nếu biên độ nến M5 hiện tại < biên độ nến M5 trước đó
=> `EntryScore += 1`

#### D2. Có râu nến rõ
Nếu râu nến ngược hướng chiếm >= 35% tổng biên độ nến M5 hoặc M15
=> `EntryScore += 1`

#### D3. Không phá được đỉnh/đáy cũ
Nếu giá test lại vùng cao/thấp gần nhất nhưng không vượt tiếp
=> `EntryScore += 1`

> Tối đa nhóm D nên cộng không quá `2 điểm`.

---

### Nhóm E - Điểm theo volatility

#### E1. ATR bình thường
Nếu:
- `atr_m5 <= 1.2 * median_atr_m5_lookback`

=> `EntryScore += 1`

#### E2. ATR hơi cao
Nếu:
- `1.2 * median_atr_m5_lookback < atr_m5 <= 1.5 * median_atr_m5_lookback`

=> `EntryScore += 0`

#### E3. ATR quá cao
Nếu:
- `atr_m5 > 1.5 * median_atr_m5_lookback`

=> `EntryScore -= 1`

---

## 5) Ngưỡng quyết định start

### Rule quyết định
- Nếu có `Hard Block` => `START = false`
- Nếu không có `Hard Block`, xét `EntryScore`

### Ngưỡng
- `EntryScore >= 6` => Start bình thường
- `EntryScore = 4 hoặc 5` => Chỉ start lot nhỏ hoặc bỏ qua
- `EntryScore <= 3` => Không start

### Rule gợi ý
- Start chuẩn: `EntryScore >= 6`
- Start thăm dò: `EntryScore = 5` và không có tín hiệu breakout
- Không start: còn lại

---

## 6) Rule tính Step động

Mục tiêu:
- Volatility thấp => Step nhỏ hơn
- Volatility cao => Step lớn hơn
- Nhưng không để Step quá nhỏ hoặc quá lớn

### 6.1 Công thức gốc
Tính step từ ATR:

`step_raw = atr_m5 * k_atr`

Trong đó:
- `k_atr` gợi ý từ `0.8` đến `1.2`
- giá trị khởi điểm nên thử: `k_atr = 1.0`

### 6.2 Giới hạn Step
Đặt:
- `step_min = step_base * 0.8`
- `step_max = step_base * 1.8`

Sau đó:
- Nếu `step_raw < step_min` => `step = step_min`
- Nếu `step_raw > step_max` => `step = step_max`
- Ngược lại => `step = step_raw`

---

## 7) Rule chỉnh Step theo trạng thái thị trường

### Case A - Volatility thấp
Nếu:
- `atr_m5 < 0.9 * median_atr_m5_lookback`

=>  
- `step = max(step_min, step_raw * 0.9)`

Ý nghĩa:
- thị trường chậm
- có thể thu hẹp step nhẹ để grid bắt nhịp hồi tốt hơn

### Case B - Volatility bình thường
Nếu:
- `0.9 <= atr_m5 / median_atr_m5_lookback <= 1.2`

=>  
- `step = step_raw`

### Case C - Volatility cao
Nếu:
- `1.2 < atr_m5 / median_atr_m5_lookback <= 1.5`

=>  
- `step = min(step_max, step_raw * 1.15)`

Ý nghĩa:
- thị trường nhanh hơn
- phải nới step để tránh nhồi lệnh quá dày

### Case D - Volatility quá cao
Nếu:
- `atr_m5 / median_atr_m5_lookback > 1.5`

=>  
- Không start  
hoặc  
- `step = step_max` và chỉ chạy khi `EntryScore >= 7`

---

## 8) Rule tăng Step khi có xu hướng

Nếu:
- EMA50 M15 đang dốc rõ
- hoặc 3 nến M15 gần nhất nghiêng cùng 1 hướng nhưng chưa tới mức hard block

=>  
- `step = step * 1.1 đến 1.2`

Ý nghĩa:
- nếu thị trường bắt đầu có hướng
- grid phải thưa ra để giảm tốc độ nhồi lệnh

---

## 9) Rule giảm Step khi thị trường sideway đẹp

Nếu:
- giá ở mép range
- ATR bình thường
- 3 nến M15 gần nhất xen kẽ, không trend rõ
- có dấu hiệu hụt lực

=>  
- `step = step * 0.9`

Nhưng vẫn phải đảm bảo:
- `step >= step_min`

---

## 10) Rule phối hợp EntryScore và Step

### Rule 1
Nếu:
- `EntryScore >= 7`
- và volatility bình thường

=>  
- dùng `step` chuẩn

### Rule 2
Nếu:
- `EntryScore = 6`
- nhưng ATR hơi cao

=>  
- tăng `step` thêm `10%`

### Rule 3
Nếu:
- `EntryScore = 4 hoặc 5`

=>  
- chỉ start nếu:
  - không có breakout
  - giá ở mép range rất rõ
  - và dùng `step >= step_base`

### Rule 4
Nếu:
- `EntryScore <= 3`

=>  
- không start, không tính tiếp

---

## 11) Bộ tham số khởi điểm gợi ý cho XAU Grid Step

- `step_base = 5`
- `k_atr = 1.0`
- `step_min = 4`
- `step_max = 9`
- `cooldown_after_exit = 20 phút`
- `lookback_range = 3 giờ`
- `atr_period_m5 = 20`
- `ema_period_m15 = 50`
- `EntryScore_start = 6`
- `EntryScore_probe = 5`

---

## 12) Pseudo Rule dạng IF-THEN

### Start filter
IF có hard block  
THEN không start

ELSE tính `EntryScore`

IF `EntryScore >= 6`  
THEN cho phép start

IF `EntryScore = 4 hoặc 5`  
THEN chỉ start lot nhỏ hoặc bỏ qua

IF `EntryScore <= 3`  
THEN không start

---

### Step filter
IF `atr_m5 / median_atr_m5_lookback < 0.9`  
THEN `step = max(step_min, atr_m5 * k_atr * 0.9)`

IF `0.9 <= atr_m5 / median_atr_m5_lookback <= 1.2`  
THEN `step = atr_m5 * k_atr`

IF `1.2 < atr_m5 / median_atr_m5_lookback <= 1.5`  
THEN `step = min(step_max, atr_m5 * k_atr * 1.15)`

IF `atr_m5 / median_atr_m5_lookback > 1.5`  
THEN không start  
hoặc chỉ start khi `EntryScore >= 7` và `step = step_max`

---

## 13) Bản cực ngắn để coder implement

### EntryScore
- Giờ ON mạnh: `+2`
- Giờ ON phụ: `+1`
- Giá ở mép range: `+2`
- Giá ở rất sát mép range: `+1`
- Cách EMA50 M15 >= 1 step: `+1`
- Cách EMA50 M15 >= 1.5 step: `+1`
- Có dấu hiệu hụt lực: `+1` đến `+2`
- ATR bình thường: `+1`
- ATR quá cao: `-1`

### Hard Block
- Giờ OFF
- Breakout mạnh
- Trend mạnh
- Giá giữa range
- Chưa hết cooldown

### Start
- `Score >= 6` => Start
- `4-5` => Probe hoặc skip
- `<= 3` => Skip

### Step
- `step_raw = atr_m5 * k_atr`
- clamp vào `[step_min, step_max]`
- volatility cao => nới step
- volatility thấp => thu step nhẹ
- trend rõ => tăng step thêm 10%-20%

---

## 14) Ghi chú quan trọng

- Bộ rule này là khung logic để lọc start tốt hơn, không phải đảm bảo thắng tuyệt đối.
- Nên backtest riêng cho:
  - `EntryScore threshold`
  - `k_atr`
  - `step_min`
  - `step_max`
  - `cooldown`
- Nếu bot chưa có đủ dữ liệu để tính VWAP hoặc volume, dùng EMA50 M15 làm vùng cân bằng là đủ để bắt đầu.
