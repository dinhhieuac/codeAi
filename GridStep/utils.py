import MetaTrader5 as mt5
import os
import json
import requests
from typing import Any, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def load_config(config_path):
    """Load configuration from JSON file"""
    if not os.path.exists(config_path):
        print(f"❌ Config file not found: {config_path}")
        return None
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return None

def connect_mt5(config):
    """Initialize MT5 connection using config (account, password, server; mt5_path tùy chọn)."""
    login = config.get("account")
    password = (config.get("password") or "").strip()
    server = (config.get("server") or "").strip()
    path_raw = config.get("mt5_path")
    path = (str(path_raw).strip() if path_raw else "") or None

    if login is None or not password or not server:
        print("❌ Thiếu account / password / server trong config JSON")
        return False

    try:
        login = int(login)
    except (TypeError, ValueError):
        print(f"❌ Số tài khoản (account) không hợp lệ: {login!r}")
        return False

    if path:
        if not os.path.isfile(path):
            print(f"❌ mt5_path không trỏ tới file tồn tại:\n   {path}")
            print(
                "   Dùng đường dẫn đầy đủ tới terminal64.exe của **đúng** terminal MT5 (live khác demo "
                "→ thường cần bản cài riêng). Ví dụ: C:\\\\Program Files\\\\Exness MT5 Real\\\\terminal64.exe"
            )
            return False

    try:
        mt5.shutdown()
    except Exception:
        pass

    try:
        if path:
            ok = mt5.initialize(path=path, login=login, password=password, server=server)
        else:
            ok = mt5.initialize(login=login, password=password, server=server)
        if not ok:
            err = mt5.last_error()
            print(f"❌ MT5 initialize thất bại: {err}")
            print(
                "   Gợi ý: (1) Mật khẩu tài khoản giao dịch (không dùng mật khẩu chỉ đọc/investor nếu broker chặn). "
                "(2) Tên server đúng như trong MT5 (File → Login) — phân biệt Real/Demo. "
                "(3) mt5_path trỏ terminal đã thêm **cùng** server đó. "
                "(4) Đóng MT5 GUI đang mở cùng terminal nếu bị conflict."
            )
            return False

        print(f"✅ Connected to MT5 Account: {login}")
        return True
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def send_telegram(message, token, chat_id):
    """Send message to Telegram"""
    if not token or not chat_id:
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")

def get_data(symbol, timeframe, n=100):
    """Fetch recent candles from MT5"""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
    if rates is None or len(rates) == 0:
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def calculate_heiken_ashi(df):
    """Calculate Heiken Ashi candles"""
    ha_df = df.copy()
    ha_df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    
    # Initialize first HA open
    ha_df.at[0, 'ha_open'] = (df.iloc[0]['open'] + df.iloc[0]['close']) / 2
    
    for i in range(1, len(df)):
        ha_df.at[i, 'ha_open'] = (ha_df.at[i-1, 'ha_open'] + ha_df.at[i-1, 'ha_close']) / 2
        
    ha_df['ha_high'] = ha_df[['high', 'ha_open', 'ha_close']].max(axis=1)
    ha_df['ha_low'] = ha_df[['low', 'ha_open', 'ha_close']].min(axis=1)
    
    return ha_df

def calculate_atr(df, period=14):
    """Calculate ATR (Average True Range)"""
    df = df.copy()
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift(1))
    df['tr2'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    atr_series = df['tr'].rolling(window=period).mean()
    return atr_series

def calculate_adx(df, period=14):
    """Calculate ADX Indicator"""
    df = df.copy()
    df['up'] = df['high'].diff()
    df['down'] = -df['low'].diff()
    
    df['dm_plus'] = np.where((df['up'] > df['down']) & (df['up'] > 0), df['up'], 0)
    df['dm_minus'] = np.where((df['down'] > df['up']) & (df['down'] > 0), df['down'], 0)
    
    df['tr'] = np.maximum(df['high'] - df['low'], 
                          np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                     abs(df['low'] - df['close'].shift(1))))
    
    df['tr_s'] = df['tr'].rolling(window=period).sum()
    df['dm_plus_s'] = df['dm_plus'].rolling(window=period).sum()
    df['dm_minus_s'] = df['dm_minus'].rolling(window=period).sum()
    
    df['di_plus'] = 100 * (df['dm_plus_s'] / df['tr_s'])
    df['di_minus'] = 100 * (df['dm_minus_s'] / df['tr_s'])
    
    df['dx'] = 100 * abs(df['di_plus'] - df['di_minus']) / (df['di_plus'] + df['di_minus'])
    df['adx'] = df['dx'].rolling(window=period).mean()
    
    return df

