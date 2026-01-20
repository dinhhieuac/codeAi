import MetaTrader5 as mt5
import json
import os
import sys

# Setup relative path import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import connect_mt5

def load_config(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def run_diagnostics():
    print("🚑 Starting Diagnostics...")
    
    # Load config 1
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs", "config_1.json")
    if not os.path.exists(config_path):
        print(f"❌ Config not found: {config_path}")
        return

    config = load_config(config_path)
    
    # 1. Connect
    if not connect_mt5(config):
        print("❌ MT5 Connection Failed")
        return

    # 2. Check Account
    account_info = mt5.account_info()
    if not account_info:
        print("❌ Failed to get account info")
        return
        
    print("\n📊 Account Info:")
    print(f"  Login: {account_info.login}")
    print(f"  Server: {account_info.server}")
    print(f"  Trade Allowed: {account_info.trade_allowed}")
    print(f"  Trade Expert: {account_info.trade_expert}")
    print(f"  Balance: {account_info.balance}")
    print(f"  Leverage: {account_info.leverage}")
    
    if not account_info.trade_allowed:
        print("⚠️ WARNING: Trade is NOT allowed for this account!")

    # 3. Check Symbol
    symbol = config['symbol']
    symbol_info = mt5.symbol_info(symbol)
    
    if not symbol_info:
        print(f"❌ Symbol {symbol} not found! (Maybe suffix needed?)")
        # Try to find similar symbols
        all_symbols = mt5.symbols_get()
        matches = [s.name for s in all_symbols if "XAU" in s.name or "GOLD" in s.name]
        print(f"  Did you mean one of these? {matches[:5]}")
        return

    print(f"\n🪙 Symbol Info ({symbol}):")
    print(f"  Select: {symbol_info.select}")
    print(f"  Visible: {symbol_info.visible}")
    print(f"  Trade Mode: {symbol_info.trade_mode} (4=Full, 0=Disable)")
    print(f"  Volume Min: {symbol_info.volume_min}")
    print(f"  Volume Max: {symbol_info.volume_max}")
    print(f"  Volume Step: {symbol_info.volume_step}")
    print(f"  Filling Mode: {symbol_info.filling_mode}")
    print(f"    (1=FOK, 2=IOC, 3=FOK+IOC)")
    
    if not symbol_info.visible:
        print("ℹ️ Attempting to select symbol in Market Watch...")
        if not mt5.symbol_select(symbol, True):
            print("❌ Failed to select symbol!")
            return
            
    # 4. Simulate Order Check
    print("\n🧪 Simulating Order Check (0.01 Lot BUY)...")
    price = mt5.symbol_info_tick(symbol).ask
    point = symbol_info.point
    sl = price - 100 * point
    tp = price + 100 * point
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": 0.01,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": 123456,
        "comment": "Diagnostic Test",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_check(request)
    if result is None:
        print("❌ Order Check returned None (Internal Error)")
    else:
        print(f"  Retcode: {result.retcode}")
        print(f"  Comment: {result.comment}")
        if result.retcode == 0:
            print("✅ Order Check PASSED! The config is valid.")
        else:
            print("❌ Order Check FAILED!")
            print("  Possible fixes:")
            if "Unsupported filling mode" in result.comment:
                print("  -> Change 'type_filling' to ORDER_FILLING_FOK or 0 (Default)")

    print("\n🏁 Diagnostics Complete")
    mt5.shutdown()

if __name__ == "__main__":
    run_diagnostics()
