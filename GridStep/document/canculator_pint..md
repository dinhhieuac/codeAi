# Hệ thống chấm điểm 9-6-3 cho Demo -> Live

## 1. Mục tiêu
Xây dựng một hệ thống chấm điểm liên tục để:

- bot demo chạy liên tục
- đọc trade history liên tục
- nhận diện trạng thái thị trường hiện tại
- chấm điểm tín hiệu hiện tại theo bối cảnh mới nhất
- nếu tín hiệu đủ tốt thì gửi lệnh sang tài khoản live
- nếu live đã có lệnh tương ứng thì không mở trùng

Hệ thống không dùng point cố định theo giờ.
Hệ thống phải tự thích nghi khi market thay đổi theo ngày, phiên, volatility, nhịp grid.

---

## 2. Ý nghĩa 9-6-3

### 9 = 9 nhóm feature chấm điểm
### 6 = 6 regime thị trường
### 3 = 3 mức quyết định cuối cùng

---

## 3. Kiến trúc tổng thể

### Tầng A - Demo Signal Engine
Nhiệm vụ:
- chạy strategy gốc
- ghi nhận signal
- đọc history trade
- tính feature
- nhận diện regime
- tính score

### Tầng B - Score Engine 9-6-3
Nhiệm vụ:
- chuẩn hóa feature
- gán trọng số theo regime
- tính điểm liên tục
- quy đổi thành xác suất chất lượng tín hiệu

### Tầng C - Live Execution Engine
Nhiệm vụ:
- nhận tín hiệu đã đạt chuẩn từ demo
- kiểm tra tài khoản live
- nếu chưa có lệnh tương ứng thì mở lệnh
- nếu đã có thì bỏ qua

---

## 4. 9 nhóm feature

## Nhóm 1: Demo Performance Short
Đọc 5 lệnh đóng cuối:
- `sum_last_5_net_profit`
- `avg_last_5_net_profit`
- `win_count_last_5`
- `last_trade_result`

## Nhóm 2: Demo Performance Medium
Đọc 10 lệnh đóng cuối:
- `sum_last_10_net_profit`
- `avg_last_10_net_profit`
- `win_rate_last_10`
- `profit_factor_last_10`

## Nhóm 3: Demo Stability
Đọc 20 lệnh gần nhất:
- `win_streak`
- `loss_streak`
- `max_drawdown_recent`
- `recovery_after_loss`

## Nhóm 4: Signal Structure
- `current_signal_type`
- `prev_signal_type`
- `same_direction_as_prev_signal`
- `reverse_direction_from_prev_signal`

## Nhóm 5: Signal Timing
- `gap_minutes_from_prev_signal`
- `signal_density_last_30m`
- `signal_density_last_60m`

## Nhóm 6: Price Position Quality
- `current_signal_open_price`
- `prev_signal_open_price`
- `price_improved_vs_prev_signal`
- `distance_to_grid_step`
- `distance_to_avg_entry`

## Nhóm 7: Execution Context
- `spread`
- `slippage_estimate`
- `pending_orders_count`
- `open_positions_count`

## Nhóm 8: Market Regime Indicators
- `volatility_state`
- `trend_state`
- `range_state`
- `momentum_state`

## Nhóm 9: Live Safety Context
- `live_has_equivalent_order`
- `live_exposure_same_direction`
- `live_risk_utilization`
- `live_margin_safety`

---

## 5. 6 regime thị trường

Hệ thống phải luôn phân loại thị trường vào 1 trong 6 trạng thái:

### Regime 1: Trend Up Clean
- xu hướng tăng rõ
- tín hiệu BUY continuation đáng tin hơn

### Regime 2: Trend Down Clean
- xu hướng giảm rõ
- tín hiệu SELL continuation đáng tin hơn

### Regime 3: Sideway Stable
- biên dao động rõ
- continuation yếu hơn
- reversal/selective entry quan trọng hơn

### Regime 4: High Volatility Expansion
- biến động mạnh
- tín hiệu đến nhanh
- cần giảm độ nhạy với density cao

### Regime 5: Noisy / Whipsaw
- đảo hướng liên tục
- score tín hiệu thấp
- cần tăng block

### Regime 6: Recovery / Transition
- vừa đổi trạng thái
- feature gần đây chưa ổn định
- cần confidence thấp hơn bình thường

---

## 6. 3 mức quyết định cuối cùng

### Level 1: Reject
- không mở live

### Level 2: Probe
- mở live nhỏ
- volume giảm
- dùng như lệnh thăm dò

### Level 3: Execute
- mở live theo volume chuẩn

---

## 7. Cách chấm điểm

## 7.1. Không dùng point cố định
Không nên dùng mãi kiểu:
- `sum5 >= 15 => +2`
- `winrate10 >= 0.5 => +1`

Thay vào đó dùng score liên tục:

```text
final_score =
    w1 * normalized_demo_short
  + w2 * normalized_demo_medium
  + w3 * normalized_demo_stability
  + w4 * normalized_signal_structure
  + w5 * normalized_signal_timing
  + w6 * normalized_price_quality
  + w7 * normalized_execution_context
  + w8 * normalized_market_regime_fit
  + w9 * normalized_live_safety
```

Trong đó:
- `w1..w9` là trọng số động
- thay đổi theo regime
- thay đổi theo hiệu quả gần đây

---

## 7.2. Chuẩn hóa feature
Mỗi feature phải đưa về thang `0 -> 1` hoặc `-1 -> +1`

Ví dụ:
- rất xấu = `0.0`
- trung tính = `0.5`
- rất tốt = `1.0`

