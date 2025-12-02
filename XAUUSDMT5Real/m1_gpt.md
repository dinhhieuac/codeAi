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



1.Đổi trend H1 → Trend M5 (EMA50/EMA100)
    M5 > EMA50 → CHỈ BUY
    M5 < EMA50 → CHỈ SELL
2.Sửa lại RETEST EMA20 M1 (6 pips → 10–20 pips)
    Vùng retest EMA20: 10–20 pips (100–200 points)
3.ATR Filter sửa lại (≥40 pips & ≤200 pips)
    ATR M1 tối thiểu: 40–60 pips
    ATR quá cao (>200–250 pips) thì không giao dịch (tránh tin mạnh)
4.Loại tín hiệu BREAKOUT khi M1 nhiễu
    Breakout M1 cực kỳ nhiễu vì:
        M1 fake rất nhiều
        Spread trượt
        Stop loss dễ bị quét
    Breakout chỉ nên dùng nếu:
        ADX(M5) > 35
        Volume tăng liên tục
        Spread nhỏ
5.Thêm bộ lọc NẾN XẤU M1
    Bỏ tín hiệu nếu nến M1 có:
    Bóng dưới > 60% thân (không BUY)
    Bóng trên > 60% thân (không SELL)
    Doji, pin bar, spinning top → bỏ
6.Không kiểm tra nến Momentum
    Bot vào ngẫu nhiên ngay sau 1 cây nến quá lớn (dễ bị đuối lực).
    ✔ Nên yêu cầu:
    Buy
    Không BUY ngay sau 1 nến tăng mạnh > 40–60 pips (chờ pullback)
    Sell
    Không SELL ngay sau 1 nến giảm mạnh > 40–60 pips
8) Không kiểm tra cấu trúc M1
    Bot chỉ dùng EMA20 → Nhưng M1 cần biết cấu trúc:
    Đỉnh sau cao hơn → BUY
    Đáy sau thấp hơn → SELL
    Nếu M1 đang giảm → bot không được BUY, dù H1 tăng.
9) Chưa có Spread Filter theo biến động
    Spread > 20–25 points → bỏ lệnh M1.
    Hiện tại bạn đặt Spread Filter đúng rồi, nhưng cần ẩn tín hiệu sau khi bị chặn (để tránh vào lại khi spread co lại trong 1–2 giây).

    Đang đọc file để nắm cấu trúc, sau đó cập nhật theo yêu cầu:


[2 tools called]


Tạo todo list và bắt đầu cập nhật bot theo yêu cầu:


[2 tools called]


Bắt đầu cập nhật bot theo yêu cầu:


[4 tools called]


Thêm các hàm filter mới và cập nhật logic breakout:


[2 tools called]


Thay thế hàm breakout cũ và thêm các hàm filter mới:


[1 tool called]


Đang đọc lại file để kiểm tra trạng thái hiện tại:


[1 tool called]


Thêm các hàm filter mới trước hàm `check_last_loss_cooldown`:


[1 tool called]


Cập nhật vòng lặp chính để sử dụng M5 và áp dụng các filter mới:


[1 tool called]


Đang đọc phần main loop để cập nhật:


[1 tool called]


Cập nhật main loop theo từng phần:


[11 tools called]


Đã cập nhật bot theo yêu cầu. Tóm tắt thay đổi:

## Các thay đổi đã hoàn thành

1. Đổi H1 → M5 trend: Dùng EMA50 trên M5 thay vì H1
2. Sửa RETEST EMA20: Vùng retest từ 6 pips → 10-20 pips (100-200 points)
3. Sửa ATR Filter: 40-200 pips (tránh tin mạnh khi ATR > 200 pips)
4. Sửa BREAKOUT: Chỉ dùng khi:
   - ADX(M5) > 35
   - Volume tăng liên tục
   - Spread < 20-25 points
   - Mặc định tắt (ENABLE_BREAKOUT = False)
5. Thêm Bad Candle Filter: Bỏ tín hiệu nếu:
   - Bóng dưới > 60% thân (không BUY)
   - Bóng trên > 60% thân (không SELL)
   - Doji (thân < 20% range)
6. Thêm Momentum Filter: Không trade sau nến > 40-60 pips
7. Thêm Structure Filter: Kiểm tra cấu trúc M1 (đỉnh/đáy)
8. Thêm Spread Filter: Bỏ lệnh nếu spread > 20-25 points

## Các hàm mới đã thêm

- `check_bad_candle()`: Kiểm tra nến xấu
- `check_momentum_candle()`: Kiểm tra nến momentum
- `check_m1_structure()`: Kiểm tra cấu trúc M1
- `check_spread_filter()`: Kiểm tra spread

Bot đã được cập nhật và sẵn sàng sử dụng. Tất cả các filter được tích hợp vào main loop và sẽ chặn tín hiệu không phù hợp.