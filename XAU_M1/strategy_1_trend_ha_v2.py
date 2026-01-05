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
from utils import load_config, connect_mt5, get_data, calculate_heiken_ashi, send_telegram, is_doji, manage_position, get_mt5_error_message, calculate_rsi, calculate_adx, calculate_atr

# Initialize Database
db = Database()

def find_previous_swing_low(df_m1, lookback=20):
    """
    Tìm previous swing low trong lookback period (không bao gồm nến cuối)
    """
    if len(df_m1) < lookback + 1:
        return None
    
    recent_df = df_m1.iloc[-lookback-1:-1]  # Không bao gồm nến cuối
    if len(recent_df) == 0:
        return None
    
    return recent_df['low'].min()

def find_previous_swing_high(df_m1, lookback=20):
    """
    Tìm previous swing high trong lookback period (không bao gồm nến cuối)
    """
    if len(df_m1) < lookback + 1:
        return None
    
    recent_df = df_m1.iloc[-lookback-1:-1]  # Không bao gồm nến cuối
    if len(recent_df) == 0:
        return None
    
    return recent_df['high'].max()

def check_liquidity_sweep_buy(df_m1, atr_val, symbol="XAUUSD", buffer_pips=2):
    """
    BUY - LIQUIDITY SWEEP CHECK (BẮT BUỘC)
    IF current_low < previous_swing_low - buffer
    AND lower_wick >= 1.5 × ATR
    AND close > open
    → BUY_SWEEP_CONFIRMED = TRUE
    """
    if len(df_m1) < 20:
        return False, "Không đủ dữ liệu"
    
    prev_swing_low = find_previous_swing_low(df_m1, lookback=20)
    if prev_swing_low is None:
        return False, "Không tìm thấy previous swing low"
    
    current_candle = df_m1.iloc[-1]
    current_low = current_candle['low']
    
    # Buffer: 2 pips cho XAUUSD (0.2 USD)
    symbol_info = mt5.symbol_info(symbol)
    point = symbol_info.point if symbol_info else 0.01
    buffer = buffer_pips * point * 10  # 2 pips = 0.2 USD cho XAUUSD
    
    lower_wick = min(current_candle['open'], current_candle['close']) - current_low
    
    # Check if swept below previous swing low
    if current_low < (prev_swing_low - buffer):
        # Check lower wick >= 1.5 × ATR
        if lower_wick >= 1.5 * atr_val:
            # Check close > open (bullish candle)
            if current_candle['close'] > current_candle['open']:
                return True, f"Sweep confirmed: Low {current_low:.2f} < {prev_swing_low:.2f}, wick={lower_wick:.2f} >= {1.5 * atr_val:.2f}"
            else:
                return False, f"Sweep low OK nhưng nến không bullish (close <= open)"
        else:
            return False, f"Sweep low OK nhưng wick {lower_wick:.2f} < {1.5 * atr_val:.2f}"
    else:
        return False, f"Chưa sweep: Low {current_low:.2f} >= {prev_swing_low - buffer:.2f}"

