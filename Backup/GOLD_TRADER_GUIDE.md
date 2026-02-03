# 🥇 Hướng dẫn sử dụng Gold Auto Trader

Hướng dẫn chi tiết để thiết lập và chạy hệ thống giao dịch tự động cho vàng (XAUUSD).

---

## 📋 Yêu cầu

1. **Tài khoản Exness MT5** (demo hoặc real)
2. **MetaTrader5** đã cài đặt và đăng nhập
3. **Python 3.8+** đã cài đặt
4. **Các thư viện Python cần thiết**

---

## 🚀 Cài đặt

### Bước 1: Cài đặt thư viện

```bash
pip install MetaTrader5 pandas numpy
```

Hoặc cài từ file requirements.txt:

```bash
pip install -r requirements.txt
```

### Bước 2: Tạo thư mục logs

```bash
mkdir logs
```

### Bước 3: Cấu hình thông tin đăng nhập

Mở file `examples/gold_auto_trader.py` và thay đổi thông tin:

```python
TRADER = GoldAutoTrader(
    login=12345678,  # ← Thay bằng số tài khoản MT5 của bạn
    password="your_password_here",  # ← Thay bằng mật khẩu MT5
    server="Exness-MT5",  # ← Thay bằng tên server của bạn
    symbol="XAUUSD"  # Symbol vàng (có thể là XAUUSD, XAUUSDm)
)
```

**Lưu ý**: 
- Kiểm tra symbol chính xác trong MT5 của bạn (có thể là `XAUUSD`, `XAUUSDm`, hoặc `GOLD`)
- Server name có thể khác tùy broker (ví dụ: `ExnessReal-MT5`, `ExnessDemo-MT5`)

---

## ⚙️ Cấu hình Bot

Bạn có thể điều chỉnh các tham số trong class `GoldAutoTrader`:

```python
# Trong __init__ method:
self.default_lot = 0.01        # Lot size mặc định
self.max_lot = 1.0            # Lot size tối đa
self.max_positions = 1        # Số vị thế tối đa cùng lúc
self.rsi_oversold = 30        # Ngưỡng RSI oversold
self.rsi_overbought = 70      # Ngưỡng RSI overbought
```

### Điều chỉnh ngưỡng tín hiệu

Trong method `run_auto_trading()`, bạn có thể thay đổi:

```python
# Yêu cầu ít nhất 2 chỉ báo đồng thuận để đặt lệnh
if analysis['signal'] == 'BUY' and analysis['strength'] >= 2:
    # Thay đổi >= 2 thành >= 3 để yêu cầu tín hiệu mạnh hơn
```

### Điều chỉnh interval kiểm tra

```python
# Kiểm tra mỗi 60 giây (có thể thay đổi)
TRADER.run_auto_trading(interval_seconds=60)

# Ví dụ: Kiểm tra mỗi 5 phút (300 giây)
TRADER.run_auto_trading(interval_seconds=300)
```

---

## 🎯 Cách chạy

### Chạy trực tiếp

```bash
cd examples
python gold_auto_trader.py
```

### Chạy nền (Linux/Mac)

```bash
nohup python examples/gold_auto_trader.py > logs/bot_output.log 2>&1 &
```

### Kiểm tra log

```bash
tail -f logs/gold_trader.log
```

---

## 📊 Cách hoạt động

### 1. Phân tích kỹ thuật

Bot sử dụng 5 chỉ báo chính:

- **RSI**: Phát hiện oversold/overbought
- **MACD**: Phát hiện crossover bullish/bearish
- **Moving Averages**: Xác định xu hướng (MA20, MA50)
- **Bollinger Bands**: Phát hiện giá ở vùng cực trị
- **Stochastic**: Xác nhận tín hiệu oversold/overbought

### 2. Tín hiệu mua (BUY)

Bot sẽ mua khi có **≥2 chỉ báo** cho tín hiệu mua, ví dụ:
- RSI < 30 (oversold)
- MACD crossover bullish
- Giá ở Bollinger Band dưới
- Stochastic oversold

### 3. Tín hiệu bán (SELL)

Bot sẽ bán khi có **≥2 chỉ báo** cho tín hiệu bán, ví dụ:
- RSI > 70 (overbought)
- MACD crossover bearish
- Giá ở Bollinger Band trên
- Stochastic overbought

### 4. Quản lý rủi ro

- **Stop Loss (SL)**: Tự động tính từ ATR (khoảng 2×ATR)
- **Take Profit (TP)**: Tự động tính từ ATR (khoảng 3×ATR)
- **Giới hạn**: SL tối thiểu 50 points, tối đa 500 points
- **Chỉ mở 1 vị thế**: Tránh overexposure

---

## 🔍 Monitoring

### Xem log real-time

```bash
tail -f logs/gold_trader.log
```

