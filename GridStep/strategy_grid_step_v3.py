"""
Grid Step Trading Bot V3 - Theo grid_step_trading_bot_strategy_v3.md (chiến lược tinh gọn)
Clone từ strategy_grid_step.py với 3 lớp chống whipsaw:
1. Re-entry lock sau SL (khóa cùng chiều + cùng mức entry)
2. Ref shift sau SL (flat không dùng mid, dùng ref_override)
3. Chop pause (pause khi phát hiện mẫu chop)
DB và comment: Grid_3_Step / Grid_3_Step_{step} để phân biệt bot khác.

Chi tiết triển khai (bước vào lệnh, state, ref_override, hủy pending): document/grid_step_entry_flow_summary.md
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
COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown.json")
PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause.json")
REF_SHIFT_FILE = os.path.join(SCRIPT_DIR, "grid_ref_shift_v3.json")
REENTRY_FILE = os.path.join(SCRIPT_DIR, "grid_reentry_v3.json")


def _sl_hit_tolerance(info, default=0.02):
    """Checklist §14: ngưỡng xác định hit SL theo symbol (point/spread), không hard-code 0.02 cho mọi market."""
    if not info:
        return default
    point = getattr(info, "point", 0.01) or 0.01
    return max(float(point) * 20, default)


# --- Re-entry lock (Lớp 1) ---
def _load_reentry_raw():
    if not os.path.exists(REENTRY_FILE):
        return {}
    try:
        with open(REENTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def _save_reentry(state_by_strategy):
    try:
        with open(REENTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(state_by_strategy, f, indent=2)
    except IOError:
        pass

def add_reentry_block(strategy_name, symbol, step_val, side, entry_price, sl_price, reason="SL"):
    """Thêm block: không đặt lại cùng chiều + cùng mức entry sau SL. Checklist §13: dedupe — không thêm nếu đã có block active cùng key."""
    raw = _load_reentry_raw()
    blocks = raw.get(strategy_name, [])
    entry_f = round(float(entry_price), 4)
    side_upper = side.upper()
    step_f = float(step_val)
    for b in blocks:
        if not b.get("active", True):
            continue
        if b.get("side", "").upper() != side_upper:
            continue
        if b.get("symbol") != symbol:
            continue
        if abs(float(b.get("step", 0)) - step_f) > 0.001:
            continue
        if abs(float(b.get("entry_price", 0)) - entry_f) <= 0.01:
            return
    sl_f = round(float(sl_price), 4)
    blocks.append({
        "symbol": symbol,
        "step": step_f,
        "side": side_upper,
        "entry_price": entry_f,
        "sl_price": sl_f,
        "unlock_price": round(sl_f - step_f, 4) if side_upper == "BUY" else round(sl_f + step_f, 4),
        "active": True,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "reason": reason,
    })
    raw[strategy_name] = blocks
    _save_reentry(raw)

def is_reentry_blocked(strategy_name, symbol, step_val, side, price, tolerance=0.01):
    """Checklist §8: so khớp strategy_name, symbol, step, side, entry_price. buy_price chỉ so block BUY, sell_price chỉ SELL."""
    raw = _load_reentry_raw()
    blocks = raw.get(strategy_name, [])
    step_f = float(step_val)
    for b in blocks:
        if not b.get("active", True):
            continue
        if b.get("side", "").upper() != side.upper():
            continue
        if b.get("symbol") != symbol:
            continue
        if abs(float(b.get("step", 0)) - step_f) > 0.001:
            continue
        if abs(float(b.get("entry_price", 0)) - float(price)) <= tolerance:
            return True
    return False

def refresh_reentry_blocks(strategy_name, bid, ask, step_val, reentry_unlock_steps=1):
    """Mở khóa block khi giá đã đi qua. Doc §4.5: BUY block unlock_price = SL - step, mở khi bid <= unlock_price; SELL unlock_price = SL + step, mở khi ask >= unlock_price."""
    raw = _load_reentry_raw()
    blocks = raw.get(strategy_name, [])
    step_f = float(step_val) * float(reentry_unlock_steps)
    changed = False
    for b in blocks:
        if not b.get("active", True):
            continue
        sl = float(b.get("sl_price", 0))
        side = b.get("side", "").upper()
        if side == "BUY" and bid <= sl - step_f:
            b["active"] = False
            changed = True
        elif side == "SELL" and ask >= sl + step_f:
            b["active"] = False
            changed = True
    if changed:
        raw[strategy_name] = [b for b in blocks if b.get("active", True)]
        _save_reentry(raw)

# --- Ref shift (Lớp 2) ---
def _load_ref_shift_raw():
    if not os.path.exists(REF_SHIFT_FILE):
        return {}
    try:
        with open(REF_SHIFT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def _save_ref_shift(state_by_strategy):
    try:
        with open(REF_SHIFT_FILE, "w", encoding="utf-8") as f:
            json.dump(state_by_strategy, f, indent=2)
    except IOError:
        pass

def get_ref_shift_state(strategy_name):
    raw = _load_ref_shift_raw()
    return raw.get(strategy_name)

PROCESSED_STOPOUT_MAX = 50


def set_ref_shift_state(strategy_name, step_val, last_stopout_side, last_stopout_entry, pending_ref_shift,
                        last_stopout_sl=None, last_stopout_time=None, last_processed_stopout_ticket=None,
                        processed_stopout_tickets=None):
    """Lưu state ref shift. processed_stopout_tickets: list ticket đã xử lý (giới hạn PROCESSED_STOPOUT_MAX) để không xử lý lặp."""
    raw = _load_ref_shift_raw()
    prev = raw.get(strategy_name) or {}
    raw[strategy_name] = {
        "step": step_val,
        "last_stopout_side": last_stopout_side,
        "last_stopout_entry": last_stopout_entry,
        "pending_ref_shift": pending_ref_shift,
    }
    if last_stopout_sl is not None:
        raw[strategy_name]["last_stopout_sl"] = last_stopout_sl
    if last_stopout_time is not None:
        raw[strategy_name]["last_stopout_time"] = last_stopout_time
    if processed_stopout_tickets is not None:
        raw[strategy_name]["processed_stopout_tickets"] = list(processed_stopout_tickets)[-PROCESSED_STOPOUT_MAX:]
    elif last_processed_stopout_ticket is not None:
        raw[strategy_name]["last_processed_stopout_ticket"] = last_processed_stopout_ticket
    elif prev.get("processed_stopout_tickets") is not None:
        raw[strategy_name]["processed_stopout_tickets"] = prev["processed_stopout_tickets"]
    elif prev.get("last_processed_stopout_ticket") is not None:
        raw[strategy_name]["last_processed_stopout_ticket"] = prev["last_processed_stopout_ticket"]
    _save_ref_shift(raw)

def compute_ref_override_and_use(strategy_name, step_val, digits):
    """Dùng ref_override khi flat và pending_ref_shift. Checklist §3: dùng last_stopout_sl đã lưu.
    BUY SL -> ref_override = last_stopout_sl - step; SELL SL -> ref_override = last_stopout_sl + step."""
    state = get_ref_shift_state(strategy_name)
    if not state or not state.get("pending_ref_shift"):
        return None, False
    side = state.get("last_stopout_side", "").upper()
    step_f = float(step_val)
    sl_stored = state.get("last_stopout_sl")
    if sl_stored is not None:
        try:
            sl_price = float(sl_stored)
        except (TypeError, ValueError):
            sl_price = None
    else:
        sl_price = None
    if sl_price is None:
        entry = float(state.get("last_stopout_entry", 0))
        sl_price = entry - step_f if side == "BUY" else entry + step_f
    if side == "BUY":
        ref_override = round(sl_price - step_f, digits)
    else:
        ref_override = round(sl_price + step_f, digits)
    set_ref_shift_state(strategy_name, step_val, state["last_stopout_side"], state["last_stopout_entry"], False)
    return ref_override, True

# --- Chop pause (Lớp 3) ---
def check_chop_and_pause(strategy_name, account_id, step_val, chop_window_trades, chop_loss_count,
                          chop_band_steps, chop_pause_minutes, require_exact):
    """Doc §2.4a: filter đúng strategy_name (+ account_id); không lấy chung theo symbol toàn cục."""
    if chop_pause_minutes <= 0 or chop_window_trades <= 0 or chop_loss_count <= 0:
        return False, None
    rows = db.get_last_closed_orders_with_entry(strategy_name, limit=chop_window_trades + 2, account_id=account_id)
    if require_exact and len(rows) < chop_window_trades:
        return False, None
    if len(rows) < chop_window_trades:
        return False, None
    window = rows[:chop_window_trades]
    loss_count = sum(1 for r in window if (r.get("profit") or 0) < 0)
    if loss_count < chop_loss_count:
        return False, None
    entries = [float(r.get("open_price") or 0) for r in window if r.get("open_price") is not None]
    if len(entries) < 2:
        return False, None
    band_width = chop_band_steps * float(step_val)
    if max(entries) - min(entries) > band_width:
        return False, None
    last_close_time = window[0].get("close_time")
    return True, last_close_time

# --- Cooldown, pause (chung) ---
def load_cooldown_levels(cooldown_minutes):
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

def _pause_until_from_value(val):
    """Checklist §7: đọc cả dạng cũ (chuỗi ISO) và dạng mới (object có paused_until, reason, meta)."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("paused_until") or val.get("until")
    return None


