# Hướng Dẫn Sử Dụng: utils_scalp_sideway.py

## 📋 Tổng Quan

File `utils_scalp_sideway.py` chứa các utility functions cho chiến lược **Scalp Sideway**, hỗ trợ nhiều cặp giao dịch: **EURUSD, XAUUSD, BTCUSD, ETHUSD, AUDUSD**, etc.

Dựa trên document: `Bot-Scalp-sideway_v1.md`

---

## 🔧 Các Functions Chính

### 1. **Indicator Calculations**

#### `calculate_ema(series, span)`
Tính Exponential Moving Average (EMA)

```python
df_m1['ema9'] = calculate_ema(df_m1['close'], 9)
df_m5['ema21'] = calculate_ema(df_m5['close'], 21)
```

#### `calculate_atr(df, period=14)`
Tính Average True Range (ATR)

```python
df_m1['atr'] = calculate_atr(df_m1, 14)
df_m5['atr'] = calculate_atr(df_m5, 14)
```

#### `calculate_body_size(candle)`
Tính body size của nến

```python
body = calculate_body_size(df_m1.iloc[-1])
```

---

### 2. **Supply/Demand Zone Detection (M5)**

#### `check_supply_m5(df_m5, current_idx=-1)`
Xác định Supply zone trên M5

**Điều kiện:**
- `High_M5_current < High_M5_prev`
- `|High_M5_prev - High_M5_current| < 0.4 × ATR_M5`

**Ví dụ:**
```python
is_supply, supply_price, msg = check_supply_m5(df_m5, current_idx=-1)
if is_supply:
    print(f"Supply zone tại: {supply_price:.5f}")
```

#### `check_demand_m5(df_m5, current_idx=-1)`
Xác định Demand zone trên M5

**Điều kiện:**
- `Low_M5_current > Low_M5_prev`
- `|Low_M5_current - Low_M5_prev| < 0.4 × ATR_M5`

**Ví dụ:**
```python
is_demand, demand_price, msg = check_demand_m5(df_m5, current_idx=-1)
if is_demand:
    print(f"Demand zone tại: {demand_price:.5f}")
```

---

### 3. **Bad Market Conditions Filter**

#### `check_atr_ratio(df_m1, current_idx=-1, lookback=20)`
Kiểm tra ATR ratio để lọc thị trường xấu

**Điều kiện:**
- `ATR_ratio > 1.5` → Tạm dừng trade 40 phút
- `ATR_ratio < 0.5` → Không trade

**Ví dụ:**
```python
is_valid, atr_ratio, msg = check_atr_ratio(df_m1, current_idx=-1)
if not is_valid:
    print(f"Thị trường xấu: {msg}")
```

#### `check_atr_increasing(df_m1, current_idx=-1, consecutive=3)`
Kiểm tra ATR tăng liên tiếp

**Điều kiện:**
- ATR_M1 tăng liên tiếp 3 nến
- ATR_M1 > ATR_M1_avg(20)
- → Dừng trade 40 phút

**Ví dụ:**
```python
should_pause, msg = check_atr_increasing(df_m1, current_idx=-1)
if should_pause:
    print(f"Dừng trade 40 phút: {msg}")
```

#### `check_large_body(df_m1, current_idx=-1, multiplier=1.2)`
Kiểm tra body size lớn

**Điều kiện:**
- `BodySize(M1) > 1.2 × ATR_M1` → Tạm dừng trade 15 phút

**Ví dụ:**
```python
should_pause, msg = check_large_body(df_m1, current_idx=-1)
if should_pause:
    print(f"Tạm dừng trade 15 phút: {msg}")
```

#### `check_bad_market_conditions(df_m1, current_idx=-1)`
Tổng hợp kiểm tra tất cả điều kiện thị trường xấu

**Ví dụ:**
```python
is_valid, conditions, msg = check_bad_market_conditions(df_m1, current_idx=-1)
if not is_valid:
    print(f"Thị trường xấu: {msg}")
    # Xem chi tiết từng điều kiện
    print(f"ATR Ratio: {conditions['atr_ratio']}")
    print(f"ATR Increasing: {conditions['atr_increasing']}")
    print(f"Large Body: {conditions['large_body']}")
```

---

