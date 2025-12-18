"""
Script để mở 1 lệnh BUY/SELL trên MT5 cho XAUUSD để test và theo dõi
Tính toán SL/TP và lot size theo công thức risk management
"""

import sys
import os
import json
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

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

def calculate_atr(df, period=14):
    """Calculate ATR"""
    df = df.copy()
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift(1))
    df['tr2'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    atr_series = df['tr'].rolling(window=period).mean()
    return atr_series

def get_pip_value_per_lot(symbol, symbol_info=None):
    """Get pip value per lot for a symbol - lấy từ MT5 nếu có"""
    if symbol_info is None:
        symbol_info = mt5.symbol_info(symbol)
    
    if symbol_info:
        # Lấy từ MT5 symbol_info (chính xác nhất)
        # trade_tick_value = giá trị của 1 tick movement
        # trade_tick_size = kích thước của 1 tick
        tick_value = getattr(symbol_info, 'trade_tick_value', None)
        tick_size = getattr(symbol_info, 'trade_tick_size', None)
        contract_size = getattr(symbol_info, 'trade_contract_size', 100000)
        point = getattr(symbol_info, 'point', 0.0001)
        
        # Với XAUUSD: thường 1 lot = 100 oz, 1 point = 0.01, tick_value = $0.01 per point per lot
        # Pip value = tick_value * (pip_size / tick_size)
        if tick_value and tick_size and tick_size > 0:
            # Pip size thường là 10x point (0.1 cho XAUUSD, 0.0001 cho EURUSD)
            pip_size = point * 10 if 'XAU' in symbol.upper() or 'GOLD' in symbol.upper() else point * 10
            pip_value = tick_value * (pip_size / tick_size)
            if pip_value > 0:
                return pip_value
        
        # Fallback: tính từ contract_size
        symbol_upper = symbol.upper()
        if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
            # XAUUSD: 1 lot = 100 oz, 1 pip (0.1) = $1 per lot
            # Nhưng có thể khác tùy broker
            if contract_size == 100:
                return 1.0  # $1 per pip per lot
            else:
                return contract_size / 100  # Approximate
        elif 'EURUSD' in symbol_upper or 'GBPUSD' in symbol_upper:
            return 10.0
        else:
            return 10.0
    
    # Default fallback
    symbol_upper = symbol.upper()
    if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        return 1.0
    return 10.0

def calculate_sl_pips(entry_price, sl_price, symbol, symbol_info=None):
    """Calculate SL distance in pips - lấy pip size từ MT5"""
    if symbol_info is None:
        symbol_info = mt5.symbol_info(symbol)
    
    if symbol_info:
        # Lấy point và digits từ MT5
        point = getattr(symbol_info, 'point', 0.0001)
        digits = getattr(symbol_info, 'digits', 5)
        
        # Pip size: thường là 10x point
        # XAUUSD: point = 0.01, pip = 0.1 (10 points)
        # EURUSD: point = 0.00001, pip = 0.0001 (10 points)
        pip_size = point * 10
        
        # Một số broker XAUUSD dùng point = 0.01, pip = 0.01 (1 point = 1 pip)
        symbol_upper = symbol.upper()
        if 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
            # Kiểm tra: nếu point = 0.01, có thể pip = 0.01 hoặc 0.1
            if point >= 0.01:
                pip_size = point  # 1 point = 1 pip
            else:
                pip_size = point * 10  # 10 points = 1 pip
        elif 'JPY' in symbol_upper:
            pip_size = 0.01  # JPY pairs
        else:
            pip_size = 0.0001  # Standard for most pairs
        
        distance = abs(entry_price - sl_price)
        sl_pips = distance / pip_size
        return sl_pips
    
    # Fallback
    symbol_upper = symbol.upper()
    if 'JPY' in symbol_upper:
        pip_size = 0.01
    elif 'XAUUSD' in symbol_upper or 'GOLD' in symbol_upper:
        pip_size = 0.1  # XAUUSD: 1 pip = 0.1
    else:
        pip_size = 0.0001
    
    distance = abs(entry_price - sl_price)
    sl_pips = distance / pip_size
    return sl_pips

def calculate_lot_size(account_balance, risk_percent, sl_pips, symbol, symbol_info=None):
    """Calculate lot size based on risk management"""
    risk_money = account_balance * (risk_percent / 100.0)
    pip_value_per_lot = get_pip_value_per_lot(symbol, symbol_info)
    
    if sl_pips > 0 and pip_value_per_lot > 0:
        lot_size = risk_money / (sl_pips * pip_value_per_lot)
    else:
        lot_size = 0.01
    
    lot_size = round(lot_size, 2)
    if lot_size < 0.01:
        lot_size = 0.01
    
    return lot_size

def open_test_order():
    """Mở 1 lệnh test trên MT5 cho XAUUSD"""
    
    print("="*80)
    print("🧪 TEST OPEN ORDER ON MT5 - XAUUSD")
    print("="*80)
    
    # Load config - thử config XAU trước, nếu không có thì dùng config EURUSD
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_tuyen_xau.json")
    
    # Nếu không có config XAU, thử tìm config khác có XAUUSD
    if not os.path.exists(config_path):
        # Tìm config có symbol XAUUSD
        configs_dir = os.path.join(script_dir, "configs")
        for filename in os.listdir(configs_dir):
            if filename.endswith('.json') and 'xau' in filename.lower():
                config_path = os.path.join(configs_dir, filename)
                break
        else:
            # Fallback: dùng config EURUSD và đổi symbol
            config_path = os.path.join(script_dir, "configs", "config_tuyen.json")
    
    config = load_config(config_path)
    
    if not config:
        print("❌ Không thể load config")
        return
    
    # Override symbol to XAUUSD
    symbol = 'XAUUSD'
    risk_percent = config.get('risk_percent', 1.0)
    use_risk_based_lot = config.get('use_risk_based_lot', True)
    magic = config.get('magic', 400006)
    
    # Load parameters
    parameters_config = config.get('parameters', {})
    atr_multiplier = parameters_config.get('atr_multiplier', 2.0)
    reward_ratio = parameters_config.get('reward_ratio', 2.0)
    
    print(f"\n📋 Config:")
    print(f"   Symbol: {symbol} (XAUUSD)")
    print(f"   Risk Percent: {risk_percent}%")
    print(f"   ATR Multiplier: {atr_multiplier}x")
    print(f"   Reward Ratio: {reward_ratio} (R:R = 1:{reward_ratio})")
    print(f"   Use Risk-Based Lot: {use_risk_based_lot}")
    
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
    
    print(f"\n💰 Account Info:")
    print(f"   Balance: {account_balance:,.2f} {account_info.currency}")
    print(f"   Equity: {account_equity:,.2f} {account_info.currency}")
    
    # Get symbol info
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        print(f"❌ Không thể lấy symbol info: {symbol}")
        print(f"   ⚠️ Có thể symbol {symbol} không tồn tại trên broker này")
        print(f"   💡 Thử các symbol khác: XAUUSD, GOLD, XAU/USD")
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
    
    # Get M1 data for ATR
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 300)
    if rates is None or len(rates) == 0:
        print(f"❌ Không thể lấy dữ liệu giá")
        mt5.shutdown()
        return
    
    df = pd.DataFrame(rates)
    df['atr'] = calculate_atr(df, 14)
    atr_val = df['atr'].iloc[-1]
    
    if pd.isna(atr_val) or atr_val <= 0:
        recent_range = df.iloc[-14:]['high'].max() - df.iloc[-14:]['low'].min()
        atr_val = recent_range / 14 if recent_range > 0 else 0.1  # Default 0.1 for XAUUSD
        print(f"   ⚠️ ATR is NaN, using fallback: {atr_val:.5f}")
    
    # Ask user for order type
    print(f"\n{'='*80}")
    print("📊 MARKET DATA")
    print(f"{'='*80}")
    print(f"   Current Ask: {tick.ask:.2f}")
    print(f"   Current Bid: {tick.bid:.2f}")
    print(f"   Spread: ${(tick.ask - tick.bid):.2f}")
    print(f"   ATR (14): {atr_val:.2f}")
    
    print(f"\n{'='*80}")
    print("🔍 CHỌN LOẠI LỆNH")
    print(f"{'='*80}")
    print("   1️⃣  BUY")
    print("   2️⃣  SELL")
    
    while True:
        try:
            choice = input("\n👉 Nhập lựa chọn (1 hoặc 2): ").strip()
            if choice == "1":
                signal_type = "BUY"
                price = tick.ask
                break
            elif choice == "2":
                signal_type = "SELL"
                price = tick.bid
                break
            else:
                print("❌ Lựa chọn không hợp lệ! Vui lòng nhập 1 hoặc 2")
        except KeyboardInterrupt:
            print("\n\n⚠️ Đã hủy. Thoát.")
            mt5.shutdown()
            return
    
    # Calculate SL and TP
    sl_distance = atr_multiplier * atr_val
    tp_distance = atr_multiplier * atr_val * reward_ratio
    
    if signal_type == "BUY":
        sl = price - sl_distance
        tp = price + tp_distance
    else:  # SELL
        sl = price + sl_distance
        tp = price - tp_distance
    
    # Normalize to symbol digits
    digits = symbol_info.digits
    price = round(price, digits)
    sl = round(sl, digits)
    tp = round(tp, digits)
    
    # Calculate lot size
    if use_risk_based_lot:
        # Lấy pip size và pip value từ MT5 (chính xác hơn)
        point = symbol_info.point
        digits = symbol_info.digits
        tick_value = getattr(symbol_info, 'trade_tick_value', None)
        tick_size = getattr(symbol_info, 'trade_tick_size', None)
        contract_size = getattr(symbol_info, 'trade_contract_size', 100)
        
        # Tính pip size
        if 'XAUUSD' in symbol.upper() or 'GOLD' in symbol.upper():
            if point >= 0.01:
                pip_size = point  # 1 point = 1 pip
            else:
                pip_size = point * 10  # 10 points = 1 pip
        else:
            pip_size = point * 10
        
        sl_pips = calculate_sl_pips(price, sl, symbol, symbol_info)
        pip_value = get_pip_value_per_lot(symbol, symbol_info)
        risk_money = account_balance * (risk_percent / 100.0)
        volume = calculate_lot_size(account_balance, risk_percent, sl_pips, symbol, symbol_info)
        
        print(f"\n{'='*80}")
        print("💰 RISK-BASED LOT CALCULATION")
        print(f"{'='*80}")
        print(f"   Account Balance: ${account_balance:,.2f}")
        print(f"   Risk: {risk_percent}% = ${risk_money:.2f}")
        print(f"   SL Distance: {sl_pips:.1f} pips (pip_size: {pip_size:.5f})")
        print(f"   Pip Value: ${pip_value:.2f} per lot")
        print(f"   Point: {point:.5f} | Tick Value: {tick_value} | Tick Size: {tick_size} | Contract Size: {contract_size}")
        print(f"   Formula: Lot = ${risk_money:.2f} / ({sl_pips:.1f} pips × ${pip_value:.2f})")
        print(f"   ✅ Calculated Lot: {volume:.2f}")
    else:
        volume = config.get('volume', 0.01)
        print(f"\n📊 Sử dụng volume cố định từ config: {volume}")
    
    # Display order details
    print(f"\n{'='*80}")
    print(f"📋 ORDER DETAILS - {signal_type}")
    print(f"{'='*80}")
    print(f"   Symbol: {symbol}")
    print(f"   Type: {signal_type}")
    print(f"   Entry Price: {price:.2f}")
    print(f"   SL Price: {sl:.2f} ({atr_multiplier}x ATR = {sl_distance:.2f})")
    print(f"   TP Price: {tp:.2f} ({atr_multiplier * reward_ratio}x ATR = {tp_distance:.2f})")
    print(f"   Volume: {volume:.2f} lot")
    print(f"   Risk:Reward = 1:{reward_ratio:.1f}")
    
    # Calculate expected risk/reward (dùng lại giá trị đã tính)
    if use_risk_based_lot:
        # sl_pips và pip_value đã được tính ở trên
        tp_pips = sl_pips * reward_ratio
        expected_risk = volume * sl_pips * pip_value
        expected_reward = volume * tp_pips * pip_value
    else:
        sl_pips = calculate_sl_pips(price, sl, symbol, symbol_info)
        tp_pips = sl_pips * reward_ratio
        pip_value = get_pip_value_per_lot(symbol, symbol_info)
        expected_risk = volume * sl_pips * pip_value
        expected_reward = volume * tp_pips * pip_value
    
    print(f"\n   💰 Expected Risk: ${expected_risk:.2f}")
    print(f"   💰 Expected Reward: ${expected_reward:.2f}")
    print(f"   📊 R:R = ${expected_risk:.2f} : ${expected_reward:.2f} = 1:{reward_ratio:.1f}")
    
    # Confirm before sending
    print(f"\n{'='*80}")
    print("⚠️  XÁC NHẬN GỬI LỆNH")
    print(f"{'='*80}")
    
    while True:
        try:
            confirm = input("👉 Bạn có chắc muốn gửi lệnh này? (yes/no): ").strip().lower()
            if confirm in ['yes', 'y']:
                break
            elif confirm in ['no', 'n']:
                print("❌ Đã hủy. Không gửi lệnh.")
                mt5.shutdown()
                return
            else:
                print("❌ Vui lòng nhập 'yes' hoặc 'no'")
        except KeyboardInterrupt:
            print("\n\n⚠️ Đã hủy. Không gửi lệnh.")
            mt5.shutdown()
            return
    
    # Sanitize comment
    import re
    reason = f"TestXAU_{signal_type}_RiskBased"
    sanitized_comment = re.sub(r'[^a-zA-Z0-9_\-]', '', reason)
    if not sanitized_comment:
        sanitized_comment = f"TestXAU{signal_type}"
    sanitized_comment = sanitized_comment[:31]
    
    # Prepare request
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if signal_type == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": magic,
        "comment": sanitized_comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    
    # Validate request
    print(f"\n🔍 Validating request...")
    check_result = mt5.order_check(request)
    if check_result is None:
        error = mt5.last_error()
        print(f"   ⚠️ order_check() trả về None. Lỗi: {error}")
    elif hasattr(check_result, 'retcode') and check_result.retcode != 0:
        print(f"   ❌ order_check() không hợp lệ: {check_result.comment if hasattr(check_result, 'comment') else 'Unknown'}")
        print(f"   ❌ Retcode: {check_result.retcode}")
        mt5.shutdown()
        return
    else:
        print(f"   ✅ Request hợp lệ")
    
    # Send order
    print(f"\n📤 Đang gửi lệnh...")
    result = mt5.order_send(request)
    
    if result is None:
        error = mt5.last_error()
        print(f"❌ Order Send Failed: Result is None")
        print(f"   Lỗi MT5: {error}")
        mt5.shutdown()
        return
    
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"\n{'='*80}")
        print("✅ ORDER EXECUTED SUCCESSFULLY")
        print(f"{'='*80}")
        print(f"   🆔 Ticket: {result.order}")
        print(f"   💱 Symbol: {symbol} ({signal_type})")
        print(f"   💵 Entry Price: {price:.2f}")
        print(f"   🛑 SL: {sl:.2f} ({atr_multiplier}x ATR = {sl_distance:.2f})")
        print(f"   🎯 TP: {tp:.2f} ({atr_multiplier * reward_ratio}x ATR = {tp_distance:.2f})")
        print(f"   📊 Volume: {volume:.2f} lot")
        print(f"   💰 Expected Risk: ${expected_risk:.2f}")
        print(f"   💰 Expected Reward: ${expected_reward:.2f}")
        print(f"   📊 R:R = 1:{reward_ratio:.1f}")
        print(f"   📋 Comment: {sanitized_comment}")
        
        # Get position info
        positions = mt5.positions_get(symbol=symbol, magic=magic)
        if positions:
            pos = positions[0]
            print(f"\n📊 Position Info:")
            print(f"   Ticket: {pos.ticket}")
            print(f"   Type: {'BUY' if pos.type == 0 else 'SELL'}")
            print(f"   Volume: {pos.volume:.2f} lot")
            print(f"   Price Open: {pos.price_open:.2f}")
            print(f"   SL: {pos.sl:.2f}")
            print(f"   TP: {pos.tp:.2f}")
            print(f"   Profit: ${pos.profit:.2f}")
            print(f"   Swap: ${pos.swap:.2f}")
        
        print(f"\n{'='*80}")
        print("✅ Lệnh đã được mở thành công! Bạn có thể theo dõi trên MT5 Terminal.")
        print(f"{'='*80}\n")
    else:
        print(f"\n❌ ORDER FAILED")
        print(f"   Retcode: {result.retcode}")
        print(f"   Comment: {result.comment if hasattr(result, 'comment') else 'Unknown'}")
        error = mt5.last_error()
        print(f"   MT5 Error: {error}")
    
    mt5.shutdown()

if __name__ == "__main__":
    open_test_order()

