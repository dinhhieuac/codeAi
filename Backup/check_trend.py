import MetaTrader5 as mt5
import pandas as pd
import json
import os

# Load Config
def load_config(filename="XAUUSDMT5/mt5_account.json"):
    if not os.path.exists(filename):
        return None
    with open(filename, 'r') as f:
        return json.load(f)

config = load_config()
if not config:
    print("Config not found")
    quit()

MT5_LOGIN = config.get("ACCOUNT_NUMBER")
MT5_PASSWORD = config.get("PASSWORD")
MT5_SERVER = config.get("SERVER")
SYMBOL = config.get("SYMBOL", "XAUUSDm")
MT5_PATH = config.get("PATH")

if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print("MT5 Init Failed")
    quit()

# Check H1 Trend
rates_h1 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 100)
df_h1 = pd.DataFrame(rates_h1)
df_h1['close'] = df_h1['close']
ema50_h1 = df_h1['close'].ewm(span=50, adjust=False).mean().iloc[-1]
close_h1 = df_h1['close'].iloc[-1]

print(f"--- H1 TREND CHECK ---")
print(f"Symbol: {SYMBOL}")
print(f"H1 Close: {close_h1}")
print(f"H1 EMA50: {ema50_h1}")
if close_h1 > ema50_h1:
    print("RESULT: BUY ONLY (Price > EMA50)")
else:
    print("RESULT: SELL ONLY (Price < EMA50)")

mt5.shutdown()
