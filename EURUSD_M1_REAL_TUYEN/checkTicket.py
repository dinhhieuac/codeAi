# -*- coding: utf-8 -*-
"""
checkTicket.py - Nhập ticket -> tra cứu giao dịch và scroll chart MT5 tới thời điểm mở lệnh.

Cách dùng:
  python checkTicket.py 12345678
  python checkTicket.py 12345678 --no-scroll   # Chỉ tra cứu, không gửi phím
  python checkTicket.py
  (sẽ hỏi nhập ticket)

Tự động scroll: Sau khi tìm được ticket, script đưa MT5 lên trước và gửi Enter -> ngày/giờ -> Enter
để chart nhảy tới vị trí mở lệnh. Cần mở sẵn chart đúng symbol (vd XAUUSD) khung M1.
Cài thêm: pip install pygetwindow pyautogui
"""

import MetaTrader5 as mt5
import os
import sys
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from utils import load_config, connect_mt5


def find_position_by_ticket(ticket):
    """Tìm lệnh đang mở theo ticket."""
    positions = mt5.positions_get(ticket=int(ticket))
    if not positions:
        return None
    return positions[0]


def find_deal_by_ticket(ticket):
    """Tìm deal trong lịch sử theo ticket (deal ticket hoặc position ticket).
    Trả về (deal_first, list_deals_của_position) để có đủ thông tin mở/đóng và profit.
    """
    ticket_int = int(ticket)
    # Thử lấy theo deal ticket (số hiển thị trong tab History)
    deals = mt5.history_deals_get(ticket=ticket_int)
    if deals and len(deals) > 0:
        first = deals[0]
        # Lấy tất cả deals của position này (cả IN và OUT) để có profit đóng lệnh
        pos_id = first.position_id
        all_for_pos = mt5.history_deals_get(position=pos_id) if pos_id else [first]
        return first, list(all_for_pos) if all_for_pos else [first]

    # Thử lấy deals gần đây và filter theo position_id / order (user có thể nhập position ticket)
    to_dt = datetime.utcnow()
    from_dt = to_dt - timedelta(days=365)
    all_deals = mt5.history_deals_get(from_dt, to_dt)
    if not all_deals:
        return None, []
    for d in all_deals:
        if d.ticket == ticket_int or d.position_id == ticket_int or d.order == ticket_int:
            pos_id = d.position_id
            all_for_pos = mt5.history_deals_get(position=pos_id) if pos_id else [d]
            return d, list(all_for_pos) if all_for_pos else [d]
    return None, []


def format_time(ts):
    """Chuyển timestamp MT5 sang chuỗi đọc được."""
    if ts is None:
        return "N/A"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def format_time_mt5_chart(ts):
    """Định dạng thời gian để gõ vào chart MT5 (Enter -> gõ -> Enter). Format: DD.MM.YY HH:MM"""
    if ts is None:
        return ""
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d.%m.%y %H:%M")  # VD: 25.02.26 22:18
    except Exception:
        return ""


