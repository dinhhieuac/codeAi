import MetaTrader5 as mt5
import json
import os

def debug_symbol():
    # Load config to get login details
    config_path = "CoinMt5/mt5_account.json"
    if not os.path.exists(config_path):
        print(f"Config not found at {config_path}")
        return

    with open(config_path, 'r') as f:
        config = json.load(f)
    
    login = config.get("ACCOUNT_NUMBER")
    password = config.get("PASSWORD")
    server = config.get("SERVER")
    symbol = "ETHUSD" # Try generic first, then config symbol

    if not mt5.initialize(login=login, password=password, server=server):
        print(f"Failed to init MT5: {mt5.last_error()}")
        return

    # Check config symbol
    config_symbol = config.get("SYMBOL", "ETHUSDm")
    print(f"Config Symbol: {config_symbol}")
    
    info = mt5.symbol_info(config_symbol)
    if info:
        print(f"Symbol: {config_symbol}")
        print(f"Point: {info.point}")
        print(f"Digits: {info.digits}")
        print(f"Tick Size: {info.trade_tick_size}")
        print(f"Contract Size: {info.trade_contract_size}")
    else:
        print(f"Symbol {config_symbol} not found")

    mt5.shutdown()

if __name__ == "__main__":
    debug_symbol()
