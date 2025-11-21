CHIẾN THUẬT 1: “BÁM THEO H1 – ĂN 5–10 PHÚT”

Đây là chiến thuật dễ nhất và hiệu quả nhất khi bạn:
Không muốn phân tích nhiều
Không muốn bị trap
Muốn vào lệnh nhanh
Muốn bot chạy ổn định

Cách làm:
1. Xác định hướng H1 bằng EMA50
Giá > EMA50 → CHỈ BUY
Giá < EMA50 → CHỈ SELL
➡️ Không phân tích gì thêm → tránh 90% thua do ngược trend.

2. Chọn điểm vào ở M1 khi giá RETEST lại EMA20
Công thức cực dễ:
Trend BUY → chờ giá M1 chạm EMA20 (hoặc dưới 3–6 pip) → BUY
Trend SELL → chờ giá M1 chạm EMA20 → SELL
➡️ Không đuổi lệnh
➡️ Không cần phân tích nến
➡️ Vào đúng vùng pullback đẹp.

3. TP 10–20 pip – SL 8–15 pip
→ Không tham
→ Rơi về đúng tỷ lệ win cao nhất của XAU (scalp theo trend).

Vì sao chiến thuật này dễ ăn?
Trend lớn H1 rất bền → bạn chỉ vào khi giá đang chạy cùng xu hướng chính.
M1 retest EMA20 → xác suất bật lại rất cao.
Không phân tích quá nhiều → không rối.
Không bị flip tín hiệu như M15.
Bot sẽ:
Chỉ BUY khi H1 trend là BUY và giá M1 retest EMA20 từ dưới lên
Chỉ SELL khi H1 trend là SELL và giá M1 retest EMA20 từ trên xuống
Tránh giao dịch khi thị trường đi ngang (ADX < 25)
TP 10-20 pip, SL 8-15 pip
Lưu ý: Các cảnh báo linter về import MetaTrader5 và pandas chỉ là warning do linter không tìm thấy thư viện, không ảnh hưởng đến chạy bot.

update 1
ENTRY BREAKOUT (KHI GIÁ KHÔNG RETEST)

Cực kỳ đơn giản:

Điều kiện SELL (vì H1 đang SELL):

ADX > 28

H1 trend SELL

Giá M1 phá đáy gần nhất trong khi còn cách EMA20 > 10–20 point

Không cần retest

→ Bot SELL follow momentum
→ TP nhanh 10–20 point
→ SL nhỏ phía trên vùng breakout