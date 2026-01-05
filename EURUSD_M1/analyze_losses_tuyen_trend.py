import MetaTrader5 as mt5
import sys
import sqlite3
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import time

# Import local modules
sys.path.append('..')
from utils import load_config, connect_mt5, get_data, calculate_rsi, get_pip_size

STRATEGY_NAME = "Tuyen_Trend"
CONFIG_FILE = "config_tuyen_trend.json"  # Adjust based on actual config file name
SYMBOL_DISPLAY = "EURUSD"

def analyze_order_loss(ticket, order_type, open_time_str, open_price, sl, tp, close_price, profit):
    """
    Phân tích một lệnh thua để xác định tại sao thua
    Note: Tuyen_Trend strategy có nhiều sub-strategies phức tạp.
    File này cung cấp phân tích cơ bản, có thể mở rộng thêm.
    """
    print(f"\n{'='*100}")
    print(f"🔻 TICKET: {ticket} | {order_type} | Entry: {open_price:.5f} | SL: {sl:.5f} | TP: {tp:.5f}")
    print(f"   Close: {close_price:.5f} | Profit: ${profit:.2f} | Entry Time: {open_time_str}")
    print(f"{'='*100}")
    
    # Parse entry time
    try:
        entry_time = datetime.strptime(open_time_str, '%Y-%m-%d %H:%M:%S')
    except:
        try:
            entry_time = datetime.fromisoformat(open_time_str.replace('Z', '+00:00'))
        except:
            print(f"❌ Cannot parse time: {open_time_str}")
            return
    
    entry_timestamp = entry_time.timestamp()
    
    # Get symbol from config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Try to find config file
    possible_configs = ["config_tuyen_trend.json", "config_tuyen.json"]
    config = None
    for cfg_file in possible_configs:
        config_path = os.path.join(script_dir, "configs", cfg_file)
        if os.path.exists(config_path):
            config = load_config(config_path)
            break
    
    if not config:
        print(f"❌ Cannot find config file")
        return
    
    symbol = config.get('symbol', 'EURUSD')
    
    # Get data at entry time
    from_time = datetime.fromtimestamp(entry_timestamp) - timedelta(hours=10)
    from_timestamp = int(from_time.timestamp())
    
    # Fetch M1, M5, H1 data
    rates_m1 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M1, from_timestamp, 300)
    rates_m5 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M5, from_timestamp, 300)
    rates_h1 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_H1, from_timestamp, 200)
    
    if rates_m1 is None or len(rates_m1) == 0 or rates_m5 is None or len(rates_m5) == 0:
        print(f"❌ Cannot get M1/M5 data for entry time")
        return
    
    df_m1 = pd.DataFrame(rates_m1)
    df_m1['time'] = pd.to_datetime(df_m1['time'], unit='s')
    df_m5 = pd.DataFrame(rates_m5)
    df_m5['time'] = pd.to_datetime(df_m5['time'], unit='s')
    df_h1 = pd.DataFrame(rates_h1) if rates_h1 is not None and len(rates_h1) > 0 else None
    if df_h1 is not None:
        df_h1['time'] = pd.to_datetime(df_h1['time'], unit='s')
    
    # Find entry candle
    entry_idx_m1 = None
    for i in range(len(df_m1) - 1, -1, -1):
        if df_m1.iloc[i]['time'] <= entry_time:
            entry_idx_m1 = i
            break
    
    if entry_idx_m1 is None:
        print(f"❌ Cannot find M1 candle for entry time")
        return
    
    df_m1_entry = df_m1.iloc[:entry_idx_m1+1].copy()
    df_m5_entry = df_m5[df_m5['time'] <= entry_time].copy()
    df_h1_entry = df_h1[df_h1['time'] <= entry_time].copy() if df_h1 is not None else None
    
    if len(df_m1_entry) < 200 or len(df_m5_entry) < 200:
        print(f"❌ Not enough data for indicators")
        return
    
    # Calculate basic indicators
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
    
    df_m1_entry['ema21'] = calculate_ema(df_m1_entry['close'], 21)
    df_m1_entry['ema50'] = calculate_ema(df_m1_entry['close'], 50)
    df_m1_entry['ema200'] = calculate_ema(df_m1_entry['close'], 200)
    df_m1_entry['atr'] = calculate_atr(df_m1_entry, 14)
    df_m1_entry['rsi'] = calculate_rsi(df_m1_entry['close'], 14)
    
    df_m5_entry['ema200'] = calculate_ema(df_m5_entry['close'], 200)
    
    # Analyze conditions
    print(f"\n📊 [PHÂN TÍCH ĐIỀU KIỆN TẠI THỜI ĐIỂM ENTRY]")
    print(f"{'─'*100}")
    
    issues = []
    passed_conditions = []
    
    curr_candle = df_m1_entry.iloc[-1]
    ema50_val = curr_candle['ema50']
    ema200_val = curr_candle['ema200']
    atr_val = curr_candle['atr']
    
    # Check M5 Trend
    m5_trend = "BULLISH" if df_m5_entry.iloc[-1]['close'] > df_m5_entry.iloc[-1]['ema200'] else "BEARISH"
    if order_type == "BUY":
        if m5_trend != "BULLISH":
            issues.append(f"❌ M5 Trend: {m5_trend} (cần BULLISH)")
        else:
            passed_conditions.append(f"✅ M5 Trend: BULLISH")
    else:
        if m5_trend != "BEARISH":
            issues.append(f"❌ M5 Trend: {m5_trend} (cần BEARISH)")
        else:
            passed_conditions.append(f"✅ M5 Trend: BEARISH")
    
    # Check EMA200 Filter
    if order_type == "BUY":
        if curr_candle['close'] <= ema200_val:
            issues.append(f"❌ EMA200 Filter: Price ({curr_candle['close']:.5f}) <= EMA200 ({ema200_val:.5f})")
        else:
            passed_conditions.append(f"✅ EMA200 Filter: Price > EMA200")
    else:
        if curr_candle['close'] >= ema200_val:
            issues.append(f"❌ EMA200 Filter: Price ({curr_candle['close']:.5f}) >= EMA200 ({ema200_val:.5f})")
        else:
            passed_conditions.append(f"✅ EMA200 Filter: Price < EMA200")
    
    # Display results
    print(f"\n✅ ĐIỀU KIỆN ĐẠT ({len(passed_conditions)}/{len(passed_conditions) + len(issues)}):")
    for cond in passed_conditions:
        print(f"   {cond}")
    
    if issues:
        print(f"\n❌ ĐIỀU KIỆN KHÔNG ĐẠT ({len(issues)}):")
        for issue in issues:
            print(f"   {issue}")
    
    # Check exit reason
    print(f"\n🏦 PHÂN TÍCH EXIT:")
    symbol_info = mt5.symbol_info(symbol)
    pip_size = get_pip_size(symbol, symbol_info)
    
    if close_price:
        sl_distance = abs(close_price - sl) if sl > 0 else 999
        tp_distance = abs(close_price - tp) if tp > 0 else 999
        sl_distance_pips = sl_distance / pip_size if pip_size > 0 else 0
        
        if sl > 0 and sl_distance_pips < 0.5:
            print(f"   🔴 HIT STOP LOSS: Close {close_price:.5f} ≈ SL {sl:.5f} (distance: {sl_distance_pips:.1f} pips)")
        elif tp > 0 and tp_distance / pip_size < 0.5:
            print(f"   🟢 HIT TAKE PROFIT: Close {close_price:.5f} ≈ TP {tp:.5f}")
        else:
            print(f"   👤 MANUAL/SCRIPT CLOSE: Close {close_price:.5f} (SL: {sl:.5f}, TP: {tp:.5f})")
    else:
        print(f"   ⚠️ RUNNING/OPEN")
    
    # Summary
    print(f"\n💡 TÓM TẮT:")
    if len(issues) > 0:
        print(f"   ⚠️ Lệnh vào khi có {len(issues)} điều kiện không đạt!")
    else:
        print(f"   ✅ Điều kiện cơ bản đạt tại entry")
        print(f"   🤔 Có thể do: SL quá chặt, market reversal, hoặc false breakout")
    
    # Display indicator values
    print(f"\n📊 GIÁ TRỊ INDICATORS TẠI ENTRY:")
    print(f"   💱 Entry Price: {open_price:.5f}")
    print(f"   📈 M5 Trend: {m5_trend}")
    print(f"   📊 EMA50: {ema50_val:.5f} | EMA200: {ema200_val:.5f}")
    current_rsi = curr_candle.get('rsi', 0)
    if pd.notna(current_rsi):
        print(f"   📊 RSI(M1): {current_rsi:.1f}")
    print(f"   📊 ATR: {atr_val:.5f}")
    print(f"   🛑 SL: {sl:.5f} | 🎯 TP: {tp:.5f}")
    if order_type == "BUY":
        sl_distance_pips = (open_price - sl) / pip_size if sl > 0 and pip_size > 0 else 0
    else:
        sl_distance_pips = (sl - open_price) / pip_size if sl > 0 and pip_size > 0 else 0
    print(f"   📏 SL Distance: {sl_distance_pips:.1f} pips")
    
    print(f"\n⚠️ LƯU Ý: Tuyen_Trend có nhiều sub-strategies phức tạp.")
    print(f"   File này chỉ phân tích điều kiện cơ bản. Có thể mở rộng thêm.")

