import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd
import json
import os
from datetime import datetime, timedelta

# Import local modules
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, calculate_heiken_ashi, send_telegram, is_doji, manage_position, get_mt5_error_message, calculate_rsi, calculate_adx, calculate_atr

# Initialize Database
db = Database()

# ============================================================================
# STATE MACHINE - Lưu state trong memory (có thể persist vào file nếu cần)
# ============================================================================
STATE_FILE = "strategy_1_state.json"

def load_state(symbol):
    """Load state từ file hoặc trả về default"""
    state_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), STATE_FILE)
    if os.path.exists(state_file_path):
        try:
            with open(state_file_path, 'r') as f:
                data = json.load(f)
                return data.get(symbol, {"state": "WAIT", "breakout_candle_idx": None, "last_reset_time": None})
        except:
            pass
    return {"state": "WAIT", "breakout_candle_idx": None, "last_reset_time": None}

def save_state(symbol, state_data):
    """Save state vào file"""
    state_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), STATE_FILE)
    all_states = {}
    if os.path.exists(state_file_path):
        try:
            with open(state_file_path, 'r') as f:
                all_states = json.load(f)
        except:
            pass
    all_states[symbol] = state_data
    try:
        with open(state_file_path, 'w') as f:
            json.dump(all_states, f, indent=2)
    except:
        pass

def reset_state(symbol):
    """Reset state về WAIT"""
    state_data = {"state": "WAIT", "breakout_candle_idx": None, "last_reset_time": datetime.now().isoformat()}
    save_state(symbol, state_data)
    return state_data

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def check_chop_range(df_m1, atr_val, lookback=10, body_threshold=0.5, overlap_threshold=0.7):
    """CHOP / RANGE FILTER"""
    if len(df_m1) < lookback:
        return False, "Không đủ dữ liệu"
    
    recent_candles = df_m1.iloc[-lookback:]
    bodies = abs(recent_candles['close'] - recent_candles['open'])
    body_avg = bodies.mean()
    
    overlaps = 0
    total_pairs = 0
    for i in range(len(recent_candles) - 1):
        candle1 = recent_candles.iloc[i]
        candle2 = recent_candles.iloc[i + 1]
        range1 = (candle1['low'], candle1['high'])
        range2 = (candle2['low'], candle2['high'])
        overlap_low = max(range1[0], range2[0])
        overlap_high = min(range1[1], range2[1])
        if overlap_low < overlap_high:
            overlap_size = overlap_high - overlap_low
            range1_size = range1[1] - range1[0]
            range2_size = range2[1] - range2[0]
            avg_range = (range1_size + range2_size) / 2
            if avg_range > 0:
                overlap_ratio = overlap_size / avg_range
                overlaps += overlap_ratio
                total_pairs += 1
    
    avg_overlap = overlaps / total_pairs if total_pairs > 0 else 0
    body_condition = body_avg < (body_threshold * atr_val)
    overlap_condition = avg_overlap > overlap_threshold
    
    if body_condition and overlap_condition:
        return True, f"CHOP: body_avg={body_avg:.2f} < {body_threshold * atr_val:.2f}, overlap={avg_overlap:.1%} > {overlap_threshold:.1%}"
    return False, f"Not CHOP: body_avg={body_avg:.2f}, overlap={avg_overlap:.1%}"

def find_swing_points(df, lookback=5):
    """Find swing highs and lows"""
    swing_highs = []
    swing_lows = []
    
    for i in range(lookback, len(df) - lookback):
        is_swing_high = True
        for j in range(i - lookback, i + lookback + 1):
            if j != i and df.iloc[j]['high'] >= df.iloc[i]['high']:
                is_swing_high = False
                break
        if is_swing_high:
            swing_highs.append({'index': i, 'price': df.iloc[i]['high']})
        
        is_swing_low = True
        for j in range(i - lookback, i + lookback + 1):
            if j != i and df.iloc[j]['low'] <= df.iloc[i]['low']:
                is_swing_low = False
                break
        if is_swing_low:
            swing_lows.append({'index': i, 'price': df.iloc[i]['low']})
    
    return swing_highs, swing_lows

