"""
Grid Step Trading Bot - Theo tài liệu grid_step_trading_bot_strategy.md
Đặt 2 lệnh chờ: BUY STOP trên giá, SELL STOP dưới giá.
Khi 1 lệnh kích hoạt → hủy lệnh còn lại, dịch grid, đặt cặp mới.
Không dùng indicator (EMA, ADX, RSI, Heiken Ashi...).
Có cooldown mức grid để giảm whipsaw sideways.
"""
import MetaTrader5 as mt5
import time
import sys
import sqlite3
import os
import json
from datetime import datetime, timedelta
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, send_telegram, get_mt5_error_message

db = Database()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown.json")


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


def save_cooldown_levels(level_keys_to_add):
    """Ghi thêm các mức level (với thời gian hiện tại) vào file cooldown."""
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
        levels[str(key)] = now
    data["levels"] = levels
    try:
        with open(COOLDOWN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError:
        pass


def is_level_in_cooldown(levels_dict, price, cooldown_minutes, digits=2):
    """Kiểm tra mức giá price có đang trong cooldown không."""
    if cooldown_minutes <= 0:
        return False
    key = str(round(float(price), digits))
    return key in levels_dict


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


def get_grid_anchor_price(symbol, magic):
    """Lấy giá neo grid: giá mở của position mới nhất (theo thời gian). Nếu không có position thì dùng giá thị trường."""
    positions = mt5.positions_get(symbol=symbol, magic=magic)
    if not positions:
        tick = mt5.symbol_info_tick(symbol)
        return (tick.bid + tick.ask) / 2.0
    # Position mới nhất
    latest = max(positions, key=lambda p: p.time)
    return float(latest.price_open)


def get_pending_orders(symbol, magic):
    """Lấy danh sách lệnh chờ (pending) của bot."""
    orders = mt5.orders_get(symbol=symbol)
    if not orders:
        return []
    return [o for o in orders if o.magic == magic]


def cancel_all_pending(symbol, magic, strategy_name="Grid_Step", account_id=0):
    """Hủy tất cả lệnh chờ của strategy; cập nhật DB status = CANCELLED."""
    orders = get_pending_orders(symbol, magic)
    for o in orders:
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        db.update_grid_pending_status(o.ticket, "CANCELLED")
    return len(orders)


def sync_grid_pending_status(symbol, magic, strategy_name="Grid_Step", account_id=0, sl_tp_price=5.0, info=None):
    """Kiểm tra lệnh chờ trong DB: nếu ticket không còn trong MT5 orders → khớp hoặc hủy; cập nhật status.
    Khi lệnh khớp → ghi vào bảng orders với SL/TP đúng (entry ± sl_tp_price), không dùng 0 từ position."""
    pending_tickets = {o.ticket for o in get_pending_orders(symbol, magic)}
    positions = mt5.positions_get(symbol=symbol, magic=magic) or []
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


def total_profit(symbol, magic):
    """Tổng lợi nhuận (floating) của tất cả position thuộc strategy."""
    positions = mt5.positions_get(symbol=symbol, magic=magic)
    if not positions:
        return 0.0
    return sum(p.profit + p.swap + getattr(p, 'commission', 0) for p in positions)


def ensure_position_sl_tp(symbol, magic, sl_tp_price, info):
    """Đặt lại SL/TP = 5 (giá) cho position nếu đang 0 (broker không kế thừa từ lệnh chờ)."""
    positions = mt5.positions_get(symbol=symbol, magic=magic) or []
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


def close_all_positions(symbol, magic):
    """Đóng tất cả position của strategy (Basket Take Profit)."""
    positions = mt5.positions_get(symbol=symbol, magic=magic)
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


def strategy_grid_step_logic(config, error_count=0):
    symbol = config['symbol']
    volume = config['volume']
    magic = config['magic']
    params = config.get('parameters', {})
    # step: cấu hình 1 giá trị dùng chung cho grid và SL/TP (vd 3, 5, 6, 7...). Có thể ghi đè bằng grid_step_price / sl_tp_price.
    step_cfg = params.get('step', 5)
    step_default = float(step_cfg) if step_cfg is not None else 5.0
    min_distance_points = params.get('min_distance_points', 5)
    max_positions = config.get('max_positions', 5)
    target_profit = params.get('target_profit', 50.0)       # Basket TP (currency)
    spread_max = params.get('spread_max', 0.5)
    sl_tp_price = params.get('sl_tp_price')
    if sl_tp_price is not None:
        sl_tp_price = float(sl_tp_price)
    else:
        sl_tp_price = step_default

    info = mt5.symbol_info(symbol)
    if not info:
        return error_count, 0
    # Bước grid theo GIÁ (VD step=5 → 5150, 5155, 5160...). Ưu tiên grid_step_price, không có thì dùng step, cuối cùng grid_step_points*point.
    grid_step_price = params.get('grid_step_price')
    if grid_step_price is not None:
        grid_step_price = float(grid_step_price)
    else:
        grid_step_points = params.get('grid_step_points')
        if grid_step_points is not None:
            grid_step_price = grid_step_points * info.point
        else:
            grid_step_price = step_default
    # XAU min lot = 0.01
    volume_min = getattr(info, 'volume_min', 0.01)
    volume_step = getattr(info, 'volume_step', 0.01)
    volume = max(float(volume), volume_min)
    if volume_step > 0:
        volume = round(volume / volume_step) * volume_step
        volume = max(volume, volume_min)
    point = info.point
    min_distance = min_distance_points * point

    # 1. Lấy positions và pending
    positions = mt5.positions_get(symbol=symbol, magic=magic)
    positions = list(positions or [])
    pendings = get_pending_orders(symbol, magic)

    # Cập nhật status lệnh chờ trong DB: khớp (FILLED) hoặc hủy (CANCELLED); ghi orders với SL/TP đúng
    sync_grid_pending_status(symbol, magic, "Grid_Step", config.get('account'), sl_tp_price, info)

    # Đặt lại SL/TP = 5 (giá) cho position nếu broker không kế thừa từ lệnh chờ (SL/TP đang 0)
    ensure_position_sl_tp(symbol, magic, sl_tp_price, info)

    # 2. Basket Take Profit
    profit = total_profit(symbol, magic)
    if profit >= target_profit and positions:
        print(f"✅ [BASKET TP] Profit {profit:.2f} >= {target_profit}, đóng tất cả.")
        close_all_positions(symbol, magic)
        cancel_all_pending(symbol, magic, "Grid_Step", config.get('account'))
        msg = f"✅ Grid Step: Basket TP hit. Profit={profit:.2f} | Closed all."
        send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
        return 0, 0

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

    # Có ít nhất 1 position → vừa có lệnh khớp: hủy hết pending, đặt cặp mới quanh anchor = giá position mới nhất
    if positions:
        cancel_all_pending(symbol, magic, "Grid_Step", config.get('account'))
        current_price = get_grid_anchor_price(symbol, magic)  # giá mở của position mới nhất
    else:
        # 0 position, 0 hoặc 1 pending: đặt cặp mới (hoặc cặp đầu tiên)
        if pendings:
            cancel_all_pending(symbol, magic, "Grid_Step", config.get('account'))  # dọn pending lẻ (1 cái)
        current_price = get_grid_anchor_price(symbol, magic)  # giá thị trường

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

    # Cooldown grid level: không trade lại cùng mức trong X phút (giảm whipsaw sideways)
    cooldown_minutes = params.get('cooldown_minutes', 0)
    if cooldown_minutes > 0:
        cooldown_levels = load_cooldown_levels(cooldown_minutes)
        if is_level_in_cooldown(cooldown_levels, buy_price, cooldown_minutes, info.digits) or is_level_in_cooldown(cooldown_levels, sell_price, cooldown_minutes, info.digits):
            if not hasattr(strategy_grid_step_logic, "_last_cooldown_log") or strategy_grid_step_logic._last_cooldown_log != (buy_price, sell_price):
                print(f"⏸️ Cooldown: mức {buy_price}/{sell_price} vừa dùng trong {cooldown_minutes} phút, bỏ qua đặt lệnh.")
                strategy_grid_step_logic._last_cooldown_log = (buy_price, sell_price)
            return error_count, 0

    # SL/TP = sl_tp_price (mặc định 5 giá). Không trailing, không breakeven.
    step = float(sl_tp_price)
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
            "comment": "GridStep",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        return mt5.order_send(req)

    # BUY @ buy_price → TP = buy_price + step, SL = buy_price - step
    # SELL @ sell_price → TP = sell_price - step, SL = sell_price + step
    sl_buy = buy_price - step
    tp_buy = buy_price + step
    sl_sell = sell_price + step
    tp_sell = sell_price - step

    print(f"📤 Đặt lệnh: BUY_STOP @ {buy_price} (SL={sl_buy}, TP={tp_buy}), SELL_STOP @ {sell_price} (SL={sl_sell}, TP={tp_sell})")
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
        print(f"✅ Grid: BUY_STOP @ {buy_price:.2f}, SELL_STOP @ {sell_price:.2f} | ref={ref}")
        if cooldown_minutes > 0:
            save_cooldown_levels([buy_price, sell_price])
        acc = config.get('account')
        db.log_grid_pending(r1.order, "Grid_Step", symbol, "BUY_STOP", buy_price, sl_buy, tp_buy, volume, acc)
        db.log_grid_pending(r2.order, "Grid_Step", symbol, "SELL_STOP", sell_price, sl_sell, tp_sell, volume, acc)
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
        check_grid_step_db()
        sys.exit(0)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_grid_step.json")
    config = load_config(config_path)

    consecutive_errors = 0

    if config and connect_mt5(config):
        print("✅ Grid Step Bot - Started")
        loop_count = 0
        try:
            while True:
                consecutive_errors, last_error_code = strategy_grid_step_logic(config, consecutive_errors)
                loop_count += 1
                # Heartbeat mỗi ~30 giây: trạng thái positions + pendings
                if loop_count % 30 == 0:
                    sym = config["symbol"]
                    mag = config["magic"]
                    pos = mt5.positions_get(symbol=sym, magic=mag) or []
                    ords = mt5.orders_get(symbol=sym) or []
                    ords = [o for o in ords if o.magic == mag]
                    tick = mt5.symbol_info_tick(sym)
                    spread = (tick.ask - tick.bid) if tick else 0
                    print(f"🔄 Grid Step | Positions: {len(pos)} | Pending: {len(ords)} | Spread: {spread:.2f} | Loop #{loop_count}")

                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Grid Step] 5 lỗi liên tiếp. Last: {error_msg}. Tạm dừng 2 phút..."
                    print(msg)
                    send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'))
                    time.sleep(120)
                    consecutive_errors = 0
                    continue

                time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 Grid Step Bot Stopped")
            mt5.shutdown()
