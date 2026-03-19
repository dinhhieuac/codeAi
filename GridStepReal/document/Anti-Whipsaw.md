# Tài liệu kỹ thuật triển khai Anti-Whipsaw cho Grid Step Bot

## 1. Mục đích tài liệu

Tài liệu này mô tả chi tiết cách triển khai một lớp lọc **Anti-Whipsaw** cho bot giao dịch kiểu **Grid Step**.

Mục tiêu của lớp lọc này là:

- giảm các lệnh bị **thua lặp lại trong vùng sideway**
- hạn chế hiện tượng bot vừa SL xong lại vào đúng level cũ
- vẫn giữ được khả năng tham gia những đoạn giá đang cho chuỗi thắng
- không dùng indicator
- tận dụng trực tiếp dữ liệu lịch sử kết quả của chính bot

Tài liệu được viết theo kiểu **dev handoff**, nghĩa là có thể dùng trực tiếp để lập trình, kiểm thử và triển khai.

---

## 2. Bối cảnh bài toán

Bot Grid Step hiện hoạt động theo nguyên lý:

- chọn một `anchor`
- làm tròn ra `ref`
- đặt `BUY STOP` ở phía trên
- đặt `SELL STOP` ở phía dưới
- khi một lệnh khớp thì hủy lệnh còn lại
- dịch grid theo position vừa khớp
- đặt cặp pending mới

Trong điều kiện thị trường có xu hướng hoặc có follow-through đủ mạnh, mô hình này hoạt động tốt.

Tuy nhiên trong điều kiện sideway hẹp, bot có thể gặp hiện tượng:

1. khớp BUY tại một level
2. chạm SL
3. quay lại đúng level đó
4. lại khớp BUY tiếp
5. lại chạm SL
6. lặp lại nhiều lần

Hoặc bot có thể bị đảo qua lại:

- BUY lỗ
- SELL lỗ
- BUY lỗ
- SELL lỗ

Vấn đề này gọi là **whipsaw sideways**.

---

## 3. Mục tiêu triển khai Anti-Whipsaw

Lớp Anti-Whipsaw cần đạt các mục tiêu kỹ thuật sau:

### 3.1. Mục tiêu chính

Chặn những lệnh có xác suất cao thuộc nhóm:

- re-entry xấu
- cùng side + cùng level vừa thua
- zone quanh level đang chop
- step hiện tại đang vào chuỗi lỗ

### 3.2. Mục tiêu phụ

Không chặn mù tất cả lệnh sau khi thua. Cần giữ được các trường hợp:

- cùng zone nhưng đang có chuỗi TP
- level vừa có lịch sử thắng
- thị trường bắt đầu thoát sideway và cho follow-through

### 3.3. Ràng buộc

Triển khai phải:

- không phá logic Grid Step hiện có
- không thay đổi cách tính anchor/ref
- chỉ là lớp lọc trước khi đặt lệnh
- có thể bật/tắt bằng config
- có thể dry-run trước khi chặn thật
- có log đầy đủ để debug

---

## 4. Tổng quan giải pháp

Mỗi lệnh mới trước khi được đặt sẽ được tính một điểm gọi là:

- `WhipsawScore`

Điểm này được tính từ dữ liệu lịch sử gần đây của chính bot.

Nếu điểm quá cao, lệnh sẽ bị bỏ qua.

Nếu điểm thấp, lệnh vẫn được phép đặt như bình thường.

Giải pháp này có các ưu điểm:

- không dùng indicator
- bám đúng logic Grid Step
- dùng trực tiếp lịch sử Win/Loss của bot
- dễ triển khai
- dễ debug
- dễ tuning

---

## 5. Công thức chính thức

Với một lệnh sắp đặt tại:

- `step`
- `side`
- `level`

tính:

