import sqlite3
import os
import sys
from datetime import datetime

# Set database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trades.db')

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def view_data():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at: {DB_PATH}")
        return

    print(f"📂 Connecting to database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    cur = conn.cursor()

    try:
        # 1. Account Stats from Orders
        cur.execute("SELECT * FROM orders")
        orders = cur.fetchall()
        
        total_trades = len(orders)
        closed_trades = [o for o in orders if o['profit'] is not None]
        total_profit = sum([o['profit'] for o in closed_trades])
        wins = len([o for o in closed_trades if o['profit'] > 0])
        losses = len([o for o in closed_trades if o['profit'] < 0])
        win_rate = (wins / len(closed_trades) * 100) if len(closed_trades) > 0 else 0.0

        print("\n" + "="*50)
        print(" 📊 ACCOUNT STATISTICS")
        print("="*50)
        print(f" Total Trades Logged: {total_trades}")
        print(f" Closed Trades:       {len(closed_trades)}")
        print(f" Net Profit:          ${total_profit:.2f}")
        print(f" Win Rate:            {win_rate:.1f}%")
        print(f" Wins / Losses:       {wins} / {losses}")

        # 2. Recent Signals
        print("\n" + "="*50)
        print(" 📡 LAST 10 SIGNALS")
        print("="*50)
        print(f"{'Time':<20} | {'Strat':<20} | {'Symbol':<8} | {'Type':<4} | {'Price':<8} | {'Info'}")
        print("-" * 100)
        
        cur.execute("SELECT * FROM signals ORDER BY timestamp DESC LIMIT 10")
        signals = cur.fetchall()
        
        if not signals:
            print(" (No signals found)")
        else:
            for sig in signals:
                # Truncate strategy name
                strat = (sig['strategy_name'][:18] + '..') if len(sig['strategy_name']) > 18 else sig['strategy_name']
                info = (sig['indicators'][:30] + '..') if sig['indicators'] and len(sig['indicators']) > 30 else sig['indicators']
                print(f"{sig['timestamp']:<20} | {strat:<20} | {sig['symbol']:<8} | {sig['signal_type']:<4} | {sig['price']:<8} | {info}")

        # 3. Recent Orders
        print("\n" + "="*50)
        print(" 📝 LAST 10 EXECUTED ORDERS")
        print("="*50)
        print(f"{'Ticket':<10} | {'Time':<20} | {'Strat':<20} | {'Type':<4} | {'Price':<8} | {'Profit'}")
        print("-" * 100)
        
        cur.execute("SELECT * FROM orders ORDER BY open_time DESC LIMIT 10")
        recent_orders = cur.fetchall()
        
        if not recent_orders:
             print(" (No orders found)")
        else:
            for order in recent_orders:
                strat = (order['strategy_name'][:18] + '..') if len(order['strategy_name']) > 18 else order['strategy_name']
                
                type_str = order.get('order_type', '???')
                profit_str = f"{order['profit']:.2f}" if order['profit'] is not None else "---"
                print(f"{order['ticket']:<10} | {order['open_time']:<20} | {strat:<20} | {type_str:<4} | {order['open_price']:<8} | {profit_str}")


    except Exception as e:
        print(f"❌ Error querying database: {e}")
    finally:
        conn.close()
        print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    view_data()
