# 📋 ĐIỀU KIỆN VÀO LỆNH - STRATEGY 1 TREND HA V3

## 🎯 TỔNG QUAN
Strategy 1 Trend HA V3 sử dụng hệ thống filter nhiều lớp để đảm bảo chỉ vào lệnh khi market có xu hướng rõ ràng và điều kiện lý tưởng.

---

## ✅ ĐIỀU KIỆN BẮT BUỘC (PHẢI ĐẠT TẤT CẢ)

### 1. 🔒 **Trading Session Check**
- ✅ **Không trong blocked hours:**
  - ❌ 11:00 - 12:00 (Giờ nghỉ phiên sáng)
  - ❌ 18:00 - 19:00 (Giờ giao phiên Âu - Mỹ)
- ✅ **Trong allowed session** (mặc định: ALL - tất cả giờ)

### 2. 📊 **Position Management**
- ✅ **Số lượng positions hiện tại < max_positions** (mặc định: 1)
- ✅ **Không có trade trong 60 giây gần nhất** (Spam filter)

### 3. 📈 **Data Availability**
- ✅ **Có đủ dữ liệu M1, M5, H1** (200 candles mỗi timeframe)

---

## 📊 ĐIỀU KIỆN TREND & MOMENTUM

### 4. 📈 **M5 Trend (EMA 200)**
- ✅ **BUY:** Close M5 > EMA 200 M5 → Trend = BULLISH
- ✅ **SELL:** Close M5 < EMA 200 M5 → Trend = BEARISH

### 5. 📈 **H1 Trend Confirmation (EMA 100)** - **BẮT BUỘC V3**
- ✅ **H1 Trend phải ĐỒNG NHẤT với M5 Trend:**
  - BUY: H1 Trend = BULLISH **VÀ** M5 Trend = BULLISH
  - SELL: H1 Trend = BEARISH **VÀ** M5 Trend = BEARISH
- ❌ Nếu H1 ≠ M5 → **BỎ TRADE**

### 6. 📊 **ADX Filter (M5)** - **V3: Tăng threshold**
- ✅ **ADX > 25** (V3: tăng từ 20 lên 25)
- ✅ **Period:** 14
- ❌ ADX ≤ 25 → **BỎ TRADE** (No strong trend)

### 7. 📊 **ATR M1 Volatility Filter** - **V3: MỚI**
- ✅ **ATR M1 < 15.0** (XAUUSD)
- ✅ **Period:** 14
- ❌ ATR M1 ≥ 15.0 → **BỎ TRADE** (Market quá volatile)

---

## 🕯️ ĐIỀU KIỆN HEIKEN ASHI & CHANNEL

### 8. 🕯️ **Heiken Ashi Candle Color**
- ✅ **BUY:** HA Close > HA Open (Green candle)
- ✅ **SELL:** HA Close < HA Open (Red candle)

### 9. 📊 **Channel Breakout (SMA55 High/Low)**
- ✅ **BUY:** HA Close > SMA55 High (Above channel)
- ✅ **SELL:** HA Close < SMA55 Low (Below channel)

### 10. 🆕 **Fresh Breakout Check**
- ✅ **BUY:** Previous HA Close ≤ Previous SMA55 High
- ✅ **SELL:** Previous HA Close ≥ Previous SMA55 Low
- ❌ Nếu không phải fresh breakout → **BỎ TRADE**

### 11. 🕯️ **Solid Candle (Not Doji)**
- ✅ **Body > 20% của range** (HA candle)
- ❌ Doji detected → **BỎ TRADE** (Indecision)

---

## 📊 ĐIỀU KIỆN RSI

### 12. 📊 **RSI Filter** - **V3: Điều chỉnh threshold**
- ✅ **BUY:** RSI > 50 (V3: giảm từ 55 xuống 50)
- ✅ **SELL:** RSI < 50 (V3: giữ nguyên 50)
- ✅ **Period:** 14
- ❌ RSI không đạt threshold → **BỎ TRADE**

---

## 📋 TÓM TẮT ĐIỀU KIỆN THEO LOẠI LỆNH

### 🟢 **BUY SIGNAL - Tất cả điều kiện phải đạt:**

1. ✅ Trading Session: Không trong blocked hours
2. ✅ Position: < max_positions, không trade trong 60s
3. ✅ Data: Có đủ M1, M5, H1 data
4. ✅ M5 Trend: BULLISH (Close > EMA 200)
5. ✅ H1 Trend: BULLISH **VÀ** = M5 Trend (BẮT BUỘC)
6. ✅ ADX: > 25 (Strong trend)
7. ✅ ATR M1: < 15.0 (Không quá volatile)
8. ✅ HA Candle: Green (Close > Open)
9. ✅ Above Channel: HA Close > SMA55 High
10. ✅ Fresh Breakout: Prev HA Close ≤ Prev SMA55 High
11. ✅ Solid Candle: Not Doji (Body > 20% range)
12. ✅ RSI: > 50

