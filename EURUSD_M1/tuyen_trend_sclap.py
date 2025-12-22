import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# Import local modules
sys.path.append('..') 
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message, calculate_rsi

# Initialize Database
db = Database()

def calculate_ema(series, span):
    """Calculate EMA"""
    return series.ewm(span=span, adjust=False).mean()

def calculate_atr(df, period=14):
    """Calculate ATR"""
    df = df.copy()
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift(1))
    df['tr2'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=period).mean()
    return df['atr']

def is_bullish_engulfing(prev_candle, curr_candle):
    """
    Bullish Engulfing Pattern:
    - Previous candle is bearish (close < open)
    - Current candle is bullish (close > open)
    - Current open < previous close
    - Current close > previous open
    """
    prev_bearish = prev_candle['close'] < prev_candle['open']
    curr_bullish = curr_candle['close'] > curr_candle['open']
    engulfs = (curr_candle['open'] < prev_candle['close']) and (curr_candle['close'] > prev_candle['open'])
    return prev_bearish and curr_bullish and engulfs

def is_bearish_engulfing(prev_candle, curr_candle):
    """
    Bearish Engulfing Pattern:
    - Previous candle is bullish (close > open)
    - Current candle is bearish (close < open)
    - Current open > previous close
    - Current close < previous open
    """
    prev_bullish = prev_candle['close'] > prev_candle['open']
    curr_bearish = curr_candle['close'] < curr_candle['open']
    engulfs = (curr_candle['open'] > prev_candle['close']) and (curr_candle['close'] < prev_candle['open'])
    return prev_bullish and curr_bearish and engulfs

def check_rsi_reversal_up(rsi_series, lookback=10):
    """
    Check if RSI is turning up (quay đầu lên)
    RSI current > RSI previous
    """
    if len(rsi_series) < 2:
        return False
    current_rsi = rsi_series.iloc[-1]
    prev_rsi = rsi_series.iloc[-2]
    return current_rsi > prev_rsi

def check_rsi_reversal_down(rsi_series, lookback=10):
    """
    Check if RSI is turning down (quay đầu xuống)
    RSI current < RSI previous
    """
    if len(rsi_series) < 2:
        return False
    current_rsi = rsi_series.iloc[-1]
    prev_rsi = rsi_series.iloc[-2]
    return current_rsi < prev_rsi

def find_previous_rsi_extreme(rsi_series, lookback=20, min_rsi=70, max_rsi=30):
    """
    Find if RSI was in extreme zone (≥70 for overbought, ≤30 for oversold) in recent lookback period
    Returns: (found, extreme_value, extreme_type)
    For BUY: Find RSI ≥70 before current
    For SELL: Find RSI ≤30 before current
    """
    if len(rsi_series) < 2:
        return (False, None, None)
    
    if len(rsi_series) < lookback:
        lookback = len(rsi_series)
    
    # Check for overbought (≥70) - for BUY signal
    # Look back from previous candle (not current)
    recent_rsi = rsi_series.iloc[-lookback:-1]  # Exclude current candle
    if len(recent_rsi) > 0:
        overbought = recent_rsi[recent_rsi >= min_rsi]
        if len(overbought) > 0:
            return (True, overbought.iloc[-1], 'overbought')
        
        # Check for oversold (≤30) - for SELL signal
        oversold = recent_rsi[recent_rsi <= max_rsi]
        if len(oversold) > 0:
            return (True, oversold.iloc[-1], 'oversold')
    
    return (False, None, None)

