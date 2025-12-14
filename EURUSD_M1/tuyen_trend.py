import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# Import local modules
sys.path.append('..') 
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message

# Initialize Database
db = Database()

def calculate_ema(series, span):
    """Calculate EMA"""
    return series.ewm(span=span, adjust=False).mean()

def calculate_atr(df, period=14):
    """Calculate ATR"""
    df = df.copy()
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift(1))
    df['tr2'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=period).mean()
    return df['atr']

def is_doji(row, body_percent=0.1):
    """Body is less than 10% of total range"""
    rng = row['high'] - row['low']
    if rng == 0: return True
    body = abs(row['close'] - row['open'])
    return (body / rng) <= body_percent

def is_pinbar(row, tail_percent=0.6, type='buy'):
    """
    Buy Pinbar: Lower tail is long (>= 60% of range), closing near top.
    Sell Pinbar: Upper tail is long, closing near bottom.
    """
    rng = row['high'] - row['low']
    if rng == 0: return False
    
    body = abs(row['close'] - row['open'])
    upper_wick = row['high'] - max(row['open'], row['close'])
    lower_wick = min(row['open'], row['close']) - row['low']
    
    if type == 'buy':
        # Long lower wick, small body near top
        return (lower_wick / rng) >= tail_percent
    elif type == 'sell':
        # Long upper wick, small body near bottom
        return (upper_wick / rng) >= tail_percent
    return False

def check_signal_candle(row, trend):
    """
    Return True if candle is Doji or Pinbar conforming to trend
    """
    if is_doji(row, 0.2): return True # Allow slightly fatter Doji
    
    if trend == "BULLISH":
        if is_pinbar(row, type='buy'): return True
    elif trend == "BEARISH":
        if is_pinbar(row, type='sell'): return True
        
    return False

def check_compression_block(df_slice):
    """
    Check for Price Action Compression (Block of 3+ candles)
    Criteria:
    1. Min 3 candles
    2. Shrinking or stable range (not expanding violently)
    3. Overlapping bodies (compression)
    """
    if len(df_slice) < 3: return False
    
    # Calculate ranges
    ranges = df_slice['high'] - df_slice['low']
    avg_range = ranges.mean()
    
    # Check if any candle is "Huge" (Momentum) - we want compression, not expansion
    # If a candle range is > 2x average, it's not compression
    if (ranges > avg_range * 2.0).any():
        return False
        
    # Check overlapping (Highs lower, Lows higher? Or just general range containment)
    # Simple compression: Avg Body Size should be small relative to Avg Range
    bodies = abs(df_slice['close'] - df_slice['open'])
    avg_body = bodies.mean()
    
    # Body should be relatively small
    if avg_body > (avg_range * 0.6): # If bodies are big, it's directional, not compressed
        return False
        
    return True

def detect_pattern(df_slice, type='W'):
    """
    Rudimentary Pattern Detection for M (Sell) or W (Buy) over last 5-10 candles.
    """
    # Simply check for Double Bottom/Top logic via fractal or pivots
    # For M1, we can check Swing Points
    # W Pattern: Low1, High1, Low2 (Higher/Same), Break?
    
    # Simplified for Bot: Check if we have two distinct lows (for W) without a lower low
    if len(df_slice) < 5: return False
    
    lows = df_slice['low'].values
    highs = df_slice['high'].values
    
    if type == 'W': # BUY
        # Look for two minima
        # Split data in half?
        mid = len(lows) // 2
        min1 = np.min(lows[:mid])
        min2 = np.min(lows[mid:])
        
        # Min2 should be >= Min1 (Higher Low or Double Bottom)
        # And recent Close should be moving up
        if min2 >= min1 * 0.9999: # Allow tiny violation or exact
             # Also check if we are near the top of the range (ready to break)
             current_close = df_slice.iloc[-1]['close']
             range_high = np.max(highs)
             if current_close > (range_high + min2)/2: # Upper half
                 return True
                 
    elif type == 'M': # SELL
        mid = len(highs) // 2
        max1 = np.max(highs[:mid])
        max2 = np.max(highs[mid:])
        
        # Max2 should be <= Max1 (Lower High or Double Top)
        if max2 <= max1 * 1.0001:
             current_close = df_slice.iloc[-1]['close']
             range_low = np.min(lows)
             if current_close < (range_low + max2)/2: # Lower half
                 return True
                 
    return False

