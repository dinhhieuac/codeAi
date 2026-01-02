import MetaTrader5 as mt5
import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime

def load_config(config_path):
    """Load configuration from JSON file"""
    if not os.path.exists(config_path):
        print(f"❌ Config file not found: {config_path}")
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
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
    """Send message to Telegram with detailed logging"""
    if not token or not chat_id:
        print(f"⚠️ Telegram: Missing token or chat_id (token={'✅' if token else '❌'}, chat_id={'✅' if chat_id else '❌'})")
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id).strip(),
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        print(f"📤 [Telegram] Đang gửi thông báo...")
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            print(f"✅ [Telegram] Đã gửi thông báo thành công")
            return True
        else:
            error_code = result.get('error_code', 'Unknown')
            error_desc = result.get('description', 'Unknown error')
            print(f"❌ [Telegram] Gửi thất bại: {error_code} - {error_desc}")
            return False
    except requests.exceptions.Timeout:
        print(f"❌ [Telegram] Timeout khi gửi thông báo")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ [Telegram] Lỗi kết nối: {e}")
        return False
    except Exception as e:
        print(f"❌ [Telegram] Lỗi không xác định: {e}")
        import traceback
        traceback.print_exc()
        return False

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

def get_pip_size(symbol, symbol_info=None):
    """
    Get pip size for a symbol (for calculating pips from points)
    EURUSD: 1 pip = 0.0001 (10 points)
    XAUUSD: 1 pip = 0.1 (10 points if point=0.01, or 1 point if point=0.1)
    BTCUSD: 1 pip = varies (usually 0.1 or 1.0)
    """
    if symbol_info is None:
        symbol_info = mt5.symbol_info(symbol)
    
    if symbol_info:
        point = getattr(symbol_info, 'point', 0.0001)
        symbol_upper = symbol.upper()
        
        if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
            # XAUUSD: pip thường là 0.1 (10 points nếu point=0.01)
            pip_size = 0.1 if point < 0.01 else point
        elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
            # BTCUSD: pip thường là 1.0 hoặc 0.1 tùy broker
            pip_size = 1.0 if point >= 0.1 else 0.1
        elif 'JPY' in symbol_upper:
            pip_size = 0.01
        else:
            pip_size = 0.0001  # Standard forex
        
        return pip_size
    
    # Fallback
    symbol_upper = symbol.upper()
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        return 0.1
    elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
        return 1.0
    elif 'JPY' in symbol_upper:
        return 0.01
    else:
        return 0.0001

