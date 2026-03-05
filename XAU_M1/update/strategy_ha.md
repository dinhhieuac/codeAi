# Cập nhật Strategy 1 Trend HA (bản gốc)

**Bot:** Strategy 1 Trend HA  
**File bot:** `XAU_M1/strategy_1_trend_ha.py`  
**Config:** `XAU_M1/configs/config_1.json`

---

## Tóm tắt chiến thuật

- **Trend:** M5 EMA200 (SMA 200), H1 EMA100, bắt buộc đồng nhất.
- **ADX:** ≥ 20.
- **Kênh:** M1 SMA55 High/Low.
- **Heiken Ashi:** nến xanh/đỏ, trên/dưới kênh, fresh breakout, không doji.
- **RSI:** BUY khi RSI > 55, SELL khi RSI < 45.
- **Khung giờ:** Không lọc (24/7).
- **SL/TP:** auto_m5 (M5 High/Low + buffer) hoặc fixed pips.

---

## Lịch sử thay đổi

### 05/03/2026 — Spam filter: 60s → 180s, cấu hình được

| Mục | Trước | Sau |
|-----|--------|-----|
| Thời gian chờ giữa 2 lệnh | Cố định 60 giây | **180 giây** (mặc định), **cấu hình được** qua config |
| Tham số config | Không có | `parameters.spam_filter_seconds` (mặc định: 180) |

**Chi tiết:**

- Spam filter đọc từ `config['parameters'].get('spam_filter_seconds', 180)`.
- Chuẩn hóa so sánh thời gian: xử lý cả `datetime` và timestamp từ MT5 (`last_ts`, `current_ts`) để tránh lỗi khi MT5 trả về kiểu khác nhau.
- Trong config đã thêm: `"spam_filter_seconds": 180` trong `parameters`.

**File sửa:**

- `XAU_M1/strategy_1_trend_ha.py` (đoạn Execute Trade, spam filter).
- `XAU_M1/configs/config_1.json` (thêm `spam_filter_seconds`).

---

## File liên quan

| File | Mô tả |
|------|--------|
| `XAU_M1/strategy_1_trend_ha.py` | Bot bản gốc Trend HA |
| `XAU_M1/configs/config_1.json` | Config (magic 100001), có `spam_filter_seconds` |

---

## Cách chạy

```bash
cd XAU_M1
python strategy_1_trend_ha.py
```

Config: `configs/config_1.json`.
