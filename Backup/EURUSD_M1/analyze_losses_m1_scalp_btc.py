import MetaTrader5 as mt5
import sys
import sqlite3
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import time

# Import local modules
sys.path.append('..')
from utils import load_config, connect_mt5, get_data, calculate_rsi, get_pip_size
# Import functions from tuyen_trend_sclap_btc
from tuyen_trend_sclap_btc import (
    calculate_ema, calculate_atr, get_min_atr_threshold,
    find_swing_high_with_rsi, find_swing_low_with_rsi,
    check_valid_pullback_buy, check_valid_pullback_sell,
    calculate_pullback_trendline_buy, calculate_pullback_trendline,
    check_trendline_break_buy, check_trendline_break_sell,
    check_bearish_divergence, check_bullish_divergence
)

STRATEGY_NAME = "M1_Scalp_BTCUSD"
CONFIG_FILE = "config_tuyen_btc.json"
SYMBOL_DISPLAY = "BTCUSD"

def analyze_order_loss(ticket, order_type, open_time_str, open_price, sl, tp, close_price, profit):
    """
    Phân tích một lệnh thua để xác định tại sao thua
    """
    print(f"\n{'='*100}")
    print(f"🔻 TICKET: {ticket} | {order_type} | Entry: {open_price:.5f} | SL: {sl:.5f} | TP: {tp:.5f}")
    print(f"   Close: {close_price:.5f} | Profit: ${profit:.2f} | Entry Time: {open_time_str}")
    print(f"{'='*100}")
    
    # Parse entry time
    try:
        entry_time = datetime.strptime(open_time_str, '%Y-%m-%d %H:%M:%S')
    except:
        try:
            entry_time = datetime.fromisoformat(open_time_str.replace('Z', '+00:00'))
        except:
            print(f"❌ Cannot parse time: {open_time_str}")
            return
    
    # Convert to UTC timestamp for MT5
    entry_timestamp = entry_time.timestamp()
    
    # Get symbol from config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", CONFIG_FILE)
    config = load_config(config_path)
    symbol = config['symbol']
    
    # Get data at entry time (need enough data for indicators)
    from_time = datetime.fromtimestamp(entry_timestamp) - timedelta(hours=10)
    from_timestamp = int(from_time.timestamp())
    
    # Fetch M1 data
    rates_m1 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M1, from_timestamp, 300)
    if rates_m1 is None or len(rates_m1) == 0:
        print(f"❌ Cannot get M1 data for entry time")
        return
    
    df_m1 = pd.DataFrame(rates_m1)
    df_m1['time'] = pd.to_datetime(df_m1['time'], unit='s')
    
    # Fetch M5 data
    rates_m5 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M5, from_timestamp, 300)
    if rates_m5 is None or len(rates_m5) == 0:
        print(f"❌ Cannot get M5 data for entry time")
        return
    
    df_m5 = pd.DataFrame(rates_m5)
    df_m5['time'] = pd.to_datetime(df_m5['time'], unit='s')
    
    # Find the candle closest to entry time
    entry_idx_m1 = None
    for i in range(len(df_m1) - 1, -1, -1):
        candle_time = df_m1.iloc[i]['time']
        if candle_time <= entry_time:
            entry_idx_m1 = i
            break
    
    if entry_idx_m1 is None:
        print(f"❌ Cannot find M1 candle for entry time")
        return
    
    # Calculate indicators up to entry candle
    df_m1_entry = df_m1.iloc[:entry_idx_m1+1].copy()
    df_m5_entry = df_m5[df_m5['time'] <= entry_time].copy()
    
    if len(df_m1_entry) < 200 or len(df_m5_entry) < 100:
        print(f"❌ Not enough data for indicators (M1: {len(df_m1_entry)}, M5: {len(df_m5_entry)})")
        return
    
    # Calculate indicators
    df_m1_entry['ema50'] = calculate_ema(df_m1_entry['close'], 50)
    df_m1_entry['ema200'] = calculate_ema(df_m1_entry['close'], 200)
    df_m1_entry['atr'] = calculate_atr(df_m1_entry, 14)
    df_m1_entry['rsi'] = calculate_rsi(df_m1_entry['close'], 14)
    
    df_m5_entry['rsi'] = calculate_rsi(df_m5_entry['close'], 14)
    
    # Get symbol info for pip size
    symbol_info = mt5.symbol_info(symbol)
    pip_size = get_pip_size(symbol, symbol_info)
    min_atr = get_min_atr_threshold(symbol, config)
    
    # Analyze conditions
    print(f"\n📊 [PHÂN TÍCH ĐIỀU KIỆN TẠI THỜI ĐIỂM ENTRY]")
    print(f"{'─'*100}")
    
    issues = []
    passed_conditions = []
    
    # Get current candle (entry candle)
    curr_candle = df_m1_entry.iloc[-1]
    ema50_val = curr_candle['ema50']
    ema200_val = curr_candle['ema200']
    atr_val = curr_candle['atr']
    current_candle_idx = len(df_m1_entry) - 1
    
    # Điều kiện 1: EMA50 > EMA200 (BUY) hoặc EMA50 < EMA200 (SELL)
    if order_type == "BUY":
        if not (ema50_val > ema200_val):
            issues.append(f"❌ ĐK1: EMA50 ({ema50_val:.5f}) <= EMA200 ({ema200_val:.5f})")
        else:
            passed_conditions.append(f"✅ ĐK1: EMA50 ({ema50_val:.5f}) > EMA200 ({ema200_val:.5f})")
    else:  # SELL
        if not (ema50_val < ema200_val):
            issues.append(f"❌ ĐK1: EMA50 ({ema50_val:.5f}) >= EMA200 ({ema200_val:.5f})")
        else:
            passed_conditions.append(f"✅ ĐK1: EMA50 ({ema50_val:.5f}) < EMA200 ({ema200_val:.5f})")
    
    # Điều kiện 2: Swing High/Low với RSI
    if order_type == "BUY":
        swing_highs = find_swing_high_with_rsi(df_m1_entry, lookback=5, min_rsi=70)
        if len(swing_highs) == 0:
            issues.append(f"❌ ĐK2: Không tìm thấy Swing High với RSI > 70")
        else:
            latest_swing_high = swing_highs[-1]
            passed_conditions.append(f"✅ ĐK2: Tìm thấy Swing High (Price: {latest_swing_high['price']:.5f}, RSI: {latest_swing_high['rsi']:.1f})")
    else:  # SELL
        swing_lows = find_swing_low_with_rsi(df_m1_entry, lookback=5, min_rsi=30)
        if len(swing_lows) == 0:
            issues.append(f"❌ ĐK2: Không tìm thấy Swing Low với RSI < 30")
        else:
            latest_swing_low = swing_lows[-1]
            passed_conditions.append(f"✅ ĐK2: Tìm thấy Swing Low (Price: {latest_swing_low['price']:.5f}, RSI: {latest_swing_low['rsi']:.1f})")
    
    # Điều kiện 3: Pullback hợp lệ
    if order_type == "BUY" and len(swing_highs) > 0:
        swing_high_idx = swing_highs[-1]['index']
        pullback_valid, pullback_end_idx, pullback_candles, pullback_msg = check_valid_pullback_buy(
            df_m1_entry, swing_high_idx, max_candles=30, rsi_target_min=40, rsi_target_max=50, rsi_min_during_pullback=32
        )
        if not pullback_valid:
            issues.append(f"❌ ĐK3: {pullback_msg}")
        else:
            passed_conditions.append(f"✅ ĐK3: {pullback_msg}")
    elif order_type == "SELL" and len(swing_lows) > 0:
        swing_low_idx = swing_lows[-1]['index']
        pullback_valid, pullback_end_idx, pullback_candles, pullback_msg = check_valid_pullback_sell(
            df_m1_entry, swing_low_idx, max_candles=30, rsi_target_min=50, rsi_target_max=60, rsi_max_during_pullback=68
        )
        if not pullback_valid:
            issues.append(f"❌ ĐK3: {pullback_msg}")
        else:
            passed_conditions.append(f"✅ ĐK3: {pullback_msg}")
    
    # Điều kiện 4: ATR >= threshold
    if pd.isna(atr_val) or atr_val < min_atr:
        symbol_upper = symbol.upper()
        if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
            issues.append(f"❌ ĐK4: ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD")
        elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
            issues.append(f"❌ ĐK4: ATR ({atr_val:.2f} USD) < {min_atr:.2f} USD")
        else:
            issues.append(f"❌ ĐK4: ATR ({atr_val:.5f}) < {min_atr:.5f}")
    else:
        symbol_upper = symbol.upper()
        if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
            passed_conditions.append(f"✅ ĐK4: ATR ({atr_val:.2f} USD) >= {min_atr:.2f} USD")
        elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
            passed_conditions.append(f"✅ ĐK4: ATR ({atr_val:.2f} USD) >= {min_atr:.2f} USD")
        else:
            passed_conditions.append(f"✅ ĐK4: ATR ({atr_val:.5f}) >= {min_atr:.5f}")
    
    # Điều kiện 5: Trendline break
    if order_type == "BUY" and len(swing_highs) > 0 and pullback_valid:
        swing_high_idx = swing_highs[-1]['index']
        trendline_info = calculate_pullback_trendline_buy(df_m1_entry, swing_high_idx, pullback_end_idx)
        if trendline_info is None:
            issues.append(f"❌ ĐK5: Không thể vẽ trendline")
        else:
            break_ok, break_msg = check_trendline_break_buy(df_m1_entry, trendline_info, current_candle_idx, ema50_val)
            if not break_ok:
                issues.append(f"❌ ĐK5: {break_msg}")
            else:
                passed_conditions.append(f"✅ ĐK5: {break_msg}")
    elif order_type == "SELL" and len(swing_lows) > 0 and pullback_valid:
        swing_low_idx = swing_lows[-1]['index']
        trendline_info = calculate_pullback_trendline(df_m1_entry, swing_low_idx, pullback_end_idx)
        if trendline_info is None:
            issues.append(f"❌ ĐK5: Không thể vẽ trendline")
        else:
            break_ok, break_msg = check_trendline_break_sell(df_m1_entry, trendline_info, current_candle_idx, ema50_val)
            if not break_ok:
                issues.append(f"❌ ĐK5: {break_msg}")
            else:
                passed_conditions.append(f"✅ ĐK5: {break_msg}")
    
    # Điều kiện 6: Không có Divergence
    if order_type == "BUY":
        has_bearish_div, bearish_div_msg = check_bearish_divergence(df_m1_entry, lookback=50)
        if has_bearish_div:
            issues.append(f"❌ ĐK6: {bearish_div_msg}")
        else:
            passed_conditions.append(f"✅ ĐK6: {bearish_div_msg}")
    else:  # SELL
        has_bullish_div, bullish_div_msg = check_bullish_divergence(df_m1_entry, lookback=50)
        if has_bullish_div:
            issues.append(f"❌ ĐK6: {bullish_div_msg}")
        else:
            passed_conditions.append(f"✅ ĐK6: {bullish_div_msg}")
    
    # Điều kiện 7: RSI(14)_M5 trong khoảng phù hợp
    if len(df_m5_entry) < 2:
        issues.append(f"❌ ĐK7: Không đủ dữ liệu M5 để tính RSI")
    else:
        rsi_m5 = df_m5_entry['rsi'].iloc[-2]  # RSI của nến M5 đã đóng gần nhất
        if pd.isna(rsi_m5):
            issues.append(f"❌ ĐK7: RSI(14)_M5 không có giá trị (NaN)")
        else:
            if order_type == "BUY":
                if not (55 <= rsi_m5 <= 65):
                    issues.append(f"❌ ĐK7: RSI(14)_M5 ({rsi_m5:.1f}) không trong khoảng 55-65")
                else:
                    passed_conditions.append(f"✅ ĐK7: RSI(14)_M5 ({rsi_m5:.1f}) trong khoảng 55-65")
            else:  # SELL
                if not (35 <= rsi_m5 <= 45):
                    issues.append(f"❌ ĐK7: RSI(14)_M5 ({rsi_m5:.1f}) không trong khoảng 35-45")
                else:
                    passed_conditions.append(f"✅ ĐK7: RSI(14)_M5 ({rsi_m5:.1f}) trong khoảng 35-45")
    
    # Display results
    print(f"\n✅ ĐIỀU KIỆN ĐẠT ({len(passed_conditions)}/7):")
    for cond in passed_conditions:
        print(f"   {cond}")
    
    if issues:
        print(f"\n❌ ĐIỀU KIỆN KHÔNG ĐẠT ({len(issues)}):")
        for issue in issues:
            print(f"   {issue}")
    
    # Check exit reason
    print(f"\n🏦 PHÂN TÍCH EXIT:")
    if close_price:
        sl_distance = abs(close_price - sl) if sl > 0 else 999
        tp_distance = abs(close_price - tp) if tp > 0 else 999
        
        # Use pip_size for distance calculation
        sl_distance_pips = sl_distance / pip_size if pip_size > 0 else 0
        tp_distance_pips = tp_distance / pip_size if pip_size > 0 else 0
        
        if sl > 0 and sl_distance_pips < 0.5:  # Within 0.5 pips
            print(f"   🔴 HIT STOP LOSS: Close {close_price:.5f} ≈ SL {sl:.5f} (distance: {sl_distance_pips:.1f} pips)")
        elif tp > 0 and tp_distance_pips < 0.5:
            print(f"   🟢 HIT TAKE PROFIT: Close {close_price:.5f} ≈ TP {tp:.5f} (distance: {tp_distance_pips:.1f} pips)")
        else:
            print(f"   👤 MANUAL/SCRIPT CLOSE: Close {close_price:.5f} (SL: {sl:.5f}, TP: {tp:.5f})")
    else:
        print(f"   ⚠️ RUNNING/OPEN")
    
    # Summary
    print(f"\n💡 TÓM TẮT:")
    if len(issues) > 0:
        print(f"   ⚠️ Lệnh vào khi có {len(issues)} điều kiện không đạt!")
        print(f"   📋 Các vấn đề: {', '.join([i.split(':')[0].replace('❌ ', '') for i in issues])}")
    else:
        print(f"   ✅ Tất cả điều kiện đạt tại entry")
        print(f"   🤔 Có thể do: SL quá chặt, market reversal, hoặc false breakout")
    
    # Display indicator values
    print(f"\n📊 GIÁ TRỊ INDICATORS TẠI ENTRY:")
    print(f"   💱 Entry Price: {open_price:.5f}")
    print(f"   📈 EMA50: {ema50_val:.5f} | EMA200: {ema200_val:.5f}")
    current_rsi = curr_candle.get('rsi', 0)
    if pd.notna(current_rsi):
        print(f"   📊 RSI(M1): {current_rsi:.1f}")
    rsi_m5_val = df_m5_entry['rsi'].iloc[-2] if len(df_m5_entry) >= 2 else None
    if pd.notna(rsi_m5_val):
        print(f"   📊 RSI(14)_M5: {rsi_m5_val:.1f}")
    symbol_upper = symbol.upper()
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        print(f"   📊 ATR: {atr_val:.2f} USD")
    elif 'BTCUSD' in symbol_upper or 'BTC' in symbol_upper:
        print(f"   📊 ATR: {atr_val:.2f} USD")
    else:
        print(f"   📊 ATR: {atr_val:.5f}")
    print(f"   🛑 SL: {sl:.5f} | 🎯 TP: {tp:.5f}")
    if order_type == "BUY":
        sl_distance_pips = (open_price - sl) / pip_size if sl > 0 and pip_size > 0 else 0
    else:
        sl_distance_pips = (sl - open_price) / pip_size if sl > 0 and pip_size > 0 else 0
    print(f"   📏 SL Distance: {sl_distance_pips:.1f} pips")

