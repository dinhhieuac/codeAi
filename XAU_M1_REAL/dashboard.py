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
from utils import connect_mt5, load_config, load_accounts, get_accounts_file_path
from update_db import load_strategy_configs

# Định nghĩa các bot giao dịch, script hỗ trợ và file cấu hình tương ứng
VALID_BOTS = {
    'strategy_1_trend_ha_multi.py': {
        'name': 'HA Multi-Exp',
        'version': 'Multi-Exp',
        'desc': 'Chạy song song nhiều cấu hình thử nghiệm (config_exp_*.json)',
        'badge': 'bg-primary text-light',
        'config': 'configs/config_exp_1.json',
        'is_multi': True
    },
    'strategy_1_trend_ha_v2.py': {
        'name': 'HA v2.0',
        'version': 'V2.0 (Khuyên dùng)',
        'desc': 'ADX, CHOP filter, ATR-based SL & trailing',
        'badge': 'bg-success',
        'config': 'configs/config_1_v2.json'
    },
    'strategy_1_trend_ha_v1.1.py': {
        'name': 'HA v1.1',
        'version': 'V1.1',
        'desc': 'Trend Heiken Ashi v1.1',
        'badge': 'bg-primary',
        'config': 'configs/config_1_v1.1.json'
    },
    'strategy_1_trend_ha_v2.1.py': {
        'name': 'HA v2.1',
        'version': 'V2.1',
        'desc': 'Trend Heiken Ashi v2.1',
        'badge': 'bg-info',
        'config': 'configs/config_1_v2.1.json'
    },
    'strategy_1_trend_ha_v3.py': {
        'name': 'HA v3.0',
        'version': 'V3.0',
        'desc': 'Trend Heiken Ashi v3.0 (Strict Entry)',
        'badge': 'bg-warning text-dark',
        'config': 'configs/config_1_v3.json'
    },
    'strategy_1_trend_ha.py': {
        'name': 'HA Original',
        'version': 'Gốc',
        'desc': 'Trend Heiken Ashi bản khởi tạo',
        'badge': 'bg-secondary',
        'config': 'configs/config_1.json'
    },
    'strategy_2_ema_atr.py': {
        'name': 'EMA ATR',
        'version': 'Strategy 2',
        'desc': 'EMA crossover kết hợp ATR trailing stop',
        'badge': 'bg-primary',
        'config': 'configs/config_2.json'
    },
    'strategy_3_pa_volume.py': {
        'name': 'PA Volume',
        'version': 'Strategy 3',
        'desc': 'Price Action kết hợp volume breakout',
        'badge': 'bg-info',
        'config': 'configs/config_3.json'
    },
    'strategy_4_ut_bot.py': {
        'name': 'UT Bot',
        'version': 'Strategy 4',
        'desc': 'UT Bot Alerts ATR trailing stop',
        'badge': 'bg-secondary',
        'config': 'configs/config_4.json'
    },
    'strategy_5_filter_first.py': {
        'name': 'Filter First',
        'version': 'Strategy 5',
        'desc': 'Lọc đa khung thời gian trước khi vào lệnh',
        'badge': 'bg-dark',
        'config': 'configs/config_5.json'
    },
    'update_db.py': {
        'name': 'Update DB',
        'version': 'Sync Tool',
        'desc': 'Đồng bộ lịch sử lệnh từ MT5 vào trades.db',
        'badge': 'bg-dark',
        'config': None
    },
}

def get_running_bots():
    """Kiểm tra chính xác xem các bot nào đang thực sự chạy bằng Python trên hệ thống"""
    running = {}
    if not psutil:
        return running
    try:
        python_names = {'python.exe', 'python', 'pythonw.exe', 'pythonw', 'py.exe', 'py'}
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pname = (proc.info.get('name') or '').lower()
                if pname not in python_names:
                    continue
                cmdline = proc.info.get('cmdline') or []
                # Bỏ qua các lệnh chạy inline test python -c "..."
                if '-c' in cmdline or any(arg.startswith('-c') for arg in cmdline):
                    continue
                
                for arg in cmdline:
                    arg_base = os.path.basename(arg).lower()
                    for bot_file in VALID_BOTS:
                        if arg_base == bot_file.lower():
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

import time

_mt5_status_cache = {'time': 0, 'data': None}

