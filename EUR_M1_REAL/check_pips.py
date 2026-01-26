import MetaTrader5 as mt5
import sys
import os
import json

# Setup relative path import for shared modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import load_config, connect_mt5

def check_pip_value():
    # Load config 1 just to get credentials
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs", "config_1.json")
    config = load_config(config_path)
    
    if not connect_mt5(config):
        print("Failed to connect for check.")
        return

    symbol = config['symbol'] # EURUSD
    info = mt5.symbol_info(symbol)
    
    if not info:
        print(f"Failed to get info for {symbol}")
        return

    print(f"\n--- 🔍 Checking Pip Value for {symbol} ---")
    print(f"Digits: {info.digits}")
    print(f"Point: {info.point}")
    
    sl_pips_input = 20
    
    # Formula used in Strategy 1:
    # sl_pips = config['parameters']['sl_pips'] * mt5.symbol_info(symbol).point * 10
    
    calculated_sl_distance = sl_pips_input * info.point * 10
    
    print(f"\nIf you put 'sl_pips': {sl_pips_input} in config:")
    print(f"Formula: {sl_pips_input} * {info.point} * 10")
    print(f"Result (Price Distance): {calculated_sl_distance:.3f}")
    
    # Calculate Risk for 0.01 Lot
    # Standard contract size for EURUSD is usually 100000. 
    # But profit calculation is best done by OrderCalcProfit for accuracy
    
    print(f"\n--- 💰 Risk Calculation for 0.01 Lot ---")
    
    current_price = mt5.symbol_info_tick(symbol).ask
    sl_price = current_price - calculated_sl_distance
    
    # Calculate potential loss in account currency
    profit = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, 0.01, current_price, sl_price)
    
    print(f"Entry: {current_price:.2f}")
    print(f"Stop Loss: {sl_price:.2f} (Distance: {calculated_sl_distance:.3f})")
    print(f"Estimated Loss (USD): {profit} (Note: Profit is negative for loss)")
    
    mt5.shutdown()

if __name__ == "__main__":
    check_pip_value()
