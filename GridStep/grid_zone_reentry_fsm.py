"""
Khóa vùng sau SL (thua) + điều kiện vào lại (nến tổng hợp theo giây).
Không dùng cooldown phút cố định; không reset theo thời gian nếu chưa đủ cấu trúc.

**Tương tác với grid (strategy):** zone lock chỉ chặn **đặt pending mới** khi ``active``; không chặn
SL/TP của lệnh đã mở. Chop +5/-5 khi **idle** (chưa lock) xử lý bằng ``trend_gate_*``, ``sl_tp_offset_price``,
``pending_stop_float_gate_*`` trong strategy — không phải bug FSM.

**Tham số ``zone_lock_tick`` (strategy truyền):** ``half_width_multiplier`` (rộng corridor),
``zone_unlock_mode`` = ``break`` | ``lite`` | ``both``, ``zone_unlock_lite_bars`` (K nến đóng liên tiếp
đóng cửa ngoài [lower,upper]), ``post_unlock_require_trend`` + ``idle_trend_gate_pass`` /
``idle_skip_post_unlock_trend``, ``zone_lock_debug_detail``.

``pending_stop_float_gate_phase``: quy tắc pending STOP khi có position — so PnL nổi với ngưỡng ``x`` / ``y``.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import MetaTrader5 as mt5

DEAL_ENTRY_IN = getattr(mt5, "DEAL_ENTRY_IN", 0)
DEAL_ENTRY_OUT = getattr(mt5, "DEAL_ENTRY_OUT", 1)


def _step_state_key(step_filter: Any) -> str:
    if step_filter is None:
        return "single"
    return str(float(step_filter))


def _round_px(x: float, digits: int) -> float:
    return round(float(x), int(digits))


def pending_stop_float_gate_phase(
    floating_pnl: float,
    gate_x: float = -1.0,
    gate_y: float = 1.0,
) -> str:
    """
    Quy tắc pending STOP khi **đang có position** (cùng step), so với ngưỡng ``gate_x`` và ``gate_y``
    (tiền tài khoản, cùng đơn vị với MT5 position profit).

    - ``weak``: ``floating_pnl < gate_x`` → hủy hết pending, không đặt cặp mới.
    - ``strong``: ``floating_pnl > gate_y`` → đã 2 pending thì giữ; chưa đủ thì đặt lại cặp.
    - ``neutral``: ``gate_x <= floating_pnl <= gate_y`` → không đặt mới nếu 0 pending; giữ 2;
      1 pending → hủy hết, không đặt (tránh lệch).

    Mặc định ``gate_x=-1``, ``gate_y=1``. Nếu ``gate_x >= gate_y`` thì coi ``gate_y = gate_x + 1e-9``.
    """
    gx = float(gate_x)
    gy = float(gate_y)
    if gx >= gy:
        gy = gx + 1e-9
    f = float(floating_pnl)
    if f < gx:
        return "weak"
    if f > gy:
        return "strong"
    return "neutral"


def _fmt_price(x: Any, nd: int) -> str:
    try:
        return f"{float(x):.{int(nd)}f}"
    except (TypeError, ValueError):
        return "?"


def get_zone_lock_status_line(
    state_path: str, step_filter: Any, tick_mid: Optional[float] = None
) -> str:
    """Chuỗi heartbeat: vì sao LOCKED, điều kiện hết lock, trạng thái hiện tại (corridor / nến)."""
    if not state_path or not str(state_path).strip() or not os.path.exists(str(state_path).strip()):
        return "zone: —"
    root = _load_root(str(state_path).strip())
    key = _step_state_key(step_filter)
    st = root.get(key) or {}
    if not bool(st.get("active")):
        lp = st.get("last_sl_position_id")
        if st.get("require_trend_after_zone_clear"):
            extra = " | post_unlock: chờ trend_gate pass"
            if lp:
                return f"zone: idle (đã xử lý SL pos={lp}){extra}"
            return f"zone: idle{extra}"
        if lp:
            return f"zone: idle (đã xử lý SL pos={lp})"
        return "zone: idle"
    nd = int(st.get("display_digits") or 2)
    mid = st.get("mid")
    lo = st.get("lower_zone")
    hi = st.get("upper_zone")
    sec = st.get("bar_sec")
    nb = len(st.get("closed_bars") or [])
    sl_when = str(st.get("locked_sl_when") or "").strip()
    pos_id = st.get("last_sl_position_id")
    mx = float(st.get("sl_deal_max_age_s") or 0.0)
    why = (
        f"vì: SL thua → khóa đặt lưới (mid deal={_fmt_price(mid, nd)} "
        f"zone [{_fmt_price(lo, nd)}-{_fmt_price(hi, nd)}]"
        + (f", deal@{sl_when}" if sl_when else "")
        + (f", pos={pos_id}" if pos_id else "")
        + ")"
    )
    until = (
        f"hết khi: không theo giờ — (1) tick ra khỏi [{_fmt_price(lo, nd)}-{_fmt_price(hi, nd)}] "
        f"để gom nến @{sec}s; (2) mở khóa: mode={st.get('unlock_mode', 'break')} "
        f"(break=pattern 2 đóng+pullback / lite=K đóng ngoài corridor / both= một trong hai)"
    )
    if mx > 0:
        until += f" | SL deal >{int(mx)}s tuổi bị bỏ qua khi idle"

    if tick_mid is not None:
        t = float(tick_mid)
        flo, fhi = float(lo), float(hi)
        if flo <= t <= fhi:
            now = (
                f"hiện: tick={_fmt_price(t, nd)} TRONG corridor → chưa gom nến n={nb} "
                f"(cần ra ngoài mới đếm @{sec}s)"
            )
        else:
            now = f"hiện: tick={_fmt_price(t, nd)} ngoài corridor n={nb} (chờ đủ cấu trúc re-entry)"
        det = str(st.get("last_tick_detail") or "").strip()
        if det:
            now += f" | {det}"
    else:
        now = f"n={nb} @{sec}s (thêm tick_mid vào heartbeat để biết trong/ngoài corridor)"

    return " | ".join([f"zone: LOCKED", why, until, now])


def _load_root(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_root(path: str, data: Dict[str, Any]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def _position_fully_closed(symbol: str, position_id: int) -> bool:
    """Position đã không còn trên MT5 (ticket position = position_id trong deals)."""
    if not position_id:
        return True
    pos = mt5.positions_get(symbol=symbol) or []
    for p in pos:
        if int(getattr(p, "ticket", 0) or 0) == int(position_id):
            return False
    return True


def _find_latest_sl_loss_deal(
    symbol: str,
    magic: int,
    comment_prefix: str,
    days_back: int = 2,
) -> Optional[Any]:
    """
    Position đóng lỗ gần nhất của bot: gom theo position_id.
    Comment prefix khớp nếu **bất kỳ** deal IN/OUT của position có comment (deal OUT đóng thường để trống comment).
    Trả về deal OUT **cuối cùng** của position đó (để lấy price/time/ticket); net = tổng các deal OUT.
    """
    now = datetime.now()
    from_date = now - timedelta(days=max(1, int(days_back)))
    to_date = now
    try:
        mt5.history_select(from_date, to_date)
    except (TypeError, ValueError, AttributeError, OSError):
        pass
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*") or []
    prefix = (comment_prefix or "GridZone").strip()
    mag_i = int(magic)
    # position_id -> aggregate
    by_pos: Dict[int, Dict[str, Any]] = {}
    for d in deals:
        if getattr(d, "symbol", "") != symbol:
            continue
        if int(getattr(d, "magic", 0) or 0) != mag_i:
            continue
        pid = getattr(d, "position_id", None) or getattr(d, "position", None)
        if pid is None:
            continue
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        if pid not in by_pos:
            by_pos[pid] = {
                "tag": False,
                "out_net": 0.0,
                "last_out_t": -1.0,
                "last_out_deal": None,
            }
        c = (getattr(d, "comment", "") or "").strip()
        if c.startswith(prefix):
            by_pos[pid]["tag"] = True
        ent = int(getattr(d, "entry", -1))
        if ent == int(DEAL_ENTRY_OUT):
            net = float(getattr(d, "profit", 0) or 0) + float(getattr(d, "swap", 0) or 0) + float(
                getattr(d, "commission", 0) or 0
            )
            by_pos[pid]["out_net"] += net
            t = float(getattr(d, "time", 0) or 0)
            if t >= by_pos[pid]["last_out_t"]:
                by_pos[pid]["last_out_t"] = t
                by_pos[pid]["last_out_deal"] = d
    best_t = -1.0
    best_deal = None
    for pid, v in by_pos.items():
        if not v.get("tag"):
            continue
        if float(v.get("out_net") or 0) >= 0:
            continue
        if not _position_fully_closed(symbol, pid):
            continue
        t = float(v.get("last_out_t") or -1)
        if t > best_t:
            best_t = t
            best_deal = v.get("last_out_deal")
    if best_deal is None:
        return None
    return best_deal


def _finalize_bar(cur: Optional[Dict[str, Any]], digits: int) -> Optional[Dict[str, Any]]:
    if not cur or not cur.get("has"):
        return None
    return {
        "o": _round_px(float(cur["o"]), digits),
        "h": _round_px(float(cur["h"]), digits),
        "l": _round_px(float(cur["l"]), digits),
        "c": _round_px(float(cur["c"]), digits),
        "t_end": float(cur.get("t_end", 0) or 0),
    }


def _validate_break_up(
    bars: List[Dict[str, Any]], mid: float, upper: float, lower: float, buffer: float
) -> bool:
    """2 nến đóng trên upper+buffer; không đóng lại <= mid sau cặp đó; pullback giữ trên upper; high mới.

    Cặp breakout ở chỉ số (i, i+1) phải có ít nhất một nến sau (i+2..) để kiểm tra pullback — không dùng
    j=len-2 rồi sub=bars[j+2:] vì sub luôn rỗng.
    """
    thr = upper + buffer
    if len(bars) < 4:
        return False
    for i in range(len(bars) - 3, -1, -1):
        if not (bars[i]["c"] > thr and bars[i + 1]["c"] > thr):
            continue
        if i + 2 >= len(bars):
            continue
        if not all(bars[k]["c"] > mid for k in range(i, len(bars))):
            continue
        if not any(
            bars[k]["l"] >= upper and bars[k]["c"] > upper for k in range(i + 2, len(bars))
        ):
            continue
        pre_max_h = max((bars[h]["h"] for h in range(0, i)), default=float("-inf"))
        if bars[-1]["h"] > pre_max_h:
            return True
    return False


def _validate_break_down(
    bars: List[Dict[str, Any]], mid: float, upper: float, lower: float, buffer: float
) -> bool:
    thr = lower - buffer
    if len(bars) < 4:
        return False
    for i in range(len(bars) - 3, -1, -1):
        if not (bars[i]["c"] < thr and bars[i + 1]["c"] < thr):
            continue
        if i + 2 >= len(bars):
            continue
        if not all(bars[k]["c"] < mid for k in range(i, len(bars))):
            continue
        if not any(
            bars[k]["h"] <= lower and bars[k]["c"] < lower for k in range(i + 2, len(bars))
        ):
            continue
        pre_min_l = min((bars[h]["l"] for h in range(0, i)), default=float("inf"))
        if bars[-1]["l"] < pre_min_l:
            return True
    return False


def _bar_close_outside_corridor(c: float, lower: float, upper: float) -> bool:
    """Đóng cửa nằm ngoài [lower, upper] (biên inclusive giống tick corridor)."""
    cl = float(c)
    return cl < float(lower) or cl > float(upper)


def _lite_unlock_ok(
    closed_bars: List[Dict[str, Any]], lower: float, upper: float, k: int
) -> bool:
    """K nến đóng liên tiếp (cuối chuỗi) có đóng cửa ngoài corridor."""
    kk = max(1, int(k))
    if len(closed_bars) < kk:
        return False
    for b in closed_bars[-kk:]:
        if not _bar_close_outside_corridor(float(b["c"]), lower, upper):
            return False
    return True


def zone_idle_post_unlock_requires_trend(state_path: str, step_filter: Any) -> bool:
    """True nếu vừa mở khóa zone và còn chờ trend_gate (idle, không active)."""
    if not state_path or not str(state_path).strip() or not os.path.exists(str(state_path).strip()):
        return False
    root = _load_root(str(state_path).strip())
    st = root.get(_step_state_key(step_filter)) or {}
    return bool(st.get("require_trend_after_zone_clear"))


def zone_lock_tick(
    *,
    state_path: str,
    symbol: str,
    magic: int,
    digits: int,
    step_filter: Any,
    grid_step: float,
    zone_buffer: float,
    bar_seconds: float,
    tick_mid: float,
    comment_prefix: str,
    max_closed_bars: int = 96,
    sl_deal_max_age_seconds: float = 28800.0,
    half_width_multiplier: float = 1.0,
    zone_unlock_mode: str = "break",
    zone_unlock_lite_bars: int = 4,
    post_unlock_require_trend: bool = False,
    zone_lock_debug_detail: bool = False,
    idle_trend_gate_pass: Optional[bool] = None,
    idle_skip_post_unlock_trend: bool = False,
) -> Tuple[bool, str, bool]:
    """
    Cập nhật state + nến tổng hợp; trả về (allowed_to_trade, reason, just_activated_lock).
    Chỉ kích hoạt khóa từ deal SL **gần đây** (tránh bật khóa khi start bot vì deal cũ trong history).
    """
    key = _step_state_key(step_filter)
    root = _load_root(state_path)
    st: Dict[str, Any] = dict(root.get(key) or {"active": False})

    if not bool(st.get("active")):
        if st.get("require_trend_after_zone_clear") and not idle_skip_post_unlock_trend:
            if idle_trend_gate_pass is True:
                st["require_trend_after_zone_clear"] = False
                root[key] = st
                _save_root(state_path, root)
            elif idle_trend_gate_pass is False:
                msg = "post_unlock_need_trend"
                if zone_lock_debug_detail:
                    msg += "|detail=trend_false"
                return False, msg, False
            else:
                msg = "post_unlock_trend_pending"
                if zone_lock_debug_detail:
                    msg += "|detail=no_trend_eval"
                return False, msg, False

        deal = _find_latest_sl_loss_deal(symbol, magic, comment_prefix)
        if deal is None:
            return True, "no_sl_loss", False
        pos_id = int(getattr(deal, "position_id", None) or getattr(deal, "position", None) or 0)
        tid = int(getattr(deal, "ticket", 0) or 0)
        if pos_id and int(st.get("last_sl_position_id") or 0) == pos_id:
            return True, "idle_same_position", False
        if (not pos_id) and tid and int(st.get("last_sl_deal_ticket") or 0) == tid:
            return True, "idle_same_deal", False
        t_deal = float(getattr(deal, "time", 0) or 0)
        if t_deal and (time.time() - t_deal) > float(sl_deal_max_age_seconds):
            st["last_sl_deal_ticket"] = tid
            st["last_sl_position_id"] = pos_id
            root[key] = st
            _save_root(state_path, root)
            return True, "idle_sl_too_old", False
        mid = float(getattr(deal, "price", 0) or tick_mid)
        step = float(grid_step)
        buf = float(zone_buffer)
        mult = max(float(half_width_multiplier), 1e-9)
        half_w = _round_px(step * mult, digits)
        lower = _round_px(mid - half_w, digits)
        upper = _round_px(mid + half_w, digits)
        locked_sl_when = ""
        if t_deal > 0:
            locked_sl_when = datetime.fromtimestamp(t_deal, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        umode = str(zone_unlock_mode or "break").strip().lower()
        if umode not in ("break", "lite", "both"):
            umode = "break"
        lk = max(1, int(zone_unlock_lite_bars or 4))
        st = {
            "active": True,
            "mid": mid,
            "step": step,
            "lower_zone": lower,
            "upper_zone": upper,
            "buffer": buf,
            "bar_sec": float(bar_seconds),
            "last_sl_deal_ticket": tid,
            "last_sl_position_id": pos_id,
            "bar_bucket_end": 0.0,
            "cur_bar": None,
            "closed_bars": [],
            "locked_sl_when": locked_sl_when,
            "display_digits": int(digits),
            "sl_deal_max_age_s": float(sl_deal_max_age_seconds),
            "lock_heartbeat_phase": "active",
            "half_width_mult": mult,
            "unlock_mode": umode,
            "lite_k": lk,
            "unlock_arm_trend_on_clear": bool(post_unlock_require_trend),
            "zone_debug": bool(zone_lock_debug_detail),
        }
        root[key] = st
        _save_root(state_path, root)
        msg = f"LOCK_SL mid={mid} zone=[{lower},{upper}] buf={buf} hw_mult={mult} unlock={umode}"
        return False, msg, True

    # Đang active: không trade nếu giá nằm trong corridor (bao gồm biên mềm)
    lower = float(st["lower_zone"])
    upper = float(st["upper_zone"])
    mid = float(st["mid"])
    if st.get("display_digits") is None:
        st["display_digits"] = int(digits)
    if st.get("sl_deal_max_age_s") is None:
        st["sl_deal_max_age_s"] = float(sl_deal_max_age_seconds)
    buf = float(st.get("buffer") or 0.0)
    bar_sec = float(st.get("bar_sec") or 15.0)
    if bar_sec < 5.0:
        bar_sec = 5.0
    dbg = bool(st.get("zone_debug")) or bool(zone_lock_debug_detail)

    if lower <= tick_mid <= upper:
        st["lock_heartbeat_phase"] = "in_corridor"
        st["last_tick_detail"] = "in_corridor"
        root[key] = st
        _save_root(state_path, root)
        msg = "inside_forbidden_zone"
        if dbg:
            msg += f"|tick={tick_mid:.5f}_lo={lower}_hi={upper}"
        return False, msg, False

    now = time.time()
    bucket_end = float(st.get("bar_bucket_end") or 0.0)
    cur = st.get("cur_bar")
    if bucket_end <= 0:
        bucket_end = now + bar_sec
        cur = {"o": tick_mid, "h": tick_mid, "l": tick_mid, "c": tick_mid, "has": True, "t_end": bucket_end}
        st["bar_bucket_end"] = bucket_end
        st["cur_bar"] = cur
    while now >= float(st["bar_bucket_end"]):
        fin = _finalize_bar(st.get("cur_bar"), digits)
        closed: List[Dict[str, Any]] = list(st.get("closed_bars") or [])
        if fin:
            closed.append(fin)
            if len(closed) > max_closed_bars:
                closed = closed[-max_closed_bars:]
        st["closed_bars"] = closed
        nxt = float(st["bar_bucket_end"]) + bar_sec
        st["bar_bucket_end"] = nxt
        st["cur_bar"] = {
            "o": tick_mid,
            "h": tick_mid,
            "l": tick_mid,
            "c": tick_mid,
            "has": True,
            "t_end": nxt,
        }
    cur = st.get("cur_bar") or {}
    cur["h"] = max(float(cur.get("h", tick_mid)), tick_mid)
    cur["l"] = min(float(cur.get("l", tick_mid)), tick_mid)
    cur["c"] = tick_mid
    cur["has"] = True
    st["cur_bar"] = cur

    bars: List[Dict[str, Any]] = list(st.get("closed_bars") or [])
    fin_live = _finalize_bar(cur, digits) if cur and cur.get("has") else None
    tmp = bars + ([fin_live] if fin_live else [])

    mode = str(st.get("unlock_mode") or "break").strip().lower()
    if mode not in ("break", "lite", "both"):
        mode = "break"
    lite_k = max(1, int(st.get("lite_k") or zone_unlock_lite_bars or 4))

    break_ok = _validate_break_up(tmp, mid, upper, lower, buf) or _validate_break_down(
        tmp, mid, upper, lower, buf
    )
    lite_ok = _lite_unlock_ok(bars, lower, upper, lite_k)

    cleared = False
    clear_reason = ""
    if mode == "lite":
        if lite_ok:
            cleared = True
            clear_reason = "ZONE_CLEARED_LITE_K_OUTSIDE"
    elif mode == "both":
        if lite_ok or break_ok:
            cleared = True
            if lite_ok and break_ok:
                clear_reason = "ZONE_CLEARED_BOTH"
            elif lite_ok:
                clear_reason = "ZONE_CLEARED_LITE_K_OUTSIDE"
            else:
                clear_reason = "ZONE_CLEARED_BREAK_HOLD"
    else:
        if break_ok:
            cleared = True
            clear_reason = "ZONE_CLEARED_BREAK_HOLD"

    if cleared:
        arm = bool(st.get("unlock_arm_trend_on_clear"))
        st_out: Dict[str, Any] = {
            "active": False,
            "last_sl_deal_ticket": st.get("last_sl_deal_ticket"),
            "last_sl_position_id": st.get("last_sl_position_id"),
            "require_trend_after_zone_clear": arm,
        }
        root[key] = st_out
        _save_root(state_path, root)
        msg = clear_reason
        if dbg:
            msg += f"|n_closed={len(bars)}|tmp={len(tmp)}|mode={mode}|brk={int(break_ok)}|lite={int(lite_ok)}"
        return True, msg, False

    st["lock_heartbeat_phase"] = "waiting_structure"
    st["last_tick_detail"] = (
        f"wait n={len(bars)} mode={mode} brk={int(break_ok)} lite={int(lite_ok)} k={lite_k}"
    )
    root[key] = st
    _save_root(state_path, root)
    msg = "zone_lock_waiting_structure"
    if dbg:
        msg += f"|n_closed={len(bars)}|tmp={len(tmp)}|mode={mode}|brk={int(break_ok)}|lite={int(lite_ok)}|k={lite_k}"
    return False, msg, False
