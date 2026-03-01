"""
Strategy 5 Filter First V2 — Clone từ XAU_M1/strategy_5_filter_first.py,
áp dụng các cập nhật từ strategy5.md:
- trade_direction (BUY_ONLY/SELL_ONLY/BOTH)
- max_risk_price (risk cap)
- atr_min_pips, atr_max_pips từ config
- Cooldown dùng datetime
- Spread filter
- Daily loss limit
- loss_streak_lookback_days
- Body >= 0.6*ATR (optional)
"""
import MetaTrader5 as mt5
import time
import sys
import numpy as np
import pandas as pd

# Import local modules (chạy từ thư mục XAU_M1_V2)
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, get_data, send_telegram, manage_position, get_mt5_error_message, calculate_rsi, calculate_adx
from datetime import datetime, timedelta

db = Database()
STRATEGY_NAME = "Strategy_5_Filter_First_V2"

def strategy_5_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    max_positions = config.get('max_positions', 1)
    trade_direction = config['parameters'].get('trade_direction', 'BUY_ONLY')

    positions = mt5.positions_get(symbol=symbol, magic=magic)
    if positions:
        for pos in positions:
            manage_position(pos.ticket, symbol, magic, config)
        if len(positions) >= max_positions:
            return error_count, 0

    df = get_data(symbol, mt5.TIMEFRAME_M1, 100)
    df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 200)
    if df is None or df_m5 is None:
        return error_count, 0

    df_m5['ema200'] = df_m5['close'].ewm(span=200, adjust=False).mean()
    df_m5 = calculate_adx(df_m5, period=14)
    m5_trend = "BULLISH" if df_m5.iloc[-1]['close'] > df_m5.iloc[-1]['ema200'] else "BEARISH"
    m5_adx = df_m5.iloc[-1].get('adx', 0)
    m5_adx_threshold = config['parameters'].get('m5_adx_threshold', 20)

    donchian_period = config['parameters'].get('donchian_period', 50)
    df['upper'] = df['high'].rolling(window=donchian_period).max().shift(1)
    df['lower'] = df['low'].rolling(window=donchian_period).min().shift(1)

    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(window=14).mean()
    df = calculate_adx(df, period=14)
    df['rsi'] = calculate_rsi(df['close'], period=14)
    df['vol_ma'] = df['tick_volume'].rolling(window=20).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3] if len(df) >= 3 else None

    signal = None
    buffer_multiplier = config['parameters'].get('buffer_multiplier', 100)
    buffer = buffer_multiplier * mt5.symbol_info(symbol).point
    breakout_confirmation = config['parameters'].get('breakout_confirmation', True)

    atr_value = last['atr'] if not pd.isna(last['atr']) else 0
    point = mt5.symbol_info(symbol).point
    atr_pips = (atr_value / point) / 10 if point > 0 else 0
    # V2: ATR từ config
    atr_min = config['parameters'].get('atr_min_pips', 10)
    atr_max = config['parameters'].get('atr_max_pips', 175)

    print(f"\n{'='*80}")
    print(f"📊 [STRATEGY 5 FILTER FIRST V2] {symbol} | trade_direction={trade_direction}")
    print(f"{'='*80}")
    print(f"💱 Price: {last['close']:.2f} | M5 Trend: {m5_trend} | RSI: {last['rsi']:.1f} | ADX: {last.get('adx', 0):.1f} | ATR: {atr_pips:.1f}p")
    print(f"   Donchian Upper: {last['upper']:.2f} | Lower: {last['lower']:.2f} | Buffer: {buffer/point:.0f} pts")

    filter_status = []

    if atr_pips < atr_min or atr_pips > atr_max:
        filter_status.append(f"❌ ATR: {atr_pips:.1f}p không trong khoảng {atr_min}-{atr_max}p")
        print(f"\n{'='*80}\n❌ [KHÔNG CÓ TÍN HIỆU] - ATR\n{'='*80}\n")
        return error_count, 0
    filter_status.append(f"✅ ATR: {atr_pips:.1f}p trong khoảng {atr_min}-{atr_max}p")

    adx_value = last.get('adx', 0)
    adx_threshold = config['parameters'].get('adx_threshold', 20)
    if pd.isna(adx_value) or adx_value < adx_threshold:
        filter_status.append(f"❌ M1 ADX: {adx_value:.1f} < {adx_threshold}")
        print(f"\n{'='*80}\n❌ [KHÔNG CÓ TÍN HIỆU] - ADX\n{'='*80}\n")
        return error_count, 0
    filter_status.append(f"✅ M1 ADX: {adx_value:.1f} >= {adx_threshold}")

    volume_threshold = config['parameters'].get('volume_threshold', 1.5)
    is_high_volume = last['tick_volume'] > (last['vol_ma'] * volume_threshold)
    vol_ratio = last['tick_volume'] / last['vol_ma'] if last['vol_ma'] > 0 else 0

    # XAU_M1: RSI threshold (BUY > threshold, SELL < threshold)
    rsi_buy_threshold = config['parameters'].get('rsi_buy_threshold', 55)
    rsi_sell_threshold = config['parameters'].get('rsi_sell_threshold', 45)
    body_min_atr_ratio = config['parameters'].get('body_min_atr_ratio', 0.6)
    body_size = abs(last['close'] - last['open'])
    body_ok = body_size >= (body_min_atr_ratio * atr_value) if atr_value > 0 else True

    # False Breakout
    false_breakout = False
    if last['close'] > (last['upper'] + buffer):
        if prev['high'] > last['upper'] and prev['close'] < last['upper']:
            false_breakout = True
            filter_status.append(f"❌ False Breakout BUY")
    elif last['close'] < (last['lower'] - buffer):
        if prev['low'] < last['lower'] and prev['close'] > last['lower']:
            false_breakout = True
            filter_status.append(f"❌ False Breakout SELL")
    if false_breakout:
        print(f"\n{'='*80}\n❌ [KHÔNG CÓ TÍN HIỆU] - False Breakout\n{'='*80}\n")
        return error_count, 0

    # BUY Signal (V2: trade_direction)
    has_breakout_buy = last['close'] > (last['upper'] + buffer)
    breakout_confirmed_buy = False
    if has_breakout_buy and trade_direction != 'SELL_ONLY':
        filter_status.append(f"✅ Breakout BUY: Price {last['close']:.2f} > Upper + Buffer")
        if not body_ok:
            filter_status.append(f"❌ Body BUY: {body_size:.4f} < {body_min_atr_ratio}*ATR")
        if breakout_confirmation:
            prev_upper = df.iloc[-2]['upper'] if len(df) >= 2 and pd.notna(df.iloc[-2].get('upper')) else last['upper']
            if prev is not None and prev['close'] > (prev_upper + buffer):
                breakout_confirmed_buy = True
                filter_status.append(f"✅ Breakout Confirmed")
            else:
                if last['close'] > last['upper'] + buffer * 1.5:
                    breakout_confirmed_buy = True
                    filter_status.append(f"✅ Strong Breakout")
                else:
                    filter_status.append(f"⏳ Breakout Not Confirmed")
        else:
            breakout_confirmed_buy = True

        if breakout_confirmed_buy and body_ok:
            if m5_trend == "BULLISH":
                filter_status.append(f"✅ M5 Trend: BULLISH")
                if pd.notna(m5_adx) and m5_adx >= m5_adx_threshold:
                    filter_status.append(f"✅ M5 ADX: {m5_adx:.1f} >= {m5_adx_threshold}")
                else:
                    filter_status.append(f"❌ M5 ADX: {m5_adx:.1f} < {m5_adx_threshold}")
                    has_breakout_buy = False
                if has_breakout_buy:
                    filter_status.append(f"{'✅' if last['rsi'] > rsi_buy_threshold else '❌'} RSI > {rsi_buy_threshold}: {last['rsi']:.1f}")
                    if last['rsi'] > rsi_buy_threshold:
                        filter_status.append(f"{'✅' if is_high_volume else '❌'} Volume: {vol_ratio:.2f}x")
                        if is_high_volume:
                            signal = "BUY"
                            print("\n✅ [SIGNAL FOUND] BUY - Tất cả điều kiện đạt!")
                        else:
                            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Volume không đủ")
                    else:
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần > {rsi_buy_threshold})")
            else:
                filter_status.append(f"❌ M5 Trend: BEARISH (cần BULLISH)")
                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - M5 Trend không phù hợp")
        elif has_breakout_buy and not body_ok:
            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Body nến BUY không đủ lớn (>= {body_min_atr_ratio}*ATR)")

    # SELL Signal (V2: trade_direction)
    has_breakout_sell = last['close'] < (last['lower'] - buffer)
    breakout_confirmed_sell = False
    if has_breakout_sell and trade_direction != 'BUY_ONLY':
        filter_status.append(f"✅ Breakout SELL: Price {last['close']:.2f} < Lower - Buffer")
        if not body_ok:
            filter_status.append(f"❌ Body SELL: {body_size:.4f} < {body_min_atr_ratio}*ATR")
        if breakout_confirmation:
            prev_lower = df.iloc[-2]['lower'] if len(df) >= 2 and pd.notna(df.iloc[-2].get('lower')) else last['lower']
            if prev is not None and prev['close'] < (prev_lower - buffer):
                breakout_confirmed_sell = True
                filter_status.append(f"✅ Breakout Confirmed")
            else:
                if last['close'] < last['lower'] - buffer * 1.5:
                    breakout_confirmed_sell = True
                    filter_status.append(f"✅ Strong Breakout")
                else:
                    filter_status.append(f"⏳ Breakout Not Confirmed")
        else:
            breakout_confirmed_sell = True

        if breakout_confirmed_sell and body_ok:
            if m5_trend == "BEARISH":
                filter_status.append(f"✅ M5 Trend: BEARISH")
                if pd.notna(m5_adx) and m5_adx >= m5_adx_threshold:
                    filter_status.append(f"✅ M5 ADX: {m5_adx:.1f} >= {m5_adx_threshold}")
                else:
                    filter_status.append(f"❌ M5 ADX: {m5_adx:.1f} < {m5_adx_threshold}")
                    has_breakout_sell = False
                if has_breakout_sell:
                    filter_status.append(f"{'✅' if last['rsi'] < rsi_sell_threshold else '❌'} RSI < {rsi_sell_threshold}: {last['rsi']:.1f}")
                    if last['rsi'] < rsi_sell_threshold:
                        filter_status.append(f"{'✅' if is_high_volume else '❌'} Volume: {vol_ratio:.2f}x")
                        if is_high_volume:
                            signal = "SELL"
                            print("\n✅ [SIGNAL FOUND] SELL - Tất cả điều kiện đạt!")
                        else:
                            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Volume không đủ")
                    else:
                        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - RSI không đạt (cần < {rsi_sell_threshold})")
            else:
                filter_status.append(f"❌ M5 Trend: BULLISH (cần BEARISH)")
                print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - M5 Trend không phù hợp")
        elif has_breakout_sell and not body_ok:
            print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Body nến SELL không đủ lớn")

    if not has_breakout_buy and not has_breakout_sell:
        filter_status.append(f"❌ No Breakout: Price trong range [Lower, Upper]")
        print(f"\n❌ [KHÔNG CÓ TÍN HIỆU] - Không có Donchian Breakout")

    if not signal:
        print(f"\n{'─'*80}\n❌ [KHÔNG CÓ TÍN HIỆU] - Tóm tắt (V2, nguồn XAU_M1)\n{'─'*80}")
        for s in filter_status:
            print(f"   {s}")
        print(f"   ATR: {atr_min}-{atr_max}p | trade_direction: {trade_direction}\n{'─'*80}\n")
        return error_count, 0

    # --- GUARDS V2 ---
    loss_streak_threshold = config['parameters'].get('loss_streak_threshold', 2)
    loss_cooldown_minutes = config['parameters'].get('loss_cooldown_minutes', 45)
    loss_streak_lookback_days = config['parameters'].get('loss_streak_lookback_days', 7)
    try:
        from_dt = datetime.now() - timedelta(days=loss_streak_lookback_days)
        from_ts = int(from_dt.timestamp())
        to_ts = int(datetime.now().timestamp())
        deals = mt5.history_deals_get(from_ts, to_ts)
        if deals:
            closed = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT and d.magic == magic and d.profit != 0]
            closed.sort(key=lambda x: x.time, reverse=True)
            loss_streak = 0
            for d in closed:
                if d.profit < 0:
                    loss_streak += 1
                else:
                    break
            if loss_streak >= loss_streak_threshold and closed:
                last_ts = closed[0].time.timestamp() if hasattr(closed[0].time, 'timestamp') else closed[0].time
                mins = (datetime.now().timestamp() - last_ts) / 60
                if mins < loss_cooldown_minutes:
                    print(f"   ⏳ Consecutive Loss Guard: {loss_streak} losses, {loss_cooldown_minutes - mins:.1f} min left")
                    return error_count, 0
    except Exception as e:
        print(f"   ⚠️ Consecutive loss check: {e}")

    # V2: Cooldown dùng datetime
    from_dt = datetime.now() - timedelta(minutes=5)
    from_ts = int(from_dt.timestamp())
    to_ts = int(datetime.now().timestamp())
    deals = mt5.history_deals_get(from_ts, to_ts)
    if deals:
        if any(d.magic == magic for d in deals):
            print(f"   ⏳ Cooldown: Last trade < 5 mins ago. Skipping.")
            return error_count, 0

    # V2: Daily loss limit
    daily_loss_limit = config['parameters'].get('daily_loss_limit', -20.0)
    try:
        day_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        day_ts = int(day_start.timestamp())
        to_ts = int(datetime.now().timestamp())
        day_deals = mt5.history_deals_get(day_ts, to_ts)
        if day_deals:
            pnl_today = sum(d.profit + d.swap + d.commission for d in day_deals if d.magic == magic)
            if pnl_today <= daily_loss_limit:
                print(f"   ⏳ Daily Loss Limit: PnL today {pnl_today:.2f} <= {daily_loss_limit}. Stop.")
                return error_count, 0
    except Exception as e:
        print(f"   ⚠️ Daily PnL check: {e}")

    tick = mt5.symbol_info_tick(symbol)
    max_spread_points = config['parameters'].get('max_spread_points', 80)
    spread_pts = (tick.ask - tick.bid) / point if point > 0 else 0
    if spread_pts > max_spread_points:
        print(f"   ❌ Spread Filter: {spread_pts:.0f} pts > {max_spread_points}. Skip.")
        return error_count, 0

    price = tick.ask if signal == "BUY" else tick.bid

    # SL/TP
    sl_mode = config['parameters'].get('sl_mode', 'atr')
    reward_ratio = config['parameters'].get('reward_ratio', 1.5)
    sl = tp = 0.0
    if sl_mode == 'atr':
        sl_mult = config['parameters'].get('sl_atr_multiplier', 2.0)
        tp_mult = config['parameters'].get('tp_atr_multiplier', 3.0)
        sl_dist = atr_value * sl_mult
        tp_dist = atr_value * tp_mult
        if signal == "BUY":
            sl, tp = price - sl_dist, price + tp_dist
        else:
            sl, tp = price + sl_dist, price - tp_dist
        min_dist = 100 * point
        if signal == "BUY":
            if (price - sl) < min_dist:
                sl = price - min_dist
                tp = price + (price - sl) * reward_ratio
        else:
            if (sl - price) < min_dist:
                sl = price + min_dist
                tp = price - (sl - price) * reward_ratio
        print(f"   📏 ATR SL: {sl:.2f} | TP: {tp:.2f} (R:R {reward_ratio})")
    elif sl_mode == 'auto_m5':
        prev_m5_high = df_m5.iloc[-2]['high']
        prev_m5_low = df_m5.iloc[-2]['low']
        buf = 20 * point
        if signal == "BUY":
            sl = prev_m5_low - buf
            if (price - sl) < 100 * point:
                sl = price - 100 * point
            tp = price + (price - sl) * reward_ratio
        else:
            sl = prev_m5_high + buf
            if (sl - price) < 100 * point:
                sl = price + 100 * point
            tp = price - (sl - price) * reward_ratio
        print(f"   📏 Auto M5 SL: {sl:.2f} | TP: {tp:.2f}")
    else:
        sl = price - 2.0 if signal == "BUY" else price + 2.0
        tp = price + 5.0 if signal == "BUY" else price - 5.0
        print(f"   📏 Fixed SL: {sl:.2f} | TP: {tp:.2f}")

    # V2: Risk cap
    max_risk_price = config['parameters'].get('max_risk_price', 9.0)
    if abs(price - sl) > max_risk_price:
        print(f"   ❌ Risk Cap: |entry-sl| = {abs(price-sl):.2f} > {max_risk_price}. Skip.")
        return error_count, 0

    print(f"🚀 Strat 5 V2 SIGNAL: {signal} @ {price}")
    db.log_signal(STRATEGY_NAME, symbol, signal, price, sl, tp, {
        "setup": "Donchian Breakout V2 (clone XAU_M1)",
        "rsi": float(last['rsi']),
        "adx": float(adx_value),
        "atr": float(atr_value),
        "atr_pips": float(atr_pips),
        "volume": int(last['tick_volume']),
        "vol_ratio": float(last['tick_volume'] / last['vol_ma']) if last['vol_ma'] > 0 else 0,
        "trend": m5_trend,
        "donchian_period": donchian_period,
        "trade_direction": trade_direction,
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
        "comment": "Strat5_FilterFirst_V2",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Order Success: {result.order}")
        db.log_order(result.order, STRATEGY_NAME, symbol, signal, volume, price, sl, tp, result.comment, account_id=config['account'])
        msg = (
            f"✅ <b>Strat 5 Filter First V2</b> (clone XAU_M1)\n"
            f"🆔 {result.order} | 💱 {symbol} {signal} @ {price}\n"
            f"🛑 SL: {sl:.2f} | 🎯 TP: {tp:.2f}\n"
            f"📊 RSI: {last['rsi']:.1f} | ADX: {adx_value:.1f} | ATR: {atr_pips:.1f}p | Dir: {trade_direction}"
        )
        send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
        return 0, 0
    print(f"❌ Order Failed: {result.retcode}")
    return error_count + 1, result.retcode

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_5_v2.json")
    if not os.path.exists(config_path):
        config_path = os.path.join(script_dir, "configs", "config_5.json")
    config = load_config(config_path)
    consecutive_errors = 0
    if config and connect_mt5(config):
        print("✅ Strategy 5 Filter First V2 (clone XAU_M1) - Started")
        try:
            while True:
                consecutive_errors, last_error_code = strategy_5_logic(config, consecutive_errors)
                if consecutive_errors >= 5:
                    msg = f"⚠️ [Strategy 5 V2] 5 failures. Last: {get_mt5_error_message(last_error_code)}. Pause 2 min."
                    print(msg)
                    send_telegram(msg, config['telegram_token'], config['telegram_chat_id'])
                    time.sleep(120)
                    consecutive_errors = 0
                time.sleep(1)
        except KeyboardInterrupt:
            mt5.shutdown()
