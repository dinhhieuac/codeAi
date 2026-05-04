"""
Grid Step Trading Bot V5.

V5 tái sử dụng toàn bộ logic từ strategy_grid_step.py, nhưng:
- chấm điểm XAUUSD: scores.py (`xauusd_grid_step_v5_score_detailed`, `xauusd_grid_step_v5_is_blocked`)
- dùng file config riêng: configs/config_grid_step_v5.json
- tách file cooldown/pause riêng cho phiên bản v5
- wrapper (vd strategy_grid_step_btc_v5) gọi configure_grid_step_v5_paths() để tách relay/live log.
- Supervisor XAU (trong **file này** — `run()`): `use_dual_supervisor` spawn hai worker `--v5-child` khi **đồng thời**
  (1) argv = config demo mặc định `config_grid_step_v5.json`, (2) không có `--no-parallel-live`,
  (3) tồn tại `configs/config_grid_step_inverse_live.json`, (4) `parameters.v5_parallel_inverse_live` trong JSON demo không phải `false`.
  Live child dùng `config_grid_step_inverse_live.json` (tài khoản / `mt5_path` riêng). Cha không login MT5.
- Supervisor BTC: vẫn dùng `strategy_grid_step_btc_v5.py` (`--btc-v5-child`, `btc_v5_parallel_live`, `config_grid_step_btc_v5_live.json`).
- parameters: v5_log_debug (alias logDebug, default false) — false: một dòng score/rules/kết luận; true: full [SIGNAL][SCORE]...
- **`loop_interval_seconds`**: `sleep` **cuối** mỗi vòng (mặc định 10 **giây**). Đơn vị mặc định là **giây** (float, tối thiểu **1 ms**): vd `0.1` = 100 ms. Để ghi **số nguyên mili giây** trên cùng key: đặt **`loop_interval_unit`**: `"ms"` (vd `100` hoặc `200` → 0.1s / 0.2s). Hoặc dùng **`loop_interval_ms`** (ưu tiên nếu có, >0). Chu kỳ thực ≈ MT5/history/score + sleep. **`v5_rescore_only_on_new_close`**: dòng `📚 [V5 Gate] chưa có lệnh đóng mới` bị **throttle** — khoảng cách tối thiểu giữa hai lần in: **`v5_gate_no_new_close_log_seconds`** (mặc định 30, clamp 1–3600) — **không** phải tần suất vòng lặp. Log `🔄 … Loop #N` mỗi 30 vòng kèm `avg_loop≈` (đo thực).
- v5_role=live (không inverse-only): không đọc history trên live; mirror theo relay / zone; có grid → base strategy.
  Kiểm tra zone (nếu không blind) = so giá mid với zone_key trong relay.
- `log/pending_stop_pair_YYYY-MM-DD.jsonl`: cặp BUY_STOP+SELL_STOP khi có lệnh/position mới (tắt: `v5_pending_pair_log_enabled`: false).
- `v5_live_inverse_limits_from_demo_file` (live): đọc `RELAY_DEMO_FILE` (vd btc_v5_relay_demo.json do demo ghi), đặt **BUY_LIMIT+SELL_LIMIT** trực tiếp trên account live — **symbol / magic / volume** lấy từ config live (không dùng symbol trong file relay để mở lệnh). Consumed: `btc_signal_inverse_consumed_relay_ids.json` (cùng bot `btc_sign_inverser` nếu chạy song song — nên tắt một trong hai).
- `v5_live_inverse_only` (live): **không** gate / relay tín hiệu / grid STOP; lắng nghe TCP (`v5_inverse_ipc_port`) — xử lý **`demo_fill`** (copy MARKET ngược chiều khi demo **khớp position**) và tùy chọn snapshot inverse LIMIT (`v5_live_inverse_limit_ipc`).
  - **`v5_live_market_copy_demo_fill_enabled`** (live, mặc định true): bật/tắt copy MARKET từ event `demo_fill` (tắt = live nhận TCP nhưng không đặt lệnh).
  - `v5_inverse_ipc_port` > 0: demo **đẩy** (1) `demo_fill` khi có **position mới** khớp; (2) `demo_close` khi position đó đã đóng (sau khi `demo_fill` TCP OK); (3) snapshot inverse khi `demo_write_inverse_relay_file` (nếu live bật `v5_live_inverse_limit_ipc`). Live: `demo_fill` → MARKET ngược; `demo_close` → đóng position comment `CopyFill_<ticket>`; consumed `v5_copy_fill_consumed_ids.json` theo `position_ticket` demo (mở).
  - `v5_demo_push_copy_fill_ipc` (demo, mặc định true): gửi `demo_fill` qua TCP khi xuất hiện **position ticket mới** (symbol/magic bot) so với snapshot đã công bố — so sánh **xuyên chu kỳ** (sau `sleep`), không chỉ `post−pre` trong cùng vòng (tránh lỡ khớp giữa hai vòng); **không** gửi khi chỉ có pending STOP chưa kích hoạt; live nên **bind** cổng IPC trước khi demo khớp (nếu không sẽ `gửi TCP thất bại` / log không đọc được position sau retry).
  - `v5_market_copy_deviation` (live): deviation market copy (mặc định 30).
  - **`v5_market_copy_sl_tp_enabled`** (live, mặc định **false**): bật thì MARKET copy-fill có SL/TP như lưới (`entry` = bid/ask live, `step` = `v5_market_copy_sl_tp_step` / `steps[0]` / `step`, + `spread_sl`/`spread_tp` root). Mặc định tắt theo yêu cầu copy “trần”.
  - **`v5_demo_push_copy_close_ipc`** (demo, mặc định true): khi demo **đóng** position đã từng gửi `demo_fill` thành công → gửi TCP `demo_close` (cùng port IPC).
  - **`v5_live_market_copy_close_enabled`** (live, mặc định true): nhận `demo_close` → `close_positions_bot` các position live có comment `CopyFill_<demo_ticket>`.
  - `v5_inverse_ipc_port` = 0: live đọc `RELAY_DEMO_FILE` như cũ (fallback).
  - `v5_inverse_ipc_host` (mặc định 127.0.0.1): host bind/listen và host push.
- `relay_demo_file` / `relay_demo_history_log_file` (parameters): đường dẫn tương đối `GridStep/` hoặc tuyệt đối — để demo và live **cùng file** snapshot inverse (vd `btc_v5_relay_demo.json`); bắt buộc nếu chạy `strategy_grid_step_v5.py` trực tiếp thay vì `strategy_grid_step_btc_v5.py`.
- `v5_demo_inverse_file_when_pair_and_missing_file` (demo): nếu **chưa có** file RELAY_DEMO nhưng MT5 đã có đủ cặp BUY_STOP+SELL_STOP → tự tạo `grid_preview` từ giá lệnh và ghi file (hữu ích khi bot demo restart mà lệnh vẫn còn).
- `v5_live_inverse_log_skip` (live): in lý do bỏ qua inverse (đã consumed, thiếu file, …); mặc định true.

Demo (p_demo) vs live (p_live) — vì sao số lệnh có thể lệch?
- **SL/TP “giống nhau”** chỉ đúng theo nghĩa: cùng **khoảng step** quanh **giá vào của chính lệnh đó** (`strategy_grid_step`: BUY_STOP/SELL_STOP ± step; `sign_inverse.place_pair_from_inverse_relay`: BUY_LIMIT/SELL_LIMIT ± step rồi cộng `spread_sl`/`spread_tp` từ config live). Demo **không** dùng spread_tp mặc định −0.3 như inverse.
- **Mức SL/TP tuyệt đối trên chart không trùng demo**: `grid_preview_inverse` hoán **buy_price/sell_price** so với demo; giá vào live sau `normalize_inverse_limit_prices` có thể lệch tick; vì vậy không thể kỳ vọng “khớp giống hệt” như hai lệnh cùng ticket — chỉ mirror **cấu trúc** lưới.
- Demo đặt **BUY_STOP + SELL_STOP** (2 pending STOP); live InvGrid đặt **BUY_LIMIT + SELL_LIMIT** (2 pending LIMIT) — cùng một snapshot nhưng **loại lệnh khác**; giá chạm STOP vs LIMIT khác điều kiện kích hoạt → **thời điểm / nhánh khớp** không đồng bộ.
- **Một chân live bị broker từ chối** (`place_pair_from_inverse_relay` trong `btc_sign_inverser`): margin, giá không hợp lệ sau `normalize_inverse_limit_prices`, IOC/FOK, symbol khác (vd BTCUSD vs BTCUSDc), freeze/stops level — một lệnh DONE một lệnh lỗi → trên tài khoản live có thể **chỉ còn 1 LIMIT**; code cố **hủy** phần còn lại (`cancel_inv_limit_pendings` khi partial fail) nhưng hủy có thể thất bại → vẫn thấy 1 lệnh.
- **Không phải lỗi đếm**: position đã khớp một phần, hoặc lệnh cũ từ snapshot trước — kiểm tra log `❌ BUY_LIMIT` / `❌ SELL_LIMIT` và `🧹 … partial fail`.
- Trước mỗi lần đặt InvGrid mới, `place_pair_from_inverse_relay` (**btc_sign_inverser** / **sign_inverse**) gọi `cancel_all_bot_limit_pendings` — hủy **mọi** BUY_LIMIT/SELL_LIMIT cùng symbol+magic, rồi mới `has_same_price_inverse_duplicate(..., check_positions=False)`: trùng **chỉ** khi còn pending LIMIT cùng mức — **không** chặn vì đã có **position** (vd SELL@4835 trong khi snapshot yêu cầu SELL_LIMIT@4835: một chân đã khớp, vẫn đặt lại cặp limit).

Copy-on-fill **MARKET** (thay cho chỉ dựa LIMIT inverse khi tắt `v5_live_inverse_limit_ipc`):
- Demo gửi TCP `{"event":"demo_fill", ...}` khi có position mới; `{"event":"demo_close", "position_ticket"}` khi position đó đã đóng trên demo (sau khi `demo_fill` gửi TCP OK). Live: MARKET copy ngược chiều; đóng position mirror khi nhận `demo_close` (comment `CopyFill_<ticket>`). SL/TP MARKET tùy chọn (`v5_market_copy_sl_tp_enabled`, mặc định tắt).
- **Đóng cuối tuần (UTC)**: `v5_weekend_flatten_enabled` — Thứ Sáu, trong khoảng **N phút** trước `v5_weekend_close_utc_hour`:`v5_weekend_close_utc_minute` (mặc định 20:59), **mỗi** process MT5 (demo **và** live — cần **bật flag trên cả hai** JSON) chạy **một lần / account / Thứ Sáu**: `v5_weekend_flatten_scope`=`bot` hoặc `account`; state `v5_weekend_flatten_<account>.json` — nếu đã `completed` cho ngày Thứ Sáu đó thì **không** chạy lại (process vẫn chạy grid bình thường); xóa file state để test lại — **sau khi flatten** process thoát (`mt5.shutdown`). Hai JSON nên cùng cửa sổ giờ UTC. Lot lệnh MARKET weekend: **`v5_weekend_flatten_volume`** trong `parameters` (nếu có và >0) thay cho `volume` root; không có thì dùng `volume` như cũ.
"""
import copy
import json
import os
import select
import socket
import subprocess
import sys
import time
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

import strategy_grid_step as base
import signal_relay
from utils import (
    cancel_all_pending_account,
    cancel_all_pending_orders_magic,
    close_all_positions_account,
    close_positions_bot,
    place_market_order,
)
from scores import (
    normalize_preferred_direction_v5,
    xauusd_grid_step_v5_is_blocked,
    xauusd_grid_step_v5_score_detailed,
)

_normalize_preferred_direction = normalize_preferred_direction_v5
_score_signal_detailed = xauusd_grid_step_v5_score_detailed


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Supervisor demo + inverse live (XAU V5) — cùng logic btc_v5 nhưng config/flag khác
V5_SUPERVISOR_DEMO_CONFIG = "config_grid_step_v5.json"
V5_SUPERVISOR_LIVE_CONFIG = "config_grid_step_inverse_live.json"
V5_SUPERVISOR_CHILD_FLAG = "--v5-child"
base.COOLDOWN_FILE = os.path.join(SCRIPT_DIR, "grid_cooldown_v5.json")
base.PAUSE_FILE = os.path.join(SCRIPT_DIR, "grid_pause_v5.json")
LIVE_LOG_FILE = os.path.join(SCRIPT_DIR, "v5_live_entry_log.jsonl")
LIVE_STATE_FILE = os.path.join(SCRIPT_DIR, "v5_live_state.json")
V5_COPY_FILL_CONSUMED_JSON = os.path.join(SCRIPT_DIR, "v5_copy_fill_consumed_ids.json")
MAX_V5_COPY_FILL_IDS = 4000
V5_PENDING_PAIR_LOG_DIR = os.path.join(SCRIPT_DIR, "log")
# Gán từ strategy_grid_step_btc_v5: module có strategy_grid_step_logic (BTC). None = strategy_grid_step mặc định.
_grid_strategy_module = None
# Gán từ strategy_grid_step_btc_v5: prefix log khi live đặt InvGrid (vd "[BTC V5 live]").
LIVE_INVERSE_LOG_PREFIX: Optional[str] = None
_v5_inv_throttle_ts: Dict[str, float] = {}


def _v5_throttle_print(key: str, msg: str, interval_sec: float = 45.0) -> None:
    now = time.monotonic()
    prev = _v5_inv_throttle_ts.get(key, 0.0)
    if now - prev < interval_sec:
        return
    _v5_inv_throttle_ts[key] = now
    print(msg)