def calculate_rsi(series, period=14):
    """
    Calculate RSI using Wilder's Smoothing (Standard MT5/TradingView RSI)
    """
    delta = series.diff()
    
    # Separate gains and losses
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    
    # Calculate initial average (simple MA)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()[:period+1]
    avg_loss = loss.rolling(window=period, min_periods=period).mean()[:period+1]
    
    # Manual loop or pandas ewm for Wilder's Smoothing (alpha=1/period)
    # Pandas EWM with adjust=False approximates Wilder's if alpha=1/period
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def is_doji(row, threshold=0.1):
    """Check if candle is a Doji (Body < 10% of Range)"""
    body = abs(row['close'] - row['open'])
    rng = row['high'] - row['low']
    return body <= (rng * threshold) if rng > 0 else True

def manage_position(order_ticket, symbol, magic, config):
    """
    Manage an open position: Breakeven & Trailing SL (Improved V2)
    
    Config parameters:
    - trailing_enabled: true/false - Enable/disable trailing SL
    - breakeven_enabled: true/false - Enable/disable breakeven
    - breakeven_trigger_pips: Fixed pips OR use "auto" for % of initial SL (default: 30)
    - breakeven_trigger_percent: % of initial SL to trigger breakeven (default: 0.5 = 50%)
    - trailing_trigger_pips: Fixed pips OR use "auto" for multiplier of initial SL (default: 50)
    - trailing_trigger_multiplier: Multiplier of initial SL to start trailing (default: 1.2)
    - trailing_mode: "atr" or "fixed" - Use ATR-based or fixed distance
    - trailing_atr_timeframe: "M1" or "M5" - Timeframe for ATR calculation (default: "M5")
    - trailing_distance_pips: Fixed trailing distance in pips (default: 50)
    - trailing_atr_multiplier: ATR multiplier for trailing (default: 1.5)
    - trailing_min_pips: Minimum trailing distance in pips (default: 30)
    - trailing_max_pips: Maximum trailing distance in pips (default: 100)
    - trailing_lock_on_pullback: Enable lock trailing when pullback > % (default: false)
    - trailing_pullback_percent: % profit loss to lock trailing (default: 0.3 = 30%)
    """
    try:
        # Check if trailing is enabled
        trailing_enabled = config.get('parameters', {}).get('trailing_enabled', True)
        breakeven_enabled = config.get('parameters', {}).get('breakeven_enabled', True)
        
        if not trailing_enabled and not breakeven_enabled:
            return  # Both disabled, skip
        
        positions = mt5.positions_get(ticket=int(order_ticket))
        if not positions:
            return

        pos = positions[0]
        current_price = mt5.symbol_info_tick(symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask
        point = mt5.symbol_info(symbol).point
        
        # Get pip size for XAUUSD
        symbol_info = mt5.symbol_info(symbol)
        pip_size = point * 10  # Default: 10 points = 1 pip
        if symbol_info:
            # For XAUUSD, pip might be 0.1 or 0.01 depending on broker
            if 'XAU' in symbol.upper() or 'GOLD' in symbol.upper():
                if point >= 0.01:
                    pip_size = point  # 1 point = 1 pip
                else:
                    pip_size = point * 10  # 10 points = 1 pip
        
        # Calculate Profit in Points and Pips
        if pos.type == mt5.ORDER_TYPE_BUY:
            profit_points = (current_price - pos.price_open) / point
            profit_pips = (current_price - pos.price_open) / pip_size
        else:
            profit_points = (pos.price_open - current_price) / point
            profit_pips = (pos.price_open - current_price) / pip_size
        
        # Calculate Initial SL Distance (estimate from current SL if not moved much, or from entry)
        # If SL is close to entry, it's likely initial SL. Otherwise, estimate from entry price.
        if pos.type == mt5.ORDER_TYPE_BUY:
            sl_distance_from_entry = (pos.price_open - pos.sl) / pip_size if pos.sl > 0 else 0
        else:
            sl_distance_from_entry = (pos.sl - pos.price_open) / pip_size if pos.sl > 0 else 0
        
        # If SL is at breakeven or very close, try to estimate initial SL from comment or use default
        # For now, use current SL distance as initial (if reasonable) or estimate from typical values
        if sl_distance_from_entry < 5:  # SL is at breakeven or very close
            # Estimate initial SL: typically 50-200 pips for XAUUSD
            # Use a conservative estimate or try to get from position history
            initial_sl_distance_pips = 100  # Default estimate
        else:
            # Use current SL distance as initial (if SL hasn't been moved much)
            initial_sl_distance_pips = max(sl_distance_from_entry, 50)  # At least 50 pips
            
        request = None
        
        # Track peak profit for pullback detection
        # Note: This requires storing peak in external storage or position comment
        # For now, we'll use a simple approach: if profit decreases significantly, be more conservative
        
        # 1. Breakeven (Improved - based on Initial SL %)
        if breakeven_enabled:
            breakeven_trigger_pips = config.get('parameters', {}).get('breakeven_trigger_pips', 30)
            breakeven_trigger_percent = config.get('parameters', {}).get('breakeven_trigger_percent', 0.5)
            
            # Use % of initial SL if breakeven_trigger_pips is "auto" or use the larger value
            if isinstance(breakeven_trigger_pips, str) and breakeven_trigger_pips.lower() == 'auto':
                breakeven_trigger_pips_calc = initial_sl_distance_pips * breakeven_trigger_percent
            else:
                # Use max of fixed pips or % of initial SL
                breakeven_trigger_pips_calc = max(breakeven_trigger_pips, initial_sl_distance_pips * breakeven_trigger_percent)
            
            breakeven_trigger_points = breakeven_trigger_pips_calc * pip_size / point
            
            if profit_points > breakeven_trigger_points:
                # Check if SL is already at or better than breakeven
                is_breakeven = False
                if pos.type == mt5.ORDER_TYPE_BUY:
                    if pos.sl >= pos.price_open: is_breakeven = True
                else:
                    if pos.sl > 0 and pos.sl <= pos.price_open: is_breakeven = True
                
                if not is_breakeven:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": symbol,
                        "sl": pos.price_open,
                        "tp": pos.tp
                    }
                    print(f"🛡️ Moved SL to Breakeven for Ticket {pos.ticket} (Profit: {profit_pips:.1f} pips, Trigger: {breakeven_trigger_pips_calc:.1f} pips)")

        # 2. Trailing Stop (Improved - based on Initial SL, M5 ATR, min/max limits)
        if trailing_enabled and request is None:
            trailing_trigger_pips = config.get('parameters', {}).get('trailing_trigger_pips', 50)
            trailing_trigger_multiplier = config.get('parameters', {}).get('trailing_trigger_multiplier', 1.2)
            
            # Calculate trailing trigger: use multiplier of initial SL or fixed, whichever is larger
            if isinstance(trailing_trigger_pips, str) and trailing_trigger_pips.lower() == 'auto':
                trailing_trigger_pips_calc = initial_sl_distance_pips * trailing_trigger_multiplier
            else:
                trailing_trigger_pips_calc = max(trailing_trigger_pips, initial_sl_distance_pips * trailing_trigger_multiplier)
            
            trailing_trigger_points = trailing_trigger_pips_calc * pip_size / point
            
            if profit_points > trailing_trigger_points:
                trailing_mode = config.get('parameters', {}).get('trailing_mode', 'atr')
                trailing_atr_timeframe = config.get('parameters', {}).get('trailing_atr_timeframe', 'M5')
                trailing_atr_multiplier = config.get('parameters', {}).get('trailing_atr_multiplier', 1.5)
                trailing_distance_pips = config.get('parameters', {}).get('trailing_distance_pips', 50)
                trailing_min_pips = config.get('parameters', {}).get('trailing_min_pips', 30)
                trailing_max_pips = config.get('parameters', {}).get('trailing_max_pips', 100)
                
                # Calculate trailing distance
                if trailing_mode == 'atr':
                    # ATR-based trailing (Improved: Use M5 for consistency with Initial SL)
                    timeframe_map = {
                        'M1': mt5.TIMEFRAME_M1,
                        'M5': mt5.TIMEFRAME_M5,
                        'M15': mt5.TIMEFRAME_M15
                    }
                    atr_timeframe = timeframe_map.get(trailing_atr_timeframe, mt5.TIMEFRAME_M5)
                    
                    rates = mt5.copy_rates_from_pos(symbol, atr_timeframe, 0, 50)
                    if rates is not None and len(rates) > 14:
                        df = pd.DataFrame(rates)
                        df['tr0'] = abs(df['high'] - df['low'])
                        df['tr1'] = abs(df['high'] - df['close'].shift(1))
                        df['tr2'] = abs(df['low'] - df['close'].shift(1))
                        df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
                        atr_value = df['tr'].rolling(window=14).mean().iloc[-1]
                        
                        if not pd.isna(atr_value) and atr_value > 0:
                            trail_dist = atr_value * trailing_atr_multiplier
                            trail_dist_pips = trail_dist / pip_size
                            # Apply min/max limits
                            trail_dist_pips = max(trailing_min_pips, min(trail_dist_pips, trailing_max_pips))
                            trail_dist = trail_dist_pips * pip_size
                        else:
                            # Fallback to fixed
                            trail_dist = trailing_distance_pips * pip_size
                    else:
                        # Fallback to fixed
                        trail_dist = trailing_distance_pips * pip_size
                else:
                    # Fixed trailing distance
                    trail_dist = trailing_distance_pips * pip_size
                
                new_sl = 0.0
                
                if pos.type == mt5.ORDER_TYPE_BUY:
                    new_sl = current_price - trail_dist
                    # Only update if new_sl is higher than current SL
                    if new_sl > pos.sl:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "symbol": symbol,
                            "sl": new_sl,
                            "tp": pos.tp
                        }
                else:
                    new_sl = current_price + trail_dist
                    # Only update if new_sl is lower than current SL (or SL is 0)
                    if pos.sl == 0 or new_sl < pos.sl:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "symbol": symbol,
                            "sl": new_sl,
                            "tp": pos.tp
                        }
                
                if request:
                    mode_str = f"ATR({trailing_atr_multiplier}x {trailing_atr_timeframe})" if trailing_mode == 'atr' else f"Fixed({trailing_distance_pips}pips)"
                    print(f"🏃 Trailing SL for {pos.ticket}: {pos.sl:.2f} -> {new_sl:.2f} ({mode_str}, Profit: {profit_pips:.1f} pips, Trigger: {trailing_trigger_pips_calc:.1f} pips)")

        if request:
             res = mt5.order_send(request)
             if res.retcode != mt5.TRADE_RETCODE_DONE:
                 print(f"⚠️ Failed to update SL/TP: {res.comment}")

    except Exception as e:
        print(f"⚠️ Error managing position {order_ticket}: {e}")

