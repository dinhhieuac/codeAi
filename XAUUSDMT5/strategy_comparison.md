# So sánh Chiến thuật: `m1_gpt.py` vs `m1_gpt_m15_Trent.py`

Dưới đây là bảng so sánh chi tiết giữa hai bot giao dịch:

| Đặc điểm | `m1_gpt.py` | `m1_gpt_m15_Trent.py` |
| :--- | :--- | :--- |
| **Chiến thuật Chính** | Bám theo xu hướng **H1** | Bám theo xu hướng **M15** |
| **Bộ lọc Xu hướng (Trend Filter)** | **EMA 50 trên khung H1** | **EMA 50 trên khung M15** |
| **Điểm vào lệnh (Entry)** | Retest **EMA 20 trên khung M1** | Retest **EMA 20 trên khung M1** |
| **Bộ lọc Sức mạnh (ADX)** | ADX(14) trên M1 >= 25 | ADX(14) trên M1 >= 25 |
| **Stop Loss (SL)** | 1.5 * ATR(M1) | 1.5 * ATR(M1) |
| **Take Profit (TP)** | 2.0 * ATR(M1) | 2.0 * ATR(M1) |
| **Chiến thuật Breakout** | Có (ADX > 28) | Có (ADX > 28) |
| **Quản lý vốn** | Giống nhau | Giống nhau |

## Phân tích Chuyên sâu

### 1. Khác biệt Cốt lõi: Khung Thời Gian Xu Hướng
*   **`m1_gpt.py` (H1 Trend)**:
    *   Sử dụng xu hướng dài hơn (1 giờ) để định hướng.
    *   **Ưu điểm**: Ổn định hơn, ít bị nhiễu bởi các biến động ngắn hạn. Thường an toàn hơn khi thị trường có xu hướng rõ ràng.
    *   **Nhược điểm**: Phản ứng chậm hơn khi thị trường đảo chiều. Có thể bỏ lỡ các cơ hội ngắn hạn khi M15 đảo chiều nhưng H1 chưa kịp phản ứng.

*   **`m1_gpt_m15_Trent.py` (M15 Trend)**:
    *   Sử dụng xu hướng trung hạn (15 phút) để định hướng.
    *   **Ưu điểm**: Nhạy bén hơn, bắt được các con sóng ngắn và trung hạn sớm hơn. Phù hợp với phong cách Scalping nhanh.
    *   **Nhược điểm**: Dễ bị "dính" các tín hiệu giả (whipsaw) khi M15 biến động mạnh hoặc đi ngược xu hướng H1/H4.

### 2. Điểm Giống Nhau
*   Cả hai đều sử dụng khung **M1** để tìm điểm vào lệnh "tinh chỉnh" (sniper entry) tại đường EMA 20.
*   Cả hai đều dùng **ATR** để đặt SL/TP, giúp thích nghi với độ biến động của thị trường.
*   Cả hai đều có cơ chế **Breakout** để vào lệnh khi giá chạy mạnh mà không hồi về EMA 20.

## Kết luận & Khuyến nghị
*   Chọn **`m1_gpt.py`** nếu bạn muốn giao dịch an toàn hơn, ít lệnh hơn nhưng chất lượng cao hơn theo xu hướng lớn.
*   Chọn **`m1_gpt_m15_Trent.py`** nếu bạn muốn giao dịch năng động hơn, chấp nhận rủi ro cao hơn để bắt các con sóng ngắn hạn.
