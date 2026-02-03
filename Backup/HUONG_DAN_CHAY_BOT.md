# 🚀 Hướng dẫn chạy Gold Auto Trader

Hướng dẫn chi tiết từng bước để chạy bot giao dịch vàng tự động.

---

## ⚙️ Bước 1: Cài đặt Python và Dependencies

### Kiểm tra Python

```bash
python3 --version
```

Nếu chưa có Python, tải từ: https://www.python.org/downloads/

### Upgrade pip (quan trọng!)

```bash
python3 -m pip install --upgrade pip
```

### Cài đặt thư viện cần thiết

```bash
pip3 install MetaTrader5 pandas numpy
```

**Hoặc dùng python3 -m pip:**

```bash
python3 -m pip install MetaTrader5 pandas numpy
```

**Lưu ý**: Nếu gặp lỗi, thử:
```bash
python3 -m pip install --user MetaTrader5 pandas numpy
```

---

## 📱 Bước 2: Chuẩn bị MetaTrader5

### Điều kiện bắt buộc:

1. ✅ **MetaTrader5 phải được cài đặt** trên máy tính
   - Tải từ: https://www.exness.com/metatrader/
   - Cài đặt và khởi động MT5

2. ✅ **Đăng nhập vào tài khoản MT5**
   - Mở MetaTrader5
   - Đăng nhập với tài khoản Exness của bạn
   - Đảm bảo đã kết nối thành công

3. ✅ **Symbol XAUUSD phải có sẵn**
   - Mở Market Watch trong MT5
   - Tìm và enable symbol `XAUUSD` (hoặc `XAUUSDm`, `GOLD`)
   - Đảm bảo symbol hiển thị giá real-time

---

## 🔧 Bước 3: Kiểm tra cấu hình

Mở file `examples/gold_auto_trader.py` và kiểm tra:

```python
TRADER = GoldAutoTrader(
    login=272736909,              # ✅ Đã cấu hình
    password="@Dinhhieu273",      # ✅ Đã cấu hình
    server="Exness-MT5Trial14",         # ⚠️ Kiểm tra tên server chính xác
    symbol="XAUUSD"              # ⚠️ Kiểm tra symbol trong MT5
)
```

**Quan trọng**: Kiểm tra **Server name** chính xác trong MT5:
- Mở MT5 → Tools → Options → Server
- Copy chính xác tên server (ví dụ: `ExnessReal-MT5`, `ExnessDemo-MT5`)

---

## 🏃 Bước 4: Chạy Bot

### Cách 1: Chạy trực tiếp (Recommended)

```bash
cd /Users/dinhhieuac/Desktop/project/exness/md5
python3 examples/gold_auto_trader.py
```

### Cách 2: Dùng script

```bash
cd /Users/dinhhieuac/Desktop/project/exness/md5
./run_gold_trader.sh
```

### Cách 3: Chạy nền (để bot chạy 24/7)

**Mac/Linux:**
```bash
cd /Users/dinhhieuac/Desktop/project/exness/md5
nohup python3 examples/gold_auto_trader.py > logs/bot_output.log 2>&1 &
```

**Kiểm tra process:**
```bash
ps aux | grep gold_auto_trader
```

**Dừng bot:**
```bash
pkill -f gold_auto_trader
```

---

## 📊 Bước 5: Monitor Bot

### Xem log real-time

```bash
tail -f logs/gold_trader.log
```

### Kiểm tra output trong terminal

Bot sẽ hiển thị:
```
✅ Đã kết nối MT5. Tài khoản: 272736909, Số dư: 1000.00
✅ Symbol XAUUSD đã sẵn sàng
🚀 Bắt đầu giao dịch tự động cho XAUUSD
⏱️  Kiểm tra tín hiệu mỗi 60 giây
📋 Quy tắc giao dịch:
   - Lot size cố định: 0.01 (không thay đổi)
   - Số lệnh tối đa: 10 lệnh cùng lúc
📈 Phân tích: Signal=BUY, Strength=3
...
```

