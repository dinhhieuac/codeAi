# Grid Step Bot — Danh sách nâng cấp ưu tiên cho dev

## Mục tiêu
Giảm **whipsaw**, giảm lỗi **live execution**, và tăng khả năng tối ưu **expectancy**.  
Ưu tiên sửa các lỗi cấu trúc trước, rồi mới tối ưu hiệu suất.

---

## Ưu tiên P1 — Phải làm trước

### 1) Tách `grid_step` khỏi `SL/TP`
**Hiện trạng:** `step` đang dùng chung cho:
- khoảng cách grid
- khoảng cách SL/TP

**Cần sửa:**
- thêm config:
  - `grid_step_price`
  - `sl_price`
  - `tp_price`

**Lý do:**
- hiện không thể tối ưu entry frequency và risk/reward độc lập
- đây là nút thắt lớn nhất của chiến lược

---

### 2) Thêm anti-reentry sau stop-out
**Hiện trạng:** vừa SL xong có thể vào lại cùng vùng rất nhanh

**Cần sửa:**
- lưu:
  - `last_stop_side`
  - `last_stop_level`
  - `last_stop_time`
- không cho re-arm cùng phía tại vùng vừa SL cho tới khi giá đi xa thêm tối thiểu 1 step hoặc hết cooldown riêng

**Lý do:**
- đây là lớp chống whipsaw quan trọng nhất
- cooldown hiện tại chưa đủ

---

### 3) Tách riêng consecutive-loss theo từng step
**Hiện trạng:** nếu dùng chung symbol/magic, lịch sử lỗ có thể bị trộn giữa các step

**Cần sửa:**
- mỗi step có `magic` riêng hoặc filter riêng theo `strategy_name/comment`
- pause phải tính độc lập cho từng step

**Lý do:**
- tránh pause sai
- tránh nhiễu thống kê giữa các kênh

---

### 4) Làm cứng logic fill/cancel/sync
**Hiện trạng:** live có thể gặp:
- 1 lệnh fill, lệnh kia chưa kịp hủy
- cả BUY STOP và SELL STOP cùng fill
- pending biến mất nhưng map position sai

**Cần sửa:**
- state machine rõ cho pending lifecycle
- recovery sync khi DB != MT5
- ưu tiên đối chiếu bằng deal history thay vì suy luận từ pending biến mất

**Lý do:**
- đây là lỗi vận hành nguy hiểm nhất khi chạy thật

---

## Ưu tiên P2 — Nâng chất lượng giao dịch

### 5) Sửa cách tính `ref`
**Hiện trạng:** `round(anchor / step)` có thể gây bias và hành vi khó đoán

**Cần sửa:**
- không dùng `round()` mặc định
- chọn quy tắc rõ ràng:
  - nearest với custom rounding, hoặc
  - `buy_level = ceil`, `sell_level = floor`

---

### 6) Thêm breakout confirmation
**Hiện trạng:** stop order bị quét bởi wick/false break

**Cần sửa:**
- thêm config:
  - `breakout_buffer_price`
  - `breakout_hold_seconds`
- chỉ vào khi breakout đủ điều kiện xác nhận

**Lý do:**
- giảm lệnh chất lượng thấp
- giảm false trigger

---

### 7) Thêm risk cap toàn bot / toàn symbol
**Cần sửa:**
- `max_total_positions_per_symbol`
- `max_total_floating_loss`
- `max_daily_loss`
- `max_simultaneous_pending`

**Lý do:**
- multi-step không thật sự độc lập
- cần chặn drawdown dây chuyền

---

### 8) Chuẩn hóa đơn vị config
**Hiện trạng:** đang trộn `price`, `point`, `minutes`

**Cần sửa:**
- đổi tên config rõ đơn vị:
  - `grid_step_price`
  - `spread_max_price`
  - `min_distance_points`
- lúc khởi động bot log rõ quy đổi thực tế

**Lý do:**
- tránh cấu hình sai âm thầm

---

## Ưu tiên P3 — Tối ưu expectancy

### 9) Cho phép TP khác SL
**Cần sửa:**
- hỗ trợ RR không cố định 1:1

**Ví dụ:**
- `SL=5`, `TP=7`
- `SL=4`, `TP=6`

---

### 10) Tách `placement_cooldown` và `stopout_cooldown`
**Cần sửa:**
- cooldown sau đặt lệnh
- cooldown riêng sau stop-out

**Lý do:**
- đúng bệnh hơn cooldown hiện tại

---

### 11) Nâng cấp anchor logic
**Có thể thử:**
- anchor = last filled grid level
- anchor = VWAP position mở
- anchor = market price + hysteresis

**Lý do:**
- tránh để bot bị kéo hoàn toàn bởi position mới nhất

---

### 12) Thêm time/session filter
**Cần sửa:**
- tránh rollover
- tránh giờ spread xấu
- có thể ưu tiên session tốt cho từng symbol

---

## Ưu tiên P4 — Hạ tầng phân tích và vận hành

### 13) Tách magic riêng cho từng step
### 14) Ghi deal-level analytics từ MT5 history
### 15) Thêm degraded mode khi spread/slippage/lỗi gửi lệnh tăng mạnh
### 16) Nâng dashboard với:
- win rate theo step
- expectancy theo step
- slippage
- re-entry count
- loss cluster
- PnL theo session / spread regime

---

## Thứ tự triển khai đề xuất

### Phase 1
1. Tách `grid_step` khỏi `SL/TP`
2. Thêm anti-reentry sau stop-out
3. Tách consecutive-loss theo từng step
4. Cứng hóa fill/cancel/sync

### Phase 2
5. Sửa logic `ref`
6. Thêm breakout confirmation
7. Thêm risk cap toàn bot
8. Chuẩn hóa config units

### Phase 3
9. TP khác SL
10. Tách 2 loại cooldown
11. Nâng anchor logic
12. Thêm session filter

### Phase 4
13. Magic riêng từng step
14. Deal-level analytics
15. Degraded mode
16. Dashboard nâng cao

---

## Chốt lại: 3 việc quan trọng nhất
1. **Tách grid step khỏi SL/TP**
2. **Thêm anti-reentry sau stop-out**
3. **Sửa multi-step + live execution sync**

Nếu chưa làm 3 việc này, bot rất dễ:
- whipsaw liên tục
- pause sai
- lệch trạng thái DB/MT5 khi chạy thật