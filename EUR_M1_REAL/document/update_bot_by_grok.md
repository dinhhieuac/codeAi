# Nâng Cấp Chi Tiết Cho Từng Bot Giao Dịch EURUSD M1

Dựa trên phân tích từ tài liệu review và kết quả thực tế, dưới đây là các nâng cấp cụ thể để giảm tỉ lệ thua và tăng tỉ lệ thắng. Các nâng cấp tập trung vào filter chặt chẽ hơn, confirmation bổ sung và risk management động.

## Strategy 1: Trend HA (V1)
- Win rate hiện tại: 40.48%.
1. **Sửa EMA200 calculation từ SMA sang EMA thực sự**: Fix bug trong review, đảm bảo trend filter chính xác.
2. **Nâng ADX threshold từ 20 lên 25 (M5/H1)**: Lọc trend mạnh hơn, tránh entry sideway.
3. **Thêm volume confirmation (≥1.3x MA20)**: Đảm bảo breakout có hỗ trợ volume.
4. **Thêm CHOP filter (CHOP <50 cho trade)**: Tránh range market như đề xuất review.
5. **Tăng spam filter từ 60s lên 300s**: Giảm overtrade.
6. **Thêm trailing stop ATR-based (1.5x)**: Bảo vệ lợi nhuận trong trend.

## Strategy 1: Trend HA V2
- Win rate hiện tại: 48.0%.
1. **Nâng RSI threshold (BUY >60, SELL <40)**: Tránh momentum yếu.
2. **Bật tất cả optional filters mặc định (volume, liquidity sweep, displacement)**: Tăng confirmation.
3. **Nâng ADX threshold từ 22 lên 28**: Lọc trend mạnh hơn.
4. **Thêm max daily loss guard (dừng sau lỗ 2% account)**: Bảo vệ vốn.
5. **Dynamic ATR buffer cho SL (1.5x nếu ATR thấp, 2.5x nếu cao)**: Linh hoạt hơn.
6. **Thêm news filter (tránh trade 30 phút trước/sau high-impact news)**: Giảm thua đột ngột.

## Strategy 1: Trend HA V2.1
- Win rate: Không dữ liệu (giả định >50%).
1. **Nâng hard gate ADX từ 20 lên 25**: Đảm bảo strong trend.
2. **Thêm volume threshold cho confirm candle (≥1.2x MA)**: Tăng validity breakout.
3. **Giảm SL limit từ 1.2x ATR xuống 1.0x**: Strict hơn, tránh SL xa.
4. **Thêm RSI divergence check trong soft confirm**: Phát hiện reversal thật.
5. **Tăng cooldown sau loss từ 45 phút lên 60 phút**: Giảm overtrade.
6. **Thêm position sizing (volume theo risk 1% account)**: Linh hoạt vốn.

## Strategy 2: EMA ATR
- Win rate: Không dữ liệu (giả định trung bình).
1. **Nâng H1 ADX threshold từ 20 lên 25**: Lọc trend mạnh.
2. **Thêm Stochastic confirmation (M1: %K(14) >80 BUY/<20 SELL)**: Xác nhận overbought/oversold.
3. **Dynamic extension check (1.0x ATR nếu volatile cao)**: Tránh entry xa EMA.
4. **Tăng volume threshold từ 1.3x lên 1.5x**: Đảm bảo spike mạnh.
5. **Thêm session filter (08:00-22:00)**: Tránh Asian như review.
6. **Chuyển TP sang R:R 2.0 với partial close**: Tăng profit khi thắng.

## Strategy 3: PA Volume
- Win rate: Không dữ liệu (giả định thấp).
1. **Nâng volume threshold từ 1.3x lên 1.6x**: Giảm pinbar yếu.
2. **Strict pinbar detection (nose <1.5x body thay 2x)**: Giảm relaxed detection.
3. **Nâng RSI threshold (>55 BUY, <45 SELL)**: Tăng momentum filter.
4. **Thêm Bollinger Bands confirm (pinbar chạm band ngoài)**: Tăng rejection quality.
5. **Giới hạn ATR range hẹp hơn (5-20 pips)**: Tránh extreme.
6. **Thêm consecutive loss guard (pause sau 2 thua)**: Giảm chuỗi thua.

## Strategy 4: UT Bot
- Win rate: Không dữ liệu (giả định trung bình).
1. **Nâng M1 ADX từ 20 lên 30**: Tránh sideway flip.
2. **Thêm CCI(20) filter (>100 BUY, <-100 SELL)**: Confirm momentum.
3. **Chuyển SL/TP sang ATR-based (2x SL, 3x TP)**: Dynamic thay fixed.
4. **Tăng volume threshold từ 1.3x lên 1.5x**: Đảm bảo flip hỗ trợ.
5. **Thêm session filter (tránh Asian)**: Giảm volatile thấp.
6. **Thêm UT repaint check (wait 2 nến sau flip)**: Giảm signal thay đổi.

## Strategy 5: Filter First
- Win rate hiện tại: 0.0%.
1. **Giảm donchian_period từ 50 xuống 30**: Channel hẹp, bắt breakout thật hơn.
2. **Nâng M1 ADX từ 20 lên 30**: Lọc mạnh, tránh false.
3. **Tăng buffer_multiplier từ 100 lên 150 points**: Tránh breakout nhỏ.
4. **Hẹp ATR range (20-100 pips thay 10-200)**: Tránh rộng.
5. **Thêm VWAP confirmation (breakout vượt VWAP)**: Tăng validity.
6. **Thêm false history check (bỏ nếu 2 false gần)**: Giảm repeat error.
