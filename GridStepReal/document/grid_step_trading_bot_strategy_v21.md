# Grid Step Trading Bot V21 — Chiến thuật & Đặc tả

## 1. Tổng quan

**V21** là bản nâng cấp của Grid Step Bot, thêm **dịch ref khỏi vùng vừa thua** sau khi có lệnh đóng do SL (theo tài liệu `dịch ref khỏi vùng vừa thua.md`). Mục tiêu: không cho bot dựng lại grid ngay đúng vùng vừa stop-out, giảm whipsaw sideways.

- **Không dùng indicator** (EMA, ADX, RSI, Heiken Ashi...).
- Luôn đặt **hai lệnh chờ** (BUY STOP / SELL STOP) quanh ref; khi **một lệnh khớp** → hủy lệnh còn lại, dịch grid, đặt cặp mới.
- **Điểm khác V21:** Khi step **flat** (không còn position) và vừa có lệnh đóng do SL, bot **không dùng mid** cho lần dựng grid kế tiếp mà dùng **ref_override** (dịch ref ra khỏi vùng vừa thua), chỉ áp dụng **một lần** rồi trở lại logic bình thường.
- Mỗi lệnh có **SL/TP cố định** (không trailing).

**Script V21:**

| Thành phần | Giá trị |
|------------|--------|
| **Script** | strategy_grid_step_v21.py |
| **Config** | configs/config_grid_step_v21.json |
| **Magic** | 100021 (phân biệt với V1: 100010, V2: 100011) |
| **File state ref-shift** | grid_ref_shift_v21.json |
| **Cooldown / Pause** | Dùng chung grid_cooldown.json, grid_pause.json |

- Trong DB (bảng `orders`, `grid_pending_orders`): **strategy_name** = `Grid_21_Step` (legacy 1 step) hoặc `Grid_21_Step_5`, `Grid_21_Step_5.0`, ... (khi dùng `steps`) để phân biệt với V1 và V2.
- Comment MT5: `Grid21` / `Grid21_{step}` (để tách lệnh/position với bot khác).
- Chạy: `python strategy_grid_step_v21.py`. Kiểm tra DB: `python strategy_grid_step_v21.py --check-db`.

---

## 2. Khác biệt V21: Dịch ref khỏi vùng vừa thua (ref_override)

### 2.1. Mục tiêu

Sau khi một lệnh bị SL, nếu dùng ngay **mid** = (bid+ask)/2 để tính ref thì ref thường rơi đúng vùng vừa stop-out → bot dựng lại cặp pending giống cặp vừa thua → dễ whipsaw lặp lại. V21 **không dùng mid** cho **lần dựng grid ngay sau khi flat do SL**, mà dùng **ref_override** dịch ra khỏi phía vừa thua.

### 2.2. Quy tắc ref_override

| Lệnh vừa thua | Entry E | step S | ref_override |
|---------------|---------|--------|---------------|
| **BUY** @ E   | E       | S      | **E − S**     |
| **SELL** @ E | E       | S      | **E + S**     |

- **BUY** vừa SL → ref_override = E − step (kéo ref xuống một nấc, tránh dựng lại vùng BUY vừa fail).
- **SELL** vừa SL → ref_override = E + step (kéo ref lên một nấc, tránh dựng lại vùng SELL vừa fail).

Ví dụ step = 5:

- BUY @ 5005 bị SL → ref_override = 5005 − 5 = **5000** → grid kế tiếp: buy_price = 5005, sell_price = 4995 (vẫn quanh 5000 nhưng “reset thấp hơn” so với neo mid có thể ≈5002).
- SELL @ 4995 bị SL → ref_override = 4995 + 5 = **5000** → grid kế tiếp dịch lên, tránh neo ngay vùng đáy vừa quét SL.

### 2.3. Điều kiện áp dụng

- Step **vừa có** lệnh đóng do SL (profit < 0, phát hiện từ DB hoặc lệnh đóng gần đây trong 2 phút).
- Step hiện **không còn position mở** (flat).
- Bot chuẩn bị dựng grid mới (sẽ tính ref từ anchor).

**Chỉ áp dụng cho lần dựng grid kế tiếp:** ref_override là **override tạm thời 1 lần**. Sau khi dùng xong → clear state (`pending_ref_shift = false`), các vòng sau lại dùng anchor bình thường (position hoặc mid).

### 2.4. Trạng thái lưu (grid_ref_shift_v21.json)