### 🔴 **SELL SIGNAL - Tất cả điều kiện phải đạt:**

1. ✅ Trading Session: Không trong blocked hours
2. ✅ Position: < max_positions, không trade trong 60s
3. ✅ Data: Có đủ M1, M5, H1 data
4. ✅ M5 Trend: BEARISH (Close < EMA 200)
5. ✅ H1 Trend: BEARISH **VÀ** = M5 Trend (BẮT BUỘC)
6. ✅ ADX: > 25 (Strong trend)
7. ✅ ATR M1: < 15.0 (Không quá volatile)
8. ✅ HA Candle: Red (Close < Open)
9. ✅ Below Channel: HA Close < SMA55 Low
10. ✅ Fresh Breakout: Prev HA Close ≥ Prev SMA55 Low
11. ✅ Solid Candle: Not Doji (Body > 20% range)
12. ✅ RSI: < 50

---

## ⚙️ CẤU HÌNH MẶC ĐỊNH (config_1_v3.json)

```json
{
  "parameters": {
    "sl_mode": "auto_m5",
    "reward_ratio": 1.5,
    "rsi_buy_threshold": 50,        // V3: Giảm từ 55
    "rsi_sell_threshold": 50,
    "rsi_high_threshold": 60,       // Dynamic R:R trigger
    "high_rsi_reward_ratio": 1.8,   // R:R khi RSI > 60
    "adx_period": 14,
    "adx_min_threshold": 25,        // V3: Tăng từ 20
    "atr_period": 14,
    "atr_max_threshold": 15.0,      // V3: MỚI - Filter volatility
    "sl_buffer_multiplier": 0.25,   // V3: 25% ATR cho SL buffer
    "h1_ema_period": 100,
    "h1_trend_confirmation_required": true,  // V3: BẮT BUỘC
    "blocked_hours": ["11:00-12:00", "18:00-19:00"]
  }
}
```

---

## 🎯 V3 IMPROVEMENTS (So với V2)

### ✅ **Cải thiện Win Rate:**
1. **RSI Filter:** BUY threshold giảm từ 55 → 50
2. **H1 Trend:** BẮT BUỘC đồng nhất với M5 (trước: optional)
3. **ADX Filter:** Tăng từ ≥ 20 → > 25

### ✅ **Giảm Loss Rate:**
1. **ATR Filter:** Chỉ trade khi ATR M1 < 15.0 (tránh volatile market)
2. **Blocked Hours:** Chặn 11:00-12:00 và 18:00-19:00

### ✅ **Trade Management:**
1. **SL Buffer:** Nới rộng thêm 25% ATR M1
2. **Dynamic R:R:** RSI > 60 → R:R = 1.8, RSI ≤ 60 → R:R = 1.5
3. **Break-even:** Khi giá đi 50% đến TP (sử dụng manage_position)

---

## 📊 THỨ TỰ KIỂM TRA (Execution Flow)

```
1. Check Trading Session → ❌ Blocked hours? → BỎ
2. Check Max Positions → ❌ Đủ positions? → BỎ
3. Get Data (M1, M5, H1) → ❌ Không có data? → BỎ
4. Calculate M5 Trend (EMA 200) → Xác định BULLISH/BEARISH
5. Calculate H1 Trend (EMA 100) → ❌ H1 ≠ M5? → BỎ
6. Calculate ADX (M5) → ❌ ADX ≤ 25? → BỎ
7. Calculate ATR (M1) → ❌ ATR ≥ 15.0? → BỎ
8. Calculate HA & Indicators
9. Check HA Candle Color → ❌ Sai màu? → BỎ
10. Check Channel Breakout → ❌ Không breakout? → BỎ
11. Check Fresh Breakout → ❌ Không fresh? → BỎ
12. Check Solid Candle → ❌ Doji? → BỎ
13. Check RSI → ❌ Không đạt threshold? → BỎ
14. ✅ TẤT CẢ ĐẠT → VÀO LỆNH
```

---

## 💡 LƯU Ý

- **Tất cả điều kiện phải đạt đồng thời** - Nếu 1 điều kiện fail → BỎ TRADE
- **H1 Trend confirmation là BẮT BUỘC** - Không thể disable trong V3
- **ATR Filter mới** - Giúp tránh trade trong market quá volatile
- **Dynamic R:R** - Tự động tăng R:R khi RSI mạnh (RSI > 60)
- **Spam Filter** - Tự động chặn nếu đã trade trong 60s gần nhất

---

**Version:** V3  
**Last Updated:** 2026-02-02  
**Strategy:** Strategy_1_Trend_HA_V3