def get_last_swing_range(df_m1, signal_type, lookback=30):
    """Get last swing range for SL size limit"""
    swing_highs, swing_lows = find_swing_points(df_m1, lookback=5)
    
    if signal_type == "BUY":
        # Tìm swing low gần nhất
        if swing_lows:
            last_swing_low = swing_lows[-1]
            # Tìm swing high trước đó
            for swing_high in reversed(swing_highs):
                if swing_high['index'] < last_swing_low['index']:
                    return swing_high['price'] - last_swing_low['price']
    else:  # SELL
        # Tìm swing high gần nhất
        if swing_highs:
            last_swing_high = swing_highs[-1]
            # Tìm swing low trước đó
            for swing_low in reversed(swing_lows):
                if swing_low['index'] < last_swing_high['index']:
                    return last_swing_high['price'] - swing_low['price']
    
    return None

def check_asian_session(symbol, allow_xau=False):
    """
    Check if current time is Asian session
    Asian Session: 00:00 - 08:00 GMT
    Ngoại lệ: XAU có thể trade (tuỳ cấu hình)
    """
    try:
        import pytz
    except ImportError:
        return False, "pytz not available"
    
    now_utc = datetime.utcnow()
    london_tz = pytz.timezone('Europe/London')
    now_london = now_utc.replace(tzinfo=pytz.UTC).astimezone(london_tz)
    hour_london = now_london.hour
    
    is_asian = (0 <= hour_london < 8) or (21 <= hour_london < 24)
    
    if is_asian:
        if allow_xau and ('XAU' in symbol.upper() or 'GOLD' in symbol.upper()):
            return False, "Asian session but XAU allowed"
        return True, f"Asian session (GMT {hour_london:02d}:00)"
    
    return False, f"Not Asian session (GMT {hour_london:02d}:00)"

def calculate_ema_slope(df, ema_period=50, lookback=3):
    """Calculate EMA slope (absolute value)"""
    if len(df) < ema_period + lookback:
        return None
    
    df['ema'] = df['close'].ewm(span=ema_period, adjust=False).mean()
    if len(df) < 2:
        return None
    
    # Slope = (EMA[-1] - EMA[-lookback]) / lookback
    slope = (df['ema'].iloc[-1] - df['ema'].iloc[-lookback]) / lookback
    return abs(slope)

# ============================================================================
# HARD GATES (P0 - BẮT BUỘC)
# ============================================================================

def check_strong_trend_m5(df_m5, signal_type, config):
    """
    Hard Gate 2.1: Strong Trend M5
    BUY: EMA50 > EMA200, ADX >= 20, |slope(EMA50)| >= minSlope
    SELL: EMA50 < EMA200, ADX >= 20, |slope(EMA50)| >= minSlope
    """
    # Calculate EMAs
    df_m5['ema50'] = df_m5['close'].ewm(span=50, adjust=False).mean()
    df_m5['ema200'] = df_m5['close'].ewm(span=200, adjust=False).mean()
    
    last_m5 = df_m5.iloc[-1]
    
    # Check EMA relationship
    if signal_type == "BUY":
        ema_ok = last_m5['ema50'] > last_m5['ema200']
    else:  # SELL
        ema_ok = last_m5['ema50'] < last_m5['ema200']
    
    if not ema_ok:
        return False, "EMA50/EMA200 relationship not valid"
    
    # Check ADX
    adx_period = config['parameters'].get('adx_period', 14)
    adx_min_threshold = config['parameters'].get('adx_min_threshold', 20)
    df_m5 = calculate_adx(df_m5, period=adx_period)
    adx_value = df_m5.iloc[-1]['adx']
    
    if pd.isna(adx_value) or adx_value < adx_min_threshold:
        return False, f"ADX={adx_value:.1f} < {adx_min_threshold}"
    
    # Check EMA50 slope
    min_slope = config['parameters'].get('min_ema50_slope', 0.0001)  # Default threshold
    ema_slope = calculate_ema_slope(df_m5, ema_period=50, lookback=3)
    
    if ema_slope is None or ema_slope < min_slope:
        return False, f"EMA50 slope too flat: {ema_slope:.6f} < {min_slope:.6f}"
    
    return True, f"Strong trend: EMA OK, ADX={adx_value:.1f}, Slope={ema_slope:.6f}"

