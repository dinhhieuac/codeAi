# Báo cáo phân tích: Các yếu tố làm nên chiến thắng của Bot XAU_M1

Dựa trên dữ liệu export từ `orders_export_Strategy_1_Trend_HA_*.csv` và `orders_export_Strategy_1_Trend_HA_V2_*.csv`.

---

## 1. Tổng quan kết quả

| Chỉ số | Giá trị |
|--------|---------|
| Tổng lệnh đã đóng | 18 |
| Win | 8 |
| Loss | 10 |
| **Win rate** | **44.4%** |

*Lưu ý: Mẫu còn nhỏ (vài ngày). Cần chạy dài hạn để kết luận ổn định.*

---

## 2. Các yếu tố làm nên chiến thắng (Win factors)

### 2.1. RSI (Relative Strength Index)

- **Win:** RSI trung bình **58.25** (min 55.6, max 60.6).
- **Loss:** RSI trung bình **56.15** (min 39.4, max 60.2).
- **Kết luận:** Lệnh thắng có RSI lúc vào lệnh **cao hơn** lệnh thua khoảng **+2.1 điểm**. Với **BUY**, RSI trong vùng **57–61** (momentum tăng nhưng chưa quá mua) thường gắn với Win hơn.

**Gợi ý:**  
- Giữ/điều chỉnh ngưỡng BUY: RSI > 55–58 (config hiện tại 55–58 là hợp lý).  
- Có thể thử **RSI > 57** để giảm tín hiệu yếu, đổi lại ít lệnh hơn.

---

### 2.2. ADX (Average Directional Index – sức mạnh xu hướng)

- **Win:** ADX trung bình **46.95** (42.5 – 55.0).
- **Loss:** ADX trung bình **56.75** (33.7 – 73.6).
- **Kết luận:** Lệnh thắng có **ADX thấp hơn** lệnh thua khoảng **-9.8**. ADX **quá cao** (ví dụ > 55–60) trong mẫu này thường đi kèm **Loss** (vào lệnh muộn, gần đỉnh/đáy hoặc exhaustion).

**Gợi ý:**  
- Thêm filter **ADX không quá cao**: ví dụ chỉ vào lệnh khi **ADX trong khoảng 20–50** (hoặc 20–55).  
- Tránh vào lệnh khi ADX > 55–60 trừ khi có bộ lọc bổ sung (pullback, confirmation).

---

### 2.3. ATR (Average True Range – độ biến động)

- **Win:** ATR trung bình **3.84** (2.42 – 5.80).  
- **Loss:** ATR trung bình **3.25** (2.80 – 3.52).  
- **Kết luận:** Lệnh thắng có ATR lúc vào lệnh **cao hơn** một chút (+0.58). Biến động đủ lớn giúp giá “chạy” tới TP; ATR quá thấp dễ sideway, dễ chạm SL.

**Gợi ý:**  
- Giữ/áp dụng **ATR filter**: chỉ vào lệnh khi ATR (M1 hoặc M5) **trên một mức tối thiểu** (ví dụ ATR > 2.0–2.5 với XAUUSD M1).  
- Có thể thêm **ATR max** để tránh vào lệnh khi tin tức (volatility cực cao).

---

### 2.4. Session (khung giờ vào lệnh)

- **Asian (00:00–08:00 server):** Win = 6, Loss = 4 → **Win rate 60%**.  
- **London_Open (08:00–13:00):** Win = 2, Loss = 6 → **Win rate 25%**.

**Kết luận:** Trong mẫu này, **Asian** cho win rate cao hơn rõ; **London_Open** nhiều loss hơn (có thể do biến động tăng, false breakout).

**Gợi ý:**  
- Cấu hình **allowed_sessions** (ví dụ 08:00–22:00) đang tránh Asian; nếu muốn tối ưu theo dữ liệu này có thể **mở rộng sang Asian** (ví dụ 00:00–22:00) và **thử giảm hoặc tránh London mở cửa** (08:00–10:00) nếu backtest tiếp tục cho thấy kém.  
- Nên backtest thêm theo session trước khi đổi config thật.

