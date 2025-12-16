# 🚀 HƯỚNG DẪN CHỌN CHẾ ĐỘ KHI START BOT

## 🎯 **TỔNG QUAN**

Bot hiện hỗ trợ **menu tương tác** để chọn chế độ filter khi start:
- **1** - Default (Mặc định) - Cân bằng
- **2** - Balanced (Cân bằng) - Linh hoạt hơn
- **3** - Strict (Khắt khe) - Chất lượng cao
- **0** - Sử dụng config mặc định

---

## 📋 **CÁCH SỬ DỤNG**

### **1. Start Bot:**
```bash
python tuyen_trend.py
```

### **2. Menu sẽ hiển thị:**
```
================================================================================
🚀 TUYEN TREND BOT (V2) - CHỌN CHẾ ĐỘ FILTER
================================================================================

📋 Vui lòng chọn chế độ filter:
   1️⃣  Default (Mặc định) - Cân bằng giữa số lượng và chất lượng (1-3 signals/ngày)
   2️⃣  Balanced (Cân bằng) - Linh hoạt hơn, nhiều signals hơn (3-8 signals/ngày)
   3️⃣  Strict (Khắt khe) - Chất lượng cao, ít signals (0-1 signals/ngày)
   0️⃣  Sử dụng config mặc định (config_tuyen.json)
================================================================================

👉 Nhập lựa chọn (1/2/3/0): 
```

### **3. Nhập số để chọn:**
- Nhập **`1`** → Chế độ Default
- Nhập **`2`** → Chế độ Balanced
- Nhập **`3`** → Chế độ Strict
- Nhập **`0`** → Config mặc định

---

## 📊 **CHO XAUUSD:**

### **1. Start Bot:**
```bash
python tuyen_trend_XAU.py
```

### **2. Menu tương tự sẽ hiển thị:**
- Nhập **`1`** → `config_tuyen_xau_default.json`
- Nhập **`2`** → `config_tuyen_xau_balanced.json`
- Nhập **`3`** → `config_tuyen_xau_strict.json`
- Nhập **`0`** → `config_tuyen_xau.json`

---

## 📁 **CÁC FILE CONFIG:**

### **EURUSD:**
- `config_tuyen.json` - Mặc định (khi không chỉ định mode)
- `config_tuyen_default.json` - Default mode
- `config_tuyen_balanced.json` - Balanced mode
- `config_tuyen_strict.json` - Strict mode

### **XAUUSD:**
- `config_tuyen_xau.json` - Mặc định (khi không chỉ định mode)
- `config_tuyen_xau_default.json` - Default mode
- `config_tuyen_xau_balanced.json` - Balanced mode
- `config_tuyen_xau_strict.json` - Strict mode

---

## 🎯 **VÍ DỤ OUTPUT KHI START:**

### **1. Menu hiển thị:**
```
================================================================================
🚀 TUYEN TREND BOT (V2) - CHỌN CHẾ ĐỘ FILTER
================================================================================

📋 Vui lòng chọn chế độ filter:
   1️⃣  Default (Mặc định) - Cân bằng giữa số lượng và chất lượng (1-3 signals/ngày)
   2️⃣  Balanced (Cân bằng) - Linh hoạt hơn, nhiều signals hơn (3-8 signals/ngày)
   3️⃣  Strict (Khắt khe) - Chất lượng cao, ít signals (0-1 signals/ngày)
   0️⃣  Sử dụng config mặc định (config_tuyen.json)
================================================================================

👉 Nhập lựa chọn (1/2/3/0): 2
```

### **2. Sau khi chọn (ví dụ chọn 2):**
```
================================================================================
✅ Tuyen Trend Bot (V2) - Started
📋 Chế độ: Cân Bằng (Balanced - Linh Hoạt)
📁 Config: config_tuyen_balanced.json
💱 Symbol: EURUSD
📊 Volume: 0.01
================================================================================
```

---

## ⚠️ **LƯU Ý:**

1. **Nếu file config không tồn tại:**
   - Bot sẽ tự động fallback về config mặc định
   - Hiển thị cảnh báo trong console

2. **File config mặc định:**
   - EURUSD: `config_tuyen.json`
   - XAUUSD: `config_tuyen_xau.json`
   - Luôn được sử dụng nếu chọn `0` hoặc file mode không tồn tại

3. **Thay đổi mode:**
   - Chỉ cần restart bot và chọn lại
   - Không cần sửa code

4. **Nhập sai:**
   - Nếu nhập số không hợp lệ, bot sẽ yêu cầu nhập lại
   - Có thể nhấn `Ctrl+C` để hủy và thoát

---

## ✅ **KẾT LUẬN**

Bot hiện hỗ trợ **menu tương tác** để chọn chế độ khi start:
- ✅ **Dễ sử dụng** - Chỉ cần nhập số 1, 2, 3 hoặc 0
- ✅ **Không cần sửa code** - Chọn trực tiếp khi start
- ✅ **Tự động fallback** - Nếu file không tồn tại
- ✅ **Hiển thị rõ ràng** - Chế độ và config đang dùng
- ✅ **An toàn** - Validate input, yêu cầu nhập lại nếu sai

**Chúc bạn trading thành công!** 🚀