def check_fresh_breakout_candle(df_m1, signal_type, state_data):
    """
    Hard Gate 2.2: Fresh Breakout Candle (C0)
    - Phá high/low gần nhất (chưa bị test)
    - Body ≥ 60% range
    - Wick ngược ≤ 30%
    - Volume ≥ 1.3 × MA(volume, 20)
    """
    if len(df_m1) < 21:
        return False, None, "Not enough data"
    
    # Calculate volume MA
    df_m1['vol_ma'] = df_m1['tick_volume'].rolling(window=20).mean()
    
    # Get last completed candle (C0)
    c0 = df_m1.iloc[-2]  # Last completed candle
    
    # Find recent swing high/low (chưa bị test)
    swing_highs, swing_lows = find_swing_points(df_m1.iloc[:-2], lookback=5)  # Exclude current candle
    
    if signal_type == "BUY":
        if not swing_highs:
            return False, None, "No swing high found"
        
        recent_high = swing_highs[-1]['price']
        breakout_ok = c0['high'] > recent_high
        
        if not breakout_ok:
            return False, None, f"High {c0['high']:.5f} not > recent swing high {recent_high:.5f}"
    else:  # SELL
        if not swing_lows:
            return False, None, "No swing low found"
        
        recent_low = swing_lows[-1]['price']
        breakout_ok = c0['low'] < recent_low
        
        if not breakout_ok:
            return False, None, f"Low {c0['low']:.5f} not < recent swing low {recent_low:.5f}"
    
    # Check body >= 60% range
    candle_range = c0['high'] - c0['low']
    body_size = abs(c0['close'] - c0['open'])
    body_ratio = body_size / candle_range if candle_range > 0 else 0
    
    if body_ratio < 0.6:
        return False, None, f"Body ratio {body_ratio:.2%} < 60%"
    
    # Check wick ngược <= 30%
    if signal_type == "BUY":
        upper_wick = c0['high'] - max(c0['open'], c0['close'])
        wick_ratio = upper_wick / candle_range if candle_range > 0 else 0
    else:  # SELL
        lower_wick = min(c0['open'], c0['close']) - c0['low']
        wick_ratio = lower_wick / candle_range if candle_range > 0 else 0
    
    if wick_ratio > 0.3:
        return False, None, f"Reverse wick ratio {wick_ratio:.2%} > 30%"
    
    # Check volume >= 1.3 × MA(volume, 20)
    vol_ma = df_m1.iloc[-2]['vol_ma']
    if pd.isna(vol_ma) or vol_ma <= 0:
        return False, None, "Volume MA not available"
    
    if c0['tick_volume'] < 1.3 * vol_ma:
        return False, None, f"Volume {c0['tick_volume']:.0f} < 1.3 × MA({vol_ma:.0f})"
    
    # Valid breakout candle
    breakout_idx = len(df_m1) - 2
    return True, breakout_idx, "Fresh breakout candle valid"

def check_confirm_candle(df_m1, signal_type, breakout_idx):
    """
    Hard Gate 2.2: Confirm Candle (C1)
    - Không đóng lại trong range cũ
    - Không phá ngược breakout
    - Volume >= 1.2 × MA(volume, 20)
    """
    if len(df_m1) < breakout_idx + 2:
        return False, "Not enough candles after breakout"
    
    c0 = df_m1.iloc[breakout_idx]  # Breakout candle (C0)
    c1 = df_m1.iloc[-2]  # Last completed candle (C1) - not current running candle
    
    # Calculate volume MA
    df_m1['vol_ma'] = df_m1['tick_volume'].rolling(window=20).mean()
    vol_ma = df_m1.iloc[-2]['vol_ma']  # Use last completed candle's vol_ma
    
    if signal_type == "BUY":
        # Không đóng lại trong range cũ (dưới breakout high)
        if c1['close'] <= c0['high']:
            return False, f"Close {c1['close']:.5f} <= breakout high {c0['high']:.5f}"
        
        # Không phá ngược breakout (low không thấp hơn range cũ quá nhiều)
        old_range_low = df_m1.iloc[breakout_idx-10:breakout_idx]['low'].min() if breakout_idx >= 10 else c0['low']
        if c1['low'] < old_range_low * 0.999:  # 0.1% buffer
            return False, f"Low {c1['low']:.5f} breaks old range {old_range_low:.5f}"
    else:  # SELL
        # Không đóng lại trong range cũ (trên breakout low)
        if c1['close'] >= c0['low']:
            return False, f"Close {c1['close']:.5f} >= breakout low {c0['low']:.5f}"
        
        # Không phá ngược breakout
        old_range_high = df_m1.iloc[breakout_idx-10:breakout_idx]['high'].max() if breakout_idx >= 10 else c0['high']
        if c1['high'] > old_range_high * 1.001:  # 0.1% buffer
            return False, f"High {c1['high']:.5f} breaks old range {old_range_high:.5f}"
    
    # Check volume >= 1.2 × MA(volume, 20)
    if pd.isna(vol_ma) or vol_ma <= 0:
        return False, "Volume MA not available"
    
    if c1['tick_volume'] < 1.2 * vol_ma:
        return False, f"Volume {c1['tick_volume']:.0f} < 1.2 × MA({vol_ma:.0f})"
    
    return True, "Confirm candle valid"

