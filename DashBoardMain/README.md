# DashBoardMain – Dashboard dùng chung cho mọi bot

Dashboard một trang với **nhiều tab**: mỗi tab là một bot, click vào tab sẽ load đúng database của bot đó.

## Cấu hình

Mở **`config.json`** và khai báo **`databases`** (mỗi key = tên tab, value = đường dẫn `trades.db`):

```json
{
    "databases": {
        "XAU_M1": "../XAU_M1/trades.db",
        "BTC_M1": "../BTC_M1/trades.db",
        "EUR_M1_REAL": "../EUR_M1_REAL/trades.db"
    },
    "default": "XAU_M1"
}
```

- **Tên tab** (key): hiển thị trên dashboard (vd: XAU_M1, BTC_M1).
- **Đường dẫn** (value): tuyệt đối hoặc tương đối so với thư mục `DashBoardMain`.
- **default**: tab được chọn khi mở trang lần đầu.

Nếu không dùng `databases` mà chỉ có **`db_path`** (đường dẫn một file), dashboard sẽ có một tab tên "Default".

## Chạy dashboard

```bash
cd DashBoardMain
python dashboard.py
```

Mặc định chạy tại: **http://127.0.0.1:5000**

## Tính năng

- **Overview:** Tổng quan lệnh, lợi nhuận, win rate, theo từng strategy.
- **Lọc thời gian:** 1 / 3 / 5 / 7 / 30 ngày, All Time, hoặc **Từ ngày → Đến ngày**.
- **Signals Analysis:** Danh sách signal, so khớp order, Export Signals/Orders.
- **Analyze signal:** Phân tích từng signal (không cần MT5).
- **Export:** CSV Orders và Signals.

**Lưu ý:** Trong chế độ dùng chung (DashBoardMain), **Check MT5** trên trang Signals sẽ không dùng được (cần chạy dashboard từ đúng thư mục bot có kết nối MT5).

## Cấu trúc thư mục

```
DashBoardMain/
  config.json       # Khai báo db_path
  dashboard.py      # Ứng dụng Flask
  display_order.json  # (Tùy chọn) Thứ tự hiển thị strategy
  README.md
  templates/
    index.html
    signals.html
```
