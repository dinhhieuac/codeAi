# Grid Step Trading Bot — Chiến thuật & Đặc tả

## 1. Tổng quan

Bot giao dịch theo **lưới bước giá (grid step)**:

- **Không dùng indicator** (EMA, ADX, RSI, Heiken Ashi...).
- Luôn đặt **hai lệnh chờ** quanh giá hiện tại:
  - **BUY STOP** trên giá
  - **SELL STOP** dưới giá
- Khi **một lệnh khớp** → hủy lệnh chờ còn lại, **dịch grid** và đặt cặp lệnh chờ mới quanh giá vừa khớp.
- Mỗi lệnh có **SL/TP cố định** (không trailing, không breakeven).

**Hai phiên bản triển khai:**

| Script | Symbol | Config | File cooldown | File pause |
|--------|--------|--------|----------------|------------|
| **strategy_grid_step.py** | XAUUSD | configs/config_grid_step.json | grid_cooldown.json | grid_pause.json |
| **strategy_grid_step_btc.py** | BTCUSD | configs/config_grid_step_btc.json | grid_cooldown_btc.json | grid_pause_btc.json |

Logic giống nhau; mỗi bot dùng DB/config và file cooldown/pause riêng. Chạy kiểm tra DB: `python strategy_grid_step.py --check-db` hoặc `python strategy_grid_step_btc.py --check-db`.

---

## 2. Cấu hình Step (bước giá)

Step có thể cấu hình **3, 5, 6, 7...** (đơn vị giá; VD XAU: 5 = 5 USD). Code hiện tại dùng **cùng một giá trị** cho bước grid và SL/TP (không tách `grid_step_price` / `sl_tp_price` trong config).

| Tham số | Mô tả | Mặc định |
|--------|--------|----------|
| **step** | Bước grid và SL/TP khi chạy 1 kênh (legacy) | 5 |
| **steps** | **Nhiều step chạy cùng lúc** — mảng, VD `[2, 3, 4, 5, 6, 7]` hoặc `[5]` | Nếu không set → dùng 1 step từ `step` |
| **min_distance_points** | Khoảng cách tối thiểu (point) giữa giá đặt lệnh mới và các position hiện có | 5 |
| **target_profit** | Basket TP: đóng hết khi tổng lợi nổi (floating) ≥ giá trị này | 50.0 |
| **spread_max** | Không đặt lệnh khi spread (giá) > giá trị này | 0.5 |
| **cooldown_minutes** | Không đặt lại cùng mức grid trong X phút; 0 = tắt | 0 |
| **consecutive_loss_pause_enabled** | Bật/tắt tạm dừng khi N lệnh thua liên tiếp | true |
| **consecutive_loss_count** | Số lệnh thua liên tiếp để kích hoạt (hủy lệnh chờ + tạm dừng) | 2 |
| **consecutive_loss_pause_minutes** | Số phút tạm dừng (tính từ giờ đóng lệnh thua cuối, theo MT5) | 5 |

*(Ghi chú: `grid_step_price`, `sl_tp_price`, `grid_step_points` có thể bổ sung sau để tách bước grid và SL/TP; hiện chỉ dùng `step` / `steps`.)*

### Chạy nhiều step cùng lúc

Khi set **`steps`** (mảng), bot chạy **song song nhiều kênh grid**, mỗi kênh một step:

- VD `"steps": [2, 3, 4, 5, 6, 7]` → 7 kênh: step 2, 3, 4, 5, 6, 7 chạy cùng lúc.
- Mỗi step có **anchor / ref / BUY STOP / SELL STOP** riêng; **position và pending** tách theo comment MT5 `GridStep_{step}`.
- **max_positions**, **target_profit**, **spread_max**, **cooldown_minutes** đọc từ config chung; **Basket TP** và **cooldown** áp dụng **theo từng step**.
- Trong DB: `strategy_name` = `Grid_Step_2`, `Grid_Step_3`, ... `Grid_Step_7` (dashboard hiển thị từng kênh).

**Ví dụ config 1 step (legacy):**

```json
"parameters": {
    "step": 5,
    "min_distance_points": 5,
    "target_profit": 50.0,
    "spread_max": 0.5
}
```

**Ví dụ config nhiều step:**