def check_sl_size_limit(df_m1, entry_price, sl_price, atr_val, signal_type):
    """
    Hard Gate 2.3: Stop Loss Size Limit
    SL_distance <= min(1.2 × ATR(14), last_swing_range)
    """
    sl_distance = abs(entry_price - sl_price)
    
    # Calculate 1.2 × ATR
    atr_limit = 1.2 * atr_val
    
    # Get last swing range
    last_swing_range = get_last_swing_range(df_m1, signal_type, lookback=30)
    
    if last_swing_range is None:
        # Fallback: chỉ dùng ATR
        max_sl = atr_limit
        reason = f"1.2 × ATR = {atr_limit:.5f}"
    else:
        max_sl = min(atr_limit, last_swing_range)
        reason = f"min(1.2 × ATR={atr_limit:.5f}, swing_range={last_swing_range:.5f}) = {max_sl:.5f}"
    
    if sl_distance > max_sl:
        return False, f"SL distance {sl_distance:.5f} > limit {max_sl:.5f} ({reason})"
    
    return True, f"SL distance {sl_distance:.5f} <= limit {max_sl:.5f}"

# ============================================================================
# SOFT CONFIRM (Check sau Hard Gate)
# ============================================================================

def check_soft_confirm(df_m1, ha_df, signal_type, config):
    """
    Soft Confirm:
    - RSI: BUY > 55, SELL < 45, RSI slope đúng hướng
    - HA candle đúng màu
    - Không doji / indecision
    """
    last_ha = ha_df.iloc[-1]
    prev_ha = ha_df.iloc[-2] if len(ha_df) >= 2 else None
    
    # Check RSI
    rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 55)
    rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 45)
    
    current_rsi = last_ha.get('rsi', None)
    if pd.isna(current_rsi):
        return False, "RSI not available"
    
    if signal_type == "BUY":
        if current_rsi <= rsi_buy_threshold:
            return False, f"RSI {current_rsi:.1f} <= {rsi_buy_threshold}"
        # RSI slope đúng hướng (rising)
        if prev_ha is not None:
            prev_rsi = prev_ha.get('rsi', None)
            if pd.notna(prev_rsi) and current_rsi <= prev_rsi:
                return False, f"RSI not rising: {current_rsi:.1f} <= {prev_rsi:.1f}"
    else:  # SELL
        if current_rsi >= rsi_sell_threshold:
            return False, f"RSI {current_rsi:.1f} >= {rsi_sell_threshold}"
        # RSI slope đúng hướng (declining)
        if prev_ha is not None:
            prev_rsi = prev_ha.get('rsi', None)
            if pd.notna(prev_rsi) and current_rsi >= prev_rsi:
                return False, f"RSI not declining: {current_rsi:.1f} >= {prev_rsi:.1f}"
    
    # Check HA candle đúng màu
    if signal_type == "BUY":
        if last_ha['ha_close'] <= last_ha['ha_open']:
            return False, "HA candle not green"
    else:  # SELL
        if last_ha['ha_close'] >= last_ha['ha_open']:
            return False, "HA candle not red"
    
    # Check không doji
    if is_doji(last_ha, threshold=0.2):
        return False, "Doji candle detected"
    
    return True, "Soft confirm passed"

# ============================================================================
# CONSECUTIVE LOSS GUARD
# ============================================================================

