"""
Review điều kiện bot Strategy_1_Trend_HA_V2
So sánh điều kiện trong bot với điều kiện trong analyze_losses
Tìm các điều kiện có thể quá strict khiến bot không vào lệnh
"""

import os
import sys
sys.path.append('..')
from utils import load_config, connect_mt5, get_data, calculate_heiken_ashi, is_doji, calculate_rsi, calculate_adx, calculate_atr
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import MetaTrader5 as mt5

def find_previous_swing_low(df_m1, lookback=20):
    """Tìm previous swing low"""
    if len(df_m1) < lookback + 1:
        return None
    recent_df = df_m1.iloc[-lookback-1:-1]
    if len(recent_df) == 0:
        return None
    return recent_df['low'].min()

def find_previous_swing_high(df_m1, lookback=20):
    """Tìm previous swing high"""
    if len(df_m1) < lookback + 1:
        return None
    recent_df = df_m1.iloc[-lookback-1:-1]
    if len(recent_df) == 0:
        return None
    return recent_df['high'].max()

def check_liquidity_sweep_buy(df_m1, atr_val, symbol="EURUSD", buffer_pips=2):
    """BUY - LIQUIDITY SWEEP CHECK"""
    if len(df_m1) < 20:
        return False, "Không đủ dữ liệu"
    
    prev_swing_low = find_previous_swing_low(df_m1, lookback=20)
    if prev_swing_low is None:
        return False, "Không tìm thấy previous swing low"
    
    current_candle = df_m1.iloc[-1]
    current_low = current_candle['low']
    
    symbol_info = mt5.symbol_info(symbol)
    point = symbol_info.point if symbol_info else 0.01
    buffer = buffer_pips * point * 10
    
    lower_wick = min(current_candle['open'], current_candle['close']) - current_low
    
    if current_low < (prev_swing_low - buffer):
        if lower_wick >= 1.5 * atr_val:
            if current_candle['close'] > current_candle['open']:
                return True, f"Sweep confirmed"
            else:
                return False, f"Sweep low OK nhưng nến không bullish"
        else:
            return False, f"Sweep low OK nhưng wick {lower_wick:.2f} < {1.5 * atr_val:.2f}"
    else:
        return False, f"Chưa sweep: Low {current_low:.2f} >= {prev_swing_low - buffer:.2f}"

def check_liquidity_sweep_sell(df_m1, atr_val, symbol="EURUSD", buffer_pips=2):
    """SELL - LIQUIDITY SWEEP CHECK"""
    if len(df_m1) < 20:
        return False, "Không đủ dữ liệu"
    
    prev_swing_high = find_previous_swing_high(df_m1, lookback=20)
    if prev_swing_high is None:
        return False, "Không tìm thấy previous swing high"
    
    current_candle = df_m1.iloc[-1]
    current_high = current_candle['high']
    
    symbol_info = mt5.symbol_info(symbol)
    point = symbol_info.point if symbol_info else 0.01
    buffer = buffer_pips * point * 10
    
    upper_wick = current_high - max(current_candle['open'], current_candle['close'])
    
    if current_high > (prev_swing_high + buffer):
        if upper_wick >= 1.5 * atr_val:
            if current_candle['close'] < current_candle['open']:
                return True, f"Sweep confirmed"
            else:
                return False, f"Sweep high OK nhưng nến không bearish"
        else:
            return False, f"Sweep high OK nhưng wick {upper_wick:.2f} < {1.5 * atr_val:.2f}"
    else:
        return False, f"Chưa sweep: High {current_high:.2f} <= {prev_swing_high + buffer:.2f}"

def check_displacement_candle(df_m1, atr_val, signal_type):
    """DISPLACEMENT CANDLE CHECK"""
    if len(df_m1) < 10:
        return False, "Không đủ dữ liệu"
    
    breakout_candle = df_m1.iloc[-1]
    body = abs(breakout_candle['close'] - breakout_candle['open'])
    
    prev_range = df_m1.iloc[-10:-1]
    prev_range_high = prev_range['high'].max()
    prev_range_low = prev_range['low'].min()
    
    if signal_type == "BUY":
        if body >= 1.2 * atr_val and breakout_candle['close'] > prev_range_high:
            return True, f"Displacement confirmed"
        else:
            return False, f"No displacement: Body={body:.2f} < {1.2 * atr_val:.2f} hoặc Close <= {prev_range_high:.2f}"
    elif signal_type == "SELL":
        if body >= 1.2 * atr_val and breakout_candle['close'] < prev_range_low:
            return True, f"Displacement confirmed"
        else:
            return False, f"No displacement: Body={body:.2f} < {1.2 * atr_val:.2f} hoặc Close >= {prev_range_low:.2f}"
    return False, "Signal type không hợp lệ"

