# Phân tích nguyên nhân Win rate thấp – M1 Scalp XAUUSD

## 1. Tình trạng kết quả (mẫu 24 lệnh)

- **0 lệnh đóng tại TP** (profit > 0)
- **10 lệnh chạm SL gốc** → lỗ
- **14 lệnh đóng tại 0** → Breakeven (từng đạt ≥10 pip, bot dời SL về entry, sau đó giá quay về chạm SL = entry)

→ Win rate = 0% vì không có lệnh nào thực sự “thắng” (chạm TP).

---

## 2. Nguyên nhân chính

### 2.1 Breakeven 10 pip quá sớm so với TP (quan trọng nhất)

**Cách tính với XAUUSD:**
- Pip size XAU = **0.1** (1 pip = 0.1 USD).
- **10 pip** = **1.0 USD** lợi nhuận → trigger dời SL về entry.

**Từ dữ liệu thực tế (ví dụ lệnh BUY):**
- Entry: 5002.654, SL: 5000.336, TP: 5007.289  
- Khoảng cách SL = **2.318 USD** ≈ **23.2 pip**  
- Khoảng cách TP = **4.635 USD** ≈ **46.4 pip**  
- TP = 2×SL (R:R 1:2) đúng như thiết kế.

**Vấn đề:**
- Breakeven kích hoạt ở **10 pip (1 USD)** ≈ chỉ **~22%** quãng đường tới TP (46 pip).
- Giá thường không đi thẳng 46 pip; hay đi 10–30 pip rồi hồi.
- Khi giá lên ~10 pip → bot dời SL về entry → giá hồi 10+ pip → chạm SL (entry) → **đóng 0**.
- Kết quả: nhiều lệnh “gần thắng” (đã +10 pip) bị biến thành **breakeven**, không bao giờ cho giá cơ hội chạm TP.

**Kết luận:** Với TP = 46 pip và Breakeven = 10 pip, ta đang **khóa lợi nhuận quá sớm** so với mục tiêu, nên hầu hết lệnh có lãi nhỏ bị “ăn lại” về 0 thay vì chạm TP.

---

### 2.2 TP = 2×SL có thể quá xa trên M1 XAU

- SL thường **~2×ATR** (khoảng 2–4 USD tùy ATR).
- TP = **2×SL** → thường **4–8 USD** (40–80 pip) cho XAU.
- Trên **M1**, biến động hay không đủ mạnh/ổn định để giá đi thẳng 40–80 pip; nhiều khi đi 15–25 pip rồi điều chỉnh.
- Hệ quả: **ít lệnh chạm TP**, nhiều lệnh kết thúc tại SL hoặc breakeven.

---

### 2.3 Nhiều lệnh cùng hướng trong thời gian ngắn (re-entry)

**Ví dụ 17 Feb 2026, SELL:**
- 14:16:01, 14:16:23, 14:20:01, 14:20:56, 14:31:26, 14:31:40, 14:31:55  
→ **7 lệnh SELL** trong ~15 phút, vùng giá 4893–4895.

**Giải thích:**
- `max_positions = 1` → mỗi lúc chỉ 1 lệnh; khi lệnh đóng (SL hoặc breakeven), bot có thể vào lệnh mới ngay nến tiếp theo.
- Cùng một vùng giá / cùng cấu trúc, điều kiện SELL vẫn “đúng” trên nhiều nến M1 → bot **re-entry nhiều lần** trong cùng một đợt di chuyển.
- Trong sideway hoặc false break, dễ thành chuỗi: vào → breakeven/đóng 0 → vào lại → lỗ.

**Kết luận:** Thiếu cơ chế “nghỉ” sau khi đóng lệnh (theo thời gian hoặc theo biến động) → dễ vào lại cùng setup nhiều lần → tăng số lệnh thua / breakeven trong cùng vùng.

---

### 2.4 Entry trên M1 dễ false break

- Tín hiệu vào lệnh: **phá trendline sóng hồi** trên **M1**.
- M1 nhiều noise; “phá vỡ” có thể chỉ là vài nến rồi giá quay lại.
- Hệ quả: tỷ lệ **false break** cao → vào lệnh khi xu hướng thật chưa rõ → dễ chạm SL hoặc lên chút rồi về breakeven.

---

### 2.5 Pip size và Breakeven (kiểm tra kỹ thuật)

