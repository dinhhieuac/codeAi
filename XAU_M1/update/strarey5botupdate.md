# Strategy 5 Filter First — Nội dung update (V2)

Tài liệu tóm tắt các thay đổi đã áp dụng khi clone sang **Strategy 5 Filter First V2** theo `strategy5.md`.

---

## Nguồn clone (đã sửa)

- **Nguồn:** **XAU_M1/strategy_5_filter_first.py** (không phải XAU_M1_V2).
- **Đích:** **XAU_M1_V2/strategy_5_filter_first_v2.py** — Clone từ XAU_M1, tích hợp toàn bộ cập nhật bên dưới. Strategy name trong DB: `Strategy_5_Filter_First_V2`, comment order: `Strat5_FilterFirst_V2`.
- Logic gốc giữ từ XAU_M1: M5/ADX threshold 20, RSI BUY > rsi_buy_threshold (55), RSI SELL < rsi_sell_threshold (45).

---

## 1. trade_direction (BUY_ONLY / SELL_ONLY / BOTH)

- **Mục đích:** Giảm lệnh SELL kém hiệu quả; mặc định chỉ giao dịch BUY.
- **Cách làm:** Thêm tham số config `trade_direction` (mặc định `BUY_ONLY`). Khi tạo signal:
  - Nếu `trade_direction == "SELL_ONLY"` thì không xét breakout BUY.
  - Nếu `trade_direction == "BUY_ONLY"` thì không xét breakout SELL.
- **Config gợi ý:** `"trade_direction": "BUY_ONLY"`

---

## 2. Trailing/Breakeven — Initial risk (chưa sửa trong file strategy)

- **Vấn đề:** Trong `utils.py`, hàm `manage_position()` ước lượng “initial SL distance” từ `pos.sl` hiện tại; khi SL đã kéo về BE thì sai.
- **Hướng sửa (thực hiện trong utils.py):** Ước lượng rủi ro ban đầu từ TP và reward_ratio, ví dụ:  
  `initial_risk_price = abs(tp - entry) / reward_ratio`, rồi dùng giá trị này cho trailing/BE thay vì dựa vào `pos.sl`.
- **Ghi chú:** Phần này cần sửa trong **XAU_M1_V2/utils.py** (hàm `manage_position()`), chưa nằm trong file strategy_5_filter_first_v2.py.

---

## 3. max_risk_price (risk cap)

- **Mục đích:** Giới hạn khoảng cách SL (risk) tối đa để tránh DD lớn do vài lệnh SL quá rộng.
- **Cách làm:** Sau khi tính xong `sl` và `tp`, tính `risk_dist = abs(price - sl)`. Nếu `risk_dist > max_risk_price` thì **không vào lệnh** (skip trade).
- **Config gợi ý:** `"max_risk_price": 9.0` (XAUUSD, đơn vị $; có thể tune 6–12).

---

## 4. ATR filter từ config (atr_min_pips, atr_max_pips)

- **Mục đích:** Bỏ hard-code, dễ tune và thống nhất scale pip/point.
- **Cách làm:** Đọc `atr_min_pips` và `atr_max_pips` từ config; mặc định dùng `atr_min_pips: 10`, `atr_max_pips: 175`.
- **Config gợi ý:** `"atr_min_pips": 10`, `"atr_max_pips": 175`

---

## 5. Cooldown dùng datetime

- **Vấn đề:** Cooldown 5 phút dùng `time.time()` cho `history_deals_get()` có thể không ổn định theo broker/MT5.
- **Cách làm:** Đổi sang dùng `datetime`:  
  `from_dt = datetime.now() - timedelta(minutes=5)`, rồi dùng `int(from_dt.timestamp())` và `int(datetime.now().timestamp())` để gọi `mt5.history_deals_get(from_ts, to_ts)`.

---

## 6. Spread filter

- **Mục đích:** Tránh entry khi spread giãn (fill xấu, dễ slippage).
- **Cách làm:** Trước khi lấy giá vào lệnh:  
  `spread_points = (ask - bid) / point`.  
  Nếu `spread_points > max_spread_points` thì **skip** (không gửi lệnh).
- **Config gợi ý:** `"max_spread_points": 80` (tune theo symbol/broker).

---

## 7. Daily loss limit (kill switch)

- **Mục đích:** Dừng giao dịch trong ngày khi lỗ vượt ngưỡng.
- **Cách làm:** Trước khi gửi lệnh: lấy deals từ đầu ngày đến hiện tại (theo magic), tính `pnl_today`. Nếu `pnl_today <= daily_loss_limit` thì **stop trade** (return, không gửi lệnh).
- **Config gợi ý:** `"daily_loss_limit": -20.0` (tune theo lot/size).

---

## 8. loss_streak_lookback_days

- **Mục đích:** Consecutive loss guard nhìn xa hơn 1 ngày để nhận ra chuỗi thua.
- **Cách làm:** Thêm config `loss_streak_lookback_days` (mặc định `7`). Khi kiểm tra loss streak, dùng `datetime.now() - timedelta(days=loss_streak_lookback_days)` làm điểm bắt đầu lấy history deals.
- **Config gợi ý:** `"loss_streak_lookback_days": 7`

---

## 9. Entry chất lượng: body nến >= 0.6*ATR

- **Mục đích:** Chỉ vào lệnh khi nến breakout có body đủ lớn (tránh false break do râu dài).
- **Cách làm:** Sau khi xác nhận breakout (close breakout vẫn giữ như cũ), thêm điều kiện:  
  `body_size = abs(close - open)`, nếu `body_size >= body_min_atr_ratio * ATR(M1)` mới cho signal (BUY/SELL).
- **Config:** `"body_min_atr_ratio": 0.6` (có thể tắt bằng giá trị 0 nếu muốn bỏ filter).

---

## 10. Config mới (gợi ý thêm vào config_5_v2.json)

```json
{
  "parameters": {
    "trade_direction": "BUY_ONLY",
    "atr_min_pips": 10,
    "atr_max_pips": 175,
    "max_spread_points": 80,
    "max_risk_price": 9.0,
    "daily_loss_limit": -20.0,
    "loss_streak_lookback_days": 7,
    "body_min_atr_ratio": 0.6
  }
}
```

---

## 11. Chạy V2

- Copy/sửa config từ `config_5.json` sang `config_5_v2.json` (trong `XAU_M1_V2/configs/`), thêm các key trên.
- Chạy: `python strategy_5_filter_first_v2.py` (từ thư mục XAU_M1_V2).  
- Nếu không có `config_5_v2.json`, script sẽ fallback sang `config_5.json`.

---

## 12. Chưa làm trong repo (ghi chú)

- **utils.py — Initial risk trong manage_position:** Cần sửa riêng trong `XAU_M1_V2/utils.py` (ước lượng initial risk từ TP/reward_ratio) để trailing/BE đúng theo R. Chi tiết xem mục 2 và `strategy5.md`.
