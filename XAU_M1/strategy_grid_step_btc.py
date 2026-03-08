"""
Grid Step Trading Bot - BTCUSD. Clone của strategy_grid_step cho cặp BTCUSD.
Cùng logic: BUY STOP / SELL STOP, nhiều step, cooldown, pause khi N lệnh thua liên tiếp.
Dùng config riêng và file cooldown/pause riêng (grid_cooldown_btc.json, grid_pause_btc.json).
"""
import MetaTrader5 as mt5
import time
import sys
import sqlite3
import os
import json
from datetime import datetime, timedelta, timezone
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, send_telegram, get_mt5_error_message

db = Database()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown_btc.json")
PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause_btc.json")


def load_cooldown_levels(cooldown_minutes):
    """Trả về dict level_key -> timestamp (chỉ các mức còn trong thời gian cooldown)."""
    if cooldown_minutes <= 0:
        return {}
    if not os.path.exists(COOLDOWN_FILE):
        return {}
    try:
        with open(COOLDOWN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}
    levels = data.get("levels", {})
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=cooldown_minutes)
    result = {}
    for level_key, ts_str in levels.items():
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo:
                ts = ts.replace(tzinfo=None)
            if ts > cutoff:
                result[level_key] = ts_str
        except (ValueError, TypeError):
            pass
    return result


def save_cooldown_levels(level_keys_to_add, step=None):
    if not level_keys_to_add:
        return
    now = datetime.utcnow().isoformat() + "Z"
    data = {"levels": {}}
    if os.path.exists(COOLDOWN_FILE):
        try:
            with open(COOLDOWN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    levels = data.get("levels", {})
    for key in level_keys_to_add:
        k = f"{key}_{step}" if step is not None else str(key)
        levels[k] = now
    data["levels"] = levels
    try:
        with open(COOLDOWN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError:
        pass


def is_level_in_cooldown(levels_dict, price, cooldown_minutes, digits=2, step=None):
    if cooldown_minutes <= 0:
        return False
    key = str(round(float(price), digits))
    if step is not None:
        key = f"{key}_{step}"
    return key in levels_dict


def load_pause_state(clean_expired=True):
    if not os.path.exists(PAUSE_FILE):
        return {}
    try:
        with open(PAUSE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}
    if not clean_expired or not state:
        return state
    now = datetime.now(timezone.utc)
    to_remove = []
    for name, until in state.items():
        try:
            until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
            if until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=timezone.utc)
            if now >= until_dt:
                to_remove.append(name)
        except (ValueError, TypeError):
            to_remove.append(name)
    for name in to_remove:
        state.pop(name, None)
    if to_remove:
        save_pause_state(state)
    return state


def save_pause_state(pauses_dict):
    try:
        with open(PAUSE_FILE, "w", encoding="utf-8") as f:
            json.dump(pauses_dict, f, indent=2)
    except IOError:
        pass


def is_paused(strategy_name):
    state = load_pause_state()
    until = state.get(strategy_name)
    if not until:
        return False
    try:
        until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)
        return now < until_dt
    except (ValueError, TypeError):
        return False


