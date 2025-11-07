# HƯỚNG DẪN SỬ DỤNG CONFIG ARRAY

## 📋 Tổng quan

File `config_xauusd.py` hiện có hệ thống config array cho phép bạn thử nghiệm nhiều cấu hình khác nhau để tối ưu tỉ lệ thắng/thua.

## 🎯 Các Config có sẵn

### 0. CONSERVATIVE (Bảo thủ)
- **Mục tiêu**: Tỉ lệ thua thấp, ít lệnh nhưng an toàn
- **Đặc điểm**:
  - Risk: 0.3%
  - MIN_SL_PIPS: 300 (SL xa)
  - MIN_SIGNAL_STRENGTH: 3 (yêu cầu 3 tín hiệu)
  - MAX_POSITIONS: 1
  - MAX_DAILY_TRADES: 10
  - MIN_TIME_BETWEEN_SAME_DIRECTION: 120 phút (2 giờ)

### 1. MODERATE (Cân bằng) - **MẶC ĐỊNH**
- **Mục tiêu**: Cân bằng giữa số lệnh và tỉ lệ thắng
- **Đặc điểm**:
  - Risk: 0.5%
  - MIN_SL_PIPS: 250
  - MIN_SIGNAL_STRENGTH: 2
  - MAX_POSITIONS: 2
  - MAX_DAILY_TRADES: 50
  - MIN_TIME_BETWEEN_SAME_DIRECTION: 60 phút

### 2. AGGRESSIVE (Tích cực)
- **Mục tiêu**: Nhiều lệnh hơn, chấp nhận tỉ lệ thua cao hơn
- **Đặc điểm**:
  - Risk: 0.5%
  - MIN_SL_PIPS: 200 (SL gần hơn)
  - MIN_SIGNAL_STRENGTH: 2
  - MAX_POSITIONS: 2
  - MAX_HOURLY_TRADES: 3
  - MIN_TIME_BETWEEN_SAME_DIRECTION: 45 phút

### 3. ULTRA_CONSERVATIVE (Cực bảo thủ)
- **Mục tiêu**: Rất ít lệnh, tỉ lệ thắng cao
- **Đặc điểm**:
  - Risk: 0.2% (rất thấp)
  - MIN_SL_PIPS: 400 (SL rất xa)
  - MIN_SIGNAL_STRENGTH: 4 (yêu cầu 4 tín hiệu)
  - MAX_POSITIONS: 1
  - MAX_DAILY_TRADES: 5
  - MIN_TIME_BETWEEN_SAME_DIRECTION: 180 phút (3 giờ)

### 4. SCALPING
- **Mục tiêu**: Nhiều lệnh nhỏ, SL/TP gần, chốt lời nhanh
- **Đặc điểm**:
  - Risk: 0.3%
  - MIN_SL_PIPS: 150 (SL gần)
  - MIN_SIGNAL_STRENGTH: 2
  - MAX_HOURLY_TRADES: 4
  - MIN_TIME_BETWEEN_SAME_DIRECTION: 30 phút
  - BREAK_EVEN_START_PIPS: 300 (break-even sớm)

### 5. SWING_TRADING
- **Mục tiêu**: Ít lệnh, SL/TP xa, giữ lâu
- **Đặc điểm**:
  - Risk: 0.5%
  - MIN_SL_PIPS: 500 (SL rất xa)
  - MIN_SIGNAL_STRENGTH: 3
  - MAX_POSITIONS: 1
  - MAX_DAILY_TRADES: 5
  - MIN_TIME_BETWEEN_SAME_DIRECTION: 240 phút (4 giờ)
  - ATR_SL_TP_MODE: "ATR_FREE" (không giới hạn USD)

