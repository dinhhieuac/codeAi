# Tổng hợp các bước vào lệnh — Grid Step Bot

Tài liệu này mô tả **thứ tự và điều kiện** mà bot kiểm tra trước khi đặt lệnh chờ (BUY STOP / SELL STOP). Áp dụng cho **strategy_grid_step.py** (V1/V2); phiên bản **V3 tinh gọn** có bổ sung chi tiết triển khai trong các mục có gắn **(V3)**.

---

## 1. Chuẩn bị mỗi vòng (trước khi quyết định có đặt lệnh hay không)

| Bước | Mô tả |
|------|--------|
| **1.1** | Đồng bộ lệnh chờ với MT5: cập nhật DB (FILLED / CANCELLED); nếu FILLED → ghi position vào bảng `orders` với SL/TP = entry ± step. |
| **1.2** | Đảm bảo SL/TP trên từng position: nếu SL/TP = 0 thì gửi TRADE_ACTION_SLTP (entry ± step). |
| **1.3** | (Nếu bật) Đồng bộ lệnh đã đóng từ MT5 vào DB (`profit`, `close_time`, …) cho **đúng strategy_name** của step — dùng cho consecutive loss / chop. |
| **1.4** | **(V3) Ghi nhận stop-out mới** — Sau khi sync lệnh đóng (1.3), nếu phát hiện có lệnh của đúng `strategy_name` vừa đóng do **SL**, bot phải: (a) tạo **re-entry block**; (b) set **pending_ref_shift = true**; (c) lưu state: `last_stopout_side`, `last_stopout_entry`, `last_stopout_sl`, `last_stopout_time`. Đây là điểm kích hoạt cho re-entry lock (lớp 1) và ref shift (lớp 2). |

---

## 2. Các điều kiện chặn — không đặt lệnh mới (return sớm)

Nếu **bất kỳ** điều kiện sau thỏa → bot **không đặt** BUY STOP / SELL STOP, chờ vòng sau.

| # | Điều kiện | Mô tả |
|---|-----------|--------|
| **2.1** | **Basket TP** | Tổng lợi nổi (floating) của step ≥ `target_profit` và có position → đóng hết position, hủy hết pending, thông báo, **return**. |
| **2.2** | **Đang pause** | Strategy (step) đang trong thời gian tạm dừng (consecutive loss pause hoặc chop pause) → log, **return**. |
| **2.3** | **Consecutive loss** | Bật consecutive loss pause và N lệnh đóng gần nhất đều lỗ (MT5 history hoặc DB) → set pause, hủy pending, **return**. *(V1/V2: thường N=2.)* |
| **2.3a** | **(V3) Consecutive loss — vai trò** | Trong V3, consecutive loss pause **không còn là lớp chống whipsaw chính**. Nó là **circuit breaker / fail-safe cuối cùng**. Khuyến nghị: `consecutive_loss_count = 3` hoặc `4`; không nên giữ mặc định `2` nếu đã bật chop pause. |
| **2.4** | **Chop pause (V22/V3)** | (Nếu bật) Trong N lệnh đóng gần nhất: đủ lỗ và entry nằm trong band hẹp → set pause, hủy pending, **return**. |
| **2.4a** | **(V3) Chop pause — filter** | Chop pause **bắt buộc** lấy đúng lệnh đóng của **strategy_name đang xử lý** (vd `Grid_3_Step_5`), không lấy chung theo symbol toàn cục. Filter tối thiểu theo: `account_id`, `symbol`, `strategy_name`. Nếu không, dữ liệu giữa các step trộn lẫn và pause sai. |
| **2.5** | **Spread** | Spread (giá) > `spread_max` hoặc `grid_step_price` < spread → **return**. |
| **2.6** | **Max positions** | Số position của step ≥ `max_positions` → **return**. |
| **2.7** | **Đã đủ 2 pending (V1/V2)** | Đã có 2 lệnh chờ (1 BUY STOP + 1 SELL STOP) của step → không đặt thêm, **return**. *(V3: bỏ; cho phép 0/1/2 pending hợp lệ.)* |

---

## 3. Chuẩn bị giá đặt lệnh (Anchor / Ref)

### 3.1. V1/V2

| Bước | Mô tả |
|------|--------|
| **Anchor** | Có position → anchor = giá mở position **mới nhất**. Không có position → anchor = **mid** = (bid + ask) / 2. |
| **Ref** | `ref = round(anchor / grid_step_price) * grid_step_price`. |
| **Giá ứng viên** | `buy_price = ref + grid_step_price`, `sell_price = ref - grid_step_price`. |

### 3.2. (V3) Quy tắc chuẩn — ba trường hợp

| Trường hợp | Cách xác định ref |
|------------|-------------------|
| **A — Còn position mở** | `anchor = giá mở position mới nhất` → `ref = round(anchor / step) * step`. |
| **B — Flat và pending_ref_shift = true** | **Bỏ qua anchor; không dùng mid.** Dùng trực tiếp `ref_override` (xem công thức dưới). |
| **C — Flat bình thường** | `anchor = mid = (bid + ask) / 2` → `ref = round(anchor / step) * step`. |