def get_mt5_error_message(error_code):
    """
    Translate MT5 Error Codes to Human Readable Messages
    """
    error_map = {
        10004: "Requote",
        10006: "Request Rejected",
        10013: "Invalid Request",
        10014: "Invalid Volume",
        10015: "Invalid Price",
        10016: "Invalid Stops",
        10018: "Market Closed",
        10027: "AutoTrading Disabled by Client",
        10030: "Unsupported Filling Mode",
        10031: "Connection Error",
        10036: "Request Timeout"
    }
    msg = error_map.get(error_code, "Unknown Error")
    return f"{error_code} ({msg})"


def check_autotrading_allowed():
    """
    Kiểm tra MT5 có bật AutoTrading (Algo Trading) không.
    Trả về True nếu được phép đặt lệnh, False nếu đang tắt (sẽ bị lỗi 10027).
    In cảnh báo ra console nếu đang tắt.
    """
    try:
        ti = mt5.terminal_info()
        if ti is None:
            return True  # Không lấy được thì không chặn
        allowed = getattr(ti, "trade_allowed", True)
        if not allowed:
            print("⚠️ AutoTrading đang TẮT trong MT5 → Lệnh sẽ bị từ chối (10027).")
            print("   → Mở MT5, bật nút 'Algo Trading' / 'AutoTrading' trên toolbar (màu xanh = bật).")
        return bool(allowed)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Grid Step – Lấy/đặt lệnh chỉ của bot (symbol + magic + comment), tái sử dụng
