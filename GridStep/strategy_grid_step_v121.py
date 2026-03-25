"""
Grid Step Trading Bot V121 — clone từ V12 + theo document/v121.md:
- Bật breakout block theo mặc định tài liệu (config).
- Re-check Hard Block + Entry Score trước mọi lần re-arm (không chỉ lúc flat); nếu không đủ điều kiện → hủy pending, không đặt lại.
- Basket stop-loss: đóng toàn bộ + hủy pending + last_exit + cooldown (giống basket TP).
- Refresh pendings sau sync; pre-check giá BUY_STOP/SELL_STOP vs ask/bid; rollback nếu một phía fail.
- V12.1 execution (parameters.v121_execution_enabled, mặc định true khi rule bật): một pending theo bias
  (mép range 67/33% + xác nhận wick nến M5), giá STOP từ low/high nến M5 ± buffer; rule/bias dùng mid thị trường;
  step SL/TP trong nhánh này = buffer-based clamp; grid legacy 2 pending vẫn ref quanh anchor.
  V12.1: M5 chỉ là nhịp đánh giá; sau đặt/sửa pending đóng băng tối thiểu 1 nến M5; chỉ MODIFY khi |entry| >= max(0.5*buffer, 0.25*ExecutionStep).
Cooldown/pause riêng: grid_cooldown_v121.json, grid_pause_v121.json, last_exit_time_v121.json.
parameters.lookback_range_hours: độ dài cửa sổ (giờ) để lấy high/low trên M15 cho range box (mặc định 3).
"""
import MetaTrader5 as mt5
import time
import sys
import sqlite3
import os
import json
import hashlib
from datetime import datetime, timedelta, timezone
sys.path.append('..')
from db import Database
from utils import (
    load_config, connect_mt5, send_telegram, get_mt5_error_message,
    get_positions_bot, get_pending_orders_bot, place_buy_stop, place_sell_stop,
    modify_pending_stop,
    get_last_n_closed_profits_bot, get_closed_deals_bot, close_positions_bot,
    check_autotrading_allowed,
)

db = Database()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown_v121.json")
PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause_v121.json")
LAST_EXIT_FILE = os.path.join(SCRIPT_DIR, "last_exit_time_v121.json")

# Tên strategy khi ghi DB (orders, grid_pending_orders) — phân biệt với bot khác. Có thể override bằng parameters.strategy_name trong config.
STRATEGY_NAME_V121 = "Grid_Step_V121"

# Khung giờ mặc định (giờ MT5/server = UTC+0). Dùng khi config không có hours_off / hours_on_strong / hours_on_weak.
# Mỗi phần tử: {"start": "HH:MM", "end": "HH:MM"} (end = hết phút cuối trước phút kết thúc, ví dụ 11:59 = đến 11h59).
DEFAULT_HOURS_OFF = [
    {"start": "08:00", "end": "09:59"},
    {"start": "13:00", "end": "13:59"},
    {"start": "15:00", "end": "16:59"},
    {"start": "19:00", "end": "19:59"},
    {"start": "22:00", "end": "22:59"},
]
DEFAULT_HOURS_ON_STRONG = [
    {"start": "10:00", "end": "11:59"},
    {"start": "14:00", "end": "14:59"},
    {"start": "17:00", "end": "18:59"},
]
DEFAULT_HOURS_ON_WEAK = [
    {"start": "02:00", "end": "02:59"},
    {"start": "23:00", "end": "23:59"},
]


def _parse_time_to_minutes(s):
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    try:
        parts = s.split(":")
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        return h * 60 + m
    except (ValueError, IndexError):
        return None


def _time_in_windows(now_dt, windows):
    """Kiểm tra now_dt (datetime, giờ MT5) có nằm trong bất kỳ khung nào không.
    windows = list of {"start": "HH:MM", "end": "HH:MM"}. Nếu rỗng/None → False."""
    if not windows:
        return False
    now_min = now_dt.hour * 60 + now_dt.minute
    for w in windows:
        if not isinstance(w, dict):
            continue
        start_min = _parse_time_to_minutes(w.get("start"))
        end_min = _parse_time_to_minutes(w.get("end"))
        if start_min is not None and end_min is not None and start_min <= now_min <= end_min:
            return True
    return False


def _get_hours_off(params):
    """Trả về danh sách khung giờ OFF từ config hoặc mặc định."""
    return params.get("hours_off") if params.get("hours_off") is not None else DEFAULT_HOURS_OFF


def _get_hours_on_strong(params):
    return params.get("hours_on_strong") if params.get("hours_on_strong") is not None else DEFAULT_HOURS_ON_STRONG


def _get_hours_on_weak(params):
    return params.get("hours_on_weak") if params.get("hours_on_weak") is not None else DEFAULT_HOURS_ON_WEAK


def load_cooldown_levels(cooldown_minutes):
    if cooldown_minutes <= 0:
        return {}
    if not os.path.exists(COOLDOWN_FILE):
        return {}
    try:
        with open(COOLDOWN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}
    levels = data.get("levels", {})
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=cooldown_minutes)
    result = {}
    for level_key, ts_str in levels.items():
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo:
                ts = ts.replace(tzinfo=None)
            if ts > cutoff:
                result[level_key] = ts_str
        except (ValueError, TypeError):
            pass
    return result


