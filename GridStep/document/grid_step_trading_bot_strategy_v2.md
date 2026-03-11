# Grid Step Trading Bot V2 — Chiến thuật & Đặc tả

## 1. Tổng quan

**V2** là bản nâng cấp của Grid Step Bot, thêm **khóa re-entry theo mức + chiều sau SL** để giảm whipsaw sideways (theo tài liệu `fix_whipsaw.md`). Phần còn lại giữ nguyên so với bản gốc.

- **Không dùng indicator** (EMA, ADX, RSI, Heiken Ashi...).
- Luôn tính **một cặp** BUY STOP / SELL STOP quanh ref; **có thể chỉ đặt 1 hoặc 0 lệnh** nếu mức/chiều đó đang bị khóa re-entry.
- Khi **một lệnh khớp** → hủy lệnh chờ còn lại, dịch grid, đặt cặp mới (với kiểm tra re-entry lock).
- Mỗi lệnh có **SL/TP cố định** (không trailing, không breakeven).

**Script V2:**

| Script | Config | File re-entry lock | File cooldown / pause |
|--------|--------|--------------------|------------------------|
| **strategy_grid_step_v2.py** | configs/config_grid_step.json | grid_reentry_locks_v2.json | Dùng chung grid_cooldown.json, grid_pause.json |

Chạy: `python strategy_grid_step_v2.py` (cùng DB và config với bản gốc nếu muốn).

---

## 2. Khác biệt V2: Re-entry lock (chống whipsaw)

### 2.1. Mục tiêu

Ngăn bot **mở lại ngay cùng chiều và cùng mức entry** vừa bị SL, tránh vòng lặp: BUY 5005 → SL → BUY 5005 → SL.

### 2.2. Cách hoạt động

- Khi phát hiện lệnh **đóng tại SL** (profit < 0 và close_price ≈ SL), bot tạo **khóa re-entry** cho đúng **chiều** (BUY/SELL) và **mức entry** (giá mở), theo từng strategy_name + symbol + step.
- **BUY @ E** bị SL (SL = E − step) → khóa **BUY:E**. Chỉ cho phép đặt lại BUY tại E khi **bid ≤ E − 2×step** (giá đã xuống thêm 1 step dưới SL).
- **SELL @ E** bị SL (SL = E + step) → khóa **SELL:E**. Chỉ cho phép đặt lại SELL tại E khi **ask ≥ E + 2×step** (giá đã lên thêm 1 step trên SL).

### 2.3. Quy tắc mở khóa

| Chiều | Entry E | SL | Unlock rule | Unlock price |
|-------|---------|-----|-------------|--------------|
| BUY   | E       | E − step | bid ≤ unlock_price | E − 2×step |
| SELL  | E       | E + step | ask ≥ unlock_price | E + 2×step |

Ví dụ step = 5:

- BUY 5005 SL tại 5000 → khóa BUY:5005; mở khóa khi **bid ≤ 4995**.
- SELL 4995 SL tại 5000 → khóa SELL:4995; mở khóa khi **ask ≥ 5005**.

### 2.4. Ảnh hưởng lên đặt lệnh

