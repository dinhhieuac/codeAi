import pandas as pd
import json
import sys
from datetime import datetime

# Fix encoding for Windows
if sys.platform == 'win32':
    import io

def analyze_atr_ranges(csv_path):
    """
    Phân tích tỉ lệ thắng thua theo ATR ranges:
    - ATR 4-15: Sẽ được trade
    - ATR > 15.0: Sẽ bị chặn
    """
    # Read CSV
    df = pd.read_csv(csv_path)
    
    # Remove duplicates - keep only unique tickets (first occurrence)
    df_unique = df.drop_duplicates(subset=['Ticket'], keep='first')
    
    print("=" * 100)
    print("📊 PHÂN TÍCH TỈ LỆ THẮNG THUA THEO ATR RANGES")
    print("=" * 100)
    print(f"📅 Ngày phân tích: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 File: {csv_path}")
    print()
    
    # Extract ATR from Signal Indicators
    atr_data = []
    for idx, row in df_unique.iterrows():
        try:
            indicators_str = row['Signal Indicators']
            if pd.notna(indicators_str):
                indicators = json.loads(indicators_str)
                atr_val = indicators.get('atr', None)
                if atr_val is not None:
                    atr_data.append({
                        'Ticket': row['Ticket'],
                        'ATR': atr_val,
                        'Win/Loss': row['Win/Loss'],
                        'Profit': row['Profit ($)'],
                        'Order Type': row['Order Type']
                    })
        except:
            continue
    
    if not atr_data:
        print("❌ Không tìm thấy dữ liệu ATR trong file!")
        return
    
    atr_df = pd.DataFrame(atr_data)
    
    # Phân loại theo ATR ranges
    atr_low = atr_df[(atr_df['ATR'] >= 4.0) & (atr_df['ATR'] < 15.0)]  # Sẽ được trade
    atr_high = atr_df[atr_df['ATR'] >= 15.0]  # Sẽ bị chặn
    
    print("## 📊 PHÂN TÍCH ATR RANGES")
    print("-" * 100)
    print()
    
    # ATR 4-15 (Sẽ được trade)
    if len(atr_low) > 0:
        atr_low_wins = atr_low[atr_low['Win/Loss'] == 'Win']
        atr_low_losses = atr_low[atr_low['Win/Loss'] == 'Loss']
        
        num_low_wins = len(atr_low_wins)
        num_low_losses = len(atr_low_losses)
        total_low = len(atr_low)
        win_rate_low = (num_low_wins / total_low * 100) if total_low > 0 else 0
        
        profit_low = atr_low['Profit'].sum()
        avg_win_low = atr_low_wins['Profit'].mean() if num_low_wins > 0 else 0
        avg_loss_low = abs(atr_low_losses['Profit'].mean()) if num_low_losses > 0 else 0
        gross_profit_low = atr_low_wins['Profit'].sum() if num_low_wins > 0 else 0
        gross_loss_low = abs(atr_low_losses['Profit'].sum()) if num_low_losses > 0 else 0
        profit_factor_low = (gross_profit_low / gross_loss_low) if gross_loss_low > 0 else 0
        
        print(f"### ✅ ATR 4.0 - 15.0 (SẼ ĐƯỢC TRADE)")
        print(f"-" * 100)
        print(f"📊 Tổng số lệnh: {total_low}")
        print(f"✅ Lệnh thắng: {num_low_wins} ({win_rate_low:.1f}%)")
        print(f"❌ Lệnh thua: {num_low_losses} ({100-win_rate_low:.1f}%)")
        print(f"💰 Tổng lợi nhuận: ${profit_low:.2f}")
        print(f"📈 Lợi nhuận trung bình/lệnh: ${profit_low/total_low:.2f}")
        print(f"📊 Avg Win: ${avg_win_low:.2f}")
        print(f"📊 Avg Loss: ${avg_loss_low:.2f}")
        print(f"📊 Profit Factor: {profit_factor_low:.2f}")
        print(f"📊 ATR trung bình: {atr_low['ATR'].mean():.2f}")
        print(f"📊 ATR min: {atr_low['ATR'].min():.2f}")
        print(f"📊 ATR max: {atr_low['ATR'].max():.2f}")
        print()
        
        # Breakdown by Order Type
        buy_low = atr_low[atr_low['Order Type'] == 'BUY']
        sell_low = atr_low[atr_low['Order Type'] == 'SELL']
        
        if len(buy_low) > 0:
            buy_low_wins = len(buy_low[buy_low['Win/Loss'] == 'Win'])
            buy_low_win_rate = (buy_low_wins / len(buy_low) * 100)
            buy_low_profit = buy_low['Profit'].sum()
            print(f"  📊 BUY: {len(buy_low)} lệnh, Win Rate: {buy_low_win_rate:.1f}%, Profit: ${buy_low_profit:.2f}")
        
        if len(sell_low) > 0:
            sell_low_wins = len(sell_low[sell_low['Win/Loss'] == 'Win'])
            sell_low_win_rate = (sell_low_wins / len(sell_low) * 100)
            sell_low_profit = sell_low['Profit'].sum()
            print(f"  📊 SELL: {len(sell_low)} lệnh, Win Rate: {sell_low_win_rate:.1f}%, Profit: ${sell_low_profit:.2f}")
        print()
    
    # ATR > 15.0 (Sẽ bị chặn)
    if len(atr_high) > 0:
        atr_high_wins = atr_high[atr_high['Win/Loss'] == 'Win']
        atr_high_losses = atr_high[atr_high['Win/Loss'] == 'Loss']
        
        num_high_wins = len(atr_high_wins)
        num_high_losses = len(atr_high_losses)
        total_high = len(atr_high)
        win_rate_high = (num_high_wins / total_high * 100) if total_high > 0 else 0
        
        profit_high = atr_high['Profit'].sum()
        avg_win_high = atr_high_wins['Profit'].mean() if num_high_wins > 0 else 0
        avg_loss_high = abs(atr_high_losses['Profit'].mean()) if num_high_losses > 0 else 0
        gross_profit_high = atr_high_wins['Profit'].sum() if num_high_wins > 0 else 0
        gross_loss_high = abs(atr_high_losses['Profit'].sum()) if num_high_losses > 0 else 0
        profit_factor_high = (gross_profit_high / gross_loss_high) if gross_loss_high > 0 else 0
        
        print(f"### ❌ ATR >= 15.0 (SẼ BỊ CHẶN)")
        print(f"-" * 100)
        print(f"📊 Tổng số lệnh: {total_high}")
        print(f"✅ Lệnh thắng: {num_high_wins} ({win_rate_high:.1f}%)")
        print(f"❌ Lệnh thua: {num_high_losses} ({100-win_rate_high:.1f}%)")
        print(f"💰 Tổng lợi nhuận: ${profit_high:.2f}")
        print(f"📈 Lợi nhuận trung bình/lệnh: ${profit_high/total_high:.2f}")
        print(f"📊 Avg Win: ${avg_win_high:.2f}")
        print(f"📊 Avg Loss: ${avg_loss_high:.2f}")
        print(f"📊 Profit Factor: {profit_factor_high:.2f}")
        print(f"📊 ATR trung bình: {atr_high['ATR'].mean():.2f}")
        print(f"📊 ATR min: {atr_high['ATR'].min():.2f}")
        print(f"📊 ATR max: {atr_high['ATR'].max():.2f}")
        print()
        
        # Breakdown by Order Type
        buy_high = atr_high[atr_high['Order Type'] == 'BUY']
        sell_high = atr_high[atr_high['Order Type'] == 'SELL']
        
        if len(buy_high) > 0:
            buy_high_wins = len(buy_high[buy_high['Win/Loss'] == 'Win'])
            buy_high_win_rate = (buy_high_wins / len(buy_high) * 100)
            buy_high_profit = buy_high['Profit'].sum()
            print(f"  📊 BUY: {len(buy_high)} lệnh, Win Rate: {buy_high_win_rate:.1f}%, Profit: ${buy_high_profit:.2f}")
        
        if len(sell_high) > 0:
            sell_high_wins = len(sell_high[sell_high['Win/Loss'] == 'Win'])
            sell_high_win_rate = (sell_high_wins / len(sell_high) * 100)
            sell_high_profit = sell_high['Profit'].sum()
            print(f"  📊 SELL: {len(sell_high)} lệnh, Win Rate: {sell_high_win_rate:.1f}%, Profit: ${sell_high_profit:.2f}")
        print()
    
    # So sánh
    print("## 📊 SO SÁNH")
    print("-" * 100)
    if len(atr_low) > 0 and len(atr_high) > 0:
        print(f"| Metric | ATR 4-15 (Được trade) | ATR >= 15 (Bị chặn) | Chênh lệch |")
        print(f"|--------|----------------------|---------------------|------------|")
        print(f"| Số lệnh | {len(atr_low)} | {len(atr_high)} | {len(atr_low) - len(atr_high)} |")
        print(f"| Win Rate | {win_rate_low:.1f}% | {win_rate_high:.1f}% | {win_rate_low - win_rate_high:.1f}% |")
        print(f"| Tổng Profit | ${profit_low:.2f} | ${profit_high:.2f} | ${profit_low - profit_high:.2f} |")
        print(f"| Profit Factor | {profit_factor_low:.2f} | {profit_factor_high:.2f} | {profit_factor_low - profit_factor_high:.2f} |")
        print(f"| Avg Win | ${avg_win_low:.2f} | ${avg_win_high:.2f} | ${avg_win_low - avg_win_high:.2f} |")
        print(f"| Avg Loss | ${avg_loss_low:.2f} | ${avg_loss_high:.2f} | ${avg_loss_low - avg_loss_high:.2f} |")
        print()
        
        # Kết luận
        print("## 💡 KẾT LUẬN")
        print("-" * 100)
        if win_rate_low > win_rate_high:
            print(f"✅ ATR 4-15 có Win Rate cao hơn ({win_rate_low:.1f}% vs {win_rate_high:.1f}%)")
        else:
            print(f"⚠️ ATR >= 15 có Win Rate cao hơn ({win_rate_high:.1f}% vs {win_rate_low:.1f}%)")
        
        if profit_low > profit_high:
            print(f"✅ ATR 4-15 có Profit tốt hơn (${profit_low:.2f} vs ${profit_high:.2f})")
        else:
            print(f"⚠️ ATR >= 15 có Profit tốt hơn (${profit_high:.2f} vs ${profit_low:.2f})")
        
        if profit_factor_low > profit_factor_high:
            print(f"✅ ATR 4-15 có Profit Factor tốt hơn ({profit_factor_low:.2f} vs {profit_factor_high:.2f})")
        else:
            print(f"⚠️ ATR >= 15 có Profit Factor tốt hơn ({profit_factor_high:.2f} vs {profit_factor_low:.2f})")
        
        print()
        print(f"🎯 **Quyết định:** Filter ATR < 15.0 sẽ {'✅ CẢI THIỆN' if (profit_low > profit_high and profit_factor_low > profit_factor_high) else '❌ KHÔNG CẢI THIỆN'} hiệu suất bot")
    
    print()
    print("=" * 100)

if __name__ == "__main__":
    # Fix encoding for Windows console
    if sys.platform == 'win32':
        import sys
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    csv_path = r"c:\Users\ADMIN\Downloads\orders_export_Strategy_1_Trend_HA_V3_20260202_165353.csv"
    analyze_atr_ranges(csv_path)
