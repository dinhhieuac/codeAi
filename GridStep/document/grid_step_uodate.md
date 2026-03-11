# Danh sách nâng cấp chiến thuật Grid Step theo độ ưu tiên

Dưới đây là danh sách nâng cấp theo **độ ưu tiên thực chiến**, tức là ưu tiên những thứ **giảm chết vì whipsaw / lỗi cấu trúc / lỗi vận hành** trước, rồi mới tới tối ưu lợi nhuận.

# Ưu tiên 1 — Bắt buộc nâng cấp trước

## 1. Tách `grid_step` khỏi `SL/TP`
**Mức ưu tiên:** cao nhất

Hiện tại một biến đang làm 2 việc:

- khoảng cách đặt lệnh
- khoảng cách SL/TP

Đây là nút thắt lớn nhất của cả chiến lược.

### Vì sao phải tách ngay
Nếu giữ chung:
- muốn vào dày hơn → phải giảm SL/TP
- muốn SL rộng hơn để bớt nhiễu → phải giảm tần suất vào
- không tối ưu được expectancy

### Nên tách thành
- `grid_step_price`
- `sl_price`
- `tp_price`

Hoặc tối thiểu:
- `grid_step_price`
- `sl_tp_price`

### Lợi ích
- tối ưu được tần suất vào lệnh độc lập với risk/reward
- dễ test các kiểu:
  - step 5, SL 5, TP 7
  - step 5, SL 4, TP 6
  - step 3, SL 5, TP 6

Đây là nâng cấp có tác động lớn nhất tới **bản chất lời/lỗ**.

---

## 2. Thêm cơ chế chống re-entry sau stop-out
**Mức ưu tiên:** rất cao

Cooldown hiện tại giúp giảm spam cùng mức, nhưng chưa đánh trúng gốc.

### Vấn đề gốc
Sau khi vừa SL, bot có thể:
- quay lại đúng mức cũ
- hoặc đảo chiều rất nhanh quanh vùng vừa chứng minh là nhiễu

### Nên thêm
Một lớp “re-arm condition” sau stop-out, ví dụ:

- sau BUY bị SL, không cho đặt lại BUY ở cụm đó cho tới khi giá đi xuống thêm 1 step rồi mới xét lại
- sau SELL bị SL, không cho đặt lại SELL ở cụm đó cho tới khi giá đi lên thêm 1 step rồi mới xét lại

Hoặc đơn giản hơn:
- lưu `last_stopped_side`, `last_stop_level`
- chỉ cho phép tái vũ trang khi giá đã rời vùng đó đủ xa

### Lợi ích
- giảm whipsaw rõ rệt
- giảm loss cluster
- giảm cảm giác “vừa thua xong vào lại đúng chỗ đó”

Nếu chỉ được chọn 1 nâng cấp ngoài việc tách step/SLTP, thì đây là cái nên làm đầu tiên.

---

## 3. Sửa logic consecutive loss trong multi-step cho tách biệt hoàn toàn từng step
**Mức ưu tiên:** rất cao

Nếu nhiều step đang dùng chung:
- symbol
- magic

thì thống kê lỗ liên tiếp có thể bị trộn.

### Cần làm
Mỗi step phải có định danh riêng để thống kê:
- magic riêng theo step, hoặc
- filter theo comment rõ ràng, hoặc
- lấy DB làm nguồn chuẩn theo `strategy_name`

### Khuyến nghị
Trong multi-step:
- `Grid_Step_2` phải pause theo lịch sử của chính nó
- `Grid_Step_5` không được bị ảnh hưởng bởi lệnh lỗ của step 2/3/4

### Lợi ích
- tránh pause sai
- tránh đánh giá sai hiệu suất từng kênh
- số liệu dashboard sạch hơn

---

## 4. Làm cứng logic xử lý fill/cancel để chống race condition
**Mức ưu tiên:** rất cao

