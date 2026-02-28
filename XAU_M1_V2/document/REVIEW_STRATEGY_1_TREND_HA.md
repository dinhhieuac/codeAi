# Review chiến thuật – Strategy 1 Trend HA (XAU_M1_V2)

## Tổng quan

Bot giao dịch **theo trend** trên **XAUUSD M1**, kết hợp:
- **Heiken Ashi** (M1) để vào lệnh breakout khỏi kênh SMA55.
- **Trend** xác định bởi EMA trên M5 và H1.
- **ADX** lọc thị trường có xu hướng; **RSI** tránh vào lệnh quá mua/quá bán.

---

## Luồng logic chính

```
1. Quản lý position mở (trailing, breakeven) → nếu đủ max_positions thì thoát
2. Lấy dữ liệu M1, M5, H1 (200 nến)
3. Xác định trend M5 (close vs EMA200), trend H1 (close vs EMA100)
4. Kiểm tra H1 trùng với M5 (nếu bật)
5. Lọc ADX >= 35 trên M5
6. Tính kênh SMA55 High/Low trên M1, Heiken Ashi, RSI
7. BUY: nến HA xanh, close > SMA55 High, fresh breakout (nến trước <= SMA55 High), không doji, RSI 40–60
8. SELL: nến HA đỏ, close < SMA55 Low, fresh breakout, không doji, RSI 40–60
9. Spam filter: không vào lệnh mới trong 60s sau lệnh vừa mở
10. SL/TP: auto_m5 (High/Low nến M5 trước) hoặc fixed pips; R:R từ config (mặc định 1.5)
11. Gửi lệnh, log DB, gửi Telegram
```

---

## Điểm mạnh

| Nội dung | Đánh giá |
|----------|----------|
| **Đa khung thời gian** | M1 (entry), M5 (trend + ADX), H1 (confirm) → giảm tín hiệu ngược trend lớn. |
| **H1 = M5** | Chỉ vào khi H1 cùng chiều M5 → tránh vào đuổi trend đã quá dài trên H1. |
| **ADX ≥ 35** | Chỉ giao dịch khi có trend rõ → bỏ qua sideway yếu. |
| **RSI 40–60** | Tránh BUY khi RSI > 70, SELL khi RSI < 30; vùng 40–60 tránh quá mua/quá bán. |
| **Fresh breakout** | Chỉ vào khi nến trước **chưa** ở ngoài kênh (prev close <= SMA55 High với BUY) → tránh vào muộn sau khi đã breakout lâu. |
| **Loại doji** | Body HA > 20% range → tránh nến doji, tăng xác suất có momentum. |
| **SL auto_m5** | SL dựa High/Low nến M5 trước + buffer → gắn với cấu trúc giá, dễ quản lý. |
| **Trailing / Breakeven** | Có trong `manage_position` (utils) → bảo vệ lợi nhuận và giảm rủi ro. |
| **Spam filter 60s** | Tránh mở nhiều lệnh liên tiếp trên cùng một “setup”. |
| **Log & Telegram** | Log DB và gửi Telegram giúp theo dõi và audit. |

---

## Điểm yếu / Rủi ro

| Vấn đề | Mô tả | Gợi ý |
|--------|--------|--------|
| **EMA200 M5 = SMA** | Dòng 45: `rolling(window=200).mean()` là **SMA**, không phải EMA → tên biến `ema200` gây hiểu nhầm, tín hiệu chậm hơn EMA thật. | Đổi sang `ewm(span=200, adjust=False).mean()` hoặc đổi tên biến thành `sma200`. |
| **Import trùng** | `from db import Database` lặp 2 lần (dòng 10–11). | Xóa 1 dòng. |
| **sys.path.append('..')** | Thêm parent path → có thể import nhầm module của project khác nếu chạy từ thư mục khác. | Dùng `os.path.dirname(os.path.abspath(__file__))` và `sys.path.insert(0, script_dir)` như các strategy khác. |
| **Không lọc session** | Giao dịch 24/7, kể cả session có spread lớn hoặc thanh khoản kém. | Thêm filter theo session (vd 08:00–22:00 server) nếu backtest cho thấy session nào tốt hơn. |
| **Không giới hạn loss liên tiếp** | Không có cơ chế dừng sau N lệnh thua liên tiếp. | Cân nhắc thêm `max_consecutive_losses` và tạm dừng (như strategy_1_trend_ha_v2.py). |
| **RSI 40–60 hẹp** | RSI phải trong 40–60 mới vào → số tín hiệu có thể ít, dễ bỏ lỡ nhiều cơ hội. | Có thể nới ra (vd 35–65) hoặc A/B test so với bản hiện tại. |
| **Một nến HA** | Chỉ dựa vào **1 nến HA** cuối → dễ nhiễu trên M1. | Cân nhắc thêm điều kiện 2 nến HA cùng màu hoặc volume > avg. |
| **Buffer 20 point cố định** | Buffer SL/TP dùng `20 * point` (dòng 222) → với XAUUSD có thể quá nhỏ so với biến động. | Cân nhắc buffer theo ATR hoặc theo % của range nến M5. |

---

## Cấu trúc điều kiện vào lệnh (tóm tắt)

**BUY:**
- M5: close > EMA200 (bullish).
- H1: close > EMA100 và cùng chiều M5 (nếu bật).
- ADX M5 ≥ 35.
- Nến HA cuối: xanh, close > SMA55 High.
- Nến HA trước: close ≤ SMA55 High (fresh breakout).
- Không doji (body > 20% range).
- RSI: 40 ≤ RSI ≤ 60; loại RSI > 70 hoặc < 30.

**SELL:** Đối xứng (bearish, close < SMA55 Low, breakout xuống, RSI 40–60).

---

## Risk & Money management

- **SL:** auto_m5 = Low (BUY) / High (SELL) của nến M5 trước ± buffer; có kiểm tra khoảng cách tối thiểu (100 point).
- **TP:** theo `reward_ratio` (mặc định 1.5) so với khoảng cách từ entry đến SL.
- **Trailing / Breakeven:** thực hiện trong `manage_position` (config: trailing_enabled, breakeven_enabled, …).
- **Max positions:** 1 (config); không thêm lệnh mới nếu đã đủ.

---

## Khuyến nghị ưu tiên

1. **Sửa EMA M5:** Dùng EMA thật cho M5 (và đổi tên biến nếu vẫn dùng SMA).
2. **Bỏ import trùng và chuẩn hóa path:** Sửa import và `sys.path` như trên.
3. **Thêm filter session (tùy chọn):** Nếu có dữ liệu backtest theo session.
4. **Thêm giới hạn loss liên tiếp:** Ví dụ dừng tạm sau 3–5 lệnh thua liên tiếp.
5. **Cân nhắc buffer SL theo ATR:** Thay 20 point cố định bằng buffer phụ thuộc volatility.

---

## Kết luận

Chiến thuật **rõ ràng, đa khung thời gian, có lọc trend (M5 + H1), ADX và RSI**, và quản lý vị thế (trailing/breakeven). Phù hợp để giao dịch theo trend trên M1 với xác nhận từ M5/H1. Cần chỉnh nhỏ (EMA thật, path/import, bảo vệ loss liên tiếp, buffer SL) để đồng bộ code và tăng độ ổn định trong giao dịch thực tế.