def tuyen_trend_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    # --- 1. Manage Existing Positions ---
    positions = mt5.positions_get(symbol=symbol, magic=magic)
    if positions:
        for pos in positions:
            manage_position(pos.ticket, symbol, magic, config)
        if len(positions) >= max_positions:
            return error_count, 0

    # --- 2. Data Fetching ---
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 300) 
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 300)
    
    if df_m1 is None or df_m5 is None: return error_count, 0

    # --- 3. M5 Trend Detection ---
    df_m5['ema21'] = calculate_ema(df_m5['close'], 21)
    df_m5['ema50'] = calculate_ema(df_m5['close'], 50)
    
    last_m5 = df_m5.iloc[-1]
    
    ema21_slope_up = df_m5.iloc[-1]['ema21'] > df_m5.iloc[-2]['ema21'] > df_m5.iloc[-3]['ema21']
    ema21_slope_down = df_m5.iloc[-1]['ema21'] < df_m5.iloc[-2]['ema21'] < df_m5.iloc[-3]['ema21']
    
    m5_trend = "NEUTRAL"
    if last_m5['close'] > last_m5['ema21'] > last_m5['ema50'] and ema21_slope_up:
        m5_trend = "BULLISH"
    elif last_m5['close'] < last_m5['ema21'] < last_m5['ema50'] and ema21_slope_down:
        m5_trend = "BEARISH"
        
    # --- 4. M1 Setup Checks ---
    df_m1['ema21'] = calculate_ema(df_m1['close'], 21)
    df_m1['ema50'] = calculate_ema(df_m1['close'], 50)
    df_m1['ema200'] = calculate_ema(df_m1['close'], 200) # Added for Strat 2
    df_m1['atr'] = calculate_atr(df_m1, 14)
    
    # Recent completed candles (last 3-5)
    c1 = df_m1.iloc[-2] # Completed
    c2 = df_m1.iloc[-3]
    c3 = df_m1.iloc[-4]
    
    def touches_ema(row):
        # Check simple intersection with EMA 21 or 50
        e21, e50 = row['ema21'], row['ema50']
        high, low = row['high'], row['low']
        return (low <= e21 <= high) or (low <= e50 <= high)

    signal_type = None
    reason = ""
    
    # === STRATEGY 1: PULLBACK + DOJI/PINBAR CLUSTER ===
    # Criteria:
    # 1. Trend M5 (Matched)
    # 2. Touch EMA 21/50
    # 3. Cluster of 2+ Doji/Pinbars
    
    is_strat1 = False
    if m5_trend != "NEUTRAL":
        # Check cluster of 2 signals
        is_c1_sig = check_signal_candle(c1, m5_trend)
        is_c2_sig = check_signal_candle(c2, m5_trend)
        # Check EMA Touch
        is_touch = touches_ema(c1) or touches_ema(c2)
        
        if is_c1_sig and is_c2_sig and is_touch:
            signal_type = "BUY" if m5_trend == "BULLISH" else "SELL"
            is_strat1 = True
            reason = "Strat1_Pullback_Cluster"

    # === STRATEGY 2: CONTINUATION + STRUCTURE (M/W + COMPRESSION) ===
    # Criteria:
    # 1. Trend M5 (Matched)
    # 2. Price > EMA 200 (Buy) or < EMA 200 (Sell) [V2 Requirement]
    # 3. Compression Block or M/W Pattern
    # 4. Near EMA 21/50 (Retest)
    
    is_strat2 = False
    # If Strat 1 already found, we can stick to it, or prioritize? 
    # Strat 1 is safer. Check Strat 2 if Strat 1 is False.
    
    if not is_strat1 and m5_trend != "NEUTRAL":
        # Check EMA 200 Filter
        pass_ema200 = False
        if m5_trend == "BULLISH" and c1['close'] > c1['ema200']: pass_ema200 = True
        if m5_trend == "BEARISH" and c1['close'] < c1['ema200']: pass_ema200 = True
        
        if pass_ema200:
            # Check Compression (Last 3-5 candles)
            recent_block = df_m1.iloc[-5:-1] # 4 completed candles
            is_compressed = check_compression_block(recent_block)
            
            # Check Pattern (M/W)
            is_pattern = detect_pattern(recent_block, type='W' if m5_trend == "BULLISH" else 'M')
            
            # Check EMA Touch (Retest)
            # The block should act around EMA
            block_touch = False
            for idx, row in recent_block.iterrows():
                if touches_ema(row):
                    block_touch = True
                    break
            
            if (is_compressed or is_pattern) and block_touch:
                 signal_type = "BUY" if m5_trend == "BULLISH" else "SELL"
                 is_strat2 = True
                 reason = f"Strat2_Continuation_{'Compression' if is_compressed else 'Pattern'}"

    # --- Logging ---
    price = mt5.symbol_info_tick(symbol).ask if signal_type == "BUY" else mt5.symbol_info_tick(symbol).bid
    print(f"📊 [TuyenTrend] P: {price} | M5: {m5_trend} | S1: {is_strat1} | S2: {is_strat2}")
    
    if not signal_type:
        return error_count, 0
        
    # --- 5. Execution Trigger ---
    # Breakout of the Signal Cluster (Strat 1) or Block (Strat 2)
    
    # Define Range to Break
    if is_strat1:
        trigger_high = max(c1['high'], c2['high'])
        trigger_low = min(c1['low'], c2['low'])
    else: # Strat 2
        # Use the block high/low
        recent_block = df_m1.iloc[-5:-1]
        trigger_high = recent_block['high'].max()
        trigger_low = recent_block['low'].min()
        
    execute = False
    sl = 0.0
    tp = 0.0
    atr_val = c1['atr']
    
    if signal_type == "BUY":
        if price > trigger_high:
            execute = True
            sl = price - (2 * atr_val)
            tp = price + (4 * atr_val)
    elif signal_type == "SELL":
        if price < trigger_low:
            execute = True
            sl = price + (2 * atr_val)
            tp = price - (4 * atr_val)
            
    if execute:
         # Spam Filter (60s)
        strat_positions = mt5.positions_get(symbol=symbol, magic=magic)
        if strat_positions:
            strat_positions = sorted(strat_positions, key=lambda x: x.time, reverse=True)
            if (mt5.symbol_info_tick(symbol).time - strat_positions[0].time) < 60:
                print("   ⏳ Trade taken recently. Waiting.")
                return error_count, 0

        print(f"🚀 SIGNAL EXECUTE: {signal_type} @ {price} | {reason}")
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal_type == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": reason,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(result.order, "Tuyen_Trend", symbol, signal_type, volume, price, sl, tp, reason, account_id=config['account'])
            
             # Telegram
            msg = (
                f"✅ <b>Tuyen Trend Bot Triggered</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal_type})\n"
                f"📋 <b>Reason:</b> {reason}\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.5f} | 🎯 <b>TP:</b> {tp:.5f}\n"
            )
            send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
            return 0, 0
        else:
            print(f"❌ Order Failed: {result.retcode} - {result.comment}")
            return error_count + 1, result.retcode

    return error_count, 0

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Assuming config path remains same
    config_path = os.path.join(script_dir, "configs", "config_tuyen.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    if config and connect_mt5(config):
        print("✅ Tuyen Trend Bot (V2) - Started")
        try:
            while True:
                consecutive_errors, last_error = tuyen_trend_logic(config, consecutive_errors)
                if consecutive_errors >= 5:
                    print("⚠️ Too many errors. Pausing...")
                    time.sleep(120)
                    consecutive_errors = 0
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
