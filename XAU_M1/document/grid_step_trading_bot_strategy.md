# Grid Step Trading Bot — Chiến thuật & Đặc tả

## 1. Tổng quan

Bot giao dịch theo **lưới bước giá (grid step)**:

- **Không dùng indicator** (EMA, ADX, RSI, Heiken Ashi...).
- Luôn đặt **hai lệnh chờ** quanh giá hiện tại:
  - **BUY STOP** trên giá
  - **SELL STOP** dưới giá
- Khi **một lệnh khớp** → hủy lệnh chờ còn lại, **dịch grid** và đặt cặp lệnh chờ mới quanh giá vừa khớp.
- Mỗi lệnh có **SL/TP cố định** (không trailing, không breakeven).

---

## 2. Cấu hình Step (bước giá)

Step có thể cấu hình **3, 5, 6, 7...** (đơn vị giá, VD với XAU: 5 = 5 USD).

| Tham số | Mô tả | Mặc định |
|--------|--------|----------|
| **step** | Bước chung cho grid và SL/TP (có thể đặt 3, 5, 6, 7...) | 5 |
| **grid_step_price** | (Tùy chọn) Ghi đè bước grid riêng | Nếu không set → dùng `step` |
| **sl_tp_price** | (Tùy chọn) Ghi đè khoảng SL/TP riêng | Nếu không set → dùng `step` |
| **grid_step_points** | (Tùy chọn) Bước grid theo point: `grid_step_points * point` | Chỉ dùng khi không có `step` / `grid_step_price` |
| **cooldown_minutes** | (Tùy chọn) Không đặt lại cùng mức grid trong X phút; 0 = tắt | 0 |

**Ví dụ config (config_grid_step.json):**

```json
"parameters": {
    "step": 5,
    "min_distance_points": 5,
    "target_profit": 50.0,
    "spread_max": 0.5
}
```

Đổi step thành 7: `"step": 7`. Muốn grid 10 nhưng SL/TP 5: thêm `"grid_step_price": 10, "sl_tp_price": 5`.

---

## 3. Cách tính giá đặt lệnh

### 3.1 Giá neo (anchor)

- **Có ít nhất 1 position** → anchor = **giá mở** của position **mới nhất** (theo thời gian).
- **Không có position** → anchor = **giá thị trường** (mid = (bid + ask) / 2).

### 3.2 Mức grid (ref)

- `ref = round(anchor / grid_step_price) * grid_step_price` (làm tròn đến mức grid gần nhất).
- VD: step = 5, anchor = 5110 → ref = 5110; anchor = 5112.3 → ref = 5110.

### 3.3 Giá đặt lệnh chờ

- **BUY STOP** = ref + grid_step_price  
- **SELL STOP** = ref - grid_step_price  

**Ví dụ (step = 5, ref = 5110):**

- BUY STOP = 5115  
- SELL STOP = 5105  

---

## 4. Luồng hoạt động (Core Logic)

1. **Đồng bộ DB**: Cập nhật trạng thái lệnh chờ (PENDING → FILLED/CANCELLED); ghi lệnh đã khớp vào bảng `orders` với SL/TP đúng.
2. **Đảm bảo SL/TP trên position**: Nếu broker không kế thừa SL/TP từ lệnh chờ, bot gửi **TRADE_ACTION_SLTP** để đặt lại SL/TP = entry ± step cho từng position.
3. **Basket Take Profit**: Nếu tổng lợi nhuận (floating) ≥ `target_profit` → đóng hết position, hủy hết lệnh chờ, gửi Telegram.
4. **Bảo vệ spread**: Nếu spread (giá) > `spread_max` hoặc grid_step < spread → không đặt lệnh, chờ vòng sau.
5. **Giới hạn position**: Nếu số position ≥ `max_positions` → không đặt thêm.
6. **Không sửa lệnh chờ đang có**:
   - Nếu **đã có đủ 2 lệnh chờ** (1 BUY STOP + 1 SELL STOP) → **không làm gì**, chờ một lệnh khớp.
   - Chỉ đặt lệnh mới khi:
     - Chưa có lệnh chờ (0) hoặc chỉ 1 (dọn pending lẻ), hoặc
     - Vừa có lệnh khớp (có position) → hủy hết pending còn lại, đặt cặp mới quanh **anchor** (giá mở position mới nhất hoặc giá thị trường).
7. **Grid zone lock**: Không đặt BUY tại mức đã có position, không đặt SELL tại mức đã có position.
8. **Khoảng cách tối thiểu**: Không đặt nếu giá BUY/SELL mới quá gần bất kỳ position nào (theo `min_distance_points`).
9. Đặt cặp **BUY STOP** và **SELL STOP** với SL/TP cố định; ghi vào DB (`grid_pending_orders`).

---

## 5. SL/TP cố định (không trailing)

- **BUY** @ price → SL = price - step, TP = price + step  
- **SELL** @ price → SL = price + step, TP = price - step  

Step ở đây là `sl_tp_price` (hoặc `step` nếu không set). Bot **không** tự động dời SL (trailing) hay breakeven.

---

## 6. Quản lý rủi ro

