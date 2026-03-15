"""
Grid Step – logic dùng chung cho strategy_grid_step.py, strategy_grid_step_btc.py, ...
Kiểm tra history MT5 theo cặp (symbol + magic) trước khi đặt BUY_STOP/SELL_STOP.
"""
import MetaTrader5 as mt5
from datetime import datetime, timedelta

# Bật log debug cho consecutive loss / history. Set False để tắt.
DEBUG_HISTORY = False


def get_last_n_closed_profits_by_symbol(symbol, magic, n, days_back=1):
    """Lấy N lệnh đóng gần nhất của cặp (symbol) + magic từ MT5 history (chỉ 1 ngày gần nhất).
    Trả về (list_profit, last_close_time_str). list_profit sắp từ mới nhất → cũ. last_close_time_str theo UTC (để tính pause)."""
    # Dùng now() (local/PC) để khoảng lấy history khớp với ngày hiển thị trên MT5 terminal
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days_back)
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*")
    if DEBUG_HISTORY:
        print(f"[GridStep:history] get_last_n_closed_profits_by_symbol symbol={symbol} magic={magic} n={n} days_back={days_back}")
        print(f"[GridStep:history]   history_deals_get: {len(deals) if deals else 0} deals (from {from_date} to {to_date} local)")
    if not deals:
        if DEBUG_HISTORY:
            print(f"[GridStep:history]   -> không có deals, return [], None")
        return [], None
    by_position = {}
    for d in deals:
        if getattr(d, "magic", 0) != magic:
            continue
        if getattr(d, "symbol", "") != symbol:
            continue
        pid = getattr(d, "position_id", None) or getattr(d, "position", None)
        if not pid:
            continue
        if pid not in by_position:
            by_position[pid] = {"out_profit": 0.0, "out_time": None}
        if d.entry == mt5.DEAL_ENTRY_OUT:
            by_position[pid]["out_profit"] += (
                getattr(d, "profit", 0) + getattr(d, "swap", 0) + getattr(d, "commission", 0)
            )
            by_position[pid]["out_time"] = getattr(d, "time", None)
    positions = []
    for pid, v in by_position.items():
        if v["out_time"] is None:
            continue
        positions.append((v["out_profit"], v["out_time"]))
    positions.sort(key=lambda x: x[1], reverse=True)
    first_n = positions[:n]
    profits = [p[0] for p in first_n]
    last_close_time_str = None
    if first_n:
        try:
            ts = first_n[0][1]
            last_close_time_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            if DEBUG_HISTORY:
                local_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                print(f"[GridStep:history]   last_close_time UTC: {last_close_time_str} | local (PC): {local_str}  (cùng 1 thời điểm, 2 múi giờ)")
        except (TypeError, OSError):
            pass
    if DEBUG_HISTORY and last_close_time_str is None and first_n:
        print(f"[GridStep:history]   last_close_time: (raw ts={first_n[0][1]})")
    if DEBUG_HISTORY:
        print(f"[GridStep:history]   positions đã đóng (symbol+magic): {len(by_position)}, lấy {len(first_n)} gần nhất")
        print(f"[GridStep:history]   profits (mới→cũ): {profits}")
        all_loss = len(profits) >= n and all((p or 0) < 0 for p in profits)
        print(f"[GridStep:history]   cần {n} lệnh thua liên tiếp -> all_loss={all_loss} (len(profits)={len(profits)}, all<0={all((p or 0) < 0 for p in profits) if profits else False})")
    return profits, last_close_time_str


def get_closed_from_mt5_history(config, days_back=1):
    """Lấy position đã đóng từ MT5 history (theo magic, 1 ngày gần nhất).
    Trả về dict position_id -> (profit, close_price, close_time_str)."""
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days_back)
    magic = config.get("magic", 0)
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*")
    if not deals:
        if DEBUG_HISTORY:
            print(f"[GridStep:history] get_closed_from_mt5_history magic={magic}: 0 deals")
        return {}
    by_position = {}
    for d in deals:
        if getattr(d, "magic", 0) != magic:
            continue
        pid = getattr(d, "position_id", None) or getattr(d, "position", None)
        if not pid:
            continue
        if pid not in by_position:
            by_position[pid] = {"out_profit": 0.0, "out_price": 0.0, "out_time": None}
        if d.entry == mt5.DEAL_ENTRY_OUT:
            by_position[pid]["out_profit"] += (
                getattr(d, "profit", 0) + getattr(d, "swap", 0) + getattr(d, "commission", 0)
            )
            by_position[pid]["out_price"] = getattr(d, "price", 0)
            by_position[pid]["out_time"] = getattr(d, "time", None)
    result = {}
    for pid, v in by_position.items():
        if v["out_profit"] != 0 or v["out_price"] != 0:
            out_ts = v.get("out_time")
            close_time_str = None
            if out_ts:
                try:
                    close_time_str = datetime.utcfromtimestamp(out_ts).strftime("%Y-%m-%d %H:%M:%S")
                except (TypeError, OSError):
                    pass
            result[pid] = (v["out_profit"], v["out_price"], close_time_str)
    if DEBUG_HISTORY:
        print(f"[GridStep:history] get_closed_from_mt5_history magic={magic}: {len(deals)} deals -> {len(result)} positions đã đóng")
    return result
