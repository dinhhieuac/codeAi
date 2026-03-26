# Grid Step Signal Filter
## Bot demo luôn đọc trade history để tìm tín hiệu phù hợp cho bot thật

## 1. Mục tiêu
Bot demo chạy liên tục để tạo tín hiệu và ghi nhận kết quả giao dịch.  
Bot thật không copy toàn bộ lệnh từ demo, mà chỉ mở lệnh khi bot demo phát hiện ra một **trạng thái giao dịch có lợi thế** dựa trên **trade history gần nhất**.

Ý tưởng cốt lõi:

- Demo = cảm biến thị trường
- Live = bộ thực thi
- Không dùng bộ lọc theo giờ
- Chỉ dùng **trade history**, **chuỗi lệnh**, **kết quả lệnh đóng**, **hướng lệnh**, **vị trí giá**, **nhịp mở lệnh**

---

## 2. Số lệnh bot phải đọc
Bot phải dùng 3 lớp dữ liệu:

### 2.1. Chấm điểm chính
- **5 lệnh đóng cuối cùng**
- Mục đích: đo trạng thái ngắn hạn của bot demo

### 2.2. Xác nhận phụ
- **10 lệnh đóng cuối cùng**
- Mục đích: xác nhận trạng thái hiện tại có đủ ổn định hay không

### 2.3. Buffer bối cảnh
- **20 lệnh gần nhất**
- Bao gồm lệnh đóng và tín hiệu gần nhất
- Mục đích: tính streak, hướng lệnh, gap thời gian, vị trí giá, cấu trúc chuỗi lệnh

Cấu hình chuẩn:

```ini
history_window = 20
profit_window_short = 5
profit_window_long = 10
```

---

## 3. Nguyên tắc hoạt động
Mỗi khi bot demo tạo ra một tín hiệu mới:

1. Bot đọc trade history gần nhất
2. Lấy ra 5 lệnh đóng cuối để chấm điểm chính
3. Lấy ra 10 lệnh đóng cuối để xác nhận phụ
4. Lấy buffer 20 lệnh gần nhất để đọc bối cảnh
5. Tính feature
6. Chấm điểm tín hiệu hiện tại
7. Nếu tín hiệu đủ mạnh thì bot thật mới mở lệnh
8. Nếu tín hiệu không đạt thì bot thật bỏ qua

---

## 4. Dữ liệu bot phải đọc từ history trade
Bot phải luôn đọc các trường sau từ tài khoản demo:

- `ticket`
- `symbol`
- `type` = BUY / SELL
- `volume`
- `open_time`
- `open_price`
- `close_time`
- `close_price`
- `profit`
- `commission`
- `swap`
- `net_profit = profit + commission + swap`
- `status` = closed / open

Ngoài ra bot cần duy trì:

- `last_5_closed_trades`
- `last_10_closed_trades`
- `last_20_trades`
- `last_closed_trade`
- `previous_signal`
- `win_streak`
- `loss_streak`

---

## 5. Các feature cần tính từ history trade

### 5.1. Từ 5 lệnh đóng cuối cùng
Đây là vùng chấm điểm chính.

- `last_trade_result`
- `sum_last_5_net_profit`
- `avg_last_5_net_profit`
- `win_count_last_5`
- `loss_count_last_5`

### 5.2. Từ 10 lệnh đóng cuối cùng
Đây là vùng xác nhận phụ.

- `sum_last_10_net_profit`
- `avg_last_10_net_profit`
- `win_rate_last_10`
- `profit_factor_last_10`

### 5.3. Từ 20 lệnh gần nhất
Đây là vùng đọc bối cảnh.

- `win_streak`
- `loss_streak`
- `same_direction_as_prev`
- `reverse_direction_from_prev`
- `gap_minutes_from_prev_signal`
- `previous_open_price`
- `current_open_below_prev_open`
- `current_open_above_prev_open`

---

## 6. Logic tín hiệu vào lệnh cho bot thật

## 6.1. Điều kiện ưu tiên mạnh
Tín hiệu được xem là đẹp nếu đồng thời thỏa các điều kiện sau:

- `gap_minutes_from_prev_signal >= 5`
- `same_direction_as_prev = true`
- `current_open_price < previous_open_price`
- ưu tiên nếu `type = SELL`

Đây là mẫu tín hiệu continuation tốt nhất trong dữ liệu hiện tại.

---

## 6.2. Bộ chấm điểm tín hiệu

### Điểm cộng
- `+2` nếu `gap_minutes_from_prev_signal >= 5`
- `+2` nếu `sum_last_5_net_profit >= 15`
- `+1` nếu `win_count_last_5 >= 3`
- `+1` nếu `sum_last_10_net_profit > 0`
- `+1` nếu `win_rate_last_10 >= 0.5`
- `+1` nếu `last_trade_result = Win`
- `+1` nếu `same_direction_as_prev = true`
- `+1` nếu `type = SELL`
- `+1` nếu `current_open_price < previous_open_price`

### Điểm trừ
- `-3` nếu `last_trade_result = Loss` và tín hiệu mới vẫn cùng hướng
- `-2` nếu `loss_streak >= 2`
- `-2` nếu `sum_last_5_net_profit < 0`
- `-1` nếu `sum_last_10_net_profit < 0`
- `-1` nếu `reverse_direction_from_prev = true`
- `-1` nếu `current_open_price > previous_open_price` trong mẫu continuation SELL mong đợi

### Ngưỡng hành động
- `score >= 6` => cho bot thật mở lệnh
- `score = 5` => chỉ mở lệnh nhỏ hoặc bỏ qua tùy mức rủi ro
- `score < 5` => bot thật không mở lệnh

---