Theo từng **strategy_name** (vd `Grid_21_Step_5.0`):

- `step`: giá trị step.
- `last_stopout_side`: "BUY" hoặc "SELL".
- `last_stopout_entry`: giá entry của lệnh vừa SL.
- `pending_ref_shift`: true khi vừa phát hiện SL và chưa dùng ref_override; false sau khi đã dùng một lần.

Luồng: phát hiện lệnh thua gần đây (từ DB) → set state (side, entry, pending_ref_shift = true). Lần flat tiếp theo cần dựng grid → dùng ref_override → set pending_ref_shift = false.

---

## 3. Cấu hình Step (bước giá)

Giống bản gốc. Tham số trong `config_grid_step_v21.json`:

| Tham số | Mô tả | Mặc định |
|--------|--------|----------|
| **step** | Bước grid và SL/TP (1 kênh legacy) | 5 |
| **steps** | Nhiều step cùng lúc, VD `[5]` hoặc `[2,5,7]` | — |
| **min_distance_points** | Khoảng cách tối thiểu (point) tới position hiện có | 5 |
| **target_profit** | Basket TP (đóng hết khi tổng lợi nổi ≥ giá trị này) | 50.0 |
| **spread_max** | Không đặt lệnh khi spread (giá) > giá trị này | 0.5 |
| **cooldown_minutes** | Không đặt lại cùng mức trong X phút; 0 = tắt | 0 |
| **consecutive_loss_pause_enabled** | Bật/tắt tạm dừng khi N lệnh thua liên tiếp | true |
| **consecutive_loss_count** | Số lệnh thua liên tiếp để kích hoạt | 2 |
| **consecutive_loss_pause_minutes** | Số phút tạm dừng (từ giờ đóng lệnh thua cuối) | 5 |

V21 không thêm tham số mới so với bản gốc.

---

## 4. Cách tính giá đặt lệnh (anchor, ref, buy_price, sell_price)

- **Có position:** anchor = giá mở của position mới nhất (theo thời gian).
- **Không position (flat):**
  - **Nếu có pending_ref_shift (hoặc vừa phát hiện lệnh thua gần đây):** dùng **ref_override** thay cho mid:
    - Lệnh vừa thua BUY @ E → ref_override = E − step.
    - Lệnh vừa thua SELL @ E → ref_override = E + step.
  - **Nếu không:** anchor = **mid** = (bid + ask) / 2.

Sau khi có anchor (hoặc ref_override dùng trực tiếp làm ref):

- **ref** = round(anchor / grid_step_price) × grid_step_price (hoặc ref = ref_override khi dùng override).
- **BUY STOP** = ref + grid_step_price.
- **SELL STOP** = ref − grid_step_price.

---

## 5. Luồng hoạt động V21 (Core Logic) — mỗi step

Thứ tự trong `strategy_grid_step_logic()` của V21:

1. **Đồng bộ DB lệnh chờ** (sync_grid_pending_status): Cập nhật PENDING → FILLED/CANCELLED; khi FILLED ghi position vào `orders` (strategy_name Grid_21_Step / Grid_21_Step_{step}, comment Grid21).
2. **Đảm bảo SL/TP trên position** (ensure_position_sl_tp).
3. **Basket Take Profit**: Tổng lợi nổi ≥ target_profit → đóng hết position của step, hủy pending, Telegram.
4. **Consecutive loss pause**: Giống bản gốc (MT5 history + DB fallback).
5. **Spread, max positions, quy tắc 2 lệnh chờ**: Giống bản gốc.
6. **Chuẩn bị đặt mới:**
   - Có position → hủy pending, anchor = giá position mới nhất.
   - Không position:
     - Nếu **pending_ref_shift** = true → dùng **ref_override** (từ state), in log "dùng ref_override (dịch khỏi vùng vừa thua)", clear pending_ref_shift.
     - Nếu chưa có state nhưng có **lệnh đóng thua trong 2 phút** (từ DB) → set state, dùng ref_override một lần, rồi clear.
     - Ngược lại → anchor = mid.
7. **ref, buy_price, sell_price**: Tính từ anchor (hoặc ref_override).
8. **Grid zone lock, min distance, cooldown**: Giống bản gốc.
9. **Đặt lệnh**: Đặt BUY STOP và SELL STOP; ghi DB (strategy_name Grid_21_Step / Grid_21_Step_{step}) và cooldown.

---

## 6. SL/TP cố định (không trailing)

Giống bản gốc:

