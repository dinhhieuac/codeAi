# Review chiến thuật – Strategy 1 Trend HA V2 (XAU_M1_V2)

## Tổng quan

Phiên bản **nâng cấp** của Strategy 1 Trend HA: cùng logic breakout Heiken Ashi + kênh SMA55 trên M1, nhưng thêm **nhiều lớp bảo vệ** (session, consecutive losses, ADX tăng, CHOP, ATR volatility, liquidity sweep, displacement, confirmation, false breakout) và **SL/TP** tối ưu hơn (buffer theo ATR M5).

---

## So sánh nhanh với bản Strategy 1 (Trend HA gốc)

| Hạng mục | Strategy 1 (gốc) | Strategy 1 V2 |
|----------|-------------------|----------------|
| Trend M5 | Close vs EMA200 | EMA200 + tùy chọn EMA50 > EMA200 |
| Trend H1 | Bắt buộc EMA100 = M5 | Tùy chọn EMA200 = M5 |
| ADX | ADX ≥ 35 | **ADX hiện tại > ADX trước** (trend đang mạnh lên) |
| RSI BUY/SELL | 40–60 | Mặc định BUY 50–65, SELL 35–50 (config 40–60) |
| Session | Không | **08:00–22:00** (tránh Asian) |
| Consecutive losses | Không | **Dừng sau 3 lệnh thua** (config) |
| CHOP filter | Không | **Bắt buộc** (body_avg, overlap) |
| ATR volatility | Không | **Bắt buộc** (ATR trong band 0.5x–2.5x avg) |
| Liquidity sweep | Không | Tùy chọn (config: true) |
| Displacement | Không | Tùy chọn (config: true) |
| Volume confirmation | Không | Tùy chọn |
| Confirmation nến | Không | 1 nến + **false breakout** (đóng lại trong kênh = bỏ) |
| SL buffer | 20 point cố định | **ATR M5 × 2.0** (config) |
| Spam filter | 60s | **300s** (config) |

---

## Luồng logic chính (thứ tự thực thi)

```
0. Consecutive losses: nếu 3 lệnh thua liên tiếp → STOP, không vào lệnh mới
0.5. Session: chỉ trade 08:00–22:00 (trừ khi config = "ALL")
1. Quản lý position (trailing, breakeven), nếu đủ max_positions → thoát
2. Lấy M1, M5, H1 (200 nến)
3. Trend M5: close vs EMA200; tùy chọn EMA50 > EMA200 (bull) hoặc EMA50 < EMA200 (bear)
4. H1 trend (EMA200): tùy chọn phải trùng M5
5. ADX: chỉ vào khi ADX hiện tại > ADX nến trước (trend đang mạnh lên)
6. ATR volatility: ATR trong [0.5×, 2.5×] ATR trung bình 50 nến
7. CHOP filter: không trade nếu body_avg < 0.5×ATR và overlap > 70%
8. Kênh SMA55 M1, Heiken Ashi, RSI, ATR M1
9. BUY: HA xanh, above channel, fresh breakout, không doji, RSI trong khoảng (50–65 mặc định)
    → Tùy chọn: Liquidity Sweep BUY, Displacement BUY, Volume > avg
    → Confirmation: nến HA giữ close > SMA55 High, không false breakout (close không đóng lại trong kênh)
10. SELL: đối xứng (HA đỏ, below channel, RSI 35–50, sweep/displacement/volume tùy chọn, confirmation + false breakout)
11. Spam filter: không vào lệnh mới trong 300s (config) sau lệnh vừa mở
12. SL: auto_m5 = High/Low M5 trước ± buffer (buffer = atr_buffer_multiplier × ATR M5, default 2.0)
13. TP: R:R từ config (1.5)
14. Gửi lệnh, log DB, Telegram
```

---

## Điểm mạnh

| Nội dung | Đánh giá |
|----------|----------|
| **Session filter** | Tránh Asian session (08:00–22:00) → giảm spread/thanh khoản kém. |
| **Consecutive losses** | Dừng sau N lệnh thua → bảo vệ vốn khi chuỗi thua. |
| **ADX current > previous** | Chỉ vào khi trend **đang mạnh lên** → tránh vào lúc ADX đỉnh/suy yếu. |
| **CHOP filter** | Body nhỏ + overlap cao → không trade trong range/chop. |
| **ATR volatility** | Tránh ATR quá thấp (yên tĩnh) hoặc quá cao (biến động cực đoan). |
| **Liquidity sweep** | Tùy chọn: sweep qua swing low/high + wick ≥ 1.2×ATR → vào theo hướng “bẫy” liquidity. |
| **Displacement** | Tùy chọn: body ≥ 1×ATR và close breakout range 10 nến → nến có momentum. |
| **False breakout** | Nếu nến confirmation đóng lại trong kênh → bỏ tín hiệu → giảm fake breakout. |
| **SL buffer theo ATR M5** | Buffer = 2×ATR M5 thay vì điểm cố định → SL phù hợp volatility. |
| **EMA thật** | M5/H1 dùng `ewm(span=..., adjust=False).mean()` → đúng EMA. |
| **Nhiều tùy chọn config** | H1, EMA50/200, sweep, displacement, volume có thể bật/tắt → linh hoạt backtest/live. |
| **Log & bảo vệ DB** | Log signal/order có try/except → tránh crash khi DB lỗi. |

