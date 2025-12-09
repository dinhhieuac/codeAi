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

    # If positions exist BUT they are not mine -> Block new entry
    if positions:
        print(f"⚠️ Market has open positions ({len(positions)}). Waiting...")
        return error_count

    # --- ENTRY MODE ---
    
    # 1. Get Data
    df = get_data(symbol, mt5.TIMEFRAME_M1, 20)
    if df is None: return error_count

    last = df.iloc[-1]
    
    # Donchian Channel 20 (Breakout)
    high_20 = df['high'].rolling(window=20).max().iloc[-2] # Previous 20 highs
    low_20 = df['low'].rolling(window=20).min().iloc[-2]   # Previous 20 lows
    
    signal = None
    
    print(f"📊 [Strat 5 Analysis] Price: {last['close']:.2f}")
    print(f"   Hi 20: {high_20:.2f} | Lo 20: {low_20:.2f}")
    
    # Price breaks High 20
    if last['close'] > high_20:
        signal = "BUY"
    elif last['close'] < low_20:
        signal = "SELL"
    else:
        print("   ❌ No Breakout (Inside Channel)")
        
    if signal:
        price = mt5.symbol_info_tick(symbol).ask if signal == "BUY" else mt5.symbol_info_tick(symbol).bid
        pip = mt5.symbol_info(symbol).point * 10
        
        # Initial Scalp SL/TP
        sl = price - (15 * pip) if signal == "BUY" else price + (15 * pip)
        tp = 0.0 # Open TP for running
        
        print(f"🚀 Strat 5 SIGNAL: {signal} (Breakout) @ {price}")
        
        db.log_signal("Strategy_5_Filter_First", symbol, signal, price, sl, tp, {"setup": "Donchian Breakout"})

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
                    msg = "🛑 CRITICAL: 5 Consecutive Order Failures. Stopping Strategy 5."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    break
                    
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
