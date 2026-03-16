"""
Grid Step Trading Bot - BTCUSD v2. Clone của strategy_grid_step_btc + Anti-Whipsaw.
Cùng logic: BUY STOP / SELL STOP, nhiều step, cooldown, pause khi N lệnh thua liên tiếp.
Thêm lớp lọc Anti-Whipsaw theo document/Anti-Whipsaw.md: tính WhipsawScore, skip lệnh nếu score >= threshold.
Dùng config riêng (config_grid_step_btc_v2.json) và file cooldown/pause riêng (grid_cooldown_btc_v2.json, grid_pause_btc_v2.json).
"""
import sys
import os
# Fix Windows console: in UTF-8 de tranh loi Unicode khi in emoji/tieng Viet
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
import MetaTrader5 as mt5
import time
import sqlite3
import json
from datetime import datetime, timedelta, timezone
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, send_telegram, get_mt5_error_message
from grid_step_common import get_last_n_closed_profits_by_symbol, get_closed_from_mt5_history

db = Database()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown_btc_v2.json")
PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause_btc_v2.json")


# ---------- Anti-Whipsaw helpers (theo Anti-Whipsaw.md) ----------

def normalize_level(price: float, step: float) -> float:
    """Chuẩn hóa giá về level đúng của step."""
    return round(float(price) / float(step)) * float(step)


def side_from_order_type(order_type) -> str:
    """Map order_type từ DB thành BUY hoặc SELL."""
    s = str(order_type or "").upper()
    if "BUY" in s:
        return "BUY"
    return "SELL"


def is_in_zone(level: float, center_level: float, step: float) -> bool:
    """Kiểm tra level có nằm trong zone [center - step, center + step] hay không."""
    step_f = float(step)
    return (float(center_level) - step_f) <= float(level) <= (float(center_level) + step_f)


def _parse_open_time(open_time_str):
    """Parse open_time từ DB (string) thành datetime naive UTC."""
    if open_time_str is None:
        return None
    if hasattr(open_time_str, "timestamp"):
        dt = open_time_str
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        return dt
    s = str(open_time_str).strip().replace("Z", "").replace("+00:00", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(s[:26], fmt.replace("%f", "").replace(".%f", "")[:19])
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s[:19])
    except (ValueError, TypeError):
        return None