---

## Điểm yếu / Rủi ro

| Vấn đề | Mô tả | Gợi ý |
|--------|--------|--------|
| **ADX > previous rất chặt** | Chỉ cần ADX tăng 1 bước so với nến trước; nếu ADX dao động quanh 30–35 có thể bỏ nhiều cơ hội. | Cân nhắc thêm điều kiện ADX ≥ ngưỡng tối thiểu (vd 25) để tránh vào khi trend quá yếu. |
| **RSI BUY 50–65 / SELL 35–50** | Vùng hẹp → ít tín hiệu; nếu config 40–60 cho cả hai thì đối xứng hơn. | So sánh backtest với vùng rộng hơn (vd 45–65 BUY, 35–55 SELL). |
| **Liquidity sweep dùng nến M1** | Swing high/low trong 20 nến M1 → có thể nhiều “sweep” nhỏ, không phải sweep đẹp trên M5. | Có thể thêm sweep trên M5 hoặc tăng lookback khi cần setup lớn hơn. |
| **Sweep/Displacement bật trong config** | config_1_v2.json có `liquidity_sweep_required: true`, `displacement_required: true` → số tín hiệu có thể rất ít. | Backtest so sánh bật vs tắt để cân bằng số lệnh và chất lượng. |
| **Confirmation 1 nến** | Chỉ 1 nến confirmation + false breakout → vẫn có thể nhiễu trên M1. | Có thể thử confirmation_candles = 2 khi muốn chặt hơn. |
| **check_consecutive_losses dùng history_deals** | Lọc `d.entry == DEAL_ENTRY_OUT`; nếu broker có deal khác (swap, commission…) có thể đếm sai. | Kiểm tra với broker thực tế; có thể lọc thêm theo symbol/position. |
| **Session theo server** | 08:00–22:00 là giờ server; nếu server khác múi giờ VN thì khung “Asian” lệch. | Ghi rõ timezone trong config hoặc đổi sang session theo giờ VN nếu cần. |

---

## Cấu trúc điều kiện vào lệnh (tóm tắt)

**BUY (đủ điều kiện):**
- Session trong 08:00–22:00 (hoặc ALL).
- Không bị dừng bởi consecutive losses.
- M5: close > EMA200; tùy chọn EMA50 > EMA200.
- H1 (nếu bật): trend = M5.
- ADX hiện tại > ADX nến trước.
- ATR trong [0.5×, 2.5×] ATR trung bình.
- Không trong vùng CHOP (body_avg, overlap).
- Nến HA xanh, close > SMA55 High, fresh breakout, không doji.
- RSI trong khoảng (mặc định 50–65; config có thể 40–60).
- Tùy chọn: Liquidity Sweep BUY (sweep qua swing low + wick ≥ 1.2×ATR + nến bullish).
- Tùy chọn: Displacement (body ≥ 1×ATR, close > range high 10 nến).
- Tùy chọn: Volume > 1.1× vol_ma.
- Confirmation: nến HA giữ close > SMA55 High; không false breakout (close không đóng lại trong kênh).

**SELL:** Đối xứng (bearish, below channel, RSI 35–50, sweep/displacement/volume/confirmation tương ứng).

---

## Risk & Money management

- **Session:** 08:00–22:00 (config), tránh Asian.
- **Consecutive losses:** Dừng tạm sau 3 lệnh thua (config).
- **SL:** auto_m5 = Low (BUY) / High (SELL) của nến M5 trước ± buffer (buffer = atr_buffer_multiplier × ATR M5, default 2.0); có kiểm tra min distance.
- **TP:** R:R từ config (1.5).
- **Trailing / Breakeven:** Trong `manage_position` (config).
- **Spam filter:** 300s (config) giữa hai lệnh.
- **Max positions:** 1.

---

## Khuyến nghị ưu tiên

1. **ADX:** Cân nhắc thêm điều kiện ADX ≥ 25 (hoặc config) để tránh vào khi trend quá yếu dù ADX tăng.
2. **Config:** So sánh backtest với `liquidity_sweep_required: false` và `displacement_required: false` để xem số lệnh và win rate; nếu ít lệnh quá có thể tắt hoặc nới điều kiện.
3. **Consecutive losses:** Kiểm tra với broker thực tế (deals, ENTRY_OUT) để đảm bảo đếm đúng 3 lệnh thua.
4. **Session:** Ghi rõ timezone (server) trong config hoặc comment; nếu cần có thể thêm option session theo giờ VN.
5. **Telegram message:** Dòng RSI trong message đang in "40-60" cho cả BUY và SELL; nên lấy từ config (rsi_buy_min/max, rsi_sell_min/max) để hiển thị đúng.

---

## Kết luận

Strategy 1 Trend HA **V2** là bản **nặng filter** và **bảo vệ vốn** (session, consecutive losses, CHOP, ATR band, ADX tăng). Các filter tùy chọn (Liquidity Sweep, Displacement, Volume, H1, EMA50/200) giúp tinh chỉnh độ chặt/lỏng. SL buffer theo ATR M5 và false breakout detection hợp lý cho scalping theo trend. Cần cân bằng số lệnh vs chất lượng qua config (sweep, displacement, RSI range) và kiểm tra ADX + consecutive losses với dữ liệu thực tế.