def load_pause_state(clean_expired=True, now_utc=None):
    """Checklist §7: hỗ trợ cả value là string ISO và object {paused_until, reason, meta}."""
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
    val = state.get(strategy_name)
    until = _pause_until_from_value(val)
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


def _format_pause_remaining(remaining):
    """Format timedelta thành chuỗi 'X phút' hoặc 'X phút Y giây'."""
    if remaining is None or remaining.total_seconds() <= 0:
        return ""
    total = int(remaining.total_seconds())
    mins, secs = total // 60, total % 60
    if secs == 0:
        return f"{mins} phút"
    return f"{mins} phút {secs} giây"


def set_paused(strategy_name, pause_minutes, from_time=None, reason=None, meta=None):
    """Ghi pause. reason/meta: lưu dạng object {paused_until, reason, meta} để log/debug (chop_detected, consecutive_loss, ...)."""
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
        elif isinstance(from_time, datetime) and from_time.tzinfo is None:
            from_time = from_time.replace(tzinfo=timezone.utc)
        until_dt = from_time + timedelta(minutes=pause_minutes)
    else:
        until_dt = datetime.now(timezone.utc) + timedelta(minutes=pause_minutes)
    until = until_dt.isoformat().replace("+00:00", "Z")
    if reason is not None or meta is not None:
        state[strategy_name] = {
            "paused_until": until,
            "reason": reason if reason is not None else "",
            "meta": meta if meta is not None else {},
        }
    else:
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
        return True, first_n[0].get("close_time")
    return False, None