def m1_scalp_logic(config, error_count=0):
    """
    M1 Scalp Strategy Logic
    BUY: EMA50 > EMA200, RSI từ ≥70 về 40-50 (không <32), RSI quay đầu lên, ATR ≥ 1.5 pips, 
         Bullish engulfing + Close > EMA50, Volume tăng
    SELL: EMA50 < EMA200, RSI từ ≤30 về 50-60 (không >68), RSI quay đầu xuống, ATR ≥ 1.5 pips,
          Bearish engulfing + Close < EMA50, Volume tăng
    SL = 2ATR + 6 point, TP = 2SL
    """
    try:
        symbol = config['symbol']
        volume = config.get('volume', 0.01)
        magic = config['magic']
        max_positions = config.get('max_positions', 1)
        
        # --- 1. Manage Existing Positions ---
        positions = mt5.positions_get(symbol=symbol, magic=magic)
        if positions:
            for pos in positions:
                manage_position(pos.ticket, symbol, magic, config)
            if len(positions) >= max_positions:
                return error_count, 0

        # --- 2. Data Fetching ---
        df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 300)
        if df_m1 is None:
            print(f"⚠️ Không thể lấy dữ liệu M1 cho {symbol}")
            return error_count, 0

        # --- 3. Calculate Indicators ---
        df_m1['ema50'] = calculate_ema(df_m1['close'], 50)
        df_m1['ema200'] = calculate_ema(df_m1['close'], 200)
        df_m1['atr'] = calculate_atr(df_m1, 14)
        df_m1['rsi'] = calculate_rsi(df_m1['close'], 14)
        
        # Volume MA (10 candles)
        df_m1['vol_ma'] = df_m1['tick_volume'].rolling(window=10).mean()
        
        # Get current and previous candles (completed candles)
        if len(df_m1) < 3:
            return error_count, 0
        
        curr_candle = df_m1.iloc[-2]  # Last completed candle
        prev_candle = df_m1.iloc[-3]   # Previous completed candle
        current_rsi = df_m1['rsi'].iloc[-2]  # RSI of last completed candle
        prev_rsi = df_m1['rsi'].iloc[-3]     # RSI of previous candle
        
        # Get current price for entry
        tick = mt5.symbol_info_tick(symbol)
        current_price = tick.ask  # Will be updated based on signal
        
        # Get point size
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            print(f"⚠️ Không thể lấy thông tin symbol {symbol}")
            return error_count, 0
        
        point = symbol_info.point
        
        # --- 4. Check ATR Condition (Điều kiện 4) ---
        atr_val = curr_candle['atr']
        # 1.5 pips = 1.5 * 0.0001 = 0.00015 (cho EURUSD, 1 pip = 0.0001)
        min_atr = 0.00015  # 1.5 pips
        if pd.isna(atr_val) or atr_val < min_atr:
            return error_count, 0
        
        signal_type = None
        reason = ""
        log_details = []
        
        # --- 5. BUY Signal Check ---
        log_details.append(f"{'='*80}")
        log_details.append(f"🔍 [BUY] Kiểm tra điều kiện BUY...")
        log_details.append(f"{'='*80}")
        
        ema50_val = curr_candle['ema50']
        ema200_val = curr_candle['ema200']
        current_price_close = curr_candle['close']  # Giá hiện tại (close của nến đã đóng cửa)
        
        # Điều kiện 1: EMA50 > EMA200 VÀ Giá hiện tại > EMA50
        buy_condition1a = ema50_val > ema200_val
        buy_condition1b = current_price_close > ema50_val
        buy_condition1 = buy_condition1a and buy_condition1b
        
        log_details.append(f"{'✅' if buy_condition1a else '❌'} [BUY] ĐK1a: EMA50 ({ema50_val:.5f}) > EMA200 ({ema200_val:.5f})")
        log_details.append(f"{'✅' if buy_condition1b else '❌'} [BUY] ĐK1b: Giá hiện tại ({current_price_close:.5f}) > EMA50 ({ema50_val:.5f})")
        
        if buy_condition1:
            # Điều kiện 2: RSI từ vùng quá mua (≥70) hồi về 40-50, RSI KHÔNG < 32
            found_extreme, extreme_rsi, extreme_type = find_previous_rsi_extreme(
                df_m1['rsi'], lookback=20, min_rsi=70, max_rsi=30
            )
            buy_condition2a = found_extreme and extreme_type == 'overbought'
            buy_condition2b = False
            buy_condition2c = False
            if buy_condition2a:
                # RSI was ≥70 before, now should be in 40-50 range, and not < 32
                buy_condition2b = (40 <= current_rsi <= 50)
                buy_condition2c = (current_rsi >= 32)
            buy_condition2 = buy_condition2a and buy_condition2b and buy_condition2c
            
            if buy_condition2a and extreme_rsi is not None:
                log_details.append(f"{'✅' if buy_condition2a else '❌'} [BUY] ĐK2a: RSI trước đó ≥70 (tìm thấy: {extreme_rsi:.1f})")
            else:
                log_details.append(f"❌ [BUY] ĐK2a: RSI trước đó ≥70 (không tìm thấy)")
            
            if buy_condition2a and extreme_rsi is not None:
                log_details.append(f"{'✅' if buy_condition2b else '❌'} [BUY] ĐK2b: RSI hiện tại ({current_rsi:.1f}) trong [40-50]")
                log_details.append(f"{'✅' if buy_condition2c else '❌'} [BUY] ĐK2c: RSI hiện tại ({current_rsi:.1f}) KHÔNG < 32")
            else:
                log_details.append(f"   ⏭️ [BUY] ĐK2b, 2c: Bỏ qua (chưa tìm thấy RSI ≥70)")
            
            # Điều kiện 3: RSI quay đầu lên
            buy_condition3 = check_rsi_reversal_up(df_m1['rsi'])
            log_details.append(f"{'✅' if buy_condition3 else '❌'} [BUY] ĐK3: RSI quay đầu lên ({prev_rsi:.1f} -> {current_rsi:.1f})")
            
            # Điều kiện 4: ATR (đã check ở trên)
            atr_pips = atr_val / 0.0001  # Convert to pips
            log_details.append(f"{'✅' if atr_val >= min_atr else '❌'} [BUY] ĐK4: ATR ({atr_pips:.1f} pips = {atr_val:.5f}) >= 1.5 pips ({min_atr:.5f})")
            
            # Điều kiện 5: Bullish engulfing + Close > EMA50
            buy_condition5a = is_bullish_engulfing(prev_candle, curr_candle)
            buy_condition5b = curr_candle['close'] > ema50_val
            buy_condition5 = buy_condition5a and buy_condition5b
            
            log_details.append(f"{'✅' if buy_condition5a else '❌'} [BUY] ĐK5a: Bullish Engulfing pattern")
            log_details.append(f"{'✅' if buy_condition5b else '❌'} [BUY] ĐK5b: Close ({curr_candle['close']:.5f}) > EMA50 ({ema50_val:.5f})")
            
            # Điều kiện 6: Volume tăng (volume nến entry ≥ volume trung bình 10 nến)
            vol_ma_val = curr_candle['vol_ma']
            buy_condition6 = False
            if not pd.isna(vol_ma_val) and vol_ma_val > 0:
                buy_condition6 = curr_candle['tick_volume'] >= vol_ma_val
                log_details.append(f"{'✅' if buy_condition6 else '❌'} [BUY] ĐK6: Volume ({curr_candle['tick_volume']:.0f}) >= MA10 ({vol_ma_val:.0f})")
            else:
                log_details.append(f"❌ [BUY] ĐK6: Volume MA không hợp lệ (vol_ma: {vol_ma_val})")
            
            # Tổng hợp kết quả BUY
            all_buy_conditions = [buy_condition1, buy_condition2, buy_condition3, buy_condition5, buy_condition6]
            buy_passed = all(all_buy_conditions)
            
            if buy_passed:
                signal_type = "BUY"
                reason = "M1_Scalp_BullishEngulfing"
                current_price = tick.ask
                
                log_details.append(f"\n🚀 [BUY SIGNAL] Tất cả điều kiện đã thỏa!")
            else:
                failed_conditions = []
                if not buy_condition1: failed_conditions.append("ĐK1 (Xu hướng)")
                if not buy_condition2: failed_conditions.append("ĐK2 (RSI extreme)")
                if not buy_condition3: failed_conditions.append("ĐK3 (RSI reversal)")
                if not buy_condition5: failed_conditions.append("ĐK5 (Engulfing)")
                if not buy_condition6: failed_conditions.append("ĐK6 (Volume)")
                log_details.append(f"\n❌ [BUY] Không đủ điều kiện. Thiếu: {', '.join(failed_conditions)}")
        else:
            log_details.append(f"   ⏭️ [BUY] ĐK1 không thỏa → Bỏ qua các điều kiện còn lại")
        
        # --- 6. SELL Signal Check ---
        if signal_type is None:
            log_details.append(f"\n{'='*80}")
            log_details.append(f"🔍 [SELL] Kiểm tra điều kiện SELL...")
            log_details.append(f"{'='*80}")
            
            # Điều kiện 1: EMA50 < EMA200 VÀ Giá hiện tại < EMA50
            sell_condition1a = ema50_val < ema200_val
            sell_condition1b = current_price_close < ema50_val
            sell_condition1 = sell_condition1a and sell_condition1b
            
            log_details.append(f"{'✅' if sell_condition1a else '❌'} [SELL] ĐK1a: EMA50 ({ema50_val:.5f}) < EMA200 ({ema200_val:.5f})")
            log_details.append(f"{'✅' if sell_condition1b else '❌'} [SELL] ĐK1b: Giá hiện tại ({current_price_close:.5f}) < EMA50 ({ema50_val:.5f})")
            
            if sell_condition1:
                # Điều kiện 2: RSI từ vùng quá bán (≤30) hồi về 50-60, RSI KHÔNG > 68
                found_extreme, extreme_rsi, extreme_type = find_previous_rsi_extreme(
                    df_m1['rsi'], lookback=20, min_rsi=70, max_rsi=30
                )
                sell_condition2a = found_extreme and extreme_type == 'oversold'
                sell_condition2b = False
                sell_condition2c = False
                if sell_condition2a:
                    # RSI was ≤30 before, now should be in 50-60 range, and not > 68
                    sell_condition2b = (50 <= current_rsi <= 60)
                    sell_condition2c = (current_rsi <= 68)
                sell_condition2 = sell_condition2a and sell_condition2b and sell_condition2c
                
                if sell_condition2a and extreme_rsi is not None:
                    log_details.append(f"{'✅' if sell_condition2a else '❌'} [SELL] ĐK2a: RSI trước đó ≤30 (tìm thấy: {extreme_rsi:.1f})")
                else:
                    log_details.append(f"❌ [SELL] ĐK2a: RSI trước đó ≤30 (không tìm thấy)")
                
                if sell_condition2a and extreme_rsi is not None:
                    log_details.append(f"{'✅' if sell_condition2b else '❌'} [SELL] ĐK2b: RSI hiện tại ({current_rsi:.1f}) trong [50-60]")
                    log_details.append(f"{'✅' if sell_condition2c else '❌'} [SELL] ĐK2c: RSI hiện tại ({current_rsi:.1f}) KHÔNG > 68")
                else:
                    log_details.append(f"   ⏭️ [SELL] ĐK2b, 2c: Bỏ qua (chưa tìm thấy RSI ≤30)")
                
                # Điều kiện 3: RSI quay đầu xuống
                sell_condition3 = check_rsi_reversal_down(df_m1['rsi'])
                log_details.append(f"{'✅' if sell_condition3 else '❌'} [SELL] ĐK3: RSI quay đầu xuống ({prev_rsi:.1f} -> {current_rsi:.1f})")
                
                # Điều kiện 4: ATR (đã check ở trên)
                atr_pips = atr_val / 0.0001  # Convert to pips
                log_details.append(f"{'✅' if atr_val >= min_atr else '❌'} [SELL] ĐK4: ATR ({atr_pips:.1f} pips = {atr_val:.5f}) >= 1.5 pips ({min_atr:.5f})")
                
                # Điều kiện 5: Bearish engulfing + Close < EMA50
                sell_condition5a = is_bearish_engulfing(prev_candle, curr_candle)
                sell_condition5b = curr_candle['close'] < ema50_val
                sell_condition5 = sell_condition5a and sell_condition5b
                
                log_details.append(f"{'✅' if sell_condition5a else '❌'} [SELL] ĐK5a: Bearish Engulfing pattern")
                log_details.append(f"{'✅' if sell_condition5b else '❌'} [SELL] ĐK5b: Close ({curr_candle['close']:.5f}) < EMA50 ({ema50_val:.5f})")
                
                # Điều kiện 6: Volume tăng
                vol_ma_val = curr_candle['vol_ma']
                sell_condition6 = False
                if not pd.isna(vol_ma_val) and vol_ma_val > 0:
                    sell_condition6 = curr_candle['tick_volume'] >= vol_ma_val
                    log_details.append(f"{'✅' if sell_condition6 else '❌'} [SELL] ĐK6: Volume ({curr_candle['tick_volume']:.0f}) >= MA10 ({vol_ma_val:.0f})")
                else:
                    log_details.append(f"❌ [SELL] ĐK6: Volume MA không hợp lệ (vol_ma: {vol_ma_val})")
                
                # Tổng hợp kết quả SELL
                all_sell_conditions = [sell_condition1, sell_condition2, sell_condition3, sell_condition5, sell_condition6]
                sell_passed = all(all_sell_conditions)
                
                if sell_passed:
                    signal_type = "SELL"
                    reason = "M1_Scalp_BearishEngulfing"
                    current_price = tick.bid
                    
                    log_details.append(f"\n🚀 [SELL SIGNAL] Tất cả điều kiện đã thỏa!")
                else:
                    failed_conditions = []
                    if not sell_condition1: failed_conditions.append("ĐK1 (Xu hướng)")
                    if not sell_condition2: failed_conditions.append("ĐK2 (RSI extreme)")
                    if not sell_condition3: failed_conditions.append("ĐK3 (RSI reversal)")
                    if not sell_condition5: failed_conditions.append("ĐK5 (Engulfing)")
                    if not sell_condition6: failed_conditions.append("ĐK6 (Volume)")
                    log_details.append(f"\n❌ [SELL] Không đủ điều kiện. Thiếu: {', '.join(failed_conditions)}")
            else:
                log_details.append(f"   ⏭️ [SELL] ĐK1 không thỏa → Bỏ qua các điều kiện còn lại")
        
        # --- 7. No Signal - Print Detailed Log ---
        if signal_type is None:
            print(f"\n{'='*80}")
            print(f"📊 [M1 Scalp] Không có tín hiệu - Chi tiết điều kiện:")
            print(f"{'='*80}")
            for detail in log_details:
                print(f"   {detail}")
            print(f"\n📈 [Indicators] Price: {curr_candle['close']:.5f} | EMA50: {ema50_val:.5f} | EMA200: {ema200_val:.5f} | RSI: {current_rsi:.1f} | ATR: {atr_val:.5f}")
            print(f"{'='*80}\n")
            return error_count, 0
        
        # --- 8. Calculate SL and TP ---
        # SL = 2ATR + 6 point, TP = 2SL
        sl_distance = (2 * atr_val) + (6 * point)
        tp_distance = 2 * sl_distance
        
        if signal_type == "BUY":
            sl = current_price - sl_distance
            tp = current_price + tp_distance
        else:  # SELL
            sl = current_price + sl_distance
            tp = current_price - tp_distance
        
        # Normalize to symbol digits
        digits = symbol_info.digits
        current_price = round(current_price, digits)
        sl = round(sl, digits)
        tp = round(tp, digits)
        
        # --- 9. Spam Filter (60s) ---
        strat_positions = mt5.positions_get(symbol=symbol, magic=magic)
        if strat_positions:
            strat_positions = sorted(strat_positions, key=lambda x: x.time, reverse=True)
            if (tick.time - strat_positions[0].time) < 60:
                print("   ⏳ Trade taken recently. Waiting.")
                return error_count, 0
        
        # --- 10. Print Log Details ---
        print(f"\n{'='*80}")
        print(f"🚀 [M1 SCALP SIGNAL] {signal_type} @ {current_price:.5f}")
        print(f"{'='*80}")
        for detail in log_details:
            print(f"   {detail}")
        print(f"\n   💰 [Risk Management]")
        print(f"   🛑 SL: {sl:.5f} (2ATR + 6pt = {sl_distance:.5f})")
        print(f"   🎯 TP: {tp:.5f} (2SL = {tp_distance:.5f})")
        print(f"   📊 Volume: {volume:.2f} lot")
        print(f"{'='*80}\n")
        
        # --- 11. Send Order ---
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal_type == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": current_price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        # Pre-order validation
        if not mt5.terminal_info():
            error_msg = "MT5 Terminal không kết nối"
            print(f"❌ {error_msg}")
            send_telegram(
                f"❌ <b>M1 Scalp Bot - Lỗi</b>\n{error_msg}",
                config.get('telegram_token'),
                config.get('telegram_chat_id')
            )
            return error_count + 1, 0
        
        if symbol_info.visible == False:
            error_msg = f"Symbol {symbol} không khả dụng"
            print(f"❌ {error_msg}")
            return error_count + 1, 0
        
        # Check stops_level
        stops_level = symbol_info.trade_stops_level
        if stops_level > 0:
            if signal_type == "BUY":
                if abs(current_price - sl) < stops_level * point:
                    error_msg = f"SL quá gần (cần >= {stops_level} points)"
                    print(f"❌ {error_msg}")
                    return error_count + 1, 0
            else:  # SELL
                if abs(sl - current_price) < stops_level * point:
                    error_msg = f"SL quá gần (cần >= {stops_level} points)"
                    print(f"❌ {error_msg}")
                    return error_count + 1, 0
        
        # Validate order
        check_result = mt5.order_check(request)
        if check_result.retcode != mt5.TRADE_RETCODE_DONE:
            error_msg = f"Order validation failed: {check_result.comment}"
            print(f"❌ {error_msg}")
            send_telegram(
                f"❌ <b>M1 Scalp Bot - Lỗi Gửi Lệnh</b>\n"
                f"💱 Symbol: {symbol} ({signal_type})\n"
                f"❌ Lỗi: {error_msg}",
                config.get('telegram_token'),
                config.get('telegram_chat_id')
            )
            return error_count + 1, 0
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(result.order, "M1_Scalp", symbol, signal_type, volume, current_price, sl, tp, reason, account_id=config.get('account'))
            
            # Detailed Telegram Message
            msg_parts = []
            msg_parts.append(f"✅ <b>M1 Scalp Bot - Lệnh Đã Được Thực Hiện</b>\n")
            msg_parts.append(f"{'='*50}\n")
            msg_parts.append(f"🆔 <b>Ticket:</b> {result.order}\n")
            msg_parts.append(f"💱 <b>Symbol:</b> {symbol} ({signal_type})\n")
            msg_parts.append(f"💵 <b>Entry Price:</b> {current_price:.5f}\n")
            msg_parts.append(f"🛑 <b>SL:</b> {sl:.5f} (2ATR + 6pt = {sl_distance:.5f})\n")
            msg_parts.append(f"🎯 <b>TP:</b> {tp:.5f} (2SL = {tp_distance:.5f})\n")
            msg_parts.append(f"📊 <b>Volume:</b> {volume:.2f} lot\n")
            msg_parts.append(f"\n")
            msg_parts.append(f"📈 <b>Điều Kiện Đã Thỏa:</b>\n")
            for detail in log_details:
                # Remove ✅ emoji for Telegram
                clean_detail = detail.replace("✅ ", "").replace("   ", "   • ")
                msg_parts.append(f"{clean_detail}\n")
            msg_parts.append(f"\n")
            msg_parts.append(f"📊 <b>Indicators:</b>\n")
            msg_parts.append(f"   • EMA50: {ema50_val:.5f}\n")
            msg_parts.append(f"   • EMA200: {ema200_val:.5f}\n")
            msg_parts.append(f"   • RSI: {current_rsi:.1f}\n")
            msg_parts.append(f"   • ATR: {atr_val:.5f}\n")
            msg_parts.append(f"   • Volume: {curr_candle['tick_volume']:.0f} (MA10: {vol_ma_val:.0f})\n")
            msg_parts.append(f"\n")
            msg_parts.append(f"{'='*50}\n")
            msg_parts.append(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            msg = "".join(msg_parts)
            send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
            return 0, 0
        else:
            error_msg = f"Order Failed: Retcode {result.retcode}"
            error_detail = f"{result.comment if hasattr(result, 'comment') else 'Unknown error'}"
            print(f"❌ {error_msg} - {error_detail}")
            send_telegram(
                f"❌ <b>M1 Scalp Bot - Lỗi Gửi Lệnh</b>\n"
                f"💱 Symbol: {symbol} ({signal_type})\n"
                f"💵 Price: {current_price:.5f}\n"
                f"🛑 SL: {sl:.5f} | 🎯 TP: {tp:.5f}\n"
                f"❌ Lỗi: {error_msg}\n"
                f"📝 Chi tiết: {error_detail}",
                config.get('telegram_token'),
                config.get('telegram_chat_id')
            )
            return error_count + 1, result.retcode
        
    except Exception as e:
        print(f"❌ Lỗi trong m1_scalp_logic: {e}")
        import traceback
        traceback.print_exc()
        return error_count + 1, 0

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_tuyen.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    if config and connect_mt5(config):
        print("\n" + "="*80)
        print(f"✅ M1 Scalp Bot - Started")
        print(f"💱 Symbol: {config.get('symbol', 'N/A')}")
        print(f"📊 Volume: {config.get('volume', 'N/A')}")
        print("="*80 + "\n")
        
        try:
            # Verify MT5 connection is still active
            if not mt5.terminal_info():
                print("❌ MT5 Terminal không còn kết nối sau khi khởi động")
                sys.exit(1)
            
            print("🔄 Bắt đầu vòng lặp chính...\n")
            
            loop_count = 0
            while True:
                try:
                    loop_count += 1
                    if loop_count % 60 == 0:  # Print every 60 iterations (~1 minute)
                        print(f"⏳ Bot đang chạy... (vòng lặp #{loop_count})")
                    
                    consecutive_errors, last_error = m1_scalp_logic(config, consecutive_errors)
                    if consecutive_errors >= 5:
                        print("⚠️ Too many errors. Pausing...")
                        time.sleep(120)
                        consecutive_errors = 0
                    time.sleep(1)
                except Exception as e:
                    print(f"❌ Lỗi trong m1_scalp_logic: {e}")
                    import traceback
                    traceback.print_exc()
                    consecutive_errors += 1
                    if consecutive_errors >= 5:
                        print("⚠️ Too many errors. Pausing...")
                        time.sleep(120)
                        consecutive_errors = 0
                    time.sleep(5)  # Wait longer on error
        except KeyboardInterrupt:
            print("\n\n⚠️ Bot stopped by user")
            mt5.shutdown()
        except Exception as e:
            print(f"\n❌ Lỗi nghiêm trọng trong bot: {e}")
            import traceback
            traceback.print_exc()
            mt5.shutdown()
            sys.exit(1)
    else:
        print("❌ Không thể kết nối MT5. Vui lòng kiểm tra lại.")
        sys.exit(1)

