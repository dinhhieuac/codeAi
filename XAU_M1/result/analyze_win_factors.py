# -*- coding: utf-8 -*-
"""
Phân tích kết quả bot XAU_M1 - Tìm các yếu tố làm nên chiến thắng (Win factors).
Chạy: python analyze_win_factors.py
"""
import os
import sys
import json
import csv
import glob
from datetime import datetime
from collections import defaultdict

# Allow run from repo root or from result folder
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

def parse_indicators(ind_str):
    """Parse Signal Indicators JSON string."""
    if not ind_str or ind_str.strip() == "":
        return {}
    try:
        s = ind_str.replace('""', '"')
        return json.loads(s)
    except Exception:
        return {}

def get_session(hour_utc):
    """Map hour (0-23) to session name. Assume server time ~ UTC+0 or UTC+2."""
    if 0 <= hour_utc < 8:
        return "Asian"
    if 8 <= hour_utc < 13:
        return "London_Open"
    if 13 <= hour_utc < 16:
        return "London_NY_Overlap"
    if 16 <= hour_utc < 22:
        return "NY"
    return "Late_NY_Asian"

def load_csv_results(result_dir):
    """Load all orders_export_*.csv in result dir. Returns list of dicts."""
    pattern = os.path.join(result_dir, "orders_export_*.csv")
    files = glob.glob(pattern)
    all_rows = []
    for f in files:
        name = os.path.basename(f)
        # Strategy name: orders_export_Strategy_1_Trend_HA_20260303_115611.csv -> Strategy_1_Trend_HA
        base = name.replace("orders_export_", "").replace(".csv", "")
        parts = base.rsplit("_", 2)
        strategy = parts[0] if len(parts) >= 3 else base
        with open(f, "r", encoding="utf-8", newline="") as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                row["_strategy"] = strategy
                row["_file"] = name
                all_rows.append(row)
    return all_rows

def safe_float(v, default=None):
    try:
        return float(v) if v else default
    except (TypeError, ValueError):
        return default

