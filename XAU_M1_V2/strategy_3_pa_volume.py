import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd

# Import local modules
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message, calculate_rsi

# Initialize Database
db = Database()

def strategy_3_logic(config, error_count=0):
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
    df = get_data(symbol, mt5.TIMEFRAME_M1, 50)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 200)  # For Trend Filter
    if df is None or df_m5 is None: return error_count, 0

    # 2. Indicators
    # Trend Filter (M5 EMA 200)
    df_m5['ema200'] = df_m5['close'].ewm(span=200, adjust=False).mean()
    m5_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"
    
    # SMA 9
    df['sma9'] = df['close'].rolling(window=9).mean()
    
    # Volume MA (to detect spikes)
    df['vol_ma'] = df['tick_volume'].rolling(window=20).mean()
    
    # ATR 14 (for volatility filter)
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

    last = df.iloc[-1]
    
    # Spread Filter
    tick = mt5.symbol_info_tick(symbol)
    point = mt5.symbol_info(symbol).point
    spread = (tick.ask - tick.bid) / point
    spread_pips = spread / 10
    max_spread = 50  # 5 pips max for XAUUSD (adjusted from 30/3 pips)
    
    # 3. Logic: Rejection Candle + Volume Spike near SMA 9
    signal = None
    early_exit_filters = []
    
    # Spread Filter
    if spread_pips > max_spread:
        early_exit_filters.append(f"❌ Spread: {spread_pips:.1f} pips > {max_spread} pips (Too high)")
        print(f"\n{'='*80}")
        print(f"❌ [KHÔNG CÓ TÍN HIỆU] - Early Exit Filter")
        print(f"{'='*80}")
        print(f"   {early_exit_filters[0]}")
        print(f"{'='*80}\n")
        return error_count, 0
    else:
        early_exit_filters.append(f"✅ Spread: {spread_pips:.1f} pips <= {max_spread} pips")
    
    # ATR Volatility Filter
    atr_value = last['atr'] if not pd.isna(last['atr']) else 0
    atr_pips = (atr_value / point) / 10 if point > 0 else 0
    # XAUUSD M1 typically has ATR 50-200 pips, so adjust range accordingly
    atr_min = 10   # Minimum ATR (pips) - Adjusted for XAUUSD
    atr_max = 200  # Maximum ATR (pips) - Adjusted for XAUUSD
    
    if atr_pips < atr_min or atr_pips > atr_max:
        early_exit_filters.append(f"❌ ATR: {atr_pips:.1f}p không trong khoảng {atr_min}-{atr_max}p")
        print(f"\n{'='*80}")
        print(f"❌ [KHÔNG CÓ TÍN HIỆU] - Early Exit Filter")
        print(f"{'='*80}")
        for filter_msg in early_exit_filters:
            print(f"   {filter_msg}")
        print(f"{'='*80}\n")
        return error_count, 0
    else:
        early_exit_filters.append(f"✅ ATR: {atr_pips:.1f}p trong khoảng {atr_min}-{atr_max}p")
    
    # SMA 9 Filter: Price at entry must be reasonably close to SMA 9 (Mean Reversion / Trend Touch)
    is_near_sma = False
    pip_val = point * 10 
    dist_to_sma = abs(last['close'] - last['sma9'])
    
    # Allow up to 10.0 pips distance (100 points) - Adjusted for XAUUSD volatility
    max_sma_distance = 100 * point  # 10 pips for XAUUSD
    if dist_to_sma <= max_sma_distance: 
        is_near_sma = True
        
    # Volume > 1.3x Average (Adjusted from 1.5x for more signals)
    volume_threshold = 1.3  # Reduced from 1.5x to 1.3x for more opportunities
    is_high_volume = last['tick_volume'] > (last['vol_ma'] * volume_threshold)
    
    # Pinbar Detection (Tightened: Nose < 1.5x body thay vì 2x)
    body_size = abs(last['close'] - last['open'])
    upper_shadow = last['high'] - max(last['close'], last['open'])
    lower_shadow = min(last['close'], last['open']) - last['low']
    
    # Minimal body size (very small body allowed)
    min_body = 0.1 * pip_val 
    if body_size < min_body: body_size = min_body  # Prevent division by zero or extreme ratios
    
    # Pinbar Detection (Adjusted: Nose < 2.0x body for more opportunities)
    pinbar_multiplier = 2.0  # Increased from 1.5x to 2.0x for more pinbar detection
    is_bullish_pinbar = (lower_shadow > pinbar_multiplier * body_size) and (upper_shadow < body_size * pinbar_multiplier)
    is_bearish_pinbar = (upper_shadow > pinbar_multiplier * body_size) and (lower_shadow < body_size * pinbar_multiplier)
    
    # Logging Analysis
    print(f"\n{'='*80}")
    print(f"📊 [STRATEGY 3: PA VOLUME ANALYSIS] {symbol}")
    print(f"{'='*80}")
    print(f"💱 Price: {last['close']:.2f} | M5 Trend: {m5_trend} | SMA9: {last['sma9']:.2f}")
    print(f"   📊 Volume: {last['tick_volume']} (Req > {int(last['vol_ma']*volume_threshold)}) | ATR: {atr_pips:.1f}p | Spread: {spread_pips:.1f}p")
    print(f"   📈 RSI: {last['rsi']:.1f} | Pinbar: {'Bull' if is_bullish_pinbar else 'Bear' if is_bearish_pinbar else 'None'}")
    
    # Track all filter status (include early exit filters)
    filter_status = early_exit_filters.copy()
    signal = None
    
    # V2: RSI Range Filter parameters
    rsi_buy_min = config['parameters'].get('rsi_buy_min', 40)
    rsi_buy_max = config['parameters'].get('rsi_buy_max', 60)
    rsi_sell_min = config['parameters'].get('rsi_sell_min', 40)
    rsi_sell_max = config['parameters'].get('rsi_sell_max', 60)
    rsi_extreme_high = config['parameters'].get('rsi_extreme_high', 70)
    rsi_extreme_low = config['parameters'].get('rsi_extreme_low', 30)
    
    # Check all conditions step by step
    if is_near_sma:
        filter_status.append(f"✅ Price near SMA9: {dist_to_sma:.1f} pts <= {max_sma_distance/point:.0f} pts")
        if is_high_volume:
            vol_ratio = last['tick_volume'] / last['vol_ma'] if last['vol_ma'] > 0 else 0
            filter_status.append(f"✅ High Volume: {vol_ratio:.2f}x > {volume_threshold}x")
            if is_bullish_pinbar and last['close'] > last['sma9']:
                filter_status.append(f"✅ Bullish Pinbar detected")
                filter_status.append(f"✅ Price > SMA9: {last['close']:.2f} > {last['sma9']:.2f}")
                if m5_trend == "BULLISH":
                    filter_status.append(f"✅ M5 Trend: BULLISH")
                    # V2: RSI Range Filter
                    current_rsi = last['rsi']
                    if current_rsi > rsi_extreme_high:
                        filter_status.append(f"❌ RSI Extreme High: {current_rsi:.1f} > {rsi_extreme_high} (Reject)")
                    elif current_rsi < rsi_extreme_low:
                        filter_status.append(f"❌ RSI Extreme Low: {current_rsi:.1f} < {rsi_extreme_low} (Reject)")
                    elif rsi_buy_min <= current_rsi <= rsi_buy_max:
                        filter_status.append(f"✅ RSI Range: {current_rsi:.1f} trong khoảng {rsi_buy_min}-{rsi_buy_max}")
                        signal = "BUY"
                        print("\n✅ [SIGNAL FOUND] BUY - Tất cả điều kiện đạt!")
                    else:
                        filter_status.append(f"❌ RSI Range: {current_rsi:.1f} không trong khoảng {rsi_buy_min}-{rsi_buy_max}")
                else:
                    filter_status.append(f"❌ M5 Trend: BEARISH (cần BULLISH)")
            elif is_bearish_pinbar and last['close'] < last['sma9']:
                filter_status.append(f"✅ Bearish Pinbar detected")
                filter_status.append(f"✅ Price < SMA9: {last['close']:.2f} < {last['sma9']:.2f}")
                if m5_trend == "BEARISH":
                    filter_status.append(f"✅ M5 Trend: BEARISH")
                    # V2: RSI Range Filter
                    current_rsi = last['rsi']
                    if current_rsi > rsi_extreme_high:
                        filter_status.append(f"❌ RSI Extreme High: {current_rsi:.1f} > {rsi_extreme_high} (Reject)")
                    elif current_rsi < rsi_extreme_low:
                        filter_status.append(f"❌ RSI Extreme Low: {current_rsi:.1f} < {rsi_extreme_low} (Reject)")
                    elif rsi_sell_min <= current_rsi <= rsi_sell_max:
                        filter_status.append(f"✅ RSI Range: {current_rsi:.1f} trong khoảng {rsi_sell_min}-{rsi_sell_max}")
                        signal = "SELL"
                        print("\n✅ [SIGNAL FOUND] SELL - Tất cả điều kiện đạt!")
                    else:
                        filter_status.append(f"❌ RSI Range: {current_rsi:.1f} không trong khoảng {rsi_sell_min}-{rsi_sell_max}")
                else:
                    filter_status.append(f"❌ M5 Trend: BULLISH (cần BEARISH)")
            else:
                if not is_bullish_pinbar and not is_bearish_pinbar:
                    filter_status.append(f"❌ Không có Pinbar (Bull: {is_bullish_pinbar}, Bear: {is_bearish_pinbar})")
                elif is_bullish_pinbar and last['close'] <= last['sma9']:
                    filter_status.append(f"❌ Bullish Pinbar nhưng Price <= SMA9: {last['close']:.2f} <= {last['sma9']:.2f}")
                elif is_bearish_pinbar and last['close'] >= last['sma9']:
                    filter_status.append(f"❌ Bearish Pinbar nhưng Price >= SMA9: {last['close']:.2f} >= {last['sma9']:.2f}")
        else:
            vol_ratio = last['tick_volume'] / last['vol_ma'] if last['vol_ma'] > 0 else 0
            filter_status.append(f"✅ Price near SMA9: {dist_to_sma:.1f} pts <= {max_sma_distance/point:.0f} pts")
            filter_status.append(f"❌ Volume không đủ: {vol_ratio:.2f}x < {volume_threshold}x (cần > {volume_threshold}x)")
            if is_bullish_pinbar or is_bearish_pinbar:
                filter_status.append(f"⚠️ Có Pinbar nhưng Volume thấp")
    else:
        filter_status.append(f"❌ Price quá xa SMA9: {dist_to_sma:.1f} pts > {max_sma_distance/point:.0f} pts (cần <= {max_sma_distance/point:.0f} pts)")
        if is_bullish_pinbar or is_bearish_pinbar:
            filter_status.append(f"⚠️ Có Pinbar nhưng Price quá xa SMA9")
    
    # Final Summary
    if not signal:
        print(f"\n{'─'*80}")
        print(f"❌ [KHÔNG CÓ TÍN HIỆU] - Tóm tắt các bộ lọc:")
        print(f"{'─'*80}")
        
        # Group filters by tier
        print(f"\n🔴 [TIER 1: EARLY EXIT FILTERS]")
        tier1_failed = [f for f in filter_status if f.startswith("❌") and ("Spread" in f or "ATR" in f)]
        tier1_passed = [f for f in filter_status if f.startswith("✅") and ("Spread" in f or "ATR" in f)]
        for status in tier1_passed:
            print(f"   {status}")
        for status in tier1_failed:
            print(f"   {status}")
        
        print(f"\n🟡 [TIER 2: SIGNAL CONDITIONS]")
        tier2_status = [f for f in filter_status if "Spread" not in f and "ATR" not in f]
        for i, status in enumerate(tier2_status, 1):
            print(f"   {i}. {status}")
        
        # Chi tiết giá trị
        print(f"\n📊 [CHI TIẾT GIÁ TRỊ]")
        print(f"   💱 Price: {last['close']:.2f}")
        print(f"   📈 M5 Trend: {m5_trend}")
        print(f"   📊 SMA9: {last['sma9']:.2f} | Distance: {dist_to_sma:.1f} pts (max: {max_sma_distance/point:.0f} pts)")
        vol_ratio = last['tick_volume'] / last['vol_ma'] if last['vol_ma'] > 0 else 0
        print(f"   📊 Volume: {last['tick_volume']} / Avg: {int(last['vol_ma'])} = {vol_ratio:.2f}x (cần > {volume_threshold}x)")
        print(f"   📊 ATR: {atr_pips:.1f} pips (range: {atr_min}-{atr_max} pips)")
        print(f"   📊 Spread: {spread_pips:.1f} pips (max: {max_spread} pips)")
        print(f"   📊 RSI: {last['rsi']:.1f} (V2: BUY cần {rsi_buy_min}-{rsi_buy_max}, SELL cần {rsi_sell_min}-{rsi_sell_max}, reject nếu >{rsi_extreme_high} hoặc <{rsi_extreme_low})")
        print(f"   📊 Pinbar: {'Bull' if is_bullish_pinbar else 'Bear' if is_bearish_pinbar else 'None'}")
        if is_bullish_pinbar or is_bearish_pinbar:
            body_pct = (body_size / (last['high'] - last['low'])) * 100 if (last['high'] - last['low']) > 0 else 0
            print(f"      Body: {body_pct:.1f}% | Lower Shadow: {lower_shadow:.2f} | Upper Shadow: {upper_shadow:.2f}")
        
        print(f"\n💡 Tổng số filters đã kiểm tra: {len(filter_status)}")
        print(f"   ✅ PASS: {len([f for f in filter_status if f.startswith('✅')])}")
        print(f"   ❌ FAIL: {len([f for f in filter_status if f.startswith('❌')])}")
        print(f"{'─'*80}\n")
    
    # 4. Execute
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
        sl_mode = config['parameters'].get('sl_mode', 'pinbar')  # Default to pinbar
        reward_ratio = config['parameters'].get('reward_ratio', 2.0)  # Default 1:2 for pinbar
        
        sl = 0.0
        tp = 0.0
        
        if sl_mode == 'atr':
            # ATR-based SL/TP (Dynamic)
            sl_multiplier = config['parameters'].get('sl_atr_multiplier', 2.0)
            tp_multiplier = config['parameters'].get('tp_atr_multiplier', 4.0)
            
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
            # Auto M5 Logic
            prev_m5_high = df_m5.iloc[-2]['high']
            prev_m5_low = df_m5.iloc[-2]['low']
            buffer = 20 * point
            
            if signal == "BUY":
                sl = prev_m5_low - buffer
                min_dist = 100 * point
                if (price - sl) < min_dist: sl = price - min_dist
                risk_dist = price - sl
                tp = price + (risk_dist * reward_ratio)
                
            elif signal == "SELL":
                sl = prev_m5_high + buffer
                min_dist = 100 * point
                if (sl - price) < min_dist: sl = price + min_dist
                risk_dist = sl - price
                tp = price - (risk_dist * reward_ratio)
            print(f"   📏 Auto M5 SL: {sl:.2f} | TP: {tp:.2f} (R:R {reward_ratio})")
        else:
            # Default Pinbar SL logic (Below Low / Above High of Pinbar)
            sl = last['low'] - (20 * point) if signal == "BUY" else last['high'] + (20 * point)
            
            risk = abs(price - sl)
            tp = price + (risk * reward_ratio) if signal == "BUY" else price - (risk * reward_ratio)
            print(f"   📏 Pinbar SL: {sl:.2f} | TP: {tp:.2f} (R:R {reward_ratio})")

        print(f"🚀 Strat 3 SIGNAL: {signal} @ {price}")
        
        db.log_signal("Strategy_3_PA_Volume", symbol, signal, price, sl, tp, {
            "vol": int(last['tick_volume']),
            "vol_ma": int(last['vol_ma']),
            "vol_ratio": float(last['tick_volume'] / last['vol_ma']) if last['vol_ma'] > 0 else 0,
            "pinbar": True,
            "rsi": float(last['rsi']),
            "atr": float(atr_value),
            "atr_pips": float(atr_pips),
            "spread_pips": float(spread_pips),
            "trend": m5_trend
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
            "comment": "Strat3_PA_Vol",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Success: {result.order}")
            db.log_order(result.order, "Strategy_3_PA_Volume", symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
            
            msg = (
                f"✅ <b>Strat 3: PA Volume Executed</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"👤 <b>Account:</b> {config['account']}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal})\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.2f} | 🎯 <b>TP:</b> {tp:.2f}\n"
                f"📊 <b>Indicators:</b>\n"
                f"• M5 Trend: {m5_trend}\n"
                f"• Vol: {int(last['tick_volume'])} ({last['tick_volume']/last['vol_ma']:.1f}x avg)\n"
                f"• ATR: {atr_pips:.1f} pips\n"
                f"• Spread: {spread_pips:.1f} pips\n"
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
    config_path = os.path.join(script_dir, "configs", "config_3.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 3: PA Volume - Started")
        try:
            while True:
                consecutive_errors, last_error_code = strategy_3_logic(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Strategy 3: PA Volume] WARNING: 5 Consecutive Order Failures. Last Error: {error_msg}. Pausing for 2 minutes..."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    time.sleep(120)
                    consecutive_errors = 0
                    print("▶️ Resuming...")
                    continue
                    
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