### 4. **Sideway Context (M5)**

#### `check_sideway_context(df_m5, current_idx=-1, ema_period=21, lookback=3)`
Kiểm tra bối cảnh Sideway trên M5

**Điều kiện:**
- `|EMA21_M5[i] - EMA21_M5[i-3]| < 0.2 × ATR_M5`
- `|Close_M5 - EMA21_M5| < 0.5 × ATR_M5`

**Ví dụ:**
```python
is_sideway, msg = check_sideway_context(df_m5, current_idx=-1)
if is_sideway:
    print(f"Bối cảnh Sideway hợp lệ: {msg}")
```

---

### 5. **Delta High/Low Calculation (M1)**

#### `calculate_delta_high(df_m1, current_idx=-1)`
Tính DeltaHigh cho SELL signal

**Công thức:** `DeltaHigh = High[i] - High[i-1]`

**Ví dụ:**
```python
delta_high, msg = calculate_delta_high(df_m1, current_idx=-1)
if delta_high is not None:
    print(f"DeltaHigh: {delta_high:.5f}")
```

#### `calculate_delta_low(df_m1, current_idx=-1)`
Tính DeltaLow cho BUY signal

**Công thức:** `DeltaLow = Low[i-1] - Low[i]`

**Ví dụ:**
```python
delta_low, msg = calculate_delta_low(df_m1, current_idx=-1)
if delta_low is not None:
    print(f"DeltaLow: {delta_low:.5f}")
```

#### `is_valid_delta_high(delta_high, atr_m1, threshold=0.3)`
Kiểm tra DeltaHigh hợp lệ

**Điều kiện hợp lệ:**
- `0 < DeltaHigh < 0.3 × ATR(M1)`

**Reset:**
- `DeltaHigh ≤ 0` → RESET
- `DeltaHigh ≥ 0.3 × ATR` → RESET

**Ví dụ:**
```python
atr_m1 = df_m1.iloc[-1]['atr']
is_valid, msg = is_valid_delta_high(delta_high, atr_m1, threshold=0.3)
if is_valid:
    print(f"DeltaHigh hợp lệ: {msg}")
```

#### `is_valid_delta_low(delta_low, atr_m1, threshold=0.3)`
Kiểm tra DeltaLow hợp lệ

**Điều kiện hợp lệ:**
- `0 < DeltaLow < 0.3 × ATR(M1)`

**Reset:**
- `DeltaLow ≤ 0` → RESET
- `DeltaLow >= 0.3 × ATR` → RESET

**Ví dụ:**
```python
atr_m1 = df_m1.iloc[-1]['atr']
is_valid, msg = is_valid_delta_low(delta_low, atr_m1, threshold=0.3)
if is_valid:
    print(f"DeltaLow hợp lệ: {msg}")
```

---

### 6. **Count Tracking**

#### `DeltaCountTracker(min_count=2)`
Class để theo dõi Count cho DeltaHigh/DeltaLow

**Ví dụ:**
```python
# Khởi tạo tracker
sell_count_tracker = DeltaCountTracker(min_count=2)
buy_count_tracker = DeltaCountTracker(min_count=2)

# Cập nhật Count
delta_high, _ = calculate_delta_high(df_m1, current_idx=-1)
atr_m1 = df_m1.iloc[-1]['atr']
is_valid, _ = is_valid_delta_high(delta_high, atr_m1)

count, is_triggered = sell_count_tracker.update(is_valid, current_idx=-1)
if is_triggered:
    print(f"SELL signal triggered! Count: {count}")
```

---

### 7. **Signal Conditions**

#### `check_sell_signal_condition(df_m1, supply_price, df_m5, current_idx=-1, buffer_multiplier=0.2)`
Kiểm tra điều kiện SELL signal

**Điều kiện:**
- `High_M1_current < High_M5_supply + 0.2 × ATR_M5`

**Ví dụ:**
```python
is_sell, msg = check_sell_signal_condition(
    df_m1, 
    supply_price, 
    df_m5, 
    current_idx=-1
)
if is_sell:
    print(f"SELL signal hợp lệ: {msg}")
```

#### `check_buy_signal_condition(df_m1, demand_price, df_m5, current_idx=-1, buffer_multiplier=0.2)`
Kiểm tra điều kiện BUY signal