def analyze_order_loss_with_stats(ticket, order_type, open_time_str, open_price, sl, tp, close_price, profit):
    """
    Phân tích một lệnh thua và trả về statistics
    """
    stats = {
        'ticket': ticket,
        'order_type': order_type,
        'profit': profit,
        'issues': [],
        'passed_conditions': [],
        'exit_reason': 'UNKNOWN',
        'sl_distance_pips': 0,
        'indicators': {}
    }
    
    # Parse entry time
    try:
        entry_time = datetime.strptime(open_time_str, '%Y-%m-%d %H:%M:%S')
    except:
        try:
            entry_time = datetime.fromisoformat(open_time_str.replace('Z', '+00:00'))
        except:
            return None
    
    entry_timestamp = entry_time.timestamp()
    
    # Get symbol from config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", CONFIG_FILE)
    config = load_config(config_path)
    symbol = config['symbol']
    
    from_time = datetime.fromtimestamp(entry_timestamp) - timedelta(hours=10)
    from_timestamp = int(from_time.timestamp())
    
    # Fetch data
    rates_m1 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M1, from_timestamp, 300)
    rates_m5 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M5, from_timestamp, 300)
    
    if rates_m1 is None or len(rates_m1) == 0 or rates_m5 is None or len(rates_m5) == 0:
        return None
    
    df_m1 = pd.DataFrame(rates_m1)
    df_m1['time'] = pd.to_datetime(df_m1['time'], unit='s')
    df_m5 = pd.DataFrame(rates_m5)
    df_m5['time'] = pd.to_datetime(df_m5['time'], unit='s')
    
    entry_idx_m1 = None
    for i in range(len(df_m1) - 1, -1, -1):
        if df_m1.iloc[i]['time'] <= entry_time:
            entry_idx_m1 = i
            break
    
    if entry_idx_m1 is None:
        return None
    
    df_m1_entry = df_m1.iloc[:entry_idx_m1+1].copy()
    df_m5_entry = df_m5[df_m5['time'] <= entry_time].copy()
    
    if len(df_m1_entry) < 200 or len(df_m5_entry) < 100:
        return None
    
    # Calculate indicators
    df_m1_entry['ema50'] = calculate_ema(df_m1_entry['close'], 50)
    df_m1_entry['ema200'] = calculate_ema(df_m1_entry['close'], 200)
    df_m1_entry['atr'] = calculate_atr(df_m1_entry, 14)
    df_m1_entry['rsi'] = calculate_rsi(df_m1_entry['close'], 14)
    df_m5_entry['rsi'] = calculate_rsi(df_m5_entry['close'], 14)
    
    symbol_info = mt5.symbol_info(symbol)
    pip_size = get_pip_size(symbol, symbol_info)
    min_atr = get_min_atr_threshold(symbol, config)
    
    curr_candle = df_m1_entry.iloc[-1]
    ema50_val = curr_candle['ema50']
    ema200_val = curr_candle['ema200']
    atr_val = curr_candle['atr']
    current_candle_idx = len(df_m1_entry) - 1
    
    # Store indicators
    stats['indicators'] = {
        'ema50': float(ema50_val),
        'ema200': float(ema200_val),
        'atr': float(atr_val),
        'rsi_m1': float(curr_candle.get('rsi', 0)),
        'rsi_m5': float(df_m5_entry['rsi'].iloc[-2]) if len(df_m5_entry) >= 2 else 0
    }
    
    # Check conditions
    # ĐK1: EMA
    if order_type == "BUY":
        if not (ema50_val > ema200_val):
            stats['issues'].append("DK1_EMA")
        else:
            stats['passed_conditions'].append("DK1_EMA")
    else:
        if not (ema50_val < ema200_val):
            stats['issues'].append("DK1_EMA")
        else:
            stats['passed_conditions'].append("DK1_EMA")
    
    # ĐK2: Swing High/Low
    if order_type == "BUY":
        swing_highs = find_swing_high_with_rsi(df_m1_entry, lookback=5, min_rsi=70)
        if len(swing_highs) == 0:
            stats['issues'].append("DK2_Swing")
        else:
            stats['passed_conditions'].append("DK2_Swing")
    else:
        swing_lows = find_swing_low_with_rsi(df_m1_entry, lookback=5, min_rsi=30)
        if len(swing_lows) == 0:
            stats['issues'].append("DK2_Swing")
        else:
            stats['passed_conditions'].append("DK2_Swing")
    
    # ĐK3: Pullback
    pullback_valid = False
    if order_type == "BUY" and len(swing_highs) > 0:
        swing_high_idx = swing_highs[-1]['index']
        pullback_valid, pullback_end_idx, _, _ = check_valid_pullback_buy(
            df_m1_entry, swing_high_idx, max_candles=30, rsi_target_min=40, rsi_target_max=50, rsi_min_during_pullback=32
        )
    elif order_type == "SELL" and len(swing_lows) > 0:
        swing_low_idx = swing_lows[-1]['index']
        pullback_valid, pullback_end_idx, _, _ = check_valid_pullback_sell(
            df_m1_entry, swing_low_idx, max_candles=30, rsi_target_min=50, rsi_target_max=60, rsi_max_during_pullback=68
        )
    
    if not pullback_valid:
        stats['issues'].append("DK3_Pullback")
    else:
        stats['passed_conditions'].append("DK3_Pullback")
    
    # ĐK4: ATR
    if pd.isna(atr_val) or atr_val < min_atr:
        stats['issues'].append("DK4_ATR")
    else:
        stats['passed_conditions'].append("DK4_ATR")
    
    # ĐK5: Trendline break
    if order_type == "BUY" and len(swing_highs) > 0 and pullback_valid:
        swing_high_idx = swing_highs[-1]['index']
        trendline_info = calculate_pullback_trendline_buy(df_m1_entry, swing_high_idx, pullback_end_idx)
        if trendline_info is None:
            stats['issues'].append("DK5_Trendline")
        else:
            break_ok, _ = check_trendline_break_buy(df_m1_entry, trendline_info, current_candle_idx, ema50_val)
            if not break_ok:
                stats['issues'].append("DK5_Trendline")
            else:
                stats['passed_conditions'].append("DK5_Trendline")
    elif order_type == "SELL" and len(swing_lows) > 0 and pullback_valid:
        swing_low_idx = swing_lows[-1]['index']
        trendline_info = calculate_pullback_trendline(df_m1_entry, swing_low_idx, pullback_end_idx)
        if trendline_info is None:
            stats['issues'].append("DK5_Trendline")
        else:
            break_ok, _ = check_trendline_break_sell(df_m1_entry, trendline_info, current_candle_idx, ema50_val)
            if not break_ok:
                stats['issues'].append("DK5_Trendline")
            else:
                stats['passed_conditions'].append("DK5_Trendline")
    else:
        stats['issues'].append("DK5_Trendline")
    
    # ĐK6: Divergence
    if order_type == "BUY":
        has_bearish_div, _ = check_bearish_divergence(df_m1_entry, lookback=50)
        if has_bearish_div:
            stats['issues'].append("DK6_Divergence")
        else:
            stats['passed_conditions'].append("DK6_Divergence")
    else:
        has_bullish_div, _ = check_bullish_divergence(df_m1_entry, lookback=50)
        if has_bullish_div:
            stats['issues'].append("DK6_Divergence")
        else:
            stats['passed_conditions'].append("DK6_Divergence")
    
    # ĐK7: RSI M5
    if len(df_m5_entry) >= 2:
        rsi_m5 = df_m5_entry['rsi'].iloc[-2]
        if pd.notna(rsi_m5):
            if order_type == "BUY":
                if not (55 <= rsi_m5 <= 65):
                    stats['issues'].append("DK7_RSI_M5")
                else:
                    stats['passed_conditions'].append("DK7_RSI_M5")
            else:
                if not (35 <= rsi_m5 <= 45):
                    stats['issues'].append("DK7_RSI_M5")
                else:
                    stats['passed_conditions'].append("DK7_RSI_M5")
        else:
            stats['issues'].append("DK7_RSI_M5")
    else:
        stats['issues'].append("DK7_RSI_M5")
    
    # Exit reason
    if close_price:
        sl_distance = abs(close_price - sl) if sl > 0 else 999
        tp_distance = abs(close_price - tp) if tp > 0 else 999
        sl_distance_pips = sl_distance / pip_size if pip_size > 0 else 0
        
        if sl > 0 and sl_distance_pips < 0.5:
            stats['exit_reason'] = "HIT_SL"
        elif tp > 0 and tp_distance / pip_size < 0.5:
            stats['exit_reason'] = "HIT_TP"
        else:
            stats['exit_reason'] = "MANUAL_CLOSE"
    else:
        stats['exit_reason'] = "RUNNING"
    
    # SL distance in pips
    if order_type == "BUY":
        stats['sl_distance_pips'] = (open_price - sl) / pip_size if sl > 0 and pip_size > 0 else 0
    else:
        stats['sl_distance_pips'] = (sl - open_price) / pip_size if sl > 0 and pip_size > 0 else 0
    
    return stats

