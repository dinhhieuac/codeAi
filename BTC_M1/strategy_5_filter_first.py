import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd

# Import local modules
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message, calculate_rsi, calculate_adx, check_consecutive_losses

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
    df_m5['ema200'] = df_m5['close'].ewm(span=200, adjust=False).mean()  # Sửa thành EMA thực sự
    # M5 ADX for trend strength confirmation
    df_m5 = calculate_adx(df_m5, period=14)
    m5_adx_threshold = config['parameters'].get('m5_adx_threshold', 20)
    m5_adx = df_m5.iloc[-1].get('adx', 0)
    
    m5_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"
    
    # M5 ADX filter: Only trade if trend is strong
    if pd.isna(m5_adx) or m5_adx < m5_adx_threshold:
        print(f"   ❌ Filtered: M5 ADX {m5_adx:.1f} < {m5_adx_threshold} (Weak Trend)")
        return error_count, 0

    # Donchian Channel (configurable, default 50)
    donchian_period = config['parameters'].get('donchian_period', 50)
    df['upper'] = df['high'].rolling(window=donchian_period).max().shift(1)  # Previous 40 highs
    df['lower'] = df['low'].rolling(window=donchian_period).min().shift(1)   # Previous 40 lows
    
    # ATR 14 (for dynamic SL/TP and volatility filter)
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    # ADX 14 (Trend Strength Filter)
    df = calculate_adx(df, period=14)
    
    # RSI 14 (Added Filter)
    df['rsi'] = calculate_rsi(df['close'], period=14)
    
    # Volume MA (for volume confirmation)
    df['vol_ma'] = df['tick_volume'].rolling(window=20).mean()
    
    # RSI thresholds (configurable, default 55/45)
    rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 55)
    rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 45)
    
    # Volume threshold (configurable, default 1.5x)
    volume_threshold = config['parameters'].get('volume_threshold', 1.5)
    
    # Breakout confirmation flag
    breakout_confirmation = config['parameters'].get('breakout_confirmation', True)
    
    # Buffer multiplier (configurable, default 100 = 5000 points for BTC)
    buffer_multiplier = config['parameters'].get('buffer_multiplier', 100)
    buffer = buffer_multiplier * mt5.symbol_info(symbol).point

    if len(df) < 3:
        return error_count, 0
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev_prev = df.iloc[-3]
    
    # 3. Logic: Donchian Breakout
    signal = None
    
    # ATR Volatility Filter
    atr_value = last['atr'] if not pd.isna(last['atr']) else 0
    point = mt5.symbol_info(symbol).point
    # Với XAUUSD: ATR được tính bằng giá trị thực (USD)
    # Chuyển sang pips: ATR(pips) = ATR(price) / point / 10
    # Ví dụ: ATR = 1.057 USD, point = 0.01 → ATR(pips) = 1.057 / 0.01 / 10 = 10.57 pips
    # Nếu ATR = 105.7 points → ATR(pips) = 105.7 / 10 = 10.57 pips
    atr_pips = (atr_value / point) / 10 if point > 0 else 0
    # Dynamic ATR Range from Config
    atr_min = config['parameters'].get('atr_min_pips', 100)
    atr_max = config['parameters'].get('atr_max_pips', 20000)
    
    print(f"📊 [Strat 5 Analysis] Price: {last['close']:.2f} | M5 Trend: {m5_trend} (ADX: {m5_adx:.1f}) | RSI: {last['rsi']:.1f} | M1 ADX: {last.get('adx', 0):.1f} | ATR: {atr_pips:.1f}p")
    print(f"   Donchian: {donchian_period} periods | Buffer: {buffer_multiplier} points | Volume: {last['tick_volume']:.0f} / MA: {last['vol_ma']:.0f} = {last['tick_volume']/last['vol_ma']:.2f}x")
    
    # ATR Volatility Filter
    if atr_pips < atr_min or atr_pips > atr_max:
        print(f"   ❌ Filtered: ATR {atr_pips:.1f}p không trong khoảng {atr_min}-{atr_max}p")
        return error_count, 0
    
    # ADX Filter (Trend Strength)
    adx_value = last.get('adx', 0)
    if pd.isna(adx_value) or adx_value < 25:
        print(f"   ❌ Filtered: ADX {adx_value:.1f} < 25 (Choppy Market)")
        return error_count, 0
    
    # Volume Confirmation
    is_high_volume = last['tick_volume'] > (last['vol_ma'] * volume_threshold)
    
    # Breakout Detection with Confirmation
    has_breakout = False
    breakout_direction = None
    
    if breakout_confirmation:
        # Confirmed Breakout: Breakout happened 1-2 candles ago, confirm continues
        # BUY: prev_prev broke upper, prev still above, last still above
        if (prev_prev['close'] > (last['upper'] + buffer) and
            prev['close'] > (last['upper'] + buffer) and
            last['close'] > (last['upper'] + buffer)):
            has_breakout = True
            breakout_direction = "BUY"
            print("   ✅ Breakout Confirmed: BUY (2 candles above upper, continues)")
        # SELL: prev_prev broke lower, prev still below, last still below
        elif (prev_prev['close'] < (last['lower'] - buffer) and
              prev['close'] < (last['lower'] - buffer) and
              last['close'] < (last['lower'] - buffer)):
            has_breakout = True
            breakout_direction = "SELL"
            print("   ✅ Breakout Confirmed: SELL (2 candles below lower, continues)")
        # Strong immediate breakout (1.5x buffer)
        elif last['close'] > (last['upper'] + buffer * 1.5):
            has_breakout = True
            breakout_direction = "BUY"
            print("   ✅ Strong Breakout: BUY (1.5x buffer)")
        elif last['close'] < (last['lower'] - buffer * 1.5):
            has_breakout = True
            breakout_direction = "SELL"
            print("   ✅ Strong Breakout: SELL (1.5x buffer)")
    else:
        # Original logic (no confirmation)
        if last['close'] > (last['upper'] + buffer):
            has_breakout = True
            breakout_direction = "BUY"
        elif last['close'] < (last['lower'] - buffer):
            has_breakout = True
            breakout_direction = "SELL"
    
    # False Breakout Check
    false_breakout = False
    if has_breakout and breakout_direction == "BUY":
        # BUY: Kiểm tra nến trước có phá vỡ nhưng đóng ngược lại không
        if prev['high'] > last['upper'] and prev['close'] < last['upper']:
            false_breakout = True
            print(f"   ❌ Filtered: False Breakout BUY (Nến trước phá vỡ nhưng đóng ngược lại)")
    elif has_breakout and breakout_direction == "SELL":
        # SELL: Kiểm tra nến trước có phá vỡ nhưng đóng ngược lại không
        if prev['low'] < last['lower'] and prev['close'] > last['lower']:
            false_breakout = True
            print(f"   ❌ Filtered: False Breakout SELL (Nến trước phá vỡ nhưng đóng ngược lại)")
    
    if false_breakout:
        return error_count, 0
    
    # BUY Signal
    if has_breakout and breakout_direction == "BUY":
        if m5_trend == "BULLISH":
            if last['rsi'] > rsi_buy_threshold:
                # RSI momentum check
                if last['rsi'] > prev['rsi']:
                    if is_high_volume:
                        signal = "BUY"
                        print(f"   ✅ All conditions met: Breakout + Volume + RSI {last['rsi']:.1f} > {rsi_buy_threshold} (rising)")
                    else:
                        print(f"   ❌ Filtered: Breakout BUY but Volume {last['tick_volume']} < {int(last['vol_ma']*volume_threshold)} ({volume_threshold}x average)")
                else:
                    print(f"   ❌ Filtered: RSI not rising ({prev['rsi']:.1f} → {last['rsi']:.1f})")
            else:
                print(f"   ❌ Filtered: Breakout BUY but RSI {last['rsi']:.1f} <= {rsi_buy_threshold}")
        else:
            print(f"   ❌ Filtered: Breakout BUY but M5 Trend is BEARISH")
             
    # SELL Signal
    elif has_breakout and breakout_direction == "SELL":
        if m5_trend == "BEARISH":
            if last['rsi'] < rsi_sell_threshold:
                # RSI momentum check
                if last['rsi'] < prev['rsi']:
                    if is_high_volume:
                        signal = "SELL"
                        print(f"   ✅ All conditions met: Breakout + Volume + RSI {last['rsi']:.1f} < {rsi_sell_threshold} (declining)")
                    else:
                        print(f"   ❌ Filtered: Breakout SELL but Volume {last['tick_volume']} < {int(last['vol_ma']*volume_threshold)} ({volume_threshold}x average)")
                else:
                    print(f"   ❌ Filtered: RSI not declining ({prev['rsi']:.1f} → {last['rsi']:.1f})")
            else:
                print(f"   ❌ Filtered: Breakout SELL but RSI {last['rsi']:.1f} >= {rsi_sell_threshold}")
        else:
            print(f"   ❌ Filtered: Breakout SELL but M5 Trend is BULLISH")
    
    if not has_breakout:
        print(f"   ❌ No Breakout: Close {last['close']:.2f} (Upper: {last['upper']:.2f}, Lower: {last['lower']:.2f}, Buffer: {buffer:.2f})")
        
    if signal:
        # --- CONSECUTIVE LOSS GUARD ---
        loss_guard_ok, loss_guard_msg = check_consecutive_losses(symbol, magic, config)
        if not loss_guard_ok:
            print(f"   ⏳ Consecutive Loss Guard: {loss_guard_msg}")
            return error_count, 0
        
        # --- SPAM FILTER & COOLDOWN ---
        deals = mt5.history_deals_get(date_from=time.time() - 300, date_to=time.time())
        if deals:
            my_deals = [d for d in deals if d.magic == magic]
            if my_deals:
                print(f"   ⏳ Cooldown: Last trade was < 5 mins ago. Skipping.")
                return error_count, 0

        price = mt5.symbol_info_tick(symbol).ask if signal == "BUY" else mt5.symbol_info_tick(symbol).bid
        
        # --- SL/TP Logic based on Config ---
        sl_mode = config['parameters'].get('sl_mode', 'atr')  # Default to ATR
        reward_ratio = config['parameters'].get('reward_ratio', 1.5)
        
        sl = 0.0
        tp = 0.0
        
        if sl_mode == 'atr':
            # ATR-based SL/TP (Dynamic)
            sl_multiplier = config['parameters'].get('sl_atr_multiplier', 2.0)
            tp_multiplier = config['parameters'].get('tp_atr_multiplier', 3.0)
            
            sl_dist = atr_value * sl_multiplier
            tp_dist = atr_value * tp_multiplier
            
            if signal == "BUY":
                sl = price - sl_dist
                tp = price + tp_dist
            else:  # SELL
                sl = price + sl_dist
                tp = price - tp_dist
            
            # Minimum distance check
            min_dist = 5000 * point  # $50 minimum
            if signal == "BUY":
                if (price - sl) < min_dist:
                    sl = price - min_dist
                    risk_dist = price - sl
                    tp = price + (risk_dist * reward_ratio)
            else:
                if (sl - price) < min_dist:
                    sl = price + min_dist
                    risk_dist = sl - price
                    tp = price - (risk_dist * reward_ratio)
            
            print(f"   📏 ATR SL: {sl:.2f} ({sl_multiplier}xATR) | TP: {tp:.2f} ({tp_multiplier}xATR, R:R {reward_ratio})")
            
        elif sl_mode == 'auto_m5':
            # Use fetched M5 data
            prev_m5_high = df_m5.iloc[-2]['high']
            prev_m5_low = df_m5.iloc[-2]['low']
            buffer_sl = 20000 * point
            
            if signal == "BUY":
                sl = prev_m5_low - buffer_sl
                min_dist = 50000 * point
                if (price - sl) < min_dist: sl = price - min_dist
                risk_dist = price - sl
                tp = price + (risk_dist * reward_ratio)
                
            elif signal == "SELL":
                sl = prev_m5_high + buffer_sl
                min_dist = 50000 * point
                if (sl - price) < min_dist: sl = price + min_dist
                risk_dist = sl - price
                tp = price - (risk_dist * reward_ratio)
            print(f"   📏 Auto M5 SL: {sl:.2f} | TP: {tp:.2f} (R:R {reward_ratio})")
        else:
            # Fixed SL/TP (Legacy)
            sl = price - 2.0 if signal == "BUY" else price + 2.0
            tp = price + 5.0 if signal == "BUY" else price - 5.0
            print(f"   📏 Fixed SL: {sl:.2f} | TP: {tp:.2f}")

        print(f"🚀 Strat 5 SIGNAL: {signal} @ {price}")
        
        db.log_signal("Strategy_5_Filter_First", symbol, signal, price, sl, tp, {
            "setup": "Donchian Breakout",
            "rsi": float(last['rsi']),
            "m5_adx": float(m5_adx),
            "m1_adx": float(adx_value),
            "atr": float(atr_value),
            "atr_pips": float(atr_pips),
            "volume": int(last['tick_volume']),
            "vol_ratio": float(last['tick_volume'] / last['vol_ma']) if last['vol_ma'] > 0 else 0,
            "trend": m5_trend,
            "donchian_period": donchian_period
        }, account_id=config['account'])

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
                f"• Donchian Breakout ({donchian_period} periods)\n"
                f"• M5 Trend: {m5_trend} (ADX: {m5_adx:.1f})\n"
                f"• RSI: {last['rsi']:.1f}\n"
                f"• M1 ADX: {adx_value:.1f}\n"
                f"• ATR: {atr_pips:.1f} pips\n"
                f"• Volume: {int(last['tick_volume'])} ({last['tick_volume']/last['vol_ma']:.1f}x avg)"
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
