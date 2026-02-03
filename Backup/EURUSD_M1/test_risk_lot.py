"""
Test script để kiểm tra tính năng Risk-Based Lot Calculation với MT5 thật
Không gửi lệnh thật lên MT5, chỉ tính toán và in log
"""

import sys
import os
import json
import MetaTrader5 as mt5

def load_config(config_path):
    """Load configuration from JSON file"""
    if not os.path.exists(config_path):
        print(f"❌ Config file not found: {config_path}")
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return None

def connect_mt5(config):
    """Connect to MT5"""
    login = config.get("account")
    password = config.get("password")
    server = config.get("server")
    path = config.get("mt5_path")
    
    if not all([login, password, server]):
        print("❌ Missing MT5 credentials in config")
        return False
    
    try:
        if path:
            if not mt5.initialize(path=path, login=login, password=password, server=server):
                print(f"❌ MT5 Init failed with path: {mt5.last_error()}")
                return False
        else:
            if not mt5.initialize(login=login, password=password, server=server):
                print(f"❌ MT5 Init failed: {mt5.last_error()}")
                return False
                
        print(f"✅ Connected to MT5 Account: {login}")
        return True
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def get_pip_value_per_lot(symbol):
    """
    Get pip value per lot for a symbol
    EURUSD: 1 pip = $10 per lot (standard)
    XAUUSD: 1 pip = $1 per lot (standard, but may vary by broker)
    """
    symbol_upper = symbol.upper()
    if 'EURUSD' in symbol_upper or 'GBPUSD' in symbol_upper or 'AUDUSD' in symbol_upper or 'NZDUSD' in symbol_upper:
        return 10.0  # $10 per pip per lot for major pairs
    elif 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        return 1.0   # $1 per pip per lot for gold (may vary)
    elif 'USDJPY' in symbol_upper or 'USDCHF' in symbol_upper or 'USDCAD' in symbol_upper:
        return 10.0
    else:
        # Default: try to get from MT5
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info:
            contract_size = getattr(symbol_info, 'trade_contract_size', 100000)
            if contract_size == 100000:
                return 10.0
            else:
                return contract_size / 10000
        return 10.0

def calculate_sl_pips(entry_price, sl_price, symbol):
    """
    Calculate SL distance in pips
    """
    symbol_upper = symbol.upper()
    
    # For JPY pairs, 1 pip = 0.01
    if 'JPY' in symbol_upper:
        pip_size = 0.01
    else:
        pip_size = 0.0001  # Standard for most pairs
    
    # Calculate distance
    distance = abs(entry_price - sl_price)
    sl_pips = distance / pip_size
    
    return sl_pips

def calculate_lot_size(account_balance, risk_percent, sl_pips, symbol):
    """
    Calculate lot size based on risk management formula:
    Lot size = RiskMoney / (SL pips × Pip Value per Lot)
    """
    # Calculate risk money
    risk_money = account_balance * (risk_percent / 100.0)
    
    # Get pip value per lot
    pip_value_per_lot = get_pip_value_per_lot(symbol)
    
    # Calculate lot size
    if sl_pips > 0 and pip_value_per_lot > 0:
        lot_size = risk_money / (sl_pips * pip_value_per_lot)
    else:
        lot_size = 0.01  # Default minimum
    
    # Round to 2 decimal places (standard lot step is 0.01)
    lot_size = round(lot_size, 2)
    
    # Ensure minimum lot size
    if lot_size < 0.01:
        lot_size = 0.01
    
    return lot_size

