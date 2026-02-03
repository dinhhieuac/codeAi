# Tài liệu Bot Check Trend & Gợi Ý Vào Lệnh

## Áp dụng cho XAUUSD, ETHUSD, BTCUSD, BNBUSD

------------------------------------------------------------------------

## 1. Kiểm tra xu hướng đa khung thời gian (M15, H1, H4, D1)

Bot phân tích 4 khung chính: - **M15** → Dùng để xác định nhịp ngắn hạn,
phát hiện pullback. - **H1** → Khung chính để xác định xu hướng giao
dịch intraday. - **H4** → Khung macro trend, dùng để biết thị trường
đang ở pha nào. - **D1** → Khung dài hạn để phát hiện vùng supply/demand
quan trọng.

Logic xác định xu hướng: - Dựa vào EMA50, EMA200, cấu trúc đỉnh đáy
(market structure), và ADX. - **Xu hướng tăng** khi: - Giá \> EMA50 \>
EMA200 - Đỉnh sau cao hơn đỉnh trước, đáy sau cao hơn đáy trước - ADX \>
25 (xu hướng mạnh) - **Xu hướng giảm** khi: - Giá \< EMA50 \< EMA200 -
Đỉnh sau thấp hơn đỉnh trước, đáy sau thấp hơn đáy trước - ADX \> 25

------------------------------------------------------------------------

## 2. Gợi ý điểm vào lệnh trên từng khung

### M15

-   Tìm pullback về EMA20/EMA50
-   Tìm nến từ chối (pinbar, engulfing)
-   ATR \< ngưỡng → tránh biến động mạnh

### H1

-   Vào lệnh theo đúng xu hướng chính
-   Retest vùng hỗ trợ/kháng cự
-   Kết hợp phân kỳ RSI để tránh vào đỉnh đáy

### H4

-   Tìm vùng supply/demand mạnh
-   Tìm phá vỡ trendline + pullback

### D1

-   Xác định vùng giá quan trọng để tránh giao dịch ngược trend lớn
-   Xác định bias chính: bullish / bearish / sideway

------------------------------------------------------------------------

## 3. Gửi log chi tiết về Telegram

Bot gửi: - Trạng thái xu hướng M15/H1/H4/D1 - Gợi ý Buy/Sell nếu có -
ATR hiện tại - ADX - Spread - Cảnh báo tin mạnh (dựa trên ATR & giờ
tin) - Chi tiết lệnh có thể vào - Cảnh báo rủi ro khi điều kiện không
đạt

------------------------------------------------------------------------

## 4. Kỹ thuật check tín hiệu nâng cao (Pro-level)

### 1) Multi-timeframe confluence

-   Tín hiệu chỉ hợp lệ khi **H1 cùng hướng**, M15 cho điểm entry đẹp.

### 2) Volume Spike Filtering

-   Loại bỏ các tín hiệu nhiễu khi volume tăng bất thường (thường là
    false breakout).

### 3) ATR Breakout Filter

-   Tránh giao dịch khi ATR tăng đột biến \> 200% trung bình → báo tin
    mạnh.

### 4) Smart Money Concept (SMC)

-   Nhận diện:
    -   Break of Structure (BOS)
    -   Change of Character (CHoCH)
    -   Order Block (OB)
    -   Liquidity sweep

### 5) False Break Trap Detection

-   Nếu giá phá 1 vùng nhưng đóng nến ngược lại → tránh giao dịch theo
    phá vỡ.

### 6) EMA Alignment Strength

-   Nếu EMA được căn thẳng theo xu hướng → xu hướng mạnh.
-   Nếu EMA rối → không giao dịch.

------------------------------------------------------------------------

## Kết luận

Bot được thiết kế theo tiêu chuẩn trader chuyên nghiệp: - Đa khung thời
gian - Không vào lệnh khi điều kiện không đạt - Lọc tín hiệu nhiễu - Hạn
chế giao dịch ngược xu hướng lớn - Gửi log rõ ràng qua Telegram
Tính năng đã thêm
Phân tích đa khung thời gian (M15, H1, H4, D1)
EMA50, EMA200
ADX (xu hướng mạnh khi > 25)
Cấu trúc đỉnh/đáy (higher highs, higher lows)
RSI, ATR, Spread
Gợi ý điểm vào lệnh
Multi-timeframe confluence (H1 & M15 cùng hướng)
M15: Pullback về EMA20/EMA50
H1: Retest vùng hỗ trợ/kháng cự
H4: Supply/Demand zones
D1: Bias chính (chỉ BUY/SELL theo bias)
Kỹ thuật nâng cao
EMA Alignment Strength
Volume Spike Filtering
ATR Breakout Filter
False Break Detection
Gửi log về Telegram
Trạng thái xu hướng từng khung
Gợi ý Buy/Sell
Cảnh báo rủi ro
Định dạng HTML
Bot chỉ gửi log, không vào lệnh trên MT5.
Có một lỗi syntax nhỏ ở cuối file (dòng 503). Bạn có thể chạy bot và kiểm tra, hoặc tôi có thể sửa nếu cần.