----update ngày 10/02/2026------------------
HA V2:Tăng SL lên > 10 pips; Chỉ đánh khi ADX > 30.
Strategy 5:Giới hạn SL tối đa 25 pips; Tuyệt đối không Buy khi RSI > 70.
HA V2 (strategy_1_trend_ha_v2.py)
SL minimum increased to > 10 pips: changed from 100 points (10 pips) to 110 points (11 pips) for both BUY and SELL signals.
ADX filter: only trade when ADX > 30 (changed from >= 28). Default threshold updated to 30, and condition changed from >= to >.
Strategy 5 (strategy_5_filter_first.py)
Maximum SL limit of 25 pips: added to all SL calculation modes (ATR-based, auto_m5, and Fixed). If calculated SL exceeds 25 pips, it is capped at 25 pips.
Hard stop for Buy when RSI > 70: added a check that blocks all Buy signals when RSI > 70, regardless of other conditions.