- Trước khi đặt **BUY STOP** tại `buy_price`: nếu **BUY:buy_price** đang khóa và chưa thỏa điều kiện mở khóa → **không đặt** BUY (có thể vẫn đặt SELL).
- Trước khi đặt **SELL STOP** tại `sell_price**: nếu **SELL:sell_price** đang khóa và chưa thỏa điều kiện mở khóa → **không đặt** SELL (có thể vẫn đặt BUY).
- Có thể xảy ra: đặt **cả hai**, chỉ **một**, hoặc **không đặt** (cả hai đều khóa) tùy trạng thái lock và bid/ask.

### 2.5. Dữ liệu lưu (grid_reentry_locks_v2.json)

Mỗi lock gồm:

- `strategy_name`, `symbol`, `step`, `side` (BUY/SELL), `entry_price`
- `unlock_rule`: `"bid_lte"` hoặc `"ask_gte"`
- `unlock_price`, `active`, `created_at`, `reason` (vd "SL")

Khi bid/ask thỏa điều kiện mở khóa, bot tự **deactivate** lock (active = false) và cho phép đặt lại mức đó.

---

## 3. Cấu hình Step (bước giá)

Giống bản gốc. Tham số dùng chung:

| Tham số | Mô tả | Mặc định |
|--------|--------|----------|
| **step** | Bước grid và SL/TP (1 kênh legacy) | 5 |
| **steps** | Nhiều step cùng lúc, VD `[5]` hoặc `[2,3,4,5,6,7]` | — |
| **min_distance_points** | Khoảng cách tối thiểu (point) tới position hiện có | 5 |
| **target_profit** | Basket TP (đóng hết khi tổng lợi nổi ≥ giá trị này) | 50.0 |
| **spread_max** | Không đặt lệnh khi spread (giá) > giá trị này | 0.5 |
| **cooldown_minutes** | Không đặt lại cùng mức trong X phút; 0 = tắt | 0 |
| **consecutive_loss_pause_enabled** | Bật/tắt tạm dừng khi N lệnh thua liên tiếp | true |
| **consecutive_loss_count** | Số lệnh thua liên tiếp để kích hoạt | 2 |
| **consecutive_loss_pause_minutes** | Số phút tạm dừng (từ giờ đóng lệnh thua cuối) | 5 |

V2 dùng chung config với bản gốc (vd `config_grid_step.json`), không thêm tham số mới.

---

## 4. Cách tính giá đặt lệnh (anchor, ref, buy_price, sell_price)

Giống bản gốc:

- **Anchor**: Có position → giá mở position mới nhất; không position → mid = (bid + ask) / 2.
- **ref** = round(anchor / grid_step_price) × grid_step_price.
- **BUY STOP** = ref + grid_step_price, **SELL STOP** = ref − grid_step_price.

Sau khi có `buy_price` và `sell_price`, V2 thêm bước kiểm tra re-entry lock và có thể bỏ qua đặt BUY và/hoặc SELL.

---

## 5. Luồng hoạt động V2 (Core Logic) — mỗi step

Thứ tự trong `strategy_grid_step_logic()` của V2:

1. **Đồng bộ DB lệnh chờ** (sync_grid_pending_status): Cập nhật PENDING → FILLED/CANCELLED; khi FILLED ghi position vào `orders` với SL/TP đúng.
2. **Phát hiện SL và thêm re-entry lock** (check_sl_closes_and_add_locks): Duyệt orders đã đóng (profit IS NOT NULL) của strategy; nếu profit < 0 và close_price ≈ sl thì thêm lock (side, entry_price) theo quy tắc §2.
3. **Đảm bảo SL/TP trên position** (ensure_position_sl_tp).
4. **Basket Take Profit**: Tổng lợi nổi ≥ target_profit → đóng hết position của step, hủy pending, Telegram.
5. **Consecutive loss pause**: Giống bản gốc (MT5 history + DB fallback).
6. **Spread, max positions, quy tắc 2 lệnh chờ**: Giống bản gốc.
7. **Chuẩn bị đặt mới**: Hủy pending (nếu cần), lấy anchor → ref → buy_price, sell_price.
8. **Grid zone lock, min distance, cooldown**: Giống bản gốc.
9. **Re-entry lock (V2)**: Với bid/ask hiện tại, kiểm tra `BUY:buy_price` và `SELL:sell_price`. Nếu lock còn active và chưa thỏa unlock → không đặt lệnh tương ứng; nếu thỏa unlock → deactivate lock và cho phép đặt.
10. **Đặt lệnh**: Đặt BUY STOP (nếu không bị khóa), SELL STOP (nếu không bị khóa); có thể 0, 1 hoặc 2 lệnh. Ghi DB và cooldown cho từng lệnh đặt thành công.

---

## 6. SL/TP cố định (không trailing)

Giống bản gốc:

- **BUY** @ price → SL = price − step, TP = price + step.
- **SELL** @ price → SL = price + step, TP = price − step.

---

## 7. Quản lý rủi ro

Giống bản gốc, thêm một lớp V2:

| Quy tắc | Mô tả |
|--------|--------|
| **Re-entry lock (V2)** | Sau SL tại (side, entry), không đặt lại cùng (side, entry) cho đến khi giá thỏa unlock (bid ≤ E−2×step cho BUY, ask ≥ E+2×step cho SELL). |
| **Grid Zone Lock** | Không đặt tại mức đã có position. |
| **Min Distance** | Khoảng cách tối thiểu (point) tới position. |
| **Max Positions** | Giới hạn position mỗi step. |
| **Basket Take Profit** | Đóng hết khi tổng lợi nổi ≥ target_profit. |
| **Spread Protection** | Không giao dịch khi spread > spread_max. |
| **Cooldown** | Không đặt lại cùng mức trong X phút. |
| **Consecutive loss pause** | N lệnh thua liên tiếp → hủy pending, tạm dừng X phút. |

---

## 8. Cơ sở dữ liệu & file (V2)

- **grid_pending_orders**, **orders**: Giống bản gốc (cùng DB).
- **grid_reentry_locks_v2.json**: Danh sách re-entry lock (strategy_name, symbol, step, side, entry_price, unlock_rule, unlock_price, active, created_at, reason). File nằm cùng thư mục script.
- **grid_cooldown.json**, **grid_pause.json**: V2 dùng chung với bản gốc khi chạy cùng symbol/config.

---

## 9. Ví dụ chuỗi giá (có re-entry lock)

**Step = 5, ref = 5000:**

- Đặt BUY 5005, SELL 4995 (nếu không bị khóa).

**BUY 5005 khớp rồi SL tại 5000:**

- Bot tạo lock **BUY:5005**, unlock khi bid ≤ 4995.
- Vòng sau: ref vẫn có thể 5000 → buy_price=5005, sell_price=4995. **BUY:5005** đang khóa → không đặt BUY 5005; chỉ đặt **SELL 4995** (nếu hợp lệ).
- Khi giá xuống, bid ≤ 4995 → lock BUY:5005 được mở; vòng tiếp theo có thể đặt lại BUY 5005.

---

## 10. Ưu điểm & Rủi ro (V2)

**Ưu điểm:**

- Giữ toàn bộ ưu điểm bản gốc (đơn giản, không indicator, nhiều step).
- **Giảm whipsaw sideways** nhờ không retry ngay cùng chiều cùng mức sau SL; chỉ retry khi giá đã đi thêm 1 step (unlock).

**Rủi ro:**

- Cùng các rủi ro cơ bản như bản gốc (sideways, biến động, đảo chiều).
- Khi cả BUY và SELL đều bị khóa tại ref hiện tại, bot không đặt lệnh nào cho step đó đến khi ít nhất một bên thỏa unlock.

---

## 11. Tóm tắt V2

1. **V2** = Grid Step Bot + **re-entry lock theo mức + chiều sau SL** (theo `fix_whipsaw.md`).
2. Cấu hình **step** / **steps** và các tham số khác giống bản gốc; chạy bằng **strategy_grid_step_v2.py**, config `config_grid_step.json`.
3. Khi lệnh đóng tại SL → thêm lock (side, entry_price). Unlock: BUY khi bid ≤ entry−2×step, SELL khi ask ≥ entry+2×step.
4. Trước khi đặt BUY STOP / SELL STOP, kiểm tra lock; có thể đặt **0, 1 hoặc 2** lệnh tùy trạng thái lock và bid/ask.
5. Lock lưu trong **grid_reentry_locks_v2.json**; cooldown và pause dùng chung file với bản gốc.
6. SL/TP cố định, không trailing; các quy tắc grid zone, min distance, basket TP, spread, cooldown, consecutive loss pause vẫn áp dụng như bản gốc.
