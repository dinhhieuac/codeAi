"""
Bot Scalp Sideway Supper Strategy
Chỉ cần khai báo config file để chạy bot

Based on: botsupper.md

Usage:
    python scalp_sideway_supper.py configs/scalp_sideway_supper_xau.json
    python scalp_sideway_supper.py configs/scalp_sideway_supper_eur.json
"""

import MetaTrader5 as mt5
import time
import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict

# Import local modules
sys.path.append('..')
from db import Database
from utils import (
    load_config, 
    connect_mt5, 
    get_data, 
    send_telegram, 
    log_to_file,
    get_pip_size
)
from utils_scalp_sideway_supper import (
    calculate_atr,
    check_atr_ratio_supper,
    calculate_delta_high,
    calculate_delta_low,
    is_valid_delta_sell_supper,
    is_valid_delta_buy_supper,
    check_range_filter,
    DeltaCountTrackerSupper,
    calculate_sl_tp_supper,
    get_delta_threshold_multiplier_supper,
    get_range_multiplier_supper,
    get_trailing_e_multiplier_supper
)

# Initialize Database
db = Database()

# Global trackers (persist across iterations)
sell_count_tracker = None
buy_count_tracker = None
last_trade_time = {}  # Dict: {symbol: datetime} để track cooldown
position_tracking = {}  # Dict: {ticket: {'entry_time': datetime, 'highest_high': float, 'lowest_low': float}}


