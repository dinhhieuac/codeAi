"""
Bot Scalp Sideway Strategy
Chỉ cần khai báo config file để chạy bot

Usage:
    python scalp_sideway.py configs/scalp_sideway_xau.json
    python scalp_sideway.py configs/scalp_sideway_eur.json
"""

import MetaTrader5 as mt5
import time
import sys
import os
import pandas as pd
from datetime import datetime
from typing import Optional, Dict

# Import local modules
sys.path.append('..')
from db import Database
from utils import (
    load_config, 
    connect_mt5, 
    get_data, 
    send_telegram, 
    manage_position, 
    log_to_file,
    calculate_rsi
)
from utils_scalp_sideway import (
    calculate_ema,
    calculate_atr,
    check_supply_m5,
    check_demand_m5,
    check_bad_market_conditions,
    check_sideway_context,
    calculate_delta_high,
    calculate_delta_low,
    is_valid_delta_high,
    is_valid_delta_low,
    DeltaCountTracker,
    check_sell_signal_condition,
    check_buy_signal_condition,
    calculate_sl_tp,
    check_max_positions_per_zone,
    check_m5_candle_change,
    get_min_atr_threshold,
    get_delta_threshold_multiplier,
    check_price_breakout_sell,
    check_price_breakout_buy
)

# Initialize Database
db = Database()

# Global trackers (persist across iterations)
sell_count_tracker = None
buy_count_tracker = None
last_supply_price = None
last_demand_price = None
last_trade_time = None
last_m5_candle_time = None