def load_recent_closed_orders_for_step(strategy_name, account_id, symbol, step, limit=300, days_back=1):
    """
    Load lịch sử lệnh đã đóng cho đúng strategy/account/symbol/step.
    Trả về list dict: { "step", "side", "level", "result", "open_time" } cho compute_whipsaw_score().
    """
    step_f = float(step)
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cutoff = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        SELECT open_price, order_type, profit, open_time, close_time
        FROM orders
        WHERE strategy_name = ? AND account_id = ? AND symbol = ? AND profit IS NOT NULL
          AND open_time >= ?
        ORDER BY COALESCE(close_time, open_time) DESC
        LIMIT ?
    """, (strategy_name, account_id, symbol, cutoff, limit))
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        profit_val = r["profit"]
        if profit_val == 0:
            continue
        open_time = _parse_open_time(r["open_time"])
        if open_time is None:
            continue
        close_time = _parse_open_time(r["close_time"]) if r["close_time"] else open_time
        result.append({
            "step": step_f,
            "side": side_from_order_type(r["order_type"]),
            "level": normalize_level(float(r["open_price"]), step_f),
            "result": "Win" if (profit_val or 0) > 0 else "Loss",
            "open_time": open_time,
            "close_time": close_time,
        })
    return result


def compute_whipsaw_score(step, side, level, now, closed_orders, weights=None):
    """
    Tính WhipsawScore theo công thức Anti-Whipsaw.md.
    closed_orders: list dict với step, side, level, result, open_time [, close_time].
    now: datetime naive UTC.
    weights: dict với các key whipsaw_weight_* (optional).
    Trả về (score: int, components: dict). Khi không có dữ liệu trả về (0, {}) (Fallback §27).
    """
    if not closed_orders:
        return 0, {}
    w = weights or {}
    def wget(key, default):
        return int(w.get(key, default))

    same_window = wget("whipsaw_same_window_minutes", 120)
    zone_window = wget("whipsaw_zone_window_minutes", 60)
    recent_same_loss_minutes = wget("whipsaw_recent_same_loss_minutes", 30)
    w_rsl = wget("whipsaw_weight_recent_same_loss", 3)
    w_same_loss = wget("whipsaw_weight_same_loss", 3)
    w_same_win = wget("whipsaw_weight_same_win", 1)
    w_zone_loss = wget("whipsaw_weight_zone_loss", 1)
    w_zone_win = wget("whipsaw_weight_zone_win", 3)
    w_c2 = wget("whipsaw_weight_last_two_losses", 3)

    step_f = float(step)
    hist = [o for o in closed_orders if float(o["step"]) == step_f]
    same = [o for o in hist if o["side"] == side and float(o["level"]) == float(level)]
    zone = [o for o in hist if is_in_zone(float(o["level"]), float(level), step_f)]

    same_120 = [o for o in same if (now - o["open_time"]) <= timedelta(minutes=same_window)]
    zone_60 = [o for o in zone if (now - o["open_time"]) <= timedelta(minutes=zone_window)]

    L_same120 = min(sum(1 for o in same_120 if o["result"] == "Loss"), 3)
    W_same120 = min(sum(1 for o in same_120 if o["result"] == "Win"), 3)
    L_zone60 = min(sum(1 for o in zone_60 if o["result"] == "Loss"), 3)
    W_zone60 = min(sum(1 for o in zone_60 if o["result"] == "Win"), 3)

    R_same30 = 0
    if same:
        last_same = max(same, key=lambda x: x["open_time"])
        gap_minutes = (now - last_same["open_time"]).total_seconds() / 60.0
        if last_same["result"] == "Loss" and gap_minutes <= recent_same_loss_minutes:
            R_same30 = 1

    # C2: "2 lệnh đóng gần nhất của cùng step đều là Loss" (§7.6) — sort theo close_time
    sort_key = lambda x: x.get("close_time") or x["open_time"]
    sorted_hist = sorted(hist, key=sort_key)
    last_two = sorted_hist[-2:] if len(sorted_hist) >= 2 else []
    C2 = 1 if (len(last_two) == 2 and all(o["result"] == "Loss" for o in last_two)) else 0

    score = (
        w_rsl * R_same30
        + w_same_loss * L_same120
        - w_same_win * W_same120
        + w_zone_loss * L_zone60
        - w_zone_win * W_zone60
        + w_c2 * C2
    )
    return int(score), {"R_same30": R_same30, "L_same120": L_same120, "W_same120": W_same120,
                       "L_zone60": L_zone60, "W_zone60": W_zone60, "C2": C2}


def should_skip_for_whipsaw(step, side, level, now, closed_orders, threshold=5, weights=None):
    """Trả về (skip: bool, score: int, components: dict)."""
    if not closed_orders:
        return False, 0, {}
    score, components = compute_whipsaw_score(step, side, level, now, closed_orders, weights)
    return score >= threshold, score, components


# ---------- Cooldown / Pause (giữ nguyên logic từ btc) ----------

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


def load_pause_state(clean_expired=True, now_utc=None):
    if not os.path.exists(PAUSE_FILE):
        return {}
    try:
        with open(PAUSE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}
    if not clean_expired or not state:
        return state
    now = now_utc if now_utc is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
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


def get_mt5_time_utc(symbol):
    utc_now = datetime.now(timezone.utc)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return utc_now
    try:
        tick_utc = datetime.utcfromtimestamp(tick.time).replace(tzinfo=timezone.utc)
        if (utc_now - tick_utc).total_seconds() > 60:
            return utc_now
        return tick_utc
    except (TypeError, OSError):
        return utc_now


def is_paused(strategy_name, now_utc=None):
    state = load_pause_state(now_utc=now_utc)
    until = state.get(strategy_name)
    if not until:
        return False
    try:
        until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        now = now_utc if now_utc is not None else datetime.now(timezone.utc)
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now < until_dt
    except (ValueError, TypeError):
        return False


def get_pause_remaining(strategy_name, now_utc=None):
    state = load_pause_state(now_utc=now_utc)
    until = state.get(strategy_name)
    if not until:
        return None
    try:
        until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        now = now_utc if now_utc is not None else datetime.now(timezone.utc)
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        remaining = until_dt - now
        return remaining if remaining.total_seconds() > 0 else None
    except (ValueError, TypeError):
        return None


def set_paused(strategy_name, pause_minutes, from_time=None):
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


def sync_closed_orders_from_mt5(config, strategy_name=None):
    closed = get_closed_from_mt5_history(config, days_back=1)
    if not closed:
        return 0
    sn = strategy_name if strategy_name is not None else config.get("strategy_name", "Grid_Step")
    account_id = config.get("account", 0)
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ticket FROM orders WHERE strategy_name = ? AND profit IS NULL AND account_id = ?",
        (sn, account_id),
    )
    tickets_pending = {row[0] for row in cursor.fetchall()}
    conn.close()
    updated = 0
    for ticket in tickets_pending:
        if ticket in closed:
            profit, close_price, close_time = closed[ticket]
            db.update_order_profit(ticket, close_price, profit, close_time)
            updated += 1
    return updated


def check_grid_step_btc_v2_db():
    """Kiểm tra dữ liệu Grid Step BTC v2 trong DB (symbol=BTCUSD). Chạy: python strategy_grid_step_btc_v2.py --check-db"""
    path = db.db_path
    symbol_filter = "BTCUSD"
    print(f"\n{'='*60}")
    print(f"[DB] path: {path} | symbol: {symbol_filter} (v2)")
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
            print(f"✅ Grid BTC v2 lệnh khớp: ticket={ticket} → position={pos.ticket} ({order_type} @ {price})")
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

    # Anti-Whipsaw config
    whipsaw_enabled = params.get('whipsaw_filter_enabled', False)
    whipsaw_dry_run = params.get('whipsaw_filter_dry_run', True)
    whipsaw_threshold = params.get('whipsaw_threshold', 5)
    whipsaw_weights = {k: v for k, v in params.items() if k.startswith("whipsaw_") and isinstance(v, (int, float))}

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
        print(f"✅ [BASKET TP BTC v2] step={_step_label} Profit {profit:.2f} >= {target_profit}, đóng tất cả.")
        close_all_positions(symbol, magic, step_filter)
        cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step_filter)
        msg = f"✅ Grid Step BTC v2 {step}: Basket TP hit. Profit={profit:.2f} | Closed all."
        send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
        return 0, 0

    if consecutive_loss_pause_enabled and consecutive_loss_pause_minutes > 0 and consecutive_loss_count > 0:
        mt5_now = get_mt5_time_utc(symbol)
        if is_paused(strategy_name, now_utc=mt5_now):
            if not hasattr(strategy_grid_step_logic, "_last_pause_log") or strategy_grid_step_logic._last_pause_log != strategy_name:
                print(f"⏸️ [{strategy_name}] Đang tạm dừng ({consecutive_loss_count} lệnh thua liên tiếp), chờ {consecutive_loss_pause_minutes} phút.")
                strategy_grid_step_logic._last_pause_log = strategy_name
            remaining = get_pause_remaining(strategy_name, now_utc=mt5_now)
            if remaining is not None:
                mins = int(remaining.total_seconds() // 60)
                secs = int(remaining.total_seconds() % 60)
                print(f"⏸️ [{strategy_name}] Thời gian chờ còn lại: {mins} phút {secs} giây")
            return error_count, 0
        profits, last_close_time_str = get_last_n_closed_profits_by_symbol(symbol, magic, consecutive_loss_count, days_back=1)
        if len(profits) >= consecutive_loss_count and all((p or 0) < 0 for p in profits):
            last_close_dt = None
            if last_close_time_str:
                try:
                    last_close_dt = datetime.strptime(last_close_time_str.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            if last_close_dt is not None:
                until_dt = last_close_dt + timedelta(minutes=consecutive_loss_pause_minutes)
                if mt5_now < until_dt:
                    n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step=None)
                    set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time_str)
                    print(f"⏸️ [{strategy_name}] (history {symbol}) {consecutive_loss_count} lệnh thua liên tiếp → đã hủy {n_cancelled} lệnh chờ, tạm dừng {consecutive_loss_pause_minutes} phút.")
                    msg = f"⏸️ Grid Step BTC v2 tạm dừng giao dịch\nLý do: {consecutive_loss_count} lệnh thua liên tiếp ({symbol}).\nTạm dừng {consecutive_loss_pause_minutes} phút."
                    send_telegram(msg, config.get("telegram_token"), config.get("telegram_chat_id"))
                    return error_count, 0
            n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step=None)
            set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time_str)
            print(f"⏸️ [{strategy_name}] (history {symbol}) {consecutive_loss_count} lệnh thua liên tiếp → đã hủy {n_cancelled} lệnh chờ, tạm dừng {consecutive_loss_pause_minutes} phút.")
            send_telegram(f"⏸️ Grid Step BTC v2 tạm dừng {consecutive_loss_pause_minutes} phút.", config.get("telegram_token"), config.get("telegram_chat_id"))
            return error_count, 0
        did_pause, last_close_time = check_consecutive_losses_and_pause(strategy_name, config.get('account'), consecutive_loss_count, consecutive_loss_pause_minutes)
        if did_pause:
            n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step=None)
            set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time)
            print(f"⏸️ [{strategy_name}] (DB) {consecutive_loss_count} lệnh thua liên tiếp → đã hủy {n_cancelled} lệnh chờ, tạm dừng {consecutive_loss_pause_minutes} phút.")
            send_telegram(f"⏸️ Grid Step BTC v2 tạm dừng {consecutive_loss_pause_minutes} phút.", config.get('telegram_token'), config.get('telegram_chat_id'))
            return error_count, 0

    tick = mt5.symbol_info_tick(symbol)
    spread_price = (tick.ask - tick.bid) if tick else 0.0
    if spread_price > spread_max:
        if not hasattr(strategy_grid_step_logic, "_last_spread_log") or strategy_grid_step_logic._last_spread_log != round(spread_price, 4):
            print(f"⏸️ BTC v2 Spread={spread_price:.3f} > {spread_max} (bỏ qua)")
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

    # ---------- Anti-Whipsaw: tính score và quyết định skip BUY/SELL ----------
    skip_buy, skip_sell = False, False
    buy_score, sell_score = 0, 0
    if whipsaw_enabled:
        now_utc = datetime.utcnow()
        buy_level = normalize_level(buy_price, step_val)
        sell_level = normalize_level(sell_price, step_val)
        closed_orders = load_recent_closed_orders_for_step(
            strategy_name=strategy_name,
            account_id=config.get("account", 0),
            symbol=symbol,
            step=step_val,
        )
        print(f"[WHIPSAW] Tính điểm step={step_filter} | buy_level={buy_level} sell_level={sell_level} | "
              f"lịch sử đóng={len(closed_orders)} lệnh | threshold={whipsaw_threshold}")
        skip_buy, buy_score, buy_comp = should_skip_for_whipsaw(
            step_val, "BUY", buy_level, now_utc, closed_orders, threshold=whipsaw_threshold, weights=whipsaw_weights
        )
        skip_sell, sell_score, sell_comp = should_skip_for_whipsaw(
            step_val, "SELL", sell_level, now_utc, closed_orders, threshold=whipsaw_threshold, weights=whipsaw_weights
        )
        # Log công thức: WhipsawScore = 3*R_same30 + 3*L_same120 - 1*W_same120 + 1*L_zone60 - 3*W_zone60 + 3*C2
        if buy_comp:
            r, l120, w120, lz, wz, c2 = buy_comp.get('R_same30', 0), buy_comp.get('L_same120', 0), buy_comp.get('W_same120', 0), buy_comp.get('L_zone60', 0), buy_comp.get('W_zone60', 0), buy_comp.get('C2', 0)
            calc = f"3*{r}+3*{l120}-1*{w120}+1*{lz}-3*{wz}+3*{c2}"
            print(f"[WHIPSAW] BUY  level={buy_level} score={buy_score} = {calc} | skip={skip_buy}")
        if sell_comp:
            r, l120, w120, lz, wz, c2 = sell_comp.get('R_same30', 0), sell_comp.get('L_same120', 0), sell_comp.get('W_same120', 0), sell_comp.get('L_zone60', 0), sell_comp.get('W_zone60', 0), sell_comp.get('C2', 0)
            calc = f"3*{r}+3*{l120}-1*{w120}+1*{lz}-3*{wz}+3*{c2}"
            print(f"[WHIPSAW] SELL level={sell_level} score={sell_score} = {calc} | skip={skip_sell}")
        if whipsaw_dry_run:
            skip_buy = skip_sell = False
        if skip_buy and skip_sell:
            print(f"[WHIPSAW] skip cả hai phía tại step={step_filter} (buy_score={buy_score}, sell_score={sell_score})")
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
    r1, r2 = None, None
    if not skip_buy:
        print(f"📤 [BTC v2 step={_step_label}] BUY_STOP @ {buy_price} (SL={sl_buy}, TP={tp_buy})")
        r1 = place_pending(mt5.ORDER_TYPE_BUY_STOP, buy_price, sl_buy, tp_buy)
    if not skip_sell:
        print(f"📤 [BTC v2 step={_step_label}] SELL_STOP @ {sell_price} (SL={sl_sell}, TP={tp_sell})")
        r2 = place_pending(mt5.ORDER_TYPE_SELL_STOP, sell_price, sl_sell, tp_sell)

    if skip_buy and skip_sell:
        return error_count, 0

    if not skip_buy and r1 is None:
        err = mt5.last_error()
        print(f"❌ BUY_STOP order_send lỗi: {err}")
        return error_count + 1, getattr(err, 'code', 0)
    if not skip_buy and r1 is not None and r1.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ BUY_STOP failed: {r1.retcode} {r1.comment}")
        return error_count + 1, r1.retcode
    if not skip_sell and r2 is None:
        err = mt5.last_error()
        print(f"❌ SELL_STOP order_send lỗi: {err}")
        return error_count + 1, getattr(err, 'code', 0)
    if not skip_sell and r2 is not None and r2.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ SELL_STOP failed: {r2.retcode} {r2.comment}")
        return error_count + 1, r2.retcode

    placed_any = False
    if not skip_buy and r1 and r1.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Grid BTC v2 step={_step_label}: BUY_STOP @ {buy_price:.2f} | ref={ref}")
        if cooldown_minutes > 0:
            save_cooldown_levels([buy_price], step_filter)
        acc = config.get('account')
        db.log_grid_pending(r1.order, strategy_name, symbol, "BUY_STOP", buy_price, sl_buy, tp_buy, volume, acc)
        placed_any = True
    if not skip_sell and r2 and r2.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Grid BTC v2 step={_step_label}: SELL_STOP @ {sell_price:.2f} | ref={ref}")
        if cooldown_minutes > 0:
            save_cooldown_levels([sell_price], step_filter)
        acc = config.get('account')
        db.log_grid_pending(r2.order, strategy_name, symbol, "SELL_STOP", sell_price, sl_sell, tp_sell, volume, acc)
        placed_any = True

    return 0, 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].strip() == "--check-db":
        check_grid_step_btc_v2_db()
        sys.exit(0)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_grid_step_btc_v2.json")
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
        whipsaw_on = params.get("whipsaw_filter_enabled", False)
        dry = params.get("whipsaw_filter_dry_run", True)
        print(f"✅ Grid Step BTC v2 Bot - Started ({label}) | Anti-Whipsaw: {'ON' if whipsaw_on else 'OFF'} (dry_run={dry})")
        loop_count = 0
        try:
            while True:
                if params.get("consecutive_loss_pause_enabled", True):
                    if steps_list is not None:
                        for step_val in steps_list:
                            sync_closed_orders_from_mt5(config, strategy_name=f"Grid_Step_{step_val}")
                    else:
                        sync_closed_orders_from_mt5(config, strategy_name="Grid_Step")
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
                    print(f"🔄 Grid Step BTC v2 | Steps: {steps_info} | Positions: {len(pos)} | Pending: {len(ords)} | Spread: {spread:.2f} | Loop #{loop_count}")

                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Grid Step BTC v2] 5 lỗi liên tiếp. Last: {error_msg}. Tạm dừng 2 phút..."
                    print(msg)
                    send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
                    time.sleep(120)
                    consecutive_errors = 0
                    continue

                time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 Grid Step BTC v2 Bot Stopped")
            mt5.shutdown()