```json
"parameters": {
    "steps": [5],
    "min_distance_points": 5,
    "target_profit": 50.0,
    "spread_max": 0.5,
    "cooldown_minutes": 0,
    "consecutive_loss_pause_enabled": true,
    "consecutive_loss_count": 2,
    "consecutive_loss_pause_minutes": 5
}
```

---

## 3. Cách tính giá đặt lệnh

### 3.1 Giá neo (anchor)

- **Có ít nhất 1 position** (của step đang xử lý) → anchor = **giá mở** của position **mới nhất** (theo thời gian).
- **Không có position** → anchor = **giá thị trường** mid = (bid + ask) / 2.

### 3.2 Mức grid (ref)

- `ref = round(anchor / grid_step_price) * grid_step_price` (làm tròn đến mức grid gần nhất), với `grid_step_price` = step của kênh (từ `step` hoặc phần tử trong `steps`).
- VD: step = 5, anchor = 5110 → ref = 5110; anchor = 5112.3 → ref = 5110.

### 3.3 Giá đặt lệnh chờ

- **BUY STOP** = ref + grid_step_price  
- **SELL STOP** = ref - grid_step_price  

**Ví dụ (step = 5, ref = 5110):**

- BUY STOP = 5115  
- SELL STOP = 5105  

---

## 4. Luồng hoạt động (Core Logic) — mỗi step

Thứ tự trong `strategy_grid_step_logic()` (áp dụng cho từng step khi dùng `steps`):

1. **Đồng bộ DB lệnh chờ**: So sánh lệnh chờ trong DB (PENDING) với MT5; nếu ticket không còn trên MT5 thì cập nhật FILLED (ghép position theo giá) hoặc CANCELLED; khi FILLED → ghi position vào bảng `orders` với SL/TP = entry ± step.
2. **Đảm bảo SL/TP trên position**: Nếu broker không kế thừa SL/TP từ lệnh chờ, bot gửi **TRADE_ACTION_SLTP** để đặt lại SL/TP = entry ± step cho từng position của step.
3. **Basket Take Profit**: Nếu tổng lợi nổi (floating) của step ≥ `target_profit` và có position → đóng hết position của step, hủy hết lệnh chờ của step, gửi Telegram, return.
4. **Consecutive loss pause**: Nếu bật và đủ điều kiện:
   - Lấy N lệnh đóng gần nhất từ **MT5 history** (symbol + magic, 1 ngày) qua `grid_step_common.get_last_n_closed_profits_by_symbol`; nếu N lệnh đều lỗ → set pause cho `strategy_name` (Grid_Step hoặc Grid_Step_{step}), hủy lệnh chờ, gửi Telegram. Fallback: kiểm tra bảng `orders` qua `check_consecutive_losses_and_pause`.
   - Thời gian pause tính từ **giờ đóng lệnh thua cuối** (MT5). Trong thời gian pause → không đặt lệnh mới, in log thời gian chờ còn lại.
5. **Bảo vệ spread**: Spread (giá) > `spread_max` hoặc grid_step (giá) < spread → không đặt lệnh, chờ vòng sau.
6. **Giới hạn position**: Số position của step ≥ `max_positions` → không đặt thêm.
7. **Quy tắc 2 lệnh chờ**: Nếu đã có đủ **2 lệnh chờ** (1 BUY STOP + 1 SELL STOP) của step → không làm gì, chờ một lệnh khớp.
8. **Chuẩn bị đặt mới**: Nếu có position hoặc có pending (0 hoặc 1) → hủy hết lệnh chờ của step, lấy **anchor** (giá mở position mới nhất hoặc mid), tính **ref** → buy_price, sell_price.
9. **Grid zone lock**: Không đặt BUY tại mức đã có position, không đặt SELL tại mức đã có position (so sánh theo tolerance 1 point).
10. **Min distance**: Không đặt nếu buy_price hoặc sell_price quá gần bất kỳ position nào (khoảng cách < `min_distance_points * point`).
11. **Cooldown**: Nếu `cooldown_minutes` > 0 và mức buy_price hoặc sell_price đang trong cooldown → bỏ qua, chờ vòng sau.
12. Đặt cặp **BUY STOP** và **SELL STOP** với SL/TP cố định; nếu thành công thì ghi vào DB (`grid_pending_orders`) và (nếu bật) ghi mức vào file cooldown.

---

## 5. SL/TP cố định (không trailing)