def scroll_chart_to_time(symbol, open_ts):
    """
    Đưa MT5 lên trước và gửi phím: Enter -> gõ ngày/giờ (DD.MM.YY HH:MM) -> Enter
    để chart nhảy tới thời điểm mở lệnh. Chart phải đang mở đúng symbol (vd M1).
    """
    date_str = format_time_mt5_chart(open_ts)
    if not date_str:
        print("  ⚠ Không có thời gian để gửi.")
        return False
    try:
        import pygetwindow as gw
        import pyautogui
    except ImportError:
        print("  ⚠ Để tự động scroll chart, cài: pip install pygetwindow pyautogui")
        print("  📋 Hoặc làm tay: Trên chart MT5 nhấn Enter, gõ:", date_str, ", rồi Enter.")
        return False

    # Tìm cửa sổ MT5 (title thường chứa "MetaTrader" hoặc "terminal")
    mt5_win = None
    for w in gw.getAllWindows():
        if not w.visible or not w.title:
            continue
        t = w.title.lower()
        if "metatrader" in t or "terminal" in t or "mt5" in t:
            mt5_win = w
            break
    if not mt5_win:
        print("  ⚠ Không tìm thấy cửa sổ MetaTrader 5. Mở MT5 và thử lại.")
        print("  📋 Làm tay: Trên chart", symbol, "M1 nhấn Enter, gõ:", date_str, ", rồi Enter.")
        return False

    try:
        mt5_win.activate()
        import time
        time.sleep(0.6)  # Đợi chart focus
        pyautogui.press("enter")
        time.sleep(0.15)
        pyautogui.typewrite(date_str, interval=0.03)
        time.sleep(0.1)
        pyautogui.press("enter")
        print("  ✅ Đã gửi phím tới MT5. Chart sẽ nhảy tới", date_str)
        return True
    except Exception as e:
        print("  ⚠ Gửi phím lỗi:", e)
        print("  📋 Làm tay: Trên chart", symbol, "M1 nhấn Enter, gõ:", date_str, ", rồi Enter.")
        return False


def print_position_info(pos):
    """In thông tin position đang mở."""
    print("\n" + "=" * 60)
    print("  LỆNH ĐANG MỞ (Position)")
    print("=" * 60)
    print(f"  Ticket:      {pos.ticket}")
    print(f"  Symbol:     {pos.symbol}")
    print(f"  Loại:       {'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL'}")
    print(f"  Khối lượng: {pos.volume}")
    print(f"  Giá mở:     {pos.price_open}")
    print(f"  SL:         {pos.sl}")
    print(f"  TP:         {pos.tp}")
    print(f"  Thời gian:  {format_time(pos.time)}")
    profit = pos.profit + pos.swap + (getattr(pos, 'commission', 0) or 0)
    print(f"  Profit:     {profit:.2f}")
    print("=" * 60)


def print_deal_info(deal, deals_of_position=None):
    """In thông tin deal đã đóng. Nếu có deals_of_position thì tính đúng Profit từ deal đóng (DEAL_ENTRY_OUT)."""
    # Một position có 2 deals: ENTRY_IN (mở, profit=0) và ENTRY_OUT (đóng, profit thực)
    if deals_of_position:
        total_profit = sum(getattr(d, 'profit', 0) or 0 for d in deals_of_position)
        total_commission = sum(getattr(d, 'commission', 0) or 0 for d in deals_of_position)
        total_swap = sum(getattr(d, 'swap', 0) or 0 for d in deals_of_position)
        deal_in = next((d for d in deals_of_position if d.entry == mt5.DEAL_ENTRY_IN), None)
        deal_out = next((d for d in deals_of_position if d.entry == mt5.DEAL_ENTRY_OUT), None)
        # Dùng deal đóng để hiển thị profit; nếu không có thì dùng deal đầu
        d_show = deal_out or deal_in or deal
    else:
        total_profit = getattr(deal, 'profit', 0) or 0
        total_commission = getattr(deal, 'commission', 0) or 0
        total_swap = getattr(deal, 'swap', 0) or 0
        deal_in = deal if getattr(deal, 'entry', None) == mt5.DEAL_ENTRY_IN else None
        deal_out = deal if getattr(deal, 'entry', None) == mt5.DEAL_ENTRY_OUT else None
        d_show = deal

    print("\n" + "=" * 60)
    print("  GIAO DỊCH ĐÃ ĐÓNG (Deal)")
    print("=" * 60)
    print(f"  Deal ticket:  {d_show.ticket}")
    print(f"  Order ticket: {d_show.order}")
    print(f"  Position ID:  {d_show.position_id}")
    print(f"  Symbol:       {d_show.symbol}")
    print(f"  Loại:         {'BUY' if d_show.type == mt5.DEAL_TYPE_BUY else 'SELL'}")
    print(f"  Khối lượng:   {d_show.volume}")
    if deal_in and deal_out:
        print(f"  Giá mở:       {deal_in.price}  (thời gian: {format_time(deal_in.time)})")
        print(f"  Giá đóng:     {deal_out.price}  (thời gian: {format_time(deal_out.time)})")
    else:
        print(f"  Giá:          {d_show.price}")
        print(f"  Thời gian:    {format_time(d_show.time)}")
    print(f"  Profit:       {total_profit:.2f}")
    print(f"  Commission:   {total_commission:.2f}")
    print(f"  Swap:         {total_swap:.2f}")
    print(f"  ---")
    print(f"  Tổng P&L:     {total_profit + total_commission + total_swap:.2f}")
    print("=" * 60)