def scalp_sideway_logic(config: Dict, error_count: int = 0) -> tuple:
    """
    Scalp Sideway Strategy Logic
    
    Args:
        config: Configuration dictionary
        error_count: Current error count
    
    Returns:
        (error_count, last_error_code)
    """
    global sell_count_tracker, buy_count_tracker
    global last_supply_price, last_demand_price
    global last_trade_time, last_m5_candle_time
    
    try:
        symbol = config['symbol']
        volume = config.get('volume', 0.01)
        magic = config['magic']
        max_positions = config.get('max_positions', 1)
        
        # Initialize trackers if not exists
        if sell_count_tracker is None:
            sell_count_tracker = DeltaCountTracker(min_count=2)
        if buy_count_tracker is None:
            buy_count_tracker = DeltaCountTracker(min_count=2)
        
        # --- 1. Manage Existing Positions ---
        all_positions = mt5.positions_get(symbol=symbol)
        positions = [pos for pos in (all_positions or []) if pos.magic == magic]
        if positions:
            for pos in positions:
                manage_position(pos.ticket, symbol, magic, config)
            if len(positions) >= max_positions:
                return error_count, 0
        
        # --- 2. Data Fetching ---
        df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 300)
        if df_m1 is None:
            print(f"⚠️ Không thể lấy dữ liệu M1 cho {symbol}")
            return error_count, 0
        
        df_m5 = get_data(symbol, mt5.TIMEFRAME_M5, 100)
        if df_m5 is None:
            print(f"⚠️ Không thể lấy dữ liệu M5 cho {symbol}")
            return error_count, 0
        
        # --- 3. Calculate Indicators ---
        df_m1['atr'] = calculate_atr(df_m1, 14)
        # Không cần EMA9 cho M1 (theo document)
        
        df_m5['atr'] = calculate_atr(df_m5, 14)
        df_m5['ema21'] = calculate_ema(df_m5['close'], 21)
        
        # Get current candles (last completed)
        if len(df_m1) < 2 or len(df_m5) < 2:
            return error_count, 0
        
        current_m1_idx = len(df_m1) - 2  # Last completed M1 candle (index)
        current_m5_idx = len(df_m5) - 2  # Last completed M5 candle (index)
        
        current_m1_candle = df_m1.iloc[current_m1_idx]
        current_m5_candle = df_m5.iloc[current_m5_idx]
        
        # Log details
        log_details = []
        log_details.append(f"\n{'='*80}")
        log_details.append(f"📊 [Scalp Sideway] {symbol} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_details.append(f"{'='*80}")
        
        # --- 4. Check Bad Market Conditions ---
        # Get options from config (default: False)
        enable_atr_increasing_check = config.get('enable_atr_increasing_check', False)
        enable_large_body_check = config.get('enable_large_body_check', False)
        is_valid_market, conditions, market_msg = check_bad_market_conditions(
            df_m1, 
            current_idx=current_m1_idx,
            enable_atr_increasing_check=enable_atr_increasing_check,
            enable_large_body_check=enable_large_body_check
        )
        log_details.append(f"\n🔍 [Thị Trường]")
        log_details.append(f"   {'✅' if is_valid_market else '❌'} {market_msg}")
        if not is_valid_market:
            # Log but don't return (continue to check other conditions for logging)
            log_details.append(f"   ⚠️ Thị trường xấu nhưng vẫn tiếp tục kiểm tra các điều kiện khác")
        
        # --- 5. Check Sideway Context ---
        is_sideway, sideway_msg = check_sideway_context(df_m5, current_idx=current_m5_idx)
        log_details.append(f"\n🔍 [Bối Cảnh Sideway M5]")
        log_details.append(f"   {'✅' if is_sideway else '❌'} {sideway_msg}")
        if not is_sideway:
            # Print log and return
            for detail in log_details:
                print(detail)
            return error_count, 0  # Not sideway, skip
        
        # --- 6. Check Supply/Demand Zones ---
        is_supply, supply_price, supply_msg = check_supply_m5(df_m5, current_idx=current_m5_idx)
        is_demand, demand_price, demand_msg = check_demand_m5(df_m5, current_idx=current_m5_idx)
        
        log_details.append(f"\n🔍 [Supply/Demand Zones M5]")
        log_details.append(f"   {'✅' if is_supply else '❌'} Supply: {supply_msg}")
        log_details.append(f"   {'✅' if is_demand else '❌'} Demand: {demand_msg}")
        
        # Update last known zones
        if is_supply:
            last_supply_price = supply_price
            log_details.append(f"   📍 Supply zone: {supply_price:.5f}")
        if is_demand:
            last_demand_price = demand_price
            log_details.append(f"   📍 Demand zone: {demand_price:.5f}")
        
        signal_type = None
        entry_price = None
        sl = None
        tp1 = None
        tp2 = None
        
        # Get delta threshold multiplier (k) from config
        delta_k = get_delta_threshold_multiplier(symbol, config)
        
        log_details.append(f"\n🔍 [SELL Signal Check]")
        
        # --- 7. SELL Signal Check ---
        if not is_supply or last_supply_price is None:
            log_details.append(f"   ❌ Không có Supply zone hoặc chưa có Supply zone hợp lệ")
        
        if is_supply and last_supply_price is not None:
            log_details.append(f"   ✅ Có Supply zone: {last_supply_price:.5f}")
            
            # Check price breakout (theo document: High_M1 > High_M5_supply + 0.4×ATR_M5 → Dừng trade 40 phút)
            price_breakout, breakout_msg = check_price_breakout_sell(
                df_m1, 
                last_supply_price, 
                df_m5, 
                current_idx=current_m1_idx
            )
            if price_breakout:
                log_details.append(f"   ⚠️ {breakout_msg}")
                log_details.append(f"{'='*80}\n")
                for detail in log_details:
                    print(detail)
                return error_count, 0
            
            # Không cần kiểm tra EMA9 (theo document)
            # Bắt đầu kiểm tra DeltaHigh ngay
            # Calculate DeltaHigh
            delta_high, delta_msg = calculate_delta_high(df_m1, current_idx=current_m1_idx)
            if delta_high is not None:
                atr_m1 = current_m1_candle['atr']
                is_valid_delta, delta_valid_msg = is_valid_delta_high(delta_high, atr_m1, threshold=delta_k)
                log_details.append(f"   📊 DeltaHigh: {delta_high:.5f}, ATR_M1: {atr_m1:.5f}, k: {delta_k}")
                log_details.append(f"   {'✅' if is_valid_delta else '❌'} {delta_valid_msg}")
                
                # Update count
                count, is_triggered = sell_count_tracker.update(is_valid_delta, current_idx=current_m1_idx)
                log_details.append(f"   📊 Count: {count}/2")
                    
                    if is_triggered:
                        log_details.append(f"   ✅ Count >= 2 → Kiểm tra điều kiện SELL")
                        # Check SELL signal condition
                        is_sell, sell_msg = check_sell_signal_condition(
                            df_m1,
                            last_supply_price,
                            df_m5,
                            current_idx=current_m1_idx,
                            buffer_multiplier=0.2
                        )
                        log_details.append(f"   {'✅' if is_sell else '❌'} {sell_msg}")
                        
                        if is_sell:
                            # Check max positions per zone
                            is_valid_pos, pos_count, pos_msg = check_max_positions_per_zone(
                                positions,
                                last_supply_price,
                                "SUPPLY",
                                max_positions=2
                            )
                            log_details.append(f"   {'✅' if is_valid_pos else '❌'} {pos_msg}")
                            
                            if is_valid_pos:
                                # Check M5 candle change (if last trade was SL)
                                if last_trade_time is not None and last_m5_candle_time is not None:
                                    # Get current M5 candle time
                                    current_m5_time = df_m5.iloc[current_m5_idx]['time']
                                    if isinstance(current_m5_time, pd.Timestamp):
                                        current_m5_time = current_m5_time.to_pydatetime()
                                    
                                    # Check if M5 candle has changed
                                    if current_m5_time <= last_m5_candle_time:
                                        log_details.append(f"   ⚠️ M5 chưa đổi nến sau lệnh SL (last: {last_m5_candle_time}, current: {current_m5_time})")
                                        log_details.append(f"{'='*80}\n")
                                        for detail in log_details:
                                            print(detail)
                                        return error_count, 0
                                
                                signal_type = "SELL"
                                entry_price = current_m1_candle['close']
                                
                                # Calculate SL/TP
                                symbol_info = mt5.symbol_info(symbol)
                                sl, tp1, tp2, sl_tp_info = calculate_sl_tp(
                                    entry_price,
                                    "SELL",
                                    atr_m1,
                                    atr_multiplier=2.0,
                                    tp_multiplier=2.0,
                                    symbol_info=symbol_info
                                )
                                
                                log_details.append(f"\n🚀 [SELL SIGNAL] Tất cả điều kiện đã thỏa!")
                                log_details.append(f"   Entry: {entry_price:.5f}")
                                log_details.append(f"   SL: {sl:.5f}")
                                log_details.append(f"   TP1: {tp1:.5f} | TP2: {tp2:.5f}")
        
        # --- 8. BUY Signal Check ---
        log_details.append(f"\n🔍 [BUY Signal Check]")
        
        if signal_type is None:
            if not is_demand or last_demand_price is None:
                log_details.append(f"   ❌ Không có Demand zone hoặc chưa có Demand zone hợp lệ")
        
        if signal_type is None and is_demand and last_demand_price is not None:
            log_details.append(f"   ✅ Có Demand zone: {last_demand_price:.5f}")
            
            # Check price breakout (theo document: Low_M1 < Low_M5_demand - 0.4×ATR_M5 → Dừng trade 40 phút)
            price_breakout, breakout_msg = check_price_breakout_buy(
                df_m1, 
                last_demand_price, 
                df_m5, 
                current_idx=current_m1_idx
            )
            if price_breakout:
                log_details.append(f"   ⚠️ {breakout_msg}")
                log_details.append(f"{'='*80}\n")
                for detail in log_details:
                    print(detail)
                return error_count, 0
            
            # Không cần kiểm tra EMA9 (theo document)
            # Bắt đầu kiểm tra DeltaLow ngay
            # Calculate DeltaLow
            delta_low, delta_msg = calculate_delta_low(df_m1, current_idx=current_m1_idx)
            if delta_low is not None:
                log_details.append(f"   📊 {delta_msg}")
                atr_m1 = current_m1_candle['atr']
                is_valid_delta, delta_valid_msg = is_valid_delta_low(delta_low, atr_m1, threshold=delta_k)
                log_details.append(f"   📊 DeltaLow: {delta_low:.5f}, ATR_M1: {atr_m1:.5f}, k: {delta_k}")
                log_details.append(f"   {'✅' if is_valid_delta else '❌'} {delta_valid_msg}")
                
                # Update count
                count, is_triggered = buy_count_tracker.update(is_valid_delta, current_idx=current_m1_idx)
                log_details.append(f"   📊 Count: {count}/2")
                    
                    if is_triggered:
                        log_details.append(f"   ✅ Count >= 2 → Kiểm tra điều kiện BUY")
                        # Check BUY signal condition
                        is_buy, buy_msg = check_buy_signal_condition(
                            df_m1,
                            last_demand_price,
                            df_m5,
                            current_idx=current_m1_idx,
                            buffer_multiplier=0.2
                        )
                        log_details.append(f"   {'✅' if is_buy else '❌'} {buy_msg}")
                        
                        if is_buy:
                            # Check max positions per zone
                            is_valid_pos, pos_count, pos_msg = check_max_positions_per_zone(
                                positions,
                                last_demand_price,
                                "DEMAND",
                                max_positions=2
                            )
                            log_details.append(f"   {'✅' if is_valid_pos else '❌'} {pos_msg}")
                            
                            if is_valid_pos:
                                # Check M5 candle change (if last trade was SL)
                                if last_trade_time is not None and last_m5_candle_time is not None:
                                    # Get current M5 candle time
                                    current_m5_time = df_m5.iloc[current_m5_idx]['time']
                                    if isinstance(current_m5_time, pd.Timestamp):
                                        current_m5_time = current_m5_time.to_pydatetime()
                                    
                                    # Check if M5 candle has changed
                                    if current_m5_time <= last_m5_candle_time:
                                        log_details.append(f"   ⚠️ M5 chưa đổi nến sau lệnh SL (last: {last_m5_candle_time}, current: {current_m5_time})")
                                        log_details.append(f"{'='*80}\n")
                                        for detail in log_details:
                                            print(detail)
                                        return error_count, 0
                                
                                signal_type = "BUY"
                                entry_price = current_m1_candle['close']
                                
                                # Calculate SL/TP
                                symbol_info = mt5.symbol_info(symbol)
                                sl, tp1, tp2, sl_tp_info = calculate_sl_tp(
                                    entry_price,
                                    "BUY",
                                    atr_m1,
                                    atr_multiplier=2.0,
                                    tp_multiplier=2.0,
                                    symbol_info=symbol_info
                                )
                                
                                log_details.append(f"\n🚀 [BUY SIGNAL] Tất cả điều kiện đã thỏa!")
                                log_details.append(f"   Entry: {entry_price:.5f}")
                                log_details.append(f"   SL: {sl:.5f}")
                                log_details.append(f"   TP1: {tp1:.5f} | TP2: {tp2:.5f}")
        
        # --- 9. No Signal ---
        if signal_type is None:
            log_details.append(f"\n📋 [Kết Quả]")
            log_details.append(f"   ❌ Không có signal")
            log_details.append(f"   💱 Price: {current_m1_candle['close']:.5f}")
            log_details.append(f"   📊 ATR_M1: {current_m1_candle['atr']:.5f}")
            if pd.notna(current_m5_candle.get('ema21')):
                log_details.append(f"   📊 EMA21_M5: {current_m5_candle['ema21']:.5f}")
            log_details.append(f"   📊 ATR_M5: {current_m5_candle['atr']:.5f}")
            log_details.append(f"{'='*80}\n")
            
            # Print all log details
            for detail in log_details:
                print(detail)
            
            return error_count, 0
        
        # --- 10. Print Log Details ---
        log_details.append(f"{'='*80}\n")
        for detail in log_details:
            print(detail)
        
        # --- 11. Send Order ---
        tick = mt5.symbol_info_tick(symbol)
        if signal_type == "BUY":
            execution_price = tick.ask
        else:
            execution_price = tick.bid
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if signal_type == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": execution_price,
            "sl": sl,
            "tp": tp1,  # Use TP1 initially
            "magic": magic,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(
                result.order,
                "Scalp_Sideway",
                symbol,
                signal_type,
                volume,
                entry_price,
                sl,
                tp1,
                "Scalp Sideway Signal",
                account_id=config.get('account')
            )
            
            # Log to file
            log_to_file(
                symbol,
                "SIGNAL",
                f"{signal_type} SIGNAL - Ticket: {result.order} | Entry: {entry_price:.5f} | SL: {sl:.5f} | TP1: {tp1:.5f} | TP2: {tp2:.5f}"
            )
            
            # Update last trade time
            last_trade_time = datetime.now()
            # Get M5 candle time
            if 'time' in df_m5.columns:
                last_m5_candle_time = df_m5.iloc[current_m5_idx]['time']
                if isinstance(last_m5_candle_time, pd.Timestamp):
                    last_m5_candle_time = last_m5_candle_time.to_pydatetime()
            else:
                last_m5_candle_time = datetime.now()
            
            # Send Telegram
            msg = (
                f"✅ <b>Scalp Sideway Bot - {symbol}</b>\n"
                f"🆔 Ticket: {result.order}\n"
                f"💱 {signal_type} @ {entry_price:.5f}\n"
                f"🛑 SL: {sl:.5f}\n"
                f"🎯 TP1: {tp1:.5f} | TP2: {tp2:.5f}\n"
                f"📊 Volume: {volume:.2f} lot"
            )
            send_telegram(msg, config.get('telegram_token'), config.get('telegram_chat_id'), symbol=symbol)
            
            return 0, 0
        else:
            error_msg = f"Order Failed: Retcode {result.retcode}"
            print(f"❌ {error_msg}")
            log_to_file(symbol, "ERROR", f"{error_msg} - {result.comment if hasattr(result, 'comment') else 'Unknown'}")
            return error_count + 1, result.retcode
        
    except Exception as e:
        error_msg = f"❌ Lỗi trong scalp_sideway_logic: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        log_to_file(config.get('symbol', 'UNKNOWN'), "ERROR", f"Exception: {str(e)}")
        return error_count + 1, 0


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("❌ Usage: python scalp_sideway.py <config_file>")
        print("   Example: python scalp_sideway.py configs/scalp_sideway_xau.json")
        sys.exit(1)
    
    config_path = sys.argv[1]
    
    # Load config
    config = load_config(config_path)
    if config is None:
        print(f"❌ Không thể load config từ: {config_path}")
        sys.exit(1)
    
    # Connect MT5
    if not connect_mt5(config):
        print("❌ Không thể kết nối MT5")
        sys.exit(1)
    
    symbol = config.get('symbol', 'UNKNOWN')
    print("\n" + "="*80)
    print(f"✅ Scalp Sideway Bot - Started")
    print(f"💱 Symbol: {symbol}")
    print(f"📊 Volume: {config.get('volume', 'N/A')}")
    print(f"🆔 Magic: {config.get('magic', 'N/A')}")
    print("="*80 + "\n")
    
    consecutive_errors = 0
    
    try:
        # Verify MT5 connection
        if not mt5.terminal_info():
            print("❌ MT5 Terminal không còn kết nối")
            sys.exit(1)
        
        print("🔄 Bắt đầu vòng lặp chính...\n")
        
        loop_count = 0
        while True:
            try:
                loop_count += 1
                if loop_count % 60 == 0:
                    print(f"⏳ Bot đang chạy... (vòng lặp #{loop_count})")
                
                consecutive_errors, last_error = scalp_sideway_logic(config, consecutive_errors)
                if consecutive_errors >= 5:
                    print("⚠️ Too many errors. Pausing...")
                    time.sleep(120)
                    consecutive_errors = 0
                time.sleep(1)
            except Exception as e:
                print(f"❌ Lỗi trong loop: {e}")
                import traceback
                traceback.print_exc()
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    print("⚠️ Too many errors. Pausing...")
                    time.sleep(120)
                    consecutive_errors = 0
                time.sleep(5)
    except KeyboardInterrupt:
        print("\n\n⚠️ Bot stopped by user")
        mt5.shutdown()
    except Exception as e:
        print(f"\n❌ Lỗi nghiêm trọng: {e}")
        import traceback
        traceback.print_exc()
        mt5.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
