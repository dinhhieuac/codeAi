"""
Check current Spread từ MT5 cho XAUUSD, BTCUSD, EURUSD, AUDUSD.
Chạy: python check_current_spread.py
Cần MT5 đang mở và config (config_grid_step.json) để kết nối.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import MetaTrader5 as mt5
from utils import load_config, connect_mt5

SYMBOLS = ["XAUUSD", "BTCUSD", "EURUSD", "AUDUSD"]


def check_spread():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_grid_step.json")
    config = load_config(config_path)
    if not config:
        print("Khong doc duoc config. Kiem tra configs/config_grid_step.json")
        return

    if not connect_mt5(config):
        print("Khong ket noi duoc MT5. Mo terminal MT5 va thu lai.")
        return

    print("\n" + "=" * 70)
    print("  CURRENT SPREAD (MT5)")
    print("=" * 70)
    print(f"  {'Symbol':<10} {'Bid':<14} {'Ask':<14} {'Spread (price)':<16} {'Spread (points)':<16} {'Point':<10}")
    print("-" * 70)

    for symbol in SYMBOLS:
        if not mt5.symbol_select(symbol, True):
            print(f"  {symbol:<10} -- Symbol khong co hoac chua enable")
            continue
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            print(f"  {symbol:<10} -- Loi lay tick/info")
            continue
        bid = tick.bid
        ask = tick.ask
        spread_price = ask - bid
        point = getattr(info, "point", None) or 0.00001
        if point and point > 0:
            spread_points = round(spread_price / point)
        else:
            spread_points = 0
        print(f"  {symbol:<10} {bid:<14.5f} {ask:<14.5f} {spread_price:<16.5f} {spread_points:<16} {point:<10.6f}")

    print("=" * 70)
    print("  Luu y: Grid Step bot so sanh spread (price) voi spread_max trong config.")
    print("=" * 70 + "\n")
    mt5.shutdown()


if __name__ == "__main__":
    check_spread()