def analyze_order_loss_with_stats(ticket, order_type, open_time_str, open_price, sl, tp, close_price, profit):
    """
    Phân tích một lệnh thua và trả về statistics
    """
    stats = {
        'ticket': ticket,
        'order_type': order_type,
        'profit': profit,
        'issues': [],
        'passed_conditions': [],
        'exit_reason': 'UNKNOWN',
        'sl_distance_pips': 0,
        'indicators': {}
    }
    
    # Similar logic to analyze_order_loss but return stats dict
    # (Implementation similar to M1_Scalp version but simplified)
    
    return stats

def generate_summary_report(all_stats, output_file):
    """
    Tạo file tổng kết với đề xuất cải thiện
    """
    # Similar to M1_Scalp version but adapted for Tuyen_Trend
    pass

def main():
    # Connect to database
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, 'trades.db')
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get total count of losing orders
    count_query = """
    SELECT COUNT(*) as total FROM orders 
    WHERE strategy_name = ? AND profit IS NOT NULL AND profit < 0
    """
    cursor.execute(count_query, (STRATEGY_NAME,))
    total_losing = cursor.fetchone()['total']
    
    if total_losing == 0:
        print(f"✅ Không có lệnh thua nào cho {STRATEGY_NAME}")
        conn.close()
        return
    
    print(f"\n{'='*100}")
    print(f"🔍 PHÂN TÍCH LỆNH THUA: {STRATEGY_NAME} ({SYMBOL_DISPLAY})")
    print(f"{'='*100}")
    print(f"📊 Tổng số lệnh thua trong database: {total_losing}")
    print(f"{'='*100}\n")
    
    while True:
        try:
            num_orders_input = input(f"📝 Nhập số lệnh thua muốn phân tích (1-{total_losing}, Enter để phân tích tất cả): ").strip()
            
            if num_orders_input == "":
                num_orders = total_losing
                print(f"✅ Sẽ phân tích tất cả {num_orders} lệnh thua\n")
                break
            else:
                num_orders = int(num_orders_input)
                if num_orders < 1:
                    print(f"❌ Số lệnh phải >= 1")
                    continue
                elif num_orders > total_losing:
                    print(f"❌ Số lệnh ({num_orders}) vượt quá tổng số lệnh thua ({total_losing})")
                    num_orders = total_losing
                    break
                else:
                    print(f"✅ Sẽ phân tích {num_orders} lệnh thua gần nhất\n")
                    break
        except ValueError:
            print(f"❌ Vui lòng nhập số hợp lệ")
            continue
        except KeyboardInterrupt:
            print(f"\n❌ Đã hủy")
            conn.close()
            return
    
    # Get losing orders
    query = """
    SELECT * FROM orders 
    WHERE strategy_name = ? AND profit IS NOT NULL AND profit < 0
    ORDER BY open_time DESC
    LIMIT ?
    """
    cursor.execute(query, (STRATEGY_NAME, num_orders))
    losing_orders = cursor.fetchall()
    
    if not losing_orders:
        print(f"✅ Không có lệnh thua nào để phân tích")
        conn.close()
        return
    
    print(f"{'='*100}")
    print(f"📊 Số lệnh sẽ phân tích: {len(losing_orders)}")
    print(f"{'='*100}\n")
    
    # Load config and connect to MT5
    possible_configs = ["config_tuyen_trend.json", "config_tuyen.json"]
    config = None
    for cfg_file in possible_configs:
        config_path = os.path.join(script_dir, "configs", cfg_file)
        if os.path.exists(config_path):
            config = load_config(config_path)
            break
    
    if not config:
        print(f"❌ Cannot find config file")
        conn.close()
        return
    
    if not connect_mt5(config):
        print(f"❌ Cannot connect to MT5")
        conn.close()
        return
    
    print(f"✅ Connected to MT5 Account: {config.get('account', 'N/A')}\n")
    
    # Analyze each losing order
    for idx, order in enumerate(losing_orders, 1):
        print(f"\n\n{'#'*100}")
        print(f"# LỆNH THUA {idx}/{len(losing_orders)}")
        print(f"{'#'*100}")
        
        analyze_order_loss(
            ticket=order['ticket'],
            order_type=order['order_type'],
            open_time_str=order['open_time'],
            open_price=order['open_price'],
            sl=order['sl'],
            tp=order['tp'],
            close_price=order['close_price'],
            profit=order['profit']
        )
        
        if len(losing_orders) > 1 and idx < len(losing_orders):
            time.sleep(0.5)
    
    print(f"\n\n{'='*100}")
    print(f"📊 TỔNG KẾT")
    print(f"{'='*100}")
    print(f"Tổng số lệnh thua đã phân tích: {len(losing_orders)}")
    print(f"{'='*100}\n")
    
    conn.close()
    mt5.shutdown()

if __name__ == "__main__":
    main()
