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

def _get_closed_positions_from_history(config, days_back=90, debug=False):
    """Lấy danh sách position đã đóng từ MT5 history (theo magic), trả về dict position_id (int) -> (profit, close_price, symbol, volume, type, open_price, close_time_str)."""
    # Dùng local time để khớp với MT5 terminal (broker/server time thường gần local)
    now = datetime.now()
    from_date = now - timedelta(days=days_back)
    to_date = now
    magic = config.get('magic', 0)
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*")
    if not deals:
        if debug:
            print(f"   [debug] history_deals_get: 0 deals (magic={magic})")
        return {}
    n_total = len(deals)
    by_position = {}
    entry_out = getattr(mt5, 'DEAL_ENTRY_OUT', 1)
    entry_in = getattr(mt5, 'DEAL_ENTRY_IN', 0)
    entry_inout = getattr(mt5, 'DEAL_ENTRY_INOUT', 4)
    for d in deals:
        d_magic = getattr(d, 'magic', 0)
        if d_magic != magic:
            continue
        pid = getattr(d, 'position_id', None) or getattr(d, 'position', None)
        if pid is None:
            continue
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        if pid not in by_position:
            by_position[pid] = {'in': None, 'out_profit': 0.0, 'out_price': 0.0, 'out_time': None}
        d_entry = getattr(d, 'entry', None)
        if d_entry == entry_in:
            by_position[pid]['in'] = d
        elif d_entry == entry_out:
            by_position[pid]['out_profit'] += getattr(d, 'profit', 0) + getattr(d, 'swap', 0) + getattr(d, 'commission', 0)
            by_position[pid]['out_price'] = getattr(d, 'price', 0)
            by_position[pid]['out_time'] = getattr(d, 'time', None)
        elif d_entry == entry_inout:
            by_position[pid]['in'] = d
            by_position[pid]['out_profit'] += getattr(d, 'profit', 0) + getattr(d, 'swap', 0) + getattr(d, 'commission', 0)
            by_position[pid]['out_price'] = getattr(d, 'price', 0)
            by_position[pid]['out_time'] = getattr(d, 'time', None)
    n_with_magic = sum(1 for d in deals if getattr(d, 'magic', 0) == magic)
    result = {}
    for pid, v in by_position.items():
        if v['out_profit'] != 0 or v['out_price'] != 0:
            din = v['in']
            is_buy = din and getattr(din, 'type', 1) == getattr(mt5, 'DEAL_TYPE_BUY', 0)
            out_ts = v.get('out_time')
            close_time_str = None
            if out_ts:
                try:
                    close_time_str = datetime.utcfromtimestamp(out_ts).strftime('%Y-%m-%d %H:%M:%S')
                except (TypeError, OSError):
                    pass
            result[int(pid)] = (
                v['out_profit'],
                v['out_price'],
                getattr(din, 'symbol', '') if din else '',
                getattr(din, 'volume', 0) if din else 0,
                mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                getattr(din, 'price', 0) if din else 0,
                close_time_str
            )
    if debug:
        print(f"   [debug] Deals: total={n_total}, magic={magic} -> {n_with_magic}, closed positions={len(result)}")
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

    account_id = int(config.get('account', 0))
    magic = config.get('magic', 0)

    # 2. Lấy deals đã đóng từ history (theo khoảng thời gian, tránh history_deals_get(position=ticket) trả về None)
    closed = _get_closed_positions_from_history(config, days_back=90, debug=True)
    if not closed and (strategy_name == "Grid_Step" or strategy_name.startswith("Grid_Step_BTC")):
        print(f"ℹ️ No closed deals in history for magic {magic} ({strategy_name})")

    # 3. Orders trong DB có profit IS NULL (match bằng int để khớp với position_id từ MT5)
    # Thử account_id từ config trước; nếu không có thì thử account_id=0 (bản ghi cũ có thể thiếu account_id)
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ticket FROM orders WHERE strategy_name = ? AND profit IS NULL AND (account_id = ? OR account_id = 0)",
        (strategy_name, account_id)
    )
    tickets_pending = [row[0] for row in cursor.fetchall()]
    # Chuẩn hóa ticket sang int để khớp với key trong closed (position_id)
    tickets_pending_int = []
    for t in tickets_pending:
        try:
            tickets_pending_int.append(int(t))
        except (TypeError, ValueError):
            tickets_pending_int.append(t)
    print(f"   [debug] Pending in DB: {len(tickets_pending_int)} (strategy={strategy_name}, account={account_id})")

    updated = 0
    for ticket in tickets_pending_int:
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

    # 4b. Grid_21_Step: tương tự Grid_Step — khi config có "steps" thì không backfill với "Grid_21_Step".
    if strategy_name == "Grid_21_Step" and closed:
        steps = config.get("parameters", {}).get("steps")
        if steps is not None and len(steps) > 0:
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
                                 float(volume), op, sl, tp, "Grid21", account_id)
                    db.update_order_profit(position_id, close_price, profit, close_time)
                    print(f"✅ Backfill Grid_21_Step position {position_id}: Profit=${profit:.2f}")
                    updated += 1

    # 4c. Grid_22_Step: tương tự — khi config có "steps" thì không backfill với "Grid_22_Step".
    if strategy_name == "Grid_22_Step" and closed:
        steps = config.get("parameters", {}).get("steps")
        if steps is not None and len(steps) > 0:
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
                                 float(volume), op, sl, tp, "Grid22", account_id)
                    db.update_order_profit(position_id, close_price, profit, close_time)
                    print(f"✅ Backfill Grid_22_Step position {position_id}: Profit=${profit:.2f}")
                    updated += 1

    # 4d. Grid_3_Step: tương tự — khi config có "steps" thì không backfill với "Grid_3_Step".
    if strategy_name == "Grid_3_Step" and closed:
        steps = config.get("parameters", {}).get("steps")
        if steps is not None and len(steps) > 0:
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
                                 float(volume), op, sl, tp, "Grid3", account_id)
                    db.update_order_profit(position_id, close_price, profit, close_time)
                    print(f"✅ Backfill Grid_3_Step position {position_id}: Profit=${profit:.2f}")
                    updated += 1

    # 4e. Grid_Step_BTC_V2_*: không backfill (bot đã ghi đúng strategy_name khi mở lệnh), chỉ update profit/close_time.

    conn.close()
    _skip_msg = (
        (strategy_name == "Grid_Step" and closed)
        or (strategy_name == "Grid_21_Step" and closed)
        or (strategy_name == "Grid_22_Step" and closed)
        or (strategy_name == "Grid_3_Step" and closed)
        or (strategy_name.startswith("Grid_Step_BTC_V2") and closed)
    )
    if not tickets_pending_int and not _skip_msg:
        if updated == 0:
            print(f"ℹ️ No pending trades to update for {strategy_name} (Account {account_id})")
    elif updated > 0:
        print(f"   → Updated {updated} trade(s) for {strategy_name}")

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
                    
                    # Method 1: Top-level or parameters.strategy_name (Grid Step V12, V11, ...)
                    strategy_name = config.get('strategy_name') or config.get("parameters", {}).get("strategy_name")
                    # Method 2: Infer from filename for Grid Step
                    if not strategy_name and filename.startswith("config_grid_step"):
                        if "v12" in filename.lower():
                            strategy_name = "Grid_Step_V12"
                        elif "v11" in filename.lower():
                            strategy_name = "Grid_Step_V11"
                        elif "v22" in filename.lower():
                            strategy_name = "Grid_22_Step"
                        elif "v21" in filename.lower():
                            strategy_name = "Grid_21_Step"
                        elif "v4" in filename.lower():
                            strategy_name = "Grid_Step_V4"
                        elif "v3" in filename.lower():
                            strategy_name = "Grid_3_Step"
                        elif "v2" in filename.lower() and "btc" not in filename.lower():
                            strategy_name = "Grid_Step_V2"
                        elif "btc_v2" in filename.lower() or "btc_v2" in filename:
                            strategy_name = "Grid_Step_BTC_V2"
                        elif "btc" in filename.lower():
                            strategy_name = "Grid_Step_BTC"
                        else:
                            strategy_name = "Grid_Step"
                    # Method 3: Other strategy configs (config_1, config_2, ...)
                    elif not strategy_name and filename.startswith("config_1"):
                        if "v2.1" in filename.lower() or "v2_1" in filename.lower():
                            strategy_name = "Strategy_1_Trend_HA_V2.1"
                        elif "v11" in filename.lower():
                            strategy_name = "Strategy_1_Trend_HA_V11"
                        elif "v2" in filename.lower():
                            strategy_name = "Strategy_1_Trend_HA_V2"
                        else:
                            strategy_name = "Strategy_1_Trend_HA"
                    elif not strategy_name and filename.startswith("config_2"):
                        strategy_name = "Strategy_2_EMA_ATR"
                    elif not strategy_name and filename.startswith("config_3"):
                        strategy_name = "Strategy_3_PA_Volume"
                    elif not strategy_name and filename.startswith("config_4"):
                        strategy_name = "Strategy_4_UT_Bot"
                    elif not strategy_name and filename.startswith("config_5"):
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

