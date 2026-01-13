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

# Import MT5 và utils
import MetaTrader5 as mt5
sys.path.append('..')
from utils import load_config, connect_mt5, get_data
from tuyen_trend_sclap_xau import (
    calculate_pullback_trendline, 
    calculate_pullback_trendline_buy,
    find_swing_high_with_rsi,
    find_swing_low_with_rsi
)

def find_ticket_by_datetime(target_datetime, symbol=None):
    """
    Tìm ticket của lệnh gần nhất với thời gian đã cho
    Args:
        target_datetime: datetime object hoặc string (format: 'YYYY-MM-DD HH:MM:SS')
        symbol: Symbol để filter (None = tất cả symbols)
    Returns:
        ticket_number hoặc None
    """
    if isinstance(target_datetime, str):
        try:
            target_datetime = datetime.strptime(target_datetime, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                target_datetime = datetime.strptime(target_datetime, '%Y-%m-%d %H:%M')
            except ValueError:
                print(f"[ERROR] Khong the parse datetime: {target_datetime}")
                return None
    
    # Load config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_tuyen_xau.json")
    if not os.path.exists(config_path):
        print(f"[ERROR] Khong tim thay config: {config_path}")
        return None
    
    config = load_config(config_path)
    if not config:
        print(f"[ERROR] Khong the load config")
        return None
    
    # Connect MT5
    if not connect_mt5(config):
        print(f"[ERROR] Khong the ket noi MT5")
        return None
    
    # Tìm trong positions đang mở
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    best_ticket = None
    best_diff = None
    
    if positions:
        for pos in positions:
            pos_time = datetime.fromtimestamp(pos.time)
            diff = abs((pos_time - target_datetime).total_seconds())
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_ticket = pos.ticket
    
    # Tìm trong history (positions đã đóng)
    # Lấy deals trong khoảng thời gian ±1 ngày
    from_time = int((target_datetime - timedelta(days=1)).timestamp())
    to_time = int((target_datetime + timedelta(days=1)).timestamp())
    
    deals = mt5.history_deals_get(from_time, to_time, group="*")
    if deals:
        for deal in deals:
            if deal.entry == mt5.DEAL_ENTRY_IN:
                if symbol and deal.symbol != symbol:
                    continue
                deal_time = datetime.fromtimestamp(deal.time)
                diff = abs((deal_time - target_datetime).total_seconds())
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_ticket = deal.position_id
    
    if best_ticket:
        print(f"[INFO] Tim thay ticket {best_ticket} gan nhat voi thoi gian {target_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Chenh lech: {best_diff/60:.1f} phut")
        return best_ticket
    else:
        print(f"[ERROR] Khong tim thay lenh nao gan voi thoi gian {target_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        return None

def get_user_input():
    """
    Lấy input từ người dùng: ticket hoặc thời gian
    Returns:
        ticket_number (int) hoặc None
    """
    print("\n" + "="*80)
    print("VE TRENDLINE TU TICKET HOAC THOI GIAN")
    print("="*80)
    print("\nChon che do:")
    print("  1. Nhap ticket (so)")
    print("  2. Nhap thoi gian (YYYY-MM-DD HH:MM:SS hoac YYYY-MM-DD HH:MM)")
    print("  3. Demo mode (du lieu gia lap)")
    print("  0. Thoat")
    
    choice = input("\nNhap lua chon (1/2/3/0): ").strip()
    
    if choice == "0":
        print("Thoat chuong trinh.")
        sys.exit(0)
    elif choice == "1":
        ticket_input = input("Nhap ticket number: ").strip()
        try:
            ticket_number = int(ticket_input)
            return ticket_number
        except ValueError:
            print(f"[ERROR] Ticket phai la so nguyen. Nhap: {ticket_input}")
            return None
    elif choice == "2":
        time_input = input("Nhap thoi gian (YYYY-MM-DD HH:MM:SS hoac YYYY-MM-DD HH:MM): ").strip()
        ticket_number = find_ticket_by_datetime(time_input)
        return ticket_number
    elif choice == "3":
        return None  # Demo mode
    else:
        print(f"[ERROR] Lua chon khong hop le: {choice}")
        return None

def calculate_pullback_trendline_buy_with_debug(df_m1, swing_high_idx, pullback_end_idx):
    """
    Wrapper function với debug logging cho calculate_pullback_trendline_buy
    """
    print(f"\n[DEBUG] calculate_pullback_trendline_buy:")
    print(f"   swing_high_idx={swing_high_idx}, pullback_end_idx={pullback_end_idx}")
    print(f"   Khoang cach: {pullback_end_idx - swing_high_idx} nen")
    print(f"   df_m1 length: {len(df_m1)}")
    
    if swing_high_idx >= len(df_m1) - 1:
        print(f"   [ERROR] swing_high_idx ({swing_high_idx}) >= len(df_m1) - 1 ({len(df_m1) - 1})")
        return None
    
    # Anchor 1
    anchor1_pos = swing_high_idx
    anchor1_price = df_m1.iloc[swing_high_idx]['high']
    print(f"   Anchor 1: Index={anchor1_pos}, Price={anchor1_price:.5f}")
    
    # Anchor 2: Tìm trong khoảng 15-30
    anchor2_start_idx_preferred = swing_high_idx + 15
    anchor2_end_idx_preferred = min(swing_high_idx + 30, len(df_m1) - 1, pullback_end_idx)
    print(f"   Anchor 2 preferred range: [{anchor2_start_idx_preferred}, {anchor2_end_idx_preferred}]")
    
    # Fallback logic
    if anchor2_start_idx_preferred >= len(df_m1) or anchor2_start_idx_preferred > anchor2_end_idx_preferred:
        print(f"   [FALLBACK] Khong du nen trong khoang 15-30, su dung fallback")
        anchor2_start_idx = swing_high_idx + 3
        anchor2_end_idx = min(pullback_end_idx, len(df_m1) - 1)
        print(f"   Anchor 2 fallback range: [{anchor2_start_idx}, {anchor2_end_idx}]")
        
        if anchor2_start_idx >= len(df_m1) or anchor2_start_idx >= anchor2_end_idx:
            print(f"   [ERROR] Khong du nen toi thieu trong fallback range")
            return None
    else:
        anchor2_start_idx = anchor2_start_idx_preferred
        anchor2_end_idx = anchor2_end_idx_preferred
        print(f"   [OK] Su dung khoang uu tien 15-30")
    
    # Tìm Anchor 2
    search_range = df_m1.iloc[anchor2_start_idx:anchor2_end_idx + 1]
    if len(search_range) == 0:
        print(f"   [ERROR] search_range rong")
        return None
    
    max_high_pos_in_range = search_range['high'].values.argmax()
    anchor2_pos = anchor2_start_idx + max_high_pos_in_range
    anchor2_price = df_m1.iloc[anchor2_pos]['high']
    print(f"   Anchor 2: Index={anchor2_pos}, Price={anchor2_price:.5f}")
    
    if anchor2_pos <= anchor1_pos:
        print(f"   [ERROR] anchor2_pos ({anchor2_pos}) <= anchor1_pos ({anchor1_pos})")
        return None
    
    # Tính trendline
    x_values = np.array([anchor1_pos, anchor2_pos])
    y_values = np.array([anchor1_price, anchor2_price])
    
    n = 2
    sum_x = x_values.sum()
    sum_y = y_values.sum()
    sum_xy = (x_values * y_values).sum()
    sum_x2 = (x_values * x_values).sum()
    
    denominator = n * sum_x2 - sum_x * sum_x
    if abs(denominator) < 1e-10:
        print(f"   [ERROR] denominator qua nho: {denominator}")
        return None
    
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    print(f"   Trendline: Slope={slope:.8f}, Intercept={intercept:.5f}")
    
    def trendline_func(pos):
        return slope * pos + intercept
    
    # Validation
    print(f"   [VALIDATION] Kiem tra cac nen giua Anchor 1 va Anchor 2...")
    validation_failed = False
    for i in range(anchor1_pos + 1, anchor2_pos):
        if i >= len(df_m1):
            break
        candle = df_m1.iloc[i]
        trendline_value = trendline_func(i)
        if candle['close'] >= trendline_value:
            print(f"   [VALIDATION FAILED] Nen {i}: Close={candle['close']:.5f} >= Trendline={trendline_value:.5f}")
            validation_failed = True
            break
    
    if validation_failed:
        print(f"   [ERROR] Validation failed - co nen Close >= Trendline")
        return None
    
    print(f"   [OK] Validation passed - tat ca nen co Close < Trendline")
    
    return {
        'slope': slope,
        'intercept': intercept,
        'func': trendline_func,
        'points': [
            {'pos': anchor1_pos, 'price': anchor1_price, 'idx': df_m1.index[anchor1_pos] if hasattr(df_m1.index[anchor1_pos], '__iter__') else anchor1_pos},
            {'pos': anchor2_pos, 'price': anchor2_price, 'idx': df_m1.index[anchor2_pos] if hasattr(df_m1.index[anchor2_pos], '__iter__') else anchor2_pos}
        ]
    }

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
        # Thử với RSI strict trước, sau đó linh hoạt hơn nếu không tìm thấy
        swing_highs_all = find_swing_high_with_rsi(df_m1, lookback=5, min_rsi=70)
        swing_highs = [sh for sh in swing_highs_all if sh['index'] < entry_idx]
        
        # Nếu không tìm thấy với RSI > 70, thử với RSI > 60
        if len(swing_highs) == 0:
            print(f"[WARNING] Khong tim thay swing high voi RSI > 70, dang thu voi RSI > 60...")
            swing_highs_all = find_swing_high_with_rsi(df_m1, lookback=5, min_rsi=60)
            swing_highs = [sh for sh in swing_highs_all if sh['index'] < entry_idx]
        
        # Nếu vẫn không tìm thấy, tìm swing high gần nhất mà không cần RSI
        if len(swing_highs) == 0:
            print(f"[WARNING] Khong tim thay swing high voi RSI, dang tim swing high gan nhat...")
            # Tìm swing high đơn giản (không cần RSI)
            swing_highs_simple = []
            lookback = 5
            for i in range(lookback, entry_idx - lookback):
                is_swing_high = True
                for j in range(i - lookback, min(i + lookback + 1, entry_idx)):
                    if j != i and df_m1.iloc[j]['high'] >= df_m1.iloc[i]['high']:
                        is_swing_high = False
                        break
                if is_swing_high:
                    rsi_val = df_m1.iloc[i].get('rsi', None)
                    swing_highs_simple.append({
                        'index': i,
                        'price': df_m1.iloc[i]['high'],
                        'rsi': rsi_val if pd.notna(rsi_val) else None
                    })
            
            if len(swing_highs_simple) > 0:
                swing_highs = swing_highs_simple
                print(f"[INFO] Tim thay {len(swing_highs)} swing high (khong can RSI)")
        
        if len(swing_highs) == 0:
            print(f"[ERROR] Khong tim thay swing high truoc entry")
            mt5.shutdown()
            return
        
        swing_high = swing_highs[-1]  # Lấy swing high gần nhất
        swing_idx = swing_high['index']
        swing_price = swing_high['price']
        rsi_val = swing_high.get('rsi', None)
        
        if rsi_val is not None:
            print(f"[INFO] Swing High: Index={swing_idx}, Price={swing_price:.5f}, RSI={rsi_val:.1f}")
        else:
            print(f"[INFO] Swing High: Index={swing_idx}, Price={swing_price:.5f}, RSI=N/A")
        
        # Vẽ trendline từ swing high đến entry
        # Sử dụng df_m1 gốc với index đúng
        print(f"[DEBUG] Dang tinh trendline: swing_idx={swing_idx}, entry_idx={entry_idx}, khoang cach={entry_idx - swing_idx} nen")
        # Sử dụng hàm với debug logging
        trendline_info = calculate_pullback_trendline_buy_with_debug(df_m1, swing_idx, entry_idx)
        
        if trendline_info is None:
            print(f"[WARNING] Khong the ve trendline")
        else:
            print(f"[OK] Ve duoc trendline voi {len(trendline_info['points'])} diem")
        
    else:  # SELL
        # SELL: Tìm swing low với RSI < 30 trước entry
        # Thử với RSI strict trước, sau đó linh hoạt hơn nếu không tìm thấy
        swing_lows_all = find_swing_low_with_rsi(df_m1, lookback=5, min_rsi=30)
        swing_lows = [sl for sl in swing_lows_all if sl['index'] < entry_idx]
        
        # Nếu không tìm thấy với RSI < 30, thử với RSI < 40
        if len(swing_lows) == 0:
            print(f"[WARNING] Khong tim thay swing low voi RSI < 30, dang thu voi RSI < 40...")
            swing_lows_all = find_swing_low_with_rsi(df_m1, lookback=5, min_rsi=40)
            swing_lows = [sl for sl in swing_lows_all if sl['index'] < entry_idx]
        
        # Nếu vẫn không tìm thấy, tìm swing low gần nhất mà không cần RSI
        if len(swing_lows) == 0:
            print(f"[WARNING] Khong tim thay swing low voi RSI, dang tim swing low gan nhat...")
            # Tìm swing low đơn giản (không cần RSI)
            swing_lows_simple = []
            lookback = 5
            for i in range(lookback, entry_idx - lookback):
                is_swing_low = True
                for j in range(i - lookback, min(i + lookback + 1, entry_idx)):
                    if j != i and df_m1.iloc[j]['low'] <= df_m1.iloc[i]['low']:
                        is_swing_low = False
                        break
                if is_swing_low:
                    rsi_val = df_m1.iloc[i].get('rsi', None)
                    swing_lows_simple.append({
                        'index': i,
                        'price': df_m1.iloc[i]['low'],
                        'rsi': rsi_val if pd.notna(rsi_val) else None
                    })
            
            if len(swing_lows_simple) > 0:
                swing_lows = swing_lows_simple
                print(f"[INFO] Tim thay {len(swing_lows)} swing low (khong can RSI)")
        
        if len(swing_lows) == 0:
            print(f"[ERROR] Khong tim thay swing low truoc entry")
            mt5.shutdown()
            return
        
        swing_low = swing_lows[-1]  # Lấy swing low gần nhất
        swing_idx = swing_low['index']
        swing_price = swing_low['price']
        rsi_val = swing_low.get('rsi', None)
        
        if rsi_val is not None:
            print(f"[INFO] Swing Low: Index={swing_idx}, Price={swing_price:.5f}, RSI={rsi_val:.1f}")
        else:
            print(f"[INFO] Swing Low: Index={swing_idx}, Price={swing_price:.5f}, RSI=N/A")
        
        # Vẽ trendline từ swing low đến entry
        # Sử dụng df_m1 gốc với index đúng
        trendline_info = calculate_pullback_trendline(df_m1, swing_idx, entry_idx)
    
    if trendline_info is None:
        print(f"[ERROR] Khong the ve trendline")
        mt5.shutdown()
        return
    
    # Vẽ biểu đồ
    fig, ax = plt.subplots(figsize=(16, 10))
    
    # Lấy dữ liệu từ swing đến entry + 20 nến sau
    start_idx = max(0, swing_idx - 10)
    end_idx = min(len(df_m1), entry_idx + 20)
    plot_df = df_m1.iloc[start_idx:end_idx].copy()
    plot_df.reset_index(drop=True, inplace=True)
    
    # Vẽ candlestick - Body nhỏ, wick dài để dễ nhìn trendline
    width = 0.3  # Giảm width từ 0.6 xuống 0.3 để body nhỏ hơn
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
        
        # Vẽ body (thân nến) - nhỏ hơn và trong suốt hơn
        body_height = abs(candle['close'] - candle['open'])
        if body_height > 0:
            rect = plt.Rectangle((x_pos - width/2, body_bottom), width, body_height, 
                               facecolor=color, edgecolor='black', linewidth=0.3, alpha=0.5)
            ax.add_patch(rect)
        else:
            # Doji - vẽ đường ngang mỏng
            ax.plot([x_pos - width/2, x_pos + width/2], [candle['close'], candle['close']], 
                   color='black', linewidth=0.5, alpha=0.5)
        
        # Vẽ wick (bấc nến) - dài và rõ hơn
        ax.plot([x_pos, x_pos], [candle['low'], candle['high']], 
               color='black', linewidth=1.0, alpha=0.8, zorder=1)
    
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
    
    # Vẽ entry point
    entry_plot_idx = entry_idx - start_idx
    ax.plot(entry_plot_idx, entry_price, 'g*', markersize=15, label=f'Entry ({order_type})', zorder=10)
    
    # Vẽ SL/TP (nếu có)
    if sl is not None:
        ax.axhline(y=sl, color='r', linestyle='--', linewidth=2, alpha=0.8, label='SL')
    if tp is not None:
        ax.axhline(y=tp, color='g', linestyle='--', linewidth=2, alpha=0.8, label='TP')
    
    # Vẽ trendline (logic Outer Trendline)
    if trendline_info is not None:
        trendline_points = trendline_info['points']
        for i, point in enumerate(trendline_points):
            # point['pos'] là index trong df_m1
            point_pos = point['pos']
            if start_idx <= point_pos < end_idx:
                point_plot_idx = point_pos - start_idx
                anchor_name = "Anchor 1" if i == 0 else "Anchor 2"
                ax.plot(point_plot_idx, point['price'], 'bo', markersize=10, label=f'Trendline Points ({anchor_name})' if i < 2 else '', zorder=5)
        
        # Vẽ đường trendline
        x_trendline = np.arange(swing_idx, entry_idx + 1)
        y_trendline = [trendline_info['func'](i) for i in x_trendline]
        x_trendline_plot = [i - start_idx for i in x_trendline if start_idx <= i < end_idx]
        y_trendline_plot = [trendline_info['func'](i) for i in x_trendline if start_idx <= i < end_idx]
        if len(x_trendline_plot) > 0:
            ax.plot(x_trendline_plot, y_trendline_plot, 'b-', linewidth=3, label='Trendline (Outer)', alpha=0.9, zorder=4)
    
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
    
    if trendline_info is not None:
        trendline_points = trendline_info['points']
        print(f"\n[TRENDLINE - Logic Outer Trendline]")
        print(f"   Tim duoc {len(trendline_points)} diem (Anchor 1 + Anchor 2)")
        for i, point in enumerate(trendline_points):
            point_pos = point['pos']
            time_val = df_m1.iloc[point_pos]['time']
            if hasattr(time_val, 'strftime'):
                time_str = time_val.strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_str = str(time_val)
            anchor_name = "Anchor 1 (Swing High)" if i == 0 else "Anchor 2 (Highest High 15-30)"
            print(f"   {anchor_name}: Index={point_pos}, Time={time_str}, Price={point['price']:.5f}")
        print(f"   Slope={trendline_info['slope']:.8f}, Intercept={trendline_info['intercept']:.5f}")
    else:
        print(f"\n[ERROR] Khong the ve trendline")
    print(f"\nEntry/SL/TP:")
    print(f"   Entry: {entry_price:.5f}")
    if sl is not None:
        print(f"   SL: {sl:.5f}")
    if tp is not None:
        print(f"   TP: {tp:.5f}")
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
# Lấy input từ người dùng: ticket hoặc thời gian
TICKET_NUMBER = get_user_input()

# Nếu có TICKET_NUMBER, vẽ trendline từ ticket
if TICKET_NUMBER is not None:
    draw_trendline_from_ticket(TICKET_NUMBER)
    mt5.shutdown()
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
    ax.plot(x_trendline, y_trendline, 'r-', linewidth=2, label='Trendline', alpha=0.8)
    
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

