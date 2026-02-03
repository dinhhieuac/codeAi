Dựa trên kinh nghiệm từ các trader chuyên nghiệp, chiến lược scalping đơn giản nhất trên M1 cho XAUUSD mà tôi thấy hiệu quả cao là sử dụng EMA crossover kết hợp ATR để quản lý rủi ro. Nó dễ setup trên bất kỳ nền tảng nào như MT4/MT5 hay TradingView, không cần phân tích phức tạp, chỉ theo tín hiệu crossover và volatility hiện tại. Tỷ lệ thắng có thể lên 60-70% nếu trade có kỷ luật (dựa trên backtest từ các nguồn), nhưng nhớ rằng không có chiến lược nào đảm bảo 100% - gold biến động mạnh, dễ slip.
Setup Indicators:

EMA 14 (fast, màu xanh).
EMA 28 (slow, màu đỏ).
ATR 14 (để tính SL/TP động).

Quy tắc Entry:

Buy (Long): Khi EMA 14 cắt lên trên EMA 28. Chỉ trade nếu đang ở session volatile như London hoặc New York (tránh Asian range-bound).
Sell (Short): Khi EMA 14 cắt xuống dưới EMA 28. Tương tự, ưu tiên session mạnh.

Không entry nếu đang có news lớn (kiểm tra calendar nhanh).
Quy tắc Exit:

Stop Loss (SL): ATR 14 x 30 (đặt dưới entry cho buy, trên entry cho sell). Ví dụ, nếu ATR = 0.5, SL = 15 pips.
Take Profit (TP): ATR 14 x 30 (đặt trên entry cho buy, dưới entry cho sell) - nhắm RR 1:1.
Hoặc trail SL khi lời 1/2 TP để lock profit nếu trend mạnh.

Tips từ pro:

Risk max 0.5-1% tài khoản per trade.
Chỉ 2-5 trade/ngày, tránh overtrade trên M1 vì noise cao.
Kết hợp với cảm nhận: Nếu price đang respect level round number (như 2500.00), tăng xác suất.
Backtest ít nhất 100 trade trước khi live.

Chiến lược này dựa trên trend-following cơ bản, dễ theo dõi mà không cần "cảm nhận" quá sâu - cứ theo crossover là đánh. Nếu muốn variant khác, thử Heiken Ashi breakout: Wait price break channel 55-MA high/low với candle Heiken Ashi đổi màu, SL ATR x2.5, TP 1.5x risk - cũng đơn giản, tỷ lệ cao hơn ở trend market. Luôn nhớ, trading là rủi ro - dùng demo trước.


Đã cập nhật toàn bộ rule trong m1_grok.py theo tài liệu m1_grok.md. Tóm tắt thay đổi:
Các thay đổi chính:
1. Cập nhật Indicators:
✅ EMA 14 (fast) và EMA 28 (slow) thay cho EMA50 H1 và EMA20 M1
✅ ATR 14 để tính SL/TP động
2. Entry Rules (theo m1_grok.md):
✅ Buy: EMA 14 cắt lên EMA 28
✅ Sell: EMA 14 cắt xuống EMA 28
✅ Session Filter: Chỉ trade trong London (8:00-16:00 GMT) hoặc New York (13:00-21:00 GMT), tránh Asian session
✅ Daily Limit: Chỉ 2-5 trade/ngày (MAX_TRADES_PER_DAY = 5)
3. Exit Rules (theo m1_grok.md):
✅ SL: ATR × 30 (ví dụ: ATR = 0.5 → SL = 15 pips)
✅ TP: ATR × 30 (RR 1:1)
✅ Trailing Stop: Trail SL khi lời 1/2 TP, bước trailing = ATR × 0.5
4. Risk Management:
✅ Risk max 0.5-1% tài khoản per trade (RISK_PER_TRADE_PERCENT = 0.5)
✅ Chỉ 2-5 trade/ngày (MAX_TRADES_PER_DAY = 5)
5. Các hàm mới:
✅ check_trading_session(): Kiểm tra session hiện tại (London/New York/Asian)
✅ check_ema_crossover(): Kiểm tra EMA14 cắt EMA28
✅ manage_positions(): Cập nhật để trail SL khi lời 1/2 TP
6. Logic trong run_bot():
✅ Kiểm tra session trước khi vào lệnh
✅ Kiểm tra EMA crossover (EMA14 vs EMA28)
✅ Kiểm tra daily limit (2-5 trade/ngày)
✅ Reset daily trades count khi sang ngày mới
Các lỗi còn lại chỉ là warnings về import (MetaTrader5, pandas, pytz) - đây là các thư viện bên ngoài, không ảnh hưởng đến chức năng. Bot đã được cập nhật theo đúng tài liệu m1_grok.md.