---

### 2.5. Entry (BUY vs SELL)

- **BUY:** Win = 8, Loss = 9 → Win rate **47.1%**.  
- **SELL:** Win = 0, Loss = 1 → chỉ 1 lệnh (Loss).

**Kết luận:** Phần lớn lệnh là BUY; SELL chưa đủ dữ liệu. Trong giai đoạn backtest, thị trường có thể thiên **uptrend** nên BUY xuất hiện nhiều và có win rate chấp nhận được.

**Gợi ý:**  
- Tiếp tục ghi nhận thêm SELL; khi đủ dữ liệu sẽ so sánh RSI/ADX/ATR/Session cho SELL.  
- Có thể kiểm tra lại điều kiện SELL (RSI < 42, trend BEARISH, v.v.) để đảm bảo tín hiệu không quá hiếm hoặc quá dễ false.

---

### 2.6. Strategy (Trend HA vs Trend HA V2)

- **Strategy_1_Trend_HA:** Win = 5, Loss = 7 → Win rate **41.7%**.  
- **Strategy_1_Trend_HA_V2:** Win = 3, Loss = 3 → Win rate **50.0%**.

**Kết luận:** V2 (có thêm ADX, ATR, filter chop, confirmation) cho **win rate cao hơn** với cùng số lệnh đóng (6). Mẫu nhỏ nhưng nhất quán với việc **thêm bộ lọc** giúp bỏ bớt lệnh xấu.

**Gợi ý:**  
- Ưu tiên phát triển và tối ưu **V2**.  
- Có thể bật thêm **H1 trend confirmation** trên V2 nếu muốn giảm lệnh ngược trend lớn.

---

## 3. Các yếu tố khác đáng theo dõi (trong code/strategy)

Những yếu tố sau **đã có trong logic** bot, nên được ghi log và phân tích khi đủ dữ liệu:

- **Trend alignment (M5 vs H1):** Đồng nhất M5–H1 thường an toàn hơn.  
- **Heiken Ashi:** Nến xanh/đỏ, breakout SMA55 High/Low, **fresh breakout** (nến trước chưa breakout).  
- **Doji / solid candle:** Tránh vào khi nến HA là doji (body nhỏ).  
- **Trailing & breakeven:** Cấu hình trailing (ATR, pips) và breakeven ảnh hưởng lớn đến P&amp;L; nên so sánh Win/Loss theo từng nhóm cấu hình.  
- **Risk/Reward (RR):** Export có cột Risk/Reward Ratio (1.5); có thể so sánh Win/Loss theo RR và theo SL mode (auto_m5 vs fixed).

---

## 4. Tóm tắt khuyến nghị

| Yếu tố | Phát hiện | Khuyến nghị |
|--------|-----------|-------------|
| **RSI** | Win có RSI cao hơn (~58 vs ~56) | Giữ RSI BUY > 55–58; có thể thử > 57. |
| **ADX** | Win có ADX thấp hơn (~47 vs ~57) | Thêm cap ADX (ví dụ 20–50 hoặc 20–55), tránh ADX > 55–60. |
| **ATR** | Win có ATR cao hơn một chút | Giữ ATR min filter; cân nhắc ATR max. |
| **Session** | Asian 60% WR, London_Open 25% | Cân nhắc mở Asian, thận trọng London mở cửa. |
| **Entry** | Chủ yếu BUY, SELL ít | Thu thêm dữ liệu SELL; kiểm tra điều kiện SELL. |
| **Strategy** | V2 win rate 50% > bản gốc 41.7% | Ưu tiên V2; thêm filter (H1, ADX cap) trên V2. |

Chạy lại script phân tích sau mỗi lần export CSV mới:

```bash
cd XAU_M1/result
python analyze_win_factors.py
```

Báo cáo số liệu chi tiết được ghi trong `win_factors_analysis.txt`.
