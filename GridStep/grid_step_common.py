"""
Grid Step – logic dùng chung cho strategy_grid_step.py, strategy_grid_step_btc.py, ...
Kiểm tra history MT5 theo cặp (symbol + magic) trước khi đặt BUY_STOP/SELL_STOP.
"""
import MetaTrader5 as mt5
from datetime import datetime, timedelta


def get_last_n_closed_profits_by_symbol(symbol, magic, n, days_back=7):
    """Lấy N lệnh đóng gần nhất của cặp (symbol) + magic từ MT5 history.
    Trả về (list_profit, last_close_time_str). list_profit sắp từ mới nhất → cũ."""
    from_date = datetime.utcnow() - timedelta(days=days_back)
    to_date = datetime.utcnow()
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*")
    if not deals:
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
            last_close_time_str = datetime.utcfromtimestamp(first_n[0][1]).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, OSError):
            pass
    return profits, last_close_time_str


def get_closed_from_mt5_history(config, days_back=2):
    """Lấy position đã đóng từ MT5 history (theo magic).
    Trả về dict position_id -> (profit, close_price, close_time_str)."""
    from_date = datetime.utcnow() - timedelta(days=days_back)
    to_date = datetime.utcnow()
    magic = config.get("magic", 0)
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*")
    if not deals:
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
    return result