### 3.3. (V3) Công thức ref_override (ghi rõ dấu)

- **BUY bị SL:**  
  `ref_override = SL - step`

- **SELL bị SL:**  
  `ref_override = SL + step`

**Ví dụ:**

- BUY @ 5005, SL = 5000, step = 5 → `ref_override = 4995`
- SELL @ 4995, SL = 5000, step = 5 → `ref_override = 5005`

### 3.4. (V3) Ref shift chỉ có hiệu lực cho lần dựng grid kế tiếp

Sau khi bot đã **dùng** `ref_override` một lần (để tính ref và đặt lệnh), phải **reset** `pending_ref_shift = false`. Không được giữ ref shift kéo dài qua nhiều vòng nếu không có stop-out mới.

---

## 4. Điều kiện từ chối theo mức (không đặt tại mức đó)

Nếu **mức** buy_price hoặc sell_price vi phạm → bot **không đặt** (hoặc không đặt phía vi phạm).

| # | Điều kiện | Áp dụng |
|---|-----------|--------|
| **4.1** | **Grid zone lock** | Không đặt BUY tại mức đã có position BUY; không đặt SELL tại mức đã có position SELL (tolerance 1 point). |
| **4.2** | **Min distance** | Không đặt nếu buy_price hoặc sell_price quá gần bất kỳ position nào (< `min_distance_points * point`). |
| **4.3** | **Cooldown** | (Nếu `cooldown_minutes` > 0) Mức buy_price hoặc sell_price đang trong cooldown → không đặt tại mức đó. *(V3: cooldown là lớp phụ, mặc định 0 — xem mục 6.)* |
| **4.4** | **Re-entry block (V3)** | (Nếu bật) Không đặt BUY tại mức entry vừa bị SL; không đặt SELL tại mức entry vừa bị SL. |

### 4.5. (V3) Re-entry block — chi tiết triển khai

- **Kiểm tra theo từng phía riêng:**  
  `buy_price` chỉ so với block của phía **BUY**; `sell_price` chỉ so với block của phía **SELL**. Không dùng một block chung cho cả hai chiều.

- **Block gắn đúng step / strategy_name:**  
  Một block phải định danh tối thiểu: `strategy_name`, `symbol`, `step`, `side`, `entry_price`. Ví dụ: `Grid_3_Step_5 | XAUUSD | step=5 | BUY | 5005`. Block của step 5 không được ảnh hưởng step 7.

- **Điều kiện mở khóa re-entry block:**
  - **BUY block:** mở khóa khi `bid <= unlock_price`, với `unlock_price = SL - step`.
  - **SELL block:** mở khóa khi `ask >= unlock_price`, với `unlock_price = SL + step`.

**Ví dụ:**

- BUY 5005 bị SL tại 5000, step = 5 → block BUY 5005; mở khóa khi `bid <= 4995`.
- SELL 4995 bị SL tại 5000, step = 5 → block SELL 4995; mở khóa khi `ask >= 5005`.

---

## 5. Hành động cuối: đặt lệnh

| Bước | Mô tả |
|------|--------|
| **5.1** | *(V1/V2)* Nếu có position hoặc có 0/1 pending → hủy hết pending của step, rồi đặt **cả hai** BUY STOP @ buy_price và SELL STOP @ sell_price (nếu không bị chặn bởi 4.1–4.3). |
| **5.2** | *(V3)* Kiểm tra **từng phía** riêng: `buy_allowed`, `sell_allowed`. Hủy pending không còn hợp lệ. Đặt **BUY STOP** nếu buy_allowed và chưa có BUY tại buy_price; đặt **SELL STOP** nếu sell_allowed và chưa có SELL tại sell_price → có thể **0, 1 hoặc 2** lệnh. |
| **5.3** | SL/TP cho mỗi lệnh chờ: BUY → SL = buy_price - step, TP = buy_price + step; SELL → SL = sell_price + step, TP = sell_price - step. |
| **5.4** | Ghi DB `grid_pending_orders`; nếu bật cooldown thì ghi mức vào file cooldown. |

### 5.5. (V3) V3 không ép đủ cặp BUY/SELL

Bot được phép ở các trạng thái: **2 pending hợp lệ**, **1 pending hợp lệ**, **0 pending hợp lệ**. Đây là hành vi đúng.

### 5.6. (V3) Không hủy pending còn hợp lệ chỉ vì thiếu cặp

**Không được:** thấy chỉ còn 1 pending → cancel pending đó → dựng lại toàn bộ chỉ để cố đủ 2 lệnh.

**Chỉ được hủy pending khi có lý do rõ ràng**, ví dụ:

- step bị pause  
- basket TP đóng rổ  
- pending phía đối diện đã fill  
- pending hiện tại không còn hợp lệ theo grid mới  
- pending bị block theo rule mới (vd re-entry block)  
- pending cần thay bằng mức mới sau stop-out  

### 5.7. (V3) Kiểm tra “đã có pending đúng mức đó chưa” trước khi đặt mới

