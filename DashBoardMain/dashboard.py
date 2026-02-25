from flask import Flask, render_template, g, request, jsonify, Response
from datetime import datetime, timedelta
import json
import sqlite3
import os
import csv
import io

# Use absolute path for templates folder
dashboard_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(dashboard_dir, 'templates')
app = Flask(__name__, template_folder=templates_dir)

# --- Databases config: multiple tabs (key -> path) ---
def _load_databases_config():
    """Load config.json. Returns (db_map: dict key->abs_path, default_key: str)."""
    config_path = os.path.join(dashboard_dir, 'config.json')
    db_map = {}
    default_key = None
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            if cfg.get('databases') and isinstance(cfg['databases'], dict):
                for key, path in cfg['databases'].items():
                    path = (path or '').strip()
                    if not path:
                        continue
                    if not os.path.isabs(path):
                        path = os.path.normpath(os.path.join(dashboard_dir, path))
                    db_map[str(key)] = path
                default_key = (cfg.get('default') or '').strip() or (list(db_map.keys())[0] if db_map else None)
                if default_key not in db_map:
                    default_key = list(db_map.keys())[0] if db_map else None
            else:
                path = (cfg.get('db_path') or '').strip() or os.environ.get('TRADES_DB_PATH', '')
                if not path:
                    path = os.path.join(dashboard_dir, 'trades.db')
                elif not os.path.isabs(path):
                    path = os.path.normpath(os.path.join(dashboard_dir, path))
                db_map['Default'] = path
                default_key = 'Default'
        except Exception as e:
            print(f"⚠️ Could not load config.json: {e}")
    if not db_map:
        db_map['Default'] = os.path.join(dashboard_dir, 'trades.db')
        default_key = 'Default'
    return db_map, default_key

DB_MAP, DEFAULT_DB_KEY = _load_databases_config()
print(f"📦 Dashboard tabs: {list(DB_MAP.keys())}, default={DEFAULT_DB_KEY}")

@app.before_request
def _set_request_db():
    """Set current DB for this request from ?db= key."""
    key = request.args.get('db', '').strip() or DEFAULT_DB_KEY
    if key not in DB_MAP:
        key = DEFAULT_DB_KEY
    g._current_db = key
    g._db_path = DB_MAP[key]

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(g._db_path)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def _parse_date_range(from_date_str, to_date_str):
    """Parse from_date and to_date (YYYY-MM-DD). Return (cutoff_utc, end_utc, filter_label) or None if invalid."""
    try:
        from_d = datetime.strptime(from_date_str.strip(), "%Y-%m-%d")
        to_d = datetime.strptime(to_date_str.strip(), "%Y-%m-%d")
        if from_d > to_d:
            return None
        # VN = UTC+7 => UTC = VN - 7
        start_vn = from_d.replace(hour=0, minute=0, second=0, microsecond=0)
        end_vn = to_d.replace(hour=23, minute=59, second=59, microsecond=999999)
        cutoff_utc = start_vn - timedelta(hours=7)
        end_utc = end_vn - timedelta(hours=7)
        end_str = end_utc.strftime("%Y-%m-%d %H:%M:%S")
        return (cutoff_utc, end_str, f"{from_date_str} → {to_date_str}")
    except (ValueError, AttributeError):
        return None