# ---------------------------------------------------------------------------

def get_positions_bot(symbol, magic, comment=None):
    """
    Lấy danh sách position đang mở chỉ của bot này.
    Lọc theo symbol, magic; nếu comment không None thì chỉ giữ position có comment khớp exact.
    Tránh lấy position của bot khác (magic/comment khác).
    """
    positions = mt5.positions_get(symbol=symbol, magic=magic) or []
    if comment is not None:
        positions = [p for p in positions if (getattr(p, "comment", "") or "").strip() == comment]
    return positions


def get_pending_orders_bot(symbol, magic, comment=None):
    """
    Lấy danh sách lệnh chờ (pending) chỉ của bot này.
    Lọc theo symbol, magic; nếu comment không None thì chỉ giữ order có comment khớp exact.
    Tránh lấy/hủy nhầm lệnh của bot khác.
    """
    orders = mt5.orders_get(symbol=symbol)
    if not orders:
        return []
    orders = [o for o in orders if o.magic == magic]
    if comment is not None:
        orders = [o for o in orders if (getattr(o, "comment", "") or "").strip() == comment]
    return orders


def has_same_price_inverse_duplicate(
    symbol: str,
    magic: int,
    px_buy_limit: float,
    px_sell_limit: float,
    digits: int,
) -> Tuple[bool, str]:
    """
    Trước khi đặt cặp BUY_LIMIT + SELL_LIMIT inverse: kiểm tra đã có lệnh chờ hoặc vị thế
    cùng magic tại đúng một trong hai mức giá (làm tròn theo digits) thì coi là trùng tín hiệu.
    Dùng từ sign_inverse / btc_sign_inverser (signal_relay chỉ ghi file, không gọi MT5).
    """
    rb = round(float(px_buy_limit), digits)
    rs = round(float(px_sell_limit), digits)
    buy_lim = getattr(mt5, "ORDER_TYPE_BUY_LIMIT", 2)
    sell_lim = getattr(mt5, "ORDER_TYPE_SELL_LIMIT", 3)
    pos_buy = getattr(mt5, "POSITION_TYPE_BUY", 0)
    pos_sell = getattr(mt5, "POSITION_TYPE_SELL", 1)

    orders = mt5.orders_get(symbol=symbol) or []
    for o in orders:
        if int(getattr(o, "magic", 0) or 0) != int(magic):
            continue
        try:
            op = round(float(getattr(o, "price_open", 0) or 0), digits)
        except (TypeError, ValueError):
            continue
        ot = int(getattr(o, "type", -1))
        if ot == buy_lim and op == rb:
            return True, f"đã có BUY_LIMIT@{op}"
        if ot == sell_lim and op == rs:
            return True, f"đã có SELL_LIMIT@{op}"

    positions = mt5.positions_get(symbol=symbol) or []
    for p in positions:
        if int(getattr(p, "magic", 0) or 0) != int(magic):
            continue
        try:
            op = round(float(getattr(p, "price_open", 0) or 0), digits)
        except (TypeError, ValueError):
            continue
        pt = int(getattr(p, "type", -1))
        if pt == pos_buy and op == rb:
            return True, f"đã có position BUY@{op}"
        if pt == pos_sell and op == rs:
            return True, f"đã có position SELL@{op}"

    return False, ""


