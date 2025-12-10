import MetaTrader5 as mt5
import time
import sys
import numpy as np

# Import local modules
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram

db = Database("trades.db")

def strategy_5_logic(config, error_count=0):
    # This strategy requires separate logic for Opening and Managing
    # For Scalping M1: We look for a breakout of the last 15 candles high/low
    
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    
    positions = mt5.positions_get(symbol=symbol)
    my_positions = [p for p in positions if p.magic == magic]
    
    if my_positions:
        pos = my_positions[0]
        current_price = mt5.symbol_info_tick(symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask
        
        profit_pips = (current_price - pos.price_open) / mt5.symbol_info(symbol).point if pos.type == mt5.ORDER_TYPE_BUY else (pos.price_open - current_price) / mt5.symbol_info(symbol).point
        
        # 1. Quick Breakeven (10 pips)
        if profit_pips > 100 and pos.sl != pos.price_open: # 10 pips (100 points)
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "symbol": symbol,
                "sl": pos.price_open, # Breakeven
                "tp": pos.tp
            }
            mt5.order_send(request)
            print(f"🛡️ Moved SL to Breakeven for Ticket {pos.ticket}")
            
        # 2. Trailing Stop for Swing (if profit > 30 pips)
        if profit_pips > 300: 
            # Simple trail: current price - 20 pips
            new_sl = current_price - (200 * mt5.symbol_info(symbol).point) if pos.type == mt5.ORDER_TYPE_BUY else current_price + (200 * mt5.symbol_info(symbol).point)
            
            # Update only if better
            if (pos.type == mt5.ORDER_TYPE_BUY and new_sl > pos.sl) or (pos.type == mt5.ORDER_TYPE_SELL and new_sl < pos.sl):
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": symbol,
                    "sl": new_sl,
                    "tp": pos.tp
                }
                mt5.order_send(request)
                print(f"🏃 Trailing SL for Ticket {pos.ticket}")
        return error_count

    # 2. Check Global Max Positions
    positions = mt5.positions_get(symbol=symbol, magic=magic)
    if positions and len(positions) >= config.get('max_positions', 1):
        print(f"⚠️ Max Positions Reached for Strategy {magic}: {len(positions)}/{config.get('max_positions', 1)}")
        return error_count

    # --- ENTRY MODE ---
    
    # 1. Get Data
    df = get_data(symbol, mt5.TIMEFRAME_M1, 20)
    if df is None: return error_count

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
    
    # BUY: Close > Upper Band
    # SELL: Close < Lower Band
    
    print(f"📊 [Strat 5 Analysis] Price: {last['close']:.2f} | Upper: {last['upper']:.2f} | Lower: {last['lower']:.2f} | RSI: {last['rsi']:.1f}")
    
    if last['close'] > last['upper']:
        if last['rsi'] > 50:
            signal = "BUY"
        else:
            print(f"   ❌ Filtered: Breakout BUY but RSI {last['rsi']:.1f} <= 50")
    elif last['close'] < last['lower']:
        if last['rsi'] < 50:
            signal = "SELL"
        else:
            print(f"   ❌ Filtered: Breakout SELL but RSI {last['rsi']:.1f} >= 50")
        
    if signal:
        # --- SPAM FILTER: Check if we traded in the last 60 seconds ---
        strat_positions = mt5.positions_get(symbol=symbol, magic=magic)
        if strat_positions:
            strat_positions = sorted(strat_positions, key=lambda x: x.time, reverse=True)
            last_trade_time = strat_positions[0].time
            current_server_time = mt5.symbol_info_tick(symbol).time
            if (current_server_time - last_trade_time) < 60:
                print(f"   ⏳ Skipping: Trade already taken {current_server_time - last_trade_time}s ago (Wait 60s per candle)")
                return error_count

        price = mt5.symbol_info_tick(symbol).ask if signal == "BUY" else mt5.symbol_info_tick(symbol).bid
        
        # --- SL/TP Logic based on Config ---
        # Strat 5 typically uses trailing, but initial SL is needed.
        sl_mode = config['parameters'].get('sl_mode', 'fixed')
        reward_ratio = config['parameters'].get('reward_ratio', 1.5)
        
        sl = 0.0
        tp = 0.0 # Strat 5 might want open TP for trailing, but lets set one if requested.
        
        if sl_mode == 'auto_m5':
            df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 10)
            if df_m5 is not None:
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
                 sl = price - 2.0 if signal == "BUY" else price + 2.0
                 tp = price + 5.0 if signal == "BUY" else price - 5.0

        else:
             # Default Strat 5 SL (Tight or recent swing)
             sl = price - 2.0 if signal == "BUY" else price + 2.0
             tp = price + 5.0 if signal == "BUY" else price - 5.0
             print(f"   📏 Default SL: {sl:.2f} | TP: {tp:.2f}")

        print(f"🚀 Strat 5 SIGNAL: {signal} @ {price}")
        
        db.log_signal("Strategy_5_Filter_First", symbol, signal, price, sl, tp, {"setup": "Donchian Breakout", "rsi": last['rsi']})

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
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Success: {result.order}")
            db.log_order(result.order, "Strategy_5_Filter_First", symbol, signal, volume, price, sl, tp, result.comment)
            send_telegram(f"✅ <b>Strat 5 Executed:</b> {signal} {symbol} @ {price}", config['telegram_token'], config['telegram_chat_id'])
            return 0
        else:
            print(f"❌ Order Failed: {result.retcode}")
            return error_count + 1

    return error_count

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
                consecutive_errors = strategy_5_logic(config, consecutive_errors)
                
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