def analyze_one_bot(closed, out):
    """Phan tich chi tiet cho 1 danh sach lenh (1 bot)."""
    wins = [r for r in closed if r.get("Win/Loss") == "Win"]
    losses = [r for r in closed if r.get("Win/Loss") == "Loss"]
    n_w, n_l = len(wins), len(losses)
    total = n_w + n_l
    wr = 100.0 * n_w / total if total else 0
    out("  Tong: {} lenh (Win: {}, Loss: {}), Win rate: {:.1f}%".format(total, n_w, n_l, wr))

    # RSI
    rsi_wins = []
    rsi_losses = []
    for r in closed:
        ind = parse_indicators(r.get("Signal Indicators", ""))
        rsi = safe_float(ind.get("rsi"))
        if rsi is not None:
            (rsi_wins if r.get("Win/Loss") == "Win" else rsi_losses).append(rsi)
    if rsi_wins or rsi_losses:
        out("  RSI (luc vao lenh):")
        if rsi_wins:
            out("    Win  - TB: {:.2f}, min: {:.2f}, max: {:.2f}, n={}".format(
                sum(rsi_wins)/len(rsi_wins), min(rsi_wins), max(rsi_wins), len(rsi_wins)))
        if rsi_losses:
            out("    Loss - TB: {:.2f}, min: {:.2f}, max: {:.2f}, n={}".format(
                sum(rsi_losses)/len(rsi_losses), min(rsi_losses), max(rsi_losses), len(rsi_losses)))
        if rsi_wins and rsi_losses:
            diff = (sum(rsi_wins)/len(rsi_wins)) - (sum(rsi_losses)/len(rsi_losses))
            out("    => Chenh lech Win - Loss: {:+.2f}".format(diff))

    # ADX
    adx_wins = []
    adx_losses = []
    for r in closed:
        ind = parse_indicators(r.get("Signal Indicators", ""))
        adx = safe_float(ind.get("adx"))
        if adx is not None:
            (adx_wins if r.get("Win/Loss") == "Win" else adx_losses).append(adx)
    if adx_wins or adx_losses:
        out("  ADX:")
        if adx_wins:
            out("    Win  - TB: {:.2f}, min: {:.2f}, max: {:.2f}, n={}".format(
                sum(adx_wins)/len(adx_wins), min(adx_wins), max(adx_wins), len(adx_wins)))
        if adx_losses:
            out("    Loss - TB: {:.2f}, min: {:.2f}, max: {:.2f}, n={}".format(
                sum(adx_losses)/len(adx_losses), min(adx_losses), max(adx_losses), len(adx_losses)))
        if adx_wins and adx_losses:
            diff = (sum(adx_wins)/len(adx_wins)) - (sum(adx_losses)/len(adx_losses))
            out("    => Chenh lech Win - Loss: {:+.2f}".format(diff))

    # ATR
    atr_wins = []
    atr_losses = []
    for r in closed:
        ind = parse_indicators(r.get("Signal Indicators", ""))
        atr = safe_float(ind.get("atr"))
        if atr is not None:
            (atr_wins if r.get("Win/Loss") == "Win" else atr_losses).append(atr)
    if atr_wins or atr_losses:
        out("  ATR:")
        if atr_wins:
            out("    Win  - TB: {:.2f}, min: {:.2f}, max: {:.2f}, n={}".format(
                sum(atr_wins)/len(atr_wins), min(atr_wins), max(atr_wins), len(atr_wins)))
        if atr_losses:
            out("    Loss - TB: {:.2f}, min: {:.2f}, max: {:.2f}, n={}".format(
                sum(atr_losses)/len(atr_losses), min(atr_losses), max(atr_losses), len(atr_losses)))
        if atr_wins and atr_losses:
            diff = (sum(atr_wins)/len(atr_wins)) - (sum(atr_losses)/len(atr_losses))
            out("    => Chenh lech Win - Loss: {:+.2f}".format(diff))

    # Session
    session_win = defaultdict(int)
    session_loss = defaultdict(int)
    for r in closed:
        ot = r.get("Open Time", r.get("Signal Timestamp", ""))
        try:
            if " " in ot:
                dt = datetime.strptime(ot[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
            else:
                continue
            sess = get_session(dt.hour)
            if r.get("Win/Loss") == "Win":
                session_win[sess] += 1
            else:
                session_loss[sess] += 1
        except Exception:
            pass
    if session_win or session_loss:
        out("  Session (gio vao lenh):")
        all_sessions = sorted(set(session_win.keys()) | set(session_loss.keys()))
        for sess in all_sessions:
            w, l = session_win[sess], session_loss[sess]
            t = w + l
            wr_s = 100.0 * w / t if t else 0
            out("    {}: Win={}, Loss={}, Win rate={:.0f}%".format(sess, w, l, wr_s))

    # Entry BUY/SELL
    buy_win = sum(1 for r in closed if r.get("Order Type") == "BUY" and r.get("Win/Loss") == "Win")
    buy_loss = sum(1 for r in closed if r.get("Order Type") == "BUY" and r.get("Win/Loss") == "Loss")
    sell_win = sum(1 for r in closed if r.get("Order Type") == "SELL" and r.get("Win/Loss") == "Win")
    sell_loss = sum(1 for r in closed if r.get("Order Type") == "SELL" and r.get("Win/Loss") == "Loss")
    out("  Entry:")
    if buy_win + buy_loss > 0:
        out("    BUY:  Win={}, Loss={}, Win rate={:.1f}%".format(buy_win, buy_loss, 100.0*buy_win/(buy_win+buy_loss)))
    if sell_win + sell_loss > 0:
        out("    SELL: Win={}, Loss={}, Win rate={:.1f}%".format(sell_win, sell_loss, 100.0*sell_win/(sell_win+sell_loss)))

def main():
    report_lines = []
    def out(s=""):
        report_lines.append(s)
        try:
            print(s)
        except UnicodeEncodeError:
            print(s.encode("ascii", "replace").decode("ascii"))

    result_dir = SCRIPT_DIR
    rows = load_csv_results(result_dir)
    if not rows:
        out("No CSV files found in: " + result_dir)
        return

    closed_all = [r for r in rows if r.get("Win/Loss") in ("Win", "Loss") and r.get("Status") not in ("Open", "")]
    if not closed_all:
        closed_all = [r for r in rows if r.get("Win/Loss") in ("Win", "Loss")]

    # Group by strategy (moi bot 1 nhom)
    by_strategy = defaultdict(list)
    for r in closed_all:
        st = r.get("_strategy", r.get("Strategy", "?"))
        by_strategy[st].append(r)

    out("=" * 80)
    out("PHAN TICH KET QUA BOT XAU_M1 - THEO TUNG BOT (CHIEN THUAT)")
    out("=" * 80)
    out("")

    for strategy_name in sorted(by_strategy.keys()):
        closed = by_strategy[strategy_name]
        out("-" * 80)
        out("BOT: {}".format(strategy_name))
        out("-" * 80)
        analyze_one_bot(closed, out)
        out("")

    out("=" * 80)
    out("Tong hop: {} lenh tu {} bot. Bao cao day du: WIN_FACTORS_REPORT.md".format(
        len(closed_all), len(by_strategy)))
    out("=" * 80)

    report_path = os.path.join(SCRIPT_DIR, "win_factors_analysis.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print("\nReport saved: " + report_path)


if __name__ == "__main__":
    main()
