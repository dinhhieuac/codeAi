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

def is_doji(row, threshold=0.1):
    """Check if candle is a Doji (Body < 10% of Range)"""
    body = abs(row['close'] - row['open'])
    rng = row['high'] - row['low']
    return body <= (rng * threshold) if rng > 0 else True