def check_chop_range(df_m1, atr_val, lookback=10, body_threshold=0.5, overlap_threshold=0.7):
    """CHOP / RANGE FILTER"""
    if len(df_m1) < lookback:
        return False, "Không đủ dữ liệu"
    
    recent_candles = df_m1.iloc[-lookback:]
    
    bodies = abs(recent_candles['close'] - recent_candles['open'])
    body_avg = bodies.mean()
    
    overlaps = 0
    total_pairs = 0
    for i in range(len(recent_candles) - 1):
        candle1 = recent_candles.iloc[i]
        candle2 = recent_candles.iloc[i + 1]
        
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
    
    body_condition = body_avg < (body_threshold * atr_val)
    overlap_condition = avg_overlap > overlap_threshold
    
    if body_condition and overlap_condition:
        return True, f"CHOP detected"
    return False, f"Not CHOP"

def check_trading_session(config):
    """Check if current time is within allowed trading hours"""
    allowed_sessions = config['parameters'].get('allowed_sessions', "08:00-22:00")
    if allowed_sessions == "ALL":
        return True, "All sessions allowed"
    
    try:
        start_str, end_str = allowed_sessions.split('-')
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
        
        symbol = config['symbol']
        current_time = mt5.symbol_info_tick(symbol).time
        if isinstance(current_time, (int, float)):
             current_dt = datetime.fromtimestamp(current_time)
        else:
             current_dt = current_time
             
        current_time_time = current_dt.time()
        
        if start_time <= end_time:
            if start_time <= current_time_time <= end_time:
                return True, f"In session ({start_str}-{end_str})"
            else:
                return False, f"Out of session ({start_str}-{end_str}), Current: {current_time_time}"
        else:
            if current_time_time >= start_time or current_time_time <= end_time:
                 return True, f"In session ({start_str}-{end_str})"
            else:
                 return False, f"Out of session ({start_str}-{end_str}), Current: {current_time_time}"
                 
    except Exception as e:
        return True, "Session check skipped (error)"

