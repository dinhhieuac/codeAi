import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# Import local modules
sys.path.append('..') # Add parent directory to path to find XAU_M1 modules if running from sub-folder
from db import Database
from db import Database
from utils import load_config, connect_mt5, get_data, calculate_heiken_ashi, send_telegram, is_doji, manage_position, get_mt5_error_message, calculate_rsi, calculate_adx, calculate_atr, check_consecutive_losses

# Initialize Database
db = Database()

def strategy_1_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    # 2. Check Global Max Positions & Manage Existing
    positions = mt5.positions_get(symbol=symbol, magic=magic)
    if positions:
        # Manage Trailing SL for all open positions of this strategy
        for pos in positions:
            manage_position(pos.ticket, symbol, magic, config)
            
        if len(positions) >= max_positions:
            # Silent return to avoid spam
            return error_count, 0

    # 1. Get Data (M1, M5, H1)
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 200)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 200)
    df_h1 = get_data(symbol, mt5.TIMEFRAME_H1, 250) # Need 200 for EMA
    
    if df_m1 is None or df_m5 is None or df_h1 is None: 
        return error_count, 0

    # --- SESSION FILTER ---
    session_start = config['parameters'].get('session_start_hour', 0)
    session_end = config['parameters'].get('session_end_hour', 24)
    current_hour = mt5.symbol_info_tick(symbol).time.hour
    if not (session_start <= current_hour < session_end):
        # Handle wrap around if needed (e.g. 23 to 8) but simplified for now (0-24 usually)
        # If start > end (e.g. 22 to 8), then valid is >= 22 OR < 8
        is_in_session = False
        if session_start < session_end:
             is_in_session = session_start <= current_hour < session_end
        else:
             is_in_session = current_hour >= session_start or current_hour < session_end
        
        if not is_in_session:
             # Silent return or periodic log? Silent to avoid spam
             if current_hour % 4 == 0 and mt5.symbol_info_tick(symbol).time.minute == 0:
                  print(f"   💤 Session Filter: Current hour {current_hour} not in {session_start}-{session_end}")
             return error_count, 0

    # 2. Calculate Indicators
    # Trend Filter: EMA 200 on M5 (using EMA for better trend following)
    df_m5['ema200'] = df_m5['close'].ewm(span=200, adjust=False).mean()
    # Trend Filter: EMA 200 on H1 [NEW]
    df_h1['ema200'] = df_h1['close'].ewm(span=200, adjust=False).mean()
    
    # ADX for trend strength confirmation
    df_m5 = calculate_adx(df_m5, period=14)
    # ATR for Volatility [NEW]
    df_m5 = calculate_atr(df_m5, period=14)
    
    adx_threshold = config['parameters'].get('adx_min_threshold', 20)
    atr_threshold = config['parameters'].get('atr_min_threshold', 0.0)
    
    m5_adx = df_m5.iloc[-1].get('adx', 0)
    m5_atr = df_m5.iloc[-1].get('atr', 0)
    
    current_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"
    h1_trend = "BULLISH" if df_h1.iloc[-1]['close'] > df_h1.iloc[-1]['ema200'] else "BEARISH"
    
    # Check H1 Trend Filter
    use_h1_trend = config['parameters'].get('use_h1_trend', True)
    if use_h1_trend and current_trend != h1_trend:
         print(f"   ❌ Filtered: Trend Mismatch (M5: {current_trend} vs H1: {h1_trend})")
         return error_count, 0

    # ATR Filter
    if m5_atr < atr_threshold:
        print(f"   ❌ Filtered: Low Volatility (ATR {m5_atr:.5f} < {atr_threshold})")
        return error_count, 0
    
    # ADX filter: Only trade if trend is strong (ADX >= threshold)
    if pd.isna(m5_adx) or m5_adx < adx_threshold:
        print(f"   ❌ Filtered: M5 ADX {m5_adx:.1f} < {adx_threshold} (Weak Trend)")
        return error_count, 0

    # Channel: 55 SMA High/Low on M1
    df_m1['sma55_high'] = df_m1['high'].rolling(window=55).mean()
    df_m1['sma55_low'] = df_m1['low'].rolling(window=55).mean()
    
    # Volume MA for confirmation
    df_m1['vol_ma'] = df_m1['tick_volume'].rolling(window=20).mean()
    
    # Heiken Ashi
    ha_df = calculate_heiken_ashi(df_m1)
    
    # RSI 14 (Added Filter)
    ha_df['rsi'] = calculate_rsi(df_m1['close'], period=14)
    
    # RSI thresholds (configurable, default 55/45)
    rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 55)
    rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 45)

    last_ha = ha_df.iloc[-1]
    prev_ha = ha_df.iloc[-2]

    # 3. Check Signals
    signal = None
    price = mt5.symbol_info_tick(symbol).ask if current_trend == "BULLISH" else mt5.symbol_info_tick(symbol).bid
    
    # Detailed Logging
    print(f"📊 [Strat 1 Analysis] Price: {price:.2f} | Trend (M5): {current_trend} | ADX: {m5_adx:.1f} | RSI: {last_ha['rsi']:.1f}")
    print(f"   HA Close: {last_ha['ha_close']:.2f} | HA Open: {last_ha['ha_open']:.2f}")
    print(f"   SMA55 High: {last_ha['sma55_high']:.2f} | SMA55 Low: {last_ha['sma55_low']:.2f}")
    print(f"   Volume: {df_m1.iloc[-1]['tick_volume']:.0f} / MA: {df_m1.iloc[-1]['vol_ma']:.0f} = {df_m1.iloc[-1]['tick_volume']/df_m1.iloc[-1]['vol_ma']:.2f}x")
    
    # BUY SETUP
    if current_trend == "BULLISH":
        is_green = last_ha['ha_close'] > last_ha['ha_open']
        is_above_channel = last_ha['ha_close'] > last_ha['sma55_high']
        is_fresh_breakout = prev_ha['ha_close'] <= prev_ha['sma55_high']
        is_solid_candle = not is_doji(last_ha, threshold=0.2) # Require body > 20% of range for HA

        if is_green and is_above_channel:
            if is_fresh_breakout:
                if is_solid_candle:
                    # Volume confirmation
                    is_high_volume = df_m1.iloc[-1]['tick_volume'] > (df_m1.iloc[-1]['vol_ma'] * 1.3)
                    if not is_high_volume:
                        print(f"   ❌ Filtered: Volume {df_m1.iloc[-1]['tick_volume']:.0f} < 1.3x MA ({df_m1.iloc[-1]['vol_ma']:.0f})")
                    elif last_ha['rsi'] > rsi_buy_threshold:
                        signal = "BUY"
                    else:
                        print(f"   ❌ Filtered: Valid Buy Setup but RSI {last_ha['rsi']:.1f} <= {rsi_buy_threshold}")
                else: 
                     print(f"   ❌ Filtered: Doji Candle detected (Indecision)")
            else:
                print("   ❌ Condition Fail: Not a fresh breakout (Previous candle was already above).")
        else:
            print(f"   ❌ Condition Fail: Green? {is_green} | Above Channel? {is_above_channel}")

    # SELL SETUP
    elif current_trend == "BEARISH":
        is_red = last_ha['ha_close'] < last_ha['ha_open']
        is_below_channel = last_ha['ha_close'] < last_ha['sma55_low']
        is_fresh_breakout = prev_ha['ha_close'] >= prev_ha['sma55_low']
        is_solid_candle = not is_doji(last_ha, threshold=0.2)

        if is_red and is_below_channel:
            if is_fresh_breakout:
                if is_solid_candle:
                    # Volume confirmation
                    is_high_volume = df_m1.iloc[-1]['tick_volume'] > (df_m1.iloc[-1]['vol_ma'] * 1.3)
                    if not is_high_volume:
                        print(f"   ❌ Filtered: Volume {df_m1.iloc[-1]['tick_volume']:.0f} < 1.3x MA ({df_m1.iloc[-1]['vol_ma']:.0f})")
                    elif last_ha['rsi'] < rsi_sell_threshold:
                        signal = "SELL"
                    else:
                        print(f"   ❌ Filtered: Valid Sell Setup but RSI {last_ha['rsi']:.1f} >= {rsi_sell_threshold}")
                else:
                    print(f"   ❌ Filtered: Doji Candle detected (Indecision)")
            else:
                print("   ❌ Condition Fail: Not a fresh breakout (Previous candle was already below).")
        else:
            print(f"   ❌ Condition Fail: Red? {is_red} | Below Channel? {is_below_channel}")

    
    # 4. Execute Trade
    if signal:
        # --- CONSECUTIVE LOSS GUARD ---
        loss_guard_ok, loss_guard_msg = check_consecutive_losses(symbol, magic, config)
        if not loss_guard_ok:
            print(f"   ⏳ Consecutive Loss Guard: {loss_guard_msg}")
            return error_count, 0
        
        # --- SPAM FILTER: Check if we traded in the last 300 seconds (5 minutes) ---
        spam_filter_seconds = config['parameters'].get('spam_filter_seconds', 300)
        strat_positions = mt5.positions_get(symbol=symbol, magic=magic)
        if strat_positions:
            strat_positions = sorted(strat_positions, key=lambda x: x.time, reverse=True)
            last_trade_time = strat_positions[0].time
            current_server_time = mt5.symbol_info_tick(symbol).time
            
            if isinstance(last_trade_time, datetime):
                last_trade_timestamp = last_trade_time.timestamp()
            else:
                last_trade_timestamp = last_trade_time
            if isinstance(current_server_time, datetime):
                current_timestamp = current_server_time.timestamp()
            else:
                current_timestamp = current_server_time
            
            time_since_last = current_timestamp - last_trade_timestamp
            if time_since_last < spam_filter_seconds:
                print(f"   ⏳ Skipping: Trade already taken {time_since_last:.0f}s ago (Wait {spam_filter_seconds}s)")
                return error_count, 0

        print(f"🚀 SIGNAL FOUND: {signal} at {price}")
        
        # SL/TP Calculation Logic
        sl_mode = config['parameters'].get('sl_mode', 'fixed')
        reward_ratio = config['parameters'].get('reward_ratio', 1.5)
        
        sl = 0.0
        tp = 0.0
        
        if sl_mode == 'auto_m5':
            # Use previous M5 candle High/Low
            # df_m5 is already fetched. row -2 is the completed candle
            prev_m5_high = df_m5.iloc[-2]['high']
            prev_m5_low = df_m5.iloc[-2]['low']
            
            # Add a small buffer (e.g., 20000 points / $200) to avoid noise
            buffer = 20000 * mt5.symbol_info(symbol).point
            
            if signal == "BUY":
                sl = prev_m5_low - buffer
                # Check if SL is too close (safety) - min 50000 points
                min_dist = 50000 * mt5.symbol_info(symbol).point
                if (price - sl) < min_dist:
                    sl = price - min_dist
                    
                risk_dist = price - sl
                tp = price + (risk_dist * reward_ratio)
                
            elif signal == "SELL":
                sl = prev_m5_high + buffer
                # Check min dist
                min_dist = 50000 * mt5.symbol_info(symbol).point
                if (sl - price) < min_dist:
                    sl = price + min_dist
                    
                risk_dist = sl - price
                tp = price - (risk_dist * reward_ratio)
                
            print(f"   📏 Auto M5 SL: {sl:.2f} (Prev High/Low) | TP: {tp:.2f} (R:R {reward_ratio})")
            
        else:
            # Fixed Pips (Legacy)
            sl_pips = config['parameters']['sl_pips'] * mt5.symbol_info(symbol).point * 10 
            tp_pips = config['parameters']['tp_pips'] * mt5.symbol_info(symbol).point * 10
            
            sl = price - sl_pips if signal == "BUY" else price + sl_pips
            tp = price + tp_pips if signal == "BUY" else price - tp_pips
            
        # Log signal to DB
        db.log_signal("Strategy_1_Trend_HA", symbol, signal, price, sl, tp, 
                      {"trend": current_trend, "adx": float(m5_adx), "ha_close": float(last_ha['ha_close']), "sl_mode": sl_mode, "rsi": float(last_ha['rsi']), "volume_ratio": float(df_m1.iloc[-1]['tick_volume']/df_m1.iloc[-1]['vol_ma'])}, 
                      account_id=config['account'])

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
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(result.order, "Strategy_1_Trend_HA", symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
            
            # Detailed Telegram Message
            msg = (
                f"✅ <b>Strat 1: Trend HA Executed</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"👤 <b>Account:</b> {config['account']}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal})\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.2f} | 🎯 <b>TP:</b> {tp:.2f}\n"
                f"📊 <b>Indicators:</b>\n"
                f"• Trend: {current_trend} (ADX: {m5_adx:.1f})\n"
                f"• RSI: {last_ha['rsi']:.1f}\n"
                f"• Volume: {df_m1.iloc[-1]['tick_volume']:.0f} ({df_m1.iloc[-1]['tick_volume']/df_m1.iloc[-1]['vol_ma']:.2f}x avg)"
            )
            send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
            return 0, 0 # Reset error count
        else:
            print(f"❌ Order Failed: {result.retcode}")
            return error_count + 1, result.retcode
    
    return error_count, 0

if __name__ == "__main__":
    import os
    # Load separate config for this strategy
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_1.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 1: Trend HA - Started")
        try:
            while True:
                consecutive_errors, last_error_code = strategy_1_logic(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Strategy 1: Trend HA] WARNING: 5 Consecutive Order Failures. Last Error: {error_msg}. Pausing for 2 minutes..."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    time.sleep(120) # Pause for 2 minutes
                    consecutive_errors = 0 # Reset counter
                    print("▶️ Resuming...")
                    continue
                    
                time.sleep(1) # Scan every second
        except KeyboardInterrupt:
            print("🛑 Bot Stopped")
            mt5.shutdown()
