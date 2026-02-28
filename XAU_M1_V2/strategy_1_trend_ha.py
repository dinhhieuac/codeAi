import MetaTrader5 as mt5
import time
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime

# Import local modules
import os
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
from db import Database
from utils import load_config, connect_mt5, get_data, calculate_heiken_ashi, send_telegram, is_doji_ha, manage_position, get_mt5_error_message, calculate_rsi, calculate_adx, calculate_atr

# Initialize Database
db = Database()

# File lưu last_trade_time ổn định (không phụ thuộc position, không bị reset khi đóng lệnh)
LAST_TRADE_TIME_FILE = os.path.join(_script_dir, "last_trade_time.json")

def _get_last_trade_time():
    """Đọc last_trade_time từ file (Unix timestamp). Trả về 0 nếu chưa có."""
    try:
        if os.path.isfile(LAST_TRADE_TIME_FILE):
            with open(LAST_TRADE_TIME_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return float(data.get("last_trade_time", 0))
    except Exception as e:
        print(f"⚠️ Read last_trade_time: {e}")
    return 0.0

def _set_last_trade_time(server_timestamp):
    """Ghi last_trade_time ra file (Unix timestamp)."""
    try:
        with open(LAST_TRADE_TIME_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_trade_time": float(server_timestamp)}, f)
    except Exception as e:
        print(f"⚠️ Write last_trade_time: {e}")

# File lưu initial SL distance theo ticket (cho breakeven/trailing dùng đúng khoảng cách SL ban đầu)
INITIAL_SL_MAP_FILE = os.path.join(_script_dir, "initial_sl_map.json")

def _load_initial_sl_map():
    """Đọc initial_sl_map từ file. Trả về dict { ticket (int): initial_sl_pips (float) }."""
    try:
        if os.path.isfile(INITIAL_SL_MAP_FILE):
            with open(INITIAL_SL_MAP_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): float(v) for k, v in (data.get("tickets") or data).items()}
    except Exception as e:
        print(f"⚠️ Read initial_sl_map: {e}")
    return {}

def _save_initial_sl_map(ticket, initial_sl_pips):
    """Thêm/ghi ticket -> initial_sl_pips vào file (merge với map hiện có)."""
    try:
        m = _load_initial_sl_map()
        m[int(ticket)] = float(initial_sl_pips)
        with open(INITIAL_SL_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump({"tickets": m}, f)
    except Exception as e:
        print(f"⚠️ Write initial_sl_map: {e}")

def strategy_1_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    # 2. Check Global Max Positions & Manage Existing
    all_positions = mt5.positions_get(symbol=symbol)
    positions = [pos for pos in (all_positions or []) if pos.magic == magic]  # Chỉ lấy positions do bot này mở
    #positions = mt5.positions_get(symbol=symbol, magic=magic)
    if positions:
        initial_sl_map = _load_initial_sl_map()
        for pos in positions:
            manage_position(pos.ticket, symbol, magic, config, initial_sl_map=initial_sl_map)
            
        if len(positions) >= max_positions:
            # Silent return to avoid spam
            return error_count, 0

    # 1. Get Data (M1, M5 for trend, H1 for long-term trend confirmation)
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 200)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 200)
    df_h1 = get_data(symbol, mt5.TIMEFRAME_H1, 200)
    
    if df_m1 is None or df_m5 is None or df_h1 is None: 
        return error_count, 0

    # use_closed_candles: khi true thì mọi điều kiện trend/ADX/RSI/signal dùng nến đã đóng (-2, -3) chống repaint
    use_closed_candles = config['parameters'].get('use_closed_candles', False)
    idx_cur = -2 if use_closed_candles else -1
    idx_prev = -3 if use_closed_candles else -2
    if use_closed_candles:
        print(f"📌 use_closed_candles=true: signal/trend/ADX/RSI dùng nến đã đóng (idx {idx_cur}/{idx_prev})")

    # 2. Calculate Indicators
    # Trend Filter: EMA 200 on M5
    df_m5['ema200'] = df_m5['close'].ewm(span=200, adjust=False).mean()
    current_trend = "BULLISH" if df_m5.iloc[idx_cur]['close'] > df_m5.iloc[idx_cur]['ema200'] else "BEARISH"
    
    # H1 Trend Filter: EMA on H1 for long-term trend confirmation
    h1_ema_period = config['parameters'].get('h1_ema_period', 100)
    h1_trend_confirmation_required = config['parameters'].get('h1_trend_confirmation_required', True)  # Default: required
    df_h1['ema100'] = df_h1['close'].ewm(span=h1_ema_period, adjust=False).mean()
    h1_trend = "BULLISH" if df_h1.iloc[idx_cur]['close'] > df_h1.iloc[idx_cur]['ema100'] else "BEARISH"
    
    # Check H1 trend alignment with M5 trend
    if h1_trend_confirmation_required:
        if h1_trend != current_trend:
            print(f"❌ H1 Trend Filter: H1 Trend ({h1_trend}) != M5 Trend ({current_trend}) - Không đồng nhất, skipping")
            return error_count, 0
        print(f"✅ H1 Trend Filter: H1 Trend ({h1_trend}) == M5 Trend ({current_trend}) - Đồng nhất (EMA{h1_ema_period}: {df_h1.iloc[idx_cur]['ema100']:.2f})")
    else:
        print(f"⏭️  H1 Trend Filter: Disabled (optional) - H1 Trend: {h1_trend}, M5 Trend: {current_trend}")
    
    # V2: ADX Filter - Yêu cầu ADX >35 cho tất cả lệnh (như V2 thành công)
    adx_period = config['parameters'].get('adx_period', 14)
    adx_min_threshold = config['parameters'].get('adx_min_threshold', 35)  # V2: Yêu cầu ADX >35
    df_m5 = calculate_adx(df_m5, period=adx_period)
    adx_value = df_m5.iloc[idx_cur]['adx']
    if pd.isna(adx_value) or adx_value < adx_min_threshold:
        print(f"❌ ADX Filter: ADX={adx_value:.1f} < {adx_min_threshold} (No trend, skipping)")
        return error_count, 0
    print(f"✅ ADX Filter: ADX={adx_value:.1f} >= {adx_min_threshold} (Trend confirmed)")

    # Channel: 55 SMA High/Low on M1
    df_m1['sma55_high'] = df_m1['high'].rolling(window=55).mean()
    df_m1['sma55_low'] = df_m1['low'].rolling(window=55).mean()
    
    # Heiken Ashi
    ha_df = calculate_heiken_ashi(df_m1)
    
    # RSI 14 (Added Filter)
    ha_df['rsi'] = calculate_rsi(df_m1['close'], period=14)

    last_ha = ha_df.iloc[idx_cur]
    prev_ha = ha_df.iloc[idx_prev]

    # 3. Check Signals
    signal = None
    price = mt5.symbol_info_tick(symbol).ask if current_trend == "BULLISH" else mt5.symbol_info_tick(symbol).bid
    
    # Detailed Logging
    print(f"\n{'='*80}")
    print(f"📊 [STRATEGY 1: TREND HA ANALYSIS] {symbol}")
    print(f"{'='*80}")
    print(f"💱 Price: {price:.2f} | Trend (M5): {current_trend} | Trend (H1): {h1_trend} | ADX: {adx_value:.1f} | RSI: {last_ha['rsi']:.1f}")
    print(f"   HA Close: {last_ha['ha_close']:.2f} | HA Open: {last_ha['ha_open']:.2f}")
    print(f"   SMA55 High: {last_ha['sma55_high']:.2f} | SMA55 Low: {last_ha['sma55_low']:.2f}")
    print(f"   H1 EMA{h1_ema_period}: {df_h1.iloc[idx_cur]['ema100']:.2f} | H1 Close: {df_h1.iloc[idx_cur]['close']:.2f}")
    
    # Track all filter status
    filter_status = []
    
    # BUY SETUP
    if current_trend == "BULLISH":
        is_green = last_ha['ha_close'] > last_ha['ha_open']
        is_above_channel = last_ha['ha_close'] > last_ha['sma55_high']
        is_fresh_breakout = prev_ha['ha_close'] <= prev_ha['sma55_high']
        is_solid_candle = not is_doji_ha(last_ha, threshold=0.2)  # Doji filter đúng Heiken Ashi (ha_open/ha_close/ha_high/ha_low)

        filter_status.append(f"✅ M5 Trend: BULLISH")
        if h1_trend_confirmation_required:
            filter_status.append(f"{'✅' if h1_trend == current_trend else '❌'} H1 Trend: {h1_trend} (EMA{h1_ema_period}: {df_h1.iloc[idx_cur]['ema100']:.2f})")
        filter_status.append(f"{'✅' if is_green else '❌'} HA Candle: {'Green' if is_green else 'Red'}")
        filter_status.append(f"{'✅' if is_above_channel else '❌'} Above Channel: {last_ha['ha_close']:.2f} > {last_ha['sma55_high']:.2f}")
        
        if is_green and is_above_channel:
            filter_status.append(f"{'✅' if is_fresh_breakout else '❌'} Fresh Breakout: Prev HA Close {prev_ha['ha_close']:.2f} <= SMA55 High {prev_ha['sma55_high']:.2f}")
            if is_fresh_breakout:
                filter_status.append(f"{'✅' if is_solid_candle else '❌'} Solid Candle (HA): {'Not Doji' if is_solid_candle else 'Doji detected (Indecision)'}")
                if is_solid_candle:
                    # V2: RSI Threshold - Chỉ BUY nếu RSI 40-60, bỏ lệnh nếu >70 hoặc <30
                    rsi_buy_min = config['parameters'].get('rsi_buy_min', 40)
                    rsi_buy_max = config['parameters'].get('rsi_buy_max', 60)
                    rsi_extreme_high = config['parameters'].get('rsi_extreme_high', 70)
                    rsi_extreme_low = config['parameters'].get('rsi_extreme_low', 30)
                    current_rsi = last_ha['rsi']
                    
                    # Check extreme values first (reject if too extreme)
                    if current_rsi > rsi_extreme_high:
                        filter_status.append(f"❌ RSI Extreme High: {current_rsi:.1f} > {rsi_extreme_high} (Reject)")
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI quá cao (>{rsi_extreme_high}), hiện tại: {current_rsi:.1f}")
                    elif current_rsi < rsi_extreme_low:
                        filter_status.append(f"❌ RSI Extreme Low: {current_rsi:.1f} < {rsi_extreme_low} (Reject)")
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI quá thấp (<{rsi_extreme_low}), hiện tại: {current_rsi:.1f}")
                    elif rsi_buy_min <= current_rsi <= rsi_buy_max:
                        filter_status.append(f"✅ RSI Range: {current_rsi:.1f} trong khoảng {rsi_buy_min}-{rsi_buy_max}")
                        signal = "BUY"
                        print(f"\n✅ [SIGNAL FOUND] BUY - Tất cả điều kiện đạt! (RSI: {current_rsi:.1f} trong khoảng {rsi_buy_min}-{rsi_buy_max})")
                    else:
                        filter_status.append(f"❌ RSI Range: {current_rsi:.1f} không trong khoảng {rsi_buy_min}-{rsi_buy_max}")
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần trong khoảng {rsi_buy_min}-{rsi_buy_max}, hiện tại: {current_rsi:.1f})")
                else: 
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Doji Candle detected")
            else:
                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Không phải fresh breakout")
        else:
            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Điều kiện cơ bản không đạt")

    # SELL SETUP
    elif current_trend == "BEARISH":
        is_red = last_ha['ha_close'] < last_ha['ha_open']
        is_below_channel = last_ha['ha_close'] < last_ha['sma55_low']
        is_fresh_breakout = prev_ha['ha_close'] >= prev_ha['sma55_low']
        is_solid_candle = not is_doji_ha(last_ha, threshold=0.2)

        filter_status.append(f"✅ M5 Trend: BEARISH")
        if h1_trend_confirmation_required:
            filter_status.append(f"{'✅' if h1_trend == current_trend else '❌'} H1 Trend: {h1_trend} (EMA{h1_ema_period}: {df_h1.iloc[idx_cur]['ema100']:.2f})")
        filter_status.append(f"{'✅' if is_red else '❌'} HA Candle: {'Red' if is_red else 'Green'}")
        filter_status.append(f"{'✅' if is_below_channel else '❌'} Below Channel: {last_ha['ha_close']:.2f} < {last_ha['sma55_low']:.2f}")
        
        if is_red and is_below_channel:
            filter_status.append(f"{'✅' if is_fresh_breakout else '❌'} Fresh Breakout: Prev HA Close {prev_ha['ha_close']:.2f} >= SMA55 Low {prev_ha['sma55_low']:.2f}")
            if is_fresh_breakout:
                filter_status.append(f"{'✅' if is_solid_candle else '❌'} Solid Candle (HA): {'Not Doji' if is_solid_candle else 'Doji detected (Indecision)'}")
                if is_solid_candle:
                    # V2: RSI Threshold - Chỉ SELL nếu RSI 40-60, bỏ lệnh nếu >70 hoặc <30
                    rsi_sell_min = config['parameters'].get('rsi_sell_min', 40)
                    rsi_sell_max = config['parameters'].get('rsi_sell_max', 60)
                    rsi_extreme_high = config['parameters'].get('rsi_extreme_high', 70)
                    rsi_extreme_low = config['parameters'].get('rsi_extreme_low', 30)
                    current_rsi = last_ha['rsi']
                    
                    # Check extreme values first (reject if too extreme)
                    if current_rsi > rsi_extreme_high:
                        filter_status.append(f"❌ RSI Extreme High: {current_rsi:.1f} > {rsi_extreme_high} (Reject)")
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI quá cao (>{rsi_extreme_high}), hiện tại: {current_rsi:.1f}")
                    elif current_rsi < rsi_extreme_low:
                        filter_status.append(f"❌ RSI Extreme Low: {current_rsi:.1f} < {rsi_extreme_low} (Reject)")
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI quá thấp (<{rsi_extreme_low}), hiện tại: {current_rsi:.1f}")
                    elif rsi_sell_min <= current_rsi <= rsi_sell_max:
                        filter_status.append(f"✅ RSI Range: {current_rsi:.1f} trong khoảng {rsi_sell_min}-{rsi_sell_max}")
                        signal = "SELL"
                        print(f"\n✅ [SIGNAL FOUND] SELL - Tất cả điều kiện đạt! (RSI: {current_rsi:.1f} trong khoảng {rsi_sell_min}-{rsi_sell_max})")
                    else:
                        filter_status.append(f"❌ RSI Range: {current_rsi:.1f} không trong khoảng {rsi_sell_min}-{rsi_sell_max}")
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần trong khoảng {rsi_sell_min}-{rsi_sell_max}, hiện tại: {current_rsi:.1f})")
                else:
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Doji Candle detected")
            else:
                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Không phải fresh breakout")
        else:
            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Điều kiện cơ bản không đạt")
    
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
        print(f"   📈 H1 Trend: {h1_trend} (EMA{h1_ema_period}: {df_h1.iloc[idx_cur]['ema100']:.2f})")
        if h1_trend_confirmation_required:
            print(f"   📈 H1 Trend Alignment: {'✅ Đồng nhất' if h1_trend == current_trend else '❌ Không đồng nhất'}")
        print(f"   📊 ADX: {adx_value:.1f} (cần >= {adx_min_threshold}) [V2: Yêu cầu ADX >35]")
        print(f"   📊 HA Close: {last_ha['ha_close']:.2f} | HA Open: {last_ha['ha_open']:.2f}")
        print(f"   📊 SMA55 High: {last_ha['sma55_high']:.2f} | SMA55 Low: {last_ha['sma55_low']:.2f}")
        # Get RSI thresholds for display
        rsi_buy_min = config['parameters'].get('rsi_buy_min', 40)
        rsi_buy_max = config['parameters'].get('rsi_buy_max', 60)
        rsi_sell_min = config['parameters'].get('rsi_sell_min', 40)
        rsi_sell_max = config['parameters'].get('rsi_sell_max', 60)
        rsi_extreme_high = config['parameters'].get('rsi_extreme_high', 70)
        rsi_extreme_low = config['parameters'].get('rsi_extreme_low', 30)
        print(f"   📊 RSI: {last_ha['rsi']:.1f} (V2: BUY cần {rsi_buy_min}-{rsi_buy_max}, SELL cần {rsi_sell_min}-{rsi_sell_max}, reject nếu >{rsi_extreme_high} hoặc <{rsi_extreme_low})")
        if current_trend == "BULLISH":
            print(f"   📊 Above Channel: {last_ha['ha_close']:.2f} > {last_ha['sma55_high']:.2f} = {is_above_channel}")
            print(f"   📊 Fresh Breakout: Prev {prev_ha['ha_close']:.2f} <= {prev_ha['sma55_high']:.2f} = {is_fresh_breakout}")
        else:
            print(f"   📊 Below Channel: {last_ha['ha_close']:.2f} < {last_ha['sma55_low']:.2f} = {is_below_channel}")
            print(f"   📊 Fresh Breakout: Prev {prev_ha['ha_close']:.2f} >= {prev_ha['sma55_low']:.2f} = {is_fresh_breakout}")
        
        print(f"\n💡 Tổng số filters đã kiểm tra: {len(filter_status)}")
        print(f"   ✅ PASS: {len([f for f in filter_status if f.startswith('✅')])}")
        print(f"   ❌ FAIL: {len([f for f in filter_status if f.startswith('❌')])}")
        print(f"{'─'*80}\n")

    
    # 4. Execute Trade
    if signal:
        # --- SPAM FILTER: Chặn mở lệnh mới nếu (now - last_trade_time) < 120s (last_trade_time lưu file ổn định) ---
        spam_filter_seconds = config['parameters'].get('spam_filter_seconds', 120)
        last_trade_ts = _get_last_trade_time()
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            current_ts = time.time()
        else:
            t = tick.time
            current_ts = t.timestamp() if isinstance(t, datetime) else float(t)
        if last_trade_ts > 0 and (current_ts - last_trade_ts) < spam_filter_seconds:
            elapsed = current_ts - last_trade_ts
            print(f"   ⏳ Skipping: Last trade {elapsed:.0f}s ago (wait {spam_filter_seconds}s)")
            return error_count, 0

        print(f"🚀 SIGNAL FOUND: {signal} at {price}")
        
        # SL/TP Calculation Logic
        sl_mode = config['parameters'].get('sl_mode', 'fixed')
        reward_ratio = config['parameters'].get('reward_ratio', 1.5)
        
        sl = 0.0
        tp = 0.0
        
        if sl_mode == 'auto_m5':
            # Use previous M5 candle High/Low; buffer và min_dist theo ATR M5 (có min/max)
            prev_m5_high = df_m5.iloc[-2]['high']
            prev_m5_low = df_m5.iloc[-2]['low']
            point = mt5.symbol_info(symbol).point
            # XAUUSD: 1 pip = 0.1 USD, point thường 0.01 -> pip_size = 10*point
            pip_size = (point * 10) if ('XAU' in symbol.upper() or 'GOLD' in symbol.upper()) and point < 0.1 else point

            atr_period_m5 = config['parameters'].get('atr_period', 14)
            df_m5['atr'] = calculate_atr(df_m5, period=atr_period_m5)
            atr_m5 = df_m5.iloc[-2]['atr']
            if pd.isna(atr_m5) or atr_m5 <= 0:
                m5_range = prev_m5_high - prev_m5_low
                atr_m5 = m5_range / atr_period_m5 if m5_range > 0 else 0.1

            atr_buffer_multiplier = config['parameters'].get('atr_buffer_multiplier', 1.5)
            atr_buffer_min_pips = config['parameters'].get('atr_buffer_min_pips', 5)
            atr_buffer_max_pips = config['parameters'].get('atr_buffer_max_pips', 50)
            buffer_pips = (atr_m5 / pip_size) * atr_buffer_multiplier
            buffer_pips = max(atr_buffer_min_pips, min(buffer_pips, atr_buffer_max_pips))
            buffer = buffer_pips * pip_size

            min_sl_distance_pips = config['parameters'].get('min_sl_distance_pips', 10)
            max_sl_distance_pips = config['parameters'].get('max_sl_distance_pips', 200)
            min_dist = min_sl_distance_pips * pip_size
            max_dist = max_sl_distance_pips * pip_size

            if signal == "BUY":
                sl = prev_m5_low - buffer
                risk_dist = price - sl
                if risk_dist < min_dist:
                    sl = price - min_dist
                    risk_dist = min_dist
                elif risk_dist > max_dist:
                    sl = price - max_dist
                    risk_dist = max_dist
                tp = price + (risk_dist * reward_ratio)

            elif signal == "SELL":
                sl = prev_m5_high + buffer
                risk_dist = sl - price
                if risk_dist < min_dist:
                    sl = price + min_dist
                    risk_dist = min_dist
                elif risk_dist > max_dist:
                    sl = price + max_dist
                    risk_dist = max_dist
                tp = price - (risk_dist * reward_ratio)

            print(f"   📏 Auto M5 SL: {sl:.2f} (Prev H/L, buffer={buffer_pips:.1f}p ATR M5) | TP: {tp:.2f} (R:R {reward_ratio})")
            
        else:
            # Fixed Pips (Legacy)
            sl_pips = config['parameters']['sl_pips'] * mt5.symbol_info(symbol).point * 10 
            tp_pips = config['parameters']['tp_pips'] * mt5.symbol_info(symbol).point * 10
            
            sl = price - sl_pips if signal == "BUY" else price + sl_pips
            tp = price + tp_pips if signal == "BUY" else price - tp_pips
            
        # Log signal to DB
        db.log_signal("Strategy_1_Trend_HA", symbol, signal, price, sl, tp, 
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
            "comment": "Strat1_Trend_HA",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            # Cập nhật last_trade_time ổn định (file) để spam filter 120s hoạt động đúng
            tick_after = mt5.symbol_info_tick(symbol)
            if tick_after is not None:
                t = tick_after.time
                ts = t.timestamp() if isinstance(t, datetime) else float(t)
                _set_last_trade_time(ts)
            # Lưu initial SL distance theo ticket cho breakeven/trailing dùng đúng
            si = mt5.symbol_info(symbol)
            pt = si.point if si else 0.01
            pip_sz = pt * 10 if pt < 0.1 else pt
            if "XAU" in symbol.upper() or "GOLD" in symbol.upper():
                pip_sz = pt if pt >= 0.01 else pt * 10
            if pip_sz > 0:
                initial_sl_pips = (price - sl) / pip_sz if signal == "BUY" else (sl - price) / pip_sz
                _save_initial_sl_map(result.order, round(initial_sl_pips, 2))
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
                f"• M5 Trend: {current_trend}\n"
                f"• H1 Trend: {h1_trend} (EMA{h1_ema_period})\n"
                f"• ADX: {adx_value:.1f}\n"
                f"• RSI: {last_ha['rsi']:.1f}"
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