def check_liquidity_sweep_sell(df_m1, atr_val, symbol="XAUUSD", buffer_pips=2):
    """
    SELL - LIQUIDITY SWEEP CHECK (BẮT BUỘC)
    IF current_high > previous_swing_high + buffer
    AND upper_wick >= 1.5 × ATR
    AND close < open
    → SELL_SWEEP_CONFIRMED = TRUE
    """
    if len(df_m1) < 20:
        return False, "Không đủ dữ liệu"
    
    prev_swing_high = find_previous_swing_high(df_m1, lookback=20)
    if prev_swing_high is None:
        return False, "Không tìm thấy previous swing high"
    
    current_candle = df_m1.iloc[-1]
    current_high = current_candle['high']
    
    # Buffer: 2 pips cho XAUUSD (0.2 USD)
    symbol_info = mt5.symbol_info(symbol)
    point = symbol_info.point if symbol_info else 0.01
    buffer = buffer_pips * point * 10  # 2 pips = 0.2 USD cho XAUUSD
    
    upper_wick = current_high - max(current_candle['open'], current_candle['close'])
    
    # Check if swept above previous swing high
    if current_high > (prev_swing_high + buffer):
        # Check upper wick >= 1.5 × ATR
        if upper_wick >= 1.5 * atr_val:
            # Check close < open (bearish candle)
            if current_candle['close'] < current_candle['open']:
                return True, f"Sweep confirmed: High {current_high:.2f} > {prev_swing_high:.2f}, wick={upper_wick:.2f} >= {1.5 * atr_val:.2f}"
            else:
                return False, f"Sweep high OK nhưng nến không bearish (close >= open)"
        else:
            return False, f"Sweep high OK nhưng wick {upper_wick:.2f} < {1.5 * atr_val:.2f}"
    else:
        return False, f"Chưa sweep: High {current_high:.2f} <= {prev_swing_high + buffer:.2f}"

def check_displacement_candle(df_m1, atr_val, signal_type):
    """
    DISPLACEMENT CANDLE CHECK
    BUY: breakout_body >= 1.2 × ATR AND close > previous_range_high
    SELL: breakout_body >= 1.2 × ATR AND close < previous_range_low
    """
    if len(df_m1) < 10:
        return False, "Không đủ dữ liệu"
    
    breakout_candle = df_m1.iloc[-1]
    body = abs(breakout_candle['close'] - breakout_candle['open'])
    
    # Get previous range (last 10 candles before current)
    prev_range = df_m1.iloc[-10:-1]
    prev_range_high = prev_range['high'].max()
    prev_range_low = prev_range['low'].min()
    
    if signal_type == "BUY":
        if body >= 1.2 * atr_val and breakout_candle['close'] > prev_range_high:
            return True, f"Displacement confirmed: Body={body:.2f} >= {1.2 * atr_val:.2f}, Close={breakout_candle['close']:.2f} > {prev_range_high:.2f}"
        else:
            return False, f"No displacement: Body={body:.2f} < {1.2 * atr_val:.2f} hoặc Close={breakout_candle['close']:.2f} <= {prev_range_high:.2f}"
    elif signal_type == "SELL":
        if body >= 1.2 * atr_val and breakout_candle['close'] < prev_range_low:
            return True, f"Displacement confirmed: Body={body:.2f} >= {1.2 * atr_val:.2f}, Close={breakout_candle['close']:.2f} < {prev_range_low:.2f}"
        else:
            return False, f"No displacement: Body={body:.2f} < {1.2 * atr_val:.2f} hoặc Close={breakout_candle['close']:.2f} >= {prev_range_low:.2f}"
    return False, "Signal type không hợp lệ"

def check_chop_range(df_m1, atr_val, lookback=10, body_threshold=0.5, overlap_threshold=0.7):
    """
    CHOP / RANGE FILTER
    IF last 10 candles:
    - body_avg < 0.5 × ATR
    - overlap > 70%
    → MARKET = CHOP → NO TRADE
    """
    if len(df_m1) < lookback:
        return False, "Không đủ dữ liệu"
    
    recent_candles = df_m1.iloc[-lookback:]
    
    # Tính body trung bình
    bodies = abs(recent_candles['close'] - recent_candles['open'])
    body_avg = bodies.mean()
    
    # Tính overlap (tỷ lệ nến chồng lên nhau)
    overlaps = 0
    total_pairs = 0
    for i in range(len(recent_candles) - 1):
        candle1 = recent_candles.iloc[i]
        candle2 = recent_candles.iloc[i + 1]
        
        # Tính overlap range
        range1 = (candle1['low'], candle1['high'])
        range2 = (candle2['low'], candle2['high'])
        
        overlap_low = max(range1[0], range2[0])
        overlap_high = min(range1[1], range2[1])
        
        if overlap_low < overlap_high:
            overlap_size = overlap_high - overlap_low
            range1_size = range1[1] - range1[0]
            range2_size = range2[1] - range2[0]
            avg_range = (range1_size + range2_size) / 2
            
            if avg_range > 0:
                overlap_ratio = overlap_size / avg_range
                overlaps += overlap_ratio
                total_pairs += 1
    
    avg_overlap = overlaps / total_pairs if total_pairs > 0 else 0
    
    # Kiểm tra điều kiện chop
    body_condition = body_avg < (body_threshold * atr_val)
    overlap_condition = avg_overlap > overlap_threshold
    
    if body_condition and overlap_condition:
        return True, f"CHOP: body_avg={body_avg:.2f} < {body_threshold * atr_val:.2f}, overlap={avg_overlap:.1%} > {overlap_threshold:.1%}"
    return False, f"Not CHOP: body_avg={body_avg:.2f}, overlap={avg_overlap:.1%}"

