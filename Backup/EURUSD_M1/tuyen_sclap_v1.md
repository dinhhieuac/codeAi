# Chiến Thuật M1 Scalp - Trend Pullback Breakout (Tuyen Scalp V1)

Dựa trên mã nguồn `tuyen_trend_sclap.py`.

Chiến thuật sử dụng khung thời gian **M1 (1 Phút)** kết hợp xác nhận xu hướng từ **M5**.

## 1. Điều Kiện Chung (Bắt buộc)
*   **Biên độ dao động (ATR):** `ATR(14)` trên khung M1 phải **lớn hơn hoặc bằng 0.00011** (1.1 pips cho EURUSD). Điều này để đảm bảo thị trường có đủ lực chạy.

---

## 2. Điều Kiện BUY (Long)
Chỉ vào lệnh khi thỏa mãn **TẤT CẢ** các điều kiện sau:

1.  **Xu hướng tăng (Trend):** 
    *   Đường trung bình động `EMA(50)` phải nằm **trên** `EMA(200)` trên khung M1.

2.  **Swing High (Đỉnh cũ):** 
    *   Tìm thấy một đỉnh (Swing High) trong quá khứ gần (trong vòng 5 nến trước đó).
    *   Tại đỉnh đó, chỉ số **RSI(14) > 70** (Quá mua).

3.  **Sóng hồi (Pullback) hợp lệ:**
    *   Giá hiện tại không được vượt quá đỉnh cũ (Swing High).
    *   Thời gian hồi tối đa: 30 nến.
    *   Trong quá trình hồi, **RSI phải hồi về vùng 40-50** ít nhất một lần.
    *   Trong quá trình hồi, RSI không được giảm xuống dưới **32** (để đảm bảo không đảo chiều xu hướng mạnh).
    *   Trong sóng hồi, **không có nến GIẢM** nào có thân nến quá lớn (`Body >= 1.2 * ATR`).
    *   Cấu trúc giá: Không phá vỡ đáy cũ gần nhất (không tạo Lower Low).

4.  **Trendline Sóng Hồi:** 
    *   Vẽ được đường Trendline giảm nối từ Swing High qua các đỉnh thấp dần trong sóng hồi.
    *   *(Xem chi tiết mục 4 bên dưới)*

5.  **Tín hiệu Phá vỡ (Breakout):**
    *   Giá đóng cửa của nến hiện tại **phá lên trên (vượt qua)** đường Trendline.
    *   Giá đóng cửa phải **nằm trên đường EMA(50)**.
    *   **RSI phải đang hướng lên** (RSI hiện tại > RSI nến trước).
    *   Chỉ số **ADX(14) >= 20** (Xác nhận lực nến).

6.  **Không có Phân kỳ Đảo chiều (Bearish Divergence):** 
    *   Không xuất hiện tín hiệu phân kỳ giảm (Giá tạo đỉnh cao hơn nhưng RSI tạo đỉnh thấp hơn) trong 50 nến gần nhất.

7.  **Bộ lọc M5 (Quan trọng):** 
    *   Chỉ số **RSI(14) trên khung M5** phải nằm trong vùng **55 đến 65**. 
    *   *Giải thích: Thể hiện xu hướng tăng bền vững, không quá mua cũng không quá yếu.*

---

## 3. Điều Kiện SELL (Short)
Chỉ vào lệnh khi thỏa mãn **TẤT CẢ** các điều kiện sau:

1.  **Xu hướng giảm (Trend):** 
    *   Đường trung bình động `EMA(50)` phải nằm **dưới** `EMA(200)` trên khung M1.

2.  **Swing Low (Đáy cũ):** 
    *   Tìm thấy một đáy (Swing Low) trong quá khứ gần (trong vòng 5 nến trước đó).
    *   Tại đáy đó, chỉ số **RSI(14) < 30** (Quá bán).

3.  **Sóng hồi (Pullback) hợp lệ:**
    *   Giá hiện tại không được phá xuống dưới đáy cũ (Swing Low).
    *   Thời gian hồi tối đa: 30 nến.
    *   Trong quá trình hồi, **RSI phải hồi lên vùng 50-60** ít nhất một lần.
    *   Trong quá trình hồi, RSI không được tăng lên quá **68** (để đảm bảo không đảo chiều xu hướng mạnh).
    *   Trong sóng hồi, **không có nến TĂNG** nào có thân nến quá lớn (`Body >= 1.2 * ATR`).
    *   Cấu trúc giá: Không phá vỡ đỉnh cũ gần nhất (không tạo Higher High).

4.  **Trendline Sóng Hồi:** 
    *   Vẽ được đường Trendline tăng nối từ Swing Low qua các đáy cao dần trong sóng hồi.
    *   *(Xem chi tiết mục 4 bên dưới)*

