# Giải pháp chống whipsaw cho Grid Step Bot

Tài liệu này mô tả chi tiết 3 giải pháp nhằm giảm rủi ro **sideways whipsaw** cho chiến lược **Grid Step** mà không dùng indicator.  
Mục tiêu là giữ nguyên “DNA” của bot hiện tại:

- không EMA / RSI / ADX
- không trailing
- không breakeven
- vẫn đặt lệnh theo grid step
- chỉ bổ sung các lớp kiểm soát hành vi vào lệnh sau khi thị trường chứng minh vùng đó đang nhiễu

---

# 1. Bối cảnh vấn đề

Bot hiện tại hoạt động theo logic:

- xác định `anchor`
- tính `ref = round(anchor / step) * step`
- đặt:
  - `BUY STOP = ref + step`
  - `SELL STOP = ref - step`

Khi một lệnh khớp:

- hủy lệnh chờ còn lại
- dịch grid theo anchor mới
- đặt cặp lệnh mới

Điểm yếu lớn nhất nằm ở thị trường **sideways / chop**:

- giá vừa chạm một phía → lệnh khớp
- quay đầu ngay → chạm SL
- bot flat
- anchor lại quay về vùng cũ
- bot đặt lại đúng mức vừa thua
- tiếp tục bị quét

Mẫu điển hình:

- BUY 5005 → SL tại 5000
- bot lại đặt BUY 5005
- BUY 5005 → SL tiếp
- lặp lại nhiều lần

Do đó cần thêm các lớp bảo vệ chống:

1. **re-entry ngay cùng mức vừa thua**
2. **neo grid lại đúng vùng vừa fail**
3. **tiếp tục trade khi thị trường đang chop rõ rệt**

---

# 2. Giải pháp số 1: khóa re-entry theo mức + chiều sau SL

## 2.1. Mục tiêu

Ngăn bot **mở lại ngay đúng cùng chiều và cùng mức entry** vừa bị SL.

Đây là giải pháp quan trọng nhất vì nó đánh trực tiếp vào vòng lặp whipsaw phổ biến nhất.

---

## 2.2. Ý tưởng cốt lõi

Khi một lệnh bị SL, tạo một “khóa re-entry” cho:

- **đúng chiều lệnh**
- **đúng mức entry**
- **đúng step / strategy_name**

Ví dụ:

- `BUY @ 5005` bị SL  
  → khóa `BUY:5005`

- `SELL @ 4995` bị SL  
  → khóa `SELL:4995`

Khóa này có nghĩa là:

- bot **không được phép đặt lại đúng mức đó theo đúng chiều đó**
- cho đến khi giá đi đủ xa để xác nhận thị trường đã rời khỏi vùng nhiễu

---

## 2.3. Tại sao phải khóa theo “mức + chiều”

Không nên khóa chỉ theo mức giá, vì:

- mức 5005 không phải lúc nào cũng xấu
- cái vừa thất bại là **BUY tại 5005**, không phải toàn bộ mọi hành động liên quan đến 5005

Ví dụ:

- BUY 5005 vừa SL
- điều cần chặn là `BUY:5005`
- không nhất thiết phải chặn:
  - `SELL:5005`
  - `BUY:5010`
  - toàn bộ step

Khóa theo **mức + chiều** giúp:

- chính xác hơn
- ít làm bot “đơ” quá mức
- vẫn cho phép bot giao dịch chiều đối diện nếu hợp lệ

---

## 2.4. Quy tắc mở khóa

### Nếu BUY bị SL

Giả sử:

- BUY @ `E`
- SL = `E - step`

Thì chỉ mở khóa lại `BUY:E` khi giá đã đi xuống thêm **1 step** dưới vùng SL.

Công thức:

- `unlock_price = SL - step`

Ví dụ:

- step = 5
- BUY @ 5005
- SL = 5000
- mở khóa lại BUY 5005 khi `bid <= 4995`

### Nếu SELL bị SL

Giả sử:

- SELL @ `E`
- SL = `E + step`

Thì chỉ mở khóa lại `SELL:E` khi giá đã đi lên thêm **1 step** trên vùng SL.

Công thức:

- `unlock_price = SL + step`

Ví dụ:

- step = 5
- SELL @ 4995
- SL = 5000
- mở khóa lại SELL 4995 khi `ask >= 5005`

---

## 2.5. Vì sao mở khóa theo “đi thêm 1 step”

Nếu chỉ khóa theo thời gian, bot vẫn có thể mở lại trong đúng vùng nhiễu.

Ví dụ:

- BUY 5005 bị SL tại 5000
- sau 2 phút giá vẫn lắc quanh 5000–5005
- nếu chỉ dựa vào thời gian, bot có thể lại đặt BUY 5005 và tiếp tục chết

Ngược lại, nếu bắt buộc giá phải đi xuống 4995 mới mở khóa:

- thị trường đã rời vùng vừa gây stop-out
- lần retry sau đó có ý nghĩa hơn

Nói cách khác:

- **không retry trong cùng vùng nhiễu**
- chỉ retry khi cấu trúc giá đã thay đổi đủ xa

---

## 2.6. Ví dụ đầy đủ

### Không có khóa

- ref = 5000
- đặt BUY 5005 / SELL 4995
- BUY 5005 khớp
- giá về 5000 → SL
- bot lại neo quanh 5000
- lại đặt BUY 5005 / SELL 4995
- BUY 5005 khớp lần nữa
- lại SL

### Có khóa re-entry

Sau khi BUY 5005 bị SL:

- tạo block `BUY:5005`
- điều kiện mở khóa: `bid <= 4995`

Ở vòng kế tiếp:

- bot vẫn có thể tính ra BUY 5005 / SELL 4995
- nhưng `BUY:5005` đang bị khóa
- nên bot **không được đặt BUY 5005**
- chỉ còn:
  - đặt SELL 4995 nếu hợp lệ
  - hoặc đứng ngoài nếu phía SELL cũng không hợp lệ

Nhờ đó vòng lặp:

- BUY 5005 → SL → BUY 5005 → SL

bị chặn lại.

---

## 2.7. Dữ liệu cần lưu

Khóa nên lưu theo:

- `strategy_name`
- `symbol`
- `step`
- `side`
- `entry_price`
- `unlock_rule`
- `unlock_price`
- `active`
- `created_at`
- `reason`

Ví dụ:

```json
{
  "strategy_name": "Grid_Step_5",
  "symbol": "XAUUSD",
  "step": 5,
  "side": "BUY",
  "entry_price": 5005.0,
  "unlock_rule": "bid_lte",
  "unlock_price": 4995.0,
  "active": true,
  "reason": "SL"
}