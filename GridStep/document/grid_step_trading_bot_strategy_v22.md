# Grid Step Trading Bot V22 — Chiến thuật & Đặc tả

## 1. Tổng quan

**V22** là bản nâng cấp của Grid Step Bot, thêm **Chop Pause**: tạm dừng riêng từng step khi phát hiện mẫu **chop** (nhiều lệnh lỗ trong vùng giá hẹp), theo đặc tả `chop_pause_spec_grid_step.md`.

- **Không dùng indicator** (EMA, ADX, RSI, Heiken Ashi...).
- Luôn đặt **hai lệnh chờ** (BUY STOP / SELL STOP) quanh ref; khi một lệnh khớp → hủy lệnh còn lại, dịch grid, đặt cặp mới.
- **Chop Pause (V22):** Nếu trong N lệnh đóng gần nhất của step có đủ số lệnh lỗ và các entry nằm trong một **band hẹp** (theo step) → pause riêng step đó trong X phút, tránh tiếp tục đặt lệnh trong môi trường whipsaw.
- Mỗi lệnh có **SL/TP cố định** (không trailing).

**Script V22:**

| Thành phần | Giá trị |
|------------|--------|
| **Script** | strategy_grid_step_v22.py |
| **Config** | configs/config_grid_step_v22.json |
| **Magic** | 100022 (phân biệt với V1/V2/V21) |
| **DB strategy_name** | Grid_22_Step / Grid_22_Step_{step} |
| **Comment MT5** | Grid22 / Grid22_{step} |
| **Cooldown / Pause** | Dùng chung grid_cooldown.json, grid_pause.json |

Chạy: `python strategy_grid_step_v22.py`. Kiểm tra DB: `python strategy_grid_step_v22.py --check-db`.

---

## 2. Chop Pause (V22) — Tạm dừng khi phát hiện chop

### 2.1. Mục tiêu

Trong Grid Step, thua lỗ lớn thường đến từ **cụm lệnh gần nhau**: đa số lỗ, entry nằm trong vùng giá hẹp, BUY/SELL khớp luân phiên rồi dừng lỗ. Chop Pause nhằm:

- Phát hiện môi trường **nhiễu / sideways / whipsaw** từ chính lịch sử lệnh đóng của step.
- **Tạm dừng riêng từng step** khi bot đang bị “xay” trong vùng hẹp.
- Không dự báo xu hướng, chỉ trả lời: *Môi trường vài lệnh gần đây có đủ xấu để nên đứng ngoài tạm thời hay không?*

### 2.2. Định nghĩa “chop”

**Chop** trong cơ chế này là trạng thái đồng thời thỏa:

1. Trong **N** lệnh đóng gần nhất của cùng `strategy_name` (step), số lệnh **lỗ** ≥ `chop_loss_count`.
2. Các **entry_price** (open_price) của N lệnh đó nằm trong một **vùng giá đủ hẹp**:  
   `max(entry) - min(entry) ≤ chop_band_steps × step` (đơn vị giá).

Nói gọn: bot giao dịch đi lại quanh vài mức grid nhưng hiệu quả thấp, chủ yếu stop-out.

### 2.3. Cấu hình Chop Pause

Trong `parameters` của config V22:

| Tham số | Mô tả | Mặc định |
|--------|--------|----------|
| **chop_pause_enabled** | Bật/tắt Chop Pause | false (nên bật khi dùng V22) |
| **chop_window_trades** | Số lệnh đóng gần nhất cần xét (N) | 4 |
| **chop_loss_count** | Số lệnh lỗ tối thiểu trong N lệnh để coi là chop | 3 |
| **chop_band_steps** | Band giá (theo bước): entry nằm trong band = `chop_band_steps × step` | 2 |
| **chop_pause_minutes** | Số phút tạm dừng step khi phát hiện chop | 15 |
| **chop_require_closed_count_exact** | true = cần đúng N lệnh đóng; false = ít nhất N | true |

Ví dụ step = 5, chop_band_steps = 2 → band = 10 (giá). Nếu 4 lệnh gần nhất có entry trong khoảng 10 và ≥ 3 lệnh lỗ → chop → pause 15 phút.

### 2.4. Luồng xử lý

- Áp dụng **theo từng step** (theo `strategy_name`).
- Mỗi vòng logic: sau sync DB, kiểm tra `is_paused` (đã pause do consecutive loss hoặc chop) → nếu đang pause thì bỏ qua.
- Nếu bật Chop Pause: lấy N lệnh đóng gần nhất (có `open_price`) từ DB; kiểm tra số lỗ và band entry; nếu thỏa → `set_paused(strategy_name, chop_pause_minutes, from_time=close_time lệnh gần nhất)`, hủy lệnh chờ của step, return.
- Pause dùng chung file `grid_pause.json` (key = strategy_name), nên step V22 và step V1/V2 tách nhau theo tên.

