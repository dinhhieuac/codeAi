# Cập nhật Strategy 1 Trend HA – Version 1.1

**Ngày:** 23/02/2026  
**Bot:** Strategy 1 Trend HA V1.1  
**File bot:** `XAU_M1/strategy_1_trend_ha_v11.py`  
**Config:** `XAU_M1/configs/config_1_v11.json`  
**Nguồn clone:** `XAU_M1/strategy_1_trend_ha.py`

---

## Tóm tắt

Clone từ `strategy_1_trend_ha.py` sang phiên bản **1.1** với hai thay đổi chính: **chỉ trade trong khung giờ (giờ server)** và **RSI theo khoảng (range)** cho BUY/SELL.

---

## Nội dung update

### 1. Chỉ cho phép trade theo khung giờ (giờ server)

- **Sáng:** 02:00 – 06:00 (giờ server).  
- **Chiều/Tối:** 13:00 – 20:00 (giờ server).  
- Ngoài hai khung trên → không vào lệnh mới (chỉ bỏ qua, không đóng lệnh cũ).  
- Thời gian lấy từ MT5 server: `symbol_info_tick(symbol).time`.  
- Hàm kiểm tra: `check_trading_session(config)`; gọi đầu `strategy_1_logic()` trước khi lấy dữ liệu/indicator.

### 2. RSI theo khoảng (range)

- **BUY:** chỉ khi **52 < RSI < 68** (strict: không lấy RSI = 52 hoặc 68).  
- **SELL:** chỉ khi **32 < RSI < 48** (strict: không lấy RSI = 32 hoặc 48).  
- Config: `rsi_buy_min`, `rsi_buy_max`, `rsi_sell_min`, `rsi_sell_max` (mặc định 52, 68, 32, 48).  
- Thay thế logic cũ: BUY theo “RSI > threshold”, SELL theo “RSI < threshold” → dùng khoảng như trên.

---

## File liên quan

| File | Mô tả |
|------|--------|
| `XAU_M1/strategy_1_trend_ha_v11.py` | Bot V1.1: session filter + RSI range, strategy name `Strategy_1_Trend_HA_V11`, comment `Strat1_HA_V11` |
| `XAU_M1/configs/config_1_v11.json` | Config riêng cho V1.1 (magic 100011), có `rsi_buy_min/max`, `rsi_sell_min/max` |

---

## Cách chạy

```bash
cd XAU_M1
python strategy_1_trend_ha_v11.py
```

Config được load từ: `configs/config_1_v11.json`.

---

## Khác biệt so với bản gốc (strategy_1_trend_ha.py)

| Hạng mục | Bản gốc | V1.1 |
|----------|--------|------|
| Khung giờ | Không lọc | Chỉ trade 02:00–06:00 và 13:00–20:00 (server) |
| BUY RSI | RSI > 55 (rsi_buy_threshold) | 52 < RSI < 68 |
| SELL RSI | RSI < 45 (rsi_sell_threshold) | 32 < RSI < 48 |
| Strategy name / DB | Strategy_1_Trend_HA | Strategy_1_Trend_HA_V11 |
| Comment lệnh | Strat1_Trend_HA | Strat1_HA_V11 |
| Magic (mặc định config) | 100001 | 100011 |

Logic trend (M5/H1), ADX, Heiken Ashi, SMA55, SL/TP, trailing/breakeven giữ nguyên như bản gốc.

---

## Lịch sử cập nhật thêm

### 05/03/2026 — Spam filter: 60s → 180s, cấu hình được

| Mục | Trước | Sau |
|-----|--------|-----|
| Thời gian chờ giữa 2 lệnh | Cố định 60 giây | **180 giây** (mặc định), **cấu hình được** qua config |
| Tham số config | Không có | `parameters.spam_filter_seconds` (mặc định: 180) |

**Chi tiết:**

- Spam filter đọc từ `config['parameters'].get('spam_filter_seconds', 180)`.
- Chuẩn hóa so sánh thời gian: xử lý cả `datetime` và timestamp từ MT5 để tránh lỗi kiểu dữ liệu.
- Trong config đã thêm: `"spam_filter_seconds": 180` trong `parameters`.

**File sửa:**

- `XAU_M1/strategy_1_trend_ha_v11.py` (đoạn Execute Trade, spam filter).
- `XAU_M1/configs/config_1_v11.json` (thêm `spam_filter_seconds`).
