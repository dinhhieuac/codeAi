from flask import Flask, render_template, g, request, jsonify, Response
from datetime import datetime, timedelta
import json
import sqlite3
import os
import csv
import io
import sys
import subprocess
import os

# Thêm thư mục hiện tại vào sys.path để import utils, db, update_db dù chạy từ bất kỳ đâu
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

try:
    import psutil
except ImportError:
    psutil = None
import MetaTrader5 as mt5
from utils import connect_mt5, load_config
from update_db import load_strategy_configs

# Định nghĩa các bot giao dịch và script hỗ trợ
VALID_BOTS = {
    'strategy_1_trend_ha_v2.py': {
        'name': 'HA v2.0',
        'version': 'V2.0 (Khuyên dùng)',
        'desc': 'ADX, CHOP filter, ATR-based SL & trailing',
        'badge': 'bg-success'
    },
    'strategy_1_trend_ha_v1.1.py': {
        'name': 'HA v1.1',
        'version': 'V1.1',
        'desc': 'Trend Heiken Ashi v1.1',
        'badge': 'bg-primary'
    },
    'strategy_1_trend_ha_v2.1.py': {
        'name': 'HA v2.1',
        'version': 'V2.1',
        'desc': 'Trend Heiken Ashi v2.1',
        'badge': 'bg-info'
    },
    'strategy_1_trend_ha_v3.py': {
        'name': 'HA v3.0',
        'version': 'V3.0',
        'desc': 'Trend Heiken Ashi v3.0 (Strict Entry)',
        'badge': 'bg-warning text-dark'
    },
    'strategy_1_trend_ha.py': {
        'name': 'HA Original',
        'version': 'Gốc',
        'desc': 'Trend Heiken Ashi bản khởi tạo',
        'badge': 'bg-secondary'
    },
    'update_db.py': {
        'name': 'Update DB',
        'version': 'Sync Tool',
        'desc': 'Đồng bộ lịch sử lệnh từ MT5 vào trades.db',
        'badge': 'bg-dark'
    },
}

def get_running_bots():
    """Kiểm tra xem các bot nào đang chạy trên hệ thống"""
    running = {}
    if not psutil:
        return running
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                cmdline_str = " ".join(cmdline).lower()
                for bot_file in VALID_BOTS:
                    if bot_file.lower() in cmdline_str:
                        running[bot_file] = proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        print(f"Lỗi kiểm tra tiến trình bot: {e}")
    return running

