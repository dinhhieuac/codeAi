import MetaTrader5 as mt5
import time
import sys
import numpy as np

# Import local modules
sys.path.append('..')
from db import Database
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message

# Initialize Database
db = Database()

def strategy_5_logic(config, error_count=0):
    # This strategy requires separate logic for Opening and Managing
    # For Scalping M1: We look for a breakout of the last 15 candles high/low
    
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

    # --- ENTRY MODE ---
    
    # 1. Get Data
    df = get_data(symbol, mt5.TIMEFRAME_M1, 100)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 200) # For Trend Filter
    
    if df is None or df_m5 is None: return error_count, 0

    # Trend Filter (M5 EMA 200)
    df_m5['ema200'] = df_m5['close'].rolling(window=200).mean()
    m5_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"

    # Donchian Channel 20 (Breakout)
    df['upper'] = df['high'].rolling(window=20).max().shift(1) # Previous 20 highs
    df['lower'] = df['low'].rolling(window=20).min().shift(1)   # Previous 20 lows
    
    # RSI 14 (Added Filter)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    last = df.iloc[-1]
    
    # 3. Logic: Donchian Breakout
    signal = None
    
    # BUY: Close > Upper Band + Buffer
    # SELL: Close < Lower Band - Buffer
    
    buffer = 50 * mt5.symbol_info(symbol).point # 0.5 pips / 50 points
    
    print(f"📊 [Strat 5 Analysis] Price: {last['close']:.2f} | M5 Trend: {m5_trend} | RSI: {last['rsi']:.1f}")
    
    if last['close'] > (last['upper'] + buffer):
        if m5_trend == "BULLISH":
            if last['rsi'] > 50:
                signal = "BUY"
                print("   ✅ Valid Breakout BUY")
            else:
                print(f"   ❌ Filtered: Breakout BUY but RSI {last['rsi']:.1f} <= 50")
        else:
             print(f"   ❌ Filtered: Breakout BUY but M5 Trend is BEARISH")
             
    elif last['close'] < (last['lower'] - buffer):
        if m5_trend == "BEARISH":
            if last['rsi'] < 50:
                signal = "SELL"
                print("   ✅ Valid Breakout SELL")
            else:
                print(f"   ❌ Filtered: Breakout SELL but RSI {last['rsi']:.1f} >= 50")
        else:
            print(f"   ❌ Filtered: Breakout SELL but M5 Trend is BULLISH")
        
    if signal:
        # --- SPAM FILTER & COOLDOWN ---
        # 1. 5-Minute Cooldown logic
        history = mt5.history_deals_get(position_id=0) # Get all deals? No, need specific history lookup
        # Better: check last closed time from DB or MT5 history for this magic.
        # Simple method: Check if we have traded recently within this session (approx) 
        # OR just use the last_trade_time from helper if we kept state, but we don't.
        # Let's rely on standard Last Trade check but increase time to 300s (5 mins)
        
        deals = mt5.history_deals_get(date_from=time.time() - 300, date_to=time.time())
        if deals:
             my_deals = [d for d in deals if d.magic == magic]
             if my_deals:
                 print(f"   ⏳ Cooldown: Last trade was < 5 mins ago. Skipping.")
                 return error_count, 0

        price = mt5.symbol_info_tick(symbol).ask if signal == "BUY" else mt5.symbol_info_tick(symbol).bid
        
        # --- SL/TP Logic based on Config ---
        # Strat 5 typically uses trailing, but initial SL is needed.
        sl_mode = config['parameters'].get('sl_mode', 'fixed')
        reward_ratio = config['parameters'].get('reward_ratio', 1.5)
        
        sl = 0.0
        tp = 0.0 # Strat 5 might want open TP for trailing, but lets set one if requested.
        
        if sl_mode == 'auto_m5':
            # Use fetched M5 data
            prev_m5_high = df_m5.iloc[-2]['high']
            prev_m5_low = df_m5.iloc[-2]['low']
            buffer_sl = 20 * mt5.symbol_info(symbol).point
            
            if signal == "BUY":
                sl = prev_m5_low - buffer_sl
                min_dist = 100 * mt5.symbol_info(symbol).point
                if (price - sl) < min_dist: sl = price - min_dist
                risk_dist = price - sl
                tp = price + (risk_dist * reward_ratio)
                
            elif signal == "SELL":
                sl = prev_m5_high + buffer_sl
                min_dist = 100 * mt5.symbol_info(symbol).point
                if (sl - price) < min_dist: sl = price + min_dist
                risk_dist = sl - price
                tp = price - (risk_dist * reward_ratio)
            print(f"   📏 Auto M5 SL: {sl:.2f} | TP: {tp:.2f}")
        else:
             # Default Strat 5 SL (Tight or recent swing)
             sl = price - 2.0 if signal == "BUY" else price + 2.0
             tp = price + 5.0 if signal == "BUY" else price - 5.0
             print(f"   📏 Default SL: {sl:.2f} | TP: {tp:.2f}")

        print(f"🚀 Strat 5 SIGNAL: {signal} @ {price}")
        
        db.log_signal("Strategy_5_Filter_First", symbol, signal, price, sl, tp, {"setup": "Donchian Breakout", "rsi": float(last['rsi']), "trend": m5_trend}, account_id=config['account'])

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": "Strat5_FilterFirst",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Success: {result.order}")
            db.log_order(result.order, "Strategy_5_Filter_First", symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
            
            msg = (
                f"✅ <b>Strat 5: Filter First Executed</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"👤 <b>Account:</b> {config['account']}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal})\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.2f} | 🎯 <b>TP:</b> {tp:.2f}\n"
                f"📊 <b>Indicators:</b>\n"
                f"• Donchian Breakout\n"
                f"• RSI: {last['rsi']:.1f}"
            )
            send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
            return 0, 0
        else:
            print(f"❌ Order Failed: {result.retcode}")
            return error_count + 1, result.retcode

    return error_count, 0

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_5.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 5: Filter First - Started")
        try:
            while True:
                consecutive_errors, last_error_code = strategy_5_logic(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Strategy 5: Filter First] WARNING: 5 Consecutive Order Failures. Last Error: {error_msg}. Pausing for 2 minutes..."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    time.sleep(120)
                    consecutive_errors = 0
                    print("▶️ Resuming...")
                    continue
                    
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
