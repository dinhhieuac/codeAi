# Chiến Thuật Vào Lệnh BTCUSD M1 (Price Action)

## 1. Xác định Trend

* Xu hướng giảm rõ rệt
* Đỉnh sau thấp hơn đỉnh trước
* Đáy sau thấp hơn đáy trước

## 2. Nến Momentum

* Nến thân dài, đóng cửa gần đáy
* Phá vỡ cấu trúc trước đó
* Đây là tín hiệu phe bán mạnh

## 3. Pullback (Hồi Nhỏ)

* 1–3 nến hồi nhỏ
* Thân nến nhỏ, volume giảm
* Không phá đỉnh nến momentum

## 4. Điểm Vào SELL

* SELL khi giá phá đáy nến hồi cuối cùng
* Không đoán đỉnh đáy
* Không vào khi nến đang chạy

## 5. Stop Loss (SL)

* SL phải ngắn và bám sát cấu trúc nến để phù hợp với độ nhiễu của M1.
* SL tiêu chuẩn: **4–8 USD** tùy biến động.
* SL đặt ở đâu?

  * Đặt trên **đỉnh của nến hồi cuối** + buffer **2–4 USD**.
  * Không đặt SL vượt quá **12 USD** cho M1 vì sẽ mất lợi thế R:R.
* Market mạnh → SL **8–10 USD**.
* Market yếu/sideway → SL **4–6 USD**.

## 6. Take Profit (TP)

* TP nhanh theo đúng bản chất của M1: **0.8R – 1.2R**.
* Không dùng TP xa kiểu swing (1.5R–2R) vì M1 nhiễu và đảo chiều nhanh.
* Ví dụ: **SL = 5 USD → TP = 4–6 USD**.
* Nếu có **momentum mạnh** (3–5 nến thân lớn liên tục) → kéo TP lên **1.5R**.

## 7. Quản Lý Lệnh

* Khi đạt **0.5R** → dời SL lên **-0.1R** (giảm rủi ro nhưng tránh bị quét BE sớm).
* Khi đạt **0.8R** → dời SL về **Entry (BE)**.
* Khi đạt **1R** → **chốt 50%**, phần còn lại trailing theo **đỉnh/đáy nến M1**.

---

## Tóm Tắt

1. Trend giảm
2. Có nến momentum
3. Hồi nhỏ
4. Break → SELL
5. SL đúng vị trí
6. TP theo R:R
7. Dời SL hợp lý

Đang đọc `CoinMt5/btc_m1_gpt.py` để nắm cấu trúc hiện tại, sau đó cập nhật theo `CoinMt5/btc.md`.


[1 tool called]


Cập nhật chiến thuật theo Price Action trong `btc.md`. Tạo các hàm mới và cập nhật logic chính:


[2 tools called]


Cập nhật tham số SL/TP và thêm các hàm Price Action:


[1 tool called]


Xóa các tham số cũ không còn dùng và thêm các hàm Price Action mới:


[1 tool called]


Đang đọc phần hàm phân tích kỹ thuật để thay thế bằng các hàm Price Action:


[1 tool called]


Thay thế các hàm cũ bằng các hàm Price Action mới:


[1 tool called]


Cập nhật `send_order` để nhận SL/TP từ `signal_info` và cập nhật `manage_positions` để quản lý theo R:R. Đang đọc `send_order`:


[1 tool called]


Đang tìm và cập nhật hàm `send_order`:


[1 tool called]


Cập nhật `send_order` để nhận `signal_info`:


[1 tool called]


Đang đọc phần còn lại của `send_order` để cập nhật:


[1 tool called]


Đang xóa phần validation cũ và cập nhật phần gửi lệnh:


[1 tool called]


Cập nhật phần logging và quản lý lệnh. Đang đọc phần logging trong `send_order`:


[1 tool called]


Cập nhật `manage_positions` để quản lý theo R:R. Đang tìm phần quản lý lệnh:


[1 tool called]


Cập nhật `run_bot` để sử dụng các hàm Price Action. Đang tìm phần `run_bot`:


[1 tool called]


Cập nhật `run_bot` để sử dụng các hàm Price Action:


[1 tool called]


Cập nhật mô tả chiến thuật và kiểm tra lỗi:


[1 tool called]


Cập nhật mô tả chiến thuật và sửa lỗi:


[2 tools called]


Cập nhật phần logging trong `send_order`:


[1 tool called]


Đang tìm phần logging trong `send_order`:


[1 tool called]


Cập nhật phần logging:


[1 tool called]


Cập nhật phần logging để dùng `sl_usd` và `tp_usd`:


[1 tool called]


Đang kiểm tra lỗi:


[2 tools called]


Đã cập nhật chiến thuật trong `CoinMt5/btc_m1_gpt.py` theo tài liệu `btc.md`. Tóm tắt thay đổi:

## Tóm tắt thay đổi:

### 1. **Cập nhật tham số SL/TP**:
   - SL: 4-8 USD (market mạnh: 8-10 USD, market yếu: 4-6 USD)
   - TP: 0.8R-1.2R (momentum mạnh: 1.5R)
   - SL buffer: 2-4 USD (đặt trên đỉnh nến hồi cuối)

### 2. **Thêm các hàm Price Action mới**:
   - `check_price_action_trend()`: Xác định trend bằng đỉnh/đáy (thay EMA50 H1)
   - `check_momentum_candle()`: Phát hiện nến momentum (thân dài, đóng cửa gần đáy)
   - `check_pullback()`: Phát hiện pullback (1-3 nến hồi nhỏ)
   - `check_entry_signal()`: Kiểm tra điểm vào SELL khi giá phá đáy nến hồi cuối

### 3. **Cập nhật logic vào lệnh**:
   - Thay logic EMA/Retest/Breakout bằng Price Action
   - Chỉ vào SELL khi: Trend giảm + Có nến momentum + Có pullback + Giá phá đáy nến hồi cuối

### 4. **Cập nhật quản lý lệnh theo R:R**:
   - Khi đạt 0.5R → dời SL lên -0.1R
   - Khi đạt 0.8R → dời SL về Entry (BE)
   - Khi đạt 1R → chốt 50% volume, phần còn lại trailing theo ATR

### 5. **Cập nhật `send_order()`**:
   - Nhận `signal_info` thay vì tính SL/TP từ ATR
   - Sử dụng SL/TP từ Price Action signal

### 6. **Cập nhật logging và mô tả**:
   - Hiển thị SL/TP bằng USD thay vì pips
   - Cập nhật mô tả chiến thuật theo `btc.md`

Bot hiện sử dụng chiến thuật Price Action theo `btc.md` thay vì EMA-based.