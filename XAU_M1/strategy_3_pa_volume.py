import MetaTrader5 as mt5
import time
import sys
import numpy as np

# Import local modules
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram

db = Database("trades.db")

def strategy_3_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    positions = mt5.positions_get(symbol=symbol)
    if positions and len(positions) >= max_positions:
        print(f"⚠️ Market has open positions ({len(positions)} >= {max_positions}). Waiting...")
        return error_count

    # 1. Get Data
    df = get_data(symbol, mt5.TIMEFRAME_M1, 50)
    if df is None: return

    # 2. Indicators
    # SMA 9
    df['sma9'] = df['close'].rolling(window=9).mean()
    
    # Volume MA (to detect spikes)
    df['vol_ma'] = df['tick_volume'].rolling(window=20).mean()
    
    last = df.iloc[-1]
    
    # 3. Logic: Rejection Candle + Volume Spike near SMA 9
    signal = None
    
    # Check Price proximity to SMA 9 (e.g., within 2 pips)
    pip_val = mt5.symbol_info(symbol).point * 10
    dist_to_sma = abs(last['close'] - last['sma9'])
    is_near_sma = dist_to_sma < (2 * pip_val) # Close enough to SMA
    
    # Check Volume Spike (Current Volume > 1.5 * Avg Volume)
    is_high_volume = last['tick_volume'] > (last['vol_ma'] * 1.5)
    
    # Check Rejection (Pinbar)
    # Bullish Pinbar: Lower shadow is long, close near high
    body_size = abs(last['close'] - last['open'])
    lower_shadow = last['open'] - last['low'] if last['close'] > last['open'] else last['close'] - last['low']
    upper_shadow = last['high'] - last['close'] if last['close'] > last['open'] else last['high'] - last['open']
    
    is_bullish_pinbar = (lower_shadow > 2 * body_size) and (upper_shadow < body_size)
    is_bearish_pinbar = (upper_shadow > 2 * body_size) and (lower_shadow < body_size)
    
    # BUY Signal
    
    print(f"📊 [Strat 3 Analysis] Price: {last['close']:.2f} | SMA9: {last['sma9']:.2f}")
    print(f"   Volume: {last['tick_volume']} (Avg: {last['vol_ma']:.1f}) | High Vol? {is_high_volume}")
    print(f"   Dist to SMA: {dist_to_sma:.3f} (Max: {2*pip_val:.3f}) | Near SMA? {is_near_sma}")
    print(f"   Bull Pinbar? {is_bullish_pinbar} | Bear Pinbar? {is_bearish_pinbar}")
    
    if is_near_sma and is_high_volume:
        if is_bullish_pinbar and last['close'] > last['sma9']:
            signal = "BUY"
        elif is_bearish_pinbar and last['close'] < last['sma9']:
            signal = "SELL"
        else:
            print("   ❌ Condition Fail: No valid Pinbar rejection found")
    else:
        print("   ❌ Condition Fail: Volume too low or Not near SMA")
    
    # 4. Execute
    if signal:
        price = mt5.symbol_info_tick(symbol).ask if signal == "BUY" else mt5.symbol_info_tick(symbol).bid
        
        # Tight SL behind the pinbar tail
        sl = last['low'] - pip_val if signal == "BUY" else last['high'] + pip_val
        sl_dist = abs(price - sl)
        
        # TP 2 times risk
        tp_dist = sl_dist * 2
        tp = price + tp_dist if signal == "BUY" else price - tp_dist

        print(f"🚀 Strat 3 SIGNAL: {signal} (Pinbar Vol) @ {price}")
        
        db.log_signal("Strategy_3_PA_Volume", symbol, signal, price, sl, tp, 
                      {"vol": int(last['tick_volume']), "vol_ma": int(last['vol_ma']), "pattern": "Pinbar"})

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": "Strat3_PA_Vol",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Success: {result.order}")
            db.log_order(result.order, "Strategy_3_PA_Volume", symbol, signal, volume, price, sl, tp, result.comment)
            send_telegram(f"✅ <b>Strat 3 Executed:</b> {signal} {symbol} @ {price}", config['telegram_token'], config['telegram_chat_id'])
            return 0
        else:
            print(f"❌ Order Failed: {result.retcode}")
            return error_count + 1
            
    return error_count

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_3.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 3: PA Volume - Started")
        try:
            while True:
                consecutive_errors = strategy_3_logic(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    msg = "🛑 CRITICAL: 5 Consecutive Order Failures. Stopping Strategy 3."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    break
                    
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
