# Grid Step Bot — Chiến lược sau khi tinh gọn

Tài liệu này là bản đặc tả chiến lược **sau khi tinh gọn** để kết hợp đầy đủ 3 lớp chống whipsaw:

1. **Khóa re-entry theo mức + chiều sau SL**
2. **Sau SL, dịch `ref` khỏi vùng vừa thua, không neo lại bằng `mid` ngay**
3. **Pause step khi phát hiện mẫu chop trong vài lệnh gần nhất**

Tài liệu bổ sung chi tiết luồng vào lệnh và state: **grid_step_entry_flow_summary.md**.

Mục tiêu của bản tinh gọn là:

- giữ nguyên bản chất **Grid Step thuần cơ học**
- **không dùng indicator**
- vẫn dùng **SL/TP cố định**
- giảm mạnh whipsaw trong sideways
- loại bỏ các quy tắc cũ đang xung đột với 3 lớp chống whipsaw

---

# 1. Triết lý chiến lược sau khi tinh gọn

Bot vẫn là một chiến lược **grid step breakout đơn giản**:

- đặt lệnh chờ theo các mức step
- khi một lệnh khớp thì theo dõi step kế tiếp
- SL/TP cố định theo step
- quản lý theo từng `strategy_name` / từng step

Nhưng khác với bản cũ, bot **không còn hành xử như một grid đối xứng tuyệt đối trong mọi vòng lặp**.

Bot mới có thêm **trí nhớ ngắn hạn theo sự kiện vừa xảy ra**:

- nếu vừa stop-out, bot ghi nhớ mức vừa sai
- nếu vừa stop-out, bot không dựng grid lại ngay vùng cũ
- nếu vài lệnh gần đây cho thấy môi trường đang chop, bot tạm đứng ngoài

Nói ngắn gọn:

> Bot không còn “reset hoàn toàn” sau mỗi vòng lặp, mà giao dịch có điều kiện hợp lệ theo trạng thái gần nhất của step.

---

# 2. Những gì giữ nguyên

Các thành phần sau **nên giữ nguyên** vì không xung đột với 3 lớp chống whipsaw và vẫn cần thiết.

## 2.1. Không dùng indicator

Vẫn giữ nguyên nguyên tắc:

- không EMA
- không RSI
- không ADX
- không Heiken Ashi
- không filter bằng indicator

## 2.2. SL/TP cố định theo step

Vẫn giữ:

- BUY @ `price` -> `SL = price - step`, `TP = price + step`
- SELL @ `price` -> `SL = price + step`, `TP = price - step`

Không trailing, không breakeven.

## 2.3. Spread protection

Vẫn giữ:

- không đặt lệnh khi spread > `spread_max`
- không đặt lệnh nếu `step < spread`

## 2.4. Grid zone lock

Vẫn giữ:

- không đặt BUY tại mức đã có position BUY của step đó
- không đặt SELL tại mức đã có position SELL của step đó

## 2.5. Min distance

Vẫn giữ:

- không đặt pending quá gần position đang mở

## 2.6. Max positions

Vẫn giữ:

- giới hạn số position đang mở theo từng step

## 2.7. Basket Take Profit

Vẫn giữ:

- nếu tổng floating profit của đúng step >= `target_profit`
- đóng toàn bộ position của step
- hủy pending của step
- return

---

# 3. Những gì phải bỏ hoặc thay đổi mạnh

Đây là phần quan trọng nhất của bản tinh gọn.

## 3.1. Bỏ quy tắc cứng: “luôn phải có 2 pending”

## Vấn đề của bản cũ

Bản cũ mặc định mỗi step luôn phải có:

- 1 BUY STOP
- 1 SELL STOP

Quy tắc này xung đột trực tiếp với:

- re-entry lock
- ref shift sau SL
- chop pause

Ví dụ:

- BUY 5005 vừa bị SL
- `BUY:5005` đang bị block
- SELL phía dưới vẫn hợp lệ

Nếu vẫn ép “luôn đủ 2 pending”, bot sẽ:

