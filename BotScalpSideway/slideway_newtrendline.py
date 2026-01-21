"""
Bot Slideway New Trendline Strategy
Chỉ cần khai báo config file để chạy bot

Based on: botslideway_newtrendline.md

Usage:
    python slideway_newtrendline.py configs/slideway_newtrendline_eur.json
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
    manage_position
)
from utils_slideway_newtrendline import (
    calculate_ema,
    calculate_atr,
    calculate_rsi,
    find_swing_high,
    find_swing_low,
    check_pullback_buy,
    check_pullback_sell,
    calculate_delta_high,
    calculate_delta_low,
    is_valid_delta_high,
    is_valid_delta_low,
    check_bearish_divergence,
    check_bullish_divergence,
    DeltaCountTracker,
    calculate_sl_tp_newtrendline,
    get_delta_threshold_multiplier,
    get_min_atr_threshold
)

# Initialize Database
db = Database()

# Global trackers (persist across iterations)
buy_count_tracker = None
sell_count_tracker = None
last_swing_high = {}  # Dict: {symbol: {'index': int, 'price': float, 'rsi': float}}
last_swing_low = {}  # Dict: {symbol: {'index': int, 'price': float, 'rsi': float}}
pullback_trades = {}  # Dict: {symbol: set of swing indices} để track max 1 lệnh/sóng hồi


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


def slideway_newtrendline_logic(config: Dict, error_count: int = 0) -> tuple:
    """
    Slideway New Trendline Strategy Logic
    
    Args:
        config: Configuration dictionary
        error_count: Current error count
    
    Returns:
        (error_count, last_error_code)
    """
    global buy_count_tracker, sell_count_tracker
    global last_swing_high, last_swing_low, pullback_trades
    
    try:
        symbol = config['symbol']
        volume = config.get('volume', 0.01)
        magic = config['magic']
        max_positions = config.get('max_positions', 1)
        
        # Initialize trackers if not exists
        if buy_count_tracker is None:
            buy_count_tracker = DeltaCountTracker(min_count=2)
        if sell_count_tracker is None:
            sell_count_tracker = DeltaCountTracker(min_count=2)
        if symbol not in last_swing_high:
            last_swing_high[symbol] = None
        if symbol not in last_swing_low:
            last_swing_low[symbol] = None
        if symbol not in pullback_trades:
            pullback_trades[symbol] = set()
        
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
        df_m1['ema50'] = calculate_ema(df_m1['close'], 50)
        df_m1['ema200'] = calculate_ema(df_m1['close'], 200)
        df_m1['rsi'] = calculate_rsi(df_m1['close'], 14)
        
        df_m5['rsi'] = calculate_rsi(df_m5['close'], 14)
        
        # Get current candles (last completed)
        if len(df_m1) < 2 or len(df_m5) < 2:
            return error_count, 0
        
        current_m1_idx = len(df_m1) - 2  # Last completed M1 candle
        current_m5_idx = len(df_m5) - 2  # Last completed M5 candle
        
        current_m1_candle = df_m1.iloc[current_m1_idx]
        current_m5_candle = df_m5.iloc[current_m5_idx]
        
        # Log details
        log_details = []
        log_details.append(f"\n{'='*80}")
        log_details.append(f"📊 [Slideway New Trendline] {symbol} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_details.append(f"{'='*80}")
        
        # --- 4. Check Basic Conditions ---
        ema50 = current_m1_candle.get('ema50', None)
        ema200 = current_m1_candle.get('ema200', None)
        atr_m1 = current_m1_candle.get('atr', None)
        min_atr = get_min_atr_threshold(symbol, config)
        
        log_details.append(f"\n🔍 [Basic Conditions]")
        
        # Điều kiện 1: EMA50 > EMA200 (BUY) hoặc EMA50 < EMA200 (SELL)
        is_bullish_trend = False
        is_bearish_trend = False
        if pd.notna(ema50) and pd.notna(ema200):
            is_bullish_trend = ema50 > ema200
            is_bearish_trend = ema50 < ema200
            log_details.append(f"   EMA50: {ema50:.5f}, EMA200: {ema200:.5f}")
            log_details.append(f"   {'✅' if is_bullish_trend else '❌'} Trend: {'BULLISH' if is_bullish_trend else 'BEARISH' if is_bearish_trend else 'NEUTRAL'}")
        else:
            log_details.append(f"   ❌ EMA không có giá trị")
            log_details.append(f"{'='*80}\n")
            for detail in log_details:
                print(detail)
            return error_count, 0
        
        # Điều kiện 2: ATR 14 ≥ 0.00011 (hoặc min_atr)
        is_valid_atr = False
        if pd.notna(atr_m1) and atr_m1 is not None:
            is_valid_atr = atr_m1 >= min_atr
            log_details.append(f"   ATR_M1: {atr_m1:.5f}, Min ATR: {min_atr:.5f}")
            log_details.append(f"   {'✅' if is_valid_atr else '❌'} ATR hợp lệ")
        else:
            log_details.append(f"   ❌ ATR không có giá trị")
            log_details.append(f"{'='*80}\n")
            for detail in log_details:
                print(detail)
            return error_count, 0
        
        if not is_valid_atr:
            log_details.append(f"{'='*80}\n")
            for detail in log_details:
                print(detail)
            return error_count, 0
        
        signal_type = None
        entry_price = None
        sl = None
        tp = None
        
        # --- 5. BUY Signal Check ---
        if is_bullish_trend:
            log_details.append(f"\n🔍 [BUY Signal Check]")
            
            # Điều kiện 3: Tìm swing high với RSI > 70
            swing_high = find_swing_high(df_m1, lookback=5, current_idx=current_m1_idx)
            if swing_high is not None:
                swing_high_rsi = swing_high.get('rsi', None)
                if pd.notna(swing_high_rsi) and swing_high_rsi > 70:
                    log_details.append(f"   ✅ Swing High: {swing_high['price']:.5f}, RSI: {swing_high_rsi:.2f} > 70")
                    
                    # Update last swing high
                    if last_swing_high[symbol] is None or swing_high['index'] > last_swing_high[symbol]['index']:
                        last_swing_high[symbol] = swing_high
                        # Reset count khi có swing high mới
                        buy_count_tracker.reset()
                    
                    # Điều kiện 4: Kiểm tra pullback hợp lệ
                    is_valid_pullback, pullback_msg = check_pullback_buy(
                        df_m1,
                        last_swing_high[symbol],
                        current_idx=current_m1_idx,
                        max_candles=30
                    )
                    log_details.append(f"   {'✅' if is_valid_pullback else '❌'} {pullback_msg}")
                    
                    if is_valid_pullback:
                        # Kiểm tra max 1 lệnh / sóng hồi
                        swing_idx = last_swing_high[symbol]['index']
                        if swing_idx in pullback_trades[symbol]:
                            log_details.append(f"   ⚠️ Đã có lệnh trong sóng hồi này (swing index: {swing_idx})")
                        else:
                            # Điều kiện 5: Tìm DeltaLow trong sóng hồi
                            delta_low, delta_low_msg = calculate_delta_low(df_m1, current_idx=current_m1_idx)
                            if delta_low is not None:
                                delta_k = get_delta_threshold_multiplier(symbol, config)
                                is_valid_delta, delta_valid_msg = is_valid_delta_low(delta_low, atr_m1, threshold=delta_k)
                                log_details.append(f"   📊 {delta_low_msg}")
                                log_details.append(f"   📊 DeltaLow: {delta_low:.5f}, ATR_M1: {atr_m1:.5f}, k: {delta_k}")
                                log_details.append(f"   {'✅' if is_valid_delta else '❌'} {delta_valid_msg}")
                                
                                # Update count
                                count, is_triggered = buy_count_tracker.update(is_valid_delta, current_idx=current_m1_idx)
                                log_details.append(f"   📊 Count: {count}/2")
                                
                                if is_triggered:
                                    # Điều kiện 6: Không có Bearish Divergence
                                    has_bearish_div, div_msg = check_bearish_divergence(df_m1, lookback=50, max_idx=current_m1_idx)
                                    log_details.append(f"   {'✅' if not has_bearish_div else '❌'} {div_msg}")
                                    
                                    if not has_bearish_div:
                                        # Điều kiện 7: RSI(14)_M5 ≥ 55 và ≤ 65
                                        rsi_m5 = current_m5_candle.get('rsi', None)
                                        if pd.notna(rsi_m5):
                                            is_valid_rsi_m5 = 55 <= rsi_m5 <= 65
                                            log_details.append(f"   RSI_M5: {rsi_m5:.2f}")
                                            log_details.append(f"   {'✅' if is_valid_rsi_m5 else '❌'} RSI_M5 trong vùng 55-65")
                                            
                                            if is_valid_rsi_m5:
                                                log_details.append(f"   ✅ Count >= 2 → BUY SIGNAL!")
                                                signal_type = "BUY"
                                                entry_price = current_m1_candle['close']
                                                
                                                # Calculate SL/TP
                                                symbol_info = mt5.symbol_info(symbol)
                                                sl, tp, sl_tp_info = calculate_sl_tp_newtrendline(
                                                    entry_price,
                                                    "BUY",
                                                    atr_m1,
                                                    symbol_info=symbol_info,
                                                    point_adjustment=6.0
                                                )
                                                
                                                log_details.append(f"\n🚀 [BUY SIGNAL] Tất cả điều kiện đã thỏa!")
                                                log_details.append(f"   Entry: {entry_price:.5f}")
                                                log_details.append(f"   SL: {sl:.5f}")
                                                log_details.append(f"   TP: {tp:.5f}")
                else:
                    log_details.append(f"   ❌ Swing High không có RSI > 70 (RSI: {swing_high_rsi if pd.notna(swing_high_rsi) else 'N/A'})")
            else:
                log_details.append(f"   ❌ Không tìm thấy Swing High")
        
        # --- 6. SELL Signal Check ---
        if signal_type is None and is_bearish_trend:
            log_details.append(f"\n🔍 [SELL Signal Check]")
            
            # Điều kiện 3: Tìm swing low với RSI < 30
            swing_low = find_swing_low(df_m1, lookback=5, current_idx=current_m1_idx)
            if swing_low is not None:
                swing_low_rsi = swing_low.get('rsi', None)
                if pd.notna(swing_low_rsi) and swing_low_rsi < 30:
                    log_details.append(f"   ✅ Swing Low: {swing_low['price']:.5f}, RSI: {swing_low_rsi:.2f} < 30")
                    
                    # Update last swing low
                    if last_swing_low[symbol] is None or swing_low['index'] > last_swing_low[symbol]['index']:
                        last_swing_low[symbol] = swing_low
                        # Reset count khi có swing low mới
                        sell_count_tracker.reset()
                    
                    # Điều kiện 4: Kiểm tra pullback hợp lệ
                    is_valid_pullback, pullback_msg = check_pullback_sell(
                        df_m1,
                        last_swing_low[symbol],
                        current_idx=current_m1_idx,
                        max_candles=30
                    )
                    log_details.append(f"   {'✅' if is_valid_pullback else '❌'} {pullback_msg}")
                    
                    if is_valid_pullback:
                        # Kiểm tra max 1 lệnh / sóng hồi
                        swing_idx = last_swing_low[symbol]['index']
                        if swing_idx in pullback_trades[symbol]:
                            log_details.append(f"   ⚠️ Đã có lệnh trong sóng hồi này (swing index: {swing_idx})")
                        else:
                            # Điều kiện 5: Tìm DeltaHigh trong sóng hồi
                            delta_high, delta_high_msg = calculate_delta_high(df_m1, current_idx=current_m1_idx)
                            if delta_high is not None:
                                delta_k = get_delta_threshold_multiplier(symbol, config)
                                is_valid_delta, delta_valid_msg = is_valid_delta_high(delta_high, atr_m1, threshold=delta_k)
                                log_details.append(f"   📊 {delta_high_msg}")
                                log_details.append(f"   📊 DeltaHigh: {delta_high:.5f}, ATR_M1: {atr_m1:.5f}, k: {delta_k}")
                                log_details.append(f"   {'✅' if is_valid_delta else '❌'} {delta_valid_msg}")
                                
                                # Update count
                                count, is_triggered = sell_count_tracker.update(is_valid_delta, current_idx=current_m1_idx)
                                log_details.append(f"   📊 Count: {count}/2")
                                
                                if is_triggered:
                                    # Điều kiện 6: Không có Bullish Divergence
                                    has_bullish_div, div_msg = check_bullish_divergence(df_m1, lookback=50, max_idx=current_m1_idx)
                                    log_details.append(f"   {'✅' if not has_bullish_div else '❌'} {div_msg}")
                                    
                                    if not has_bullish_div:
                                        # Điều kiện 7: RSI(14)_M5 ≥ 35 và ≤ 45
                                        rsi_m5 = current_m5_candle.get('rsi', None)
                                        if pd.notna(rsi_m5):
                                            is_valid_rsi_m5 = 35 <= rsi_m5 <= 45
                                            log_details.append(f"   RSI_M5: {rsi_m5:.2f}")
                                            log_details.append(f"   {'✅' if is_valid_rsi_m5 else '❌'} RSI_M5 trong vùng 35-45")
                                            
                                            if is_valid_rsi_m5:
                                                log_details.append(f"   ✅ Count >= 2 → SELL SIGNAL!")
                                                signal_type = "SELL"
                                                entry_price = current_m1_candle['close']
                                                
                                                # Calculate SL/TP
                                                symbol_info = mt5.symbol_info(symbol)
                                                sl, tp, sl_tp_info = calculate_sl_tp_newtrendline(
                                                    entry_price,
                                                    "SELL",
                                                    atr_m1,
                                                    symbol_info=symbol_info,
                                                    point_adjustment=6.0
                                                )
                                                
                                                log_details.append(f"\n🚀 [SELL SIGNAL] Tất cả điều kiện đã thỏa!")
                                                log_details.append(f"   Entry: {entry_price:.5f}")
                                                log_details.append(f"   SL: {sl:.5f}")
                                                log_details.append(f"   TP: {tp:.5f}")
                else:
                    log_details.append(f"   ❌ Swing Low không có RSI < 30 (RSI: {swing_low_rsi if pd.notna(swing_low_rsi) else 'N/A'})")
            else:
                log_details.append(f"   ❌ Không tìm thấy Swing Low")
        
        # --- 7. No Signal ---
        if signal_type is None:
            log_details.append(f"\n📋 [Kết Quả]")
            log_details.append(f"   ❌ Không có signal")
            log_details.append(f"   💱 Price: {current_m1_candle['close']:.5f}")
            log_details.append(f"   📊 ATR_M1: {atr_m1:.5f}")
            log_details.append(f"{'='*80}\n")
            
            for detail in log_details:
                print(detail)
            
            return error_count, 0
        
        # --- 8. Print Log Details ---
        log_details.append(f"{'='*80}\n")
        for detail in log_details:
            print(detail)
        
        # --- 9. Send Order ---
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
                "Slideway_NewTrendline",
                symbol,
                signal_type,
                volume,
                entry_price,
                sl,
                tp,
                "Slideway New Trendline Signal",
                account_id=config.get('account')
            )
            
            # Ghi log chi tiết khi order thành công
            swing_info = last_swing_high[symbol] if signal_type == "BUY" else last_swing_low[symbol]
            additional_info = {
                "Swing_Price": swing_info['price'] if swing_info else None,
                "Swing_RSI": swing_info.get('rsi', None) if swing_info else None,
                "ATR_M1": atr_m1,
                "Delta_K": get_delta_threshold_multiplier(symbol, config),
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
            
            # Track pullback trade
            swing_idx = swing_info['index'] if swing_info else None
            if swing_idx is not None:
                pullback_trades[symbol].add(swing_idx)
            
            # Send Telegram
            msg = (
                f"✅ <b>Slideway New Trendline Bot - {symbol}</b>\n"
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
        error_msg = f"❌ Lỗi trong slideway_newtrendline_logic: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        log_to_file(config.get('symbol', 'UNKNOWN'), "ERROR", f"Exception: {str(e)}")
        return error_count + 1, 0


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("❌ Usage: python slideway_newtrendline.py <config_file>")
        print("   Example: python slideway_newtrendline.py configs/slideway_newtrendline_eur.json")
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
    print(f"✅ Slideway New Trendline Bot - Started")
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
                
                consecutive_errors, last_error = slideway_newtrendline_logic(config, consecutive_errors)
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