def normalize_inverse_limit_prices(
    info: Any,
    tick: Any,
    px_buy_lim: float,
    px_sell_lim: float,
    digits: int,
) -> Tuple[Optional[float], Optional[float], str]:
    """
    Kéo giá relay về vùng hợp lệ MT5: BUY_LIMIT < ask, SELL_LIMIT > bid, tôn trọng trade_stops_level /
    trade_freeze_level (theo point). Trả về (None, None, lý do) nếu spread không đủ hoặc buy≥sell sau chỉnh.
    """
    if tick is None:
        return (
            round(float(px_buy_lim), digits),
            round(float(px_sell_lim), digits),
            "",
        )
    bid = float(tick.bid)
    ask = float(tick.ask)
    point = float(getattr(info, "point", 0) or 0)
    if point <= 0:
        point = float(10 ** (-digits))
    stops = int(getattr(info, "trade_stops_level", 0) or 0)
    freeze = int(getattr(info, "trade_freeze_level", 0) or 0)
    min_pts = max(stops, freeze, 1)
    min_dist = min_pts * point
    eps = point * 0.25

    max_buy = ask - min_dist
    min_sell = bid + min_dist
    if max_buy <= min_sell + eps:
        return (
            None,
            None,
            f"spread không đủ cho limit (ask−min={max_buy:.{digits}f} ≤ bid+min={min_sell:.{digits}f})",
        )

    pb = round(float(px_buy_lim), digits)
    ps = round(float(px_sell_lim), digits)
    notes: list[str] = []
    if pb > max_buy + eps:
        pb = round(max_buy, digits)
        notes.append(f"BUY_LIMIT→{pb} (≤ ask−min_dist)")
    if ps < min_sell - eps:
        ps = round(min_sell, digits)
        notes.append(f"SELL_LIMIT→{ps} (≥ bid+min_dist)")

    if pb >= ps:
        return (
            None,
            None,
            f"lưới sau chỉnh giá không hợp lệ: BUY {pb} ≥ SELL {ps}",
        )

    note = "; ".join(notes) if notes else ""
    return pb, ps, note