def generate_summary_report(all_stats, output_file):
    """
    Tạo file tổng kết với đề xuất cải thiện
    """
    total_losses = len(all_stats)
    if total_losses == 0:
        return
    
    # Count issues
    issue_counts = {}
    exit_reasons = {}
    sl_distances = []
    avg_profit = 0
    
    for stat in all_stats:
        for issue in stat['issues']:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
        
        exit_reasons[stat['exit_reason']] = exit_reasons.get(stat['exit_reason'], 0) + 1
        
        if stat['sl_distance_pips'] > 0:
            sl_distances.append(stat['sl_distance_pips'])
        
        avg_profit += stat['profit']
    
    avg_profit = avg_profit / total_losses
    
    # Calculate percentages
    issue_percentages = {k: (v / total_losses * 100) for k, v in issue_counts.items()}
    exit_percentages = {k: (v / total_losses * 100) for k, v in exit_reasons.items()}
    avg_sl_distance = sum(sl_distances) / len(sl_distances) if sl_distances else 0
    
    # Generate report
    report = []
    report.append("=" * 100)
    report.append("📊 BÁO CÁO TỔNG KẾT PHÂN TÍCH LỆNH THUA")
    report.append(f"Strategy: {STRATEGY_NAME} ({SYMBOL_DISPLAY})")
    report.append(f"Ngày tạo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 100)
    report.append("")
    
    # 1. Tổng quan
    report.append("## 1. TỔNG QUAN")
    report.append("-" * 100)
    report.append(f"Tổng số lệnh thua phân tích: {total_losses}")
    report.append(f"Tổng lỗ: ${sum([s['profit'] for s in all_stats]):.2f}")
    report.append(f"Lỗ trung bình: ${avg_profit:.2f}")
    report.append(f"Khoảng cách SL trung bình: {avg_sl_distance:.1f} pips")
    report.append("")
    
    # 2. Phân tích Exit Reasons
    report.append("## 2. PHÂN TÍCH LÝ DO THOÁT LỆNH")
    report.append("-" * 100)
    for reason, count in sorted(exit_reasons.items(), key=lambda x: x[1], reverse=True):
        percentage = exit_percentages[reason]
        reason_name = {
            'HIT_SL': '🔴 Hit Stop Loss',
            'HIT_TP': '🟢 Hit Take Profit',
            'MANUAL_CLOSE': '👤 Manual/Script Close',
            'RUNNING': '⚠️ Đang chạy'
        }.get(reason, reason)
        report.append(f"  {reason_name}: {count} lệnh ({percentage:.1f}%)")
    report.append("")
    
    # 3. Phân tích điều kiện không đạt
    report.append("## 3. PHÂN TÍCH ĐIỀU KIỆN KHÔNG ĐẠT")
    report.append("-" * 100)
    if issue_counts:
        for issue, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = issue_percentages[issue]
            issue_name = {
                'DK1_EMA': 'ĐK1: EMA50/EMA200 không đúng',
                'DK2_Swing': 'ĐK2: Không tìm thấy Swing High/Low với RSI',
                'DK3_Pullback': 'ĐK3: Pullback không hợp lệ',
                'DK4_ATR': 'ĐK4: ATR < threshold',
                'DK5_Trendline': 'ĐK5: Không phá vỡ trendline',
                'DK6_Divergence': 'ĐK6: Có Divergence',
                'DK7_RSI_M5': 'ĐK7: RSI(14)_M5 không trong khoảng phù hợp'
            }.get(issue, issue)
            report.append(f"  ❌ {issue_name}: {count} lệnh ({percentage:.1f}%)")
    else:
        report.append("  ✅ Tất cả lệnh đều đạt đủ điều kiện tại entry")
    report.append("")
    
    # 4. Đề xuất cải thiện
    report.append("## 4. ĐỀ XUẤT CẢI THIỆN")
    report.append("-" * 100)
    
    improvements = []
    
    # Check for common issues
    if issue_counts.get('DK1_EMA', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'ĐK1: EMA50/EMA200 không đúng',
            'count': issue_counts['DK1_EMA'],
            'percentage': issue_percentages['DK1_EMA'],
            'suggestion': [
                'Kiểm tra lại logic tính EMA',
                'Thêm filter ADX để xác nhận trend strength',
                'Kiểm tra trend trên timeframe cao hơn (H1)'
            ]
        })
    
    if issue_counts.get('DK3_Pullback', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'ĐK3: Pullback không hợp lệ',
            'count': issue_counts['DK3_Pullback'],
            'percentage': issue_percentages['DK3_Pullback'],
            'suggestion': [
                'Điều chỉnh tham số pullback (max_candles, RSI target)',
                'Kiểm tra lại logic kiểm tra nến giảm/tăng trong pullback',
                'Thêm filter để kiểm tra pullback thật sự'
            ]
        })
    
    if issue_counts.get('DK5_Trendline', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'ĐK5: Không phá vỡ trendline',
            'count': issue_counts['DK5_Trendline'],
            'percentage': issue_percentages['DK5_Trendline'],
            'suggestion': [
                'Kiểm tra lại logic vẽ trendline',
                'Thêm filter để kiểm tra breakout thật sự',
                'Chờ retest sau breakout trước khi vào lệnh'
            ]
        })
    
    if issue_counts.get('DK7_RSI_M5', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'MEDIUM',
            'issue': 'ĐK7: RSI(14)_M5 không trong khoảng phù hợp',
            'count': issue_counts['DK7_RSI_M5'],
            'percentage': issue_percentages['DK7_RSI_M5'],
            'suggestion': [
                'Điều chỉnh khoảng RSI M5 cho phù hợp hơn',
                'Kiểm tra lại logic tính RSI trên M5'
            ]
        })
    
    # SL Analysis
    if exit_reasons.get('HIT_SL', 0) > total_losses * 0.5:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'Quá nhiều lệnh hit SL',
            'count': exit_reasons['HIT_SL'],
            'percentage': exit_percentages['HIT_SL'],
            'suggestion': [
                f'SL trung bình hiện tại: {avg_sl_distance:.1f} pips - có thể quá chặt',
                'Tăng SL buffer (từ 2ATR + 6pt lên 2.5ATR + 10pt)',
                'Thêm filter CHOP/RANGE để tránh trade trong market sideways',
                'Thêm Liquidity Sweep check để tránh false breakout'
            ]
        })
    
    # If all conditions passed but still losing
    all_conditions_passed = len([s for s in all_stats if len(s['issues']) == 0])
    if all_conditions_passed > total_losses * 0.3:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'Lệnh vào đúng điều kiện nhưng vẫn thua',
            'count': all_conditions_passed,
            'percentage': (all_conditions_passed / total_losses * 100),
            'suggestion': [
                'Thêm filter External BOS (Break of Structure)',
                'Thêm Liquidity Filter',
                'Thêm Multi-Timeframe Context (H1 bias)',
                'Cải thiện SL logic - dùng structure level thay vì ATR',
                'Thêm filter để tránh trade trong news events'
            ]
        })
    
    # General improvements
    improvements.append({
        'priority': 'MEDIUM',
        'issue': 'Cải thiện chung',
        'count': 0,
        'percentage': 0,
        'suggestion': [
            'Thêm spam filter dài hơn (từ 60s lên 300s)',
            'Thêm consecutive loss management (dừng sau 2-3 lệnh thua liên tiếp)',
            'Thêm session filter (tránh Asian session nếu không phù hợp)',
            'Thêm volume confirmation',
            'Thêm ATR filter để tránh trade khi market quá yên tĩnh hoặc quá biến động'
        ]
    })
    
    # Write improvements
    for idx, imp in enumerate(improvements, 1):
        if imp['count'] > 0:
            report.append(f"\n### {idx}. [{imp['priority']}] {imp['issue']} ({imp['count']} lệnh - {imp['percentage']:.1f}%)")
        else:
            report.append(f"\n### {idx}. [{imp['priority']}] {imp['issue']}")
        report.append("")
        for sug in imp['suggestion']:
            report.append(f"  • {sug}")
        report.append("")
    
    # 5. Kết luận
    report.append("## 5. KẾT LUẬN")
    report.append("-" * 100)
    report.append("")
    report.append("Dựa trên phân tích, các cải thiện ưu tiên:")
    report.append("")
    
    high_priority = [imp for imp in improvements if imp['priority'] == 'HIGH' and imp['count'] > 0]
    if high_priority:
        report.append("🔴 ƯU TIÊN CAO:")
        for imp in high_priority:
            report.append(f"  - {imp['issue']}: {imp['count']} lệnh ({imp['percentage']:.1f}%)")
        report.append("")
    
    report.append("💡 Khuyến nghị:")
    report.append("  1. Implement các filter ưu tiên cao trước")
    report.append("  2. Test trên demo account trước khi áp dụng live")
    report.append("  3. Monitor kết quả và điều chỉnh thêm")
    report.append("  4. Xem xét clone strategy thành V2 với các cải thiện")
    report.append("")
    report.append("=" * 100)
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    print(f"\n✅ Đã tạo file tổng kết: {output_file}")

