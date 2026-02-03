Đã chuyển từ H1 sang M15 để xác định xu hướng. Tóm tắt thay đổi:
Các thay đổi đã thực hiện:
1. Thay đổi biến config:
EMA_H1 = 50 → EMA_M15 = 50 (EMA50 trên M15)
2. Thay đổi hàm kiểm tra xu hướng:
check_h1_trend() → check_m15_trend()
Sử dụng mt5.TIMEFRAME_M15 thay vì mt5.TIMEFRAME_H1
Cập nhật log từ [H1 TREND] → [M15 TREND]
3. Cập nhật các hàm liên quan:
check_m1_retest_ema20(): Nhận m15_trend thay vì h1_trend
check_m1_breakout(): Nhận m15_trend thay vì h1_trend
Tất cả logic so sánh đã được cập nhật
4. Cập nhật phần run_bot():
Tất cả tham chiếu h1_trend → m15_trend
Log messages: H1 Trend → M15 Trend
Mô tả chiến thuật: "BÁM THEO H1" → "BÁM THEO M15"
5. Cập nhật comments và descriptions:
Tất cả comments và mô tả đã được cập nhật từ H1 sang M15
Kết quả:
Bot sẽ:
Xác định xu hướng trên khung M15 bằng EMA50 (thay vì H1)
Chỉ BUY khi M15 trend = BUY (Giá > EMA50 trên M15)
Chỉ SELL khi M15 trend = SELL (Giá < EMA50 trên M15)
Vào lệnh ở M1 khi giá retest EMA20 hoặc breakout
Bot hiện sử dụng M15 để xác định xu hướng thay vì H1.