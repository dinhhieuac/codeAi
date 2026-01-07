import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd

# Import local modules
sys.path.append('..')
from db import Database
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message, calculate_rsi, calculate_adx, check_consecutive_losses

# Initialize Database
# Initialize Database
db = Database()

def strategy_2_logic(config, error_count=0):
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
            print(f"⚠️ Max Positions Reached for Strategy {magic}: {len(positions)}/{max_positions}")
            return error_count, 0

    # 1. Get Data
    df = get_data(symbol, mt5.TIMEFRAME_M1, 100)
    df_h1 = get_data(symbol, mt5.TIMEFRAME_H1, 100) # H1 Trend Filter
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 10)  # Added for Auto SL
    
    if df is None or df_h1 is None or df_m5 is None: return error_count, 0

    # --- SESSION FILTER ---
    session_start = config['parameters'].get('session_start_hour', 0)
    session_end = config['parameters'].get('session_end_hour', 24)
    current_hour = mt5.symbol_info_tick(symbol).time.hour
    
    # Check if current_hour is within start-end range
    is_in_session = False
    if session_start < session_end:
         is_in_session = session_start <= current_hour < session_end
    else: # Wrap around (e.g. 22 to 8)
         is_in_session = current_hour >= session_start or current_hour < session_end
    
    if not is_in_session:
         if current_hour % 4 == 0 and mt5.symbol_info_tick(symbol).time.minute == 0:
              print(f"   💤 Session Filter (Strat 2): Current hour {current_hour} not in {session_start}-{session_end}")
         return error_count, 0

    # H1 Trend
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    # H1 ADX for trend strength confirmation
    df_h1 = calculate_adx(df_h1, period=14)
    h1_adx_threshold = config['parameters'].get('h1_adx_threshold', 20)
    h1_adx = df_h1.iloc[-1].get('adx', 0)
    
    h1_trend = "BULLISH" if df_h1.iloc[-1]['close'] > df_h1.iloc[-1]['ema50'] else "BEARISH"
    
    # H1 ADX filter: Only trade if trend is strong
    if pd.isna(h1_adx) or h1_adx < h1_adx_threshold:
        print(f"   ❌ Filtered: H1 ADX {h1_adx:.1f} < {h1_adx_threshold} (Weak Trend)")
        return error_count, 0

    # 2. Indicators (M1)
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
    df['rsi'] = calculate_rsi(df['close'], period=14)
    
    # Volume MA for confirmation
    df['vol_ma'] = df['tick_volume'].rolling(window=20).mean()
    
    # RSI thresholds (configurable, default 55/45)
    rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 55)
    rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 45)
    
    # Crossover confirmation flag
    crossover_confirmation = config['parameters'].get('crossover_confirmation', True)
    
    if len(df) < 3:
        return error_count, 0
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev_prev = df.iloc[-3]
    
    # 3. Logic: Crossover + RSI Filter + H1 Trend
    signal = None
    
    print(f"📊 [Strat 2 Analysis] H1 Trend: {h1_trend} (ADX: {h1_adx:.1f}) | EMA14: {last['ema14']:.3f} | EMA28: {last['ema28']:.3f} | RSI: {last['rsi']:.1f}")
    print(f"   Volume: {last['tick_volume']:.0f} / MA: {last['vol_ma']:.0f} = {last['tick_volume']/last['vol_ma']:.2f}x")
    
    # BUY: EMA 14 crosses ABOVE EMA 28 AND RSI > threshold AND H1 Bullish
    has_crossover = False
    crossover_direction = None
    
    if crossover_confirmation:
        # Confirmation: Crossover happened 1-2 candles ago, confirm trend continues
        # Check if crossover happened at prev_prev -> prev, and trend continues at last
        if (prev_prev['ema14'] <= prev_prev['ema28'] and 
            prev['ema14'] > prev['ema28'] and 
            last['ema14'] > last['ema28']):  # Trend continues
            has_crossover = True
            crossover_direction = "BUY"
            print("   ✅ Crossover Confirmed: EMA 14 > EMA 28 (2 candles ago, trend continues)")
        # Also check immediate crossover if strong
        elif (prev['ema14'] <= prev['ema28'] and 
              last['ema14'] > last['ema28'] and
              last['ema14'] > prev['ema14']):  # EMA14 still rising
            has_crossover = True
            crossover_direction = "BUY"
            print("   ✅ Crossover: EMA 14 > EMA 28 (Immediate, EMA14 rising)")
    else:
        # Original logic (no confirmation)
        if prev['ema14'] <= prev['ema28'] and last['ema14'] > last['ema28']:
            has_crossover = True
            crossover_direction = "BUY"
            print("   ✅ Crossover: EMA 14 > EMA 28 (Bullish)")
    
    if has_crossover and crossover_direction == "BUY":
        if h1_trend == "BULLISH":
            # Extension Check
            extension_multiplier = config['parameters'].get('extension_multiplier', 1.5)
            if abs(last['close'] - last['ema14']) > (extension_multiplier * last['atr']):
                print(f"   ❌ Filtered: Price Extended (Dist: {abs(last['close'] - last['ema14']):.2f} > {extension_multiplier}xATR)")
            # Volume confirmation
            volume_multiplier = config['parameters'].get('volume_multiplier', 1.3)
            if last['tick_volume'] <= (last['vol_ma'] * volume_multiplier):
                print(f"   ❌ Filtered: Volume {last['tick_volume']:.0f} < {volume_multiplier}x MA ({last['vol_ma']:.0f})")
            # RSI threshold
            elif last['rsi'] > rsi_buy_threshold:
                # RSI momentum check
                if last['rsi'] > prev['rsi']:
                    signal = "BUY"
                    print(f"   ✅ All conditions met: Crossover + Volume + RSI {last['rsi']:.1f} > {rsi_buy_threshold} (rising)")
                else:
                    print(f"   ❌ Filtered: RSI not rising ({prev['rsi']:.1f} → {last['rsi']:.1f})")
            else:
                print(f"   ❌ Filtered: Crossover BUY but RSI {last['rsi']:.1f} <= {rsi_buy_threshold}")
        else:
             print(f"   ❌ Filtered: Crossover BUY but H1 Trend is BEARISH")
    
    # SELL: EMA 14 crosses BELOW EMA 28 AND RSI < threshold AND H1 Bearish
    if not has_crossover:
        if crossover_confirmation:
            # Confirmation: Crossover happened 1-2 candles ago, confirm trend continues
            if (prev_prev['ema14'] >= prev_prev['ema28'] and 
                prev['ema14'] < prev['ema28'] and 
                last['ema14'] < last['ema28']):  # Trend continues
                has_crossover = True
                crossover_direction = "SELL"
                print("   ✅ Crossover Confirmed: EMA 14 < EMA 28 (2 candles ago, trend continues)")
            # Also check immediate crossover if strong
            elif (prev['ema14'] >= prev['ema28'] and 
                  last['ema14'] < last['ema28'] and
                  last['ema14'] < prev['ema14']):  # EMA14 still falling
                has_crossover = True
                crossover_direction = "SELL"
                print("   ✅ Crossover: EMA 14 < EMA 28 (Immediate, EMA14 falling)")
        else:
            # Original logic
            if prev['ema14'] >= prev['ema28'] and last['ema14'] < last['ema28']:
                has_crossover = True
                crossover_direction = "SELL"
                print("   ✅ Crossover: EMA 14 < EMA 28 (Bearish)")
    
    if has_crossover and crossover_direction == "SELL":
        if h1_trend == "BEARISH":
            # Extension Check
            extension_multiplier = config['parameters'].get('extension_multiplier', 1.5)
            if abs(last['close'] - last['ema14']) > (extension_multiplier * last['atr']):
                print(f"   ❌ Filtered: Price Extended (Dist: {abs(last['close'] - last['ema14']):.2f} > {extension_multiplier}xATR)")
            # Volume confirmation
            volume_multiplier = config['parameters'].get('volume_multiplier', 1.3)
            if last['tick_volume'] <= (last['vol_ma'] * volume_multiplier):
                print(f"   ❌ Filtered: Volume {last['tick_volume']:.0f} < {volume_multiplier}x MA ({last['vol_ma']:.0f})")
            # RSI threshold
            elif last['rsi'] < rsi_sell_threshold:
                # RSI momentum check
                if last['rsi'] < prev['rsi']:
                    signal = "SELL"
                    print(f"   ✅ All conditions met: Crossover + Volume + RSI {last['rsi']:.1f} < {rsi_sell_threshold} (declining)")
                else:
                    print(f"   ❌ Filtered: RSI not declining ({prev['rsi']:.1f} → {last['rsi']:.1f})")
            else:
                print(f"   ❌ Filtered: Crossover SELL but RSI {last['rsi']:.1f} >= {rsi_sell_threshold}")
        else:
             print(f"   ❌ Filtered: Crossover SELL but H1 Trend is BULLISH")

    if not has_crossover:
        diff = last['ema14'] - last['ema28']
        if diff > 0:
            print(f"   ❌ No Cross (Already Bullish, Gap: {diff:.3f})")
        else:
            print(f"   ❌ No Cross (Already Bearish, Gap: {diff:.3f})")
        
    # 4. Execute
    if signal:
        # --- CONSECUTIVE LOSS GUARD ---
        loss_guard_ok, loss_guard_msg = check_consecutive_losses(symbol, magic, config)
        if not loss_guard_ok:
            print(f"   ⏳ Consecutive Loss Guard: {loss_guard_msg}")
            return error_count, 0
        
        # --- SPAM FILTER: Check if we traded in the last 5 minutes ---
        deals = mt5.history_deals_get(date_from=time.time() - 300, date_to=time.time())
        if deals:
             my_deals = [d for d in deals if d.magic == magic]
             if my_deals:
                 print(f"   ⏳ Cooldown: Last trade was < 5 mins ago. Skipping.")
                 return error_count, 0

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
            buffer = 20000 * mt5.symbol_info(symbol).point
            
            if signal == "BUY":
                sl = prev_m5_low - buffer
                min_dist = 50000 * mt5.symbol_info(symbol).point
                if (price - sl) < min_dist: sl = price - min_dist
                risk_dist = price - sl
                tp = price + (risk_dist * reward_ratio)
                
            elif signal == "SELL":
                sl = prev_m5_high + buffer
                min_dist = 50000 * mt5.symbol_info(symbol).point
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
                      {"ema14": float(last['ema14']), "ema28": float(last['ema28']), "atr": float(atr_val), "rsi": float(last['rsi']), 
                       "h1_adx": float(h1_adx), "volume_ratio": float(last['tick_volume']/last['vol_ma'])},
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
            "comment": "Strat2_EMA_ATR",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Success: {result.order}")
            db.log_order(result.order, "Strategy_2_EMA_ATR", symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
            
            msg = (
                f"✅ <b>Strat 2: EMA ATR Executed</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"👤 <b>Account:</b> {config['account']}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal})\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.2f} | 🎯 <b>TP:</b> {tp:.2f}\n"
                f"📊 <b>Indicators:</b>\n"
                f"• H1 Trend: {h1_trend} (ADX: {h1_adx:.1f})\n"
                f"• EMA14: {last['ema14']:.2f}\n"
                f"• EMA28: {last['ema28']:.2f}\n"
                f"• RSI: {last['rsi']:.1f}\n"
                f"• Volume: {last['tick_volume']:.0f} ({last['tick_volume']/last['vol_ma']:.2f}x avg)"
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
    config_path = os.path.join(script_dir, "configs", "config_2.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 2: EMA ATR - Started")
        try:
            while True:
                consecutive_errors, last_error_code = strategy_2_logic(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Strategy 2: EMA ATR] WARNING: 5 Consecutive Order Failures. Last Error: {error_msg}. Pausing for 2 minutes..."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    time.sleep(120)
                    consecutive_errors = 0
                    print("▶️ Resuming...")
                    continue
                    
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
