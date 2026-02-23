# Review: M1 Scalp XAUUSD – Chiến thuật & Kết quả thực tế

## 1. Tóm tắt chiến thuật (tuyen_trend_sclap_xau.py)

### Ý tưởng
- **M1 Scalp – Swing + Pullback + Trendline Break**: Vào lệnh khi giá phá vỡ trendline của sóng hồi (pullback) sau một swing high (BUY) hoặc swing low (SELL), có xác nhận RSI và cấu trúc xu hướng.

### Điều kiện chung
- **ATR(14) M1 ≥ 0.1** (XAUUSD): Chỉ giao dịch khi biến động đủ (lọc sideway).
- **Không divergence**: BUY không có Bearish Divergence, SELL không có Bullish Divergence.
- **RSI M5**:
  - BUY: RSI(14) M5 ∈ [55, 65].
  - SELL: RSI(14) M5 ∈ [35, 45].
- **Spam filter**: Cách tối thiểu 60s giữa hai lệnh cùng symbol.

### BUY (Swing High + Pullback + Trendline Break)
| # | Điều kiện |
|---|-----------|
| 1 | EMA50 > EMA200 (xu hướng tăng) |
| 2 | Có **Swing High** với RSI > 70, UpperWick < 1.3×ATR |
| 3 | **Sóng hồi hợp lệ**: không tạo đỉnh mới, ≤30 nến, RSI hồi về 40–50, RSI > 32 trong hồi, không nến giảm body ≥ 1.2×ATR, không nến có UpperWick ≥ 1.3×ATR, không phá cấu trúc tăng, slope pullback trong [-18, 48] |
| 4 | Vẽ **trendline** từ swing high qua các đỉnh thấp dần (pullback) |
| 5 | **Nến phá vỡ**: close > trendline, close ≥ EMA50, RSI quay lên, ADX ≥ 20 |
| 6 | Không Bearish Divergence |
| 7 | RSI M5 ∈ [55, 65] |

### SELL (Swing Low + Pullback + Trendline Break)
| # | Điều kiện |
|---|-----------|
| 1 | EMA50 < EMA200 (xu hướng giảm) |
| 2 | Có **Swing Low** với RSI < 30, LowerWick < 1.3×ATR |
| 3 | **Sóng hồi hợp lệ**: tương tự BUY (đáy cao dần, RSI 50–60, v.v.) |
| 4 | Trendline sóng hồi (tăng) từ swing low |
| 5 | Nến phá vỡ xuống (close < trendline, close ≤ EMA50, RSI quay xuống, ADX ≥ 20) |
| 6 | Không Bullish Divergence |
| 7 | RSI M5 ∈ [35, 45] |

### Risk
- **SL**: `2 × ATR(14)_M1 + 6 × point`
- **TP**: `2 × SL` → **Tỷ lệ R:R = 1:2**
- Volume: từ config hoặc risk-based (risk % balance).
- **Breakeven (utils.manage_position)**: Khi lợi nhuận **> 10 pip**, bot dời SL về giá entry (config `enable_breakeven: true` trong config_tuyen_xau.json). Lệnh đóng khi giá chạm SL mới → có thể đóng tại 0 nếu giá quay về entry.

---

## 2. Kết quả thực tế (orders_M1_Scalp_XAUUSD.csv)

### Thống kê mẫu (24 lệnh, ~10–20 Feb 2026)

| Chỉ số | Giá trị |
|--------|--------|
| **Tổng lệnh** | 24 |
| **BUY** | 7 (SwingHigh_Pullback_TrendlineBreak) |
| **SELL** | 17 (SwingLow_Pullback_TrendlineBreak) |
| **Lệnh có profit &lt; 0** | 10 (chạm SL gốc) |
| **Lệnh profit = 0** | 14 (**Breakeven**: bot dời SL về entry khi lợi nhuận đạt 10 pip, sau đó giá quay về chạm SL = entry → đóng 0) |
| **Lệnh profit &gt; 0** | 0 |
| **Tổng P/L** | **≈ -206.34 USD** |
| **Win rate (chỉ tính lệnh đóng có lãi vs lỗ)** | 0% (0 win / 10 loss) |

### Các lệnh lỗ lớn (USD)
- -54.17 (BUY, 13 Feb)
- -49.93 (SELL, 18 Feb)
- -37.97 (BUY, 13 Feb)
- -31.52 (SELL, 17 Feb)
- -20.12 (BUY, 16 Feb)
- -9.29 (SELL, 17 Feb)
- Còn lại: -1.88, -1.1, -0.36, -0.16, -0.14

