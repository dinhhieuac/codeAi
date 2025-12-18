"""
Test script để kiểm tra tính năng Risk-Based Lot Calculation
Không gửi lệnh thật lên MT5, chỉ in log để test
"""

import sys
import os
sys.path.append('..')
from utils import load_config, connect_mt5
import MetaTrader5 as mt5

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
    """Test risk-based lot calculation với các scenarios khác nhau"""
    
    print("="*80)
    print("🧪 TEST RISK-BASED LOT CALCULATION")
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
    
    print(f"\n📋 Config:")
    print(f"   Symbol: {symbol}")
    print(f"   Risk Percent: {risk_percent}%")
    print(f"   Use Risk-Based Lot: {use_risk_based_lot}")
    
    # Connect to MT5 (optional, chỉ để lấy account balance)
    account_balance = 10000.0  # Default test balance
    if connect_mt5(config):
        account_info = mt5.account_info()
        if account_info:
            account_balance = account_info.balance
            print(f"\n✅ Connected to MT5")
            print(f"   Account Balance: ${account_balance:.2f}")
        else:
            print(f"\n⚠️ Không thể lấy account info, dùng balance test: ${account_balance:.2f}")
    else:
        print(f"\n⚠️ Không kết nối được MT5, dùng balance test: ${account_balance:.2f}")
    
    # Test scenarios
    print(f"\n{'='*80}")
    print("📊 TEST SCENARIOS")
    print(f"{'='*80}")
    
    test_cases = [
        {
            "name": "EURUSD - SL 20 pips",
            "symbol": "EURUSD",
            "entry_price": 1.10000,
            "sl_price": 1.09800,  # 20 pips
            "account_balance": account_balance,
            "risk_percent": risk_percent
        },
        {
            "name": "EURUSD - SL 30 pips",
            "symbol": "EURUSD",
            "entry_price": 1.10000,
            "sl_price": 1.09700,  # 30 pips
            "account_balance": account_balance,
            "risk_percent": risk_percent
        },
        {
            "name": "XAUUSD - SL 20 pips",
            "symbol": "XAUUSD",
            "entry_price": 2000.00,
            "sl_price": 1998.00,  # 20 pips (20 USD)
            "account_balance": account_balance,
            "risk_percent": risk_percent
        },
        {
            "name": "EURUSD - Risk 2%",
            "symbol": "EURUSD",
            "entry_price": 1.10000,
            "sl_price": 1.09800,  # 20 pips
            "account_balance": account_balance,
            "risk_percent": 2.0
        },
        {
            "name": "EURUSD - Vốn lớn $50,000",
            "symbol": "EURUSD",
            "entry_price": 1.10000,
            "sl_price": 1.09800,  # 20 pips
            "account_balance": 50000.0,
            "risk_percent": risk_percent
        },
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n{'─'*80}")
        print(f"Test {i}: {test['name']}")
        print(f"{'─'*80}")
        
        # Calculate SL pips
        sl_pips = calculate_sl_pips(test['entry_price'], test['sl_price'], test['symbol'])
        
        # Get pip value
        pip_value = get_pip_value_per_lot(test['symbol'])
        
        # Calculate lot size
        lot_size = calculate_lot_size(
            test['account_balance'],
            test['risk_percent'],
            sl_pips,
            test['symbol']
        )
        
        # Calculate risk money
        risk_money = test['account_balance'] * (test['risk_percent'] / 100.0)
        
        # Display results
        print(f"   Entry Price: {test['entry_price']:.5f}")
        print(f"   SL Price: {test['sl_price']:.5f}")
        print(f"   SL Distance: {sl_pips:.1f} pips")
        print(f"   Account Balance: ${test['account_balance']:,.2f}")
        print(f"   Risk: {test['risk_percent']}% = ${risk_money:.2f}")
        print(f"   Pip Value: ${pip_value:.2f} per lot")
        print(f"   Formula: Lot = ${risk_money:.2f} / ({sl_pips:.1f} pips × ${pip_value:.2f})")
        print(f"   Calculated Lot: {lot_size:.2f}")
        
        # Verify calculation
        expected_risk = lot_size * sl_pips * pip_value
        print(f"   ✅ Verification: {lot_size:.2f} lot × {sl_pips:.1f} pips × ${pip_value:.2f} = ${expected_risk:.2f} risk")
        
        if abs(expected_risk - risk_money) < 0.01:
            print(f"   ✅ PASS: Risk matches expected (${expected_risk:.2f} ≈ ${risk_money:.2f})")
        else:
            print(f"   ⚠️ WARNING: Risk mismatch (${expected_risk:.2f} ≠ ${risk_money:.2f})")
    
    print(f"\n{'='*80}")
    print("✅ TEST COMPLETED")
    print(f"{'='*80}\n")
    
    # Cleanup
    if mt5.terminal_info():
        mt5.shutdown()

if __name__ == "__main__":
    test_risk_lot_calculation()

