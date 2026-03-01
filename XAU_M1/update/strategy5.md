from pathlib import Path

md = """# Strategy_5_Filter_First — Danh sách vấn đề cần sửa (net profit ↑, drawdown ↓)

Tài liệu này liệt kê **các vấn đề/điểm yếu** đã thấy từ code (`strategy_5_filter_first.py`, `utils.py`) và kết quả lệnh (orders export), kèm **hướng sửa cụ thể** để bạn dễ copy/áp dụng.

> Không ghi lại bất kỳ **password/token** nào trong cấu hình. Nếu file config của bạn đang để plain text, nên chuyển sang biến môi trường.

---

## 1) SELL đang kéo hiệu suất xuống (ưu tiên sửa #1)
**Triệu chứng**
- Trong giai đoạn log đã xuất, BUY lời còn SELL âm → net profit bị kéo xuống và DD tăng.

**Sửa**
- Thêm cấu hình `trade_direction` và mặc định chạy **BUY_ONLY**.
- Hoặc giữ SELL nhưng **siết điều kiện SELL** (ADX/RSI/volume/EMA slope) để giảm lệnh xấu.

**Gợi ý config**
- `trade_direction: BUY_ONLY`

---

## 2) Trailing/Breakeven bị “cắt lời sớm” do ước lượng sai initial risk (ưu tiên sửa #2)
**Triệu chứng**
- Rất ít lệnh chạm TP (phần lớn đóng kiểu “OTHER”), win thường nhỏ, trong khi loss vẫn đủ lớn.
- Trong `utils.py -> manage_position()`, code đang ước lượng “initial SL distance” dựa vào `pos.sl` hiện tại.
  - Khi SL đã được kéo về BE, `pos.sl` không còn phản ánh **rủi ro ban đầu**, dẫn tới trigger trailing/BE sai.

**Sửa**
- Ước lượng rủi ro ban đầu dựa trên **TP** (vì TP được set theo RR cố định), ví dụ:
  - `initial_risk_price = abs(tp - entry) / reward_ratio`
- Dùng giá trị này để tính `initial_sl_distance_pips` ổn định dù SL đã bị dời.

**Nơi sửa**
- `utils.py` → hàm `manage_position()` → đoạn “Calculate Initial SL Distance …”

---

## 3) Thiếu “risk cap” (max SL distance) → DD bị kéo bởi lệnh SL quá rộng (ưu tiên sửa #3)
**Triệu chứng**
- Có lệnh SL khoảng cách rất lớn (risk lớn) gây “đuôi drawdown”.

**Sửa**
- Sau khi tính SL/TP, thêm filter:
  - nếu `abs(entry - sl) > max_risk_price` (XAUUSD dùng đơn vị $) → **skip trade**
- Đây là cách **giảm DD mạnh** mà vẫn giữ chiến lược breakout.

**Gợi ý config**
- `max_risk_price: 9.0` (XAUUSD; bạn có thể tune 6–12 tùy khẩu vị)

**Nơi sửa**
- `strategy_5_filter_first.py` → ngay sau khi set xong `sl`/`tp`.

---

## 4) ATR filter hard-code & scale có nguy cơ lệch (ưu tiên sửa #4)
**Triệu chứng**
- `atr_min`, `atr_max` đang hard-code (ví dụ 10–200).
- Có rủi ro lệch scale “pip/point” (đặc biệt với XAUUSD) nếu quy đổi ATR và pip_size không nhất quán giữa entry và manage.

**Sửa**
- Đưa `atr_min_pips`, `atr_max_pips` vào config.
- Rà lại 1 chuẩn thống nhất:
  - `pip_size` cho XAUUSD thường là `0.01` (tùy broker/symbol digits)
  - mọi quy đổi pips/points dùng **cùng một công thức** ở cả strategy và utils.

**Gợi ý config**
- `atr_max_pips: 175` (đã giúp lọc bớt đoạn volatility dễ slippage trong sample)

**Nơi sửa**
- `strategy_5_filter_first.py` → chỗ set `atr_min`, `atr_max`
- `utils.py` → chỗ tính `pip_size` / trailing distance.

---

## 5) Cooldown 5 phút đang gọi lịch sử bằng `time.time()` (bug dữ liệu đầu vào)
**Triệu chứng**
- `mt5.history_deals_get()` thường cần `datetime` range. Dùng `time.time()` có thể trả về kết quả sai/không ổn định theo broker/MT5 build.

**Sửa**
- Đổi sang `datetime.now() - timedelta(minutes=5)`.

**Nơi sửa**
- `strategy_5_filter_first.py` → đoạn cooldown check.

---

## 6) Chưa có spread filter → dễ bị fill xấu / SLippage (giảm net, tăng DD)
**Triệu chứng**
- Breakout ở M1 rất nhạy với spread giãn. Không lọc spread sẽ làm entry xấu và SL dễ bị quét.

**Sửa**
- Trước khi đặt lệnh: tính `spread_points = (ask - bid) / point`
- Nếu `spread_points > max_spread_points` → skip.

**Gợi ý config**
- `max_spread_points: 80` (tune tùy symbol/broker)

**Nơi sửa**
- `strategy_5_filter_first.py` → ngay trước khi lấy `price` vào lệnh.

---

## 7) Thiếu “daily loss limit / kill switch” để chặn chuỗi thua (giảm DD)
**Triệu chứng**
- Bot có loss-streak cooldown, nhưng không có ngưỡng “dừng trong ngày” khi thị trường xấu.

**Sửa**
- Tính PnL trong ngày theo `history_deals_get(day_start, now)`.
- Nếu `pnl_today <= daily_loss_limit` → stop trade hết ngày.

**Gợi ý config**
- `daily_loss_limit: -20.0` (ví dụ; tune theo lot/size)

---

## 8) Loss-streak guard chỉ nhìn ~1 ngày gần nhất (logic chưa “bền”)
**Triệu chứng**
- Nếu chuỗi thua cách ngày, guard có thể không nhận ra (vì lookback ngắn).

**Sửa**
- Tăng lookback (ví dụ 7–30 ngày) **hoặc**
- Lưu streak vào file/DB state (bền vững qua restart).

**Nơi sửa**
- `strategy_5_filter_first.py` → đoạn `history_deals_get(datetime.now() - timedelta(days=1), ...)`

---

## 9) Tối ưu entry để tăng chất lượng (tăng net & giảm DD, nhưng sẽ giảm số lệnh)
**Triệu chứng**
- Donchian breakout dễ dính false break (đặc biệt khi chỉ dựa high/low).

**Sửa khuyến nghị**
- Bắt buộc **close breakout**:
  - BUY: `close > donchian_high + buffer`
  - SELL: `close < donchian_low - buffer`
- Thêm điều kiện “body đủ lớn” (tránh râu dài):
  - `body >= 0.6 * ATR(M1)`

**Nơi sửa**
- `strategy_5_filter_first.py` → phần tạo signal BUY/SELL.

---

## 10) Checklist thay đổi tối thiểu để đạt mục tiêu (khuyến nghị thứ tự)
1. **BUY_ONLY** (tắt SELL)
2. **Fix initial risk trong manage_position** (trailing/BE đúng theo R)
3. **Add risk cap** (max_risk_price)
4. **ATR max từ config + thống nhất pip/point**
5. **Cooldown dùng datetime**
6. **Spread filter**
7. **Daily loss limit**
8. (tuỳ chọn) Close-breakout + body/ATR filter

---

## 11) Gợi ý tên cấu hình mới (để bạn copy vào config sau này)
- `trade_direction`: `"BUY_ONLY" | "SELL_ONLY" | "BOTH"`
- `atr_min_pips`, `atr_max_pips`
- `max_spread_points`
- `max_risk_price`
- `daily_loss_limit`
- `loss_streak_lookback_days`

---

## 12) Ghi chú bảo mật (rất nên làm)
- Không để `password`, `telegram token` dạng plain text trong repo/chat.
- Dùng biến môi trường / `.env` và thêm vào `.gitignore`.

"""
Path("/mnt/data/fixes_strategy_5.md").write_text(md, encoding="utf-8")
"/mnt/data/fixes_strategy_5.md"