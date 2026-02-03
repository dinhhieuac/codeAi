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
from utils import load_config, connect_mt5, get_data, calculate_heiken_ashi, is_doji, calculate_rsi

STRATEGY_NAME = "Strategy_1_Trend_HA"

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
    config_path = os.path.join(script_dir, "configs", "config_1.json")
    config = load_config(config_path)
    symbol = config['symbol']
    
    # Get data at entry time (need enough data for indicators)
    # We need to get data BEFORE entry time to calculate indicators
    # Get 300 candles before entry to ensure we have enough for EMA200, SMA55, etc.
    from_time = datetime.fromtimestamp(entry_timestamp) - timedelta(hours=10)  # 10 hours before
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
    # For M1, find the candle that contains entry_time
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
    
    if len(df_m1_entry) < 55 or len(df_m5_entry) < 200:
        print(f"❌ Not enough data for indicators (M1: {len(df_m1_entry)}, M5: {len(df_m5_entry)})")
        return
    
    # Calculate indicators
    # M5 EMA200
    df_m5_entry['ema200'] = df_m5_entry['close'].rolling(window=200).mean()
    current_trend = "BULLISH" if df_m5_entry.iloc[-1]['close'] > df_m5_entry.iloc[-1]['ema200'] else "BEARISH"
    
    # M1 SMA55 High/Low
    df_m1_entry['sma55_high'] = df_m1_entry['high'].rolling(window=55).mean()
    df_m1_entry['sma55_low'] = df_m1_entry['low'].rolling(window=55).mean()
    
    # Heiken Ashi
    ha_df = calculate_heiken_ashi(df_m1_entry)
    
    # RSI
    ha_df['rsi'] = calculate_rsi(df_m1_entry['close'], period=14)
    
    # Get last 2 HA candles
    if len(ha_df) < 2:
        print(f"❌ Not enough HA candles")
        return
    
    last_ha = ha_df.iloc[-1]
    prev_ha = ha_df.iloc[-2]
    
    # Analyze conditions
    print(f"\n📊 [PHÂN TÍCH ĐIỀU KIỆN TẠI THỜI ĐIỂM ENTRY]")
    print(f"{'─'*100}")
    
    issues = []
    passed_conditions = []
    
    # Check M5 Trend
    if order_type == "BUY":
        if current_trend != "BULLISH":
            issues.append(f"❌ M5 Trend: {current_trend} (cần BULLISH)")
        else:
            passed_conditions.append(f"✅ M5 Trend: BULLISH")
    else:  # SELL
        if current_trend != "BEARISH":
            issues.append(f"❌ M5 Trend: {current_trend} (cần BEARISH)")
        else:
            passed_conditions.append(f"✅ M5 Trend: BEARISH")
    
    # Check HA Candle
    if order_type == "BUY":
        is_green = last_ha['ha_close'] > last_ha['ha_open']
        if not is_green:
            issues.append(f"❌ HA Candle: Red (cần Green)")
        else:
            passed_conditions.append(f"✅ HA Candle: Green")
    else:  # SELL
        is_red = last_ha['ha_close'] < last_ha['ha_open']
        if not is_red:
            issues.append(f"❌ HA Candle: Green (cần Red)")
        else:
            passed_conditions.append(f"✅ HA Candle: Red")
    
    # Check Channel
    if order_type == "BUY":
        is_above_channel = last_ha['ha_close'] > last_ha['sma55_high']
        if not is_above_channel:
            issues.append(f"❌ Above Channel: {last_ha['ha_close']:.2f} <= {last_ha['sma55_high']:.2f}")
        else:
            passed_conditions.append(f"✅ Above Channel: {last_ha['ha_close']:.2f} > {last_ha['sma55_high']:.2f}")
    else:  # SELL
        is_below_channel = last_ha['ha_close'] < last_ha['sma55_low']
        if not is_below_channel:
            issues.append(f"❌ Below Channel: {last_ha['ha_close']:.2f} >= {last_ha['sma55_low']:.2f}")
        else:
            passed_conditions.append(f"✅ Below Channel: {last_ha['ha_close']:.2f} < {last_ha['sma55_low']:.2f}")
    
    # Check Fresh Breakout
    if order_type == "BUY":
        is_fresh_breakout = prev_ha['ha_close'] <= prev_ha['sma55_high']
        if not is_fresh_breakout:
            issues.append(f"❌ Fresh Breakout: Prev HA {prev_ha['ha_close']:.2f} > SMA55 High {prev_ha['sma55_high']:.2f}")
        else:
            passed_conditions.append(f"✅ Fresh Breakout: Prev HA {prev_ha['ha_close']:.2f} <= SMA55 High {prev_ha['sma55_high']:.2f}")
    else:  # SELL
        is_fresh_breakout = prev_ha['ha_close'] >= prev_ha['sma55_low']
        if not is_fresh_breakout:
            issues.append(f"❌ Fresh Breakout: Prev HA {prev_ha['ha_close']:.2f} < SMA55 Low {prev_ha['sma55_low']:.2f}")
        else:
            passed_conditions.append(f"✅ Fresh Breakout: Prev HA {prev_ha['ha_close']:.2f} >= SMA55 Low {prev_ha['sma55_low']:.2f}")
    
    # Check Solid Candle (not Doji)
    is_solid = not is_doji(last_ha, threshold=0.2)
    if not is_solid:
        issues.append(f"❌ Solid Candle: Doji detected (Indecision)")
    else:
        passed_conditions.append(f"✅ Solid Candle: Not Doji")
    
    # Check RSI
    if order_type == "BUY":
        if last_ha['rsi'] <= 50:
            issues.append(f"❌ RSI: {last_ha['rsi']:.1f} <= 50 (cần > 50)")
        else:
            passed_conditions.append(f"✅ RSI: {last_ha['rsi']:.1f} > 50")
    else:  # SELL
        if last_ha['rsi'] >= 50:
            issues.append(f"❌ RSI: {last_ha['rsi']:.1f} >= 50 (cần < 50)")
        else:
            passed_conditions.append(f"✅ RSI: {last_ha['rsi']:.1f} < 50")
    
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
        
        if sl > 0 and sl_distance < 0.1:  # Within 0.1 (10 points)
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
        print(f"   🤔 Có thể do: SL quá chặt, market reversal, hoặc false breakout")
    
    # Display indicator values
    print(f"\n📊 GIÁ TRỊ INDICATORS TẠI ENTRY:")
    print(f"   💱 Entry Price: {open_price:.2f}")
    print(f"   📈 M5 Trend: {current_trend} (EMA200: {df_m5_entry.iloc[-1]['ema200']:.2f})")
    print(f"   📊 HA Close: {last_ha['ha_close']:.2f} | HA Open: {last_ha['ha_open']:.2f}")
    print(f"   📊 SMA55 High: {last_ha['sma55_high']:.2f} | SMA55 Low: {last_ha['sma55_low']:.2f}")
    print(f"   📊 RSI: {last_ha['rsi']:.1f}")
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
    config_path = os.path.join(script_dir, "configs", "config_1.json")
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
    
    if len(df_m1_entry) < 55 or len(df_m5_entry) < 200:
        return None
    
    # Calculate indicators
    df_m5_entry['ema200'] = df_m5_entry['close'].rolling(window=200).mean()
    current_trend = "BULLISH" if df_m5_entry.iloc[-1]['close'] > df_m5_entry.iloc[-1]['ema200'] else "BEARISH"
    
    df_m1_entry['sma55_high'] = df_m1_entry['high'].rolling(window=55).mean()
    df_m1_entry['sma55_low'] = df_m1_entry['low'].rolling(window=55).mean()
    
    ha_df = calculate_heiken_ashi(df_m1_entry)
    ha_df['rsi'] = calculate_rsi(df_m1_entry['close'], period=14)
    
    if len(ha_df) < 2:
        return None
    
    last_ha = ha_df.iloc[-1]
    prev_ha = ha_df.iloc[-2]
    
    # Store indicators
    stats['indicators'] = {
        'trend': current_trend,
        'rsi': float(last_ha['rsi']),
        'ha_close': float(last_ha['ha_close']),
        'sma55_high': float(last_ha['sma55_high']),
        'sma55_low': float(last_ha['sma55_low'])
    }
    
    # Check conditions
    if order_type == "BUY":
        if current_trend != "BULLISH":
            stats['issues'].append("M5_Trend")
        else:
            stats['passed_conditions'].append("M5_Trend")
        
        is_green = last_ha['ha_close'] > last_ha['ha_open']
        if not is_green:
            stats['issues'].append("HA_Candle")
        else:
            stats['passed_conditions'].append("HA_Candle")
        
        is_above_channel = last_ha['ha_close'] > last_ha['sma55_high']
        if not is_above_channel:
            stats['issues'].append("Above_Channel")
        else:
            stats['passed_conditions'].append("Above_Channel")
        
        is_fresh_breakout = prev_ha['ha_close'] <= prev_ha['sma55_high']
        if not is_fresh_breakout:
            stats['issues'].append("Fresh_Breakout")
        else:
            stats['passed_conditions'].append("Fresh_Breakout")
        
        is_solid = not is_doji(last_ha, threshold=0.2)
        if not is_solid:
            stats['issues'].append("Solid_Candle")
        else:
            stats['passed_conditions'].append("Solid_Candle")
        
        if last_ha['rsi'] <= 50:
            stats['issues'].append("RSI")
        else:
            stats['passed_conditions'].append("RSI")
        
        stats['sl_distance_pips'] = (open_price - sl) / 0.01 if sl > 0 else 0
    else:  # SELL
        if current_trend != "BEARISH":
            stats['issues'].append("M5_Trend")
        else:
            stats['passed_conditions'].append("M5_Trend")
        
        is_red = last_ha['ha_close'] < last_ha['ha_open']
        if not is_red:
            stats['issues'].append("HA_Candle")
        else:
            stats['passed_conditions'].append("HA_Candle")
        
        is_below_channel = last_ha['ha_close'] < last_ha['sma55_low']
        if not is_below_channel:
            stats['issues'].append("Below_Channel")
        else:
            stats['passed_conditions'].append("Below_Channel")
        
        is_fresh_breakout = prev_ha['ha_close'] >= prev_ha['sma55_low']
        if not is_fresh_breakout:
            stats['issues'].append("Fresh_Breakout")
        else:
            stats['passed_conditions'].append("Fresh_Breakout")
        
        is_solid = not is_doji(last_ha, threshold=0.2)
        if not is_solid:
            stats['issues'].append("Solid_Candle")
        else:
            stats['passed_conditions'].append("Solid_Candle")
        
        if last_ha['rsi'] >= 50:
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
        # Count issues
        for issue in stat['issues']:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
        
        # Count exit reasons
        exit_reasons[stat['exit_reason']] = exit_reasons.get(stat['exit_reason'], 0) + 1
        
        # SL distances
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
                'M5_Trend': 'M5 Trend không đúng',
                'HA_Candle': 'HA Candle không đúng màu',
                'Above_Channel': 'Không Above Channel (BUY)',
                'Below_Channel': 'Không Below Channel (SELL)',
                'Fresh_Breakout': 'Không phải Fresh Breakout',
                'Solid_Candle': 'Doji Candle (Indecision)',
                'RSI': 'RSI không đạt ngưỡng'
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
    if issue_counts.get('M5_Trend', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'M5 Trend không đúng',
            'count': issue_counts['M5_Trend'],
            'percentage': issue_percentages['M5_Trend'],
            'suggestion': [
                'Thêm filter ADX để xác nhận trend strength (ADX >= 20)',
                'Kiểm tra trend trên timeframe cao hơn (H1) để xác nhận',
                'Chờ confirmation từ nhiều timeframe trước khi vào lệnh'
            ]
        })
    
    if issue_counts.get('Fresh_Breakout', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'HIGH',
            'issue': 'Không phải Fresh Breakout',
            'count': issue_counts['Fresh_Breakout'],
            'percentage': issue_percentages['Fresh_Breakout'],
            'suggestion': [
                'Thêm filter để kiểm tra breakout thật sự (volume confirmation)',
                'Chờ retest sau breakout trước khi vào lệnh',
                'Kiểm tra xem có false breakout không (nến đóng ngược lại)'
            ]
        })
    
    if issue_counts.get('RSI', 0) > total_losses * 0.3:
        improvements.append({
            'priority': 'MEDIUM',
            'issue': 'RSI không đạt ngưỡng',
            'count': issue_counts['RSI'],
            'percentage': issue_percentages['RSI'],
            'suggestion': [
                'Tăng ngưỡng RSI cho BUY (từ > 50 lên > 55)',
                'Giảm ngưỡng RSI cho SELL (từ < 50 xuống < 45)',
                'Thêm RSI divergence check để tránh overbought/oversold'
            ]
        })
    
    if issue_counts.get('Solid_Candle', 0) > total_losses * 0.2:
        improvements.append({
            'priority': 'MEDIUM',
            'issue': 'Doji Candle (Indecision)',
            'count': issue_counts['Solid_Candle'],
            'percentage': issue_percentages['Solid_Candle'],
            'suggestion': [
                'Tăng threshold cho Doji detection (từ 0.2 lên 0.3)',
                'Thêm filter để bỏ qua nến có body quá nhỏ',
                'Chờ nến confirmation sau Doji'
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
                'Tăng SL buffer từ M5 High/Low (từ 20 points lên 1.5x ATR)',
                'Thêm filter CHOP/RANGE để tránh trade trong market sideways',
                'Thêm Liquidity Sweep check để tránh false breakout',
                'Kiểm tra Displacement Candle trước khi vào lệnh'
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
                'Thêm filter External BOS (Break of Structure) - chỉ trade khi break major swing',
                'Thêm Liquidity Filter - kiểm tra khoảng cách đến opposing liquidity',
                'Thêm Multi-Timeframe Context (H1 bias)',
                'Cải thiện SL logic - dùng structure level thay vì M5 High/Low',
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
            'Thêm volume confirmation (volume > 1.3x average)',
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
    print(f"🔍 PHÂN TÍCH LỆNH THUA: {STRATEGY_NAME}")
    print(f"{'='*100}")
    print(f"📊 Tổng số lệnh thua trong database: {total_losing}")
    print(f"{'='*100}\n")
    
    while True:
        try:
            num_orders_input = input(f"📝 Nhập số lệnh thua muốn phân tích (1-{total_losing}, Enter để phân tích tất cả): ").strip()
            
            if num_orders_input == "":
                # Analyze all orders
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
    config_path = os.path.join(script_dir, "configs", "config_1.json")
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
        
        # Auto-continue if analyzing multiple orders (no pause needed)
        # Only pause if user wants to see details for each order
        if len(losing_orders) > 1 and idx < len(losing_orders):
            # Optional: Add a small delay for readability
            time.sleep(0.5)  # 0.5 second pause between orders
    
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

