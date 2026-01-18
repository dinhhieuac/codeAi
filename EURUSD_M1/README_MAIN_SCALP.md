# 🚀 Hướng Dẫn Sử Dụng: mainScalpSideway.py

## 📋 Tổng Quan

File `mainScalpSideway.py` dùng để chạy **tất cả các bot Scalp Sideway** cùng lúc với các config khác nhau.

---

## 🎯 Cách Sử Dụng

### **Chạy Tất Cả Bots:**

```bash
python mainScalpSideway.py
```

**Bot sẽ tự động:**
- ✅ Load tất cả config files trong `configs/`
- ✅ Khởi động từng bot với config tương ứng
- ✅ Monitor các bots đang chạy
- ✅ Hiển thị thông báo nếu bot nào dừng

---

## 📊 Danh Sách Bots Được Chạy

Mặc định, file sẽ chạy các bots sau:

1. **XAUUSD** - `configs/scalp_sideway_xau.json`
2. **EURUSD** - `configs/scalp_sideway_eur.json`
3. **BTCUSD** - `configs/scalp_sideway_btc.json`

---

## ⚙️ Tùy Chỉnh

### **Thêm Bot Mới:**

Mở file `mainScalpSideway.py` và thêm config vào list:

```python
configs = [
    os.path.join(base_dir, "configs", "scalp_sideway_xau.json"),
    os.path.join(base_dir, "configs", "scalp_sideway_eur.json"),
    os.path.join(base_dir, "configs", "scalp_sideway_btc.json"),
    os.path.join(base_dir, "configs", "scalp_sideway_eth.json"),  # Thêm mới
]
```

### **Bỏ Bot:**

Xóa dòng config tương ứng khỏi list.

---

## 📝 Output Mẫu

```
================================================================================
🚀 Starting Scalp Sideway Bots...
================================================================================
📂 Execution Directory: /path/to/EURUSD_M1
🤖 Bot Script: /path/to/EURUSD_M1/scalp_sideway.py
📋 Config Files: 3
================================================================================

   [1/3] ▶️ Launching bot với config: scalp_sideway_xau.json
   [2/3] ▶️ Launching bot với config: scalp_sideway_eur.json
   [3/3] ▶️ Launching bot với config: scalp_sideway_btc.json

================================================================================
✅ 3 bot(s) đang chạy!
================================================================================
📊 Danh sách bots đang chạy:
   1. scalp_sideway_xau.json (PID: 12345)
   2. scalp_sideway_eur.json (PID: 12346)
   3. scalp_sideway_btc.json (PID: 12347)

⚠️  Nhấn Ctrl+C để dừng tất cả bots.
================================================================================
```

---

## 🛑 Dừng Bots

### **Cách 1: Nhấn Ctrl+C**
- Tất cả bots sẽ được dừng gracefully
- Main process sẽ terminate tất cả subprocesses

### **Cách 2: Kill Process**
```bash
# Tìm PID của main process
ps aux | grep mainScalpSideway

# Kill process
kill <PID>
```

---

## 🔍 Monitoring

File sẽ tự động:
- ✅ Monitor các bots mỗi 5 giây
- ✅ Hiển thị cảnh báo nếu bot nào dừng
- ✅ Hiển thị exit code khi bot dừng

**Ví dụ cảnh báo:**
```
⚠️ [2025-01-06 15:30:45] Bot 'scalp_sideway_xau.json' đã dừng (Exit Code: 1)
```

---

## 🔄 Auto-Restart (Optional)

Nếu muốn tự động khởi động lại bot khi dừng, uncomment phần code trong `mainScalpSideway.py`:

```python
# Optional: Restart logic could go here
# Uncomment below to auto-restart
print(f"🔄 Đang khởi động lại bot '{config_name}'...")
new_p = subprocess.Popen([sys.executable, proc_info['script'], proc_info['config']])
processes[i]['process'] = new_p
time.sleep(2)
```

---

## ⚠️ Lưu Ý

1. **Config Files**: Đảm bảo tất cả config files tồn tại
2. **Magic Numbers**: Mỗi bot phải có magic number riêng
3. **MT5 Connection**: Tất cả bots sẽ dùng cùng MT5 connection
4. **Resources**: Chạy nhiều bot cùng lúc có thể tốn tài nguyên

---

## 📚 Tài Liệu Liên Quan

- `scalp_sideway.py` - Main bot file
- `README_SCALP_SIDEWAY.md` - Hướng dẫn bot
- `SCALP_SIDEWAY_USAGE.md` - Hướng dẫn chi tiết

---

## 🎯 Tóm Tắt

**Chỉ cần chạy:**
```bash
python mainScalpSideway.py
```

**Vậy thôi! Tất cả bots sẽ tự động chạy.** 🚀