@app.route('/')
def index():
    cur = get_db().cursor()
    
    from_date_param = request.args.get('from_date', '').strip()
    to_date_param = request.args.get('to_date', '').strip()
    days_param = request.args.get('days', '30')
    
    # Priority: custom date range if both from_date and to_date are provided
    if from_date_param and to_date_param:
        parsed = _parse_date_range(from_date_param, to_date_param)
        if parsed:
            cutoff_date, end_str, filter_label = parsed
            cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
            current_filter = 'range'
            cur.execute(
                "SELECT * FROM orders WHERE open_time >= ? AND open_time <= ? ORDER BY open_time DESC",
                (cutoff_str, end_str)
            )
            orders = cur.fetchall()
            cur.execute(
                "SELECT * FROM signals WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 50",
                (cutoff_str, end_str)
            )
            signals = cur.fetchall()
        else:
            # invalid range, fallback to days
            from_date_param = ''
            to_date_param = ''
            parsed = None
    else:
        parsed = None
    
    if parsed is None:
        # Get Filter Parameter (days or all)
        if days_param == "all":
            cutoff_date = datetime(2000, 1, 1)
            filter_label = "All Time"
            current_filter = "all"
        else:
            try:
                days = int(days_param)
                if days == 1:
                    filter_label = "Today"
                else:
                    filter_label = f"Last {days} Days"
            except Exception:
                days = 30
                filter_label = "Last 30 Days"
            now_vn = datetime.utcnow() + timedelta(hours=7)
            start_of_today_vn = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
            start_date_vn = start_of_today_vn - timedelta(days=days - 1)
            cutoff_date = start_date_vn - timedelta(hours=7)
            current_filter = days_param
        
        cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT * FROM orders WHERE open_time >= ? ORDER BY open_time DESC", (cutoff_str,))
        orders = cur.fetchall()
        cur.execute("SELECT * FROM signals WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 50", (cutoff_str,))
        signals = cur.fetchall()
    
    # Calculate Stats
    total_trades = len(orders)
    total_profit = sum([o['profit'] for o in orders if o['profit'] is not None])
    wins = len([o for o in orders if o['profit'] is not None and o['profit'] > 0])
    losses = len([o for o in orders if o['profit'] is not None and o['profit'] < 0])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    # --- ADVANCED STATS PER STRATEGY ---
    # Auto-detect all strategies from database
    cur.execute("SELECT DISTINCT strategy_name FROM orders WHERE strategy_name IS NOT NULL AND strategy_name != ''")
    strategies = [row['strategy_name'] for row in cur.fetchall()]
    
    # Optional: Load display order from config file (if exists)
    # This allows custom ordering without hardcoding in code
    display_order_config = load_display_order_config()
    
    bot_stats = []
    
    # Get last 30 days data for Daily PNL Calendar (independent of filter)
    now_vn_30d = datetime.utcnow() + timedelta(hours=7)
    start_of_today_vn_30d = now_vn_30d.replace(hour=0, minute=0, second=0, microsecond=0)
    start_date_vn_30d = start_of_today_vn_30d - timedelta(days=29)  # 30 days including today
    cutoff_date_30d = start_date_vn_30d - timedelta(hours=7)
    cutoff_str_30d = cutoff_date_30d.strftime("%Y-%m-%d %H:%M:%S")
    
    # Fetch orders for last 30 days for Daily PNL
    cur.execute("SELECT * FROM orders WHERE open_time >= ? AND profit IS NOT NULL ORDER BY open_time DESC", (cutoff_str_30d,))
    orders_30d = cur.fetchall()
    
    for strat in strategies:
        # Get trades for this strategy (using filtered orders for stats)
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
        
        # Auto-format strategy name for display
        display_name = format_strategy_name(strat)
        
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
        
        # Calculate Daily PNL Calendar for this strategy (always last 30 days)
        s_orders_30d = [o for o in orders_30d if o['strategy_name'] == strat]
        daily_pnl = process_daily_pnl(s_orders_30d)
        bot_stats[-1]['daily_pnl'] = daily_pnl

        # Win/Loss by hour (Vietnam time) for this bot
        bot_stats[-1]['hourly_win_loss'] = process_hourly_stats(s_orders)

        # Win/Loss by RSI and ADX buckets (from closest signal indicators)
        orders_with_indicators = fetch_orders_with_indicators(cur, strat, s_orders)
        bot_stats[-1]['rsi_win_loss'] = process_rsi_bucket_stats(orders_with_indicators)
        bot_stats[-1]['adx_win_loss'] = process_adx_bucket_stats(orders_with_indicators)

    # Auto-sort strategies
    # Priority: Use display_order_config if available, otherwise sort by net profit (descending)
    if display_order_config and len(display_order_config) > 0:
        # Sort by custom order from config
        def get_sort_key(bot):
            raw_name = bot['raw_name']
            if raw_name in display_order_config:
                return (0, display_order_config.index(raw_name))  # Custom order first
            else:
                return (1, -bot['net_profit'])  # Then by net profit (descending)
        bot_stats.sort(key=get_sort_key)
    else:
        # Default: Sort by net profit (descending), then by trades (descending)
        bot_stats.sort(key=lambda x: (-x['net_profit'], -x['trades']))

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
                           current_filter=current_filter,
                           filter_label=filter_label,
                           from_date=from_date_param if from_date_param else '',
                           to_date=to_date_param if to_date_param else '',
                           current_db=g._current_db,
                           db_tabs=list(DB_MAP.keys()))

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