def place_pending_order(symbol, volume, order_type, price, sl, tp, magic, comment, digits=None, type_filling=None):
    """
    Đặt 1 lệnh chờ BUY_STOP hoặc SELL_STOP. Chỉ của bot: dùng magic + comment để sau này lọc.
    order_type: mt5.ORDER_TYPE_BUY_STOP hoặc mt5.ORDER_TYPE_SELL_STOP.
    digits: số chữ số thập phân (nếu None lấy từ symbol_info).
    type_filling: mt5.ORDER_FILLING_IOC / FOK / RETURN (None = tự chọn theo symbol).
    Trả về kết quả mt5.order_send (hoặc None nếu lỗi).
    """
    info = mt5.symbol_info(symbol)
    if not info:
        return None
    if digits is None:
        digits = getattr(info, "digits", 2)
    if type_filling is None:
        type_filling = mt5.ORDER_FILLING_FOK
        if getattr(info, "filling_mode", 0) & 2:
            type_filling = mt5.ORDER_FILLING_IOC
    req = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": round(float(price), digits),
        "sl": round(float(sl), digits) if sl else 0.0,
        "tp": round(float(tp), digits) if tp else 0.0,
        "magic": magic,
        "comment": (comment or "").strip(),
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": type_filling,
    }
    return mt5.order_send(req)


def place_buy_stop(symbol, volume, price, sl, tp, magic, comment, digits=None, type_filling=None):
    """Đặt lệnh BUY_STOP. Chỉ của bot (magic + comment). Trả về result của order_send."""
    return place_pending_order(
        symbol, volume, mt5.ORDER_TYPE_BUY_STOP, price, sl, tp, magic, comment,
        digits=digits, type_filling=type_filling
    )


def place_sell_stop(symbol, volume, price, sl, tp, magic, comment, digits=None, type_filling=None):
    """Đặt lệnh SELL_STOP. Chỉ của bot (magic + comment). Trả về result của order_send."""
    return place_pending_order(
        symbol, volume, mt5.ORDER_TYPE_SELL_STOP, price, sl, tp, magic, comment,
        digits=digits, type_filling=type_filling
    )


