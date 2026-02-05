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
from utils import load_config, connect_mt5, get_data, calculate_rsi, calculate_adx

STRATEGY_NAME = "Strategy_4_UT_Bot"

def calculate_ut_bot(df, sensitivity=2, period=10):
    """
    UT Bot Logic: ATR Trailing Stop
    """
    df['atr'] = df['high'].combine(df['close'].shift(1), max) - df['low'].combine(df['close'].shift(1), min)
    df['atr'] = df['atr'].rolling(window=period).mean()
    df['n_loss'] = sensitivity * df['atr']
    
    # Initialize Stop Logic columns
    df['x_atr_trailing_stop'] = 0.0
    df['pos'] = 0  # 1 for Buy, -1 for Sell
    
    for i in range(1, len(df)):
        # Calculate trailing stop
        if df.at[i, 'close'] > df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] > df.at[i-1, 'x_atr_trailing_stop']:
            df.at[i, 'x_atr_trailing_stop'] = max(df.at[i-1, 'x_atr_trailing_stop'], df.at[i, 'close'] - df.at[i, 'n_loss'])
        elif df.at[i, 'close'] < df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] < df.at[i-1, 'x_atr_trailing_stop']:
            df.at[i, 'x_atr_trailing_stop'] = min(df.at[i-1, 'x_atr_trailing_stop'], df.at[i, 'close'] + df.at[i, 'n_loss'])
        elif df.at[i, 'close'] > df.at[i-1, 'x_atr_trailing_stop']:
            df.at[i, 'x_atr_trailing_stop'] = df.at[i, 'close'] - df.at[i, 'n_loss']
        else:
            df.at[i, 'x_atr_trailing_stop'] = df.at[i, 'close'] + df.at[i, 'n_loss']
            
        # Determine Position
        prev_pos = df.at[i-1, 'pos']
        if df.at[i, 'close'] > df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] < df.at[i-1, 'x_atr_trailing_stop']:
             df.at[i, 'pos'] = 1  # BUY Signal transition
        elif df.at[i, 'close'] < df.at[i-1, 'x_atr_trailing_stop'] and df.at[i-1, 'close'] > df.at[i-1, 'x_atr_trailing_stop']:
             df.at[i, 'pos'] = -1  # SELL Signal transition
        else:
             df.at[i, 'pos'] = prev_pos if prev_pos != 0 else (1 if df.at[i, 'close'] > df.at[i, 'x_atr_trailing_stop'] else -1)

    return df

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
    
    # Convert to UTC timestamp for MT5
    entry_timestamp = entry_time.timestamp()
    
    # Get symbol from config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_4.json")
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
    
    # Fetch H1 data
    rates_h1 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_H1, from_timestamp, 100)
    if rates_h1 is None or len(rates_h1) == 0:
        print(f"❌ Cannot get H1 data for entry time")
        return
    
    df_h1 = pd.DataFrame(rates_h1)
    df_h1['time'] = pd.to_datetime(df_h1['time'], unit='s')
    
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
    df_h1_entry = df_h1[df_h1['time'] <= entry_time].copy()
    
    if len(df_m1_entry) < 20 or len(df_h1_entry) < 50:
        print(f"❌ Not enough data for indicators (M1: {len(df_m1_entry)}, H1: {len(df_h1_entry)})")
        return
    
    # Calculate indicators
    # H1 Trend Filter
    df_h1_entry['ema50'] = df_h1_entry['close'].ewm(span=50, adjust=False).mean()
    h1_trend = "BULLISH" if df_h1_entry.iloc[-1]['close'] > df_h1_entry.iloc[-1]['ema50'] else "BEARISH"
    
    # M1 RSI
    df_m1_entry['rsi'] = calculate_rsi(df_m1_entry['close'], period=14)
    
    # M1 ADX
    df_m1_entry = calculate_adx(df_m1_entry, period=14)
    adx_value = df_m1_entry.iloc[-1]['adx']
    adx_threshold = 20
    
    # UT Bot calculation
    df_ut = calculate_ut_bot(df_m1_entry, sensitivity=2, period=10)
    
    if len(df_ut) < 2:
        print(f"❌ Not enough UT Bot data")
        return
    
    last = df_ut.iloc[-1]
    prev = df_ut.iloc[-2]
    
    # Check UT Signal
    ut_signal = None
    if prev['pos'] == -1 and last['pos'] == 1:
        ut_signal = "BUY"
    elif prev['pos'] == 1 and last['pos'] == -1:
        ut_signal = "SELL"
    
    # Analyze conditions
    print(f"\n📊 [PHÂN TÍCH ĐIỀU KIỆN TẠI THỜI ĐIỂM ENTRY]")
    print(f"{'─'*100}")
    
    issues = []
    passed_conditions = []
    
    # Check ADX
    if pd.isna(adx_value) or adx_value < adx_threshold:
        issues.append(f"❌ ADX: {adx_value:.1f} < {adx_threshold} (cần >= {adx_threshold})")
    else:
        passed_conditions.append(f"✅ ADX: {adx_value:.1f} >= {adx_threshold}")
    
    # Check UT Signal
    if order_type == "BUY":
        if ut_signal != "BUY":
            issues.append(f"❌ UT Signal: {ut_signal} (cần BUY, Pos: {prev['pos']} → {last['pos']})")
        else:
            passed_conditions.append(f"✅ UT Signal: BUY (Pos: {prev['pos']} → {last['pos']})")
    else:  # SELL
        if ut_signal != "SELL":
            issues.append(f"❌ UT Signal: {ut_signal} (cần SELL, Pos: {prev['pos']} → {last['pos']})")
        else:
            passed_conditions.append(f"✅ UT Signal: SELL (Pos: {prev['pos']} → {last['pos']})")
    
    # Check H1 Trend
    if order_type == "BUY":
        if h1_trend != "BULLISH":
            issues.append(f"❌ H1 Trend: {h1_trend} (cần BULLISH)")
        else:
            passed_conditions.append(f"✅ H1 Trend: BULLISH")
    else:  # SELL
        if h1_trend != "BEARISH":
            issues.append(f"❌ H1 Trend: {h1_trend} (cần BEARISH)")
        else:
            passed_conditions.append(f"✅ H1 Trend: BEARISH")
    
    # Check RSI
    rsi_threshold = 50
    if order_type == "BUY":
        if last['rsi'] <= rsi_threshold:
            issues.append(f"❌ RSI: {last['rsi']:.1f} <= {rsi_threshold} (cần > {rsi_threshold})")
        else:
            passed_conditions.append(f"✅ RSI: {last['rsi']:.1f} > {rsi_threshold}")
    else:  # SELL
        if last['rsi'] >= rsi_threshold:
            issues.append(f"❌ RSI: {last['rsi']:.1f} >= {rsi_threshold} (cần < {rsi_threshold})")
        else:
            passed_conditions.append(f"✅ RSI: {last['rsi']:.1f} < {rsi_threshold}")
    
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
        print(f"   🤔 Có thể do: SL quá chặt, market reversal, hoặc false signal")
    
    # Display indicator values
    print(f"\n📊 GIÁ TRỊ INDICATORS TẠI ENTRY:")
    print(f"   💱 Entry Price: {open_price:.2f}")
    print(f"   📈 H1 Trend: {h1_trend} (EMA50: {df_h1_entry.iloc[-1]['ema50']:.2f})")
    print(f"   📊 ADX: {adx_value:.1f} (cần >= {adx_threshold})")
    print(f"   📊 UT Position: {last['pos']} (Prev: {prev['pos']})")
    print(f"   📊 UT Trailing Stop: {last.get('x_atr_trailing_stop', 0):.2f}")
    print(f"   📊 RSI: {last['rsi']:.1f} (BUY cần > {rsi_threshold}, SELL cần < {rsi_threshold})")
    print(f"   🛑 SL: {sl:.2f} | 🎯 TP: {tp:.2f}")
    if order_type == "BUY":
        sl_distance_pips = (open_price - sl) / 0.01 if sl > 0 else 0
        print(f"   📏 SL Distance: {sl_distance_pips:.1f} pips")
    else:
        sl_distance_pips = (sl - open_price) / 0.01 if sl > 0 else 0
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
    config_path = os.path.join(script_dir, "configs", "config_4.json")
    config = load_config(config_path)
    symbol = config['symbol']
    
    from_time = datetime.fromtimestamp(entry_timestamp) - timedelta(hours=10)
    from_timestamp = int(from_time.timestamp())
    
    # Fetch data
    rates_m1 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M1, from_timestamp, 300)
    rates_h1 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_H1, from_timestamp, 100)
    
    if rates_m1 is None or len(rates_m1) == 0 or rates_h1 is None or len(rates_h1) == 0:
        return None
    
    df_m1 = pd.DataFrame(rates_m1)
    df_m1['time'] = pd.to_datetime(df_m1['time'], unit='s')
    df_h1 = pd.DataFrame(rates_h1)
    df_h1['time'] = pd.to_datetime(df_h1['time'], unit='s')
    
    entry_idx_m1 = None
    for i in range(len(df_m1) - 1, -1, -1):
        if df_m1.iloc[i]['time'] <= entry_time:
            entry_idx_m1 = i
            break
    
    if entry_idx_m1 is None:
        return None
    
    df_m1_entry = df_m1.iloc[:entry_idx_m1+1].copy()
    df_h1_entry = df_h1[df_h1['time'] <= entry_time].copy()
    
    if len(df_m1_entry) < 20 or len(df_h1_entry) < 50:
        return None
    
    # Calculate indicators
    df_h1_entry['ema50'] = df_h1_entry['close'].ewm(span=50, adjust=False).mean()
    h1_trend = "BULLISH" if df_h1_entry.iloc[-1]['close'] > df_h1_entry.iloc[-1]['ema50'] else "BEARISH"
    
    df_m1_entry['rsi'] = calculate_rsi(df_m1_entry['close'], period=14)
    df_m1_entry = calculate_adx(df_m1_entry, period=14)
    adx_value = df_m1_entry.iloc[-1]['adx']
    adx_threshold = 20
    
    df_ut = calculate_ut_bot(df_m1_entry, sensitivity=2, period=10)
    
    if len(df_ut) < 2:
        return None
    
    last = df_ut.iloc[-1]
    prev = df_ut.iloc[-2]
    
    ut_signal = None
    if prev['pos'] == -1 and last['pos'] == 1:
        ut_signal = "BUY"
    elif prev['pos'] == 1 and last['pos'] == -1:
        ut_signal = "SELL"
    
    # Store indicators
    stats['indicators'] = {
        'h1_trend': h1_trend,
        'adx': float(adx_value) if pd.notna(adx_value) else 0.0,
        'rsi': float(last['rsi']),
        'ut_pos': int(last['pos']),
        'ut_pos_prev': int(prev['pos']),
        'ut_signal': ut_signal
    }
    
    # Check conditions
    rsi_threshold = 50
    
    if order_type == "BUY":
        if pd.isna(adx_value) or adx_value < adx_threshold:
            stats['issues'].append("ADX")
        else:
            stats['passed_conditions'].append("ADX")
        
        if ut_signal != "BUY":
            stats['issues'].append("UT_Signal")
        else:
            stats['passed_conditions'].append("UT_Signal")
        
        if h1_trend != "BULLISH":
            stats['issues'].append("H1_Trend")
        else:
            stats['passed_conditions'].append("H1_Trend")
        
        if last['rsi'] <= rsi_threshold:
            stats['issues'].append("RSI")
        else:
            stats['passed_conditions'].append("RSI")
        
        stats['sl_distance_pips'] = (open_price - sl) / 0.01 if sl > 0 else 0
    else:  # SELL
        if pd.isna(adx_value) or adx_value < adx_threshold:
            stats['issues'].append("ADX")
        else:
            stats['passed_conditions'].append("ADX")
        
        if ut_signal != "SELL":
            stats['issues'].append("UT_Signal")
        else:
            stats['passed_conditions'].append("UT_Signal")
        
        if h1_trend != "BEARISH":
            stats['issues'].append("H1_Trend")
        else:
            stats['passed_conditions'].append("H1_Trend")
        
        if last['rsi'] >= rsi_threshold:
            stats['issues'].append("RSI")
        else:
            stats['passed_conditions'].append("RSI")
        
        stats['sl_distance_pips'] = (sl - open_price) / 0.01 if sl > 0 else 0
    
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
    
    # Calculate percentages
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
                'ADX': 'ADX không đạt (cần >= 20)',
                'UT_Signal': 'UT Signal không đúng (không có pos flip)',
                'H1_Trend': 'H1 Trend không đúng',
                'RSI': 'RSI không đạt ngưỡng (BUY > 50, SELL < 50)'
            }.get(issue, issue)
            report.append(f"  ❌ {issue_name}: {count} lệnh ({percentage:.1f}%)")
    else:
        report.append("  ✅ Tất cả lệnh đều đạt đủ điều kiện tại entry")
    report.append("")
    
    # 4. Đề xuất cải thiện
    report.append("## 4. ĐỀ XUẤT CẢI THIỆN")
    report.append("-" * 100)
    
    improvements = []
    
    if issue_counts.get('ADX', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'ADX không đạt',
            'count': issue_counts['ADX'],
            'percentage': issue_percentages['ADX'],
            'suggestion': [
                'Tăng ADX threshold từ 20 lên 25 để chỉ trade khi trend mạnh hơn',
                'Kiểm tra ADX trên timeframe cao hơn (H1)'
            ]
        })
    
    if issue_counts.get('UT_Signal', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'UT Signal không đúng',
            'count': issue_counts['UT_Signal'],
            'percentage': issue_percentages['UT_Signal'],
            'suggestion': [
                'Kiểm tra lại UT Bot calculation logic',
                'Thêm confirmation: chờ 1-2 nến sau UT signal',
                'Thêm volume confirmation cho UT signal'
            ]
        })
    
    if issue_counts.get('H1_Trend', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'H1 Trend không đúng',
            'count': issue_counts['H1_Trend'],
            'percentage': issue_percentages['H1_Trend'],
            'suggestion': [
                'Thêm ADX filter trên H1 để xác nhận trend strength',
                'Kiểm tra trend trên timeframe cao hơn (H4/D1)'
            ]
        })
    
    if issue_counts.get('RSI', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'MEDIUM',
            'issue': 'RSI không đạt ngưỡng',
            'count': issue_counts['RSI'],
            'percentage': issue_percentages['RSI'],
            'suggestion': [
                'Tăng RSI threshold: BUY > 55, SELL < 45',
                'Thêm RSI momentum check (RSI đang tăng/giảm)'
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
                'Tăng SL buffer (từ 20 points lên 1.5x ATR)',
                'Thêm volume confirmation để tránh false signals',
                'Thêm filter để tránh trade trong news events'
            ]
        })
    
    improvements.append({
        'priority': 'MEDIUM',
        'issue': 'Cải thiện chung',
        'count': 0,
        'percentage': 0,
        'suggestion': [
            'Thêm volume confirmation (volume > 1.3x average)',
            'Thêm consecutive loss management',
            'Thêm session filter (tránh Asian session)'
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
    report.append("  1. Kiểm tra lại UT Bot calculation logic")
    report.append("  2. Tăng ADX threshold nếu vẫn có nhiều lệnh thua")
    report.append("  3. Thêm volume confirmation")
    report.append("  4. Test trên demo account trước khi áp dụng")
    report.append("  5. Monitor kết quả và điều chỉnh thêm")
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
    
    # Get losing orders
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
    config_path = os.path.join(script_dir, "configs", "config_4.json")
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
    
    # Generate summary report
    output_file = os.path.join(script_dir, f"improvement_report_{STRATEGY_NAME}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
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

