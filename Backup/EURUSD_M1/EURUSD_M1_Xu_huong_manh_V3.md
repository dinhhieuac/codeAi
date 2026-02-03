# 📘 BOT TRADING SPEC  
## BUY & SELL LOGIC – TRÁNH VÀO LỆNH SAI (TECHNICAL DOCUMENT)

---

## I. MỤC TIÊU
- Loại bỏ giao dịch trong **sóng hồi nhỏ**
- Tránh BUY/SELL trước **liquidity sweep**
- Chỉ giao dịch khi có **BOS + Displacement**
- Hạn chế overtrading và trap trade

---

## II. NGUYÊN NHÂN GỐC (ROOT CAUSE)

❌ Bot thua khi:
- Dùng Fibonacci trên **pullback wave**
- Giao dịch trong **vùng nén (chop)**
- Phá cấu trúc nội bộ (internal BOS)
- Không phân biệt trạng thái thanh khoản

➡️ Indicator đúng – **Context sai**

---

# =========================
# 🔵 BUY SIDE SPEC
# =========================

## III. BUY – NGUYÊN TẮC CỐT LÕI

- BUY **chỉ sau khi quét thanh khoản phía dưới**
- BUY khi có **External BOS + Displacement**
- CẤM BUY trước sweep hoặc trong chop

---

## IV. BUY UPDATE 1 — LIQUIDITY SWEEP (BẮT BUỘC)

```
IF current_low < previous_swing_low - buffer
AND lower_wick >= 1.5 × ATR
AND close > open
→ BUY_SWEEP_CONFIRMED = TRUE
```

❌ Không sweep → NO BUY

---

## V. BUY UPDATE 2 — DISPLACEMENT CANDLE

```
IF breakout_body >= 1.2 × ATR
AND close > previous_range_high
→ DISPLACEMENT = TRUE
```

---

## VI. BUY UPDATE 3 — EXTERNAL BOS FILTER

```
IF close > last_external_swing_high
→ BOS_UP_CONFIRMED
ELSE → INTERNAL BOS → SKIP
```

---

## VII. BUY UPDATE 4 — LIQUIDITY BELOW FILTER

```
IF distance(entry, nearest_low) < 2.5 pips
→ WAIT (chưa BUY)
```

---

## VIII. BUY UPDATE 5 — MULTI TIMEFRAME CONTEXT

```
IF H1_bias = SELL
→ Risk = 0.5R
→ TP ≤ 2R
```

---

## IX. BUY UPDATE 6 — STOP LOSS LOGIC

```
SL = min(
  structure_low - buffer,
  entry - 3 × ATR
)
```

---

## X. BUY CHECKLIST

```
[ ] Sweep dưới
[ ] Displacement
[ ] External BOS
[ ] Không liquidity dưới
[ ] Không chop
[ ] SL dưới cấu trúc
```

---

# =========================
# 🔴 SELL SIDE SPEC
# =========================

## XI. SELL – NGUYÊN TẮC CỐT LÕI

- SELL **chỉ sau khi quét thanh khoản phía trên**
- SELL khi có **External BOS DOWN**
- CẤM SELL trong sóng hồi nhỏ

---

## XII. SELL UPDATE 1 — LIQUIDITY SWEEP

```
IF current_high > previous_swing_high + buffer
AND upper_wick >= 1.5 × ATR
AND close < open
→ SELL_SWEEP_CONFIRMED = TRUE
```

---

## XIII. SELL UPDATE 2 — DISPLACEMENT CANDLE

```
IF breakout_body >= 1.2 × ATR
AND close < previous_range_low
→ DISPLACEMENT = TRUE
```

---

## XIV. SELL UPDATE 3 — EXTERNAL BOS FILTER

```
IF close < last_external_swing_low
→ BOS_DOWN_CONFIRMED
ELSE → INTERNAL BOS → SKIP
```

---

## XV. SELL UPDATE 4 — LIQUIDITY ABOVE FILTER

```
IF distance(entry, nearest_high) < 2.5 pips
→ WAIT
```

---

## XVI. SELL UPDATE 5 — MULTI TIMEFRAME CONTEXT

```
IF H1_bias = BUY
→ Risk = 0.5R
→ TP ≤ 2R
```

---

## XVII. SELL UPDATE 6 — STOP LOSS LOGIC

```
SL = max(
  structure_high + buffer,
  entry + 3 × ATR
)
```

---

## XVIII. SELL CHECKLIST

```
[ ] Sweep trên
[ ] Displacement
[ ] External BOS
[ ] Không liquidity trên
[ ] Không chop
[ ] SL trên cấu trúc
```

---

## XIX. CHOP / RANGE FILTER (CHUNG)

```
IF last 10 candles:
- body_avg < 0.5 × ATR
- overlap > 70%
→ MARKET = CHOP
→ NO TRADE
```

---

## XX. ANTI OVERTRADING LOCK

```
IF trade_result = LOSS
→ Lock trading 20–30 candles
```

---

## XXI. KẾT LUẬN

🎯 Bot chỉ giao dịch khi **Liquidity → Structure → Momentum** đồng thuận  
🚫 Không giao dịch khi market chưa lấy thanh khoản