5.  **Tín hiệu Phá vỡ (Breakout):**
    *   Giá đóng cửa của nến hiện tại **phá xuống dưới** đường Trendline.
    *   Giá đóng cửa phải **nằm dưới đường EMA(50)**.
    *   **RSI phải đang hướng xuống** (RSI hiện tại < RSI nến trước).
    *   Chỉ số **ADX(14) >= 20**.

6.  **Không có Phân kỳ Đảo chiều (Bullish Divergence):** 
    *   Không xuất hiện tín hiệu phân kỳ tăng (Giá tạo đáy thấp hơn nhưng RSI tạo đáy cao hơn) trong 50 nến gần nhất.

7.  **Bộ lọc M5 (Quan trọng):** 
    *   Chỉ số **RSI(14) trên khung M5** phải nằm trong vùng **35 đến 45**.
    *   *Giải thích: Thể hiện xu hướng giảm bền vững.*

---

## 4. Chi Tiết Trendline Sóng Hồi
Bot không vẽ trendline bằng cách nối thủ công các đỉnh/đáy ngoài cùng, mà sử dụng thuật toán toán học để xác định xu hướng chính của sóng hồi:

### 4.1. Quy trình vẽ Trendline cho lệnh BUY (Trendline giảm kháng cự)
1.  **Xác định vùng dữ liệu:** Lấy các cây nến từ **Swing High** đến cây nến hiện tại.
2.  **Tìm Đỉnh Cục Bộ (Local Maxima):** Tìm tất cả các cây nến có giá High cao hơn nến liền trước và liền sau.
3.  **Lọc đỉnh xu hướng Giảm (Strict Descending):**
    *   Bắt đầu từ Swing High.
    *   Chỉ chấp nhận các đỉnh tiếp theo nếu giá của nó **Thấp hơn hoặc Bằng** đỉnh hợp lệ trước đó.
    *   Bỏ qua các đỉnh nhô cao bất thường phá vỡ cấu trúc giảm ngắn hạn.
4.  **Tính toán đường thẳng:** Sử dụng **Hồi quy tuyến tính (Linear Regression)** đi qua các đỉnh hợp lệ đã lọc để tạo ra phương trình đường thẳng `y = ax + b`.

### 4.2. Quy trình vẽ Trendline cho lệnh SELL (Trendline tăng hỗ trợ)
1.  **Xác định vùng dữ liệu:** Lấy các cây nến từ **Swing Low** đến cây nến hiện tại.
2.  **Tìm Đáy Cục Bộ (Local Minima):** Tìm tất cả các cây nến có giá Low thấp hơn **2 nến** liền trước và **2 nến** liền sau (độ nhiễu ít hơn).
3.  **Lọc đáy xu hướng Tăng (Ascending Structure):**
    *   Bắt đầu từ Swing Low.
    *   Chấp nhận đáy sau **Cao hơn** đáy trước (Higher Low).
    *   *Cơ chế linh hoạt:* Có chấp nhận đáy thấp hơn đáy trước một chút (độ trễ nhỏ/nhiễu) miễn là nó vẫn **Cao hơn Swing Low** và sau đó giá tiếp tục tạo đáy cao hơn (đảm bảo cấu trúc tăng chưa bị gãy).
4.  **Tính toán đường thẳng:** Sử dụng **Hồi quy tuyến tính** đi qua các đáy hợp lệ.

### 4.3. Ý nghĩa
*   Việc dùng **Hồi quy tuyến tính** giúp đường Trendline "mượt" hơn và bám sát xu hướng trung bình của các đỉnh/đáy, tránh bị sai lệch bởi một vài râu nến (spikes) bất thường.
*   Yêu cầu tối thiểu phải có **2 điểm** (Swing Point + ít nhất 1 đỉnh/đáy nữa) mới vẽ được Trendline. Nếu sóng hồi quá dốc và không tạo ra cấu trúc đỉnh đáy rõ ràng, Bot sẽ không giao dịch (mã lỗi: "Không thể vẽ trendline").

---

## 5. Quản Lý Rủi Ro (Risk Management)
*   **Điểm vào lệnh (Entry):** Giá đóng cửa của nến phá vỡ trendline.
*   **Cắt lỗ (Stop Loss - SL):** `2 * ATR(14) + 6 Points` (Khoảng 2 ATR cộng thêm 0.6 pip).
*   **Chốt lời (Take Profit - TP):** `2 * SL` (Tỷ lệ Risk:Reward là 1:2).
*   **Khối lượng (Volume):**
    *   Mặc định là fix lot (0.01).
    *   Có chế độ tính lot theo `risk_percent` (ví dụ 1% tài khoản) nếu được bật trong config.

---
*Bot đi theo phong cách **Scalping theo xu hướng (Trend Following Scalp)**: chờ xác nhận xu hướng chính, chờ sóng hồi điều chỉnh, và vào lệnh khi giá phá vỡ sóng hồi để tiếp tục xu hướng chính, kết hợp đa khung thời gian M1/M5 để lọc nhiễu.*
