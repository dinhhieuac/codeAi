"""
Grid Step Trading Bot - Theo tài liệu grid_step_trading_bot_strategy.md
Đặt 2 lệnh chờ: BUY STOP trên giá, SELL STOP dưới giá.
Khi 1 lệnh kích hoạt → hủy lệnh còn lại, dịch grid, đặt cặp mới.
Không dùng indicator (EMA, ADX, RSI, Heiken Ashi...).
"""
import MetaTrader5 as mt5
import time
import sys
sys.path.append('..')
from db import Database
from utils import load_config, connect_mt5, send_telegram, get_mt5_error_message

db = Database()


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


def sync_grid_pending_status(symbol, magic, strategy_name="Grid_Step", account_id=0):
    """Kiểm tra lệnh chờ trong DB: nếu ticket không còn trong MT5 orders → khớp hoặc hủy; cập nhật status."""
    pending_tickets = {o.ticket for o in get_pending_orders(symbol, magic)}
    positions = mt5.positions_get(symbol=symbol, magic=magic) or []
    info = mt5.symbol_info(symbol)
    digits = getattr(info, "digits", 2) if info else 2
    pos_by_price = {}
    for p in positions:
        key = round(float(p.price_open), digits)
        pos_by_price[key] = p
    for row in db.get_grid_pending_by_status(strategy_name, symbol, "PENDING"):
        ticket, order_type, price = row["ticket"], row["order_type"], row["price"]
        if ticket in pending_tickets:
            continue
        # Ticket không còn trong lệnh chờ → đã khớp hoặc bị hủy (ta đã CANCELLED khi gọi cancel_all)
        price_key = round(float(price), digits) if digits else round(float(price), 2)
        pos = pos_by_price.get(price_key)
        if pos:
            db.update_grid_pending_status(ticket, "FILLED", position_ticket=pos.ticket)
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
    min_distance_points = params.get('min_distance_points', 5)
    max_positions = config.get('max_positions', 5)
    target_profit = params.get('target_profit', 50.0)       # Basket TP (currency)
    spread_max = params.get('spread_max', 0.5)
    # SL/TP cố định theo giá (mặc định 5). Không tự động dời SL (no trailing).
    sl_tp_price = params.get('sl_tp_price', 5.0)

    info = mt5.symbol_info(symbol)
    if not info:
        return error_count, 0
    # Bước grid theo GIÁ (VD XAU: 5.0 → mức 5150, 5155, 5160, 5165...). Dùng grid_step_price (price) hoặc grid_step_points*point.
    grid_step_price = params.get('grid_step_price')
    if grid_step_price is not None:
        grid_step_price = float(grid_step_price)
    else:
        grid_step_points = params.get('grid_step_points', 500)
        grid_step_price = grid_step_points * info.point
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

    # Cập nhật status lệnh chờ trong DB: khớp (FILLED) hoặc hủy (CANCELLED)
    sync_grid_pending_status(symbol, magic, "Grid_Step", config.get('account'))

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