- hoặc cố đặt lại BUY trái với block
- hoặc hủy luôn SELL hợp lệ chỉ vì thiếu cặp

## Quy tắc mới

Thay vì “luôn có đúng 2 pending”, đổi thành:

> Mỗi vòng, bot đặt **tối đa 2 pending hợp lệ**.

Tức là bot có thể có:

- 2 pending
- 1 pending
- 0 pending

Đây là hành vi **hợp lệ và mong muốn**.

---

## 3.2. Bỏ quy tắc vô điều kiện: “không có position thì anchor = mid”

## Vấn đề của bản cũ

Bản cũ dùng:

- còn position -> anchor = giá mở position mới nhất
- không còn position -> anchor = mid

Điều này gây lỗi lớn ngay sau stop-out:

- vừa BUY bị SL
- flat
- mid vẫn nằm quanh vùng stop-out
- ref lại về đúng vùng cũ
- bot lại dựng lại cặp giá vừa gây thua

## Quy tắc mới

Chỉ dùng `mid` khi **flat và không có trạng thái stop-out cần xử lý**.

Cụ thể:

- còn position -> anchor = giá mở position mới nhất
- flat + vừa có stop-out -> **không dùng mid ngay**
- flat + không có stop-out pending -> mới dùng mid

---

## 3.3. Bỏ logic rộng: “có 0/1 pending thì cancel hết rồi dựng lại”

## Vấn đề của bản cũ

Bản cũ có xu hướng:

- nếu step chỉ còn 0 hoặc 1 pending
- thì hủy hết pending còn lại
- rồi tính lại ref và dựng cặp mới

Khi thêm 3 lớp chống whipsaw, logic này gây:

- churn pending không cần thiết
- tự phá pending hợp lệ
- vòng lặp cancel/place liên tục
- khó debug

## Quy tắc mới

Chỉ hủy pending khi có lý do rõ ràng, ví dụ:

- phía đối diện đã fill
- step bị pause
- basket TP đóng rổ
- pending hiện tại vi phạm rule mới
- pending hiện tại không còn thuộc grid hợp lệ mới
- cần thay thế bằng mức mới sau sự kiện stop-out

Không còn áp dụng kiểu:

> thiếu cặp -> cancel hết -> dựng lại toàn bộ

---

## 3.4. Hạ vai trò hoặc tắt mặc định cooldown kiểu cũ

## Vấn đề của cooldown kiểu cũ

Cooldown hiện tại là:

- sau khi **đặt lệnh tại một mức**
- trong X phút không đặt lại mức đó

Logic này quá thô vì không phân biệt:

- thắng hay thua
- BUY hay SELL
- vừa TP hay vừa SL
- giá đã rời vùng đó hay chưa

Trong khi 3 lớp mới xử lý chính xác hơn nhiều.

## Quy tắc mới

Cooldown kiểu cũ không còn là lớp chống whipsaw chính.

Khuyến nghị:

- mặc định đặt `cooldown_minutes = 0`
- chỉ bật lại nếu muốn làm lớp phụ time-based

Nếu giữ cooldown, phải coi nó là:

- lớp phụ
- không phải cơ chế chính để chống re-entry

---

## 3.5. Giữ consecutive loss pause nhưng đổi vai trò

## Vấn đề của bản cũ

Bản cũ thường để:

- `consecutive_loss_count = 2`
- pause khá nhanh

Khi thêm chop pause, ngưỡng 2 lệnh thua liên tiếp thường quá nhạy.

## Quy tắc mới

Consecutive loss pause không còn là cơ chế chống sideways chính.

Nó trở thành:

> circuit breaker cuối cùng khi step vẫn gặp chuỗi thua nặng dù đã có các lớp chống whipsaw khác.

Khuyến nghị:

- tăng `consecutive_loss_count` lên `3` hoặc `4`
- coi đây là lớp fail-safe
- không dùng nó để thay thế chop pause

---

# 4. Ba lớp chống whipsaw trong chiến lược mới

## 4.1. Lớp 1 — Re-entry lock sau SL

Khi một lệnh đóng do SL (và chưa được xử lý — xem dedupe bên dưới):

