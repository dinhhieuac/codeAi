"""
Grid Step Trading Bot - Theo tài liệu grid_step_trading_bot_strategy.md
Đặt 2 lệnh chờ (mặc định LIMIT): BUY LIMIT = ref − bước, SELL LIMIT = ref + bước (ref làm mức tham chiếu; MT5: BUY_LIMIT < ask, SELL_LIMIT > bid).
Tùy chọn `grid_pending_stop_enabled`: BUY STOP = ref + bước, SELL STOP = ref − bước; SL/TP vẫn entry ± bước như LIMIT.
Khi 1 lệnh kích hoạt → hủy lệnh còn lại, dịch grid, đặt cặp mới.
Không dùng indicator (EMA, ADX, RSI, Heiken Ashi...).
Có cooldown mức grid để giảm whipsaw sideways.
Tùy chọn: một lệnh đóng thua (MT5 history) → hủy toàn bộ pending, đóng mọi position cùng symbol/magic, tạm dừng X phút (single_loss_reset_*).
Mỗi lần start process: xóa pause kill cũ; không lặp kill cho cùng một lần đóng (last_handled). Deal quá cũ (history_max_age) bỏ qua.
single_loss_reset: bỏ qua thắng nhỏ 0 < profit < ignore_win_below (scan history), chỉ xét lệnh đủ “ý nghĩa” đầu tiên.

Khi ``grid_pending_stop_enabled`` và có position: ``pending_stop_float_gate_phase`` (grid_zone_reentry_fsm) — PnL nổi vs ``pending_stop_float_gate_x`` / ``_y`` (mặc định -1 / 1): yếu thì hủy pending không đặt; mạnh thì giữ/đặt lại cặp; vùng giữa thì không đặt mới nếu chưa có đủ 2 pending.
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
from utils import (
    load_config, connect_mt5, send_telegram, get_mt5_error_message,
    get_positions_bot, get_pending_orders_bot, cancel_pending_orders_bot,
    place_buy_limit, place_sell_limit, place_buy_stop, place_sell_stop,
    get_last_n_closed_profits_bot, get_last_n_closed_summaries_bot,
    get_closed_deals_bot, close_positions_bot,
)

from grid_zone_reentry_fsm import pending_stop_float_gate_phase

db = Database()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown.json")
PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause.json")
# Pause chung mọi step: khi bật single_loss_reset — tránh step khác vẫn giao dịch.
SINGLE_LOSS_RESET_PAUSE_STRATEGY_KEY = "Grid_Step_single_loss_kill"
_single_loss_session_bootstrapped = False
# Deal đóng (UTC) đã xử lý kill — tránh lặp mỗi vòng; reset khi bootstrap phiên.
_single_loss_last_handled_close_utc = None

# Optional: strategy_grid_step_v5 gán callable để ghi log khi đặt BUY_LIMIT/SELL_LIMIT thất bại (không import v5 ở đây).
log_pending_stop_attempt = None
# Optional: dict do caller gộp thêm (vd v5_role, grid_preview); đọc trong callback nếu cần.
grid_pending_stop_log_context = None


def _order_send_result_dict(r):
    if r is None:
        return None
    return {
        "retcode": int(getattr(r, "retcode", 0) or 0),
        "comment": str(getattr(r, "comment", "") or ""),
        "order": int(getattr(r, "order", 0) or 0),
    }


def _try_log_pending_stop_failure(payload):
    fn = log_pending_stop_attempt
    if not callable(fn):
        return
    try:
        line = dict(payload)
        ctx = grid_pending_stop_log_context
        if isinstance(ctx, dict) and ctx:
            line["log_context"] = ctx
        fn(line)
    except Exception:
        pass


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


def bootstrap_single_loss_reset_session(mt5_now, enabled, pause_minutes):
    """
    Một lần mỗi process khi bật single_loss_reset: reset last_handled, xóa pause kill cũ trong grid_pause.json.
    """
    global _single_loss_last_handled_close_utc, _single_loss_session_bootstrapped
    if not enabled or pause_minutes <= 0 or _single_loss_session_bootstrapped:
        return
    _single_loss_session_bootstrapped = True
    _single_loss_last_handled_close_utc = None
    state = load_pause_state(clean_expired=True, now_utc=mt5_now)
    if SINGLE_LOSS_RESET_PAUSE_STRATEGY_KEY in state:
        state.pop(SINGLE_LOSS_RESET_PAUSE_STRATEGY_KEY, None)
        save_pause_state(state)
    print("🔄 [single_loss_kill] Phiên bot mới: reset last_handled; pause kill cũ đã xóa (nếu có).")


def check_single_loss_should_trigger(
    symbol,
    magic,
    now_utc,
    history_max_age_minutes,
    last_handled_close_utc,
    min_loss_abs,
    ignore_win_below=1.0,
    history_scan_max=50,
):
    """
    MT5 history (GridStep*, mới → cũ): bỏ qua các lệnh **thắng** có 0 < profit < ignore_win_below;
    lệnh đóng đầu tiên còn lại dùng cho rule — chỉ trigger khi thua và |loss| > min_loss_abs,
    trong cửa history_max_age, close sau last_handled.
    """
    try:
        scan = int(history_scan_max)
    except (TypeError, ValueError):
        scan = 50
    if scan < 1:
        scan = 50
    rows = get_last_n_closed_summaries_bot(
        symbol, magic, scan, days_back=1, comment_prefix="GridStep"
    )
    try:
        min_abs = float(min_loss_abs)
    except (TypeError, ValueError):
        min_abs = 1.0
    if min_abs < 0:
        min_abs = 0.0
    try:
        ign = float(ignore_win_below)
    except (TypeError, ValueError):
        ign = 1.0

    now = now_utc
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        max_age = float(history_max_age_minutes)
    except (TypeError, ValueError):
        max_age = 1440.0
    if max_age <= 0:
        max_age = 1440.0
    cutoff = now - timedelta(minutes=max_age)

    chosen_net = None
    chosen_ts_str = None
    for net, ts_str in rows:
        p = float(net or 0)
        if ign > 0 and p > 0 and p < ign:
            continue
        chosen_net = p
        chosen_ts_str = ts_str
        break

    if chosen_net is None or not chosen_ts_str:
        return False, None, None
    # Chỉ reset khi thua đủ lớn
    if chosen_net >= -min_abs:
        return False, None, None

    last_close_dt = None
    try:
        last_close_dt = datetime.strptime(
            chosen_ts_str.strip(), "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    if last_close_dt is None:
        return False, None, None
    if last_close_dt < cutoff:
        return False, None, None
    if last_handled_close_utc is not None:
        lh = last_handled_close_utc
        if lh.tzinfo is None:
            lh = lh.replace(tzinfo=timezone.utc)
        if last_close_dt <= lh:
            return False, None, None
    return True, chosen_ts_str, last_close_dt


def sync_closed_orders_from_mt5(config, strategy_name=None):
    """Đồng bộ lệnh đã đóng từ MT5 history vào bảng orders (profit, close_time). Giúp kiểm tra consecutive loss ngay trong bot.
    strategy_name: nếu None thì dùng config.get('strategy_name','Grid_Step'); khi dùng steps thì gọi sync cho từng 'Grid_Step_{step}'."""
    closed = get_closed_deals_bot(config["symbol"], config["magic"], days_back=1, comment_prefix="GridStep")
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


def check_grid_step_db():
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
        cur.execute("SELECT COUNT(*) FROM grid_pending_orders WHERE strategy_name = 'Grid_Step'")
        n = cur.fetchone()[0]
        cur.execute("""
            SELECT status, COUNT(*) as c FROM grid_pending_orders WHERE strategy_name = 'Grid_Step'
            GROUP BY status
        """)
        by_status = {row['status']: row['c'] for row in cur.fetchall()}
        print(f"\n[grid_pending_orders] Grid_Step: {n} dong")
        for st, c in by_status.items():
            print(f"   - {st}: {c}")
        cur.execute("""
            SELECT ticket, order_type, price, status, position_ticket, placed_at, filled_at
            FROM grid_pending_orders WHERE strategy_name = 'Grid_Step'
            ORDER BY placed_at DESC LIMIT 5
        """)
        rows = cur.fetchall()
        if rows:
            print("   Moi nhat (toi da 5):")
            for r in rows:
                print(f"     ticket={r['ticket']} {r['order_type']} @ {r['price']} status={r['status']} position_ticket={r['position_ticket']} placed={r['placed_at']}")
    except sqlite3.OperationalError as e:
        print(f"\n[grid_pending_orders] Bang chua co hoac loi: {e}")

    # Bảng orders (Grid_Step)
    try:
        cur.execute("SELECT COUNT(*) FROM orders WHERE strategy_name = 'Grid_Step'")
        n_ord = cur.fetchone()[0]
        cur.execute("""
            SELECT ticket, order_type, volume, open_price, sl, tp, profit, open_time, comment
            FROM orders WHERE strategy_name = 'Grid_Step' ORDER BY open_time DESC LIMIT 5
        """)
        rows_ord = cur.fetchall()
        print(f"\n[orders] Grid_Step: {n_ord} dong")
        if rows_ord:
            for r in rows_ord:
                print(f"     ticket={r['ticket']} {r['order_type']} vol={r['volume']} price={r['open_price']} profit={r['profit']} time={r['open_time']}")
    except sqlite3.OperationalError as e:
        print(f"\n[orders] {e}")

    conn.close()
    print(f"{'='*60}\n")


def _comment_for_step(step):
    """Comment MT5 cho từng step. step=None = legacy single (GridStep)."""
    return "GridStep" if step is None else f"GridStep_{step}"


def get_positions_for_step(symbol, magic, step):
    """Lấy positions thuộc một step (filter theo comment). step=None = tất cả (backward compat)."""
    comment = None if step is None else _comment_for_step(step)
    return get_positions_bot(symbol, magic, comment=comment)


def get_grid_anchor_price(symbol, magic, step=None):
    """Lấy giá neo grid: giá mở của position mới nhất (theo thời gian). Nếu không có position thì dùng giá thị trường."""
    positions = get_positions_for_step(symbol, magic, step)
    if not positions:
        tick = mt5.symbol_info_tick(symbol)
        return (tick.bid + tick.ask) / 2.0
    latest = max(positions, key=lambda p: p.time)
    return float(latest.price_open)


def get_pending_orders(symbol, magic, step=None):
    """Lấy danh sách lệnh chờ (pending). step=None = tất cả; step=N chỉ lấy comment GridStep_N."""
    orders = mt5.orders_get(symbol=symbol)
    if not orders:
        return []
    orders = [o for o in orders if o.magic == magic]
    if step is not None:
        comment = _comment_for_step(step)
        orders = [o for o in orders if getattr(o, "comment", "") == comment]
    return orders


def cancel_all_pending(symbol, magic, strategy_name="Grid_Step", account_id=0, step=None):
    """Hủy lệnh chờ của strategy (hoặc chỉ lệnh của step nếu step != None); cập nhật DB = CANCELLED."""
    comment = None if step is None else _comment_for_step(step)
    orders = get_pending_orders_bot(symbol, magic, comment=comment)
    for o in orders:
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        db.update_grid_pending_status(o.ticket, "CANCELLED")
    return len(orders)


def sync_grid_pending_status(symbol, magic, strategy_name="Grid_Step", account_id=0, sl_tp_price=5.0, info=None, step=None):
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
    comment = None if step is None else _comment_for_step(step)
    return close_positions_bot(symbol, magic, comment=comment)


def strategy_grid_step_logic(config, error_count=0, step=None):
    """Chạy logic grid cho một step. step = giá trị bước (vd 5); step=None = chế độ cũ 1 step (strategy_name Grid_Step)."""
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    params = config.get('parameters', {})
    # step=None: backward compat (config chỉ có "step", không có "steps") → 1 kênh, strategy_name "Grid_Step"
    if step is None:
        step_val = float(params.get('step', 5) or 5)
        grid_step_price = step_val
        sl_tp_price = step_val
        strategy_name = "Grid_Step"
        step_filter = None  # không lọc theo comment
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
    grid_pending_stop_enabled = bool(params.get("grid_pending_stop_enabled", False))
    try:
        pending_stop_float_gate_x = float(params.get("pending_stop_float_gate_x", -1))
    except (TypeError, ValueError):
        pending_stop_float_gate_x = -1.0
    try:
        pending_stop_float_gate_y = float(params.get("pending_stop_float_gate_y", 1))
    except (TypeError, ValueError):
        pending_stop_float_gate_y = 1.0
    # Tạm dừng khi N lệnh thua liên tiếp: on/off + số lệnh + thời gian dừng (phút)
    consecutive_loss_pause_enabled = params.get('consecutive_loss_pause_enabled', True)
    consecutive_loss_count = params.get('consecutive_loss_count', 2)
    consecutive_loss_pause_minutes = params.get('consecutive_loss_pause_minutes', 5)
    single_loss_reset_enabled = params.get('single_loss_reset_enabled', False)
    single_loss_reset_pause_minutes = int(params.get('single_loss_reset_pause_minutes', 0) or 0)
    single_loss_reset_history_max_age_minutes = params.get('single_loss_reset_history_max_age_minutes', 1440)
    single_loss_reset_min_loss_abs = params.get('single_loss_reset_min_loss_abs', 1.0)
    single_loss_reset_ignore_win_below = params.get('single_loss_reset_ignore_win_below', 1.0)
    try:
        single_loss_reset_history_scan_max = int(params.get('single_loss_reset_history_scan_max', 50) or 50)
    except (TypeError, ValueError):
        single_loss_reset_history_scan_max = 50
    if single_loss_reset_history_scan_max < 1:
        single_loss_reset_history_scan_max = 50

    mt5_now = get_mt5_time_utc(symbol)
    bootstrap_single_loss_reset_session(mt5_now, single_loss_reset_enabled, single_loss_reset_pause_minutes)
    if single_loss_reset_enabled and single_loss_reset_pause_minutes > 0:
        if is_paused(SINGLE_LOSS_RESET_PAUSE_STRATEGY_KEY, now_utc=mt5_now):
            n_cancelled = cancel_all_pending(
                symbol, magic, strategy_name, config.get("account"), step=None
            )
            n_closed = close_all_positions(symbol, magic, step=None)
            if n_cancelled or n_closed:
                print(
                    f"🧹 [single_loss_kill] Đang pause -> đã dọn {n_cancelled} pending LIMIT, "
                    f"đóng {n_closed} position còn sót."
                )
            if not hasattr(strategy_grid_step_logic, "_last_sl_kill_log") or strategy_grid_step_logic._last_sl_kill_log != SINGLE_LOSS_RESET_PAUSE_STRATEGY_KEY:
                print(
                    f"⏸️ [single_loss_kill] Tạm dừng mọi step sau 1 lệnh thua — cửa sổ {single_loss_reset_pause_minutes} phút từ giờ đóng lệnh."
                )
                strategy_grid_step_logic._last_sl_kill_log = SINGLE_LOSS_RESET_PAUSE_STRATEGY_KEY
            remaining = get_pause_remaining(SINGLE_LOSS_RESET_PAUSE_STRATEGY_KEY, now_utc=mt5_now)
            if remaining is not None:
                mins = int(remaining.total_seconds() // 60)
                secs = int(remaining.total_seconds() % 60)
                print(f"⏸️ [single_loss_kill] Còn lại: {mins} phút {secs} giây")
            return error_count, 0
        strategy_grid_step_logic._last_sl_kill_log = None

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

    # 2c. Một lệnh đóng thua (history) → hủy toàn bộ pending + đóng mọi position (mọi step), pause chung X phút
    if single_loss_reset_enabled and single_loss_reset_pause_minutes > 0:
        global _single_loss_last_handled_close_utc
        react, last_close_ts, last_close_dt = check_single_loss_should_trigger(
            symbol,
            magic,
            mt5_now,
            single_loss_reset_history_max_age_minutes,
            _single_loss_last_handled_close_utc,
            single_loss_reset_min_loss_abs,
            single_loss_reset_ignore_win_below,
            single_loss_reset_history_scan_max,
        )
        if react and last_close_ts and last_close_dt is not None:
            if not is_paused(SINGLE_LOSS_RESET_PAUSE_STRATEGY_KEY, now_utc=mt5_now):
                n_cancelled = cancel_all_pending(
                    symbol, magic, strategy_name, config.get("account"), step=None
                )
                n_closed = close_all_positions(symbol, magic, step=None)
                set_paused(
                    SINGLE_LOSS_RESET_PAUSE_STRATEGY_KEY,
                    single_loss_reset_pause_minutes,
                    from_time=last_close_ts,
                )
                _single_loss_last_handled_close_utc = last_close_dt
                print(
                    f"🛑 [single_loss_kill] 1 lệnh thua (MT5 history, GridStep*) "
                    f"→ đã hủy {n_cancelled} pending, đóng {n_closed} position (mọi comment step). "
                    f"Pause {single_loss_reset_pause_minutes} phút từ giờ đóng lệnh."
                )
                msg = (
                    f"🛑 Grid Step — single_loss_kill ({symbol})\n"
                    f"1 lệnh đóng thua gần nhất (GridStep*).\n"
                    f"Hủy {n_cancelled} lệnh chờ, đóng {n_closed} vị thế.\n"
                    f"Tạm dừng {single_loss_reset_pause_minutes} phút từ giờ đóng lệnh thua."
                )
                send_telegram(msg, config.get("telegram_token"), config.get("telegram_chat_id"))
            return error_count, 0

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
        # Kiểm tra từ MT5 history theo cặp (mỗi vòng lặp) -> nếu N lệnh thua liên tiếp thì hủy hết lệnh chờ và pause
        profits, last_close_time_str = get_last_n_closed_profits_bot(symbol, magic, consecutive_loss_count, days_back=1, comment_prefix="GridStep")
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
                    msg = f"⏸️ Grid Step tạm dừng giao dịch\nLý do: {consecutive_loss_count} lệnh thua liên tiếp ({symbol}).\nĐã hủy {n_cancelled} lệnh chờ (BUY LIMIT/SELL LIMIT).\nTạm dừng {consecutive_loss_pause_minutes} phút (tính từ giờ đóng lệnh thua cuối)."
                    send_telegram(msg, config.get("telegram_token"), config.get("telegram_chat_id"))
                    return error_count, 0
            else:
                n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step=None)
                set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time_str)
                print(f"⏸️ [{strategy_name}] (history {symbol}) {consecutive_loss_count} lệnh thua liên tiếp → đã hủy {n_cancelled} lệnh chờ, tạm dừng {consecutive_loss_pause_minutes} phút.")
                msg = f"⏸️ Grid Step tạm dừng giao dịch\nLý do: {consecutive_loss_count} lệnh thua liên tiếp ({symbol}).\nĐã hủy {n_cancelled} lệnh chờ (BUY LIMIT/SELL LIMIT).\nTạm dừng {consecutive_loss_pause_minutes} phút (tính từ giờ đóng lệnh thua cuối)."
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
                    msg = f"⏸️ Grid Step tạm dừng giao dịch\nLý do: {consecutive_loss_count} lệnh thua liên tiếp.\nĐã hủy {n_cancelled} lệnh chờ (BUY LIMIT/SELL LIMIT).\nTạm dừng {consecutive_loss_pause_minutes} phút (tính từ giờ đóng lệnh thua cuối)."
                    send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
                    return error_count, 0
            else:
                n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step=None)
                set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time)
                print(f"⏸️ [{strategy_name}] (DB) {consecutive_loss_count} lệnh thua liên tiếp → đã hủy {n_cancelled} lệnh chờ, tạm dừng {consecutive_loss_pause_minutes} phút (từ giờ đóng lệnh thua cuối).")
                msg = f"⏸️ Grid Step tạm dừng giao dịch\nLý do: {consecutive_loss_count} lệnh thua liên tiếp.\nĐã hủy {n_cancelled} lệnh chờ (BUY LIMIT/SELL LIMIT).\nTạm dừng {consecutive_loss_pause_minutes} phút (tính từ giờ đóng lệnh thua cuối)."
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
    #    - Có position (LIMIT grid): hủy pending, đặt cặp mới quanh anchor
    #    - Có position + STOP grid: pending_stop_float_gate_phase (PnL vs x / y)
    if len(positions) >= max_positions:
        return error_count, 0

    if grid_pending_stop_enabled and positions:
        fpnl = total_profit(symbol, magic, step_filter)
        phase = pending_stop_float_gate_phase(
            fpnl, pending_stop_float_gate_x, pending_stop_float_gate_y
        )
        if phase == "weak":
            n_can = cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
            _wg = (step_filter, round(fpnl, 2), "weak")
            if not hasattr(strategy_grid_step_logic, "_ps_float_log") or strategy_grid_step_logic._ps_float_log != _wg:
                print(
                    f"⏸️ [pending_stop_float] [{strategy_name}] step={step_filter} float={fpnl:.2f} < x={pending_stop_float_gate_x:.2f} "
                    f"→ đã hủy {n_can} pending, không đặt mới."
                )
                strategy_grid_step_logic._ps_float_log = _wg
            return error_count, 0
        if phase == "neutral":
            strategy_grid_step_logic._ps_float_log = None
            if len(pendings) == 2:
                return error_count, 0
            if len(pendings) == 1:
                n_can = cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
                _wg = (step_filter, round(fpnl, 2), "neutral", 1)
                if not hasattr(strategy_grid_step_logic, "_ps_float_neutral_log") or strategy_grid_step_logic._ps_float_neutral_log != _wg:
                    print(
                        f"⏸️ [pending_stop_float] [{strategy_name}] step={step_filter} float={fpnl:.2f} trong [x={pending_stop_float_gate_x:.2f}, "
                        f"y={pending_stop_float_gate_y:.2f}] → 1 pending lệch, đã hủy {n_can}, không đặt mới."
                    )
                    strategy_grid_step_logic._ps_float_neutral_log = _wg
                return error_count, 0
            _wg0 = (step_filter, round(fpnl, 2), "neutral", 0)
            if not hasattr(strategy_grid_step_logic, "_ps_float_neutral_log0") or strategy_grid_step_logic._ps_float_neutral_log0 != _wg0:
                print(
                    f"⏸️ [pending_stop_float] [{strategy_name}] step={step_filter} float={fpnl:.2f} trong [x={pending_stop_float_gate_x:.2f}, "
                    f"y={pending_stop_float_gate_y:.2f}] → chưa có pending, chờ float > y để đặt cặp."
                )
                strategy_grid_step_logic._ps_float_neutral_log0 = _wg0
            return error_count, 0
        strategy_grid_step_logic._ps_float_log = None
        strategy_grid_step_logic._ps_float_neutral_log = None
        strategy_grid_step_logic._ps_float_neutral_log0 = None
        if len(pendings) == 2:
            return error_count, 0
        if len(pendings) == 1:
            cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
        current_price = get_grid_anchor_price(symbol, magic, step_filter)
    else:
        if len(pendings) == 2:
            return error_count, 0
        if positions:
            cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step_filter)
            current_price = get_grid_anchor_price(symbol, magic, step_filter)
        else:
            if pendings:
                cancel_all_pending(symbol, magic, strategy_name, config.get('account'), step_filter)
            current_price = get_grid_anchor_price(symbol, magic, step_filter)

    # ref = mức grid gần giá nhất (round). VD ref=4505, step=5:
    # LIMIT: BUY ref−step, SELL ref+step | STOP: BUY ref+step, SELL ref−step
    ref = round(current_price / grid_step_price) * grid_step_price
    ref = round(ref, info.digits)

    if grid_pending_stop_enabled:
        buy_price = round(ref + grid_step_price, info.digits)
        sell_price = round(ref - grid_step_price, info.digits)
    else:
        buy_price = round(ref - grid_step_price, info.digits)
        sell_price = round(ref + grid_step_price, info.digits)

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
    filling = mt5.ORDER_FILLING_IOC if (info.filling_mode & 2) else mt5.ORDER_FILLING_FOK
    comment = _comment_for_step(step_filter)
    sl_buy = buy_price - step_val
    tp_buy = buy_price + step_val
    sl_sell = sell_price + step_val
    tp_sell = sell_price - step_val

    _step_label = step_filter if step_filter is not None else step_val
    _buy_ot = "BUY_STOP" if grid_pending_stop_enabled else "BUY_LIMIT"
    _sell_ot = "SELL_STOP" if grid_pending_stop_enabled else "SELL_LIMIT"
    print(
        f"📤 [step={_step_label}] {_buy_ot} @ {buy_price} (SL={sl_buy}, TP={tp_buy}), "
        f"{_sell_ot} @ {sell_price} (SL={sl_sell}, TP={tp_sell}) | ref={ref}"
    )
    if grid_pending_stop_enabled:
        r1 = place_buy_stop(symbol, volume, buy_price, sl_buy, tp_buy, magic, comment, digits=info.digits, type_filling=filling)
        r2 = place_sell_stop(symbol, volume, sell_price, sl_sell, tp_sell, magic, comment, digits=info.digits, type_filling=filling)
    else:
        r1 = place_buy_limit(symbol, volume, buy_price, sl_buy, tp_buy, magic, comment, digits=info.digits, type_filling=filling)
        r2 = place_sell_limit(symbol, volume, sell_price, sl_sell, tp_sell, magic, comment, digits=info.digits, type_filling=filling)

    def _pending_fail_base(failure):
        le = mt5.last_error()
        if le and len(le) >= 2:
            le_out = {"code": int(le[0]), "message": str(le[1])}
        else:
            le_out = None
        return {
            "event": "pending_limit_pair_error",
            "ok": False,
            "failure": failure,
            "grid_pending_stop": grid_pending_stop_enabled,
            "symbol": symbol,
            "magic": magic,
            "strategy_name": strategy_name,
            "step_label": _step_label,
            "volume": volume,
            "ref": ref,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "sl_buy": sl_buy,
            "tp_buy": tp_buy,
            "sl_sell": sl_sell,
            "tp_sell": tp_sell,
            "buy_limit": _order_send_result_dict(r1),
            "sell_limit": _order_send_result_dict(r2),
            "mt5_last_error": le_out,
        }

    if r1 is None:
        err = mt5.last_error()
        print(f"❌ {_buy_ot} order_send lỗi: {err}")
        _try_log_pending_stop_failure(_pending_fail_base("buy_none"))
        return error_count + 1, getattr(err, 'code', 0)
    if r2 is None:
        err = mt5.last_error()
        print(f"❌ {_sell_ot} order_send lỗi: {err}")
        _try_log_pending_stop_failure(_pending_fail_base("sell_none"))
        return error_count + 1, getattr(err, 'code', 0)

    if r1.retcode == mt5.TRADE_RETCODE_DONE and r2.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Grid step={_step_label}: {_buy_ot} @ {buy_price:.2f}, {_sell_ot} @ {sell_price:.2f} | ref={ref}")
        if cooldown_minutes > 0:
            save_cooldown_levels([buy_price, sell_price], step_filter)
        acc = config.get('account')
        db.log_grid_pending(r1.order, strategy_name, symbol, _buy_ot, buy_price, sl_buy, tp_buy, volume, acc)
        db.log_grid_pending(r2.order, strategy_name, symbol, _sell_ot, sell_price, sl_sell, tp_sell, volume, acc)
        return 0, 0
    if r1.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ {_buy_ot} failed: {r1.retcode} {r1.comment}")
        p = _pending_fail_base("buy_retcode")
        p["mt5_last_error"] = None
        _try_log_pending_stop_failure(p)
        return error_count + 1, r1.retcode
    if r2.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ {_sell_ot} failed: {r2.retcode} {r2.comment}")
        p = _pending_fail_base("sell_retcode")
        p["mt5_last_error"] = None
        _try_log_pending_stop_failure(p)
        return error_count + 1, r2.retcode

    return error_count, 0


_GRID_STEP_LOOP_SLEEP_MIN = 0.001  # 1 ms


def grid_step_loop_sleep_seconds(params):
    """
    Sleep cuối mỗi vòng main loop (`python strategy_grid_step.py`).
    - `loop_interval_ms` > 0: dùng mili giây (ghi đè).
    - `loop_interval_unit` = `ms`: `loop_interval_seconds` là mili giây (vd 500 → 0.5s).
    - Mặc định: `loop_interval_seconds` là giây (float), mặc định 1 (như sleep cũ), tối thiểu 1 ms.
    """
    p = params or {}
    raw_ms = p.get("loop_interval_ms")
    if raw_ms is not None and str(raw_ms).strip() != "":
        try:
            ms = float(raw_ms)
            if ms > 0:
                return max(_GRID_STEP_LOOP_SLEEP_MIN, ms / 1000.0)
        except (TypeError, ValueError):
            pass
    unit = str(p.get("loop_interval_unit", "s") or "s").lower().strip()
    try:
        v = float(p.get("loop_interval_seconds", 1))
    except (TypeError, ValueError):
        v = 1.0
    if v <= 0:
        v = 1.0
    if unit in ("ms", "millisecond", "milliseconds"):
        return max(_GRID_STEP_LOOP_SLEEP_MIN, v / 1000.0)
    return max(_GRID_STEP_LOOP_SLEEP_MIN, v)


def _loop_interval_log_repr(sleep_s):
    if sleep_s < 1.0:
        return f"{sleep_s * 1000.0:.0f}ms"
    s = f"{sleep_s:.4f}".rstrip("0").rstrip(".")
    return f"{s}s"


def _format_last_two_closed_for_heartbeat(symbol, magic):
    """Chuỗi ngắn: 2 position đóng gần nhất (GridStep*), profit + giờ đóng UTC."""
    rows = get_last_n_closed_summaries_bot(symbol, magic, 2, days_back=1, comment_prefix="GridStep")
    if not rows:
        return "closed: —"
    parts = []
    for i, (net, ts) in enumerate(rows, start=1):
        parts.append(f"#{i} net={net:+.2f} @{ts}")
    return "closed: " + " | ".join(parts)


def _format_top_pending_heartbeat(orders, max_n=2):
    """Tóm tắt tối đa max_n lệnh chờ (type + giá + comment ngắn)."""
    if not orders:
        return "pend: —"
    bits = []
    for o in orders[:max_n]:
        ot = int(getattr(o, "type", -1))
        bl = getattr(mt5, "ORDER_TYPE_BUY_LIMIT", 2)
        slm = getattr(mt5, "ORDER_TYPE_SELL_LIMIT", 3)
        bs = getattr(mt5, "ORDER_TYPE_BUY_STOP", 4)
        ss = getattr(mt5, "ORDER_TYPE_SELL_STOP", 5)
        if ot == bl:
            tname = "BLIM"
        elif ot == slm:
            tname = "SLIM"
        elif ot == bs:
            tname = "BSTOP"
        elif ot == ss:
            tname = "SSTOP"
        else:
            tname = str(ot)
        px = float(getattr(o, "price_open", 0) or 0)
        cmt = (getattr(o, "comment", "") or "").strip()[:12]
        bits.append(f"{tname}@{px:.2f}" + (f"({cmt})" if cmt else ""))
    return "pend: " + ", ".join(bits)


def grid_step_loop_log_every_n(params):
    """
    In dòng 🔄 Grid Step mỗi N vòng (sau sleep trước đó, tức sau khi chạy logic).
    - Mặc định 30 (như cũ).
    - 1 = mỗi vòng.
    - 0 = tắt heartbeat (chỉ còn log từ strategy_grid_step_logic).
    """
    p = params or {}
    try:
        n = int(p.get("loop_log_every_n", 30))
    except (TypeError, ValueError):
        n = 30
    if n < 0:
        n = 30
    return n


if __name__ == "__main__":
    import os
    if len(sys.argv) > 1 and sys.argv[1].strip() == "--check-db":
        check_grid_step_db()
        sys.exit(0)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_grid_step_5min.json")
    config = load_config(config_path)

    consecutive_errors = 0

    if config and connect_mt5(config):
        params = config.get("parameters", {})
        loop_sleep_s = grid_step_loop_sleep_seconds(params)
        loop_log_every_n = grid_step_loop_log_every_n(params)
        if "steps" in params and params["steps"] is not None:
            steps_config = params["steps"]
            if not isinstance(steps_config, list):
                steps_config = [steps_config]
            steps_list = [float(s) for s in steps_config]
        else:
            steps_list = None  # legacy: 1 step từ "step", gọi logic với step=None
        label = f"steps: {steps_list}" if steps_list is not None else "single step (legacy)"
        consecutive_loss_pause_enabled = params.get("consecutive_loss_pause_enabled", True)
        log_n_txt = "off" if loop_log_every_n == 0 else f"every {loop_log_every_n} loop(s)"
        _pend_mode = "STOP" if bool(params.get("grid_pending_stop_enabled", False)) else "LIMIT"
        print(
            f"✅ Grid Step Bot - Started ({label}) | pending={_pend_mode} | loop_interval={_loop_interval_log_repr(loop_sleep_s)} "
            f"| loop_log={log_n_txt}"
        )
        loop_count = 0
        try:
            while True:
                # Đồng bộ lệnh đã đóng từ MT5 vào DB (profit, close_time) cho đúng strategy_name của từng step
                if consecutive_loss_pause_enabled:
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
                # Heartbeat: mỗi N vòng (loop_log_every_n; 0 = tắt)
                if loop_log_every_n > 0 and loop_count % loop_log_every_n == 0:
                    sym = config["symbol"]
                    mag = config["magic"]
                    pos = mt5.positions_get(symbol=sym, magic=mag) or []
                    ords = mt5.orders_get(symbol=sym) or []
                    ords = [o for o in ords if o.magic == mag]
                    tick = mt5.symbol_info_tick(sym)
                    spread = (tick.ask - tick.bid) if tick else 0
                    steps_info = steps_list if steps_list else "1"
                    last2 = _format_last_two_closed_for_heartbeat(sym, mag)
                    pend2 = _format_top_pending_heartbeat(ords, max_n=2)
                    print(
                        f"🔄 Grid Step | loop_interval={_loop_interval_log_repr(loop_sleep_s)} | "
                        f"Steps: {steps_info} | Positions: {len(pos)} | Pending: {len(ords)} | "
                        f"Spread: {spread:.2f} | {last2} | {pend2} | Loop #{loop_count}"
                    )

                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Grid Step] 5 lỗi liên tiếp. Last: {error_msg}. Tạm dừng 2 phút..."
                    print(msg)
                    send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
                    time.sleep(120)
                    consecutive_errors = 0
                    continue

                time.sleep(loop_sleep_s)
        except KeyboardInterrupt:
            print("🛑 Grid Step Bot Stopped")
            mt5.shutdown()
