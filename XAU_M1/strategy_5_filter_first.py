import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd

# Import local modules
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message, calculate_rsi, calculate_adx

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
    m5_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"

    # Donchian Channel 40 (Breakout) - Tăng từ 20 để giảm false signal
    donchian_period = 40
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

    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 3. Logic: Donchian Breakout
    signal = None
    
    # BUY: Close > Upper Band + Buffer
    # SELL: Close < Lower Band - Buffer
    
    buffer = 50 * mt5.symbol_info(symbol).point  # 0.5 pips / 50 points
    
    # ATR Volatility Filter
    atr_value = last['atr'] if not pd.isna(last['atr']) else 0
    point = mt5.symbol_info(symbol).point
    # Với XAUUSD: ATR được tính bằng giá trị thực (USD)
    # Chuyển sang pips: ATR(pips) = ATR(price) / point / 10
    # Ví dụ: ATR = 1.057 USD, point = 0.01 → ATR(pips) = 1.057 / 0.01 / 10 = 10.57 pips
    # Nếu ATR = 105.7 points → ATR(pips) = 105.7 / 10 = 10.57 pips
    atr_pips = (atr_value / point) / 10 if point > 0 else 0
    # XAUUSD M1: ATR thường từ 10-150 pips (tùy volatility)
    # Threshold điều chỉnh để phù hợp với XAUUSD M1 scalping
    atr_min = 10   # Minimum ATR (pips) - tránh market quá yên tĩnh
    atr_max = 200  # Maximum ATR (pips) - tránh market quá biến động (news events)
    
    print(f"📊 [Strat 5 Analysis] Price: {last['close']:.2f} | M5 Trend: {m5_trend} | RSI: {last['rsi']:.1f} | ADX: {last.get('adx', 0):.1f} | ATR: {atr_pips:.1f}p")
    
    # ATR Volatility Filter
    if atr_pips < atr_min or atr_pips > atr_max:
        print(f"   ❌ Filtered: ATR {atr_pips:.1f}p không trong khoảng {atr_min}-{atr_max}p")
        return error_count, 0
    
    # ADX Filter (Trend Strength)
    adx_value = last.get('adx', 0)
    if pd.isna(adx_value) or adx_value < 20:
        print(f"   ❌ Filtered: ADX {adx_value:.1f} < 20 (Choppy Market)")
        return error_count, 0
    
    # Volume Confirmation
    is_high_volume = last['tick_volume'] > (last['vol_ma'] * 1.3)  # Volume > 1.3x average
    
    # False Breakout Check
    false_breakout = False
    if last['close'] > (last['upper'] + buffer):
        # BUY: Kiểm tra nến trước có phá vỡ nhưng đóng ngược lại không
        if prev['high'] > last['upper'] and prev['close'] < last['upper']:
            false_breakout = True
            print(f"   ❌ Filtered: False Breakout BUY (Nến trước phá vỡ nhưng đóng ngược lại)")
    elif last['close'] < (last['lower'] - buffer):
        # SELL: Kiểm tra nến trước có phá vỡ nhưng đóng ngược lại không
        if prev['low'] < last['lower'] and prev['close'] > last['lower']:
            false_breakout = True
            print(f"   ❌ Filtered: False Breakout SELL (Nến trước phá vỡ nhưng đóng ngược lại)")
    
    if false_breakout:
        return error_count, 0
    
    # BUY Signal
    if last['close'] > (last['upper'] + buffer):
        if m5_trend == "BULLISH":
            if last['rsi'] > 50:
                if is_high_volume:
                    signal = "BUY"
                    print("   ✅ Valid Breakout BUY (Volume confirmed)")
                else:
                    print(f"   ❌ Filtered: Breakout BUY but Volume {last['tick_volume']} < {int(last['vol_ma']*1.3)} (1.3x average)")
            else:
                print(f"   ❌ Filtered: Breakout BUY but RSI {last['rsi']:.1f} <= 50")
        else:
            print(f"   ❌ Filtered: Breakout BUY but M5 Trend is BEARISH")
             
    # SELL Signal
    elif last['close'] < (last['lower'] - buffer):
        if m5_trend == "BEARISH":
            if last['rsi'] < 50:
                if is_high_volume:
                    signal = "SELL"
                    print("   ✅ Valid Breakout SELL (Volume confirmed)")
                else:
                    print(f"   ❌ Filtered: Breakout SELL but Volume {last['tick_volume']} < {int(last['vol_ma']*1.3)} (1.3x average)")
            else:
                print(f"   ❌ Filtered: Breakout SELL but RSI {last['rsi']:.1f} >= 50")
        else:
            print(f"   ❌ Filtered: Breakout SELL but M5 Trend is BULLISH")
        
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
            min_dist = 100 * point  # 10 pips minimum
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
            buffer_sl = 20 * point
            
            if signal == "BUY":
                sl = prev_m5_low - buffer_sl
                min_dist = 100 * point
                if (price - sl) < min_dist: sl = price - min_dist
                risk_dist = price - sl
                tp = price + (risk_dist * reward_ratio)
                
            elif signal == "SELL":
                sl = prev_m5_high + buffer_sl
                min_dist = 100 * point
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
            "adx": float(adx_value),
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
                f"• RSI: {last['rsi']:.1f}\n"
                f"• ADX: {adx_value:.1f}\n"
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
