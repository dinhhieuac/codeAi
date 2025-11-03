# 📱 Hướng Dẫn Cấu Hình Telegram Notifications

Bot sẽ tự động gửi thông báo qua Telegram khi mở lệnh mới.

---

## 📋 Bước 1: Tạo Telegram Bot

1. Mở Telegram, tìm kiếm **@BotFather**
2. Gửi lệnh: `/newbot`
3. Đặt tên cho bot (ví dụ: "My Trading Bot")
4. Đặt username cho bot (phải kết thúc bằng "bot", ví dụ: "my_trading_bot")
5. BotFather sẽ trả về **Bot Token** (dạng: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
6. **Lưu lại Token này** - dùng để cấu hình

---

## 📋 Bước 2: Lấy Chat ID

### Cách 1: Gửi tin nhắn cho bot cá nhân

1. Tìm bot vừa tạo (username bạn đã đặt)
2. Nhấn **Start** hoặc gửi bất kỳ tin nhắn nào cho bot
3. Truy cập URL trong trình duyệt:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
   Thay `<YOUR_BOT_TOKEN>` bằng token bạn nhận được từ BotFather
4. Tìm trong JSON response, có dòng `"chat":{"id":123456789}`
5. **Số `123456789` là Chat ID của bạn**

### Cách 2: Dùng bot @userinfobot

1. Tìm kiếm bot **@userinfobot** trên Telegram
2. Gửi `/start` cho bot này
3. Bot sẽ trả về Chat ID của bạn

### Cách 3: Lấy Chat ID của Group

1. Thêm bot vào group/channel
2. Đặt bot làm admin (nếu là channel)
3. Gửi tin nhắn bất kỳ trong group
4. Truy cập URL: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
5. Tìm `"chat":{"id":-1001234567890}` (số âm = group/channel)

---

## 📋 Bước 3: Cấu Hình trong configbtc.py

Mở file `configbtc.py` và điền thông tin:

```python
# ============================================
# Telegram Notifications Settings
# ============================================
USE_TELEGRAM_NOTIFICATIONS = True  # True để bật thông báo

TELEGRAM_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"  # Token từ BotFather

TELEGRAM_CHAT_ID = "123456789"  # Chat ID của bạn (hoặc group ID)

TELEGRAM_SEND_ON_ORDER_OPEN = True   # Gửi thông báo khi mở lệnh
TELEGRAM_SEND_ON_ORDER_CLOSE = False # Gửi thông báo khi đóng lệnh
```

---

## 📋 Bước 4: Cài Đặt Dependencies

```bash
pip install requests
```

Hoặc:

```bash
pip install -r requirements.txt
```

---

## 📋 Bước 5: Test

1. Chạy bot: `python3 examples/btc.py`
2. Khi bot mở lệnh, bạn sẽ nhận được thông báo trên Telegram

---

## 📨 Format Thông Báo

Bot sẽ gửi thông báo với format:

```
🟢 LỆNH MỚI: BUY BTCUSD

📊 Thông tin lệnh:
   • Ticket: 12345678
   • Volume: 0.01 lots
   • Giá vào: 80000.00
   • SL: 78000.00 (2000 points)
   • TP: 83000.00 (3000 points)
   • Risk: 800.00 (1.0%)

📈 Thông tin tài khoản:
   • Equity: 80000.00
   • Balance: 80000.00
   • Lệnh hôm nay: 1/300

💡 Lý do:
RSI oversold (28.50), MACD bullish momentum, Strong Uptrend...
```

---

## ⚠️ Lưu Ý

1. **Bảo mật**: Không commit `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` vào git
2. **Tắt thông báo**: Đặt `USE_TELEGRAM_NOTIFICATIONS = False` nếu không muốn dùng
3. **Error handling**: Bot sẽ tiếp tục chạy ngay cả khi gửi Telegram thất bại (chỉ log warning)
4. **Timeout**: Request timeout = 5 giây để tránh bot bị block

---

## 🔧 Troubleshooting

### Không nhận được thông báo?

1. ✅ Kiểm tra `USE_TELEGRAM_NOTIFICATIONS = True`
2. ✅ Kiểm tra `TELEGRAM_BOT_TOKEN` có đúng không
3. ✅ Kiểm tra `TELEGRAM_CHAT_ID` có đúng không
4. ✅ Gửi `/start` cho bot trước
5. ✅ Xem log file để kiểm tra lỗi: `tail -f logs/auto_trader_v3.log`

### Lỗi "Bad Request" hoặc "Unauthorized"?

- Bot Token sai → Kiểm tra lại token từ BotFather
- Chat ID sai → Lấy lại Chat ID theo hướng dẫn bước 2

---

## 📝 Ví Dụ Cấu Hình

```python
# configbtc.py
USE_TELEGRAM_NOTIFICATIONS = True
TELEGRAM_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
TELEGRAM_CHAT_ID = "987654321"
TELEGRAM_SEND_ON_ORDER_OPEN = True
TELEGRAM_SEND_ON_ORDER_CLOSE = False
```

---

**Chúc bạn trade thành công! 🚀**