hoặc:
- xấu = `-1`
- tốt = `+1`

Ví dụ:
```text
normalized_sum5 = percentile_rank(sum_last_5_net_profit, rolling_window=100)
normalized_gap = percentile_rank(gap_minutes_from_prev_signal, rolling_window=100)
normalized_spread = 1 - percentile_rank(spread, rolling_window=100)
```

---

## 7.3. Trọng số động theo regime
Mỗi regime dùng một bộ trọng số khác nhau.

Ví dụ:

### Trend Down Clean
- tăng trọng số:
  - `signal_structure`
  - `price_quality`
  - `same_direction`
  - `sell_continuation`

### Sideway Stable
- giảm trọng số:
  - continuation
- tăng trọng số:
  - stability
  - spread
  - signal density control

### Noisy / Whipsaw
- tăng trọng số:
  - hard block
  - confidence penalty

---

## 8. Bộ confidence

Mỗi feature phải có thêm `confidence`.

Ví dụ:
- 30 tín hiệu gần nhất feature này vẫn hiệu quả -> confidence cao
- 30 tín hiệu gần nhất feature này suy yếu -> confidence thấp

Công thức:

```text
effective_feature_score = raw_feature_score * feature_confidence
```

Trong đó:
- `feature_confidence` nằm trong khoảng `0.5 -> 1.5`

---

## 9. Bộ quên dữ liệu cũ
Hệ thống phải dùng decay để không bị dính dữ liệu quá cũ.

Ví dụ:

```text
trade_weight = exp(-age_in_hours / decay_factor)
```

Gợi ý:
- short-term decay = nhanh
- medium-term decay = vừa
- long-term decay = chậm

---

## 10. Hard block
Trước khi tính score cuối, phải qua hard block.

Không mở live nếu:
- spread quá xấu
- slippage quá cao
- loss_streak vượt ngưỡng
- live margin không an toàn
- live đã có lệnh tương ứng
- số lệnh mở vượt giới hạn
- regime = noisy cực mạnh

---

## 11. Công thức xác suất cuối
Sau khi tính score, quy đổi sang xác suất chất lượng tín hiệu:

```text
entry_probability = sigmoid(final_score)
```

Hoặc đơn giản:
```text
entry_probability = clamp((final_score + 1) / 2, 0, 1)
```

---

## 12. Quy tắc ra quyết định 3 mức

### Reject
```text
if entry_probability < 0.55:
    reject
```

### Probe
```text
if 0.55 <= entry_probability < 0.72:
    open_small_live_trade
```

### Execute
```text
if entry_probability >= 0.72:
    open_normal_live_trade
```

---

## 13. Luồng xử lý chuẩn

```pseudo
on_new_demo_signal(signal):
    closed5 = load_last_closed_trades(5)
    closed10 = load_last_closed_trades(10)
    history20 = load_recent_trade_history(20)
    signal_history = load_recent_signal_history(20)
    live_state = load_live_state()

    features = extract_9_feature_groups(
        signal,
        closed5,
        closed10,
        history20,
        signal_history,
        live_state
    )

    regime = detect_regime(features)

    if is_hard_block(features, regime, live_state):
        return REJECT

    weights = get_dynamic_weights(regime)
    confidence = get_feature_confidence(features, regime)

    final_score = calc_weighted_score(features, weights, confidence)
    entry_probability = convert_score_to_probability(final_score)

    if live_has_equivalent_order(live_state, signal):
        return SKIP_DUPLICATE

    if entry_probability >= 0.72:
        return EXECUTE_NORMAL

    if entry_probability >= 0.55:
        return EXECUTE_SMALL

    return REJECT
```

---

## 14. Rule kiểm tra lệnh tương ứng trên live
Không mở lệnh live nếu đã có lệnh tương ứng:

- cùng `symbol`
- cùng `type`
- cùng `magic`
- giá vào gần tín hiệu mới trong ngưỡng cho phép

Ví dụ:

```pseudo
is_equivalent_order(order, signal):
    return (
        order.symbol == signal.symbol
        and order.type == signal.type
        and order.magic == signal.magic
        and abs(order.open_price - signal.entry_price) <= duplicate_price_threshold
    )
```

---

## 15. Output chuẩn của hệ thống
Mỗi tín hiệu phải trả ra:

- `signal_id`
- `symbol`
- `signal_type`
- `entry_price`
- `regime`
- `final_score`
- `entry_probability`
- `decision = REJECT / PROBE / EXECUTE`
- `top_positive_features`
- `top_negative_features`
- `hard_block_reason`
- `live_duplicate_status`

---

## 16. Tham số khuyến nghị ban đầu

```ini
closed_short_window = 5
closed_medium_window = 10
history_window = 20
signal_history_window = 20
feature_rolling_window = 100
regime_window = 50
hard_block_max_loss_streak = 2
duplicate_price_threshold = 0.8 * grid_step
probe_probability_threshold = 0.55
execute_probability_threshold = 0.72
short_decay_factor_hours = 6
medium_decay_factor_hours = 24
long_decay_factor_hours = 72
```

---

## 17. Kết luận
Hệ thống 9-6-3 không chấm điểm theo kiểu cố định.

Nó hoạt động như sau:

- demo chạy liên tục
- đọc history liên tục
- trích xuất 9 nhóm feature
- nhận diện 6 regime thị trường
- quy đổi thành 3 mức quyết định
- nếu tín hiệu đủ tốt và live chưa có lệnh tương ứng thì mở cho live

Công thức cốt lõi:

**Demo -> Feature -> Regime -> Dynamic Weight -> Probability -> Check Live -> Execute**