def get_mt5_account_and_positions():
    """Lấy thông tin tài khoản và các vị thế đang mở từ MT5 một cách THỤ ĐỘNG với Cache.
    Tuyệt đối không gọi connect_mt5 kèm login/password để không kích hoạt cơ chế
    bảo mật tự động tắt Algo Trading của phần mềm MetaTrader 5."""
    global _mt5_status_cache
    now = time.time()
    if now - _mt5_status_cache['time'] < 3 and _mt5_status_cache['data'] is not None:
        return _mt5_status_cache['data']

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
    
    try:
        # Tìm đường dẫn MT5 khả dụng từ accounts.json hoặc default
        candidate_paths = [
            "C:/Program Files/MetaTrader 5/terminal64.exe",
            "C:/Program Files/MT183677261/terminal64.exe"
        ]
        try:
            accs = load_accounts()
            for acc_cfg in accs.values():
                p = acc_cfg.get('mt5_path')
                if p and p not in candidate_paths and os.path.exists(p):
                    candidate_paths.insert(0, p)
        except Exception:
            pass

        init_ok = False
        for p in candidate_paths:
            if os.path.exists(p):
                if mt5.initialize(path=p, timeout=1000):
                    init_ok = True
                    break

        if not init_ok:
            if not mt5.initialize(timeout=1000):
                _mt5_status_cache['time'] = now
                _mt5_status_cache['data'] = result
                return result
            
        acc_info = mt5.account_info()
        if not acc_info:
            _mt5_status_cache['time'] = now
            _mt5_status_cache['data'] = result
            return result
            
        result['connected'] = True
        result['account'] = acc_info.login
        result['server'] = acc_info.server
        result['balance'] = round(acc_info.balance, 2)
        result['equity'] = round(acc_info.equity, 2)
        
        positions = mt5.positions_get()
        pos_list = []
        total_profit = 0.0
        magic_label_map = {
            100021: "HA Multi (Exp 1 - #100021)",
            100022: "HA Multi (Exp 2 - #100022)",
            100002: "HA v2.0 (#100002)",
            100003: "HA v2.1/v3.0 (#100003)",
            100011: "HA v1.1 (#100011)",
            100001: "HA Original (#100001)",
            2000: "EMA ATR (#2000)",
            3000: "PA Volume (#3000)",
            4000: "UT Bot (#4000)",
            5000: "Filter First (#5000)"
        }
        for p in (positions or []):
            total_profit += p.profit
            bot_lbl = magic_label_map.get(p.magic)
            if not bot_lbl and p.magic > 0:
                bot_lbl = f"Magic #{p.magic}"
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
                'comment': p.comment,
                'bot_label': bot_lbl
            })
        result['positions_count'] = len(pos_list)
        result['floating_profit'] = round(total_profit, 2)
        result['positions'] = pos_list
    except Exception:
        pass
        
    _mt5_status_cache['time'] = now
    _mt5_status_cache['data'] = result
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

def format_strategy_display_name(strat):
    """Định dạng tên hiển thị thân thiện, chuyên nghiệp cho từng chiến lược và cấu hình thử nghiệm"""
    if not strat:
        return "Unknown"
    if "100021" in strat:
        return "HA Multi (Exp 1 - #100021)"
    if "100022" in strat:
        return "HA Multi (Exp 2 - #100022)"
    if strat.startswith("Strategy_1_Trend_HA_V2_"):
        magic_part = strat.replace("Strategy_1_Trend_HA_V2_", "")
        return f"HA Multi (Exp - #{magic_part})"
    if strat == "Strategy_1_Trend_HA_V2":
        return "HA v2.0"
    if strat == "Strategy_1_Trend_HA_V2.1":
        return "HA v2.1"
    if strat == "Strategy_1_Trend_HA_V3":
        return "HA v3.0"
    if strat == "Strategy_1_Trend_HA_V1.1":
        return "HA v1.1"
    if strat == "Strategy_1_Trend_HA":
        return "HA Original"
    if strat == "Strategy_2_EMA_ATR":
        return "EMA ATR"
    if strat == "Strategy_3_PA_Volume":
        return "PA Volume"
    if strat == "Strategy_4_UT_Bot":
        return "UT Bot"
    if strat == "Strategy_5_Filter_First":
        return "Filter First"
    return strat.replace("Strategy_", "").replace("_", " ")

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
            "name": format_strategy_display_name(strat),
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
        "Strategy_1_Trend_HA_V2",
        "Strategy_1_Trend_HA_V2_100021",
        "Strategy_1_Trend_HA_V2_100022",
        "Strategy_1_Trend_HA_V2.1",
        "Strategy_1_Trend_HA_V3",
        "Strategy_1_Trend_HA_V1.1",
        "Strategy_1_Trend_HA",
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

    # Bổ sung thông tin khung giờ giao dịch & thông số chính của bot
    base_dir = os.path.dirname(os.path.abspath(__file__))
    accounts_dict = load_accounts()
    enriched_bots = {}
    for bot_file, meta in VALID_BOTS.items():
        m = dict(meta)
        cfg_path = m.get('config')
        session_info = {'enabled': True, 'start': '08:00', 'end': '22:00', 'display': '08:00 - 22:00'}
        params_summary = None
        if m.get('is_multi'):
            try:
                configs_dir = os.path.join(base_dir, 'configs')
                exp_files = sorted([f for f in os.listdir(configs_dir) if f.startswith('config_exp_') and f.endswith('.json')])
                magics = []
                accs = []
                for ef in exp_files:
                    try:
                        with open(os.path.join(configs_dir, ef), 'r', encoding='utf-8') as f:
                            edata = json.load(f)
                            if 'magic' in edata:
                                magics.append(str(edata['magic']))
                            aid = edata.get('account_id')
                            if aid and aid in accounts_dict:
                                accs.append(str(accounts_dict[aid].get('account', aid)))
                            elif edata.get('account'):
                                accs.append(str(edata.get('account')))
                    except Exception:
                        pass
                magic_disp = ", ".join(magics) if magics else "--"
                acc_disp = ", ".join(list(dict.fromkeys(accs))) if accs else "--"
                params_summary = {
                    'symbol': 'XAUUSDc (Multi)',
                    'volume': f"{len(exp_files)} Files",
                    'max_positions': len(exp_files),
                    'magic': magic_disp,
                    'account_no': acc_disp,
                    'account_name': f"{len(exp_files)} cấu hình thử nghiệm",
                    'sl_display': 'Riêng từng',
                    'tp_display': 'config',
                    'trailing': True,
                    'trailing_mode': 'MULTI',
                    'breakeven': True,
                    'key_ind': f"{len(exp_files)} files: {', '.join(exp_files)}"
                }
                session_info = {
                    'enabled': False,
                    'start': 'ALL',
                    'end': 'TIME',
                    'display': 'Theo từng file config'
                }
            except Exception:
                pass
        elif cfg_path:
            full_cfg_path = os.path.join(base_dir, cfg_path)
            if os.path.exists(full_cfg_path):
                try:
                    with open(full_cfg_path, 'r', encoding='utf-8') as f:
                        cdata = json.load(f)
                    p = cdata.get('parameters', {})
                    
                    acc_id = cdata.get('account_id')
                    acc_info = accounts_dict.get(acc_id, {}) if acc_id else {}
                    acc_no = acc_info.get('account') or cdata.get('account', '--')
                    acc_name = acc_info.get('name') or f"TK {acc_no}"
                    sym = cdata.get('symbol') or acc_info.get('symbol', 'XAUUSDc')
                    vol = cdata.get('volume', 0.01)
                    magic = cdata.get('magic', '--')
                    max_pos = cdata.get('max_positions', 1)

                    sl_mode = p.get('sl_mode', 'auto_m5')
                    if sl_mode == 'auto_m5':
                        sl_disp = 'Auto M5'
                    elif sl_mode == 'atr':
                        sl_disp = 'ATR'
                    elif sl_mode == 'fixed':
                        sl_disp = f"{p.get('sl_pips', 20)}p"
                    else:
                        sl_disp = str(sl_mode)
                        
                    rr = p.get('reward_ratio')
                    if rr:
                        tp_disp = f"1:{rr}"
                    elif p.get('tp_pips'):
                        tp_disp = f"{p.get('tp_pips')}p"
                    else:
                        tp_disp = '1:1.5'

                    trail_en = bool(p.get('trailing_enabled', True))
                    trail_mode = str(p.get('trailing_mode', 'atr')).upper()
                    be_en = bool(p.get('breakeven_enabled', True))

                    key_ind = []
                    if 'adx_min_threshold' in p:
                        key_ind.append(f"ADX>{p['adx_min_threshold']}")
                    if 'rsi_buy_threshold' in p and 'rsi_sell_threshold' in p:
                        key_ind.append(f"RSI:{p['rsi_sell_threshold']}/{p['rsi_buy_threshold']}")
                    elif 'rsi_threshold' in p:
                        key_ind.append(f"RSI:{p['rsi_threshold']}")
                    if p.get('confirmation_enabled'):
                        key_ind.append("Conf:ON")

                    params_summary = {
                        'symbol': sym,
                        'volume': vol,
                        'max_positions': max_pos,
                        'magic': magic,
                        'account_no': str(acc_no),
                        'account_name': acc_name,
                        'sl_display': sl_disp,
                        'tp_display': tp_disp,
                        'trailing': trail_en,
                        'trailing_mode': trail_mode,
                        'breakeven': be_en,
                        'key_ind': " | ".join(key_ind) if key_ind else None
                    }

                    filt_en = p.get('session_filter_enabled')
                    if filt_en is None:
                        filt_en = str(p.get('allowed_sessions', '')).upper() != 'ALL'
                    
                    s_time = p.get('trading_start_time', '08:00')
                    e_time = p.get('trading_end_time', '22:00')
                    if 'allowed_sessions' in p and '-' in str(p['allowed_sessions']):
                        parts = str(p['allowed_sessions']).split('-')
                        if len(parts) == 2:
                            s_time, e_time = parts[0].strip(), parts[1].strip()
                    
                    session_info = {
                        'enabled': bool(filt_en),
                        'start': s_time,
                        'end': e_time,
                        'display': f"{s_time} - {e_time}" if filt_en else "ALL TIME (24/5)"
                    }
                except Exception:
                    pass
        m['session'] = session_info
        m['params_summary'] = params_summary
        enriched_bots[bot_file] = m

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
                           valid_bots=enriched_bots,
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
            'config': meta.get('config'),
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

