import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd

# Import local modules
sys.path.append('..')
from db import Database
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, calculate_adx, manage_position, get_mt5_error_message, calculate_rsi, check_consecutive_losses

# Initialize Database
db = Database()

def calculate_ut_bot(df, sensitivity=2, period=10):
    # ... (Keep existing implementation)
    """
    Approximate UT Bot Logic:
    ATR Trailing Stop logic basically.
    """
    df['atr'] = df['high'].combine(df['close'].shift(1), max) - df['low'].combine(df['close'].shift(1), min)
    df['atr'] = df['atr'].rolling(window=period).mean()
    df['n_loss'] = sensitivity * df['atr']
    
    # Initialize Stop Logic columns
    df['x_atr_trailing_stop'] = 0.0
    df['pos'] = 0 # 1 for Buy, -1 for Sell
    
    for i in range(1, len(df)):
        # Calculate trailing stop
        if df.at[i, 'close'] > df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] > df.at[i-1, 'x_atr_trailing_stop']:
            df.at[i, 'x_atr_trailing_stop'] = max(df.at[i-1, 'x_atr_trailing_stop'], df.at[i, 'close'] - df.at[i, 'n_loss'])
        elif df.at[i, 'close'] < df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] < df.at[i-1, 'x_atr_trailing_stop']:
            df.at[i, 'x_atr_trailing_stop'] = min(df.at[i-1, 'x_atr_trailing_stop'], df.at[i, 'close'] + df.at[i, 'n_loss'])
        elif df.at[i, 'close'] > df.at[i-1, 'x_atr_trailing_stop']:
            df.at[i, 'x_atr_trailing_stop'] = df.at[i, 'close'] - df.at[i, 'n_loss']
        else:
            df.at[i, 'x_atr_trailing_stop'] = df.at[i, 'close'] + df.at[i, 'n_loss']
            
        # Determine Position
        prev_pos = df.at[i-1, 'pos']
        if df.at[i, 'close'] > df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] < df.at[i-1, 'x_atr_trailing_stop']:
             df.at[i, 'pos'] = 1 # BUY Signal transition
        elif df.at[i, 'close'] < df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] > df.at[i-1, 'x_atr_trailing_stop']:
             df.at[i, 'pos'] = -1 # SELL Signal transition
        else:
             df.at[i, 'pos'] = prev_pos if prev_pos != 0 else (1 if df.at[i, 'close'] > df.at[i, 'x_atr_trailing_stop'] else -1)

    return df

