# 📊 EUR/USD – M1 SCALPING STRATEGY (A+)

---

## 🟢 TRƯỜNG HỢP BUY (M1)

### 1️⃣ Điều kiện Xu hướng
- EMA50 > EMA200
- Giá hiện tại > EMA50

---

### 2️⃣ Điều kiện RSI (14) – Pullback theo trend
- RSI trước đó ≥ 70 (đã quá mua → có sóng tăng thật)
- RSI hiện tại ∈ [40 – 50]
- RSI KHÔNG < 32
- RSI quay đầu lên  
  → RSI hiện tại > RSI nến trước

---

### 3️⃣ Điều kiện Biến động
- ATR(14) ≥ 0.00011

---

### 4️⃣ Điều kiện Nến Entry
- Nến **Bullish Engulfing**
- Close nến entry > EMA50

---

### 5️⃣ Điều kiện Volume
- Volume nến entry ≥ Volume trung bình 10 nến trước

---

### 6️⃣ Vào lệnh
- BUY khi nến Bullish Engulfing đóng cửa

**Stop Loss**
- SL = 2 × ATR + 6 points

**Take Profit**
- TP = 2 × SL  
- RR = 1 : 2

---

## 🔴 TRƯỜNG HỢP SELL (M1)

### 1️⃣ Điều kiện Xu hướng
- EMA50 < EMA200
- Giá hiện tại < EMA50

---

### 2️⃣ Điều kiện RSI (14)
- RSI trước đó ≤ 30 (đã quá bán thật)
- RSI hiện tại ∈ [50 – 60]
- RSI KHÔNG > 68
- RSI quay đầu xuống  
  → RSI hiện tại < RSI nến trước

---

### 3️⃣ Điều kiện Biến động
- ATR(14) ≥ 0.00011

---

### 4️⃣ Điều kiện Nến Entry
- Nến **Bearish Engulfing**
- Close nến entry < EMA50

---

### 5️⃣ Điều kiện Volume
- Volume nến entry ≥ Volume trung bình 10 nến trước

---

### 6️⃣ Vào lệnh
- SELL khi nến Bearish Engulfing đóng cửa

**Stop Loss**
- SL = 2 × ATR + 6 points

**Take Profit**
- TP = 2 × SL  
- RR = 1 : 2

---

## ⚠️ RULE BẮT BUỘC
- Không trade phiên Á
- Không trade 5 phút trước & sau tin đỏ
- Thua 2 lệnh liên tiếp → NGHỈ
- Không dời SL thủ công
- Không vào lệnh nếu ATR < 0.00011

---

## ✅ GHI CHÚ
- Chiến lược: Pullback Momentum theo Trend
- Khung thời gian: M1
- Sản phẩm: EUR/USD
- Phù hợp: Đánh tay & BOT