@app.route('/api/order_history/<int:ticket>')
def api_order_history(ticket):
    """Lấy toàn bộ lịch sử chi tiết và tiến trình dời SL của một lệnh theo ticket"""
    conn = get_db()
    cur = conn.cursor()
    
    # 1. Truy vấn thông tin lệnh từ bảng orders
    cur.execute("SELECT * FROM orders WHERE ticket = ?", (ticket,))
    order_row = cur.fetchone()
    order_dict = dict(order_row) if order_row else None
    
    # 2. Truy vấn danh sách sự kiện từ bảng order_logs
    try:
        cur.execute("""
            SELECT id, ticket, timestamp, event_type, old_sl, new_sl, old_tp, new_tp, 
                   current_price, profit_pips, profit_usd, reason, details 
            FROM order_logs 
            WHERE ticket = ? 
            ORDER BY timestamp ASC, id ASC
        """, (ticket,))
        logs = [dict(row) for row in cur.fetchall()]
    except Exception:
        logs = []
        
    # 3. Kiểm tra xem lệnh có đang mở trực tiếp trên MT5 hay không
    live_pos_info = None
    try:
        if mt5.initialize():
            positions = mt5.positions_get(ticket=ticket)
            if positions:
                p = positions[0]
                symbol_info = mt5.symbol_info(p.symbol)
                pip_size = (symbol_info.point * 10) if (symbol_info and 'XAU' not in p.symbol.upper()) else (symbol_info.point if symbol_info and symbol_info.point >= 0.01 else 0.1)
                curr_price = p.price_current
                profit_pips = ((curr_price - p.price_open) if p.type == mt5.ORDER_TYPE_BUY else (p.price_open - curr_price)) / pip_size
                live_pos_info = {
                    'is_open': True,
                    'current_price': p.price_current,
                    'current_sl': p.sl,
                    'current_tp': p.tp,
                    'profit_usd': round(p.profit, 2),
                    'profit_pips': round(profit_pips, 1),
                    'comment': p.comment,
                    'magic': p.magic
                }
    except Exception:
        pass

    # Đảm bảo timeline luôn có mốc ENTRY và EXIT đầy đủ
    if order_dict:
        has_entry = any(l.get('event_type') == 'ENTRY' for l in logs)
        if not has_entry:
            init_sl = order_dict.get('initial_sl') or order_dict.get('sl')
            logs.insert(0, {
                'timestamp': order_dict.get('open_time'),
                'event_type': 'ENTRY',
                'old_sl': init_sl,
                'new_sl': init_sl,
                'old_tp': order_dict.get('tp'),
                'new_tp': order_dict.get('tp'),
                'current_price': order_dict.get('open_price'),
                'profit_pips': 0.0,
                'profit_usd': 0.0,
                'reason': f"Khởi tạo lệnh {order_dict.get('order_type')} {order_dict.get('volume')} lot tại giá {order_dict.get('open_price')}",
                'details': ''
            })
        if order_dict.get('profit') is not None and order_dict.get('close_time'):
            has_exit = any(l.get('event_type') == 'EXIT' for l in logs)
            if not has_exit:
                logs.append({
                    'timestamp': order_dict.get('close_time'),
                    'event_type': 'EXIT',
                    'old_sl': order_dict.get('sl'),
                    'new_sl': order_dict.get('sl'),
                    'old_tp': order_dict.get('tp'),
                    'new_tp': order_dict.get('tp'),
                    'current_price': order_dict.get('close_price'),
                    'profit_pips': None,
                    'profit_usd': order_dict.get('profit'),
                    'reason': f"Đóng lệnh tại giá {order_dict.get('close_price')}, Lợi nhuận: ${order_dict.get('profit'):.2f}",
                    'details': ''
                })

    return jsonify({
        'success': True,
        'ticket': ticket,
        'order': order_dict,
        'logs': logs,
        'live_pos': live_pos_info
    })

