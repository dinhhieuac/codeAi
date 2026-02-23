from flask import Flask, render_template, g, request, Response
from datetime import datetime, timedelta
import json
import sqlite3
import os
import csv
import io

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
    cur.execute("SELECT DISTINCT strategy_name FROM orders WHERE strategy_name IS NOT NULL")
    strategies = [row['strategy_name'] for row in cur.fetchall()]
    
    # Debug: Print available strategies
    if not strategies:
        print(f"⚠️ [Dashboard] No strategies found in database")
    else:
        print(f"📊 [Dashboard] Found {len(strategies)} strategies: {strategies}")
    
    bot_stats = []
    
    for strat in strategies:
        # Get trades for this strategy (filtered by time AND with profit)
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
        
        # Format strategy name for display
        if strat.startswith("M1_Scalp_"):
            # Extract symbol from strategy name (e.g., "M1_Scalp_EURUSD" -> "M1 Scalp EURUSD")
            display_name = strat.replace("M1_Scalp_", "M1 Scalp ").replace("_", " ")
        else:
            display_name = strat.replace("Strategy_", "").replace("_", " ")
        
        bot_stats.append({
            "raw_name": strat, # Added for template filtering
            "name": display_name,
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
    # Sort by User Defined Order (1, 4, 2, 5, M1 Scalp)
    desired_order = [
        "Strategy_1_Trend_HA",
        "Strategy_4_UT_Bot",
        "Strategy_2_EMA_ATR", 
        "Strategy_5_Filter_First",
        "M1_Scalp_EURUSD",
        "M1_Scalp_XAUUSD",
        "M1_Scalp_BTCUSD"
    ]
    
    # Filter only requested bots and sort
    # If a strategy is in desired_order, use that order; otherwise append at the end
    bot_stats_filtered = []
    bot_stats_other = []
    
    for bot in bot_stats:
        if bot['raw_name'] in desired_order:
            bot_stats_filtered.append(bot)
        else:
            bot_stats_other.append(bot)
    
    # Sort filtered bots by desired_order
    bot_stats_filtered.sort(key=lambda x: desired_order.index(x['raw_name']))
    # Sort other bots by net profit (descending)
    bot_stats_other.sort(key=lambda x: x['net_profit'], reverse=True)
    
    # Combine: desired_order first, then others
    bot_stats = bot_stats_filtered + bot_stats_other
    
    # Debug: Print bot_stats summary
    print(f"📊 [Dashboard] Generated {len(bot_stats)} bot stats entries")
    for bot in bot_stats:
        print(f"   - {bot['raw_name']}: {bot['trades']} trades, Net Profit: ${bot['net_profit']:.2f}")

    return render_template('index.html', 
                           orders=orders, 
                           signals=signals, 
                           total_trades=total_trades,
                           total_profit=total_profit,
                           win_rate=win_rate,
                           wins=wins,
                           losses=losses,
                           bot_stats=bot_stats,
                           current_filter=days_param,
                           filter_label=filter_label)


@app.route('/export_orders')
def export_orders():
    """Export orders for a specific bot (strategy) as CSV. Uses same days filter as dashboard."""
    strategy = request.args.get('strategy', '').strip()
    if not strategy:
        return "Missing strategy parameter", 400
    days_param = request.args.get('days', '30')
    if days_param == "all":
        days = 36500
    else:
        try:
            days = int(days_param)
        except ValueError:
            days = 30
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
    cur = get_db().cursor()
    cur.execute(
        "SELECT ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, open_time, close_price, profit, comment, account_id FROM orders WHERE strategy_name = ? AND open_time >= ? ORDER BY open_time DESC",
        (strategy, cutoff_str)
    )
    rows = cur.fetchall()
    keys = ['ticket', 'strategy_name', 'symbol', 'order_type', 'volume', 'open_price', 'sl', 'tp', 'open_time', 'close_price', 'profit', 'comment', 'account_id']
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(keys)
    for row in rows:
        writer.writerow([row[k] for k in keys])
    output.seek(0)
    safe_name = strategy.replace(" ", "_").replace("/", "-")
    filename = f"orders_{safe_name}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == '__main__':
    print(f"🚀 Dashboard running on http://127.0.0.1:5005")
    app.run(debug=True, port=5005)
