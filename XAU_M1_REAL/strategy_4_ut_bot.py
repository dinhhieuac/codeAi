import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd

# Import local modules
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, calculate_adx, manage_position, get_mt5_error_message, calculate_rsi
from datetime import datetime, timedelta

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
    # Trend Filter (H1 EMA50 + ADX)
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df_h1 = calculate_adx(df_h1, period=14)
    trend = "BULLISH" if df_h1.iloc[-1]['close'] > df_h1.iloc[-1]['ema50'] else "BEARISH"
    h1_adx = df_h1.iloc[-1].get('adx', 0)
    h1_adx_threshold = config['parameters'].get('h1_adx_threshold', 20)
    
    # RSI Calculation (M1)
    df_m1['rsi'] = calculate_rsi(df_m1['close'], period=14)
    
    # ADX Calculation (M1)
    df_m1 = calculate_adx(df_m1, period=14)
    
    # Volume MA for confirmation
    df_m1['vol_ma'] = df_m1['tick_volume'].rolling(window=20).mean()

    # UT Bot on M1
    sensitivity = config['parameters'].get('sensitivity', 2)
    period = config['parameters'].get('period', 10)
    df_ut = calculate_ut_bot(df_m1, sensitivity=sensitivity, period=period)
    
    if len(df_ut) < 3:
        return error_count, 0
    
    last = df_ut.iloc[-1]
    prev = df_ut.iloc[-2]
    prev2 = df_ut.iloc[-3] if len(df_ut) >= 3 else None
    
    # 3. Signals with Confirmation
    ut_signal = None
    ut_signal_confirmed = False
    
    # Check for crossover (Flip from -1 to 1 or 1 to -1)
    if prev['pos'] == -1 and last['pos'] == 1:
        ut_signal = "BUY"
        # Confirmation: Check if pos is still 1 (maintained)
        if last['pos'] == 1:
            ut_signal_confirmed = True
    elif prev['pos'] == 1 and last['pos'] == -1:
        ut_signal = "SELL"
        # Confirmation: Check if pos is still -1 (maintained)
        if last['pos'] == -1:
            ut_signal_confirmed = True
    
    signal = None
    
    print(f"\n{'='*80}")
    print(f"📊 [STRATEGY 4: UT BOT ANALYSIS] {symbol}")
    print(f"{'='*80}")
    print(f"💱 Price: {last['close']:.2f} | Trend H1: {trend} | UT Pos: {last['pos']} (Prev: {prev['pos']}) | RSI: {last['rsi']:.1f} | ADX: {last['adx']:.1f}")
    
    # Track all filter status
    filter_status = []
    
    # Get config parameters
    adx_threshold = config['parameters'].get('adx_threshold', 20)
    rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 55)  # Increased from 50
    rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 45)  # Decreased from 50
    volume_threshold = config['parameters'].get('volume_threshold', 1.3)  # Volume confirmation
    ut_confirmation = config['parameters'].get('ut_confirmation', True)  # Wait for confirmation
    
    # Filter: Only trade valid breakouts if ADX > threshold (Trend Strength)
    if pd.isna(last.get('adx', 0)) or last.get('adx', 0) < adx_threshold: 
        filter_status.append(f"❌ M1 ADX < {adx_threshold}: {last.get('adx', 0):.1f} (Choppy Market)")
        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - M1 ADX quá thấp")
    else:
        filter_status.append(f"✅ M1 ADX >= {adx_threshold}: {last.get('adx', 0):.1f}")
        
        if ut_signal == "BUY":
            filter_status.append(f"✅ UT Signal: BUY (Pos: {prev['pos']} → {last['pos']})")
            
            # UT Signal Confirmation
            if ut_confirmation:
                if ut_signal_confirmed:
                    filter_status.append(f"✅ UT Signal Confirmed: Pos maintained at {last['pos']}")
                else:
                    filter_status.append(f"❌ UT Signal Not Confirmed: Pos changed")
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - UT Signal không được xác nhận")
                    ut_signal = None  # Reset to skip further checks
            
            if ut_signal == "BUY":
                # H1 Trend + ADX Filter
                if trend == "BULLISH":
                    filter_status.append(f"✅ H1 Trend: BULLISH")
                    
                    if pd.notna(h1_adx) and h1_adx >= h1_adx_threshold:
                        filter_status.append(f"✅ H1 ADX: {h1_adx:.1f} >= {h1_adx_threshold}")
                    else:
                        filter_status.append(f"❌ H1 ADX: {h1_adx:.1f} < {h1_adx_threshold} (cần >= {h1_adx_threshold})")
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - H1 ADX không đạt")
                        ut_signal = None
                    
                    if ut_signal == "BUY":
                        # RSI Filter (stricter)
                        filter_status.append(f"{'✅' if last['rsi'] > rsi_buy_threshold else '❌'} RSI > {rsi_buy_threshold}: {last['rsi']:.1f}")
                        
                        if last['rsi'] > rsi_buy_threshold:
                            # Volume Confirmation
                            vol_ratio = last['tick_volume'] / last['vol_ma'] if last['vol_ma'] > 0 else 0
                            is_high_volume = last['tick_volume'] > (last['vol_ma'] * volume_threshold)
                            filter_status.append(f"{'✅' if is_high_volume else '❌'} Volume: {vol_ratio:.2f}x {'>' if is_high_volume else '<'} {volume_threshold}x")
                            
                            if is_high_volume:
                                signal = "BUY"
                                print("\n✅ [SIGNAL FOUND] BUY - Tất cả điều kiện đạt!")
                            else:
                                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Volume không đủ")
                        else:
                            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần > {rsi_buy_threshold})")
                else:
                    filter_status.append(f"❌ H1 Trend: BEARISH (cần BULLISH)")
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - H1 Trend không phù hợp")
                    
        elif ut_signal == "SELL":
            filter_status.append(f"✅ UT Signal: SELL (Pos: {prev['pos']} → {last['pos']})")
            
            # UT Signal Confirmation
            if ut_confirmation:
                if ut_signal_confirmed:
                    filter_status.append(f"✅ UT Signal Confirmed: Pos maintained at {last['pos']}")
                else:
                    filter_status.append(f"❌ UT Signal Not Confirmed: Pos changed")
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - UT Signal không được xác nhận")
                    ut_signal = None
            
            if ut_signal == "SELL":
                # H1 Trend + ADX Filter
                if trend == "BEARISH":
                    filter_status.append(f"✅ H1 Trend: BEARISH")
                    
                    if pd.notna(h1_adx) and h1_adx >= h1_adx_threshold:
                        filter_status.append(f"✅ H1 ADX: {h1_adx:.1f} >= {h1_adx_threshold}")
                    else:
                        filter_status.append(f"❌ H1 ADX: {h1_adx:.1f} < {h1_adx_threshold} (cần >= {h1_adx_threshold})")
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - H1 ADX không đạt")
                        ut_signal = None
                    
                    if ut_signal == "SELL":
                        # RSI Filter (stricter)
                        filter_status.append(f"{'✅' if last['rsi'] < rsi_sell_threshold else '❌'} RSI < {rsi_sell_threshold}: {last['rsi']:.1f}")
                        
                        if last['rsi'] < rsi_sell_threshold:
                            # Volume Confirmation
                            vol_ratio = last['tick_volume'] / last['vol_ma'] if last['vol_ma'] > 0 else 0
                            is_high_volume = last['tick_volume'] > (last['vol_ma'] * volume_threshold)
                            filter_status.append(f"{'✅' if is_high_volume else '❌'} Volume: {vol_ratio:.2f}x {'>' if is_high_volume else '<'} {volume_threshold}x")
                            
                            if is_high_volume:
                                signal = "SELL"
                                print("\n✅ [SIGNAL FOUND] SELL - Tất cả điều kiện đạt!")
                            else:
                                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Volume không đủ")
                        else:
                            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần < {rsi_sell_threshold})")
                else:
                    filter_status.append(f"❌ H1 Trend: BULLISH (cần BEARISH)")
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - H1 Trend không phù hợp")
        else:
            filter_status.append(f"❌ No UT Signal: Pos unchanged ({prev['pos']} → {last['pos']})")
            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Không có UT Signal")
    
    # Final Summary
    if not signal:
        print(f"\n{'─'*80}")
        print(f"❌ [KHÔNG CÓ TÍN HIỆU] - Tóm tắt các bộ lọc:")
        print(f"{'─'*80}")
        for i, status in enumerate(filter_status, 1):
            print(f"   {i}. {status}")
        
        # Chi tiết giá trị
        print(f"\n📊 [CHI TIẾT GIÁ TRỊ]")
        print(f"   💱 Price: {last['close']:.2f}")
        print(f"   📈 H1 Trend: {trend}")
        print(f"   📊 H1 ADX: {h1_adx:.1f} (cần >= {h1_adx_threshold})")
        print(f"   📊 UT Position: {last['pos']} (Prev: {prev['pos']})")
        print(f"   📊 M1 ADX: {last.get('adx', 0):.1f} (cần >= {adx_threshold})")
        print(f"   📊 RSI: {last['rsi']:.1f} (BUY cần > {rsi_buy_threshold}, SELL cần < {rsi_sell_threshold})")
        vol_ratio = last['tick_volume'] / last['vol_ma'] if last['vol_ma'] > 0 else 0
        print(f"   📊 Volume: {vol_ratio:.2f}x (cần > {volume_threshold}x)")
        print(f"   📊 UT Trailing Stop: {last.get('x_atr_trailing_stop', 0):.2f}")
        
        print(f"\n💡 Tổng số filters đã kiểm tra: {len(filter_status)}")
        print(f"   ✅ PASS: {len([f for f in filter_status if f.startswith('✅')])}")
        print(f"   ❌ FAIL: {len([f for f in filter_status if f.startswith('❌')])}")
        print(f"{'─'*80}\n")
            
    # 4. Execute
    if signal:
        # --- CONSECUTIVE LOSS GUARD ---
        loss_streak_threshold = config['parameters'].get('loss_streak_threshold', 2)
        loss_cooldown_minutes = config['parameters'].get('loss_cooldown_minutes', 45)
        
        try:
            from_timestamp = int((datetime.now() - timedelta(days=1)).timestamp())
            to_timestamp = int(datetime.now().timestamp())
            deals = mt5.history_deals_get(from_timestamp, to_timestamp)
            
            if deals:
                closed_deals = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT and d.magic == magic and d.profit != 0]
                closed_deals.sort(key=lambda x: x.time, reverse=True)
                
                loss_streak = 0
                for deal in closed_deals:
                    if deal.profit < 0:
                        loss_streak += 1
                    else:
                        break
                
                if loss_streak >= loss_streak_threshold:
                    if len(closed_deals) > 0:
                        last_deal_time = closed_deals[0].time
                        last_deal_timestamp = last_deal_time.timestamp() if isinstance(last_deal_time, datetime) else last_deal_time
                        minutes_since_last = (datetime.now().timestamp() - last_deal_timestamp) / 60
                        
                        if minutes_since_last < loss_cooldown_minutes:
                            remaining = loss_cooldown_minutes - minutes_since_last
                            print(f"   ⏳ Consecutive Loss Guard: {loss_streak} losses, {remaining:.1f} minutes remaining")
                            return error_count, 0
        except Exception as e:
            print(f"   ⚠️ Error checking consecutive losses: {e}")
        
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
                      {"trend": trend, "ut_pos": int(last['pos']), "rsi": float(last['rsi'])},
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
                f"• Trend: {trend}\n"
                f"• ADX: {last.get('adx', 0):.1f}\n"
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