- tạo block theo `strategy_name + symbol + step + side + entry_price`
- **Dedupe**: không thêm block mới nếu đã tồn tại block active cùng (strategy_name, symbol, step, side, entry_price)
- block chỉ cấm:
  - đúng chiều vừa thua
  - đúng mức entry vừa thua
  - đúng symbol và step (tránh block ảnh hưởng sai step/symbol)

Kiểm tra block: `is_reentry_blocked(strategy_name, symbol, step_val, side, price)` — so khớp đủ strategy_name, symbol, step, side, entry_price.

Ví dụ:

- BUY 5005 bị SL -> block `BUY:5005` (cùng symbol, step)
- SELL 4995 bị SL -> block `SELL:4995`

Điều kiện mở khóa mặc định:

- BUY block mở khi `bid <= unlock_price` (unlock_price = SL - step)
- SELL block mở khi `ask >= unlock_price` (unlock_price = SL + step)

Mục tiêu:

- không cho bot retry ngay cùng sai lầm vừa xảy ra

---

## 4.2. Lớp 2 — Ref shift sau SL

Khi step vừa có lệnh đóng do SL và hiện tại **không còn position mở**:

- không dùng `mid` để dựng grid kế tiếp
- dùng `ref_override` tính từ **`last_stopout_sl`** đã lưu trong state (khi ghi nhận stop-out):

  - BUY bị SL → `ref_override = last_stopout_sl - step`
  - SELL bị SL → `ref_override = last_stopout_sl + step`

State ref shift lưu: `last_stopout_side`, `last_stopout_entry`, `last_stopout_sl`, `last_stopout_time`, `pending_ref_shift`, `last_processed_stopout_ticket`. Khi dùng xong `ref_override` chỉ reset `pending_ref_shift = false`, giữ lại `last_processed_stopout_ticket` để tránh xử lý lặp cùng một stop-out.

Mục tiêu:

- kéo grid ra khỏi vùng vừa stop-out
- tránh dựng lại đúng vùng giá vừa fail

---

## 4.3. Lớp 3 — Chop pause

Nếu `N` lệnh đóng gần nhất của cùng step cho thấy:

- số lệnh lỗ đủ lớn
- entry nằm trong band giá hẹp

thì pause step đó trong `X` phút.

Mục tiêu:

- dừng giao dịch trong môi trường nhiễu rõ rệt
- tránh bot bị xay tiếp trong cùng một vùng

---

# 5. Flow chiến lược mới cho mỗi step

Flow khuyến nghị cho `strategy_grid_step_logic()` sau khi tinh gọn.

## Bước 1. Đồng bộ pending orders

- sync `grid_pending_orders` với MT5
- cập nhật `FILLED` / `CANCELLED`
- nếu `FILLED`, ghi position vào `orders`

## Bước 2. Đồng bộ lệnh đóng

- sync closed orders từ MT5 vào DB
- cập nhật `profit`, `close_time`, `close reason` nếu có

## Bước 3. Ghi nhận stop-out mới (chỉ xử lý 1 lần mỗi lệnh SL)

Nếu phát hiện lệnh vừa đóng do SL **và** ticket đó **chưa** nằm trong `last_processed_stopout_ticket`:

- tạo re-entry block (và dedupe: không thêm nếu đã có block active cùng strategy_name, symbol, step, side, entry_price)
- set state `pending_ref_shift = true`
- lưu:
  - `last_stopout_side`
  - `last_stopout_entry`
  - `last_stopout_sl`
  - `last_stopout_time`
  - **`last_processed_stopout_ticket`** (để vòng sau không xử lý lặp cùng một stop-out)

Một lệnh SL chỉ sinh ra **một** re-entry block và **một** lần `pending_ref_shift = true`.

## Bước 4. Kiểm tra pause hiện tại

Nếu strategy đang pause:

- log thời gian còn lại
- không đặt lệnh mới
- return

## Bước 5. Basket TP

Nếu floating profit của step >= `target_profit`:

- đóng toàn bộ positions của step
- hủy pending của step
- notify
- return

## Bước 6. Consecutive loss pause kiểu fail-safe

