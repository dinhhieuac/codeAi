Đã điều chỉnh các thông số trong CoinMt5/eth_m1_gpt.py cho phù hợp với ETHUSD. Tóm tắt thay đổi:
Các thay đổi chính:
1. Điều chỉnh ATR và Pip Value:
get_pip_value(): Đổi từ 0.01 (XAUUSD) → 1.0 (ETHUSD) - Với ETHUSD: 1 pip = 1 USD
calculate_atr_from_m1(): ATR trả về trực tiếp (không chia cho 0.01) - Với ETHUSD: ATR đã là pips
2. Điều chỉnh thông số SL/TP:
SL_POINTS_MIN: 50 → 3 (3 pips)
SL_POINTS_MAX: 50000 → 500 (500 pips)
TP_POINTS_MIN: 80 → 5 (5 pips)
TP_POINTS_MAX: 50000 → 1000 (1000 pips)
Lưu ý: Với ETHUSD, 1 pip = 1 point (không phải 10 points như XAUUSD)
3. Điều chỉnh ATR Filter:
ATR_MIN_THRESHOLD: 100 → 5 pips (phù hợp với biến động ETHUSD)
4. Điều chỉnh khoảng cách Retest/Breakout:
RETEST_DISTANCE_MAX: 60 → 6 pips (6 points)
BREAKOUT_DISTANCE_MIN: 100 → 10 pips (10 points)
BREAKOUT_DISTANCE_MAX: 200 → 30 pips (30 points)
5. Điều chỉnh Break Even:
BREAK_EVEN_START_POINTS: 100 → 5 pips
pips_buffer: 10 points → 1 point (1 pip)
6. Sửa logic tính toán trong send_order():
Fixed SL: FIXED_SL_USD trực tiếp = pips (không chia cho 0.01)
ATR-based SL/TP: Không nhân 10 (vì 1 pip = 1 point)
Tất cả các chỗ hiển thị pips: Bỏ chia cho 10
7. Sửa Trailing Stop:
trailing_step_points: Không nhân 10 (vì 1 pip = 1 point)
Hiển thị profit: Bỏ chia cho 10
Bot đã được điều chỉnh cho ETHUSD với các thông số phù hợp với biến động và đặc tính của cặp này.