def check_consecutive_losses(symbol, magic, config):
    """
    Check consecutive losses and apply cooldown
    loss_streak >= 2 → cooldown 30-60 phút
    """
    loss_streak_threshold = config['parameters'].get('loss_streak_threshold', 2)
    cooldown_minutes = config['parameters'].get('loss_cooldown_minutes', 45)  # Default 45 minutes
    
    try:
        # Get deals from last 24 hours
        from_timestamp = int((datetime.now() - timedelta(days=1)).timestamp())
        to_timestamp = int(datetime.now().timestamp())
        deals = mt5.history_deals_get(from_timestamp, to_timestamp)
        
        if deals is None or len(deals) == 0:
            return True, "No deals found"
        
        # Filter closed deals with this magic number
        closed_deals = []
        for deal in deals:
            if (deal.entry == mt5.DEAL_ENTRY_OUT and 
                deal.magic == magic and 
                deal.profit != 0):
                closed_deals.append(deal)
        
        if len(closed_deals) == 0:
            return True, "No closed deals"
        
        # Sort by time (newest first)
        closed_deals.sort(key=lambda x: x.time, reverse=True)
        
        # Count consecutive losses
        loss_streak = 0
        for deal in closed_deals:
            if deal.profit < 0:
                loss_streak += 1
            else:
                break  # Stop at first win
        
        if loss_streak >= loss_streak_threshold:
            # Check if we're still in cooldown
            if len(closed_deals) > 0:
                last_deal_time = closed_deals[0].time
                if isinstance(last_deal_time, datetime):
                    last_deal_timestamp = last_deal_time.timestamp()
                else:
                    last_deal_timestamp = last_deal_time
                
                current_timestamp = datetime.now().timestamp()
                minutes_since_last = (current_timestamp - last_deal_timestamp) / 60
                
                if minutes_since_last < cooldown_minutes:
                    remaining = cooldown_minutes - minutes_since_last
                    return False, f"Cooldown: {loss_streak} consecutive losses, {remaining:.1f} minutes remaining"
                else:
                    return True, f"Cooldown expired: {loss_streak} consecutive losses, {minutes_since_last:.1f} minutes passed"
        
        return True, f"Loss streak: {loss_streak} < {loss_streak_threshold}"
    except Exception as e:
        return True, f"Error checking losses: {e}"

# ============================================================================
# MAIN LOGIC
# ============================================================================

