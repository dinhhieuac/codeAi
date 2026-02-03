
# 🟡 QUY TẮC GIAO DỊCH XAU/USD (GOLD/USD)

## ⚙️ I. THÔNG SỐ CƠ BẢN
| Mục | Giá trị khuyến nghị |
|-----|---------------------|
| Khung thời gian chính | M15 / H1 |
| Risk mỗi lệnh | 0.5–1% balance |
| Max lệnh cùng lúc | 2 |
| Max lệnh/ngày | 10 |
| Khoảng cách tối thiểu giữa 2 lệnh cùng chiều | 45 phút |
| Khoảng cách ngược chiều | 20 phút |

---

## 💰 II. QUẢN LÝ VỐN & RỦI RO

### 1. Giới hạn tổng thể:
- **Max loss/ngày:** 5%
- **Max drawdown:** 15%
- **Max consecutive losses:** 4
- **Tạm ngưng giao dịch khi:**
  - Equity < 85% Balance
  - Drawdown trong ngày > 5%
  - Winrate 10 lệnh gần nhất < 40%

### 2. Lot size linh động:
- Giảm **50% lot size sau 3 lệnh thua liên tiếp**
- Tăng **+25% lot size sau 2 lệnh thắng liên tiếp**, nhưng không vượt 1.5× lot ban đầu

---

## 🎯 III. STOP LOSS / TAKE PROFIT (SL/TP)

### 1. Theo ATR (biến động thật):
```python
ATR = average_true_range(14)
TP = 1.5 * ATR
SL = 1.0 * ATR
```
→ RR ≈ **1.5 : 1**, tự động điều chỉnh theo biến động thực tế.

### 2. Quy tắc linh hoạt:
- Nếu giá đang ở **vùng kháng cự/ hỗ trợ mạnh**, giảm TP còn **1.0×ATR**, SL **0.8×ATR**
- Nếu **xác nhận trend mạnh (MA20 > MA50 > MA200)**, cho phép kéo TP lên **2×ATR**, giữ SL **1×ATR**

---

## 🕓 IV. QUY TẮC THỜI GIAN GIAO DỊCH

### 1. Giờ “ngon ăn” (High-probability):
| Phiên | Giờ VN | Ghi chú |
|--------|---------|---------|
| Phiên Âu | 14:00–17:30 | Vàng bắt đầu biến động mạnh |
| Phiên Mỹ | 19:30–23:30 | Giao dịch chính, nhiều cơ hội nhất |

### 2. Giờ tránh:
- ❌ **14:30–16:30** – Biến động hỗn loạn trước phiên Mỹ
- ❌ **20:30–21:30** – Tin tức Mỹ công bố (Nonfarm, CPI, FOMC…)
- ❌ Không trade **5 phút trước/sau tin mạnh**

---

## 🧭 V. PHÂN TÍCH KỸ THUẬT

### Kết hợp 5 nhóm chỉ báo chính:
| Nhóm | Dấu hiệu BUY | Dấu hiệu SELL |
|------|---------------|----------------|
| RSI | RSI < 30 (quá bán) + bật lên | RSI > 70 (quá mua) + đảo chiều |
| MACD | Cross lên, histogram dương | Cross xuống, histogram âm |
| MA (EMA20, 50, 200) | Giá > MA20 > MA50 | Giá < MA20 < MA50 |
| Bollinger Bands | Giá chạm band dưới, RSI xác nhận | Giá chạm band trên, RSI xác nhận |
| Volume + Momentum | Volume tăng theo hướng nến xác nhận | Volume giảm khi nến yếu |

---

## 🧠 VI. RULE THÔNG MINH (BẢO VỆ LỢI NHUẬN)

1. **Trailing Stop động:**
   - Kích hoạt khi lợi nhuận > 1×ATR
   - Theo sau 50% lợi nhuận hiện tại

2. **Auto Breakeven:**
   - Khi lợi nhuận đạt 1.2×SL → dời SL về điểm hòa vốn

3. **Không mở thêm lệnh khi có vị thế âm > 2%**

4. **Sau chuỗi thắng > 5 lệnh**, nghỉ 30 phút (tránh overconfidence).

---

## 📊 VII. THEO DÕI HIỆU SUẤT
| Metric | Ngưỡng cảnh báo |
|---------|----------------|
| Winrate (20 lệnh gần nhất) | < 45% → giảm lot |
| RR trung bình | < 1.2 → cần tối ưu SL/TP |
| Max drawdown | > 15% → dừng hệ thống |
| Profit factor | < 1.3 → tạm ngưng 1 ngày |
