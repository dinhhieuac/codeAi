"""
Demo: Mô phỏng cách bot vẽ trendline cho hình ảnh
Giả lập dữ liệu từ hình để minh họa logic vẽ trendline
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

def calculate_pullback_trendline_demo(lows, swing_low_idx=0):
    """
    Mô phỏng logic vẽ trendline (SELL - các đáy cao dần)
    """
    local_mins = []
    lookback = 2  # So sánh với 2 nến trước và sau
    
    for i in range(lookback, len(lows) - lookback):
        is_local_min = True
        for j in range(i - lookback, i + lookback + 1):
            if j != i and lows[j] <= lows[i]:
                is_local_min = False
                break
        
        if is_local_min:
            local_mins.append({'pos': i, 'price': lows[i]})
    
    # Thêm swing low vào đầu
    swing_low_price = lows[swing_low_idx]
    local_mins.insert(0, {'pos': swing_low_idx, 'price': swing_low_price})
    
    local_mins = sorted(local_mins, key=lambda x: x['pos'])
    
    # Lọc các đáy cao dần (Logic mới - linh hoạt)
    filtered_mins = [local_mins[0]]
    swing_low_price = local_mins[0]['price']
    
    for i in range(1, len(local_mins)):
        current_price = local_mins[i]['price']
        last_price = filtered_mins[-1]['price']
        
        # Điều kiện 1: Cao hơn đáy trước
        if current_price >= last_price:
            filtered_mins.append(local_mins[i])
        # Điều kiện 2: Thấp hơn đáy trước nhưng vẫn cao hơn swing low
        elif current_price >= swing_low_price:
            has_higher_low_after = False
            for j in range(i + 1, len(local_mins)):
                if local_mins[j]['price'] > current_price:
                    has_higher_low_after = True
                    break
            
            if has_higher_low_after or i == len(local_mins) - 1:
                max_pullback = last_price * 0.999  # Cho phép pullback tối đa 0.1%
                if current_price >= max_pullback:
                    filtered_mins.append(local_mins[i])
    
    if len(filtered_mins) < 2:
        return None, local_mins
    
    # Linear regression
    x_values = np.array([m['pos'] for m in filtered_mins])
    y_values = np.array([m['price'] for m in filtered_mins])
    
    n = len(x_values)
    sum_x = x_values.sum()
    sum_y = y_values.sum()
    sum_xy = (x_values * y_values).sum()
    sum_x2 = (x_values * x_values).sum()
    
    denominator = n * sum_x2 - sum_x * sum_x
    if abs(denominator) < 1e-10:
        return None, local_mins
    
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    
    def trendline_func(pos):
        return slope * pos + intercept
    
    return {
        'slope': slope,
        'intercept': intercept,
        'func': trendline_func,
        'points': filtered_mins
    }, local_mins

# Tạo dữ liệu mẫu dựa trên hình ảnh
# Giả lập: Downtrend → Bottom → Uptrend (pullback)
np.random.seed(42)

# Tạo timeline (từ 7 Jan 05:24 đến 7 Jan 06:16, mỗi 1 phút = 1 nến)
n_candles = 52  # ~52 phút
timeline = [datetime(2026, 1, 7, 5, 24) + timedelta(minutes=i) for i in range(n_candles)]

# Tạo giá giả lập
prices = []
base_price = 4455.0

# Phase 1: Downtrend (0-20 nến)
for i in range(20):
    base_price -= np.random.uniform(0.5, 2.0)
    prices.append(base_price)

# Phase 2: Bottom/Consolidation (20-28 nến)
for i in range(8):
    base_price += np.random.uniform(-0.3, 0.3)
    prices.append(base_price)

# Phase 3: Uptrend/Pullback (28-52 nến)
for i in range(24):
    base_price += np.random.uniform(0.2, 1.5)
    prices.append(base_price)

# Tạo DataFrame với highs và lows
df = pd.DataFrame({
    'time': timeline,
    'close': prices,
    'high': [p + np.random.uniform(0.1, 0.5) for p in prices],
    'low': [p - np.random.uniform(0.1, 0.5) for p in prices]
})

# Swing Low tại nến 20-28 (bottom phase)
swing_low_idx = 24  # Giả sử swing low tại nến 24

# Lấy lows từ swing low đến cuối (pullback phase)
pullback_lows = df.iloc[swing_low_idx:]['low'].values

# Vẽ trendline
trendline_info, all_local_mins = calculate_pullback_trendline_demo(
    pullback_lows, 
    swing_low_idx=0  # Swing low là điểm đầu tiên trong pullback_lows
)

# Vẽ biểu đồ
fig, ax = plt.subplots(figsize=(14, 8))

# Vẽ giá
ax.plot(df.index, df['close'], 'o-', color='white', linewidth=1, markersize=3, label='Close Price')
ax.fill_between(df.index, df['low'], df['high'], alpha=0.3, color='gray', label='High-Low Range')

# Vẽ swing low
ax.plot(swing_low_idx, df.iloc[swing_low_idx]['low'], 'ro', markersize=10, label='Swing Low')

# Vẽ tất cả local minima tìm được
all_min_positions = [swing_low_idx + m['pos'] for m in all_local_mins]
all_min_prices = [m['price'] for m in all_local_mins]
ax.plot(all_min_positions, all_min_prices, 'yo', markersize=6, label='All Local Minima')

# Vẽ các điểm được chọn cho trendline
if trendline_info:
    trendline_points = trendline_info['points']
    selected_positions = [swing_low_idx + p['pos'] for p in trendline_points]
    selected_prices = [p['price'] for p in trendline_points]
    ax.plot(selected_positions, selected_prices, 'go', markersize=8, label='Selected Points for Trendline')
    
    # Vẽ trendline
    x_trendline = np.arange(swing_low_idx, len(df))
    y_trendline = [trendline_info['func'](i - swing_low_idx) for i in x_trendline]
    ax.plot(x_trendline, y_trendline, 'r-', linewidth=2, label='Trendline (New Logic)', alpha=0.8)
    
    # In thông tin
    print(f"\n{'='*60}")
    print(f"📊 KẾT QUẢ VẼ TRENDLINE")
    print(f"{'='*60}")
    print(f"✅ Tìm được {len(all_local_mins)} local minima")
    print(f"✅ Chọn được {len(trendline_points)} điểm cho trendline")
    print(f"\n📍 Các điểm được chọn:")
    for i, point in enumerate(trendline_points):
        idx = swing_low_idx + point['pos']
        time_str = df.iloc[idx]['time'].strftime('%H:%M')
        print(f"   Điểm {i+1}: Index={idx}, Time={time_str}, Price={point['price']:.2f}")
    print(f"\n📈 Trendline: Slope={trendline_info['slope']:.6f}, Intercept={trendline_info['intercept']:.2f}")
    print(f"{'='*60}\n")

# Vẽ trendline cũ (logic cũ - chỉ chọn đáy cao hơn đáy trước)
if len(all_local_mins) > 1:
    old_filtered = [all_local_mins[0]]
    for i in range(1, len(all_local_mins)):
        if all_local_mins[i]['price'] >= old_filtered[-1]['price']:
            old_filtered.append(all_local_mins[i])
    
    if len(old_filtered) >= 2:
        old_positions = [swing_low_idx + p['pos'] for p in old_filtered]
        old_prices = [p['price'] for p in old_filtered]
        
        # Linear regression cho trendline cũ
        x_old = np.array(old_positions)
        y_old = np.array(old_prices)
        n_old = len(x_old)
        sum_x_old = x_old.sum()
        sum_y_old = y_old.sum()
        sum_xy_old = (x_old * y_old).sum()
        sum_x2_old = (x_old * x_old).sum()
        denominator_old = n_old * sum_x2_old - sum_x_old * sum_x_old
        
        if abs(denominator_old) > 1e-10:
            slope_old = (n_old * sum_xy_old - sum_x_old * sum_y_old) / denominator_old
            intercept_old = (sum_y_old - slope_old * sum_x_old) / n_old
            
            x_trendline_old = np.arange(swing_low_idx, len(df))
            y_trendline_old = [slope_old * (i - swing_low_idx) + intercept_old for i in x_trendline_old]
            ax.plot(x_trendline_old, y_trendline_old, 'm--', linewidth=2, label='Trendline (Old Logic)', alpha=0.6)
            
            print(f"📉 Trendline cũ: {len(old_filtered)} điểm (bỏ sót {len(all_local_mins) - len(old_filtered)} đáy)")

ax.set_xlabel('Candle Index', fontsize=12)
ax.set_ylabel('Price', fontsize=12)
ax.set_title('Demo: Vẽ Trendline Pullback (SELL Signal)', fontsize=14, fontweight='bold')
ax.legend(loc='upper left', fontsize=10)
ax.grid(True, alpha=0.3)

# Highlight pullback phase
ax.axvspan(swing_low_idx, len(df)-1, alpha=0.1, color='yellow', label='Pullback Phase')

plt.tight_layout()
plt.savefig('EURUSD_M1/trendline_demo.png', dpi=150, bbox_inches='tight')
print(f"✅ Đã lưu biểu đồ vào: EURUSD_M1/trendline_demo.png")
plt.show()