Nếu đủ điều kiện circuit breaker:

- set pause
- hủy pending
- return

## Bước 7. Chop pause

Lấy `N` lệnh đóng gần nhất của step.

Nếu:

- đủ số lệnh để đánh giá
- số lệnh lỗ >= ngưỡng
- band entry <= `chop_band_steps * step`

thì:

- set pause
- hủy pending
- notify
- return

## Bước 8. Spread protection và bảo vệ tick

Nếu `tick = mt5.symbol_info_tick(symbol)` là `None`:

- không gọi `refresh_reentry_blocks` (tránh crash)
- return sớm

Nếu spread không hợp lệ:

- không đặt lệnh mới
- return hoặc chờ vòng sau

## Bước 9. Max positions

Nếu số position mở >= `max_positions`:

- không đặt thêm
- return

## Bước 10. Xác định `ref`

### Nếu còn position mở

- `anchor = giá mở position mới nhất`
- `ref = round(anchor / step) * step`
- **Không** hủy toàn bộ pending chỉ vì đang có position; chỉ hủy từng pending không còn hợp lệ.

### Nếu flat và `pending_ref_shift = true`

- đọc `last_stopout_sl` từ state (đã lưu khi ghi nhận stop-out)
- **ref_override** tính từ `last_stopout_sl`:
  - BUY SL → `ref_override = last_stopout_sl - step`
  - SELL SL → `ref_override = last_stopout_sl + step`
- không dùng `mid`
- sau khi sử dụng xong, reset `pending_ref_shift = false` (giữ lại `last_processed_stopout_ticket`)

Ref shift **chỉ** được set từ bước “Ghi nhận stop-out mới”, không dùng hàm bổ sung đọc SL từ history (logic đơn giản, tránh arm lặp).

### Nếu flat bình thường

- `anchor = mid`
- `ref = round(anchor / step) * step`

## Bước 11. Tính giá pending ứng viên

- `buy_price = ref + step`
- `sell_price = ref - step`

## Bước 12. Kiểm tra hợp lệ từng phía riêng biệt

**Thứ tự check** (bắt buộc): zone lock → min distance → re-entry block → cooldown.

### Với BUY

Check lần lượt:

1. zone lock (đã có position BUY tại mức buy_price?)
2. min distance (pending quá gần position đang mở?)
3. re-entry block BUY (so khớp strategy_name, **symbol**, **step**, side, entry_price)
4. cooldown phụ nếu còn dùng

Ghi nhận lý do từ chối (`buy_reason`) và **log** khi BUY bị block: `[strategy_name] BUY @ price blocked: reason1, reason2`.

### Với SELL

Check lần lượt:

1. zone lock
2. min distance
3. re-entry block SELL (so khớp strategy_name, symbol, step, side, entry_price)
4. cooldown phụ

Ghi nhận `sell_reason` và log khi SELL bị block.

## Bước 13. Quản lý pending hiện có

Không còn rule “không đủ cặp thì cancel hết”. **Không** hủy toàn bộ pending chỉ vì đang có position.

Chỉ hủy từng pending khi:

- step pause
- basket TP
- pending cũ không còn hợp lệ (sai mức grid mới, bị block, step pause)
- pending cũ cần thay bởi mức mới sau stop-out
- phía đối diện đã fill và mức cũ không còn hợp lệ

Sau bất kỳ thao tác hủy pending hàng loạt: **refresh** lại danh sách `pendings` từ MT5/DB trước khi kiểm tra `has_buy_pending` / `has_sell_pending`.

## Bước 14. Đặt các pending hợp lệ

Bot được phép ở một trong ba trạng thái:

- đặt cả BUY và SELL nếu cả hai hợp lệ
- chỉ đặt BUY nếu BUY hợp lệ, SELL không hợp lệ
- chỉ đặt SELL nếu SELL hợp lệ, BUY không hợp lệ
- không đặt gì nếu cả hai không hợp lệ

Đây là hành vi chuẩn của chiến lược mới.

## Bước 15. Refresh unlock cho re-entry blocks

