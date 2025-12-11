import MetaTrader5 as mt5
import time
import sys
import numpy as np

# Import local modules
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position

# Initialize Database
db = Database()

def strategy_3_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    # 2. Check Global Max Positions & Manage Existing
    positions = mt5.positions_get(symbol=symbol, magic=magic)
    if positions:
        for pos in positions:
            manage_position(pos.ticket, symbol, magic, config)
            
        if len(positions) >= max_positions:
            return error_count, 0

    # 1. Get Data
    df = get_data(symbol, mt5.TIMEFRAME_M1, 50)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 10) # Added for Auto SL
    if df is None or df_m5 is None: return error_count, 0

    # 2. Indicators
    # SMA 9
    df['sma9'] = df['close'].rolling(window=9).mean()
    
    # Volume MA (to detect spikes)
    df['vol_ma'] = df['tick_volume'].rolling(window=20).mean()
    
    # RSI 14 (Added Filter)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    last = df.iloc[-1]
    
    # 3. Logic: Rejection Candle + Volume Spike near SMA 9
    signal = None
    
    # SMA 9 Filter: Price at entry must be reasonably close to SMA 9 (Mean Reversion / Trend Touch)
    is_near_sma = False
    pip_val = mt5.symbol_info(symbol).point * 10 
    dist_to_sma = abs(last['close'] - last['sma9'])
    
    # Relaxed: Allow up to 2.0 pips distance (20 points)
    if dist_to_sma <= 20 * mt5.symbol_info(symbol).point: 
        is_near_sma = True
        
    # Relaxed: Volume > 1.2x Average
    is_high_volume = last['tick_volume'] > (last['vol_ma'] * 1.2)
    
    # Pinbar Detection (Relaxed: Tail > 1.5 * Body)
    body_size = abs(last['close'] - last['open'])
    upper_shadow = last['high'] - max(last['close'], last['open'])
    lower_shadow = min(last['close'], last['open']) - last['low']
    
    # Minimal body size (very small body allowed)
    min_body = 0.1 * pip_val 
    if body_size < min_body: body_size = min_body # Prevent division by zero or extreme ratios
    
    is_bullish_pinbar = (lower_shadow > 1.5 * body_size) and (upper_shadow < body_size * 1.0)
    is_bearish_pinbar = (upper_shadow > 1.5 * body_size) and (lower_shadow < body_size * 1.0)
    
    # Logging Analysis
    print(f"📊 [Strat 3 Analysis] Price: {last['close']:.2f} | SMA9: {last['sma9']:.2f}")
    print(f"   Vol: {last['tick_volume']} (Req > {int(last['vol_ma']*1.2)}) | Pinbar? {'Bull' if is_bullish_pinbar else 'Bear' if is_bearish_pinbar else 'None'}")
    
    signal = None
    if is_near_sma:
        if is_high_volume:
            if is_bullish_pinbar and last['close'] > last['sma9']:
                if last['rsi'] > 50:
                    signal = "BUY"
                    print("   ✅ Valid Setup: Bullish Pinbar + Vol + RSI > 50")
                else:
                    print(f"   ❌ Filtered: Valid Pinbar but RSI {last['rsi']:.1f} <= 50")
            elif is_bearish_pinbar and last['close'] < last['sma9']:
                if last['rsi'] < 50:
                    signal = "SELL"
                    print("   ✅ Valid Setup: Bearish Pinbar + Vol + RSI < 50")
                else:
                    print(f"   ❌ Filtered: Valid Pinbar but RSI {last['rsi']:.1f} >= 50")
            else:
                 pass # Silent fail for non-pinbars to reduce log spam
                 # print("   ❌ Condition Fail: No valid Pinbar rejection found")
        else:
            if is_bullish_pinbar or is_bearish_pinbar:
                 print(f"   ❌ Filtered: Pinbar found but Volume {last['tick_volume']} too low")
    else:
        # Only print if we had a pinbar but missed SMA
        if is_bullish_pinbar or is_bearish_pinbar:
             print(f"   ❌ Filtered: Pinbar found but Price too far from SMA ({dist_to_sma:.1f} pts)")
    
    # 4. Execute
    if signal:
        # --- SPAM FILTER & COOLDOWN ---
        deals = mt5.history_deals_get(date_from=time.time() - 300, date_to=time.time())
        if deals:
             my_deals = [d for d in deals if d.magic == magic]
             if my_deals:
                 print(f"   ⏳ Cooldown: Last trade was < 5 mins ago. Skipping.")
                 return error_count, 0

        price = mt5.symbol_info_tick(symbol).ask if signal == "BUY" else mt5.symbol_info_tick(symbol).bid
        
        # --- SL/TP Logic based on Config ---
        sl_mode = config['parameters'].get('sl_mode', 'fixed')
        reward_ratio = config['parameters'].get('reward_ratio', 1.5)
        
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
            print(f"   📏 Auto M5 SL: {sl:.2f} | TP: {tp:.2f}")

        else:
            # Default Pinbar SL logic (Below Low / Above High of Pinbar)
            sl = last['low'] - (20 * mt5.symbol_info(symbol).point) if signal == "BUY" else last['high'] + (20 * mt5.symbol_info(symbol).point)
            
            risk = abs(price - sl)
            tp = price + (risk * 2) if signal == "BUY" else price - (risk * 2)
            print(f"   📏 Pinbar SL: {sl:.2f} | TP: {tp:.2f}")

        print(f"🚀 Strat 3 SIGNAL: {signal} @ {price}")
        
        db.log_signal("Strategy_3_PA_Volume", symbol, signal, price, sl, tp, 
                      {"vol": int(last['tick_volume']), "vol_ma": int(last['vol_ma']), "pinbar": True, "rsi": float(last['rsi'])},
                      account_id=config['account'])

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
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Success: {result.order}")
            db.log_order(result.order, "Strategy_3_PA_Volume", symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
            
            msg = (
                f"✅ <b>Strat 3: PA Volume Executed</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"👤 <b>Account:</b> {config['account']}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal})\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.2f} | 🎯 <b>TP:</b> {tp:.2f}\n"
                f"📊 <b>Indicators:</b>\n"
                f"• Vol: {int(last['tick_volume'])}\n"
                f"• Vol MA: {int(last['vol_ma'])}\n"
                f"• RSI: {last['rsi']:.1f}"
            )
            send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
            send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
            return 0, 0
        else:
            print(f"❌ Order Failed: {result.retcode}")
            return error_count + 1, result.retcode
            
    return error_count, 0

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
                consecutive_errors, last_error_code = strategy_3_logic(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    msg = f"⚠️ [Strategy 3: PA Volume] WARNING: 5 Consecutive Order Failures. Last Error: {last_error_code}. Pausing for 2 minutes..."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    time.sleep(120)
                    consecutive_errors = 0
                    print("▶️ Resuming...")
                    continue
                    
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
