from flask import Flask, render_template, g, request
from datetime import datetime, timedelta
import json
import sqlite3
import os

app = Flask(__name__)
# Use absolute path to ensure we always find the correct trades.db
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trades.db')

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
    
    # Get Filter Parameter
    days_param = request.args.get('days', '30') # Default 30 days
    if days_param == "all":
        days = 36500 # 100 years approx
        filter_label = "All Time"
    else:
        try:
            days = int(days_param)
            filter_label = f"Last {days} Days"
        except:
            days = 30
            filter_label = "Last 30 Days"
            
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")

    # Fetch Orders Filtered by Time
    cur.execute("SELECT * FROM orders WHERE open_time >= ? ORDER BY open_time DESC", (cutoff_str,))
    orders = cur.fetchall()
    
    # Calculate Stats
    total_trades = len(orders)
    total_profit = sum([o['profit'] for o in orders if o['profit'] is not None])
    wins = len([o for o in orders if o['profit'] is not None and o['profit'] > 0])
    losses = len([o for o in orders if o['profit'] is not None and o['profit'] < 0])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    # Fetch Recent Signals
    cur.execute("SELECT * FROM signals ORDER BY timestamp DESC LIMIT 50")
    signals = cur.fetchall()

    # --- ADVANCED STATS PER STRATEGY ---
    cur.execute("SELECT DISTINCT strategy_name FROM orders")
    strategies = [row['strategy_name'] for row in cur.fetchall()]
    
    bot_stats = []
    
    for strat in strategies:
        # Get trades for this strategy
        s_orders = [o for o in orders if o['strategy_name'] == strat and o['profit'] is not None]
        
        s_total = len(s_orders)
        if s_total == 0: continue
        
        s_wins = [o for o in s_orders if o['profit'] > 0]
        s_losses = [o for o in s_orders if o['profit'] < 0]
        
        s_gross_profit = sum([o['profit'] for o in s_wins])
        s_gross_loss = abs(sum([o['profit'] for o in s_losses]))
        s_net_profit = sum([o['profit'] for o in s_orders])
        
        s_avg_win = (s_gross_profit / len(s_wins)) if s_wins else 0.0
        s_avg_loss = (s_gross_loss / len(s_losses)) if s_losses else 0.0 # Positive number for display
        
        pf = (s_gross_profit / s_gross_loss) if s_gross_loss > 0 else 99.9
        win_rate = (len(s_wins) / s_total) * 100
        
        bot_stats.append({
            "raw_name": strat, # Added for template filtering
            "name": strat.replace("Strategy_", "").replace("_", " "),
            "trades": s_total,
            "win_rate": win_rate,
            "pf": pf,
            "avg_win": s_avg_win,
            "avg_loss": -s_avg_loss, # Make negative for display
            "net_profit": s_net_profit,
            "chart_data": [] # Placeholder
        })
        
        # Calculate Equity Curve for this strategy
        # Sort orders ascending by time for chart
        chart_orders = sorted(s_orders, key=lambda x: x['open_time'])
        equity = 0
        points = []
        for o in chart_orders:
            equity += o['profit']
            points.append({
                'x': o['open_time'],
                'y': equity
            })
        
        # Update the last added bot_stats entry with chart data
        bot_stats[-1]['chart_data'] = points
        
    # Sort by Net Profit
    # Sort by User Defined Order (1, 4, 2, 5)
    desired_order = [
        "Strategy_1_Trend_HA",
        "Strategy_4_UT_Bot",
        "Strategy_2_EMA_ATR", 
        "Strategy_5_Filter_First"
    ]
    
    # Filter only requested bots and sort
    bot_stats = [b for b in bot_stats if b['raw_name'] in desired_order]
    bot_stats.sort(key=lambda x: desired_order.index(x['raw_name']))

    # --- HOURLY STATS (VIETNAM TIME) ---
    hourly_stats = process_hourly_stats(orders)

    return render_template('index.html', 
                           orders=orders, 
                           signals=signals, 
                           total_trades=total_trades,
                           total_profit=total_profit,
                           win_rate=win_rate,
                           wins=wins,
                           losses=losses,
                           bot_stats=bot_stats,
                           hourly_stats=hourly_stats,
                           current_filter=days_param,
                           filter_label=filter_label)

def process_hourly_stats(orders):
    """
    Aggregate trade stats by hour of day (Vietnam Time UTC+7).
    """
    stats = {}
    # Initialize 0-23 hours
    for h in range(24):
        stats[h] = {
            'hour': h,
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'profit': 0.0
        }
        
    for order in orders:
        if order['profit'] is None:
            continue
            
        try:
            # Parse open_time (UTC)
            # Ensure format matches DB string
            # Example: 2025-12-10 06:10:02
            utc_time = datetime.strptime(order['open_time'], "%Y-%m-%d %H:%M:%S")
            
            # Convert to Vietnam Time (UTC+7)
            vn_time = utc_time + timedelta(hours=7)
            hour = vn_time.hour
            
            stats[hour]['trades'] += 1
            stats[hour]['profit'] += order['profit']
            if order['profit'] > 0:
                stats[hour]['wins'] += 1
            elif order['profit'] < 0:
                stats[hour]['losses'] += 1
                
        except Exception as e:
            print(f"Error processing time for order {order['ticket']}: {e}")
            continue
            
    # Calculate Win Rate and convert to list
    result = []
    for h in range(24):
        s = stats[h]
        total = s['trades']
        win_rate = (s['wins'] / total * 100) if total > 0 else 0
        s['win_rate'] = win_rate
        result.append(s)
        
    return result

def format_vn_time(value):
    """
    Convert UTC string or datetime to Vietnam Time string (UTC+7).
    """
    if not value:
        return ""
    
    try:
        # If it's already a string, parse it
        if isinstance(value, str):
            # Try parsing with seconds
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # Try parsing without seconds or other formats if needed
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
        else:
            dt = value
            
        # Add 7 hours
        vn_time = dt + timedelta(hours=7)
        res = vn_time.strftime("%Y-%m-%d %H:%M:%S")
        # print(f"DEBUG: Converted {value} -> {res}", flush=True)
        return res
    except Exception as e:
        print(f"DEBUG: Error parsing '{value}': {e}")
        return value # Return original on error

# Register Jinja2 filter
app.jinja_env.filters['to_vn_time'] = format_vn_time

if __name__ == '__main__':
    print(f"🚀 Dashboard running on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