Ở cuối vòng (chỉ khi `tick is not None`):

- kiểm tra giá hiện tại (bid, ask)
- block nào đủ điều kiện mở khóa thì set inactive
- BUY block: unlock khi `bid <= unlock_price` (unlock_price = SL - step)
- SELL block: unlock khi `ask >= unlock_price` (unlock_price = SL + step)

---

# 6. Quy tắc mới về pending orders

Đây là thay đổi lớn nhất so với bản cũ.

## 6.1. Bản cũ

- luôn cố giữ 2 pending đối xứng
- nếu không đủ cặp thì dễ cancel/rebuild

## 6.2. Bản mới

Pending là **kết quả của bộ lọc hợp lệ**, không phải mục tiêu bắt buộc phải đủ cặp.

### Quy tắc chuẩn

- bot đặt **mọi pending hợp lệ**
- bot không đặt pending không hợp lệ chỉ để đủ cặp
- bot không hủy pending hợp lệ chỉ vì phía còn lại đang bị block

Tức là:

> “Có 1 pending hợp lệ” là trạng thái đúng, không phải trạng thái lỗi.

---

# 7. Quy tắc mới về anchor và ref

## 7.1. Anchor cũ

- còn position -> position mới nhất
- flat -> mid

## 7.2. Anchor/ref mới

### Trường hợp bình thường

- còn position -> như cũ
- flat, không có stop-out pending -> dùng mid như cũ

### Trường hợp sau stop-out

- flat, vừa stop-out -> không dùng mid ngay
- dùng `ref_override` tính từ **last_stopout_sl** đã lưu: BUY SL → `ref_override = last_stopout_sl - step`, SELL SL → `ref_override = last_stopout_sl + step`

Điều này tạo ra **trí nhớ ngắn hạn sau SL**.

---

# 8. State và quy ước triển khai

## 8.1. Naming thống nhất

- **strategy_name (DB, state)**: `Grid_3_Step` (single step) hoặc `Grid_3_Step_{step}` (multi-step).
- **Comment MT5**: cùng chuẩn — `Grid_3_Step` / `Grid_3_Step_{step}` để log, dashboard và tài liệu đồng bộ.

## 8.2. Pause state (file pause)

Hỗ trợ hai dạng value cho mỗi step:

- **Dạng cũ**: chuỗi ISO thời gian hết pause, ví dụ `"2026-03-12T10:45:00"`.
- **Dạng mới**: object `{ "paused_until": "…", "reason": "chop_detected", "meta": { … } }`. Đọc `paused_until` hoặc `until` để so thời gian.

Backward compatible với file pause cũ.

## 8.3. Xác định lệnh đóng do SL (hit SL)

Không hard-code tolerance cố định cho mọi symbol. Dùng ngưỡng theo symbol, ví dụ:

- `sl_tolerance = max(point * 20, 0.02)` (hoặc config riêng)
- So sánh: `abs(close_price - sl) <= sl_tolerance`

Giúp XAU, BTC và các market khác dùng chung logic ổn định hơn.

## 8.4. Ref shift state — đọc một lần

Trong cùng một vòng logic, chỉ gọi `get_ref_shift_state(strategy_name)` một lần (ví dụ khi “Ghi nhận stop-out”), lưu vào biến local và tái sử dụng (dedupe ticket, kiểm tra pending_ref_shift, v.v.).

---

# 9. Cấu hình khuyến nghị

```json
{
  "steps": [5],
  "min_distance_points": 5,
  "target_profit": 50.0,
  "spread_max": 0.5,
  "max_positions": 5,

  "cooldown_minutes": 0,

  "consecutive_loss_pause_enabled": true,
  "consecutive_loss_count": 3,
  "consecutive_loss_pause_minutes": 10,

  "reentry_lock_enabled": true,
  "reentry_unlock_steps": 1,

  "post_sl_ref_shift_enabled": true,

  "chop_pause_enabled": true,
  "chop_window_trades": 4,
  "chop_loss_count": 3,
  "chop_band_steps": 2,
  "chop_pause_minutes": 15,
  "chop_require_closed_count_exact": true
}
```