def print_instructions(symbol, open_time_str, ticket, is_position=True):
    """In hướng dẫn scroll tới giao dịch trên MT5."""
    mt5_date_str = ""  # Sẽ set bên main nếu cần
    print("\n  📌 Cách xem giao dịch này trên MT5:")
    print("  ----------------------------------------")
    if is_position:
        print("  • Tab [Trade]: Tìm ticket", ticket, "trong danh sách lệnh đang mở.")
    print("  • Tab [History]: Tìm ticket", ticket, "(hoặc Deal #)", "trong lịch sử.")
    print("  • Chart: Mở chart", symbol, "khung M1, kéo trục thời gian về:", open_time_str)
    print("  • Hoặc: Trên chart nhấn Enter -> gõ ngày/giờ (DD.MM.YY HH:MM) -> Enter.")
    print("  ----------------------------------------\n")


def main():
    # Ticket từ tham số dòng lệnh hoặc nhập tay
    if len(sys.argv) >= 2:
        try:
            ticket_str = sys.argv[1].strip()
            ticket = int(ticket_str)
        except ValueError:
            print("❌ Ticket phải là số. Ví dụ: python checkTicket.py 12345678")
            return
    else:
        ticket_str = input("Nhập ticket (số): ").strip()
        if not ticket_str:
            print("❌ Chưa nhập ticket.")
            return
        try:
            ticket = int(ticket_str)
        except ValueError:
            print("❌ Ticket phải là số.")
            return

    # Config và kết nối MT5
    config_path = os.path.join(SCRIPT_DIR, "configs", "config_tuyen.json")
    if not os.path.exists(config_path):
        config_path = os.path.join(SCRIPT_DIR, "configs", "config_template.json")
    config = load_config(config_path)
    if not config:
        print("❌ Không đọc được config.")
        return

    if not connect_mt5(config):
        print("❌ Không kết nối được MT5. Kiểm tra terminal đang mở và config.")
        return

    # Ưu tiên tìm trong position đang mở
    pos = find_position_by_ticket(ticket)
    if pos:
        print_position_info(pos)
        print_instructions(pos.symbol, format_time(pos.time), ticket, is_position=True)
        do_scroll = "--no-scroll" not in sys.argv
        if do_scroll:
            scroll_chart_to_time(pos.symbol, pos.time)
        mt5.shutdown()
        return

    # Tìm trong history deals
    deal, deals_list = find_deal_by_ticket(ticket)
    if deal:
        # Thời gian mở lệnh để hướng dẫn scroll chart (ưu tiên deal IN)
        deal_in = next((d for d in deals_list if d.entry == mt5.DEAL_ENTRY_IN), None) if deals_list else None
        open_ts = deal_in.time if deal_in else deal.time
        open_time_str = format_time(open_ts)
        print_deal_info(deal, deals_of_position=deals_list if deals_list else None)
        print_instructions(deal.symbol, open_time_str, ticket, is_position=False)
        do_scroll = "--no-scroll" not in sys.argv
        if do_scroll:
            scroll_chart_to_time(deal.symbol, open_ts)
        mt5.shutdown()
        return

    print("\n❌ Không tìm thấy giao dịch với ticket:", ticket)
    print("   Kiểm tra lại số ticket (tab Trade hoặc History trong MT5).")
    mt5.shutdown()


if __name__ == "__main__":
    main()