def manage_position_supper(order_ticket, symbol, magic, config, df_m1=None):
    """
    Manage an open position: Breakeven & Trailing SL (Bot Supper)
    
    Logic theo botsupper.md:
    - Nếu lợi nhuận ≥ E×ATR → dời Stop Loss về Entry
    - Nếu lợi nhuận ≥ 0.5×ATR → bắt đầu trailing
    - BUY: SL = max(SL, HighestHigh - 0.5 × ATR) - chỉ đi lên
    - SELL: SL = min(SL, LowestLow + 0.5 × ATR) - chỉ đi xuống
    """
    try:
        positions = mt5.positions_get(ticket=int(order_ticket))
        if not positions:
            return
        
        pos = positions[0]
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        current_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        
        # Get ATR
        if df_m1 is None:
            df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 50)
        if df_m1 is None or len(df_m1) < 1:
            return
        
        df_m1['atr'] = calculate_atr(df_m1, 14)
        current_atr = df_m1.iloc[-1]['atr']
        if pd.isna(current_atr) or current_atr is None:
            return
        
        # Get E multiplier
        e_multiplier = get_trailing_e_multiplier_supper(symbol, config)
        
        # Calculate profit in price
        if pos.type == mt5.ORDER_TYPE_BUY:
            profit_price = current_price - pos.price_open
        else:
            profit_price = pos.price_open - current_price
        
        # Initialize tracking if not exists
        if order_ticket not in position_tracking:
            position_tracking[order_ticket] = {
                'entry_time': datetime.now(),
                'highest_high': current_price if pos.type == mt5.ORDER_TYPE_BUY else pos.price_open,
                'lowest_low': current_price if pos.type == mt5.ORDER_TYPE_SELL else pos.price_open
            }
        
        tracking = position_tracking[order_ticket]
        
        # Update highest/lowest
        if pos.type == mt5.ORDER_TYPE_BUY:
            tracking['highest_high'] = max(tracking['highest_high'], current_price)
        else:
            tracking['lowest_low'] = min(tracking['lowest_low'], current_price)
        
        request = None
        digits = symbol_info.digits
        
        # 1. Breakeven: Nếu lợi nhuận ≥ E×ATR → dời SL về Entry
        breakeven_trigger = e_multiplier * current_atr
        if profit_price >= breakeven_trigger:
            # Check if SL is already at or better than breakeven
            is_breakeven = False
            tolerance = symbol_info.point * 0.5
            if pos.type == mt5.ORDER_TYPE_BUY:
                if pos.sl > 0 and (pos.sl >= pos.price_open - tolerance):
                    is_breakeven = True
            else:
                if pos.sl > 0 and (pos.sl <= pos.price_open + tolerance):
                    is_breakeven = True
            
            if not is_breakeven:
                new_sl = round(pos.price_open, digits)
                new_tp = round(pos.tp, digits) if pos.tp > 0 else 0
                
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": symbol,
                    "sl": new_sl,
                    "tp": new_tp
                }
                print(f"🛡️ [Breakeven] Ticket {pos.ticket}: Moved SL to entry ({new_sl:.5f}) | Profit: {profit_price:.5f}")
                log_to_file(symbol, "BREAKEVEN", f"Ticket: {pos.ticket} | SL moved to entry: {new_sl:.5f} | Profit: {profit_price:.5f}")
        
        # 2. Trailing Stop: Nếu lợi nhuận ≥ 0.5×ATR → bắt đầu trailing
        trailing_trigger = 0.5 * current_atr
        if profit_price >= trailing_trigger and request is None:
            new_sl = None
            
            if pos.type == mt5.ORDER_TYPE_BUY:
                # SL = max(SL, HighestHigh - 0.5 × ATR)
                # Chỉ cho phép SL đi lên, không bao giờ đi xuống
                candidate_sl = tracking['highest_high'] - (0.5 * current_atr)
                candidate_sl = round(candidate_sl, digits)
                
                # Only update if new_sl is higher than current SL
                tolerance = symbol_info.point * 0.5
                if pos.sl == 0 or candidate_sl > pos.sl + tolerance:
                    new_sl = candidate_sl
            else:  # SELL
                # SL = min(SL, LowestLow + 0.5 × ATR)
                # SL chỉ được hạ xuống, không bao giờ kéo lên
                candidate_sl = tracking['lowest_low'] + (0.5 * current_atr)
                candidate_sl = round(candidate_sl, digits)
                
                # Only update if new_sl is lower than current SL
                tolerance = symbol_info.point * 0.5
                if pos.sl == 0 or candidate_sl < pos.sl - tolerance:
                    new_sl = candidate_sl
            
            if new_sl is not None:
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": symbol,
                    "sl": new_sl,
                    "tp": round(pos.tp, digits) if pos.tp > 0 else 0
                }
                print(f"🏃 [Trailing] Ticket {pos.ticket}: SL {pos.sl:.5f} -> {new_sl:.5f} | Profit: {profit_price:.5f}")
                log_to_file(symbol, "TRAILING", f"Ticket: {pos.ticket} | SL: {pos.sl:.5f} -> {new_sl:.5f} | Profit: {profit_price:.5f}")
        
        # Send request if exists
        if request:
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"⚠️ Failed to update SL/TP for ticket {order_ticket}: {result.retcode}")
        
        # Clean up tracking if position closed
        if order_ticket in position_tracking:
            # Check if position still exists
            current_positions = mt5.positions_get(ticket=int(order_ticket))
            if not current_positions:
                del position_tracking[order_ticket]
                
    except Exception as e:
        print(f"⚠️ Error in manage_position_supper: {e}")
        import traceback
        traceback.print_exc()