def main(db_path=None):
    """Chạy sync MT5 -> DB. db_path: đường dẫn trades.db (None = dùng mặc định GridStep/trades.db)."""
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if db_path is None:
        db_path = os.path.join(script_dir, "trades.db")
    db_path = os.path.normpath(os.path.abspath(db_path))
    print(f"📂 Using DB: {db_path}")
    db = Database(db_path)
    
    # Auto-load strategy configs mapping
    strategies = load_strategy_configs(script_dir)
    
    from datetime import datetime
    
    for strat_name, config_file in strategies.items():
        if not os.path.exists(config_file):
            print(f"⚠️ Config not found: {config_file} (skipping {strat_name})")
            continue
        config = load_config(config_file)
        # Grid Step BTC (v1): config có "steps" [200] → update từng strategy_name Grid_Step_200.0, ...
        if strat_name == "Grid_Step_BTC":
            steps = config.get("parameters", {}).get("steps")
            if steps is not None and len(steps) > 0:
                for step in steps:
                    sn = f"Grid_Step_{float(step)}"
                    print(f"\n--- Processing {sn} (Grid Step BTC) ---")
                    update_trades_for_strategy(db, config, sn)
            else:
                print(f"\n--- Processing {strat_name} ---")
                update_trades_for_strategy(db, config, "Grid_Step")
        # Grid Step BTC V2: config có "steps" [200] → update từng strategy_name Grid_Step_BTC_V2_200.0, ...
        elif strat_name == "Grid_Step_BTC_V2":
            steps = config.get("parameters", {}).get("steps")
            if steps is not None and len(steps) > 0:
                for step in steps:
                    sn = f"Grid_Step_BTC_V2_{float(step)}"
                    print(f"\n--- Processing {sn} (Grid Step BTC V2) ---")
                    update_trades_for_strategy(db, config, sn)
            else:
                print(f"\n--- Processing {strat_name} ---")
                update_trades_for_strategy(db, config, "Grid_Step_BTC_V2")
        elif strat_name == "Grid_21_Step":
            steps = config.get("parameters", {}).get("steps")
            if steps is not None and len(steps) > 0:
                for step in steps:
                    sn = f"Grid_21_Step_{float(step)}"
                    print(f"\n--- Processing {sn} (Grid 21 Step) ---")
                    update_trades_for_strategy(db, config, sn)
            else:
                print(f"\n--- Processing {strat_name} ---")
                update_trades_for_strategy(db, config, "Grid_21_Step")
        elif strat_name == "Grid_22_Step":
            steps = config.get("parameters", {}).get("steps")
            if steps is not None and len(steps) > 0:
                for step in steps:
                    sn = f"Grid_22_Step_{float(step)}"
                    print(f"\n--- Processing {sn} (Grid 22 Step) ---")
                    update_trades_for_strategy(db, config, sn)
            else:
                print(f"\n--- Processing {strat_name} ---")
                update_trades_for_strategy(db, config, "Grid_22_Step")
        else:
            print(f"\n--- Processing {strat_name} ---")
            update_trades_for_strategy(db, config, strat_name)

    print("\n✅ Update Complete!")
    mt5.shutdown()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync closed trades from MT5 to DB")
    parser.add_argument("--db", type=str, default=None, help="Path to trades.db (default: GridStep/trades.db)")
    parser.add_argument("--once", action="store_true", help="Run once and exit (no loop)")
    args = parser.parse_args()
    db_path = args.db
    if os.environ.get("TRADES_DB_PATH"):
        db_path = db_path or os.environ.get("TRADES_DB_PATH")
    try:
        if args.once:
            main(db_path=db_path)
        else:
            while True:
                main(db_path=db_path)
                print("Sleeping for 600 seconds...")
                time.sleep(600)
    except KeyboardInterrupt:
        print("\n🛑 update_db stopped by user (Ctrl+C)")
        try:
            mt5.shutdown()
        except Exception:
            pass