- **BUY** @ price → SL = price - step, TP = price + step  
- **SELL** @ price → SL = price + step, TP = price - step  

Step ở đây là bước của kênh (trùng với grid_step_price). Bot **không** tự động dời SL (trailing) hay breakeven.

---

## 6. Quản lý rủi ro

| Quy tắc | Mô tả |
|--------|--------|
| **Grid Zone Lock** | Mỗi mức grid chỉ một lệnh; không mở thêm position trùng mức (position_at_level). |
| **Min Distance** | Khoảng cách tối thiểu (point) giữa giá đặt lệnh mới và các position hiện có. |
| **Max Positions** | Giới hạn số position mở cùng lúc cho mỗi step (VD: 5). |
| **Basket Take Profit** | Khi tổng lợi nổi của step ≥ `target_profit` → đóng tất cả position của step, hủy pending. |
| **Spread Protection** | Không giao dịch khi spread (giá) > `spread_max`; grid step (giá) phải ≥ spread. |
| **Cooldown grid level** | (Tùy chọn) Không đặt lệnh lại tại cùng mức trong X phút; giảm whipsaw sideways. |
| **Consecutive loss pause** | (Tùy chọn) Khi có N lệnh thua liên tiếp (theo MT5 history symbol+magic hoặc DB) → hủy lệnh chờ, tạm dừng X phút (từ giờ đóng lệnh thua cuối). |

### Tạm dừng khi N lệnh thua liên tiếp

- **consecutive_loss_pause_enabled** (mặc định true): Bật/tắt. `false` = không kiểm tra, không tạm dừng.
- **consecutive_loss_count** (mặc định 2): Số lệnh thua liên tiếp để kích hoạt. Nguồn: **MT5 history** (deals, symbol + magic, 1 ngày) hoặc fallback bảng **orders** (theo strategy_name + account_id).
- **consecutive_loss_pause_minutes** (mặc định 5): Số phút tạm dừng. Thời gian tính từ **giờ đóng lệnh thua cuối** (giờ MT5/server).
- Trạng thái pause lưu theo **strategy_name** trong `grid_pause.json` (XAU) hoặc `grid_pause_btc.json` (BTC). Hết thời gian thì bot tự đặt lệnh lại.

Mỗi vòng lặp, bot gọi **sync_closed_orders_from_mt5** để cập nhật profit/close_time từ MT5 vào bảng `orders`, giúp kiểm tra consecutive loss từ DB khi cần.

---

## 7. Vòng lặp chính (main loop)

- Mỗi vòng (~1 giây):
  - Nếu bật consecutive loss pause: đồng bộ lệnh đã đóng từ MT5 vào DB (`sync_closed_orders_from_mt5`) cho từng strategy_name (Grid_Step hoặc Grid_Step_{step}).
  - Gọi **strategy_grid_step_logic** cho từng step (hoặc 1 lần với step=None nếu legacy).
- Mỗi ~30 vòng: in heartbeat (số positions, pending, spread, loop count).
- **5 lỗi gửi lệnh liên tiếp**: gửi Telegram, sleep 2 phút, reset error count rồi tiếp tục.

---

## 8. Rủi ro lớn nhất: Sideways Whipsaw

Khi giá đi ngang (sideways), anchor luôn reset theo **lệnh cuối** (giá mở position mới nhất hoặc giá thị trường). Bot có thể **mở BUY → SL → mở BUY lại cùng mức → SL** lặp lại, gây lỗ liên tục.

**Ví dụ (step = 5):**

| Bước | Giá | Sự kiện | Anchor sau |
|------|-----|--------|------------|
| 1 | 5000 | Đặt BUY 5005, SELL 4995 | — |
| 2 | 5005 | BUY 5005 khớp | 5005 |
| 3 | 5000 | SL (5005 → 5000) | 5000 (giá thị trường) |
| 4 | 5000 | Đặt lại BUY 5005, SELL 4995 | 5000 |
| 5 | 5005 | BUY 5005 khớp lại | 5005 |
| 6 | 5000 | SL lại | 5000 |
| … | … | **Lặp: Mở BUY → SL → Mở BUY → SL** | … |

👉 **Điểm yếu:** Cùng mức 5005 được mở lại ngay sau khi SL vì anchor = 5000 (giá sau SL), ref = 5000 → BUY lại 5005.

