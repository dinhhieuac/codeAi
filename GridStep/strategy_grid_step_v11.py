"""
Grid Step Trading Bot V11 - Clone của strategy_grid_step.py.
Dùng config riêng (config_grid_step_v11.json), cooldown/pause riêng (grid_cooldown_v11.json, grid_pause_v11.json).
Bot chỉ chạy trong khung giờ (giờ server MT5):
  BẬT: 10:00–11:59, 14:00–14:59, 17:00–18:59
  TẮT: ngoài các khung trên (08:00–09:59, 12:00–13:59, 15:00–16:59, 19:00–23:59, v.v.)
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
from grid_step_common import get_last_n_closed_profits_by_symbol, get_closed_from_mt5_history

db = Database()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown_v11.json")
PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause_v11.json")


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
                ts = ts.replace(tzinfo=None)  # so sánh với naive utc
            if ts > cutoff:
                result[level_key] = ts_str
        except (ValueError, TypeError):
            pass
    return result


def save_cooldown_levels(level_keys_to_add, step=None):
    """Ghi thêm các mức level (với thời gian hiện tại) vào file cooldown. step != None: key = price_step (multi-step)."""
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
    """Kiểm tra mức giá price có đang trong cooldown không. step != None: key = price_step."""
    if cooldown_minutes <= 0:
        return False
    key = str(round(float(price), digits))
    if step is not None:
        key = f"{key}_{step}"
    return key in levels_dict


def _pause_until_from_value(val):
    """Đọc cả dạng cũ (chuỗi ISO) và dạng mới từ V3 (object có paused_until, reason, meta)."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("paused_until") or val.get("until")
    return None


def load_pause_state(clean_expired=True, now_utc=None):
    """Đọc trạng thái tạm dừng (strategy_name -> paused_until ISO). Nếu clean_expired=True thì xóa mục hết hạn.
    now_utc: dùng giờ MT5 (hoặc None = datetime.now(timezone.utc)) để so sánh."""
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
    for name, val in state.items():
        until = _pause_until_from_value(val)
        try:
            if until is None:
                to_remove.append(name)
                continue
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
    """Ghi lại trạng thái tạm dừng."""
    try:
        with open(PAUSE_FILE, "w", encoding="utf-8") as f:
            json.dump(pauses_dict, f, indent=2)
    except IOError:
        pass


def get_mt5_time_utc(symbol):
    """Lấy giờ 'hiện tại' cho so sánh pause. tick.time của MT5 là thời điểm tick/quote cuối, không phải giờ server thực ->
    nếu thị trường ít biến động tick.time cũ, thời gian chờ còn lại sai. Dùng tick.time khi còn mới (< 60s), nếu cũ thì dùng utcnow()."""
    utc_now = datetime.now(timezone.utc)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return utc_now
    try:
        tick_utc = datetime.utcfromtimestamp(tick.time).replace(tzinfo=timezone.utc)
        # tick.time = thời điểm tick cuối, có thể cũ -> nếu lệch quá 60s so với PC thì dùng PC
        if (utc_now - tick_utc).total_seconds() > 60:
            return utc_now
        return tick_utc
    except (TypeError, OSError):
        return utc_now


