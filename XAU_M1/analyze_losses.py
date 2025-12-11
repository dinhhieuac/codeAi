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

print(f"\n🔍 ANALYZING LOSSES FOR: {STRATEGY_NAME}\n" + "="*80)

# 1. Get Losing Orders
query_orders = """
SELECT * FROM orders 
WHERE strategy_name = ? AND profit <= 0
ORDER BY open_time DESC
LIMIT 50
"""
cursor.execute(query_orders, (STRATEGY_NAME,))
losing_orders = cursor.fetchall()

if not losing_orders:
    print("✅ No losing trades found (or no data)!")
    exit()

print(f"Found {len(losing_orders)} losing/breakeven trades. Digging into context...\n")

for order in losing_orders:
    ticket = order['ticket']
    open_time_str = order['open_time']
    profit = order['profit']
    order_type = order['order_type']
    
    # Convert string time to object
    try:
        # DB format usually: '2025-12-10 09:00:00'
        open_time = datetime.strptime(open_time_str, '%Y-%m-%d %H:%M:%S')
    except:
        # Try ISO format if needed
        try:
            open_time = datetime.fromisoformat(open_time_str)
        except:
            print(f"⚠️ Time parse error for {open_time_str}")
            continue

    # 2. Find closest Signal (Context)
    # Look for a signal within 30 seconds BEFORE the order
    # Signal string format needs matching match
    
    # We need to query range
    time_lower = (open_time - timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
    time_upper = (open_time + timedelta(seconds=5)).strftime('%Y-%m-%d %H:%M:%S') # Allow small drift forward?

    query_sig = """
    SELECT * FROM signals 
    WHERE strategy_name = ? 
    AND timestamp BETWEEN ? AND ?
    ORDER BY timestamp DESC 
    LIMIT 1
    """
    cursor.execute(query_sig, (STRATEGY_NAME, time_lower, time_upper))
    signal = cursor.fetchone()
    
    print(f"🔻 Ticket {ticket} | {order_type} | PnL: ${profit:.2f} | 🕒 {open_time_str}")
    
    if signal:
        try:
            indicators = json.loads(signal['indicators'])
            # Strategy 1 Indicators: trend, ha_close, sl_mode, rsi
            trend = indicators.get('trend', 'N/A')
            rsi = indicators.get('rsi', 0)
            ha_close = indicators.get('ha_close', 0)
            
            print(f"   📊 Context at Entry:")
            print(f"      • Trend: {trend}")
            print(f"      • RSI:   {rsi:.1f} (Was it Overbought/Oversold?)")
            
            # Auto-Analysis
            if order_type == 'BUY':
                if rsi > 70:
                    print("      ⚠️ WARNING: Bought when RSI was high (>70). Potential Top?")
                if trend == 'BEARISH': # Should not happen if logic works
                    print("      ⚠️ CRITICAL: Bought against Bearish Trend!")
            elif order_type == 'SELL':
                if rsi < 30:
                    print("      ⚠️ WARNING: Sold when RSI was low (<30). Potential Bottom?")
                if trend == 'BULLISH':
                    print("      ⚠️ CRITICAL: Sold against Bullish Trend!")
                    
        except Exception as e:
            print(f"   ⚠️ Error parsing indicators: {e}")
            print(f"   Raw: {signal['indicators']}")
    else:
        print("   ❌ No Signal Data found (Manual trade or DB missed signal log)")
        
    print("-" * 80)

conn.close()