**Điều kiện:**
- `Low_M1_current > Low_M5_demand + 0.2 × ATR_M5`

**Ví dụ:**
```python
is_buy, msg = check_buy_signal_condition(
    df_m1, 
    demand_price, 
    df_m5, 
    current_idx=-1
)
if is_buy:
    print(f"BUY signal hợp lệ: {msg}")
```

---

### 8. **Position Management**

#### `calculate_sl_tp(entry_price, signal_type, atr_m1, atr_multiplier=2.0, tp_multiplier=2.0, symbol_info=None)`
Tính SL và TP cho lệnh

**Công thức:**
- `SL = 2 × ATR = 1R`
- `TP1 = +1R` (chốt 50%, dời SL về BE)
- `TP2 = 2R`

**Ví dụ:**
```python
symbol_info = mt5.symbol_info(symbol)
sl, tp1, tp2, info = calculate_sl_tp(
    entry_price=1.10000,
    signal_type="BUY",
    atr_m1=0.00050,
    atr_multiplier=2.0,
    tp_multiplier=2.0,
    symbol_info=symbol_info
)
print(f"SL: {sl:.5f}, TP1: {tp1:.5f}, TP2: {tp2:.5f}")
```

#### `check_max_positions_per_zone(positions, zone_price, zone_type, max_positions=2, tolerance=0.0001)`
Kiểm tra số lượng lệnh tối đa trong một vùng Supply/Demand

**Ví dụ:**
```python
all_positions = mt5.positions_get(symbol=symbol)
is_valid, count, msg = check_max_positions_per_zone(
    positions=all_positions,
    zone_price=supply_price,
    zone_type="SUPPLY",
    max_positions=2
)
if not is_valid:
    print(f"Không thể mở thêm lệnh: {msg}")
```

#### `check_m5_candle_change(df_m5, last_trade_time, current_idx=-1)`
Kiểm tra M5 đã đổi nến chưa

**Lưu ý:** Nếu 1 lệnh SL → không vào lại cho đến khi M5 đổi nến

**Ví dụ:**
```python
last_trade_time = datetime(2025, 1, 6, 10, 30, 0)
has_changed, msg = check_m5_candle_change(df_m5, last_trade_time, current_idx=-1)
if has_changed:
    print(f"M5 đã đổi nến: {msg}")
    # Có thể vào lệnh mới
```

---

### 9. **Helper Functions**

#### `get_min_atr_threshold(symbol, config=None)`
Get minimum ATR threshold based on symbol type

**Hỗ trợ:**
- EURUSD, GBPUSD, USDJPY, AUDUSD: `0.00011`
- XAUUSD, GOLD: `0.1`
- BTCUSD, BTC: `50.0`
- ETHUSD, ETH: `5.0`

**Ví dụ:**
```python
min_atr = get_min_atr_threshold("XAUUSD")
print(f"Min ATR cho XAUUSD: {min_atr}")
```

---

## 📝 Ví Dụ Sử Dụng Hoàn Chỉnh

### **SELL Signal Flow:**