def place_buy_limit(symbol, volume, price, sl, tp, magic, comment, digits=None, type_filling=None):
    """Đặt lệnh BUY_LIMIT. Chỉ của bot (magic + comment). Trả về result của order_send."""
    return place_pending_order(
        symbol, volume, mt5.ORDER_TYPE_BUY_LIMIT, price, sl, tp, magic, comment,
        digits=digits, type_filling=type_filling
    )


def place_sell_limit(symbol, volume, price, sl, tp, magic, comment, digits=None, type_filling=None):
    """Đặt lệnh SELL_LIMIT. Chỉ của bot (magic + comment). Trả về result của order_send."""
    return place_pending_order(
        symbol, volume, mt5.ORDER_TYPE_SELL_LIMIT, price, sl, tp, magic, comment,
        digits=digits, type_filling=type_filling
    )


def modify_pending_stop(symbol, order_ticket, price, sl, tp, digits=None, type_filling=None):
    """
    Sửa giá / SL / TP lệnh chờ (BUY_STOP / SELL_STOP). TRADE_ACTION_MODIFY.
    Trả về kết quả order_send hoặc None.
    """
    info = mt5.symbol_info(symbol)
    if not info:
        return None
    if digits is None:
        digits = getattr(info, "digits", 2)
    if type_filling is None:
        type_filling = mt5.ORDER_FILLING_FOK
        if getattr(info, "filling_mode", 0) & 2:
            type_filling = mt5.ORDER_FILLING_IOC
    req = {
        "action": mt5.TRADE_ACTION_MODIFY,
        "order": int(order_ticket),
        "symbol": symbol,
        "price": round(float(price), digits),
        "sl": round(float(sl), digits),
        "tp": round(float(tp), digits),
        "type_filling": type_filling,
    }
    return mt5.order_send(req)


def get_last_n_closed_profits_bot(symbol, magic, n, days_back=1, comment_prefix=None):
    """
    Lấy N lệnh đóng gần nhất chỉ của bot: symbol + magic; nếu comment_prefix có thì chỉ deal có comment bắt đầu bằng prefix.
    Trả về (list_profit, last_close_time_str). list_profit từ mới → cũ. last_close_time_str UTC "YYYY-MM-DD HH:MM:SS".
    """
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days_back)
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*")
    if not deals:
        return [], None
    by_position = {}
    for d in deals:
        if getattr(d, "magic", 0) != magic:
            continue
        if getattr(d, "symbol", "") != symbol:
            continue
        if comment_prefix is not None:
            c = (getattr(d, "comment", "") or "").strip()
            if not c.startswith(comment_prefix):
                continue
        pid = getattr(d, "position_id", None) or getattr(d, "position", None)
        if not pid:
            continue
        if pid not in by_position:
            by_position[pid] = {"out_profit": 0.0, "out_time": None}
        if d.entry == mt5.DEAL_ENTRY_OUT:
            by_position[pid]["out_profit"] += (
                getattr(d, "profit", 0) + getattr(d, "swap", 0) + getattr(d, "commission", 0)
            )
            by_position[pid]["out_time"] = getattr(d, "time", None)
    positions = []
    for pid, v in by_position.items():
        if v["out_time"] is None:
            continue
        positions.append((v["out_profit"], v["out_time"]))
    positions.sort(key=lambda x: x[1], reverse=True)
    first_n = positions[:n]
    profits = [p[0] for p in first_n]
    last_close_time_str = None
    if first_n:
        try:
            ts = first_n[0][1]
            last_close_time_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, OSError):
            pass
    return profits, last_close_time_str