def review_conditions():
    """
    Review tất cả điều kiện bot và so sánh với analyze_losses
    """
    print(f"\n{'='*100}")
    print(f"REVIEW DIEU KIEN BOT - Strategy_1_Trend_HA_V2")
    print(f"{'='*100}\n")
    
    # Load config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_1_v2.json")
    config = load_config(config_path)
    
    if not config:
        print(f"[ERROR] Khong the load config")
        return
    
    # Connect MT5
    if not connect_mt5(config):
        print(f"[ERROR] Khong the ket noi MT5")
        return
    
    symbol = config['symbol']
    
    # Get current data
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 200)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 200)
    df_h1 = get_data(symbol, mt5.TIMEFRAME_H1, 200)
    
    if df_m1 is None or df_m5 is None or df_h1 is None:
        print(f"[ERROR] Khong the lay du lieu")
        mt5.shutdown()
        return
    
    # Calculate indicators
    df_m5['ema200'] = df_m5['close'].ewm(span=200, adjust=False).mean()
    df_m5['ema50'] = df_m5['close'].ewm(span=50, adjust=False).mean()
    current_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"
    
    df_h1['ema200'] = df_h1['close'].ewm(span=200, adjust=False).mean()
    h1_trend = "BULLISH" if df_h1.iloc[-1]['close'] > df_h1.iloc[-1]['ema200'] else "BEARISH"
    
    adx_period = config['parameters'].get('adx_period', 14)
    adx_min_threshold = config['parameters'].get('adx_min_threshold', 25)
    df_m5 = calculate_adx(df_m5, period=adx_period)
    adx_value = df_m5.iloc[-1]['adx']
    
    df_m1['sma55_high'] = df_m1['high'].rolling(window=55).mean()
    df_m1['sma55_low'] = df_m1['low'].rolling(window=55).mean()
    df_m1['vol_ma'] = df_m1['tick_volume'].rolling(window=10).mean()
    
    ha_df = calculate_heiken_ashi(df_m1)
    ha_df['rsi'] = calculate_rsi(df_m1['close'], period=14)
    
    atr_period = config['parameters'].get('atr_period', 14)
    df_m1['atr'] = calculate_atr(df_m1, period=atr_period)
    atr_val = df_m1.iloc[-1]['atr']
    if pd.isna(atr_val) or atr_val <= 0:
        recent_range = df_m1.iloc[-atr_period:]['high'].max() - df_m1.iloc[-atr_period:]['low'].min()
        atr_val = recent_range / atr_period if recent_range > 0 else 0.1
    
    last_ha = ha_df.iloc[-1]
    prev_ha = ha_df.iloc[-2]
    
    # Print current values
    print(f"[INFO] Gia tri hien tai:")
    print(f"   Price: {df_m1.iloc[-1]['close']:.2f}")
    print(f"   M5 Trend: {current_trend}")
    print(f"   H1 Trend: {h1_trend}")
    print(f"   EMA50 M5: {df_m5.iloc[-1]['ema50']:.2f}")
    print(f"   EMA200 M5: {df_m5.iloc[-1]['ema200']:.2f}")
    print(f"   ADX: {adx_value:.1f}")
    print(f"   RSI: {last_ha['rsi']:.1f}")
    print(f"   ATR: {atr_val:.2f}")
    print()
    
    # Review từng điều kiện
    print(f"{'='*100}")
    print(f"PHAN TICH TUNG DIEU KIEN")
    print(f"{'='*100}\n")
    
    conditions_status = []
    
    # 1. Session Filter
    is_in_session, session_msg = check_trading_session(config)
    conditions_status.append({
        'name': 'Session Filter',
        'required': True,
        'status': is_in_session,
        'message': session_msg,
        'version': 'V4',
        'strict_level': 'MEDIUM'
    })
    
    # 2. M5 Trend (EMA200)
    ema50_m5 = df_m5.iloc[-1]['ema50']
    ema200_m5 = df_m5.iloc[-1]['ema200']
    m5_trend_ok = current_trend in ["BULLISH", "BEARISH"]
    conditions_status.append({
        'name': 'M5 Trend (EMA200)',
        'required': True,
        'status': m5_trend_ok,
        'message': f"M5 Trend: {current_trend}",
        'version': 'V1',
        'strict_level': 'LOW'
    })
    
    # 3. EMA50 > EMA200 trên M5 (V3 - MỚI)
    if current_trend == "BULLISH":
        ema50_ok = ema50_m5 > ema200_m5
        ema50_msg = f"EMA50 ({ema50_m5:.2f}) > EMA200 ({ema200_m5:.2f})"
    else:
        ema50_ok = ema50_m5 < ema200_m5
        ema50_msg = f"EMA50 ({ema50_m5:.2f}) < EMA200 ({ema200_m5:.2f})"
    
    conditions_status.append({
        'name': 'EMA50 vs EMA200 M5',
        'required': True,
        'status': ema50_ok,
        'message': ema50_msg,
        'version': 'V3 (MỚI)',
        'strict_level': 'HIGH',
        'note': 'Điều kiện V3 mới - có thể quá strict'
    })
    
    # 4. H1 Trend Confirmation (V3 - MỚI)
    h1_trend_ok = h1_trend == current_trend
    conditions_status.append({
        'name': 'H1 Trend == M5 Trend',
        'required': True,
        'status': h1_trend_ok,
        'message': f"H1 Trend ({h1_trend}) == M5 Trend ({current_trend})",
        'version': 'V3 (MỚI)',
        'strict_level': 'HIGH',
        'note': 'Điều kiện V3 mới - có thể quá strict'
    })
    
    # 5. ADX Filter
    adx_ok = pd.notna(adx_value) and adx_value >= adx_min_threshold
    conditions_status.append({
        'name': f'ADX >= {adx_min_threshold}',
        'required': True,
        'status': adx_ok,
        'message': f"ADX={adx_value:.1f} >= {adx_min_threshold}",
        'version': 'V2 (Tăng từ 20 lên 25)',
        'strict_level': 'MEDIUM',
        'note': 'V3 tăng từ 20 lên 25 - strict hơn'
    })
    
    # 6. CHOP Filter
    chop_lookback = config['parameters'].get('chop_lookback', 10)
    chop_body_threshold = config['parameters'].get('chop_body_threshold', 0.5)
    chop_overlap_threshold = config['parameters'].get('chop_overlap_threshold', 0.7)
    is_chop, chop_msg = check_chop_range(df_m1, atr_val, lookback=chop_lookback, 
                                         body_threshold=chop_body_threshold, 
                                         overlap_threshold=chop_overlap_threshold)
    conditions_status.append({
        'name': 'CHOP Filter',
        'required': True,
        'status': not is_chop,
        'message': chop_msg,
        'version': 'V2',
        'strict_level': 'MEDIUM'
    })
    
    # 7. HA Candle Color
    if current_trend == "BULLISH":
        is_green = last_ha['ha_close'] > last_ha['ha_open']
        ha_color_ok = is_green
        ha_color_msg = f"HA Candle: {'Green' if is_green else 'Red'}"
    else:
        is_red = last_ha['ha_close'] < last_ha['ha_open']
        ha_color_ok = is_red
        ha_color_msg = f"HA Candle: {'Red' if is_red else 'Green'}"
    
    conditions_status.append({
        'name': 'HA Candle Color',
        'required': True,
        'status': ha_color_ok,
        'message': ha_color_msg,
        'version': 'V1',
        'strict_level': 'LOW'
    })
    
    # 8. Above/Below Channel
    if current_trend == "BULLISH":
        is_above_channel = last_ha['ha_close'] > last_ha['sma55_high']
        channel_ok = is_above_channel
        channel_msg = f"Above Channel: {last_ha['ha_close']:.2f} > {last_ha['sma55_high']:.2f}"
    else:
        is_below_channel = last_ha['ha_close'] < last_ha['sma55_low']
        channel_ok = is_below_channel
        channel_msg = f"Below Channel: {last_ha['ha_close']:.2f} < {last_ha['sma55_low']:.2f}"
    
    conditions_status.append({
        'name': 'Channel Breakout',
        'required': True,
        'status': channel_ok,
        'message': channel_msg,
        'version': 'V1',
        'strict_level': 'LOW'
    })
    
    # 9. Fresh Breakout
    if current_trend == "BULLISH":
        is_fresh_breakout = prev_ha['ha_close'] <= prev_ha['sma55_high']
    else:
        is_fresh_breakout = prev_ha['ha_close'] >= prev_ha['sma55_low']
    
    conditions_status.append({
        'name': 'Fresh Breakout',
        'required': True,
        'status': is_fresh_breakout,
        'message': f"Fresh Breakout: {'Yes' if is_fresh_breakout else 'No'}",
        'version': 'V1',
        'strict_level': 'MEDIUM'
    })
    
    # 10. Solid Candle (Not Doji)
    is_solid_candle = not is_doji(last_ha, threshold=0.2)
    conditions_status.append({
        'name': 'Solid Candle (Not Doji)',
        'required': True,
        'status': is_solid_candle,
        'message': f"Solid Candle: {'Yes' if is_solid_candle else 'No (Doji)'}",
        'version': 'V1',
        'strict_level': 'LOW'
    })
    
    # 11. RSI Filter
    rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 60)
    rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 40)
    if current_trend == "BULLISH":
        rsi_ok = last_ha['rsi'] > rsi_buy_threshold
        rsi_msg = f"RSI={last_ha['rsi']:.1f} > {rsi_buy_threshold}"
    else:
        rsi_ok = last_ha['rsi'] < rsi_sell_threshold
        rsi_msg = f"RSI={last_ha['rsi']:.1f} < {rsi_sell_threshold}"
    
    conditions_status.append({
        'name': f'RSI Filter (BUY>{rsi_buy_threshold}, SELL<{rsi_sell_threshold})',
        'required': True,
        'status': rsi_ok,
        'message': rsi_msg,
        'version': 'V3 (Tăng từ 55/45 lên 60/40)',
        'strict_level': 'HIGH',
        'note': 'V3 tăng threshold - strict hơn nhiều'
    })
    
    # 12. Liquidity Sweep (V3 - MỚI, BẮT BUỘC)
    if current_trend == "BULLISH":
        has_sweep, sweep_msg = check_liquidity_sweep_buy(df_m1, atr_val, symbol=symbol, buffer_pips=2)
    else:
        has_sweep, sweep_msg = check_liquidity_sweep_sell(df_m1, atr_val, symbol=symbol, buffer_pips=2)
    
    conditions_status.append({
        'name': 'Liquidity Sweep',
        'required': True,
        'status': has_sweep,
        'message': sweep_msg,
        'version': 'V3 (MỚI - BẮT BUỘC)',
        'strict_level': 'VERY HIGH',
        'note': 'Điều kiện V3 mới - RẤT STRICT, có thể là nguyên nhân chính'
    })
    
    # 13. Displacement Candle (V3 - MỚI, BẮT BUỘC)
    signal_type = "BUY" if current_trend == "BULLISH" else "SELL"
    has_displacement, displacement_msg = check_displacement_candle(df_m1, atr_val, signal_type)
    
    conditions_status.append({
        'name': 'Displacement Candle',
        'required': True,
        'status': has_displacement,
        'message': displacement_msg,
        'version': 'V3 (MỚI - BẮT BUỘC)',
        'strict_level': 'VERY HIGH',
        'note': 'Điều kiện V3 mới - RẤT STRICT, có thể là nguyên nhân chính'
    })
    
    # 14. Volume Confirmation (V3 - MỚI)
    current_volume = df_m1.iloc[-1]['tick_volume']
    vol_ma = df_m1.iloc[-1]['vol_ma']
    volume_multiplier = config['parameters'].get('volume_confirmation_multiplier', 1.3)
    has_volume_confirmation = current_volume > (vol_ma * volume_multiplier)
    
    conditions_status.append({
        'name': f'Volume Confirmation ({volume_multiplier}x avg)',
        'required': True,
        'status': has_volume_confirmation,
        'message': f"Volume: {current_volume:.0f} > {vol_ma * volume_multiplier:.0f}",
        'version': 'V3 (MỚI)',
        'strict_level': 'HIGH',
        'note': 'Điều kiện V3 mới - strict'
    })
    
    # 15. Confirmation Candles (V3 - Tăng từ 1 lên 2)
    confirmation_enabled = config['parameters'].get('confirmation_enabled', True)
    confirmation_candles = config['parameters'].get('confirmation_candles', 2)
    
    if confirmation_enabled and len(ha_df) >= confirmation_candles + 1:
        if current_trend == "BULLISH":
            breakout_level = last_ha['sma55_high']
            all_confirmed = True
            for i in range(1, confirmation_candles + 1):
                if len(ha_df) >= i + 1:
                    conf_candle = ha_df.iloc[-i]
                    if conf_candle['ha_close'] <= breakout_level:
                        all_confirmed = False
                        break
            if all_confirmed:
                latest_candle = ha_df.iloc[-1]
                confirmation_ok = latest_candle['ha_close'] > breakout_level
                confirmation_msg = f"Confirmation: {confirmation_candles} nến confirmed" if confirmation_ok else "False breakout detected"
            else:
                confirmation_ok = False
                confirmation_msg = f"Chờ {confirmation_candles} nến confirmation"
        else:
            breakout_level = last_ha['sma55_low']
            all_confirmed = True
            for i in range(1, confirmation_candles + 1):
                if len(ha_df) >= i + 1:
                    conf_candle = ha_df.iloc[-i]
                    if conf_candle['ha_close'] >= breakout_level:
                        all_confirmed = False
                        break
            if all_confirmed:
                latest_candle = ha_df.iloc[-1]
                confirmation_ok = latest_candle['ha_close'] < breakout_level
                confirmation_msg = f"Confirmation: {confirmation_candles} nến confirmed" if confirmation_ok else "False breakout detected"
            else:
                confirmation_ok = False
                confirmation_msg = f"Chờ {confirmation_candles} nến confirmation"
    else:
        confirmation_ok = True  # Disabled
        confirmation_msg = "Confirmation disabled"
    
    conditions_status.append({
        'name': f'Confirmation Candles ({confirmation_candles} nến)',
        'required': confirmation_enabled,
        'status': confirmation_ok,
        'message': confirmation_msg,
        'version': 'V3 (Tăng từ 1 lên 2)',
        'strict_level': 'HIGH',
        'note': 'V3 tăng từ 1 lên 2 nến - strict hơn'
    })
    
    # Print summary
    print(f"{'STT':<4} {'Điều Kiện':<35} {'Version':<20} {'Status':<8} {'Strict':<10} {'Ghi Chú'}")
    print(f"{'-'*100}")
    
    for idx, cond in enumerate(conditions_status, 1):
        status_str = "✅ PASS" if cond['status'] else "❌ FAIL"
        strict_str = cond.get('strict_level', 'N/A')
        note_str = cond.get('note', '')
        version_str = cond.get('version', 'V1')
        
        print(f"{idx:<4} {cond['name']:<35} {version_str:<20} {status_str:<8} {strict_str:<10} {note_str}")
    
    # Summary
    print(f"\n{'='*100}")
    print(f"TOM TAT")
    print(f"{'='*100}\n")
    
    total_conditions = len(conditions_status)
    passed_conditions = len([c for c in conditions_status if c['status']])
    failed_conditions = total_conditions - passed_conditions
    
    print(f"Tong so dieu kien: {total_conditions}")
    print(f"Dieu kien dat: {passed_conditions}")
    print(f"Dieu kien khong dat: {failed_conditions}")
    
    # Phân tích điều kiện V3 mới
    v3_conditions = [c for c in conditions_status if 'V3' in c.get('version', '')]
    v3_failed = [c for c in v3_conditions if not c['status']]
    
    print(f"\nDieu kien V3 (moi them vao): {len(v3_conditions)}")
    print(f"Dieu kien V3 khong dat: {len(v3_failed)}")
    
    if v3_failed:
        print(f"\n⚠️ CAC DIEU KIEN V3 KHONG DAT (co the la nguyen nhan chinh):")
        for cond in v3_failed:
            print(f"   ❌ {cond['name']}: {cond['message']}")
            if cond.get('note'):
                print(f"      → {cond['note']}")
    
    # Điều kiện VERY HIGH strict level
    very_high_strict = [c for c in conditions_status if c.get('strict_level') == 'VERY HIGH' and not c['status']]
    if very_high_strict:
        print(f"\n🔴 CAC DIEU KIEN RAT STRICT KHONG DAT (nguyen nhan chinh):")
        for cond in very_high_strict:
            print(f"   ❌ {cond['name']}: {cond['message']}")
            print(f"      Version: {cond.get('version', 'N/A')}")
            if cond.get('note'):
                print(f"      → {cond['note']}")
    
    # So sánh với analyze_losses
    print(f"\n{'='*100}")
    print(f"SO SANH VOI ANALYZE_LOSSES")
    print(f"{'='*100}\n")
    
    print(f"Dieu kien trong analyze_losses_strategy1_v2.py:")
    print(f"   1. M5 Trend (EMA200)")
    print(f"   2. ADX >= 20 (V2)")
    print(f"   3. HA Candle đúng màu")
    print(f"   4. Above/Below Channel")
    print(f"   5. Fresh Breakout")
    print(f"   6. Solid Candle (Not Doji)")
    print(f"   7. RSI > 55 (BUY) hoặc RSI < 45 (SELL) (V2)")
    
    print(f"\nDieu kien TRONG BOT (V3) - THEM VAO:")
    print(f"   ❌ EMA50 > EMA200 trên M5 (V3)")
    print(f"   ❌ H1 Trend == M5 Trend (V3)")
    print(f"   ❌ ADX >= 25 (V3 tăng từ 20)")
    print(f"   ❌ RSI > 60 (BUY) hoặc RSI < 40 (SELL) (V3 tăng từ 55/45)")
    print(f"   ❌ Liquidity Sweep (V3 - BẮT BUỘC)")
    print(f"   ❌ Displacement Candle (V3 - BẮT BUỘC)")
    print(f"   ❌ Volume Confirmation 1.3x (V3)")
    print(f"   ❌ Confirmation Candles = 2 (V3 tăng từ 1)")
    print(f"   ❌ CHOP Filter (V2)")
    print(f"   ❌ Session Filter (V4)")
    
    print(f"\n💡 KET LUAN:")
    print(f"   Bot co {len(v3_conditions)} dieu kien V3 moi them vao")
    print(f"   Trong do co {len([c for c in v3_conditions if c.get('strict_level') in ['VERY HIGH', 'HIGH']])} dieu kien RAT STRICT")
    print(f"   Cac dieu kien V3 co the la nguyen nhan chinh khiến bot khong vao lenh trong 7 ngay")
    print(f"\n   De xuat:")
    print(f"   1. Giam strict level cua cac dieu kien V3:")
    print(f"      - Liquidity Sweep: Co the optional hoac giam buffer")
    print(f"      - Displacement Candle: Co the optional hoac giam threshold")
    print(f"      - Volume: Giam tu 1.3x xuong 1.1x hoac optional")
    print(f"      - Confirmation: Giam tu 2 xuong 1 nến")
    print(f"   2. Giam threshold:")
    print(f"      - ADX: Giam tu 25 xuong 22-23")
    print(f"      - RSI: Giam tu 60/40 xuong 58/42")
    print(f"   3. Lam optional mot so dieu kien:")
    print(f"      - H1 Trend confirmation: Co the optional")
    print(f"      - EMA50 > EMA200: Co the optional")
    
    print(f"\n{'='*100}\n")
    
    mt5.shutdown()

if __name__ == "__main__":
    review_conditions()
