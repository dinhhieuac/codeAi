import MetaTrader5 as mt5
import sqlite3
import json
import os
import time
from datetime import datetime, timedelta
from db import Database
from utils import connect_mt5

def load_config(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def _get_closed_positions_from_history(config, days_back=90):
    """Lấy danh sách position đã đóng từ MT5 history (theo magic), trả về dict position_id -> (profit, close_price, symbol, volume, type, open_price)."""
    from_date = datetime.utcnow() - timedelta(days=days_back)
    to_date = datetime.utcnow()
    magic = config.get('magic', 0)
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*")
    if not deals:
        return {}
    by_position = {}
    for d in deals:
        if getattr(d, 'magic', 0) != magic:
            continue
        pid = getattr(d, 'position_id', None) or getattr(d, 'position', None)
        if not pid:
            continue
        if pid not in by_position:
            by_position[pid] = {'in': None, 'out_profit': 0.0, 'out_price': 0.0, 'out_time': None}
        if d.entry == mt5.DEAL_ENTRY_IN:
            by_position[pid]['in'] = d
        elif d.entry == mt5.DEAL_ENTRY_OUT:
            by_position[pid]['out_profit'] += getattr(d, 'profit', 0) + getattr(d, 'swap', 0) + getattr(d, 'commission', 0)
            by_position[pid]['out_price'] = getattr(d, 'price', 0)
            by_position[pid]['out_time'] = getattr(d, 'time', None)  # Unix timestamp (giờ server)
    result = {}
    for pid, v in by_position.items():
        if v['out_profit'] != 0 or v['out_price'] != 0:
            din = v['in']
            is_buy = din and getattr(din, 'type', 1) == getattr(mt5, 'DEAL_TYPE_BUY', 0)
            # close_time: từ deal OUT (giờ server) -> ISO string cho DB
            out_ts = v.get('out_time')
            close_time_str = None
            if out_ts:
                try:
                    close_time_str = datetime.utcfromtimestamp(out_ts).strftime('%Y-%m-%d %H:%M:%S')
                except (TypeError, OSError):
                    pass
            result[pid] = (
                v['out_profit'],
                v['out_price'],
                getattr(din, 'symbol', '') if din else '',
                getattr(din, 'volume', 0) if din else 0,
                mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                getattr(din, 'price', 0) if din else 0,
                close_time_str
            )
    return result


def update_trades_for_strategy(db, config, strategy_name):
    # 1. Connect to MT5 for this account
    if not connect_mt5(config):
        print(f"❌ Could not connect for {strategy_name}")
        return

    current_account = mt5.account_info()
    if current_account is None:
        print(f"❌ Failed to retrieve account info.")
        return
    if current_account.login != config['account']:
        print(f"⚠️ CRITICAL: Account Mismatch! Configured: {config['account']} but Active: {current_account.login}")
        return

    account_id = config['account']
    magic = config.get('magic', 0)

    # 2. Lấy deals đã đóng từ history (theo khoảng thời gian, tránh history_deals_get(position=ticket) trả về None)
    closed = _get_closed_positions_from_history(config, days_back=90)
    if not closed and strategy_name == "Grid_Step":
        print(f"ℹ️ No closed deals in history for magic {magic} (Grid_Step)")

    # 3. Orders trong DB có profit IS NULL
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT ticket FROM orders WHERE strategy_name = ? AND profit IS NULL AND account_id = ?", (strategy_name, account_id))
    tickets_pending = [row[0] for row in cursor.fetchall()]

    updated = 0
    for ticket in tickets_pending:
        if ticket in closed:
            row = closed[ticket]
            profit, close_price = row[0], row[1]
            close_time = row[6] if len(row) > 6 else None
            db.update_order_profit(ticket, close_price, profit, close_time)
            print(f"✅ Updated trade {ticket}: Profit=${profit:.2f}")
            updated += 1

    # 4. Grid_Step: đồng bộ từ history — position đã đóng nhưng chưa có trong orders thì insert (backfill).
    # Khi config có "steps" (vd [5], [200]) thì bot chính đã ghi đúng Grid_Step_5.0 / Grid_Step_200.0;
    # không backfill với "Grid_Step" để tránh tạo bản ghi sai strategy_name.
    if strategy_name == "Grid_Step" and closed:
        steps = config.get("parameters", {}).get("steps")
        if steps is not None and len(steps) > 0:
            # Đang dùng multi-step: không backfill với "Grid_Step", tránh ghi nhận sai trong dashboard.
            pass
        else:
            p = config.get("parameters", {})
            step = float(p.get("sl_tp_price") or p.get("step") or 5.0)
            for position_id, row in closed.items():
                profit, close_price, symbol, volume, order_type, open_price = row[0], row[1], row[2], row[3], row[4], row[5]
                close_time = row[6] if len(row) > 6 else None
                if not db.order_exists(position_id):
                    order_type_str = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
                    op = float(open_price)
                    if order_type == mt5.ORDER_TYPE_BUY:
                        sl, tp = op - step, op + step
                    else:
                        sl, tp = op + step, op - step
                    db.log_order(position_id, strategy_name, symbol or config.get('symbol', 'XAUUSD'), order_type_str,
                                 float(volume), op, sl, tp, "GridStep", account_id)
                    db.update_order_profit(position_id, close_price, profit, close_time)
                    print(f"✅ Backfill Grid_Step position {position_id}: Profit=${profit:.2f}")
                    updated += 1

    conn.close()
    if not tickets_pending and not (strategy_name == "Grid_Step" and closed):
        if updated == 0:
            print(f"ℹ️ No pending trades to update for {strategy_name} (Account {account_id})")

def load_strategy_configs(script_dir):
    """
    Load strategy configs mapping from file or auto-detect from configs directory.
    Returns a dictionary mapping strategy_name -> config_file_path
    """
    # Try to load from strategy_configs.json first
    config_mapping_file = os.path.join(script_dir, "strategy_configs.json")
    if os.path.exists(config_mapping_file):
        try:
            with open(config_mapping_file, 'r') as f:
                mapping = json.load(f)
                # Convert relative paths to absolute
                strategies = {}
                for strat_name, config_path in mapping.items():
                    # Skip non-strategy keys like "description"
                    if strat_name == "description" or not isinstance(config_path, str):
                        continue
                    if not os.path.isabs(config_path):
                        config_path = os.path.join(script_dir, config_path)
                    strategies[strat_name] = config_path
                return strategies
        except Exception as e:
            print(f"⚠️ Could not load strategy_configs.json: {e}")
    
    # Fallback: Auto-detect from configs directory
    configs_dir = os.path.join(script_dir, "configs")
    strategies = {}
    
    if os.path.exists(configs_dir):
        # Scan for config files
        for filename in os.listdir(configs_dir):
            if filename.startswith("config_") and filename.endswith(".json"):
                config_path = os.path.join(configs_dir, filename)
                try:
                    config = load_config(config_path)
                    # Try to extract strategy name from config
                    # Check if there's a 'version' or 'description' field that might contain strategy name
                    strategy_name = None
                    
                    # Method 1: Check if config has a 'strategy_name' field
                    if 'strategy_name' in config:
                        strategy_name = config['strategy_name']
                    # Method 2: Try to infer from filename (e.g., config_1_v2.json -> Strategy_1_Trend_HA_V2)
                    elif filename.startswith("config_1"):
                        if "v2.1" in filename.lower() or "v2_1" in filename.lower():
                            strategy_name = "Strategy_1_Trend_HA_V2.1"
                        elif "v11" in filename.lower():
                            strategy_name = "Strategy_1_Trend_HA_V11"
                        elif "v2" in filename.lower():
                            strategy_name = "Strategy_1_Trend_HA_V2"
                        else:
                            strategy_name = "Strategy_1_Trend_HA"
                    elif filename.startswith("config_2"):
                        strategy_name = "Strategy_2_EMA_ATR"
                    elif filename.startswith("config_3"):
                        strategy_name = "Strategy_3_PA_Volume"
                    elif filename.startswith("config_4"):
                        strategy_name = "Strategy_4_UT_Bot"
                    elif filename.startswith("config_5"):
                        strategy_name = "Strategy_5_Filter_First"
                    
                    if strategy_name:
                        strategies[strategy_name] = config_path
                        print(f"📋 Auto-detected: {strategy_name} -> {filename}")
                except Exception as e:
                    print(f"⚠️ Could not parse {filename}: {e}")
    
    # If still empty, use default mapping
    if not strategies:
        print("⚠️ No strategies auto-detected, using default mapping")
        strategies = {
            "Strategy_1_Trend_HA": os.path.join(script_dir, "configs", "config_1.json"),
            "Strategy_1_Trend_HA_V2": os.path.join(script_dir, "configs", "config_1_v2.json"),
            "Strategy_1_Trend_HA_V2.1": os.path.join(script_dir, "configs", "config_1_v2.1.json"),
            "Strategy_1_Trend_HA_V11": os.path.join(script_dir, "configs", "config_1_v11.json"),
            "Strategy_2_EMA_ATR": os.path.join(script_dir, "configs", "config_2.json"),
            "Strategy_3_PA_Volume": os.path.join(script_dir, "configs", "config_3.json"),
            "Strategy_4_UT_Bot": os.path.join(script_dir, "configs", "config_4.json"),
            "Strategy_5_Filter_First": os.path.join(script_dir, "configs", "config_5.json")
        }
    
    return strategies

def main():
    # Pass None so db.py uses the internal absolute path logic
    db = Database(None)
    
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Auto-load strategy configs mapping
    strategies = load_strategy_configs(script_dir)
    
    from datetime import datetime
    
    for strat_name, config_file in strategies.items():
        if os.path.exists(config_file):
            print(f"\n--- Processing {strat_name} ---")
            config = load_config(config_file)
            update_trades_for_strategy(db, config, strat_name)
        else:
            print(f"⚠️ Config not found: {config_file} (skipping {strat_name})")

    print("\n✅ Update Complete!")
    mt5.shutdown()

if __name__ == "__main__":
    while True:
        main()
        print("Sleeping for 600 seconds...") 
        time.sleep(600)
