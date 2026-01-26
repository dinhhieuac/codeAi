
import sqlite3
import json
import os
from datetime import datetime, timedelta

# Connect to DB
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trades.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

STRATEGY_NAME = "Strategy_1_Trend_HA"

print(f"\n🔍 DEEP DIVE LOSS ANALYSIS: {STRATEGY_NAME}")
print("Inferring Exit Reasons from Database records...\n")
print("="*100)

# Get Losing Orders
query_orders = """
SELECT * FROM orders 
WHERE strategy_name = ? AND profit <= 0
ORDER BY open_time DESC
LIMIT 50
"""
cursor.execute(query_orders, (STRATEGY_NAME,))
losing_orders = cursor.fetchall()

if not losing_orders:
    print("✅ No losing trades found!")
    exit()

for order in losing_orders:
    ticket = order['ticket']
    open_time_str = order['open_time']
    db_profit = order['profit']
    order_type = order['order_type']
    open_price = order['open_price']
    close_price = order['close_price']
    sl = order['sl']
    tp = order['tp']
    comment = order['comment']
    
    # Parse DB Time
    try:
        open_time = datetime.strptime(open_time_str, '%Y-%m-%d %H:%M:%S')
    except:
        try:
             open_time = datetime.fromisoformat(open_time_str)
        except:
             pass

    print(f"🔻 TICKET {ticket} | {order_type} | PnL: ${db_profit:.2f} | 🕒 {open_time_str}")

    # --- A. EXIT ANALYSIS (Inferred from DB) ---
    exit_reason = "UNKNOWN"
    notes = []
    
    if close_price:
        # Check distance to SL
        if sl > 0 and abs(close_price - sl) < 0.05: # Within 5 points (0.5 pips)
            exit_reason = "🔴 HIT STOP LOSS"
        elif tp > 0 and abs(close_price - tp) < 0.05:
             exit_reason = "🟢 HIT TAKE PROFIT"
        else:
             exit_reason = "👤 MANUAL / SCRIPT CLOSE"
             notes.append(f"Close Price {close_price} != SL {sl} / TP {tp}")
    else:
        exit_reason = "⚠️ RUNNING / OPEN"

    print(f"   🏦 TRADE REALITY:")
    print(f"      • Entry: {open_price} | Exit: {close_price}")
    print(f"      • SL: {sl} | TP: {tp}")
    print(f"      • Result: {exit_reason}")
    if comment:
        print(f"      • Comment: {comment}")

    # --- B. STRATEGY CONTEXT ANALYSIS ---
    time_lower = (open_time - timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
    time_upper = (open_time + timedelta(seconds=5)).strftime('%Y-%m-%d %H:%M:%S')

    query_sig = """
    SELECT * FROM signals 
    WHERE strategy_name = ? 
    AND timestamp BETWEEN ? AND ?
    ORDER BY timestamp DESC 
    LIMIT 1
    """
    cursor.execute(query_sig, (STRATEGY_NAME, time_lower, time_upper))
    signal = cursor.fetchone()
    
    if signal:
        try:
            indicators = json.loads(signal['indicators'])
            trend = indicators.get('trend', 'N/A')
            rsi = indicators.get('rsi', 0)
            
            print(f"   📊 STRATEGY CONTEXT:")
            print(f"      • Trend: {trend}")
            print(f"      • RSI:   {rsi:.1f}")
            
            # Pattern Recognition
            if order_type == 'BUY' and rsi > 70:
                print("      ⚠️ FAILURE PATTERN: Bought Top (RSI > 70)")
            elif order_type == 'SELL' and rsi < 30:
                print("      ⚠️ FAILURE PATTERN: Sold Bottom (RSI < 30)")
                
        except:
            pass
    else:
        print("   ❌ No Context Logged")
        
    print("-" * 100)

conn.close()

