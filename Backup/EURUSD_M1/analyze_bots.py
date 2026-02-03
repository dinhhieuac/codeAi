import sqlite3
import pandas as pd
import os

# Connect to DB
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trades.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Query
query = """
SELECT 
    strategy_name,
    COUNT(*) as total_trades,
    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losses,
    SUM(profit) as total_profit
FROM orders
WHERE profit IS NOT NULL
GROUP BY strategy_name
ORDER BY total_profit DESC
"""

try:
    cursor.execute(query)
    rows = cursor.fetchall()
    
    print("\n==================================================")
    print(" 🤖 BOT PERFORMANCE BREAKDOWN")
    print("==================================================")
    
    if not rows:
        print("No closed trades found.")
    else:
        # Header
        print(f"{'Strategy':<25} | {'Trades':<6} | {'Win%':<6} | {'PF':<5} | {'Avg Win':<8} | {'Avg Loss':<8} | {'PnL ($)':<10}")
        print("-" * 100)
        
        for row in rows:
            strategy_raw, total, wins, losses, profit = row
            
            # Additional Queries for Advanced Stats
            cursor.execute("SELECT AVG(profit) FROM orders WHERE strategy_name=? AND profit > 0", (strategy_raw,))
            avg_win = cursor.fetchone()[0] or 0.0
            
            cursor.execute("SELECT AVG(profit) FROM orders WHERE strategy_name=? AND profit < 0", (strategy_raw,))
            avg_loss = cursor.fetchone()[0] or 0.0 # Will be negative
            
            cursor.execute("SELECT SUM(profit) FROM orders WHERE strategy_name=? AND profit > 0", (strategy_raw,))
            gross_profit = cursor.fetchone()[0] or 0.0
            
            cursor.execute("SELECT SUM(profit) FROM orders WHERE strategy_name=? AND profit < 0", (strategy_raw,))
            gross_loss = abs(cursor.fetchone()[0] or 0.0)
            
            # Metrics
            total = total or 0
            wins = wins or 0
            profit = profit or 0.0
            win_rate = (wins / total * 100) if total > 0 else 0
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.9 # Infinite
            
            name = strategy_raw.replace("Strategy_", "").replace("_", " ")
            name = (name[:22] + '..') if len(name) > 22 else name
            
            print(f"{name:<25} | {total:<6} | {win_rate:5.1f}% | {profit_factor:<5.2f} | ${avg_win:<7.2f} | ${avg_loss:<7.2f} | ${profit:<9.2f}")
            
    print("==================================================\n")

except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