def strategy_1_logic_v21(config, error_count=0):
    """
    Strategy 1 Trend HA V2.1 - Hard Gate Implementation
    """
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    
    # Initialize logging structure
    log_data = {
        "state": "WAIT",
        "strong_trend": False,
        "fresh_breakout": False,
        "confirm_candle": False,
        "SL_distance": 0.0,
        "ATR": 0.0,
        "decision": "SKIP",
        "skip_reason": ""
    }
    
    # Manage existing positions (V2.1: Only manage trailing SL, no manual close)
    all_positions = mt5.positions_get(symbol=symbol)
    positions = [pos for pos in (all_positions or []) if pos.magic == magic]
    
    if positions:
        # V2.1: Only manage trailing SL/breakeven, do NOT allow manual/script close
        # Exit only via TP or SL (handled by MT5)
        for pos in positions:
            # Only manage trailing SL, not close positions
            manage_position(pos.ticket, symbol, magic, config)
        if len(positions) >= max_positions:
            return error_count, 0
    
    # Get data
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 300)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 300)
    
    if df_m1 is None or df_m5 is None:
        return error_count, 0
    
    # Calculate ATR
    atr_period = config['parameters'].get('atr_period', 14)
    df_m1['atr'] = calculate_atr(df_m1, period=atr_period)
    atr_val = df_m1.iloc[-1]['atr']
    if pd.isna(atr_val) or atr_val <= 0:
        recent_range = df_m1.iloc[-atr_period:]['high'].max() - df_m1.iloc[-atr_period:]['low'].min()
        atr_val = recent_range / atr_period if recent_range > 0 else 0.1
    
    log_data["ATR"] = float(atr_val)
    
    # Load state
    state_data = load_state(symbol)
    current_state = state_data.get("state", "WAIT")
    log_data["state"] = current_state
    
    # Determine signal type from M5 trend (preliminary check)
    df_m5['ema50'] = df_m5['close'].ewm(span=50, adjust=False).mean()
    df_m5['ema200'] = df_m5['close'].ewm(span=200, adjust=False).mean()
    preliminary_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"
    signal_type = "BUY" if preliminary_trend == "BULLISH" else "SELL"
    
    # ========================================================================
    # TRADE MANAGEMENT: Consecutive Loss Guard
    # ========================================================================
    loss_guard_ok, loss_guard_msg = check_consecutive_losses(symbol, magic, config)
    if not loss_guard_ok:
        log_data["skip_reason"] = f"loss_guard: {loss_guard_msg}"
        print(f"⏳ [TRADE MANAGEMENT] Consecutive Loss Guard: {loss_guard_msg}")
        print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
        return error_count, 0
    
    # ========================================================================
    # HARD GATE 1: Session Filter
    # ========================================================================
    allow_xau_asian = config['parameters'].get('allow_xau_asian', False)
    is_asian, session_msg = check_asian_session(symbol, allow_xau=allow_xau_asian)
    if is_asian:
        log_data["skip_reason"] = f"session: {session_msg}"
        print(f"❌ [HARD GATE] Session Filter: {session_msg}")
        print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
        return error_count, 0
    
    # ========================================================================
    # HARD GATE 2: Strong Trend M5
    # ========================================================================
    strong_trend_ok, trend_msg = check_strong_trend_m5(df_m5, signal_type, config)
    log_data["strong_trend"] = strong_trend_ok
    
    if not strong_trend_ok:
        log_data["skip_reason"] = f"trend: {trend_msg}"
        print(f"❌ [HARD GATE] Strong Trend M5: {trend_msg}")
        reset_state(symbol)  # Reset state nếu trend không đạt
        print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
        return error_count, 0
    
    print(f"✅ [HARD GATE] Strong Trend M5: {trend_msg}")
    
    # ========================================================================
    # STATE MACHINE: WAIT → CONFIRM → ENTRY
    # ========================================================================
    
    if current_state == "WAIT":
        # Check for fresh breakout candle (C0)
        breakout_ok, breakout_idx, breakout_msg = check_fresh_breakout_candle(df_m1, signal_type, state_data)
        log_data["fresh_breakout"] = breakout_ok
        
        if breakout_ok:
            # Transition to CONFIRM state
            state_data["state"] = "CONFIRM"
            state_data["breakout_candle_idx"] = breakout_idx
            save_state(symbol, state_data)
            log_data["state"] = "CONFIRM"
            print(f"✅ [STATE] WAIT → CONFIRM: {breakout_msg}")
            print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
            return error_count, 0
        else:
            log_data["skip_reason"] = f"breakout: {breakout_msg}"
            print(f"❌ [STATE WAIT] Fresh Breakout: {breakout_msg}")
            print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
            return error_count, 0
    
    elif current_state == "CONFIRM":
        breakout_idx = state_data.get("breakout_candle_idx")
        if breakout_idx is None:
            # Reset nếu không có breakout_idx
            reset_state(symbol)
            log_data["state"] = "WAIT"
            log_data["skip_reason"] = "state: missing breakout_idx, reset to WAIT"
            print(f"⚠️ [STATE CONFIRM] Missing breakout_idx, reset to WAIT")
            print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
            return error_count, 0
        
        # Check confirm candle (C1) - must be completed candle
        confirm_ok, confirm_msg = check_confirm_candle(df_m1, signal_type, breakout_idx)
        log_data["confirm_candle"] = confirm_ok
        
        if confirm_ok:
            # Transition to ENTRY state (will execute on next iteration)
            state_data["state"] = "ENTRY"
            save_state(symbol, state_data)
            log_data["state"] = "ENTRY"
            print(f"✅ [STATE] CONFIRM → ENTRY: {confirm_msg}")
            print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
            return error_count, 0  # Return here, entry will happen on next iteration
        else:
            # Reset nếu không có C1
            reset_state(symbol)
            log_data["state"] = "WAIT"
            log_data["skip_reason"] = f"confirm: {confirm_msg}"
            print(f"❌ [STATE CONFIRM] Confirm Candle: {confirm_msg} → RESET")
            print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
            return error_count, 0
    
    if current_state == "ENTRY":
        # Chỉ vào lệnh tại state ENTRY (sau khi đã pass WAIT và CONFIRM)
        # Calculate indicators for entry
        ha_df = calculate_heiken_ashi(df_m1)
        ha_df['rsi'] = calculate_rsi(df_m1['close'], period=14)
        
        # Get entry price (use last completed candle close for consistency)
        last_completed_candle = df_m1.iloc[-2]  # Last completed candle
        entry_price = last_completed_candle['close']
        
        # Get current market price for order execution
        tick = mt5.symbol_info_tick(symbol)
        execution_price = tick.ask if signal_type == "BUY" else tick.bid
        
        # Calculate SL/TP
        sl_mode = config['parameters'].get('sl_mode', 'auto_m5')
        reward_ratio = config['parameters'].get('reward_ratio', 1.5)
        
        if sl_mode == 'auto_m5':
            prev_m5_high = df_m5.iloc[-2]['high']
            prev_m5_low = df_m5.iloc[-2]['low']
            atr_buffer_multiplier = config['parameters'].get('atr_buffer_multiplier', 1.5)
            df_m5['atr'] = calculate_atr(df_m5, period=atr_period)
            atr_m5 = df_m5.iloc[-2]['atr']
            if pd.isna(atr_m5) or atr_m5 <= 0:
                m5_range = prev_m5_high - prev_m5_low
                atr_m5 = m5_range / atr_period if m5_range > 0 else 0.1
            buffer = atr_buffer_multiplier * atr_m5
            
            if signal_type == "BUY":
                sl = prev_m5_low - buffer
                min_dist = 100 * mt5.symbol_info(symbol).point
                if (entry_price - sl) < min_dist:
                    sl = entry_price - min_dist
                risk_dist = entry_price - sl
                tp = entry_price + (risk_dist * reward_ratio)
            else:  # SELL
                sl = prev_m5_high + buffer
                min_dist = 100 * mt5.symbol_info(symbol).point
                if (sl - entry_price) < min_dist:
                    sl = entry_price + min_dist
                risk_dist = sl - entry_price
                tp = entry_price - (risk_dist * reward_ratio)
        else:
            sl_pips = config['parameters']['sl_pips'] * mt5.symbol_info(symbol).point * 10
            tp_pips = config['parameters']['tp_pips'] * mt5.symbol_info(symbol).point * 10
            sl = entry_price - sl_pips if signal_type == "BUY" else entry_price + sl_pips
            tp = entry_price + tp_pips if signal_type == "BUY" else entry_price - tp_pips
        
        sl_distance = abs(entry_price - sl)
        log_data["SL_distance"] = float(sl_distance)
        
        # ====================================================================
        # HARD GATE 3: SL Size Limit
        # ====================================================================
        sl_limit_ok, sl_limit_msg = check_sl_size_limit(df_m1, entry_price, sl, atr_val, signal_type)
        if not sl_limit_ok:
            reset_state(symbol)
            log_data["state"] = "WAIT"
            log_data["skip_reason"] = f"SL: {sl_limit_msg}"
            print(f"❌ [HARD GATE] SL Size Limit: {sl_limit_msg}")
            print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
            return error_count, 0
        
        print(f"✅ [HARD GATE] SL Size Limit: {sl_limit_msg}")
        
        # ====================================================================
        # SOFT CONFIRM
        # ====================================================================
        soft_ok, soft_msg = check_soft_confirm(df_m1, ha_df, signal_type, config)
        if not soft_ok:
            log_data["decision"] = "SKIP"
            log_data["skip_reason"] = f"soft: {soft_msg}"
            print(f"⚠️ [SOFT CONFIRM] {soft_msg} → SKIP ENTRY (không invalidate setup)")
            # Không reset state, chỉ skip entry
            print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
            return error_count, 0
        
        print(f"✅ [SOFT CONFIRM] {soft_msg}")
        
        # ====================================================================
        # ENTRY EXECUTION
        # ====================================================================
        # Spam filter
        spam_filter_seconds = config['parameters'].get('spam_filter_seconds', 300)
        all_strat_positions = mt5.positions_get(symbol=symbol)
        strat_positions = [pos for pos in (all_strat_positions or []) if pos.magic == magic]
        if strat_positions:
            strat_positions = sorted(strat_positions, key=lambda x: x.time, reverse=True)
            last_trade_time = strat_positions[0].time
            current_server_time = mt5.symbol_info_tick(symbol).time
            
            if isinstance(last_trade_time, datetime):
                last_trade_timestamp = last_trade_time.timestamp()
            else:
                last_trade_timestamp = last_trade_time
            if isinstance(current_server_time, datetime):
                current_timestamp = current_server_time.timestamp()
            else:
                current_timestamp = current_server_time
            
            time_since_last = current_timestamp - last_trade_timestamp
            if time_since_last < spam_filter_seconds:
                log_data["skip_reason"] = f"spam: {time_since_last:.0f}s < {spam_filter_seconds}s"
                print(f"⏳ [SPAM FILTER] Trade taken {time_since_last:.0f}s ago")
                print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
                return error_count, 0
        
        # Normalize prices
        symbol_info = mt5.symbol_info(symbol)
        digits = symbol_info.digits
        entry_price = round(entry_price, digits)
        sl = round(sl, digits)
        tp = round(tp, digits)
        
        # Send order (use execution_price for actual order, entry_price for logging)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal_type == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": execution_price,  # Use current market price for execution
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": "Strat1_HA_V2.1",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(result.order, "Strategy_1_Trend_HA_V2.1", symbol, signal_type, volume, execution_price, sl, tp, result.comment, account_id=config['account'])
            
            # Reset state after successful entry
            reset_state(symbol)
            log_data["decision"] = "ENTER"
            log_data["skip_reason"] = ""
            log_data["state"] = "WAIT"  # Reset to WAIT after entry
            print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
            
            # Telegram notification
            msg = (
                f"✅ <b>Strat 1: Trend HA V2.1 Executed</b>\n"
                f"🆔 <b>Ticket:</b> {result.order}\n"
                f"💱 <b>Symbol:</b> {symbol} ({signal_type})\n"
                f"💵 <b>Entry:</b> {execution_price:.2f} (Close of breakout candle: {entry_price:.2f})\n"
                f"🛑 <b>SL:</b> {sl:.2f} | 🎯 <b>TP:</b> {tp:.2f}\n"
                f"📊 <b>V2.1 Hard Gates:</b>\n"
                f"• Strong Trend: ✅\n"
                f"• Fresh Breakout: ✅\n"
                f"• Confirm Candle: ✅\n"
                f"• SL Size Limit: ✅\n"
                f"• Soft Confirm: ✅\n"
                f"📊 <b>State Machine:</b> WAIT → CONFIRM → ENTRY ✅"
            )
            send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
            return 0, 0
        else:
            log_data["skip_reason"] = f"order_failed: {result.retcode}"
            print(f"❌ Order Failed: {result.retcode}")
            print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
            return error_count + 1, result.retcode
    elif current_state not in ["WAIT", "CONFIRM", "ENTRY"]:
        # Invalid state, reset
        reset_state(symbol)
        log_data["state"] = "WAIT"
        log_data["skip_reason"] = f"invalid_state: {current_state}"
        print(f"⚠️ [STATE] Invalid state {current_state}, reset to WAIT")
        print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
        return error_count, 0
    
    # Default: log và return (for WAIT and CONFIRM states that didn't transition)
    print(f"📊 [LOG] {json.dumps(log_data, indent=2)}")
    return error_count, 0

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_1_v2.1.json")
    config = load_config(config_path)
    
    consecutive_errors = 0
    
    if config and connect_mt5(config):
        print("✅ Strategy 1: Trend HA V2.1 - Started")
        print("📋 V2.1 Improvements:")
        print("   ✅ Hard Gates: Strong Trend, Fresh Breakout, Confirm Candle, SL Limit")
        print("   ✅ State Machine: WAIT → CONFIRM → ENTRY")
        print("   ✅ Session Filter: Asian Session → NO TRADE")
        print("   ✅ Soft Confirm: RSI, HA candle, Doji check")
        print("   ✅ JSON Logging: Detailed entry attempt logs")
        try:
            while True:
                consecutive_errors, last_error_code = strategy_1_logic_v21(config, consecutive_errors)
                
                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Strategy 1: Trend HA V2.1] WARNING: 5 Consecutive Order Failures. Last Error: {error_msg}. Pausing for 2 minutes..."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    time.sleep(120)
                    consecutive_errors = 0
                    print("▶️ Resuming...")
                    continue
                    
                time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 Bot Stopped")
            mt5.shutdown()

