# 📊 Dashboard Auto-Detection Guide

## Tổng quan

Dashboard và `update_db.py` đã được cập nhật để **tự động phát hiện** các bot mới từ database, không cần hardcode trong code.

## Cách thêm bot mới

### Bước 1: Tạo bot và config file

1. Tạo file bot mới (ví dụ: `strategy_6_new_bot.py`)
2. Tạo config file tương ứng (ví dụ: `configs/config_6.json`)
3. Đảm bảo bot log orders với `strategy_name` đúng vào database

### Bước 2: Thêm vào `strategy_configs.json` (cho update_db.py)

Mở file `XAU_M1/strategy_configs.json` và thêm entry mới:

```json
{
    "Strategy_6_New_Bot": "configs/config_6.json",
    ...
}
```

**Lưu ý:** `strategy_name` trong JSON phải khớp với tên được sử dụng trong bot khi log orders (ví dụ: `db.log_order(..., "Strategy_6_New_Bot", ...)`).

### Bước 3: (Tùy chọn) Thêm vào `display_order.json` (cho dashboard)

Nếu muốn kiểm soát thứ tự hiển thị trong dashboard, mở file `XAU_M1/display_order.json` và thêm strategy name vào list:

```json
{
    "strategy_order": [
        "Strategy_1_Trend_HA",
        "Strategy_1_Trend_HA_V2",
        "Strategy_6_New_Bot",  // Thêm vào đây
        ...
    ]
}
```

**Lưu ý:** Nếu không thêm vào `display_order.json`, bot mới sẽ tự động xuất hiện trong dashboard và được sắp xếp theo net profit (giảm dần).

## Cách hoạt động

### Dashboard (`dashboard.py`)

1. **Tự động phát hiện:** Query database để lấy tất cả `strategy_name` distinct
2. **Tự động format:** Tên strategy được format tự động (ví dụ: `Strategy_1_Trend_HA_V2` → `1 Trend HA V2`)
3. **Tự động sắp xếp:**
   - Nếu có `display_order.json`: Sắp xếp theo thứ tự trong file
   - Nếu không: Sắp xếp theo net profit (giảm dần), sau đó theo số trades

### Update DB (`update_db.py`)

1. **Tự động phát hiện:** 
   - Đầu tiên tìm `strategy_configs.json`
   - Nếu không có, tự động scan thư mục `configs/` và infer strategy name từ filename
   - Nếu vẫn không có, sử dụng default mapping
2. **Xử lý:** Chỉ xử lý các strategies có config file tồn tại

## Files liên quan

- `dashboard.py`: Dashboard chính, tự động phát hiện strategies từ database
- `update_db.py`: Script cập nhật profit cho closed orders, tự động phát hiện từ `strategy_configs.json`
- `display_order.json`: (Tùy chọn) Định nghĩa thứ tự hiển thị trong dashboard
- `strategy_configs.json`: (Tùy chọn) Mapping strategy names với config files cho `update_db.py`

## Ví dụ

### Thêm bot mới: Strategy_1_Trend_HA_V2.1

1. Bot đã tạo: `strategy_1_trend_ha_v2.1.py`
2. Config đã tạo: `configs/config_1_v2.1.json`
3. Bot log với name: `"Strategy_1_Trend_HA_V2.1"`

**Cập nhật `strategy_configs.json`:**
```json
{
    "Strategy_1_Trend_HA_V2.1": "configs/config_1_v2.1.json"
}
```

**Cập nhật `display_order.json` (tùy chọn):**
```json
{
    "strategy_order": [
        "Strategy_1_Trend_HA",
        "Strategy_1_Trend_HA_V2",
        "Strategy_1_Trend_HA_V2.1",  // Thêm vào đây
        ...
    ]
}
```

Sau đó, dashboard sẽ tự động hiển thị bot mới và `update_db.py` sẽ tự động cập nhật profit cho bot này!