def set_paused(strategy_name, pause_minutes, from_time=None):
    """from_time = thời điểm lệnh thua cuối (giờ server), None = ngay bây giờ."""
    state = load_pause_state()
    if from_time is not None:
        if isinstance(from_time, str):
            try:
                from_time = datetime.strptime(from_time.replace("Z", "").strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    from_time = datetime.fromisoformat(from_time.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    from_time = datetime.now(timezone.utc)
            if from_time.tzinfo is None:
                from_time = from_time.replace(tzinfo=timezone.utc)
        until_dt = from_time + timedelta(minutes=pause_minutes)
    else:
        until_dt = datetime.now(timezone.utc) + timedelta(minutes=pause_minutes)
    until = until_dt.isoformat().replace("+00:00", "Z")
    state[strategy_name] = until
    save_pause_state(state)


def check_consecutive_losses_and_pause(strategy_name, account_id, consecutive_loss_count, pause_minutes):
    """Trả về (True, close_time_của_lệnh_thua_cuối) hoặc (False, None)."""
    if pause_minutes <= 0 or consecutive_loss_count <= 0:
        return False, None
    rows = db.get_last_closed_orders(strategy_name, limit=consecutive_loss_count + 2, account_id=account_id)
    if len(rows) < consecutive_loss_count:
        return False, None
    first_n = rows[:consecutive_loss_count]
    if all((r["profit"] or 0) < 0 for r in first_n):
        last_close_time = first_n[0].get("close_time")
        return True, last_close_time
    return False, None


def check_grid_step_btc_db():
    """Kiểm tra dữ liệu Grid Step BTC trong DB (symbol=BTCUSD). Chạy: python strategy_grid_step_btc.py --check-db"""
    path = db.db_path
    symbol_filter = "BTCUSD"
    print(f"\n{'='*60}")
    print(f"[DB] path: {path} | symbol: {symbol_filter}")
    print(f"     Ton tai: {os.path.exists(path)}")
    if not os.path.exists(path):
        print("     File DB khong ton tai.")
        return
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        cur.execute("SELECT COUNT(*) FROM grid_pending_orders WHERE symbol = ?", (symbol_filter,))
        n = cur.fetchone()[0]
        cur.execute("""
            SELECT status, COUNT(*) as c FROM grid_pending_orders WHERE symbol = ?
            GROUP BY status
        """, (symbol_filter,))
        by_status = {row['status']: row['c'] for row in cur.fetchall()}
        print(f"\n[grid_pending_orders] {symbol_filter}: {n} dong")
        for st, c in by_status.items():
            print(f"   - {st}: {c}")
        cur.execute("""
            SELECT ticket, order_type, price, status, position_ticket, placed_at, filled_at
            FROM grid_pending_orders WHERE symbol = ?
            ORDER BY placed_at DESC LIMIT 5
        """, (symbol_filter,))
        rows = cur.fetchall()
        if rows:
            print("   Moi nhat (toi da 5):")
            for r in rows:
                print(f"     ticket={r['ticket']} {r['order_type']} @ {r['price']} status={r['status']} position_ticket={r['position_ticket']} placed={r['placed_at']}")
    except sqlite3.OperationalError as e:
        print(f"\n[grid_pending_orders] Bang chua co hoac loi: {e}")

    try:
        cur.execute("SELECT COUNT(*) FROM orders WHERE symbol = ?", (symbol_filter,))
        n_ord = cur.fetchone()[0]
        cur.execute("""
            SELECT ticket, order_type, volume, open_price, sl, tp, profit, open_time, comment
            FROM orders WHERE symbol = ? ORDER BY open_time DESC LIMIT 5
        """, (symbol_filter,))
        rows_ord = cur.fetchall()
        print(f"\n[orders] {symbol_filter}: {n_ord} dong")
        if rows_ord:
            for r in rows_ord:
                print(f"     ticket={r['ticket']} {r['order_type']} vol={r['volume']} price={r['open_price']} profit={r['profit']} time={r['open_time']}")
    except sqlite3.OperationalError as e:
        print(f"\n[orders] {e}")

    conn.close()
    print(f"{'='*60}\n")


def _comment_for_step(step):
    return "GridStep" if step is None else f"GridStep_{step}"


def get_positions_for_step(symbol, magic, step):
    positions = mt5.positions_get(symbol=symbol, magic=magic) or []
    if step is None:
        return list(positions)
    comment = _comment_for_step(step)
    return [p for p in positions if getattr(p, "comment", "") == comment]


def get_grid_anchor_price(symbol, magic, step=None):
    positions = get_positions_for_step(symbol, magic, step)
    if not positions:
        tick = mt5.symbol_info_tick(symbol)
        return (tick.bid + tick.ask) / 2.0
    latest = max(positions, key=lambda p: p.time)
    return float(latest.price_open)


def get_pending_orders(symbol, magic, step=None):
    orders = mt5.orders_get(symbol=symbol)
    if not orders:
        return []
    orders = [o for o in orders if o.magic == magic]
    if step is not None:
        comment = _comment_for_step(step)
        orders = [o for o in orders if getattr(o, "comment", "") == comment]
    return orders


def cancel_all_pending(symbol, magic, strategy_name="Grid_Step", account_id=0, step=None):
    orders = get_pending_orders(symbol, magic, step)
    for o in orders:
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        db.update_grid_pending_status(o.ticket, "CANCELLED")
    return len(orders)


def sync_grid_pending_status(symbol, magic, strategy_name="Grid_Step", account_id=0, sl_tp_price=5.0, info=None, step=None):
    pending_tickets = {o.ticket for o in get_pending_orders(symbol, magic, step)}
    positions = get_positions_for_step(symbol, magic, step)
    info = info or mt5.symbol_info(symbol)
    digits = getattr(info, "digits", 2) if info else 2
    pos_by_price = {}
    for p in positions:
        key = round(float(p.price_open), digits)
        pos_by_price[key] = p
    step_val = float(sl_tp_price)
    for row in db.get_grid_pending_by_status(strategy_name, symbol, "PENDING"):
        ticket, order_type, price = row["ticket"], row["order_type"], row["price"]
        if ticket in pending_tickets:
            continue
        price_key = round(float(price), digits) if digits else round(float(price), 2)
        pos = pos_by_price.get(price_key)
        if pos:
            db.update_grid_pending_status(ticket, "FILLED", position_ticket=pos.ticket)
            entry = float(pos.price_open)
            if pos.type == mt5.ORDER_TYPE_BUY:
                sl, tp = round(entry - step_val, digits), round(entry + step_val, digits)
            else:
                sl, tp = round(entry + step_val, digits), round(entry - step_val, digits)
            if not db.order_exists(pos.ticket):
                db.log_order(
                    pos.ticket, strategy_name, symbol,
                    "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                    float(pos.volume), entry, sl, tp,
                    "GridStep", account_id
                )
            print(f"✅ Grid BTC lệnh khớp: ticket={ticket} → position={pos.ticket} ({order_type} @ {price})")
        else:
            db.update_grid_pending_status(ticket, "CANCELLED")


def position_at_level(positions, level_price, point, tolerance_points=1):
    tol = tolerance_points * point
    for p in positions:
        if abs(p.price_open - level_price) <= tol:
            return True
    return False


def total_profit(symbol, magic, step=None):
    positions = get_positions_for_step(symbol, magic, step)
    if not positions:
        return 0.0
    return sum(p.profit + p.swap + getattr(p, 'commission', 0) for p in positions)


def ensure_position_sl_tp(symbol, magic, sl_tp_price, info, step=None):
    positions = get_positions_for_step(symbol, magic, step)
    step_val = float(sl_tp_price)
    for pos in positions:
        entry = float(pos.price_open)
        sl, tp = float(pos.sl or 0), float(pos.tp or 0)
        if pos.type == mt5.ORDER_TYPE_BUY:
            want_sl = round(entry - step_val, info.digits)
            want_tp = round(entry + step_val, info.digits)
        else:
            want_sl = round(entry + step_val, info.digits)
            want_tp = round(entry - step_val, info.digits)
        if abs(sl - want_sl) > 0.001 or abs(tp - want_tp) > 0.001:
            r = mt5.order_send({
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": symbol,
                "position": pos.ticket,
                "sl": want_sl,
                "tp": want_tp,
            })
            if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"   SL/TP set: pos {pos.ticket} -> SL={want_sl}, TP={want_tp}")
            elif r:
                print(f"   SL/TP fail pos {pos.ticket}: {r.retcode} {r.comment}")


def close_all_positions(symbol, magic, step=None):
    positions = get_positions_for_step(symbol, magic, step)
    for p in positions:
        tick = mt5.symbol_info_tick(symbol)
        price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
        mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": p.volume,
            "type": mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": p.ticket,
            "price": price,
            "magic": magic,
            "comment": "Grid_Basket_TP",
            "type_filling": mt5.ORDER_FILLING_IOC,
        })
    return len(positions)