| Quy tắc | Mô tả |
|--------|--------|
| **Grid Zone Lock** | Mỗi mức grid chỉ một lệnh; không mở thêm position trùng mức. |
| **Min Distance** | Khoảng cách tối thiểu (point) giữa giá đặt lệnh mới và các position hiện có. |
| **Max Positions** | Giới hạn số position mở cùng lúc (VD: 5). |
| **Basket Take Profit** | Khi tổng lợi nổi ≥ `target_profit` (VD: 50) → đóng tất cả, hủy pending. |
| **Spread Protection** | Không giao dịch khi spread (giá) > `spread_max`; grid step (giá) phải ≥ spread. |
| **Cooldown grid level** | (Tùy chọn) Không đặt lệnh lại tại cùng mức trong X phút; giảm whipsaw sideways. |

---

## 7. Rủi ro lớn nhất: Sideways Whipsaw

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

## 8. Cải thiện chống Whipsaw

### 8.1 Cooldown grid level (đã triển khai)

- **Tham số:** `cooldown_minutes` (số phút, mặc định 0 = tắt).
- **Cách hoạt động:** Sau khi đặt lệnh tại mức **buy_price** hoặc **sell_price**, bot ghi mức đó với thời điểm đặt. Trong X phút tiếp theo, **không đặt lệnh lại** tại đúng mức đó (nếu ref tính ra lại trùng mức đang cooldown thì bỏ qua, chờ vòng sau).
- **Config:** Trong `parameters` thêm `"cooldown_minutes": 5` (vd 5 phút). File lưu: `grid_cooldown.json` (cùng thư mục bot).

### 8.2 Đợi giá phá thêm 1 step sau SL (gợi ý)

- **Ý tưởng:** Nếu vừa chạm SL tại một mức, chỉ cho phép đặt lệnh lại tại mức đó khi giá đã **phá thêm 1 step** theo hướng có lợi (vd sau SL BUY tại 5005, đợi giá xuống 4995 rồi mới cho phép BUY 5005 lại).
- **Lợi ích:** Tránh vào lại ngay tại cùng mức khi thị trường vẫn đang đi ngang.
- **Triển khai:** Có thể bổ sung sau (track lệnh vừa đóng do SL, so sánh với giá hiện tại trước khi đặt).

---

## 9. Cơ sở dữ liệu

- **grid_pending_orders**: Lưu từng lệnh chờ (BUY_STOP/SELL_STOP): ticket, symbol, order_type, price, sl, tp, volume, status (PENDING → FILLED/CANCELLED), position_ticket (khi FILLED), placed_at, filled_at.
- **orders**: Lệnh đã khớp (position) được ghi với SL/TP đúng (entry ± step) để dashboard và báo cáo hiển thị chính xác.
- **grid_cooldown.json**: (Khi bật cooldown) Lưu thời điểm đặt lệnh theo từng mức giá để áp dụng cooldown.

---

## 10. Ví dụ chuỗi giá

**Step = 5, giá hiện tại 5000 (ref = 5000):**

- Đặt: BUY STOP 5005, SELL STOP 4995.

**Nếu BUY 5005 khớp:**

- Grid dịch lên; anchor = 5005 (giá mở position mới nhất).
- ref = 5005 → Đặt mới: BUY STOP 5010, SELL STOP 5000.

**Nếu SELL 4995 khớp:**

- Anchor = 4995 → ref = 4995.
- Đặt mới: BUY STOP 5000, SELL STOP 4990.

---

## 11. Ưu điểm & Rủi ro

**Ưu điểm:**

- Logic đơn giản, không phụ thuộc indicator.
- Dễ cấu hình step (3, 5, 6, 7...).
- Có thể bám theo xu hướng từng bước.

**Rủi ro:**

- **Sideways**: Giá đi ngang, khớp BUY rồi SELL liên tục → dễ whipsaw.
- **Biến động tin tức**: Giá nhảy mạnh → nhiều lệnh khớp nhanh.
- **Đảo chiều**: Nhiều position một chiều, giá đảo chiều → drawdown lớn.

---

## 12. Tóm tắt

1. Cấu hình **step** (3, 5, 6, 7...) cho grid và SL/TP; có thể tách `grid_step_price` / `sl_tp_price`.
2. Luôn đặt **một cặp** BUY STOP và SELL STOP quanh **ref** (ref = round(anchor / grid_step) * grid_step).
3. Khi **một lệnh khớp** → hủy pending còn lại, đặt cặp mới quanh anchor (giá mở position mới nhất hoặc giá thị trường).
4. **Không** thay đổi lệnh chờ đang chờ khớp; chỉ đặt mới khi 0/1 pending hoặc sau khi có fill.
5. SL/TP **cố định** entry ± step; không trailing; có bù SL/TP trên position nếu broker không kế thừa từ lệnh chờ.
6. Áp dụng **giới hạn position**, **khoảng cách tối thiểu**, **basket TP** và **spread** để quản lý rủi ro.
7. (Tùy chọn) **Cooldown grid level** (`cooldown_minutes` > 0): không đặt lại cùng mức trong X phút, giảm whipsaw sideways.
