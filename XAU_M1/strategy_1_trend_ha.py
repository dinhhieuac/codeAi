import MetaTrader5 as mt5
import time
import sys
import numpy as np
from datetime import datetime

# Import local modules
sys.path.append('..') # Add parent directory to path to find XAU_M1 modules if running from sub-folder
from db import Database
from utils import load_config, connect_mt5, get_data, calculate_heiken_ashi, send_telegram

# Initialize Database
db = Database("trades.db")

def strategy_1_logic(config):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    
    # Check if we already have an open position
    positions = mt5.positions_get(symbol=symbol)
    if positions:
        for pos in positions:
            if pos.magic == magic:
                print(f"⚠️ Position already open: {pos.ticket}. Waiting...")
                return

    # 1. Get Data (M1 and M5 for trend)
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 200)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 200)
    
    if df_m1 is None or df_m5 is None: 
        return

    # 2. Calculate Indicators
    # Trend Filter: EMA 200 on M5 (or M1 as per guide, let's use M5 for better trend)
    df_m5['ema200'] = df_m5['close'].rolling(window=200).mean() # Using SMA for simplicity or implement EMA
    current_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"

    # Channel: 55 SMA High/Low on M1
    df_m1['sma55_high'] = df_m1['high'].rolling(window=55).mean()
    df_m1['sma55_low'] = df_m1['low'].rolling(window=55).mean()
    
    # Heiken Ashi
    ha_df = calculate_heiken_ashi(df_m1)
    last_ha = ha_df.iloc[-1]
    prev_ha = ha_df.iloc[-2]

    # 3. Check Signals
    signal = None
    price = mt5.symbol_info_tick(symbol).ask if current_trend == "BULLISH" else mt5.symbol_info_tick(symbol).bid
    
    price = mt5.symbol_info_tick(symbol).ask if current_trend == "BULLISH" else mt5.symbol_info_tick(symbol).bid
    
    # Detailed Logging
    print(f"📊 [Strat 1 Analysis] Price: {price:.2f} | Trend (M5): {current_trend}")
    print(f"   HA Close: {last_ha['ha_close']:.2f} | HA Open: {last_ha['ha_open']:.2f}")
    print(f"   SMA55 High: {last_ha['sma55_high']:.2f} | SMA55 Low: {last_ha['sma55_low']:.2f}")
    
    # BUY SETUP
    if current_trend == "BULLISH":
        is_green = last_ha['ha_close'] > last_ha['ha_open']
        is_above_channel = last_ha['ha_close'] > last_ha['sma55_high']
        is_fresh_breakout = prev_ha['ha_close'] <= prev_ha['sma55_high']
        
        if is_green and is_above_channel:
            if is_fresh_breakout:
                signal = "BUY"
            else:
                print("   ❌ Condition Fail: Not a fresh breakout (Previous candle was already above).")
        else:
            print(f"   ❌ Condition Fail: Green? {is_green} | Above Channel? {is_above_channel}")

    # SELL SETUP
    elif current_trend == "BEARISH":
        is_red = last_ha['ha_close'] < last_ha['ha_open']
        is_below_channel = last_ha['ha_close'] < last_ha['sma55_low']
        is_fresh_breakout = prev_ha['ha_close'] >= prev_ha['sma55_low']
        
        if is_red and is_below_channel:
            if is_fresh_breakout:
                signal = "SELL"
            else:
                print("   ❌ Condition Fail: Not a fresh breakout (Previous candle was already below).")
        else:
            print(f"   ❌ Condition Fail: Red? {is_red} | Below Channel? {is_below_channel}")

    
    # 4. Execute Trade
    if signal:
        print(f"🚀 SIGNAL FOUND: {signal} at {price}")
        
        # Calculate SL/TP
        # SL: Recent Swing Low/High or fixed pips. Let's use config pips.
        sl_pips = config['parameters']['sl_pips'] * mt5.symbol_info(symbol).point * 10 
        tp_pips = config['parameters']['tp_pips'] * mt5.symbol_info(symbol).point * 10
        
        sl = price - sl_pips if signal == "BUY" else price + sl_pips
        tp = price + tp_pips if signal == "BUY" else price - tp_pips
        
        # Log signal to DB
        db.log_signal("Strategy_1_Trend_HA", symbol, signal, price, sl, tp, 
                      {"trend": current_trend, "ha_close": last_ha['ha_close'], "ma_high": last_ha['sma55_high']})

        # Send Order
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": "Strat1_Trend_HA",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(result.order, "Strategy_1_Trend_HA", symbol, signal, volume, price, sl, tp, result.comment)
            send_telegram(f"✅ <b>Strat 1 Executed:</b> {signal} {symbol} @ {price}", config['telegram_token'], config['telegram_chat_id'])
        else:
            print(f"❌ Order Failed: {result.retcode}")

if __name__ == "__main__":
    import os
    # Load separate config for this strategy
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_1.json")
    config = load_config(config_path)
    if config and connect_mt5(config):
        print("✅ Strategy 1: Trend HA - Started")
        try:
            while True:
                strategy_1_logic(config)
                time.sleep(1) # Scan every second
        except KeyboardInterrupt:
            print("🛑 Bot Stopped")
            mt5.shutdown()