def save_cooldown_levels(level_keys_to_add, step=None):
    if not level_keys_to_add:
        return
    now = datetime.utcnow().isoformat() + "Z"
    data = {"levels": {}}
    if os.path.exists(COOLDOWN_FILE):
        try:
            with open(COOLDOWN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    levels = data.get("levels", {})
    for key in level_keys_to_add:
        k = f"{key}_{step}" if step is not None else str(key)
        levels[k] = now
    data["levels"] = levels
    try:
        with open(COOLDOWN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError:
        pass


def is_level_in_cooldown(levels_dict, price, cooldown_minutes, digits=2, step=None):
    if cooldown_minutes <= 0:
        return False
    key = str(round(float(price), digits))
    if step is not None:
        key = f"{key}_{step}"
    return key in levels_dict


def _pause_until_from_value(val):
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("paused_until") or val.get("until")
    return None


def load_pause_state(clean_expired=True, now_utc=None):
    if not os.path.exists(PAUSE_FILE):
        return {}
    try:
        with open(PAUSE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}
    if not clean_expired or not state:
        return state
    now = now_utc if now_utc is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    to_remove = []
    for name, val in state.items():
        until = _pause_until_from_value(val)
        try:
            if until is None:
                to_remove.append(name)
                continue
            until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
            if until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=timezone.utc)
            if now >= until_dt:
                to_remove.append(name)
        except (ValueError, TypeError):
            to_remove.append(name)
    for name in to_remove:
        state.pop(name, None)
    if to_remove:
        save_pause_state(state)
    return state


def save_pause_state(pauses_dict):
    try:
        with open(PAUSE_FILE, "w", encoding="utf-8") as f:
            json.dump(pauses_dict, f, indent=2)
    except IOError:
        pass


def get_mt5_time_utc(symbol, return_source=False):
    """Lấy giờ hiện tại dùng cho rule (hours_off, entry score), pause, cooldown.
    Ưu tiên: giờ SERVER MT5 (tick.time = thời điểm tick cuối từ broker). Nếu tick None hoặc cũ >60s thì dùng giờ máy LOCAL (UTC).
    Config khung giờ (hours_off, hours_on_strong, hours_on_weak) cần đặt theo giờ server MT5.
    return_source=True: trả về (datetime, "MT5_server"|"local_UTC"). Mặc định chỉ trả về datetime."""
    utc_now = datetime.now(timezone.utc)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return (utc_now, "local_UTC") if return_source else utc_now
    try:
        tick_utc = datetime.utcfromtimestamp(tick.time).replace(tzinfo=timezone.utc)
        if (utc_now - tick_utc).total_seconds() > 60:
            return (utc_now, "local_UTC") if return_source else utc_now
        return (tick_utc, "MT5_server") if return_source else tick_utc
    except (TypeError, OSError):
        return (utc_now, "local_UTC") if return_source else utc_now


def is_paused(strategy_name, now_utc=None):
    state = load_pause_state(now_utc=now_utc)
    until = _pause_until_from_value(state.get(strategy_name))
    if not until:
        return False
    try:
        until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        now = now_utc if now_utc is not None else datetime.now(timezone.utc)
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now < until_dt
    except (ValueError, TypeError):
        return False


def get_pause_remaining(strategy_name, now_utc=None):
    state = load_pause_state(now_utc=now_utc)
    until = _pause_until_from_value(state.get(strategy_name))
    if not until:
        return None
    try:
        until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        now = now_utc if now_utc is not None else datetime.now(timezone.utc)
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        remaining = until_dt - now
        return remaining if remaining.total_seconds() > 0 else None
    except (ValueError, TypeError):
        return None


def set_paused(strategy_name, pause_minutes, from_time=None):
    state = load_pause_state()
    if from_time is not None:
        if isinstance(from_time, str):
            try:
                from_time = datetime.strptime(from_time.replace("Z", "").strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    from_time = datetime.fromisoformat(from_time.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    from_time = datetime.now(timezone.utc)
            if from_time.tzinfo is None:
                from_time = from_time.replace(tzinfo=timezone.utc)
        elif isinstance(from_time, datetime):
            if from_time.tzinfo is None:
                from_time = from_time.replace(tzinfo=timezone.utc)
        else:
            from_time = datetime.now(timezone.utc)
        until_dt = from_time + timedelta(minutes=pause_minutes)
    else:
        until_dt = datetime.now(timezone.utc) + timedelta(minutes=pause_minutes)
    until = until_dt.isoformat().replace("+00:00", "Z")
    state[strategy_name] = until
    save_pause_state(state)


def save_last_exit_time(now_utc=None):
    """Ghi thời điểm đóng chu kỳ (basket TP hoặc basket SL) để áp dụng cooldown sau exit."""
    now = now_utc if now_utc is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    s = now.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LAST_EXIT_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_exit_time": s}, f, indent=2)
    except IOError:
        pass


def load_last_exit_time():
    """Trả về datetime UTC hoặc None."""
    if not os.path.exists(LAST_EXIT_FILE):
        return None
    try:
        with open(LAST_EXIT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        s = data.get("last_exit_time")
        if not s:
            return None
        dt = datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (json.JSONDecodeError, IOError, ValueError):
        return None


def check_consecutive_losses_and_pause(strategy_name, account_id, consecutive_loss_count, pause_minutes):
    """Chỉ đếm lệnh của bot này: DB lọc theo strategy_name + account_id (không lấy lệnh bot khác)."""
    if pause_minutes <= 0 or consecutive_loss_count <= 0:
        return False, None
    rows = db.get_last_closed_orders(strategy_name, limit=consecutive_loss_count + 2, account_id=account_id)
    if len(rows) < consecutive_loss_count:
        return False, None
    first_n = rows[:consecutive_loss_count]
    if all((r["profit"] or 0) < 0 for r in first_n):
        last_close_time = first_n[0].get("close_time")
        return True, last_close_time
    return False, None


def sync_closed_orders_from_mt5(config, strategy_name=None):
    closed = get_closed_deals_bot(config["symbol"], config["magic"], days_back=1, comment_prefix=(strategy_name or STRATEGY_NAME_V121).replace("Grid_Step_", "GridStep_"))
    if not closed:
        return 0
    sn = strategy_name if strategy_name is not None else config.get("parameters", {}).get("strategy_name", STRATEGY_NAME_V121)
    account_id = config.get("account", 0)
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ticket FROM orders WHERE strategy_name = ? AND profit IS NULL AND account_id = ?",
        (sn, account_id),
    )
    tickets_pending = {row[0] for row in cursor.fetchall()}
    conn.close()
    updated = 0
    for ticket in tickets_pending:
        if ticket in closed:
            profit, close_price, close_time = closed[ticket]
            db.update_order_profit(ticket, close_price, profit, close_time)
            updated += 1
    return updated


# ---------- Rule Start Step XAU (từ rule_start_step_xau.md) ----------

def _get_rates(symbol, timeframe, count):
    """Lấy nến từ MT5 (copy_rates_from_pos).

    Python MT5 trả mảng thời gian tăng dần: [0]=nến cũ nhất, [-1]=nến hiện tại (đang chạy),
    [-2]=vừa đóng gần nhất. (Khác với chỉ số vị trí trong tài liệu MQL «từ hiện tại lùi».)
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    return rates if rates is not None and len(rates) >= 1 else None


def _v121_last_closed_m5_open_ts(symbol):
    """Unix mở nến M5 đã đóng gần nhất (rates[-2])."""
    r = _get_rates(symbol, mt5.TIMEFRAME_M5, 3)
    if r is None or len(r) < 2:
        return None
    return int(r[-2]["time"])


def _v121_params_fingerprint(params):
    """Hash parameters để phát hiện đổi config → hủy pending V12.1."""
    if not params:
        return ""
    try:
        blob = json.dumps(params, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def _v121_pending_implied_bias(pending_order):
    t = pending_order.type
    if t == mt5.ORDER_TYPE_BUY_STOP:
        return "BUY"
    if t == mt5.ORDER_TYPE_SELL_STOP:
        return "SELL"
    return None


def _v121_pending_move_min_delta(buf, step_val, params):
    """Ngưỡng tối thiểu để được MODIFY entry: max(0.5*buffer, 0.25*ExecutionStep) — rule 26.4."""
    bfrac = float(params.get("v121_pending_update_buffer_fraction", 0.5))
    sfrac = float(params.get("v121_pending_update_step_fraction", 0.25))
    return max(bfrac * float(buf), sfrac * float(step_val))


def _v121_clear_execution_armed_state():
    """Xóa trạng thái arm V12.1 (bias/config/mốc M5 đã xử lý)."""
    strategy_grid_step_logic._v121_armed_bias = None
    strategy_grid_step_logic._v121_armed_params_sig = None
    strategy_grid_step_logic._v121_last_processed_m5_close_ts = None
    strategy_grid_step_logic._v121_pending_placed_m5_ts = None


def _v121_tp_leg_price(step_val, spread_tp_adj, min_leg_floor):
    """Khoảng giá entry → TP: step − spread (parameters.spread), không nhỏ hơn min_leg_floor."""
    adj = max(0.0, float(spread_tp_adj or 0))
    return max(float(step_val) - adj, float(min_leg_floor))


def _ema(close_arr, period):
    """close_arr: list/array từ cũ -> mới (index 0 = cũ nhất). Trả về EMA tại vị trí cuối."""
    if period <= 0 or len(close_arr) < period:
        return None
    k = 2.0 / (period + 1)
    ema_val = sum(close_arr[:period]) / period
    for i in range(period, len(close_arr)):
        ema_val = close_arr[i] * k + ema_val * (1 - k)
    return ema_val


def _atr(rates, period):
    """rates: copy_rates (cũ→mới): [0] cũ nhất, [-1] nến hiện tại. Trả về ATR tại nến đóng gần nhất (index -2)."""
    if rates is None or len(rates) < period + 2:
        return None
    # True range: max(high-low, |high-prev_close|, |low-prev_close|)
    tr_list = []
    for i in range(1, len(rates)):
        high, low = float(rates[i]["high"]), float(rates[i]["low"])
        prev_close = float(rates[i - 1]["close"])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    if len(tr_list) < period + 1:
        return None
    # SMA(TR) trên period nến kết thúc tại nến đóng gần nhất (bỏ TR của nến đang chạy tr[-1])
    return sum(tr_list[-(period + 1) : -1]) / period


def _median(arr):
    if not arr:
        return None
    a = sorted(arr)
    n = len(a)
    return (a[n // 2] + a[(n - 1) // 2]) / 2.0


def _v121_lookback_range_hours(params):
    """
    Số giờ dùng để dựng box high/low trên M15 (parameters.lookback_range_hours, mặc định 3).
    Cho phép số thập phân (vd 0.5 = 30 phút). Clamp 0.25h–96h.
    """
    try:
        h = float(params.get("lookback_range_hours", 3))
    except (TypeError, ValueError):
        h = 3.0
    return max(0.25, min(96.0, h))


def _v121_lookback_m15_bars(params):
    """Số nến M15 đã đóng cho range box = round(hours×4), tối thiểu 1."""
    return max(1, int(round(_v121_lookback_range_hours(params) * 4)))


def rule_v121_fetch_context(symbol, params):
    """Lấy toàn bộ dữ liệu cần cho rule: atr_m5, atr_m15, ema50_m15, range box M15 (độ dài lookback_range_hours), last3 M15, last3 M5 (breakout_3bars), M5 current/prev bar.
    Trả về dict hoặc None nếu thiếu dữ liệu."""
    atr_period_m5 = params.get("atr_period_m5", 20)
    ema_period_m15 = params.get("ema_period_m15", 50)
    lh_cfg = _v121_lookback_range_hours(params)
    lookback_m15_bars = _v121_lookback_m15_bars(params)
    need_m5 = atr_period_m5 + 5
    need_m15 = max(ema_period_m15 + 5, lookback_m15_bars + 5, 3 + 5, 52)  # 52 để có ema50 và ema50_prev (slope)
    rates_m5 = _get_rates(symbol, mt5.TIMEFRAME_M5, need_m5)
    rates_m15 = _get_rates(symbol, mt5.TIMEFRAME_M15, need_m15)
    if rates_m5 is None or rates_m15 is None:
        return None
    # M5: [-1]=đang chạy, [-2]=vừa đóng (mảng MT5 Python: cũ→mới)
    close_m5 = [float(r["close"]) for r in rates_m5]
    high_m5 = [float(r["high"]) for r in rates_m5]
    low_m5 = [float(r["low"]) for r in rates_m5]
    atr_m5 = _atr(rates_m5, atr_period_m5)
    if atr_m5 is None:
        return None
    range_m5_current = high_m5[-1] - low_m5[-1] if len(high_m5) and high_m5[-1] != low_m5[-1] else 0.0
    range_m5_prev = high_m5[-2] - low_m5[-2] if len(high_m5) > 1 else 0.0
    close_m15 = [float(r["close"]) for r in rates_m15]
    # EMA50 M15: close_m15 đã cũ→mới (đúng thứ tự MT5), không đảo [::-1]
    close_m15_old_to_new = close_m15
    ema50_m15 = _ema(close_m15_old_to_new, ema_period_m15)
    ema50_prev = _ema(close_m15_old_to_new[:-1], ema_period_m15) if len(close_m15_old_to_new) > ema_period_m15 else None
    ema50_slope = (ema50_m15 - ema50_prev) if (ema50_m15 is not None and ema50_prev is not None) else None
    atr_m15 = _atr(rates_m15, 20)
    # Range box: N nến M15 đã đóng gần nhất: i=1 → [-2], i=2 → [-3], … (bỏ [-1] đang chạy)
    n_range = min(lookback_m15_bars, len(rates_m15) - 1)
    if n_range < 1:
        return None
    range_high_3h = max(float(rates_m15[-1 - i]["high"]) for i in range(1, 1 + n_range))
    range_low_3h = min(float(rates_m15[-1 - i]["low"]) for i in range(1, 1 + n_range))
    last3_m15 = []
    for i in range(1, min(4, len(rates_m15))):
        r = rates_m15[-1 - i]
        last3_m15.append({
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
        })
    last3_m5 = []
    for i in range(1, min(4, len(rates_m5))):
        r = rates_m5[-1 - i]
        last3_m5.append({
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
        })
    # Median ATR M5 lookback (để so sánh volatility)
    atr_lookback = params.get("median_atr_lookback", 50)
    rates_m5_long = _get_rates(symbol, mt5.TIMEFRAME_M5, atr_lookback + atr_period_m5 + 2)
    median_atr_m5 = None
    if rates_m5_long is not None and len(rates_m5_long) >= atr_period_m5 + atr_lookback:
        atr_values = []
        for j in range(1, min(atr_lookback + 1, len(rates_m5_long) - atr_period_m5)):
            slice_ = rates_m5_long[j : j + atr_period_m5 + 1]
            a = _atr(slice_, atr_period_m5)
            if a is not None:
                atr_values.append(a)
        if atr_values:
            median_atr_m5 = _median(atr_values)
    if median_atr_m5 is None or median_atr_m5 <= 0:
        median_atr_m5 = atr_m5  # fallback
    return {
        "price": (float(rates_m5[-1]["high"]) + float(rates_m5[-1]["low"])) / 2.0 if rates_m5 is not None else None,
        "atr_m5": atr_m5,
        "atr_m15": atr_m15,
        "ema50_m15": ema50_m15,
        "ema50_slope": ema50_slope,
        "lookback_range_hours": lh_cfg,
        "lookback_m15_bars": lookback_m15_bars,
        "range_high_3h": range_high_3h,
        "range_low_3h": range_low_3h,
        "last3_m15": last3_m15,
        "last3_m5": last3_m5,
        "range_m5_current": range_m5_current,
        "range_m5_prev": range_m5_prev,
        "rates_m5": rates_m5,
        "median_atr_m5": median_atr_m5,
    }


def _v121_breakout_range_hi_lo(ctx, step_base, params):
    """
    Buffer = max(margin * step_base, pct * range_3h). Tắt khi margin<=0 và pct<=0.
    Trả về (enabled, hi, lo, breakout_buffer, margin, pct, range_size_3h) hoặc (False, None, None, 0, ...).
    """
    margin = params.get("block_breakout_range_margin")
    if margin is None:
        margin = 0.5
    margin = float(margin)
    pct = params.get("block_breakout_range_pct")
    if pct is None:
        pct = 0.20
    pct = float(pct)
    if margin <= 0 and pct <= 0:
        return False, None, None, 0.0, margin, pct, 0.0
    range_size_3h = float(ctx["range_high_3h"] - ctx["range_low_3h"])
    if range_size_3h <= 0:
        range_size_3h = float(step_base)
    breakout_buffer = max(margin * float(step_base), pct * range_size_3h)
    hi = float(ctx["range_high_3h"]) + breakout_buffer
    lo = float(ctx["range_low_3h"]) - breakout_buffer
    return True, hi, lo, breakout_buffer, margin, pct, range_size_3h


def rule_v121_hard_blocks(ctx, last_exit_dt, step_base, cooldown_after_exit_minutes, params, now_utc=None):
    """Rule mới không dùng time filter. Hard Block: giá giữa range, breakout, trend mạnh (+ EMA dốc cùng hướng), cooldown (caller), ATR quá nóng."""
    range_size_3h = ctx["range_high_3h"] - ctx["range_low_3h"]
    if range_size_3h <= 0:
        range_size_3h = step_base
    price = ctx["price"]
    mid_low = ctx["range_low_3h"] + range_size_3h * 0.33
    mid_high = ctx["range_low_3h"] + range_size_3h * 0.67
    # Tổng thân 3 nến M15 (trend_strong); breakout_3bars dùng last3_m5 — xem Block 2b
    sum3_body = sum(abs(b["close"] - b["open"]) for b in ctx["last3_m15"])

    # Block 1: Giá đang ở giữa range
    if mid_low < price < mid_high:
        return True, "price_mid_range"
    # Block 2: Breakout mạnh (range nến M5 hiện tại > ratio * ATR M5). ratio=0 để tắt block; không cấu hình = 1.8 (mặc định).
    block_breakout_m5_ratio = params.get("block_breakout_m5_ratio")
    if block_breakout_m5_ratio is None:
        block_breakout_m5_ratio = 1.8
    if float(block_breakout_m5_ratio) > 0 and ctx["range_m5_current"] > float(block_breakout_m5_ratio) * ctx["atr_m5"]:
        return True, "breakout_m5"
    # Block 2b: Tổng thân 3 nến M5 đã đóng > ratio * step_base. ratio=0 để tắt; không cấu hình = 3.0 (mặc định).
    last3_m5 = ctx.get("last3_m5") or []
    sum3_body_m5 = sum(abs(b["close"] - b["open"]) for b in last3_m5)
    block_breakout_3bars_ratio = params.get("block_breakout_3bars_ratio")
    if block_breakout_3bars_ratio is None:
        block_breakout_3bars_ratio = 3.0
    if (
        float(block_breakout_3bars_ratio) > 0
        and len(last3_m5) >= 3
        and sum3_body_m5 > float(block_breakout_3bars_ratio) * step_base
    ):
        return True, "breakout_3bars"
    # Block 2c: breakout_range — buffer = max(margin×step_base, pct×range_3h); tắt khi margin<=0 và pct<=0.
    br_en, hi_br, lo_br, _buf_br, _m_br, _p_br, _rs_br = _v121_breakout_range_hi_lo(ctx, step_base, params)
    if br_en and hi_br is not None and lo_br is not None:
        if price >= hi_br or price <= lo_br:
            return True, "breakout_range"
    # Block 3: Trend mạnh - 3 nến M15 cùng màu + tổng thân > 2.5*step_base + EMA50 dốc cùng hướng
    if len(ctx["last3_m15"]) >= 3 and sum3_body > 2.5 * step_base:
        same_color_up = all(b["close"] >= b["open"] for b in ctx["last3_m15"])
        same_color_down = all(b["close"] <= b["open"] for b in ctx["last3_m15"])
        slope = ctx.get("ema50_slope")
        slope_ok = False
        if slope is not None and abs(slope) > step_base * 0.03:  # dốc rõ
            if same_color_up and slope > 0:
                slope_ok = True
            elif same_color_down and slope < 0:
                slope_ok = True
        if (same_color_up or same_color_down) and slope_ok:
            return True, "trend_strong"
    # Block 4: Cooldown sau exit - do caller kiểm tra
    # Block 5: ATR quá nóng
    med = ctx.get("median_atr_m5") or ctx["atr_m5"]
    if med and ctx["atr_m5"] > 1.5 * med:
        return True, "atr_quá_nóng"
    return False, ""


def rule_v121_check_cooldown_exit(last_exit_dt, now_utc, cooldown_after_exit_minutes):
    """Nếu chưa đủ 20 phút sau last_exit thì block."""
    if cooldown_after_exit_minutes <= 0 or last_exit_dt is None:
        return False
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    if last_exit_dt.tzinfo is None:
        last_exit_dt = last_exit_dt.replace(tzinfo=timezone.utc)
    return (now_utc - last_exit_dt).total_seconds() < cooldown_after_exit_minutes * 60


def rule_v121_entry_score(ctx, now_utc, step_base, params):
    """Rule mới không dùng giờ. A=range, B=EMA, C=hụt lực (max 2), D=volatility, E=mean-reversion (max 2)."""
    score = 0
    breakdown = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
    range_size = ctx["range_high_3h"] - ctx["range_low_3h"]
    if range_size <= 0:
        range_size = step_base
    top_zone = ctx["range_low_3h"] + range_size * 0.67
    bottom_zone = ctx["range_low_3h"] + range_size * 0.33
    rh, rl = ctx["range_high_3h"], ctx["range_low_3h"]
    price = ctx["price"]
    # Chỉ tính mép khi giá còn trong biên 3h (tránh +điểm khi đã breakout — trùng breakout_range block)
    in_upper_third = top_zone <= price <= rh
    in_lower_third = rl <= price <= bottom_zone

    # A - Vị trí trong range (mép +2, rất sát mép +1)
    if in_upper_third or in_lower_third:
        score += 2
        breakdown["A"] = 2
    if (rl + range_size * 0.85 <= price <= rh) or (rl <= price <= rl + range_size * 0.15):
        score += 1
        breakdown["A"] += 1
    # B - Độ lệch khỏi EMA50 M15 (>= 1 step +1, >= 1.5 step +1)
    if ctx.get("ema50_m15") is not None:
        distance_ema = abs(price - ctx["ema50_m15"])
        if distance_ema >= 1.0 * step_base:
            score += 1
            breakdown["B"] += 1
        if distance_ema >= 1.5 * step_base:
            score += 1
            breakdown["B"] += 1
    # C - Dấu hiệu hụt lực (max 2): nến nhỏ hơn trước, râu nến ngược >= 35%
    c_score = 0
    if ctx["range_m5_prev"] > 0 and ctx["range_m5_current"] < ctx["range_m5_prev"]:
        c_score += 1
    for bar in ctx["last3_m15"][:1]:
        total = bar["high"] - bar["low"]
        if total <= 0:
            continue
        body = abs(bar["close"] - bar["open"])
        wick = total - body
        if wick >= 0.35 * total:
            c_score += 1
            break
    c_score = min(c_score, 2)
    score += c_score
    breakdown["C"] = c_score
    # D - Volatility: bình thường +1, 1.2-1.5 +0, >1.5 -1
    med = ctx.get("median_atr_m5") or ctx["atr_m5"]
    if med <= 0:
        med = ctx["atr_m5"]
    if ctx["atr_m5"] <= 1.2 * med:
        score += 1
        breakdown["D"] = 1
    elif ctx["atr_m5"] > 1.5 * med:
        score -= 1
        breakdown["D"] = -1
    # E - Cấu trúc mean-reversion (max 2): giá chạm mép quay đầu, giá lệch EMA không mở rộng
    e_score = 0
    if in_upper_third or in_lower_third:
        for bar in ctx["last3_m15"][:1]:
            total = bar["high"] - bar["low"]
            if total <= 0:
                continue
            wick = total - abs(bar["close"] - bar["open"])
            if wick >= 0.35 * total:
                e_score += 1
                break
    if ctx.get("ema50_m15") is not None:
        distance_ema = abs(price - ctx["ema50_m15"])
        if distance_ema >= 1.0 * step_base and ctx["range_m5_prev"] > 0 and ctx["range_m5_current"] < ctx["range_m5_prev"]:
            e_score += 1
    e_score = min(e_score, 2)
    score += e_score
    breakdown["E"] = e_score
    return score, breakdown


def rule_v121_dynamic_step(ctx, params):
    """step_raw = atr_m5 * k_atr, clamp [step_min, step_max], điều chỉnh theo volatility và cấu trúc (trend/sideway)."""
    step_base = float(params.get("step_base", 5))
    k_atr = float(params.get("k_atr", 1.0))
    step_min = float(params.get("step_min", step_base * 0.8))
    step_max = float(params.get("step_max", step_base * 1.8))
    atr_m5 = ctx["atr_m5"]
    median_atr = ctx.get("median_atr_m5") or atr_m5
    if median_atr <= 0:
        median_atr = atr_m5
    step_raw = atr_m5 * k_atr
    ratio = atr_m5 / median_atr if median_atr else 1.0
    adj = ""
    if ratio < 0.9:
        step_raw = max(step_min, step_raw * 0.9)
        adj = "x0.9(vol_thấp)"
    elif ratio <= 1.2:
        adj = "chuẩn"
    elif ratio <= 1.5:
        step_raw = min(step_max, step_raw * 1.15)
        adj = "x1.15(vol_cao)"
    else:
        step_raw = step_max
        adj = "=step_max(vol_rất_cao)"
    step_raw = max(step_min, min(step_max, step_raw))
    # Chỉnh Step theo cấu trúc: trend nhẹ => nới step, sideway đẹp => thu step
    range_size = ctx["range_high_3h"] - ctx["range_low_3h"] or step_base
    price = ctx["price"]
    rl, rh = ctx["range_low_3h"], ctx["range_high_3h"]
    t67 = rl + range_size * 0.67
    b33 = rl + range_size * 0.33
    at_edge = (t67 <= price <= rh) or (rl <= price <= b33)
    last3 = ctx.get("last3_m15") or []
    same_up = len(last3) >= 3 and all(b["close"] >= b["open"] for b in last3)
    same_down = len(last3) >= 3 and all(b["close"] <= b["open"] for b in last3)
    slope = ctx.get("ema50_slope")
    slope_same = slope is not None and abs(slope) > step_base * 0.03 and ((same_up and slope > 0) or (same_down and slope < 0))
    hụt_lực = ctx["range_m5_prev"] > 0 and ctx["range_m5_current"] < ctx["range_m5_prev"]
    bars_xen_kẽ = len(last3) < 3 or not (same_up or same_down)
    if slope_same:
        step_raw = min(step_max, step_raw * 1.1)
        adj += "+trend1.1"
    elif at_edge and ratio <= 1.2 and bars_xen_kẽ and hụt_lực:
        step_raw = max(step_min, step_raw * 0.9)
        adj += "+sideway0.9"
    step_raw = max(step_min, min(step_max, step_raw))
    step_val = round(step_raw, 3)
    detail = {"step_raw": round(atr_m5 * k_atr, 3), "atr_m5": round(atr_m5, 3), "ratio": round(ratio, 2), "step_min": step_min, "step_max": step_max, "adj": adj.strip() or "chuẩn"}
    return step_val, detail


def _rule_v121_block_debug_log(ctx, params):
    """Số liệu MT5 + ngưỡng config cho từng hard block (để log, tránh nhầm giữa breakout_m5 vs breakout_3bars)."""
    step_base_cfg = float(params.get("step_base", 5))
    out = {
        "step_base_for_blocks": step_base_cfg,
        "lookback_range_hours": _v121_lookback_range_hours(params),
        "lookback_m15_bars": _v121_lookback_m15_bars(params),
    }
    if ctx is None:
        return out

    # Block 2 — breakout M5
    r_m5 = params.get("block_breakout_m5_ratio")
    if r_m5 is None:
        r_m5 = 1.8
    r_m5 = float(r_m5)
    out["block_breakout_m5_ratio"] = r_m5
    atr = float(ctx.get("atr_m5") or 0)
    out["mt5_range_m5_current"] = ctx.get("range_m5_current")
    out["mt5_atr_m5"] = ctx.get("atr_m5")
    if r_m5 > 0 and atr > 0:
        out["breakout_m5_threshold"] = r_m5 * atr

    # Block 2b — tổng thân 3 nến M5 đã đóng vs ratio * step_base (config), KHÔNG dùng step động
    r3 = params.get("block_breakout_3bars_ratio")
    if r3 is None:
        r3 = 3.0
    r3 = float(r3)
    out["block_breakout_3bars_ratio"] = r3
    last3_m5 = ctx.get("last3_m5") or []
    sum3_body_m5 = sum(abs(b["close"] - b["open"]) for b in last3_m5)
    out["mt5_sum3_body_m5"] = sum3_body_m5
    if r3 > 0:
        out["breakout_3bars_threshold"] = r3 * step_base_cfg

    # Block 2c — range 3h (buffer = max(margin×step_base, pct×range_3h), giống rule_v121_hard_blocks)
    rm = params.get("block_breakout_range_margin")
    if rm is None:
        rm = 0.5
    rp = params.get("block_breakout_range_pct")
    if rp is None:
        rp = 0.20
    out["block_breakout_range_margin"] = float(rm)
    out["block_breakout_range_pct"] = float(rp)
    br_en, hi_br, lo_br, buf_br, _, _, rs_dbg = _v121_breakout_range_hi_lo(ctx, step_base_cfg, params)
    if br_en and hi_br is not None:
        out["mt5_price_rule"] = ctx.get("price")
        out["breakout_range_buffer"] = round(buf_br, 3)
        out["breakout_range_range_size_3h"] = round(rs_dbg, 3)
        out["breakout_range_high_line"] = hi_br
        out["breakout_range_low_line"] = lo_br

    # Block 5 — ATR nóng
    med = ctx.get("median_atr_m5") or ctx.get("atr_m5")
    out["median_atr_m5"] = med
    if med:
        out["atr_hot_threshold"] = 1.5 * float(med)

    return out


def _rule_v121_unsatisfied_list(ctx, last_exit_dt, step_base, params, now_utc, cooldown_after_exit, score, entry_score_start, entry_score_probe):
    """
    Liệt kê điều kiện khiến không allow_start: cooldown → hard blocks (độc lập) → ngưỡng EntryScore.
    Chỉ dùng phần score khi không có hard block nào kích hoạt.
    """
    if cooldown_after_exit > 0 and last_exit_dt and rule_v121_check_cooldown_exit(last_exit_dt, now_utc, cooldown_after_exit):
        return ["cooldown sau exit (basket TP/SL): chưa đủ thời gian chờ so với last_exit_time"]
    if ctx is None:
        return ["no_data: thiếu dữ liệu nến M5/M15 hoặc ATR"]

    ret = []
    range_size_3h = ctx["range_high_3h"] - ctx["range_low_3h"]
    if range_size_3h <= 0:
        range_size_3h = step_base
    price = ctx["price"]
    mid_low = ctx["range_low_3h"] + range_size_3h * 0.33
    mid_high = ctx["range_low_3h"] + range_size_3h * 0.67
    lh = _v121_lookback_range_hours(params)
    if mid_low < price < mid_high:
        ret.append(f"price_mid_range: giá trong 33–67% range box {lh:g}h (không start)")

    block_breakout_m5_ratio = params.get("block_breakout_m5_ratio")
    if block_breakout_m5_ratio is None:
        block_breakout_m5_ratio = 1.8
    if float(block_breakout_m5_ratio) > 0 and ctx["range_m5_current"] > float(block_breakout_m5_ratio) * ctx["atr_m5"]:
        thr = float(block_breakout_m5_ratio) * ctx["atr_m5"]
        ret.append(f"breakout_m5: range_m5 {ctx['range_m5_current']:.3f} > ngưỡng {thr:.3f} (ratio×ATR)")

    last3_m5 = ctx.get("last3_m5") or []
    sum3_body_m5 = sum(abs(b["close"] - b["open"]) for b in last3_m5)
    block_breakout_3bars_ratio = params.get("block_breakout_3bars_ratio")
    if block_breakout_3bars_ratio is None:
        block_breakout_3bars_ratio = 3.0
    thr3 = float(block_breakout_3bars_ratio) * step_base
    if float(block_breakout_3bars_ratio) > 0 and len(last3_m5) >= 3 and sum3_body_m5 > thr3:
        ret.append(f"breakout_3bars: tổng |thân| 3 nến M5 {sum3_body_m5:.3f} > {thr3:.3f} (ratio×step_base config)")

    br_en, hi, lo, buf_u, _m_u, _p_u, _rs_u = _v121_breakout_range_hi_lo(ctx, step_base, params)
    if br_en and hi is not None and (price >= hi or price <= lo):
        ret.append(
            f"breakout_range: giá {price:.3f} ngoài [lo−buffer, hi+buffer] (box {lh:g}h) "
            f"buffer=max(margin×step,pct×range_span)={buf_u:.3f}"
        )

    sum3_body_m15 = sum(abs(b["close"] - b["open"]) for b in ctx["last3_m15"])
    if len(ctx["last3_m15"]) >= 3 and sum3_body_m15 > 2.5 * step_base:
        same_color_up = all(b["close"] >= b["open"] for b in ctx["last3_m15"])
        same_color_down = all(b["close"] <= b["open"] for b in ctx["last3_m15"])
        slope = ctx.get("ema50_slope")
        slope_ok = False
        if slope is not None and abs(slope) > step_base * 0.03:
            if same_color_up and slope > 0:
                slope_ok = True
            elif same_color_down and slope < 0:
                slope_ok = True
        if (same_color_up or same_color_down) and slope_ok:
            ret.append("trend_strong: 3 nến M15 cùng màu + EMA50 dốc cùng hướng + tổng |thân| M15 > 2.5×step_base")

    med = ctx.get("median_atr_m5") or ctx["atr_m5"]
    if med and ctx["atr_m5"] > 1.5 * med:
        ret.append(f"atr_quá_nóng: atr_m5 {ctx['atr_m5']:.3f} > 1.5×median {1.5 * float(med):.3f}")

    if ret:
        return ret

    if score <= 3:
        return [f"score_low: EntryScore={score} (≤3, không start)"]
    if score < entry_score_probe:
        return [f"score quá thấp: EntryScore={score} (< entry_score_probe={entry_score_probe})"]
    if score < entry_score_start:
        return [f"score_probe: EntryScore={score} (≥{entry_score_probe} nhưng < entry_score_start={entry_score_start})"]
    return []


def _merge_log_info(base, ctx, params, last_exit_dt=None, now_utc=None, cooldown_after_exit=20, step_base=5.0, score=0, entry_score_start=6, entry_score_probe=5):
    m = _rule_v121_block_debug_log(ctx, params)
    out = dict(base)
    out.update(m)
    out["unsatisfied_conditions"] = _rule_v121_unsatisfied_list(
        ctx, last_exit_dt, step_base, params, now_utc, cooldown_after_exit,
        score, entry_score_start, entry_score_probe,
    )
    return out


def _format_v121_block_reason_detail(block_reason, log_info):
    """Một dòng giải thích ngắn theo đúng block đang active (không lẫn M5 khi block là 3bars)."""
    if not block_reason or not log_info:
        return ""
    br = block_reason
    if br == "breakout_m5":
        return (
            f" | [breakout_m5] ratio={log_info.get('block_breakout_m5_ratio')} "
            f"range_m5={log_info.get('mt5_range_m5_current')} atr_m5={log_info.get('mt5_atr_m5')} "
            f"ngưỡng={log_info.get('breakout_m5_threshold')}"
        )
    if br == "breakout_3bars":
        return (
            f" | [breakout_3bars] ratio={log_info.get('block_breakout_3bars_ratio')} "
            f"* step_base={log_info.get('step_base_for_blocks')} → ngưỡng={log_info.get('breakout_3bars_threshold')} "
            f"| MT5 sum(|thân|) 3 nến M5={log_info.get('mt5_sum3_body_m5')} "
            f"(block nếu sum > ngưỡng; khác PrecheckStep trong log rule)"
        )
    if br == "breakout_range":
        return (
            f" | [breakout_range] box={log_info.get('lookback_range_hours')}h "
            f"margin={log_info.get('block_breakout_range_margin')} "
            f"pct={log_info.get('block_breakout_range_pct')} "
            f"buffer={log_info.get('breakout_range_buffer')} range_span={log_info.get('breakout_range_range_size_3h')} "
            f"price={log_info.get('mt5_price_rule')} high_line={log_info.get('breakout_range_high_line')} "
            f"low_line={log_info.get('breakout_range_low_line')}"
        )
    if br == "trend_strong":
        return " | [trend_strong] 3 nến M15 + EMA slope (xem rule trong code)"
    if br == "atr_quá_nóng":
        return (
            f" | [atr_quá_nóng] atr_m5={log_info.get('mt5_atr_m5')} median={log_info.get('median_atr_m5')} "
            f"ngưỡng_1.5xmedian={log_info.get('atr_hot_threshold')}"
        )
    if br == "price_mid_range":
        lh = log_info.get("lookback_range_hours", 3)
        return f" | [price_mid_range] giá trong 33–67% range box {lh}h"
    return ""


def rule_v121_allow_start_and_step(symbol, price, params, now_utc):
    """
    Trả về (allow_start, step_value, entry_score, block_reason, log_info).
    log_info = dict với score_breakdown (A,B,C,D,E), step_detail, unsatisfied_conditions, ...
    """
    step_base = float(params.get("step_base", 5))
    cooldown_after_exit = int(params.get("cooldown_after_exit_minutes", 20))
    entry_score_start = int(params.get("entry_score_start", 6))
    entry_score_probe = int(params.get("entry_score_probe", 5))
    empty_log = {"score_breakdown": {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}, "step_detail": {}}
    last_exit_dt = load_last_exit_time()

    def _mi(base, ctx, sc):
        return _merge_log_info(
            base, ctx, params,
            last_exit_dt=last_exit_dt,
            now_utc=now_utc,
            cooldown_after_exit=cooldown_after_exit,
            step_base=step_base,
            score=sc,
            entry_score_start=entry_score_start,
            entry_score_probe=entry_score_probe,
        )

    ctx = rule_v121_fetch_context(symbol, params)
    if ctx is None:
        return False, step_base, 0, "no_data", _mi(empty_log, None, 0)
    ctx["price"] = price
    blocked, reason = rule_v121_hard_blocks(ctx, last_exit_dt, step_base, cooldown_after_exit, params, now_utc)
    if rule_v121_check_cooldown_exit(last_exit_dt, now_utc, cooldown_after_exit):
        return False, step_base, 0, "cooldown_after_exit", _mi(empty_log, ctx, 0)
    if blocked:
        score, breakdown = rule_v121_entry_score(ctx, now_utc, step_base, params)
        step_val, step_detail = rule_v121_dynamic_step(ctx, params)
        return False, step_val, score, reason, _mi({"score_breakdown": breakdown, "step_detail": step_detail}, ctx, score)
    score, breakdown = rule_v121_entry_score(ctx, now_utc, step_base, params)
    if score <= 3:
        step_val, step_detail = rule_v121_dynamic_step(ctx, params)
        return False, step_val, score, "score_low", _mi({"score_breakdown": breakdown, "step_detail": step_detail}, ctx, score)
    step_val, step_detail = rule_v121_dynamic_step(ctx, params)
    if score >= entry_score_start:
        return True, step_val, score, "", _mi({"score_breakdown": breakdown, "step_detail": step_detail}, ctx, score)
    if score >= entry_score_probe:
        return False, step_val, score, "score_probe", _mi({"score_breakdown": breakdown, "step_detail": step_detail}, ctx, score)
    return False, step_val, score, "score_below_start", _mi({"score_breakdown": breakdown, "step_detail": step_detail}, ctx, score)


def check_grid_step_v121_db():
    path = db.db_path
    print(f"\n{'='*60}")
    print(f"[DB] path: {path}")
    print(f"     Ton tai: {os.path.exists(path)}")
    if not os.path.exists(path):
        print("     File DB khong ton tai.")
        return
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM grid_pending_orders WHERE strategy_name LIKE 'Grid_Step_V121%'")
        n = cur.fetchone()[0]
        print(f"\n[grid_pending_orders] (strategy_name LIKE 'Grid_Step_V121%'): {n} dong")
        cur.execute("SELECT COUNT(*) FROM orders WHERE strategy_name LIKE 'Grid_Step_V121%'")
        n_ord = cur.fetchone()[0]
        print(f"[orders] (strategy_name LIKE 'Grid_Step_V121%'): {n_ord} dong")
    except sqlite3.OperationalError as e:
        print(f"[DB] {e}")
    conn.close()
    print(f"{'='*60}\n")


def _comment_for_step(step):
    return "GridStep_V121" if step is None else f"GridStep_V121_{step}"


def get_positions_for_step(symbol, magic, step):
    """Chỉ lấy positions của bot V121: lọc theo symbol, magic và comment (GridStep_V121)."""
    return get_positions_bot(symbol, magic, comment=_comment_for_step(step))


def get_grid_anchor_price(symbol, magic, step=None):
    positions = get_positions_for_step(symbol, magic, step)
    if not positions:
        tick = mt5.symbol_info_tick(symbol)
        return (tick.bid + tick.ask) / 2.0
    latest = max(positions, key=lambda p: p.time)
    return float(latest.price_open)


def get_market_price_now(symbol):
    """Mid bid/ask hiện tại — dùng cho rule V12.1 (không dùng anchor position)."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    bid = float(getattr(tick, "bid", 0.0) or 0.0)
    ask = float(getattr(tick, "ask", 0.0) or 0.0)
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return bid or ask or None


def get_pending_orders(symbol, magic, step=None):
    """Chỉ lấy lệnh chờ của bot V121: lọc theo symbol, magic và comment (GridStep_V121). Tránh cancel/đụng bot khác."""
    return get_pending_orders_bot(symbol, magic, comment=_comment_for_step(step))


def cancel_all_pending(symbol, magic, strategy_name=None, account_id=0, step=None):
    """Hủy chỉ lệnh chờ của bot V121 (đã lọc theo comment GridStep_V121 trong get_pending_orders)."""
    if strategy_name is None:
        strategy_name = STRATEGY_NAME_V121
    orders = get_pending_orders_bot(symbol, magic, comment=_comment_for_step(step))
    for o in orders:
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        db.update_grid_pending_status(o.ticket, "CANCELLED")
    return len(orders)


def sync_grid_pending_status(
    symbol,
    magic,
    strategy_name=None,
    account_id=0,
    sl_tp_price=5.0,
    info=None,
    step=None,
    tp_spread_adj=0.0,
    min_tp_leg_floor=0.0,
):
    """Đồng bộ status lệnh chờ với MT5. Khi một lệnh khớp → hủy mọi pending còn lại (1 hoặc 2 lệnh tùy chế độ).
    TP log DB: khoảng TP = step − tp_spread_adj (tối thiểu min_tp_leg_floor); SL giữ nguyên step."""
    if strategy_name is None:
        strategy_name = STRATEGY_NAME_V121
    pending_tickets = {o.ticket for o in get_pending_orders(symbol, magic, step)}
    positions = get_positions_for_step(symbol, magic, step)
    info = info or mt5.symbol_info(symbol)
    digits = getattr(info, "digits", 2) if info else 2
    pos_by_price = {}
    for p in positions:
        key = round(float(p.price_open), digits)
        pos_by_price[key] = p
    step_val = float(sl_tp_price)
    floor = float(min_tp_leg_floor) if min_tp_leg_floor else 0.0
    tp_leg = _v121_tp_leg_price(step_val, tp_spread_adj, floor)
    filled_this_sync = False
    for row in db.get_grid_pending_by_status(strategy_name, symbol, "PENDING"):
        ticket, order_type, price = row["ticket"], row["order_type"], row["price"]
        if ticket in pending_tickets:
            continue
        price_key = round(float(price), digits) if digits else round(float(price), 2)
        pos = pos_by_price.get(price_key)
        if pos:
            db.update_grid_pending_status(ticket, "FILLED", position_ticket=pos.ticket)
            filled_this_sync = True
            entry = float(pos.price_open)
            if pos.type == mt5.ORDER_TYPE_BUY:
                sl, tp = round(entry - step_val, digits), round(entry + tp_leg, digits)
            else:
                sl, tp = round(entry + step_val, digits), round(entry - tp_leg, digits)
            if not db.order_exists(pos.ticket):
                comment_db = strategy_name.replace("Grid_Step_", "GridStep_") if strategy_name else "GridStep_V121"
                db.log_order(
                    pos.ticket, strategy_name, symbol,
                    "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                    float(pos.volume), entry, sl, tp,
                    comment_db, account_id
                )
            print(f"✅ Grid V121 lệnh khớp: ticket={ticket} → position={pos.ticket} ({order_type} @ {price})")
        else:
            db.update_grid_pending_status(ticket, "CANCELLED")
    if filled_this_sync:
        n = cancel_all_pending(symbol, magic, strategy_name, account_id, step)
        if n > 0:
            print(f"   [V121] Đã hủy {n} lệnh chờ còn lại sau khi khớp.")
        _v121_clear_execution_armed_state()
    return


def position_at_level(positions, level_price, point, tolerance_points=1):
    tol = tolerance_points * point
    for p in positions:
        if abs(p.price_open - level_price) <= tol:
            return True
    return False


def v121_bias_from_range_and_m5(ctx, step_base):
    """
    V12.1: mép range 67/33% + xác nhận thân/wick nến M5 đóng (wick >= 0.5 * body).
    """
    range_size = ctx["range_high_3h"] - ctx["range_low_3h"]
    if range_size <= 0:
        range_size = float(step_base)
    price = ctx["price"]
    top_zone = ctx["range_low_3h"] + range_size * 0.67
    bottom_zone = ctx["range_low_3h"] + range_size * 0.33
    rates_m5 = ctx.get("rates_m5")
    if rates_m5 is None or len(rates_m5) < 2:
        return None
    sig = rates_m5[-2]
    o = float(sig["open"])
    h = float(sig["high"])
    l = float(sig["low"])
    c = float(sig["close"])
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    bearish_m5 = c < o
    bullish_m5 = c > o
    sell_confirm = bearish_m5 and upper_wick >= body * 0.5
    buy_confirm = bullish_m5 and lower_wick >= body * 0.5
    rh, rl = ctx["range_high_3h"], ctx["range_low_3h"]
    if top_zone <= price <= rh and sell_confirm:
        return "SELL"
    if rl <= price <= bottom_zone and buy_confirm:
        return "BUY"
    return None


def v121_pending_entry_buffer(ctx, spread_price, min_distance_points, point):
    """buffer = max(0.15 * atr_m5, 1.5 * spread, min_distance_points * point)."""
    atr_m5 = float(ctx.get("atr_m5") or 0)
    md = float(min_distance_points) * float(point)
    return max(0.15 * atr_m5, 1.5 * float(spread_price), md)


def v121_dynamic_step_from_buffer(ctx, buf, params):
    """
    V12.1: step = clamp(max(1.05*atr_m5, 0.25*range_3h, 2.2*buffer), step_min, step_max).
    """
    step_base = float(params.get("step_base", 5))
    step_min = float(params.get("step_min", step_base * 0.8))
    step_max = float(params.get("step_max", step_base * 1.8))
    atr_m5 = float(ctx.get("atr_m5") or step_base)
    range_3h = float(ctx.get("range_high_3h", 0) - ctx.get("range_low_3h", 0))
    if range_3h <= 0:
        range_3h = step_base
    raw = max(
        1.05 * atr_m5,
        0.25 * range_3h,
        2.2 * float(buf),
    )
    step_val = max(step_min, min(step_max, raw))
    detail = {
        "mode": "v121_buffer_based",
        "atr_m5": round(atr_m5, 3),
        "range_3h": round(range_3h, 3),
        "buffer": round(float(buf), 3),
        "raw": round(raw, 3),
        "step_min": step_min,
        "step_max": step_max,
    }
    return round(step_val, 3), detail


def v121_pending_guard_prices(info, point, spread_price):
    stops_level_points = float(getattr(info, "trade_stops_level", 0) or 0)
    freeze_level_points = float(getattr(info, "trade_freeze_level", 0) or 0)
    stops_buffer = stops_level_points * point
    freeze_buffer = freeze_level_points * point
    extra_buffer = max(0.5 * float(spread_price), point)
    min_pending_gap = max(stops_buffer, freeze_buffer, extra_buffer)
    return {
        "stops_buffer": stops_buffer,
        "freeze_buffer": freeze_buffer,
        "extra_buffer": extra_buffer,
        "min_pending_gap": min_pending_gap,
    }


def total_profit(symbol, magic, step=None):
    positions = get_positions_for_step(symbol, magic, step)
    if not positions:
        return 0.0
    return sum(p.profit + p.swap + getattr(p, 'commission', 0) for p in positions)


def close_all_positions(symbol, magic, step=None):
    return close_positions_bot(symbol, magic, comment=_comment_for_step(step))


def strategy_grid_step_logic(config, error_count=0, step=None):
    """V121: step động + re-check rule trước mọi lần đặt lại pending; basket TP/SL."""
    symbol = config["symbol"]
    volume = config["volume"]
    magic = config["magic"]
    params = config.get("parameters", {})
    strategy_name = params.get("strategy_name", STRATEGY_NAME_V121)
    step_filter = None
    min_distance_points = params.get("min_distance_points", 5)
    max_positions = config.get("max_positions", 5)
    target_profit = params.get("target_profit", 50.0)
    basket_stop_loss_usd = float(params.get("basket_stop_loss_usd", 0) or 0)
    spread_max = params.get("spread_max", 0.5)
    consecutive_loss_pause_enabled = params.get("consecutive_loss_pause_enabled", True)
    consecutive_loss_count = params.get("consecutive_loss_count", 2)
    consecutive_loss_pause_minutes = params.get("consecutive_loss_pause_minutes", 5)
    rule_enabled = params.get("rule_start_step_enabled", True)
    # V12.1: một pending theo bias + M5; chỉ khi rule bật (cần context/score). Tắt = grid đối xứng 2 pending.
    v121_exec = bool(params.get("v121_execution_enabled", True)) and rule_enabled

    info = mt5.symbol_info(symbol)
    if not info:
        return error_count, 0
    volume_min = getattr(info, "volume_min", 0.01)
    volume_step = getattr(info, "volume_step", 0.01)
    volume = max(float(volume), volume_min)
    if volume_step > 0:
        volume = round(volume / volume_step) * volume_step
        volume = max(volume, volume_min)
    point = info.point
    min_distance = min_distance_points * point

    positions = get_positions_for_step(symbol, magic, step_filter)
    positions = list(positions)
    pendings = get_pending_orders(symbol, magic, step_filter)

    # Tính step động sớm để dùng cho sync/ensure và place (V121 rule). Giá cho rule: mid thị trường, không anchor position.
    mt5_now, time_src = get_mt5_time_utc(symbol, return_source=True)
    current_price_early = get_market_price_now(symbol)
    if current_price_early is None:
        return error_count, 0
    if rule_enabled:
        allow_start, dynamic_step, entry_score, block_reason, log_info = rule_v121_allow_start_and_step(
            symbol, current_price_early, params, mt5_now
        )
        grid_step_price = dynamic_step
        sl_tp_price = dynamic_step
    else:
        allow_start = True
        grid_step_price = float(params.get("step_base", 5))
        sl_tp_price = grid_step_price
        entry_score = 0
        block_reason = ""
        log_info = {}

    spread_tp_cfg = float(params.get("spread", 0.5) or 0)
    sync_grid_pending_status(
        symbol,
        magic,
        strategy_name,
        config.get("account"),
        sl_tp_price,
        info,
        step_filter,
        tp_spread_adj=spread_tp_cfg,
        min_tp_leg_floor=min_distance,
    )
    pendings = get_pending_orders(symbol, magic, step_filter)

    # Basket TP
    profit = total_profit(symbol, magic, step_filter)
    if profit >= target_profit and positions:
        print(f"✅ [BASKET TP] V121 Profit {profit:.2f} >= {target_profit}, đóng tất cả.")
        close_all_positions(symbol, magic, step_filter)
        cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
        if v121_exec:
            _v121_clear_execution_armed_state()
        save_last_exit_time(get_mt5_time_utc(symbol))
        msg = f"✅ Grid Step V121: Basket TP. Profit={profit:.2f} | Closed all."
        send_telegram(msg, config.get("telegram_token"), config.get("telegram_chat_id"))
        return 0, 0

    # Basket SL (tổng lỗ rổ)
    if basket_stop_loss_usd > 0 and positions and profit <= -abs(basket_stop_loss_usd):
        print(f"🛑 [BASKET SL] V121 Profit {profit:.2f} <= -{abs(basket_stop_loss_usd):.2f}, đóng tất cả.")
        close_all_positions(symbol, magic, step_filter)
        cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
        if v121_exec:
            _v121_clear_execution_armed_state()
        save_last_exit_time(get_mt5_time_utc(symbol))
        msg = f"🛑 Grid Step V121: Basket SL. Profit={profit:.2f} | Closed all."
        send_telegram(msg, config.get("telegram_token"), config.get("telegram_chat_id"))
        return 0, 0

    # Consecutive loss pause (giống v11)
    if consecutive_loss_pause_enabled and consecutive_loss_pause_minutes > 0 and consecutive_loss_count > 0:
        mt5_now = get_mt5_time_utc(symbol)
        if is_paused(strategy_name, now_utc=mt5_now):
            if not hasattr(strategy_grid_step_logic, "_last_pause_log_v121") or strategy_grid_step_logic._last_pause_log_v121 != strategy_name:
                remaining = get_pause_remaining(strategy_name, now_utc=mt5_now)
                remaining_min = max(1, int((remaining.total_seconds() + 59) // 60)) if remaining else consecutive_loss_pause_minutes
                print(f"⏸️ [V121] Đang tạm dừng ({consecutive_loss_count} lệnh thua liên tiếp), chờ {consecutive_loss_pause_minutes} phút (còn {remaining_min} phút).")
                strategy_grid_step_logic._last_pause_log_v121 = strategy_name
            if v121_exec and get_pending_orders(symbol, magic, step_filter):
                n_p = cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
                if n_p:
                    _v121_clear_execution_armed_state()
                    print(f"   [V121 V12.1] Pause: đã hủy {n_p} lệnh chờ.")
            return error_count, 0
        # Chỉ lấy lệnh của bot: MT5 history lọc theo comment_prefix (GridStep_V121/...), không lẫn bot khác
        comment_prefix = (strategy_name or STRATEGY_NAME_V121).replace("Grid_Step_", "GridStep_")
        profits, last_close_time_str = get_last_n_closed_profits_bot(symbol, magic, consecutive_loss_count, days_back=1, comment_prefix=comment_prefix)
        if len(profits) >= consecutive_loss_count and all((p or 0) < 0 for p in profits):
            last_close_dt = None
            if last_close_time_str:
                try:
                    last_close_dt = datetime.strptime(last_close_time_str.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            if last_close_dt is None or mt5_now < last_close_dt + timedelta(minutes=consecutive_loss_pause_minutes):
                n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
                if v121_exec and n_cancelled:
                    _v121_clear_execution_armed_state()
                set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time_str)
                print(f"⏸️ [V121] {consecutive_loss_count} lệnh thua liên tiếp → hủy {n_cancelled} lệnh chờ, tạm dừng {consecutive_loss_pause_minutes} phút.")
                send_telegram(f"⏸️ Grid Step V121 tạm dừng: {consecutive_loss_count} lệnh thua liên tiếp.", config.get("telegram_token"), config.get("telegram_chat_id"))
                return error_count, 0
        did_pause, last_close_time = check_consecutive_losses_and_pause(strategy_name, config.get("account"), consecutive_loss_count, consecutive_loss_pause_minutes)
        # Chỉ set pause khi lệnh thua cuối còn "mới" (trong vòng pause_minutes+1 phút). Tránh: hết pause → check DB vẫn thấy 2 lệnh thua cũ → set pause lại → kẹt vô hạn
        if did_pause:
            if not last_close_time:
                did_pause = False  # DB không có close_time → coi như cũ, không pause lại
            else:
                try:
                    close_dt = datetime.strptime(last_close_time.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    try:
                        close_dt = datetime.fromisoformat(last_close_time.replace("Z", "+00:00"))
                        if close_dt.tzinfo is None:
                            close_dt = close_dt.replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        close_dt = None
                if close_dt is None:
                    did_pause = False  # không parse được → không pause lại
                else:
                    age_seconds = (mt5_now - close_dt).total_seconds() if mt5_now.tzinfo else (datetime.now(timezone.utc) - close_dt).total_seconds()
                    if age_seconds > (consecutive_loss_pause_minutes + 1) * 60:
                        did_pause = False
        if did_pause:
            n_cancelled = cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
            if v121_exec and n_cancelled:
                _v121_clear_execution_armed_state()
            set_paused(strategy_name, consecutive_loss_pause_minutes, from_time=last_close_time)
            print(f"⏸️ [V121] (DB) {consecutive_loss_count} lệnh thua → tạm dừng {consecutive_loss_pause_minutes} phút.")
            return error_count, 0

    tick = mt5.symbol_info_tick(symbol)
    spread_price = (tick.ask - tick.bid) if tick else 0.0
    if spread_price > spread_max:
        return error_count, 0
    if len(positions) >= max_positions:
        return error_count, 0
    # Legacy: tối đa 2 pending. V12.1: tối đa 1; >1 thì dọn.
    if v121_exec:
        if len(pendings) > 1:
            cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
            pendings = get_pending_orders(symbol, magic, step_filter)
            _v121_clear_execution_armed_state()
    elif len(pendings) == 2:
        return error_count, 0

    # Log chi tiết điểm và PrecheckStep (rule/block/start; khác ExecutionStep buffer-based trong nhánh V12.1).
    if rule_enabled and log_info:
        b = log_info.get("score_breakdown") or {}
        sd = log_info.get("step_detail") or {}
        try:
            ts = mt5_now.strftime("%H:%M") if hasattr(mt5_now, "strftime") else f"{mt5_now.hour:02d}:{mt5_now.minute:02d}"
        except Exception:
            ts = "?"
        score_str = f"EntryScore={entry_score} (A={b.get('A',0)} B={b.get('B',0)} C={b.get('C',0)} D={b.get('D',0)} E={b.get('E',0)})"
        ps = grid_step_price
        if sd:
            adj_part = (sd.get("adj", "") or "").strip()
            adj_suffix = f" {adj_part}" if adj_part else ""
            step_str = (
                f"PrecheckStep={ps:.3f} | step_raw={sd.get('step_raw', ps):.3f} "
                f"atr_m5={sd.get('atr_m5', 0):.3f} ratio={sd.get('ratio', 1.0):.2f}{adj_suffix} "
                f"[min={sd.get('step_min', 0)} max={sd.get('step_max', 0)}]"
            )
        else:
            step_str = f"PrecheckStep={ps:.3f}"
        time_str = f"Giờ={ts}({time_src})"
        block_detail = _format_v121_block_reason_detail(block_reason, log_info)
        unsat = log_info.get("unsatisfied_conditions") or []
        unsat_line = ""
        if unsat:
            unsat_line = "\n   📋 Chưa thỏa mãn: " + " | ".join(unsat)
        min_sc = int(params.get("entry_score_start", 6))
        if not allow_start:
            # Gộp log block: dòng 1 = score + PrecheckStep; dòng 2 = Block + chi tiết (tránh wrap cắt "EntryScore")
            head = f"⏸️ [V121] {time_str} | {score_str} | {step_str}"
            block_line = f"   Block: {block_reason} | min_score>={min_sc}{block_detail}"
            full_text = f"{head}\n{block_line}{unsat_line}"
            # Tránh spam cùng trạng thái mỗi giây (hai tick giá lệch nhẹ vẫn in một lần trong cửa sổ throttle)
            throttle_sec = float(params.get("block_log_throttle_seconds", 25))
            sig = (strategy_name, block_reason, entry_score, round(ps, 2))
            now_m = time.monotonic()
            prev = getattr(strategy_grid_step_logic, "_v121_block_log_sig", None)
            if (
                throttle_sec > 0
                and prev is not None
                and prev[0] == sig
                and (now_m - prev[1]) < throttle_sec
            ):
                pass
            else:
                print(full_text)
                strategy_grid_step_logic._v121_block_log_sig = (sig, now_m)
        else:
            print(f"📊 [V121] {time_str} | {score_str} | {step_str} | allow_start={allow_start}{block_detail}{unsat_line}")
            strategy_grid_step_logic._v121_block_log_sig = None

    # V121: re-check Hard Block + Entry Score trước mọi lần re-arm (không chỉ lúc flat). Không đủ điều kiện → hủy pending, không đặt lại.
    if rule_enabled and not allow_start:
        if pendings:
            n_c = cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
            if n_c:
                print(f"⏸️ [V121] Không re-arm (rule): {block_reason or 'score'} — đã hủy {n_c} lệnh chờ.")
                if v121_exec:
                    _v121_clear_execution_armed_state()
        return error_count, 0

    if not v121_exec and grid_step_price < spread_price:
        return error_count, 0

    # V12.1: tắt v121_pending_recheck_on_m5 → giữ pending đến khớp (hành vi cũ).
    if v121_exec and pendings and not params.get("v121_pending_recheck_on_m5", True):
        return error_count, 0

    # V12.1: cùng một nến M5 đã xử lý rồi → không recheck đặt lại (spread/block đã xử lý phía trên).
    if v121_exec and pendings and params.get("v121_pending_recheck_on_m5", True):
        m5_gate_ts = _v121_last_closed_m5_open_ts(symbol)
        last_m5_done = getattr(strategy_grid_step_logic, "_v121_last_processed_m5_close_ts", None)
        if m5_gate_ts is not None and last_m5_done is not None and m5_gate_ts == last_m5_done:
            return error_count, 0

    if positions:
        cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
        if v121_exec:
            _v121_clear_execution_armed_state()
    elif not v121_exec and pendings:
        cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)

    current_price = get_market_price_now(symbol)
    if current_price is None:
        return error_count, 0

    digits = getattr(info, "digits", 2)
    acc = config.get("account")
    cooldown_minutes = params.get("cooldown_minutes", 0)

    # --- V12.1: một pending (SELL STOP hoặc BUY STOP) theo bias + nến M5 đóng gần nhất (rates_m5[-2]) ---
    if v121_exec:
        ctx = rule_v121_fetch_context(symbol, params)
        if ctx is None:
            return error_count, 0
        ctx["price"] = current_price
        sb = float(params.get("step_base", 5))
        bias = v121_bias_from_range_and_m5(ctx, sb)
        rates_m5 = ctx.get("rates_m5")
        if rates_m5 is None or len(rates_m5) < 2:
            return error_count, 0
        sig = rates_m5[-2]
        low_sig = float(sig["low"])
        high_sig = float(sig["high"])
        m5_close_ts = int(rates_m5[-2]["time"])
        pend_cur = get_pending_orders(symbol, magic, step_filter)
        if bias is None:
            if pend_cur:
                cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
                _v121_clear_execution_armed_state()
                strategy_grid_step_logic._v121_last_processed_m5_close_ts = m5_close_ts
            print(f"⏸️ [V121 V12.1] Chưa có bias. EntryScore={entry_score}")
            return error_count, 0
        buf = v121_pending_entry_buffer(ctx, spread_price, min_distance_points, point)
        tick_pl = mt5.symbol_info_tick(symbol)
        if tick_pl is None:
            return error_count, 0
        bid, ask = float(tick_pl.bid), float(tick_pl.ask)
        guard = v121_pending_guard_prices(info, point, spread_price)
        min_pending_gap = guard["min_pending_gap"]

        step_val, step_detail_v121 = v121_dynamic_step_from_buffer(ctx, buf, params)
        grid_step_price = step_val
        sl_tp_price = step_val
        if step_val < spread_price:
            print(
                f"⏸️ [V121 V12.1] ExecutionStep (buffer-based) {step_val:.3f} < spread {spread_price:.3f}."
            )
            return error_count, 0
        print(
            f"📏 [V121 V12.1 ExecutionStep] atr={step_detail_v121['atr_m5']} "
            f"range_3h={step_detail_v121['range_3h']} "
            f"buffer={step_detail_v121['buffer']} raw={step_detail_v121['raw']} "
            f"clamp=[{step_detail_v121['step_min']},{step_detail_v121['step_max']}] "
            f"-> ExecutionStep={step_val}"
        )
        sell_price = round(low_sig - buf, digits)
        buy_price = round(high_sig + buf, digits)
        cur_fp = _v121_params_fingerprint(params)
        filling = mt5.ORDER_FILLING_IOC if (info.filling_mode & 2) else mt5.ORDER_FILLING_FOK
        comment = _comment_for_step(step_filter)
        pend_cur = get_pending_orders(symbol, magic, step_filter)
        if pend_cur and params.get("v121_pending_recheck_on_m5", True):
            if getattr(strategy_grid_step_logic, "_v121_armed_bias", None) is None:
                strategy_grid_step_logic._v121_armed_bias = _v121_pending_implied_bias(pend_cur[0])
                if getattr(strategy_grid_step_logic, "_v121_pending_placed_m5_ts", None) is None:
                    strategy_grid_step_logic._v121_pending_placed_m5_ts = m5_close_ts
            armed_sig = getattr(strategy_grid_step_logic, "_v121_armed_params_sig", None)
            if armed_sig is None:
                strategy_grid_step_logic._v121_armed_params_sig = cur_fp
            elif armed_sig != cur_fp:
                cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
                pend_cur = get_pending_orders(symbol, magic, step_filter)
                strategy_grid_step_logic._v121_armed_bias = None
                strategy_grid_step_logic._v121_armed_params_sig = None
                print("🔄 [V121 V12.1] Đổi config → hủy pending, sẽ đặt lại nếu đủ điều kiện.")
            armed_bias = getattr(strategy_grid_step_logic, "_v121_armed_bias", None)
            if pend_cur and armed_bias and bias != armed_bias:
                cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
                pend_cur = get_pending_orders(symbol, magic, step_filter)
                strategy_grid_step_logic._v121_armed_bias = None
                strategy_grid_step_logic._v121_armed_params_sig = None
                print("🔄 [V121 V12.1] Đổi bias → hủy pending.")
            if pend_cur:
                implied = _v121_pending_implied_bias(pend_cur[0])
                if implied and implied != bias:
                    cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
                    pend_cur = get_pending_orders(symbol, magic, step_filter)
                    strategy_grid_step_logic._v121_armed_bias = None
                    strategy_grid_step_logic._v121_armed_params_sig = None
                    print("🔄 [V121 V12.1] Loại lệnh chờ không khớp bias → hủy.")
            if pend_cur:
                # Rule 26: chưa qua đủ 1 nến M5 sau đặt/sửa → không MODIFY (M5 chỉ là nhịp đánh giá).
                placed_m5 = getattr(strategy_grid_step_logic, "_v121_pending_placed_m5_ts", None)
                if placed_m5 is not None and m5_close_ts <= int(placed_m5):
                    strategy_grid_step_logic._v121_last_processed_m5_close_ts = m5_close_ts
                    strategy_grid_step_logic._v121_armed_bias = bias
                    strategy_grid_step_logic._v121_armed_params_sig = cur_fp
                    return 0, 0
                ord0 = pend_cur[0]
                new_entry = sell_price if bias == "SELL" else buy_price
                old_entry = float(ord0.price_open)
                thr_move = _v121_pending_move_min_delta(buf, step_val, params)
                diff = abs(new_entry - old_entry)
                if diff < thr_move:
                    strategy_grid_step_logic._v121_last_processed_m5_close_ts = m5_close_ts
                    strategy_grid_step_logic._v121_armed_bias = bias
                    strategy_grid_step_logic._v121_armed_params_sig = cur_fp
                    return 0, 0
                tp_leg_v = _v121_tp_leg_price(step_val, spread_tp_cfg, min_distance)
                use_px = round(new_entry, digits)
                if bias == "SELL":
                    if bid > 0 and use_px >= (bid - min_pending_gap):
                        print(
                            f"⏸️ [V121 V12.1] MODIFY SELL_STOP bỏ qua: giá {use_px} >= bid-gap."
                        )
                        strategy_grid_step_logic._v121_last_processed_m5_close_ts = m5_close_ts
                        return error_count, 0
                    nsl = round(use_px + step_val, digits)
                    ntp = round(use_px - tp_leg_v, digits)
                    otype = "SELL_STOP"
                else:
                    if ask > 0 and use_px <= (ask + min_pending_gap):
                        print(
                            f"⏸️ [V121 V12.1] MODIFY BUY_STOP bỏ qua: giá {use_px} <= ask+gap."
                        )
                        strategy_grid_step_logic._v121_last_processed_m5_close_ts = m5_close_ts
                        return error_count, 0
                    nsl = round(use_px - step_val, digits)
                    ntp = round(use_px + tp_leg_v, digits)
                    otype = "BUY_STOP"
                ocp = round(float(ord0.price_open), digits)
                ocs = round(float(getattr(ord0, "sl", 0) or 0), digits)
                octp = round(float(getattr(ord0, "tp", 0) or 0), digits)
                if use_px == ocp and nsl == ocs and ntp == octp:
                    strategy_grid_step_logic._v121_last_processed_m5_close_ts = m5_close_ts
                    strategy_grid_step_logic._v121_armed_bias = bias
                    strategy_grid_step_logic._v121_armed_params_sig = cur_fp
                    return 0, 0
                _tik = int(getattr(ord0, "ticket", 0) or 0)
                rmod = (
                    modify_pending_stop(symbol, _tik, use_px, nsl, ntp, digits=info.digits, type_filling=filling)
                    if _tik
                    else None
                )
                if rmod is not None and rmod.retcode == mt5.TRADE_RETCODE_DONE:
                    db.log_grid_pending(int(_tik), strategy_name, symbol, otype, use_px, nsl, ntp, volume, acc)
                    print(
                        f"🔧 [V121 V12.1] MODIFY {otype} #{_tik} (Δentry≥{round(thr_move, digits)}): "
                        f"px={use_px} SL={nsl} TP={ntp}"
                    )
                    strategy_grid_step_logic._v121_last_processed_m5_close_ts = m5_close_ts
                    strategy_grid_step_logic._v121_pending_placed_m5_ts = m5_close_ts
                    strategy_grid_step_logic._v121_armed_bias = bias
                    strategy_grid_step_logic._v121_armed_params_sig = cur_fp
                    return 0, 0
                errm = mt5.last_error() if rmod is None else (rmod.retcode, rmod.comment)
                print(f"⚠️ [V121 V12.1] MODIFY thất bại {errm} → hủy và đặt lại.")
                cancel_all_pending(symbol, magic, strategy_name, config.get("account"), step_filter)
                pend_cur = get_pending_orders(symbol, magic, step_filter)
                strategy_grid_step_logic._v121_armed_bias = None
                strategy_grid_step_logic._v121_armed_params_sig = None
                strategy_grid_step_logic._v121_pending_placed_m5_ts = None

        if bias == "SELL":
            if bid > 0 and sell_price >= (bid - min_pending_gap):
                print(
                    f"⏸️ [V121 V12.1] SELL_STOP skip: {sell_price} >= bid-gap {round(bid - min_pending_gap, digits)} "
                    f"(bid={bid}, gap={min_pending_gap:.3f})"
                )
                return error_count, 0
            if position_at_level(positions, sell_price, point):
                return error_count, 0
            for p in positions:
                if abs(p.price_open - sell_price) < min_distance:
                    return error_count, 0
            if cooldown_minutes > 0:
                cooldown_levels = load_cooldown_levels(cooldown_minutes)
                if is_level_in_cooldown(cooldown_levels, sell_price, cooldown_minutes, digits, step_filter):
                    return error_count, 0
            tp_leg_v = _v121_tp_leg_price(step_val, spread_tp_cfg, min_distance)
            sl_sell = round(sell_price + step_val, digits)
            tp_sell = round(sell_price - tp_leg_v, digits)
            print(f"📤 [V121 V12.1] bias=SELL | SELL_STOP @ {sell_price} (low_M5={low_sig} buf={buf:.3f}) SL={sl_sell} TP={tp_sell} (leg={tp_leg_v}=step-spread)")
            r = place_sell_stop(symbol, volume, sell_price, sl_sell, tp_sell, magic, comment, digits=info.digits, type_filling=filling)
            if r is None:
                err = mt5.last_error()
                print(f"❌ SELL_STOP lỗi: {err}")
                return error_count + 1, getattr(err, "code", 0)
            if r.retcode != mt5.TRADE_RETCODE_DONE:
                msg = f"❌ SELL_STOP failed: {r.retcode} {r.comment}"
                if r.retcode == 10027:
                    msg += " → Bật nút 'Algo Trading' trong MT5 để cho phép đặt lệnh."
                print(msg)
                return error_count + 1, r.retcode
            if cooldown_minutes > 0:
                save_cooldown_levels([sell_price], step_filter)
            db.log_grid_pending(r.order, strategy_name, symbol, "SELL_STOP", sell_price, sl_sell, tp_sell, volume, acc)
            print(f"✅ Grid V121 V12.1: SELL_STOP @ {sell_price:.2f}")
            strategy_grid_step_logic._v121_last_processed_m5_close_ts = m5_close_ts
            strategy_grid_step_logic._v121_pending_placed_m5_ts = m5_close_ts
            strategy_grid_step_logic._v121_armed_bias = bias
            strategy_grid_step_logic._v121_armed_params_sig = cur_fp
            return 0, 0

        if ask > 0 and buy_price <= (ask + min_pending_gap):
            print(
                f"⏸️ [V121 V12.1] BUY_STOP skip: {buy_price} <= ask+gap {round(ask + min_pending_gap, digits)} "
                f"(ask={ask}, gap={min_pending_gap:.3f})"
            )
            return error_count, 0
        if position_at_level(positions, buy_price, point):
            return error_count, 0
        for p in positions:
            if abs(p.price_open - buy_price) < min_distance:
                return error_count, 0
        if cooldown_minutes > 0:
            cooldown_levels = load_cooldown_levels(cooldown_minutes)
            if is_level_in_cooldown(cooldown_levels, buy_price, cooldown_minutes, digits, step_filter):
                return error_count, 0
        tp_leg_v = _v121_tp_leg_price(step_val, spread_tp_cfg, min_distance)
        sl_buy = round(buy_price - step_val, digits)
        tp_buy = round(buy_price + tp_leg_v, digits)
        print(f"📤 [V121 V12.1] bias=BUY | BUY_STOP @ {buy_price} (high_M5={high_sig} buf={buf:.3f}) SL={sl_buy} TP={tp_buy} (leg={tp_leg_v}=step-spread)")
        r = place_buy_stop(symbol, volume, buy_price, sl_buy, tp_buy, magic, comment, digits=info.digits, type_filling=filling)
        if r is None:
            err = mt5.last_error()
            print(f"❌ BUY_STOP lỗi: {err}")
            return error_count + 1, getattr(err, "code", 0)
        if r.retcode != mt5.TRADE_RETCODE_DONE:
            msg = f"❌ BUY_STOP failed: {r.retcode} {r.comment}"
            if r.retcode == 10027:
                msg += " → Bật nút 'Algo Trading' trong MT5 để cho phép đặt lệnh."
            print(msg)
            return error_count + 1, r.retcode
        if cooldown_minutes > 0:
            save_cooldown_levels([buy_price], step_filter)
        db.log_grid_pending(r.order, strategy_name, symbol, "BUY_STOP", buy_price, sl_buy, tp_buy, volume, acc)
        print(f"✅ Grid V121 V12.1: BUY_STOP @ {buy_price:.2f}")
        strategy_grid_step_logic._v121_last_processed_m5_close_ts = m5_close_ts
        strategy_grid_step_logic._v121_pending_placed_m5_ts = m5_close_ts
        strategy_grid_step_logic._v121_armed_bias = bias
        strategy_grid_step_logic._v121_armed_params_sig = cur_fp
        return 0, 0

    legacy_anchor_price = get_grid_anchor_price(symbol, magic, step_filter)
    ref = round(legacy_anchor_price / grid_step_price) * grid_step_price
    ref = round(ref, info.digits)
    buy_price = round(ref + grid_step_price, info.digits)
    sell_price = round(ref - grid_step_price, info.digits)

    if position_at_level(positions, buy_price, point):
        return error_count, 0
    if position_at_level(positions, sell_price, point):
        return error_count, 0
    for p in positions:
        if abs(p.price_open - buy_price) < min_distance or abs(p.price_open - sell_price) < min_distance:
            return error_count, 0

    if cooldown_minutes > 0:
        cooldown_levels = load_cooldown_levels(cooldown_minutes)
        if is_level_in_cooldown(cooldown_levels, buy_price, cooldown_minutes, info.digits, step_filter) or is_level_in_cooldown(cooldown_levels, sell_price, cooldown_minutes, info.digits, step_filter):
            return error_count, 0

    step_val = float(sl_tp_price)
    tp_leg_l = _v121_tp_leg_price(step_val, spread_tp_cfg, min_distance)
    filling = mt5.ORDER_FILLING_FOK
    if info.filling_mode & 2:
        filling = mt5.ORDER_FILLING_IOC

    comment = _comment_for_step(step_filter)
    sl_buy = buy_price - step_val
    tp_buy = buy_price + tp_leg_l
    sl_sell = sell_price + step_val
    tp_sell = sell_price - tp_leg_l

    if tick is None:
        return error_count, 0
    bid, ask = tick.bid, tick.ask
    if bid > 0 and buy_price <= ask:
        print(f"⏸️ [V121] BUY_STOP skip: price {buy_price} <= ask {ask} (Invalid price).")
        return error_count, 0
    if bid > 0 and sell_price >= bid:
        print(f"⏸️ [V121] SELL_STOP skip: price {sell_price} >= bid {bid} (Invalid price).")
        return error_count, 0

    print(
        f"📤 [V121] PrecheckStep={grid_step_price:.3f} | BUY_STOP @ {buy_price} (SL={sl_buy}, TP={tp_buy}) | "
        f"SELL_STOP @ {sell_price} (SL={sl_sell}, TP={tp_sell})"
    )
    r1 = place_buy_stop(symbol, volume, buy_price, sl_buy, tp_buy, magic, comment, digits=info.digits, type_filling=filling)
    r2 = place_sell_stop(symbol, volume, sell_price, sl_sell, tp_sell, magic, comment, digits=info.digits, type_filling=filling)

    if r1 is None:
        err = mt5.last_error()
        print(f"❌ BUY_STOP lỗi: {err}")
        return error_count + 1, getattr(err, "code", 0)
    if r2 is None:
        err = mt5.last_error()
        print(f"❌ SELL_STOP lỗi: {err}")
        return error_count + 1, getattr(err, "code", 0)
    if r1.retcode == mt5.TRADE_RETCODE_DONE and r2 is not None and r2.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Grid V121: BUY_STOP @ {buy_price:.2f}, SELL_STOP @ {sell_price:.2f} | ref={ref}")
        if cooldown_minutes > 0:
            save_cooldown_levels([buy_price, sell_price], step_filter)
        db.log_grid_pending(r1.order, strategy_name, symbol, "BUY_STOP", buy_price, sl_buy, tp_buy, volume, acc)
        db.log_grid_pending(r2.order, strategy_name, symbol, "SELL_STOP", sell_price, sl_sell, tp_sell, volume, acc)
        return 0, 0
    # Một phía thành công, phía kia fail → gỡ pending đã đặt để tránh grid nửa vời
    if r1.retcode == mt5.TRADE_RETCODE_DONE and r2.retcode != mt5.TRADE_RETCODE_DONE:
        oid = getattr(r1, "order", None)
        if oid:
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": oid})
            print(f"⚠️ [V121] Rollback BUY_STOP order={oid} (SELL_STOP không thành công).")
        msg = f"❌ SELL_STOP failed: {r2.retcode} {r2.comment}"
        if r2.retcode == 10027:
            msg += " → Bật nút 'Algo Trading' trong MT5 để cho phép đặt lệnh."
        print(msg)
        return error_count + 1, r2.retcode
    if r2.retcode == mt5.TRADE_RETCODE_DONE and r1.retcode != mt5.TRADE_RETCODE_DONE:
        oid = getattr(r2, "order", None)
        if oid:
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": oid})
            print(f"⚠️ [V121] Rollback SELL_STOP order={oid} (BUY_STOP không thành công).")
        msg = f"❌ BUY_STOP failed: {r1.retcode} {r1.comment}"
        if r1.retcode == 10027:
            msg += " → Bật nút 'Algo Trading' trong MT5 để cho phép đặt lệnh."
        print(msg)
        return error_count + 1, r1.retcode
    _hint_10027 = " → Bật nút 'Algo Trading' trong MT5 để cho phép đặt lệnh."
    if r1.retcode != mt5.TRADE_RETCODE_DONE:
        msg = f"❌ BUY_STOP failed: {r1.retcode} {r1.comment}"
        if r1.retcode == 10027:
            msg += _hint_10027
        print(msg)
        return error_count + 1, r1.retcode
    if r2.retcode != mt5.TRADE_RETCODE_DONE:
        msg = f"❌ SELL_STOP failed: {r2.retcode} {r2.comment}"
        if r2.retcode == 10027:
            msg += _hint_10027
        print(msg)
        return error_count + 1, r2.retcode
    return error_count, 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].strip() == "--check-db":
        check_grid_step_v121_db()
        sys.exit(0)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "configs", "config_grid_step_v121.json")
    config = load_config(config_path)

    consecutive_errors = 0
    if config and connect_mt5(config):
        check_autotrading_allowed()  # Cảnh báo nếu AutoTrading tắt trong MT5 (lỗi 10027)
        params = config.get("parameters", {})
        rule_enabled = params.get("rule_start_step_enabled", True)
        v121_exec = bool(params.get("v121_execution_enabled", True)) and rule_enabled
        _lb_h = _v121_lookback_range_hours(params)
        _lb_b = _v121_lookback_m15_bars(params)
        print(
            f"✅ Grid Step V121 Bot - Started | Rule: {'ON' if rule_enabled else 'OFF'} | "
            f"V12.1 execution: {'ON' if v121_exec else 'OFF'} | "
            f"Range box M15: {_lb_h}h (~{_lb_b} nến đóng, lookback_range_hours)"
        )
        loop_count = 0
        try:
            while True:
                if params.get("consecutive_loss_pause_enabled", True):
                    sync_closed_orders_from_mt5(config, strategy_name=params.get("strategy_name", STRATEGY_NAME_V121))
                consecutive_errors, last_error_code = strategy_grid_step_logic(config, consecutive_errors, step=None)
                loop_count += 1
                if loop_count % 30 == 0:
                    sym = config["symbol"]
                    mag = config["magic"]
                    # Chỉ đếm position/pending của bot V121 (comment GridStep_V121/...), tránh lẫn bot khác
                    _v121_prefix = (params.get("strategy_name") or STRATEGY_NAME_V121).replace("Grid_Step_", "GridStep_")
                    _all_pos = mt5.positions_get(symbol=sym, magic=mag) or []
                    pos = [p for p in _all_pos if (getattr(p, "comment", "") or "").startswith(_v121_prefix)]
                    _all_ords = mt5.orders_get(symbol=sym) or []
                    ords = [o for o in _all_ords if o.magic == mag and (getattr(o, "comment", "") or "").startswith(_v121_prefix)]
                    tick = mt5.symbol_info_tick(sym)
                    spread = (tick.ask - tick.bid) if tick else 0
                    print(f"🔄 Grid V121 | Positions: {len(pos)} | Pending: {len(ords)} | Spread: {spread:.2f} | Loop #{loop_count}")
                if consecutive_errors >= 5:
                    error_msg = get_mt5_error_message(last_error_code)
                    print(f"⚠️ [V121] 5 lỗi liên tiếp. Tạm dừng 2 phút... {error_msg}")
                    send_telegram(f"⚠️ Grid Step V121: 5 lỗi liên tiếp. {error_msg}", config.get("telegram_token"), config.get("telegram_chat_id"))
                    time.sleep(120)
                    consecutive_errors = 0
                time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 Grid Step V121 Bot Stopped")
            mt5.shutdown()
