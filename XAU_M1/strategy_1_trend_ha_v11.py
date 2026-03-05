"""
Strategy 1 Trend HA - Version 1.1
Clone of strategy_1_trend_ha with:
- Chỉ trade khung giờ (giờ server): Sáng 02:00-06:00, Chiều/Tối 13:00-20:00
- BUY khi 52 < RSI < 68; SELL khi 32 < RSI < 48
"""
import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# Import local modules
import os
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
from db import Database
from utils import load_config, connect_mt5, get_data, calculate_heiken_ashi, send_telegram, is_doji, manage_position, get_mt5_error_message, calculate_rsi, calculate_adx

# Initialize Database
db = Database()

STRATEGY_NAME = "Strategy_1_Trend_HA_V11"
COMMENT = "Strat1_HA_V11"

def check_trading_session(config):
    """
    Chỉ cho phép trade trong khung giờ (giờ server):
    - Sáng: 02:00 - 06:00
    - Chiều/Tối: 13:00 - 20:00
    """
    symbol = config['symbol']
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return True, "No tick (skip session check)"
        t = tick.time
        if isinstance(t, (int, float)):
            current_dt = datetime.fromtimestamp(t)
        else:
            current_dt = t
        current_time = current_dt.time()

        # Sáng: 02:00 - 06:00
        morning_start = datetime.strptime("02:00", "%H:%M").time()
        morning_end = datetime.strptime("06:00", "%H:%M").time()
        # Chiều/Tối: 13:00 - 20:00
        afternoon_start = datetime.strptime("13:00", "%H:%M").time()
        afternoon_end = datetime.strptime("20:00", "%H:%M").time()

        in_morning = morning_start <= current_time < morning_end
        in_afternoon = afternoon_start <= current_time < afternoon_end
        if in_morning:
            return True, "Session: Sáng (02:00-06:00)"
        if in_afternoon:
            return True, "Session: Chiều/Tối (13:00-20:00)"
        return False, f"Ngoài khung giờ (Server: {current_time.strftime('%H:%M')}, cần 02:00-06:00 hoặc 13:00-20:00)"
    except Exception as e:
        print(f"⚠️ Session check error: {e}")
        return True, "Session check skipped (error)"

