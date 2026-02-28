import MetaTrader5 as mt5
import os
import json
import requests
import pandas as pd
import numpy as np

def load_config(config_path):
    """Load configuration from JSON file"""
    if not os.path.exists(config_path):
        print(f"❌ Config file not found: {config_path}")
        return None
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
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

    try:
        if path:
            if not mt5.initialize(path=path, login=login, password=password, server=server):
                print(f"❌ MT5 Init failed with path: {mt5.last_error()}")
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
    """Check if candle is a Doji (Body < 10% of Range) - nến thường."""
    body = abs(row['close'] - row['open'])
    rng = row['high'] - row['low']
    return body <= (rng * threshold) if rng > 0 else True

def is_doji_ha(row, threshold=0.2):
    """Check if Heiken Ashi candle is Doji: body < threshold * range (dùng ha_open/ha_close/ha_high/ha_low)."""
    body = abs(row['ha_close'] - row['ha_open'])
    rng = row['ha_high'] - row['ha_low']
    return body <= (rng * threshold) if rng > 0 else True

def manage_position(order_ticket, symbol, magic, config, initial_sl_map=None):
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
        current_price = mt5.symbol_info_tick(symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask
        point = mt5.symbol_info(symbol).point
        
        # Get pip size for XAUUSD
        symbol_info = mt5.symbol_info(symbol)
        pip_size = point * 10  # Default: 10 points = 1 pip
        if symbol_info:
            # For XAUUSD, pip might be 0.1 or 0.01 depending on broker
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
        
        # Initial SL distance: ưu tiên từ initial_sl_map (lưu khi vào lệnh), không còn ước lượng "<5 pips thì cho 100"
        if initial_sl_map and isinstance(initial_sl_map, dict) and int(order_ticket) in initial_sl_map:
            initial_sl_distance_pips = float(initial_sl_map[int(order_ticket)])
        else:
            if pos.type == mt5.ORDER_TYPE_BUY:
                sl_distance_from_entry = (pos.price_open - pos.sl) / pip_size if pos.sl > 0 else 0
            else:
                sl_distance_from_entry = (pos.sl - pos.price_open) / pip_size if pos.sl > 0 else 0
            if sl_distance_from_entry < 5:
                initial_sl_distance_pips = 100
            else:
                initial_sl_distance_pips = max(sl_distance_from_entry, 50)
            
        request = None
        
        # Track peak profit for pullback detection
        # Note: This requires storing peak in external storage or position comment
        # For now, we'll use a simple approach: if profit decreases significantly, be more conservative
        
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
                # Check if SL is already at or better than breakeven
                is_breakeven = False
                if pos.type == mt5.ORDER_TYPE_BUY:
                    if pos.sl >= pos.price_open: is_breakeven = True
                else:
                    if pos.sl > 0 and pos.sl <= pos.price_open: is_breakeven = True
                
                if not is_breakeven:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": symbol,
                        "sl": pos.price_open,
                        "tp": pos.tp
                    }
                    print(f"🛡️ Moved SL to Breakeven for Ticket {pos.ticket} (Profit: {profit_pips:.1f} pips, Trigger: {breakeven_trigger_pips_calc:.1f} pips)")

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
                    # ATR-based trailing (Improved: Use M5 for consistency with Initial SL)
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
                            # Apply min/max limits
                            trail_dist_pips = max(trailing_min_pips, min(trail_dist_pips, trailing_max_pips))
                            trail_dist = trail_dist_pips * pip_size
                        else:
                            # Fallback to fixed
                            trail_dist = trailing_distance_pips * pip_size
                    else:
                        # Fallback to fixed
                        trail_dist = trailing_distance_pips * pip_size
                else:
                    # Fixed trailing distance
                    trail_dist = trailing_distance_pips * pip_size
                
                new_sl = 0.0
                
                if pos.type == mt5.ORDER_TYPE_BUY:
                    new_sl = current_price - trail_dist
                    # Only update if new_sl is higher than current SL
                    if new_sl > pos.sl:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "symbol": symbol,
                            "sl": new_sl,
                            "tp": pos.tp
                        }
                else:
                    new_sl = current_price + trail_dist
                    # Only update if new_sl is lower than current SL (or SL is 0)
                    if pos.sl == 0 or new_sl < pos.sl:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "symbol": symbol,
                            "sl": new_sl,
                            "tp": pos.tp
                        }
                
                if request:
                    mode_str = f"ATR({trailing_atr_multiplier}x {trailing_atr_timeframe})" if trailing_mode == 'atr' else f"Fixed({trailing_distance_pips}pips)"
                    print(f"🏃 Trailing SL for {pos.ticket}: {pos.sl:.2f} -> {new_sl:.2f} ({mode_str}, Profit: {profit_pips:.1f} pips, Trigger: {trailing_trigger_pips_calc:.1f} pips)")

        if request:
             res = mt5.order_send(request)
             if res.retcode != mt5.TRADE_RETCODE_DONE:
                 print(f"⚠️ Failed to update SL/TP: {res.comment}")

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
