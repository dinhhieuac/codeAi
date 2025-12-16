# 🚀 HƯỚNG DẪN CHỌN CHẾ ĐỘ KHI START BOT

## 🎯 **TỔNG QUAN**

Bot hiện hỗ trợ **3 chế độ filter** có thể chọn khi start:
- **`default`** - Mặc định (cân bằng)
- **`balanced`** - Cân bằng (linh hoạt hơn)
- **`strict`** - Khắt khe (chất lượng cao)

---

## 📋 **CÁCH SỬ DỤNG**

### **1. Chế độ mặc định (không chỉ định mode):**
```bash
python tuyen_trend.py
```
- Sử dụng file: `config_tuyen.json`
- Chế độ: Mặc định

---

### **2. Chế độ Default (cân bằng):**
```bash
python tuyen_trend.py --mode default
```
- Sử dụng file: `config_tuyen_default.json`
- Chế độ: Cân bằng giữa số lượng và chất lượng
- Signals: 1-3/ngày

---

### **3. Chế độ Balanced (linh hoạt hơn):**
```bash
python tuyen_trend.py --mode balanced
```
- Sử dụng file: `config_tuyen_balanced.json`
- Chế độ: Linh hoạt, nhiều signals hơn
- Signals: 3-8/ngày

---

### **4. Chế độ Strict (khắt khe):**
```bash
python tuyen_trend.py --mode strict
```
- Sử dụng file: `config_tuyen_strict.json`
- Chế độ: Khắt khe, chất lượng cao
- Signals: 0-1/ngày

---

## 📊 **CHO XAUUSD:**

### **1. Chế độ mặc định:**
```bash
python tuyen_trend_XAU.py
```
- Sử dụng file: `config_tuyen_xau.json`

### **2. Chế độ Default:**
```bash
python tuyen_trend_XAU.py --mode default
```
- Sử dụng file: `config_tuyen_xau_default.json`

### **3. Chế độ Balanced:**
```bash
python tuyen_trend_XAU.py --mode balanced
```
- Sử dụng file: `config_tuyen_xau_balanced.json`

### **4. Chế độ Strict:**
```bash
python tuyen_trend_XAU.py --mode strict
```
- Sử dụng file: `config_tuyen_xau_strict.json`

---

## 🔍 **XEM HELP:**

```bash
python tuyen_trend.py --help
```

Sẽ hiển thị:
```
usage: tuyen_trend.py [-h] [--mode {default,balanced,strict}]

Tuyen Trend Bot - Chọn chế độ filter

optional arguments:
  -h, --help            show this help message and exit
  --mode {default,balanced,strict}
                        Chế độ filter: default (mặc định), balanced (cân bằng), strict (khắt khe)

Ví dụ sử dụng:
  python tuyen_trend.py                    # Dùng config mặc định (config_tuyen.json)
  python tuyen_trend.py --mode default     # Chế độ mặc định
  python tuyen_trend.py --mode balanced    # Chế độ cân bằng (linh hoạt hơn)
  python tuyen_trend.py --mode strict     # Chế độ khắt khe (chất lượng cao)
```

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

### **Khi start với mode:**
```
================================================================================
✅ Tuyen Trend Bot (V2) - Started
📋 Chế độ: Cân Bằng (Linh Hoạt)
📁 Config: config_tuyen_balanced.json
================================================================================
```

### **Khi start không chỉ định mode:**
```
================================================================================
✅ Tuyen Trend Bot (V2) - Started
📋 Chế độ: Mặc Định (config_tuyen.json)
📁 Config: config_tuyen.json
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
   - Luôn được sử dụng nếu không chỉ định mode hoặc file mode không tồn tại

3. **Thay đổi mode:**
   - Chỉ cần restart bot với `--mode` khác
   - Không cần sửa code

---

## ✅ **KẾT LUẬN**

Bot hiện hỗ trợ **chọn chế độ dễ dàng** khi start:
- ✅ Không cần sửa code
- ✅ Chỉ cần thêm `--mode` khi start
- ✅ Tự động fallback nếu file không tồn tại
- ✅ Hiển thị rõ ràng chế độ đang dùng

**Chúc bạn trading thành công!** 🚀