---

## 9. Cải thiện chống Whipsaw

### 9.1 Cooldown grid level (đã triển khai)

- **Tham số:** `cooldown_minutes` (số phút, mặc định 0 = tắt).
- **Cách hoạt động:** Sau khi đặt lệnh tại mức **buy_price** hoặc **sell_price**, bot ghi mức đó (và step nếu multi-step) với thời điểm đặt vào file cooldown. Trong X phút tiếp theo, **không đặt lệnh lại** tại đúng mức đó.
- **File:** `grid_cooldown.json` (XAU) hoặc `grid_cooldown_btc.json` (BTC), cùng thư mục script.

### 9.2 Đợi giá phá thêm 1 step sau SL (gợi ý)

- **Ý tưởng:** Sau khi chạm SL tại một mức, chỉ cho phép đặt lệnh lại tại mức đó khi giá đã **phá thêm 1 step** theo hướng có lợi.
- **Triển khai:** Có thể bổ sung sau (track lệnh vừa đóng do SL, so sánh với giá hiện tại trước khi đặt).

---

## 10. Cơ sở dữ liệu & file

- **grid_pending_orders**: Lưu từng lệnh chờ (BUY_STOP/SELL_STOP): ticket, symbol, order_type, price, sl, tp, volume, status (PENDING → FILLED/CANCELLED), position_ticket (khi FILLED), placed_at, filled_at, strategy_name.
- **orders**: Lệnh đã khớp (position) được ghi với SL/TP đúng (entry ± step) để dashboard và báo cáo hiển thị chính xác; đồng bộ profit/close_time từ MT5 khi cần.
- **grid_cooldown.json** / **grid_cooldown_btc.json**: (Khi bật cooldown) Lưu thời điểm đặt lệnh theo từng mức giá (và step) để áp dụng cooldown.
- **grid_pause.json** / **grid_pause_btc.json**: Lưu trạng thái tạm dừng theo strategy_name (paused_until ISO).

---

## 11. Ví dụ chuỗi giá

**Step = 5, giá hiện tại 5000 (ref = 5000):**

- Đặt: BUY STOP 5005, SELL STOP 4995.

**Nếu BUY 5005 khớp:**

- Grid dịch lên; anchor = 5005 (giá mở position mới nhất).
- ref = 5005 → Đặt mới: BUY STOP 5010, SELL STOP 5000.

**Nếu SELL 4995 khớp:**

- Anchor = 4995 → ref = 4995.
- Đặt mới: BUY STOP 5000, SELL STOP 4990.

---

## 12. Ưu điểm & Rủi ro

**Ưu điểm:**

- Logic đơn giản, không phụ thuộc indicator.
- Dễ cấu hình step (3, 5, 6, 7...); có thể chạy nhiều step song song.
- Có thể bám theo xu hướng từng bước.

**Rủi ro:**

- **Sideways**: Giá đi ngang, khớp BUY rồi SELL liên tục → dễ whipsaw.
- **Biến động tin tức**: Giá nhảy mạnh → nhiều lệnh khớp nhanh.
- **Đảo chiều**: Nhiều position một chiều, giá đảo chiều → drawdown lớn.

---

## 13. Tóm tắt

1. Cấu hình **step** hoặc **steps** (mảng) cho grid và SL/TP; hiện tại cùng một giá trị cho cả hai.
2. Luôn đặt **một cặp** BUY STOP và SELL STOP quanh **ref** (ref = round(anchor / grid_step) * grid_step).
3. Khi **một lệnh khớp** → hủy pending còn lại của step, đặt cặp mới quanh anchor (giá mở position mới nhất hoặc giá thị trường).
4. **Không** sửa lệnh chờ đang chờ khớp; chỉ đặt mới khi 0/1 pending hoặc sau khi có fill (và đã hủy pending còn lại).
5. SL/TP **cố định** entry ± step; không trailing; có bù SL/TP trên position nếu broker không kế thừa từ lệnh chờ.
6. Áp dụng **max positions**, **min distance**, **basket TP**, **spread** và (tùy chọn) **cooldown**, **consecutive loss pause** để quản lý rủi ro.
7. Hai script: **strategy_grid_step.py** (XAUUSD), **strategy_grid_step_btc.py** (BTCUSD); logic giống nhau, khác config và file cooldown/pause.
