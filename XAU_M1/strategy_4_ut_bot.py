import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd

# Import local modules
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram

db = Database("trades.db")

def calculate_ut_bot(df, sensitivity=2, period=10):
    """
    Approximate UT Bot Logic:
    ATR Trailing Stop logic basically.
    """
    df['atr'] = df['high'].combine(df['close'].shift(1), max) - df['low'].combine(df['close'].shift(1), min)
    df['atr'] = df['atr'].rolling(window=period).mean()
    df['n_loss'] = sensitivity * df['atr']
    
    # Initialize Stop Logic columns
    df['x_atr_trailing_stop'] = 0.0
    df['pos'] = 0 # 1 for Buy, -1 for Sell
    
    for i in range(1, len(df)):
        # Calculate trailing stop
        if df.at[i, 'close'] > df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] > df.at[i-1, 'x_atr_trailing_stop']:
            df.at[i, 'x_atr_trailing_stop'] = max(df.at[i-1, 'x_atr_trailing_stop'], df.at[i, 'close'] - df.at[i, 'n_loss'])
        elif df.at[i, 'close'] < df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] < df.at[i-1, 'x_atr_trailing_stop']:
            df.at[i, 'x_atr_trailing_stop'] = min(df.at[i-1, 'x_atr_trailing_stop'], df.at[i, 'close'] + df.at[i, 'n_loss'])
        elif df.at[i, 'close'] > df.at[i-1, 'x_atr_trailing_stop']:
            df.at[i, 'x_atr_trailing_stop'] = df.at[i, 'close'] - df.at[i, 'n_loss']
        else:
            df.at[i, 'x_atr_trailing_stop'] = df.at[i, 'close'] + df.at[i, 'n_loss']
            
        # Determine Position
        prev_pos = df.at[i-1, 'pos']
        if df.at[i, 'close'] > df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] < df.at[i-1, 'x_atr_trailing_stop']:
             df.at[i, 'pos'] = 1 # BUY Signal transition
        elif df.at[i, 'close'] < df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] > df.at[i-1, 'x_atr_trailing_stop']:
             df.at[i, 'pos'] = -1 # SELL Signal transition
        else:
             df.at[i, 'pos'] = prev_pos if prev_pos != 0 else (1 if df.at[i, 'close'] > df.at[i, 'x_atr_trailing_stop'] else -1)

    return df

def strategy_4_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    positions = mt5.positions_get(symbol=symbol)
    if positions and len(positions) >= max_positions:
        print(f"⚠️ Market has open positions ({len(positions)} >= {max_positions}). Waiting...")
        return error_count

    # 1. Get Data
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 200)
    df_h1 = get_data(symbol, mt5.TIMEFRAME_H1, 50) # Trend Filter
    
    if df_m1 is None or df_h1 is None: return

    # 2. Indicators
    # Trend Filter (H1 MACD or just simple MA)
    df_h1['ema50'] = df_h1['close'].ewm(span=50).mean()
    trend = "BULLISH" if df_h1.iloc[-1]['close'] > df_h1.iloc[-1]['ema50'] else "BEARISH"
    
    # UT Bot on M1
    df_ut = calculate_ut_bot(df_m1, sensitivity=2, period=10)
    last = df_ut.iloc[-1]
    prev = df_ut.iloc[-2]
    
    # 3. Signals
    signal = None
    
    print(f"📊 [Strat 4 Analysis] Trend H1: {trend}")
    print(f"   UT Bot Pos: {last['pos']} (Prev: {prev['pos']})")
    
    # BUY: UT Bot matches H1 Trend
    # UT Bot Signal flips from -1 to 1 (Buy Signal)
    if trend == "BULLISH":
        if prev['pos'] == -1 and last['pos'] == 1:
            signal = "BUY"
        else:
            print("   ❌ No Signal: Waiting for UT Bot BUY flip (-1 -> 1)")

    # SELL: UT Bot matches H1 Trend
    # UT Bot Signal flips from 1 to -1 (Sell Signal)
    elif trend == "BEARISH":
        if prev['pos'] == 1 and last['pos'] == -1:
            signal = "SELL"
        else:
            print("   ❌ No Signal: Waiting for UT Bot SELL flip (1 -> -1)")
        
    # 4. Execute
    if signal:
        price = mt5.symbol_info_tick(symbol).ask if signal == "BUY" else mt5.symbol_info_tick(symbol).bid
        
        # UT Bot uses the ATR line as SL usually
        sl = last['x_atr_trailing_stop']
        
        # Calculate R:R 1:1.5 or 1:2
        risk = abs(price - sl)
        tp = price + (risk * 2) if signal == "BUY" else price - (risk * 2)
        
        print(f"🚀 Strat 4 SIGNAL: {signal} (UT Bot) @ {price} | Trend: {trend}")
        
        db.log_signal("Strategy_4_UT_Bot", symbol, signal, price, sl, tp, 
                      {"trend": trend, "ut_stop": last['x_atr_trailing_stop']})

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": "Strat4_UT_Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Success: {result.order}")
            db.log_order(result.order, "Strategy_4_UT_Bot", symbol, signal, volume, price, sl, tp, result.comment)
            send_telegram(f"✅ <b>Strat 4 Executed:</b> {signal} {symbol} @ {price}", config['telegram_token'], config['telegram_chat_id'])
            return 0
        else:
             print(f"❌ Order Failed: {result.retcode}")
             return error_count + 1
             
    return error_count

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_4.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 4: UT Bot - Started")
        try:
            while True:
                consecutive_errors = strategy_4_logic(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    msg = "🛑 CRITICAL: 5 Consecutive Order Failures. Stopping Strategy 4."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    break
                    
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
