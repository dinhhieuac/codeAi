# Đặc tả triển khai: Chop Pause cho Grid Step Bot

Tài liệu này mô tả chi tiết cơ chế **Pause step khi phát hiện mẫu chop trong vài lệnh gần nhất** để dev có thể triển khai code trực tiếp vào bot hiện tại.

Mục tiêu của cơ chế này là:

- phát hiện môi trường giá **nhiễu / sideways / whipsaw**
- **tạm dừng riêng từng step** khi bot đang bị quay trong vùng giá hẹp
- tránh tiếp tục đặt lệnh trong môi trường có xác suất stop-out cao
- **không dùng indicator**
- giữ nguyên bản chất chiến lược Grid Step

---

# 1. Bài toán cần giải quyết

Trong Grid Step Bot, thua lỗ lớn thường không đến từ một lệnh đơn lẻ mà đến từ một **cụm lệnh gần nhau** có đặc điểm:

- đa số là lỗ
- entry nằm trong một vùng giá hẹp
- BUY/SELL bị khớp luân phiên rồi dừng lỗ
- thị trường không đi đủ xa để tạo nhịp thắng sạch

Ví dụ với `step = 5`:

- BUY 5005 -> SL
- SELL 4995 -> SL
- BUY 5000 -> TP nhỏ hoặc SL
- SELL 4995 -> SL

Nếu bot tiếp tục giao dịch trong trạng thái này thì rất dễ bị:

- whipsaw liên tục
- lỗ dày trong thời gian ngắn
- hao hụt do execution/slippage/spread

Do đó cần thêm một lớp logic:

> Nếu vài lệnh đóng gần nhất cho thấy bot đang bị xay trong cùng một vùng hẹp và đa số là lỗ, thì pause riêng step đó trong một khoảng thời gian.

---

# 2. Khái niệm “chop” trong cơ chế này

Trong phạm vi của bot này, **chop** là trạng thái mà:

1. Trong `N` lệnh đóng gần nhất của cùng `strategy_name`, số lệnh lỗ đủ lớn.
2. Các `entry_price` của các lệnh đó nằm trong một vùng giá đủ hẹp.

Nói đơn giản:

- bot đang giao dịch đi giao dịch lại quanh cùng vài mức grid
- nhưng hiệu quả thấp, chủ yếu là stop-out

Cơ chế này **không cố dự báo xu hướng**, mà chỉ trả lời:

> Môi trường vài lệnh gần đây có đủ xấu để nên đứng ngoài tạm thời hay không?

---

# 3. Phạm vi áp dụng

Cơ chế Chop Pause áp dụng theo **từng step / từng strategy_name**, không áp dụng toàn bot.

Ví dụ khi chạy multi-step:

- `Grid_Step_3`
- `Grid_Step_5`
- `Grid_Step_7`

thì mỗi step phải được đánh giá độc lập.

Có thể xảy ra tình huống:

- `Grid_Step_5` đang chop mạnh -> pause
- `Grid_Step_7` vẫn giao dịch bình thường

Đây là hành vi mong muốn.

---

# 4. Cấu hình đề xuất

Thêm các tham số sau vào `parameters`:

```json
{
  "chop_pause_enabled": true,
  "chop_window_trades": 4,
  "chop_loss_count": 3,
  "chop_band_steps": 2,
  "chop_pause_minutes": 15,
  "chop_require_closed_count_exact": true
}