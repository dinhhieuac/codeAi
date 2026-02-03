Dưới đây là nội dung chi tiết bạn có thể copy trực tiếp vào tệp `.md` (ví dụ: `HUONG_DAN_TOI_UU_BOT_V3.md`). Nội dung này đã được cô đọng từ các phân tích dữ liệu thực tế để tối ưu hóa riêng cho **Strategy 1: Trend HA**.

---

# 🚀 CHIẾN LƯỢC TỐI ƯU HÓA BOT TREND HA (V3.0)

Bản hướng dẫn này tập trung vào việc **loại bỏ các lệnh nhiễu** để nâng tỉ lệ thắng từ ~50% lên mức kỳ vọng **>65%** dựa trên dữ liệu giao dịch thực tế.

---

## 1. BẮT BUỘC ĐỒNG THUẬN ĐA KHUNG (TREND ALIGNMENT)

Đây là yếu tố quan trọng nhất. Dữ liệu cho thấy lệnh thắng chủ yếu xuất hiện khi xu hướng M5 và H1 đồng nhất.

* **Logic:**
* **Lệnh BUY:** Chỉ thực hiện khi `m5_trend == BULLISH` **VÀ** `h1_trend == BULLISH`.
* **Lệnh SELL:** Chỉ thực hiện khi `m5_trend == BEARISH` **VÀ** `h1_trend == BEARISH`.


* **Giá trị mang lại:** Nâng Win Rate lên **66.8%** (Tăng 17% so với đánh đơn khung).

---

## 2. BỘ LỌC BIẾN ĐỘNG (ATR FILTER) THEO TÀI SẢN

Mức biến động lý tưởng để Bot "ăn trend" mà không bị quét râu nến.

| Tài sản | Vùng Giao dịch (Trade) | Vùng Dừng (Skip) | Mục tiêu |
| --- | --- | --- | --- |
| **Vàng (XAU)** |  | **** | Tránh tin tức quét 2 đầu. |
| **Bitcoin (BTC)** | **** |  | Tránh thị trường đi ngang (Sideways). |

---

## 3. BỘ LỌC KHUNG GIỜ (SESSION FILTER)

Dựa trên phân tích Win Rate theo giờ hệ thống.

* **Giờ Vàng (Ưu tiên chạy):** **02:00, 05:00, 23:00**.
* **Giờ Tử Thần (Bắt buộc nghỉ):** **04:00**.
* *Lý do:* Đây là giờ chuyển phiên, phí **Spread** thường giãn rất mạnh, tỉ lệ thua thực tế lên tới **80%**.



---

## 4. MOMENTUM VỚI RSI (XÁC NHẬN LỰC ĐẨY)

Chỉ vào lệnh khi giá có đà chạy mạnh để sớm đạt Take Profit.

* **Lệnh BUY:** RSI nằm trong vùng **60 - 70**.
* **Lệnh SELL:** RSI nằm trong vùng **30 - 40**.
* **Lưu ý:** Tránh vào lệnh khi RSI nằm ở vùng lưỡng lự (45 - 55).

---

## 5. QUẢN LÝ RỦI RO & LỢI NHUẬN

Duy trì lợi thế **Average Win ($5.8) > Average Loss ($4.8)**.

1. **Spread Guard:** Không vào lệnh nếu `Current Spread > Average Spread * 1.2`.
2. **Break-even (Hòa vốn):** Tự động dời Stop Loss về điểm vào lệnh (Entry) khi giá chạy được  lợi nhuận.
3. **R:R Ratio:** Duy trì tỷ lệ tối thiểu .

---

## 🛠 DANH SÁCH KIỂM TRA TRIỂN KHAI (CHECKLIST)

* [ ] **Code:** Thêm điều kiện so sánh `m5_trend` và `h1_trend`.
* [ ] **Code:** Thêm bộ lọc giờ `Hour() != 4`.
* [ ] **Settings:** Cài đặt thông số ATR riêng cho từng cặp (XAU và BTC).
* [ ] **Execution:** Chạy trên tài khoản có phí Spread thấp (như tài khoản Zero hoặc Pro).

---

*Ngày cập nhật: 03/02/2026*
*Phân tích bởi: AI Collaborative Assistant*

---

Tôi có thể giúp bạn chuyển toàn bộ các logic này thành đoạn mã **Pine Script (TradingView)** hoặc **MQL5 (MT5)** ngay bây giờ nếu bạn cần!