def manage_position(order_ticket, symbol, magic, config):
    """
    Manage an open position: Breakeven & Trailing SL
    - Breakeven Trigger: 10 pips -> Move SL to Open Price
    - Trailing Trigger: 30 pips -> Trail by 20 pips
    Tính toán dựa trên pip size của từng symbol (EURUSD, XAUUSD, BTCUSD)
    """
    try:
        positions = mt5.positions_get(ticket=int(order_ticket))
        if not positions:
            return

        pos = positions[0]
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return
            
        current_price = mt5.symbol_info_tick(symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask
        point = symbol_info.point
        pip_size = get_pip_size(symbol, symbol_info)
        
        # Calculate Profit in Pips (not points)
        if pos.type == mt5.ORDER_TYPE_BUY:
            profit_price = current_price - pos.price_open
        else:
            profit_price = pos.price_open - current_price
        
        profit_pips = profit_price / pip_size
        
        request = None
        
        # 1. Quick Breakeven (10 pips)
        # Move SL to Entry if not already there
        breakeven_trigger_pips = 10.0
        if profit_pips > breakeven_trigger_pips:
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
                print(f"🛡️ [Breakeven] Ticket {pos.ticket}: Moved SL to entry price ({pos.price_open:.5f}) | Profit: {profit_pips:.1f} pips")
                
                # Send Telegram notification for Breakeven
                telegram_token = config.get('telegram_token')
                telegram_chat_id = config.get('telegram_chat_id')
                if telegram_token and telegram_chat_id:
                    signal_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
                    breakeven_msg = (
                        f"🛡️ <b>Breakeven Activated</b>\n"
                        f"{'='*50}\n"
                        f"🆔 <b>Ticket:</b> {pos.ticket}\n"
                        f"💱 <b>Symbol:</b> {symbol} ({signal_type})\n"
                        f"💵 <b>Entry:</b> {pos.price_open:.5f}\n"
                        f"🛑 <b>New SL:</b> {pos.price_open:.5f} (Entry Price)\n"
                        f"📊 <b>Profit:</b> {profit_pips:.1f} pips\n"
                        f"📈 <b>Volume:</b> {pos.volume:.2f} lot\n"
                        f"⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"{'='*50}"
                    )
                    send_telegram(breakeven_msg, telegram_token, telegram_chat_id)

        # 2. Trailing Stop (Trigger > 30 pips, Trail by 20 pips)
        trailing_trigger_pips = 30.0
        trailing_distance_pips = 20.0
        
        if request is None and profit_pips > trailing_trigger_pips:
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
                symbol_upper = symbol.upper()
                if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                    print(f"🏃 [Trailing] Ticket {pos.ticket}: SL {pos.sl:.2f} -> {new_sl:.2f} | Profit: {profit_pips:.1f} pips")
                elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                    print(f"🏃 [Trailing] Ticket {pos.ticket}: SL {pos.sl:.2f} -> {new_sl:.2f} | Profit: {profit_pips:.1f} pips")
                else:
                    print(f"🏃 [Trailing] Ticket {pos.ticket}: SL {pos.sl:.5f} -> {new_sl:.5f} | Profit: {profit_pips:.1f} pips")

        if request:
            res = mt5.order_send(request)
            if res.retcode != mt5.TRADE_RETCODE_DONE:
                error_msg = f"⚠️ Failed to update SL/TP for {pos.ticket}: {res.comment}"
                print(error_msg)
                
                # Send Telegram notification for error
                telegram_token = config.get('telegram_token')
                telegram_chat_id = config.get('telegram_chat_id')
                if telegram_token and telegram_chat_id:
                    error_telegram_msg = (
                        f"❌ <b>SL/TP Update Failed</b>\n"
                        f"{'='*50}\n"
                        f"🆔 <b>Ticket:</b> {pos.ticket}\n"
                        f"💱 <b>Symbol:</b> {symbol}\n"
                        f"❌ <b>Error:</b> {res.comment}\n"
                        f"📝 <b>Retcode:</b> {res.retcode}\n"
                        f"⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"{'='*50}"
                    )
                    send_telegram(error_telegram_msg, telegram_token, telegram_chat_id)
            else:
                print(f"✅ Successfully updated SL/TP for {pos.ticket}")

    except Exception as e:
        error_msg = f"⚠️ Error managing position {order_ticket}: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        
        # Send Telegram notification for exception
        try:
            telegram_token = config.get('telegram_token')
            telegram_chat_id = config.get('telegram_chat_id')
            if telegram_token and telegram_chat_id:
                error_telegram_msg = (
                    f"❌ <b>Position Management Error</b>\n"
                    f"{'='*50}\n"
                    f"🆔 <b>Ticket:</b> {order_ticket}\n"
                    f"💱 <b>Symbol:</b> {symbol}\n"
                    f"❌ <b>Error:</b> {str(e)}\n"
                    f"⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"{'='*50}"
                )
                send_telegram(error_telegram_msg, telegram_token, telegram_chat_id)
        except Exception as telegram_error:
            print(f"⚠️ Failed to send Telegram error notification: {telegram_error}")
        
        # Send Telegram notification for exception
        try:
            telegram_token = config.get('telegram_token')
            telegram_chat_id = config.get('telegram_chat_id')
            if telegram_token and telegram_chat_id:
                error_telegram_msg = (
                    f"❌ <b>Position Management Error</b>\n"
                    f"{'='*50}\n"
                    f"🆔 <b>Ticket:</b> {order_ticket}\n"
                    f"💱 <b>Symbol:</b> {symbol}\n"
                    f"❌ <b>Error:</b> {str(e)}\n"
                    f"⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"{'='*50}"
                )
                send_telegram(error_telegram_msg, telegram_token, telegram_chat_id)
        except Exception as telegram_error:
            print(f"⚠️ Failed to send Telegram error notification: {telegram_error}")

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
