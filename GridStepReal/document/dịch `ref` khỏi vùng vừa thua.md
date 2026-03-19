# Giải pháp số 2: Sau SL, dịch `ref` khỏi vùng vừa thua, không neo lại bằng `mid` ngay

## 1. Mục tiêu

Giải pháp này nhằm giảm tình trạng bot **vừa bị Stop Loss xong lại dựng grid mới ngay đúng vùng vừa thua**, dẫn đến:

- đặt lại cùng cặp mức giá cũ
- vào lại vùng nhiễu quá sớm
- lặp whipsaw nhiều lần trong market sideways

Ý tưởng chính là:

> Khi một lệnh vừa bị SL và step hiện đang **flat** (không còn position mở), bot **không dùng ngay giá mid hiện tại để dựng grid mới như bình thường**.  
> Thay vào đó, bot sẽ **dịch `ref` ra khỏi vùng vừa thua** để ép grid rời khỏi khu vực vừa gây stop-out.

---

## 2. Vấn đề của cách neo hiện tại bằng `mid`

Trong logic gốc:

- nếu có position → `anchor = giá mở của position mới nhất`
- nếu không có position → `anchor = mid = (bid + ask) / 2`
- sau đó:
  - `ref = round(anchor / step) * step`
  - `buy_price = ref + step`
  - `sell_price = ref - step`

### Điểm yếu sau một cú SL

Khi bot vừa bị SL, thị trường thường vẫn còn đang ở đúng vùng nhiễu đó.  
Nếu lấy `mid` ngay tại thời điểm vừa flat, thì:

- `anchor` thường rơi đúng vùng vừa stop-out
- `ref` quay lại đúng level cũ
- bot dựng lại cặp pending rất giống cặp vừa thua

### Ví dụ

Giả sử:

- `step = 5`
- ban đầu `ref = 5000`
- bot đặt:
  - BUY STOP = 5005
  - SELL STOP = 4995

Giá đi lên:
- BUY 5005 khớp

Sau đó giá quay về:
- BUY 5005 bị SL tại 5000

Lúc này bot flat.  
Nếu ngay vòng sau:

- `mid ≈ 5000`
- `ref = round(5000 / 5) * 5 = 5000`

thì bot lại dựng:

- BUY STOP = 5005
- SELL STOP = 4995

Đó chính là cơ chế kéo bot quay lại đúng vùng vừa fail.

---

## 3. Ý tưởng cốt lõi của giải pháp

Thay vì:

- vừa SL xong
- bot flat
- lấy `mid`
- tính lại `ref` như bình thường

ta sửa thành:

> Nếu step vừa có một lệnh đóng do SL và hiện không còn position mở, thì **không dùng `mid` cho lần dựng grid kế tiếp**.  
> Bot sẽ dùng một **`ref` override** được dịch **ra khỏi phía vừa thua**.

Nói ngắn gọn:

- vừa thua phía trên → kéo `ref` xuống
- vừa thua phía dưới → kéo `ref` lên

---

## 4. Quy tắc dịch `ref`

## 4.1. Trường hợp lệnh vừa thua là BUY

Giả sử:

- lệnh vừa SL là `BUY @ E`
- `step = S`

Thì dùng:

- `ref_override = E - S`

### Ví dụ

- BUY @ 5005
- step = 5
- lệnh bị SL
- `ref_override = 5005 - 5 = 5000`

Khi đó grid kế tiếp sẽ được dựng từ `ref = 5000`, thay vì lấy `mid` rồi làm tròn lại.

### Ý nghĩa thực tế

Phía trên vừa thất bại.  
Do đó bot không nên neo theo giá hiện tại một cách thụ động, mà nên ép grid lùi xuống một nấc để:

- tránh dựng lại ngay vùng vừa thua
- tạo cảm giác “reset thấp hơn”
- hạn chế việc đuổi lại đúng vùng BUY vừa fail

---

## 4.2. Trường hợp lệnh vừa thua là SELL

Giả sử:

- lệnh vừa SL là `SELL @ E`
- `step = S`

Thì dùng:

- `ref_override = E + S`

### Ví dụ

- SELL @ 4995
- step = 5
- lệnh bị SL
- `ref_override = 4995 + 5 = 5000`

### Ý nghĩa thực tế

Phía dưới vừa thất bại.  
Bot nên ép grid dịch lên một nấc, thay vì lại dựng ngay quanh vùng đáy vừa quét SL.

---

## 5. Mục tiêu thật sự của `ref_override`

Giải pháp này **không nhằm dự báo xu hướng**.  
Nó chỉ làm một việc rất cụ thể:

> Không cho phép bot “vừa đau xong quay lại ngay chỗ vừa đau”.

Bot vẫn là grid step, vẫn không có indicator, vẫn giao dịch cơ học.  
Nhưng sau một stop-out, nó được buộc phải:

- **dịch cấu trúc grid khỏi vùng vừa fail**
- thay vì dựng lại cấu trúc cũ theo `mid`

---

## 6. So sánh: Cách cũ vs cách mới

## 6.1. Cách cũ

Sau SL:

- step flat
- `anchor = mid`
- `ref = round(mid / step) * step`
- dựng lại grid quanh `ref`

### Hệ quả
Nếu `mid` vẫn đang quanh vùng stop-out, bot gần như dựng lại cấu trúc cũ.

---

## 6.2. Cách mới

Sau SL:

- step flat
- phát hiện `last_stopout_side`
- lấy `last_stopout_entry`
- tính `ref_override`
- dùng `ref_override` cho **lần dựng grid kế tiếp**
- sau đó reset trạng thái override

### Hệ quả
Grid mới được dựng theo hướng **rời xa vùng vừa fail**, chứ không theo `mid` ngay.

---

## 7. Điều kiện áp dụng

Giải pháp này không nên áp dụng mọi lúc.  
Chỉ áp dụng khi **đồng thời** thỏa các điều kiện sau:

1. step vừa có một lệnh đóng do SL
2. step hiện **không còn position mở**
3. bot chuẩn bị dựng grid mới
4. trạng thái `pending_ref_shift = true`

Nếu vẫn còn position mở, thì logic anchor cũ vẫn nên giữ nguyên:

- `anchor = giá mở của position mới nhất`

---

## 8. Chỉ áp dụng cho “lần dựng grid kế tiếp”

Đây là điểm rất quan trọng.

Giải pháp này nên là một **override tạm thời 1 lần**, không phải thay đổi lâu dài.

### Vì sao

Nếu bạn giữ `ref_override` quá lâu:

- bot sẽ bị lệch cấu trúc một cách cứng nhắc
- mất tính tự nhiên của grid
- khó dự đoán hành vi

Do đó nên dùng rule:

- vừa SL → set `pending_ref_shift = true`
- lần kế tiếp khi step flat và cần dựng grid → dùng `ref_override`
- sau khi dùng xong → set `pending_ref_shift = false`

---

## 9. Trạng thái cần lưu

Chỉ cần lưu rất ít state.

Ví dụ:

```json
{
  "strategy_name": "Grid_Step_5",
  "step": 5,
  "last_stopout_side": "BUY",
  "last_stopout_entry": 5005.0,
  "pending_ref_shift": true
}