import MetaTrader5 as mt5
import sqlite3
import json
import os
import time
from datetime import datetime
from db import Database
from utils import connect_mt5

def load_config(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def update_trades_for_strategy(db, config, strategy_name):
    # 1. Connect to MT5 for this account
    if not connect_mt5(config):
        print(f"❌ Could not connect for {strategy_name}")
        return

    # Verify Strict Account Match
    current_account = mt5.account_info()
    if current_account is None:
        print(f"❌ Failed to retrieve account info.")
        return

    if current_account.login != config['account']:
        print(f"⚠️ CRITICAL: Account Mismatch! Configured: {config['account']} but Active: {current_account.login}")
        print(f"🛑 Aborting update for {strategy_name} to protect data.")
        return

    # 2. Get Pending Orders from DB for this strategy
    # Filter by strategy AND account_id (so we don't mix updates)
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT ticket FROM orders WHERE strategy_name = ? AND profit IS NULL AND account_id = ?", (strategy_name, config['account']))
    tickets = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not tickets:
        print(f"ℹ️ No pending trades for {strategy_name} (Account {config['account']})")
        return

    print(f"🔍 Checking {len(tickets)} pending trades for {strategy_name}...")

    # 3. Check history for each ticket
    # Note: A position might have multiple deals (entry, partial close, close). 
    # We want the DEAL that closed the position (ENTRY_OUT).
    
    # We fetch history from a comfortable past range
    from_date = datetime(2024, 1, 1) # Adjust as needed
    to_date = datetime.now()
    
    for ticket in tickets:
        # Get deals associated with this position ticket
        deals = mt5.history_deals_get(position=ticket)
        
        if deals:
            total_profit = 0.0
            close_price = 0.0
            is_closed = False
            
            for deal in deals:
                # ENTRY_OUT means it's a closing deal (TP, SL, or Manual Close)
                if deal.entry == mt5.DEAL_ENTRY_OUT:
                    total_profit += deal.profit + deal.swap + deal.commission
                    close_price = deal.price
                    is_closed = True
            
            if is_closed:
                print(f"✅ Found CLOSED Trade {ticket}: Profit=${total_profit:.2f}")
                db.update_order_profit(ticket, close_price, total_profit)
        else:
            # Case: Maybe ticket is invalid or too old, or simply still open
            # We can check if position still exists
            active_pos = mt5.positions_get(ticket=ticket)
            if not active_pos:
                print(f"❓ Trade {ticket} not in Open Positions and not in History (Manual Check Needed or date range issue)")

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
