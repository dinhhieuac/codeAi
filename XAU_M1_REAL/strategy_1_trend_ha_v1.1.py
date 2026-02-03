import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# Import local modules
sys.path.append('..') # Add parent directory to path to find XAU_M1 modules if running from sub-folder
from db import Database
from utils import load_config, connect_mt5, get_data, calculate_heiken_ashi, send_telegram, is_doji, manage_position, get_mt5_error_message, calculate_rsi, calculate_adx

# Initialize Database
db = Database()

def strategy_1_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    # 2. Check Global Max Positions & Manage Existing
    all_positions = mt5.positions_get(symbol=symbol)
    positions = [pos for pos in (all_positions or []) if pos.magic == magic]  # Chỉ lấy positions do bot này mở
    if positions:
        # Manage Trailing SL for all open positions of this strategy
        for pos in positions:
            manage_position(pos.ticket, symbol, magic, config)
            
        if len(positions) >= max_positions:
            # Silent return to avoid spam
            return error_count, 0

    # 1. Get Data (M1, M5 for trend, H1 for long-term trend confirmation)
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 200)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 200)
    df_h1 = get_data(symbol, mt5.TIMEFRAME_H1, 200)
    
    if df_m1 is None or df_m5 is None or df_h1 is None: 
        return error_count, 0

    # 2. Calculate Indicators
    # Trend Filter: EMA 200 on M5
    df_m5['ema200'] = df_m5['close'].ewm(span=200, adjust=False).mean()
    current_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"
    
    # H1 Trend Filter: EMA 100 on H1 for long-term trend confirmation
    h1_ema_period = config['parameters'].get('h1_ema_period', 100)
    h1_trend_confirmation_required = config['parameters'].get('h1_trend_confirmation_required', True)  # V1.1: BẮT BUỘC
    df_h1['ema100'] = df_h1['close'].ewm(span=h1_ema_period, adjust=False).mean()
    h1_trend = "BULLISH" if df_h1.iloc[-1]['close'] > df_h1.iloc[-1]['ema100'] else "BEARISH"
    
    # V1.1: Check H1 trend alignment with M5 trend - BẮT BUỘC
    if h1_trend_confirmation_required:
        if h1_trend != current_trend:
            print(f"❌ H1 Trend Filter: H1 Trend ({h1_trend}) != M5 Trend ({current_trend}) - Không đồng nhất, skipping")
            return error_count, 0
        print(f"✅ H1 Trend Filter: H1 Trend ({h1_trend}) == M5 Trend ({current_trend}) - Đồng nhất (EMA{h1_ema_period}: {df_h1.iloc[-1]['ema100']:.2f})")
    else:
        print(f"⚠️ H1 Trend Filter: Disabled - V1.1 yêu cầu H1 confirmation BẮT BUỘC")
        return error_count, 0  # V1.1: Không cho phép disable
    
    # ADX Filter: ADX(14) >= 20 to confirm trend strength
    adx_period = config['parameters'].get('adx_period', 14)
    adx_min_threshold = config['parameters'].get('adx_min_threshold', 20)
    df_m5 = calculate_adx(df_m5, period=adx_period)
    adx_value = df_m5.iloc[-1]['adx']
    if pd.isna(adx_value) or adx_value < adx_min_threshold:
        print(f"❌ ADX Filter: ADX={adx_value:.1f} < {adx_min_threshold} (No trend, skipping)")
        return error_count, 0
    print(f"✅ ADX Filter: ADX={adx_value:.1f} >= {adx_min_threshold} (Trend confirmed)")

    # Channel: 55 SMA High/Low on M1
    df_m1['sma55_high'] = df_m1['high'].rolling(window=55).mean()
    df_m1['sma55_low'] = df_m1['low'].rolling(window=55).mean()
    
    # Heiken Ashi
    ha_df = calculate_heiken_ashi(df_m1)
    
    # RSI 14
    ha_df['rsi'] = calculate_rsi(df_m1['close'], period=14)

    last_ha = ha_df.iloc[-1]
    prev_ha = ha_df.iloc[-2]

    # 3. Check Signals
    signal = None
    price = mt5.symbol_info_tick(symbol).ask if current_trend == "BULLISH" else mt5.symbol_info_tick(symbol).bid
    
    # Detailed Logging
    print(f"\n{'='*80}")
    print(f"📊 [STRATEGY 1: TREND HA V1.1 ANALYSIS] {symbol}")
    print(f"{'='*80}")
    print(f"💱 Price: {price:.2f} | Trend (M5): {current_trend} | Trend (H1): {h1_trend} | ADX: {adx_value:.1f} | RSI: {last_ha['rsi']:.1f}")
    print(f"   HA Close: {last_ha['ha_close']:.2f} | HA Open: {last_ha['ha_open']:.2f}")
    print(f"   SMA55 High: {last_ha['sma55_high']:.2f} | SMA55 Low: {last_ha['sma55_low']:.2f}")
    print(f"   H1 EMA{h1_ema_period}: {df_h1.iloc[-1]['ema100']:.2f} | H1 Close: {df_h1.iloc[-1]['close']:.2f}")
    
    # Track all filter status
    filter_status = []
    
    # V1.1: BUY SETUP - Chỉ khi m5_trend == BULLISH VÀ h1_trend == BULLISH
    if current_trend == "BULLISH" and h1_trend == "BULLISH":
        is_green = last_ha['ha_close'] > last_ha['ha_open']
        is_above_channel = last_ha['ha_close'] > last_ha['sma55_high']
        is_fresh_breakout = prev_ha['ha_close'] <= prev_ha['sma55_high']
        is_solid_candle = not is_doji(last_ha, threshold=0.2) # Require body > 20% of range for HA

        filter_status.append(f"✅ M5 Trend: BULLISH")
        filter_status.append(f"✅ H1 Trend: BULLISH (V1.1: BẮT BUỘC đồng nhất)")
        filter_status.append(f"{'✅' if is_green else '❌'} HA Candle: {'Green' if is_green else 'Red'}")
        filter_status.append(f"{'✅' if is_above_channel else '❌'} Above Channel: {last_ha['ha_close']:.2f} > {last_ha['sma55_high']:.2f}")
        
        if is_green and is_above_channel:
            filter_status.append(f"{'✅' if is_fresh_breakout else '❌'} Fresh Breakout: Prev HA Close {prev_ha['ha_close']:.2f} <= SMA55 High {prev_ha['sma55_high']:.2f}")
            if is_fresh_breakout:
                filter_status.append(f"{'✅' if is_solid_candle else '❌'} Solid Candle: {'Not Doji' if is_solid_candle else 'Doji detected (Indecision)'}")
                if is_solid_candle:
                    # RSI Filter
                    rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 55)
                    filter_status.append(f"{'✅' if last_ha['rsi'] > rsi_buy_threshold else '❌'} RSI > {rsi_buy_threshold}: {last_ha['rsi']:.1f}")
                    if last_ha['rsi'] > rsi_buy_threshold:
                        signal = "BUY"
                        print(f"\n✅ [SIGNAL FOUND] BUY - Tất cả điều kiện đạt! (M5: {current_trend}, H1: {h1_trend}, RSI: {last_ha['rsi']:.1f} > {rsi_buy_threshold})")
                    else:
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần > {rsi_buy_threshold}, hiện tại: {last_ha['rsi']:.1f})")
                else: 
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Doji Candle detected")
            else:
                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Không phải fresh breakout")
        else:
            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Điều kiện cơ bản không đạt")
    elif current_trend == "BULLISH" and h1_trend != "BULLISH":
        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - M5 Trend BULLISH nhưng H1 Trend {h1_trend} (V1.1: Cần cả 2 cùng BULLISH)")

    # V1.1: SELL SETUP - Chỉ khi m5_trend == BEARISH VÀ h1_trend == BEARISH
    if current_trend == "BEARISH" and h1_trend == "BEARISH":
        is_red = last_ha['ha_close'] < last_ha['ha_open']
        is_below_channel = last_ha['ha_close'] < last_ha['sma55_low']
        is_fresh_breakout = prev_ha['ha_close'] >= prev_ha['sma55_low']
        is_solid_candle = not is_doji(last_ha, threshold=0.2)

        filter_status.append(f"✅ M5 Trend: BEARISH")
        filter_status.append(f"✅ H1 Trend: BEARISH (V1.1: BẮT BUỘC đồng nhất)")
        filter_status.append(f"{'✅' if is_red else '❌'} HA Candle: {'Red' if is_red else 'Green'}")
        filter_status.append(f"{'✅' if is_below_channel else '❌'} Below Channel: {last_ha['ha_close']:.2f} < {last_ha['sma55_low']:.2f}")
        
        if is_red and is_below_channel:
            filter_status.append(f"{'✅' if is_fresh_breakout else '❌'} Fresh Breakout: Prev HA Close {prev_ha['ha_close']:.2f} >= SMA55 Low {prev_ha['sma55_low']:.2f}")
            if is_fresh_breakout:
                filter_status.append(f"{'✅' if is_solid_candle else '❌'} Solid Candle: {'Not Doji' if is_solid_candle else 'Doji detected (Indecision)'}")
                if is_solid_candle:
                    # RSI Filter
                    rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 45)
                    filter_status.append(f"{'✅' if last_ha['rsi'] < rsi_sell_threshold else '❌'} RSI < {rsi_sell_threshold}: {last_ha['rsi']:.1f}")
                    if last_ha['rsi'] < rsi_sell_threshold:
                        signal = "SELL"
                        print(f"\n✅ [SIGNAL FOUND] SELL - Tất cả điều kiện đạt! (M5: {current_trend}, H1: {h1_trend}, RSI: {last_ha['rsi']:.1f} < {rsi_sell_threshold})")
                    else:
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần < {rsi_sell_threshold}, hiện tại: {last_ha['rsi']:.1f})")
                else:
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Doji Candle detected")
            else:
                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Không phải fresh breakout")
        else:
            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Điều kiện cơ bản không đạt")
    elif current_trend == "BEARISH" and h1_trend != "BEARISH":
        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - M5 Trend BEARISH nhưng H1 Trend {h1_trend} (V1.1: Cần cả 2 cùng BEARISH)")
    
    # Final Summary
    if not signal:
        print(f"\n{'─'*80}")
        print(f"❌ [KHÔNG CÓ TÍN HIỆU] - Tóm tắt các bộ lọc:")
        print(f"{'─'*80}")
        for i, status in enumerate(filter_status, 1):
            print(f"   {i}. {status}")
        
        # Chi tiết giá trị
        print(f"\n📊 [CHI TIẾT GIÁ TRỊ]")
        print(f"   💱 Price: {price:.2f}")
        print(f"   📈 M5 Trend: {current_trend}")
        print(f"   📈 H1 Trend: {h1_trend} (EMA{h1_ema_period}: {df_h1.iloc[-1]['ema100']:.2f})")
        print(f"   📈 Trend Alignment: {'✅ Đồng nhất' if h1_trend == current_trend else '❌ Không đồng nhất (V1.1: BẮT BUỘC)'}")
        print(f"   📊 ADX: {adx_value:.1f} (cần >= {adx_min_threshold})")
        print(f"   📊 HA Close: {last_ha['ha_close']:.2f} | HA Open: {last_ha['ha_open']:.2f}")
        print(f"   📊 SMA55 High: {last_ha['sma55_high']:.2f} | SMA55 Low: {last_ha['sma55_low']:.2f}")
        # Get RSI thresholds for display
        rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 55)
        rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 45)
        print(f"   📊 RSI: {last_ha['rsi']:.1f} (BUY cần > {rsi_buy_threshold}, SELL cần < {rsi_sell_threshold})")
        if current_trend == "BULLISH":
            print(f"   📊 Above Channel: {last_ha['ha_close']:.2f} > {last_ha['sma55_high']:.2f}")
            print(f"   📊 Fresh Breakout: Prev {prev_ha['ha_close']:.2f} <= {prev_ha['sma55_high']:.2f}")
        else:
            print(f"   📊 Below Channel: {last_ha['ha_close']:.2f} < {last_ha['sma55_low']:.2f}")
            print(f"   📊 Fresh Breakout: Prev {prev_ha['ha_close']:.2f} >= {prev_ha['sma55_low']:.2f}")
        
        print(f"\n💡 Tổng số filters đã kiểm tra: {len(filter_status)}")
        print(f"   ✅ PASS: {len([f for f in filter_status if f.startswith('✅')])}")
        print(f"   ❌ FAIL: {len([f for f in filter_status if f.startswith('❌')])}")
        print(f"{'─'*80}\n")

    
    # 4. Execute Trade
    if signal:
        # --- SPAM FILTER: Check if we traded in the last 60 seconds ---
        strat_positions = mt5.positions_get(symbol=symbol, magic=magic)
        if strat_positions:
            strat_positions = sorted(strat_positions, key=lambda x: x.time, reverse=True)
            last_trade_time = strat_positions[0].time
            current_server_time = mt5.symbol_info_tick(symbol).time
            if (current_server_time - last_trade_time) < 60:
                print(f"   ⏳ Skipping: Trade already taken {current_server_time - last_trade_time}s ago (Wait 60s per candle)")
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
            
            # Add a small buffer (e.g., 20 points / 2 pips) to avoid noise
            buffer = 20 * mt5.symbol_info(symbol).point
            
            if signal == "BUY":
                sl = prev_m5_low - buffer
                # Check if SL is too close (safety) - min 10 pips
                min_dist = 100 * mt5.symbol_info(symbol).point
                if (price - sl) < min_dist:
                    sl = price - min_dist
                    
                risk_dist = price - sl
                tp = price + (risk_dist * reward_ratio)
                
            elif signal == "SELL":
                sl = prev_m5_high + buffer
                # Check min dist
                min_dist = 100 * mt5.symbol_info(symbol).point
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
        db.log_signal("Strategy_1_Trend_HA_V1.1", symbol, signal, price, sl, tp, 
                      {"m5_trend": current_trend, "h1_trend": h1_trend, "ha_close": float(last_ha['ha_close']), "sl_mode": sl_mode, "rsi": float(last_ha['rsi'])}, 
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
            "comment": "Strat1_HA_V1.1",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(result.order, "Strategy_1_Trend_HA_V1.1", symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
            
            # Detailed Telegram Message
            msg = (
                f"✅ <b>Strat 1: Trend HA V1.1 Executed</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"👤 <b>Account:</b> {config['account']}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal})\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.2f} | 🎯 <b>TP:</b> {tp:.2f}\n"
                f"📊 <b>Indicators:</b>\n"
                f"• M5 Trend: {current_trend}\n"
                f"• H1 Trend: {h1_trend} (EMA{h1_ema_period}) ✅\n"
                f"• ADX: {adx_value:.1f}\n"
                f"• RSI: {last_ha['rsi']:.1f}\n"
                f"• V1.1: M5 & H1 đồng nhất ✅"
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
    config_path = os.path.join(script_dir, "configs", "config_1_v1.1.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 1: Trend HA V1.1 - Started")
        print("📋 V1.1 Improvements:")
        print("   ✅ H1 Trend Confirmation BẮT BUỘC")
        print("   ✅ BUY chỉ khi M5 & H1 cùng BULLISH")
        print("   ✅ SELL chỉ khi M5 & H1 cùng BEARISH")
        try:
            while True:
                consecutive_errors, last_error_code = strategy_1_logic(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Strategy 1: Trend HA V1.1] WARNING: 5 Consecutive Order Failures. Last Error: {error_msg}. Pausing for 2 minutes..."
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