### 6. LOW_LOSS (Tối ưu giảm tỉ lệ thua)
- **Mục tiêu**: SL xa, signal mạnh, ít lệnh
- **Đặc điểm**:
  - Risk: 0.4%
  - MIN_SL_PIPS: 350 (SL rất xa)
  - MIN_SIGNAL_STRENGTH: 3
  - MAX_POSITIONS: 1
  - MAX_DAILY_TRADES: 20
  - MIN_TIME_BETWEEN_SAME_DIRECTION: 90 phút (1.5 giờ)

## 🔧 Cách sử dụng

### Cách 1: Dùng Index (Số)

Mở file `config_xauusd.py` và thay đổi:

```python
CONFIG_INDEX = 0  # CONSERVATIVE
# CONFIG_INDEX = 1  # MODERATE (mặc định)
# CONFIG_INDEX = 2  # AGGRESSIVE
# CONFIG_INDEX = 3  # ULTRA_CONSERVATIVE
# CONFIG_INDEX = 4  # SCALPING
# CONFIG_INDEX = 5  # SWING_TRADING
# CONFIG_INDEX = 6  # LOW_LOSS
```

### Cách 2: Dùng Tên Config

```python
CONFIG_INDEX = "CONSERVATIVE"
# CONFIG_INDEX = "MODERATE"
# CONFIG_INDEX = "AGGRESSIVE"
# CONFIG_INDEX = "ULTRA_CONSERVATIVE"
# CONFIG_INDEX = "SCALPING"
# CONFIG_INDEX = "SWING_TRADING"
# CONFIG_INDEX = "LOW_LOSS"
```

## 📊 So sánh các Config

| Config | Risk | MIN_SL | Signal | Max Positions | Max Daily | Mục tiêu |
|--------|------|--------|--------|---------------|-----------|----------|
| CONSERVATIVE | 0.3% | 300 | 3 | 1 | 10 | Tỉ lệ thua thấp |
| MODERATE | 0.5% | 250 | 2 | 2 | 50 | Cân bằng |
| AGGRESSIVE | 0.5% | 200 | 2 | 2 | 50 | Nhiều lệnh |
| ULTRA_CONSERVATIVE | 0.2% | 400 | 4 | 1 | 5 | Rất an toàn |
| SCALPING | 0.3% | 150 | 2 | 2 | 50 | Chốt nhanh |
| SWING_TRADING | 0.5% | 500 | 3 | 1 | 5 | Giữ lâu |
| LOW_LOSS | 0.4% | 350 | 3 | 1 | 20 | Giảm thua |

## 🧪 Khuyến nghị thử nghiệm

1. **Bắt đầu với MODERATE** (config mặc định)
2. **Nếu tỉ lệ thua cao** → Thử:
   - **CONSERVATIVE** (index 0): SL xa hơn, signal mạnh hơn
   - **LOW_LOSS** (index 6): Tối ưu để giảm tỉ lệ thua
   - **ULTRA_CONSERVATIVE** (index 3): Rất an toàn
3. **Nếu ít lệnh quá** → Thử:
   - **AGGRESSIVE** (index 2): Nhiều lệnh hơn
   - **SCALPING** (index 4): Chốt nhanh

## 📝 Lưu ý

- Khi thay đổi `CONFIG_INDEX`, bot sẽ tự động load config mới khi khởi động
- Tất cả các biến trong config sẽ được override
- Các biến không có trong config (như SYMBOL, TIMEFRAME) sẽ giữ nguyên giá trị mặc định
- Log sẽ hiển thị config đang sử dụng khi bot khởi động

## 🔍 Kiểm tra config hiện tại

Chạy lệnh sau để xem config đang sử dụng:

```bash
cd XAUUSD_BOT_FULL_V2
python3 -c "from config_xauusd import selected_config, CONFIG_INDEX, list_configs; print('Config đang sử dụng:', selected_config['name']); print('Index:', CONFIG_INDEX); print('\nDanh sách configs:'); [print(f'  {i}: {c[\"name\"]} - {c[\"description\"]}') for i, c in enumerate(list_configs())]"
```

