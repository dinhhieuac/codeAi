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
    # Need sufficient history for EMA 200/50
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 300) 
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 300)
    
    if df_m1 is None or df_m5 is None: return error_count, 0

    # --- 3. M5 Trend Detection ---
    # 1.1: Supply/Demand H1 (Skipped - manual/visual mostly, assume trend following is safe)
    # 1.2: Structure M5
    # Sell: Price < EMA 21 < EMA 50, EMA Slope Down
    # Buy: Price > EMA 21 > EMA 50, EMA Slope Up
    
    df_m5['ema21'] = calculate_ema(df_m5['close'], 21)
    df_m5['ema50'] = calculate_ema(df_m5['close'], 50)
    
    last_m5 = df_m5.iloc[-1]
    prev_m5 = df_m5.iloc[-2] # Completed candle
    
    # Check Slope (using last 3 candles to ensure it's not flat)
    ema21_slope_up = df_m5.iloc[-1]['ema21'] > df_m5.iloc[-2]['ema21'] > df_m5.iloc[-3]['ema21']
    ema21_slope_down = df_m5.iloc[-1]['ema21'] < df_m5.iloc[-2]['ema21'] < df_m5.iloc[-3]['ema21']
    
    m5_trend = "NEUTRAL"
    if last_m5['close'] > last_m5['ema21'] > last_m5['ema50'] and ema21_slope_up:
        m5_trend = "BULLISH"
    elif last_m5['close'] < last_m5['ema21'] < last_m5['ema50'] and ema21_slope_down:
        m5_trend = "BEARISH"
        
    # --- 4. M1 Pullback & Setup ---
    # 2.2: Pullback to EMA 21/50
    # 2.3: Cluster of min 2 Doji/Pinbar
    
    df_m1['ema21'] = calculate_ema(df_m1['close'], 21)
    df_m1['ema50'] = calculate_ema(df_m1['close'], 50)
    df_m1['atr'] = calculate_atr(df_m1, 14)
    
    # We look at completed candles for the Setup Cluster
    c1 = df_m1.iloc[-2] # Most recent completed
    c2 = df_m1.iloc[-3] # Previous
    
    # Check if candles are "Around EMA"
    # Logic: Low <= EMA21 <= High OR Low <= EMA50 <= High (Intersects)
    # OR Body is between EMA21 and EMA50?
    # "Chững lại tại EMA" -> Interaction or close proximity.
    
    def touches_ema(row):
        # Check proximity to EMA 21 or 50 (within 2 pips?)
        # Or Just High >= EMA >= Low
        e21 = row['ema21']
        e50 = row['ema50']
        
        # Check limits
        c_high = row['high']
        c_low = row['low']
        
        # Intersection
        cond21 = (c_low <= e21 <= c_high)
        cond50 = (c_low <= e50 <= c_high)
        
        # Or close proximity (if price is just sitting on top)
        # Assuming Trend, for Buy, Low might just touch EMA
        return cond21 or cond50

    setup_valid = False
    signal_type = None
    
    # Check Setup Candles
    is_c1_signal = check_signal_candle(c1, m5_trend)
    is_c2_signal = check_signal_candle(c2, m5_trend)
    
    # Check interaction with EMA
    # At least one of the candles in cluster should interact with EMA
    is_near_ema = touches_ema(c1) or touches_ema(c2)
    
    # Valid Cluster?
    if m5_trend != "NEUTRAL" and is_c1_signal and is_c2_signal and is_near_ema:
        signal_type = "BUY" if m5_trend == "BULLISH" else "SELL"
        setup_valid = True
        
    price = mt5.symbol_info_tick(symbol).ask if signal_type == "BUY" else mt5.symbol_info_tick(symbol).bid
    
    # Logging
    print(f"📊 [TuyenTrend] P: {price} | M5 Trend: {m5_trend}")
    print(f"   M1 Candles (-2, -3): Signal? {is_c1_signal}, {is_c2_signal} | Near EMA? {is_near_ema}")
    
    if not setup_valid:
        return error_count, 0
        
    # --- 5. Execution Trigger ---
    # Buy: Break High of Signal
    # Sell: Break Low of Signal
    
    cluster_high = max(c1['high'], c2['high'])
    cluster_low = min(c1['low'], c2['low'])
    
    execute = False
    sl = 0.0
    tp = 0.0
    
    if signal_type == "BUY":
        # Breakout check
        if price > cluster_high:
            execute = True
            atr_val = c1['atr']
            sl = price - (2 * atr_val) # SL = 2 * ATR
            tp = price + (4 * atr_val) # TP = 2 * SL (2 * 2 = 4 ATR)
            
            # Safety checks for SL
            # Ensure SL is below cluster low? Strategy says 2*ATR, usually safer.
            # But technically SL should be logical. Doc says "SL = 2 x ATR(14)". Stick to doc.
            
    elif signal_type == "SELL":
        if price < cluster_low:
            execute = True
            atr_val = c1['atr']
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

        print(f"🚀 SIGNAL EXECUTE: {signal_type} @ {price}")
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal_type == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": "Tuyen_Trend_M1",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(result.order, "Tuyen_Trend", symbol, signal_type, volume, price, sl, tp, result.comment, account_id=config['account'])
            
             # Telegram
            msg = (
                f"✅ <b>Tuyen Trend Bot Triggered</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal_type})\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.5f} | 🎯 <b>TP:</b> {tp:.5f}\n"
                f"📉 <b>Reason:</b> M5 Trend + M1 EMA Pullback + 2 Candle Rejection"
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
    config_path = os.path.join(script_dir, "configs", "config_tuyen.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    if config and connect_mt5(config):
        print("✅ Tuyen Trend Bot - Started")
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