### Kiểm tra vị thế trong MT5

Bot sẽ log mỗi khi có vị thế mở:
```
📊 Đang có 1 vị thế mở
   - BUY 0.01 lots, P&L: 15.50
```

### Ví dụ output log

```
2024-01-15 10:30:00 - INFO - ✅ Đã kết nối MT5. Tài khoản: 12345678, Số dư: 1000.00
2024-01-15 10:30:01 - INFO - ✅ Symbol XAUUSD đã sẵn sàng
2024-01-15 10:30:01 - INFO - 🚀 Bắt đầu giao dịch tự động cho XAUUSD
2024-01-15 10:31:00 - INFO - 📈 Phân tích: Signal=BUY, Strength=3
2024-01-15 10:31:00 - INFO -    RSI: 28.50
2024-01-15 10:31:00 - INFO -    Lý do: RSI oversold (28.50), MACD crossover bullish, Price at BB lower band
2024-01-15 10:31:01 - INFO - ✅ Đã mở lệnh BUY XAUUSD 0.01 lots tại 2020.50, SL: 2015.00, TP: 2030.00
```

---

## ⚠️ Lưu ý quan trọng

### 1. Test trên Demo trước

**LUÔN** test trên tài khoản demo ít nhất 1-2 tuần trước khi chạy real.

### 2. Kiểm tra kết nối

- Đảm bảo MetaTrader5 đang chạy
- Đảm bảo đã đăng nhập vào tài khoản MT5
- Kiểm tra symbol có tồn tại trong Market Watch

### 3. Quản lý rủi ro

- Bắt đầu với lot size nhỏ (0.01)
- Monitor bot thường xuyên, đặc biệt khi mới chạy
- Đặt giới hạn daily loss nếu cần

### 4. Thị trường vàng

- Vàng (XAUUSD) có volatility cao
- Giá có thể biến động mạnh trong tin tức
- Cân nhắc tắt bot trong giờ tin tức quan trọng (NFP, FOMC, v.v.)

### 5. VPS/Server

Nếu muốn chạy 24/7, nên chạy trên VPS:
- AWS, DigitalOcean, Vultr
- Hoặc máy tính luôn bật tại nhà

---

## 🛠️ Troubleshooting

### Lỗi: "MT5 initialization failed"

**Nguyên nhân**: MetaTrader5 không chạy hoặc không tìm thấy

**Giải pháp**:
1. Mở MetaTrader5
2. Đăng nhập vào tài khoản
3. Thử lại

### Lỗi: "Symbol XAUUSD không tồn tại"

**Nguyên nhân**: Symbol không đúng hoặc chưa được enable

**Giải pháp**:
1. Kiểm tra symbol trong MT5 Market Watch
2. Thử các symbol khác: `XAUUSD`, `XAUUSDm`, `GOLD`
3. Enable symbol trong Market Watch

### Lỗi: "MT5 login failed"

**Nguyên nhân**: Thông tin đăng nhập sai hoặc server không đúng

**Giải pháp**:
1. Kiểm tra lại login, password, server
2. Server name có thể là: `ExnessReal-MT5`, `ExnessDemo-MT5`, v.v.
3. Thử đăng nhập thủ công trong MT5 để xác nhận

### Bot không đặt lệnh

**Nguyên nhân**: Không đủ tín hiệu hoặc đã có vị thế mở

**Giải pháp**:
- Đây là hành vi bình thường nếu không có đủ tín hiệu (strength < 2)
- Kiểm tra log để xem lý do
- Có thể giảm ngưỡng `strength >= 2` xuống `>= 1` nếu muốn bot tích cực hơn

---

## 📈 Tối ưu hóa

### Điều chỉnh theo style giao dịch

**Conservative (Bảo thủ)**:
```python
if analysis['signal'] == 'BUY' and analysis['strength'] >= 3:  # Yêu cầu 3+ tín hiệu
```

**Aggressive (Tích cực)**:
```python
if analysis['signal'] == 'BUY' and analysis['strength'] >= 1:  # Chỉ cần 1 tín hiệu
```

### Điều chỉnh timeframe

Mặc định bot dùng H1 (1 giờ). Có thể thay đổi:

```python
df = self.get_historical_data(timeframe=mt5.TIMEFRAME_M15, bars=200)  # 15 phút
df = self.get_historical_data(timeframe=mt5.TIMEFRAME_H4, bars=200)    # 4 giờ
```

---

## 📞 Hỗ trợ

Nếu gặp vấn đề, kiểm tra:
1. File log: `logs/gold_trader.log`
2. MT5 terminal logs
3. Kết nối internet và MT5

---

**Chúc bạn giao dịch thành công! 🚀**

> ⚠️ **Nhắc lại**: Luôn test trên demo trước và quản lý rủi ro cẩn thận!

