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

def log_to_file(symbol, message_type, content, log_dir=None):
    """
    Log message to file
    
    Args:
        symbol: Trading symbol (e.g., BTCUSD, XAUUSD)
        message_type: Type of message (SIGNAL, ERROR, TELEGRAM_SUCCESS, TELEGRAM_ERROR, BREAKEVEN, TRAILING)
        content: Message content
        log_dir: Directory to store log files (default: "logs" in script directory)
    """
    try:
        # Get script directory (where utils.py is located)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Use provided log_dir or default to "logs" in script directory
        if log_dir is None:
            log_dir = os.path.join(script_dir, "logs")
        elif not os.path.isabs(log_dir):
            # If relative path, make it relative to script directory
            log_dir = os.path.join(script_dir, log_dir)
        
        # Create logs directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Create log filename based on symbol and date
        log_filename = f"{symbol.lower()}_m1_scalp_{datetime.now().strftime('%Y%m%d')}.txt"
        log_path = os.path.join(log_dir, log_filename)
        
        # Format log entry
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] [{message_type}] {content}\n"
        
        # Append to file
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        # Debug: Print log path (only for first few logs to avoid spam)
        if message_type in ["SIGNAL", "ERROR", "TELEGRAM_ERROR"]:
            print(f"📝 [Log File] Đã ghi log vào: {log_path}")
        
        return True
    except Exception as e:
        print(f"⚠️ [Log File] Lỗi khi ghi log: {e}")
        import traceback
        traceback.print_exc()
        return False

def escape_html(text):
    """Escape HTML special characters for Telegram HTML parse mode"""
    if not isinstance(text, str):
        text = str(text)
    # Escape HTML entities - MUST escape & first to avoid double escaping
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    # Note: We don't escape quotes because Telegram HTML mode doesn't require it
    return text

def escape_html_message(message):
    """Escape HTML entities in message while preserving HTML tags"""
    if not isinstance(message, str):
        message = str(message)
    
    # Strategy: Find and protect valid HTML tags first, then escape everything, then restore tags
    # This ensures no special characters in text content cause parsing errors
    
    import re
    
    # Step 1: Find all valid HTML tags and replace with placeholders
    valid_tags = []
    tag_placeholder_pattern = r'</?(?:b|i|u|s|code|pre)>'
    tag_counter = 0
    
    def replace_tag(match):
        nonlocal tag_counter
        tag = match.group(0)
        placeholder = f"__TAG_PLACEHOLDER_{tag_counter}__"
        valid_tags.append((placeholder, tag))
        tag_counter += 1
        return placeholder
    
    # Replace valid tags with placeholders
    message_with_placeholders = re.sub(tag_placeholder_pattern, replace_tag, message)
    
    # Step 2: Escape the entire message (now all < and > are safe to escape)
    escaped = escape_html(message_with_placeholders)
    
    # Step 3: Restore valid tags
    for placeholder, original_tag in valid_tags:
        escaped = escaped.replace(placeholder, original_tag)
    
    return escaped

def send_telegram(message, token, chat_id, symbol=None, log_to_file_enabled=True):
    """Send message to Telegram with detailed logging"""
    if not token or not chat_id:
        error_msg = f"⚠️ Telegram: Missing token or chat_id (token={'✅' if token else '❌'}, chat_id={'✅' if chat_id else '❌'})"
        print(error_msg)
        if symbol and log_to_file_enabled:
            log_to_file(symbol, "TELEGRAM_ERROR", error_msg)
        return False
    
    # Escape HTML entities in message (preserve HTML tags)
    try:
        escaped_message = escape_html_message(message)
    except Exception as e:
        print(f"⚠️ [Telegram] Lỗi khi escape HTML: {e}")
        # Fallback: simple escape
        escaped_message = escape_html(message)
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id).strip(),
        "text": escaped_message,
        "parse_mode": "HTML"
    }
    
    try:
        print(f"📤 [Telegram] Đang gửi thông báo...")
        if symbol and log_to_file_enabled:
            log_to_file(symbol, "TELEGRAM_ATTEMPT", f"Đang gửi thông báo Telegram...")
        
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            success_msg = f"✅ [Telegram] Đã gửi thông báo thành công"
            print(success_msg)
            if symbol and log_to_file_enabled:
                # Log success with message preview (first 200 chars)
                msg_preview = message.replace('\n', ' ')[:200]
                log_to_file(symbol, "TELEGRAM_SUCCESS", f"Đã gửi thành công: {msg_preview}...")
            return True
        else:
            error_code = result.get('error_code', 'Unknown')
            error_desc = result.get('description', 'Unknown error')
            error_msg = f"❌ [Telegram] Gửi thất bại: {error_code} - {error_desc}"
            print(error_msg)
            if symbol and log_to_file_enabled:
                log_to_file(symbol, "TELEGRAM_ERROR", f"Gửi thất bại: {error_code} - {error_desc}")
            return False
    except requests.exceptions.Timeout:
        error_msg = f"❌ [Telegram] Timeout khi gửi thông báo"
        print(error_msg)
        if symbol and log_to_file_enabled:
            log_to_file(symbol, "TELEGRAM_ERROR", "Timeout khi gửi thông báo")
        return False
    except requests.exceptions.RequestException as e:
        error_msg = f"❌ [Telegram] Lỗi kết nối: {e}"
        print(error_msg)
        if symbol and log_to_file_enabled:
            log_to_file(symbol, "TELEGRAM_ERROR", f"Lỗi kết nối: {str(e)}")
        return False
    except Exception as e:
        error_msg = f"❌ [Telegram] Lỗi không xác định: {e}"
        print(error_msg)
        traceback.print_exc()
        if symbol and log_to_file_enabled:
            log_to_file(symbol, "TELEGRAM_ERROR", f"Lỗi không xác định: {str(e)}")
        return False

