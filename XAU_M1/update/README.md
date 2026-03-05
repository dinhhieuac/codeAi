# XAU_M1 — Theo dõi cập nhật bot

Thư mục này chứa tài liệu ghi lại **toàn bộ thay đổi** của từng bot để theo dõi lịch sử và cấu hình.

---

## Danh sách file cập nhật theo bot

| Bot | File MD | Mô tả |
|-----|---------|--------|
| **Strategy 1 Trend HA** (gốc) | [strategy_ha.md](strategy_ha.md) | Chiến thuật Trend HA bản gốc; spam filter 180s, cấu hình được |
| **Strategy 1 Trend HA V1.1** | [stratry_ha_v11.md](stratry_ha_v11.md) | Clone + khung giờ 02:00–06:00 & 13:00–20:00, RSI range; spam filter 180s, cấu hình được |
| **Strategy 5 Filter First** | [strategy5.md](strategy5.md) | Danh sách vấn đề / hướng sửa |
| **Strategy 5 Bot** | [strarey5botupdate.md](strarey5botupdate.md) | Cập nhật bot strategy 5 |

---

## Cập nhật gần đây (tóm tắt)

- **05/03/2026:** Spam filter cho **strategy_1_trend_ha** và **strategy_1_trend_ha_v11**: 60s → **180s**, thêm tham số **`spam_filter_seconds`** trong config (cấu hình được). Chi tiết trong từng file MD tương ứng.
