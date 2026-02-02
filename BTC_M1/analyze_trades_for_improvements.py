import pandas as pd
import json
import numpy as np
from collections import defaultdict

# Đọc file CSV
csv_file = r'c:\Users\ADMIN\Downloads\orders_export_20260202_140346.csv'
df = pd.read_csv(csv_file)

# Lọc chỉ các lệnh đã đóng (có Profit)
df_closed = df[df['Status'].isin(['Win', 'Loss'])].copy()

import sys
sys.stdout.reconfigure(encoding='utf-8')

print(f"Tong so lenh: {len(df)}")
print(f"Lenh da dong: {len(df_closed)}")
print(f"Lenh dang chay: {len(df[df['Status'] == 'Open'])}")
print("\n" + "="*80 + "\n")

# Phân tích theo từng Strategy
strategies = df_closed['Strategy'].unique()
improvements = {}

for strategy in sorted(strategies):
    strat_df = df_closed[df_closed['Strategy'] == strategy].copy()
    
    total = len(strat_df)
    wins = len(strat_df[strat_df['Win/Loss'] == 'Win'])
    losses = len(strat_df[strat_df['Win/Loss'] == 'Loss'])
    win_rate = (wins / total * 100) if total > 0 else 0
    
    total_profit = strat_df['Profit ($)'].sum()
    avg_win = strat_df[strat_df['Win/Loss'] == 'Win']['Profit ($)'].mean() if wins > 0 else 0
    avg_loss = abs(strat_df[strat_df['Win/Loss'] == 'Loss']['Profit ($)'].mean()) if losses > 0 else 0
    profit_factor = (avg_win / avg_loss) if avg_loss > 0 else 0
    
    # Phân tích RSI cho Win/Loss
    rsi_wins = []
    rsi_losses = []
    adx_wins = []
    adx_losses = []
    volume_ratio_wins = []
    volume_ratio_losses = []
    
    # Phân tích theo Order Type
    buy_wins = len(strat_df[(strat_df['Order Type'] == 'BUY') & (strat_df['Win/Loss'] == 'Win')])
    buy_losses = len(strat_df[(strat_df['Order Type'] == 'BUY') & (strat_df['Win/Loss'] == 'Loss')])
    sell_wins = len(strat_df[(strat_df['Order Type'] == 'SELL') & (strat_df['Win/Loss'] == 'Win')])
    sell_losses = len(strat_df[(strat_df['Order Type'] == 'SELL') & (strat_df['Win/Loss'] == 'Loss')])
    
    # Phân tích indicators từ Signal Indicators
    for idx, row in strat_df.iterrows():
        try:
            indicators_str = row['Signal Indicators']
            if pd.notna(indicators_str) and indicators_str:
                if isinstance(indicators_str, str):
                    indicators = json.loads(indicators_str)
                else:
                    indicators = indicators_str
                
                # RSI
                rsi = indicators.get('rsi') or indicators.get('RSI')
                if rsi:
                    if row['Win/Loss'] == 'Win':
                        rsi_wins.append(rsi)
                    else:
                        rsi_losses.append(rsi)
                
                # ADX
                adx = indicators.get('adx') or indicators.get('ADX') or indicators.get('m1_adx') or indicators.get('m5_adx') or indicators.get('h1_adx')
                if adx:
                    if row['Win/Loss'] == 'Win':
                        adx_wins.append(adx)
                    else:
                        adx_losses.append(adx)
                
                # Volume Ratio
                vol_ratio = indicators.get('volume_ratio') or indicators.get('vol_ratio')
                if vol_ratio:
                    if row['Win/Loss'] == 'Win':
                        volume_ratio_wins.append(vol_ratio)
                    else:
                        volume_ratio_losses.append(vol_ratio)
        except:
            pass
    
    # Tính toán thống kê
    avg_rsi_win = np.mean(rsi_wins) if rsi_wins else None
    avg_rsi_loss = np.mean(rsi_losses) if rsi_losses else None
    avg_adx_win = np.mean(adx_wins) if adx_wins else None
    avg_adx_loss = np.mean(adx_losses) if adx_losses else None
    avg_vol_win = np.mean(volume_ratio_wins) if volume_ratio_wins else None
    avg_vol_loss = np.mean(volume_ratio_losses) if volume_ratio_losses else None
    
    # Phân tích SL/TP
    sl_hits = len(strat_df[strat_df['Close Price'] == strat_df['Stop Loss']]) if 'Stop Loss' in strat_df.columns else 0
    tp_hits = len(strat_df[strat_df['Close Price'] == strat_df['Take Profit']]) if 'Take Profit' in strat_df.columns else 0
    
    improvements[strategy] = {
        'total': total,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'total_profit': total_profit,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'buy_win_rate': (buy_wins / (buy_wins + buy_losses) * 100) if (buy_wins + buy_losses) > 0 else 0,
        'sell_win_rate': (sell_wins / (sell_wins + sell_losses) * 100) if (sell_wins + sell_losses) > 0 else 0,
        'avg_rsi_win': avg_rsi_win,
        'avg_rsi_loss': avg_rsi_loss,
        'avg_adx_win': avg_adx_win,
        'avg_adx_loss': avg_adx_loss,
        'avg_vol_win': avg_vol_win,
        'avg_vol_loss': avg_vol_loss,
        'rsi_wins': rsi_wins,
        'rsi_losses': rsi_losses,
    }
    
    print(f"Bot: {strategy}")
    print(f"   Tong lenh: {total} | Win: {wins} ({win_rate:.1f}%) | Loss: {losses}")
    print(f"   Total Profit: ${total_profit:.2f} | Avg Win: ${avg_win:.2f} | Avg Loss: ${avg_loss:.2f} | PF: {profit_factor:.2f}")
    if avg_rsi_win:
        print(f"   RSI - Win: {avg_rsi_win:.1f} | Loss: {avg_rsi_loss:.1f}")
    if avg_adx_win:
        print(f"   ADX - Win: {avg_adx_win:.1f} | Loss: {avg_adx_loss:.1f}")
    if avg_vol_win:
        print(f"   Volume Ratio - Win: {avg_vol_win:.2f}x | Loss: {avg_vol_loss:.2f}x")
    print(f"   BUY Win Rate: {improvements[strategy]['buy_win_rate']:.1f}% | SELL Win Rate: {improvements[strategy]['sell_win_rate']:.1f}%")
    print()