def get_recent_closed_entry_prices_bot(symbol, magic, lookback_minutes, days_back=1, comment_prefix=None):
    """
    Giá vào (DEAL_ENTRY_IN) của các position đã đóng trong lookback_minutes gần nhất.
    Chỉ lệnh bot: symbol + magic; comment_prefix nếu có thì prefix comment (GridStep_...).
    Trả về list giá (float), mới đóng trước (theo thời điểm deal OUT cuối).
    """
    if lookback_minutes <= 0:
        return []
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days_back)
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*")
    if not deals:
        return []
    now_ts = datetime.now().timestamp()
    cutoff = now_ts - lookback_minutes * 60
    by_position = {}
    for d in deals:
        if getattr(d, "magic", 0) != magic:
            continue
        if getattr(d, "symbol", "") != symbol:
            continue
        if comment_prefix is not None:
            c = (getattr(d, "comment", "") or "").strip()
            if not c.startswith(comment_prefix):
                continue
        pid = getattr(d, "position_id", None) or getattr(d, "position", None)
        if not pid:
            continue
        if pid not in by_position:
            by_position[pid] = {"in_price": None, "out_time": None}
        if d.entry == mt5.DEAL_ENTRY_IN:
            by_position[pid]["in_price"] = getattr(d, "price", None)
        elif d.entry == mt5.DEAL_ENTRY_OUT:
            t = getattr(d, "time", None)
            if t is not None:
                prev = by_position[pid].get("out_time")
                if prev is None or t >= prev:
                    by_position[pid]["out_time"] = t
    rows = []
    for pid, v in by_position.items():
        op = v.get("out_time")
        ip = v.get("in_price")
        if op is None or ip is None:
            continue
        if op < cutoff:
            continue
        rows.append((float(ip), op))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [r[0] for r in rows]


def get_closed_deals_bot(symbol, magic, days_back=1, comment_prefix=None):
    """
    Lấy các position đã đóng chỉ của bot: symbol + magic; nếu comment_prefix có thì chỉ deal có comment bắt đầu bằng prefix.
    Trả về dict position_id -> (profit, close_price, close_time_str).
    """
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days_back)
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*")
    if not deals:
        return {}
    by_position = {}
    for d in deals:
        if getattr(d, "magic", 0) != magic:
            continue
        if getattr(d, "symbol", "") != symbol:
            continue
        if comment_prefix is not None:
            c = (getattr(d, "comment", "") or "").strip()
            if not c.startswith(comment_prefix):
                continue
        pid = getattr(d, "position_id", None) or getattr(d, "position", None)
        if not pid:
            continue
        if pid not in by_position:
            by_position[pid] = {"out_profit": 0.0, "out_price": 0.0, "out_time": None}
        if d.entry == mt5.DEAL_ENTRY_OUT:
            by_position[pid]["out_profit"] += (
                getattr(d, "profit", 0) + getattr(d, "swap", 0) + getattr(d, "commission", 0)
            )
            by_position[pid]["out_price"] = getattr(d, "price", 0)
            by_position[pid]["out_time"] = getattr(d, "time", None)
    result = {}
    for pid, v in by_position.items():
        if v["out_profit"] != 0 or v["out_price"] != 0:
            out_ts = v.get("out_time")
            close_time_str = None
            if out_ts:
                try:
                    close_time_str = datetime.utcfromtimestamp(out_ts).strftime("%Y-%m-%d %H:%M:%S")
                except (TypeError, OSError):
                    pass
            result[pid] = (v["out_profit"], v["out_price"], close_time_str)
    return result


def cancel_pending_orders_bot(symbol, magic, comment=None):
    """
    Hủy tất cả lệnh chờ chỉ của bot (symbol + magic + comment nếu có).
    Trả về số lệnh đã hủy.
    """
    orders = get_pending_orders_bot(symbol, magic, comment=comment)
    for o in orders:
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
    return len(orders)


def close_positions_bot(symbol, magic, comment=None, type_filling=None):
    """
    Đóng tất cả position đang mở chỉ của bot (symbol + magic + comment nếu có).
    Trả về số position đã gửi lệnh đóng.
    """
    positions = get_positions_bot(symbol, magic, comment=comment)
    if type_filling is None:
        info = mt5.symbol_info(symbol)
        type_filling = mt5.ORDER_FILLING_IOC
        if info and getattr(info, "filling_mode", 0) & 2:
            type_filling = mt5.ORDER_FILLING_IOC
    closed = 0
    for p in positions:
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            continue
        price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
        r = mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": p.volume,
            "type": mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": p.ticket,
            "price": price,
            "magic": magic,
            "comment": "Close_Bot",
            "type_filling": type_filling,
        })
        if r and r.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
    return closed