def safe_sync_db():
    """Đồng bộ lịch sử lệnh và vị thế từ MT5 vào trades.db an toàn:
    1. Kết nối thụ động vào terminal MT5 đang mở (thử các đường dẫn từ accounts.json nếu cần).
    2. Quét toàn bộ vị thế đang mở và lịch sử deal khớp lệnh của các bot/magic.
    3. Tự động nhập (import) các lệnh bị thiếu vào bảng orders trong trades.db.
    4. Cập nhật close_price, profit, close_time cho các lệnh đã đóng.
    5. Tuyệt đối không gọi mt5.shutdown() hay re-login để bảo vệ Algo Trading.
    """
    candidate_paths = [
        "C:/Program Files/MetaTrader 5/terminal64.exe",
        "C:/Program Files/MT184164131/terminal64.exe",
        "C:/Program Files/MT183677261/terminal64.exe"
    ]
    try:
        accs = load_accounts()
        for acc_cfg in accs.values():
            p = acc_cfg.get('mt5_path')
            if p and p not in candidate_paths and os.path.exists(p):
                candidate_paths.insert(0, p)
    except Exception:
        pass

    init_ok = False
    acc = mt5.account_info()
    if acc:
        init_ok = True
    else:
        for p in candidate_paths:
            if os.path.exists(p):
                if mt5.initialize(path=p, timeout=2000):
                    acc = mt5.account_info()
                    if acc:
                        init_ok = True
                        break
        if not init_ok:
            if mt5.initialize(timeout=2000):
                acc = mt5.account_info()
                init_ok = bool(acc)

    if not init_ok or not acc:
        return False, "Không thể kết nối với MetaTrader 5 (MT5 chưa được mở hoặc chưa đăng nhập)"

    active_login = acc.login
    base_dir = os.path.dirname(os.path.abspath(__file__))
    configs_dir = os.path.join(base_dir, 'configs')

    # Xây dựng bảng map Magic -> Strategy Name & Comment Prefix -> Strategy Name
    magic_map = {
        100021: "Strategy_1_Trend_HA_V2_100021",
        100022: "Strategy_1_Trend_HA_V2_100022",
        100002: "Strategy_1_Trend_HA_V2",
        100003: "Strategy_1_Trend_HA_V2.1",
        100011: "Strategy_1_Trend_HA_V1.1",
        100001: "Strategy_1_Trend_HA",
        2000: "Strategy_2_EMA_ATR",
        3000: "Strategy_3_PA_Volume",
        4000: "Strategy_4_UT_Bot",
        5000: "Strategy_5_Filter_First"
    }
    comment_map = {
        "exp1": "Strategy_1_Trend_HA_V2_100021",
        "exp2": "Strategy_1_Trend_HA_V2_100022",
        "s1_100021": "Strategy_1_Trend_HA_V2_100021",
        "s1_100022": "Strategy_1_Trend_HA_V2_100022",
    }

    # Quét thêm từ các file config nếu có
    if os.path.exists(configs_dir):
        for f in os.listdir(configs_dir):
            if f.endswith('.json') and (f.startswith('config_') or f.startswith('config_exp_')):
                try:
                    with open(os.path.join(configs_dir, f), 'r', encoding='utf-8') as jf:
                        cdata = json.load(jf)
                        m = cdata.get('magic')
                        if m:
                            if f.startswith('config_exp_'):
                                s_name = f"Strategy_1_Trend_HA_V2_{m}"
                            elif 'v2.1' in f:
                                s_name = "Strategy_1_Trend_HA_V2.1"
                            elif 'v2' in f:
                                s_name = "Strategy_1_Trend_HA_V2"
                            elif 'v3' in f:
                                s_name = "Strategy_1_Trend_HA_V3"
                            elif 'v1.1' in f:
                                s_name = "Strategy_1_Trend_HA_V1.1"
                            elif 'config_2' in f:
                                s_name = "Strategy_2_EMA_ATR"
                            elif 'config_3' in f:
                                s_name = "Strategy_3_PA_Volume"
                            elif 'config_4' in f:
                                s_name = "Strategy_4_UT_Bot"
                            elif 'config_5' in f:
                                s_name = "Strategy_5_Filter_First"
                            else:
                                s_name = f"Strategy_Unknown_{m}"
                            magic_map[m] = s_name
                        cm = cdata.get('order_comment') or cdata.get('parameters', {}).get('order_comment')
                        if cm and m:
                            comment_map[str(cm).lower()] = magic_map[m]
                except Exception:
                    pass

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Đảm bảo các cột cần thiết tồn tại
    try:
        cur.execute("PRAGMA table_info(orders)")
        cols = [c[1] for c in cur.fetchall()]
        if 'close_time' not in cols:
            cur.execute("ALTER TABLE orders ADD COLUMN close_time DATETIME")
        if 'account_id' not in cols:
            cur.execute("ALTER TABLE orders ADD COLUMN account_id INTEGER DEFAULT 0")
        if 'initial_sl' not in cols:
            cur.execute("ALTER TABLE orders ADD COLUMN initial_sl REAL")
        conn.commit()
    except Exception:
        pass

    # Lấy danh sách lệnh hiện có trong DB
    cur.execute("SELECT ticket, strategy_name, profit, close_price, close_time FROM orders")
    existing_orders = {}
    for row in cur.fetchall():
        existing_orders[row[0]] = {
            'strategy_name': row[1],
            'profit': row[2],
            'close_price': row[3],
            'close_time': row[4]
        }

    imported_open = 0
    imported_history = 0
    updated_closed = 0

    def resolve_strategy(magic_no, comment_str):
        if magic_no and int(magic_no) in magic_map:
            return magic_map[int(magic_no)]
        if comment_str:
            c_low = comment_str.lower()
            for k, s in comment_map.items():
                if k in c_low:
                    return s
        if magic_no and int(magic_no) > 0:
            return f"Strategy_Auto_{magic_no}"
        return None

    # 1. Quét Open Positions từ MT5
    try:
        positions = mt5.positions_get()
        if positions:
            for p in positions:
                strat = resolve_strategy(p.magic, p.comment)
                if not strat:
                    continue
                if p.ticket not in existing_orders:
                    o_type = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                    o_time = datetime.fromtimestamp(p.time).strftime("%Y-%m-%d %H:%M:%S")
                    init_sl = p.sl if p.sl > 0 else p.price_open
                    cur.execute('''
                        INSERT OR IGNORE INTO orders (ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, open_time, comment, account_id, initial_sl)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (p.ticket, strat, p.symbol, o_type, p.volume, p.price_open, p.sl, p.tp, o_time, p.comment, active_login, init_sl))
                    existing_orders[p.ticket] = {'strategy_name': strat, 'profit': None, 'close_price': None, 'close_time': None}
                    imported_open += 1
    except Exception as e:
        print(f"Lỗi khi đồng bộ Open Positions: {e}")

    # 2. Quét History Deals từ MT5 (90 ngày gần nhất)
    try:
        from_date = datetime.now() - timedelta(days=90)
        to_date = datetime.now() + timedelta(days=1)
        deals = mt5.history_deals_get(from_date, to_date)
        if deals:
            deals_by_pos = {}
            for d in deals:
                if d.position_id > 0:
                    deals_by_pos.setdefault(d.position_id, []).append(d)

            for pos_id, d_list in deals_by_pos.items():
                in_deal = next((d for d in d_list if d.entry == mt5.DEAL_ENTRY_IN), None)
                out_deals = [d for d in d_list if d.entry == mt5.DEAL_ENTRY_OUT]
                
                # Xác định magic & comment
                d_magic = (in_deal.magic if in_deal else (d_list[0].magic if d_list else 0))
                d_comment = (in_deal.comment if in_deal else (d_list[0].comment if d_list else ""))
                strat = resolve_strategy(d_magic, d_comment)
                if not strat:
                    continue

                total_profit = sum(d.profit + d.swap + d.commission for d in d_list)
                is_closed = len(out_deals) > 0
                close_price = out_deals[-1].price if is_closed else None
                close_time = datetime.fromtimestamp(out_deals[-1].time).strftime("%Y-%m-%d %H:%M:%S") if is_closed else None

                if pos_id in existing_orders:
                    # Nếu lệnh đang mở trong DB nhưng trên MT5 đã đóng -> cập nhật
                    if existing_orders[pos_id]['profit'] is None and is_closed:
                        cur.execute('''
                            UPDATE orders 
                            SET close_price = ?, profit = ?, close_time = ? 
                            WHERE ticket = ?
                        ''', (close_price, round(total_profit, 2), close_time, pos_id))
                        try:
                            cur.execute('''
                                INSERT INTO order_logs (ticket, timestamp, event_type, old_sl, new_sl, old_tp, new_tp, current_price, profit_pips, profit_usd, reason, details)
                                VALUES (?, ?, 'EXIT', NULL, NULL, NULL, NULL, ?, NULL, ?, ?, NULL)
                            ''', (pos_id, close_time, close_price, round(total_profit, 2), f"Đóng lệnh tại giá {close_price:.2f} (Lợi nhuận: ${round(total_profit, 2):.2f})"))
                        except Exception:
                            pass
                        existing_orders[pos_id]['profit'] = round(total_profit, 2)
                        updated_closed += 1
                else:
                    # Lệnh chưa có trong DB -> nhập mới
                    if in_deal:
                        o_type = "BUY" if in_deal.type == mt5.DEAL_TYPE_BUY else "SELL"
                        o_time = datetime.fromtimestamp(in_deal.time).strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Tra cứu SL ban đầu từ MT5 order history
                        sl, tp, init_sl = 0.0, 0.0, 0.0
                        try:
                            h_orders = mt5.history_orders_get(ticket=pos_id)
                            if h_orders and len(h_orders) > 0:
                                sl = h_orders[0].sl
                                tp = h_orders[0].tp
                                init_sl = sl if sl > 0 else in_deal.price
                        except Exception:
                            pass
                        if not init_sl:
                            init_sl = sl if sl > 0 else in_deal.price

                        cur.execute('''
                            INSERT OR REPLACE INTO orders (ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, open_time, close_price, profit, close_time, comment, account_id, initial_sl)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (pos_id, strat, in_deal.symbol, o_type, in_deal.volume, in_deal.price, sl, tp, o_time, close_price, (round(total_profit, 2) if is_closed else None), close_time, d_comment, active_login, init_sl))
                        try:
                            cur.execute('''
                                INSERT INTO order_logs (ticket, timestamp, event_type, old_sl, new_sl, old_tp, new_tp, current_price, profit_pips, profit_usd, reason, details)
                                VALUES (?, ?, 'ENTRY', ?, ?, ?, ?, ?, 0.0, 0.0, ?, ?)
                            ''', (pos_id, o_time, init_sl, sl, tp, tp, in_deal.price, f"Mở lệnh {o_type} {in_deal.volume} lot tại giá {in_deal.price:.2f}", json.dumps({"strategy": strat, "comment": d_comment}, ensure_ascii=False)))
                            if is_closed and close_time:
                                cur.execute('''
                                    INSERT INTO order_logs (ticket, timestamp, event_type, old_sl, new_sl, old_tp, new_tp, current_price, profit_pips, profit_usd, reason, details)
                                    VALUES (?, ?, 'EXIT', NULL, NULL, NULL, NULL, ?, NULL, ?, ?, NULL)
                                ''', (pos_id, close_time, close_price, round(total_profit, 2), f"Đóng lệnh tại giá {close_price:.2f} (Lợi nhuận: ${round(total_profit, 2):.2f})"))
                        except Exception:
                            pass
                        imported_history += 1
                        existing_orders[pos_id] = {'strategy_name': strat, 'profit': round(total_profit, 2) if is_closed else None}
    except Exception as e:
        print(f"Lỗi khi đồng bộ History Deals: {e}")

    conn.commit()
    conn.close()

    return True, f"Đồng bộ thành công từ MT5 (TK: {active_login})! Nhập mới: {imported_open} vị thế mở, {imported_history} lệnh lịch sử; Cập nhật: {updated_closed} lệnh đã đóng."

