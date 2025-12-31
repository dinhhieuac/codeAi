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
from utils import load_config, connect_mt5, get_data, calculate_rsi

STRATEGY_NAME = "Strategy_3_PA_Volume"

def analyze_order_loss(ticket, order_type, open_time_str, open_price, sl, tp, close_price, profit):
    """
    Phân tích một lệnh thua để xác định tại sao thua
    """
    print(f"\n{'='*100}")
    print(f"🔻 TICKET: {ticket} | {order_type} | Entry: {open_price:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
    print(f"   Close: {close_price:.2f} | Profit: ${profit:.2f} | Entry Time: {open_time_str}")
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
    
    entry_timestamp = entry_time.timestamp()
    
    # Get symbol from config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_3.json")
    config = load_config(config_path)
    symbol = config['symbol']
    
    # Get data at entry time
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
    
    if len(df_m1_entry) < 20 or len(df_m5_entry) < 200:
        print(f"❌ Not enough data for indicators (M1: {len(df_m1_entry)}, M5: {len(df_m5_entry)})")
        return
    
    # Calculate indicators
    # M5 Trend Filter
    df_m5_entry['ema200'] = df_m5_entry['close'].ewm(span=200, adjust=False).mean()
    m5_trend = "BULLISH" if df_m5_entry.iloc[-1]['close'] > df_m5_entry.iloc[-1]['ema200'] else "BEARISH"
    
    # M1 SMA 9
    df_m1_entry['sma9'] = df_m1_entry['close'].rolling(window=9).mean()
    
    # M1 Volume MA
    df_m1_entry['vol_ma'] = df_m1_entry['tick_volume'].rolling(window=20).mean()
    
    # M1 ATR 14
    df_m1_entry['tr'] = np.maximum(
        df_m1_entry['high'] - df_m1_entry['low'],
        np.maximum(
            abs(df_m1_entry['high'] - df_m1_entry['close'].shift(1)),
            abs(df_m1_entry['low'] - df_m1_entry['close'].shift(1))
        )
    )
    df_m1_entry['atr'] = df_m1_entry['tr'].rolling(window=14).mean()
    
    # M1 RSI
    df_m1_entry['rsi'] = calculate_rsi(df_m1_entry['close'], period=14)
    
    if len(df_m1_entry) < 1:
        print(f"❌ Not enough M1 data")
        return
    
    last = df_m1_entry.iloc[-1]
    
    # Get point size
    point = mt5.symbol_info(symbol).point
    pip_val = point * 10
    
    # Calculate ATR in pips
    atr_value = last['atr'] if not pd.isna(last['atr']) else 0
    atr_pips = (atr_value / point) / 10 if point > 0 else 0
    atr_min = 5
    atr_max = 30
    
    # Check conditions
    volume_threshold = 1.5
    is_high_volume = last['tick_volume'] > (last['vol_ma'] * volume_threshold)
    
    # Pinbar Detection
    body_size = abs(last['close'] - last['open'])
    upper_shadow = last['high'] - max(last['close'], last['open'])
    lower_shadow = min(last['close'], last['open']) - last['low']
    
    min_body = 0.1 * pip_val
    if body_size < min_body:
        body_size = min_body
    
    is_bullish_pinbar = (lower_shadow > 1.5 * body_size) and (upper_shadow < body_size * 1.5)
    is_bearish_pinbar = (upper_shadow > 1.5 * body_size) and (lower_shadow < body_size * 1.5)
    
    # SMA9 distance
    dist_to_sma = abs(last['close'] - last['sma9'])
    is_near_sma = dist_to_sma <= 5000 * point
    
    # Analyze conditions
    print(f"\n📊 [PHÂN TÍCH ĐIỀU KIỆN TẠI THỜI ĐIỂM ENTRY]")
    print(f"{'─'*100}")
    
    issues = []
    passed_conditions = []
    
    # Check M5 Trend
    if order_type == "BUY":
        if m5_trend != "BULLISH":
            issues.append(f"❌ M5 Trend: {m5_trend} (cần BULLISH)")
        else:
            passed_conditions.append(f"✅ M5 Trend: BULLISH")
    else:  # SELL
        if m5_trend != "BEARISH":
            issues.append(f"❌ M5 Trend: {m5_trend} (cần BEARISH)")
        else:
            passed_conditions.append(f"✅ M5 Trend: BEARISH")
    
    # Check ATR Filter
    if atr_pips < atr_min or atr_pips > atr_max:
        issues.append(f"❌ ATR Filter: {atr_pips:.1f}p không trong khoảng {atr_min}-{atr_max}p")
    else:
        passed_conditions.append(f"✅ ATR Filter: {atr_pips:.1f}p trong khoảng {atr_min}-{atr_max}p")
    
    # Check Volume
    if not is_high_volume:
        issues.append(f"❌ Volume: {last['tick_volume']:.0f} < {volume_threshold}x MA ({last['vol_ma']:.0f})")
    else:
        passed_conditions.append(f"✅ Volume: {last['tick_volume']:.0f} > {volume_threshold}x MA ({last['vol_ma']:.0f})")
    
    # Check Pinbar
    if order_type == "BUY":
        if not is_bullish_pinbar:
            issues.append(f"❌ Pinbar: Không phải Bullish Pinbar")
        else:
            passed_conditions.append(f"✅ Pinbar: Bullish Pinbar detected")
    else:  # SELL
        if not is_bearish_pinbar:
            issues.append(f"❌ Pinbar: Không phải Bearish Pinbar")
        else:
            passed_conditions.append(f"✅ Pinbar: Bearish Pinbar detected")
    
    # Check SMA9 Distance
    if not is_near_sma:
        issues.append(f"❌ SMA9 Distance: {dist_to_sma:.1f} points > 5000 points")
    else:
        passed_conditions.append(f"✅ SMA9 Distance: {dist_to_sma:.1f} points <= 5000 points")
    
    # Check Price vs SMA9
    if order_type == "BUY":
        if last['close'] <= last['sma9']:
            issues.append(f"❌ Price vs SMA9: Close {last['close']:.2f} <= SMA9 {last['sma9']:.2f}")
        else:
            passed_conditions.append(f"✅ Price vs SMA9: Close {last['close']:.2f} > SMA9 {last['sma9']:.2f}")
    else:  # SELL
        if last['close'] >= last['sma9']:
            issues.append(f"❌ Price vs SMA9: Close {last['close']:.2f} >= SMA9 {last['sma9']:.2f}")
        else:
            passed_conditions.append(f"✅ Price vs SMA9: Close {last['close']:.2f} < SMA9 {last['sma9']:.2f}")
    
    # Check RSI
    if order_type == "BUY":
        if last['rsi'] <= 50:
            issues.append(f"❌ RSI: {last['rsi']:.1f} <= 50 (cần > 50)")
        else:
            passed_conditions.append(f"✅ RSI: {last['rsi']:.1f} > 50")
    else:  # SELL
        if last['rsi'] >= 50:
            issues.append(f"❌ RSI: {last['rsi']:.1f} >= 50 (cần < 50)")
        else:
            passed_conditions.append(f"✅ RSI: {last['rsi']:.1f} < 50")
    
    # Display results
    print(f"\n✅ ĐIỀU KIỆN ĐẠT ({len(passed_conditions)}/{len(passed_conditions) + len(issues)}):")
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
        
        if sl > 0 and sl_distance < 0.1:
            print(f"   🔴 HIT STOP LOSS: Close {close_price:.2f} ≈ SL {sl:.2f} (distance: {sl_distance:.2f})")
        elif tp > 0 and tp_distance < 0.1:
            print(f"   🟢 HIT TAKE PROFIT: Close {close_price:.2f} ≈ TP {tp:.2f} (distance: {tp_distance:.2f})")
        else:
            print(f"   👤 MANUAL/SCRIPT CLOSE: Close {close_price:.2f} (SL: {sl:.2f}, TP: {tp:.2f})")
    else:
        print(f"   ⚠️ RUNNING/OPEN")
    
    # Summary
    print(f"\n💡 TÓM TẮT:")
    if len(issues) > 0:
        print(f"   ⚠️ Lệnh vào khi có {len(issues)} điều kiện không đạt!")
        print(f"   📋 Các vấn đề: {', '.join([i.split(':')[0].replace('❌ ', '') for i in issues])}")
    else:
        print(f"   ✅ Tất cả điều kiện đạt tại entry")
        print(f"   🤔 Có thể do: SL quá chặt, market reversal, hoặc false pinbar")
    
    # Display indicator values
    print(f"\n📊 GIÁ TRỊ INDICATORS TẠI ENTRY:")
    print(f"   💱 Entry Price: {open_price:.2f}")
    print(f"   📈 M5 Trend: {m5_trend} (EMA200: {df_m5_entry.iloc[-1]['ema200']:.2f})")
    print(f"   📊 SMA9: {last['sma9']:.2f} | Distance: {dist_to_sma:.1f} points")
    print(f"   📊 Volume: {last['tick_volume']:.0f} / MA: {last['vol_ma']:.0f} = {last['tick_volume']/last['vol_ma']:.2f}x")
    print(f"   📊 ATR: {atr_pips:.1f} pips")
    print(f"   📊 RSI: {last['rsi']:.1f}")
    print(f"   📊 Pinbar: {'Bullish' if is_bullish_pinbar else 'Bearish' if is_bearish_pinbar else 'None'}")
    print(f"   🛑 SL: {sl:.2f} | 🎯 TP: {tp:.2f}")
    if order_type == "BUY":
        sl_distance_pips = (open_price - sl) / point / 10 if sl > 0 else 0
        print(f"   📏 SL Distance: {sl_distance_pips:.1f} pips")
    else:
        sl_distance_pips = (sl - open_price) / point / 10 if sl > 0 else 0
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
    config_path = os.path.join(script_dir, "configs", "config_3.json")
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
    
    if len(df_m1_entry) < 20 or len(df_m5_entry) < 200:
        return None
    
    # Calculate indicators
    df_m5_entry['ema200'] = df_m5_entry['close'].ewm(span=200, adjust=False).mean()
    m5_trend = "BULLISH" if df_m5_entry.iloc[-1]['close'] > df_m5_entry.iloc[-1]['ema200'] else "BEARISH"
    
    df_m1_entry['sma9'] = df_m1_entry['close'].rolling(window=9).mean()
    df_m1_entry['vol_ma'] = df_m1_entry['tick_volume'].rolling(window=20).mean()
    
    df_m1_entry['tr'] = np.maximum(
        df_m1_entry['high'] - df_m1_entry['low'],
        np.maximum(
            abs(df_m1_entry['high'] - df_m1_entry['close'].shift(1)),
            abs(df_m1_entry['low'] - df_m1_entry['close'].shift(1))
        )
    )
    df_m1_entry['atr'] = df_m1_entry['tr'].rolling(window=14).mean()
    df_m1_entry['rsi'] = calculate_rsi(df_m1_entry['close'], period=14)
    
    if len(df_m1_entry) < 1:
        return None
    
    last = df_m1_entry.iloc[-1]
    point = mt5.symbol_info(symbol).point
    pip_val = point * 10
    
    atr_value = last['atr'] if not pd.isna(last['atr']) else 0
    atr_pips = (atr_value / point) / 10 if point > 0 else 0
    atr_min = 5
    atr_max = 30
    
    volume_threshold = 1.5
    is_high_volume = last['tick_volume'] > (last['vol_ma'] * volume_threshold)
    
    body_size = abs(last['close'] - last['open'])
    upper_shadow = last['high'] - max(last['close'], last['open'])
    lower_shadow = min(last['close'], last['open']) - last['low']
    
    min_body = 0.1 * pip_val
    if body_size < min_body:
        body_size = min_body
    
    is_bullish_pinbar = (lower_shadow > 1.5 * body_size) and (upper_shadow < body_size * 1.5)
    is_bearish_pinbar = (upper_shadow > 1.5 * body_size) and (lower_shadow < body_size * 1.5)
    
    dist_to_sma = abs(last['close'] - last['sma9'])
    is_near_sma = dist_to_sma <= 5000 * point
    
    # Store indicators
    stats['indicators'] = {
        'trend': m5_trend,
        'rsi': float(last['rsi']),
        'atr_pips': float(atr_pips),
        'volume_ratio': float(last['tick_volume'] / last['vol_ma']) if last['vol_ma'] > 0 else 0,
        'sma9': float(last['sma9']),
        'dist_to_sma': float(dist_to_sma)
    }
    
    # Check conditions
    if order_type == "BUY":
        if m5_trend != "BULLISH":
            stats['issues'].append("M5_Trend")
        else:
            stats['passed_conditions'].append("M5_Trend")
        
        if atr_pips < atr_min or atr_pips > atr_max:
            stats['issues'].append("ATR_Filter")
        else:
            stats['passed_conditions'].append("ATR_Filter")
        
        if not is_high_volume:
            stats['issues'].append("Volume")
        else:
            stats['passed_conditions'].append("Volume")
        
        if not is_bullish_pinbar:
            stats['issues'].append("Pinbar")
        else:
            stats['passed_conditions'].append("Pinbar")
        
        if not is_near_sma:
            stats['issues'].append("SMA9_Distance")
        else:
            stats['passed_conditions'].append("SMA9_Distance")
        
        if last['close'] <= last['sma9']:
            stats['issues'].append("Price_vs_SMA9")
        else:
            stats['passed_conditions'].append("Price_vs_SMA9")
        
        if last['rsi'] <= 50:
            stats['issues'].append("RSI")
        else:
            stats['passed_conditions'].append("RSI")
        
        stats['sl_distance_pips'] = (open_price - sl) / point / 10 if sl > 0 else 0
    else:  # SELL
        if m5_trend != "BEARISH":
            stats['issues'].append("M5_Trend")
        else:
            stats['passed_conditions'].append("M5_Trend")
        
        if atr_pips < atr_min or atr_pips > atr_max:
            stats['issues'].append("ATR_Filter")
        else:
            stats['passed_conditions'].append("ATR_Filter")
        
        if not is_high_volume:
            stats['issues'].append("Volume")
        else:
            stats['passed_conditions'].append("Volume")
        
        if not is_bearish_pinbar:
            stats['issues'].append("Pinbar")
        else:
            stats['passed_conditions'].append("Pinbar")
        
        if not is_near_sma:
            stats['issues'].append("SMA9_Distance")
        else:
            stats['passed_conditions'].append("SMA9_Distance")
        
        if last['close'] >= last['sma9']:
            stats['issues'].append("Price_vs_SMA9")
        else:
            stats['passed_conditions'].append("Price_vs_SMA9")
        
        if last['rsi'] >= 50:
            stats['issues'].append("RSI")
        else:
            stats['passed_conditions'].append("RSI")
        
        stats['sl_distance_pips'] = (sl - open_price) / point / 10 if sl > 0 else 0
    
    # Exit reason
    if close_price:
        sl_distance = abs(close_price - sl) if sl > 0 else 999
        tp_distance = abs(close_price - tp) if tp > 0 else 999
        
        if sl > 0 and sl_distance < 0.1:
            stats['exit_reason'] = "HIT_SL"
        elif tp > 0 and tp_distance < 0.1:
            stats['exit_reason'] = "HIT_TP"
        else:
            stats['exit_reason'] = "MANUAL_CLOSE"
    else:
        stats['exit_reason'] = "RUNNING"
    
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
    
    issue_percentages = {k: (v / total_losses * 100) for k, v in issue_counts.items()}
    exit_percentages = {k: (v / total_losses * 100) for k, v in exit_reasons.items()}
    avg_sl_distance = sum(sl_distances) / len(sl_distances) if sl_distances else 0
    
    # Generate report
    report = []
    report.append("=" * 100)
    report.append("📊 BÁO CÁO TỔNG KẾT PHÂN TÍCH LỆNH THUA")
    report.append(f"Strategy: {STRATEGY_NAME}")
    report.append(f"Ngày tạo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 100)
    report.append("")
    
    report.append("## 1. TỔNG QUAN")
    report.append("-" * 100)
    report.append(f"Tổng số lệnh thua phân tích: {total_losses}")
    report.append(f"Tổng lỗ: ${sum([s['profit'] for s in all_stats]):.2f}")
    report.append(f"Lỗ trung bình: ${avg_profit:.2f}")
    report.append(f"Khoảng cách SL trung bình: {avg_sl_distance:.1f} pips")
    report.append("")
    
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
    
    report.append("## 3. PHÂN TÍCH ĐIỀU KIỆN KHÔNG ĐẠT")
    report.append("-" * 100)
    if issue_counts:
        for issue, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = issue_percentages[issue]
            issue_name = {
                'M5_Trend': 'M5 Trend không đúng',
                'ATR_Filter': 'ATR Filter không đạt',
                'Volume': 'Volume không đủ',
                'Pinbar': 'Không phải Pinbar',
                'SMA9_Distance': 'Giá quá xa SMA9',
                'Price_vs_SMA9': 'Price vs SMA9 không đúng',
                'RSI': 'RSI không đạt ngưỡng'
            }.get(issue, issue)
            report.append(f"  ❌ {issue_name}: {count} lệnh ({percentage:.1f}%)")
    else:
        report.append("  ✅ Tất cả lệnh đều đạt đủ điều kiện tại entry")
    report.append("")
    
    report.append("## 4. ĐỀ XUẤT CẢI THIỆN")
    report.append("-" * 100)
    
    improvements = []
    
    if issue_counts.get('M5_Trend', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'M5 Trend không đúng',
            'count': issue_counts['M5_Trend'],
            'percentage': issue_percentages['M5_Trend'],
            'suggestion': [
                'Thêm ADX filter trên M5 để xác nhận trend strength',
                'Kiểm tra trend trên timeframe cao hơn (H1)'
            ]
        })
    
    if issue_counts.get('Pinbar', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'Không phải Pinbar',
            'count': issue_counts['Pinbar'],
            'percentage': issue_percentages['Pinbar'],
            'suggestion': [
                'Tăng threshold cho Pinbar detection',
                'Thêm confirmation: chờ 1-2 nến sau Pinbar'
            ]
        })
    
    if issue_counts.get('Volume', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'MEDIUM',
            'issue': 'Volume không đủ',
            'count': issue_counts['Volume'],
            'percentage': issue_percentages['Volume'],
            'suggestion': [
                'Tăng volume threshold từ 1.5x lên 1.8x',
                'Thêm check: volume phải tăng trong 2-3 nến liên tiếp'
            ]
        })
    
    if exit_reasons.get('HIT_SL', 0) > total_losses * 0.5:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'Quá nhiều lệnh hit SL',
            'count': exit_reasons['HIT_SL'],
            'percentage': exit_percentages['HIT_SL'],
            'suggestion': [
                f'SL trung bình hiện tại: {avg_sl_distance:.1f} pips - có thể quá chặt',
                'Tăng SL buffer',
                'Thêm filter CHOP/RANGE để tránh trade trong market sideways'
            ]
        })
    
    improvements.append({
        'priority': 'MEDIUM',
        'issue': 'Cải thiện chung',
        'count': 0,
        'percentage': 0,
        'suggestion': [
            'Thêm consecutive loss management',
            'Thêm session filter',
            'Thêm spread filter check'
        ]
    })
    
    for idx, imp in enumerate(improvements, 1):
        if imp['count'] > 0:
            report.append(f"\n### {idx}. [{imp['priority']}] {imp['issue']} ({imp['count']} lệnh - {imp['percentage']:.1f}%)")
        else:
            report.append(f"\n### {idx}. [{imp['priority']}] {imp['issue']}")
        report.append("")
        for sug in imp['suggestion']:
            report.append(f"  • {sug}")
        report.append("")
    
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
    report.append("")
    report.append("=" * 100)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    print(f"\n✅ Đã tạo file tổng kết: {output_file}")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, 'trades.db')
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
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
    
    print(f"\n{'='*100}")
    print(f"🔍 PHÂN TÍCH LỆNH THUA: {STRATEGY_NAME}")
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
    
    config_path = os.path.join(script_dir, "configs", "config_3.json")
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
    
    all_stats = []
    
    for idx, order in enumerate(losing_orders, 1):
        print(f"\n\n{'#'*100}")
        print(f"# LỆNH THUA {idx}/{len(losing_orders)}")
        print(f"{'#'*100}")
        
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
    
    output_file = os.path.join(script_dir, f"improvement_report_{STRATEGY_NAME}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    generate_summary_report(all_stats, output_file)
    
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