Trước khi gửi BUY STOP hoặc SELL STOP, cần kiểm tra:

- đã có **BUY STOP** của step tại **buy_price** chưa  
- đã có **SELL STOP** của step tại **sell_price** chưa  

Nếu đã có đúng pending hợp lệ tại đúng mức đó thì **không đặt lại**. Tránh spam lệnh và ghi DB trùng.

---

## 6. (V3) Cooldown

- Cooldown kiểu cũ **không còn là lớp chống whipsaw chính**; chỉ là **lớp phụ time-based**. Khuyến nghị mặc định: **`cooldown_minutes = 0`**.
- Nếu vẫn bật cooldown, **thứ tự ưu tiên** khi kiểm tra điều kiện đặt lệnh có thể là: (1) zone lock, (2) min distance, (3) re-entry block, (4) cooldown phụ. Cooldown không được thay thế re-entry block.

---

## 7. (V3) State cần có để triển khai

### 7.1. Re-entry blocks — cấu trúc gợi ý

Ví dụ (theo strategy_name, mỗi block có đủ thông tin để filter và unlock):

```json
{
  "Grid_3_Step_5": [
    {
      "symbol": "XAUUSD",
      "step": 5,
      "side": "BUY",
      "entry_price": 5005.0,
      "sl_price": 5000.0,
      "unlock_rule": "bid_lte",
      "unlock_price": 4995.0,
      "active": true,
      "created_at": "2026-03-12T10:30:00",
      "reason": "SL"
    }
  ]
}
```

*(Trong code có thể tính `unlock_price` từ `sl_price` và `step` thay vì lưu riêng; `unlock_rule` có thể ngầm hiểu: BUY → bid <= sl - step, SELL → ask >= sl + step.)*

### 7.2. Ref shift state (pending_ref_shift)

Cần lưu tối thiểu: `last_stopout_side`, `last_stopout_entry`, `last_stopout_sl`, `last_stopout_time`, `pending_ref_shift` (boolean). Sau khi dùng ref_override một lần → set `pending_ref_shift = false`.

---

## 8. Tóm tắt thứ tự (flow vào lệnh)

```
Sync pending (1.1) → Đảm bảo SL/TP (1.2) → Sync closed (1.3) → [V3: Ghi nhận stop-out (1.4)]
    → Basket TP? (có → đóng hết, return)
    → Đang pause? (có → return)
    → Consecutive loss? (có → pause, return)
    → Chop pause? (V22/V3, có → pause, return)  [V3: filter đúng strategy_name]
    → Spread / max positions / đủ 2 pending (V1/V2)? (có → return)
    → [V3: A/B/C] Tính anchor hoặc ref_override → ref → buy_price, sell_price
    → Zone lock / min distance / re-entry block (V3) / cooldown? (vi phạm → không đặt phía đó hoặc return)
    → [V3: Kiểm tra đã có pending đúng mức chưa] → Đặt BUY STOP và/hoặc SELL STOP (theo từng phiên bản)
    → [V3: Refresh unlock re-entry blocks]
    → Ghi DB, cooldown (nếu có)
```

---

## 9. Khác biệt theo phiên bản

| Nội dung | V1/V2 (strategy_grid_step) | V22 (chop pause) | V3 (tinh gọn) |
|----------|----------------------------|-------------------|----------------|
| **Chuẩn bị** | 1.1–1.3 | 1.1–1.3 | + 1.4 Ghi nhận stop-out |
| **Anchor khi flat** | Luôn mid | Luôn mid | Flat + pending_ref_shift → ref_override (SL ± step); sau khi dùng reset pending_ref_shift |
| **Số pending** | Luôn cố 2 (hoặc 0 khi chờ khớp) | Luôn cố 2 | Tối đa 2 **hợp lệ**, có thể 0 hoặc 1; không ép đủ cặp |
| **Chặn trước khi đặt** | Consecutive loss, spread, max pos, đủ 2 pending | + Chop pause | + Chop pause (filter strategy_name); Consecutive loss = fail-safe (count 3/4) |
| **Hủy pending** | Có position hoặc 0/1 pending → hủy hết rồi đặt lại | Giống V1/V2 | Chỉ hủy khi có lý do rõ ràng; không hủy vì thiếu cặp |
| **Đặt lệnh** | Đặt cả 2 nếu pass | Đặt cả 2 nếu pass | Kiểm tra từng phía; đặt chỉ khi chưa có pending đúng mức |
| **Re-entry / Ref shift** | Không | Không | Block theo side + strategy_name; ref_override; refresh unlock cuối vòng |
| **Cooldown** | Có thể bật | Có thể bật | Lớp phụ, mặc định 0; ưu tiên sau re-entry block |
| **Refresh unlock** | — | — | Cuối vòng: mở khóa re-entry khi bid/ask qua unlock_price |

---

*Tài liệu tham chiếu: grid_step_trading_bot_strategy.md, grid_step_trading_bot_strategy_v3.md, chop_pause_spec_grid_step.md.*