Trong market nhanh, có thể xảy ra:
- một lệnh khớp
- lệnh còn lại chưa kịp hủy
- rồi cả hai cùng khớp

### Cần nâng cấp
Phải xử lý được các tình huống:
- cả BUY STOP và SELL STOP cùng fill
- pending biến mất nhưng chưa map được position chắc chắn
- position khớp rồi SL/TP gần như ngay lập tức trước vòng lặp sau

### Nên bổ sung
- state machine rõ hơn cho từng pending
- log transaction-level
- đối chiếu bằng deal history thay vì suy luận quá nhiều từ “pending biến mất”
- cơ chế “recovery sync” khi state không khớp DB/MT5

### Lợi ích
- bot live ổn định hơn nhiều
- giảm lỗi âm thầm kiểu DB nghĩ A nhưng MT5 đang là B

---

# Ưu tiên 2 — Nâng cấp mạnh về chất lượng giao dịch

## 5. Thay `round(anchor / step)` bằng quy tắc neo grid rõ ràng hơn
**Mức ưu tiên:** cao

Hiện tại ref theo nearest grid có thể khiến:
- lệnh không đối xứng quanh giá
- bias khó đoán khi anchor nằm giữa 2 mức
- phụ thuộc cách round

### Nên cân nhắc 2 hướng

### Hướng A: giữ “nearest grid” nhưng tự định nghĩa rounding
Không dùng `round()` mặc định.  
Dùng quy tắc rõ ràng, nhất quán.

### Hướng B: dùng grid theo hướng thị trường hiện tại
Ví dụ:
- BUY level = mức grid phía trên gần nhất
- SELL level = mức grid phía dưới gần nhất

Tức là neo theo:
- `floor` cho một bên
- `ceil` cho bên kia

Cách này thường trực quan hơn “round về mức gần nhất”.

### Lợi ích
- entry behavior dễ hiểu hơn
- giảm các trường hợp đặt lệch khó giải thích

---

## 6. Thêm xác nhận breakout thay vì chỉ đặt stop thuần
**Mức ưu tiên:** cao

Hiện tại chỉ cần giá quét qua stop là vào.  
Điều này rất dễ dính wick và false break.

### Có thể thêm xác nhận kiểu price-action, không cần indicator
Ví dụ:
- chỉ coi là hợp lệ nếu giá vượt level thêm `entry_buffer`
- hoặc giữ trên/dưới level tối thiểu X giây
- hoặc chỉ đặt lại nếu giá đóng qua level

### Tham số gợi ý
- `breakout_buffer_price`
- `breakout_hold_seconds`

### Lợi ích
- giảm fill bởi nhiễu
- giảm số lệnh chất lượng thấp
- rất hữu ích với XAU và BTC khi giật mạnh

---

## 7. Tách risk control toàn bot khỏi risk control từng step
**Mức ưu tiên:** cao

Hiện tại các step tương đối độc lập, nhưng thực tế chúng cùng phơi nhiễm trên một symbol.

### Nên thêm lớp portfolio-level
- `max_total_positions_per_symbol`
- `max_total_floating_loss`
- `max_daily_loss`
- `max_simultaneous_pending`
- emergency pause nếu spread/slippage bất thường

### Lợi ích
- chặn drawdown dây chuyền khi multi-step cùng sai
- tránh ảo giác “mỗi step nhỏ nên tổng là an toàn”

---

## 8. Chuẩn hóa đơn vị cấu hình
**Mức ưu tiên:** cao

Hiện tại có chỗ dùng:
- giá
- point
- phút

rất dễ nhầm.

### Nên làm
Chọn một chuẩn rõ ràng cho mọi tham số:
- hoặc toàn bộ theo `price`
- hoặc tách cực rõ tên biến:
  - `min_distance_points`
  - `spread_max_price`
  - `grid_step_price`