def test_risk_lot_calculation():
    """Test risk-based lot calculation với dữ liệu thật từ MT5"""
    
    print("="*80)
    print("🧪 TEST RISK-BASED LOT CALCULATION (MT5 REAL DATA)")
    print("="*80)
    
    # Load config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_tuyen.json")
    config = load_config(config_path)
    
    if not config:
        print("❌ Không thể load config")
        return
    
    symbol = config.get('symbol', 'EURUSD')
    risk_percent = config.get('risk_percent', 1.0)
    use_risk_based_lot = config.get('use_risk_based_lot', True)
    
    # Load parameters config
    parameters_config = config.get('parameters', {})
    atr_multiplier = parameters_config.get('atr_multiplier', 2.0)
    reward_ratio = parameters_config.get('reward_ratio', 2.0)
    
    print(f"\n📋 Config:")
    print(f"   Symbol: {symbol}")
    print(f"   Risk Percent: {risk_percent}%")
    print(f"   Use Risk-Based Lot: {use_risk_based_lot}")
    print(f"   ATR Multiplier: {atr_multiplier}x (for SL)")
    print(f"   Reward Ratio: {reward_ratio} (R:R = 1:{reward_ratio})")
    
    # Connect to MT5
    if not connect_mt5(config):
        print("❌ Không thể kết nối MT5. Thoát.")
        return
    
    # Get account info
    account_info = mt5.account_info()
    if not account_info:
        print("❌ Không thể lấy account info")
        mt5.shutdown()
        return
    
    account_balance = account_info.balance
    account_equity = account_info.equity
    account_currency = account_info.currency
    
    print(f"\n💰 Account Info:")
    print(f"   Balance: {account_balance:,.2f} {account_currency}")
    print(f"   Equity: {account_equity:,.2f} {account_currency}")
    
    # Get symbol info
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        print(f"❌ Không thể lấy symbol info: {symbol}")
        mt5.shutdown()
        return
    
    if not symbol_info.visible:
        print(f"⚠️ Symbol {symbol} không visible. Đang kích hoạt...")
        if not mt5.symbol_select(symbol, True):
            print(f"❌ Không thể kích hoạt symbol: {symbol}")
            mt5.shutdown()
            return
    
    # Get current price
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"❌ Không thể lấy tick data: {symbol}")
        mt5.shutdown()
        return
    
    current_price = tick.ask if tick.ask > 0 else tick.bid
    
    print(f"\n📊 Symbol Info:")
    print(f"   Symbol: {symbol}")
    print(f"   Current Price: {current_price:.5f}")
    print(f"   Digits: {symbol_info.digits}")
    print(f"   Point: {symbol_info.point}")
    print(f"   Contract Size: {symbol_info.trade_contract_size}")
    
    # Get ATR để tính SL (giống như trong bot)
    import pandas as pd
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 300)
    if rates is None or len(rates) == 0:
        print(f"❌ Không thể lấy dữ liệu giá")
        mt5.shutdown()
        return
    
    df = pd.DataFrame(rates)
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift(1))
    df['tr2'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    atr_val = df['tr'].rolling(window=14).mean().iloc[-1]
    
    # Calculate SL và TP using config parameters (giống bot)
    sl_distance = atr_multiplier * atr_val
    tp_distance = atr_multiplier * atr_val * reward_ratio
    
    sl_buy = current_price - sl_distance
    tp_buy = current_price + tp_distance
    sl_sell = current_price + sl_distance
    tp_sell = current_price - tp_distance
    
    print(f"\n📈 Market Data:")
    print(f"   ATR (14): {atr_val:.5f}")
    print(f"   SL Distance ({atr_multiplier}x ATR): {sl_distance:.5f}")
    print(f"   TP Distance ({atr_multiplier * reward_ratio}x ATR): {tp_distance:.5f}")
    print(f"   Risk:Reward = 1:{reward_ratio:.1f}")
    
    # Test BUY scenario
    print(f"\n{'='*80}")
    print("📊 BUY SCENARIO")
    print(f"{'='*80}")
    
    sl_pips_buy = calculate_sl_pips(current_price, sl_buy, symbol)
    pip_value_buy = get_pip_value_per_lot(symbol)
    lot_size_buy = calculate_lot_size(account_balance, risk_percent, sl_pips_buy, symbol)
    risk_money_buy = account_balance * (risk_percent / 100.0)
    
    print(f"   Entry Price: {current_price:.5f}")
    print(f"   SL Price: {sl_buy:.5f} ({atr_multiplier}x ATR = {sl_distance:.5f})")
    print(f"   TP Price: {tp_buy:.5f} ({atr_multiplier * reward_ratio}x ATR = {tp_distance:.5f})")
    print(f"   SL Distance: {sl_pips_buy:.1f} pips")
    print(f"   Account Balance: ${account_balance:,.2f}")
    print(f"   Risk: {risk_percent}% = ${risk_money_buy:.2f}")
    print(f"   Pip Value: ${pip_value_buy:.2f} per lot")
    print(f"   Formula: Lot = ${risk_money_buy:.2f} / ({sl_pips_buy:.1f} pips × ${pip_value_buy:.2f})")
    print(f"   ✅ Calculated Lot: {lot_size_buy:.2f}")
    
    # Verify
    expected_risk_buy = lot_size_buy * sl_pips_buy * pip_value_buy
    expected_reward_buy = lot_size_buy * (sl_pips_buy * reward_ratio) * pip_value_buy
    print(f"   ✅ Verification:")
    print(f"      Risk: {lot_size_buy:.2f} lot × {sl_pips_buy:.1f} pips × ${pip_value_buy:.2f} = ${expected_risk_buy:.2f}")
    print(f"      Reward: {lot_size_buy:.2f} lot × {sl_pips_buy * reward_ratio:.1f} pips × ${pip_value_buy:.2f} = ${expected_reward_buy:.2f}")
    print(f"      R:R = ${expected_risk_buy:.2f} : ${expected_reward_buy:.2f} = 1:{reward_ratio:.1f}")
    
    # Test SELL scenario
    print(f"\n{'='*80}")
    print("📊 SELL SCENARIO")
    print(f"{'='*80}")
    
    sl_pips_sell = calculate_sl_pips(current_price, sl_sell, symbol)
    pip_value_sell = get_pip_value_per_lot(symbol)
    lot_size_sell = calculate_lot_size(account_balance, risk_percent, sl_pips_sell, symbol)
    risk_money_sell = account_balance * (risk_percent / 100.0)
    
    print(f"   Entry Price: {current_price:.5f}")
    print(f"   SL Price: {sl_sell:.5f} ({atr_multiplier}x ATR = {sl_distance:.5f})")
    print(f"   TP Price: {tp_sell:.5f} ({atr_multiplier * reward_ratio}x ATR = {tp_distance:.5f})")
    print(f"   SL Distance: {sl_pips_sell:.1f} pips")
    print(f"   Account Balance: ${account_balance:,.2f}")
    print(f"   Risk: {risk_percent}% = ${risk_money_sell:.2f}")
    print(f"   Pip Value: ${pip_value_sell:.2f} per lot")
    print(f"   Formula: Lot = ${risk_money_sell:.2f} / ({sl_pips_sell:.1f} pips × ${pip_value_sell:.2f})")
    print(f"   ✅ Calculated Lot: {lot_size_sell:.2f}")
    
    # Verify
    expected_risk_sell = lot_size_sell * sl_pips_sell * pip_value_sell
    expected_reward_sell = lot_size_sell * (sl_pips_sell * reward_ratio) * pip_value_sell
    print(f"   ✅ Verification:")
    print(f"      Risk: {lot_size_sell:.2f} lot × {sl_pips_sell:.1f} pips × ${pip_value_sell:.2f} = ${expected_risk_sell:.2f}")
    print(f"      Reward: {lot_size_sell:.2f} lot × {sl_pips_sell * reward_ratio:.1f} pips × ${pip_value_sell:.2f} = ${expected_reward_sell:.2f}")
    print(f"      R:R = ${expected_risk_sell:.2f} : ${expected_reward_sell:.2f} = 1:{reward_ratio:.1f}")
    
    print(f"\n{'='*80}")
    print("✅ TEST COMPLETED")
    print(f"{'='*80}\n")
    
    # Cleanup
    mt5.shutdown()

if __name__ == "__main__":
    test_risk_lot_calculation()