## 7. Điều kiện chặn lệnh
Bot thật không được mở lệnh nếu gặp một trong các trường hợp sau:

- `loss_streak >= 2`
- `sum_last_5_net_profit < 0`
- `sum_last_10_net_profit < 0`
- tín hiệu mới là BUY đảo chiều trong trạng thái không rõ xu hướng
- tín hiệu demo xuất hiện quá dồn dập, `gap_minutes_from_prev_signal < 5`
- demo vừa thua và tín hiệu mới vẫn cùng hướng nhưng không có cải thiện về vị trí giá
- số lệnh mở đồng thời vượt ngưỡng an toàn

---

## 8. Luồng xử lý chuẩn

## 8.1. Demo bot
- Chạy full-time
- Ghi nhận mọi lệnh
- Lưu toàn bộ history trade
- Sau mỗi lệnh đóng hoặc mỗi tín hiệu mới, cập nhật state

## 8.2. Live bot
Khi demo có tín hiệu mới:

1. Đọc 5 lệnh đóng cuối cùng
2. Đọc 10 lệnh đóng cuối cùng
3. Đọc buffer 20 lệnh gần nhất
4. Tính feature
5. Tính score
6. Kiểm tra điều kiện chặn
7. Nếu đạt thì mở lệnh live
8. Ghi log lý do vào lệnh hoặc không vào lệnh

---

## 9. Pseudocode

```pseudo
onNewDemoSignal(signal):
    closed5 = loadLastClosedTrades(symbol, 5)
    closed10 = loadLastClosedTrades(symbol, 10)
    history20 = loadLastTrades(symbol, 20)

    features = extractFeatures(closed5, closed10, history20, signal)

    score = 0

    if features.gap_minutes_from_prev_signal >= 5:
        score += 2

    if features.sum_last_5_net_profit >= 15:
        score += 2

    if features.win_count_last_5 >= 3:
        score += 1

    if features.sum_last_10_net_profit > 0:
        score += 1

    if features.win_rate_last_10 >= 0.5:
        score += 1

    if features.last_trade_result == "Win":
        score += 1

    if features.same_direction_as_prev:
        score += 1

    if signal.type == "SELL":
        score += 1

    if signal.open_price < features.previous_open_price:
        score += 1

    if features.last_trade_result == "Loss" and features.same_direction_as_prev:
        score -= 3

    if features.loss_streak >= 2:
        score -= 2

    if features.sum_last_5_net_profit < 0:
        score -= 2

    if features.sum_last_10_net_profit < 0:
        score -= 1

    if features.reverse_direction_from_prev:
        score -= 1

    if isBlocked(features):
        rejectLiveEntry(signal, reason="blocked")
        return

    if score >= 6:
        openLiveTrade(signal, risk="normal", reason="high_score")
    elif score == 5:
        openLiveTrade(signal, risk="small", reason="medium_score")
    else:
        rejectLiveEntry(signal, reason="low_score")
```

---

## 10. Hàm extractFeatures

```pseudo
extractFeatures(closed5, closed10, history20, current_signal):
    prev_signal = getPreviousSignal(history20)
    last_closed = closed5[0]

    return {
        last_trade_result: last_closed.net_profit > 0 ? "Win" : "Loss",

        sum_last_5_net_profit: sum(closed5.net_profit),
        avg_last_5_net_profit: average(closed5.net_profit),
        win_count_last_5: count(closed5.net_profit > 0),
        loss_count_last_5: count(closed5.net_profit <= 0),

        sum_last_10_net_profit: sum(closed10.net_profit),
        avg_last_10_net_profit: average(closed10.net_profit),
        win_rate_last_10: count(closed10.net_profit > 0) / 10,
        profit_factor_last_10: grossProfit(closed10) / grossLoss(closed10),

        win_streak: calcWinStreak(history20),
        loss_streak: calcLossStreak(history20),

        same_direction_as_prev: current_signal.type == prev_signal.type,
        reverse_direction_from_prev: current_signal.type != prev_signal.type,

        gap_minutes_from_prev_signal: minutesBetween(current_signal.open_time, prev_signal.open_time),
        previous_open_price: prev_signal.open_price,

        current_open_below_prev_open: current_signal.open_price < prev_signal.open_price,
        current_open_above_prev_open: current_signal.open_price > prev_signal.open_price
    }
```

---

## 11. Tần suất bot phải đọc history
Bot phải luôn đọc history trade theo chu kỳ ngắn:

- mỗi khi có tín hiệu demo mới
- mỗi khi có lệnh demo đóng
- hoặc mỗi 1 đến 5 giây nếu cần realtime

Bot không được ra quyết định chỉ dựa vào 1 lệnh đơn lẻ.  
Bot phải luôn đánh giá tín hiệu hiện tại trong bối cảnh của:

- **5 lệnh đóng cuối cùng**
- **10 lệnh đóng cuối cùng**
- **20 lệnh gần nhất**

---

## 12. Cấu hình chuẩn

```ini
history_window = 20
profit_window_short = 5
profit_window_long = 10
min_gap_minutes = 5
entry_score_threshold = 6
medium_score_threshold = 5
max_loss_streak = 2
preferred_direction = SELL
allow_reverse_entry = false
```

---

## 13. Kết luận
Chiến lược không dùng time filter.  
Bot thật chỉ vào lệnh khi bot demo xác nhận được rằng tín hiệu hiện tại đang nằm trong một **trạng thái lịch sử có lợi thế**.

Công thức cốt lõi:

**Demo tạo tín hiệu -> đọc 5 lệnh đóng cuối -> xác nhận bằng 10 lệnh đóng cuối -> đọc bối cảnh 20 lệnh gần nhất -> tính feature -> chấm điểm -> nếu score đủ cao thì live mới vào**