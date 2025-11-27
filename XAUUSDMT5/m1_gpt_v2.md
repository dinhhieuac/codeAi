Đã thêm rule "VÀO LỆNH CHUẨN NHẤT" vào bot m1_gpt_v2.py. Tóm tắt:
Những gì đã thêm:
1. Cấu hình mới (dòng 31-40):
    ENABLE_GOLDEN_ENTRY = True - Bật/tắt rule này
    EMA_FAST = 9, EMA_SLOW = 21 - EMA cho momentum
    CANDLE_BODY_MIN_RATIO = 0.5, CANDLE_BODY_MAX_RATIO = 0.8 - Nến dài 50-80%
    SPREAD_MAX = 0.15 - Spread tối đa
    VOLUME_INCREASE_MIN = 1.2, VOLUME_INCREASE_MAX = 1.4 - Volume tăng 20-40%
    STRUCTURE_LOOKBACK = 10 - Số nến để xác định Higher Low/Lower High
2. Các hàm kiểm tra mới:
    check_price_structure() - Điều kiện 1: Cấu trúc giá
    BUY: Higher Low hoặc phá đỉnh nhỏ (micro breakout)
    SELL: Lower High hoặc phá đáy nhỏ (micro breakdown)
    check_momentum() - Điều kiện 2: Momentum
    Nến dài 50-80% toàn nến
    EMA9 tách khỏi EMA21
    Spread ≤ 0.15
    Volume tăng 20-40% so với nến trước
    check_confirmation() - Điều kiện 3: Xác nhận
    BUY: Break micro high, close trên EMA9 sau retest EMA21, hoặc rejection đuôi dưới dài
    SELL: Break micro low, close dưới EMA9 sau retest EMA21, hoặc rejection đuôi trên dài
    check_golden_entry() - Tổng hợp 3 điều kiện
    Chỉ trả về signal khi đủ 3 điều kiện và cùng hướng
3. Tích hợp vào logic chính:
    Trong run_bot(), ưu tiên kiểm tra Golden Entry trước
    Nếu không có Golden Entry, dùng logic cũ (RETEST/BREAKOUT)
    Timing: Vào lệnh ngay khi nến trigger đóng (0-1 giây sau)
4. Cách sử dụng:
    Bật: ENABLE_GOLDEN_ENTRY = True (mặc định)
    Tắt: ENABLE_GOLDEN_ENTRY = False → Bot dùng logic cũ (RETEST/BREAKOUT)
    Bot sẽ chỉ vào lệnh khi đủ 3 điều kiện cùng lúc, giúp tăng winrate và giảm false signals.