def sync_closed_orders_from_mt5(config, strategy_name=None):
    closed = get_closed_from_mt5_history(config, days_back=1)
    if not closed:
        return 0
    sn = strategy_name if strategy_name is not None else config.get("strategy_name", "Grid_3_Step")
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
    path = db.db_path
    print(f"\n{'='*60}")
    print(f"[DB V3] path: {path}")
    if not os.path.exists(path):
        print("     File DB khong ton tai.")
        return
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM grid_pending_orders WHERE strategy_name LIKE 'Grid_3_Step%'")
        n = cur.fetchone()[0]
        cur.execute("SELECT status, COUNT(*) as c FROM grid_pending_orders WHERE strategy_name LIKE 'Grid_3_Step%' GROUP BY status")
        by_status = {row['status']: row['c'] for row in cur.fetchall()}
        print(f"\n[grid_pending_orders] Grid_3_Step*: {n} dong")
        for st, c in by_status.items():
            print(f"   - {st}: {c}")
    except sqlite3.OperationalError as e:
        print(f"\n[grid_pending_orders] {e}")
    try:
        cur.execute("SELECT COUNT(*) FROM orders WHERE strategy_name LIKE 'Grid_3_Step%'")
        n_ord = cur.fetchone()[0]
        cur.execute("SELECT ticket, order_type, volume, open_price, profit, open_time FROM orders WHERE strategy_name LIKE 'Grid_3_Step%' ORDER BY open_time DESC LIMIT 5")
        rows_ord = cur.fetchall()
        print(f"\n[orders] Grid_3_Step*: {n_ord} dong")
        if rows_ord:
            for r in rows_ord:
                print(f"     ticket={r['ticket']} {r['order_type']} price={r['open_price']} profit={r['profit']}")
    except sqlite3.OperationalError as e:
        print(f"\n[orders] {e}")
    conn.close()
    print(f"{'='*60}\n")