@app.route('/api/sync_db', methods=['POST'])
def api_sync_db():
    """Thực thi đồng bộ an toàn dữ liệu MT5 vào trades.db trực tiếp từ Web"""
    try:
        success, msg = safe_sync_db()
        return jsonify({'success': success, 'message': msg}), (200 if success else 400)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khi đồng bộ MT5: {str(e)}'}), 500

# =========================================================================
# ACCOUNT CONFIGURATION APIS (GET / SAVE / DELETE)
# =========================================================================

@app.route('/api/accounts')
def api_get_accounts():
    """Lấy danh sách các tài khoản MT5 từ configs/accounts.json"""
    accounts_path = get_accounts_file_path()
    try:
        if os.path.exists(accounts_path):
            with open(accounts_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {"accounts": {}, "default_account": None}
            
        accounts = data.get("accounts", {})
        accounts_list = []
        for acc_id, acc_info in accounts.items():
            item = dict(acc_info)
            item['id'] = acc_id
            accounts_list.append(item)
            
        return jsonify({
            'success': True,
            'accounts': accounts,
            'accounts_list': accounts_list,
            'default_account': data.get("default_account")
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khi đọc file accounts.json: {str(e)}'}), 500

@app.route('/api/save_account', methods=['POST'])
def api_save_account():
    """Thêm mới hoặc cập nhật tài khoản MT5 vào configs/accounts.json"""
    data = request.get_json() or {}
    acc_id = data.get('id', '').strip()
    name = data.get('name', '').strip()
    account_no = data.get('account')
    password = data.get('password', '').strip()
    server = data.get('server', '').strip()
    mt5_path = data.get('mt5_path', '').strip()
    symbol = data.get('symbol', 'XAUUSDc').strip()
    is_default = data.get('is_default', False)
    
    if not account_no or not server:
        return jsonify({'success': False, 'message': 'Vui lòng nhập Số tài khoản và Server!'}), 400
        
    try:
        account_no = int(account_no)
    except ValueError:
        return jsonify({'success': False, 'message': 'Số tài khoản phải là số nguyên!'}), 400
        
    if not acc_id:
        acc_id = f"acc_{account_no}"
        
    if not name:
        name = f"Tài khoản {account_no} ({server})"
        
    accounts_path = get_accounts_file_path()
    try:
        raw_data = {"accounts": {}, "default_account": acc_id}
        if os.path.exists(accounts_path):
            with open(accounts_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
                
        if "accounts" not in raw_data:
            raw_data["accounts"] = {}
            
        raw_data["accounts"][acc_id] = {
            "name": name,
            "account": account_no,
            "password": password,
            "server": server,
            "mt5_path": mt5_path or "C:/Program Files/MetaTrader 5/terminal64.exe",
            "symbol": symbol or "XAUUSDc"
        }
        
        if is_default or not raw_data.get("default_account"):
            raw_data["default_account"] = acc_id
            
        with open(accounts_path, 'w', encoding='utf-8') as f:
            json.dump(raw_data, f, indent=4, ensure_ascii=False)
            
        return jsonify({
            'success': True,
            'message': f'Đã lưu thành công tài khoản "{name}" ({account_no})!',
            'account_id': acc_id,
            'account': raw_data["accounts"][acc_id]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khi ghi file accounts.json: {str(e)}'}), 500

@app.route('/api/delete_account', methods=['POST'])
def api_delete_account():
    """Xóa tài khoản MT5"""
    data = request.get_json() or {}
    acc_id = data.get('id', '').strip()
    if not acc_id:
        return jsonify({'success': False, 'message': 'Thiếu mã tài khoản (id) cần xóa!'}), 400
        
    accounts_path = get_accounts_file_path()
    try:
        if not os.path.exists(accounts_path):
            return jsonify({'success': False, 'message': 'Không tìm thấy file accounts.json!'}), 404
            
        with open(accounts_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        accounts = raw_data.get("accounts", {})
        if acc_id not in accounts:
            return jsonify({'success': False, 'message': f'Tài khoản "{acc_id}" không tồn tại!'}), 404
            
        del accounts[acc_id]
        if raw_data.get("default_account") == acc_id:
            raw_data["default_account"] = next(iter(accounts.keys())) if accounts else None
            
        with open(accounts_path, 'w', encoding='utf-8') as f:
            json.dump(raw_data, f, indent=4, ensure_ascii=False)
            
        return jsonify({'success': True, 'message': f'Đã xóa tài khoản {acc_id} thành công!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khi xóa tài khoản: {str(e)}'}), 500

# =========================================================================
# BOT CONFIGURATION APIS (GET CONFIG / SAVE CONFIG / RESTART BOT / MULTI EXP)
# =========================================================================

def _get_all_exp_configs(base_dir):
    """Liệt kê tất cả các file cấu hình thử nghiệm config_exp_*.json kèm magic number"""
    configs_dir = os.path.join(base_dir, 'configs')
    if not os.path.exists(configs_dir):
        return []
    exp_files = sorted([f for f in os.listdir(configs_dir) if f.startswith('config_exp_') and f.endswith('.json')])
    result = []
    for ef in exp_files:
        path = os.path.join(configs_dir, ef)
        magic = None
        comment = ""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                d = json.load(f)
                magic = d.get('magic')
                comment = d.get('parameters', {}).get('order_comment', '')
        except Exception:
            pass
        result.append({
            'filename': ef,
            'rel_path': f"configs/{ef}",
            'magic': magic,
            'comment': comment
        })
    return result

@app.route('/api/bot_config')
def api_get_bot_config():
    """Lấy nội dung cấu hình JSON của bot hoặc file thử nghiệm cụ thể"""
    bot_file = request.args.get('bot', '').strip()
    config_file_param = request.args.get('config_file', '').strip()
    
    if not bot_file or bot_file not in VALID_BOTS:
        return jsonify({'success': False, 'message': f'Bot "{bot_file}" không hợp lệ!'}), 400
        
    meta = VALID_BOTS[bot_file]
    base_dir = os.path.dirname(os.path.abspath(__file__))
    exp_configs = _get_all_exp_configs(base_dir)
    
    if config_file_param:
        clean_name = os.path.basename(config_file_param)
        config_rel = f"configs/{clean_name}"
    else:
        config_rel = meta.get('config')
        
    if not config_rel:
        return jsonify({'success': False, 'message': f'Bot {bot_file} không có file cấu hình!'}), 400
        
    config_path = os.path.normpath(os.path.join(base_dir, config_rel))
    
    if not os.path.exists(config_path):
        return jsonify({'success': False, 'message': f'Không tìm thấy file cấu hình: {config_rel}'}), 404
        
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        parsed = json.loads(raw_content)
        running = get_running_bots()
        accounts_dict = load_accounts()
        accounts_list = [{'id': k, **v} for k, v in accounts_dict.items()]
        return jsonify({
            'success': True,
            'bot': bot_file,
            'bot_name': meta['name'],
            'is_multi': meta.get('is_multi', False),
            'config_path': config_rel,
            'config_filename': os.path.basename(config_path),
            'exp_configs': exp_configs,
            'config_data': parsed,
            'config_raw': raw_content,
            'accounts_list': accounts_list,
            'is_running': bot_file in running,
            'pid': running.get(bot_file)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khi đọc file cấu hình: {str(e)}'}), 500

@app.route('/api/save_bot_config', methods=['POST'])
def api_save_bot_config():
    """Lưu và cập nhật lại file cấu hình JSON của bot hoặc file thử nghiệm"""
    data = request.get_json() or {}
    bot_file = data.get('bot', '').strip()
    config_file_param = data.get('config_file', '').strip()
    config_raw = data.get('config_raw')
    config_data = data.get('config_data')
    
    if not bot_file or bot_file not in VALID_BOTS:
        return jsonify({'success': False, 'message': f'Bot "{bot_file}" không hợp lệ!'}), 400
        
    meta = VALID_BOTS[bot_file]
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    if config_file_param:
        clean_name = os.path.basename(config_file_param)
        config_rel = f"configs/{clean_name}"
    else:
        config_rel = meta.get('config')
        
    if not config_rel:
        return jsonify({'success': False, 'message': f'Bot {bot_file} không hỗ trợ cấu hình!'}), 400
        
    config_path = os.path.normpath(os.path.join(base_dir, config_rel))
    
    # Kiểm tra JSON hợp lệ
    parsed_json = None
    if config_raw is not None:
        try:
            parsed_json = json.loads(config_raw)
        except Exception as e:
            return jsonify({'success': False, 'message': f'Cú pháp JSON không hợp lệ: {str(e)}'}), 400
    elif config_data is not None:
        parsed_json = config_data
    else:
        return jsonify({'success': False, 'message': 'Thiếu dữ liệu cấu hình để lưu!'}), 400
        
    try:
        # Ghi file với mã hóa UTF-8 và format đẹp (indent=4)
        formatted_json_str = json.dumps(parsed_json, indent=4, ensure_ascii=False)
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(formatted_json_str)
            
        running = get_running_bots()
        is_running = bot_file in running
        
        msg = f"Đã lưu thành công cấu hình {meta['name']} ({config_rel})!"
        if is_running:
            msg += f" (Lưu ý: Bot đang chạy với PID {running[bot_file]}, hãy khởi động lại bot để áp dụng cài đặt mới)."
            
        return jsonify({
            'success': True,
            'message': msg,
            'is_running': is_running,
            'pid': running.get(bot_file),
            'config_data': parsed_json,
            'config_raw': formatted_json_str,
            'config_filename': os.path.basename(config_path),
            'config_path': config_rel
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khi lưu file cấu hình: {str(e)}'}), 500

@app.route('/api/create_exp_config', methods=['POST'])
def api_create_exp_config():
    """Tạo mới một file cấu hình thử nghiệm config_exp_*.json"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    configs_dir = os.path.join(base_dir, 'configs')
    
    # Tìm index mới
    exp_files = [f for f in os.listdir(configs_dir) if f.startswith('config_exp_') and f.endswith('.json')]
    existing_indices = []
    max_magic = 100020
    
    for ef in exp_files:
        try:
            idx = int(ef.replace('config_exp_', '').replace('.json', ''))
            existing_indices.append(idx)
        except ValueError:
            pass
        try:
            with open(os.path.join(configs_dir, ef), 'r', encoding='utf-8') as f:
                d = json.load(f)
                m = d.get('magic', 0)
                if isinstance(m, int) and m > max_magic:
                    max_magic = m
        except Exception:
            pass
            
    next_idx = max(existing_indices, default=0) + 1
    new_magic = max_magic + 1
    new_filename = f"config_exp_{next_idx}.json"
    new_path = os.path.join(configs_dir, new_filename)
    
    # Chọn file mẫu để clone (ưu tiên config_exp_1.json hoặc config_template.json)
    template_path = os.path.join(configs_dir, 'config_exp_1.json')
    if not os.path.exists(template_path):
        template_path = os.path.join(configs_dir, 'config_template.json')
        
    try:
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                template_data = json.load(f)
        else:
            template_data = {
                "symbol": "XAUUSDc",
                "volume": 0.01,
                "magic": new_magic,
                "max_positions": 1,
                "parameters": {
                    "order_comment": f"EXP_{next_idx}"
                }
            }
            
        template_data['magic'] = new_magic
        if 'parameters' not in template_data:
            template_data['parameters'] = {}
        template_data['parameters']['order_comment'] = f"EXP_{next_idx}"
        
        with open(new_path, 'w', encoding='utf-8') as f:
            json.dump(template_data, f, indent=4, ensure_ascii=False)
            
        return jsonify({
            'success': True,
            'message': f'Đã tạo thành công file thử nghiệm mới "{new_filename}" (Magic: {new_magic})!',
            'filename': new_filename,
            'rel_path': f"configs/{new_filename}",
            'magic': new_magic
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khi tạo file thử nghiệm: {str(e)}'}), 500

@app.route('/api/delete_exp_config', methods=['POST'])
def api_delete_exp_config():
    """Xóa một file cấu hình thử nghiệm config_exp_*.json"""
    data = request.get_json() or {}
    filename = data.get('filename', '').strip()
    if not filename or not filename.startswith('config_exp_') or not filename.endswith('.json'):
        return jsonify({'success': False, 'message': 'Tên file thử nghiệm không hợp lệ!'}), 400
        
    base_dir = os.path.dirname(os.path.abspath(__file__))
    configs_dir = os.path.join(base_dir, 'configs')
    exp_files = [f for f in os.listdir(configs_dir) if f.startswith('config_exp_') and f.endswith('.json')]
    
    if len(exp_files) <= 1:
        return jsonify({'success': False, 'message': 'Không thể xóa file thử nghiệm cuối cùng!'}), 400
        
    target_path = os.path.join(configs_dir, filename)
    if not os.path.exists(target_path):
        return jsonify({'success': False, 'message': f'File {filename} không tồn tại!'}), 404
        
    try:
        os.remove(target_path)
        return jsonify({'success': True, 'message': f'Đã xóa file cấu hình thử nghiệm "{filename}" thành công!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khi xóa file: {str(e)}'}), 500

@app.route('/api/restart_bot', methods=['POST'])
def api_restart_bot():
    """Khởi động lại bot (Dừng tiến trình cũ và mở lại tiến trình mới)"""
    data = request.get_json() or {}
    bot_file = data.get('bot', '').strip()
    if not bot_file or bot_file not in VALID_BOTS:
        return jsonify({'success': False, 'message': f'Bot "{bot_file}" không hợp lệ!'}), 400
        
    running = get_running_bots()
    if bot_file in running:
        pid = running[bot_file]
        try:
            if psutil:
                p = psutil.Process(pid)
                for child in p.children(recursive=True):
                    child.terminate()
                p.terminate()
        except Exception as e:
            print(f"Lỗi khi dừng PID {pid}: {e}")
            
    import time
    time.sleep(1)
    _launch_bot_process(bot_file, VALID_BOTS[bot_file]['name'])
    
    return jsonify({
        'success': True,
        'message': f"Đã gửi lệnh khởi động lại bot {VALID_BOTS[bot_file]['name']}!"
    })

if __name__ == '__main__':
    print(f"🚀 Dashboard running on http://127.0.0.1:5007")
    app.run(host='0.0.0.0', port=5007, debug=False, threaded=True)

