from flask import Flask, render_template, g
import sqlite3
import os

app = Flask(__name__)
DB_PATH = 'trades.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    cur = get_db().cursor()
    
    # Fetch Orders
    cur.execute("SELECT * FROM orders ORDER BY executed_at DESC")
    orders = cur.fetchall()
    
    # Calculate Stats
    total_trades = len(orders)
    total_profit = sum([o['profit'] for o in orders if o['profit'] is not None])
    wins = len([o for o in orders if o['profit'] is not None and o['profit'] > 0])
    losses = len([o for o in orders if o['profit'] is not None and o['profit'] < 0])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    # Fetch Recent Signals
    cur.execute("SELECT * FROM signals ORDER BY created_at DESC LIMIT 50")
    signals = cur.fetchall()

    return render_template('index.html', 
                           orders=orders, 
                           signals=signals, 
                           total_trades=total_trades,
                           total_profit=total_profit,
                           win_rate=win_rate,
                           wins=wins,
                           losses=losses)

if __name__ == '__main__':
    print(f"🚀 Dashboard running on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