### Nhận xét nhanh
1. **Lệnh profit = 0 là do Breakeven (theo thiết kế bot)**: Config `enable_breakeven: true` (config_tuyen_xau.json). Khi lợi nhuận đạt **10 pip**, bot gọi `manage_position()` trong `utils.py` và **dời SL về giá entry**. Sau đó nếu giá quay về chạm SL (entry) thì lệnh đóng với profit = 0. → 14 lệnh đóng 0 = 14 lệnh từng có lãi ≥10 pip rồi bị “ăn lại” về breakeven.
2. **Không có lệnh đóng tại TP (profit > 0) trong mẫu**: Mọi lệnh hoặc chạm SL gốc (lỗ) hoặc chạm SL breakeven (0). Không có lệnh nào chạm TP (2×SL).
3. **SELL nhiều hơn BUY (17 vs 7)**: Có thể xu hướng giảm nhiều hơn trong sample, hoặc điều kiện SELL dễ thỏa hơn.
4. **Lỗ tập trung vài ngày**: 13, 16, 17, 18 Feb → cần xem lại biến động và session (châu Á / London / NY).

---

## 3. Đánh giá & Đề xuất

### Điểm mạnh chiến thuật
- Logic rõ: swing + pullback + trendline break, có lọc RSI M1/M5, ATR, divergence, cấu trúc.
- R:R 1:2 (TP = 2×SL) hợp lý nếu win rate đủ cao.
- Nhiều filter (RSI, ADX, slope pullback, wick size) giảm tín hiệu rác.

### Vấn đề so với kết quả thực tế
1. **Win rate 0% trong mẫu**: Có thể sample ngắn hoặc giai đoạn không thuận; cần backtest dài hơn và nhiều market regime.
2. **Nhiều lệnh đóng 0**: Đây là **Breakeven** (10 pip → dời SL về entry), không phải SL quá sát hay đóng tay. Ý nghĩa: 14 lệnh từng có lãi ≥10 pip nhưng sau đó giá hồi về chạm SL breakeven → có thể TP (2×SL) đang xa, giá ít khi chạm TP trước khi bị kéo về.
3. **Lỗ lớn vài lệnh**: Một vài lệnh lỗ ~40–54 USD → kiểm tra volume và risk per trade (lot size vs balance).
4. **XAUUSD biến động mạnh**: ATR M1 có thể bị “noise” → trendline break trên M1 dễ false break; có thể cần thêm filter khung M5/M15 (session, structure) hoặc làm chặt điều kiện break.

### Đề xuất chỉnh sửa (gợi ý)
| Hạng mục | Đề xuất |
|----------|--------|
| **SL** | Thử nới SL (ví dụ 2.5×ATR hoặc 3×ATR) cho XAU để tránh bị quét bởi noise M1; hoặc giữ 2ATR nhưng chỉ vào khi ATR đủ lớn (ví dụ ATR > 0.15). |
| **TP** | Có thể giữ 2×SL; nếu thấy giá hay chạm TP rồi quay lại, có thể thử chốt 1.5×SL một phần. |
| **RSI M5** | Vùng 55–65 (BUY) / 35–45 (SELL) khá hẹp → có thể nới ra (ví dụ 52–68 và 32–48) và xem lại số lệnh vs chất lượng. |
| **Pullback** | max_candles=30 có thể dài với M1 → thử rút xuống 20–25 để tránh pullback “quá cũ”. |
| **Session / timeframe** | Chỉ cho phép vào lệnh trong session có volume (London, NY) hoặc thêm filter structure M5/M15 để tránh scalp M1 thuần trong sideway. |
| **Breakeven** | Hiện tại: 10 pip → dời SL về 0. 14 lệnh đóng 0 = từng có lãi ≥10 pip rồi bị kéo về. Có thể giữ (bảo vệ vốn) hoặc thử tăng trigger (ví dụ 15 pip) để ít bị “ăn lại” hơn. |
| **Backtest** | Chạy backtest dài (3–6 tháng) với dữ liệu M1 XAUUSD, so sánh win rate và profit factor với kết quả 24 lệnh thực tế. |

---

## 4. Kết luận

- **Chiến thuật**: M1 Scalp Swing + Pullback + Trendline Break có logic rõ, filter nhiều, R:R 1:2.
- **Kết quả mẫu (24 lệnh)**: Tổng P/L âm (~-206 USD), win rate 0%, nhiều lệnh đóng tại 0.
- **Hướng đi**: (1) Thu thập thêm dữ liệu thực tế và backtest dài hạn; (2) Điều chỉnh SL/ATR và RSI M5 cho phù hợp XAU; (3) Cân nhắc filter session/timeframe và làm chặt điều kiện break để giảm false signal trên M1.

File dữ liệu: `orders_M1_Scalp_XAUUSD.csv`  
Bot: `tuyen_trend_sclap_xau.py`