# Tạo file đề xuất nâng cấp
output = []
output.append("# 🚀 ĐỀ XUẤT NÂNG CẤP CÁC BOT BTC_M1\n")
output.append(f"*Dựa trên phân tích {len(df_closed)} lệnh đã đóng*\n")
output.append("="*80 + "\n")

# Đề xuất cho từng bot
for strategy, stats in improvements.items():
    output.append(f"## 🤖 {strategy}\n")
    output.append(f"**Hiện tại:** Win Rate: {stats['win_rate']:.1f}% | Profit Factor: {stats['profit_factor']:.2f}\n\n")
    
    recommendations = []
    
    # 1. Phân tích RSI
    if stats['avg_rsi_win'] and stats['avg_rsi_loss']:
        if strategy == 'Strategy_1_Trend_HA':
            current_buy_threshold = 55
            current_sell_threshold = 45
        elif strategy in ['Strategy_2_EMA_ATR', 'Strategy_4_UT_Bot', 'Strategy_5_Filter_First']:
            current_buy_threshold = 55
            current_sell_threshold = 45
        else:
            current_buy_threshold = 50
            current_sell_threshold = 50
        
        # Phân tích RSI cho BUY
        if stats['rsi_wins'] and stats['rsi_losses']:
            buy_wins_rsi = [r for r in stats['rsi_wins'] if r > 50]
            buy_losses_rsi = [r for r in stats['rsi_losses'] if r > 50]
            
            if buy_wins_rsi and buy_losses_rsi and len(buy_wins_rsi) >= 5:
                # Tìm RSI threshold tối ưu: RSI trung bình của wins nhưng không quá cao
                avg_buy_win_rsi = np.mean(buy_wins_rsi)
                avg_buy_loss_rsi = np.mean(buy_losses_rsi) if buy_losses_rsi else current_buy_threshold
                
                # Nếu RSI của wins cao hơn losses đáng kể, tăng threshold
                if avg_buy_win_rsi > avg_buy_loss_rsi + 3:
                    optimal_buy_rsi = min(70, max(current_buy_threshold + 2, int(avg_buy_loss_rsi + 5)))
                    if optimal_buy_rsi > current_buy_threshold:
                        recommendations.append(f"**RSI BUY Threshold:** Tăng từ {current_buy_threshold} lên {optimal_buy_rsi} (RSI wins = {avg_buy_win_rsi:.1f}, losses = {avg_buy_loss_rsi:.1f})")
                elif avg_buy_win_rsi < avg_buy_loss_rsi - 3:
                    # Nếu RSI của wins thấp hơn losses, có thể giảm threshold
                    optimal_buy_rsi = max(50, min(current_buy_threshold - 2, int(avg_buy_win_rsi + 2)))
                    if optimal_buy_rsi < current_buy_threshold:
                        recommendations.append(f"**RSI BUY Threshold:** Giảm từ {current_buy_threshold} xuống {optimal_buy_rsi} (RSI wins = {avg_buy_win_rsi:.1f}, losses = {avg_buy_loss_rsi:.1f})")
            
            # Phân tích RSI cho SELL
            sell_wins_rsi = [r for r in stats['rsi_wins'] if r < 50]
            sell_losses_rsi = [r for r in stats['rsi_losses'] if r < 50]
            
            if sell_wins_rsi and sell_losses_rsi and len(sell_wins_rsi) >= 5:
                avg_sell_win_rsi = np.mean(sell_wins_rsi)
                avg_sell_loss_rsi = np.mean(sell_losses_rsi) if sell_losses_rsi else current_sell_threshold
                
                # Nếu RSI của wins thấp hơn losses đáng kể, giảm threshold
                if avg_sell_win_rsi < avg_sell_loss_rsi - 3:
                    optimal_sell_rsi = max(30, min(current_sell_threshold - 2, int(avg_sell_loss_rsi - 5)))
                    if optimal_sell_rsi < current_sell_threshold:
                        recommendations.append(f"**RSI SELL Threshold:** Giảm từ {current_sell_threshold} xuống {optimal_sell_rsi} (RSI wins = {avg_sell_win_rsi:.1f}, losses = {avg_sell_loss_rsi:.1f})")
                elif avg_sell_win_rsi > avg_sell_loss_rsi + 3:
                    optimal_sell_rsi = min(50, max(current_sell_threshold + 2, int(avg_sell_win_rsi - 2)))
                    if optimal_sell_rsi > current_sell_threshold:
                        recommendations.append(f"**RSI SELL Threshold:** Tăng từ {current_sell_threshold} lên {optimal_sell_rsi} (RSI wins = {avg_sell_win_rsi:.1f}, losses = {avg_sell_loss_rsi:.1f})")
    
    # 2. Phân tích ADX
    if stats['avg_adx_win'] and stats['avg_adx_loss']:
        if stats['avg_adx_win'] > stats['avg_adx_loss']:
            optimal_adx = max(20, int(stats['avg_adx_loss'] + 5))  # ADX của losses + 5
            recommendations.append(f"**ADX Threshold:** Tăng lên {optimal_adx} (ADX trung bình: Wins = {stats['avg_adx_win']:.1f}, Losses = {stats['avg_adx_loss']:.1f})")
    
    # 3. Phân tích Volume
    if stats['avg_vol_win'] and stats['avg_vol_loss']:
        if stats['avg_vol_win'] > stats['avg_vol_loss']:
            optimal_vol = max(1.3, stats['avg_vol_loss'] + 0.2)  # Volume của losses + 0.2
            recommendations.append(f"**Volume Threshold:** Tăng lên {optimal_vol:.2f}x (Volume ratio trung bình: Wins = {stats['avg_vol_win']:.2f}x, Losses = {stats['avg_vol_loss']:.2f}x)")
    
    # 4. Phân tích BUY vs SELL
    if abs(stats['buy_win_rate'] - stats['sell_win_rate']) > 10:
        if stats['buy_win_rate'] > stats['sell_win_rate']:
            recommendations.append(f"**BUY Performance tốt hơn:** BUY Win Rate = {stats['buy_win_rate']:.1f}% vs SELL = {stats['sell_win_rate']:.1f}% - Cân nhắc tăng filter cho SELL hoặc giảm filter cho BUY")
        else:
            recommendations.append(f"**SELL Performance tốt hơn:** SELL Win Rate = {stats['sell_win_rate']:.1f}% vs BUY = {stats['buy_win_rate']:.1f}% - Cân nhắc tăng filter cho BUY hoặc giảm filter cho SELL")
    
    # 5. Phân tích Profit Factor
    if stats['profit_factor'] < 1.0:
        recommendations.append(f"**Profit Factor thấp ({stats['profit_factor']:.2f}):** Cần cải thiện R:R ratio hoặc tăng win rate. Đề xuất:")
        recommendations.append(f"  - Tăng TP multiplier (hiện tại R:R = 1.5, thử 2.0)")
        recommendations.append(f"  - Hoặc giảm SL size để giảm avg loss")
    
    # 6. Phân tích Win Rate thấp
    if stats['win_rate'] < 30:
        recommendations.append(f"**⚠️ CẢNH BÁO: Win Rate rất thấp ({stats['win_rate']:.1f}%)**")
        recommendations.append(f"  - Mặc dù Profit Factor tốt ({stats['profit_factor']:.2f}), win rate thấp có thể do:")
        recommendations.append("    + Quá nhiều filter dẫn đến bỏ lỡ cơ hội tốt")
        recommendations.append("    + Hoặc filter chưa đủ chính xác, vào lệnh quá sớm")
        recommendations.append("  - Đề xuất: Cân bằng giữa số lượng filter và chất lượng signal")
    
    # 7. Đề xuất cụ thể theo từng bot
    if strategy == 'Strategy_1_Trend_HA':
        if stats['win_rate'] < 30:
            recommendations.append("**Tăng filter nghiêm ngặt hơn:**")
            recommendations.append("  - Tăng M5 ADX threshold từ 20 lên 25-30 (ADX losses = {:.1f})".format(stats['avg_adx_loss']))
            recommendations.append("  - Tăng volume threshold từ 1.3x lên 1.5x (Volume losses = {:.2f}x)".format(stats['avg_vol_loss']))
            recommendations.append("  - Đảm bảo H1 trend khớp với M5 trend (đã có nhưng cần kiểm tra)")
            recommendations.append("  - Tăng RSI threshold: BUY > 60, SELL < 40 (RSI wins = {:.1f}, losses = {:.1f})".format(stats['avg_rsi_win'], stats['avg_rsi_loss']))
    
    elif strategy == 'Strategy_2_EMA_ATR':
        if stats['win_rate'] < 30:
            recommendations.append("**Cải thiện EMA Crossover:**")
            recommendations.append("  - Yêu cầu crossover confirmation (2 nến) - đã có nhưng cần kiểm tra")
            recommendations.append("  - Tăng H1 ADX threshold từ 20 lên 25-30 (ADX losses = {:.1f})".format(stats['avg_adx_loss']))
            recommendations.append("  - Thêm filter: Price không quá xa EMA14 (< 1.0x ATR thay vì 1.5x)")
            recommendations.append("  - Tăng volume threshold lên {:.2f}x (Volume losses = {:.2f}x)".format(stats['avg_vol_loss'] + 0.2, stats['avg_vol_loss']))
    
    elif strategy == 'Strategy_3_PA_Volume':
        if stats['win_rate'] < 50:
            recommendations.append("**Tăng chất lượng Pinbar:**")
            recommendations.append("  - Tăng volume threshold từ 1.5x lên 2.0x")
            recommendations.append("  - Yêu cầu pinbar shadow > 2.0x body (thay vì 1.5x)")
            recommendations.append("  - Tăng RSI threshold: BUY > 55, SELL < 45")
    
    elif strategy == 'Strategy_4_UT_Bot':
        if stats['win_rate'] < 30:
            recommendations.append("**Cải thiện UT Bot Signal:**")
            recommendations.append("  - Tăng M1 ADX threshold từ 25 lên 30-35 (ADX losses = {:.1f})".format(stats['avg_adx_loss']))
            recommendations.append("  - Yêu cầu UT confirmation (2 nến) - đã có nhưng cần kiểm tra")
            recommendations.append("  - Tăng volume threshold từ 1.3x lên {:.2f}x (Volume losses = {:.2f}x)".format(stats['avg_vol_loss'] + 0.2, stats['avg_vol_loss']))
            if stats['buy_win_rate'] < stats['sell_win_rate'] - 10:
                recommendations.append("  - ⚠️ BUY performance kém ({:.1f}% vs SELL {:.1f}%) - Tăng filter cho BUY hoặc tắt BUY signals".format(stats['buy_win_rate'], stats['sell_win_rate']))
    
    elif strategy == 'Strategy_5_Filter_First':
        if stats['win_rate'] < 35:
            recommendations.append("**Giảm False Breakout:**")
            recommendations.append("  - Tăng buffer multiplier từ 100 lên 150-200 points")
            recommendations.append("  - Yêu cầu breakout confirmation (2 nến) - đã có nhưng cần kiểm tra")
            recommendations.append("  - Tăng M1 ADX threshold từ 25 lên 30-35 (ADX losses = {:.1f})".format(stats['avg_adx_loss']))
            recommendations.append("  - Tăng volume threshold từ 1.5x lên {:.2f}x (Volume losses = {:.2f}x)".format(stats['avg_vol_loss'] + 0.3, stats['avg_vol_loss']))
            if stats['buy_win_rate'] < stats['sell_win_rate'] - 10:
                recommendations.append("  - ⚠️ BUY performance kém ({:.1f}% vs SELL {:.1f}%) - Tăng filter cho BUY".format(stats['buy_win_rate'], stats['sell_win_rate']))
            recommendations.append("  - Tăng RSI threshold: BUY > 60, SELL < 40 (RSI wins = {:.1f}, losses = {:.1f})".format(stats['avg_rsi_win'], stats['avg_rsi_loss']))
    
    # Ghi đề xuất
    if recommendations:
        output.append("### ✅ Đề xuất nâng cấp:\n")
        for rec in recommendations:
            output.append(f"- {rec}\n")
    else:
        output.append("### ✅ Bot đang hoạt động tốt, không cần thay đổi lớn\n")
    
    output.append("\n" + "-"*80 + "\n\n")

# Ghi file
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
output_file = os.path.join(script_dir, "DE_XUAT_NANG_CAP_BOTS.md")
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(''.join(output))

print(f"\n✅ Đã tạo file đề xuất: {output_file}")