---

## 3. Cấu hình Step (chung với bản gốc)

Ngoài các tham số Chop Pause ở trên, V22 dùng cùng cấu hình step như bản gốc:

| Tham số | Mô tả | Mặc định |
|--------|--------|----------|
| **step** / **steps** | Bước grid và SL/TP; nhiều kênh dùng `steps` (vd `[5]`) | 5 |
| **min_distance_points** | Khoảng cách tối thiểu (point) tới position | 5 |
| **target_profit** | Basket TP (đóng hết khi tổng lợi nổi ≥) | 50.0 |
| **spread_max** | Không đặt lệnh khi spread > | 0.5 |
| **cooldown_minutes** | Không đặt lại cùng mức trong X phút; 0 = tắt | 0 |
| **consecutive_loss_pause_enabled** | Bật tạm dừng khi N lệnh thua liên tiếp | true |
| **consecutive_loss_count** | Số lệnh thua liên tiếp để kích hoạt | 2 |
| **consecutive_loss_pause_minutes** | Số phút tạm dừng (consecutive loss) | 5 |

---

## 4. Cách tính giá đặt lệnh

Giống bản gốc:

- **Anchor:** Có position → giá mở position mới nhất; không position → mid = (bid + ask) / 2.
- **ref** = round(anchor / grid_step_price) × grid_step_price.
- **BUY STOP** = ref + grid_step_price, **SELL STOP** = ref - grid_step_price.

---

## 5. Luồng hoạt động V22 (mỗi step)

1. Sync lệnh chờ (grid_pending_orders), đảm bảo SL/TP trên position.
2. Basket Take Profit: nếu tổng lợi nổi ≥ target_profit → đóng hết, hủy pending, return.
3. **Pause (chung):** Nếu `is_paused(strategy_name)` → in log, return.
4. **Chop Pause (V22):** Nếu bật và thỏa điều kiện chop → set_paused(chop_pause_minutes), hủy pending, return.
5. Consecutive loss pause: như bản gốc (MT5 history + DB).
6. Spread, max positions, 2 lệnh chờ: như bản gốc.
7. Hủy pending (nếu cần), lấy anchor → ref → buy_price, sell_price.
8. Grid zone lock, min distance, cooldown: như bản gốc.
9. Đặt BUY STOP và SELL STOP, ghi DB (strategy_name Grid_22_Step / Grid_22_Step_{step}).

---

## 6. SL/TP, quản lý rủi ro

- **SL/TP:** Cố định theo step (BUY: SL = entry − step, TP = entry + step; SELL ngược lại). Không trailing.
- **Quản lý rủi ro:** Grid zone lock, min distance, max positions, Basket TP, spread protection, cooldown, consecutive loss pause — giống bản gốc. **Thêm:** Chop Pause (pause riêng step khi phát hiện chop).

---

## 7. Cơ sở dữ liệu & file (V22)

- **orders**, **grid_pending_orders:** strategy_name = `Grid_22_Step` hoặc `Grid_22_Step_{step}`; comment ghi trong orders = "Grid22".
- **grid_pause.json:** Dùng chung; key = strategy_name nên Grid_22_Step_5 và Grid_Step_5 tách nhau.
- **grid_cooldown.json:** Dùng chung.
- **update_db.py:** Có xử lý backfill cho `Grid_22_Step` (khi không dùng `steps`); khi có `steps` không backfill với tên "Grid_22_Step". Mapping trong `strategy_configs.json`: `"Grid_22_Step": "configs/config_grid_step_v22.json"`.

---

## 8. Tóm tắt V22

1. **V22** = Grid Step Bot + **Chop Pause** (theo `chop_pause_spec_grid_step.md`).
2. **strategy_name** trong DB: `Grid_22_Step` / `Grid_22_Step_{step}`. Comment MT5: `Grid22` / `Grid22_{step}`. Config: `config_grid_step_v22.json`, magic **100022**.
3. **Chop:** Trong N lệnh đóng gần nhất, nếu ≥ chop_loss_count lệnh lỗ và các entry nằm trong band (chop_band_steps × step) → pause step trong chop_pause_minutes phút.
4. Áp dụng **theo từng step**; pause/consecutive loss dùng chung `grid_pause.json`.
5. Các quy tắc grid, SL/TP, basket TP, spread, cooldown, consecutive loss pause giống bản gốc.
