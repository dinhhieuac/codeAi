import MetaTrader5 as mt5
import time
import sys
import numpy as np

# Import local modules
sys.path.append('..')
from db import Database
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message, calculate_rsi

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

    # H1 Trend
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    h1_trend = "BULLISH" if df_h1.iloc[-1]['close'] > df_h1.iloc[-1]['ema50'] else "BEARISH"

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
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 3. Logic: Crossover + RSI Filter + H1 Trend
    signal = None
    
    print(f"\n{'='*80}")
    print(f"📊 [STRATEGY 2: EMA ATR ANALYSIS] {symbol}")
    print(f"{'='*80}")
    print(f"💱 Price: {last['close']:.2f} | H1 Trend: {h1_trend} | EMA14: {last['ema14']:.3f} | EMA28: {last['ema28']:.3f} | RSI: {last['rsi']:.1f}")
    
    # Track all filter status
    filter_status = []
    
    # Check for crossover
    has_crossover = False
    crossover_direction = None
    
    # BUY: EMA 14 crosses ABOVE EMA 28 AND RSI > 50 AND H1 Bullish
    if prev['ema14'] <= prev['ema28'] and last['ema14'] > last['ema28']:
        has_crossover = True
        crossover_direction = "BUY"
        filter_status.append(f"✅ EMA Crossover: EMA14 > EMA28 (Bullish)")
        
        if h1_trend == "BULLISH":
            filter_status.append(f"✅ H1 Trend: BULLISH")
            # Extension Check
            price_dist = abs(last['close'] - last['ema14'])
            atr_threshold = 1.5 * last['atr']
            is_extended = price_dist > atr_threshold
            filter_status.append(f"{'❌' if is_extended else '✅'} Price Extension: {price_dist:.2f} {'>' if is_extended else '<='} {atr_threshold:.2f} (1.5xATR)")
            
            if not is_extended:
                filter_status.append(f"{'✅' if last['rsi'] > 50 else '❌'} RSI > 50: {last['rsi']:.1f}")
                if last['rsi'] > 50:
                    signal = "BUY"
                    print("\n✅ [SIGNAL FOUND] BUY - Tất cả điều kiện đạt!")
                else:
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt")
            else:
                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Price Extended")
        else:
            filter_status.append(f"❌ H1 Trend: BEARISH (cần BULLISH)")
            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - H1 Trend không phù hợp")
        
    # SELL: EMA 14 crosses BELOW EMA 28 AND RSI < 50 AND H1 Bearish
    elif prev['ema14'] >= prev['ema28'] and last['ema14'] < last['ema28']:
        has_crossover = True
        crossover_direction = "SELL"
        filter_status.append(f"✅ EMA Crossover: EMA14 < EMA28 (Bearish)")
        
        if h1_trend == "BEARISH":
            filter_status.append(f"✅ H1 Trend: BEARISH")
            # Extension Check
            price_dist = abs(last['close'] - last['ema14'])
            atr_threshold = 1.5 * last['atr']
            is_extended = price_dist > atr_threshold
            filter_status.append(f"{'❌' if is_extended else '✅'} Price Extension: {price_dist:.2f} {'>' if is_extended else '<='} {atr_threshold:.2f} (1.5xATR)")
            
            if not is_extended:
                filter_status.append(f"{'✅' if last['rsi'] < 50 else '❌'} RSI < 50: {last['rsi']:.1f}")
                if last['rsi'] < 50:
                    signal = "SELL"
                    print("\n✅ [SIGNAL FOUND] SELL - Tất cả điều kiện đạt!")
                else:
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt")
            else:
                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Price Extended")
        else:
            filter_status.append(f"❌ H1 Trend: BULLISH (cần BEARISH)")
            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - H1 Trend không phù hợp")

    else:
        diff = last['ema14'] - last['ema28']
        if diff > 0:
            filter_status.append(f"❌ No Crossover: Already Bullish (Gap: {diff:.3f})")
        else:
            filter_status.append(f"❌ No Crossover: Already Bearish (Gap: {diff:.3f})")
        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Không có EMA Crossover")
    
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
        print(f"   📈 H1 Trend: {h1_trend}")
        print(f"   📊 EMA14: {last['ema14']:.3f} | EMA28: {last['ema28']:.3f} | Gap: {last['ema14'] - last['ema28']:.3f}")
        print(f"   📊 RSI: {last['rsi']:.1f} (BUY cần > 50, SELL cần < 50)")
        print(f"   📊 ATR: {last['atr']:.2f}")
        price_dist = abs(last['close'] - last['ema14'])
        atr_threshold = 1.5 * last['atr']
        print(f"   📊 Price Distance from EMA14: {price_dist:.2f} (max: {atr_threshold:.2f} = 1.5xATR)")
        
        print(f"\n💡 Tổng số filters đã kiểm tra: {len(filter_status)}")
        print(f"   ✅ PASS: {len([f for f in filter_status if f.startswith('✅')])}")
        print(f"   ❌ FAIL: {len([f for f in filter_status if f.startswith('❌')])}")
        print(f"{'─'*80}\n")
        
    # 4. Execute
    if signal:
        # --- SPAM FILTER: Check if we traded in the last 60 seconds ---
        # Get all deals from history to check Cooldown
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
                      {"ema14": float(last['ema14']), "ema28": float(last['ema28']), "atr": float(atr_val), "rsi": float(last['rsi'])},
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
            print(f"✅ Order Scussess: {result.order}")
            db.log_order(result.order, "Strategy_2_EMA_ATR", symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
            
            msg = (
                f"✅ <b>Strat 2: EMA ATR Executed</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"👤 <b>Account:</b> {config['account']}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal})\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.2f} | 🎯 <b>TP:</b> {tp:.2f}\n"
                f"📊 <b>Indicators:</b>\n"
                f"• EMA14: {last['ema14']:.2f}\n"
                f"• EMA28: {last['ema28']:.2f}\n"
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
