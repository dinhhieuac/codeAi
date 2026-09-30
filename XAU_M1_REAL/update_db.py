import MetaTrader5 as mt5
import sqlite3
import json
import os
import time
import signal
import sys
from datetime import datetime
from db import Database
from utils import connect_mt5, load_config

def update_trades_for_strategy(db, config, strategy_name):
    # Kiểm tra xem MT5 đã đang kết nối tới tài khoản nào
    current_account = mt5.account_info()
    
    if current_account is not None:
        if current_account.login != config.get('account'):
            print(f"ℹ️ Bỏ qua {strategy_name}: Config account ({config.get('account')}) khác với tài khoản đang hoạt động trên MT5 ({current_account.login})")
            return
    else:
        # Nếu MT5 chưa kết nối tài khoản nào, mới tiến hành kết nối
        if not connect_mt5(config):
            print(f"❌ Không thể kết nối MT5 cho {strategy_name}")
            return
        current_account = mt5.account_info()
        if current_account is None or current_account.login != config.get('account'):
            print(f"🛑 Không thể xác thực tài khoản cho {strategy_name}")
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
            close_time = None
            is_closed = False
            
            for deal in deals:
                # ENTRY_OUT means it's a closing deal (TP, SL, or Manual Close)
                if deal.entry == mt5.DEAL_ENTRY_OUT:
                    total_profit += deal.profit + deal.swap + deal.commission
                    close_price = deal.price
                    is_closed = True
                    close_time = datetime.fromtimestamp(deal.time).strftime("%Y-%m-%d %H:%M:%S")
            
            if is_closed:
                print(f"✅ Found CLOSED Trade {ticket}: Profit=${total_profit:.2f}")
                db.update_order_profit(ticket, close_price, total_profit, close_time)
        else:
            # Case: Maybe ticket is invalid or too old, or simply still open
            # We can check if position still exists
            active_pos = mt5.positions_get(ticket=ticket)
            if not active_pos:
                print(f"❓ Trade {ticket} not in Open Positions and not in History (Manual Check Needed or date range issue)")

    # 4. Check for missing trades in MT5 history that match this strategy's magic number
    magic = config.get('magic')
    if magic:
        from_date = datetime.now() - timedelta(days=90)
        to_date = datetime.now() + timedelta(days=1)
        recent_deals = mt5.history_deals_get(from_date, to_date)
        if recent_deals:
            conn = sqlite3.connect(db.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT ticket, profit FROM orders WHERE account_id = ?", (config['account'],))
            existing_db_orders = {row[0]: row[1] for row in cursor.fetchall()}
            
            deals_by_pos = {}
            for d in recent_deals:
                if d.position_id > 0 and d.magic == magic:
                    deals_by_pos.setdefault(d.position_id, []).append(d)
                    
            for pos_id, d_list in deals_by_pos.items():
                in_deal = next((d for d in d_list if d.entry == mt5.DEAL_ENTRY_IN), None)
                out_deals = [d for d in d_list if d.entry == mt5.DEAL_ENTRY_OUT]
                tot_p = sum(d.profit + d.swap + d.commission for d in d_list)
                is_cls = len(out_deals) > 0
                cp = out_deals[-1].price if is_cls else None
                ct = datetime.fromtimestamp(out_deals[-1].time).strftime("%Y-%m-%d %H:%M:%S") if is_cls else None
                
                if pos_id in existing_db_orders:
                    if existing_db_orders[pos_id] is None and is_cls:
                        db.update_order_profit(pos_id, cp, round(tot_p, 2), ct)
                        print(f"✅ Updated CLOSED Trade {pos_id} for {strategy_name}: Profit=${tot_p:.2f}")
                else:
                    if in_deal:
                        o_type = "BUY" if in_deal.type == mt5.DEAL_TYPE_BUY else "SELL"
                        ot = datetime.fromtimestamp(in_deal.time).strftime("%Y-%m-%d %H:%M:%S")
                        sl, tp, init_sl = 0.0, 0.0, in_deal.price
                        try:
                            ho = mt5.history_orders_get(ticket=pos_id)
                            if ho:
                                sl = ho[0].sl
                                tp = ho[0].tp
                                init_sl = sl if sl > 0 else in_deal.price
                        except Exception:
                            pass
                        cursor.execute('''
                            INSERT OR REPLACE INTO orders (ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, open_time, close_price, profit, close_time, comment, account_id, initial_sl)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (pos_id, strategy_name, in_deal.symbol, o_type, in_deal.volume, in_deal.price, sl, tp, ot, cp, (round(tot_p, 2) if is_cls else None), ct, in_deal.comment, config['account'], init_sl))
                        try:
                            cursor.execute('''
                                INSERT INTO order_logs (ticket, timestamp, event_type, old_sl, new_sl, old_tp, new_tp, current_price, profit_pips, profit_usd, reason, details)
                                VALUES (?, ?, 'ENTRY', ?, ?, ?, ?, ?, 0.0, 0.0, ?, ?)
                            ''', (pos_id, ot, init_sl, sl, tp, tp, in_deal.price, f"Mở lệnh {o_type} {in_deal.volume} lot tại giá {in_deal.price:.2f}", json.dumps({"strategy": strategy_name, "comment": in_deal.comment}, ensure_ascii=False)))
                            if is_cls and ct:
                                cursor.execute('''
                                    INSERT INTO order_logs (ticket, timestamp, event_type, old_sl, new_sl, old_tp, new_tp, current_price, profit_pips, profit_usd, reason, details)
                                    VALUES (?, ?, 'EXIT', NULL, NULL, NULL, NULL, ?, NULL, ?, ?, NULL)
                                ''', (pos_id, ct, cp, round(tot_p, 2), f"Đóng lệnh tại giá {cp:.2f} (Lợi nhuận: ${round(tot_p, 2):.2f})"))
                        except Exception:
                            pass
                        conn.commit()
                        print(f"📥 Imported missing Trade {pos_id} for {strategy_name}: Profit={'${:.2f}'.format(tot_p) if is_cls else 'OPEN'}")
            conn.close()

def load_strategy_configs(script_dir):
    """
    Load strategy configs mapping from file or auto-detect from configs directory.
    Returns a dictionary mapping strategy_name -> config_file_path
    """
    configs_dir = os.path.join(script_dir, "configs")
    # Try to load from strategy_configs.json first
    config_mapping_file = os.path.join(script_dir, "strategy_configs.json")
    if os.path.exists(config_mapping_file):
        try:
            with open(config_mapping_file, 'r') as f:
                mapping = json.load(f)
                # Convert relative paths to absolute
                strategies = {}
                for strat_name, config_path in mapping.items():
                    if strat_name == "description":
                        continue
                    if not os.path.isabs(config_path):
                        config_path = os.path.join(script_dir, config_path)
                    strategies[strat_name] = config_path

                # Auto-detect any extra config_exp_*.json files
                if os.path.exists(configs_dir):
                    for filename in os.listdir(configs_dir):
                        if filename.startswith("config_exp_") and filename.endswith(".json"):
                            cfg_path = os.path.join(configs_dir, filename)
                            try:
                                cfg_data = load_config(cfg_path)
                                if cfg_data and 'magic' in cfg_data:
                                    exp_strat = f"Strategy_1_Trend_HA_V2_{cfg_data['magic']}"
                                    if exp_strat not in strategies:
                                        strategies[exp_strat] = cfg_path
                            except Exception:
                                pass
                return strategies
        except Exception as e:
            print(f"⚠️ Could not load strategy_configs.json: {e}")
    
    # Fallback: Auto-detect from configs directory
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
                    # Method 2: Try to infer from filename
                    elif filename.startswith("config_exp_"):
                        if 'magic' in config:
                            strategy_name = f"Strategy_1_Trend_HA_V2_{config['magic']}"
                        else:
                            strategy_name = f"Strategy_1_Trend_HA_V2_{filename.replace('.json', '')}"
                    elif filename.startswith("config_1"):
                        if "v2.1" in filename.lower() or "v2_1" in filename.lower():
                            strategy_name = "Strategy_1_Trend_HA_V2.1"
                        elif "v2" in filename.lower():
                            strategy_name = "Strategy_1_Trend_HA_V2"
                        elif "v1.1" in filename.lower() or "v1_1" in filename.lower():
                            strategy_name = "Strategy_1_Trend_HA_V1.1"
                        elif "v3" in filename.lower():
                            strategy_name = "Strategy_1_Trend_HA_V3"
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
            "Strategy_1_Trend_HA_V1.1": os.path.join(script_dir, "configs", "config_1_v1.1.json"),
            "Strategy_1_Trend_HA_V2": os.path.join(script_dir, "configs", "config_1_v2.json"),
            "Strategy_1_Trend_HA_V2.1": os.path.join(script_dir, "configs", "config_1_v2.1.json"),
            "Strategy_2_EMA_ATR": os.path.join(script_dir, "configs", "config_2.json"),
            "Strategy_3_PA_Volume": os.path.join(script_dir, "configs", "config_3.json"),
            "Strategy_4_UT_Bot": os.path.join(script_dir, "configs", "config_4.json"),
            "Strategy_5_Filter_First": os.path.join(script_dir, "configs", "config_5.json")
        }
    
    return strategies

def main():
    try:
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
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted during update. Cleaning up...")
        raise  # Re-raise to be handled by outer try-catch

def signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) gracefully"""
    print("\n\n⚠️ Interrupt received. Shutting down gracefully...")
    try:
        mt5.shutdown()
        print("✅ MT5 connection closed.")
    except:
        pass
    print("👋 Goodbye!")
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        while True:
            main()
            print("Sleeping for 600 seconds... (Press Ctrl+C to stop)") 
            try:
                time.sleep(600)
            except KeyboardInterrupt:
                print("\n⚠️ Interrupted during sleep. Exiting gracefully...")
                break
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted. Shutting down MT5 and exiting...")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    finally:
        # Ensure MT5 is properly shut down
        try:
            mt5.shutdown()
            print("✅ MT5 connection closed.")
        except:
            pass
        print("👋 Goodbye!")
