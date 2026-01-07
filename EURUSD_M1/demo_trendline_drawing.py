"""
Demo: Mô phỏng cách bot vẽ trendline cho hình ảnh
Giả lập dữ liệu từ hình để minh họa logic vẽ trendline

Option: Vẽ trendline từ ticket của lệnh MT5
- Đặt TICKET_NUMBER để vẽ trendline cho lệnh đó
- Hoặc để None để chạy demo với dữ liệu giả lập
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import sys

# Import MT5 và utils nếu cần vẽ từ ticket
# ========== CẤU HÌNH VẼ TRENDLINE TỪ TICKET ==========
# Để vẽ trendline từ ticket của lệnh MT5:
#   1. Đặt TICKET_NUMBER = <số_ticket> (ví dụ: 1044748590)
#   2. Script sẽ tự động:
#      - Load config từ configs/config_tuyen_xau.json
#      - Kết nối MT5
#      - Lấy thông tin lệnh từ ticket
#      - Tìm swing high/low trước entry
#      - Vẽ trendline tương ứng
#      - Hiển thị biểu đồ với entry, SL, TP
#
# Ví dụ:
#   TICKET_NUMBER = 1044748590
#
# Để chạy demo mode (dữ liệu giả lập):
#   TICKET_NUMBER = None
# ===========================================
TICKET_NUMBER = 3433918380  # None = demo mode, hoặc nhập ticket (ví dụ: 1044748590)
TICKET_NUMBER=3422943403
TICKET_NUMBER=3421683434
if TICKET_NUMBER is not None:
    import MetaTrader5 as mt5
    sys.path.append('..')
    from utils import load_config, connect_mt5, get_data
    from tuyen_trend_sclap_xau import (
        calculate_pullback_trendline, 
        calculate_pullback_trendline_buy,
        find_swing_high_with_rsi,
        find_swing_low_with_rsi
    )

def draw_trendline_from_ticket(ticket_number):
    """
    Vẽ trendline từ ticket của lệnh MT5
    """
    print(f"\n{'='*80}")
    print(f"VE TRENDLINE TU TICKET: {ticket_number}")
    print(f"{'='*80}\n")
    
    # Load config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_tuyen_xau.json")
    if not os.path.exists(config_path):
        print(f"[ERROR] Khong tim thay config: {config_path}")
        return
    
    config = load_config(config_path)
    if not config:
        print(f"[ERROR] Khong the load config")
        return
    
    # Connect MT5
    if not connect_mt5(config):
        print(f"[ERROR] Khong the ket noi MT5")
        return
    
    # Lấy thông tin position từ ticket (thử cả position đang mở và đã đóng)
    pos = None
    symbol = None
    entry_time = None
    entry_price = None
    order_type = None
    sl = None
    tp = None
    is_closed = False
    
    # Thử tìm trong positions đang mở
    positions = mt5.positions_get(ticket=ticket_number)
    if positions and len(positions) > 0:
        pos = positions[0]
        symbol = pos.symbol
        entry_time = datetime.fromtimestamp(pos.time)
        entry_price = pos.price_open
        order_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        sl = pos.sl
        tp = pos.tp
        is_closed = False
        print(f"[INFO] Tim thay position DANG MO")
    else:
        # Tìm trong history (position đã đóng)
        print(f"[INFO] Khong tim thay position dang mo, dang tim trong lich su...")
        deals = mt5.history_deals_get(position=ticket_number)
        if deals and len(deals) > 0:
            # Lấy deal đầu tiên (entry) và deal cuối cùng (exit)
            entry_deal = None
            exit_deal = None
            
            for deal in deals:
                if deal.entry == mt5.DEAL_ENTRY_IN:
                    entry_deal = deal
                elif deal.entry == mt5.DEAL_ENTRY_OUT:
                    exit_deal = deal
            
            if entry_deal:
                symbol = entry_deal.symbol
                entry_time = datetime.fromtimestamp(entry_deal.time)
                entry_price = entry_deal.price
                order_type = "BUY" if entry_deal.type == mt5.DEAL_TYPE_BUY else "SELL"
                is_closed = True
                
                # Tìm SL/TP từ deals hoặc từ position ticket trong history
                # Thử lấy từ history orders
                orders = mt5.history_orders_get(position=ticket_number)
                if orders and len(orders) > 0:
                    order = orders[0]
                    sl = order.sl
                    tp = order.tp
                else:
                    # Nếu không có trong orders, đặt None
                    sl = None
                    tp = None
                
                print(f"[INFO] Tim thay position DA DONG trong lich su")
            else:
                print(f"[ERROR] Khong tim thay entry deal cho ticket: {ticket_number}")
                mt5.shutdown()
                return
        else:
            print(f"[ERROR] Khong tim thay position voi ticket: {ticket_number}")
            print(f"   Kiem tra lai ticket hoac position da dong chua")
            mt5.shutdown()
            return
    
    print(f"[INFO] Thong tin lenh:")
    print(f"   Symbol: {symbol}")
    print(f"   Type: {order_type}")
    print(f"   Status: {'DA DONG' if is_closed else 'DANG MO'}")
    print(f"   Entry Time: {entry_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Entry Price: {entry_price:.5f}")
    if sl is not None:
        print(f"   SL: {sl:.5f}")
    else:
        print(f"   SL: N/A")
    if tp is not None:
        print(f"   TP: {tp:.5f}")
    else:
        print(f"   TP: N/A")
    print()
    
    # Lấy dữ liệu M1 (300 nến để đủ dữ liệu)
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 300)
    if df_m1 is None:
        print(f"[ERROR] Khong the lay du lieu M1 cho {symbol}")
        mt5.shutdown()
        return
    
    # Tính indicators
    def calculate_ema(series, span):
        return series.ewm(span=span, adjust=False).mean()
    
    def calculate_atr(df, period=14):
        df = df.copy()
        df['tr0'] = abs(df['high'] - df['low'])
        df['tr1'] = abs(df['high'] - df['close'].shift(1))
        df['tr2'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=period).mean()
        return df['atr']
    
    def calculate_rsi(series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    df_m1['ema50'] = calculate_ema(df_m1['close'], 50)
    df_m1['ema200'] = calculate_ema(df_m1['close'], 200)
    df_m1['atr'] = calculate_atr(df_m1, 14)
    df_m1['rsi'] = calculate_rsi(df_m1['close'], 14)
    
    # Tìm index của nến entry (nến gần nhất với entry_time)
    entry_idx = None
    for i in range(len(df_m1) - 1, -1, -1):
        # So sánh với cột 'time' thay vì index
        if df_m1.iloc[i]['time'] <= entry_time:
            entry_idx = i
            break
    
    if entry_idx is None:
        print(f"[ERROR] Khong tim thay nen entry trong du lieu")
        mt5.shutdown()
        return
    
    entry_time_str = df_m1.iloc[entry_idx]['time'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(df_m1.iloc[entry_idx]['time'], 'strftime') else str(df_m1.iloc[entry_idx]['time'])
    print(f"[INFO] Entry nen: Index={entry_idx}, Time={entry_time_str}")
    
    # Tìm swing high/low trước entry
    swing_idx = None
    trendline_info = None
    
    if order_type == "BUY":
        # BUY: Tìm swing high với RSI > 70 trước entry
        # Tìm trong df_m1 gốc nhưng chỉ xét các nến trước entry
        swing_highs_all = find_swing_high_with_rsi(df_m1, lookback=5, min_rsi=70)
        # Lọc chỉ lấy các swing high trước entry
        swing_highs = [sh for sh in swing_highs_all if sh['index'] < entry_idx]
        
        if len(swing_highs) == 0:
            print(f"[ERROR] Khong tim thay swing high voi RSI > 70 truoc entry")
            mt5.shutdown()
            return
        
        swing_high = swing_highs[-1]  # Lấy swing high gần nhất
        swing_idx = swing_high['index']
        swing_price = swing_high['price']
        
        print(f"[INFO] Swing High: Index={swing_idx}, Price={swing_price:.5f}, RSI={swing_high['rsi']:.1f}")
        
        # Vẽ trendline từ swing high đến entry
        # Sử dụng df_m1 gốc với index đúng
        trendline_info = calculate_pullback_trendline_buy(df_m1, swing_idx, entry_idx)
        
    else:  # SELL
        # SELL: Tìm swing low với RSI < 30 trước entry
        # Tìm trong df_m1 gốc nhưng chỉ xét các nến trước entry
        swing_lows_all = find_swing_low_with_rsi(df_m1, lookback=5, min_rsi=30)
        # Lọc chỉ lấy các swing low trước entry
        swing_lows = [sl for sl in swing_lows_all if sl['index'] < entry_idx]
        
        if len(swing_lows) == 0:
            print(f"[ERROR] Khong tim thay swing low voi RSI < 30 truoc entry")
            mt5.shutdown()
            return
        
        swing_low = swing_lows[-1]  # Lấy swing low gần nhất
        swing_idx = swing_low['index']
        swing_price = swing_low['price']
        
        print(f"[INFO] Swing Low: Index={swing_idx}, Price={swing_price:.5f}, RSI={swing_low['rsi']:.1f}")
        
        # Vẽ trendline từ swing low đến entry
        # Sử dụng df_m1 gốc với index đúng
        trendline_info = calculate_pullback_trendline(df_m1, swing_idx, entry_idx)
    
    if trendline_info is None:
        print(f"[ERROR] Khong the ve trendline")
        mt5.shutdown()
        return
    
    # Tính trendline cũ (logic cũ - chỉ chọn đáy/đỉnh cao/thấp hơn trước)
    trendline_info_old = None
    if order_type == "BUY":
        # BUY: Trendline cũ - chỉ chọn đỉnh thấp hơn đỉnh trước
        pullback_candles = df_m1.iloc[swing_idx:entry_idx + 1]
        highs = pullback_candles['high'].values
        local_maxs_old = []
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                local_maxs_old.append({'pos': i + swing_idx, 'price': highs[i]})
        
        # Thêm swing high
        local_maxs_old.insert(0, {'pos': swing_idx, 'price': df_m1.iloc[swing_idx]['high']})
        local_maxs_old = sorted(local_maxs_old, key=lambda x: x['pos'])
        
        # Logic cũ: chỉ chọn đỉnh thấp hơn đỉnh trước
        filtered_maxs_old = [local_maxs_old[0]]
        for i in range(1, len(local_maxs_old)):
            if local_maxs_old[i]['price'] <= filtered_maxs_old[-1]['price']:
                filtered_maxs_old.append(local_maxs_old[i])
        
        if len(filtered_maxs_old) >= 2:
            x_old = np.array([m['pos'] for m in filtered_maxs_old])
            y_old = np.array([m['price'] for m in filtered_maxs_old])
            n_old = len(x_old)
            sum_x_old = x_old.sum()
            sum_y_old = y_old.sum()
            sum_xy_old = (x_old * y_old).sum()
            sum_x2_old = (x_old * x_old).sum()
            denominator_old = n_old * sum_x2_old - sum_x_old * sum_x_old
            
            if abs(denominator_old) > 1e-10:
                slope_old = (n_old * sum_xy_old - sum_x_old * sum_y_old) / denominator_old
                intercept_old = (sum_y_old - slope_old * sum_x_old) / n_old
                
                def trendline_func_old(pos):
                    return slope_old * pos + intercept_old
                
                trendline_info_old = {
                    'slope': slope_old,
                    'intercept': intercept_old,
                    'func': trendline_func_old,
                    'points': filtered_maxs_old
                }
    else:  # SELL
        # SELL: Trendline cũ - chỉ chọn đáy cao hơn đáy trước
        pullback_candles = df_m1.iloc[swing_idx:entry_idx + 1]
        lows = pullback_candles['low'].values
        local_mins_old = []
        lookback = 2
        for i in range(lookback, len(lows) - lookback):
            is_local_min = True
            for j in range(i - lookback, i + lookback + 1):
                if j != i and lows[j] <= lows[i]:
                    is_local_min = False
                    break
            if is_local_min:
                local_mins_old.append({'pos': i + swing_idx, 'price': lows[i]})
        
        # Thêm swing low
        local_mins_old.insert(0, {'pos': swing_idx, 'price': df_m1.iloc[swing_idx]['low']})
        local_mins_old = sorted(local_mins_old, key=lambda x: x['pos'])
        
        # Logic cũ: chỉ chọn đáy cao hơn đáy trước
        filtered_mins_old = [local_mins_old[0]]
        for i in range(1, len(local_mins_old)):
            if local_mins_old[i]['price'] >= filtered_mins_old[-1]['price']:
                filtered_mins_old.append(local_mins_old[i])
        
        if len(filtered_mins_old) >= 2:
            x_old = np.array([m['pos'] for m in filtered_mins_old])
            y_old = np.array([m['price'] for m in filtered_mins_old])
            n_old = len(x_old)
            sum_x_old = x_old.sum()
            sum_y_old = y_old.sum()
            sum_xy_old = (x_old * y_old).sum()
            sum_x2_old = (x_old * x_old).sum()
            denominator_old = n_old * sum_x2_old - sum_x_old * sum_x_old
            
            if abs(denominator_old) > 1e-10:
                slope_old = (n_old * sum_xy_old - sum_x_old * sum_y_old) / denominator_old
                intercept_old = (sum_y_old - slope_old * sum_x_old) / n_old
                
                def trendline_func_old(pos):
                    return slope_old * pos + intercept_old
                
                trendline_info_old = {
                    'slope': slope_old,
                    'intercept': intercept_old,
                    'func': trendline_func_old,
                    'points': filtered_mins_old
                }
    
    # Vẽ biểu đồ
    fig, ax = plt.subplots(figsize=(16, 10))
    
    # Lấy dữ liệu từ swing đến entry + 20 nến sau
    start_idx = max(0, swing_idx - 10)
    end_idx = min(len(df_m1), entry_idx + 20)
    plot_df = df_m1.iloc[start_idx:end_idx].copy()
    plot_df.reset_index(drop=True, inplace=True)
    
    # Vẽ candlestick
    width = 0.6
    for i in range(len(plot_df)):
        idx = start_idx + i
        candle = df_m1.iloc[idx]
        x_pos = i
        
        # Xác định màu nến (xanh = tăng, đỏ = giảm)
        if candle['close'] >= candle['open']:
            color = 'green'
            body_bottom = candle['open']
            body_top = candle['close']
        else:
            color = 'red'
            body_bottom = candle['close']
            body_top = candle['open']
        
        # Vẽ body (thân nến)
        body_height = abs(candle['close'] - candle['open'])
        if body_height > 0:
            rect = plt.Rectangle((x_pos - width/2, body_bottom), width, body_height, 
                               facecolor=color, edgecolor='black', linewidth=0.5, alpha=0.7)
            ax.add_patch(rect)
        
        # Vẽ wick (bấc nến)
        ax.plot([x_pos, x_pos], [candle['low'], candle['high']], 
               color='black', linewidth=0.5, alpha=0.7)
    
    # Vẽ EMA
    ema50_plot = [df_m1.iloc[start_idx + i]['ema50'] for i in range(len(plot_df))]
    ema200_plot = [df_m1.iloc[start_idx + i]['ema200'] for i in range(len(plot_df))]
    ax.plot(range(len(plot_df)), ema50_plot, 'b-', linewidth=1, alpha=0.5, label='EMA50')
    ax.plot(range(len(plot_df)), ema200_plot, 'orange', linewidth=1, alpha=0.5, label='EMA200')
    
    # Vẽ swing point
    swing_plot_idx = swing_idx - start_idx
    if order_type == "BUY":
        ax.plot(swing_plot_idx, df_m1.iloc[swing_idx]['high'], 'ro', markersize=12, label='Swing High', zorder=10)
    else:
        ax.plot(swing_plot_idx, df_m1.iloc[swing_idx]['low'], 'ro', markersize=12, label='Swing Low', zorder=10)
    
    # Tính entry/SL/TP từ trendline cũ (nếu có)
    entry_price_old = None
    sl_old = None
    tp_old = None
    if trendline_info_old:
        # Entry price từ trendline cũ tại entry_idx
        entry_price_old = trendline_info_old['func'](entry_idx)
        
        # Tính SL/TP từ entry price cũ (dùng cùng công thức: SL = 2ATR + 6 point, TP = 2SL)
        atr_val = df_m1.iloc[entry_idx]['atr']
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info and pd.notna(atr_val):
            point = symbol_info.point
            sl_distance = (2 * atr_val) + (6 * point)
            tp_distance = 2 * sl_distance
            
            if order_type == "BUY":
                sl_old = entry_price_old - sl_distance
                tp_old = entry_price_old + tp_distance
            else:  # SELL
                sl_old = entry_price_old + sl_distance
                tp_old = entry_price_old - tp_distance
            
            # Normalize
            digits = symbol_info.digits
            entry_price_old = round(entry_price_old, digits)
            sl_old = round(sl_old, digits)
            tp_old = round(tp_old, digits)
    
    # Vẽ entry point (mới - thực tế)
    entry_plot_idx = entry_idx - start_idx
    ax.plot(entry_plot_idx, entry_price, 'g*', markersize=15, label=f'Entry NEW ({order_type})', zorder=10)
    
    # Vẽ entry point cũ (nếu có)
    if entry_price_old is not None:
        ax.plot(entry_plot_idx, entry_price_old, 'm*', markersize=12, label=f'Entry OLD ({order_type})', zorder=10)
    
    # Vẽ SL/TP mới (thực tế - nếu có)
    if sl is not None:
        ax.axhline(y=sl, color='r', linestyle='--', linewidth=2, alpha=0.8, label='SL NEW')
    if tp is not None:
        ax.axhline(y=tp, color='g', linestyle='--', linewidth=2, alpha=0.8, label='TP NEW')
    
    # Vẽ SL/TP cũ (nếu có)
    if sl_old is not None:
        ax.axhline(y=sl_old, color='m', linestyle=':', linewidth=2, alpha=0.7, label='SL OLD')
    if tp_old is not None:
        ax.axhline(y=tp_old, color='m', linestyle=':', linewidth=2, alpha=0.7, label='TP OLD')
    
    # Vẽ trendline mới (logic mới)
    trendline_points = trendline_info['points']
    for i, point in enumerate(trendline_points):
        # point['pos'] là index trong df_m1
        point_pos = point['pos']
        if start_idx <= point_pos < end_idx:
            point_plot_idx = point_pos - start_idx
            ax.plot(point_plot_idx, point['price'], 'go', markersize=8, label='Trendline Points (New)' if i == 0 else '')
    
    # Vẽ đường trendline mới
    x_trendline = np.arange(swing_idx, entry_idx + 1)
    y_trendline = [trendline_info['func'](i) for i in x_trendline]
    x_trendline_plot = [i - start_idx for i in x_trendline if start_idx <= i < end_idx]
    y_trendline_plot = [trendline_info['func'](i) for i in x_trendline if start_idx <= i < end_idx]
    if len(x_trendline_plot) > 0:
        ax.plot(x_trendline_plot, y_trendline_plot, 'r-', linewidth=2.5, label='Trendline (New Logic)', alpha=0.9)
    
    # Vẽ trendline cũ (logic cũ) nếu có
    if trendline_info_old:
        trendline_points_old = trendline_info_old['points']
        for i, point in enumerate(trendline_points_old):
            point_pos = point['pos']
            if start_idx <= point_pos < end_idx:
                point_plot_idx = point_pos - start_idx
                ax.plot(point_plot_idx, point['price'], 'mo', markersize=6, label='Trendline Points (Old)' if i == 0 else '')
        
        x_trendline_old = np.arange(swing_idx, entry_idx + 1)
        y_trendline_old = [trendline_info_old['func'](i) for i in x_trendline_old]
        x_trendline_plot_old = [i - start_idx for i in x_trendline_old if start_idx <= i < end_idx]
        y_trendline_plot_old = [trendline_info_old['func'](i) for i in x_trendline_old if start_idx <= i < end_idx]
        if len(x_trendline_plot_old) > 0:
            ax.plot(x_trendline_plot_old, y_trendline_plot_old, 'm--', linewidth=2, label='Trendline (Old Logic)', alpha=0.7)
    
    # Highlight pullback phase
    pullback_start_plot = swing_idx - start_idx
    pullback_end_plot = entry_idx - start_idx
    ax.axvspan(pullback_start_plot, pullback_end_plot, alpha=0.1, color='yellow', label='Pullback Phase')
    
    ax.set_xlabel('Candle Index (relative)', fontsize=12)
    ax.set_ylabel('Price', fontsize=12)
    ax.set_title(f'Trendline Analysis - Ticket: {ticket_number} ({order_type}) | {symbol}', fontsize=14, fontweight='bold')
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # In thông tin
    print(f"\n{'='*60}")
    print(f"KET QUA VE TRENDLINE")
    print(f"{'='*60}")
    print(f"[OK] Trendline MOI: Tim duoc {len(trendline_points)} diem")
    print(f"\nCac diem trendline MOI:")
    for i, point in enumerate(trendline_points):
        point_pos = point['pos']
        time_val = df_m1.iloc[point_pos]['time']
        if hasattr(time_val, 'strftime'):
            time_str = time_val.strftime('%Y-%m-%d %H:%M:%S')
        else:
            time_str = str(time_val)
        print(f"   Diem {i+1}: Index={point_pos}, Time={time_str}, Price={point['price']:.5f}")
    print(f"\nTrendline MOI: Slope={trendline_info['slope']:.8f}, Intercept={trendline_info['intercept']:.5f}")
    
    if trendline_info_old:
        print(f"\n[OK] Trendline CU: Tim duoc {len(trendline_info_old['points'])} diem")
        print(f"\nCac diem trendline CU:")
        for i, point in enumerate(trendline_info_old['points']):
            point_pos = point['pos']
            time_val = df_m1.iloc[point_pos]['time']
            if hasattr(time_val, 'strftime'):
                time_str = time_val.strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_str = str(time_val)
            print(f"   Diem {i+1}: Index={point_pos}, Time={time_str}, Price={point['price']:.5f}")
        print(f"\nTrendline CU: Slope={trendline_info_old['slope']:.8f}, Intercept={trendline_info_old['intercept']:.5f}")
        print(f"\nSo sanh: Trendline MOI co {len(trendline_points)} diem, Trendline CU co {len(trendline_info_old['points'])} diem")
        
        # In thông tin Entry/SL/TP cũ
        if entry_price_old is not None:
            print(f"\n{'='*60}")
            print(f"ENTRY/SL/TP - SO SANH")
            print(f"{'='*60}")
            print(f"\n[MOI - Thuc te]")
            print(f"   Entry: {entry_price:.5f}")
            if sl is not None:
                print(f"   SL: {sl:.5f}")
            if tp is not None:
                print(f"   TP: {tp:.5f}")
            
            print(f"\n[CU - Tinh tu trendline cu]")
            print(f"   Entry: {entry_price_old:.5f}")
            if sl_old is not None:
                print(f"   SL: {sl_old:.5f}")
            if tp_old is not None:
                print(f"   TP: {tp_old:.5f}")
            
            # Tính chênh lệch
            entry_diff = entry_price - entry_price_old
            print(f"\n[Chenh lech]")
            print(f"   Entry: {entry_diff:+.5f} ({entry_diff/entry_price*100:+.3f}%)")
            if sl is not None and sl_old is not None:
                sl_diff = sl - sl_old
                print(f"   SL: {sl_diff:+.5f}")
            if tp is not None and tp_old is not None:
                tp_diff = tp - tp_old
                print(f"   TP: {tp_diff:+.5f}")
    else:
        print(f"\n[WARNING] Khong the ve trendline CU (khong du diem)")
    
    print(f"{'='*60}\n")
    
    plt.tight_layout()
    output_file = f'trendline_ticket_{ticket_number}.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"[OK] Da luu bieu do vao: {output_file}")
    plt.show()
    
    mt5.shutdown()

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
        # Điều kiện 3: Nếu chỉ có 2 điểm và điểm thứ 2 thấp hơn swing low, vẫn thêm vào để vẽ trendline
        elif len(local_mins) == 2 and i == 1:
            # Cho phép pullback lớn hơn một chút (0.5%) nếu chỉ có 2 điểm
            max_pullback = swing_low_price * 0.995
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

# ========== KIỂM TRA MODE ==========
# Nếu có TICKET_NUMBER, vẽ trendline từ ticket
if TICKET_NUMBER is not None:
    draw_trendline_from_ticket(TICKET_NUMBER)
    sys.exit(0)

# ========== DEMO MODE ==========
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

# ========== CẤU HÌNH VẼ TRENDLINE ==========
# Swing Low tại nến 20-28 (bottom phase)
swing_low_idx = 24  # Giả sử swing low tại nến 24

# Option 1: Chọn bằng INDEX (ưu tiên nếu cả 2 đều được chỉ định)
# - Đặt None để tự động từ swing_low_idx đến cuối dữ liệu
# - Hoặc chỉ định start_idx và end_idx cụ thể
TRENDLINE_START_IDX = None  # None = dùng swing_low_idx, hoặc chỉ định index (ví dụ: 25)
TRENDLINE_END_IDX = None    # None = đến cuối dữ liệu, hoặc chỉ định index (ví dụ: 45)

# Option 2: Chọn bằng DATETIME (sẽ override INDEX nếu được chỉ định)
# - Đặt None để không dùng datetime
# - Hoặc chỉ định datetime string (format: 'YYYY-MM-DD HH:MM:SS') hoặc datetime object
# Ví dụ: '2026-01-07 13:12:04' hoặc datetime(2026, 1, 7, 13, 12, 4)
TRENDLINE_START_DATETIME = None  # None hoặc datetime string/object (ví dụ: '2026-01-07 13:12:04')
TRENDLINE_END_DATETIME = None    # None hoặc datetime string/object (ví dụ: '2026-01-07 14:00:00')

# Ví dụ: Để chọn thời điểm '2026-01-07 13:12:04', uncomment dòng sau:
# TRENDLINE_START_DATETIME = '2026-01-07 13:12:04'

# Ví dụ sử dụng:
#   
#   1. Chọn bằng datetime (ưu tiên):
#      TRENDLINE_START_DATETIME = '2026-01-07 13:12:04'
#      TRENDLINE_END_DATETIME = '2026-01-07 14:00:00'
#      # Hoặc chỉ chọn start, end sẽ tự động đến cuối:
#      TRENDLINE_START_DATETIME = '2026-01-07 13:12:04'
#      TRENDLINE_END_DATETIME = None
#
#   2. Chọn bằng index:
#      TRENDLINE_START_IDX = 25
#      TRENDLINE_END_IDX = 45
#
#   3. Mặc định (từ swing low đến cuối):
#      Tất cả đều None
#
# Lưu ý: Nếu chỉ định cả datetime và index, datetime sẽ được ưu tiên.
# ===========================================

# Hàm helper: Chuyển datetime string/object thành datetime object
def parse_datetime(dt_input):
    """Chuyển datetime string hoặc object thành datetime object"""
    if dt_input is None:
        return None
    if isinstance(dt_input, datetime):
        return dt_input
    if isinstance(dt_input, str):
        try:
            return datetime.strptime(dt_input, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                return datetime.strptime(dt_input, '%Y-%m-%d %H:%M')
            except ValueError:
                raise ValueError(f"Khong the parse datetime: {dt_input}. Dung format 'YYYY-MM-DD HH:MM:SS' hoac 'YYYY-MM-DD HH:MM'")
    return None

# Hàm helper: Tìm index gần nhất với datetime
def find_nearest_index(df, target_datetime):
    """Tìm index của nến gần nhất với target_datetime"""
    if target_datetime is None:
        return None
    
    # Tìm nến có time <= target_datetime và gần nhất
    mask = df['time'] <= target_datetime
    if mask.any():
        idx = df[mask].index[-1]
        return idx
    else:
        # Nếu không tìm thấy, lấy nến đầu tiên
        return df.index[0]

# Xác định khoảng thời gian để vẽ trendline
# Ưu tiên datetime nếu được chỉ định
if TRENDLINE_START_DATETIME is not None:
    start_dt = parse_datetime(TRENDLINE_START_DATETIME)
    trendline_start = find_nearest_index(df, start_dt)
    print(f"[INFO] Tim thay nen gan nhat voi {TRENDLINE_START_DATETIME}: Index={trendline_start}, Time={df.iloc[trendline_start]['time']}")
elif TRENDLINE_START_IDX is not None:
    trendline_start = TRENDLINE_START_IDX
    # Đảm bảo start >= swing_low_idx
    if trendline_start < swing_low_idx:
        trendline_start = swing_low_idx
        print(f"[WARNING] TRENDLINE_START_IDX phai >= swing_low_idx ({swing_low_idx}). Da tu dong dieu chinh.")
else:
    trendline_start = swing_low_idx

if TRENDLINE_END_DATETIME is not None:
    end_dt = parse_datetime(TRENDLINE_END_DATETIME)
    trendline_end_idx = find_nearest_index(df, end_dt)
    trendline_end = trendline_end_idx + 1  # +1 vì iloc là exclusive
    print(f"[INFO] Tim thay nen gan nhat voi {TRENDLINE_END_DATETIME}: Index={trendline_end_idx}, Time={df.iloc[trendline_end_idx]['time']}")
elif TRENDLINE_END_IDX is not None:
    trendline_end = TRENDLINE_END_IDX + 1  # +1 vì iloc là exclusive
else:
    trendline_end = len(df)

# Đảm bảo end > start
if trendline_end <= trendline_start:
    trendline_end = len(df)
    print(f"[WARNING] TRENDLINE_END phai > TRENDLINE_START. Da tu dong dieu chinh.")

# Lấy lows trong khoảng thời gian đã chọn
trendline_data = df.iloc[trendline_start:trendline_end]
pullback_lows = trendline_data['low'].values

# Tính toán offset để vẽ đúng vị trí trên biểu đồ
trendline_offset = trendline_start

print(f"\n[INFO] Khoang thoi gian ve trendline:")
print(f"   Start Index: {trendline_start} (Time: {df.iloc[trendline_start]['time'].strftime('%H:%M')})")
print(f"   End Index: {trendline_end-1} (Time: {df.iloc[trendline_end-1]['time'].strftime('%H:%M')})")
print(f"   So nen: {len(pullback_lows)}")

# Kiểm tra có đủ nến để vẽ trendline không
if len(pullback_lows) < 2:
    print(f"[WARNING] Chi co {len(pullback_lows)} nen trong khoang thoi gian da chon. Can it nhat 2 nen de ve trendline.")
    print(f"[WARNING] Vui long chon lai khoang thoi gian hoac kiem tra du lieu.")

# Vẽ trendline
trendline_info, all_local_mins = calculate_pullback_trendline_demo(
    pullback_lows, 
    swing_low_idx=0  # Swing low là điểm đầu tiên trong pullback_lows (nếu swing_low_idx == trendline_start)
)

# Vẽ biểu đồ
fig, ax = plt.subplots(figsize=(14, 8))

# Vẽ giá
ax.plot(df.index, df['close'], 'o-', color='white', linewidth=1, markersize=3, label='Close Price')
ax.fill_between(df.index, df['low'], df['high'], alpha=0.3, color='gray', label='High-Low Range')

# Vẽ swing low
ax.plot(swing_low_idx, df.iloc[swing_low_idx]['low'], 'ro', markersize=10, label='Swing Low')

# Vẽ tất cả local minima tìm được
all_min_positions = [trendline_offset + m['pos'] for m in all_local_mins]
all_min_prices = [m['price'] for m in all_local_mins]
ax.plot(all_min_positions, all_min_prices, 'yo', markersize=6, label='All Local Minima')

# Vẽ các điểm được chọn cho trendline
if trendline_info:
    trendline_points = trendline_info['points']
    selected_positions = [trendline_offset + p['pos'] for p in trendline_points]
    selected_prices = [p['price'] for p in trendline_points]
    ax.plot(selected_positions, selected_prices, 'go', markersize=8, label='Selected Points for Trendline')
    
    # Vẽ trendline trong khoảng thời gian đã chọn
    x_trendline = np.arange(trendline_start, trendline_end)
    y_trendline = [trendline_info['func'](i - trendline_offset) for i in x_trendline]
    ax.plot(x_trendline, y_trendline, 'r-', linewidth=2, label='Trendline (New Logic)', alpha=0.8)
    
    # In thông tin
    print(f"\n{'='*60}")
    print(f"KET QUA VE TRENDLINE")
    print(f"{'='*60}")
    print(f"[OK] Tim duoc {len(all_local_mins)} local minima")
    print(f"[OK] Chon duoc {len(trendline_points)} diem cho trendline")
    print(f"\nCac diem duoc chon:")
    for i, point in enumerate(trendline_points):
        idx = trendline_offset + point['pos']
        time_str = df.iloc[idx]['time'].strftime('%H:%M')
        print(f"   Diem {i+1}: Index={idx}, Time={time_str}, Price={point['price']:.2f}")
    print(f"\nTrendline: Slope={trendline_info['slope']:.6f}, Intercept={trendline_info['intercept']:.2f}")
    print(f"{'='*60}\n")

# Vẽ trendline cũ (logic cũ - chỉ chọn đáy cao hơn đáy trước)
if len(all_local_mins) > 1:
    old_filtered = [all_local_mins[0]]
    for i in range(1, len(all_local_mins)):
        if all_local_mins[i]['price'] >= old_filtered[-1]['price']:
            old_filtered.append(all_local_mins[i])
    
    if len(old_filtered) >= 2:
        old_positions = [trendline_offset + p['pos'] for p in old_filtered]
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
            
            x_trendline_old = np.arange(trendline_start, trendline_end)
            y_trendline_old = [slope_old * (i - trendline_offset) + intercept_old for i in x_trendline_old]
            ax.plot(x_trendline_old, y_trendline_old, 'm--', linewidth=2, label='Trendline (Old Logic)', alpha=0.6)
            
            print(f"Trendline cu: {len(old_filtered)} diem (bo sot {len(all_local_mins) - len(old_filtered)} day)")

ax.set_xlabel('Candle Index', fontsize=12)
ax.set_ylabel('Price', fontsize=12)
ax.set_title('Demo: Vẽ Trendline Pullback (SELL Signal)', fontsize=14, fontweight='bold')
ax.legend(loc='upper left', fontsize=10)
ax.grid(True, alpha=0.3)

# Highlight pullback phase (khoảng thời gian đã chọn để vẽ trendline)
ax.axvspan(trendline_start, trendline_end-1, alpha=0.1, color='yellow', label='Trendline Range')

plt.tight_layout()
plt.savefig('trendline_demo.png', dpi=150, bbox_inches='tight')
print(f"[OK] Da luu bieu do vao: trendline_demo.png")
plt.show()