def strategy_1_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    # 2. Check Global Max Positions & Manage Existing
    # Lấy tất cả positions của symbol, sau đó filter theo magic để chỉ xử lý positions do bot này mở
    all_positions = mt5.positions_get(symbol=symbol)
    positions = [pos for pos in (all_positions or []) if pos.magic == magic]  # Chỉ lấy positions do bot này mở
    
    if positions:
        # Manage Trailing SL for all open positions of this strategy
        for pos in positions:
            manage_position(pos.ticket, symbol, magic, config)
            
        if len(positions) >= max_positions:
            # Silent return to avoid spam
            return error_count, 0

    # 1. Get Data (M1, M5, and H1 for trend)
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 200)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 200)
    df_h1 = get_data(symbol, mt5.TIMEFRAME_H1, 200)  # V3: Thêm H1 cho trend confirmation
    
    if df_m1 is None or df_m5 is None or df_h1 is None: 
        return error_count, 0

    # 2. Calculate Indicators
    # Trend Filter: EMA 200 on M5 (V2: Fixed - dùng EMA thực sự)
    df_m5['ema200'] = df_m5['close'].ewm(span=200, adjust=False).mean()  # V2: EMA thực sự
    df_m5['ema50'] = df_m5['close'].ewm(span=50, adjust=False).mean()  # V3: Thêm EMA50 cho trend confirmation
    current_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"
    
    # V3: EMA50 > EMA200 trên M5 (trend confirmation mạnh hơn)
    ema50_m5 = df_m5.iloc[-1]['ema50']
    ema200_m5 = df_m5.iloc[-1]['ema200']
    if current_trend == "BULLISH":
        if ema50_m5 <= ema200_m5:
            print(f"❌ M5 Trend Filter: EMA50 ({ema50_m5:.2f}) <= EMA200 ({ema200_m5:.2f}) - Trend không đủ mạnh")
            return error_count, 0
    else:  # BEARISH
        if ema50_m5 >= ema200_m5:
            print(f"❌ M5 Trend Filter: EMA50 ({ema50_m5:.2f}) >= EMA200 ({ema200_m5:.2f}) - Trend không đủ mạnh")
            return error_count, 0
    print(f"✅ M5 Trend Filter: EMA50 ({ema50_m5:.2f}) {'>' if current_trend == 'BULLISH' else '<'} EMA200 ({ema200_m5:.2f}) - Trend mạnh")
    
    # V3: H1 Trend Confirmation
    df_h1['ema200'] = df_h1['close'].ewm(span=200, adjust=False).mean()
    h1_trend = "BULLISH" if df_h1.iloc[-1]['close'] > df_h1.iloc[-1]['ema200'] else "BEARISH"
    if h1_trend != current_trend:
        print(f"❌ H1 Trend Confirmation: H1 Trend ({h1_trend}) != M5 Trend ({current_trend}) - Không đồng nhất")
        return error_count, 0
    print(f"✅ H1 Trend Confirmation: H1 Trend ({h1_trend}) == M5 Trend ({current_trend}) - Đồng nhất")
    
    # V3: ADX Filter - Tăng threshold từ 20 lên 25 (default)
    adx_period = config['parameters'].get('adx_period', 14)
    adx_min_threshold = config['parameters'].get('adx_min_threshold', 25)  # V3: Tăng từ 20 lên 25
    df_m5 = calculate_adx(df_m5, period=adx_period)
    adx_value = df_m5.iloc[-1]['adx']
    if pd.isna(adx_value) or adx_value < adx_min_threshold:
        print(f"❌ ADX Filter: ADX={adx_value:.1f} < {adx_min_threshold} (No trend, skipping)")
        return error_count, 0
    print(f"✅ ADX Filter: ADX={adx_value:.1f} >= {adx_min_threshold} (Trend confirmed)")

    # Channel: 55 SMA High/Low on M1
    df_m1['sma55_high'] = df_m1['high'].rolling(window=55).mean()
    df_m1['sma55_low'] = df_m1['low'].rolling(window=55).mean()
    
    # Volume MA for confirmation
    df_m1['vol_ma'] = df_m1['tick_volume'].rolling(window=10).mean()
    
    # Heiken Ashi
    ha_df = calculate_heiken_ashi(df_m1)
    
    # RSI 14 (Added Filter)
    ha_df['rsi'] = calculate_rsi(df_m1['close'], period=14)
    
    # V2: Calculate ATR for CHOP detection and SL buffer
    atr_period = config['parameters'].get('atr_period', 14)
    df_m1['atr'] = calculate_atr(df_m1, period=atr_period)
    atr_val = df_m1.iloc[-1]['atr']
    if pd.isna(atr_val) or atr_val <= 0:
        # Fallback: use recent range
        recent_range = df_m1.iloc[-atr_period:]['high'].max() - df_m1.iloc[-atr_period:]['low'].min()
        atr_val = recent_range / atr_period if recent_range > 0 else 0.1
    
    # V2: CHOP/RANGE Filter (BẮT BUỘC)
    chop_lookback = config['parameters'].get('chop_lookback', 10)
    chop_body_threshold = config['parameters'].get('chop_body_threshold', 0.5)
    chop_overlap_threshold = config['parameters'].get('chop_overlap_threshold', 0.7)
    is_chop, chop_msg = check_chop_range(df_m1, atr_val, lookback=chop_lookback, 
                                         body_threshold=chop_body_threshold, 
                                         overlap_threshold=chop_overlap_threshold)
    if is_chop:
        print(f"❌ CHOP Filter: {chop_msg} (Skipping)")
        return error_count, 0
    print(f"✅ CHOP Filter: {chop_msg}")

    last_ha = ha_df.iloc[-1]
    prev_ha = ha_df.iloc[-2]

    # 3. Check Signals
    signal = None
    price = mt5.symbol_info_tick(symbol).ask if current_trend == "BULLISH" else mt5.symbol_info_tick(symbol).bid
    
    # Detailed Logging
    print(f"\n{'='*80}")
    print(f"📊 [STRATEGY 1: TREND HA ANALYSIS] {symbol}")
    print(f"{'='*80}")
    print(f"💱 Price: {price:.2f} | Trend (M5): {current_trend} | ADX: {adx_value:.1f} | RSI: {last_ha['rsi']:.1f}")
    print(f"   HA Close: {last_ha['ha_close']:.2f} | HA Open: {last_ha['ha_open']:.2f}")
    print(f"   SMA55 High: {last_ha['sma55_high']:.2f} | SMA55 Low: {last_ha['sma55_low']:.2f}")
    print(f"   ATR: {atr_val:.2f}")
    
    # Track all filter status
    filter_status = []
    
    # BUY SETUP
    if current_trend == "BULLISH":
        is_green = last_ha['ha_close'] > last_ha['ha_open']
        is_above_channel = last_ha['ha_close'] > last_ha['sma55_high']
        is_fresh_breakout = prev_ha['ha_close'] <= prev_ha['sma55_high']
        is_solid_candle = not is_doji(last_ha, threshold=0.2) # Require body > 20% of range for HA

        filter_status.append(f"✅ M5 Trend: BULLISH")
        filter_status.append(f"{'✅' if is_green else '❌'} HA Candle: {'Green' if is_green else 'Red'}")
        filter_status.append(f"{'✅' if is_above_channel else '❌'} Above Channel: {last_ha['ha_close']:.2f} > {last_ha['sma55_high']:.2f}")
        
        if is_green and is_above_channel:
            filter_status.append(f"{'✅' if is_fresh_breakout else '❌'} Fresh Breakout: Prev HA Close {prev_ha['ha_close']:.2f} <= SMA55 High {prev_ha['sma55_high']:.2f}")
            if is_fresh_breakout:
                filter_status.append(f"{'✅' if is_solid_candle else '❌'} Solid Candle: {'Not Doji' if is_solid_candle else 'Doji detected (Indecision)'}")
                if is_solid_candle:
                    # V3: Improved RSI filter - Tăng threshold từ 55 lên 60 (default)
                    rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 60)  # V3: Tăng từ 55 lên 60
                    filter_status.append(f"{'✅' if last_ha['rsi'] > rsi_buy_threshold else '❌'} RSI > {rsi_buy_threshold}: {last_ha['rsi']:.1f} (V3: stricter)")
                    if last_ha['rsi'] > rsi_buy_threshold:
                        # V3: Liquidity Sweep Check (BẮT BUỘC)
                        has_sweep, sweep_msg = check_liquidity_sweep_buy(df_m1, atr_val, symbol=symbol, buffer_pips=2)
                        filter_status.append(f"{'✅' if has_sweep else '❌'} Liquidity Sweep: {sweep_msg}")
                        if has_sweep:
                            # V3: Displacement Candle Check
                            has_displacement, displacement_msg = check_displacement_candle(df_m1, atr_val, "BUY")
                            filter_status.append(f"{'✅' if has_displacement else '❌'} Displacement Candle: {displacement_msg}")
                            if has_displacement:
                                # V3: Volume Confirmation
                                current_volume = df_m1.iloc[-1]['tick_volume']
                                vol_ma = df_m1.iloc[-1]['vol_ma']
                                volume_multiplier = config['parameters'].get('volume_confirmation_multiplier', 1.3)
                                has_volume_confirmation = current_volume > (vol_ma * volume_multiplier)
                                filter_status.append(f"{'✅' if has_volume_confirmation else '❌'} Volume Confirmation: {current_volume:.0f} > {vol_ma * volume_multiplier:.0f} ({volume_multiplier}x avg)")
                                if has_volume_confirmation:
                                    # V3: Confirmation check - đợi 2-3 nến sau breakout (tăng từ 1 nến)
                                    confirmation_enabled = config['parameters'].get('confirmation_enabled', True)
                                    confirmation_candles = config['parameters'].get('confirmation_candles', 2)  # V3: Tăng từ 1 lên 2
                                    if confirmation_enabled and len(ha_df) >= confirmation_candles + 1:
                                        breakout_level = last_ha['sma55_high']
                                        # Kiểm tra các nến confirmation (từ nến -1 đến -confirmation_candles)
                                        all_confirmed = True
                                        for i in range(1, confirmation_candles + 1):
                                            if len(ha_df) >= i + 1:
                                                conf_candle = ha_df.iloc[-i]
                                                if conf_candle['ha_close'] <= breakout_level:
                                                    all_confirmed = False
                                                    break
                                        
                                        # V3: Kiểm tra false breakout - nến cuối cùng không đóng ngược lại channel
                                        if all_confirmed:
                                            latest_candle = ha_df.iloc[-1]
                                            if latest_candle['ha_close'] > breakout_level:
                                                signal = "BUY"
                                                print(f"\n✅ [SIGNAL FOUND] BUY - Tất cả điều kiện đạt (V3: với {confirmation_candles} nến confirmation + Liquidity Sweep + Displacement)!")
                                            else:
                                                print(f"\n❌ [FALSE BREAKOUT] - Nến cuối đóng ngược lại channel ({latest_candle['ha_close']:.2f} <= {breakout_level:.2f})")
                                        else:
                                            print(f"\n⏳ [CHỜ CONFIRMATION] - Cần {confirmation_candles} nến confirmation, hiện tại chưa đủ")
                                    else:
                                        signal = "BUY"
                                        print("\n✅ [SIGNAL FOUND] BUY - Tất cả điều kiện đạt!")
                                else:
                                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Volume không đạt (cần > {volume_multiplier}x average)")
                            else:
                                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - {displacement_msg}")
                        else:
                            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - {sweep_msg}")
                    else:
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần > {rsi_buy_threshold}, hiện tại: {last_ha['rsi']:.1f})")
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
        is_solid_candle = not is_doji(last_ha, threshold=0.2)

        filter_status.append(f"✅ M5 Trend: BEARISH")
        filter_status.append(f"{'✅' if is_red else '❌'} HA Candle: {'Red' if is_red else 'Green'}")
        filter_status.append(f"{'✅' if is_below_channel else '❌'} Below Channel: {last_ha['ha_close']:.2f} < {last_ha['sma55_low']:.2f}")
        
        if is_red and is_below_channel:
            filter_status.append(f"{'✅' if is_fresh_breakout else '❌'} Fresh Breakout: Prev HA Close {prev_ha['ha_close']:.2f} >= SMA55 Low {prev_ha['sma55_low']:.2f}")
            if is_fresh_breakout:
                filter_status.append(f"{'✅' if is_solid_candle else '❌'} Solid Candle: {'Not Doji' if is_solid_candle else 'Doji detected (Indecision)'}")
                if is_solid_candle:
                    # V3: Improved RSI filter - Giảm threshold từ 45 xuống 40 (default)
                    rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 40)  # V3: Giảm từ 45 xuống 40
                    filter_status.append(f"{'✅' if last_ha['rsi'] < rsi_sell_threshold else '❌'} RSI < {rsi_sell_threshold}: {last_ha['rsi']:.1f} (V3: stricter)")
                    if last_ha['rsi'] < rsi_sell_threshold:
                        # V3: Liquidity Sweep Check (BẮT BUỘC)
                        has_sweep, sweep_msg = check_liquidity_sweep_sell(df_m1, atr_val, symbol=symbol, buffer_pips=2)
                        filter_status.append(f"{'✅' if has_sweep else '❌'} Liquidity Sweep: {sweep_msg}")
                        if has_sweep:
                            # V3: Displacement Candle Check
                            has_displacement, displacement_msg = check_displacement_candle(df_m1, atr_val, "SELL")
                            filter_status.append(f"{'✅' if has_displacement else '❌'} Displacement Candle: {displacement_msg}")
                            if has_displacement:
                                # V3: Volume Confirmation
                                current_volume = df_m1.iloc[-1]['tick_volume']
                                vol_ma = df_m1.iloc[-1]['vol_ma']
                                volume_multiplier = config['parameters'].get('volume_confirmation_multiplier', 1.3)
                                has_volume_confirmation = current_volume > (vol_ma * volume_multiplier)
                                filter_status.append(f"{'✅' if has_volume_confirmation else '❌'} Volume Confirmation: {current_volume:.0f} > {vol_ma * volume_multiplier:.0f} ({volume_multiplier}x avg)")
                                if has_volume_confirmation:
                                    # V3: Confirmation check - đợi 2-3 nến sau breakout (tăng từ 1 nến)
                                    confirmation_enabled = config['parameters'].get('confirmation_enabled', True)
                                    confirmation_candles = config['parameters'].get('confirmation_candles', 2)  # V3: Tăng từ 1 lên 2
                                    if confirmation_enabled and len(ha_df) >= confirmation_candles + 1:
                                        breakout_level = last_ha['sma55_low']
                                        # Kiểm tra các nến confirmation (từ nến -1 đến -confirmation_candles)
                                        all_confirmed = True
                                        for i in range(1, confirmation_candles + 1):
                                            if len(ha_df) >= i + 1:
                                                conf_candle = ha_df.iloc[-i]
                                                if conf_candle['ha_close'] >= breakout_level:
                                                    all_confirmed = False
                                                    break
                                        
                                        # V3: Kiểm tra false breakout - nến cuối cùng không đóng ngược lại channel
                                        if all_confirmed:
                                            latest_candle = ha_df.iloc[-1]
                                            if latest_candle['ha_close'] < breakout_level:
                                                signal = "SELL"
                                                print(f"\n✅ [SIGNAL FOUND] SELL - Tất cả điều kiện đạt (V3: với {confirmation_candles} nến confirmation + Liquidity Sweep + Displacement)!")
                                            else:
                                                print(f"\n❌ [FALSE BREAKOUT] - Nến cuối đóng ngược lại channel ({latest_candle['ha_close']:.2f} >= {breakout_level:.2f})")
                                        else:
                                            print(f"\n⏳ [CHỜ CONFIRMATION] - Cần {confirmation_candles} nến confirmation, hiện tại chưa đủ")
                                    else:
                                        signal = "SELL"
                                        print("\n✅ [SIGNAL FOUND] SELL - Tất cả điều kiện đạt!")
                                else:
                                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Volume không đạt (cần > {volume_multiplier}x average)")
                            else:
                                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - {displacement_msg}")
                        else:
                            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - {sweep_msg}")
                    else:
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần < {rsi_sell_threshold}, hiện tại: {last_ha['rsi']:.1f})")
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
        print(f"   📊 HA Close: {last_ha['ha_close']:.2f} | HA Open: {last_ha['ha_open']:.2f}")
        print(f"   📊 SMA55 High: {last_ha['sma55_high']:.2f} | SMA55 Low: {last_ha['sma55_low']:.2f}")
        rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 55)
        rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 45)
        print(f"   📊 RSI: {last_ha['rsi']:.1f} (V3: BUY cần > {rsi_buy_threshold}, SELL cần < {rsi_sell_threshold})")
        print(f"   📊 ADX: {adx_value:.1f} (cần >= {adx_min_threshold}) [V3: Tăng từ 20 lên 25]")
        print(f"   📊 H1 Trend: {h1_trend} (phải == M5 Trend: {current_trend})")
        print(f"   📊 EMA50 M5: {ema50_m5:.2f} | EMA200 M5: {ema200_m5:.2f}")
        print(f"   📊 ATR: {atr_val:.2f}")
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
        # --- SPAM FILTER: V2 - Check if we traded in the last N seconds (configurable) ---
        spam_filter_seconds = config['parameters'].get('spam_filter_seconds', 300)
        # Chỉ lấy positions do bot này mở (filter theo magic)
        all_strat_positions = mt5.positions_get(symbol=symbol)
        strat_positions = [pos for pos in (all_strat_positions or []) if pos.magic == magic]
        if strat_positions:
            strat_positions = sorted(strat_positions, key=lambda x: x.time, reverse=True)
            last_trade_time = strat_positions[0].time
            current_server_time = mt5.symbol_info_tick(symbol).time
            
            # Convert to timestamp if needed
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
                print(f"   ⏳ Skipping: Trade already taken {time_since_last:.0f}s ago (V2: Wait {spam_filter_seconds}s)")
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
            
            # V3: Calculate ATR on M5 for better buffer - Tăng multiplier từ 1.5x lên 2.0x (default)
            atr_period_m5 = config['parameters'].get('atr_period', 14)
            atr_buffer_multiplier = config['parameters'].get('atr_buffer_multiplier', 2.0)  # V3: Tăng từ 1.5 lên 2.0
            df_m5['atr'] = calculate_atr(df_m5, period=atr_period_m5)
            atr_m5 = df_m5.iloc[-2]['atr']
            if pd.isna(atr_m5) or atr_m5 <= 0:
                # Fallback: use M5 range
                m5_range = prev_m5_high - prev_m5_low
                atr_m5 = m5_range / atr_period_m5 if m5_range > 0 else 0.1
            
            # V3: Buffer dựa trên ATR - Tăng từ 1.5x lên 2.0x (có thể config lên 2.5x)
            buffer = atr_buffer_multiplier * atr_m5
            print(f"   📊 M5 ATR: {atr_m5:.2f} | Buffer: {buffer:.2f} ({atr_buffer_multiplier}x ATR) [V3: Tăng từ 1.5x]")
            
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
                
            print(f"   📏 Auto M5 SL: {sl:.2f} (Prev High/Low ± {buffer:.2f} buffer) | TP: {tp:.2f} (R:R {reward_ratio})")
            
        else:
            # Fixed Pips (Legacy)
            sl_pips = config['parameters']['sl_pips'] * mt5.symbol_info(symbol).point * 10 
            tp_pips = config['parameters']['tp_pips'] * mt5.symbol_info(symbol).point * 10
            
            sl = price - sl_pips if signal == "BUY" else price + sl_pips
            tp = price + tp_pips if signal == "BUY" else price - tp_pips
            
        # Log signal to DB
        db.log_signal("Strategy_1_Trend_HA_V2", symbol, signal, price, sl, tp, 
                      {"trend": current_trend, "ha_close": float(last_ha['ha_close']), "sl_mode": sl_mode, "rsi": float(last_ha['rsi']), "adx": float(adx_value), "atr": float(atr_val)}, 
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
            "comment": "Strat1_HA_V2",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(result.order, "Strategy_1_Trend_HA_V2", symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
            
            # Detailed Telegram Message
            msg = (
                f"✅ <b>Strat 1: Trend HA V2 Executed</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"👤 <b>Account:</b> {config['account']}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal})\n"
                f"💵 <b>Price:</b> {price:.2f}\n"
                f"🛑 <b>SL:</b> {sl:.2f} | 🎯 <b>TP:</b> {tp:.2f}\n"
                f"📊 <b>Indicators:</b>\n"
                f"• Trend: {current_trend}\n"
                f"• ADX: {adx_value:.1f} (>= 25 ✅) [V3: Tăng từ 20]\n"
                f"• RSI: {last_ha['rsi']:.1f} (V3: {'> 60' if signal == 'BUY' else '< 40'} ✅)\n"
                f"• H1 Trend: {h1_trend} (== M5: {current_trend} ✅)\n"
                f"• EMA50/200 M5: {ema50_m5:.2f}/{ema200_m5:.2f} ✅\n"
                f"• Liquidity Sweep: PASS ✅\n"
                f"• Displacement Candle: PASS ✅\n"
                f"• ATR: {atr_val:.2f}\n"
                f"• CHOP Filter: PASS ✅"
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
    config_path = os.path.join(script_dir, "configs", "config_1_v2.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 1: Trend HA V3 - Started")
        print("📋 V3 Improvements (dựa trên phân tích lệnh thua):")
        print("   ✅ EMA200 calculation fixed (dùng EMA thực sự)")
        print("   ✅ ADX filter increased (>= 25, từ 20)")
        print("   ✅ RSI filter stricter (> 60 / < 40, từ > 55 / < 45)")
        print("   ✅ CHOP/RANGE filter added")
        print("   ✅ SL buffer increased (2.0x ATR, từ 1.5x)")
        print("   ✅ Confirmation check improved (2-3 nến, từ 1 nến)")
        print("   ✅ H1 Trend confirmation added")
        print("   ✅ EMA50 > EMA200 trên M5 added")
        print("   ✅ Liquidity Sweep check added")
        print("   ✅ Displacement Candle check added")
        print("   ✅ Volume confirmation added (1.3x average)")
        print("   ✅ False breakout detection added")
        print("   ✅ Spam filter increased (5 minutes)")
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