```text
WhipsawScore =
    3 * R_same30
  + 3 * L_same120
  - 1 * W_same120
  + 1 * L_zone60
  - 3 * W_zone60
  + 3 * C2


Quy tắc quyết định:
  Nếu WhipsawScore >= 5  => SKIP lệnh
  Nếu WhipsawScore <  5  => CHO PHÉP đặt lệnh
Đây là ngưỡng mặc định khuyến nghị để triển khai phiên bản đầu.

6. Ý nghĩa kỹ thuật của score
  WhipsawScore là điểm rủi ro của lệnh sắp đặt.
  Nó không phải:
    profit
    spread
    indicator
    xác suất toán học tuyệt đối
  Nó là một chỉ số nội bộ của bot để trả lời câu hỏi:
    Lệnh sắp đặt hiện tại có đang quá giống các lệnh vừa thua trong vùng sideway không?
  Hiểu đơn giản:
    dấu hiệu xấu thì cộng điểm
    dấu hiệu tốt thì trừ điểm
    tổng điểm càng cao thì càng dễ whipsaw
    tổng điểm càng thấp thì càng an toàn để vào lệnh

7. Định nghĩa chi tiết các biến
  7.1. R_same30
  Biến nhị phân.
  R_same30 = 1
  nếu:
  lệnh gần nhất tại cùng side + cùng level
  có kết quả là Loss
  và xảy ra trong 30 phút gần nhất
  Ngược lại:
  R_same30 = 0
  Ý nghĩa
  Đây là tín hiệu whipsaw mạnh nhất.
  Ví dụ:
  vừa BUY 70600 bị SL
  12 phút sau lại chuẩn bị BUY 70600
  thì đây là pattern rất xấu.
  Vì sao trọng số là 3
  Vì đây là dạng re-entry xấu rõ nhất và cần bị phạt mạnh.
  7.2. L_same120
    Số lệnh Loss của:
    cùng step
    cùng side
    cùng level
    trong 120 phút gần nhất
    Có chặn trần:
    L_same120 = min(số loss cùng side + level trong 120 phút, 3)
    Ý nghĩa
    Nếu đúng level đó đang thua lặp lại trong 2 giờ gần đây thì level đó đang xấu.
    Vì sao phải chặn trần
    Để score không tăng vô hạn khi một level bị giao dịch quá nhiều lần.
  7.3. W_same120
    Số lệnh Win của:
    cùng step
    cùng side
    cùng level
    trong 120 phút gần nhất
    Có chặn trần:
    W_same120 = min(số win cùng side + level trong 120 phút, 3)
    Ý nghĩa
    Nếu đúng level đó vừa có win, không nên khóa quá tay.
    Vì sao trọng số là -1
    Chỉ giảm nhẹ cảnh báo, không xóa sạch cảnh báo.
  7.4. L_zone60
    Số lệnh Loss trong zone quanh level hiện tại trong 60 phút gần nhất.
    Zone được định nghĩa như sau, với step = S:
    zone = [level - S, level + S]
    Ví dụ:
    step = 200
    level = 70600
    thì zone là:
    [70400, 70800]
    Có chặn trần:
    L_zone60 = min(số loss trong zone trong 60 phút, 3)
    Ý nghĩa
    Whipsaw không chỉ lặp ở một giá duy nhất mà thường xảy ra trong cả một cụm level.
  7.5. W_zone60
    Số lệnh Win trong zone đó trong 60 phút gần nhất
    W_zone60 = min(số win trong zone trong 60 phút, 3)
    Ý nghĩa
    Đây là biến quan trọng nhất để bảo vệ chuỗi thắng.
    Nếu zone đang có nhiều TP thì score phải giảm mạnh để bot không bị chặn mù.
    Vì sao trọng số là -3
    Vì cần ưu tiên giữ khả năng giao dịch ở những vùng đang có follow-through tốt.
  7.6. C2
    Biến nhị phân.
    C2 = 1
    nếu 2 lệnh đóng gần nhất của cùng step đều là Loss.
    Ngược lại:
    C2 = 0
    Ý nghĩa
    Đây là lớp phanh tổng quát ở cấp step.
    Ngay cả khi chưa đủ dữ liệu ở đúng same side + same level, việc vừa có 2 loss liên tiếp vẫn là dấu hiệu đáng cảnh giác.

8. Tại sao chọn trọng số như vậy
  Công thức:
  WhipsawScore =
      3 * R_same30
    + 3 * L_same120
    - 1 * W_same120
    + 1 * L_zone60
    - 3 * W_zone60
    + 3 * C2
  được xây theo logic sau:
  8.1. +3 * R_same30
    Phạt mạnh vì:
    vừa thua
    quay lại đúng level
    quay lại quá sớm
  8.2. +3 * L_same120
    Phạt mạnh vì đúng level đó đã chứng minh là đang xấu.
  8.3. -1 * W_same120
    Giảm nhẹ vì level đó vẫn có khả năng ăn được.
  8.4. +1 * L_zone60
    Phạt vừa phải vì cả vùng đang chop.
  8.5. -3 * W_zone60
    Giảm mạnh để không làm hỏng chuỗi thắng ở vùng đang tốt.
  8.6. +3 * C2
    Phạt mạnh vì step hiện tại vừa có dấu hiệu chuỗi lỗ.

9. Ví dụ tính score
  9.1. Ví dụ lệnh xấu
    Bot chuẩn bị đặt:
    BUY 70600
    Giả sử lịch sử gần đây như sau:
    lệnh gần nhất của BUY 70600 là Loss, cách hiện tại 20 phút
    R_same30 = 1
    trong 120 phút gần nhất:
    BUY 70600 có 1 Loss
    BUY 70600 có 0 Win
    L_same120 = 1
    W_same120 = 0
    trong zone 70400–70800 trong 60 phút gần nhất:
    có 2 Loss
    có 0 Win
    L_zone60 = 2
    W_zone60 = 0
    2 lệnh gần nhất của step đều là Loss
    C2 = 1
    Khi đó:
    WhipsawScore =
        3*1
      + 3*1
      - 1*0
      + 1*2
      - 3*0
      + 3*1
    = 11
    Kết luận:
    11 >= 5 => SKIP
  9.2. Ví dụ lệnh tốt
    Bot chuẩn bị đặt:
    SELL 72000
    Giả sử:
    không có loss gần đây ở SELL 72000
    R_same30 = 0
    trong 120 phút:
    0 Loss
    1 Win
    L_same120 = 0
    W_same120 = 1
    trong zone 71800–72200 trong 60 phút:
    0 Loss
    2 Win
    L_zone60 = 0
    W_zone60 = 2
    2 lệnh gần nhất không phải đều Loss
    C2 = 0
    Khi đó:
    WhipsawScore =
        3*0
      + 3*0
      - 1*1
      + 1*0
      - 3*2
      + 3*0
    = -7
    Kết luận:
    -7 < 5 => CHO PHÉP
10. Phạm vi tích hợp
  Lớp Anti-Whipsaw chỉ nên nằm ở giai đoạn:
  sau khi bot đã tính được buy_price và sell_price
  trước khi gọi hàm đặt pending order
  Nó không nên can thiệp vào:
  cách tính anchor
  cách tính ref
  cách tính SL/TP
  cách đồng bộ pending
  cách basket TP
  cách pause hiện có
  Như vậy rủi ro phá vỡ hệ thống sẽ thấp hơn.
11. Vị trí chèn trong strategy_grid_step_logic()
  Thứ tự khuyến nghị trong logic hiện tại:
  1.bot đồng bộ pending với MT5
  2.bot bảo đảm SL/TP cho position
  3.bot kiểm tra basket TP
  4.bot kiểm tra pause
  5.bot kiểm tra spread
  7.bot kiểm tra max positions
  8.bot kiểm tra đủ 2 pending chưa
  9.bot tính anchor
  10.bot tính ref
  11.bot tính buy_price, sell_price
  12.bot kiểm tra zone lock
  13.bot kiểm tra min distance
  14.bot kiểm tra cooldown
  15.bot tính WhipsawScore cho BUY và SELL
  16.bot skip phía có score cao
  17.bot đặt lệnh cho phía còn lại
    Lớp Anti-Whipsaw nên đặt gần cuối như vậy để:
      không thay đổi logic nền
      tận dụng toàn bộ các lớp bảo vệ đã có
      chỉ là cổng chặn cuối cùng trước khi gửi lệnh
 12. Chuẩn hóa level
  Trước khi thống kê lịch sử hoặc tính score, luôn phải chuẩn hóa giá về level đúng của step.
  Hàm chuẩn hóa:
    def normalize_level(price: float, step: float) -> float:
        return round(price / step) * step
  Ví dụ:
  step = 200
  price = 70613
  thì level chuẩn là:
    70600
  Lưu ý
  Tất cả các giá trong lịch sử phải được normalize theo cùng công thức.
  Nếu không, hệ thống có thể coi:
    70599.9
    70600
    70600.1
  là 3 level khác nhau.   

13. Định dạng dữ liệu đầu vào
  Hàm tính score cần một danh sách closed_orders.
  Mỗi record tối thiểu phải có:
  {
      "step": 200.0,
      "side": "BUY",
      "level": 70600.0,
      "result": "Win",
      "open_time": datetime(...),
  }
  Ý nghĩa từng field
    step: step hiện tại của strategy
    side: BUY hoặc SELL
    level: giá vào lệnh đã normalize
    result: Win hoặc Loss
    open_time: thời điểm mở lệnh

14. Nguồn dữ liệu
  Dữ liệu có thể lấy từ:
    bảng orders trong DB
    hoặc lịch sử MT5 đã sync vào DB
  Khuyến nghị lấy từ DB vì:
    dễ query
    dễ lọc theo account/strategy
    không phụ thuộc MT5 live ở thời điểm tính score
15. Mapping dữ liệu từ DB
  Giả sử record trong bảng orders có:
    open_price
    order_type
    profit
    open_time
    strategy_name
    symbol
    account_id
  thì mapping như sau:
  15.1. side
    Từ order_type:
    nếu chứa "BUY" thì side = "BUY"
    nếu chứa "SELL" thì side = "SELL"
  15.2. level
    Từ open_price, sau đó normalize:
    level = normalize_level(open_price, step)
  15.3. result
    profit > 0 => "Win"
    profit < 0 => "Loss"
    profit == 0 => có thể bỏ qua hoặc gán "Flat" rồi không tính
  15.4. open_time
    Dùng trực tiếp open_time
16. Yêu cầu lọc dữ liệu trước khi tính score
  Trước khi tính score, phải lọc lịch sử đúng theo:
    cùng symbol
    cùng account_id
    cùng strategy_name
    cùng step
  Không được lấy lẫn:
    symbol khác
    account khác
    strategy khác
    step khác
  Nếu bot chạy multi-step thì đây là điều bắt buộc.

17. Lưu ý đặc biệt khi chạy multi-step
  Nếu hệ thống chạy:
  Grid_Step_100
  Grid_Step_200
  Grid_Step_300
  thì mỗi step phải có lịch sử riêng để tính score.
  Không được gộp tất cả lại.
  Khuyến nghị dùng helper:
  def get_strategy_name_for_step(base_name: str, step: float) -> str:
      return f"{base_name}_{int(step) if float(step).is_integer() else step}"
  Ngoài ra, comment trên MT5 cũng nên mang step để dễ audit và debug.
  Ví dụ tốt:
  GridStep_200
  Ví dụ không tốt:
  GridStep
  vì không phân biệt được step.
18. Cấu trúc hàm cần triển khai
  Hệ thống nên có các hàm sau:
  18.1. normalize_level()
  Chuẩn hóa giá về level
  18.2. side_from_order_type()
  Map order type thành BUY/SELL
  18.3. is_in_zone()
  Kiểm tra level có nằm trong zone hay không
  18.4. load_recent_closed_orders_for_step()
  Load lịch sử lệnh đóng cần thiết
  18.5. compute_whipsaw_score()
  Tính điểm score
  18.6. should_skip_for_whipsaw()
  Trả về:
  có skip hay không
  score là bao nhiêu
19. Code mẫu cho các helper
  19.1. normalize_level
  def normalize_level(price: float, step: float) -> float:
      return round(price / step) * step
  19.2. side_from_order_type
  def side_from_order_type(order_type: str) -> str:
      order_type = str(order_type).upper()
      if "BUY" in order_type:
          return "BUY"
      return "SELL"
  19.3. is_in_zone
  def is_in_zone(level: float, center_level: float, step: float) -> bool:
      return (center_level - step) <= level <= (center_level + step)
20. Code mẫu cho compute_whipsaw_score()
  from datetime import timedelta

  def compute_whipsaw_score(step: float, side: str, level: float, now, closed_orders: list) -> int:
      """
      closed_orders: list of dict
      each dict:
      {
          "step": float,
          "side": "BUY"|"SELL",
          "level": float,
          "result": "Win"|"Loss",
          "open_time": datetime
      }
      """

      hist = [o for o in closed_orders if float(o["step"]) == float(step)]

      same = [
          o for o in hist
          if o["side"] == side and float(o["level"]) == float(level)
      ]

      zone = [
          o for o in hist
          if is_in_zone(float(o["level"]), float(level), float(step))
      ]

      same_120 = [
          o for o in same
          if (now - o["open_time"]) <= timedelta(minutes=120)
      ]

      zone_60 = [
          o for o in zone
          if (now - o["open_time"]) <= timedelta(minutes=60)
      ]

      L_same120 = min(sum(1 for o in same_120 if o["result"] == "Loss"), 3)
      W_same120 = min(sum(1 for o in same_120 if o["result"] == "Win"), 3)

      L_zone60 = min(sum(1 for o in zone_60 if o["result"] == "Loss"), 3)
      W_zone60 = min(sum(1 for o in zone_60 if o["result"] == "Win"), 3)

      R_same30 = 0
      if same:
          last_same = max(same, key=lambda x: x["open_time"])
          gap_minutes = (now - last_same["open_time"]).total_seconds() / 60.0
          if last_same["result"] == "Loss" and gap_minutes <= 30:
              R_same30 = 1

      sorted_hist = sorted(hist, key=lambda x: x["open_time"])
      last_two = sorted_hist[-2:] if len(sorted_hist) >= 2 else []
      C2 = int(len(last_two) == 2 and all(o["result"] == "Loss" for o in last_two))

      score = (
          3 * R_same30
          + 3 * L_same120
          - 1 * W_same120
          + 1 * L_zone60
          - 3 * W_zone60
          + 3 * C2
      )

      return int(score)
21. Code mẫu cho should_skip_for_whipsaw()
  def should_skip_for_whipsaw(step: float, side: str, level: float, now, closed_orders: list, threshold: int = 5):
      score = compute_whipsaw_score(step, side, level, now, closed_orders)
      return score >= threshold, score
22. Hàm load dữ liệu lịch sử
  Khuyến nghị:
  def load_recent_closed_orders_for_step(strategy_name, account_id, symbol, step) -> list:
      """
      Trả về list dict cho compute_whipsaw_score()
      chỉ lấy lệnh đã đóng của đúng:
      - strategy_name
      - account_id
      - symbol
      - step
      """
  Gợi ý logic
  query từ bảng orders
  chỉ lấy lệnh đã đóng
  chỉ lấy profit != 0 nếu không muốn tính hòa vốn
  lọc theo:
  strategy_name
  account_id
  symbol
  map từng record về dict chuẩn
  trả về list
  Khuyến nghị phạm vi query
  Chỉ cần lấy:
  1 ngày gần nhất
  hoặc 300 lệnh gần nhất
  Vì score chỉ dùng các cửa sổ ngắn:
  30 phút
  60 phút
  120 phút
23. Ví dụ tích hợp vào luồng đặt lệnh
  Đây là vị trí nên chèn vào sau khi đã có buy_price và sell_price.
  from datetime import datetime

  buy_level = normalize_level(buy_price, step)
  sell_level = normalize_level(sell_price, step)

  closed_orders = load_recent_closed_orders_for_step(
      strategy_name=strategy_name,
      account_id=account_id,
      symbol=symbol,
      step=step,
  )

  skip_buy, buy_score = should_skip_for_whipsaw(
      step=step,
      side="BUY",
      level=buy_level,
      now=datetime.utcnow(),
      closed_orders=closed_orders,
      threshold=5,
  )

  skip_sell, sell_score = should_skip_for_whipsaw(
      step=step,
      side="SELL",
      level=sell_level,
      now=datetime.utcnow(),
      closed_orders=closed_orders,
      threshold=5,
  )

  logger.info(
      f"[WHIPSAW] step={step} "
      f"buy_level={buy_level} buy_score={buy_score} skip_buy={skip_buy} "
      f"sell_level={sell_level} sell_score={sell_score} skip_sell={skip_sell}"
  )

  if skip_buy and skip_sell:
      logger.info(f"[WHIPSAW] skip both sides at step={step}")
      return

  if not skip_buy:
      place_buy_stop(...)

  if not skip_sell:
      place_sell_stop(...)
24. Hành vi mong muốn khi runtime
  Sau khi triển khai, bot sẽ có hành vi như sau:
  24.1. Trường hợp bình thường
  Nếu score thấp:
  bot đặt pending như cũ
  24.2. Trường hợp một phía xấu
  Nếu BUY xấu nhưng SELL chưa xấu:
  skip BUY
  vẫn cho phép SELL
  Nếu SELL xấu nhưng BUY chưa xấu:
  skip SELL
  vẫn cho phép BUY
  24.3. Trường hợp cả hai phía đều xấu
  Nếu cả BUY và SELL đều có score cao:
  skip cả hai
  chờ vòng lặp sau
25. Logging bắt buộc
  Cần log chi tiết thành phần score.
  Ví dụ:
  logger.info(
      f"[WHIPSAW] step={step} side={side} level={level} "
      f"score={score} "
      f"R_same30={R_same30} "
      f"L_same120={L_same120} W_same120={W_same120} "
      f"L_zone60={L_zone60} W_zone60={W_zone60} "
      f"C2={C2}"
  )
  Ví dụ log:
  [WHIPSAW] step=200 side=BUY level=70600 score=7 R_same30=1 L_same120=1 W_same120=0 L_zone60=1 W_zone60=0 C2=1
  Mục đích log
  Log này cho phép biết chính xác:
  tại sao lệnh bị skip
  score cao vì biến nào
  có cần chỉnh threshold hay trọng số không
26. Config đề xuất
  Thêm vào config:
  {
    "whipsaw_filter_enabled": true,
    "whipsaw_filter_dry_run": true,
    "whipsaw_threshold": 5,
    "whipsaw_same_window_minutes": 120,
    "whipsaw_zone_window_minutes": 60,
    "whipsaw_recent_same_loss_minutes": 30,
    "whipsaw_weight_recent_same_loss": 3,
    "whipsaw_weight_same_loss": 3,
    "whipsaw_weight_same_win": 1,
    "whipsaw_weight_zone_loss": 1,
    "whipsaw_weight_zone_win": 3,
    "whipsaw_weight_last_two_losses": 3
  }
  Ý nghĩa
  enabled: bật/tắt filter
  dry_run: chỉ log, chưa block thật
  threshold: ngưỡng skip
  các window_minutes: cửa sổ thời gian
  các weight_*: trọng số từng biến
27. Fallback khi thiếu dữ liệu
  Nếu không load được lịch sử hoặc dữ liệu rỗng:
  score = 0
  không block lệnh
  Ví dụ:
  if not closed_orders:
      return 0
  Lý do
  Lớp Anti-Whipsaw là bổ sung, không được làm bot ngừng giao dịch chỉ vì thiếu dữ liệu.
28. Edge cases bắt buộc xử lý
  28.1. Không đủ 2 lệnh để tính C2
  Khi đó:
  C2 = 0
  28.2. Không có lệnh nào cùng side + level
  Khi đó:
  R_same30 = 0
  L_same120 = 0
  W_same120 = 0
  28.3. Dữ liệu cũ ngoài cửa sổ thời gian
  Không tính.
  28.4. Giá có số lẻ
  Phải normalize trước.
  28.5. Hòa vốn
  Nếu profit == 0, nên bỏ qua hoặc coi là Flat và không tính vào Win/Loss.
  28.6. Timezone không thống nhất
  Phải thống nhất timezone của:
  open_time
  now
  nếu không các cửa sổ thời gian sẽ sai.
29. Quy trình triển khai từng bước
  Bước 1. Thêm helper chuẩn hóa level
  Tạo normalize_level() và dùng thống nhất mọi nơi có so sánh level.
  Bước 2. Thêm helper map side
  Tạo side_from_order_type() để chuẩn hóa BUY/SELL.
  Bước 3. Thêm helper zone
  Tạo is_in_zone() để xác định record có nằm trong zone hay không.
  Bước 4. Tạo hàm load lịch sử
  Viết load_recent_closed_orders_for_step() để lấy dữ liệu đúng strategy, đúng account, đúng symbol, đúng step.
  Bước 5. Tạo hàm tính score
  Viết compute_whipsaw_score().
  Bước 6. Tạo hàm ra quyết định
  Viết should_skip_for_whipsaw().
  Bước 7. Chèn vào logic đặt lệnh
  Sau khi có buy_price và sell_price, tính:
  buy_level
  sell_level
  buy_score
  sell_score
  rồi quyết định skip phía nào.
  Bước 8. Thêm log chi tiết
  Log toàn bộ thành phần score.
  Bước 9. Bật dry-run
  Chạy bot ở chế độ chỉ log, chưa chặn thật.
  Bước 10. Quan sát log
  Kiểm tra trong 1-2 ngày:
  score có hợp lý không
  những lệnh bị gắn cờ có thật sự xấu không
  có chặn nhầm nhiều lệnh thắng không
  Bước 11. Bật block thật
  Sau khi dry-run ổn, chuyển whipsaw_filter_dry_run=false.
  Bước 12. Tối ưu tham số
  Nếu cần, chỉnh:
  threshold
  trọng số
  cửa sổ thời gian
30. Kế hoạch rollout an toàn
  Giai đoạn 1. Dev local
  code helper
  code compute
  unit test
  Giai đoạn 2. Dry-run trên môi trường thật
  chỉ log
  chưa chặn thật
  Giai đoạn 3. Shadow evaluation
  Đối chiếu:
  lệnh nào bị đánh dấu skip
  lệnh đó thực tế win hay loss
  Giai đoạn 4. Enable thật
  bật skip thật
  giữ log đầy đủ
  Giai đoạn 5. Theo dõi
  Theo dõi:
  số lệnh bị skip
  win rate
  profit factor
  số chuỗi lỗ liên tiếp
  số lần re-entry cùng level
31. Kiểm thử
  31.1. Unit test bắt buộc
  Case 1
  Vừa có loss cùng side + level trong 10 phút.
  Kỳ vọng:
  score tăng mạnh
  dễ vượt ngưỡng
  Case 2
  Zone đang có nhiều win.
  Kỳ vọng:
  score giảm
  không bị block mù
  Case 3
  Không có lịch sử.
  Kỳ vọng:
  score = 0
  không skip
  Case 4
  Có 2 loss liên tiếp nhưng zone đang tốt.
  Kỳ vọng:
  score tăng do C2
  nhưng có thể chưa vượt ngưỡng nếu W_zone60 đủ cao
  Case 5
  Cùng level vừa có 1 loss và 1 win.
  Kỳ vọng:
  score tăng vừa phải
  không phạt quá tay
  31.2. Dry-run log
  Thêm config:
  {
    "whipsaw_filter_dry_run": true
  }
  Khi đó bot:
  vẫn tính score
  vẫn log skip/allow
  nhưng chưa block lệnh thật
  Sau 1-2 ngày, đánh giá log rồi mới bật thật.
32. Các chỉ số nên theo dõi sau triển khai
  Sau khi enable, nên theo dõi:
  tổng số lệnh bị skip
  tỷ lệ lệnh BUY bị skip
  tỷ lệ lệnh SELL bị skip
  số lần skip cả hai phía
  tỷ lệ lệnh sau khi skip mà thực tế đáng lẽ là loss
  tỷ lệ lệnh sau khi skip mà thực tế đáng lẽ là win
  số chuỗi 2, 3, 4 loss liên tiếp
  số lần re-entry cùng side + cùng level trong 30 phút
  33. Điều nên và không nên kỳ vọng
  Nên kỳ vọng
  giảm re-entry xấu
  giảm loss lặp trong sideway
  giảm số chuỗi lỗ ngắn liên tiếp
  giữ được nhiều hơn các vùng đang có follow-through
  Không nên kỳ vọng
  loại bỏ hoàn toàn lệnh thua
  biến mọi sideway thành có lời
  thay thế toàn bộ risk management
  sửa được mọi vấn đề nếu step/config nền đang chưa phù hợp
  34. Kết luận
  Lớp Anti-Whipsaw này là một bộ lọc thuần lịch sử kết quả của bot.
  Nó không cần indicator, không thay đổi triết lý Grid Step, và có thể tích hợp như một lớp chặn cuối trước khi đặt lệnh.
  Công thức sử dụng:
  WhipsawScore =
      3 * R_same30
    + 3 * L_same120
    - 1 * W_same120
    + 1 * L_zone60
    - 3 * W_zone60
    + 3 * C2
  Quy tắc:
  Nếu score >= 5 => skip lệnh
  Nếu score < 5  => cho phép đặt
  Đây là cách phù hợp để giải quyết đúng điểm yếu lớn nhất của Grid Step trong sideway:
  vừa thua xong vào lại quá sớm
  vào lại đúng level
  lặp loss trong cùng zone
  Triển khai theo hướng này sẽ giúp bot:
  lọc bớt các lệnh có xác suất whipsaw cao
  nhưng vẫn giữ khả năng giao dịch ở các vùng đang có xác suất thắng tốt