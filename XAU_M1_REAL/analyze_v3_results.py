import pandas as pd
import json
import sys
from datetime import datetime
from collections import defaultdict

# Fix encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def analyze_v3_results(csv_path):
    """
    Phân tích kết quả Strategy 1 Trend HA V3 sau 1 tuần
    """
    # Read CSV
    df = pd.read_csv(csv_path)
    
    # Remove duplicates - keep only unique tickets (first occurrence)
    df_unique = df.drop_duplicates(subset=['Ticket'], keep='first')
    
    print("=" * 100)
    print("📊 BÁO CÁO PHÂN TÍCH KẾT QUẢ STRATEGY 1 TREND HA V3 (1 TUẦN)")
    print("=" * 100)
    print(f"📅 Ngày phân tích: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 File: {csv_path}")
    print()
    
    # Basic Stats
    total_trades = len(df_unique)
    wins = df_unique[df_unique['Win/Loss'] == 'Win']
    losses = df_unique[df_unique['Win/Loss'] == 'Loss']
    
    num_wins = len(wins)
    num_losses = len(losses)
    win_rate = (num_wins / total_trades * 100) if total_trades > 0 else 0
    
    total_profit = df_unique['Profit ($)'].sum()
    gross_profit = wins['Profit ($)'].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses['Profit ($)'].sum()) if len(losses) > 0 else 0
    
    avg_win = gross_profit / num_wins if num_wins > 0 else 0
    avg_loss = gross_loss / num_losses if num_losses > 0 else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0
    
    print("## 1. TỔNG QUAN")
    print("-" * 100)
    print(f"Tổng số lệnh: {total_trades}")
    print(f"Lệnh thắng: {num_wins} ({win_rate:.1f}%)")
    print(f"Lệnh thua: {num_losses} ({100-win_rate:.1f}%)")
    print(f"Tổng lợi nhuận: ${total_profit:.2f}")
    print(f"Lợi nhuận trung bình/lệnh: ${total_profit/total_trades:.2f}")
    print()
    
    print("## 2. PHÂN TÍCH LỢI NHUẬN")
    print("-" * 100)
    print(f"Tổng lợi nhuận từ lệnh thắng: ${gross_profit:.2f}")
    print(f"Tổng lỗ từ lệnh thua: ${-gross_loss:.2f}")
    print(f"Lợi nhuận trung bình/lệnh thắng: ${avg_win:.2f}")
    print(f"Lỗ trung bình/lệnh thua: ${avg_loss:.2f}")
    print(f"Profit Factor: {profit_factor:.2f}")
    print()
    
    # R:R Analysis
    print("## 3. PHÂN TÍCH RISK/REWARD RATIO")
    print("-" * 100)
    rr_15 = df_unique[df_unique['Risk/Reward Ratio'] == 1.5]
    rr_18 = df_unique[df_unique['Risk/Reward Ratio'] == 1.8]
    
    print(f"Lệnh với R:R = 1.5: {len(rr_15)} lệnh")
    if len(rr_15) > 0:
        rr_15_wins = len(rr_15[rr_15['Win/Loss'] == 'Win'])
        rr_15_win_rate = (rr_15_wins / len(rr_15) * 100) if len(rr_15) > 0 else 0
        rr_15_profit = rr_15['Profit ($)'].sum()
        print(f"  - Win Rate: {rr_15_win_rate:.1f}%")
        print(f"  - Tổng Profit: ${rr_15_profit:.2f}")
    
    print(f"Lệnh với R:R = 1.8: {len(rr_18)} lệnh")
    if len(rr_18) > 0:
        rr_18_wins = len(rr_18[rr_18['Win/Loss'] == 'Win'])
        rr_18_win_rate = (rr_18_wins / len(rr_18) * 100) if len(rr_18) > 0 else 0
        rr_18_profit = rr_18['Profit ($)'].sum()
        print(f"  - Win Rate: {rr_18_win_rate:.1f}%")
        print(f"  - Tổng Profit: ${rr_18_profit:.2f}")
    print()
    
    # Order Type Analysis
    print("## 4. PHÂN TÍCH THEO LOẠI LỆNH")
    print("-" * 100)
    buy_trades = df_unique[df_unique['Order Type'] == 'BUY']
    sell_trades = df_unique[df_unique['Order Type'] == 'SELL']
    
    print(f"Lệnh BUY: {len(buy_trades)} lệnh")
    if len(buy_trades) > 0:
        buy_wins = len(buy_trades[buy_trades['Win/Loss'] == 'Win'])
        buy_win_rate = (buy_wins / len(buy_trades) * 100) if len(buy_trades) > 0 else 0
        buy_profit = buy_trades['Profit ($)'].sum()
        print(f"  - Win Rate: {buy_win_rate:.1f}%")
        print(f"  - Tổng Profit: ${buy_profit:.2f}")
    
    print(f"Lệnh SELL: {len(sell_trades)} lệnh")
    if len(sell_trades) > 0:
        sell_wins = len(sell_trades[sell_trades['Win/Loss'] == 'Win'])
        sell_win_rate = (sell_wins / len(sell_trades) * 100) if len(sell_trades) > 0 else 0
        sell_profit = sell_trades['Profit ($)'].sum()
        print(f"  - Win Rate: {sell_win_rate:.1f}%")
        print(f"  - Tổng Profit: ${sell_profit:.2f}")
    print()
    
    # Indicators Analysis
    print("## 5. PHÂN TÍCH INDICATORS")
    print("-" * 100)
    
    # Parse indicators
    rsi_values = []
    adx_values = []
    atr_values = []
    
    for idx, row in df_unique.iterrows():
        try:
            indicators_str = row['Signal Indicators']
            if pd.notna(indicators_str) and indicators_str:
                indicators = json.loads(indicators_str.replace("'", '"'))
                if 'rsi' in indicators:
                    rsi_values.append({'value': indicators['rsi'], 'profit': row['Profit ($)'], 'win': row['Win/Loss'] == 'Win'})
                if 'adx' in indicators:
                    adx_values.append({'value': indicators['adx'], 'profit': row['Profit ($)'], 'win': row['Win/Loss'] == 'Win'})
                if 'atr' in indicators:
                    atr_values.append({'value': indicators['atr'], 'profit': row['Profit ($)'], 'win': row['Win/Loss'] == 'Win'})
        except:
            continue
    
    if rsi_values:
        rsi_df = pd.DataFrame(rsi_values)
        print(f"RSI Analysis ({len(rsi_df)} lệnh có data):")
        print(f"  - RSI trung bình: {rsi_df['value'].mean():.1f}")
        print(f"  - RSI min: {rsi_df['value'].min():.1f}")
        print(f"  - RSI max: {rsi_df['value'].max():.1f}")
        
        # RSI > 50 vs <= 50
        rsi_high = rsi_df[rsi_df['value'] > 50]
        rsi_low = rsi_df[rsi_df['value'] <= 50]
        
        if len(rsi_high) > 0:
            rsi_high_wins = len(rsi_high[rsi_high['win'] == True])
            rsi_high_win_rate = (rsi_high_wins / len(rsi_high) * 100)
            print(f"  - RSI > 50: {len(rsi_high)} lệnh, Win Rate: {rsi_high_win_rate:.1f}%")
        
        if len(rsi_low) > 0:
            rsi_low_wins = len(rsi_low[rsi_low['win'] == True])
            rsi_low_win_rate = (rsi_low_wins / len(rsi_low) * 100)
            print(f"  - RSI <= 50: {len(rsi_low)} lệnh, Win Rate: {rsi_low_win_rate:.1f}%")
    
    if adx_values:
        adx_df = pd.DataFrame(adx_values)
        print(f"\nADX Analysis ({len(adx_df)} lệnh có data):")
        print(f"  - ADX trung bình: {adx_df['value'].mean():.1f}")
        print(f"  - ADX min: {adx_df['value'].min():.1f}")
        print(f"  - ADX max: {adx_df['value'].max():.1f}")
        
        # ADX > 25 vs <= 25
        adx_high = adx_df[adx_df['value'] > 25]
        adx_low = adx_df[adx_df['value'] <= 25]
        
        if len(adx_high) > 0:
            adx_high_wins = len(adx_high[adx_high['win'] == True])
            adx_high_win_rate = (adx_high_wins / len(adx_high) * 100)
            print(f"  - ADX > 25: {len(adx_high)} lệnh, Win Rate: {adx_high_win_rate:.1f}%")
        
        if len(adx_low) > 0:
            adx_low_wins = len(adx_low[adx_low['win'] == True])
            adx_low_win_rate = (adx_low_wins / len(adx_low) * 100)
            print(f"  - ADX <= 25: {len(adx_low)} lệnh, Win Rate: {adx_low_win_rate:.1f}%")
    
    if atr_values:
        atr_df = pd.DataFrame(atr_values)
        print(f"\nATR Analysis ({len(atr_df)} lệnh có data):")
        print(f"  - ATR trung bình: {atr_df['value'].mean():.2f}")
        print(f"  - ATR min: {atr_df['value'].min():.2f}")
        print(f"  - ATR max: {atr_df['value'].max():.2f}")
        
        # ATR < 2.0, 2.0-3.0, > 3.0
        atr_low = atr_df[atr_df['value'] < 2.0]
        atr_med = atr_df[(atr_df['value'] >= 2.0) & (atr_df['value'] <= 3.0)]
        atr_high = atr_df[atr_df['value'] > 3.0]
        
        if len(atr_low) > 0:
            atr_low_wins = len(atr_low[atr_low['win'] == True])
            atr_low_win_rate = (atr_low_wins / len(atr_low) * 100)
            print(f"  - ATR < 2.0 (Lý tưởng): {len(atr_low)} lệnh, Win Rate: {atr_low_win_rate:.1f}%")
        
        if len(atr_med) > 0:
            atr_med_wins = len(atr_med[atr_med['win'] == True])
            atr_med_win_rate = (atr_med_wins / len(atr_med) * 100)
            print(f"  - ATR 2.0-3.0 (Cẩn trọng): {len(atr_med)} lệnh, Win Rate: {atr_med_win_rate:.1f}%")
        
        if len(atr_high) > 0:
            atr_high_wins = len(atr_high[atr_high['win'] == True])
            atr_high_win_rate = (atr_high_wins / len(atr_high) * 100)
            print(f"  - ATR > 3.0 (Quá cao - nên bỏ): {len(atr_high)} lệnh, Win Rate: {atr_high_win_rate:.1f}%")
    
    print()
    
    # Loss Analysis
    print("## 6. PHÂN TÍCH LỆNH THUA")
    print("-" * 100)
    if len(losses) > 0:
        print(f"Tổng số lệnh thua: {len(losses)}")
        print(f"Lỗ lớn nhất: ${losses['Profit ($)'].min():.2f}")
        print(f"Lỗ nhỏ nhất: ${losses['Profit ($)'].max():.2f}")
        print(f"Lỗ trung bình: ${avg_loss:.2f}")
        
        # Analyze loss reasons
        print("\nTop 5 lệnh thua lớn nhất:")
        top_losses = losses.nsmallest(5, 'Profit ($)')
        for idx, loss in top_losses.iterrows():
            try:
                indicators_str = loss['Signal Indicators']
                if pd.notna(indicators_str) and indicators_str:
                    indicators = json.loads(indicators_str.replace("'", '"'))
                    rsi_val = f"{indicators.get('rsi', 'N/A'):.1f}" if 'rsi' in indicators else 'N/A'
                    adx_val = f"{indicators.get('adx', 'N/A'):.1f}" if 'adx' in indicators else 'N/A'
                else:
                    rsi_val = 'N/A'
                    adx_val = 'N/A'
                print(f"  - Ticket {loss['Ticket']}: ${loss['Profit ($)']:.2f} | {loss['Order Type']} | RSI: {rsi_val} | ADX: {adx_val}")
            except:
                print(f"  - Ticket {loss['Ticket']}: ${loss['Profit ($)']:.2f} | {loss['Order Type']}")
    print()
    
    # Win Analysis
    print("## 7. PHÂN TÍCH LỆNH THẮNG")
    print("-" * 100)
    if len(wins) > 0:
        print(f"Tổng số lệnh thắng: {len(wins)}")
        print(f"Lợi nhuận lớn nhất: ${wins['Profit ($)'].max():.2f}")
        print(f"Lợi nhuận nhỏ nhất: ${wins['Profit ($)'].min():.2f}")
        print(f"Lợi nhuận trung bình: ${avg_win:.2f}")
        
        # Analyze win reasons
        print("\nTop 5 lệnh thắng lớn nhất:")
        top_wins = wins.nlargest(5, 'Profit ($)')
        for idx, win in top_wins.iterrows():
            try:
                indicators_str = win['Signal Indicators']
                if pd.notna(indicators_str) and indicators_str:
                    indicators = json.loads(indicators_str.replace("'", '"'))
                    rsi_val = f"{indicators.get('rsi', 'N/A'):.1f}" if 'rsi' in indicators else 'N/A'
                    adx_val = f"{indicators.get('adx', 'N/A'):.1f}" if 'adx' in indicators else 'N/A'
                else:
                    rsi_val = 'N/A'
                    adx_val = 'N/A'
                print(f"  - Ticket {win['Ticket']}: ${win['Profit ($)']:.2f} | {win['Order Type']} | RSI: {rsi_val} | ADX: {adx_val}")
            except:
                print(f"  - Ticket {win['Ticket']}: ${win['Profit ($)']:.2f} | {win['Order Type']}")
    print()
    
    # V3 Improvements Assessment
    print("## 8. ĐÁNH GIÁ CÁC CẢI THIỆN V3")
    print("-" * 100)
    
    improvements = []
    
    # 1. RSI > 50 filter
    if rsi_values:
        rsi_df = pd.DataFrame(rsi_values)
        rsi_above_50 = rsi_df[rsi_df['value'] > 50]
        if len(rsi_above_50) > 0:
            rsi_50_win_rate = (len(rsi_above_50[rsi_above_50['win'] == True]) / len(rsi_above_50) * 100)
            improvements.append({
                'name': 'RSI > 50 Filter',
                'status': '✅ Đang hoạt động' if rsi_50_win_rate >= 50 else '⚠️ Cần review',
                'win_rate': rsi_50_win_rate,
                'trades': len(rsi_above_50)
            })
    
    # 2. ADX > 25 filter
    if adx_values:
        adx_df = pd.DataFrame(adx_values)
        adx_above_25 = adx_df[adx_df['value'] > 25]
        if len(adx_above_25) > 0:
            adx_25_win_rate = (len(adx_above_25[adx_above_25['win'] == True]) / len(adx_above_25) * 100)
            improvements.append({
                'name': 'ADX > 25 Filter',
                'status': '✅ Đang hoạt động' if adx_25_win_rate >= 50 else '⚠️ Cần review',
                'win_rate': adx_25_win_rate,
                'trades': len(adx_above_25)
            })
    
    # 3. Dynamic R:R
    if len(rr_18) > 0:
        rr_18_win_rate = (len(rr_18[rr_18['Win/Loss'] == 'Win']) / len(rr_18) * 100) if len(rr_18) > 0 else 0
        improvements.append({
            'name': 'Dynamic R:R (1.8 cho RSI > 60)',
            'status': '✅ Đang hoạt động' if rr_18_win_rate >= 40 else '⚠️ Cần review',
            'win_rate': rr_18_win_rate,
            'trades': len(rr_18)
        })
    
    # 4. ATR Filter
    if atr_values:
        atr_df = pd.DataFrame(atr_values)
        atr_high_trades = atr_df[atr_df['value'] > 3.0]
        if len(atr_high_trades) > 0:
            atr_high_win_rate = (len(atr_high_trades[atr_high_trades['win'] == True]) / len(atr_high_trades) * 100)
            improvements.append({
                'name': 'ATR > 3.0 Filter (nên bỏ trade)',
                'status': '⚠️ Vẫn có lệnh với ATR > 3.0' if len(atr_high_trades) > 0 else '✅ Không có lệnh ATR > 3.0',
                'win_rate': atr_high_win_rate,
                'trades': len(atr_high_trades)
            })
    
    for imp in improvements:
        print(f"  {imp['status']} - {imp['name']}: {imp['trades']} lệnh, Win Rate: {imp['win_rate']:.1f}%")
    
    print()
    
    # Summary
    print("## 9. KẾT LUẬN")
    print("-" * 100)
    print(f"✅ Win Rate: {win_rate:.1f}% - {'Tốt' if win_rate >= 50 else 'Cần cải thiện'}")
    print(f"✅ Profit Factor: {profit_factor:.2f} - {'Tốt' if profit_factor >= 1.5 else 'Cần cải thiện'}")
    print(f"✅ Tổng Profit: ${total_profit:.2f} - {'Lợi nhuận' if total_profit > 0 else 'Lỗ'}")
    
    if win_rate >= 50 and profit_factor >= 1.5 and total_profit > 0:
        print("\n🎉 Bot V3 đang hoạt động tốt!")
    elif win_rate < 50 or profit_factor < 1.5:
        print("\n⚠️ Bot V3 cần điều chỉnh thêm:")
        if win_rate < 50:
            print("   - Win Rate thấp, cần siết chặt filters hơn")
        if profit_factor < 1.5:
            print("   - Profit Factor thấp, cần cải thiện R:R hoặc giảm avg loss")
    
    print()
    print("=" * 100)

if __name__ == "__main__":
    import sys
    csv_path = r"c:\Users\ADMIN\Downloads\orders_export_Strategy_1_Trend_HA_V3_20260202_165353.csv"
    
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    
    analyze_v3_results(csv_path)
