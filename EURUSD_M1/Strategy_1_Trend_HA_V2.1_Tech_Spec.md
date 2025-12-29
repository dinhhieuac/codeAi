# 📘 TECH SPEC – BOT UPDATE V2 → V2.1

**Strategy:** Strategy_1_Trend_HA  
**Version:** V2.1  
**Mục tiêu:** Ngăn bot vào lệnh khi điều kiện lõi chưa đạt (Hard Gate)

---

## 1️⃣ CORE PRINCIPLE

> ❗ **Fail 1 điều kiện lõi ⇒ NO TRADE**  
> ❌ Không score / không weight / không soft logic

---

## 2️⃣ HARD GATES (CHECK TRƯỚC ENTRY)

### 2.1 Strong Trend – M5 (BẮT BUỘC)

**BUY**
- EMA50 > EMA200  
- ADX(14) ≥ 20  
- |slope(EMA50)| ≥ `minSlope`

**SELL**
- EMA50 < EMA200  
- ADX(14) ≥ 20  
- |slope(EMA50)| ≥ `minSlope`

❌ EMA đi ngang / chồng → **NO TRADE**

---

### 2.2 Fresh Breakout + Confirmation

#### Breakout Candle (C0)
- Phá high/low gần nhất (chưa bị test)
- Body ≥ 60% range
- Wick ngược ≤ 30%
- Volume ≥ 1.3 × MA(volume, 20)

#### Confirm Candle (C1)
- Không đóng lại trong range cũ
- Không phá ngược breakout
- Volume ≥ 1.2 × MA(volume, 20)

❌ Không có C1 → **RESET STATE**

---

### 2.3 Stop Loss Size Limit

```
SL_distance ≤ min(1.2 × ATR(14), last_swing_range)
```

❌ SL lớn hơn → **NO TRADE**

---

### 2.4 Session Filter

- Asian Session → **NO TRADE**
- Ngoại lệ: XAU (tuỳ cấu hình)

---

## 3️⃣ STATE MACHINE (BẮT BUỘC)

```
WAIT → CONFIRM → ENTRY
```

- `WAIT`: chờ breakout hợp lệ
- `CONFIRM`: chờ nến xác nhận C1
- `ENTRY`: chỉ vào lệnh tại state này

❌ Không được entry tại WAIT hoặc CONFIRM

---

## 4️⃣ SOFT CONFIRM (CHECK SAU HARD GATE)

- RSI:
  - BUY > 55
  - SELL < 45
  - RSI slope đúng hướng
- HA candle đúng màu
- Không doji / indecision

❌ Soft fail → **SKIP ENTRY** (không invalidate setup)

---

## 5️⃣ TRADE MANAGEMENT

### 5.1 Exit Rule

- Chỉ cho phép:
  - Take Profit
  - Stop Loss

❌ Disable manual / script close

---

### 5.2 Consecutive Loss Guard

```
loss_streak ≥ 2
→ cooldown 30–60 phút
```

---

## 6️⃣ LOGGING (BẮT BUỘC)

Mỗi lần attempt entry phải log:

```json
{
  "state": "WAIT | CONFIRM | ENTRY",
  "strong_trend": true,
  "fresh_breakout": true,
  "confirm_candle": true,
  "SL_distance": 0,
  "ATR": 0,
  "decision": "ENTER | SKIP",
  "skip_reason": "trend | breakout | SL | session"
}
```

---

## 7️⃣ KPI ĐÁNH GIÁ SAU UPDATE

| Metric | Target |
|------|--------|
| Manual close | 0% |
| SL trung bình | ↓ ≥ 50% |
| Fail M5 trend | < 20% |
| Tổng số lệnh | ↓ 40–60% |

---

## 8️⃣ UPDATE PRIORITY

| Priority | Item |
|--------|------|
| 🔴 P0 | Hard Gate logic |
| 🔴 P0 | State Machine |
| 🔴 P0 | SL size limiter |
| 🟡 P1 | Strong trend slope |
| 🟡 P1 | Disable manual close |
| 🟢 P2 | Loss streak & session filter |

---

## 9️⃣ KẾT LUẬN

- Không thêm indicator
- Không ML / AI
- Không tuning RSI thêm
- **Chỉ siết quyền ENTRY**

> Ít lệnh hơn – nhưng chất lượng cao hơn