def process_daily_pnl(orders):
    """
    Aggregate trade stats by day (Vietnam Time UTC+7).
    Returns a dictionary with date keys (YYYY-MM-DD) and PNL values.
    """
    daily_stats = {}
    
    for order in orders:
        if order['profit'] is None:
            continue
            
        try:
            # Parse open_time (UTC)
            utc_time = datetime.strptime(order['open_time'], "%Y-%m-%d %H:%M:%S")
            
            # Convert to Vietnam Time (UTC+7)
            vn_time = utc_time + timedelta(hours=7)
            date_key = vn_time.strftime("%Y-%m-%d")
            
            if date_key not in daily_stats:
                daily_stats[date_key] = 0.0
            
            daily_stats[date_key] += order['profit']
                
        except Exception as e:
            print(f"Error processing time for order {order['ticket']}: {e}")
            continue
    
    return daily_stats

def fetch_orders_with_indicators(cur, strategy_name, orders):
    """
    For each order, find the closest signal (same strategy, symbol, order_type, within 30 min)
    and extract RSI and ADX from signal indicators.
    Returns list of dicts: {order, rsi, adx} with rsi/adx=None if not found.
    """
    if not orders:
        return []
    try:
        open_times = [o['open_time'] for o in orders]
        t_min = min(open_times)
        t_max = max(open_times)
        try:
            dt_min = datetime.strptime(t_min, "%Y-%m-%d %H:%M:%S") - timedelta(minutes=30)
            dt_max = datetime.strptime(t_max, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=30)
        except ValueError:
            return [{'order': dict(o), 'rsi': None, 'adx': None} for o in orders]
        t0 = dt_min.strftime("%Y-%m-%d %H:%M:%S")
        t1 = dt_max.strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            SELECT timestamp, symbol, signal_type, indicators
            FROM signals
            WHERE strategy_name = ? AND timestamp >= ? AND timestamp <= ?
        """, (strategy_name, t0, t1))
        signals = cur.fetchall()
    except Exception as e:
        print(f"fetch_orders_with_indicators: {e}")
        return [{'order': dict(o), 'rsi': None, 'adx': None} for o in orders]

    def parse_indicator(indicators, key, min_val=0, max_val=100):
        if indicators is None:
            return None
        try:
            if isinstance(indicators, str):
                data = json.loads(indicators)
            else:
                data = indicators
            if isinstance(data, dict) and key in data:
                v = float(data[key])
                return v if min_val <= v <= max_val else None
            return None
        except Exception:
            return None

    def order_time_seconds(ot):
        try:
            return datetime.strptime(ot, "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            return 0

    result = []
    for o in orders:
        o = dict(o)
        o_time = order_time_seconds(o['open_time'])
        best_rsi = best_adx = None
        best_diff = float('inf')
        for sig in signals:
            if sig['symbol'] != o.get('symbol') or sig['signal_type'] != o.get('order_type'):
                continue
            try:
                st = datetime.strptime(sig['timestamp'], "%Y-%m-%d %H:%M:%S").timestamp()
            except Exception:
                try:
                    st = datetime.strptime(str(sig['timestamp'])[:19], "%Y-%m-%d %H:%M:%S").timestamp()
                except Exception:
                    continue
            diff = abs(st - o_time)
            if diff < best_diff and diff <= 30 * 60:
                rsi = parse_indicator(sig['indicators'], 'rsi')
                adx = parse_indicator(sig['indicators'], 'adx')
                if rsi is not None or adx is not None:
                    best_diff = diff
                    best_rsi = rsi
                    best_adx = adx
        result.append({'order': o, 'rsi': best_rsi, 'adx': best_adx})
    return result

def process_rsi_bucket_stats(orders_with_rsi):
    """
    Bucket orders by RSI (0-10, 10-20, ..., 90-100) and count wins/losses per bucket.
    Returns list of {label, wins, losses} for chart.
    """
    buckets = []
    for low in range(0, 100, 10):
        high = low + 10
        buckets.append({'label': f'{low}-{high}', 'wins': 0, 'losses': 0})
    for item in orders_with_rsi:
        rsi = item.get('rsi')
        if rsi is None:
            continue
        try:
            rsi = float(rsi)
            if rsi < 0 or rsi > 100:
                continue
        except (TypeError, ValueError):
            continue
        profit = item['order'].get('profit')
        if profit is None:
            continue
        idx = min(int(rsi // 10), 9)
        if rsi == 100:
            idx = 9
        if profit > 0:
            buckets[idx]['wins'] += 1
        elif profit < 0:
            buckets[idx]['losses'] += 1
    return buckets

def process_adx_bucket_stats(orders_with_indicators):
    """
    Bucket orders by ADX (0-10, 10-20, ..., 90-100) and count wins/losses per bucket.
    Returns list of {label, wins, losses} for chart.
    """
    buckets = []
    for low in range(0, 100, 10):
        high = low + 10
        buckets.append({'label': f'{low}-{high}', 'wins': 0, 'losses': 0})
    for item in orders_with_indicators:
        adx = item.get('adx')
        if adx is None:
            continue
        try:
            adx = float(adx)
            if adx < 0 or adx > 100:
                continue
        except (TypeError, ValueError):
            continue
        profit = item['order'].get('profit')
        if profit is None:
            continue
        idx = min(int(adx // 10), 9)
        if adx == 100:
            idx = 9
        if profit > 0:
            buckets[idx]['wins'] += 1
        elif profit < 0:
            buckets[idx]['losses'] += 1
    return buckets

def load_display_order_config():
    """
    Load display order configuration from config file (optional).
    Returns a list of strategy names in desired display order.
    If config file doesn't exist, returns empty list (will use default sorting).
    """
    config_path = os.path.join(dashboard_dir, 'display_order.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get('strategy_order', [])
        except Exception as e:
            print(f"Warning: Could not load display_order.json: {e}")
    return []

def format_strategy_name(raw_name):
    """
    Auto-format strategy name for display.
    Examples:
    - "Strategy_1_Trend_HA" -> "1 Trend HA"
    - "Strategy_1_Trend_HA_V2" -> "1 Trend HA V2"
    - "Strategy_4_UT_Bot" -> "4 UT Bot"
    """
    # Remove "Strategy_" prefix if present
    name = raw_name.replace("Strategy_", "")
    
    # Replace underscores with spaces
    name = name.replace("_", " ")
    
    # Capitalize first letter of each word
    words = name.split()
    formatted_words = []
    for word in words:
        # Keep version numbers (V2, V3, etc.) uppercase
        if word.upper().startswith('V') and len(word) > 1 and word[1:].isdigit():
            formatted_words.append(word.upper())
        else:
            # Capitalize first letter, lowercase rest
            formatted_words.append(word.capitalize())
    
    return " ".join(formatted_words)

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
                try:
                    # Try with milliseconds
                    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    # Try parsing without seconds
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

@app.route('/signals')
def signals_page():
    """Display all signals with ability to check MT5 results"""
    cur = get_db().cursor()
    
    # Get filter parameter
    days_param = request.args.get('days', '7')  # Default 7 days
    if days_param == "all":
        days = 36500
        filter_label = "All Time"
    else:
        try:
            days = int(days_param)
            filter_label = f"Last {days} Days"
        except:
            days = 7
            filter_label = "Last 7 Days"
    
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
    
    # Fetch signals
    cur.execute("SELECT * FROM signals WHERE timestamp >= ? ORDER BY timestamp DESC", (cutoff_str,))
    signals = cur.fetchall()
    
    # For each signal, try to find matching order
    signals_with_status = []
    for sig in signals:
        signal_dict = dict(sig)
        
        # Try to find matching order (within 30 seconds of signal)
        try:
            # Handle different datetime formats
            sig_timestamp = sig['timestamp']
            if isinstance(sig_timestamp, str):
                # Try different formats
                try:
                    sig_time = datetime.strptime(sig_timestamp, '%Y-%m-%d %H:%M:%S')
                except:
                    try:
                        sig_time = datetime.strptime(sig_timestamp, '%Y-%m-%d %H:%M:%S.%f')
                    except:
                        sig_time = datetime.fromisoformat(sig_timestamp.replace('Z', '+00:00'))
            else:
                sig_time = datetime.fromtimestamp(sig_timestamp)
            
            time_lower = (sig_time - timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
            time_upper = (sig_time + timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            # If datetime parsing fails, skip order matching
            time_lower = None
            time_upper = None
        
        matching_order = None
        if time_lower and time_upper:
            try:
                cur.execute("""
                    SELECT * FROM orders 
                    WHERE strategy_name = ? 
                    AND symbol = ?
                    AND order_type = ?
                    AND open_time BETWEEN ? AND ?
                    ORDER BY ABS(open_price - ?) ASC
                    LIMIT 1
                """, (sig['strategy_name'], sig['symbol'], sig['signal_type'], time_lower, time_upper, sig['price']))
                
                matching_order = cur.fetchone()
            except Exception as e:
                # If query fails, continue without matching order
                pass
        
        if matching_order:
            signal_dict['order_ticket'] = matching_order['ticket']
            signal_dict['order_profit'] = matching_order['profit']
            signal_dict['order_status'] = 'closed' if matching_order['profit'] is not None else 'open'
            signal_dict['has_order'] = True
        else:
            signal_dict['order_ticket'] = None
            signal_dict['order_profit'] = None
            signal_dict['order_status'] = 'not_found'
            signal_dict['has_order'] = False
        
        signals_with_status.append(signal_dict)
    
    # Calculate stats for template
    total_signals = len(signals_with_status)
    matched_orders = len([s for s in signals_with_status if s['has_order']])
    wins = len([s for s in signals_with_status if s['has_order'] and s['order_profit'] is not None and s['order_profit'] > 0])
    losses = len([s for s in signals_with_status if s['has_order'] and s['order_profit'] is not None and s['order_profit'] < 0])
    
    # Get list of strategies for filter dropdown
    cur.execute("SELECT DISTINCT strategy_name FROM orders ORDER BY strategy_name")
    strategies = [row['strategy_name'] for row in cur.fetchall()]
    
    return render_template('signals.html', 
                         signals=signals_with_status,
                         total_signals=total_signals,
                         matched_orders=matched_orders,
                         wins=wins,
                         losses=losses,
                         current_filter=days_param,
                         filter_label=filter_label,
                         strategies=strategies,
                         check_mt5_available=False,
                         current_db=g._current_db,
                         db_tabs=list(DB_MAP.keys()))

@app.route('/api/check_signal/<int:signal_id>')
def check_signal(signal_id):
    """Check MT5 not available in shared dashboard (no bot config/MT5 here)."""
    return jsonify({
        'error': 'Check MT5 is not available in shared dashboard. Run dashboard from the bot folder to use this feature.'
    }), 503

@app.route('/api/analyze_signal/<int:signal_id>')
def analyze_signal(signal_id):
    """Analyze signal to determine why it won/lost and provide recommendations"""
    cur = get_db().cursor()
    
    # Get signal details
    cur.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
    signal = cur.fetchone()
    
    if not signal:
        return jsonify({'error': 'Signal not found'}), 404
    
    signal_dict = dict(signal)
    
    # Try to find matching order
    order_info = None
    try:
        sig_timestamp = signal_dict['timestamp']
        if isinstance(sig_timestamp, str):
            try:
                signal_time = datetime.strptime(sig_timestamp, '%Y-%m-%d %H:%M:%S')
            except:
                try:
                    signal_time = datetime.strptime(sig_timestamp, '%Y-%m-%d %H:%M:%S.%f')
                except:
                    signal_time = datetime.fromisoformat(sig_timestamp.replace('Z', '+00:00'))
        else:
            signal_time = datetime.fromtimestamp(sig_timestamp)
        
        time_lower_order = (signal_time - timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
        time_upper_order = (signal_time + timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
        
        cur.execute("""
            SELECT * FROM orders 
            WHERE strategy_name = ? 
            AND symbol = ?
            AND order_type = ?
            AND open_time BETWEEN ? AND ?
            ORDER BY ABS(open_price - ?) ASC
            LIMIT 1
        """, (signal_dict['strategy_name'], signal_dict['symbol'], signal_dict['signal_type'], 
              time_lower_order, time_upper_order, signal_dict['price']))
        
        order_row = cur.fetchone()
        if order_row:
            order_info = dict(order_row)
    except Exception as e:
        pass  # Order not found, continue without it
    
    # Get similar signals for comparison (same strategy, within 7 days)
    try:
        sig_timestamp = signal_dict['timestamp']
        if isinstance(sig_timestamp, str):
            try:
                signal_time = datetime.strptime(sig_timestamp, '%Y-%m-%d %H:%M:%S')
            except:
                try:
                    signal_time = datetime.strptime(sig_timestamp, '%Y-%m-%d %H:%M:%S.%f')
                except:
                    signal_time = datetime.fromisoformat(sig_timestamp.replace('Z', '+00:00'))
        else:
            signal_time = datetime.fromtimestamp(sig_timestamp)
    except:
        signal_time = datetime.now()
    
    time_lower = (signal_time - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    time_upper = (signal_time + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    
    # Get similar signals
    cur.execute("""
        SELECT s.*, o.profit, o.close_price, o.open_price, o.sl as order_sl, o.tp as order_tp
        FROM signals s
        LEFT JOIN orders o ON s.strategy_name = o.strategy_name 
            AND s.symbol = o.symbol 
            AND s.signal_type = o.order_type
            AND ABS((julianday(s.timestamp) - julianday(o.open_time)) * 24 * 60) < 30
        WHERE s.strategy_name = ? 
        AND s.timestamp BETWEEN ? AND ?
        AND s.id != ?
        ORDER BY s.timestamp DESC
        LIMIT 50
    """, (signal_dict['strategy_name'], time_lower, time_upper, signal_id))
    
    similar_signals = cur.fetchall()
    
    # Analyze indicators if available
    indicators = None
    if signal_dict.get('indicators'):
        try:
            indicators = json.loads(signal_dict['indicators']) if isinstance(signal_dict['indicators'], str) else signal_dict['indicators']
        except:
            pass
    
    # Calculate statistics from similar signals
    similar_with_results = [s for s in similar_signals if s['profit'] is not None]
    win_rate = 0
    avg_profit = 0
    avg_loss = 0
    if similar_with_results:
        wins = [s for s in similar_with_results if s['profit'] > 0]
        losses = [s for s in similar_with_results if s['profit'] < 0]
        win_rate = (len(wins) / len(similar_with_results)) * 100 if similar_with_results else 0
        avg_profit = sum([s['profit'] for s in wins]) / len(wins) if wins else 0
        avg_loss = abs(sum([s['profit'] for s in losses]) / len(losses)) if losses else 0
    
    # Analyze current signal
    analysis = {
        'signal_info': {
            'id': signal_dict['id'],
            'timestamp': signal_dict['timestamp'],
            'strategy': signal_dict['strategy_name'],
            'symbol': signal_dict['symbol'],
            'type': signal_dict['signal_type'],
            'price': signal_dict['price'],
            'sl': signal_dict['sl'],
            'tp': signal_dict['tp']
        },
        'order_info': order_info,
        'indicators': indicators,
        'statistics': {
            'similar_signals_count': len(similar_signals),
            'similar_with_results': len(similar_with_results),
            'win_rate': round(win_rate, 1),
            'avg_profit': round(avg_profit, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(avg_profit / avg_loss, 2) if avg_loss > 0 else 0
        },
        'analysis': [],
        'recommendations': []
    }
    
    # Determine result
    result = 'unknown'
    if order_info:
        if order_info.get('profit') is not None:
            result = 'win' if order_info['profit'] > 0 else 'loss'
        else:
            result = 'open'
    else:
        result = 'no_order'
    
    # Analysis points (simplified version)
    if result == 'win':
        analysis['analysis'].append({
            'type': 'success',
            'title': '✅ Trade Won',
            'message': f"Trade closed with profit of ${order_info.get('profit', 0):.2f}"
        })
    elif result == 'loss':
        analysis['analysis'].append({
            'type': 'error',
            'title': '❌ Trade Lost',
            'message': f"Trade closed with loss of ${abs(order_info.get('profit', 0)):.2f}"
        })
    elif result == 'open':
        analysis['analysis'].append({
            'type': 'info',
            'title': '⏳ Trade Still Open',
            'message': "Position is still running. Analysis will be available after close."
        })
    else:
        analysis['analysis'].append({
            'type': 'warning',
            'title': '⚠️ No Order Found',
            'message': "No matching order found for this signal. Signal may not have been executed."
        })
    
    return jsonify(analysis)

@app.route('/api/export_orders')
def export_orders():
    """Export all orders with full information to CSV"""
    cur = get_db().cursor()
    
    # Get filter parameters
    days_param = request.args.get('days', 'all')
    strategy_param = request.args.get('strategy', 'all')
    
    if days_param == "all":
        days = 36500
    else:
        try:
            days = int(days_param)
        except:
            days = 36500
    
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
    
    # Build query with optional strategy filter
    # First get all orders, then join with closest signal using a simpler approach
    # Use a two-step process: get orders first, then find matching signals
    base_query = """
        SELECT 
            o.ticket,
            o.strategy_name,
            o.symbol,
            o.order_type,
            o.volume,
            o.open_price,
            o.sl,
            o.tp,
            o.open_time,
            o.close_price,
            o.profit,
            o.comment,
            o.account_id
        FROM orders o
        WHERE o.open_time >= ?
    """
    
    params = [cutoff_str]
    
    # Add strategy filter if specified
    if strategy_param and strategy_param != 'all':
        base_query += " AND o.strategy_name = ?"
        params.append(strategy_param)
    
    base_query += " ORDER BY o.open_time DESC"
    
    cur.execute(base_query, tuple(params))
    orders = cur.fetchall()
    
    # Now find matching signals for each order
    orders_with_signals = []
    for order in orders:
        order_dict = dict(order)
        
        # Find closest matching signal
        cur.execute("""
            SELECT timestamp, indicators, status
            FROM signals
            WHERE strategy_name = ?
              AND symbol = ?
              AND signal_type = ?
              AND ABS((julianday(?) - julianday(timestamp)) * 24 * 60) < 30
            ORDER BY ABS((julianday(?) - julianday(timestamp)) * 24 * 60)
            LIMIT 1
        """, (order['strategy_name'], order['symbol'], order['order_type'], 
              order['open_time'], order['open_time']))
        
        signal = cur.fetchone()
        if signal:
            order_dict['signal_timestamp'] = signal['timestamp']
            order_dict['signal_indicators'] = signal['indicators']
            order_dict['signal_status'] = signal['status']
        else:
            order_dict['signal_timestamp'] = None
            order_dict['signal_indicators'] = None
            order_dict['signal_status'] = None
        
        orders_with_signals.append(order_dict)
    
    # Use orders_with_signals instead of fetching from database again
    orders = orders_with_signals
    
    params = [cutoff_str]
    
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    headers = [
        'Ticket',
        'Strategy',
        'Symbol',
        'Order Type',
        'Volume',
        'Open Price',
        'Stop Loss',
        'Take Profit',
        'Open Time',
        'Close Price',
        'Profit ($)',
        'Status',
        'Comment',
        'Account ID',
        'Signal Timestamp',
        'Signal Indicators',
        'Signal Status',
        'Win/Loss',
        'Profit %',
        'Risk/Reward Ratio'
    ]
    writer.writerow(headers)
    
    # Write data rows
    for order in orders:
        row = []
        
        # Basic order info
        row.append(order['ticket'])
        row.append(order['strategy_name'])
        row.append(order['symbol'])
        row.append(order['order_type'])
        row.append(order['volume'])
        row.append(order['open_price'])
        row.append(order['sl'])
        row.append(order['tp'])
        row.append(order['open_time'])
        row.append(order['close_price'] if order['close_price'] else '')
        row.append(order['profit'] if order['profit'] is not None else '')
        
        # Status
        if order['profit'] is None:
            status = 'Open'
        elif order['profit'] > 0:
            status = 'Win'
        else:
            status = 'Loss'
        row.append(status)
        
        row.append(order['comment'] if order['comment'] else '')
        row.append(order['account_id'])
        
        # Signal info
        row.append(order['signal_timestamp'] if order['signal_timestamp'] else '')
        
        # Indicators (format as JSON string)
        indicators_str = ''
        if order['signal_indicators']:
            try:
                if isinstance(order['signal_indicators'], str):
                    indicators_str = order['signal_indicators']
                else:
                    indicators_str = json.dumps(order['signal_indicators'])
            except:
                indicators_str = str(order['signal_indicators'])
        row.append(indicators_str)
        
        row.append(order['signal_status'] if order['signal_status'] else '')
        
        # Calculated fields
        # Win/Loss
        if order['profit'] is not None:
            row.append('Win' if order['profit'] > 0 else 'Loss')
        else:
            row.append('Running')
        
        # Profit %
        profit_pct = ''
        if order['profit'] is not None and order['open_price'] and order['close_price']:
            if order['order_type'] == 'BUY':
                profit_pct = ((order['close_price'] - order['open_price']) / order['open_price'] * 100)
            else:
                profit_pct = ((order['open_price'] - order['close_price']) / order['open_price'] * 100)
            profit_pct = f"{profit_pct:.4f}%"
        row.append(profit_pct)
        
        # Risk/Reward Ratio
        rr_ratio = ''
        if order['sl'] and order['tp'] and order['open_price']:
            if order['order_type'] == 'BUY':
                risk = abs(order['open_price'] - order['sl'])
                reward = abs(order['tp'] - order['open_price'])
            else:
                risk = abs(order['sl'] - order['open_price'])
                reward = abs(order['open_price'] - order['tp'])
            if risk > 0:
                rr_ratio = f"{reward / risk:.2f}"
        row.append(rr_ratio)
        
        writer.writerow(row)
    
    # Prepare response
    output.seek(0)
    strategy_suffix = ""
    if strategy_param and strategy_param != 'all':
        # Clean strategy name for filename
        clean_strategy = strategy_param.replace(' ', '_').replace('/', '_')
        strategy_suffix = f"_{clean_strategy}"
    filename = f"orders_export{strategy_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )

@app.route('/api/export_signals')
def export_signals():
    """Export all signals with full information to CSV"""
    cur = get_db().cursor()
    
    # Get filter parameters
    days_param = request.args.get('days', 'all')
    strategy_param = request.args.get('strategy', 'all')
    
    if days_param == "all":
        days = 36500
    else:
        try:
            days = int(days_param)
        except:
            days = 36500
    
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
    
    # Build query
    query = """
        SELECT 
            s.id,
            s.timestamp,
            s.strategy_name,
            s.symbol,
            s.signal_type,
            s.price,
            s.sl,
            s.tp,
            s.indicators,
            s.status,
            s.account_id,
            o.ticket as order_ticket,
            o.open_price as order_open_price,
            o.close_price as order_close_price,
            o.profit as order_profit,
            o.open_time as order_open_time
        FROM signals s
        LEFT JOIN orders o ON s.strategy_name = o.strategy_name 
            AND s.symbol = o.symbol 
            AND s.signal_type = o.order_type
            AND ABS((julianday(s.timestamp) - julianday(o.open_time)) * 24 * 60) < 30
        WHERE s.timestamp >= ?
    """
    
    params = [cutoff_str]
    
    # Add strategy filter if specified
    if strategy_param and strategy_param != 'all':
        query += " AND s.strategy_name = ?"
        params.append(strategy_param)
    
    query += " ORDER BY s.timestamp DESC"
    
    cur.execute(query, tuple(params))
    signals = cur.fetchall()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    headers = [
        'Signal ID',
        'Timestamp',
        'Strategy',
        'Symbol',
        'Signal Type',
        'Price',
        'Stop Loss',
        'Take Profit',
        'Indicators',
        'Status',
        'Account ID',
        'Order Ticket',
        'Order Open Price',
        'Order Close Price',
        'Order Profit ($)',
        'Order Open Time',
        'Has Order',
        'Order Status'
    ]
    writer.writerow(headers)
    
    # Write data rows
    for sig in signals:
        row = []
        
        # Signal info
        row.append(sig['id'])
        row.append(sig['timestamp'])
        row.append(sig['strategy_name'])
        row.append(sig['symbol'])
        row.append(sig['signal_type'])
        row.append(sig['price'])
        row.append(sig['sl'] if sig['sl'] else '')
        row.append(sig['tp'] if sig['tp'] else '')
        
        # Indicators (format as JSON string)
        indicators_str = ''
        if sig['indicators']:
            try:
                if isinstance(sig['indicators'], str):
                    indicators_str = sig['indicators']
                else:
                    indicators_str = json.dumps(sig['indicators'])
            except:
                indicators_str = str(sig['indicators'])
        row.append(indicators_str)
        
        row.append(sig['status'] if sig['status'] else '')
        row.append(sig['account_id'])
        
        # Order info
        row.append(sig['order_ticket'] if sig['order_ticket'] else '')
        row.append(sig['order_open_price'] if sig['order_open_price'] else '')
        row.append(sig['order_close_price'] if sig['order_close_price'] else '')
        row.append(sig['order_profit'] if sig['order_profit'] is not None else '')
        row.append(sig['order_open_time'] if sig['order_open_time'] else '')
        
        # Calculated fields
        has_order = 'Yes' if sig['order_ticket'] else 'No'
        row.append(has_order)
        
        if sig['order_profit'] is not None:
            order_status = 'Win' if sig['order_profit'] > 0 else 'Loss'
        elif sig['order_ticket']:
            order_status = 'Open'
        else:
            order_status = 'No Order'
        row.append(order_status)
        
        writer.writerow(row)
    
    # Prepare response
    output.seek(0)
    strategy_suffix = ""
    if strategy_param and strategy_param != 'all':
        # Clean strategy name for filename
        clean_strategy = strategy_param.replace(' ', '_').replace('/', '_')
        strategy_suffix = f"_{clean_strategy}"
    filename = f"signals_export{strategy_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )

if __name__ == '__main__':
    print(f"🚀 Dashboard running on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