def _comment_for_step(step):
    """Checklist §6: thống nhất với strategy_name — Grid_3_Step / Grid_3_Step_{step}."""
    return "Grid_3_Step" if step is None else f"Grid_3_Step_{step}"

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

def cancel_all_pending(symbol, magic, strategy_name="Grid_3_Step", account_id=0, step=None):
    orders = get_pending_orders(symbol, magic, step)
    for o in orders:
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        db.update_grid_pending_status(o.ticket, "CANCELLED")
    return len(orders)

def sync_grid_pending_status(symbol, magic, strategy_name="Grid_3_Step", account_id=0, sl_tp_price=5.0, info=None, step=None):
    pending_tickets = {o.ticket for o in get_pending_orders(symbol, magic, step)}
    positions = get_positions_for_step(symbol, magic, step)
    info = info or mt5.symbol_info(symbol)
    digits = getattr(info, "digits", 2) if info else 2
    pos_by_price = {}
    for p in positions:
        key = round(float(p.price_open), digits)
        pos_by_price[key] = p
    step_f = float(sl_tp_price)
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
                sl, tp = round(entry - step_f, digits), round(entry + step_f, digits)
            else:
                sl, tp = round(entry + step_f, digits), round(entry - step_f, digits)
            if not db.order_exists(pos.ticket):
                db.log_order(
                    pos.ticket, strategy_name, symbol,
                    "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                    float(pos.volume), entry, sl, tp,
                    _comment_for_step(step), account_id
                )
            print(f"✅ [{strategy_name}] lệnh khớp: ticket={ticket} → position={pos.ticket} ({order_type} @ {price})")
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
    step_f = float(sl_tp_price)
    for pos in positions:
        entry = float(pos.price_open)
        sl, tp = float(pos.sl or 0), float(pos.tp or 0)
        if pos.type == mt5.ORDER_TYPE_BUY:
            want_sl = round(entry - step_f, info.digits)
            want_tp = round(entry + step_f, info.digits)
        else:
            want_sl = round(entry + step_f, info.digits)
            want_tp = round(entry - step_f, info.digits)
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
    """Logic V3: Grid_3_Step naming, re-entry lock, ref shift, chop pause, tối đa 2 pending hợp lệ (có thể 0/1/2)."""
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    params = config.get('parameters', {})
    if step is None:
        step_val = float(params.get('step', 5) or 5)
        grid_step_price = step_val
        sl_tp_price = step_val
        strategy_name = "Grid_3_Step"
        step_filter = None
    else:
        step = float(step)
        step_val = step
        grid_step_price = step
        sl_tp_price = step
        strategy_name = f"Grid_3_Step_{step}"
        step_filter = step

    min_distance_points = params.get('min_distance_points', 5)
    max_positions = config.get('max_positions', 5)
    target_profit = params.get('target_profit', 50.0)
    spread_max = params.get('spread_max', 0.5)
    cooldown_minutes = params.get('cooldown_minutes', 0)
    consecutive_loss_pause_enabled = params.get('consecutive_loss_pause_enabled', True)
    consecutive_loss_count = params.get('consecutive_loss_count', 3)
    consecutive_loss_pause_minutes = params.get('consecutive_loss_pause_minutes', 10)
    reentry_lock_enabled = params.get('reentry_lock_enabled', True)
    reentry_unlock_steps = params.get('reentry_unlock_steps', 1)
    post_sl_ref_shift_enabled = params.get('post_sl_ref_shift_enabled', True)
    chop_pause_enabled = params.get('chop_pause_enabled', True)
    chop_window_trades = params.get('chop_window_trades', 4)
    chop_loss_count = params.get('chop_loss_count', 3)
    chop_band_steps = params.get('chop_band_steps', 2)
    chop_pause_minutes = params.get('chop_pause_minutes', 15)
    chop_require_closed_count_exact = params.get('chop_require_closed_count_exact', True)

    info = mt5.symbol_info(symbol)
    if not info:
        return error_count, 0
    volume_min = getattr(info, 'volume_min', 0.01)
    volume_step = getattr(info, 'volume_step', 0.01)
    volume = max(float(volume), volume_min)
    if volume_step > 0:
        volume = round(volume / volume_step) * volume_step
        volume = max(volume, volume_min)
    point = info.point
    min_distance = min_distance_points * point
    digits = getattr(info, "digits", 2)
    account_id = config.get('account', 0)

    positions = get_positions_for_step(symbol, magic, step_filter)
    positions = list(positions)
    pendings = get_pending_orders(symbol, magic, step_filter)

    sync_grid_pending_status(symbol, magic, strategy_name, account_id, sl_tp_price, info, step_filter)
    ensure_position_sl_tp(symbol, magic, sl_tp_price, info, step_filter)

    # 1.4 Ghi nhận stop-out mới từ DB. Patch: xử lý tất cả stop-out chưa processed (limit=10), dùng processed_stopout_tickets.
    ref_state = get_ref_shift_state(strategy_name) or {}
    if reentry_lock_enabled or post_sl_ref_shift_enabled:
        rows = db.get_last_closed_orders_with_sl(strategy_name, limit=10, account_id=account_id)
        processed_tickets = list(ref_state.get("processed_stopout_tickets") or [])
        if not processed_tickets and ref_state.get("last_processed_stopout_ticket") is not None:
            processed_tickets = [ref_state["last_processed_stopout_ticket"]]
        for r in rows:
            stopout_ticket = r.get("ticket")
            if stopout_ticket is None or stopout_ticket in processed_tickets:
                continue
            if (r.get("profit") or 0) >= 0:
                continue
            close_price = r.get("close_price")
            sl = r.get("sl")
            sl_tolerance = _sl_hit_tolerance(info)
            if close_price is None or sl is None or abs(float(close_price) - float(sl)) > sl_tolerance:
                continue
            order_type = (r.get("order_type") or "").upper()
            side = "BUY" if "BUY" in order_type else "SELL"
            entry = float(r.get("open_price") or 0)
            sl_price = float(sl)
            close_time = r.get("close_time")
            if reentry_lock_enabled:
                add_reentry_block(strategy_name, symbol, step_val, side, entry, sl_price, reason="SL")
            processed_tickets.append(stopout_ticket)
            processed_tickets = processed_tickets[-PROCESSED_STOPOUT_MAX:]
            if post_sl_ref_shift_enabled:
                set_ref_shift_state(
                    strategy_name, step_val, side, entry, True,
                    last_stopout_sl=sl_price, last_stopout_time=close_time,
                    processed_stopout_tickets=processed_tickets
                )
            else:
                ref_state = get_ref_shift_state(strategy_name) or {}
                set_ref_shift_state(
                    strategy_name, step_val,
                    ref_state.get("last_stopout_side", ""), ref_state.get("last_stopout_entry", 0),
                    ref_state.get("pending_ref_shift", False),
                    last_stopout_sl=ref_state.get("last_stopout_sl"),
                    last_stopout_time=ref_state.get("last_stopout_time"),
                    processed_stopout_tickets=processed_tickets
                )

    # Basket TP
    profit = total_profit(symbol, magic, step_filter)
    if profit >= target_profit and positions:
        _step_label = step_filter if step_filter is not None else "single"
        print(f"✅ [BASKET TP V3] step={_step_label} Profit {profit:.2f} >= {target_profit}, đóng tất cả.")
        close_all_positions(symbol, magic, step_filter)
        cancel_all_pending(symbol, magic, strategy_name, account_id, step_filter)
        send_telegram(f"✅ [Grid_3_Step] Basket TP hit. Profit={profit:.2f}", config.get('telegram_token'), config.get('telegram_chat_id'))
        return 0, 0

    # Pause check
    if consecutive_loss_pause_enabled or chop_pause_enabled:
        mt5_now = get_mt5_time_utc(symbol)
        if is_paused(strategy_name, now_utc=mt5_now):
            if not hasattr(strategy_grid_step_logic, "_last_pause_v3") or strategy_grid_step_logic._last_pause_v3 != strategy_name:
                print(f"⏸️ [{strategy_name}] Đang tạm dừng.")
                strategy_grid_step_logic._last_pause_v3 = strategy_name
            return error_count, 0
        if chop_pause_enabled and chop_pause_minutes > 0:
            did_chop, chop_close_time = check_chop_and_pause(
                strategy_name, account_id, step_val,
                chop_window_trades, chop_loss_count, chop_band_steps,
                chop_pause_minutes, chop_require_closed_count_exact
            )
            if did_chop:
                cancel_all_pending(symbol, magic, strategy_name, account_id, step_filter)
                # Pause từ thời điểm hiện tại (mt5_now), không từ chop_close_time, để paused_until luôn trong tương lai và is_paused() đúng
                set_paused(
                    strategy_name, chop_pause_minutes, from_time=mt5_now,
                    reason="chop_detected",
                    meta={"window_trades": chop_window_trades, "loss_count": chop_loss_count, "band_steps": chop_band_steps, "chop_close_time": chop_close_time},
                )
                remaining = get_pause_remaining(strategy_name, now_utc=mt5_now)
                remain_str = _format_pause_remaining(remaining) if remaining else f"{chop_pause_minutes} phút"
                print(f"⏸️ [{strategy_name}] Chop Pause → tạm dừng {chop_pause_minutes} phút (còn {remain_str}).")
                send_telegram(f"⏸️ [{strategy_name}] Chop Pause. Còn {remain_str}.", config.get("telegram_token"), config.get("telegram_chat_id"))
                return error_count, 0

    if consecutive_loss_pause_enabled and consecutive_loss_pause_minutes > 0 and consecutive_loss_count > 0:
        mt5_now = get_mt5_time_utc(symbol)
        if is_paused(strategy_name, now_utc=mt5_now):
            return error_count, 0
        profits, last_close_time_str = get_last_n_closed_profits_by_symbol(symbol, magic, consecutive_loss_count, days_back=1)
        if len(profits) >= consecutive_loss_count and all((p or 0) < 0 for p in profits):
            last_close_dt = None
            if last_close_time_str:
                try:
                    last_close_dt = datetime.strptime(last_close_time_str.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            if last_close_dt is None or mt5_now < last_close_dt + timedelta(minutes=consecutive_loss_pause_minutes):
                cancel_all_pending(symbol, magic, strategy_name, account_id, step_filter)
                set_paused(
                    strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time_str,
                    reason="consecutive_loss",
                    meta={"count": consecutive_loss_count},
                )
                send_telegram(f"⏸️ [Grid_3_Step] Tạm dừng ({consecutive_loss_count} lệnh thua liên tiếp).", config.get("telegram_token"), config.get("telegram_chat_id"))
                return error_count, 0
        did_pause, last_close_time = check_consecutive_losses_and_pause(strategy_name, account_id, consecutive_loss_count, consecutive_loss_pause_minutes)
        if did_pause:
            cancel_all_pending(symbol, magic, strategy_name, account_id, step_filter)
            set_paused(
                strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time,
                reason="consecutive_loss",
                meta={"count": consecutive_loss_count},
            )
            return error_count, 0

    # Spread. Checklist §5: bảo vệ tick is None (tránh crash khi refresh_reentry_blocks)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return error_count, 0
    spread_price = (tick.ask - tick.bid)
    if spread_price > spread_max:
        return error_count, 0
    if grid_step_price < spread_price:
        return error_count, 0

    if len(positions) >= max_positions:
        return error_count, 0

    # Ref: có position -> anchor từ position. Flat -> ref_override hoặc ổn định ref từ pending (tránh đổi ref mỗi tick khiến hủy/đặt lại liên tục, lệnh không khớp).
    def _order_price(ord):
        return float(getattr(ord, "price_open", 0) or getattr(ord, "price", 0))

    if positions:
        current_price = get_grid_anchor_price(symbol, magic, step_filter)
        ref = round(current_price / grid_step_price) * grid_step_price
        ref = round(ref, digits)
        buy_price = round(ref + grid_step_price, digits)
        sell_price = round(ref - grid_step_price, digits)
    else:
        ref_override_val, used_override = compute_ref_override_and_use(strategy_name, step_val, digits)
        if used_override:
            ref = round(ref_override_val / grid_step_price) * grid_step_price
            ref = round(ref, digits)
            buy_price = round(ref + grid_step_price, digits)
            sell_price = round(ref - grid_step_price, digits)
        elif pendings:
            # Đã có pending: giữ ref từ pending, không lấy mid mỗi tick → tránh hủy/đặt lại liên tục, cho phép lệnh khớp
            ref_from_pending = None
            for o in pendings:
                op = _order_price(o)
                if op <= 0:
                    continue
                if o.type == mt5.ORDER_TYPE_BUY_STOP:
                    ref_from_pending = round(op - grid_step_price, digits)
                    break
                if o.type == mt5.ORDER_TYPE_SELL_STOP:
                    ref_from_pending = round(op + grid_step_price, digits)
                    break
            if ref_from_pending is not None:
                ref = ref_from_pending
                buy_price = round(ref + grid_step_price, digits)
                sell_price = round(ref - grid_step_price, digits)
            else:
                current_price = get_grid_anchor_price(symbol, magic, step_filter)
                ref = round(current_price / grid_step_price) * grid_step_price
                ref = round(ref, digits)
                buy_price = round(ref + grid_step_price, digits)
                sell_price = round(ref - grid_step_price, digits)
        else:
            current_price = get_grid_anchor_price(symbol, magic, step_filter)
            ref = round(current_price / grid_step_price) * grid_step_price
            ref = round(ref, digits)
            buy_price = round(ref + grid_step_price, digits)
            sell_price = round(ref - grid_step_price, digits)

    # Checklist §11: Thứ tự đúng spec — zone lock → min distance → re-entry block → cooldown
    buy_allowed = True
    buy_reason = []
    if position_at_level(positions, buy_price, point):
        buy_allowed = False
        buy_reason.append("zone_lock")
    for p in positions:
        if abs(p.price_open - buy_price) < min_distance:
            buy_allowed = False
            buy_reason.append("min_distance")
            break
    if buy_allowed and reentry_lock_enabled and is_reentry_blocked(strategy_name, symbol, step_val, "BUY", buy_price):
        buy_allowed = False
        buy_reason.append("reentry_block")
    if cooldown_minutes > 0:
        cooldown_levels = load_cooldown_levels(cooldown_minutes)
        if is_level_in_cooldown(cooldown_levels, buy_price, cooldown_minutes, digits, step_filter):
            buy_allowed = False
            buy_reason.append("cooldown")

    sell_allowed = True
    sell_reason = []
    if position_at_level(positions, sell_price, point):
        sell_allowed = False
        sell_reason.append("zone_lock")
    for p in positions:
        if abs(p.price_open - sell_price) < min_distance:
            sell_allowed = False
            sell_reason.append("min_distance")
            break
    if sell_allowed and reentry_lock_enabled and is_reentry_blocked(strategy_name, symbol, step_val, "SELL", sell_price):
        sell_allowed = False
        sell_reason.append("reentry_block")
    if cooldown_minutes > 0:
        cooldown_levels = load_cooldown_levels(cooldown_minutes)
        if is_level_in_cooldown(cooldown_levels, sell_price, cooldown_minutes, digits, step_filter):
            sell_allowed = False
            sell_reason.append("cooldown")

    # Doc §5.6: Chỉ hủy pending khi có lý do rõ ràng (không còn hợp lệ / mức khác / bị block), không hủy vì thiếu cặp
    for o in pendings:
        op = _order_price(o)
        if o.type == mt5.ORDER_TYPE_BUY_STOP:
            if not buy_allowed or abs(op - buy_price) > 0.01:
                mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
                db.update_grid_pending_status(o.ticket, "CANCELLED")
        else:
            if not sell_allowed or abs(op - sell_price) > 0.01:
                mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
                db.update_grid_pending_status(o.ticket, "CANCELLED")

    # Doc §5.7: Kiểm tra đã có pending đúng mức đó chưa. Checklist §10: sau hủy pending phải refresh pendings (đã có ở trên).
    pendings = get_pending_orders(symbol, magic, step_filter)
    has_buy_pending = any(o.type == mt5.ORDER_TYPE_BUY_STOP and abs(_order_price(o) - buy_price) < 0.01 for o in pendings)
    has_sell_pending = any(o.type == mt5.ORDER_TYPE_SELL_STOP and abs(_order_price(o) - sell_price) < 0.01 for o in pendings)
    if not buy_allowed and buy_reason:
        print(f"   [{strategy_name}] BUY @ {buy_price} blocked: {', '.join(buy_reason)}")
    if not sell_allowed and sell_reason:
        print(f"   [{strategy_name}] SELL @ {sell_price} blocked: {', '.join(sell_reason)}")
    if buy_allowed and has_buy_pending and sell_allowed and has_sell_pending:
        if tick is not None:
            refresh_reentry_blocks(strategy_name, tick.bid, tick.ask, step_val, reentry_unlock_steps)
        return error_count, 0
    if not buy_allowed and not sell_allowed:
        if tick is not None:
            refresh_reentry_blocks(strategy_name, tick.bid, tick.ask, step_val, reentry_unlock_steps)
        return error_count, 0

    step_val_f = float(sl_tp_price)
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

    sl_buy = buy_price - step_val_f
    tp_buy = buy_price + step_val_f
    sl_sell = sell_price + step_val_f
    tp_sell = sell_price - step_val_f

    placed = 0
    if buy_allowed and not has_buy_pending:
        r1 = place_pending(mt5.ORDER_TYPE_BUY_STOP, buy_price, sl_buy, tp_buy)
        if r1 and r1.retcode == mt5.TRADE_RETCODE_DONE:
            db.log_grid_pending(r1.order, strategy_name, symbol, "BUY_STOP", buy_price, sl_buy, tp_buy, volume, account_id)
            placed += 1
            if cooldown_minutes > 0:
                save_cooldown_levels([buy_price], step_filter)
        elif r1:
            print(f"❌ BUY_STOP failed: {r1.retcode} {r1.comment}")
            return error_count + 1, r1.retcode
    if sell_allowed and not has_sell_pending:
        r2 = place_pending(mt5.ORDER_TYPE_SELL_STOP, sell_price, sl_sell, tp_sell)
        if r2 and r2.retcode == mt5.TRADE_RETCODE_DONE:
            db.log_grid_pending(r2.order, strategy_name, symbol, "SELL_STOP", sell_price, sl_sell, tp_sell, volume, account_id)
            placed += 1
            if cooldown_minutes > 0:
                save_cooldown_levels([sell_price], step_filter)
        elif r2:
            print(f"❌ SELL_STOP failed: {r2.retcode} {r2.comment}")
            return error_count + 1, r2.retcode

    if tick is not None:
        refresh_reentry_blocks(strategy_name, tick.bid, tick.ask, step_val, reentry_unlock_steps)
    _step_label = step_filter if step_filter is not None else step_val
    if placed > 0:
        print(f"✅ [{strategy_name}] step={_step_label}: placed {placed} pending(s) | ref={ref} buy_allowed={buy_allowed} sell_allowed={sell_allowed}")
    return 0, 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].strip() == "--check-db":
        check_grid_step_db()
        sys.exit(0)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_grid_step_v3.json")
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
        print(f"✅ [Grid_3_Step] Bot started ({label})")
        loop_count = 0
        try:
            while True:
                if steps_list is not None:
                    for step_val in steps_list:
                        sync_closed_orders_from_mt5(config, strategy_name=f"Grid_3_Step_{step_val}")
                else:
                    sync_closed_orders_from_mt5(config, strategy_name="Grid_3_Step")
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
                    print(f"🔄 [Grid_3_Step] Steps: {steps_info} | Positions: {len(pos)} | Pending: {len(ords)} | Spread: {spread:.2f} | Loop #{loop_count}")

                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Grid_3_Step] 5 lỗi liên tiếp. Last: {error_msg}. Tạm dừng 2 phút..."
                    print(msg)
                    send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
                    time.sleep(120)
                    consecutive_errors = 0
                    continue

                time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 [Grid_3_Step] Bot stopped")
            mt5.shutdown()