def strategy_1_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)

    # 0. Check trading session (V1.1: chỉ trade 02:00-06:00 và 13:00-20:00 server)
    in_session, session_msg = check_trading_session(config)
    if not in_session:
        return error_count, 0

    # 2. Check Global Max Positions & Manage Existing
    all_positions = mt5.positions_get(symbol=symbol)
    positions = [pos for pos in (all_positions or []) if pos.magic == magic]
    if positions:
        for pos in positions:
            manage_position(pos.ticket, symbol, magic, config)
        if len(positions) >= max_positions:
            return error_count, 0

    # 1. Get Data
    df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 200)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 200)
    df_h1 = get_data(symbol, mt5.TIMEFRAME_H1, 200)

    if df_m1 is None or df_m5 is None or df_h1 is None:
        return error_count, 0

    # 2. Calculate Indicators
    df_m5['ema200'] = df_m5['close'].rolling(window=200).mean()
    current_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"

    h1_ema_period = config['parameters'].get('h1_ema_period', 100)
    h1_trend_confirmation_required = config['parameters'].get('h1_trend_confirmation_required', True)
    df_h1['ema100'] = df_h1['close'].rolling(window=h1_ema_period).mean()
    h1_trend = "BULLISH" if df_h1.iloc[-1]['close'] > df_h1.iloc[-1]['ema100'] else "BEARISH"

    if h1_trend_confirmation_required:
        if h1_trend != current_trend:
            print(f"❌ H1 Trend Filter: H1 ({h1_trend}) != M5 ({current_trend}), skipping")
            return error_count, 0
        print(f"✅ H1 Trend Filter: {h1_trend} == M5 | {session_msg}")
    else:
        print(f"⏭️  H1 Trend: {h1_trend}, M5: {current_trend} | {session_msg}")

    adx_period = config['parameters'].get('adx_period', 14)
    adx_min_threshold = config['parameters'].get('adx_min_threshold', 20)
    df_m5 = calculate_adx(df_m5, period=adx_period)
    adx_value = df_m5.iloc[-1]['adx']
    if pd.isna(adx_value) or adx_value < adx_min_threshold:
        print(f"❌ ADX Filter: ADX={adx_value:.1f} < {adx_min_threshold}")
        return error_count, 0
    print(f"✅ ADX: {adx_value:.1f} >= {adx_min_threshold}")

    df_m1['sma55_high'] = df_m1['high'].rolling(window=55).mean()
    df_m1['sma55_low'] = df_m1['low'].rolling(window=55).mean()
    ha_df = calculate_heiken_ashi(df_m1)
    ha_df['rsi'] = calculate_rsi(df_m1['close'], period=14)

    last_ha = ha_df.iloc[-1]
    prev_ha = ha_df.iloc[-2]

    signal = None
    price = mt5.symbol_info_tick(symbol).ask if current_trend == "BULLISH" else mt5.symbol_info_tick(symbol).bid

    # V1.1 RSI ranges: BUY 52 < RSI < 68, SELL 32 < RSI < 48
    rsi_buy_min = config['parameters'].get('rsi_buy_min', 52)
    rsi_buy_max = config['parameters'].get('rsi_buy_max', 68)
    rsi_sell_min = config['parameters'].get('rsi_sell_min', 32)
    rsi_sell_max = config['parameters'].get('rsi_sell_max', 48)

    print(f"\n{'='*80}")
    print(f"📊 [STRATEGY 1 TREND HA V1.1] {symbol} | {session_msg}")
    print(f"{'='*80}")
    print(f"💱 Price: {price:.2f} | Trend M5: {current_trend} | H1: {h1_trend} | ADX: {adx_value:.1f} | RSI: {last_ha['rsi']:.1f}")
    print(f"   RSI V1.1: BUY {rsi_buy_min}-{rsi_buy_max}, SELL {rsi_sell_min}-{rsi_sell_max}")

    filter_status = []

    # BUY SETUP
    if current_trend == "BULLISH":
        is_green = last_ha['ha_close'] > last_ha['ha_open']
        is_above_channel = last_ha['ha_close'] > last_ha['sma55_high']
        is_fresh_breakout = prev_ha['ha_close'] <= prev_ha['sma55_high']
        is_solid_candle = not is_doji(last_ha, threshold=0.2)
        current_rsi = last_ha['rsi']
        rsi_ok_buy = rsi_buy_min < current_rsi < rsi_buy_max

        filter_status.append(f"✅ M5 Trend: BULLISH")
        filter_status.append(f"{'✅' if is_green else '❌'} HA Green")
        filter_status.append(f"{'✅' if is_above_channel else '❌'} Above Channel")
        filter_status.append(f"{'✅' if is_fresh_breakout else '❌'} Fresh Breakout")
        filter_status.append(f"{'✅' if is_solid_candle else '❌'} Solid Candle")
        filter_status.append(f"{'✅' if rsi_ok_buy else '❌'} RSI {current_rsi:.1f} trong ({rsi_buy_min}, {rsi_buy_max})")

        if is_green and is_above_channel and is_fresh_breakout and is_solid_candle and rsi_ok_buy:
            signal = "BUY"
            print(f"\n✅ [SIGNAL] BUY - RSI {current_rsi:.1f} trong ({rsi_buy_min}, {rsi_buy_max})")
        elif is_green and is_above_channel and is_fresh_breakout and is_solid_candle and not rsi_ok_buy:
            print(f"\n❌ [NO SIGNAL] BUY - RSI {current_rsi:.1f} không trong ({rsi_buy_min}, {rsi_buy_max})")
        else:
            print(f"\n❌ [NO SIGNAL] BUY - Điều kiện HA/channel chưa đạt")

    # SELL SETUP
    elif current_trend == "BEARISH":
        is_red = last_ha['ha_close'] < last_ha['ha_open']
        is_below_channel = last_ha['ha_close'] < last_ha['sma55_low']
        is_fresh_breakout = prev_ha['ha_close'] >= prev_ha['sma55_low']
        is_solid_candle = not is_doji(last_ha, threshold=0.2)
        current_rsi = last_ha['rsi']
        rsi_ok_sell = rsi_sell_min < current_rsi < rsi_sell_max

        filter_status.append(f"✅ M5 Trend: BEARISH")
        filter_status.append(f"{'✅' if is_red else '❌'} HA Red")
        filter_status.append(f"{'✅' if is_below_channel else '❌'} Below Channel")
        filter_status.append(f"{'✅' if is_fresh_breakout else '❌'} Fresh Breakout")
        filter_status.append(f"{'✅' if is_solid_candle else '❌'} Solid Candle")
        filter_status.append(f"{'✅' if rsi_ok_sell else '❌'} RSI {current_rsi:.1f} trong ({rsi_sell_min}, {rsi_sell_max})")

        if is_red and is_below_channel and is_fresh_breakout and is_solid_candle and rsi_ok_sell:
            signal = "SELL"
            print(f"\n✅ [SIGNAL] SELL - RSI {current_rsi:.1f} trong ({rsi_sell_min}, {rsi_sell_max})")
        elif is_red and is_below_channel and is_fresh_breakout and is_solid_candle and not rsi_ok_sell:
            print(f"\n❌ [NO SIGNAL] SELL - RSI {current_rsi:.1f} không trong ({rsi_sell_min}, {rsi_sell_max})")
        else:
            print(f"\n❌ [NO SIGNAL] SELL - Điều kiện HA/channel chưa đạt")

    if not signal:
        print(f"\n{'─'*80}")
        for i, s in enumerate(filter_status, 1):
            print(f"   {i}. {s}")
        print(f"   RSI: {last_ha['rsi']:.1f} | BUY cần ({rsi_buy_min}, {rsi_buy_max}), SELL cần ({rsi_sell_min}, {rsi_sell_max})")
        print(f"{'─'*80}\n")

    # 4. Execute Trade
    if signal:
        spam_filter_seconds = config['parameters'].get('spam_filter_seconds', 180)
        strat_positions = mt5.positions_get(symbol=symbol, magic=magic)
        if strat_positions:
            strat_positions = sorted(strat_positions, key=lambda x: x.time, reverse=True)
            last_trade_time = strat_positions[0].time
            current_server_time = mt5.symbol_info_tick(symbol).time
            last_ts = last_trade_time.timestamp() if isinstance(last_trade_time, datetime) else last_trade_time
            current_ts = current_server_time.timestamp() if isinstance(current_server_time, datetime) else current_server_time
            time_since_last = current_ts - last_ts
            if time_since_last < spam_filter_seconds:
                print(f"   ⏳ Skipping: trade {time_since_last:.0f}s ago (wait {spam_filter_seconds}s)")
                return error_count, 0

        print(f"🚀 SIGNAL: {signal} @ {price}")

        sl_mode = config['parameters'].get('sl_mode', 'fixed')
        reward_ratio = config['parameters'].get('reward_ratio', 1.5)
        sl = 0.0
        tp = 0.0

        if sl_mode == 'auto_m5':
            prev_m5_high = df_m5.iloc[-2]['high']
            prev_m5_low = df_m5.iloc[-2]['low']
            buffer = 20 * mt5.symbol_info(symbol).point
            point = mt5.symbol_info(symbol).point
            min_dist = 100 * point
            if signal == "BUY":
                sl = prev_m5_low - buffer
                if (price - sl) < min_dist:
                    sl = price - min_dist
                risk_dist = price - sl
                tp = price + (risk_dist * reward_ratio)
            else:
                sl = prev_m5_high + buffer
                if (sl - price) < min_dist:
                    sl = price + min_dist
                risk_dist = sl - price
                tp = price - (risk_dist * reward_ratio)
            print(f"   📏 Auto M5 SL: {sl:.2f} | TP: {tp:.2f} (R:R {reward_ratio})")
        else:
            sl_pips = config['parameters']['sl_pips'] * mt5.symbol_info(symbol).point * 10
            tp_pips = config['parameters']['tp_pips'] * mt5.symbol_info(symbol).point * 10
            sl = price - sl_pips if signal == "BUY" else price + sl_pips
            tp = price + tp_pips if signal == "BUY" else price - tp_pips

        db.log_signal(STRATEGY_NAME, symbol, signal, price, sl, tp,
                      {"m5_trend": current_trend, "h1_trend": h1_trend, "ha_close": float(last_ha['ha_close']), "sl_mode": sl_mode, "rsi": float(last_ha['rsi'])},
                      account_id=config['account'])

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": COMMENT,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order: {result.order}")
            db.log_order(result.order, STRATEGY_NAME, symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
            msg = (
                f"✅ <b>Strat 1 Trend HA V1.1</b>\n"
                f"🆔 Ticket: {result.order} | 💱 {symbol} {signal}\n"
                f"💵 Price: {price:.2f} | SL: {sl:.2f} | TP: {tp:.2f}\n"
                f"📊 RSI: {last_ha['rsi']:.1f} | {session_msg}"
            )
            send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
            return 0, 0
        else:
            print(f"❌ Order Failed: {result.retcode}")
            return error_count + 1, result.retcode

    return error_count, 0

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_1_v11.json")
    config = load_config(config_path)
    consecutive_errors = 0

    if config and connect_mt5(config):
        print("✅ Strategy 1 Trend HA V1.1 - Started")
        print("   Session: 02:00-06:00 & 13:00-20:00 (server) | RSI BUY (52,68) SELL (32,48)")
        try:
            while True:
                consecutive_errors, last_error_code = strategy_1_logic(config, consecutive_errors)
                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Strategy 1 Trend HA V1.1] 5 failures. Last: {error_msg}. Pausing 2 min..."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    time.sleep(120)
                    consecutive_errors = 0
                    continue
                time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 Bot Stopped")
            mt5.shutdown()