### Cần làm thêm
Khi khởi động bot:
- in ra toàn bộ quy đổi thực tế
- ví dụ `min_distance_points=5 => 0.05 price`

### Lợi ích
- tránh cấu hình sai âm thầm
- dễ audit, dễ backtest, dễ so sánh XAU/BTC

---

# Ưu tiên 3 — Tăng chất lượng expectancy

## 9. Cho phép TP khác SL
**Mức ưu tiên:** trung bình-cao

Sau khi tách step khỏi SL/TP, bước tiếp theo là cho phép:
- RR không còn cứng 1:1

### Ví dụ
- SL = 1 step
- TP = 1.2 step hoặc 1.5 step

Hoặc:
- SL = 0.8 step
- TP = 1.2 step

### Tác dụng
Nếu bot đang thắng nhờ trend continuation, thì TP lớn hơn SL có thể tốt hơn 1:1.  
Ngược lại, nếu bot thắng nhờ hit rate cao, có thể giữ TP thấp hơn nhưng win-rate cao hơn.

Không test cái này thì chưa biết edge thật nằm ở đâu.

---

## 10. Thay cooldown “sau khi đặt lệnh” bằng cooldown “sau khi stop-out” hoặc tách 2 loại cooldown
**Mức ưu tiên:** trung bình-cao

Hiện tại cooldown ghi sau khi đặt thành công.  
Điều này có ích, nhưng hơi thô.

### Nên tách thành 2 loại
- `placement_cooldown`: chống spam đặt lệnh ở cùng mức
- `stopout_cooldown`: chống vào lại vùng vừa thua

Trong đó `stopout_cooldown` quan trọng hơn.

### Lợi ích
- đúng bệnh hơn
- giảm việc chặn nhầm các setup chưa từng gây lỗ

---

## 11. Nâng cấp anchor logic
**Mức ưu tiên:** trung bình

Hiện tại anchor = giá mở của position mới nhất.  
Cách này bám momentum gần nhất, nhưng bỏ qua inventory tổng.

### Có thể thử các biến thể
- anchor = VWAP của các position đang mở trong step
- anchor = mức grid cuối cùng đã fill
- anchor = extreme gần nhất theo hướng position
- anchor = giá thị trường nhưng có hysteresis

### Mục tiêu
Để bot bớt bị “lôi” hoàn toàn bởi lệnh mới nhất, nhất là khi đang có nhiều position cùng phía.

---

## 12. Thêm time/session filter
**Mức ưu tiên:** trung bình

Chiến thuật breakout stop rất nhạy với thời điểm trong ngày.

### Nên lọc theo phiên
Ví dụ:
- tránh giờ rollover / spread xấu
- tránh phút quanh tin lớn
- chỉ chạy phiên London/NY overlap cho XAU
- với BTC có thể cần logic khác

Không cần indicator, chỉ cần filter theo thời gian cũng đã giảm nhiễu khá nhiều.

---

# Ưu tiên 4 — Nâng cấp để vận hành và đánh giá tốt hơn

## 13. Làm dashboard thống kê đúng “bản chất chiến lược”
**Mức ưu tiên:** trung bình

Cần thêm các chỉ số thay vì chỉ nhìn PnL tổng:

- win rate theo step
- expectancy theo step
- average slippage
- số lần re-entry cùng level
- số cụm lỗ liên tiếp
- PnL theo session
- PnL theo spread regime
- ratio TP/SL/basket-close
- thời gian giữ lệnh trung bình

Không có các thống kê này thì rất khó biết bot đang chết vì:
- step sai
- spread
- whipsaw
- execution
- hay portfolio overstack

---

## 14. Tách magic number cho từng step / từng symbol / từng script
**Mức ưu tiên:** trung bình

Đây gần như là hạ tầng bắt buộc nếu muốn live sạch.

Ví dụ:
- XAU step 2 một magic
- XAU step 5 một magic
- BTC step 5 một magic