def _launch_bot_process(bot_file, label):
    """Khởi chạy bot trong cửa sổ Command Prompt riêng biệt"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.normpath(os.path.join(base_dir, '..', '.venv', 'Scripts', 'python.exe'))
    python_exe = venv_python if os.path.exists(venv_python) else sys.executable
    script_path = os.path.join(base_dir, bot_file)
    
    cmd = f'start "XAU Bot - {label}" cmd /k "chcp 65001 >nul && cd /d "{base_dir}" && title XAU_M1_REAL - {label} && "{python_exe}" -X utf8 "{script_path}""'
    subprocess.Popen(cmd, shell=True)

def get_mt5_account_and_positions():
    """Lấy thông tin tài khoản và các vị thế đang mở từ MT5"""
    result = {
        'connected': False,
        'account': None,
        'server': None,
        'balance': 0.0,
        'equity': 0.0,
        'floating_profit': 0.0,
        'positions_count': 0,
        'positions': []
    }
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    primary_config = os.path.join(base_dir, "configs", "config_1_v2.json")
    config = None
    if os.path.exists(primary_config):
        config = load_config(primary_config)
    
    if not config:
        config_dir = os.path.join(base_dir, "configs")
        if os.path.exists(config_dir):
            for f in os.listdir(config_dir):
                if f.endswith(".json") and f != "config_template.json":
                    config = load_config(os.path.join(config_dir, f))
                    if config:
                        break
                    
    if not config:
        return result
        
    result['account'] = config.get('account')
    result['server'] = config.get('server')
    
    try:
        acc_info = mt5.account_info()
        if acc_info is None or (acc_info.login != config.get('account')):
            if not connect_mt5(config):
                return result
            acc_info = mt5.account_info()
            
        if acc_info:
            result['connected'] = True
            result['account'] = acc_info.login
            result['server'] = acc_info.server
            result['balance'] = round(acc_info.balance, 2)
            result['equity'] = round(acc_info.equity, 2)
            
            positions = mt5.positions_get()
            pos_list = []
            total_profit = 0.0
            for p in (positions or []):
                total_profit += p.profit
                pos_list.append({
                    'ticket': p.ticket,
                    'symbol': p.symbol,
                    'type': 'BUY' if p.type == mt5.ORDER_TYPE_BUY else 'SELL',
                    'volume': p.volume,
                    'open_price': p.price_open,
                    'current_price': p.price_current,
                    'sl': p.sl,
                    'tp': p.tp,
                    'profit': round(p.profit, 2),
                    'magic': p.magic,
                    'comment': p.comment
                })
            result['positions_count'] = len(pos_list)
            result['floating_profit'] = round(total_profit, 2)
            result['positions'] = pos_list
    except Exception as e:
        print(f"Lỗi lấy thông tin MT5: {e}")
        
    return result

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

def _parse_date_range(from_date_str, to_date_str):
    """Parse from_date and to_date (YYYY-MM-DD). Return (cutoff_utc, end_utc_str, filter_label) or None if invalid."""
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
            from_date_param = ''
            to_date_param = ''
            parsed = None
    else:
        parsed = None

    if parsed is None:
        if days_param == "all":
            days = 36500
            filter_label = "All Time"
            current_filter = "all"
        else:
            try:
                days = int(days_param)
                filter_label = f"Last {days} Days"
            except Exception:
                days = 30
                filter_label = "Last 30 Days"
            current_filter = days_param
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT * FROM orders WHERE open_time >= ? ORDER BY open_time DESC", (cutoff_str,))
        orders = cur.fetchall()
        cur.execute("SELECT * FROM signals ORDER BY timestamp DESC LIMIT 50")
        signals = cur.fetchall()

    # Calculate Stats
    total_trades = len(orders)
    total_profit = sum([o['profit'] for o in orders if o['profit'] is not None])
    wins = len([o for o in orders if o['profit'] is not None and o['profit'] > 0])
    losses = len([o for o in orders if o['profit'] is not None and o['profit'] < 0])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

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
        
    # Sort by User Defined Order without filtering out unlisted strategies
    desired_order = [
        "Strategy_1_Trend_HA",
        "Strategy_1_Trend_HA_V1.1",
        "Strategy_1_Trend_HA_V2",
        "Strategy_1_Trend_HA_V2.1",
        "Strategy_1_Trend_HA_V3",
        "Strategy_4_UT_Bot",
        "Strategy_2_EMA_ATR",
        "Strategy_3_PA_Volume",
        "Strategy_5_Filter_First"
    ]
    
    def sort_key(b):
        raw = b.get('raw_name', '')
        return (0, desired_order.index(raw)) if raw in desired_order else (1, raw)
    bot_stats.sort(key=sort_key)

    # Lấy thông tin MT5 tài khoản và vị thế đang mở
    account_info = get_mt5_account_and_positions()

    return render_template('index.html', 
                           orders=orders, 
                           signals=signals, 
                           total_trades=total_trades,
                           total_profit=total_profit,
                           win_rate=win_rate,
                           wins=wins,
                           losses=losses,
                           bot_stats=bot_stats,
                           current_filter=current_filter,
                           filter_label=filter_label,
                           from_date=from_date_param if from_date_param else '',
                           to_date=to_date_param if to_date_param else '',
                           valid_bots=VALID_BOTS,
                           running_bots=get_running_bots(),
                           account_info=account_info)

@app.route('/atr_analysis')
def atr_analysis_page():
    """Display ATR analysis page"""
    cur = get_db().cursor()
    
    # Get all strategies for filter
    cur.execute("SELECT DISTINCT strategy_name FROM orders")
    strategies = [row['strategy_name'] for row in cur.fetchall()]
    
    return render_template('atr_analysis.html', strategies=strategies)

@app.route('/api/atr_analysis')
def api_atr_analysis():
    """API endpoint for ATR analysis data"""
    cur = get_db().cursor()
    
    # Get filter parameters
    days_param = request.args.get('days', '30')
    strategy_param = request.args.get('strategy', 'all')
    threshold = float(request.args.get('threshold', 15.0))
    
    if days_param == "all":
        days = 36500
    else:
        try:
            days = int(days_param)
        except:
            days = 30
    
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
    
    # Build query with JOIN to signals table to get indicators
    if strategy_param == "all":
        query = """
            SELECT 
                o.ticket,
                o.strategy_name,
                o.order_type,
                o.profit,
                o.open_time,
                s.indicators as signal_indicators
            FROM orders o
            LEFT JOIN signals s ON o.strategy_name = s.strategy_name 
                AND o.symbol = s.symbol 
                AND o.order_type = s.signal_type
                AND ABS((julianday(o.open_time) - julianday(s.timestamp)) * 24 * 60) < 30
            WHERE o.open_time >= ? AND o.profit IS NOT NULL
        """
        params = (cutoff_str,)
    else:
        query = """
            SELECT 
                o.ticket,
                o.strategy_name,
                o.order_type,
                o.profit,
                o.open_time,
                s.indicators as signal_indicators
            FROM orders o
            LEFT JOIN signals s ON o.strategy_name = s.strategy_name 
                AND o.symbol = s.symbol 
                AND o.order_type = s.signal_type
                AND ABS((julianday(o.open_time) - julianday(s.timestamp)) * 24 * 60) < 30
            WHERE o.open_time >= ? AND o.strategy_name = ? AND o.profit IS NOT NULL
        """
        params = (cutoff_str, strategy_param)
    
    cur.execute(query, params)
    orders = cur.fetchall()
    
    # Extract ATR from signal_indicators
    atr_data = []
    orders_with_indicators = 0
    orders_without_indicators = 0
    
    for order in orders:
        try:
            indicators_str = order['signal_indicators']
            if indicators_str:
                orders_with_indicators += 1
                if isinstance(indicators_str, str):
                    indicators = json.loads(indicators_str)
                else:
                    indicators = indicators_str
                
                atr_val = indicators.get('atr', None)
                if atr_val is not None:
                    atr_data.append({
                        'ticket': order['ticket'],
                        'strategy': order['strategy_name'],
                        'order_type': order['order_type'],
                        'atr': float(atr_val),
                        'profit': float(order['profit']) if order['profit'] else 0,
                        'win_loss': 'Win' if order['profit'] and order['profit'] > 0 else 'Loss',
                        'open_time': order['open_time']
                    })
                else:
                    orders_without_indicators += 1
            else:
                orders_without_indicators += 1
        except Exception as e:
            orders_without_indicators += 1
            continue
    
    # Debug info (can be removed in production)
    if len(orders) > 0 and len(atr_data) == 0:
        # Return info about why no data
        return jsonify({
            'summary': {
                'total_trades': len(orders),
                'atr_low_count': 0,
                'atr_high_count': 0,
                'avg_atr': 0,
                'debug_info': {
                    'total_orders': len(orders),
                    'orders_with_indicators': orders_with_indicators,
                    'orders_without_indicators': orders_without_indicators,
                    'orders_with_atr': len(atr_data)
                }
            },
            'comparison': {'low': {}, 'high': {}},
            'chart_data': {'distribution': {'labels': [], 'data': [], 'colors': []}, 'win_rate': {'labels': [], 'data': []}},
            'trades': []
        })
    
    if not atr_data:
        return jsonify({
            'summary': {'total_trades': 0},
            'comparison': {'low': {}, 'high': {}},
            'chart_data': {'distribution': {'labels': [], 'data': [], 'colors': []}, 'win_rate': {'labels': [], 'data': []}},
            'trades': []
        })
    
    # Separate by threshold
    atr_low = [d for d in atr_data if d['atr'] < threshold]
    atr_high = [d for d in atr_data if d['atr'] >= threshold]
    
    # Calculate summary
    total_trades = len(atr_data)
    avg_atr = sum(d['atr'] for d in atr_data) / total_trades if total_trades > 0 else 0
    
    # Calculate comparison stats
    def calc_stats(data):
        if not data:
            return {
                'trades': 0,
                'win_rate': 0,
                'total_profit': 0,
                'profit_factor': 0,
                'avg_win': 0,
                'avg_loss': 0
            }
        
        wins = [d for d in data if d['win_loss'] == 'Win']
        losses = [d for d in data if d['win_loss'] == 'Loss']
        
        num_wins = len(wins)
        num_losses = len(losses)
        total = len(data)
        win_rate = (num_wins / total * 100) if total > 0 else 0
        
        gross_profit = sum(w['profit'] for w in wins)
        gross_loss = abs(sum(l['profit'] for l in losses))
        total_profit = sum(d['profit'] for d in data)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0
        
        avg_win = (gross_profit / num_wins) if num_wins > 0 else 0
        avg_loss = (gross_loss / num_losses) if num_losses > 0 else 0
        
        return {
            'trades': total,
            'win_rate': win_rate,
            'total_profit': total_profit,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss
        }
    
    low_stats = calc_stats(atr_low)
    high_stats = calc_stats(atr_high)
    
    # Prepare chart data - ATR Distribution
    atr_ranges = [
        (0, 5, '0-5'),
        (5, 10, '5-10'),
        (10, 15, '10-15'),
        (15, 20, '15-20'),
        (20, 25, '20-25'),
        (25, float('inf'), '25+')
    ]
    
    distribution_labels = []
    distribution_data = []
    distribution_colors = []
    
    for min_atr, max_atr, label in atr_ranges:
        count = len([d for d in atr_data if min_atr <= d['atr'] < max_atr])
        distribution_labels.append(label)
        distribution_data.append(count)
        if max_atr <= threshold:
            distribution_colors.append('rgba(40, 167, 69, 0.6)')  # Green
        else:
            distribution_colors.append('rgba(220, 53, 69, 0.6)')  # Red
    
    # Win Rate by ATR Range
    win_rate_labels = []
    win_rate_data = []
    
    for min_atr, max_atr, label in atr_ranges:
        range_data = [d for d in atr_data if min_atr <= d['atr'] < max_atr]
        if range_data:
            wins = len([d for d in range_data if d['win_loss'] == 'Win'])
            win_rate = (wins / len(range_data) * 100) if range_data else 0
            win_rate_labels.append(label)
            win_rate_data.append(win_rate)
    
    return jsonify({
        'summary': {
            'total_trades': total_trades,
            'atr_low_count': len(atr_low),
            'atr_high_count': len(atr_high),
            'avg_atr': avg_atr
        },
        'comparison': {
            'low': low_stats,
            'high': high_stats
        },
        'chart_data': {
            'distribution': {
                'labels': distribution_labels,
                'data': distribution_data,
                'colors': distribution_colors
            },
            'win_rate': {
                'labels': win_rate_labels,
                'data': win_rate_data
            }
        },
        'trades': sorted(atr_data, key=lambda x: x['open_time'], reverse=True)[:100]  # Last 100 trades
    })

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
                         strategies=strategies)

@app.route('/api/check_signal/<int:signal_id>')
def check_signal(signal_id):
    """Check signal result via MT5"""
    cur = get_db().cursor()
    
    # Get signal details
    cur.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
    signal = cur.fetchone()
    
    if not signal:
        return jsonify({'error': 'Signal not found'}), 404
    
    signal_dict = dict(signal)
    
    # Load strategy config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies = load_strategy_configs(script_dir)
    
    strategy_name = signal_dict['strategy_name']
    if strategy_name not in strategies:
        return jsonify({'error': f'Config not found for {strategy_name}'}), 404
    
    config_path = strategies[strategy_name]
    if not os.path.exists(config_path):
        return jsonify({'error': f'Config file not found: {config_path}'}), 404
    
    config = load_config(config_path)
    if not config:
        return jsonify({'error': 'Failed to load config'}), 500
    
    # Connect to MT5
    if not connect_mt5(config):
        return jsonify({'error': 'Failed to connect to MT5'}), 500
    
    try:
        # Verify account match
        current_account = mt5.account_info()
        if current_account is None:
            return jsonify({'error': 'Failed to retrieve account info'}), 500
        
        if current_account.login != config['account']:
            return jsonify({'error': f'Account mismatch: Expected {config["account"]}, got {current_account.login}'}), 400
        
        # Search for trades around signal time
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
        except Exception as e:
            return jsonify({'error': f'Invalid timestamp format: {e}'}), 400
        
        from_date = signal_time - timedelta(minutes=5)
        to_date = signal_time + timedelta(hours=24)  # Check up to 24 hours after signal
        
        # Get history deals
        deals = mt5.history_deals_get(from_date, to_date)
        
        if deals is None:
            return jsonify({
                'status': 'not_found',
                'message': 'No trades found in MT5 history for this time period'
            })
        
        # Find matching trade
        # Match by: symbol, order type, price proximity, time proximity
        symbol = signal_dict['symbol']
        signal_type = signal_dict['signal_type']
        signal_price = signal_dict['price']
        
        # Convert signal type to MT5 order type
        expected_order_type = mt5.ORDER_TYPE_BUY if signal_type == 'BUY' else mt5.ORDER_TYPE_SELL
        
        matching_positions = []
        
        # First, try to find positions directly
        positions = mt5.positions_get(symbol=symbol)
        if positions:
            for pos in positions:
                # Check if position type matches
                if pos.type != expected_order_type:
                    continue
                
                # Check if price is close (within 0.5 points for XAUUSD)
                if abs(pos.price_open - signal_price) > 0.5:
                    continue
                
                # Check if time is close (within 5 minutes)
                pos_time = datetime.fromtimestamp(pos.time)
                if abs((pos_time - signal_time).total_seconds()) > 300:
                    continue
                
                matching_positions.append(pos)
        
        # Also check history deals for closed positions
        matching_deals = []
        for deal in deals:
            # Only check entry deals
            if deal.entry != mt5.DEAL_ENTRY_IN:
                continue
            
            # Check if deal matches signal
            if deal.symbol != symbol:
                continue
            
            # Check if price is close (within 0.5 points for XAUUSD)
            if abs(deal.price - signal_price) > 0.5:
                continue
            
            # Check if time is close (within 5 minutes)
            deal_time = datetime.fromtimestamp(deal.time)
            if abs((deal_time - signal_time).total_seconds()) > 300:
                continue
            
            # Get position to check type
            pos_deals = mt5.history_deals_get(position=deal.position_id)
            if pos_deals:
                # Get position from first deal
                pos_info = mt5.positions_get(ticket=deal.position_id)
                if not pos_info:
                    # Position is closed, check from history
                    # We'll verify the type from the position_id
                    matching_deals.append(deal)
        
        # Prioritize open positions, then closed deals
        if matching_positions:
            position_ticket = matching_positions[0].ticket
        elif matching_deals:
            position_ticket = matching_deals[0].position_id
        else:
            return jsonify({
                'status': 'not_found',
                'message': 'No matching trades found in MT5 history'
            })
        
        # Check if position is still open
        open_positions = mt5.positions_get(ticket=position_ticket)
        
        if open_positions:
            # Position is still open
            pos = open_positions[0]
            current_profit = pos.profit
            return jsonify({
                'status': 'open',
                'position_ticket': position_ticket,
                'current_profit': round(current_profit, 2),
                'message': f'Position still open, current profit: ${current_profit:.2f}'
            })
        
        # Position is closed, get deals
        position_deals = mt5.history_deals_get(position=position_ticket)
        
        if not position_deals:
            return jsonify({
                'status': 'found',
                'message': 'Trade found but position deals unavailable',
                'position_ticket': position_ticket
            })
        
        # Calculate total profit
        total_profit = 0.0
        close_price = 0.0
        is_closed = False
        
        for deal in position_deals:
            if deal.entry == mt5.DEAL_ENTRY_OUT:
                total_profit += deal.profit + deal.swap + deal.commission
                close_price = deal.price
                is_closed = True
        
        if is_closed:
            return jsonify({
                'status': 'closed',
                'position_ticket': position_ticket,
                'profit': round(total_profit, 2),
                'close_price': round(close_price, 5),
                'result': 'win' if total_profit > 0 else 'loss',
                'message': f'Trade closed with profit: ${total_profit:.2f}'
            })
        else:
            return jsonify({
                'status': 'unknown',
                'position_ticket': position_ticket,
                'message': 'Position found but closing deal not found'
            })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        mt5.shutdown()

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
    
    # Analysis points
    if result == 'win':
        analysis['analysis'].append({
            'type': 'success',
            'title': '✅ Trade Won',
            'message': f"Trade closed with profit of ${order_info.get('profit', 0):.2f}"
        })
        
        # Check if SL/TP ratio is good
        if signal_dict['sl'] and signal_dict['tp']:
            sl_tp_ratio = abs((signal_dict['tp'] - signal_dict['price']) / (signal_dict['price'] - signal_dict['sl']))
            if sl_tp_ratio >= 1.5:
                analysis['analysis'].append({
                    'type': 'info',
                    'title': '📊 Good Risk/Reward',
                    'message': f"SL/TP ratio: {sl_tp_ratio:.2f} (Target is {sl_tp_ratio:.1f}x the risk)"
                })
            else:
                analysis['recommendations'].append({
                    'type': 'warning',
                    'title': '⚠️ Improve Risk/Reward',
                    'message': f"Current SL/TP ratio: {sl_tp_ratio:.2f}. Consider increasing TP to at least 1.5x SL distance"
                })
        
        # Compare with average
        if avg_profit > 0 and order_info.get('profit', 0) < avg_profit * 0.5:
            analysis['recommendations'].append({
                'type': 'info',
                'title': '💡 Below Average Win',
                'message': f"This win (${order_info.get('profit', 0):.2f}) is below average (${avg_profit:.2f}). Consider trailing stop to lock more profit."
            })
    
    elif result == 'loss':
        analysis['analysis'].append({
            'type': 'error',
            'title': '❌ Trade Lost',
            'message': f"Trade closed with loss of ${abs(order_info.get('profit', 0)):.2f}"
        })
        
        # Check exit reason
        if order_info.get('close_price') and signal_dict['sl']:
            sl_distance = abs(order_info['close_price'] - signal_dict['sl'])
            tp_distance = abs(order_info['close_price'] - signal_dict['tp']) if signal_dict['tp'] else float('inf')
            
            if sl_distance < 0.1:  # Hit SL
                analysis['analysis'].append({
                    'type': 'error',
                    'title': '🛑 Hit Stop Loss',
                    'message': f"Price hit SL at {signal_dict['sl']:.5f}"
                })
                
                # Recommendations for SL hits
                if indicators:
                    if 'rsi' in indicators:
                        rsi = indicators['rsi']
                        if signal_dict['signal_type'] == 'BUY' and rsi > 70:
                            analysis['recommendations'].append({
                                'type': 'warning',
                                'title': '⚠️ Overbought Entry',
                                'message': f"RSI was {rsi:.1f} (overbought) when entering BUY. Consider waiting for RSI < 60 or add RSI filter."
                            })
                        elif signal_dict['signal_type'] == 'SELL' and rsi < 30:
                            analysis['recommendations'].append({
                                'type': 'warning',
                                'title': '⚠️ Oversold Entry',
                                'message': f"RSI was {rsi:.1f} (oversold) when entering SELL. Consider waiting for RSI > 40 or add RSI filter."
                            })
                
                # Check SL distance
                if signal_dict['sl'] and signal_dict['price']:
                    sl_distance_pips = abs(signal_dict['price'] - signal_dict['sl']) * 10  # Approximate for XAUUSD
                    if sl_distance_pips < 50:
                        analysis['recommendations'].append({
                            'type': 'warning',
                            'title': '⚠️ SL Too Tight',
                            'message': f"SL distance: ~{sl_distance_pips:.1f} pips. Consider widening SL to at least 50-100 pips to avoid noise."
                        })
                    elif sl_distance_pips > 200:
                        analysis['recommendations'].append({
                            'type': 'info',
                            'title': '💡 SL Too Wide',
                            'message': f"SL distance: ~{sl_distance_pips:.1f} pips. Consider tightening SL to reduce risk per trade."
                        })
            
            elif tp_distance < 0.1:  # Hit TP (shouldn't happen for loss)
                pass
            else:
                analysis['analysis'].append({
                    'type': 'warning',
                    'title': '👤 Manual Close',
                    'message': f"Trade closed manually at {order_info.get('close_price', 0):.5f}"
                })
        
        # Compare with average loss
        if avg_loss > 0 and abs(order_info.get('profit', 0)) > avg_loss * 1.5:
            analysis['recommendations'].append({
                'type': 'error',
                'title': '🔴 Larger Than Average Loss',
                'message': f"This loss (${abs(order_info.get('profit', 0)):.2f}) is {abs(order_info.get('profit', 0)) / avg_loss:.1f}x the average loss (${avg_loss:.2f}). Review entry conditions."
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
    
    # General recommendations based on statistics
    if win_rate > 0:
        if win_rate < 40:
            analysis['recommendations'].append({
                'type': 'error',
                'title': '🔴 Low Win Rate',
                'message': f"Recent win rate: {win_rate:.1f}%. Consider tightening entry filters or reviewing strategy logic."
            })
        elif win_rate >= 60:
            analysis['recommendations'].append({
                'type': 'success',
                'title': '✅ Good Win Rate',
                'message': f"Recent win rate: {win_rate:.1f}%. Strategy is performing well."
            })
        
        if avg_profit > 0 and avg_loss > 0:
            pf = avg_profit / avg_loss
            if pf < 1.0:
                analysis['recommendations'].append({
                    'type': 'error',
                    'title': '🔴 Negative Profit Factor',
                    'message': f"Profit Factor: {pf:.2f}. Average loss exceeds average win. Review risk management."
                })
            elif pf < 1.5:
                analysis['recommendations'].append({
                    'type': 'warning',
                    'title': '⚠️ Low Profit Factor',
                    'message': f"Profit Factor: {pf:.2f}. Aim for at least 1.5. Consider improving TP targets or reducing SL size."
                })
    
    # Indicator-based recommendations
    if indicators:
        if 'rsi' in indicators:
            rsi = indicators['rsi']
            if rsi > 70:
                analysis['recommendations'].append({
                    'type': 'warning',
                    'title': '📊 RSI Overbought',
                    'message': f"RSI: {rsi:.1f}. Market is overbought. Consider waiting for pullback or adding RSI filter < 70 for BUY signals."
                })
            elif rsi < 30:
                analysis['recommendations'].append({
                    'type': 'warning',
                    'title': '📊 RSI Oversold',
                    'message': f"RSI: {rsi:.1f}. Market is oversold. Consider waiting for bounce or adding RSI filter > 30 for SELL signals."
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
    query = """
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
            o.account_id,
            s.timestamp as signal_timestamp,
            s.indicators as signal_indicators,
            s.status as signal_status
        FROM orders o
        LEFT JOIN signals s ON o.strategy_name = s.strategy_name 
            AND o.symbol = s.symbol 
            AND o.order_type = s.signal_type
            AND ABS((julianday(o.open_time) - julianday(s.timestamp)) * 24 * 60) < 30
        WHERE o.open_time >= ?
    """
    
    params = [cutoff_str]
    
    # Add strategy filter if specified
    if strategy_param and strategy_param != 'all':
        query += " AND o.strategy_name = ?"
        params.append(strategy_param)
    
    query += " ORDER BY o.open_time DESC"
    
    cur.execute(query, tuple(params))
    orders = cur.fetchall()
    
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

# ==========================================
# BOT CONTROL APIS (START / STOP / STATUS)
# ==========================================

@app.route('/api/bot_status')
def api_bot_status():
    """Lấy trạng thái thực tế của tất cả các bot"""
    running = get_running_bots()
    bots_info = []
    for filename, meta in VALID_BOTS.items():
        is_running = filename in running
        bots_info.append({
            'file': filename,
            'name': meta['name'],
            'version': meta['version'],
            'desc': meta['desc'],
            'badge': meta.get('badge', 'bg-secondary'),
            'running': is_running,
            'pid': running.get(filename)
        })
    return jsonify({
        'success': True,
        'bots': bots_info,
        'running_count': len(running)
    })

@app.route('/api/start_bot', methods=['POST'])
def api_start_bot():
    """Khởi chạy một bot hoặc tất cả các bot"""
    data = request.get_json() or {}
    bot_file = data.get('bot')
    
    if bot_file == 'all':
        started = []
        running = get_running_bots()
        for b, meta in VALID_BOTS.items():
            if b != 'update_db.py' and b not in running:
                _launch_bot_process(b, meta['name'])
                started.append(meta['name'])
        if started:
            return jsonify({'success': True, 'message': f"Đã gửi lệnh khởi chạy: {', '.join(started)}"})
        return jsonify({'success': True, 'message': "Tất cả các chiến lược giao dịch đã đang chạy!"})
        
    if bot_file not in VALID_BOTS:
        return jsonify({'success': False, 'message': f'Bot "{bot_file}" không hợp lệ!'}), 400
        
    running = get_running_bots()
    if bot_file in running:
        return jsonify({'success': False, 'message': f"Bot {VALID_BOTS[bot_file]['name']} đang chạy rồi (PID: {running[bot_file]})"})
        
    _launch_bot_process(bot_file, VALID_BOTS[bot_file]['name'])
    return jsonify({'success': True, 'message': f"Đã khởi chạy thành công {VALID_BOTS[bot_file]['name']} trong cửa sổ riêng!"})

@app.route('/api/stop_bot', methods=['POST'])
def api_stop_bot():
    """Dừng bot bằng PID"""
    data = request.get_json() or {}
    bot_file = data.get('bot')
    running = get_running_bots()
    
    if bot_file == 'all':
        stopped = []
        for b, pid in running.items():
            try:
                if psutil:
                    p = psutil.Process(pid)
                    for child in p.children(recursive=True):
                        child.terminate()
                    p.terminate()
                    stopped.append(VALID_BOTS.get(b, {}).get('name', b))
            except Exception as e:
                print(f"Lỗi khi dừng PID {pid}: {e}")
        return jsonify({'success': True, 'message': f"Đã dừng {len(stopped)} bot ({', '.join(stopped)})"})
        
    if bot_file in running:
        pid = running[bot_file]
        try:
            if psutil:
                p = psutil.Process(pid)
                for child in p.children(recursive=True):
                    child.terminate()
                p.terminate()
            return jsonify({'success': True, 'message': f"Đã dừng bot {VALID_BOTS.get(bot_file, {}).get('name', bot_file)} (PID: {pid})"})
        except Exception as e:
            return jsonify({'success': False, 'message': f"Lỗi khi dừng bot: {e}"}), 500
            
    return jsonify({'success': False, 'message': f"Bot {bot_file} hiện không chạy!"}), 400

@app.route('/api/open_positions')
def api_open_positions():
    """Lấy danh sách lệnh đang mở và trạng thái tài khoản MT5"""
    return jsonify(get_mt5_account_and_positions())

@app.route('/api/sync_db', methods=['POST'])
def api_sync_db():
    """Thực thi update_db để đồng bộ dữ liệu MT5 vào trades.db trực tiếp từ Web"""
    try:
        from update_db import main as run_update_db
        run_update_db()
        return jsonify({'success': True, 'message': 'Đồng bộ MT5 vào Database thành công!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khi đồng bộ MT5: {str(e)}'}), 500

if __name__ == '__main__':
    print(f"🚀 Dashboard running on http://127.0.0.1:5007")
    app.run(debug=True, port=5007)