def log_debug_indicators(symbol, df_m1, df_m5=None, config=None, log_dir=None):
    """
    Log chi tiết các chỉ số kỹ thuật vào file debug mỗi phút
    
    Args:
        symbol: Trading symbol
        df_m1: DataFrame M1 với các chỉ số đã tính
        df_m5: DataFrame M5 (optional)
        log_dir: Directory to store log files
    """
    try:
        # Get script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Use provided log_dir or default to "logs" in script directory
        if log_dir is None:
            log_dir = os.path.join(script_dir, "logs")
        elif not os.path.isabs(log_dir):
            log_dir = os.path.join(script_dir, log_dir)
        
        # Create logs directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Create debug log filename: {symbol}_debug_{YYYYMMDD}.txt
        # Normalize symbol name (remove spaces, convert to lowercase)
        if symbol is None:
            symbol = "UNKNOWN"
        symbol_normalized = str(symbol).lower().replace(' ', '').replace('-', '').strip()
        log_filename = f"{symbol_normalized}_debug_{datetime.now().strftime('%Y%m%d')}.txt"
        log_path = os.path.join(log_dir, log_filename)
        
        # Debug: Print log path
        print(f"📝 [Debug Log] Tạo file: {log_path} cho symbol: {symbol} (normalized: {symbol_normalized})")
        
        # Get current candle (last completed candle)
        if len(df_m1) < 2:
            return False
        
        curr_candle = df_m1.iloc[-2]  # Last completed candle
        prev_candle = df_m1.iloc[-3] if len(df_m1) >= 3 else None
        
        # Get current tick price
        try:
            tick = mt5.symbol_info_tick(symbol)
            current_bid = tick.bid if tick else None
            current_ask = tick.ask if tick else None
        except:
            current_bid = None
            current_ask = None
        
        # Format timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Build debug log content
        debug_lines = []
        debug_lines.append("=" * 100)
        debug_lines.append(f"[{timestamp}] DEBUG INDICATORS - {symbol}")
        debug_lines.append("=" * 100)
        
        # Current Price Info
        debug_lines.append("\n📊 [GIÁ HIỆN TẠI]")
        if current_bid and current_ask:
            debug_lines.append(f"   Bid: {current_bid:.5f} | Ask: {current_ask:.5f} | Spread: {current_ask - current_bid:.5f}")
        debug_lines.append(f"   Nến hiện tại (đã đóng): Time={curr_candle.name}")
        debug_lines.append(f"   Open: {curr_candle['open']:.5f} | High: {curr_candle['high']:.5f} | Low: {curr_candle['low']:.5f} | Close: {curr_candle['close']:.5f}")
        if prev_candle is not None:
            debug_lines.append(f"   Nến trước: Open: {prev_candle['open']:.5f} | High: {prev_candle['high']:.5f} | Low: {prev_candle['low']:.5f} | Close: {prev_candle['close']:.5f}")
        
        # Volume Info
        debug_lines.append("\n📈 [VOLUME]")
        debug_lines.append(f"   Tick Volume (nến hiện tại): {curr_candle.get('tick_volume', 'N/A')}")
        if 'vol_ma' in df_m1.columns:
            vol_ma = df_m1['vol_ma'].iloc[-2] if pd.notna(df_m1['vol_ma'].iloc[-2]) else None
            if vol_ma is not None:
                debug_lines.append(f"   Volume MA(10): {vol_ma:.2f}")
        
        # EMA Indicators
        debug_lines.append("\n📉 [EMA - EXPONENTIAL MOVING AVERAGE]")
        ema50 = curr_candle.get('ema50', None)
        ema200 = curr_candle.get('ema200', None)
        if pd.notna(ema50):
            debug_lines.append(f"   EMA50: {ema50:.5f}")
        if pd.notna(ema200):
            debug_lines.append(f"   EMA200: {ema200:.5f}")
        if pd.notna(ema50) and pd.notna(ema200):
            ema_diff = ema50 - ema200
            ema_diff_pct = (ema_diff / ema200) * 100 if ema200 != 0 else 0
            debug_lines.append(f"   EMA50 - EMA200: {ema_diff:.5f} ({ema_diff_pct:+.3f}%)")
            debug_lines.append(f"   Trend: {'BULLISH' if ema50 > ema200 else 'BEARISH'}")
        
        # ATR Indicator
        debug_lines.append("\n📊 [ATR - AVERAGE TRUE RANGE]")
        atr = curr_candle.get('atr', None)
        if pd.notna(atr):
            debug_lines.append(f"   ATR(14): {atr:.5f}")
            # Calculate ATR in pips for forex
            symbol_upper = symbol.upper()
            if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                debug_lines.append(f"   ATR: {atr:.2f} USD")
            elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                debug_lines.append(f"   ATR: {atr:.2f} USD")
            else:
                atr_pips = atr / 0.0001
                debug_lines.append(f"   ATR: {atr_pips:.1f} pips")
        
        # RSI Indicator
        debug_lines.append("\n📈 [RSI - RELATIVE STRENGTH INDEX]")
        rsi = curr_candle.get('rsi', None)
        prev_rsi = prev_candle.get('rsi', None) if prev_candle is not None else None
        if pd.notna(rsi):
            debug_lines.append(f"   RSI(14)_M1: {rsi:.2f}")
            if rsi >= 70:
                debug_lines.append(f"   RSI Status: OVERBOUGHT (≥70)")
            elif rsi <= 30:
                debug_lines.append(f"   RSI Status: OVERSOLD (≤30)")
            else:
                debug_lines.append(f"   RSI Status: NEUTRAL")
        if pd.notna(prev_rsi) and pd.notna(rsi):
            rsi_change = rsi - prev_rsi
            debug_lines.append(f"   RSI Change: {rsi_change:+.2f} ({prev_rsi:.2f} → {rsi:.2f})")
            debug_lines.append(f"   RSI Direction: {'RISING' if rsi > prev_rsi else 'FALLING' if rsi < prev_rsi else 'FLAT'}")
        
        # ADX Indicator
        debug_lines.append("\n📊 [ADX - AVERAGE DIRECTIONAL INDEX]")
        adx = curr_candle.get('adx', None)
        di_plus = curr_candle.get('di_plus', None)
        di_minus = curr_candle.get('di_minus', None)
        if pd.notna(adx):
            debug_lines.append(f"   ADX(14): {adx:.2f}")
            if adx >= 25:
                debug_lines.append(f"   ADX Status: STRONG TREND (≥25)")
            elif adx >= 20:
                debug_lines.append(f"   ADX Status: MODERATE TREND (20-25)")
            elif adx >= 18:
                debug_lines.append(f"   ADX Status: WEAK TREND (18-20)")
            else:
                debug_lines.append(f"   ADX Status: NO TREND (<18)")
        if pd.notna(di_plus) and pd.notna(di_minus):
            debug_lines.append(f"   +DI: {di_plus:.2f} | -DI: {di_minus:.2f}")
            if di_plus > di_minus:
                debug_lines.append(f"   Direction: BULLISH (+DI > -DI)")
            elif di_minus > di_plus:
                debug_lines.append(f"   Direction: BEARISH (-DI > +DI)")
            else:
                debug_lines.append(f"   Direction: NEUTRAL")
        
        # M5 RSI (if available)
        if df_m5 is not None and len(df_m5) >= 2:
            debug_lines.append("\n📈 [RSI M5]")
            rsi_m5 = df_m5['rsi'].iloc[-2] if 'rsi' in df_m5.columns else None
            if pd.notna(rsi_m5):
                debug_lines.append(f"   RSI(14)_M5: {rsi_m5:.2f}")
                if 55 <= rsi_m5 <= 65:
                    debug_lines.append(f"   M5 RSI Status: BUY ZONE (55-65)")
                elif 35 <= rsi_m5 <= 45:
                    debug_lines.append(f"   M5 RSI Status: SELL ZONE (35-45)")
                else:
                    debug_lines.append(f"   M5 RSI Status: OUT OF ZONE")
        
        # Recent Swing Points (skip to avoid circular import)
        debug_lines.append("\n🔍 [SWING POINTS ANALYSIS]")
        debug_lines.append(f"   (Swing points analysis available in main strategy logic)")
        
        # Current Conditions Summary
        debug_lines.append("\n✅ [ĐIỀU KIỆN HIỆN TẠI]")
        if pd.notna(ema50) and pd.notna(ema200):
            debug_lines.append(f"   ĐK1 BUY (EMA50 > EMA200): {'✅' if ema50 > ema200 else '❌'}")
            debug_lines.append(f"   ĐK1 SELL (EMA50 < EMA200): {'✅' if ema50 < ema200 else '❌'}")
        if pd.notna(atr):
            # Try to get min_atr from config or use default based on symbol
            min_atr = 0.00011  # Default for forex
            symbol_upper = symbol.upper()
            if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                min_atr = 0.50  # Default for XAUUSD
            elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                min_atr = 10.0  # Default for BTCUSD
            elif config is not None:
                # Try to get from config if available
                try:
                    # Check if get_min_atr_threshold is available in calling module
                    import sys
                    calling_module = sys.modules.get('__main__')
                    if calling_module and hasattr(calling_module, 'get_min_atr_threshold'):
                        min_atr = calling_module.get_min_atr_threshold(symbol, config)
                except:
                    pass
            debug_lines.append(f"   ĐK4 ATR (≥ {min_atr:.5f}): {'✅' if atr >= min_atr else '❌'} ({atr:.5f})")
        if pd.notna(adx):
            debug_lines.append(f"   ĐK5 ADX (≥ 18): {'✅' if adx >= 18 else '❌'} ({adx:.2f})")
        
        debug_lines.append("\n" + "=" * 100 + "\n")
        
        # Write to file
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(debug_lines))
        
        # Print confirmation (only first time per day to avoid spam)
        print(f"📝 [Debug Log] Đã ghi debug indicators vào: {log_path}")
        
        return True
    except Exception as e:
        print(f"⚠️ [Debug Log] Lỗi khi ghi debug log: {e}")
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
        # Check if breakeven is enabled in config (default: true for backward compatibility)
        enable_breakeven = config.get('enable_breakeven', False)
        breakeven_trigger_pips = 10.0
        if enable_breakeven and profit_pips > breakeven_trigger_pips:
            # Normalize values to symbol digits for comparison
            digits = symbol_info.digits
            normalized_entry = round(pos.price_open, digits)
            normalized_current_sl = round(pos.sl, digits) if pos.sl > 0 else 0
            
            # Check if SL is already at or better than breakeven (with tolerance for floating point)
            is_breakeven = False
            tolerance = point * 0.5  # Half a point tolerance for comparison
            if pos.type == mt5.ORDER_TYPE_BUY:
                if pos.sl > 0 and (pos.sl >= pos.price_open - tolerance):
                    is_breakeven = True
            else:
                if pos.sl > 0 and (pos.sl <= pos.price_open + tolerance):
                    is_breakeven = True
            
            if not is_breakeven:
                # Normalize SL and TP to symbol digits before sending
                new_sl = round(pos.price_open, digits)
                new_tp = round(pos.tp, digits) if pos.tp > 0 else 0
                
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": symbol,
                    "sl": new_sl,
                    "tp": new_tp
                }
                print(f"🛡️ [Breakeven] Ticket {pos.ticket}: Moved SL to entry price ({new_sl:.5f}) | Profit: {profit_pips:.1f} pips")
                
                # Log to file: BREAKEVEN
                signal_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
                breakeven_log_content = (
                    f"🛡️ BREAKEVEN - Ticket: {pos.ticket} | "
                    f"Symbol: {symbol} ({signal_type}) | "
                    f"Entry: {pos.price_open:.5f} | New SL: {pos.price_open:.5f} | "
                    f"Profit: {profit_pips:.1f} pips | Volume: {pos.volume:.2f} lot"
                )
                log_to_file(symbol, "BREAKEVEN", breakeven_log_content)
                
                # Send Telegram notification for Breakeven
                telegram_token = config.get('telegram_token')
                telegram_chat_id = config.get('telegram_chat_id')
                if telegram_token and telegram_chat_id:
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
                    send_telegram(breakeven_msg, telegram_token, telegram_chat_id, symbol=symbol)

        # 2. Trailing Stop (Trigger > 30 pips, Trail by 20 pips)
        # Check if trailing stop is enabled in config (default: true for backward compatibility)
        enable_trailing_stop = config.get('enable_trailing_stop', True)
        trailing_trigger_pips = 30.0
        trailing_distance_pips = 20.0
        
        if enable_trailing_stop and request is None and profit_pips > trailing_trigger_pips:
            trail_dist = trailing_distance_pips * pip_size
            new_sl = 0.0
            digits = symbol_info.digits
            
            if pos.type == mt5.ORDER_TYPE_BUY:
                new_sl = current_price - trail_dist
                new_sl = round(new_sl, digits)
                # Only update if new_sl is higher than current SL (with tolerance)
                tolerance = point * 0.5
                if pos.sl == 0 or new_sl > pos.sl + tolerance:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": symbol,
                        "sl": new_sl,
                        "tp": round(pos.tp, digits) if pos.tp > 0 else 0
                    }
            else:
                new_sl = current_price + trail_dist
                new_sl = round(new_sl, digits)
                # Only update if new_sl is lower than current SL (or SL is 0) (with tolerance)
                tolerance = point * 0.5
                if pos.sl == 0 or new_sl < pos.sl - tolerance:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": symbol,
                        "sl": new_sl,
                        "tp": round(pos.tp, digits) if pos.tp > 0 else 0
                    }
            
            if request:
                symbol_upper = symbol.upper()
                if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
                    print(f"🏃 [Trailing] Ticket {pos.ticket}: SL {pos.sl:.2f} -> {new_sl:.2f} | Profit: {profit_pips:.1f} pips")
                elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
                    print(f"🏃 [Trailing] Ticket {pos.ticket}: SL {pos.sl:.2f} -> {new_sl:.2f} | Profit: {profit_pips:.1f} pips")
                else:
                    print(f"🏃 [Trailing] Ticket {pos.ticket}: SL {pos.sl:.5f} -> {new_sl:.5f} | Profit: {profit_pips:.1f} pips")
                
                # Log to file: TRAILING
                signal_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
                trailing_log_content = (
                    f"🏃 TRAILING - Ticket: {pos.ticket} | "
                    f"Symbol: {symbol} ({signal_type}) | "
                    f"SL: {pos.sl:.5f} -> {new_sl:.5f} | "
                    f"Profit: {profit_pips:.1f} pips"
                )
                log_to_file(symbol, "TRAILING", trailing_log_content)

        if request:
            # Double-check: Only send if there's an actual change
            digits = symbol_info.digits
            new_sl_normalized = round(request['sl'], digits)
            new_tp_normalized = round(request['tp'], digits) if request['tp'] > 0 else 0
            current_sl_normalized = round(pos.sl, digits) if pos.sl > 0 else 0
            current_tp_normalized = round(pos.tp, digits) if pos.tp > 0 else 0
            
            # Skip if no actual change (avoid retcode 10025 "No changes")
            if new_sl_normalized == current_sl_normalized and new_tp_normalized == current_tp_normalized:
                print(f"⏭️ [Breakeven/Trailing] Ticket {pos.ticket}: No change needed (SL already at {current_sl_normalized:.5f})")
                return
            
            res = mt5.order_send(request)
            if res.retcode != mt5.TRADE_RETCODE_DONE:
                # Don't log as error if it's "No changes" (retcode 10025) - this is expected sometimes
                if res.retcode == 10025:
                    print(f"⏭️ [Breakeven/Trailing] Ticket {pos.ticket}: No changes needed (SL/TP already at target)")
                else:
                    error_msg = f"⚠️ Failed to update SL/TP for {pos.ticket}: {res.comment}"
                    print(error_msg)
                    
                    # Log to file: ERROR
                    error_log_content = (
                        f"❌ SL/TP UPDATE ERROR - Ticket: {pos.ticket} | "
                        f"Symbol: {symbol} | Error: {res.comment} | Retcode: {res.retcode}"
                    )
                    log_to_file(symbol, "ERROR", error_log_content)
                    
                    # Send Telegram notification for error (only if not "No changes")
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
                        send_telegram(error_telegram_msg, telegram_token, telegram_chat_id, symbol=symbol)
            else:
                print(f"✅ Successfully updated SL/TP for {pos.ticket}")

    except Exception as e:
        error_msg = f"⚠️ Error managing position {order_ticket}: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        
        # Log to file: ERROR
        log_to_file(symbol, "ERROR", f"Position Management Exception - Ticket: {order_ticket} | Error: {str(e)}")
        
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
                send_telegram(error_telegram_msg, telegram_token, telegram_chat_id, symbol=symbol)
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
