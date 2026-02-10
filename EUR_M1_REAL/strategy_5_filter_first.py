import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd

# Import local modules
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message, calculate_rsi, calculate_adx
from datetime import datetime, timedelta

# Initialize Database
db = Database()

def strategy_5_logic(config, error_count=0):
    # This strategy requires separate logic for Opening and Managing
    # For Scalping M1: We look for a breakout of the last 15 candles high/low
    
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    # 2. Check Global Max Positions & Manage Existing
    positions = mt5.positions_get(symbol=symbol, magic=magic)
    if positions:
        for pos in positions:
            manage_position(pos.ticket, symbol, magic, config)
            
        if len(positions) >= max_positions:
            return error_count, 0

    # --- ENTRY MODE ---
    
    # 1. Get Data
    df = get_data(symbol, mt5.TIMEFRAME_M1, 100)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 200) # For Trend Filter
    
    if df is None or df_m5 is None: return error_count, 0

    # Trend Filter (M5 EMA 200 + ADX)
    df_m5['ema200'] = df_m5['close'].ewm(span=200, adjust=False).mean()
    df_m5 = calculate_adx(df_m5, period=14)
    m5_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"
    m5_adx = df_m5.iloc[-1].get('adx', 0)
    m5_adx_threshold = config['parameters'].get('m5_adx_threshold', 20)

    # Donchian Channel (UPGRADED: Giảm từ 50 xuống 30)
    donchian_period = config['parameters'].get('donchian_period', 30)  # UPGRADED: Giảm từ 50 xuống 30
    df['upper'] = df['high'].rolling(window=donchian_period).max().shift(1)
    df['lower'] = df['low'].rolling(window=donchian_period).min().shift(1)
    
    # ATR 14 (for dynamic SL/TP and volatility filter)
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    # ADX 14 (Trend Strength Filter)
    df = calculate_adx(df, period=14)
    
    # RSI 14 (Added Filter)
    df['rsi'] = calculate_rsi(df['close'], period=14)
    
    # Volume MA (for volume confirmation)
    df['vol_ma'] = df['tick_volume'].rolling(window=20).mean()
    
    # UPGRADED: VWAP calculation for confirmation
    df['vwap'] = (df['close'] * df['tick_volume']).rolling(window=donchian_period).sum() / df['tick_volume'].rolling(window=donchian_period).sum()

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3] if len(df) >= 3 else None
    
    # 3. Logic: Donchian Breakout
    signal = None
    
    # Get config parameters
    buffer_multiplier = config['parameters'].get('buffer_multiplier', 150)  # UPGRADED: Tăng từ 100 lên 150 points
    buffer = buffer_multiplier * mt5.symbol_info(symbol).point
    breakout_confirmation = config['parameters'].get('breakout_confirmation', True)  # Wait 1-2 candles after breakout
    
    # ATR Volatility Filter (UPGRADED: Hẹp range từ 10-200 xuống 20-100 pips)
    atr_value = last['atr'] if not pd.isna(last['atr']) else 0
    point = mt5.symbol_info(symbol).point
    # Với EURUSD: ATR được tính bằng giá trị thực
    # Chuyển sang pips: ATR(pips) = ATR(price) / point / 10
    # Ví dụ: ATR = 0.0001, point = 0.00001 → ATR(pips) = 0.0001 / 0.00001 / 10 = 1 pip
    # Nếu ATR = 10 points → ATR(pips) = 10 / 10 = 1 pip
    atr_pips = (atr_value / point) / 10 if point > 0 else 0
    # EURUSD M1: ATR thường từ 5-30 pips (tùy volatility)
    # UPGRADED: Hẹp range để tránh extreme volatility
    atr_min = 20   # UPGRADED: Tăng từ 10 lên 20 pips
    atr_max = 100  # UPGRADED: Giảm từ 200 xuống 100 pips
    
    print(f"\n{'='*80}")
    print(f"📊 [STRATEGY 5: FILTER FIRST ANALYSIS] {symbol}")
    print(f"{'='*80}")
    print(f"💱 Price: {last['close']:.2f} | M5 Trend: {m5_trend} | RSI: {last['rsi']:.1f} | ADX: {last.get('adx', 0):.1f} | ATR: {atr_pips:.1f}p")
    print(f"   Donchian Upper: {last['upper']:.2f} | Lower: {last['lower']:.2f} | Buffer: {buffer/point:.0f} pts")
    
    # Track all filter status
    filter_status = []
    early_exit = False
    
    # ATR Volatility Filter
    if atr_pips < atr_min or atr_pips > atr_max:
        filter_status.append(f"❌ ATR: {atr_pips:.1f}p không trong khoảng {atr_min}-{atr_max}p")
        print(f"\n{'='*80}")
        print(f"❌ [KHÔNG CÓ TÍN HIỆU] - Early Exit Filter")
        print(f"{'='*80}")
        print(f"   {filter_status[0]}")
        print(f"{'='*80}\n")
        return error_count, 0
    else:
        filter_status.append(f"✅ ATR: {atr_pips:.1f}p trong khoảng {atr_min}-{atr_max}p")
    
    # ADX Filter (UPGRADED: Nâng từ 20 lên 30)
    adx_value = last.get('adx', 0)
    adx_threshold = config['parameters'].get('adx_threshold', 30)  # UPGRADED: Nâng từ 20 lên 30
    if pd.isna(adx_value) or adx_value < adx_threshold:
        filter_status.append(f"❌ M1 ADX: {adx_value:.1f} < {adx_threshold} (Choppy Market)")
        print(f"\n{'='*80}")
        print(f"❌ [KHÔNG CÓ TÍN HIỆU] - Early Exit Filter")
        print(f"{'='*80}")
        for status in filter_status:
            print(f"   {status}")
        print(f"{'='*80}\n")
        return error_count, 0
    else:
        filter_status.append(f"✅ M1 ADX: {adx_value:.1f} >= {adx_threshold}")
    
    # Volume Confirmation (stricter)
    volume_threshold = config['parameters'].get('volume_threshold', 1.5)  # Increased from 1.3
    is_high_volume = last['tick_volume'] > (last['vol_ma'] * volume_threshold)
    vol_ratio = last['tick_volume'] / last['vol_ma'] if last['vol_ma'] > 0 else 0
    
    # RSI thresholds (stricter)
    rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 55)  # Increased from 50
    rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 45)  # Decreased from 50
    
    # UPGRADED: False Breakout Check + False History Check (bỏ nếu 2 false gần)
    false_breakout = False
    false_history_count = 0
    
    if last['close'] > (last['upper'] + buffer):
        # BUY: Kiểm tra nến trước có phá vỡ nhưng đóng ngược lại không
        if prev['high'] > last['upper'] and prev['close'] < last['upper']:
            false_breakout = True
            filter_status.append(f"❌ False Breakout BUY: Nến trước phá vỡ nhưng đóng ngược lại")
    elif last['close'] < (last['lower'] - buffer):
        # SELL: Kiểm tra nến trước có phá vỡ nhưng đóng ngược lại không
        if prev['low'] < last['lower'] and prev['close'] > last['lower']:
            false_breakout = True
            filter_status.append(f"❌ False Breakout SELL: Nến trước phá vỡ nhưng đóng ngược lại")
    
    # UPGRADED: Check false history (kiểm tra 10 nến gần nhất có bao nhiêu false breakout)
    if len(df) >= 10:
        for i in range(2, min(12, len(df))):  # Check last 10 candles
            check_candle = df.iloc[-i]
            check_prev = df.iloc[-i-1] if i+1 < len(df) else None
            check_upper = df.iloc[-i]['upper'] if pd.notna(df.iloc[-i].get('upper')) else None
            check_lower = df.iloc[-i]['lower'] if pd.notna(df.iloc[-i].get('lower')) else None
            
            if check_prev is not None and check_upper is not None and check_lower is not None:
                # Check BUY false
                if check_prev['high'] > check_upper and check_candle['close'] < check_upper:
                    false_history_count += 1
                # Check SELL false
                elif check_prev['low'] < check_lower and check_candle['close'] > check_lower:
                    false_history_count += 1
    
    if false_breakout:
        filter_status.append(f"❌ False Breakout: Current candle")
    if false_history_count >= 2:
        filter_status.append(f"❌ False History: {false_history_count} false breakouts trong 10 nến gần nhất")
    
    if false_breakout or false_history_count >= 2:
        print(f"\n{'='*80}")
        print(f"❌ [KHÔNG CÓ TÍN HIỆU] - False Breakout Detected (Current: {false_breakout}, History: {false_history_count})")
        print(f"{'='*80}")
        for status in filter_status:
            print(f"   {status}")
        print(f"{'='*80}\n")
        return error_count, 0
    
    # BUY Signal
    has_breakout_buy = last['close'] > (last['upper'] + buffer)
    breakout_confirmed_buy = False
    
    if has_breakout_buy:
        filter_status.append(f"✅ Breakout BUY: Price {last['close']:.2f} > Upper {last['upper']:.2f} + Buffer")
        
        # Breakout Confirmation: Check if breakout is maintained
        if breakout_confirmation:
            # Check if previous candle also broke out (confirmation)
            # Use prev's upper for comparison
            prev_upper = df.iloc[-2]['upper'] if len(df) >= 2 and pd.notna(df.iloc[-2].get('upper')) else last['upper']
            if prev is not None and prev['close'] > (prev_upper + buffer):
                breakout_confirmed_buy = True
                filter_status.append(f"✅ Breakout Confirmed: Prev candle also broke out")
            else:
                # Still allow if current candle is strong breakout (1.5x buffer above upper)
                if last['close'] > last['upper'] + buffer * 1.5:  # Strong breakout
                    breakout_confirmed_buy = True
                    filter_status.append(f"✅ Strong Breakout: Price > Upper + {buffer * 1.5 / point:.0f} points")
                else:
                    filter_status.append(f"⏳ Breakout Not Confirmed: Waiting for confirmation candle")
        else:
            breakout_confirmed_buy = True
        
        if breakout_confirmed_buy:
            # M5 Trend + ADX Filter
            if m5_trend == "BULLISH":
                filter_status.append(f"✅ M5 Trend: BULLISH")
                
                # UPGRADED: Tuyệt đối không Buy khi RSI > 70
                if last['rsi'] > 70:
                    filter_status.append(f"❌ RSI Hard Stop: {last['rsi']:.1f} > 70 (Tuyệt đối không Buy)")
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI > 70 (Tuyệt đối không Buy)")
                    has_breakout_buy = False
                else:
                    filter_status.append(f"✅ RSI Hard Stop: {last['rsi']:.1f} <= 70 (OK để Buy)")
                
                if pd.notna(m5_adx) and m5_adx >= m5_adx_threshold:
                    filter_status.append(f"✅ M5 ADX: {m5_adx:.1f} >= {m5_adx_threshold}")
                else:
                    filter_status.append(f"❌ M5 ADX: {m5_adx:.1f} < {m5_adx_threshold} (cần >= {m5_adx_threshold})")
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - M5 ADX không đạt")
                    has_breakout_buy = False
                
                if has_breakout_buy:
                    # UPGRADED: VWAP Confirmation (breakout vượt VWAP)
                    vwap_value = last.get('vwap', None)
                    vwap_confirmation_required = config['parameters'].get('vwap_confirmation_required', True)
                    vwap_ok = True
                    if vwap_confirmation_required and pd.notna(vwap_value):
                        vwap_ok = last['close'] > vwap_value
                        filter_status.append(f"{'✅' if vwap_ok else '❌'} VWAP Confirmation: Close {last['close']:.2f} > VWAP {vwap_value:.2f}")
                    else:
                        filter_status.append(f"⏭️ VWAP Confirmation: Disabled")
                    
                    if vwap_ok:
                        # RSI Filter (stricter)
                        filter_status.append(f"{'✅' if last['rsi'] > rsi_buy_threshold else '❌'} RSI > {rsi_buy_threshold}: {last['rsi']:.1f}")
                        
                        if last['rsi'] > rsi_buy_threshold:
                            filter_status.append(f"{'✅' if is_high_volume else '❌'} Volume: {vol_ratio:.2f}x {'>' if is_high_volume else '<'} {volume_threshold}x")
                            if is_high_volume:
                                signal = "BUY"
                                print("\n✅ [SIGNAL FOUND] BUY - Tất cả điều kiện đạt!")
                            else:
                                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Volume không đủ")
                        else:
                            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần > {rsi_buy_threshold})")
                    else:
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - VWAP confirmation không đạt")
            else:
                filter_status.append(f"❌ M5 Trend: BEARISH (cần BULLISH)")
                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - M5 Trend không phù hợp")
             
    # SELL Signal
    has_breakout_sell = last['close'] < (last['lower'] - buffer)
    breakout_confirmed_sell = False
    
    if has_breakout_sell:
        filter_status.append(f"✅ Breakout SELL: Price {last['close']:.2f} < Lower {last['lower']:.2f} - Buffer")
        
        # Breakout Confirmation
        if breakout_confirmation:
            # Use prev's lower for comparison
            prev_lower = df.iloc[-2]['lower'] if len(df) >= 2 and pd.notna(df.iloc[-2].get('lower')) else last['lower']
            if prev is not None and prev['close'] < (prev_lower - buffer):
                breakout_confirmed_sell = True
                filter_status.append(f"✅ Breakout Confirmed: Prev candle also broke out")
            else:
                # Still allow if current candle is strong breakout
                if last['close'] < last['lower'] - buffer * 1.5:  # Strong breakout
                    breakout_confirmed_sell = True
                    filter_status.append(f"✅ Strong Breakout: Price < Lower - {buffer * 1.5 / point:.0f} points")
                else:
                    filter_status.append(f"⏳ Breakout Not Confirmed: Waiting for confirmation candle")
        else:
            breakout_confirmed_sell = True
        
        if breakout_confirmed_sell:
            # M5 Trend + ADX Filter
            if m5_trend == "BEARISH":
                filter_status.append(f"✅ M5 Trend: BEARISH")
                
                if pd.notna(m5_adx) and m5_adx >= m5_adx_threshold:
                    filter_status.append(f"✅ M5 ADX: {m5_adx:.1f} >= {m5_adx_threshold}")
                else:
                    filter_status.append(f"❌ M5 ADX: {m5_adx:.1f} < {m5_adx_threshold} (cần >= {m5_adx_threshold})")
                    print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - M5 ADX không đạt")
                    has_breakout_sell = False
                
                if has_breakout_sell:
                    # UPGRADED: VWAP Confirmation (breakout vượt VWAP)
                    vwap_value = last.get('vwap', None)
                    vwap_confirmation_required = config['parameters'].get('vwap_confirmation_required', True)
                    vwap_ok = True
                    if vwap_confirmation_required and pd.notna(vwap_value):
                        vwap_ok = last['close'] < vwap_value
                        filter_status.append(f"{'✅' if vwap_ok else '❌'} VWAP Confirmation: Close {last['close']:.2f} < VWAP {vwap_value:.2f}")
                    else:
                        filter_status.append(f"⏭️ VWAP Confirmation: Disabled")
                    
                    if vwap_ok:
                        # RSI Filter (stricter)
                        filter_status.append(f"{'✅' if last['rsi'] < rsi_sell_threshold else '❌'} RSI < {rsi_sell_threshold}: {last['rsi']:.1f}")
                        
                        if last['rsi'] < rsi_sell_threshold:
                            filter_status.append(f"{'✅' if is_high_volume else '❌'} Volume: {vol_ratio:.2f}x {'>' if is_high_volume else '<'} {volume_threshold}x")
                            if is_high_volume:
                                signal = "SELL"
                                print("\n✅ [SIGNAL FOUND] SELL - Tất cả điều kiện đạt!")
                            else:
                                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Volume không đủ")
                        else:
                            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần < {rsi_sell_threshold})")
                    else:
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - VWAP confirmation không đạt")
            else:
                filter_status.append(f"❌ M5 Trend: BULLISH (cần BEARISH)")
                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - M5 Trend không phù hợp")
    
    if not has_breakout_buy and not has_breakout_sell:
        filter_status.append(f"❌ No Breakout: Price {last['close']:.2f} trong range [{last['lower']:.2f}, {last['upper']:.2f}]")
        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Không có Donchian Breakout")
    
    # Final Summary
    if not signal:
        print(f"\n{'─'*80}")
        print(f"❌ [KHÔNG CÓ TÍN HIỆU] - Tóm tắt các bộ lọc:")
        print(f"{'─'*80}")
        
        # Group filters by tier
        print(f"\n🔴 [TIER 1: EARLY EXIT FILTERS]")
        tier1_status = [f for f in filter_status if "ATR" in f or "ADX" in f or "False Breakout" in f]
        for status in tier1_status:
            print(f"   {status}")
        
        print(f"\n🟡 [TIER 2: SIGNAL CONDITIONS]")
        tier2_status = [f for f in filter_status if "ATR" not in f and "ADX" not in f and "False Breakout" not in f]
        for i, status in enumerate(tier2_status, 1):
            print(f"   {i}. {status}")
        
        # Chi tiết giá trị
        print(f"\n📊 [CHI TIẾT GIÁ TRỊ]")
        print(f"   💱 Price: {last['close']:.2f}")
        print(f"   📈 M5 Trend: {m5_trend}")
        print(f"   📊 Donchian Upper: {last['upper']:.2f} | Lower: {last['lower']:.2f} | Period: {donchian_period}")
        vwap_value = last.get('vwap', None)
        if pd.notna(vwap_value):
            print(f"   📊 VWAP: {vwap_value:.2f} (UPGRADED: VWAP confirmation)")
        print(f"   📊 ATR: {atr_pips:.1f} pips (range: {atr_min}-{atr_max} pips) [UPGRADED: Hẹp range]")
        print(f"   📊 M1 ADX: {adx_value:.1f} (cần >= {adx_threshold}) [UPGRADED: Từ 20 lên 30]")
        print(f"   📊 M5 ADX: {m5_adx:.1f} (cần >= {m5_adx_threshold})")
        print(f"   📊 RSI: {last['rsi']:.1f} (BUY cần > {rsi_buy_threshold} và <= 70, SELL cần < {rsi_sell_threshold}) [UPGRADED: Tuyệt đối không Buy khi RSI > 70]")
        print(f"   📊 Volume: {last['tick_volume']} / Avg: {int(last['vol_ma'])} = {vol_ratio:.2f}x (cần > {volume_threshold}x)")
        
        print(f"\n💡 Tổng số filters đã kiểm tra: {len(filter_status)}")
        print(f"   ✅ PASS: {len([f for f in filter_status if f.startswith('✅')])}")
        print(f"   ❌ FAIL: {len([f for f in filter_status if f.startswith('❌')])}")
        print(f"{'─'*80}\n")
        
    if signal:
        # --- CONSECUTIVE LOSS GUARD ---
        loss_streak_threshold = config['parameters'].get('loss_streak_threshold', 2)
        loss_cooldown_minutes = config['parameters'].get('loss_cooldown_minutes', 45)
        
        try:
            from_timestamp = int((datetime.now() - timedelta(days=1)).timestamp())
            to_timestamp = int(datetime.now().timestamp())
            deals = mt5.history_deals_get(from_timestamp, to_timestamp)
            
            if deals:
                closed_deals = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT and d.magic == magic and d.profit != 0]
                closed_deals.sort(key=lambda x: x.time, reverse=True)
                
                loss_streak = 0
                for deal in closed_deals:
                    if deal.profit < 0:
                        loss_streak += 1
                    else:
                        break
                
                if loss_streak >= loss_streak_threshold:
                    if len(closed_deals) > 0:
                        last_deal_time = closed_deals[0].time
                        last_deal_timestamp = last_deal_time.timestamp() if isinstance(last_deal_time, datetime) else last_deal_time
                        minutes_since_last = (datetime.now().timestamp() - last_deal_timestamp) / 60
                        
                        if minutes_since_last < loss_cooldown_minutes:
                            remaining = loss_cooldown_minutes - minutes_since_last
                            print(f"   ⏳ Consecutive Loss Guard: {loss_streak} losses, {remaining:.1f} minutes remaining")
                            return error_count, 0
        except Exception as e:
            print(f"   ⚠️ Error checking consecutive losses: {e}")
        
        # --- SPAM FILTER & COOLDOWN ---
        deals = mt5.history_deals_get(date_from=time.time() - 300, date_to=time.time())
        if deals:
            my_deals = [d for d in deals if d.magic == magic]
            if my_deals:
                print(f"   ⏳ Cooldown: Last trade was < 5 mins ago. Skipping.")
                return error_count, 0

        price = mt5.symbol_info_tick(symbol).ask if signal == "BUY" else mt5.symbol_info_tick(symbol).bid
        
        # --- SL/TP Logic based on Config ---
        sl_mode = config['parameters'].get('sl_mode', 'atr')  # Default to ATR
        reward_ratio = config['parameters'].get('reward_ratio', 1.5)
        
        sl = 0.0
        tp = 0.0
        
        if sl_mode == 'atr':
            # ATR-based SL/TP (Dynamic)
            sl_multiplier = config['parameters'].get('sl_atr_multiplier', 2.0)
            tp_multiplier = config['parameters'].get('tp_atr_multiplier', 3.0)
            
            sl_dist = atr_value * sl_multiplier
            tp_dist = atr_value * tp_multiplier
            
            if signal == "BUY":
                sl = price - sl_dist
                tp = price + tp_dist
            else:  # SELL
                sl = price + sl_dist
                tp = price - tp_dist
            
            # Minimum distance check
            min_dist = 100 * point  # 10 pips minimum
            if signal == "BUY":
                if (price - sl) < min_dist:
                    sl = price - min_dist
                    risk_dist = price - sl
                    tp = price + (risk_dist * reward_ratio)
            else:
                if (sl - price) < min_dist:
                    sl = price + min_dist
                    risk_dist = sl - price
                    tp = price - (risk_dist * reward_ratio)
            
            # UPGRADED: Giới hạn SL tối đa 25 pips
            max_sl_pips = 25
            max_sl_dist = max_sl_pips * point * 10  # 25 pips
            if signal == "BUY":
                risk_dist = price - sl
                if risk_dist > max_sl_dist:
                    sl = price - max_sl_dist
                    risk_dist = max_sl_dist
                    tp = price + (risk_dist * reward_ratio)
                    print(f"   ⚠️ SL giới hạn: Risk {risk_dist/point/10:.1f} pips > {max_sl_pips} pips, dùng max: {max_sl_pips} pips")
            else:  # SELL
                risk_dist = sl - price
                if risk_dist > max_sl_dist:
                    sl = price + max_sl_dist
                    risk_dist = max_sl_dist
                    tp = price - (risk_dist * reward_ratio)
                    print(f"   ⚠️ SL giới hạn: Risk {risk_dist/point/10:.1f} pips > {max_sl_pips} pips, dùng max: {max_sl_pips} pips")
            
            print(f"   📏 ATR SL: {sl:.2f} ({sl_multiplier}xATR) | TP: {tp:.2f} ({tp_multiplier}xATR, R:R {reward_ratio})")
            
        elif sl_mode == 'auto_m5':
            # Use fetched M5 data
            prev_m5_high = df_m5.iloc[-2]['high']
            prev_m5_low = df_m5.iloc[-2]['low']
            buffer_sl = 20 * point
            
            if signal == "BUY":
                sl = prev_m5_low - buffer_sl
                min_dist = 100 * point
                if (price - sl) < min_dist: sl = price - min_dist
                risk_dist = price - sl
                # UPGRADED: Giới hạn SL tối đa 25 pips
                max_sl_pips = 25
                max_sl_dist = max_sl_pips * point * 10
                if risk_dist > max_sl_dist:
                    sl = price - max_sl_dist
                    risk_dist = max_sl_dist
                    print(f"   ⚠️ SL giới hạn: Risk {risk_dist/point/10:.1f} pips > {max_sl_pips} pips, dùng max: {max_sl_pips} pips")
                tp = price + (risk_dist * reward_ratio)
                
            elif signal == "SELL":
                sl = prev_m5_high + buffer_sl
                min_dist = 100 * point
                if (sl - price) < min_dist: sl = price + min_dist
                risk_dist = sl - price
                # UPGRADED: Giới hạn SL tối đa 25 pips
                max_sl_pips = 25
                max_sl_dist = max_sl_pips * point * 10
                if risk_dist > max_sl_dist:
                    sl = price + max_sl_dist
                    risk_dist = max_sl_dist
                    print(f"   ⚠️ SL giới hạn: Risk {risk_dist/point/10:.1f} pips > {max_sl_pips} pips, dùng max: {max_sl_pips} pips")
                tp = price - (risk_dist * reward_ratio)
            print(f"   📏 Auto M5 SL: {sl:.2f} | TP: {tp:.2f} (R:R {reward_ratio})")
        else:
            # Fixed SL/TP (Legacy)
            sl = price - 2.0 if signal == "BUY" else price + 2.0
            tp = price + 5.0 if signal == "BUY" else price - 5.0
            # UPGRADED: Giới hạn SL tối đa 25 pips cho Fixed mode
            max_sl_pips = 25
            max_sl_dist = max_sl_pips * point * 10
            if signal == "BUY":
                risk_dist = price - sl
                if risk_dist > max_sl_dist:
                    sl = price - max_sl_dist
                    risk_dist = max_sl_dist
                    tp = price + (risk_dist * reward_ratio)
                    print(f"   ⚠️ SL giới hạn: Risk {risk_dist/point/10:.1f} pips > {max_sl_pips} pips, dùng max: {max_sl_pips} pips")
            else:
                risk_dist = sl - price
                if risk_dist > max_sl_dist:
                    sl = price + max_sl_dist
                    risk_dist = max_sl_dist
                    tp = price - (risk_dist * reward_ratio)
                    print(f"   ⚠️ SL giới hạn: Risk {risk_dist/point/10:.1f} pips > {max_sl_pips} pips, dùng max: {max_sl_pips} pips")
            print(f"   📏 Fixed SL: {sl:.2f} | TP: {tp:.2f}")

        print(f"🚀 Strat 5 SIGNAL: {signal} @ {price}")
        
        db.log_signal("Strategy_5_Filter_First", symbol, signal, price, sl, tp, {
            "setup": "Donchian Breakout",
            "rsi": float(last['rsi']),
            "adx": float(adx_value),
            "atr": float(atr_value),
            "atr_pips": float(atr_pips),
            "volume": int(last['tick_volume']),
            "vol_ratio": float(last['tick_volume'] / last['vol_ma']) if last['vol_ma'] > 0 else 0,
            "trend": m5_trend,
            "donchian_period": donchian_period
        }, account_id=config['account'])

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": "Strat5_FilterFirst",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Success: {result.order}")
            db.log_order(result.order, "Strategy_5_Filter_First", symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
            
            msg = (
                f"✅ <b>Strat 5: Filter First Executed</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"👤 <b>Account:</b> {config['account']}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal})\n"
                f"💵 <b>Price:</b> {price}\n"
                f"🛑 <b>SL:</b> {sl:.2f} | 🎯 <b>TP:</b> {tp:.2f}\n"
                f"📊 <b>Indicators:</b>\n"
                f"• Donchian Breakout ({donchian_period} periods) [UPGRADED: 30]\n"
                f"• VWAP: {last.get('vwap', 0):.2f} [UPGRADED: VWAP confirmation]\n"
                f"• RSI: {last['rsi']:.1f}\n"
                f"• ADX: {adx_value:.1f} [UPGRADED: >= 30]\n"
                f"• ATR: {atr_pips:.1f} pips [UPGRADED: 20-100 range]\n"
                f"• Volume: {int(last['tick_volume'])} ({last['tick_volume']/last['vol_ma']:.1f}x avg)"
            )
            send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
            return 0, 0
        else:
            print(f"❌ Order Failed: {result.retcode}")
            return error_count + 1, result.retcode

    return error_count, 0

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_5.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 5: Filter First - Started (UPGRADED)")
        print("📋 UPGRADED Improvements:")
        print("   ✅ Donchian period reduced (50 → 30)")
        print("   ✅ M1 ADX threshold increased (20 → 30)")
        print("   ✅ Buffer multiplier increased (100 → 150 points)")
        print("   ✅ ATR range narrowed (10-200 → 20-100 pips)")
        print("   ✅ VWAP confirmation added")
        print("   ✅ False history check (skip if 2+ false breakouts in last 10 candles)")
        try:
            while True:
                consecutive_errors, last_error_code = strategy_5_logic(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Strategy 5: Filter First] WARNING: 5 Consecutive Order Failures. Last Error: {error_msg}. Pausing for 2 minutes..."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    time.sleep(120)
                    consecutive_errors = 0
                    print("▶️ Resuming...")
                    continue
                    
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
