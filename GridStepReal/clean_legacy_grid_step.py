"""
Kiểm tra / xóa dữ liệu legacy strategy_name = 'Grid_Step' trong DB.
Dashboard chỉ hiển thị strategy có data; nếu từng chạy bot ở chế độ legacy (chỉ "step", không "steps")
thì sẽ có bản ghi 'Grid_Step' → tab "Grid_Step" vẫn xuất hiện dù giờ bạn chỉ dùng Grid_Step_5.0, Grid_Step_200.0.

Cách chạy:
  python clean_legacy_grid_step.py           # chỉ đếm và in ra
  python clean_legacy_grid_step.py --delete  # xóa hẳn bản ghi strategy_name = 'Grid_Step'
"""
import os
import sys
import sqlite3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "trades.db")

LEGACY_NAME = "Grid_Step"


def main():
    do_delete = len(sys.argv) > 1 and sys.argv[1].strip() == "--delete"
    if not os.path.exists(DB_PATH):
        print(f"DB không tồn tại: {DB_PATH}")
        return
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM orders WHERE strategy_name = ?",
        (LEGACY_NAME,),
    )
    n_orders = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM grid_pending_orders WHERE strategy_name = ?",
        (LEGACY_NAME,),
    )
    n_pending = cur.fetchone()[0]

    print(f"Strategy legacy '{LEGACY_NAME}' trong DB:")
    print(f"  orders: {n_orders}")
    print(f"  grid_pending_orders: {n_pending}")

    if n_orders == 0 and n_pending == 0:
        print("Không có dữ liệu legacy. Tab 'Grid_Step' có thể do DB khác hoặc cache.")
        conn.close()
        return

    if do_delete:
        cur.execute("DELETE FROM orders WHERE strategy_name = ?", (LEGACY_NAME,))
        deleted_orders = cur.rowcount
        cur.execute("DELETE FROM grid_pending_orders WHERE strategy_name = ?", (LEGACY_NAME,))
        deleted_pending = cur.rowcount
        conn.commit()
        print(f"\nĐã xóa: orders={deleted_orders}, grid_pending_orders={deleted_pending}")
        print("Refresh dashboard sẽ không còn tab 'Grid_Step'.")
    else:
        print("\nChạy với --delete để xóa các bản ghi này (tab 'Grid_Step' sẽ biến mất sau khi refresh dashboard).")

    conn.close()


if __name__ == "__main__":
    main()
