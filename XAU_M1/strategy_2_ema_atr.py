import MetaTrader5 as mt5
import time
import sys
import numpy as np

# Import local modules
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram

# Initialize Database
db = Database("trades.db")

def strategy_2_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    positions = mt5.positions_get(symbol=symbol)
    if positions and len(positions) >= max_positions:
        print(f"⚠️ Market has open positions ({len(positions)} >= {max_positions}). Waiting...")
        return error_count

    # 1. Get Data
    df = get_data(symbol, mt5.TIMEFRAME_M1, 100)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 10) # Added for Auto M5 SL
    if df is None or df_m5 is None: return error_count

    # 2. Indicators
    # EMA 14 and 28
    df['ema14'] = df['close'].ewm(span=14, adjust=False).mean()
    df['ema28'] = df['close'].ewm(span=28, adjust=False).mean()
    
    # ATR 14
    df['tr'] = np.maximum(
        df['high'] - df['low'], 
        np.maximum(
            abs(df['high'] - df['close'].shift(1)), 
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(window=14).mean()

    # RSI 14 (Added Filter)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 3. Logic: Crossover + RSI Filter
    signal = None
    
    print(f"📊 [Strat 2 Analysis] EMA14: {last['ema14']:.3f} | EMA28: {last['ema28']:.3f} | ATR: {last['atr']:.3f} | RSI: {last['rsi']:.1f}")
    
    # BUY: EMA 14 crosses ABOVE EMA 28 AND RSI > 50
    if prev['ema14'] <= prev['ema28'] and last['ema14'] > last['ema28']:
        if last['rsi'] > 50:
            signal = "BUY"
            print("   ✅ Crossover: EMA 14 > EMA 28 AND RSI > 50 (Strong Uptrend)")
        else:
            print(f"   ❌ Filtered: Crossover BUY but RSI {last['rsi']:.1f} <= 50")
        
    # SELL: EMA 14 crosses BELOW EMA 28 AND RSI < 50
    elif prev['ema14'] >= prev['ema28'] and last['ema14'] < last['ema28']:
        if last['rsi'] < 50:
            signal = "SELL"
            print("   ✅ Crossover: EMA 14 < EMA 28 AND RSI < 50 (Strong Downtrend)")
        else:
             print(f"   ❌ Filtered: Crossover SELL but RSI {last['rsi']:.1f} >= 50")
    else:
        diff = last['ema14'] - last['ema28']
        if diff > 0:
            print(f"   ❌ No Cross (Already Bullish, Gap: {diff:.3f})")
        else:
            print(f"   ❌ No Cross (Already Bearish, Gap: {diff:.3f})")
        
    # 4. Execute
    if signal:
        # --- SPAM FILTER: Check if we traded in the last 60 seconds ---
        # Get all open positions for this specific strategy
        strat_positions = mt5.positions_get(symbol=symbol, magic=magic)
        if strat_positions:
            # Sort by open time descending (newest first)
            strat_positions = sorted(strat_positions, key=lambda x: x.time, reverse=True)
            last_trade_time = strat_positions[0].time
            current_server_time = mt5.symbol_info_tick(symbol).time
            
            # If last trade was less than 60 seconds ago, SKIP
            if (current_server_time - last_trade_time) < 60:
                print(f"   ⏳ Skipping: Trade already taken {current_server_time - last_trade_time}s ago (Wait 60s per candle)")
                return error_count

        price = mt5.symbol_info_tick(symbol).ask if signal == "BUY" else mt5.symbol_info_tick(symbol).bid
        
        # --- SL/TP Logic ---
        sl_mode = config['parameters'].get('sl_mode', 'atr') # Default to ATR for Strat 2
        reward_ratio = config['parameters'].get('reward_ratio', 1.5)
        atr_val = last['atr']
        
        sl = 0.0
        tp = 0.0
        
        if sl_mode == 'auto_m5':
             # Auto M5 Logic
            prev_m5_high = df_m5.iloc[-2]['high']
            prev_m5_low = df_m5.iloc[-2]['low']
            buffer = 20 * mt5.symbol_info(symbol).point
            
            if signal == "BUY":
                sl = prev_m5_low - buffer
                min_dist = 100 * mt5.symbol_info(symbol).point
                if (price - sl) < min_dist: sl = price - min_dist
                risk_dist = price - sl
                tp = price + (risk_dist * reward_ratio)
                
            elif signal == "SELL":
                sl = prev_m5_high + buffer
                min_dist = 100 * mt5.symbol_info(symbol).point
                if (sl - price) < min_dist: sl = price + min_dist
                risk_dist = sl - price
                tp = price - (risk_dist * reward_ratio)
            
            print(f"   📏 Auto M5 SL: {sl:.2f} | TP: {tp:.2f} (R:R {reward_ratio})")
            
        else:
            # Dynamic SL/TP based on ATR (Original)
            sl_dist = atr_val * 2.0
            tp_dist = atr_val * 3.0 # R:R 1:1.5
            sl = price - sl_dist if signal == "BUY" else price + sl_dist
            tp = price + tp_dist if signal == "BUY" else price - tp_dist
            print(f"   📏 ATR SL: {sl:.2f} | TP: {tp:.2f} (ATR: {atr_val:.2f})")
            
        print(f"🚀 Strat 2 SIGNAL: {signal} @ {price}")

        db.log_signal("Strategy_2_EMA_ATR", symbol, signal, price, sl, tp, 
                      {"ema14": last['ema14'], "ema28": last['ema28'], "atr": atr_val, "rsi": last['rsi']})
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": "Strat2_EMA_ATR",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Scussess: {result.order}")
            db.log_order(result.order, "Strategy_2_EMA_ATR", symbol, signal, volume, price, sl, tp, result.comment)
            send_telegram(f"✅ <b>Strat 2 Executed:</b> {signal} {symbol} @ {price}", config['telegram_token'], config['telegram_chat_id'])
            return 0
        else:
            print(f"❌ Order Failed: {result.retcode}")
            return error_count + 1
            
    return error_count

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_2.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 2: EMA ATR - Started")
        try:
            while True:
                consecutive_errors = strategy_2_logic(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    msg = "⚠️ WARNING: 5 Consecutive Order Failures. Pausing for 2 minutes..."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    time.sleep(120)
                    consecutive_errors = 0
                    print("▶️ Resuming...")
                    continue
                    
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