### Lợi ích
- history sạch
- pause sạch
- sync sạch
- dễ recovery khi DB lệch

---

## 15. Thêm chế độ “degraded mode” khi execution xấu
**Mức ưu tiên:** trung bình

Ví dụ tự pause nếu:
- spread tăng đột ngột liên tục
- slippage trung bình vượt ngưỡng
- tỷ lệ fill bất thường
- có nhiều lỗi gửi lệnh liên tiếp

Hiện tại có “5 lỗi gửi lệnh liên tiếp thì nghỉ 2 phút”, tốt nhưng còn đơn giản.

---

## 16. Ghi nhận deal-level từ MT5 history thay vì chỉ order/position level
**Mức ưu tiên:** trung bình

Khi cần phân tích sâu live:
- fill price thực
- slippage
- partial fill
- close reason
- commission/swap

đều nên lấy từ deal history chuẩn.

Đây rất quan trọng nếu muốn đánh giá chiến lược thật sự, chứ không chỉ đánh giá logic lý thuyết.

---

# Ưu tiên 5 — Tối ưu nâng cao, làm sau

## 17. Thử adaptive step theo volatility regime
**Mức ưu tiên:** thấp hơn

Ví dụ:
- volatility thấp → step nhỏ hơn
- volatility cao → step lớn hơn

Nhưng đây là nâng cấp làm sau, vì nếu nền tảng chưa ổn thì adaptive chỉ làm hệ phức tạp hơn.

---

## 18. Thử phân cụm step thay vì chạy dải dày `[2,3,4,5,6,7]`
**Mức ưu tiên:** thấp hơn

Thay vì chạy dày, có thể chỉ giữ vài step đại diện:
- fast
- medium
- slow

Ví dụ:
- `[3,5,8]` thay vì `[2,3,4,5,6,7]`

Lợi ích:
- giảm tương quan nội bộ
- giảm overtrading
- dễ phân tích hiệu quả từng lớp

---

## 19. Xem xét partial take profit hoặc staged exit
**Mức ưu tiên:** thấp hơn

Ví dụ:
- chốt một phần ở 1 step
- phần còn lại theo basket hoặc TP xa hơn

Nhưng cái này nên làm sau khi bạn đã xác định edge thật sự nằm ở đâu.

---

# Thứ tự triển khai mình khuyên

Nếu phải làm theo đúng thứ tự để hiệu quả nhất, mình khuyên:

### Giai đoạn 1
1. Tách `grid_step` khỏi `SL/TP`
2. Thêm anti-reentry sau stop-out
3. Sửa consecutive-loss tách riêng từng step
4. Làm cứng sync/fill/cancel chống race condition

### Giai đoạn 2
5. Đổi logic ref/rounding cho rõ ràng
6. Thêm breakout confirmation bằng price-only
7. Thêm risk cap toàn bot / toàn symbol
8. Chuẩn hóa toàn bộ đơn vị cấu hình

### Giai đoạn 3
9. Cho TP khác SL
10. Tách stopout-cooldown khỏi placement-cooldown
11. Nâng cấp anchor logic
12. Thêm time/session filter

### Giai đoạn 4
13. Nâng cấp dashboard thống kê
14. Tách magic riêng cho từng step
15. Thêm degraded mode theo execution
16. Ghi deal-level analytics

### Giai đoạn 5
17. Adaptive step
18. Giảm tương quan multi-step
19. Partial exit / staged exit

# Kết luận ngắn gọn

Nếu chỉ chọn **3 việc quan trọng nhất**, mình sẽ chọn:

1. **Tách grid step khỏi SL/TP**  
2. **Chặn vào lại sau stop-out bằng cơ chế riêng, không chỉ cooldown hiện tại**  
3. **Làm sạch multi-step và race condition trong live execution**

Ba việc này tác động trực tiếp tới:
- expectancy
- whipsaw
- độ ổn định khi chạy thật