```python
import pandas as pd
import MetaTrader5 as mt5
from utils_scalp_sideway import *

# 1. Lấy dữ liệu
df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 300)
df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 100)

# 2. Tính indicators
df_m1['atr'] = calculate_atr(df_m1, 14)
df_m1['ema9'] = calculate_ema(df_m1['close'], 9)
df_m5['atr'] = calculate_atr(df_m5, 14)
df_m5['ema21'] = calculate_ema(df_m5['close'], 21)

# 3. Kiểm tra thị trường xấu
is_valid_market, conditions, msg = check_bad_market_conditions(df_m1, current_idx=-1)
if not is_valid_market:
    print(f"Thị trường xấu: {msg}")
    return

# 4. Kiểm tra bối cảnh Sideway
is_sideway, msg = check_sideway_context(df_m5, current_idx=-1)
if not is_sideway:
    print(f"Không phải sideway: {msg}")
    return

# 5. Xác định Supply zone
is_supply, supply_price, msg = check_supply_m5(df_m5, current_idx=-1)
if not is_supply:
    print(f"Không có Supply zone: {msg}")
    return

# 6. Kiểm tra điều kiện M1: Giá đóng cửa ≥ EMA9
current_candle = df_m1.iloc[-1]
if current_candle['close'] < current_candle['ema9']:
    print("Giá đóng cửa < EMA9 → Không tính DeltaHigh")
    return

# 7. Tính và kiểm tra DeltaHigh
delta_high, msg = calculate_delta_high(df_m1, current_idx=-1)
atr_m1 = current_candle['atr']
is_valid_delta, msg = is_valid_delta_high(delta_high, atr_m1, threshold=0.3)

# 8. Cập nhật Count
sell_count_tracker = DeltaCountTracker(min_count=2)
count, is_triggered = sell_count_tracker.update(is_valid_delta, current_idx=-1)

# 9. Kiểm tra điều kiện SELL signal
if is_triggered:
    is_sell, msg = check_sell_signal_condition(
        df_m1, 
        supply_price, 
        df_m5, 
        current_idx=-1
    )
    if is_sell:
        # Tính SL/TP
        symbol_info = mt5.symbol_info(symbol)
        entry_price = current_candle['close']
        sl, tp1, tp2, info = calculate_sl_tp(
            entry_price, 
            "SELL", 
            atr_m1, 
            symbol_info=symbol_info
        )
        print(f"🚀 SELL Signal: Entry={entry_price:.5f}, SL={sl:.5f}, TP1={tp1:.5f}, TP2={tp2:.5f}")
```

### **BUY Signal Flow:**

```python
# Tương tự SELL nhưng:
# 1. Kiểm tra Demand zone thay vì Supply
is_demand, demand_price, msg = check_demand_m5(df_m5, current_idx=-1)

# 2. Kiểm tra: Giá đóng cửa ≤ EMA9
if current_candle['close'] > current_candle['ema9']:
    print("Giá đóng cửa > EMA9 → Không tính DeltaLow")
    return

# 3. Tính DeltaLow thay vì DeltaHigh
delta_low, msg = calculate_delta_low(df_m1, current_idx=-1)
is_valid_delta, msg = is_valid_delta_low(delta_low, atr_m1, threshold=0.3)

# 4. Kiểm tra điều kiện BUY signal
is_buy, msg = check_buy_signal_condition(
    df_m1, 
    demand_price, 
    df_m5, 
    current_idx=-1
)
```

---

## ⚠️ Lưu Ý Quan Trọng

1. **Index Convention:**
   - `current_idx=-1` = nến cuối cùng (đang hình thành)
   - `current_idx=-2` = nến đã đóng gần nhất (nên dùng cho signal)

2. **DataFrame Requirements:**
   - DataFrame phải có columns: `open`, `high`, `low`, `close`
   - Cần tính ATR và EMA trước khi sử dụng các functions

3. **Multi-Symbol Support:**
   - Tất cả functions đều hỗ trợ nhiều cặp giao dịch
   - Sử dụng `get_min_atr_threshold()` để lấy threshold phù hợp

4. **Error Handling:**
   - Tất cả functions đều trả về tuple với message
   - Luôn kiểm tra `is_valid` hoặc `is_xxx` trước khi sử dụng kết quả

5. **Position Management:**
   - Max 2 lệnh / vùng Supply/Demand
   - Nếu 1 lệnh SL → không vào lại cho đến khi M5 đổi nến

---

## 🔄 Tích Hợp Vào Bot

Để tích hợp vào bot, import các functions:

```python
from utils_scalp_sideway import (
    calculate_ema,
    calculate_atr,
    check_supply_m5,
    check_demand_m5,
    check_bad_market_conditions,
    check_sideway_context,
    calculate_delta_high,
    calculate_delta_low,
    is_valid_delta_high,
    is_valid_delta_low,
    DeltaCountTracker,
    check_sell_signal_condition,
    check_buy_signal_condition,
    calculate_sl_tp,
    check_max_positions_per_zone,
    check_m5_candle_change,
    get_min_atr_threshold
)
```

---

## 📚 Tài Liệu Tham Khảo

- `Bot-Scalp-sideway_v1.md` - Chiến lược gốc
- `utils.py` - Utility functions chung
- `tuyen_trend_sclap.py` - Ví dụ implementation tương tự
