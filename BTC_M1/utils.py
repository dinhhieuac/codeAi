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

def manage_position(order_ticket, symbol, magic, config):
    """
    Manage an open position: Breakeven & Trailing SL
    Defaults:
    - Breakeven Trigger: 10 pips (100 points) -> Move SL to Open Price
    - Trailing Trigger: 30 pips (300 points) -> Trail by 20 pips (200 points)
    """
    try:
        positions = mt5.positions_get(ticket=int(order_ticket))
        if not positions:
            return

        pos = positions[0]
        current_price = mt5.symbol_info_tick(symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask
        point = mt5.symbol_info(symbol).point
        
        # Calculate Profit in Points
        if pos.type == mt5.ORDER_TYPE_BUY:
            profit_points = (current_price - pos.price_open) / point
        else:
            profit_points = (pos.price_open - current_price) / point
            
        request = None
        
        # 1. Quick Breakeven (10000 points / $100)
        # Move SL to Entry if not already there
        if profit_points > 10000:
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
                 print(f"🛡️ Moved SL to Breakeven for Ticket {pos.ticket}")

        # 2. Trailing Stop (Trigger > 30000 points / $300)
        # Trail distance: 20000 points / $200
        if request is None and profit_points > 30000:
            trail_dist = 20000 * point
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
                print(f"🏃 Trailing SL for {pos.ticket}: {pos.sl:.2f} -> {new_sl:.2f}")

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