def _v5_param_bool(params: Optional[Dict[str, Any]], key: str, default: bool = False) -> bool:
    """Đọc flag từ JSON/parameters — chấp nhận true/false, 0/1, 'true'/'yes' (khi sửa tay)."""
    if not params:
        return default
    v = params.get(key, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off", ""):
            return False
    return bool(v)


_V5_LOOP_SLEEP_MIN = 0.001  # 1 ms (hệ điều hành có thể không ngủ chính xác hơn)


def _v5_loop_sleep_seconds(params: Optional[Dict[str, Any]]) -> float:
    """
    Thời gian sleep cuối mỗi vòng main loop.
    - `loop_interval_ms` > 0: dùng mili giây (ghi đè).
    - `loop_interval_unit` = `ms`: `loop_interval_seconds` là mili giây (vd 100 → 0.1s).
    - Mặc định: `loop_interval_seconds` là giây (float), tối thiểu 1 ms.
    """
    p = params or {}
    raw_ms = p.get("loop_interval_ms")
    if raw_ms is not None and str(raw_ms).strip() != "":
        try:
            ms = float(raw_ms)
            if ms > 0:
                return max(_V5_LOOP_SLEEP_MIN, ms / 1000.0)
        except (TypeError, ValueError):
            pass
    unit = str(p.get("loop_interval_unit", "s") or "s").lower().strip()
    try:
        v = float(p.get("loop_interval_seconds", 10))
    except (TypeError, ValueError):
        v = 10.0
    if v <= 0:
        v = 10.0
    if unit in ("ms", "millisecond", "milliseconds"):
        return max(_V5_LOOP_SLEEP_MIN, v / 1000.0)
    return max(_V5_LOOP_SLEEP_MIN, v)


def _v5_loop_interval_log_repr(sleep_s: float) -> str:
    if sleep_s < 1.0:
        return f"{sleep_s * 1000.0:.0f}ms"
    s = f"{sleep_s:.4f}".rstrip("0").rstrip(".")
    return f"{s}s"


def _v5_synthetic_grid_preview_from_pair_snap(pair_snap: dict, step_val: float) -> Dict[str, Any]:
    """Từ cặp BUY_STOP/SELL_STOP trên MT5 → grid_preview cho demo_write_inverse_relay_file khi gate không có gpr."""
    bs = pair_snap.get("buy_stop_pending") or []
    ss = pair_snap.get("sell_stop_pending") or []
    if not bs or not ss:
        return {}
    try:
        buy_px = max(float(x["price_open"]) for x in bs)
        sell_px = min(float(x["price_open"]) for x in ss)
    except (TypeError, ValueError, KeyError):
        return {}
    ref = round((buy_px + sell_px) / 2.0, 8)
    return {
        "buy_price": buy_px,
        "sell_price": sell_px,
        "step": float(step_val),
        "ref": ref,
    }


def _v5_weekend_flatten_state_path(config: Dict[str, Any]) -> str:
    acct = config.get("account")
    acct_s = str(acct) if acct is not None else "unknown"
    return os.path.join(SCRIPT_DIR, f"v5_weekend_flatten_{acct_s}.json")


def _v5_weekend_flatten_load_state(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _v5_weekend_flatten_save_state(path: str, friday_key: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "friday_utc_date": friday_key,
                    "completed": True,
                    "ts_utc": datetime.now(timezone.utc).isoformat(),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except OSError as e:
        print(f"⚠️ [V5 weekend] Không ghi state {path}: {e}")


def _v5_weekend_flatten_maybe(
    config: Dict[str, Any], params: Dict[str, Any], sym: str, mag: int
) -> bool:
    """
    Thứ Sáu UTC, trong cửa sổ [close − minutes_before, close]: hủy pending + đóng position theo
    `v5_weekend_flatten_scope` (bot = chỉ symbol/magic; account = cả tài khoản), rồi market BUY/SELL
    trên `symbol` config (nếu có). Trả True nếu đã xử lý — caller thoát bot.
    """
    if not sym or not _v5_param_bool(params, "v5_weekend_flatten_enabled", False):
        return False
    now = datetime.now(timezone.utc)
    if int(now.weekday()) != 4:
        return False
    hour = int(params.get("v5_weekend_close_utc_hour", 20))
    minute = int(params.get("v5_weekend_close_utc_minute", 59))
    mb = max(1, int(params.get("v5_weekend_flatten_minutes_before", 5)))
    d = now.date()
    close_begin = datetime(d.year, d.month, d.day, hour, minute, 0, 0, tzinfo=timezone.utc)
    window_start = close_begin - timedelta(minutes=mb)
    close_end = datetime(d.year, d.month, d.day, hour, minute, 59, 999999, tzinfo=timezone.utc)
    if not (window_start <= now <= close_end):
        return False
    friday_key = d.isoformat()
    st_path = _v5_weekend_flatten_state_path(config)
    st = _v5_weekend_flatten_load_state(st_path)
    if str(st.get("friday_utc_date") or "") == friday_key and st.get("completed"):
        acct = config.get("account")
        _v5_throttle_print(
            f"wknd_done_{acct}",
            f"ℹ️ [V5 weekend] Không hủy / không market lần này — mỗi account chỉ flatten một lần mỗi Thứ Sáu "
            f"(đã ghi state {friday_key}, account={acct}). Lần đầu trong cửa sổ giờ đã chạy cancel+market+rồi thoát; "
            f"sau khi bạn mở lại bot, vòng lặp chỉ in dòng này. Xóa `{os.path.basename(st_path)}` để ép chạy lại cùng ngày.",
            120.0,
        )
        return False
    raw_wv = params.get("v5_weekend_flatten_volume")
    vol = float(config.get("volume") or 0.01)
    if raw_wv is not None and str(raw_wv).strip() != "":
        try:
            wv = float(raw_wv)
            if wv > 0:
                vol = wv
        except (TypeError, ValueError):
            pass
    direction = str(params.get("v5_weekend_flatten_direction", "SELL") or "SELL").strip().upper()
    cmt = str(params.get("v5_weekend_flatten_comment", "V5_weekend_flat") or "V5_weekend_flat")
    dev = int(params.get("v5_weekend_flatten_deviation", 30))
    sl_w = float(params.get("v5_weekend_flatten_sl", 0) or 0)
    tp_w = float(params.get("v5_weekend_flatten_tp", 0) or 0)
    ai = mt5.account_info()
    acct_s = str(ai.login) if ai else "?"
    scope = str(params.get("v5_weekend_flatten_scope", "bot") or "bot").strip().lower()
    if scope == "account":
        print(
            f"🕐 [V5 weekend] Thứ Sáu UTC {now.strftime('%H:%M')} | scope=account (mọi symbol/magic) "
            f"| market {direction} {sym} vol={vol} | account={acct_s}"
        )
        n_rm = cancel_all_pending_account()
        n_cl = close_all_positions_account()
    else:
        print(
            f"🕐 [V5 weekend] Thứ Sáu UTC {now.strftime('%H:%M')} | scope=bot ({sym} magic={mag}) "
            f"| market {direction} vol={vol} | account={acct_s}"
        )
        n_rm = cancel_all_pending_orders_magic(sym, mag)
        n_cl = close_positions_bot(sym, mag, comment=None)
    print(f"🧹 [V5 weekend] Đã hủy {n_rm} pending, đóng {n_cl} position.")
    if direction in ("BUY", "SELL"):
        is_buy = direction == "BUY"
        r = place_market_order(
            sym,
            vol,
            is_buy,
            mag,
            cmt,
            sl=sl_w,
            tp=tp_w,
            deviation=dev,
        )
        if r is None:
            print("❌ [V5 weekend] order_send market = None")
        elif int(getattr(r, "retcode", 0) or 0) != mt5.TRADE_RETCODE_DONE:
            print(f"❌ [V5 weekend] Market {direction} retcode={r.retcode} {getattr(r, 'comment', '')}")
        else:
            print(f"✅ [V5 weekend] Market {direction} OK ticket={getattr(r, 'order', 0)}")
    else:
        print(f"⏭️ [V5 weekend] v5_weekend_flatten_direction={direction!r} — bỏ qua lệnh market (chỉ đóng lệnh).")
    _v5_weekend_flatten_save_state(st_path, friday_key)
    return True


# Live blind: bỏ qua cooldown / duplicate-skip khi các gate này (không chỉ live_relay_ok).
_LIVE_BLIND_RELAX_REASONS = frozenset(
    ("live_relay_ok", "live_blind_no_relay_file", "live_no_signal_relay")
)


def _invoke_strategy_grid_step_logic(config, consecutive_errors, step):
    mod = _grid_strategy_module if _grid_strategy_module is not None else base
    if step is not None:
        return mod.strategy_grid_step_logic(config, consecutive_errors, step=step)
    return mod.strategy_grid_step_logic(config, consecutive_errors, step=None)


def _v5_apply_relay_paths_from_config(config: Dict[str, Any]) -> None:
    """
    Đồng bộ RELAY_DEMO_FILE (và history base) từ `parameters` trong JSON.
    Cần khi chạy `strategy_grid_step_v5.py` trực tiếp: mặc định signal_relay dùng v5_relay_demo.json,
    trong khi BTC V5 + live inverse cần cùng file btc_v5_relay_demo.json với wrapper strategy_grid_step_btc_v5.
    """
    params = config.get("parameters") or {}

    def _resolve(p: Any) -> Optional[str]:
        if p is None or not str(p).strip():
            return None
        s = str(p).strip()
        return s if os.path.isabs(s) else os.path.join(SCRIPT_DIR, s)

    rd = _resolve(params.get("relay_demo_file"))
    if rd:
        signal_relay.RELAY_DEMO_FILE = rd
    rh = _resolve(params.get("relay_demo_history_log_file"))
    if rh:
        signal_relay.RELAY_DEMO_HISTORY_LOG = rh
    if rd or rh:
        print(
            f"📁 [V5] relay paths từ config: demo_inverse={signal_relay.RELAY_DEMO_FILE}"
            + (f" | history_base={signal_relay.RELAY_DEMO_HISTORY_LOG}" if rh else "")
        )


def configure_grid_step_v5_paths(
    *,
    relay_signal_file=None,
    relay_state_file=None,
    relay_history_log_file=None,
    relay_demo_file=None,
    relay_demo_history_log_file=None,
    live_log_file=None,
    live_state_file=None,
):
    """
    Trỏ file relay + live entry log/state (dùng trong strategy_grid_step_btc_v5).
    Gọi ngay sau `import strategy_grid_step_v5`.
    relay_demo_history_log_file: base path (vd v5_relay_demo_history.jsonl); append thực tế vào
    v5_relay_demo_history_<SYMBOL>.jsonl theo payload.symbol.
    """
    global LIVE_LOG_FILE, LIVE_STATE_FILE
    if relay_signal_file is not None:
        signal_relay.RELAY_SIGNAL_FILE = relay_signal_file
    if relay_state_file is not None:
        signal_relay.RELAY_STATE_FILE = relay_state_file
    if relay_history_log_file is not None:
        signal_relay.RELAY_SIGNAL_HISTORY_LOG = relay_history_log_file
    if relay_demo_file is not None:
        signal_relay.RELAY_DEMO_FILE = relay_demo_file
    if relay_demo_history_log_file is not None:
        signal_relay.RELAY_DEMO_HISTORY_LOG = relay_demo_history_log_file
    if live_log_file is not None:
        LIVE_LOG_FILE = live_log_file
    if live_state_file is not None:
        LIVE_STATE_FILE = live_state_file


def _relay_zone_matches_current(config, relay_payload):
    """
    Live (không blind): zone của giá thị trường (mid bid/ask) phải khớp zone_key trong relay từ demo.
    Không tính entry/grid preview trên account live — chỉ so giá với cùng relay_zone_points như demo.
    """
    params = config.get("parameters", {})
    zp = float(params.get("relay_zone_points") or 200)
    tick = mt5.symbol_info_tick(config["symbol"])
    if tick is None:
        return False
    mid = (float(tick.bid) + float(tick.ask)) / 2.0
    want = int(relay_payload.get("zone_key") or 0)
    got = signal_relay.price_zone_key(mid, zp)
    return want == got


def _fetch_closed_positions_list(
    symbol, magic, comment_prefix="GridStep", days_back=3, max_positions=500
):
    """
    Lấy trade đã đóng (position-level) từ MT5 history.
    Sort theo close_time giảm dần; cắt max_positions (không dùng slice này cho chuỗi tín hiệu — chỉ cho state).
    """
    to_date = datetime.now()
    from_date = to_date - timedelta(days=max(1, int(days_back)))
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        deals = mt5.history_deals_get(from_date, to_date, group="*")
    if not deals:
        return []

    by_pos = {}
    for d in deals:
        if getattr(d, "magic", 0) != magic:
            continue
        if getattr(d, "symbol", "") != symbol:
            continue
        c = (getattr(d, "comment", "") or "").strip()
        if comment_prefix and not c.startswith(comment_prefix):
            continue
        pid = getattr(d, "position_id", None) or getattr(d, "position", None)
        if not pid:
            continue
        row = by_pos.setdefault(pid, {"in": None, "out": None})
        if d.entry == mt5.DEAL_ENTRY_IN:
            t = getattr(d, "time", None)
            prev = row["in"]
            if prev is None or (t is not None and t <= prev["time"]):
                row["in"] = {
                    "time": t,
                    "price": float(getattr(d, "price", 0) or 0),
                    "type": "BUY" if int(getattr(d, "type", -1)) == int(mt5.DEAL_TYPE_BUY) else "SELL",
                    "volume": float(getattr(d, "volume", 0) or 0),
                }
        elif d.entry == mt5.DEAL_ENTRY_OUT:
            t = getattr(d, "time", None)
            prev = row["out"]
            if prev is None or (t is not None and t >= prev["time"]):
                row["out"] = {
                    "time": t,
                    "price": float(getattr(d, "price", 0) or 0),
                    "profit": float(getattr(d, "profit", 0) or 0),
                    "commission": float(getattr(d, "commission", 0) or 0),
                    "swap": float(getattr(d, "swap", 0) or 0),
                }

    closed = []
    for pid, r in by_pos.items():
        if not r["in"] or not r["out"]:
            continue
        net_profit = r["out"]["profit"] + r["out"]["commission"] + r["out"]["swap"]
        closed.append(
            {
                "position_id": int(pid),
                "type": r["in"]["type"],
                "volume": r["in"]["volume"],
                "open_time": int(r["in"]["time"] or 0),
                "open_price": float(r["in"]["price"]),
                "close_time": int(r["out"]["time"] or 0),
                "close_price": float(r["out"]["price"]),
                "profit": float(r["out"]["profit"]),
                "commission": float(r["out"]["commission"]),
                "swap": float(r["out"]["swap"]),
                "net_profit": float(net_profit),
            }
        )
    closed.sort(key=lambda x: x["close_time"], reverse=True)
    cap = max(1, int(max_positions))
    return closed[:cap]


def _fetch_closed_trades(symbol, magic, history_window=20, comment_prefix="GridStep", days_back=3):
    """Tương thích cũ: chỉ lấy history_window bản ghi đầu (theo close_time)."""
    raw = _fetch_closed_positions_list(
        symbol, magic, comment_prefix=comment_prefix, days_back=days_back, max_positions=max(int(history_window), 1)
    )
    return raw[: max(1, int(history_window))]


def _calc_streak(closed):
    win_streak = 0
    loss_streak = 0
    for tr in closed:
        if tr["net_profit"] > 0:
            if loss_streak == 0:
                win_streak += 1
            else:
                break
        else:
            if win_streak == 0:
                loss_streak += 1
            else:
                break
    return win_streak, loss_streak


def _v5_gate_step_val(config):
    p = config.get("parameters", {})
    steps = p.get("steps")
    if steps is not None:
        if isinstance(steps, list) and len(steps) > 0:
            return float(steps[0])
        return float(steps)
    return float(p.get("step", 5) or 5)


def _v5_preview_grid_levels(config):
    """
    Giá BUY_STOP / SELL_STOP dự kiến (cùng công thức anchor + ref như strategy_grid_step),
    không hủy pending — chỉ đọc giá để chấm entry score.
    """
    symbol = config["symbol"]
    magic = config["magic"]
    step_val = _v5_gate_step_val(config)
    step_filter = step_val
    info = mt5.symbol_info(symbol)
    if not info:
        return None
    current_price = base.get_grid_anchor_price(symbol, magic, step_filter)
    ref = round(current_price / step_val) * step_val
    ref = round(ref, info.digits)
    buy_price = round(ref + step_val, info.digits)
    sell_price = round(ref - step_val, info.digits)
    return {
        "buy_price": buy_price,
        "sell_price": sell_price,
        "ref": ref,
        "step": step_val,
        "anchor": float(current_price),
    }


def _v5_step_filter_for_gate(config):
    """Cùng kênh step đầu với preview grid (GridStep_N hoặc None)."""
    p = config.get("parameters", {})
    steps = p.get("steps")
    if steps is not None:
        if isinstance(steps, list) and len(steps) > 0:
            return float(steps[0])
        return float(steps)
    return None


def _open_positions_as_signals(symbol, magic, step_filter):
    """Vị thế đang mở — tín hiệu đã khớp, có open_time thật."""
    positions = base.get_positions_for_step(symbol, magic, step_filter)
    out = []
    for p in positions or []:
        out.append(
            {
                "position_id": int(getattr(p, "ticket", 0) or 0),
                "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                "open_time": int(getattr(p, "time", 0) or 0),
                "open_price": float(p.price_open),
                "close_time": 0,
                "source": "open_position",
            }
        )
    return out


def _merge_signal_history(open_signals, closed_positions, signal_window):
    """
    Merge tín hiệu thật: position đang mở + lịch sử đóng (theo open_time).
    Không sort theo close_time trước; closed_positions là từ _fetch_closed_positions_list (đã sort close_time).
    """
    merged = []
    seen = set()
    for s in open_signals:
        pid = s["position_id"]
        if pid and pid not in seen:
            seen.add(pid)
            merged.append(s)
    for c in closed_positions:
        pid = int(c.get("position_id", 0) or 0)
        if pid and pid not in seen:
            seen.add(pid)
            merged.append(
                {
                    "position_id": pid,
                    "type": c["type"],
                    "open_time": int(c["open_time"]),
                    "open_price": float(c["open_price"]),
                    "close_time": int(c.get("close_time") or 0),
                    "source": "closed_history",
                }
            )
    merged.sort(key=lambda x: x["open_time"], reverse=True)
    win = max(1, int(signal_window))
    return merged[:win]


def _find_previous_signal(
    signal_history,
    current_signal_type,
    current_signal_open_price,
    price_tolerance,
    grid_step=None,
    open_same_dir_grid_step_mult=None,
):
    """
    Tín hiệu đứng trước current_entry (không lấy nhầm leg đang mở trùng chu kỳ hiện tại).

    Bỏ qua phần tử đầu khi:
    - cùng hướng và |giá - current| <= price_tolerance (trùng mức stop); hoặc
    - source=open_position, cùng hướng, và giá trong ~một bước lưới so với current stop
      (vì tolerance theo point có thể << grid_step, ví dụ XAU step=5).
    """
    if not signal_history:
        return None, 0
    cur_type = str(current_signal_type or "").upper()
    cur_px = float(current_signal_open_price)
    tol = float(price_tolerance)
    gs = float(grid_step) if grid_step is not None and float(grid_step) > 0 else None
    mult = (
        float(open_same_dir_grid_step_mult)
        if open_same_dir_grid_step_mult is not None and float(open_same_dir_grid_step_mult) > 0
        else 1.05
    )
    open_same_dir_max_dist = (max(tol, gs * mult) if gs is not None else tol)

    i = 0
    while i < len(signal_history):
        s = signal_history[i]
        st = str(s.get("type", "")).upper()
        opx = float(s.get("open_price", 0) or 0)
        src = str(s.get("source", "") or "")
        dist = abs(opx - cur_px)

        if st != cur_type:
            break

        if dist <= tol:
            i += 1
            continue

        if src == "open_position" and gs is not None and dist <= open_same_dir_max_dist:
            i += 1
            continue

        break

    prev = signal_history[i] if i < len(signal_history) else None
    return prev, i


def _compute_grid_entry_signal(preview, tick, pendings):
    """
    Tín hiệu vào lưới gần nhất (cùng logic với base: 2 stop; chọn phía gần mid).
    Thời gian: time_setup của pending (lúc grid được treo) nếu có; không thì tick.time.
    """
    bid = float(tick.bid)
    ask = float(tick.ask)
    mid = (bid + ask) / 2.0
    buy_price = float(preview["buy_price"])
    sell_price = float(preview["sell_price"])
    if abs(mid - buy_price) <= abs(mid - sell_price):
        cur_type = "BUY"
        cur_px = buy_price
    else:
        cur_type = "SELL"
        cur_px = sell_price
    ts = int(getattr(tick, "time", 0) or 0) or int(time.time())
    ts_src = "tick_time"
    if pendings:
        setups = []
        for o in pendings:
            t = int(getattr(o, "time_setup", 0) or 0)
            if t > 0:
                setups.append(t)
        if setups:
            ts = min(setups)
            ts_src = "pending_time_setup_min"
    return {
        "current_signal_type": cur_type,
        "current_signal_open_price": cur_px,
        "current_signal_open_ts": ts,
        "current_signal_ts_source": ts_src,
        "nearest_stop_rule": "min_distance_to_mid",
        "mid_price": mid,
    }


def _build_v5_features(
    closed_state,
    signal_history,
    prev_signal,
    entry_signal,
    preferred_direction,
    min_gap_minutes,
    preview,
):
    """
    State: từ closed_state (đã sort theo close_time — slice từ history_window).
    Entry: tín hiệu hiện tại từ _compute_grid_entry_signal; prev từ _find_previous_signal (bỏ trùng entry hiện tại).
    """
    c5 = closed_state[:5]
    c10 = closed_state[:10]
    if not c5:
        return {"ready": False, "reason": "not_enough_closed_trades"}

    last_closed = c5[0]
    sum5 = sum(t["net_profit"] for t in c5)
    sum10 = sum(t["net_profit"] for t in c10) if c10 else 0.0
    win5 = sum(1 for t in c5 if t["net_profit"] > 0)
    win10 = sum(1 for t in c10 if t["net_profit"] > 0) if c10 else 0
    gross_profit10 = sum(t["net_profit"] for t in c10 if t["net_profit"] > 0)
    gross_loss10 = abs(sum(t["net_profit"] for t in c10 if t["net_profit"] <= 0))
    pf10 = (gross_profit10 / gross_loss10) if gross_loss10 > 0 else float("inf")
    win_streak, loss_streak = _calc_streak(closed_state)

    last_trade_result = "Win" if last_closed["net_profit"] > 0 else "Loss"

    pref = _normalize_preferred_direction(preferred_direction)

    cur_type = str(entry_signal.get("current_signal_type") or "SELL").upper()
    cur_px = float(entry_signal["current_signal_open_price"])
    cur_ts = int(entry_signal.get("current_signal_open_ts") or 0)

    prev_sig = prev_signal
    prev_type = prev_sig["type"] if prev_sig else None
    prev_open = float(prev_sig["open_price"]) if prev_sig else cur_px
    prev_open_ts = int(prev_sig["open_time"]) if prev_sig else 0
    prev_src = prev_sig.get("source") if prev_sig else None

    same_dir = bool(prev_type and cur_type == prev_type)
    reverse_dir = bool(prev_type and cur_type != prev_type)
    gap_min = (float(cur_ts) - float(prev_open_ts)) / 60.0 if prev_sig and prev_open_ts else 999.0
    min_gap_ok = gap_min >= float(min_gap_minutes)

    prev_close_ts = int(prev_sig.get("close_time") or 0) if prev_sig else 0
    if prev_sig and prev_open_ts:
        if prev_close_ts > 0:
            prev_duration_min = max(0.0, (float(prev_close_ts) - float(prev_open_ts)) / 60.0)
            gap_from_prev_close_min = max(0.0, (float(cur_ts) - float(prev_close_ts)) / 60.0)
        else:
            prev_duration_min = max(0.0, (float(cur_ts) - float(prev_open_ts)) / 60.0)
            gap_from_prev_close_min = None
    else:
        prev_duration_min = None
        gap_from_prev_close_min = None

    cur_below_prev = cur_px < prev_open
    cur_above_prev = cur_px > prev_open

    return {
        "ready": True,
        "min_gap_minutes": float(min_gap_minutes),
        "last_trade_result": last_trade_result,
        "sum_last_5_net_profit": sum5,
        "avg_last_5_net_profit": (sum5 / len(c5)),
        "win_count_last_5": win5,
        "loss_count_last_5": len(c5) - win5,
        "sum_last_10_net_profit": sum10,
        "avg_last_10_net_profit": (sum10 / len(c10)) if c10 else 0.0,
        "win_rate_last_10": (win10 / len(c10)) if c10 else 0.0,
        "profit_factor_last_10": pf10,
        "win_streak": win_streak,
        "loss_streak": loss_streak,
        "signal_type": cur_type,
        "preferred_direction": pref,
        "current_signal_type": cur_type,
        "current_signal_open_price": cur_px,
        "current_signal_open_ts": cur_ts,
        "current_signal_ts_source": entry_signal.get("current_signal_ts_source"),
        "prev_signal_type": prev_type,
        "prev_signal_open_price": prev_open,
        "prev_signal_open_ts": prev_open_ts,
        "prev_signal_source": prev_src,
        "signal_history_len": len(signal_history),
        "same_direction_as_prev_signal": same_dir,
        "reverse_direction_from_prev_signal": reverse_dir,
        "gap_minutes_from_prev_signal": gap_min,
        "gap_from_prev_signal_min": gap_min,
        "prev_duration_min": prev_duration_min,
        "gap_from_prev_close_min": gap_from_prev_close_min,
        "min_gap_ok": min_gap_ok,
        "current_open_below_prev_open": cur_below_prev,
        "current_open_above_prev_open": cur_above_prev,
        "grid_preview": preview,
        "entry_signal_meta": {
            "nearest_stop_rule": entry_signal.get("nearest_stop_rule"),
            "mid_price": entry_signal.get("mid_price"),
        },
    }


def _score_signal(features):
    s, _ = _score_signal_detailed(features)
    return s


def _is_blocked(features, max_loss_streak=2, hard_block_sum10_negative=True, hard_block_min_gap=True):
    return xauusd_grid_step_v5_is_blocked(
        features,
        max_loss_streak=max_loss_streak,
        hard_block_sum10_negative=hard_block_sum10_negative,
        hard_block_min_gap=hard_block_min_gap,
    )


def _closed_list_signature(closed):
    """Chữ ký lịch sử đóng: đổi khi có lệnh đóng mới (hoặc số bản ghi đổi)."""
    if not closed:
        return (0, 0, 0)
    top = closed[0]
    return (
        int(top.get("close_time", 0) or 0),
        int(top.get("position_id", 0) or 0),
        len(closed),
    )


def _v5_gate_cache_key(config, v5_role):
    return (
        str(v5_role),
        str(config.get("symbol") or ""),
        int(config.get("magic") or 0),
        int(config.get("account") or 0),
    )


def _v5_peek_any_out_deal_after(symbol, magic, comment_prefix, since_ts: int) -> bool:
    """
    True nếu có deal OUT (đóng) sau since_ts — cần build lại full closed list.
    Chỉ quét cửa sổ thời gian ngắn sau mốc since_ts (nhẹ hơn build toàn bộ by_pos).
    """
    if since_ts <= 0:
        return True
    try:
        from_dt = datetime.utcfromtimestamp(max(0, since_ts - 5))
        to_dt = datetime.now()
        deals = mt5.history_deals_get(from_dt, to_dt)
        if deals is None:
            deals = mt5.history_deals_get(from_dt, to_dt, group="*")
        for d in deals or []:
            if getattr(d, "magic", 0) != magic:
                continue
            if getattr(d, "symbol", "") != symbol:
                continue
            c = (getattr(d, "comment", "") or "").strip()
            if comment_prefix and not c.startswith(comment_prefix):
                continue
            if int(getattr(d, "entry", -1)) != int(mt5.DEAL_ENTRY_OUT):
                continue
            t = int(getattr(d, "time", 0) or 0)
            if t > since_ts:
                return True
    except Exception:
        return True
    return False


def _v5_try_return_cached_gate_without_full_fetch(
    config, v5_role, symbol, magic, history_comment_prefix
):
    """
    Khi đã có cache score và peek không thấy deal OUT mới → trả cache, không gọi _fetch_closed_positions_list.
    """
    params = config.get("parameters", {})
    if not bool(params.get("v5_rescore_only_on_new_close", False)):
        return None
    ck = _v5_gate_cache_key(config, v5_role)
    c = getattr(run, "_v5_gate_score_cache", None)
    if not isinstance(c, dict) or c.get("key") != ck:
        return None
    lc_ts = int(c.get("last_close_ts") or 0)
    if lc_ts <= 0:
        return None
    if _v5_peek_any_out_deal_after(symbol, magic, history_comment_prefix, lc_ts):
        return None
    _v5_log_gate_no_new_close_throttled(config)
    feat = copy.deepcopy(c["features"])
    feat["v5_score_reused_no_new_close"] = True
    feat["v5_gate_history_skip"] = "peek_no_new_out_deal"
    return c["allow"], c["gate_reason"], feat


def _v5_log_gate_no_new_close_throttled(config: Dict[str, Any]) -> None:
    """
    Khi `v5_rescore_only_on_new_close`: tái dùng score, không fetch full history — log nhắc ngắn.
    Dòng này **không** in mỗi vòng: khoảng tối thiểu giữa hai lần in = `parameters.v5_gate_no_new_close_log_seconds`
    (mặc định 30, clamp 1–3600), khác khoảng sleep cuối vòng (`loop_interval_seconds` / `loop_interval_ms` / `loop_interval_unit`).
    """
    params = (config or {}).get("parameters") or {}
    try:
        gap = float(params.get("v5_gate_no_new_close_log_seconds", 30.0))
    except (TypeError, ValueError):
        gap = 30.0
    gap = max(1.0, min(gap, 3600.0))
    msg = "📚 [V5 Gate] chưa có lệnh đóng mới"
    now_m = time.monotonic()
    prev = getattr(run, "_v5_gate_no_close_log", None)
    if prev is not None and prev[0] == msg and (now_m - prev[1]) < gap:
        return
    print(f"{msg} (nhắc log tối đa 1 lần/{gap:.0f}s, không phải chu kỳ vòng lặp)")
    run._v5_gate_no_close_log = (msg, now_m)


def _v5_live_gate_features_no_relay():
    """Live đang có grid: không chấm điểm từ account; chỉ để base strategy quản lý lệnh."""
    return {
        "ready": True,
        "score": None,
        "score_breakdown": {"add": [], "sub": [], "note": "relay_only_live_has_grid"},
        "blocked": False,
        "block_reason": None,
        "min_gap_ok": True,
        "current_signal_type": None,
        "signal_type": None,
        "current_signal_open_price": None,
        "grid_preview": {},
        "relay_id": None,
    }


def _v5_history_score_gate(config):
    """
    Chỉ dùng cho v5_role=demo: đọc history session hiện tại, tính score/log, không chặn lệnh (demo_mode_no_gate).
    Live không gọi hàm này — live chỉ nhận tín hiệu qua relay.
    """
    params = config.get("parameters", {})
    v5_role = str(params.get("v5_role", "demo")).lower().strip()
    if v5_role != "demo":
        return False, "only_demo_uses_history_gate", {}
    history_window = int(params.get("history_window", 20))
    signal_history_window = int(params.get("signal_history_window", history_window))
    history_days_back = int(params.get("history_days_back", 7))
    max_closed_fetch = max(
        int(params.get("max_closed_fetch", 500)),
        history_window,
        signal_history_window,
        5,
    )
    min_gap_minutes = float(params.get("min_gap_minutes", 5))
    max_loss_streak = int(params.get("max_loss_streak", 2))
    preferred_direction = _normalize_preferred_direction(params.get("preferred_direction", "SELL"))
    history_comment_prefix = str(params.get("history_comment_prefix", "") or "").strip() or None
    symbol = config["symbol"]
    magic = config["magic"]

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False, "tick_none", {}

    gate_history_source_line = None
    _r = _v5_try_return_cached_gate_without_full_fetch(
        config, v5_role, symbol, magic, history_comment_prefix
    )
    if _r is not None:
        return _r
    closed = _fetch_closed_positions_list(
        symbol,
        magic,
        comment_prefix=history_comment_prefix,
        days_back=history_days_back,
        max_positions=max_closed_fetch,
    )
    gate_history_source_line = (
        f"📚 [V5 Gate] history source=current account={config.get('account')} "
        f"symbol={symbol} magic={magic} window={history_window} days_back={history_days_back}"
    )
    if len(closed) < 5:
        if gate_history_source_line:
            print(gate_history_source_line)
        try:
            last_closed_time = None
            if closed:
                ts = int(closed[0].get("close_time", 0) or 0)
                if ts > 0:
                    last_closed_time = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            print(
                f"📚 [V5 Gate] history loaded: closed_count={len(closed)} "
                f"(need>=5, window={history_window}) last_closed={last_closed_time}"
            )
        except Exception:
            pass
        # Phải có grid_preview (buy/sell stop dự kiến) — không thì demo không ghi được btc_v5_relay_demo.json
        # khi vừa đặt lệnh (live inverse-only đọc file rỗng mãi).
        preview_early = _v5_preview_grid_levels(config)
        if preview_early is None:
            return False, "preview_grid_failed", {"closed_count": len(closed), "role": v5_role}
        feat_insuff = {
            "closed_count": len(closed),
            "role": v5_role,
            "ready": True,
            "grid_preview": preview_early,
            "score": None,
            "blocked": False,
            "block_reason": None,
            "score_breakdown": {
                "decision": "REJECT",
                "add": [],
                "sub": [],
                "note": "insufficient_history",
            },
        }
        return True, f"demo_insufficient_history:{len(closed)}", feat_insuff

    sig = _closed_list_signature(closed)
    cache_key = _v5_gate_cache_key(config, v5_role)
    rescore_only = bool(params.get("v5_rescore_only_on_new_close", False))

    def _cache_put(allow, gate_reason, features, closed_for_ts=None):
        if not rescore_only:
            return
        ts = 0
        if closed_for_ts and len(closed_for_ts) > 0:
            ts = int(closed_for_ts[0].get("close_time", 0) or 0)
        try:
            run._v5_gate_score_cache = {
                "key": cache_key,
                "sig": sig,
                "allow": allow,
                "gate_reason": gate_reason,
                "features": copy.deepcopy(features),
                "last_close_ts": ts,
            }
        except Exception:
            pass

    if rescore_only:
        c = getattr(run, "_v5_gate_score_cache", None)
        if isinstance(c, dict) and c.get("key") == cache_key and c.get("sig") == sig:
            _v5_log_gate_no_new_close_throttled()
            try:
                if (not c.get("last_close_ts")) and closed and closed[0].get("close_time"):
                    c2 = dict(c)
                    c2["last_close_ts"] = int(closed[0]["close_time"])
                    run._v5_gate_score_cache = c2
            except Exception:
                pass
            feat = copy.deepcopy(c["features"])
            feat["v5_score_reused_no_new_close"] = True
            return c["allow"], c["gate_reason"], feat

    if gate_history_source_line:
        print(gate_history_source_line)
    try:
        last_closed_time = None
        if closed:
            ts = int(closed[0].get("close_time", 0) or 0)
            if ts > 0:
                last_closed_time = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"📚 [V5 Gate] history loaded: closed_count={len(closed)} "
            f"(need>=5, window={history_window}) last_closed={last_closed_time}"
        )
    except Exception:
        pass

    closed_state = closed[: max(1, history_window)]

    step_filter = _v5_step_filter_for_gate(config)
    signal_closed_for_merge = closed

    open_sigs = _open_positions_as_signals(symbol, magic, step_filter)
    signal_history = _merge_signal_history(open_sigs, signal_closed_for_merge, signal_history_window)

    preview = _v5_preview_grid_levels(config)
    if preview is None:
        return False, "preview_grid_failed", {"closed_count": len(closed), "role": v5_role}

    pendings = base.get_pending_orders(symbol, magic, step_filter)
    entry_signal = _compute_grid_entry_signal(preview, tick, pendings)

    info = mt5.symbol_info(symbol)
    point = float(getattr(info, "point", 0.01) or 0.01) if info else 0.01
    digits = int(getattr(info, "digits", 5) or 5) if info else 5
    tol_cfg = params.get("prev_signal_price_tolerance")
    if tol_cfg is not None and float(tol_cfg) > 0:
        price_tol = float(tol_cfg)
    else:
        price_tol = max(2.0 * point, 10 ** (-digits) * 0.5)

    grid_step = preview.get("step")
    open_mult = params.get("prev_signal_open_same_dir_grid_step_mult")

    prev_signal, prev_leading_skipped = _find_previous_signal(
        signal_history,
        entry_signal["current_signal_type"],
        entry_signal["current_signal_open_price"],
        price_tol,
        grid_step=grid_step,
        open_same_dir_grid_step_mult=open_mult,
    )

    features = _build_v5_features(
        closed_state,
        signal_history,
        prev_signal,
        entry_signal,
        preferred_direction,
        min_gap_minutes,
        preview,
    )
    features["state_history_source"] = "current_account"
    features["signal_closed_merge_source"] = "same_as_state_fetch"
    features["signal_history_window"] = signal_history_window
    features["prev_signal_price_tolerance"] = price_tol
    features["prev_signal_leading_overlap_skipped"] = prev_leading_skipped
    _om = float(open_mult) if open_mult is not None and float(open_mult) > 0 else 1.05
    features["prev_signal_open_same_dir_max_dist"] = (
        max(price_tol, float(grid_step) * _om) if grid_step is not None and float(grid_step) > 0 else None
    )
    if not features.get("ready"):
        return False, str(features.get("reason", "feature_not_ready")), features

    hard_block_sum10 = bool(params.get("v5_hard_block_sum10_negative", True))
    hard_block_min_gap = bool(params.get("v5_hard_block_min_gap", True))
    blocked, block_reason = _is_blocked(
        features,
        max_loss_streak=max_loss_streak,
        hard_block_sum10_negative=hard_block_sum10,
        hard_block_min_gap=hard_block_min_gap,
    )
    score, score_breakdown = _score_signal_detailed(features)
    features["score"] = score
    features["score_breakdown"] = score_breakdown
    features["blocked"] = blocked
    features["block_reason"] = block_reason

    # Demo: luôn cho chạy bot gốc, nhưng vẫn trả đủ feature/score để log quan sát.
    _cache_put(True, "demo_mode_no_gate", features, closed_for_ts=closed)
    return True, "demo_mode_no_gate", features


def _v5_features_qualify_live_equivalent(features: dict, params: dict) -> bool:
    """
    Tiêu chí “đủ điểm như cổng live” để demo phát relay sớm: ready, không blocked,
    medium + entry score, preferred direction (nếu cấu hình).
    Dùng trên demo để phát relay ngay khi đủ điểm (không chờ MT5 đặt lệnh).
    """
    if not features or not features.get("ready"):
        return False
    if features.get("blocked"):
        return False
    try:
        sc = int(features.get("score")) if features.get("score") is not None else None
    except (TypeError, ValueError):
        sc = None
    if sc is None:
        return False
    medium_thr = int(params.get("medium_score_threshold", 5))
    entry_thr = int(params.get("entry_score_threshold", 6))
    if sc < medium_thr:
        return False
    if sc < entry_thr:
        return False
    allow_reverse = bool(params.get("allow_reverse_entry", True))
    preferred = str(params.get("preferred_direction", "BOTH") or "BOTH").upper()
    cur_sig = str(features.get("current_signal_type") or features.get("signal_type") or "").upper()
    if not allow_reverse and preferred in ("BUY", "SELL") and cur_sig != preferred:
        return False
    return True


def _append_live_entry_log(record):
    try:
        with open(LIVE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except IOError:
        pass


def _snapshot_bot_orders_positions(symbol, magic):
    orders = mt5.orders_get(symbol=symbol) or []
    orders = [o for o in orders if getattr(o, "magic", 0) == magic]
    positions = mt5.positions_get(symbol=symbol) or []
    positions = [p for p in positions if getattr(p, "magic", 0) == magic]
    pending_tickets = sorted(int(getattr(o, "ticket", 0) or 0) for o in orders)
    position_tickets = sorted(int(getattr(p, "ticket", 0) or 0) for p in positions)
    return pending_tickets, position_tickets


def _collect_pending_stop_pair(symbol: str, magic: int) -> Optional[dict]:
    """
    Cặp lưới: ít nhất một BUY_STOP và một SELL_STOP pending cùng symbol/magic.
    Trả về dict chi tiết hoặc None nếu không đủ cặp.
    """
    orders = mt5.orders_get(symbol=symbol) or []
    buy_stops: list = []
    sell_stops: list = []
    ot_buy = getattr(mt5, "ORDER_TYPE_BUY_STOP", 4)
    ot_sell = getattr(mt5, "ORDER_TYPE_SELL_STOP", 5)
    for o in orders:
        if int(getattr(o, "magic", 0) or 0) != int(magic):
            continue
        ot = int(getattr(o, "type", -1))
        ticket = int(getattr(o, "ticket", 0) or 0)
        price_open = float(getattr(o, "price_open", 0) or 0)
        vol = float(
            getattr(o, "volume_initial", 0)
            or getattr(o, "volume_current", 0)
            or 0
        )
        cmt = str(getattr(o, "comment", "") or "")
        row = {
            "ticket": ticket,
            "price_open": price_open,
            "volume": vol,
            "comment": cmt,
        }
        if ot == ot_buy:
            buy_stops.append(row)
        elif ot == ot_sell:
            sell_stops.append(row)
    if not buy_stops or not sell_stops:
        return None
    return {
        "symbol": symbol,
        "magic": magic,
        "buy_stop_pending": buy_stops,
        "sell_stop_pending": sell_stops,
    }


def _append_pending_stop_pair_daily_log(record: dict) -> None:
    """Một dòng JSON / ngày — tên file theo ngày local."""
    try:
        os.makedirs(V5_PENDING_PAIR_LOG_DIR, exist_ok=True)
    except OSError:
        return
    day = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(V5_PENDING_PAIR_LOG_DIR, f"pending_stop_pair_{day}.jsonl")
    line = dict(record)
    line["_logged_ts"] = time.time()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except IOError:
        pass


def _v5_append_pending_stop_failure_log(line: dict) -> None:
    """Ghi cùng file pending_stop_pair_*.jsonl khi base.strategy_grid_step_logic đặt BUY_STOP/SELL_STOP lỗi."""
    ctx = line.pop("log_context", None) or {}
    if not bool(ctx.get("enabled", True)):
        return
    rec = dict(line)
    if ctx.get("v5_role") is not None:
        rec["v5_role"] = ctx.get("v5_role")
    if "grid_preview" in ctx:
        rec["grid_preview"] = ctx.get("grid_preview")
    _append_pending_stop_pair_daily_log(rec)


base.log_pending_stop_attempt = _v5_append_pending_stop_failure_log


def _live_has_equivalent_order(symbol, magic, step_filter, signal_type, entry_price, price_threshold):
    """
    Live đã có lệnh/position tương ứng tín hiệu: cùng symbol/magic (đã lọc), cùng chiều,
    giá vào gần entry_price trong price_threshold.
    """
    st = str(signal_type or "").upper()
    if st not in ("BUY", "SELL"):
        return False
    try:
        ep = float(entry_price)
    except (TypeError, ValueError):
        return False
    thr = float(price_threshold)

    for p in base.get_positions_for_step(symbol, magic, step_filter) or []:
        ptype = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
        if ptype == st and abs(float(p.price_open) - ep) <= thr:
            return True

    for o in base.get_pending_orders(symbol, magic, step_filter) or []:
        ot = int(getattr(o, "type", -1))
        opr = float(getattr(o, "price_open", 0) or 0)
        if st == "BUY" and ot == mt5.ORDER_TYPE_BUY_STOP and abs(opr - ep) <= thr:
            return True
        if st == "SELL" and ot == mt5.ORDER_TYPE_SELL_STOP and abs(opr - ep) <= thr:
            return True
    return False


def _load_live_state():
    if not os.path.exists(LIVE_STATE_FILE):
        return {}
    try:
        with open(LIVE_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_live_state(state):
    try:
        with open(LIVE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except IOError:
        pass


def _live_entry_cooldown_remaining_seconds(symbol, magic, min_gap_seconds):
    if min_gap_seconds <= 0:
        return 0
    state = _load_live_state()
    key = f"{symbol}:{magic}"
    ts = state.get(key, {}).get("last_entry_ts_utc")
    if not ts:
        return 0
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        remain = int(min_gap_seconds - (now - dt).total_seconds())
        return max(0, remain)
    except (ValueError, TypeError):
        return 0


def _mark_live_entry_now(symbol, magic):
    state = _load_live_state()
    key = f"{symbol}:{magic}"
    state[key] = {
        "last_entry_ts_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    _save_live_state(state)


def _v5_signal_relation(gf):
    """REVERSAL | CONTINUATION | FIRST_SIGNAL"""
    if not gf or not gf.get("ready"):
        return "FIRST_SIGNAL"
    pt = gf.get("prev_signal_type")
    ct = gf.get("current_signal_type") or gf.get("signal_type")
    if not pt or not ct:
        return "FIRST_SIGNAL"
    if str(pt).upper() == str(ct).upper():
        return "CONTINUATION"
    return "REVERSAL"


def _v5_score_decision_label(gf, entry_thr):
    sb = gf.get("score_breakdown") if isinstance(gf.get("score_breakdown"), dict) else {}
    d = sb.get("decision")
    if d in ("EXECUTE", "NEUTRAL", "PROBE", "REJECT"):
        return d
    try:
        sc = int(gf.get("score")) if gf.get("score") is not None else 0
    except (TypeError, ValueError):
        sc = 0
    if sc >= int(entry_thr):
        return "EXECUTE"
    if sc == 3:
        return "NEUTRAL"
    if 1 <= sc <= 2:
        return "PROBE"
    return "REJECT"


def _v5_live_entry_gate_label(score, entry_thr):
    """Chỉ theo điểm vs entry_threshold: QUALIFIED | REJECT (chưa tính hard_block)."""
    try:
        s = int(score) if score is not None else 0
    except (TypeError, ValueError):
        return "?"
    return "QUALIFIED" if s >= int(entry_thr) else "REJECT"


def _v5_effective_live_gate_label(score, entry_thr, blocked):
    """Cổng thực tế cho log: đủ điểm nhưng hard_block → BLOCKED (tránh QUALIFIED + kết_luận không đạt)."""
    if blocked:
        return "BLOCKED"
    return _v5_live_entry_gate_label(score, entry_thr)


def _v5_gate_main_reason_code(gate_reason):
    """Map gate_reason -> MAIN_REASON mã ngắn."""
    gr = str(gate_reason or "")
    if not gr:
        return "UNKNOWN"
    if gr.startswith("blocked:"):
        br = gr.replace("blocked:", "", 1)
        if "loss_streak" in br:
            return "HARD_BLOCK_LOSS_STREAK"
        if "sum_last_10" in br or "deep_negative" in gr:
            return "HARD_BLOCK_SUM10_DEEP_NEGATIVE"
        if "sum_last_5" in br:
            return "HARD_BLOCK_SUM5"
        if "gap" in br:
            return "HARD_BLOCK_MIN_GAP"
        return "HARD_BLOCK"
    if "below_entry_score" in gr or "low_score" in gr:
        return "SCORE_REJECT"
    if gr in ("tick_none", "preview_grid_failed", "feature_not_ready"):
        return "NO_SIGNAL"
    if "need>=" in gr or "closed_trades" in gr:
        return "INSUFFICIENT_HISTORY"
    if gr.startswith("live_maintenance"):
        return "LIVE_MAINTENANCE"
    if gr == "live_relay_ok":
        return "RELAY_OK"
    if "direction_gate" in gr:
        return "DIRECTION_GATE"
    return "GATE_" + gr[:24].replace(" ", "_")


def _v5_grid_action_reason(pre_np, pre_npos, new_p, new_pos, mx, v5_role=None):
    """action, reason_code cho [GRID] khi không có lệnh mới."""
    mx = int(mx or 5)
    if pre_np >= 2 and not new_p:
        # Demo: không dùng mã GRID_FULL_2_PENDING (dễ nhầm với “không đủ điều kiện” score); live giữ mã cũ.
        if str(v5_role or "").lower().strip() == "demo":
            return "NO_NEW_ORDER", "DEMO_SCORE_OK_NO_FILL"
        return "NO_NEW_ORDER", "GRID_FULL_2_PENDING"
    if pre_npos >= mx and not new_pos:
        return "NO_NEW_ORDER", "MAX_POSITIONS_REACHED"
    if new_p or new_pos:
        return "PLACE_ORDER", "NEW_TICKETS"
    return "NO_NEW_ORDER", "GRID_NO_CHANGE"


def _v5_compute_result_main(ctx):
    """(RESULT, MAIN_REASON) cho [V5] dòng đầu."""
    exit_kind = ctx.get("exit_kind") or "normal"
    gate_reason = str(ctx.get("gate_reason") or "")
    if exit_kind == "no_relay_flat":
        return "SKIP", "NO_RELAY"
    if exit_kind == "relay_zone_mismatch":
        return "SKIP", "RELAY_ZONE_MISMATCH"
    if exit_kind == "gate_blocked":
        return "BLOCKED", _v5_gate_main_reason_code(gate_reason)
    if exit_kind == "live_cooldown":
        return "SKIP", "LIVE_COOLDOWN"
    if exit_kind == "dup_skip":
        return "SKIP", "DUPLICATE_PENDING"
    if ctx.get("new_pending") or ctx.get("new_positions"):
        return "NEW_ORDER", "ORDER_PLACED"
    g_act, g_reason = _v5_grid_action_reason(
        ctx.get("pre_np", 0),
        ctx.get("pre_npos", 0),
        ctx.get("new_pending") or [],
        ctx.get("new_positions") or [],
        ctx.get("max_positions", 5),
        ctx.get("v5_role"),
    )
    if g_act == "PLACE_ORDER":
        return "NEW_ORDER", "ORDER_PLACED"
    return "NO_ORDER", g_reason


def _v5_gate_pass_for_log(ctx) -> bool:
    """Cổng tín hiệu (điểm + không hard_block) — dùng để ghi chú log, độc lập với có đặt lệnh hay không."""
    gf = ctx.get("gate_features") or {}
    entry_thr = int(ctx.get("entry_thr") or 6)
    return _v5_ket_luan_dat(gf, entry_thr)


def _v5_ket_luan_dat(gate_features: dict, entry_thr: int) -> bool:
    """
    Khớp kết_luận=đạt trên log demo (_v5_emit_minimal_cycle_log):
    score >= entry_score_threshold và không hard_block.
    Dùng để ghi v5_relay_signal.json khi relay bật.
    """
    if not gate_features:
        return False
    if bool(gate_features.get("blocked")):
        return False
    sc = gate_features.get("score")
    try:
        si = int(sc) if sc is not None else None
    except (TypeError, ValueError):
        return False
    return si is not None and si >= int(entry_thr)


def _v5_param_log_debug(params):
    """True = full block [SIGNAL][SCORE]...; False (default) = một dòng điểm + kết luận. Alias JSON: logDebug."""
    return bool(params.get("v5_log_debug", params.get("logDebug", False)))


def _v5_emit_minimal_cycle_log(ctx, params):
    """
    Chế độ ngắn: điểm, plus/minus rules, live_gate, kết luận đạt/không đạt, RESULT.
    kết_luận=đạt khi score>=entry_threshold và không hard_block (điểm cao vẫn có thể bị block, vd min_gap).
    """
    if not bool(params.get("v5_structured_log", True)):
        return
    gf = ctx.get("gate_features") or {}
    sb = gf.get("score_breakdown") if isinstance(gf.get("score_breakdown"), dict) else {}
    adds = sb.get("add") or []
    subs = sb.get("sub") or []
    entry_thr = int(ctx.get("entry_thr") or 6)
    sc = gf.get("score")
    result, main = _v5_compute_result_main(ctx)
    blocked = bool(gf.get("blocked"))
    lg = _v5_effective_live_gate_label(sc, entry_thr, blocked)
    prof = sb.get("decision") if sb.get("decision") else _v5_score_decision_label(gf, entry_thr)
    plus_s = ",".join(str(x) for x in adds) if adds else "-"
    minus_s = ",".join(str(x) for x in subs) if subs else "-"
    try:
        si = int(sc) if sc is not None else None
    except (TypeError, ValueError):
        si = None
    ok = si is not None and si >= entry_thr and not blocked
    concl = "đạt" if ok else "không đạt"
    blk = ""
    if blocked:
        blk = f" | block={gf.get('block_reason') or 'yes'}"
    print(
        f"[V5] score={sc} | profile={prof} | +[{plus_s}] | -[{minus_s}] | "
        f"live_gate={lg}{blk} | kết_luận={concl} | RESULT={result} | {main}"
    )
    print("")


def _v5_emit_structured_cycle_log(ctx, params):
    """
    Log một vòng: RESULT / MAIN_REASON + [SIGNAL][SCORE][CONTEXT][BLOCK][GRID][RELAY][LIVE_CHECK].
    ctx: dict từ run loop (exit_kind, gate_*, grid_*, relay_*, ...).
    """
    if not bool(params.get("v5_structured_log", True)):
        return
    compact = bool(params.get("v5_compact_cycle_log", False))
    gf = ctx.get("gate_features") or {}
    sb = gf.get("score_breakdown") if isinstance(gf.get("score_breakdown"), dict) else {}
    adds = sb.get("add") or []
    subs = sb.get("sub") or []
    entry_thr = int(ctx.get("entry_thr") or 6)
    sc = gf.get("score")
    v5_role = str(ctx.get("v5_role") or "demo")

    result, main = _v5_compute_result_main(ctx)
    g_act, g_reason = _v5_grid_action_reason(
        ctx.get("pre_np", 0),
        ctx.get("pre_npos", 0),
        ctx.get("new_pending") or [],
        ctx.get("new_positions") or [],
        ctx.get("max_positions", 5),
        ctx.get("v5_role"),
    )

    if compact:
        rel = _v5_signal_relation(gf)
        side = gf.get("current_signal_type") or gf.get("signal_type") or "-"
        ep = gf.get("current_signal_open_price")
        ps = f"{gf.get('prev_signal_type')} {gf.get('prev_signal_open_price')}"
        minus_rules = ",".join(subs) if subs else "none"
        print(f"[V5] RESULT={result} | MAIN_REASON={main}")
        print(f"[SIGNAL] {side} {ep} | prev={ps} | relation={rel}")
        lg = _v5_effective_live_gate_label(sc, entry_thr, bool(gf.get("blocked")))
        prof = sb.get("decision") if sb.get("decision") else _v5_score_decision_label(gf, entry_thr)
        print(
            f"[SCORE] score={sc} | profile={prof} | live_entry_gate={lg} | minus={minus_rules}"
        )
        print(f"[BLOCK] hard_block={gf.get('blocked')} | reason={gf.get('block_reason') or '-'}")
        print(
            f"[GRID] positions={ctx.get('pre_npos')} | pendings={ctx.get('pre_np')} | "
            f"action={g_act} | reason={g_reason}"
        )
        ren = ctx.get("relay_enabled", False)
        rs = ctx.get("relay_sent", False)
        rr = ctx.get("relay_reason") or "-"
        print(f"[RELAY] sent={rs} | reason={rr}" if ren else "[RELAY] enabled=False")
        return

    print(f"[V5] RESULT={result} | MAIN_REASON={main}")
    print("[SIGNAL]")
    print(f"- side={gf.get('current_signal_type') or gf.get('signal_type') or '-'}")
    print(f"- entry={gf.get('current_signal_open_price')}")
    print(f"- prev_side={gf.get('prev_signal_type')}")
    print(f"- prev_open={gf.get('prev_signal_open_price')}")
    print(f"- relation={_v5_signal_relation(gf)}")
    print(f"- preferred={gf.get('preferred_direction')}")

    print("[SCORE]")
    print(f"- score={sc}")
    print(f"- profile={sb.get('decision') or _v5_score_decision_label(gf, entry_thr)}")
    print(f"- live_entry_gate={_v5_effective_live_gate_label(sc, entry_thr, bool(gf.get('blocked')))}")
    print(f"- add={len(adds)}")
    print(f"- sub={len(subs)}")
    plus_rules = ", ".join(adds) if adds else "none"
    minus_rules = ", ".join(subs) if subs else "none"
    print(f"- plus_rules={plus_rules}")
    print(f"- minus_rules={minus_rules}")

    print("[CONTEXT]")
    gsm = gf.get("gap_from_prev_signal_min")
    if gsm is None:
        gsm = gf.get("gap_minutes_from_prev_signal")
    print(f"- gap_signal_min={gsm}")
    gc = gf.get("gap_from_prev_close_min")
    print(f"- gap_from_prev_close_min={gc if gc is not None else '-'}")
    pd = gf.get("prev_duration_min")
    print(f"- prev_duration_min={pd if pd is not None else '-'}")
    print(f"- ts_src={gf.get('current_signal_ts_source')}")

    print("[BLOCK]")
    print(f"- hard_block={gf.get('blocked')}")
    print(f"- block_reason={gf.get('block_reason') or '-'}")
    print(f"- min_gap_ok={gf.get('min_gap_ok')}")
    print(f"- loss_streak={gf.get('loss_streak')}")
    print(f"- last_closed={gf.get('last_trade_result')}")
    print(f"- sum5={gf.get('sum_last_5_net_profit')}")
    print(f"- sum10={gf.get('sum_last_10_net_profit')}")

    print("[GRID]")
    print(f"- positions={ctx.get('pre_npos')}")
    print(f"- pendings={ctx.get('pre_np')}")
    print(f"- action={g_act}")
    print(f"- reason={g_reason}")

    ren = bool(ctx.get("relay_enabled", False))
    print("[RELAY]")
    print(f"- enabled={ren}")
    if ren:
        print(f"- sent={bool(ctx.get('relay_sent'))}")
        if ctx.get("relay_zone") is not None:
            print(f"- zone={ctx.get('relay_zone')}")
        if ctx.get("relay_side"):
            print(f"- side={ctx.get('relay_side')}")
        print(f"- reason={ctx.get('relay_reason') or '-'}")
    else:
        print("- reason=RELAY_DISABLED")

    if v5_role != "live":
        blk_demo = bool(gf.get("blocked"))
        try:
            s_int = int(sc) if sc is not None else 0
        except (TypeError, ValueError):
            s_int = None
        if blk_demo:
            eq = "BLOCKED"
        elif s_int is None:
            eq = "?"
        else:
            eq = "QUALIFIED" if s_int >= entry_thr else "REJECT"
        print("[LIVE_CHECK]")
        print(f"- equivalent={eq}")
        print(f"- entry_threshold={entry_thr}")
        print(f"- score={sc}")
        if eq == "REJECT":
            print("- note=score < entry_threshold; profile=PROBE chỉ là bucket 1–2 điểm (scores.py), không phải đủ cổng live")
        elif eq == "BLOCKED":
            print(f"- note=đủ điểm nhưng hard_block (vd min_gap) — block_reason={gf.get('block_reason') or '-'}")
    print("")


def _v5_try_emit_cycle_log(ctx, params):
    """Throttle ~10s khi cùng (RESULT, MAIN, score, pendings, positions)."""
    if not bool(params.get("v5_structured_log", True)):
        return
    gf = ctx.get("gate_features") or {}
    if gf.get("v5_score_reused_no_new_close") and bool(params.get("v5_quiet_structured_when_no_new_close", True)):
        return
    r, m = _v5_compute_result_main(ctx)
    sig = (r, m, gf.get("score"), ctx.get("pre_np"), ctx.get("pre_npos"))
    now_m = time.monotonic()
    prev = getattr(run, "_last_v5_struct_log", None)
    if prev is not None and prev[0] == sig and (now_m - prev[1]) < 10.0:
        return
    if _v5_param_log_debug(params):
        _v5_emit_structured_cycle_log(ctx, params)
    else:
        _v5_emit_minimal_cycle_log(ctx, params)
    run._last_v5_struct_log = (sig, now_m)


def _v5_load_json_file(path: str, default: Any) -> Any:
    if not os.path.isfile(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _v5_relay_demo_file_missing_or_bad(path: str) -> bool:
    """
    True = chưa có snapshot inverse hợp lệ cho live (không file / 0 byte / JSON lỗi / thiếu grid_preview_inverse).
    Dùng để bootstrap từ cặp STOP trên MT5 khi file tồn tại nhưng rỗng (từng tạo tay hoặc ghi dở).
    """
    if not os.path.isfile(path):
        return True
    try:
        if os.path.getsize(path) == 0:
            return True
    except OSError:
        return True
    data = _v5_load_json_file(path, None)
    if not isinstance(data, dict) or not data:
        return True
    inv = data.get("grid_preview_inverse")
    if not isinstance(inv, dict):
        return True
    if inv.get("buy_price") is None or inv.get("sell_price") is None:
        return True
    return False


def _v5_inverse_ipc_port_value(params: Optional[Dict[str, Any]]) -> int:
    params = params or {}
    try:
        p = int(params.get("v5_inverse_ipc_port") or 0)
    except (TypeError, ValueError):
        return 0
    return p if 0 < p <= 65535 else 0


def _v5_inverse_ipc_host(params: Optional[Dict[str, Any]]) -> str:
    h = str((params or {}).get("v5_inverse_ipc_host") or "127.0.0.1").strip()
    return h or "127.0.0.1"


def _v5_load_copy_fill_consumed() -> Set[str]:
    data = _v5_load_json_file(V5_COPY_FILL_CONSUMED_JSON, {})
    if isinstance(data, dict):
        ids = data.get("consumed_demo_position_tickets") or data.get("ids") or []
    elif isinstance(data, list):
        ids = data
    else:
        ids = []
    return {str(x).strip() for x in ids if str(x).strip()}


def _v5_save_copy_fill_consumed_disk(consumed: Set[str]) -> None:
    lst = sorted(consumed)
    if len(lst) > MAX_V5_COPY_FILL_IDS:
        lst = lst[-MAX_V5_COPY_FILL_IDS :]
    tmp = V5_COPY_FILL_CONSUMED_JSON + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"consumed_demo_position_tickets": lst}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, V5_COPY_FILL_CONSUMED_JSON)
    except OSError as e:
        print(f"⚠️ [V5 live copy-fill] Không ghi {V5_COPY_FILL_CONSUMED_JSON}: {e}")


def _v5_push_ipc_json_line(host: str, port: int, obj: Dict[str, Any]) -> bool:
    """Gửi một dòng JSON + \\n tới TCP (giống snapshot inverse)."""
    if port <= 0 or port > 65535:
        return False
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n"
    for attempt in range(4):
        try:
            with socket.create_connection((host, port), timeout=3.0) as s:
                s.sendall(data)
            return True
        except OSError:
            if attempt < 3:
                time.sleep(0.35)
    return False


def _v5_demo_copy_fill_fresh_tickets_cross_cycle(
    position_tickets: List[int],
    state: Dict[str, Any],
) -> List[int]:
    """
    Demo copy-fill: ticket position **mới** so với trạng thái đã xử lý (xuyên chu kỳ sleep).

    Vấn đề cũ: chỉ so `post_positions − pre_positions` trong một vòng — nếu khớp trong
    `time.sleep` giữa hai vòng thì vòng sau `pre` đã có ticket → luôn rỗng, không gửi TCP.

    Gọi sau snapshot `pre` và sau snapshot `post` (cùng vòng); `state` giữ `announced` + `ready`.
    Ticket chỉ được thêm vào `announced` sau khi `_v5_demo_emit_copy_fill_ipc_events` trả về (TCP OK hoặc bỏ qua vĩnh viễn).
    """
    cur: Set[int] = set(int(t) for t in position_tickets)
    ann: Set[int] = state.setdefault("announced", set())
    if not state.get("ready"):
        ann.clear()
        ann.update(cur)
        state["ready"] = True
        return []
    return sorted(t for t in cur if t not in ann)


def _v5_demo_emit_copy_fill_ipc_events(
    config: Dict[str, Any],
    params: Dict[str, Any],
    sym: str,
    mag: int,
    new_tickets: list,
    sync_close_tickets: Optional[Set[int]] = None,
) -> Set[int]:
    """
    Demo: mỗi position mới (ticket) gửi event `demo_fill` qua inverse IPC port.
    Chỉ chạy khi có **position đã khớp** (danh sách ticket từ cross-cycle hoặc intracycle) — không gửi khi chỉ có lệnh chờ STOP/LIMIT.

    Trả về ticket đã xử lý xong cho copy-fill (gửi TCP thành công, hoặc magic/symbol lệch — không nên lặp vô hạn).
    Nếu `sync_close_tickets` khác None: mỗi ticket **demo_fill** gửi TCP OK được thêm vào set để sau này phát `demo_close` khi position biến mất trên demo.
    """
    done: Set[int] = set()
    port = _v5_inverse_ipc_port_value(params)
    if port <= 0:
        return done
    host = _v5_inverse_ipc_host(params)
    pos_buy = int(getattr(mt5, "POSITION_TYPE_BUY", 0))
    for tid in new_tickets:
        try:
            t_int = int(tid)
        except (TypeError, ValueError):
            continue
        plist: list = []
        for _retry in range(8):
            plist = list(mt5.positions_get(ticket=t_int) or [])
            if plist:
                break
            time.sleep(0.04)
        if not plist:
            plist = [
                p
                for p in (mt5.positions_get(symbol=sym) or [])
                if int(getattr(p, "ticket", 0) or 0) == t_int
            ]
        if not plist:
            _v5_throttle_print(
                f"cf_emit_no_pos_{t_int}",
                f"⚠️ [V5 demo_fill] Không đọc được position ticket={t_int} (symbol={sym}) sau retry — không gửi TCP. "
                f"Live cần lắng nghe {host}:{port} trước khi khớp.",
                60.0,
            )
            continue
        p = plist[0]
        if int(getattr(p, "magic", 0) or 0) != int(mag):
            _v5_throttle_print(
                f"cf_emit_bad_magic_{t_int}",
                f"⚠️ [V5 demo_fill] ticket={t_int} magic={getattr(p, 'magic', 0)} ≠ config {mag} — không gửi.",
                60.0,
            )
            done.add(t_int)
            continue
        p_sym = str(getattr(p, "symbol", "") or "").strip()
        if p_sym != sym:
            _v5_throttle_print(
                f"cf_emit_bad_sym_{t_int}",
                f"⚠️ [V5 demo_fill] ticket={t_int} symbol position={p_sym!r} ≠ config {sym!r} — không gửi.",
                60.0,
            )
            done.add(t_int)
            continue
        ptype = int(getattr(p, "type", -1))
        side = "BUY" if ptype == pos_buy else "SELL"
        try:
            px = float(getattr(p, "price_open", 0) or 0)
        except (TypeError, ValueError):
            px = 0.0
        vol = float(getattr(p, "volume", 0) or 0)
        tm = int(getattr(p, "time", 0) or 0)
        evt: Dict[str, Any] = {
            "event": "demo_fill",
            "position_ticket": t_int,
            "side": side,
            "price": px,
            "volume": vol,
            "time": tm,
            "symbol": sym,
            "magic": mag,
        }
        if _v5_push_ipc_json_line(host, port, evt):
            print(
                f"📤 [V5 demo_fill] sent position_ticket={t_int} side={side} price={px} vol={vol} "
                f"→ {host}:{port}"
            )
            done.add(t_int)
            if sync_close_tickets is not None:
                sync_close_tickets.add(t_int)
        else:
            print(f"⚠️ [V5 demo_fill] gửi TCP thất bại ticket={t_int} → {host}:{port}")
    return done


def _v5_demo_try_emit_demo_close_ipc(
    params: Dict[str, Any],
    sym: str,
    mag: int,
    current_position_tickets: List[int],
    state: Dict[str, Any],
) -> None:
    """
    Demo: position ticket đã từng `demo_fill` (TCP OK) mà không còn trên tài khoản demo → gửi `demo_close`.
    """
    if not _v5_param_bool(params, "v5_demo_push_copy_close_ipc", True):
        return
    port = _v5_inverse_ipc_port_value(params)
    if port <= 0:
        return
    track: Set[int] = state.setdefault("sync_close_tickets", set())
    if not track:
        return
    cur = set(int(t) for t in current_position_tickets)
    host = _v5_inverse_ipc_host(params)
    for t_int in sorted(track):
        if t_int in cur:
            continue
        evt: Dict[str, Any] = {
            "event": "demo_close",
            "position_ticket": t_int,
            "symbol": sym,
            "magic": mag,
        }
        if _v5_push_ipc_json_line(host, port, evt):
            print(f"📤 [V5 demo_close] sent demo position_ticket={t_int} → {host}:{port}")
            track.discard(t_int)
        else:
            print(
                f"⚠️ [V5 demo_close] gửi TCP thất bại ticket={t_int} → {host}:{port} "
                f"(giữ trong hàng đợi, thử lại vòng sau)"
            )


def _v5_market_copy_step_price(params: Dict[str, Any]) -> float:
    """Khoảng giá ±step cho SL/TP copy MARKET (ưu tiên v5_market_copy_sl_tp_step → steps[0] → step → 5)."""
    raw = params.get("v5_market_copy_sl_tp_step")
    if raw is not None:
        try:
            v = float(raw)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    steps = params.get("steps")
    if isinstance(steps, (list, tuple)) and steps:
        try:
            v = float(steps[0])
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    st = params.get("step")
    if st is not None:
        try:
            v = float(st)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return 5.0


def _v5_config_spread_sl_tp_root(config: Dict[str, Any]) -> tuple[float, float]:
    """Giống sign_inverse: SL += spread_sl, TP += spread_tp (root JSON)."""
    raw_sl = config.get("spread_sl")
    raw_tp = config.get("spread_tp")
    try:
        spread_sl = 0.0 if raw_sl is None else float(raw_sl)
    except (TypeError, ValueError):
        spread_sl = 0.0
    try:
        spread_tp = -0.3 if raw_tp is None else float(raw_tp)
    except (TypeError, ValueError):
        spread_tp = -0.3
    return spread_sl, spread_tp


def _v5_live_market_copy_sl_tp_prices(
    config: Dict[str, Any],
    params: Dict[str, Any],
    sym_live: str,
    is_live_buy: bool,
) -> tuple[float, float]:
    """
    SL/TP cho lệnh MARKET copy-fill: mốc entry = bid/ask live tại lúc gửi (khớp broker).
    Công thức cùng nhánh với grid / sign_inverse (± step + spread_sl/spread_tp).
    """
    if not _v5_param_bool(params, "v5_market_copy_sl_tp_enabled", False):
        return (0.0, 0.0)
    step_val = _v5_market_copy_step_price(params)
    if step_val <= 0:
        return (0.0, 0.0)
    tick = mt5.symbol_info_tick(sym_live)
    if not tick:
        return (0.0, 0.0)
    entry_ref = float(tick.ask) if is_live_buy else float(tick.bid)
    info = mt5.symbol_info(sym_live)
    digits = int(getattr(info, "digits", 5) or 5) if info else 5
    spread_sl, spread_tp = _v5_config_spread_sl_tp_root(config)
    if is_live_buy:
        sl = round(entry_ref - step_val + spread_sl, digits)
        tp = round(entry_ref + step_val + spread_tp, digits)
    else:
        sl = round(entry_ref + step_val + spread_sl, digits)
        tp = round(entry_ref - step_val + spread_tp, digits)
    point = float(getattr(info, "point", 0) or 0) if info else 0
    if point <= 0:
        point = float(10 ** (-digits))
    eps = point * 2.0
    if is_live_buy:
        if not (sl < entry_ref - eps and tp > entry_ref + eps):
            _v5_throttle_print(
                "mkt_copy_sl_tp_bad_buy",
                f"⚠️ [V5 live copy-fill] SL/TP BUY không hợp lệ (step/spread/stops?) entry≈{entry_ref} sl={sl} tp={tp} — đặt MARKET không SL/TP.",
                120.0,
            )
            return (0.0, 0.0)
    else:
        if not (tp < entry_ref - eps and sl > entry_ref + eps):
            _v5_throttle_print(
                "mkt_copy_sl_tp_bad_sell",
                f"⚠️ [V5 live copy-fill] SL/TP SELL không hợp lệ entry≈{entry_ref} sl={sl} tp={tp} — đặt MARKET không SL/TP.",
                120.0,
            )
            return (0.0, 0.0)
    return (sl, tp)


def _v5_live_apply_demo_fill_market(
    config: Dict[str, Any],
    payload: Dict[str, Any],
    consumed: Set[str],
    params: Optional[Dict[str, Any]],
) -> None:
    """
    Live: demo BUY → MARKET SELL; demo SELL → MARKET BUY. Symbol/magic/volume từ config live.
    SL/TP chỉ khi `v5_market_copy_sl_tp_enabled`: true (mặc định tắt).
    Chỉ ghi consumed khi order_send DONE.
    Tắt bằng `parameters.v5_live_market_copy_demo_fill_enabled`: false.
    """
    params = params or {}
    if not _v5_param_bool(params, "v5_live_market_copy_demo_fill_enabled", True):
        _v5_throttle_print(
            "live_mkt_copy_disabled",
            "ℹ️ [V5 live copy-fill] Tắt — v5_live_market_copy_demo_fill_enabled=false (không đặt MARKET).",
            120.0,
        )
        return
    pid = str(payload.get("position_ticket") or "").strip()
    if not pid:
        return
    if pid in consumed:
        _v5_throttle_print(
            f"cf_dup_{pid}",
            f"ℹ️ [V5 live copy-fill] Bỏ qua — đã xử lý demo position_ticket={pid}",
            90.0,
        )
        return
    side = str(payload.get("side") or "").strip().upper()
    if side not in ("BUY", "SELL"):
        print(f"⚠️ [V5 live copy-fill] side không hợp lệ: {side!r}")
        return
    sym_live = str(config.get("symbol") or "").strip()
    if not sym_live:
        return
    mag_live = int(config.get("magic") or 0)
    vol = float(config.get("volume") or 0.01)
    try:
        dev = int(params.get("v5_market_copy_deviation", 30))
    except (TypeError, ValueError):
        dev = 30
    cmt = f"CopyFill_{pid}"[:31]
    is_live_buy = side == "SELL"
    live_dir = "BUY" if is_live_buy else "SELL"
    sl_px, tp_px = _v5_live_market_copy_sl_tp_prices(config, params, sym_live, is_live_buy)
    r = place_market_order(
        sym_live,
        vol,
        is_live_buy,
        mag_live,
        cmt,
        sl=sl_px,
        tp=tp_px,
        deviation=dev,
    )
    if r is None:
        print("❌ [V5 live copy-fill] order_send = None")
    elif int(getattr(r, "retcode", 0) or 0) != mt5.TRADE_RETCODE_DONE:
        cm = str(getattr(r, "comment", "") or "")
        print(f"❌ [V5 live copy-fill] MARKET {live_dir} retcode={getattr(r, 'retcode', 0)} {cm}")
    else:
        ot = int(getattr(r, "order", 0) or 0)
        stp = f" sl={sl_px} tp={tp_px}" if (sl_px or tp_px) else " sl=0 tp=0"
        print(f"✅ [V5 live copy-fill] MARKET {live_dir} OK ticket={ot} (demo pos {pid}){stp}")
        consumed.add(pid)
        _v5_save_copy_fill_consumed_disk(consumed)


def _v5_copyfill_comment_matches_live(cmt: str, demo_pid: str) -> bool:
    """
    So khớp comment position live với nhãn CopyFill_<demo_ticket> (chính xác hoặc broker cắt chuỗi).
    """
    c = (cmt or "").strip()
    if not c.startswith("CopyFill_"):
        return False
    want = f"CopyFill_{demo_pid}"[:31]
    if c == want:
        return True
    if len(c) <= len(want) and want[: len(c)] == c:
        return True
    if len(c) >= len(want) and c[: len(want)] == want:
        return True
    suf = c[len("CopyFill_") :]
    return suf == demo_pid


def _v5_close_copyfill_mirror_positions(sym_live: str, mag_live: int, demo_pid: str) -> int:
    """Đóng mọi position live (symbol+magic) có comment khớp CopyFill cho ticket demo."""
    info = mt5.symbol_info(sym_live)
    type_filling = mt5.ORDER_FILLING_IOC
    if info and getattr(info, "filling_mode", 0) & 2:
        type_filling = mt5.ORDER_FILLING_IOC
    positions = mt5.positions_get(symbol=sym_live, magic=mag_live) or []
    closed = 0
    for p in positions:
        c = (getattr(p, "comment", "") or "").strip()
        if not _v5_copyfill_comment_matches_live(c, demo_pid):
            continue
        tick = mt5.symbol_info_tick(sym_live)
        if not tick:
            continue
        pt = int(getattr(p, "ticket", 0) or 0)
        ptype = int(getattr(p, "type", -1))
        vol = float(getattr(p, "volume", 0) or 0)
        price = float(tick.bid) if ptype == getattr(mt5, "POSITION_TYPE_BUY", 0) else float(tick.ask)
        r = mt5.order_send(
            {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": sym_live,
                "volume": vol,
                "type": mt5.ORDER_TYPE_SELL
                if ptype == getattr(mt5, "POSITION_TYPE_BUY", 0)
                else mt5.ORDER_TYPE_BUY,
                "position": pt,
                "price": price,
                "magic": mag_live,
                "comment": "Close_CopyFill",
                "type_filling": type_filling,
            }
        )
        if r and int(getattr(r, "retcode", 0) or 0) == mt5.TRADE_RETCODE_DONE:
            closed += 1
    return closed


def _v5_live_apply_demo_close_market(
    config: Dict[str, Any],
    payload: Dict[str, Any],
    params: Optional[Dict[str, Any]],
) -> None:
    """
    Live: demo đóng position → đóng position mirror (comment `CopyFill_<demo_ticket>`).
    """
    params = params or {}
    if not _v5_param_bool(params, "v5_live_market_copy_close_enabled", True):
        _v5_throttle_print(
            "live_mkt_close_disabled",
            "ℹ️ [V5 live copy-close] Tắt — v5_live_market_copy_close_enabled=false.",
            120.0,
        )
        return
    raw = payload.get("position_ticket")
    try:
        pid = str(int(float(str(raw).strip())))
    except (TypeError, ValueError):
        pid = str(raw or "").strip()
    if not pid:
        return
    sym_live = str(config.get("symbol") or "").strip()
    if not sym_live:
        return
    mag_live = int(config.get("magic") or 0)
    want = f"CopyFill_{pid}"[:31]
    n = _v5_close_copyfill_mirror_positions(sym_live, mag_live, pid)
    if n > 0:
        print(f"✅ [V5 live copy-close] Đã đóng {n} position | nhãn≈{want!r} (demo ticket {pid})")
    else:
        sample = []
        for p in (mt5.positions_get(symbol=sym_live, magic=mag_live) or [])[:5]:
            sample.append(str(getattr(p, "comment", "") or ""))
        _v5_throttle_print(
            f"live_close_miss_{pid}",
            f"ℹ️ [V5 live copy-close] Không khớp position (magic={mag_live}) cho demo ticket {pid}, "
            f"nhãn mong đợi {want!r}. Mẫu comment đang mở: {sample}",
            60.0,
        )


def _v5_open_inverse_listener(host: str, port: int) -> Optional[socket.socket]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(8)
        s.setblocking(False)
        print(
            f"📡 [V5 live] Inverse IPC: lắng nghe {host}:{port} — `demo_fill` / `demo_close` "
            f"và/hoặc snapshot inverse LIMIT (nếu bật v5_live_inverse_limit_ipc)."
        )
        return s
    except OSError as e:
        print(f"❌ [V5 live] Không bind inverse IPC {host}:{port}: {e}")
        return None


def _v5_live_apply_inverse_payload(
    config: Dict[str, Any],
    consumed: Set[str],
    params: Optional[Dict[str, Any]],
    payload: Dict[str, Any],
    *,
    source_detail: str,
) -> None:
    """Đặt InvGrid từ dict snapshot (file hoặc TCP); `source_detail` dùng trong log."""
    params = params or {}
    log_skip = bool(params.get("v5_live_inverse_log_skip", True))
    try:
        import btc_sign_inverser as _bi
    except ImportError:
        return
    skip = _bi.inverse_payload_ready(payload, consumed, None)
    rid = str(payload.get("relay_id") or "")
    if skip is not None:
        if log_skip:
            if skip == "already_consumed":
                _v5_throttle_print(
                    f"inv_consumed_{rid}",
                    f"ℹ️ [V5 live] Inverse bỏ qua: relay_id đã consumed ({rid[:8]}…).\n"
                    f"   → Mở btc_signal_inverse_consumed_relay_ids.json, xóa id này nếu muốn đặt lại cùng snapshot.",
                    120.0,
                )
            else:
                _v5_throttle_print(
                    f"inv_skip_{skip}",
                    f"ℹ️ [V5 live] Inverse bỏ qua: {skip} ({source_detail})",
                    45.0,
                )
        return
    sym_live = str(config.get("symbol") or "").strip()
    if not sym_live:
        return
    place_payload = _bi._as_place_payload(payload, sym_live)
    place_payload["magic"] = int(config.get("magic") or 0)
    vol = float(config.get("volume") or 0.01)
    inv_lp = LIVE_INVERSE_LOG_PREFIX or "[V5 live]"
    inv = payload.get("grid_preview_inverse") or {}
    print(
        f"📤 {inv_lp} Chuẩn bị InvGrid | {sym_live} magic={place_payload.get('magic')} vol={vol} | "
        f"BUY_LIMIT giá={inv.get('buy_price')} SELL_LIMIT giá={inv.get('sell_price')} | "
        f"relay={str(rid)[:8]}… | nguồn={source_detail}"
    )
    ok, err, mark_consumed = _bi.place_pair_from_inverse_relay(
        place_payload, vol, log_prefix=inv_lp
    )
    if rid and (ok or mark_consumed):
        _bi.save_consumed_id(str(rid), consumed)
        consumed.add(str(rid))
    if ok:
        print(f"✅ {inv_lp} Hoàn tất snapshot ({source_detail}) relay={str(rid)[:8]}…")
    elif mark_consumed and err and "thiếu" not in err:
        print(f"⚠️ {inv_lp} Inverse — consumed: {err}")
    elif not ok and not mark_consumed and err:
        print(f"⚠️ {inv_lp} Inverse đặt lệnh thất bại (sẽ thử lại): {err}")


def _v5_live_poll_inverse_ipc(
    config: Dict[str, Any],
    consumed: Set[str],
    copy_fill_consumed: Set[str],
    params: Optional[Dict[str, Any]],
    listener: socket.socket,
    timeout_sec: float,
) -> None:
    """select + drain mọi kết nối pending (demo có thể gửi demo_fill rồi demo_close liền)."""
    params = params or {}
    try:
        r, _, _ = select.select([listener], [], [], max(0.0, float(timeout_sec)))
    except (ValueError, OSError):
        return
    if not r:
        return

    def _handle_one_payload(payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict) or not payload:
            return
        ev = str(payload.get("event") or "").strip().lower()
        if ev == "demo_fill":
            _v5_live_apply_demo_fill_market(config, payload, copy_fill_consumed, params)
            return
        if ev == "demo_close":
            _v5_live_apply_demo_close_market(config, payload, params)
            return
        if _v5_param_bool(params, "v5_live_inverse_limit_ipc", False):
            _v5_live_apply_inverse_payload(
                config, consumed, params, payload, source_detail="IPC localhost"
            )
        else:
            _v5_throttle_print(
                "inv_ipc_skip_non_fill",
                "ℹ️ [V5 live] IPC: bỏ qua snapshot inverse LIMIT (v5_live_inverse_limit_ipc=false). "
                "Chỉ xử lý demo_fill / demo_close.",
                120.0,
            )

    while True:
        try:
            conn, _ = listener.accept()
        except BlockingIOError:
            break
        except OSError:
            break
        try:
            conn.settimeout(12.0)
            parts: list = []
            total = 0
            while total < 512 * 1024:
                b = conn.recv(8192)
                if not b:
                    break
                parts.append(b)
                total += len(b)
                if b"\n" in b:
                    break
            raw = b"".join(parts)
            line = raw.split(b"\n", 1)[0].decode("utf-8", errors="replace")
            payload = json.loads(line)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            _v5_throttle_print("inv_ipc_bad", f"⚠️ [V5 live] Inverse IPC payload lỗi: {e}", 45.0)
            payload = None
        finally:
            try:
                conn.close()
            except OSError:
                pass
        if isinstance(payload, dict) and payload:
            _handle_one_payload(payload)


def _v5_live_try_inverse_limits_from_demo_file(
    config: Dict[str, Any],
    consumed: Set[str],
    params: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Đọc snapshot inverse (demo_write_inverse_relay_file) từ RELAY_DEMO_FILE;
    đặt cặp limit trên session MT5 hiện tại với symbol/magic từ config live.
    """
    params = params or {}
    log_skip = bool(params.get("v5_live_inverse_log_skip", True))
    path = signal_relay.RELAY_DEMO_FILE
    if not os.path.isfile(path):
        if log_skip:
            _v5_throttle_print(
                "inv_missing_file",
                f"ℹ️ [V5 live] Chưa có file inverse: {path}\n"
                f"   → Demo phải ghi file (cùng thư mục GridStep) hoặc bật v5_inverse_ipc_port (TCP) để không dùng file.",
                90.0,
            )
        return
    payload = _v5_load_json_file(path, None)
    if not isinstance(payload, dict) or not payload:
        if log_skip:
            _v5_throttle_print(
                "inv_empty",
                f"ℹ️ [V5 live] File inverse rỗng / lỗi đọc: {path}\n"
                f"   → Đợi demo ghi snapshot hợp lệ (hoặc vừa ghi xong — thử lại sau vài giây).",
                60.0,
            )
        return
    _v5_live_apply_inverse_payload(
        config,
        consumed,
        params,
        payload,
        source_detail=f"file {os.path.basename(path)}",
    )


def _v5_normalize_config_trade_keys(config: Dict[str, Any]) -> None:
    """Đảm bảo symbol/magic ở top-level (một số JSON chỉ khai báo trong parameters hoặc thiếu magic)."""
    params = config.get("parameters") or {}
    if not str(config.get("symbol") or "").strip():
        alt = params.get("symbol")
        if alt is not None and str(alt).strip():
            config["symbol"] = str(alt).strip()
    if "magic" not in config:
        if "magic" in params:
            try:
                config["magic"] = int(params["magic"])
            except (TypeError, ValueError):
                config["magic"] = 0
        else:
            config["magic"] = 0
    else:
        try:
            config["magic"] = int(config["magic"])
        except (TypeError, ValueError):
            config["magic"] = 0


def _v5_argv_config_basename() -> str:
    a = sys.argv[1:]
    if not a:
        return V5_SUPERVISOR_DEMO_CONFIG
    if a[0].strip() == "--config" and len(a) >= 2:
        return os.path.basename(a[1].strip())
    if a[0].strip().endswith(".json"):
        return os.path.basename(a[0].strip())
    return V5_SUPERVISOR_DEMO_CONFIG


def _v5_strip_supervisor_flags() -> None:
    sys.argv = [
        sys.argv[0],
        *[x for x in sys.argv[1:] if x not in ("--no-parallel-live", V5_SUPERVISOR_CHILD_FLAG)],
    ]


def _v5_parallel_inverse_live_enabled(demo_config_path: str) -> bool:
    try:
        with open(demo_config_path, encoding="utf-8") as f:
            demo_cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return True
    return bool(demo_cfg.get("parameters", {}).get("v5_parallel_inverse_live", True))


def run():
    args = sys.argv[1:]
    if args and args[0].strip() == "--check-db":
        base.check_grid_step_db()
        sys.exit(0)

    if V5_SUPERVISOR_CHILD_FLAG in sys.argv:
        _v5_strip_supervisor_flags()
        _run_v5_bot()
        return

    if len(sys.argv) == 1:
        sys.argv.extend(["--config", V5_SUPERVISOR_DEMO_CONFIG])

    no_parallel = "--no-parallel-live" in sys.argv
    cfg_base = _v5_argv_config_basename()
    live_path = os.path.join(SCRIPT_DIR, "configs", V5_SUPERVISOR_LIVE_CONFIG)
    demo_path = os.path.join(SCRIPT_DIR, "configs", V5_SUPERVISOR_DEMO_CONFIG)
    demo_selected = cfg_base == V5_SUPERVISOR_DEMO_CONFIG
    if no_parallel:
        print("📌 [V5] --no-parallel-live: chỉ chạy một process (config hiện tại).")
    _v5_strip_supervisor_flags()

    use_dual_supervisor = (
        demo_selected
        and not no_parallel
        and os.path.isfile(live_path)
        and _v5_parallel_inverse_live_enabled(demo_path)
    )

    if use_dual_supervisor:
        script = os.path.abspath(__file__)
        py = sys.executable
        cmd_demo = [py, script, "--config", V5_SUPERVISOR_DEMO_CONFIG, V5_SUPERVISOR_CHILD_FLAG]
        cmd_live = [py, script, "--config", V5_SUPERVISOR_LIVE_CONFIG, V5_SUPERVISOR_CHILD_FLAG]
        print(
            f"🚀 [V5] Supervisor: demo ({V5_SUPERVISOR_DEMO_CONFIG}) + live inverse ({V5_SUPERVISOR_LIVE_CONFIG}). "
            f"Hai terminal MT5 (mt5_path). Ctrl+C dừng cả hai."
        )
        p_demo = None
        p_live = None
        try:
            p_demo = subprocess.Popen(cmd_demo, cwd=SCRIPT_DIR)
            p_live = subprocess.Popen(cmd_live, cwd=SCRIPT_DIR)
        except OSError as e:
            print(f"⚠️ [V5] Không spawn process: {e}")
            if p_demo is not None and p_demo.poll() is None:
                p_demo.terminate()
            return
        try:
            while p_demo.poll() is None or p_live.poll() is None:
                time.sleep(0.4)
        except KeyboardInterrupt:
            print("\n🛑 [V5] Supervisor dừng (Ctrl+C)…")
        finally:
            for p in (p_demo, p_live):
                if p is not None and p.poll() is None:
                    p.terminate()
                    try:
                        p.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        p.kill()
        return

    _run_v5_bot()


def _run_v5_bot():
    args = sys.argv[1:]
    if args and args[0].strip() == "--check-db":
        base.check_grid_step_db()
        sys.exit(0)

    config_name = "config_grid_step_v5.json"
    if args:
        if args[0].strip() == "--config" and len(args) >= 2:
            config_name = args[1].strip()
        elif args[0].strip().endswith(".json"):
            # tiện chạy nhanh: python strategy_grid_step_v5.py config_grid_step_v5_live.json
            config_name = args[0].strip()
    config_path = os.path.join(SCRIPT_DIR, "configs", config_name)
    print(f"📁 [V5] using config: {config_path}")
    config = base.load_config(config_path)
    if config:
        _v5_normalize_config_trade_keys(config)
        _v5_apply_relay_paths_from_config(config)

    consecutive_errors = 0
    if config and base.connect_mt5(config):
        params = config.get("parameters", {})
        loop_interval_seconds = _v5_loop_sleep_seconds(params)
        if "steps" in params and params["steps"] is not None:
            steps_config = params["steps"]
            if not isinstance(steps_config, list):
                steps_config = [steps_config]
            steps_list = [float(s) for s in steps_config]
        else:
            steps_list = None

        label = f"steps: {steps_list}" if steps_list is not None else "single step (legacy)"
        consecutive_loss_pause_enabled = params.get("consecutive_loss_pause_enabled", True)
        print(f"✅ Grid Step Bot V5 - Started ({label})")
        loop_count = 0
        demo_copy_fill_ipc_state: Dict[str, Any] = {
            "announced": set(),
            "ready": False,
            "sync_close_tickets": set(),
        }
        live_inverse_consumed: Optional[Set[str]] = None
        _p0 = config.get("parameters") or {}
        copy_fill_consumed: Set[str] = (
            _v5_load_copy_fill_consumed()
            if str(_p0.get("v5_role", "")).lower().strip() == "live"
            and _v5_param_bool(_p0, "v5_live_inverse_only", False)
            else set()
        )
        inverse_ipc_listener: Optional[socket.socket] = None
        if str(_p0.get("v5_role", "")).lower().strip() == "live" and _v5_param_bool(
            _p0, "v5_live_inverse_only", False
        ):
            ipc_p = _v5_inverse_ipc_port_value(_p0)
            print(
                "📌 [V5] v5_live_inverse_only: copy MARKET (`demo_fill`) + đóng mirror (`demo_close`) + tùy chọn InvGrid LIMIT qua IPC "
                "— bỏ qua relay tín hiệu / gate / grid STOP. "
                + (
                    f"TCP {_v5_inverse_ipc_host(_p0)}:{ipc_p}."
                    if ipc_p > 0
                    else "Đọc snapshot từ RELAY_DEMO_FILE (file .json)."
                )
            )
            ai0 = mt5.account_info()
            acct_s = str(ai0.login) if ai0 else "?"
            print(
                f"💡 [V5 live inverse-only] MT5 account={acct_s} — process này không chạy [V5 Gate] hay Grid STOP. "
                f"Nếu supervisor (demo+live), các dòng 📚 [V5 Gate] / 📤 Grid STOP là từ process DEMO (khác account)."
            )

        try:
            while True:
                params = config.get("parameters", {})
                v5_role = str(params.get("v5_role", "demo")).lower().strip()
                entry_thr = int(params.get("entry_score_threshold", 6))
                relay_verbose = bool(params.get("relay_verbose_log", True))
                sym = str(config.get("symbol") or "").strip()
                mag = int(config.get("magic") or 0)
                if sym and _v5_weekend_flatten_maybe(config, params, sym, mag):
                    print("🛑 [V5 weekend] Hoàn tất — dừng bot (mt5.shutdown).")
                    break
                pre_pending, pre_positions = _snapshot_bot_orders_positions(sym, mag)
                if v5_role == "demo" and _v5_inverse_ipc_port_value(params) > 0:
                    _v5_demo_try_emit_demo_close_ipc(
                        params, sym, mag, pre_positions, demo_copy_fill_ipc_state
                    )
                if (
                    v5_role == "demo"
                    and _v5_inverse_ipc_port_value(params) > 0
                    and _v5_param_bool(params, "v5_demo_push_copy_fill_ipc", True)
                ):
                    _cf_sync_pre = (
                        demo_copy_fill_ipc_state.setdefault("sync_close_tickets", set())
                        if _v5_param_bool(params, "v5_demo_push_copy_close_ipc", True)
                        else None
                    )
                    _cf_fresh_pre = _v5_demo_copy_fill_fresh_tickets_cross_cycle(
                        pre_positions, demo_copy_fill_ipc_state
                    )
                    if _cf_fresh_pre:
                        _cf_done_pre = _v5_demo_emit_copy_fill_ipc_events(
                            config, params, sym, mag, _cf_fresh_pre, _cf_sync_pre
                        )
                        demo_copy_fill_ipc_state["announced"].update(_cf_done_pre)
                has_grid = len(pre_pending) > 0 or len(pre_positions) > 0
                live_relay_blind = bool(params.get("live_relay_blind_follow", False))
                active_relay_id = None

                if v5_role == "live" and _v5_param_bool(params, "v5_live_inverse_only", False):
                    if live_inverse_consumed is None:
                        import btc_sign_inverser as _btc_si

                        live_inverse_consumed = _btc_si.load_consumed_ids()
                    ipc_port = _v5_inverse_ipc_port_value(params)
                    if ipc_port > 0:
                        if inverse_ipc_listener is None:
                            inverse_ipc_listener = _v5_open_inverse_listener(
                                _v5_inverse_ipc_host(params), ipc_port
                            )
                        if inverse_ipc_listener is not None:
                            _v5_live_poll_inverse_ipc(
                                config,
                                live_inverse_consumed,
                                copy_fill_consumed,
                                params,
                                inverse_ipc_listener,
                                loop_interval_seconds,
                            )
                        else:
                            _v5_live_try_inverse_limits_from_demo_file(
                                config, live_inverse_consumed, params
                            )
                    else:
                        _v5_live_try_inverse_limits_from_demo_file(
                            config, live_inverse_consumed, params
                        )
                    time.sleep(loop_interval_seconds)
                    continue

                if v5_role == "live" and bool(
                    params.get("v5_live_inverse_limits_from_demo_file", False)
                ):
                    if live_inverse_consumed is None:
                        import btc_sign_inverser as _btc_si

                        live_inverse_consumed = _btc_si.load_consumed_ids()
                    _v5_live_try_inverse_limits_from_demo_file(
                        config, live_inverse_consumed, params
                    )

                if v5_role == "live":
                    if not has_grid:
                        use_signal_relay = bool(params.get("signal_relay_enabled", False))
                        if use_signal_relay:
                            relay_payload = signal_relay.relay_read_valid(config)
                            if not relay_payload:
                                if live_relay_blind and bool(
                                    params.get("v5_live_run_grid_when_relay_missing", False)
                                ):
                                    allow_live = True
                                    gate_reason = "live_blind_no_relay_file"
                                    gate_features = _v5_live_gate_features_no_relay()
                                    active_relay_id = None
                                else:
                                    _v5_try_emit_cycle_log(
                                        {
                                            "exit_kind": "no_relay_flat",
                                            "v5_role": v5_role,
                                            "entry_thr": entry_thr,
                                            "max_positions": config.get("max_positions", 5),
                                            "pre_np": len(pre_pending),
                                            "pre_npos": len(pre_positions),
                                            "gate_reason": "no_relay",
                                            "gate_features": {},
                                            "relay_enabled": True,
                                            "relay_sent": False,
                                            "relay_reason": "NO_RELAY",
                                        },
                                        params,
                                    )
                                    time.sleep(loop_interval_seconds)
                                    continue
                            elif not live_relay_blind and not _relay_zone_matches_current(
                                config, relay_payload
                            ):
                                _v5_try_emit_cycle_log(
                                    {
                                        "exit_kind": "relay_zone_mismatch",
                                        "v5_role": v5_role,
                                        "entry_thr": entry_thr,
                                        "max_positions": config.get("max_positions", 5),
                                        "pre_np": len(pre_pending),
                                        "pre_npos": len(pre_positions),
                                        "gate_reason": "relay_zone_mismatch",
                                        "gate_features": signal_relay.relay_to_gate_features(
                                            relay_payload
                                        ),
                                        "relay_enabled": True,
                                        "relay_sent": False,
                                        "relay_reason": "RELAY_ZONE_MISMATCH",
                                    },
                                    params,
                                )
                                time.sleep(loop_interval_seconds)
                                continue
                            else:
                                allow_live = True
                                gate_reason = "live_relay_ok"
                                gate_features = signal_relay.relay_to_gate_features(relay_payload)
                                active_relay_id = relay_payload.get("relay_id")
                        else:
                            allow_live = True
                            gate_reason = "live_no_signal_relay"
                            gate_features = _v5_live_gate_features_no_relay()
                            active_relay_id = None
                    else:
                        allow_live = True
                        gate_reason = "live_grid_maintenance"
                        gate_features = _v5_live_gate_features_no_relay()
                else:
                    allow_live, gate_reason, gate_features = _v5_history_score_gate(config)

                if not allow_live:
                    _v5_try_emit_cycle_log(
                        {
                            "exit_kind": "gate_blocked",
                            "v5_role": v5_role,
                            "entry_thr": entry_thr,
                            "max_positions": config.get("max_positions", 5),
                            "pre_np": len(pre_pending),
                            "pre_npos": len(pre_positions),
                            "gate_reason": gate_reason,
                            "gate_features": gate_features or {},
                            "relay_enabled": bool(params.get("signal_relay_enabled", False)),
                            "relay_sent": False,
                            "relay_reason": "NO_DEMO_ORDER",
                        },
                        params,
                    )
                    # Gate chặn → không tới snapshot post; vẫn thử demo_close nếu position vừa biến mất trên demo.
                    if v5_role == "demo" and _v5_inverse_ipc_port_value(params) > 0:
                        _, _pos_gate = _snapshot_bot_orders_positions(sym, mag)
                        _v5_demo_try_emit_demo_close_ipc(
                            params, sym, mag, _pos_gate, demo_copy_fill_ipc_state
                        )
                    time.sleep(loop_interval_seconds)
                    continue

                # Demo: kết_luận=đạt (score>=entry, không block) → ghi v5_relay_signal.json (zone trùng thì signal_relay bỏ qua).
                relay_early_sent = False
                relay_early_reason = "NO_DEMO_ORDER"
                relay_early_zone = None
                relay_early_side = None
                if (
                    v5_role == "demo"
                    and bool(params.get("signal_relay_enabled", False))
                    and gate_features
                    and _v5_ket_luan_dat(gate_features, entry_thr)
                ):
                    _rid_er, relay_early_reason = signal_relay.demo_try_publish_relay(
                        config,
                        gate_features,
                        relay_zone_points=float(params.get("relay_zone_points") or 200),
                        ttl_minutes=float(params.get("relay_signal_ttl_minutes") or 180),
                        verbose=False,
                    )
                    relay_early_sent = _rid_er is not None
                    if relay_early_sent:
                        try:
                            ep = float(gate_features.get("current_signal_open_price") or 0)
                            relay_early_zone = signal_relay.price_zone_key(
                                ep, float(params.get("relay_zone_points") or 200)
                            )
                            relay_early_side = str(
                                gate_features.get("current_signal_type")
                                or gate_features.get("signal_type")
                                or ""
                            ).upper()
                        except (TypeError, ValueError):
                            pass

                live_min_entry_gap_seconds = int(float(params.get("live_min_entry_gap_minutes", 5)) * 60)
                if v5_role == "live":
                    remain_cd = _live_entry_cooldown_remaining_seconds(sym, mag, live_min_entry_gap_seconds)
                    # Chỉ chặn mở mới khi hệ thống đang flat (không position, không pending).
                    # Nếu đang có lệnh, để base strategy quản lý vòng đời bình thường.
                    skip_live_cd = live_relay_blind and str(gate_reason) in _LIVE_BLIND_RELAX_REASONS
                    if (
                        remain_cd > 0
                        and (len(pre_pending) == 0 and len(pre_positions) == 0)
                        and not skip_live_cd
                    ):
                        _v5_try_emit_cycle_log(
                            {
                                "exit_kind": "live_cooldown",
                                "v5_role": v5_role,
                                "entry_thr": entry_thr,
                                "max_positions": config.get("max_positions", 5),
                                "pre_np": len(pre_pending),
                                "pre_npos": len(pre_positions),
                                "gate_reason": gate_reason,
                                "gate_features": gate_features or {},
                                "relay_enabled": bool(params.get("signal_relay_enabled", False)),
                                "relay_sent": False,
                                "relay_reason": "LIVE_COOLDOWN",
                            },
                            params,
                        )
                        time.sleep(loop_interval_seconds)
                        continue

                # Live: tín hiệu demo đủ điểm nhưng đã có cặp pending khớp tín hiệu → không gọi strategy (tránh thừa).
                live_skip_dup = bool(params.get("live_skip_if_equivalent", True))
                if live_relay_blind and str(gate_reason) in _LIVE_BLIND_RELAX_REASONS:
                    live_skip_dup = False
                if (
                    v5_role == "live"
                    and live_skip_dup
                    and allow_live
                    and gate_reason != "live_grid_maintenance"
                ):
                    step_f = _v5_step_filter_for_gate(config)
                    sig_type = gate_features.get("current_signal_type") or gate_features.get("signal_type")
                    sig_px = gate_features.get("current_signal_open_price")
                    gpr = gate_features.get("grid_preview") or {}
                    step_val = float(gpr.get("step") or _v5_gate_step_val(config))
                    info_lp = mt5.symbol_info(sym)
                    pt = float(getattr(info_lp, "point", 0.01) or 0.01) if info_lp else 0.01
                    dthr_raw = params.get("live_duplicate_price_threshold")
                    if dthr_raw is not None and float(dthr_raw) > 0:
                        dthr = float(dthr_raw)
                    else:
                        dthr = max(2.0 * pt, step_val * 1.05)
                    try:
                        spx = float(sig_px) if sig_px is not None else 0.0
                    except (TypeError, ValueError):
                        spx = 0.0
                    has_eq = _live_has_equivalent_order(sym, mag, step_f, sig_type, spx, dthr)
                    npos_ct = len(pre_positions)
                    npen_ct = len(pre_pending)
                    if has_eq and npos_ct == 0 and npen_ct == 2:
                        _v5_try_emit_cycle_log(
                            {
                                "exit_kind": "dup_skip",
                                "v5_role": v5_role,
                                "entry_thr": entry_thr,
                                "max_positions": config.get("max_positions", 5),
                                "pre_np": len(pre_pending),
                                "pre_npos": len(pre_positions),
                                "gate_reason": gate_reason,
                                "gate_features": gate_features or {},
                                "relay_enabled": bool(params.get("signal_relay_enabled", False)),
                                "relay_sent": False,
                                "relay_reason": "DUPLICATE_PENDING",
                            },
                            params,
                        )
                        time.sleep(loop_interval_seconds)
                        continue

                if consecutive_loss_pause_enabled:
                    if steps_list is not None:
                        for step_val in steps_list:
                            base.sync_closed_orders_from_mt5(config, strategy_name=f"Grid_Step_{step_val}")
                    else:
                        base.sync_closed_orders_from_mt5(config, strategy_name="Grid_Step")

                base.grid_pending_stop_log_context = {
                    "enabled": bool(params.get("v5_pending_pair_log_enabled", True)),
                    "v5_role": v5_role,
                    "grid_preview": (
                        gate_features.get("grid_preview")
                        if isinstance(gate_features, dict)
                        else None
                    ),
                }
                if steps_list is not None:
                    for step_val in steps_list:
                        consecutive_errors, last_error_code = _invoke_strategy_grid_step_logic(
                            config, consecutive_errors, step_val
                        )
                else:
                    consecutive_errors, last_error_code = _invoke_strategy_grid_step_logic(
                        config, consecutive_errors, None
                    )

                post_pending, post_positions = _snapshot_bot_orders_positions(sym, mag)
                new_pending = [t for t in post_pending if t not in pre_pending]
                new_positions = [t for t in post_positions if t not in pre_positions]

                if v5_role == "demo" and _v5_inverse_ipc_port_value(params) > 0:
                    _v5_demo_try_emit_demo_close_ipc(
                        params, sym, mag, post_positions, demo_copy_fill_ipc_state
                    )
                if (
                    v5_role == "demo"
                    and _v5_inverse_ipc_port_value(params) > 0
                    and _v5_param_bool(params, "v5_demo_push_copy_fill_ipc", True)
                ):
                    _cf_sync_post = (
                        demo_copy_fill_ipc_state.setdefault("sync_close_tickets", set())
                        if _v5_param_bool(params, "v5_demo_push_copy_close_ipc", True)
                        else None
                    )
                    _cf_fresh_post = _v5_demo_copy_fill_fresh_tickets_cross_cycle(
                        post_positions, demo_copy_fill_ipc_state
                    )
                    if _cf_fresh_post:
                        _cf_done_post = _v5_demo_emit_copy_fill_ipc_events(
                            config, params, sym, mag, _cf_fresh_post, _cf_sync_post
                        )
                        demo_copy_fill_ipc_state["announced"].update(_cf_done_post)

                if bool(params.get("v5_pending_pair_log_enabled", True)) and (
                    new_pending or new_positions
                ):
                    pair_snap = _collect_pending_stop_pair(sym, mag)
                    if pair_snap is not None:
                        gpr_log = (
                            gate_features.get("grid_preview")
                            if isinstance(gate_features, dict)
                            else None
                        )
                        _append_pending_stop_pair_daily_log(
                            {
                                "v5_role": v5_role,
                                "symbol": sym,
                                "magic": mag,
                                "new_pending_tickets": new_pending,
                                "new_position_tickets": new_positions,
                                "pending_count": len(post_pending),
                                "position_count": len(post_positions),
                                "grid_preview": gpr_log,
                                "pending_stop_pair": pair_snap,
                            }
                        )

                # Demo: ghi file inverse — khi vừa có lệnh mới + gate có grid_preview;
                # hoặc file chưa tồn tại nhưng MT5 đã có đủ cặp BUY_STOP+SELL_STOP (synthetic gpr).
                if v5_role == "demo" and isinstance(gate_features, dict):
                    path_inv = signal_relay.RELAY_DEMO_FILE
                    gpr = gate_features.get("grid_preview")
                    wrote = False
                    if (
                        (new_pending or new_positions)
                        and isinstance(gpr, dict)
                        and gpr.get("buy_price") is not None
                        and gpr.get("sell_price") is not None
                    ):
                        signal_relay.demo_write_inverse_relay_file(config, gate_features)
                        wrote = True
                    if not wrote and bool(
                        params.get("v5_demo_inverse_file_when_pair_and_missing_file", True)
                    ) and _v5_relay_demo_file_missing_or_bad(path_inv):
                        pair_snap_w = _collect_pending_stop_pair(sym, mag)
                        if pair_snap_w is not None:
                            step_w = (
                                float(steps_list[0])
                                if steps_list
                                else float(params.get("step", 5) or 5)
                            )
                            gpr_syn = _v5_synthetic_grid_preview_from_pair_snap(
                                pair_snap_w, step_w
                            )
                            if gpr_syn.get("buy_price") is not None:
                                gf_w = dict(gate_features)
                                gf_w["grid_preview"] = gpr_syn
                                signal_relay.demo_write_inverse_relay_file(config, gf_w)
                                print(
                                    f"📄 [V5 demo] Đã ghi {os.path.basename(path_inv)} từ cặp STOP trên MT5 "
                                    f"(file thiếu / rỗng / lỗi — live có thể đọc)."
                                )

                relay_sent = relay_early_sent
                relay_reason = relay_early_reason
                relay_zone = relay_early_zone
                relay_side = relay_early_side
                # Chỉ ghi relay khi kết_luận=đạt (giống publish sớm). Grid vẫn có thể đặt lệnh khi gate chặn điểm
                # (demo_mode) — không mirror lên live nếu không đủ điều kiện score.
                if v5_role == "demo" and bool(params.get("signal_relay_enabled", False)) and (
                    new_pending or new_positions
                ):
                    if gate_features and _v5_ket_luan_dat(gate_features, entry_thr):
                        _rid, rsn_ord = signal_relay.demo_try_publish_relay(
                            config,
                            gate_features,
                            relay_zone_points=float(params.get("relay_zone_points") or 200),
                            ttl_minutes=float(params.get("relay_signal_ttl_minutes") or 180),
                            verbose=False,
                        )
                        if _rid is not None:
                            relay_sent = True
                            relay_reason = rsn_ord
                            try:
                                ep = float(gate_features.get("current_signal_open_price") or 0)
                                relay_zone = signal_relay.price_zone_key(
                                    ep, float(params.get("relay_zone_points") or 200)
                                )
                                relay_side = str(
                                    gate_features.get("current_signal_type")
                                    or gate_features.get("signal_type")
                                    or ""
                                ).upper()
                            except (TypeError, ValueError):
                                pass
                        elif not relay_early_sent:
                            relay_reason = rsn_ord
                    elif not relay_early_sent:
                        relay_reason = "SKIP_RELAY_NOT_QUALIFIED"

                if v5_role == "live" and active_relay_id and (new_pending or new_positions):
                    signal_relay.relay_consume(active_relay_id, verbose=relay_verbose)

                rr_out = relay_reason
                if v5_role != "demo" and relay_reason == "NO_DEMO_ORDER":
                    rr_out = "NOT_DEMO_ROLE"

                _v5_try_emit_cycle_log(
                    {
                        "exit_kind": "normal",
                        "v5_role": v5_role,
                        "entry_thr": entry_thr,
                        "max_positions": config.get("max_positions", 5),
                        "pre_np": len(pre_pending),
                        "pre_npos": len(pre_positions),
                        "gate_reason": gate_reason,
                        "gate_features": gate_features or {},
                        "new_pending": new_pending,
                        "new_positions": new_positions,
                        "relay_enabled": bool(params.get("signal_relay_enabled", False)),
                        "relay_sent": relay_sent,
                        "relay_reason": rr_out,
                        "relay_zone": relay_zone,
                        "relay_side": relay_side or None,
                    },
                    params,
                )

                if not new_pending and not new_positions:
                    if not bool(params.get("v5_structured_log", True)) and bool(
                        params.get("v5_verbose_no_order_log", True)
                    ):
                        print(
                            "ℹ️ [V5] no new order | "
                            f"role={v5_role} score={gate_features.get('score')} pending="
                            f"{len(pre_pending)}/{len(post_pending)} pos={len(pre_positions)}/{len(post_positions)}"
                        )
                if v5_role == "live" and (new_pending or new_positions):
                    _mark_live_entry_now(sym, mag)
                    now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    record = {
                        "ts_utc": now_utc,
                        "role": v5_role,
                        "symbol": sym,
                        "magic": mag,
                        "demo_relay_id": gate_features.get("relay_id"),
                        "gate_reason": gate_reason,
                        "score": gate_features.get("score"),
                        "score_breakdown": gate_features.get("score_breakdown"),
                        "conditions": {
                            "min_gap_ok": gate_features.get("min_gap_ok"),
                            "min_gap_minutes": gate_features.get("min_gap_minutes"),
                            "same_direction_as_prev_signal": gate_features.get("same_direction_as_prev_signal"),
                            "signal_type": gate_features.get("signal_type"),
                            "current_signal_open_price": gate_features.get("current_signal_open_price"),
                            "current_signal_ts_source": gate_features.get("current_signal_ts_source"),
                            "prev_signal_open_price": gate_features.get("prev_signal_open_price"),
                            "prev_signal_source": gate_features.get("prev_signal_source"),
                            "state_history_source": gate_features.get("state_history_source"),
                            "signal_closed_merge_source": gate_features.get("signal_closed_merge_source"),
                            "preferred_direction": gate_features.get("preferred_direction"),
                            "sum_last_5_net_profit": gate_features.get("sum_last_5_net_profit"),
                            "sum_last_10_net_profit": gate_features.get("sum_last_10_net_profit"),
                            "win_count_last_5": gate_features.get("win_count_last_5"),
                            "win_rate_last_10": gate_features.get("win_rate_last_10"),
                            "loss_streak": gate_features.get("loss_streak"),
                            "last_trade_result": gate_features.get("last_trade_result"),
                            "current_open_below_prev_open": gate_features.get("current_open_below_prev_open"),
                            "reverse_direction_from_prev_signal": gate_features.get(
                                "reverse_direction_from_prev_signal"
                            ),
                            "blocked": gate_features.get("blocked"),
                            "block_reason": gate_features.get("block_reason"),
                        },
                        "new_pending_tickets": new_pending,
                        "new_position_tickets": new_positions,
                        "pending_count_after": len(post_pending),
                        "position_count_after": len(post_positions),
                    }
                    _append_live_entry_log(record)
                    print(
                        f"📝 [V5 Live] logged entry event: pending={new_pending} positions={new_positions} "
                        f"score={gate_features.get('score')} -> {LIVE_LOG_FILE}"
                    )

                loop_count += 1
                if loop_count % 30 == 0:
                    pos = mt5.positions_get(symbol=sym, magic=mag) or []
                    ords = mt5.orders_get(symbol=sym) or []
                    ords = [o for o in ords if o.magic == mag]
                    tick = mt5.symbol_info_tick(sym)
                    spread = (tick.ask - tick.bid) if tick else 0
                    steps_info = steps_list if steps_list else "1"
                    now_hb = time.monotonic()
                    last_hb = getattr(run, "_v5_heartbeat_mono", None)
                    avg_txt = ""
                    if isinstance(last_hb, (int, float)) and (now_hb - float(last_hb)) > 0.05:
                        avg_txt = f" | avg_loop≈{(now_hb - float(last_hb)) / 30.0:.2f}s (30 vòng)"
                    run._v5_heartbeat_mono = now_hb
                    print(
                        f"🔄 Grid Step V5 | loop_interval={_v5_loop_interval_log_repr(loop_interval_seconds)}{avg_txt} | "
                        f"Steps: {steps_info} | Positions: {len(pos)} | "
                        f"Pending: {len(ords)} | Spread: {spread:.2f} | Loop #{loop_count}"
                    )

                if consecutive_errors >= 5:
                    error_msg = base.get_mt5_error_message(last_error_code)
                    msg = f"⚠️ [Grid Step V5] 5 lỗi liên tiếp. Last: {error_msg}. Tạm dừng 2 phút..."
                    print(msg)
                    base.send_telegram(msg, config.get("telegram_token"), config.get("telegram_chat_id"))
                    time.sleep(120)
                    consecutive_errors = 0
                    continue

                time.sleep(loop_interval_seconds)
        except KeyboardInterrupt:
            print("🛑 Grid Step Bot V5 Stopped")
        finally:
            mt5.shutdown()


if __name__ == "__main__":
    run()