- `utils.get_pip_size()` với XAUUSD trả về **0.1** (đúng chuẩn vàng).
- `manage_position()` dùng `profit_pips = profit_price / pip_size` → 10 pip = 1.0 USD với XAU là **đúng**.
- Vấn đề không phải sai công thức pip, mà là **mức 10 pip (1 USD) quá nhỏ** so với SL/TP của chiến lược (SL ~23 pip, TP ~46 pip).

---

## 3. Tóm tắt nguyên nhân theo mức độ ảnh hưởng

| # | Nguyên nhân | Ảnh hưởng |
|---|-------------|-----------|
| 1 | **Breakeven 10 pip quá sớm** so với TP (46 pip) → nhiều lệnh “gần thắng” bị kéo về 0 | **Rất cao** |
| 2 | **TP = 2×SL** trên M1 XAU khó đạt → ít lệnh chạm TP | **Cao** |
| 3 | **Re-entry liên tục** cùng hướng trong vài phút → nhiều lệnh thua/0 trong cùng vùng | **Trung bình** |
| 4 | **False break** trên M1 → chất lượng entry không cao | **Trung bình** |

---

## 4. Đề xuất chỉnh sửa (ưu tiên)

### 4.1 Breakeven (tác động lớn nhất)

- **Cách 1 – Tăng trigger Breakeven (khuyến nghị):**  
  Trigger **20–25 pip** thay vì 10 pip (với XAU: 2–2.5 USD).  
  → Chỉ dời SL về entry khi lợi nhuận đã đi được gần nửa quãng tới TP, giảm “ăn lại” lệnh đang có lãi.
- **Cách 2 – Breakeven có buffer:**  
  Dời SL về **entry + 5 pip** (0.5 USD XAU) thay vì đúng entry.  
  → Vẫn bảo vệ vốn nhưng giảm số lệnh đóng đúng 0 khi giá hồi nhẹ.
- **Cách 3 – Tắt Breakeven tạm thời:**  
  Set `enable_breakeven: false` trong config, chạy thử và so sánh win rate / tổng P/L với hiện tại.

**Triển khai nhanh:** Thêm config `breakeven_trigger_pips` (mặc định 10), với XAU có thể set **20** hoặc **25** trong `config_tuyen_xau.json`, và dùng biến này trong `utils.manage_position()` thay vì hard-code 10.

---

### 4.2 TP / R:R

- Thử **TP = 1.5×SL** (R:R 1:1.5) thay vì 2×SL cho XAU M1.  
  → TP gần hơn, tăng xác suất chạm TP, có thể cải thiện win rate (cần test và so sánh P/L).
- Hoặc giữ TP = 2×SL nhưng **tăng trigger Breakeven** (như 4.1) để ít lệnh bị kéo về 0 trước khi có cơ hội chạm TP.

---

### 4.3 Cooldown sau khi đóng lệnh

- Sau khi đóng một lệnh (dù lỗ hay breakeven), **không mở lệnh mới cùng symbol trong X phút** (ví dụ 5–15 phút) hoặc cho đến khi nến M5 đóng.
- Tránh re-entry liên tục cùng hướng trong vài phút (như cụm 7 SELL ngày 17 Feb).
- Có thể thêm: `last_close_time` + `cooldown_minutes` trong config và kiểm tra trong bot trước khi mở lệnh.

---

### 4.4 Lọc entry (tùy chọn)

- Chỉ cho phép vào lệnh khi **ADX M5** đủ lớn (ví dụ ≥ 25) để giảm vào lệnh trong sideway.
- Hoặc chỉ vào trong **session London / NY** (giảm false break giờ ít biến động).

---

## 5. Việc nên làm ngay (không đổi code nhiều)

1. **Config:** Trong `config_tuyen_xau.json` thử **tắt Breakeven**: `"enable_breakeven": false` và chạy ít nhất vài chục lệnh, so sánh:
   - Số lệnh đóng tại TP (profit > 0)  
   - Số lệnh đóng tại SL (lỗ)  
   - Tổng P/L  
   Nếu win rate và P/L tốt hơn → xác nhận Breakeven 10 pip đang làm tệ win rate.
2. **Hoặc** chỉnh code ít: thêm `breakeven_trigger_pips` (mặc định 10), set **20** cho XAU trong config và dùng trong `manage_position()`.

Sau khi có dữ liệu mới, có thể tinh chỉnh tiếp (TP, cooldown, filter session/ADX).
