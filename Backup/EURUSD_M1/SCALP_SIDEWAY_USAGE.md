# Hướng Dẫn Sử Dụng: Scalp Sideway Bot

## 🚀 Cách Chạy Bot

### **Cách 1: Chạy Trực Tiếp**

```bash
# Chạy bot cho XAUUSD
python scalp_sideway.py configs/scalp_sideway_xau.json

# Chạy bot cho EURUSD
python scalp_sideway.py configs/scalp_sideway_eur.json

# Chạy bot cho BTCUSD
python scalp_sideway.py configs/scalp_sideway_btc.json
```

### **Cách 2: Chạy Nhiều Bot Cùng Lúc**

Tạo file `main_scalp_sideway.py`:

```python
import subprocess
import sys
import os

base_dir = os.path.dirname(os.path.abspath(__file__))

configs = [
    "configs/scalp_sideway_xau.json",
    "configs/scalp_sideway_eur.json",
    "configs/scalp_sideway_btc.json",
]

for config in configs:
    config_path = os.path.join(base_dir, config)
    print(f"🚀 Starting bot với config: {config_path}")
    subprocess.Popen([sys.executable, "scalp_sideway.py", config_path])
```

Chạy:
```bash
python main_scalp_sideway.py
```

---

## 📝 Tạo Config File Mới

### **Template Config:**

Tạo file `configs/scalp_sideway_<symbol>.json`:

```json
{
    "account": 413011866,
    "password": "your_password",
    "server": "Exness-MT5Trial6",
    "mt5_path": "C:\\Program Files\\MetaTrader 5 EXNESS -1\\terminal64.exe",
    "symbol": "XAUUSD",
    "volume": 0.01,
    "risk_percent": 2.0,
    "use_risk_based_lot": false,
    "min_atr": null,
    "magic": 500001,
    "max_positions": 1,
    "enable_breakeven": true,
    "enable_trailing_stop": true,
    "telegram_token": "your_telegram_token",
    "telegram_chat_id": "your_chat_id"
}
```

### **Các Symbol Hỗ Trợ:**

- **XAUUSD** (Gold) - Magic: 500001
- **EURUSD** (Forex) - Magic: 500002
- **BTCUSD** (Bitcoin) - Magic: 500003
- **ETHUSD** (Ethereum) - Magic: 500004
- **AUDUSD** (Forex) - Magic: 500005
- Và nhiều cặp khác...

---

## ⚙️ Cấu Hình

### **Các Tham Số Quan Trọng:**

1. **`symbol`**: Cặp giao dịch (XAUUSD, EURUSD, BTCUSD, etc.)
2. **`magic`**: Magic number (phải unique cho mỗi bot)
3. **`volume`**: Khối lượng giao dịch (lot)
4. **`max_positions`**: Số lệnh tối đa cùng lúc
5. **`enable_breakeven`**: Bật/tắt Breakeven
6. **`enable_trailing_stop`**: Bật/tắt Trailing Stop

### **Risk Management:**

- **`use_risk_based_lot`**: `true` = Tính lot tự động theo risk
- **`risk_percent`**: Tỷ lệ rủi ro (1.0 = 1%, 2.0 = 2%)

---

## 📊 Chiến Lược

### **SELL Signal:**
1. Xác định Supply zone trên M5
2. Kiểm tra thị trường xấu (ATR ratio, large body, etc.)
3. Kiểm tra bối cảnh Sideway
4. Tính DeltaHigh và Count (≥ 2)
5. Kiểm tra điều kiện SELL

### **BUY Signal:**
1. Xác định Demand zone trên M5
2. Kiểm tra thị trường xấu
3. Kiểm tra bối cảnh Sideway
4. Tính DeltaLow và Count (≥ 2)
5. Kiểm tra điều kiện BUY

### **Quản Lý Lệnh:**
- **SL**: 2 × ATR = 1R
- **TP1**: +1R (chốt 50%, dời SL về BE)
- **TP2**: 2R
- **Max 2 lệnh / vùng Supply/Demand**
- Nếu 1 lệnh SL → không vào lại cho đến khi M5 đổi nến

---

## 🔍 Log Files

Log files được lưu trong thư mục `logs/`:
- `{symbol}_m1_scalp_{YYYYMMDD}.txt`

Ví dụ:
- `xauusd_m1_scalp_20250106.txt`
- `eurusd_m1_scalp_20250106.txt`

---

## ⚠️ Lưu Ý

1. **Magic Number**: Mỗi bot phải có magic number riêng
2. **Config Path**: Phải là đường dẫn đầy đủ hoặc relative từ thư mục chứa script
3. **MT5 Connection**: Đảm bảo MT5 đã được cài đặt và config đúng
4. **Telegram**: Cần có token và chat_id để nhận thông báo

---

## 🐛 Troubleshooting

### **Lỗi: "Config file not found"**
- Kiểm tra đường dẫn config file
- Đảm bảo file tồn tại

### **Lỗi: "MT5 Init failed"**
- Kiểm tra account, password, server
- Kiểm tra đường dẫn MT5

### **Lỗi: "Không thể lấy dữ liệu"**
- Kiểm tra kết nối MT5
- Kiểm tra symbol có tồn tại không

---

## 📚 Tài Liệu Tham Khảo

- `Bot-Scalp-sideway_v1.md` - Chiến lược gốc
- `utils_scalp_sideway.py` - Utility functions
- `UTILS_SCALP_SIDEWAY_GUIDE.md` - Hướng dẫn sử dụng utilities