def _parse_time_to_minutes(s):
    """Chuyển 'HH:MM' hoặc 'H:MM' thành số phút từ 0h. Trả về None nếu lỗi."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    try:
        parts = s.split(":")
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        return h * 60 + m
    except (ValueError, IndexError):
        return None


def is_in_trading_hours_v11(now_dt, trading_hours=None):
    """Kiểm tra giờ server MT5 có trong khung BẬT không. trading_hours = list of {"start": "HH:MM", "end": "HH:MM"} (giờ MT5). now_dt = datetime từ get_mt5_time_utc. Nếu trading_hours rỗng/None thì dùng mặc định 10-11:59, 14-14:59, 17-18:59."""
    if now_dt is None:
        return False
    default = [{"start": "10:00", "end": "11:59"}, {"start": "14:00", "end": "14:59"}, {"start": "17:00", "end": "18:59"}]
    windows = trading_hours if trading_hours else default
    if not windows:
        return False
    now_min = now_dt.hour * 60 + now_dt.minute
    for w in windows:
        start_min = _parse_time_to_minutes(w.get("start") if isinstance(w, dict) else None)
        end_min = _parse_time_to_minutes(w.get("end") if isinstance(w, dict) else None)
        if start_min is not None and end_min is not None and start_min <= now_min <= end_min:
            return True
    return False


def _trading_hours_summary(trading_hours):
    """Tạo chuỗi ngắn mô tả khung giờ để in log."""
    if not trading_hours:
        return "10-11:59, 14-14:59, 17-18:59"
    parts = []
    for w in trading_hours:
        if isinstance(w, dict) and w.get("start") and w.get("end"):
            parts.append(f"{w['start']}-{w['end']}")
    return ", ".join(parts) if parts else "10-11:59, 14-14:59, 17-18:59"


def is_paused(strategy_name, now_utc=None):
    """Kiểm tra strategy (step) có đang trong thời gian tạm dừng không. now_utc = giờ MT5 (nếu có) để so sánh."""
    state = load_pause_state(now_utc=now_utc)
    until = _pause_until_from_value(state.get(strategy_name))
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
    """Trả về thời gian chờ còn lại (timedelta) hoặc None nếu không đang pause. Dùng để hiển thị 'còn lại X phút Y giây'."""
    state = load_pause_state(now_utc=now_utc)
    until = _pause_until_from_value(state.get(strategy_name))
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
    """Tạm dừng strategy trong pause_minutes phút. from_time = thời điểm lệnh thua cuối (giờ server), None = ngay bây giờ."""
    state = load_pause_state()
    if from_time is not None:
        # from_time: datetime hoặc str "YYYY-MM-DD HH:MM:SS" (giờ server/UTC)
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
    """Nếu có đủ N lệnh thua liên tiếp trong history thì set pause. Trả về (True, close_time_của_lệnh_thua_cuối) hoặc (False, None)."""
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
    """Đồng bộ lệnh đã đóng từ MT5 history vào bảng orders (profit, close_time). Giúp kiểm tra consecutive loss ngay trong bot.
    strategy_name: nếu None thì dùng config.get('strategy_name','Grid_Step'); khi dùng steps thì gọi sync cho từng 'Grid_Step_{step}'."""
    closed = get_closed_from_mt5_history(config, days_back=1)
    if not closed:
        return 0
    sn = strategy_name if strategy_name is not None else config.get("strategy_name", "Grid_Step_V11")
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


def check_grid_step_v11_db():
    """Kiểm tra dữ liệu Grid Step trong DB (grid_pending_orders, orders). Chạy: python strategy_grid_step.py --check-db"""
    path = db.db_path
    print(f"\n{'='*60}")
    print(f"[DB] path: {path}")
    print(f"     Ton tai: {os.path.exists(path)}")
    if not os.path.exists(path):
        print("     File DB khong ton tai.")
        return
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Bảng grid_pending_orders
    try:
        cur.execute("SELECT COUNT(*) FROM grid_pending_orders WHERE strategy_name = 'Grid_Step_V11'")
        n = cur.fetchone()[0]
        cur.execute("""
            SELECT status, COUNT(*) as c FROM grid_pending_orders WHERE strategy_name = 'Grid_Step_V11'
            GROUP BY status
        """)
        by_status = {row['status']: row['c'] for row in cur.fetchall()}
        print(f"\n[grid_pending_orders] Grid_Step_V11: {n} dong")
        for st, c in by_status.items():
            print(f"   - {st}: {c}")
        cur.execute("""
            SELECT ticket, order_type, price, status, position_ticket, placed_at, filled_at
            FROM grid_pending_orders WHERE strategy_name = 'Grid_Step_V11'
            ORDER BY placed_at DESC LIMIT 5
        """)
        rows = cur.fetchall()
        if rows:
            print("   Moi nhat (toi da 5):")
            for r in rows:
                print(f"     ticket={r['ticket']} {r['order_type']} @ {r['price']} status={r['status']} position_ticket={r['position_ticket']} placed={r['placed_at']}")
    except sqlite3.OperationalError as e:
        print(f"\n[grid_pending_orders] Bang chua co hoac loi: {e}")

    # Bảng orders (Grid_Step_V11)
    try:
        cur.execute("SELECT COUNT(*) FROM orders WHERE strategy_name = 'Grid_Step_V11'")
        n_ord = cur.fetchone()[0]
        cur.execute("""
            SELECT ticket, order_type, volume, open_price, sl, tp, profit, open_time, comment
            FROM orders WHERE strategy_name = 'Grid_Step_V11' ORDER BY open_time DESC LIMIT 5
        """)
        rows_ord = cur.fetchall()
        print(f"\n[orders] Grid_Step_V11: {n_ord} dong")
        if rows_ord:
            for r in rows_ord:
                print(f"     ticket={r['ticket']} {r['order_type']} vol={r['volume']} price={r['open_price']} profit={r['profit']} time={r['open_time']}")
    except sqlite3.OperationalError as e:
        print(f"\n[orders] {e}")

    conn.close()
    print(f"{'='*60}\n")


def _comment_for_step(step):
    """Comment MT5 cho từng step (V11 dùng prefix GridStep_V11)."""
    return "GridStep_V11" if step is None else f"GridStep_V11_{step}"


def get_positions_for_step(symbol, magic, step):
    """Chỉ lấy positions của bot V11: lọc theo symbol, magic và comment (GridStep_V11). Tránh đụng bot khác."""
    positions = mt5.positions_get(symbol=symbol, magic=magic) or []
    comment = _comment_for_step(step)
    return [p for p in positions if getattr(p, "comment", "") == comment]


def get_grid_anchor_price(symbol, magic, step=None):
    """Lấy giá neo grid: giá mở của position mới nhất (theo thời gian). Nếu không có position thì dùng giá thị trường."""
    positions = get_positions_for_step(symbol, magic, step)
    if not positions:
        tick = mt5.symbol_info_tick(symbol)
        return (tick.bid + tick.ask) / 2.0
    latest = max(positions, key=lambda p: p.time)
    return float(latest.price_open)


def get_pending_orders(symbol, magic, step=None):
    """Chỉ lấy lệnh chờ của bot V11: lọc theo symbol, magic và comment (GridStep_V11). Tránh cancel/đụng bot khác."""
    orders = mt5.orders_get(symbol=symbol)
    if not orders:
        return []
    orders = [o for o in orders if o.magic == magic]
    comment = _comment_for_step(step)
    orders = [o for o in orders if getattr(o, "comment", "") == comment]
    return orders


def cancel_all_pending(symbol, magic, strategy_name="Grid_Step_V11", account_id=0, step=None):
    """Hủy chỉ lệnh chờ của bot V11 (đã lọc theo comment GridStep_V11 trong get_pending_orders)."""
    orders = get_pending_orders(symbol, magic, step)  # đã lọc theo comment → chỉ bot V11
    for o in orders:
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        db.update_grid_pending_status(o.ticket, "CANCELLED")
    return len(orders)


def sync_grid_pending_status(symbol, magic, strategy_name="Grid_Step_V11", account_id=0, sl_tp_price=5.0, info=None, step=None):
    """Kiểm tra lệnh chờ trong DB: nếu ticket không còn trong MT5 orders → khớp hoặc hủy; cập nhật status.
    Khi lệnh khớp → ghi vào bảng orders với SL/TP đúng. step=None = single-step mode."""
    pending_tickets = {o.ticket for o in get_pending_orders(symbol, magic, step)}
    positions = get_positions_for_step(symbol, magic, step)
    info = info or mt5.symbol_info(symbol)
    digits = getattr(info, "digits", 2) if info else 2
    pos_by_price = {}
    for p in positions:
        key = round(float(p.price_open), digits)
        pos_by_price[key] = p
    step = float(sl_tp_price)
    for row in db.get_grid_pending_by_status(strategy_name, symbol, "PENDING"):
        ticket, order_type, price = row["ticket"], row["order_type"], row["price"]
        if ticket in pending_tickets:
            continue
        # Ticket không còn trong lệnh chờ → đã khớp hoặc bị hủy (ta đã CANCELLED khi gọi cancel_all)
        price_key = round(float(price), digits) if digits else round(float(price), 2)
        pos = pos_by_price.get(price_key)
        if pos:
            db.update_grid_pending_status(ticket, "FILLED", position_ticket=pos.ticket)
            # SL/TP chuẩn: entry ± 5 (giá). Dùng giá đúng thay vì pos.sl/pos.tp có thể 0.
            entry = float(pos.price_open)
            if pos.type == mt5.ORDER_TYPE_BUY:
                sl, tp = round(entry - step, digits), round(entry + step, digits)
            else:
                sl, tp = round(entry + step, digits), round(entry - step, digits)
            if not db.order_exists(pos.ticket):
                db.log_order(
                    pos.ticket, strategy_name, symbol,
                    "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                    float(pos.volume), entry, sl, tp,
                    "GridStep", account_id
                )
            print(f"✅ Grid lệnh khớp: ticket={ticket} → position={pos.ticket} ({order_type} @ {price})")
        else:
            db.update_grid_pending_status(ticket, "CANCELLED")


def position_at_level(positions, level_price, point, tolerance_points=1):
    """Kiểm tra đã có position tại mức giá level_price chưa (trong phạm vi tolerance)."""
    tol = tolerance_points * point
    for p in positions:
        if abs(p.price_open - level_price) <= tol:
            return True
    return False


def total_profit(symbol, magic, step=None):
    """Tổng lợi nhuận (floating) của positions thuộc strategy (hoặc thuộc step nếu step != None)."""
    positions = get_positions_for_step(symbol, magic, step)
    if not positions:
        return 0.0
    return sum(p.profit + p.swap + getattr(p, 'commission', 0) for p in positions)


def ensure_position_sl_tp(symbol, magic, sl_tp_price, info, step=None):
    """Đặt lại SL/TP cho position nếu đang 0 (broker không kế thừa từ lệnh chờ)."""
    positions = get_positions_for_step(symbol, magic, step)
    step = float(sl_tp_price)
    for pos in positions:
        entry = float(pos.price_open)
        sl, tp = float(pos.sl or 0), float(pos.tp or 0)
        if pos.type == mt5.ORDER_TYPE_BUY:
            want_sl = round(entry - step, info.digits)
            want_tp = round(entry + step, info.digits)
        else:
            want_sl = round(entry + step, info.digits)
            want_tp = round(entry - step, info.digits)
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
    """Đóng tất cả position của strategy (hoặc chỉ của step nếu step != None)."""
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
    """Chạy logic grid cho một step. step = giá trị bước (vd 5); step=None = chế độ cũ 1 step (strategy_name Grid_Step)."""
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    params = config.get('parameters', {})
    # step=None: 1 kênh, strategy_name "Grid_Step_V11"
    if step is None:
        step_val = float(params.get('step', 5) or 5)
        grid_step_price = step_val
        sl_tp_price = step_val
        strategy_name = "Grid_Step_V11"
        step_filter = None
    else:
        step = float(step)
        step_val = step
        grid_step_price = step
        sl_tp_price = step
        strategy_name = f"Grid_Step_V11_{step}"
        step_filter = step
    min_distance_points = params.get('min_distance_points', 5)
    max_positions = config.get('max_positions', 5)
    target_profit = params.get('target_profit', 50.0)
    spread_max = params.get('spread_max', 0.5)
    # Tạm dừng khi N lệnh thua liên tiếp: on/off + số lệnh + thời gian dừng (phút)
    consecutive_loss_pause_enabled = params.get('consecutive_loss_pause_enabled', True)
    consecutive_loss_count = params.get('consecutive_loss_count', 2)
    consecutive_loss_pause_minutes = params.get('consecutive_loss_pause_minutes', 5)

    info = mt5.symbol_info(symbol)
    if not info:
        return error_count, 0
    # XAU min lot = 0.01
    volume_min = getattr(info, 'volume_min', 0.01)
    volume_step = getattr(info, 'volume_step', 0.01)
    volume = max(float(volume), volume_min)
    if volume_step > 0:
        volume = round(volume / volume_step) * volume_step
        volume = max(volume, volume_min)
    point = info.point
    min_distance = min_distance_points * point

    # 1. Lấy positions và pending (chỉ của step này khi step_filter != None)
    positions = get_positions_for_step(symbol, magic, step_filter)
    positions = list(positions)
    pendings = get_pending_orders(symbol, magic, step_filter)

    # Cập nhật status lệnh chờ trong DB
    sync_grid_pending_status(symbol, magic, strategy_name, config.get('account'), sl_tp_price, info, step_filter)

    # Đặt lại SL/TP cho position nếu broker không kế thừa từ lệnh chờ
    ensure_position_sl_tp(symbol, magic, sl_tp_price, info, step_filter)

    # 2. Basket Take Profit (theo step)
    profit = total_profit(symbol, magic, step_filter)
    if profit >= target_profit and positions:
        _step_label = step_filter if step_filter is not None else "single"
        print(f"✅ [BASKET TP] step={_step_label} Profit {profit:.2f} >= {target_profit}, đóng tất cả.")
        close_all_positions(symbol, magic, step_filter)
        cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step_filter)
        msg = f"✅ Grid Step {step}: Basket TP hit. Profit={profit:.2f} | Closed all."
        send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
        return 0, 0

    # 2b. Tạm dừng khi có N lệnh thua liên tiếp (on/off: consecutive_loss_pause_enabled, số lệnh: consecutive_loss_count, thời gian: consecutive_loss_pause_minutes)
    if consecutive_loss_pause_enabled and consecutive_loss_pause_minutes > 0 and consecutive_loss_count > 0:
        mt5_now = get_mt5_time_utc(symbol)  # Giờ MT5 để so sánh: nếu (MT5 now - lệnh thua cuối) > 5 phút thì cho giao dịch lại
        if is_paused(strategy_name, now_utc=mt5_now):
            if not hasattr(strategy_grid_step_logic, "_last_pause_log") or strategy_grid_step_logic._last_pause_log != strategy_name:
                print(f"⏸️ [{strategy_name}] Đang tạm dừng ({consecutive_loss_count} lệnh thua liên tiếp), chờ {consecutive_loss_pause_minutes} phút (tính từ giờ đóng lệnh thua cuối, theo giờ MT5).")
                strategy_grid_step_logic._last_pause_log = strategy_name
            remaining = get_pause_remaining(strategy_name, now_utc=mt5_now)
            if remaining is not None:
                mins = int(remaining.total_seconds() // 60)
                secs = int(remaining.total_seconds() % 60)
                print(f"⏸️ [{strategy_name}] Thời gian chờ còn lại: {mins} phút {secs} giây")
            return error_count, 0
        # Kiểm tra từ MT5 history theo cặp (mỗi vòng lặp) -> nếu N lệnh thua liên tiếp thì hủy hết lệnh chờ và pause (chỉ tính lệnh của bot V11: comment_prefix GridStep_V11)
        profits, last_close_time_str = get_last_n_closed_profits_by_symbol(symbol, magic, consecutive_loss_count, days_back=1, comment_prefix="GridStep_V11")
        if len(profits) >= consecutive_loss_count and all((p or 0) < 0 for p in profits):
            # Chỉ pause nếu lệnh thua cuối chưa quá 5 phút; nếu đã quá 5 phút thì cho giao dịch bình thường
            last_close_dt = None
            if last_close_time_str:
                try:
                    last_close_dt = datetime.strptime(last_close_time_str.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            if last_close_dt is not None:
                until_dt = last_close_dt + timedelta(minutes=consecutive_loss_pause_minutes)
                if mt5_now >= until_dt:
                    # Đã hết 5 phút từ lệnh thua cuối -> không pause, giao dịch bình thường
                    pass
                else:
                    n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step=None)
                    set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time_str)
                    print(f"⏸️ [{strategy_name}] (history {symbol}) {consecutive_loss_count} lệnh thua liên tiếp → đã hủy {n_cancelled} lệnh chờ, tạm dừng {consecutive_loss_pause_minutes} phút.")
                    msg = f"⏸️ Grid Step tạm dừng giao dịch\nLý do: {consecutive_loss_count} lệnh thua liên tiếp ({symbol}).\nĐã hủy {n_cancelled} lệnh chờ (BUY STOP/SELL STOP).\nTạm dừng {consecutive_loss_pause_minutes} phút (tính từ giờ đóng lệnh thua cuối)."
                    send_telegram(msg, config.get("telegram_token"), config.get("telegram_chat_id"))
                    return error_count, 0
            else:
                n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step=None)
                set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time_str)
                print(f"⏸️ [{strategy_name}] (history {symbol}) {consecutive_loss_count} lệnh thua liên tiếp → đã hủy {n_cancelled} lệnh chờ, tạm dừng {consecutive_loss_pause_minutes} phút.")
                msg = f"⏸️ Grid Step tạm dừng giao dịch\nLý do: {consecutive_loss_count} lệnh thua liên tiếp ({symbol}).\nĐã hủy {n_cancelled} lệnh chờ (BUY STOP/SELL STOP).\nTạm dừng {consecutive_loss_pause_minutes} phút (tính từ giờ đóng lệnh thua cuối)."
                send_telegram(msg, config.get("telegram_token"), config.get("telegram_chat_id"))
                return error_count, 0
        # Kiểm tra từ DB (fallback)
        did_pause, last_close_time = check_consecutive_losses_and_pause(strategy_name, config.get('account'), consecutive_loss_count, consecutive_loss_pause_minutes)
        if did_pause:
            # Chỉ pause nếu lệnh thua cuối chưa quá 5 phút (giống nhánh history)
            last_close_dt = None
            if last_close_time:
                if isinstance(last_close_time, str):
                    try:
                        last_close_dt = datetime.strptime(last_close_time.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    except ValueError:
                        try:
                            last_close_dt = datetime.fromisoformat(last_close_time.replace("Z", "+00:00"))
                            if last_close_dt.tzinfo is None:
                                last_close_dt = last_close_dt.replace(tzinfo=timezone.utc)
                        except (ValueError, TypeError):
                            pass
            if last_close_dt is not None:
                until_dt = last_close_dt + timedelta(minutes=consecutive_loss_pause_minutes)
                if mt5_now >= until_dt:
                    pass  # Đã hết 5 phút từ lệnh thua cuối -> không pause
                else:
                    n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step=None)
                    set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time)
                    print(f"⏸️ [{strategy_name}] (DB) {consecutive_loss_count} lệnh thua liên tiếp → đã hủy {n_cancelled} lệnh chờ, tạm dừng {consecutive_loss_pause_minutes} phút (từ giờ đóng lệnh thua cuối).")
                    msg = f"⏸️ Grid Step tạm dừng giao dịch\nLý do: {consecutive_loss_count} lệnh thua liên tiếp.\nĐã hủy {n_cancelled} lệnh chờ (BUY STOP/SELL STOP).\nTạm dừng {consecutive_loss_pause_minutes} phút (tính từ giờ đóng lệnh thua cuối)."
                    send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
                    return error_count, 0
            else:
                n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step=None)
                set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time)
                print(f"⏸️ [{strategy_name}] (DB) {consecutive_loss_count} lệnh thua liên tiếp → đã hủy {n_cancelled} lệnh chờ, tạm dừng {consecutive_loss_pause_minutes} phút (từ giờ đóng lệnh thua cuối).")
                msg = f"⏸️ Grid Step tạm dừng giao dịch\nLý do: {consecutive_loss_count} lệnh thua liên tiếp.\nĐã hủy {n_cancelled} lệnh chờ (BUY STOP/SELL STOP).\nTạm dừng {consecutive_loss_pause_minutes} phút (tính từ giờ đóng lệnh thua cuối)."
                send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
                return error_count, 0

    # 3. Spread protection: so sánh theo GIÁ (price), tránh nhầm point (XAU point=0.001 → 252 points = 0.252)
    tick = mt5.symbol_info_tick(symbol)
    spread_price = (tick.ask - tick.bid) if tick else 0.0
    if spread_price > spread_max:
        if not hasattr(strategy_grid_step_logic, "_last_spread_log") or strategy_grid_step_logic._last_spread_log != round(spread_price, 4):
            print(f"⏸️ Spread={spread_price:.3f} > {spread_max} (bỏ qua đến khi spread nhỏ hơn)")
            strategy_grid_step_logic._last_spread_log = round(spread_price, 4)
        return error_count, 0
    # Grid step (giá) phải >= spread
    if grid_step_price < spread_price:
        if not hasattr(strategy_grid_step_logic, "_last_grid_log"):
            print(f"⚠️ Grid step (giá)={grid_step_price:.3f} quá nhỏ so với spread {spread_price:.3f}. Tăng grid_step_price trong config.")
            strategy_grid_step_logic._last_grid_log = True
        return error_count, 0

    # 4. Quy tắc: KHÔNG update lệnh chờ đang có. Chỉ đặt lệnh mới khi:
    #    - Chưa có lệnh chờ (0 pendings) → đặt cặp đầu tiên
    #    - Có position (vừa có lệnh khớp) → hủy lệnh chờ còn lại, đặt cặp mới quanh giá khớp
    if len(positions) >= max_positions:
        return error_count, 0

    # Đã có 2 lệnh chờ → không làm gì, chờ một lệnh được khớp (mở position)
    if len(pendings) == 2:
        return error_count, 0

    # Có ít nhất 1 position → hủy pending của step này, đặt cặp mới quanh anchor
    if positions:
        cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step_filter)
        current_price = get_grid_anchor_price(symbol, magic, step_filter)
    else:
        if pendings:
            cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step_filter)
        current_price = get_grid_anchor_price(symbol, magic, step_filter)

    # ref = mức grid gần giá nhất (round). VD giá 5110 → ref=5110 → BUY 5115, SELL 5105
    ref = round(current_price / grid_step_price) * grid_step_price
    ref = round(ref, info.digits)

    # BUY STOP = ref + 1 bước, SELL STOP = ref - 1 bước (đối xứng quanh ref)
    buy_price = round(ref + grid_step_price, info.digits)
    sell_price = round(ref - grid_step_price, info.digits)

    # Grid zone lock: không đặt nếu đã có position tại mức đó
    if position_at_level(positions, buy_price, point):
        return error_count, 0
    if position_at_level(positions, sell_price, point):
        return error_count, 0

    # Min distance: không đặt nếu quá gần position có sẵn
    for p in positions:
        if abs(p.price_open - buy_price) < min_distance or abs(p.price_open - sell_price) < min_distance:
            return error_count, 0

    # Cooldown grid level (theo step khi chạy nhiều step)
    cooldown_minutes = params.get('cooldown_minutes', 0)
    if cooldown_minutes > 0:
        cooldown_levels = load_cooldown_levels(cooldown_minutes)
        if is_level_in_cooldown(cooldown_levels, buy_price, cooldown_minutes, info.digits, step_filter) or is_level_in_cooldown(cooldown_levels, sell_price, cooldown_minutes, info.digits, step_filter):
            _log_key = (step_filter, buy_price, sell_price)
            if not hasattr(strategy_grid_step_logic, "_last_cooldown_log") or strategy_grid_step_logic._last_cooldown_log != _log_key:
                print(f"⏸️ Cooldown step={step_filter}: mức {buy_price}/{sell_price} trong {cooldown_minutes} phút, bỏ qua.")
                strategy_grid_step_logic._last_cooldown_log = _log_key
            return error_count, 0

    # SL/TP = sl_tp_price (bằng step cho kênh này). Không trailing.
    step_val = float(sl_tp_price)
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

    # BUY @ buy_price → TP = buy_price + step_val, SL = buy_price - step_val
    sl_buy = buy_price - step_val
    tp_buy = buy_price + step_val
    sl_sell = sell_price + step_val
    tp_sell = sell_price - step_val

    _step_label = step_filter if step_filter is not None else step_val
    print(f"📤 [step={_step_label}] BUY_STOP @ {buy_price} (SL={sl_buy}, TP={tp_buy}), SELL_STOP @ {sell_price} (SL={sl_sell}, TP={tp_sell})")
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
        print(f"✅ Grid step={_step_label}: BUY_STOP @ {buy_price:.2f}, SELL_STOP @ {sell_price:.2f} | ref={ref}")
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
    import os
    if len(sys.argv) > 1 and sys.argv[1].strip() == "--check-db":
        check_grid_step_v11_db()
        sys.exit(0)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_grid_step_v11.json")
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
        consecutive_loss_pause_enabled = params.get("consecutive_loss_pause_enabled", True)
        trading_hours = params.get("trading_hours")  # list of {"start": "HH:MM", "end": "HH:MM"}
        hours_summary = _trading_hours_summary(trading_hours)
        print(f"✅ Grid Step V11 Bot - Started ({label}) | Khung giờ BẬT (MT5): {hours_summary}")
        loop_count = 0
        try:
            while True:
                # Kiểm tra khung giờ (giờ server MT5): chỉ chạy logic khi BẬT
                symbol = config.get("symbol")
                mt5_now = get_mt5_time_utc(symbol) if symbol else datetime.now(timezone.utc)
                if not is_in_trading_hours_v11(mt5_now, trading_hours):
                    if loop_count % 30 == 0:
                        ts = mt5_now.strftime("%Y-%m-%d %H:%M") if hasattr(mt5_now, "strftime") else f"{mt5_now.hour:02d}:{mt5_now.minute:02d}"
                        print(f"⏸️ [V11] Ngoài khung giờ | Giờ MT5: {ts} → bỏ qua. BẬT: {hours_summary}")
                    loop_count += 1
                    time.sleep(1)
                    continue
                # Đồng bộ lệnh đã đóng từ MT5 vào DB
                if consecutive_loss_pause_enabled:
                    if steps_list is not None:
                        for step_val in steps_list:
                            sync_closed_orders_from_mt5(config, strategy_name=f"Grid_Step_V11_{step_val}")
                    else:
                        sync_closed_orders_from_mt5(config, strategy_name="Grid_Step_V11")
                if steps_list is not None:
                    for step_val in steps_list:
                        consecutive_errors, last_error_code = strategy_grid_step_logic(config, consecutive_errors, step=step_val)
                else:
                    consecutive_errors, last_error_code = strategy_grid_step_logic(config, consecutive_errors, step=None)
                loop_count += 1
                # Heartbeat mỗi ~30 giây (kèm khung giờ hiện tại)
                if loop_count % 30 == 0:
                    sym = config["symbol"]
                    mag = config["magic"]
                    mt5_time = get_mt5_time_utc(sym)
                    time_str = mt5_time.strftime("%Y-%m-%d %H:%M") if hasattr(mt5_time, "strftime") else ""
                    pos = mt5.positions_get(symbol=sym, magic=mag) or []
                    ords = mt5.orders_get(symbol=sym) or []
                    ords = [o for o in ords if o.magic == mag]
                    tick = mt5.symbol_info_tick(sym)
                    spread = (tick.ask - tick.bid) if tick else 0
                    steps_info = steps_list if steps_list else "1"
                    print(f"🔄 Grid Step V11 | Giờ MT5: {time_str} | Steps: {steps_info} | Positions: {len(pos)} | Pending: {len(ords)} | Spread: {spread:.2f} | Loop #{loop_count}")

                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Grid Step V11] 5 lỗi liên tiếp. Last: {error_msg}. Tạm dừng 2 phút..."
                    print(msg)
                    send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
                    time.sleep(120)
                    consecutive_errors = 0
                    continue

                time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 Grid Step V11 Bot Stopped")
            mt5.shutdown()
