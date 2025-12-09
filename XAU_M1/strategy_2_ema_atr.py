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
    if df is None: return

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
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 3. Logic: Crossover
    signal = None
    
    print(f"📊 [Strat 2 Analysis] EMA14: {last['ema14']:.3f} | EMA28: {last['ema28']:.3f} | ATR: {last['atr']:.3f}")
    
    # BUY: EMA 14 crosses ABOVE EMA 28
    if prev['ema14'] <= prev['ema28'] and last['ema14'] > last['ema28']:
        signal = "BUY"
        print("   ✅ Crossover: EMA 14 crossed ABOVE EMA 28")
        
    # SELL: EMA 14 crosses BELOW EMA 28
    elif prev['ema14'] >= prev['ema28'] and last['ema14'] < last['ema28']:
        signal = "SELL"
        print("   ✅ Crossover: EMA 14 crossed BELOW EMA 28")
    else:
        diff = last['ema14'] - last['ema28']
        if diff > 0:
            print(f"   ❌ No Cross (Already Bullish, Gap: {diff:.3f})")
        else:
            print(f"   ❌ No Cross (Already Bearish, Gap: {diff:.3f})")
        
    # 4. Execute
    if signal:
        price = mt5.symbol_info_tick(symbol).ask if signal == "BUY" else mt5.symbol_info_tick(symbol).bid
        atr_val = last['atr']
        
        # Dynamic SL/TP based on ATR
        sl_dist = atr_val * 2.0
        tp_dist = atr_val * 3.0 # R:R 1:1.5
        
        sl = price - sl_dist if signal == "BUY" else price + sl_dist
        tp = price + tp_dist if signal == "BUY" else price - tp_dist
        
        print(f"🚀 Strat 2 SIGNAL: {signal} @ {price} | ATR: {atr_val:.2f}")

        db.log_signal("Strategy_2_EMA_ATR", symbol, signal, price, sl, tp, 
                      {"ema14": last['ema14'], "ema28": last['ema28'], "atr": atr_val})
        
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
                    msg = "🛑 CRITICAL: 5 Consecutive Order Failures. Stopping Strategy 2."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    break
                    
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