def strategy_4_logic(config, error_count=0):
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
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 200)
    df_h1 = get_data(symbol, mt5.TIMEFRAME_H1, 50) # Trend Filter
    
    if df_m1 is None or df_h1 is None: return error_count, 0

    # 2. Indicators
    # Trend Filter (H1 EMA50)
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    # H1 ADX for trend strength confirmation
    df_h1 = calculate_adx(df_h1, period=14)
    h1_adx_threshold = config['parameters'].get('h1_adx_threshold', 20)
    h1_adx = df_h1.iloc[-1].get('adx', 0)
    
    trend = "BULLISH" if df_h1.iloc[-1]['close'] > df_h1.iloc[-1]['ema50'] else "BEARISH"
    
    # H1 ADX filter: Only trade if trend is strong
    if pd.isna(h1_adx) or h1_adx < h1_adx_threshold:
        print(f"   ❌ Filtered: H1 ADX {h1_adx:.1f} < {h1_adx_threshold} (Weak Trend)")
        return error_count, 0
    
    # RSI Calculation (M1)
    df_m1['rsi'] = calculate_rsi(df_m1['close'], period=14)
    
    # Volume MA for confirmation
    df_m1['vol_ma'] = df_m1['tick_volume'].rolling(window=20).mean()
    
    # ADX Calculation (M1)
    df_m1 = calculate_adx(df_m1)
    
    # RSI thresholds (configurable, default 55/45)
    rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 55)
    rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 45)
    
    # UT confirmation flag
    ut_confirmation = config['parameters'].get('ut_confirmation', True)

    # UT Bot on M1
    df_ut = calculate_ut_bot(df_m1, sensitivity=2, period=10)
    
    if len(df_ut) < 3:
        return error_count, 0
    
    last = df_ut.iloc[-1]
    prev = df_ut.iloc[-2]
    prev_prev = df_ut.iloc[-3]
    
    # 3. Signals
    ut_signal = None
    has_ut_signal = False
    
    # UT Signal with confirmation
    if ut_confirmation:
        # Confirmed UT Signal: Flip happened 1-2 candles ago, confirm position continues
        # BUY: prev_prev was SELL, prev flipped to BUY, last still BUY
        if (prev_prev['pos'] == -1 and 
            prev['pos'] == 1 and 
            last['pos'] == 1):  # Still in BUY
            has_ut_signal = True
            ut_signal = "BUY"
            print("   ✅ UT Signal Confirmed: BUY (2 candles ago, position continues)")
        # SELL: prev_prev was BUY, prev flipped to SELL, last still SELL
        elif (prev_prev['pos'] == 1 and 
              prev['pos'] == -1 and 
              last['pos'] == -1):  # Still in SELL
            has_ut_signal = True
            ut_signal = "SELL"
            print("   ✅ UT Signal Confirmed: SELL (2 candles ago, position continues)")
        # Also check immediate flip if strong
        elif (prev['pos'] == -1 and last['pos'] == 1):
            # Immediate BUY flip, check if it's strong
            if last['close'] > prev['close']:  # Price rising
                has_ut_signal = True
                ut_signal = "BUY"
                print("   ✅ UT Signal: BUY (Immediate flip, price rising)")
        elif (prev['pos'] == 1 and last['pos'] == -1):
            # Immediate SELL flip, check if it's strong
            if last['close'] < prev['close']:  # Price falling
                has_ut_signal = True
                ut_signal = "SELL"
                print("   ✅ UT Signal: SELL (Immediate flip, price falling)")
    else:
        # Original logic (no confirmation)
        if prev['pos'] == -1 and last['pos'] == 1:
            has_ut_signal = True
            ut_signal = "BUY"
            print("   ✅ UT Signal: BUY")
        elif prev['pos'] == 1 and last['pos'] == -1:
            has_ut_signal = True
            ut_signal = "SELL"
            print("   ✅ UT Signal: SELL")
    
    signal = None
    
    print(f"📊 [Strat 4 Analysis] Trend H1: {trend} (ADX: {h1_adx:.1f}) | UT Pos: {last['pos']} | RSI: {last['rsi']:.1f} | M1 ADX: {last['adx']:.1f}")
    print(f"   Volume: {df_m1.iloc[-1]['tick_volume']:.0f} / MA: {df_m1.iloc[-1]['vol_ma']:.0f} = {df_m1.iloc[-1]['tick_volume']/df_m1.iloc[-1]['vol_ma']:.2f}x")
    
    # Filter: Only trade valid breakouts if ADX > 25 (Trend Strength)
    if last['adx'] < 25: 
        print(f"   ❌ Filtered: Low M1 ADX ({last['adx']:.1f} < 25) - Choppy Market")
    elif has_ut_signal and ut_signal == "BUY" and trend == "BULLISH":
        # Volume confirmation
        if df_m1.iloc[-1]['tick_volume'] <= (df_m1.iloc[-1]['vol_ma'] * 1.3):
            print(f"   ❌ Filtered: Volume {df_m1.iloc[-1]['tick_volume']:.0f} < 1.3x MA ({df_m1.iloc[-1]['vol_ma']:.0f})")
        elif last['rsi'] > rsi_buy_threshold:
            # RSI momentum check
            if last['rsi'] > prev['rsi']:
                signal = "BUY"
                print(f"   ✅ All conditions met: UT Signal + Volume + RSI {last['rsi']:.1f} > {rsi_buy_threshold} (rising)")
            else:
                print(f"   ❌ Filtered: RSI not rising ({prev['rsi']:.1f} → {last['rsi']:.1f})")
        else:
            print(f"   ❌ Filtered: Buy Signal but RSI {last['rsi']:.1f} <= {rsi_buy_threshold}")
            
    elif has_ut_signal and ut_signal == "SELL" and trend == "BEARISH":
        # Volume confirmation
        if df_m1.iloc[-1]['tick_volume'] <= (df_m1.iloc[-1]['vol_ma'] * 1.3):
            print(f"   ❌ Filtered: Volume {df_m1.iloc[-1]['tick_volume']:.0f} < 1.3x MA ({df_m1.iloc[-1]['vol_ma']:.0f})")
        elif last['rsi'] < rsi_sell_threshold:
            # RSI momentum check
            if last['rsi'] < prev['rsi']:
                signal = "SELL"
                print(f"   ✅ All conditions met: UT Signal + Volume + RSI {last['rsi']:.1f} < {rsi_sell_threshold} (declining)")
            else:
                print(f"   ❌ Filtered: RSI not declining ({prev['rsi']:.1f} → {last['rsi']:.1f})")
        else:
            print(f"   ❌ Filtered: Sell Signal but RSI {last['rsi']:.1f} >= {rsi_sell_threshold}")
    
    if not has_ut_signal:
        print(f"   ❌ No UT Signal: Prev Pos: {prev['pos']}, Last Pos: {last['pos']}")
            
    # 4. Execute
    if signal:
        # --- CONSECUTIVE LOSS GUARD ---
        loss_guard_ok, loss_guard_msg = check_consecutive_losses(symbol, magic, config)
        if not loss_guard_ok:
            print(f"   ⏳ Consecutive Loss Guard: {loss_guard_msg}")
            return error_count, 0
        
        # --- SPAM FILTER: Check Cooldown (5 Mins) ---
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
            # Fetch M5 explicitly here since this Strat uses H1 and M1
            df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 10)
            if df_m5 is not None:
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
                print(f"   📏 Auto M5 SL: {sl:.2f} | TP: {tp:.2f}")
            else:
                 # Fallback if no M5 data
                 sl = price - 2.0 if signal == "BUY" else price + 2.0
                 tp = price + 3.0 if signal == "BUY" else price - 3.0

        else:
            # Fixed 20/30 pips approx (2.0/3.0) for UT Bot default
            sl = price - 2.0 if signal == "BUY" else price + 2.0
            tp = price + 3.0 if signal == "BUY" else price - 3.0
            print(f"   📏 Fixed SL: {sl:.2f} | TP: {tp:.2f}")

        print(f"🚀 Strat 4 SIGNAL: {signal} @ {price}")
        db.log_signal("Strategy_4_UT_Bot", symbol, signal, price, sl, tp, 
                      {"trend": trend, "h1_adx": float(h1_adx), "ut_pos": int(last['pos']), "rsi": float(last['rsi']), "volume_ratio": float(df_m1.iloc[-1]['tick_volume']/df_m1.iloc[-1]['vol_ma'])},
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
            "comment": "Strat4_UT_Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Success: {result.order}")
            db.log_order(result.order, "Strategy_4_UT_Bot", symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
            
            msg = (
                f"✅ <b>Strat 4: UT Bot Executed</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"👤 <b>Account:</b> {config['account']}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal})\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.2f} | 🎯 <b>TP:</b> {tp:.2f}\n"
                f"📊 <b>Indicators:</b>\n"
                f"• H1 Trend: {trend} (ADX: {h1_adx:.1f})\n"
                f"• M1 ADX: {last.get('adx', 0):.1f}\n"
                f"• RSI: {last['rsi']:.1f}\n"
                f"• Volume: {df_m1.iloc[-1]['tick_volume']:.0f} ({df_m1.iloc[-1]['tick_volume']/df_m1.iloc[-1]['vol_ma']:.2f}x avg)"
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
    config_path = os.path.join(script_dir, "configs", "config_4.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 4: UT Bot - Started")
        try:
            while True:
                consecutive_errors, last_error_code = strategy_4_logic(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Strategy 4: UT Bot] WARNING: 5 Consecutive Order Failures. Last Error: {error_msg}. Pausing for 2 minutes..."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    time.sleep(120)
                    consecutive_errors = 0
                    print("▶️ Resuming...")
                    continue
                    
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