- **BUY** @ price → SL = price − step, TP = price + step.
- **SELL** @ price → SL = price + step, TP = price − step.

---

## 7. Quản lý rủi ro

| Quy tắc | Mô tả |
|--------|--------|
| **Ref shift (V21)** | Sau SL, khi flat, lần dựng grid kế tiếp dùng ref_override (E−step cho BUY SL, E+step cho SELL SL) thay vì mid; chỉ áp dụng một lần. |
| **Grid Zone Lock** | Không đặt tại mức đã có position. |
| **Min Distance** | Khoảng cách tối thiểu (point) tới position. |
| **Max Positions** | Giới hạn position mỗi step. |
| **Basket Take Profit** | Đóng hết khi tổng lợi nổi ≥ target_profit. |
| **Spread Protection** | Không giao dịch khi spread > spread_max. |
| **Cooldown** | Không đặt lại cùng mức trong X phút. |
| **Consecutive loss pause** | N lệnh thua liên tiếp → hủy pending, tạm dừng X phút. |

---

## 8. Cơ sở dữ liệu & file (V21)

- **grid_pending_orders**, **orders**: Cùng DB với bản gốc; **strategy_name** = `Grid_21_Step` hoặc `Grid_21_Step_{step}` (vd `Grid_21_Step_5.0`) để dashboard và báo cáo tách với V1/V2.
- **grid_ref_shift_v21.json**: State ref-shift theo strategy_name (step, last_stopout_side, last_stopout_entry, pending_ref_shift). File nằm cùng thư mục script.
- **grid_cooldown.json**, **grid_pause.json**: V21 dùng chung với bản gốc (pause/cooldown theo strategy_name nên Grid_21_Step_5 và Grid_Step_5 tách nhau).
- **update_db.py**: Có xử lý riêng cho strategy `Grid_21_Step` (backfill khi không dùng `steps`; khi có `steps` không backfill với tên "Grid_21_Step"). Mapping trong `strategy_configs.json`: `"Grid_21_Step": "configs/config_grid_step_v21.json"`.

---

## 9. Ví dụ chuỗi giá (ref_override)

**Step = 5, ban đầu ref = 5000:**

- Đặt BUY 5005, SELL 4995.

**BUY 5005 khớp rồi SL tại 5000:**

- Bot flat. Lệnh vừa thua BUY @ 5005 → ref_override = 5005 − 5 = **5000**.
- Lần dựng grid kế tiếp: dùng ref_override = 5000 (không lấy mid có thể ≈5000.x) → vẫn buy_price=5005, sell_price=4995 nhưng logic đã “ép” ref từ phía vừa thua (BUY) xuống 5000; sau đó clear state.
- Các vòng sau lại dùng mid bình thường.

**SELL 4995 khớp rồi SL tại 5000:**

- ref_override = 4995 + 5 = **5000** → grid kế tiếp dịch ref lên 5000 (tránh neo lại đúng vùng đáy vừa SL).

---

## 10. Ưu điểm & Rủi ro (V21)

**Ưu điểm:**

- Giữ toàn bộ ưu điểm bản gốc (đơn giản, không indicator, nhiều step).
- **Giảm khả năng dựng lại grid ngay đúng vùng vừa SL** nhờ ref_override một lần; không kéo ref theo mid thụ động sau stop-out.

**Rủi ro:**

- Cùng các rủi ro cơ bản như bản gốc (sideways, biến động, đảo chiều).
- Ref_override chỉ dịch một nấc (1×step); trong thị trường sideways kéo dài vẫn có thể vào lại vùng tương tự sau vài vòng.

---

## 11. Tóm tắt V21

1. **V21** = Grid Step Bot + **dịch ref khỏi vùng vừa thua** (theo `dịch ref khỏi vùng vừa thua.md`).
2. **strategy_name** trong DB: `Grid_21_Step` / `Grid_21_Step_{step}`. Comment MT5: `Grid21` / `Grid21_{step}`. Config: `config_grid_step_v21.json`, magic **100021**.
3. Khi flat và vừa có lệnh đóng do SL → dùng **ref_override** (BUY SL: E−step, SELL SL: E+step) cho **lần dựng grid kế tiếp** rồi clear state.
4. State lưu trong **grid_ref_shift_v21.json**; cooldown và pause dùng chung file với bản gốc.
5. SL/TP cố định; các quy tắc grid zone, min distance, basket TP, spread, cooldown, consecutive loss pause giống bản gốc.
