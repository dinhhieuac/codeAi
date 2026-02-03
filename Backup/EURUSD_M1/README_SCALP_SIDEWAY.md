# 🚀 Scalp Sideway Bot - Hướng Dẫn Sử Dụng Đơn Giản

## ✅ Đã Hoàn Thành

### **Files Đã Tạo:**

1. **`scalp_sideway.py`** - Main bot file
2. **`utils_scalp_sideway.py`** - Utility functions
3. **Config files:**
   - `configs/scalp_sideway_xau.json` - XAUUSD
   - `configs/scalp_sideway_eur.json` - EURUSD
   - `configs/scalp_sideway_btc.json` - BTCUSD

---

## 🎯 Cách Sử Dụng (Cực Kỳ Đơn Giản)

### **Chỉ cần 1 dòng lệnh:**

```bash
# Chạy bot cho XAUUSD
python scalp_sideway.py configs/scalp_sideway_xau.json

# Chạy bot cho EURUSD
python scalp_sideway.py configs/scalp_sideway_eur.json

# Chạy bot cho BTCUSD
python scalp_sideway.py configs/scalp_sideway_btc.json
```

**Vậy thôi! Bot sẽ tự động:**
- ✅ Load config
- ✅ Kết nối MT5
- ✅ Chạy chiến lược Scalp Sideway
- ✅ Gửi thông báo Telegram
- ✅ Log vào file

---

## 📝 Tạo Config File Mới

### **Bước 1: Copy template**

```bash
cp configs/scalp_sideway_xau.json configs/scalp_sideway_eth.json
```

### **Bước 2: Sửa config**

Mở file `configs/scalp_sideway_eth.json` và sửa:

```json
{
    "symbol": "ETHUSD",        // Đổi symbol
    "magic": 500004,           // Đổi magic number (unique)
    "volume": 0.01,            // Điều chỉnh volume
    ...
}
```

### **Bước 3: Chạy bot**

```bash
python scalp_sideway.py configs/scalp_sideway_eth.json
```

---

## 🔧 Cấu Hình Nhanh

### **Các Tham Số Quan Trọng:**

| Tham Số | Mô Tả | Ví Dụ |
|---------|-------|-------|
| `symbol` | Cặp giao dịch | `XAUUSD`, `EURUSD`, `BTCUSD` |
| `magic` | Magic number (phải unique) | `500001`, `500002`, `500003` |
| `volume` | Khối lượng giao dịch | `0.01` (1 micro lot) |
| `max_positions` | Số lệnh tối đa | `1` hoặc `2` |
| `enable_breakeven` | Bật Breakeven | `true` hoặc `false` |
| `enable_trailing_stop` | Bật Trailing Stop | `true` hoặc `false` |

---

## 📊 Chiến Lược

### **SELL Signal:**
1. ✅ Supply zone trên M5
2. ✅ Thị trường hợp lệ (ATR ratio, sideway)
3. ✅ DeltaHigh hợp lệ (Count ≥ 2)
4. ✅ Điều kiện SELL

### **BUY Signal:**
1. ✅ Demand zone trên M5
2. ✅ Thị trường hợp lệ
3. ✅ DeltaLow hợp lệ (Count ≥ 2)
4. ✅ Điều kiện BUY

### **Quản Lý Lệnh:**
- **SL**: 2 × ATR = 1R
- **TP1**: +1R (chốt 50%, dời SL về BE)
- **TP2**: 2R
- **Max 2 lệnh / vùng**

---

## 📁 Cấu Trúc Files

```
EURUSD_M1/
├── scalp_sideway.py              # Main bot
├── utils_scalp_sideway.py         # Utilities
├── configs/
│   ├── scalp_sideway_xau.json    # Config XAUUSD
│   ├── scalp_sideway_eur.json    # Config EURUSD
│   └── scalp_sideway_btc.json    # Config BTCUSD
└── logs/
    └── {symbol}_m1_scalp_{date}.txt
```

---

## 🎉 Ví Dụ Sử Dụng

### **Chạy Bot XAUUSD:**

```bash
cd EURUSD_M1
python scalp_sideway.py configs/scalp_sideway_xau.json
```

**Output:**
```
✅ Scalp Sideway Bot - Started
💱 Symbol: XAUUSD
📊 Volume: 0.01
🆔 Magic: 500001
🔄 Bắt đầu vòng lặp chính...
```

### **Chạy Nhiều Bot Cùng Lúc:**

Tạo file `run_all_sideway.py`:

```python
import subprocess
import sys
import time

configs = [
    "configs/scalp_sideway_xau.json",
    "configs/scalp_sideway_eur.json",
    "configs/scalp_sideway_btc.json",
]

for config in configs:
    print(f"🚀 Starting: {config}")
    subprocess.Popen([sys.executable, "scalp_sideway.py", config])
    time.sleep(2)

print("✅ All bots started!")
```

Chạy:
```bash
python run_all_sideway.py
```

---

## ⚠️ Lưu Ý

1. **Magic Number**: Mỗi bot phải có magic number riêng
2. **Config Path**: Relative từ thư mục chứa `scalp_sideway.py`
3. **MT5**: Đảm bảo MT5 đã được cài đặt và config đúng
4. **Telegram**: Cần có token và chat_id

---

## 📚 Tài Liệu

- `SCALP_SIDEWAY_USAGE.md` - Hướng dẫn chi tiết
- `UTILS_SCALP_SIDEWAY_GUIDE.md` - Hướng dẫn utilities
- `Bot-Scalp-sideway_v1.md` - Chiến lược gốc

---

## 🎯 Tóm Tắt

**Chỉ cần:**
1. Tạo config file (hoặc dùng template có sẵn)
2. Chạy: `python scalp_sideway.py configs/scalp_sideway_xau.json`
3. Xong! Bot tự động chạy.

**Đơn giản vậy thôi!** 🚀