def main():
    # Connect to database
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, 'trades.db')
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get total count of losing orders
    count_query = """
    SELECT COUNT(*) as total FROM orders 
    WHERE strategy_name = ? AND profit IS NOT NULL AND profit < 0
    """
    cursor.execute(count_query, (STRATEGY_NAME,))
    total_losing = cursor.fetchone()['total']
    
    if total_losing == 0:
        print(f"✅ Không có lệnh thua nào cho {STRATEGY_NAME}")
        conn.close()
        return
    
    # Ask user how many orders to analyze
    print(f"\n{'='*100}")
    print(f"🔍 PHÂN TÍCH LỆNH THUA: {STRATEGY_NAME} ({SYMBOL_DISPLAY})")
    print(f"{'='*100}")
    print(f"📊 Tổng số lệnh thua trong database: {total_losing}")
    print(f"{'='*100}\n")
    
    while True:
        try:
            num_orders_input = input(f"📝 Nhập số lệnh thua muốn phân tích (1-{total_losing}, Enter để phân tích tất cả): ").strip()
            
            if num_orders_input == "":
                num_orders = total_losing
                print(f"✅ Sẽ phân tích tất cả {num_orders} lệnh thua\n")
                break
            else:
                num_orders = int(num_orders_input)
                if num_orders < 1:
                    print(f"❌ Số lệnh phải >= 1")
                    continue
                elif num_orders > total_losing:
                    print(f"❌ Số lệnh ({num_orders}) vượt quá tổng số lệnh thua ({total_losing})")
                    print(f"   Sẽ phân tích {total_losing} lệnh thua gần nhất\n")
                    num_orders = total_losing
                    break
                else:
                    print(f"✅ Sẽ phân tích {num_orders} lệnh thua gần nhất\n")
                    break
        except ValueError:
            print(f"❌ Vui lòng nhập số hợp lệ")
            continue
        except KeyboardInterrupt:
            print(f"\n❌ Đã hủy")
            conn.close()
            return
    
    # Get losing orders (limited to num_orders)
    query = """
    SELECT * FROM orders 
    WHERE strategy_name = ? AND profit IS NOT NULL AND profit < 0
    ORDER BY open_time DESC
    LIMIT ?
    """
    cursor.execute(query, (STRATEGY_NAME, num_orders))
    losing_orders = cursor.fetchall()
    
    if not losing_orders:
        print(f"✅ Không có lệnh thua nào để phân tích")
        conn.close()
        return
    
    print(f"{'='*100}")
    print(f"📊 Số lệnh sẽ phân tích: {len(losing_orders)}")
    print(f"{'='*100}\n")
    
    # Load config and connect to MT5
    config_path = os.path.join(script_dir, "configs", CONFIG_FILE)
    config = load_config(config_path)
    
    if not config:
        print(f"❌ Cannot load config from {config_path}")
        conn.close()
        return
    
    if not connect_mt5(config):
        print(f"❌ Cannot connect to MT5")
        conn.close()
        return
    
    print(f"✅ Connected to MT5 Account: {config['account']}\n")
    
    # Collect statistics
    all_stats = []
    
    # Analyze each losing order
    for idx, order in enumerate(losing_orders, 1):
        print(f"\n\n{'#'*100}")
        print(f"# LỆNH THUA {idx}/{len(losing_orders)}")
        print(f"{'#'*100}")
        
        # Detailed analysis (for display)
        analyze_order_loss(
            ticket=order['ticket'],
            order_type=order['order_type'],
            open_time_str=order['open_time'],
            open_price=order['open_price'],
            sl=order['sl'],
            tp=order['tp'],
            close_price=order['close_price'],
            profit=order['profit']
        )
        
        # Collect stats
        stat = analyze_order_loss_with_stats(
            ticket=order['ticket'],
            order_type=order['order_type'],
            open_time_str=order['open_time'],
            open_price=order['open_price'],
            sl=order['sl'],
            tp=order['tp'],
            close_price=order['close_price'],
            profit=order['profit']
        )
        
        if stat:
            all_stats.append(stat)
        
        if len(losing_orders) > 1 and idx < len(losing_orders):
            time.sleep(0.5)
    
    # Generate summary report
    output_file = os.path.join(script_dir, f"improvement_report_{STRATEGY_NAME}_{SYMBOL_DISPLAY}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    generate_summary_report(all_stats, output_file)
    
    # Summary statistics
    print(f"\n\n{'='*100}")
    print(f"📊 TỔNG KẾT")
    print(f"{'='*100}")
    print(f"Tổng số lệnh thua đã phân tích: {len(losing_orders)}")
    print(f"Tổng số lệnh có đủ dữ liệu: {len(all_stats)}")
    print(f"{'='*100}\n")
    
    conn.close()
    mt5.shutdown()

if __name__ == "__main__":
    main()