def strategy_grid_step_logic(config, error_count=0, step=None):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    params = config.get('parameters', {})
    if step is None:
        step_val = float(params.get('step', 5) or 5)
        grid_step_price = step_val
        sl_tp_price = step_val
        strategy_name = "Grid_Step"
        step_filter = None
    else:
        step = float(step)
        step_val = step
        grid_step_price = step
        sl_tp_price = step
        strategy_name = f"Grid_Step_{step}"
        step_filter = step
    min_distance_points = params.get('min_distance_points', 5)
    max_positions = config.get('max_positions', 5)
    target_profit = params.get('target_profit', 50.0)
    spread_max = params.get('spread_max', 0.5)
    consecutive_loss_pause_enabled = params.get('consecutive_loss_pause_enabled', True)
    consecutive_loss_count = params.get('consecutive_loss_count', 2)
    consecutive_loss_pause_minutes = params.get('consecutive_loss_pause_minutes', 5)

    info = mt5.symbol_info(symbol)
    if not info:
        return error_count, 0
    volume_min = getattr(info, 'volume_min', 0.01)
    volume_step_vol = getattr(info, 'volume_step', 0.01)
    volume = max(float(volume), volume_min)
    if volume_step_vol > 0:
        volume = round(volume / volume_step_vol) * volume_step_vol
        volume = max(volume, volume_min)
    point = info.point
    min_distance = min_distance_points * point

    positions = get_positions_for_step(symbol, magic, step_filter)
    positions = list(positions)
    pendings = get_pending_orders(symbol, magic, step_filter)

    sync_grid_pending_status(symbol, magic, strategy_name, config.get('account'), sl_tp_price, info, step_filter)
    ensure_position_sl_tp(symbol, magic, sl_tp_price, info, step_filter)

    profit = total_profit(symbol, magic, step_filter)
    if profit >= target_profit and positions:
        _step_label = step_filter if step_filter is not None else "single"
        print(f"✅ [BASKET TP BTC] step={_step_label} Profit {profit:.2f} >= {target_profit}, đóng tất cả.")
        close_all_positions(symbol, magic, step_filter)
        cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step_filter)
        msg = f"✅ Grid Step BTC {step}: Basket TP hit. Profit={profit:.2f} | Closed all."
        send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
        return 0, 0

    if consecutive_loss_pause_enabled and consecutive_loss_pause_minutes > 0 and consecutive_loss_count > 0:
        if is_paused(strategy_name):
            if not hasattr(strategy_grid_step_logic, "_last_pause_log") or strategy_grid_step_logic._last_pause_log != strategy_name:
                print(f"⏸️ [{strategy_name}] Đang tạm dừng ({consecutive_loss_count} lệnh thua liên tiếp), chờ {consecutive_loss_pause_minutes} phút (từ giờ đóng lệnh thua cuối).")
                strategy_grid_step_logic._last_pause_log = strategy_name
            return error_count, 0
        did_pause, last_close_time = check_consecutive_losses_and_pause(strategy_name, config.get('account'), consecutive_loss_count, consecutive_loss_pause_minutes)
        if did_pause:
            n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step=None)
            set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time)
            print(f"⏸️ [{strategy_name}] {consecutive_loss_count} lệnh thua liên tiếp → đã hủy {n_cancelled} lệnh chờ, tạm dừng {consecutive_loss_pause_minutes} phút (từ giờ đóng lệnh thua cuối).")
            return error_count, 0

    tick = mt5.symbol_info_tick(symbol)
    spread_price = (tick.ask - tick.bid) if tick else 0.0
    if spread_price > spread_max:
        if not hasattr(strategy_grid_step_logic, "_last_spread_log") or strategy_grid_step_logic._last_spread_log != round(spread_price, 4):
            print(f"⏸️ BTC Spread={spread_price:.3f} > {spread_max} (bỏ qua)")
            strategy_grid_step_logic._last_spread_log = round(spread_price, 4)
        return error_count, 0
    if grid_step_price < spread_price:
        if not hasattr(strategy_grid_step_logic, "_last_grid_log"):
            print(f"⚠️ Grid step (giá)={grid_step_price:.3f} quá nhỏ so với spread {spread_price:.3f}. Tăng grid_step trong config.")
            strategy_grid_step_logic._last_grid_log = True
        return error_count, 0

    if len(positions) >= max_positions:
        return error_count, 0
    if len(pendings) == 2:
        return error_count, 0

    if positions:
        cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step_filter)
        current_price = get_grid_anchor_price(symbol, magic, step_filter)
    else:
        if pendings:
            cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step_filter)
        current_price = get_grid_anchor_price(symbol, magic, step_filter)

    ref = round(current_price / grid_step_price) * grid_step_price
    ref = round(ref, info.digits)
    buy_price = round(ref + grid_step_price, info.digits)
    sell_price = round(ref - grid_step_price, info.digits)

    if position_at_level(positions, buy_price, point):
        return error_count, 0
    if position_at_level(positions, sell_price, point):
        return error_count, 0
    for p in positions:
        if abs(p.price_open - buy_price) < min_distance or abs(p.price_open - sell_price) < min_distance:
            return error_count, 0

    cooldown_minutes = params.get('cooldown_minutes', 0)
    if cooldown_minutes > 0:
        cooldown_levels = load_cooldown_levels(cooldown_minutes)
        if is_level_in_cooldown(cooldown_levels, buy_price, cooldown_minutes, info.digits, step_filter) or is_level_in_cooldown(cooldown_levels, sell_price, cooldown_minutes, info.digits, step_filter):
            _log_key = (step_filter, buy_price, sell_price)
            if not hasattr(strategy_grid_step_logic, "_last_cooldown_log") or strategy_grid_step_logic._last_cooldown_log != _log_key:
                print(f"⏸️ Cooldown step={step_filter}: mức {buy_price}/{sell_price} trong {cooldown_minutes} phút, bỏ qua.")
                strategy_grid_step_logic._last_cooldown_log = _log_key
            return error_count, 0

    step_sl_tp = float(sl_tp_price)
    filling = mt5.ORDER_FILLING_FOK
    if info.filling_mode & 2:
        filling = mt5.ORDER_FILLING_IOC

    def place_pending(order_type, price, sl, tp):
        req = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": round(price, info.digits),
            "sl": round(sl, info.digits) if sl else 0.0,
            "tp": round(tp, info.digits) if tp else 0.0,
            "magic": magic,
            "comment": _comment_for_step(step_filter),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        return mt5.order_send(req)

    sl_buy = buy_price - step_sl_tp
    tp_buy = buy_price + step_sl_tp
    sl_sell = sell_price + step_sl_tp
    tp_sell = sell_price - step_sl_tp

    _step_label = step_filter if step_filter is not None else step_val
    print(f"📤 [BTC step={_step_label}] BUY_STOP @ {buy_price} (SL={sl_buy}, TP={tp_buy}), SELL_STOP @ {sell_price} (SL={sl_sell}, TP={tp_sell})")
    r1 = place_pending(mt5.ORDER_TYPE_BUY_STOP, buy_price, sl_buy, tp_buy)
    r2 = place_pending(mt5.ORDER_TYPE_SELL_STOP, sell_price, sl_sell, tp_sell)

    if r1 is None:
        err = mt5.last_error()
        print(f"❌ BUY_STOP order_send lỗi: {err}")
        return error_count + 1, getattr(err, 'code', 0)
    if r2 is None:
        err = mt5.last_error()
        print(f"❌ SELL_STOP order_send lỗi: {err}")
        return error_count + 1, getattr(err, 'code', 0)

    if r1.retcode == mt5.TRADE_RETCODE_DONE and r2.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Grid BTC step={_step_label}: BUY_STOP @ {buy_price:.2f}, SELL_STOP @ {sell_price:.2f} | ref={ref}")
        if cooldown_minutes > 0:
            save_cooldown_levels([buy_price, sell_price], step_filter)
        acc = config.get('account')
        db.log_grid_pending(r1.order, strategy_name, symbol, "BUY_STOP", buy_price, sl_buy, tp_buy, volume, acc)
        db.log_grid_pending(r2.order, strategy_name, symbol, "SELL_STOP", sell_price, sl_sell, tp_sell, volume, acc)
        return 0, 0
    if r1.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ BUY_STOP failed: {r1.retcode} {r1.comment}")
        return error_count + 1, r1.retcode
    if r2.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ SELL_STOP failed: {r2.retcode} {r2.comment}")
        return error_count + 1, r2.retcode

    return error_count, 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].strip() == "--check-db":
        check_grid_step_btc_db()
        sys.exit(0)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_grid_step_btc.json")
    config = load_config(config_path)

    consecutive_errors = 0

    if config and connect_mt5(config):
        params = config.get("parameters", {})
        if "steps" in params and params["steps"] is not None:
            steps_config = params["steps"]
            if not isinstance(steps_config, list):
                steps_config = [steps_config]
            steps_list = [float(s) for s in steps_config]
        else:
            steps_list = None
        label = f"steps: {steps_list}" if steps_list is not None else "single step (legacy)"
        print(f"✅ Grid Step BTC Bot - Started ({label})")
        loop_count = 0
        try:
            while True:
                if steps_list is not None:
                    for step_val in steps_list:
                        consecutive_errors, last_error_code = strategy_grid_step_logic(config, consecutive_errors, step=step_val)
                else:
                    consecutive_errors, last_error_code = strategy_grid_step_logic(config, consecutive_errors, step=None)
                loop_count += 1
                if loop_count % 30 == 0:
                    sym = config["symbol"]
                    mag = config["magic"]
                    pos = mt5.positions_get(symbol=sym, magic=mag) or []
                    ords = mt5.orders_get(symbol=sym) or []
                    ords = [o for o in ords if o.magic == mag]
                    tick = mt5.symbol_info_tick(sym)
                    spread = (tick.ask - tick.bid) if tick else 0
                    steps_info = steps_list if steps_list else "1"
                    print(f"🔄 Grid Step BTC | Steps: {steps_info} | Positions: {len(pos)} | Pending: {len(ords)} | Spread: {spread:.2f} | Loop #{loop_count}")

                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Grid Step BTC] 5 lỗi liên tiếp. Last: {error_msg}. Tạm dừng 2 phút..."
                    print(msg)
                    send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
                    time.sleep(120)
                    consecutive_errors = 0
                    continue

                time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 Grid Step BTC Bot Stopped")
            mt5.shutdown()
