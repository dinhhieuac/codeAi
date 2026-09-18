import sys
import os
import json
import requests
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def get_accounts_file_path():
    """Get the path to accounts.json"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    configs_path = os.path.join(base_dir, "configs", "accounts.json")
    if os.path.exists(configs_path):
        return configs_path
    root_path = os.path.join(base_dir, "accounts.json")
    if os.path.exists(root_path):
        return root_path
    return configs_path

def load_accounts(accounts_path=None):
    """Load MT5 accounts configuration dictionary"""
    if not accounts_path:
        accounts_path = get_accounts_file_path()
    if not os.path.exists(accounts_path):
        return {}
    try:
        with open(accounts_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("accounts", {})
    except Exception as e:
        print(f"⚠️ Error loading accounts.json: {e}")
        return {}

def load_config(config_path):
    """Load configuration from JSON file and merge account credentials if account_id is specified"""
    if not os.path.exists(config_path):
        print(f"❌ Config file not found: {config_path}")
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        # Check if config specifies an account_id
        account_id = config.get("account_id")
        if account_id:
            # Look up account details in accounts.json
            config_dir = os.path.dirname(os.path.abspath(config_path))
            candidate_accounts_file = os.path.join(config_dir, "accounts.json")
            accounts = load_accounts(candidate_accounts_file if os.path.exists(candidate_accounts_file) else None)
            
            acc_info = accounts.get(account_id)
            if acc_info:
                # Merge account fields into config if not already explicitly overridden
                for key in ["account", "password", "server", "mt5_path", "symbol"]:
                    if key in acc_info and (key not in config or config[key] is None):
                        config[key] = acc_info[key]
            else:
                print(f"⚠️ Account ID '{account_id}' not found in accounts.json!")
        return config
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return None

def connect_mt5(config):
    """Initialize MT5 connection using config"""
    login = config.get("account")
    password = config.get("password")
    server = config.get("server")
    path = config.get("mt5_path") # Optional custom path

    if not all([login, password, server]):
        print("❌ Missing MT5 credentials in config")
        return False

    # Tự động điều chỉnh đường dẫn MT5 nếu đường dẫn trong config không tồn tại
    if path and not os.path.exists(path):
        default_candidate = "C:/Program Files/MetaTrader 5/terminal64.exe"
        if os.path.exists(default_candidate):
            path = default_candidate
        else:
            path = None

    try:
        if path:
            if not mt5.initialize(path=path, login=login, password=password, server=server):
                print(f"❌ MT5 Init failed with path: {mt5.last_error()}")
                # Thử fallback không dùng path
                if not mt5.initialize(login=login, password=password, server=server):
                    return False
        else:
            if not mt5.initialize(login=login, password=password, server=server):
                print(f"❌ MT5 Init failed: {mt5.last_error()}")
                return False
                
        print(f"✅ Connected to MT5 Account: {login}")
        return True
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def send_telegram(message, token, chat_id):
    """Send message to Telegram"""
    if not token or not chat_id:
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")

def get_data(symbol, timeframe, n=100):
    """Fetch recent candles from MT5"""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
    if rates is None or len(rates) == 0:
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def calculate_heiken_ashi(df):
    """Calculate Heiken Ashi candles"""
    ha_df = df.copy()
    ha_df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    
    # Initialize first HA open
    ha_df.at[0, 'ha_open'] = (df.iloc[0]['open'] + df.iloc[0]['close']) / 2
    
    for i in range(1, len(df)):
        ha_df.at[i, 'ha_open'] = (ha_df.at[i-1, 'ha_open'] + ha_df.at[i-1, 'ha_close']) / 2
        
    ha_df['ha_high'] = ha_df[['high', 'ha_open', 'ha_close']].max(axis=1)
    ha_df['ha_low'] = ha_df[['low', 'ha_open', 'ha_close']].min(axis=1)
    
    return ha_df

def calculate_atr(df, period=14):
    """Calculate ATR (Average True Range)"""
    df = df.copy()
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift(1))
    df['tr2'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    atr_series = df['tr'].rolling(window=period).mean()
    return atr_series

def calculate_adx(df, period=14):
    """Calculate ADX Indicator"""
    df = df.copy()
    df['up'] = df['high'].diff()
    df['down'] = -df['low'].diff()
    
    df['dm_plus'] = np.where((df['up'] > df['down']) & (df['up'] > 0), df['up'], 0)
    df['dm_minus'] = np.where((df['down'] > df['up']) & (df['down'] > 0), df['down'], 0)
    
    df['tr'] = np.maximum(df['high'] - df['low'], 
                          np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                     abs(df['low'] - df['close'].shift(1))))
    
    df['tr_s'] = df['tr'].rolling(window=period).sum()
    df['dm_plus_s'] = df['dm_plus'].rolling(window=period).sum()
    df['dm_minus_s'] = df['dm_minus'].rolling(window=period).sum()
    
    df['di_plus'] = 100 * (df['dm_plus_s'] / df['tr_s'])
    df['di_minus'] = 100 * (df['dm_minus_s'] / df['tr_s'])
    
    df['dx'] = 100 * abs(df['di_plus'] - df['di_minus']) / (df['di_plus'] + df['di_minus'])
    df['adx'] = df['dx'].rolling(window=period).mean()
    
    return df

def calculate_rsi(series, period=14):
    """
    Calculate RSI using Wilder's Smoothing (Standard MT5/TradingView RSI)
    """
    delta = series.diff()
    
    # Separate gains and losses
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    
    # Calculate initial average (simple MA)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()[:period+1]
    avg_loss = loss.rolling(window=period, min_periods=period).mean()[:period+1]
    
    # Manual loop or pandas ewm for Wilder's Smoothing (alpha=1/period)
    # Pandas EWM with adjust=False approximates Wilder's if alpha=1/period
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def is_doji(row, threshold=0.1):
    """Check if candle is a Doji (Body < 10% of Range)"""
    body = abs(row['close'] - row['open'])
    rng = row['high'] - row['low']
    return body <= (rng * threshold) if rng > 0 else True

# Bộ nhớ đệm lưu trữ Initial SL cho từng Ticket (In-memory cache)
_INITIAL_SL_CACHE = {}

def get_initial_sl_distance(pos, symbol, pip_size):
    """
    Lấy chính xác Initial SL (SL ban đầu) và khoảng cách Initial SL (pips) của vị thế.
    Cơ chế tìm kiếm đa tầng chính xác:
    1. Kiểm tra cache trong bộ nhớ (_INITIAL_SL_CACHE)
    2. Nếu SL hiện tại còn nguyên (chưa bị dời về BE, khoảng cách >= 5 pips) -> lưu ngay vào cache
    3. Nếu SL đã bị dời về BE -> truy vấn lịch sử Order khởi tạo vị thế từ MT5 (mt5.history_orders_get)
    4. Nếu không tìm thấy trong MT5 -> truy vấn bảng orders trong trades.db (initial_sl)
    5. Fallback an toàn nếu hoàn toàn không có dữ liệu: 50 pips
    """
    ticket = int(pos.ticket)
    
    # 1. Kiểm tra Cache trong bộ nhớ
    if ticket in _INITIAL_SL_CACHE:
        cached = _INITIAL_SL_CACHE[ticket]
        if cached.get('initial_dist_pips', 0) > 0:
            return cached.get('initial_sl', pos.sl), cached['initial_dist_pips']

    initial_sl = None
    initial_dist_pips = None

    # 2. Kiểm tra SL hiện tại của vị thế nếu chưa bị kéo về hòa vốn
    if pos.sl > 0:
        if pos.type == mt5.ORDER_TYPE_BUY:
            dist = (pos.price_open - pos.sl) / pip_size
            if pos.sl < pos.price_open and dist >= 5.0:
                initial_sl = pos.sl
                initial_dist_pips = dist
        else:
            dist = (pos.sl - pos.price_open) / pip_size
            if pos.sl > pos.price_open and dist >= 5.0:
                initial_sl = pos.sl
                initial_dist_pips = dist

    # 3. Truy vấn Order mở lệnh từ lịch sử MT5 (history_orders_get lưu vĩnh viễn SL ban đầu)
    if initial_dist_pips is None or initial_dist_pips <= 0:
        try:
            h_orders = mt5.history_orders_get(position=ticket)
            if h_orders:
                for ho in h_orders:
                    if ho.sl > 0:
                        if pos.type == mt5.ORDER_TYPE_BUY and ho.sl < pos.price_open:
                            initial_sl = ho.sl
                            initial_dist_pips = (pos.price_open - ho.sl) / pip_size
                            break
                        elif pos.type == mt5.ORDER_TYPE_SELL and ho.sl > pos.price_open:
                            initial_sl = ho.sl
                            initial_dist_pips = (ho.sl - pos.price_open) / pip_size
                            break
        except Exception:
            pass

    # 4. Truy vấn trades.db (initial_sl)
    if initial_dist_pips is None or initial_dist_pips <= 0:
        try:
            import sqlite3
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.db")
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                c.execute("PRAGMA table_info(orders)")
                cols = [col[1] for col in c.fetchall()]
                query = "SELECT initial_sl, sl FROM orders WHERE ticket = ?" if 'initial_sl' in cols else "SELECT sl FROM orders WHERE ticket = ?"
                c.execute(query, (ticket,))
                row = c.fetchone()
                conn.close()
                if row:
                    db_sl = row[0] if (row[0] is not None and row[0] > 0) else (row[1] if len(row) > 1 else None)
                    if db_sl and db_sl > 0:
                        initial_sl = db_sl
                        if pos.type == mt5.ORDER_TYPE_BUY:
                            initial_dist_pips = (pos.price_open - initial_sl) / pip_size
                        else:
                            initial_dist_pips = (initial_sl - pos.price_open) / pip_size
        except Exception:
            pass

    # 5. Fallback nếu không có dữ liệu (50 pips thay vì 100 pips)
    if initial_dist_pips is None or initial_dist_pips <= 0:
        initial_dist_pips = 50.0
        initial_sl = (pos.price_open - 50.0 * pip_size) if pos.type == mt5.ORDER_TYPE_BUY else (pos.price_open + 50.0 * pip_size)

    # Lưu vào cache cho các lần gọi tiếp theo
    _INITIAL_SL_CACHE[ticket] = {
        'initial_sl': initial_sl,
        'initial_dist_pips': initial_dist_pips
    }
    return initial_sl, initial_dist_pips

def manage_position(order_ticket, symbol, magic, config):
    """
    Manage an open position: Breakeven & Trailing SL (Improved V2)
    
    Config parameters:
    - trailing_enabled: true/false - Enable/disable trailing SL
    - breakeven_enabled: true/false - Enable/disable breakeven
    - breakeven_trigger_pips: Fixed pips OR use "auto" for % of initial SL (default: 30)
    - breakeven_trigger_percent: % of initial SL to trigger breakeven (default: 0.5 = 50%)
    - trailing_trigger_pips: Fixed pips OR use "auto" for multiplier of initial SL (default: 50)
    - trailing_trigger_multiplier: Multiplier of initial SL to start trailing (default: 1.2)
    - trailing_mode: "atr" or "fixed" - Use ATR-based or fixed distance
    - trailing_atr_timeframe: "M1" or "M5" - Timeframe for ATR calculation (default: "M5")
    - trailing_distance_pips: Fixed trailing distance in pips (default: 50)
    - trailing_atr_multiplier: ATR multiplier for trailing (default: 1.5)
    - trailing_min_pips: Minimum trailing distance in pips (default: 30)
    - trailing_max_pips: Maximum trailing distance in pips (default: 100)
    - trailing_lock_on_pullback: Enable lock trailing when pullback > % (default: false)
    - trailing_pullback_percent: % profit loss to lock trailing (default: 0.3 = 30%)
    """
    try:
        # Check if trailing is enabled
        trailing_enabled = config.get('parameters', {}).get('trailing_enabled', True)
        breakeven_enabled = config.get('parameters', {}).get('breakeven_enabled', True)
        
        if not trailing_enabled and not breakeven_enabled:
            return  # Both disabled, skip
        
        positions = mt5.positions_get(ticket=int(order_ticket))
        if not positions:
            return

        pos = positions[0]
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            return

        digits = symbol_info.digits
        point = symbol_info.point
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return
            
        current_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        
        # Get pip size for XAUUSD
        pip_size = point * 10  # Default: 10 points = 1 pip
        if 'XAU' in symbol.upper() or 'GOLD' in symbol.upper():
            if point >= 0.01:
                pip_size = point  # 1 point = 1 pip
            else:
                pip_size = point * 10  # 10 points = 1 pip
        
        # Calculate Profit in Points and Pips
        if pos.type == mt5.ORDER_TYPE_BUY:
            profit_points = (current_price - pos.price_open) / point
            profit_pips = (current_price - pos.price_open) / pip_size
        else:
            profit_points = (pos.price_open - current_price) / point
            profit_pips = (pos.price_open - current_price) / pip_size
        
        # Lấy chính xác Initial SL và khoảng cách Initial SL (pips) không dùng ước lượng 100 pips
        initial_sl, initial_sl_distance_pips = get_initial_sl_distance(pos, symbol, pip_size)
            
        request = None
        pos_sl_rounded = round(pos.sl, digits)
        price_open_rounded = round(pos.price_open, digits)
        
        # 1. Breakeven (Improved - based on Initial SL %)
        if breakeven_enabled:
            breakeven_trigger_pips = config.get('parameters', {}).get('breakeven_trigger_pips', 30)
            breakeven_trigger_percent = config.get('parameters', {}).get('breakeven_trigger_percent', 0.5)
            
            # Use % of initial SL if breakeven_trigger_pips is "auto" or use the larger value
            if isinstance(breakeven_trigger_pips, str) and breakeven_trigger_pips.lower() == 'auto':
                breakeven_trigger_pips_calc = initial_sl_distance_pips * breakeven_trigger_percent
            else:
                # Use max of fixed pips or % of initial SL
                breakeven_trigger_pips_calc = max(breakeven_trigger_pips, initial_sl_distance_pips * breakeven_trigger_percent)
            
            breakeven_trigger_points = breakeven_trigger_pips_calc * pip_size / point
            
            if profit_points > breakeven_trigger_points:
                # Check if SL is already at or better than breakeven (using rounded comparison)
                is_breakeven = False
                if pos.type == mt5.ORDER_TYPE_BUY:
                    if pos_sl_rounded >= (price_open_rounded - 0.5 * point):
                        is_breakeven = True
                else:
                    if pos.sl > 0 and pos_sl_rounded <= (price_open_rounded + 0.5 * point):
                        is_breakeven = True
                
                if not is_breakeven:
                    # Target SL is price_open rounded to broker digits
                    target_sl = price_open_rounded
                    if abs(target_sl - pos_sl_rounded) >= point:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "symbol": symbol,
                            "sl": target_sl,
                            "tp": round(pos.tp, digits),
                            "_action_desc": f"Breakeven (Profit: {profit_pips:.1f}p, Trigger: {breakeven_trigger_pips_calc:.1f}p, InitSL Dist: {initial_sl_distance_pips:.1f}p)"
                        }

        # 2. Trailing Stop (Improved - based on Initial SL, M5 ATR, min/max limits)
        if trailing_enabled and request is None:
            trailing_trigger_pips = config.get('parameters', {}).get('trailing_trigger_pips', 50)
            trailing_trigger_multiplier = config.get('parameters', {}).get('trailing_trigger_multiplier', 1.2)
            
            # Calculate trailing trigger: use multiplier of initial SL or fixed, whichever is larger
            if isinstance(trailing_trigger_pips, str) and trailing_trigger_pips.lower() == 'auto':
                trailing_trigger_pips_calc = initial_sl_distance_pips * trailing_trigger_multiplier
            else:
                trailing_trigger_pips_calc = max(trailing_trigger_pips, initial_sl_distance_pips * trailing_trigger_multiplier)
            
            trailing_trigger_points = trailing_trigger_pips_calc * pip_size / point
            
            if profit_points > trailing_trigger_points:
                trailing_mode = config.get('parameters', {}).get('trailing_mode', 'atr')
                trailing_atr_timeframe = config.get('parameters', {}).get('trailing_atr_timeframe', 'M5')
                trailing_atr_multiplier = config.get('parameters', {}).get('trailing_atr_multiplier', 1.5)
                trailing_distance_pips = config.get('parameters', {}).get('trailing_distance_pips', 50)
                trailing_min_pips = config.get('parameters', {}).get('trailing_min_pips', 30)
                trailing_max_pips = config.get('parameters', {}).get('trailing_max_pips', 100)
                
                # Calculate trailing distance
                if trailing_mode == 'atr':
                    timeframe_map = {
                        'M1': mt5.TIMEFRAME_M1,
                        'M5': mt5.TIMEFRAME_M5,
                        'M15': mt5.TIMEFRAME_M15
                    }
                    atr_timeframe = timeframe_map.get(trailing_atr_timeframe, mt5.TIMEFRAME_M5)
                    
                    rates = mt5.copy_rates_from_pos(symbol, atr_timeframe, 0, 50)
                    if rates is not None and len(rates) > 14:
                        df = pd.DataFrame(rates)
                        df['tr0'] = abs(df['high'] - df['low'])
                        df['tr1'] = abs(df['high'] - df['close'].shift(1))
                        df['tr2'] = abs(df['low'] - df['close'].shift(1))
                        df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
                        atr_value = df['tr'].rolling(window=14).mean().iloc[-1]
                        
                        if not pd.isna(atr_value) and atr_value > 0:
                            trail_dist = atr_value * trailing_atr_multiplier
                            trail_dist_pips = trail_dist / pip_size
                            trail_dist_pips = max(trailing_min_pips, min(trail_dist_pips, trailing_max_pips))
                            trail_dist = trail_dist_pips * pip_size
                        else:
                            trail_dist = trailing_distance_pips * pip_size
                    else:
                        trail_dist = trailing_distance_pips * pip_size
                else:
                    trail_dist = trailing_distance_pips * pip_size
                
                new_sl = 0.0
                
                if pos.type == mt5.ORDER_TYPE_BUY:
                    new_sl = round(current_price - trail_dist, digits)
                    # Only update if new_sl is higher than current SL by at least 1 point
                    if new_sl - pos_sl_rounded >= point:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "symbol": symbol,
                            "sl": new_sl,
                            "tp": round(pos.tp, digits)
                        }
                else:
                    new_sl = round(current_price + trail_dist, digits)
                    # Only update if new_sl is lower than current SL by at least 1 point (or SL is 0)
                    if pos.sl == 0 or (pos_sl_rounded - new_sl >= point):
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "symbol": symbol,
                            "sl": new_sl,
                            "tp": round(pos.tp, digits)
                        }
                
                if request:
                    mode_str = f"ATR({trailing_atr_multiplier}x {trailing_atr_timeframe})" if trailing_mode == 'atr' else f"Fixed({trailing_distance_pips}pips)"
                    request['_action_desc'] = f"Trailing SL ({mode_str}, Profit: {profit_pips:.1f}p, Trigger: {trailing_trigger_pips_calc:.1f}p, InitSL Dist: {initial_sl_distance_pips:.1f}p)"

        if request:
            # Prevent sending if target sl and tp match current position sl and tp
            if pos_sl_rounded == request['sl'] and round(pos.tp, digits) == request['tp']:
                return

            action_desc = request.pop('_action_desc', None)
            res = mt5.order_send(request)
            if res.retcode == 10025 or (res.comment and "No changes" in res.comment):
                # Position is already at requested SL/TP on the broker
                pass
            elif res.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"⚠️ Failed to update SL/TP for #{pos.ticket}: {res.comment} (Code: {res.retcode})")
            else:
                extra = f" [{action_desc}]" if action_desc else ""
                print(f"✅ Updated SL/TP successfully for #{pos.ticket} -> SL: {request['sl']}{extra}")

    except Exception as e:
        print(f"⚠️ Error managing position {order_ticket}: {e}")

def get_mt5_error_message(error_code):
    """
    Translate MT5 Error Codes to Human Readable Messages
    """
    error_map = {
        10004: "Requote",
        10006: "Request Rejected",
        10013: "Invalid Request",
        10014: "Invalid Volume",
        10015: "Invalid Price",
        10016: "Invalid Stops",
        10018: "Market Closed",
        10027: "AutoTrading Disabled by Client",
        10030: "Unsupported Filling Mode",
        10031: "Connection Error",
        10036: "Request Timeout"
    }
    msg = error_map.get(error_code, "Unknown Error")
    return f"{error_code} ({msg})"