def log_signal_details_to_file(
    symbol: str,
    signal_type: str,
    entry_price: float,
    sl: float,
    tp: float,
    log_details: list,
    additional_info: Optional[Dict] = None
):
    """
    Ghi log chi tiết khi có tín hiệu vào file log
    """
    try:
        log_content = []
        log_content.append(f"\n{'='*80}")
        log_content.append(f"🚀 [SIGNAL DETECTED] {signal_type} - {symbol}")
        log_content.append(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_content.append(f"{'='*80}")
        
        for detail in log_details:
            log_content.append(detail)
        
        log_content.append(f"\n📊 [Signal Details]")
        log_content.append(f"   Signal Type: {signal_type}")
        log_content.append(f"   Entry Price: {entry_price:.5f}")
        log_content.append(f"   Stop Loss: {sl:.5f}")
        log_content.append(f"   Take Profit: {tp:.5f}")
        log_content.append(f"   SL Distance: {abs(entry_price - sl):.5f}")
        log_content.append(f"   TP Distance: {abs(tp - entry_price):.5f}")
        log_content.append(f"   Risk/Reward: 1:2")
        
        if additional_info:
            log_content.append(f"\n📈 [Additional Info]")
            for key, value in additional_info.items():
                if isinstance(value, float):
                    log_content.append(f"   {key}: {value:.5f}")
                else:
                    log_content.append(f"   {key}: {value}")
        
        log_content.append(f"{'='*80}\n")
        
        log_message = "\n".join(log_content)
        log_to_file(symbol, "SIGNAL", log_message)
        
    except Exception as e:
        print(f"⚠️ Lỗi khi ghi log chi tiết: {e}")


def scalp_sideway_supper_logic(config: Dict, error_count: int = 0) -> tuple:
    """
    Scalp Sideway Supper Strategy Logic
    
    Args:
        config: Configuration dictionary
        error_count: Current error count
    
    Returns:
        (error_count, last_error_code)
    """
    global sell_count_tracker, buy_count_tracker, last_trade_time
    
    try:
        symbol = config['symbol']
        volume = config.get('volume', 0.01)
        magic = config['magic']
        max_positions = config.get('max_positions', 1)
        
        # Initialize trackers if not exists
        if sell_count_tracker is None:
            sell_count_tracker = DeltaCountTrackerSupper(min_count=2)
        if buy_count_tracker is None:
            buy_count_tracker = DeltaCountTrackerSupper(min_count=2)
        if symbol not in last_trade_time:
            last_trade_time[symbol] = None
        
        # Check cooldown (3 phút)
        if last_trade_time[symbol] is not None:
            time_since_last_trade = datetime.now() - last_trade_time[symbol]
            if time_since_last_trade < timedelta(minutes=3):
                remaining_seconds = 180 - int(time_since_last_trade.total_seconds())
                if remaining_seconds > 0:
                    # Skip this iteration (cooldown active)
                    return error_count, 0
        
        # --- 1. Manage Existing Positions ---
        all_positions = mt5.positions_get(symbol=symbol)
        positions = [pos for pos in (all_positions or []) if pos.magic == magic]
        if positions:
            for pos in positions:
                df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 50)
                manage_position_supper(pos.ticket, symbol, magic, config, df_m1)
            if len(positions) >= max_positions:
                return error_count, 0
        
        # --- 2. Data Fetching ---
        df_m1 = get_data(symbol, mt5.TIMEFRAME_M1, 300)
        if df_m1 is None:
            print(f"⚠️ Không thể lấy dữ liệu M1 cho {symbol}")
            return error_count, 0
        
        # --- 3. Calculate Indicators ---
        df_m1['atr'] = calculate_atr(df_m1, 14)
        
        # Get current candle (last completed)
        if len(df_m1) < 2:
            return error_count, 0
        
        current_m1_idx = len(df_m1) - 2  # Last completed M1 candle
        current_m1_candle = df_m1.iloc[current_m1_idx]
        
        # Log details
        log_details = []
        log_details.append(f"\n{'='*80}")
        log_details.append(f"📊 [Scalp Sideway Supper] {symbol} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_details.append(f"{'='*80}")
        
        # --- 4. Check ATR Ratio Filter ---
        is_valid_atr_ratio, atr_ratio, atr_ratio_msg = check_atr_ratio_supper(df_m1, current_idx=current_m1_idx)
        log_details.append(f"\n🔍 [ATR Ratio Filter]")
        log_details.append(f"   {'✅' if is_valid_atr_ratio else '❌'} {atr_ratio_msg}")
        
        if not is_valid_atr_ratio:
            # Reset count và không xét Delta
            sell_count_tracker.reset()
            buy_count_tracker.reset()
            log_details.append(f"   ⚠️ ATR ratio không hợp lệ → KHÔNG xét Delta, Count = 0")
            log_details.append(f"{'='*80}\n")
            for detail in log_details:
                print(detail)
            return error_count, 0
        
        # --- 5. Calculate Delta ---
        delta_high, delta_high_msg = calculate_delta_high(df_m1, current_idx=current_m1_idx)
        delta_low, delta_low_msg = calculate_delta_low(df_m1, current_idx=current_m1_idx)
        
        atr_m1 = current_m1_candle['atr']
        delta_k = get_delta_threshold_multiplier_supper(symbol, config)
        range_q = get_range_multiplier_supper(symbol, config)
        
        signal_type = None
        entry_price = None
        sl = None
        tp = None
        
        log_details.append(f"\n🔍 [SELL Signal Check]")
        
        # --- 6. SELL Signal Check ---
        if delta_high is not None and delta_low is not None:
            # Check range filter
            is_valid_range, range_value, range_msg = check_range_filter(
                df_m1, 
                current_idx=current_m1_idx,
                atr_m1=atr_m1,
                q_multiplier=range_q
            )
            log_details.append(f"   📊 Range: {range_value:.5f}, q: {range_q}, Threshold: {range_q * atr_m1:.5f}")
            log_details.append(f"   {'✅' if is_valid_range else '❌'} {range_msg}")
            
            if not is_valid_range:
                # Range không hợp lệ → Count = 0
                sell_count_tracker.reset()
                log_details.append(f"   ⚠️ Range không hợp lệ → Count = 0")
            elif is_valid_range:
                # Check delta với điều kiện khóa hướng
                is_valid_delta, delta_valid_msg = is_valid_delta_sell_supper(
                    delta_high,
                    delta_low,
                    atr_m1,
                    threshold=delta_k
                )
                log_details.append(f"   📊 DeltaHigh: {delta_high:.5f}, DeltaLow: {delta_low:.5f}, k: {delta_k}")
                log_details.append(f"   {'✅' if is_valid_delta else '❌'} {delta_valid_msg}")
                
                # Update count
                count, is_triggered = sell_count_tracker.update(is_valid_delta, current_idx=current_m1_idx)
                log_details.append(f"   📊 Count: {count}/2")
                
                if is_triggered:
                    log_details.append(f"   ✅ Count >= 2 → SELL SIGNAL!")
                    signal_type = "SELL"
                    entry_price = current_m1_candle['close']
                    
                    # Calculate SL/TP
                    symbol_info = mt5.symbol_info(symbol)
                    sl, tp, sl_tp_info = calculate_sl_tp_supper(
                        entry_price,
                        "SELL",
                        atr_m1,
                        symbol_info=symbol_info
                    )
                    
                    log_details.append(f"\n🚀 [SELL SIGNAL] Tất cả điều kiện đã thỏa!")
                    log_details.append(f"   Entry: {entry_price:.5f}")
                    log_details.append(f"   SL: {sl:.5f}")
                    log_details.append(f"   TP: {tp:.5f}")
        
        # --- 7. BUY Signal Check ---
        if signal_type is None:
            log_details.append(f"\n🔍 [BUY Signal Check]")
            
            if delta_high is not None and delta_low is not None:
                # Check range filter
                is_valid_range, range_value, range_msg = check_range_filter(
                    df_m1, 
                    current_idx=current_m1_idx,
                    atr_m1=atr_m1,
                    q_multiplier=range_q
                )
                log_details.append(f"   📊 Range: {range_value:.5f}, q: {range_q}, Threshold: {range_q * atr_m1:.5f}")
                log_details.append(f"   {'✅' if is_valid_range else '❌'} {range_msg}")
                
                if not is_valid_range:
                    # Range không hợp lệ → Count = 0
                    buy_count_tracker.reset()
                    log_details.append(f"   ⚠️ Range không hợp lệ → Count = 0")
                elif is_valid_range:
                    # Check delta với điều kiện khóa hướng
                    is_valid_delta, delta_valid_msg = is_valid_delta_buy_supper(
                        delta_low,
                        delta_high,
                        atr_m1,
                        threshold=delta_k
                    )
                    log_details.append(f"   📊 DeltaLow: {delta_low:.5f}, DeltaHigh: {delta_high:.5f}, k: {delta_k}")
                    log_details.append(f"   {'✅' if is_valid_delta else '❌'} {delta_valid_msg}")
                    
                    # Update count
                    count, is_triggered = buy_count_tracker.update(is_valid_delta, current_idx=current_m1_idx)
                    log_details.append(f"   📊 Count: {count}/2")
                    
                    if is_triggered:
                        log_details.append(f"   ✅ Count >= 2 → BUY SIGNAL!")
                        signal_type = "BUY"
                        entry_price = current_m1_candle['close']
                        
                        # Calculate SL/TP
                        symbol_info = mt5.symbol_info(symbol)
                        sl, tp, sl_tp_info = calculate_sl_tp_supper(
                            entry_price,
                            "BUY",
                            atr_m1,
                            symbol_info=symbol_info
                        )
                        
                        log_details.append(f"\n🚀 [BUY SIGNAL] Tất cả điều kiện đã thỏa!")
                        log_details.append(f"   Entry: {entry_price:.5f}")
                        log_details.append(f"   SL: {sl:.5f}")
                        log_details.append(f"   TP: {tp:.5f}")
        
        # --- 8. No Signal ---
        if signal_type is None:
            log_details.append(f"\n📋 [Kết Quả]")
            log_details.append(f"   ❌ Không có signal")
            log_details.append(f"   💱 Price: {current_m1_candle['close']:.5f}")
            log_details.append(f"   📊 ATR_M1: {atr_m1:.5f}")
            log_details.append(f"   📊 ATR_Ratio: {atr_ratio:.3f}")
            log_details.append(f"{'='*80}\n")
            
            for detail in log_details:
                print(detail)
            
            return error_count, 0
        
        # --- 9. Print Log Details ---
        log_details.append(f"{'='*80}\n")
        for detail in log_details:
            print(detail)
        
        # --- 10. Send Order ---
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
            "tp": tp,
            "magic": magic,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Order Executed: {result.order}")
            db.log_order(
                result.order,
                "Scalp_Sideway_Supper",
                symbol,
                signal_type,
                volume,
                entry_price,
                sl,
                tp,
                "Scalp Sideway Supper Signal",
                account_id=config.get('account')
            )
            
            # Ghi log chi tiết khi order thành công
            additional_info = {
                "DeltaHigh": delta_high if delta_high is not None else 0,
                "DeltaLow": delta_low if delta_low is not None else 0,
                "ATR_M1": atr_m1,
                "Delta_K": delta_k,
                "Range_Q": range_q,
                "ATR_Ratio": atr_ratio,
                "Count": count,
                "Current_Price": current_m1_candle['close'],
                "Volume": volume
            }
            log_signal_details_to_file(
                symbol,
                signal_type,
                entry_price,
                sl,
                tp,
                log_details,
                additional_info
            )
            
            # Update last trade time (for cooldown)
            last_trade_time[symbol] = datetime.now()
            
            # Send Telegram
            msg = (
                f"✅ <b>Scalp Sideway Supper Bot - {symbol}</b>\n"
                f"🆔 Ticket: {result.order}\n"
                f"💱 {signal_type} @ {entry_price:.5f}\n"
                f"🛑 SL: {sl:.5f}\n"
                f"🎯 TP: {tp:.5f}\n"
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
        error_msg = f"❌ Lỗi trong scalp_sideway_supper_logic: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        log_to_file(config.get('symbol', 'UNKNOWN'), "ERROR", f"Exception: {str(e)}")
        return error_count + 1, 0


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("❌ Usage: python scalp_sideway_supper.py <config_file>")
        print("   Example: python scalp_sideway_supper.py configs/scalp_sideway_supper_xau.json")
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
    print(f"✅ Scalp Sideway Supper Bot - Started")
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
                
                consecutive_errors, last_error = scalp_sideway_supper_logic(config, consecutive_errors)
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