---

## ⚠️ Xử lý lỗi thường gặp

### Lỗi 1: "MT5 initialization failed"

**Nguyên nhân**: MetaTrader5 không chạy

**Giải pháp**:
1. Mở MetaTrader5
2. Đăng nhập vào tài khoản
3. Chạy lại bot

### Lỗi 2: "MT5 login failed"

**Nguyên nhân**: Thông tin đăng nhập sai

**Giải pháp**:
1. Kiểm tra lại login, password trong code
2. **Quan trọng**: Kiểm tra **Server name** chính xác
   - Mở MT5 → Tools → Options → Server
   - Copy tên server chính xác (ví dụ: `ExnessReal-MT5`)

### Lỗi 3: "Symbol XAUUSD không tồn tại"

**Nguyên nhân**: Symbol không đúng hoặc chưa enable

**Giải pháp**:
1. Trong MT5, mở Market Watch (View → Market Watch)
2. Tìm symbol vàng (có thể là `XAUUSD`, `XAUUSDm`, `GOLD`)
3. Right-click → Show
4. Thử đổi symbol trong code nếu cần

### Lỗi 4: "No module named 'MetaTrader5'"

**Nguyên nhân**: Chưa cài đặt thư viện

**Giải pháp**:
```bash
python3 -m pip install --upgrade pip
python3 -m pip install MetaTrader5 pandas numpy
```

Nếu vẫn lỗi, thử:
```bash
python3 -m pip install --user MetaTrader5 pandas numpy
```

### Lỗi 5: "Could not find a version that satisfies the requirement MetaTrader5"

**Nguyên nhân**: pip quá cũ hoặc không tìm thấy package

**Giải pháp**:
```bash
# Upgrade pip
python3 -m pip install --upgrade pip

# Cài lại
python3 -m pip install MetaTrader5 pandas numpy

# Hoặc thử với user install
python3 -m pip install --user MetaTrader5 pandas numpy
```

---

## ✅ Checklist trước khi chạy

- [ ] Python 3.8+ đã cài đặt
- [ ] MetaTrader5 đã cài đặt và đang chạy
- [ ] Đã đăng nhập vào tài khoản MT5
- [ ] Symbol XAUUSD đã được enable trong Market Watch
- [ ] Đã cài đặt thư viện: `MetaTrader5`, `pandas`, `numpy`
- [ ] Đã cấu hình đúng login, password, server trong code
- [ ] Đã kiểm tra server name chính xác trong MT5
- [ ] Đã test trên tài khoản **DEMO** trước

---

## 🎯 Ví dụ chạy thành công

```
2024-10-31 10:15:00 - INFO - ✅ Đã kết nối MT5. Tài khoản: 272736909, Số dư: 1000.00
2024-10-31 10:15:01 - INFO - ✅ Symbol XAUUSD đã sẵn sàng
2024-10-31 10:15:01 - INFO - 🚀 Bắt đầu giao dịch tự động cho XAUUSD
2024-10-31 10:15:01 - INFO - ⏱️  Kiểm tra tín hiệu mỗi 60 giây
2024-10-31 10:15:01 - INFO - 📋 Quy tắc giao dịch:
2024-10-31 10:15:01 - INFO -    - Lot size cố định: 0.01 (không thay đổi)
2024-10-31 10:15:01 - INFO -    - Số lệnh tối đa: 10 lệnh cùng lúc
2024-10-31 10:16:01 - INFO - 📈 Phân tích: Signal=HOLD, Strength=0
2024-10-31 10:16:01 - INFO -    RSI: 55.20
2024-10-31 10:16:01 - INFO -    Lý do: 
...
```

---

## 🔄 Dừng Bot

Nhấn `Ctrl + C` trong terminal để dừng bot an toàn.

---

**Chúc bạn giao dịch thành công! 🚀**

> ⚠️ **NHẮC LẠI**: Luôn test trên tài khoản **DEMO** trước khi dùng real!

