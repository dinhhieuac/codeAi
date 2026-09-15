#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Interactive Launcher for XAU_M1_REAL Strategies
"""
import os
import sys
import subprocess

FILES = [
    ("1", "strategy_1_trend_ha_v1.1.py", "Heiken Ashi Trend v1.1"),
    ("2", "strategy_1_trend_ha_v2.1.py", "Heiken Ashi Trend v2.1"),
    ("3", "strategy_1_trend_ha_v2.py",   "Heiken Ashi Trend v2.0"),
    ("4", "strategy_1_trend_ha_v3.py",   "Heiken Ashi Trend v3.0"),
    ("5", "strategy_1_trend_ha.py",      "Heiken Ashi Trend (Original)"),
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def print_menu():
    print("\n" + "=" * 65)
    print("      🚀 XAU_M1_REAL - TRÌNH KHỞI CHẠY BOT GIAO DỊCH")
    print("=" * 65)
    print(f"📂 Thư mục bot: {BASE_DIR}")
    print(f"🐍 Python:     {sys.executable}")
    print("=" * 65)
    for key, filename, desc in FILES:
        print(f" [{key}] {filename:<32} ({desc})")
    print("-" * 65)
    print(" [6] Chạy TẤT CẢ 5 chiến lược trên (Mở từng cửa sổ riêng)")
    print(" [7] Chạy Update DB (update_db.py)")
    print(" [8] Chạy Dashboard (dashboard.py)")
    print("-" * 65)
    print(" [0] Thoát")
    print("=" * 65)

def launch_file(filename, title=None):
    script_path = os.path.join(BASE_DIR, filename)
    if not os.path.isfile(script_path):
        print(f"❌ Không tìm thấy file: {script_path}")
        return
    
    cmd_title = title or f"XAU Bot - {filename}"
    print(f"▶️ Đang khởi chạy {filename} trong cửa sổ riêng...")
    
    # Windows: Launch in a separate command window so output is visible
    cmd = f'start "{cmd_title}" cmd /k "cd /d "{BASE_DIR}" && "{sys.executable}" "{script_path}""'
    subprocess.Popen(cmd, shell=True)

def main():
    while True:
        print_menu()
        choice = input("\n👉 Nhập lựa chọn của bạn [0-8]: ").strip()
        
        if choice == "0":
            print("Tạm biệt!")
            sys.exit(0)
        elif choice in ["1", "2", "3", "4", "5"]:
            idx = int(choice) - 1
            filename, desc = FILES[idx][1], FILES[idx][2]
            launch_file(filename, f"XAU Bot - {desc}")
        elif choice == "6":
            for _, filename, desc in FILES:
                launch_file(filename, f"XAU Bot - {desc}")
        elif choice == "7":
            launch_file("update_db.py", "XAU Bot - Update DB")
        elif choice == "8":
            launch_file("dashboard.py", "XAU Bot - Dashboard")
        else:
            print("❌ Lựa chọn không hợp lệ! Vui lòng nhập số từ 0 đến 8.")
            continue
        
        sub = input("\n[1] Quay lại Menu | [0] Thoát: ").strip()
        if sub == "0":
            print("Tạm biệt!")
            break

if __name__ == "__main__":
    main()
