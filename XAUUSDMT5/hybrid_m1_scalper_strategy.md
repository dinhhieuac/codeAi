# Hybrid M1 Scalper Strategy Documentation

## Tổng Quan (Overview)
Bot **Hybrid M1 Scalper** là một hệ thống giao dịch tự động trên cặp **XAUUSD** (Vàng), sử dụng kết hợp xu hướng dài hạn trên khung **H1** và điểm vào lệnh tối ưu trên khung **M1**.

Chiến thuật chủ đạo là **Trend Following (Theo xu hướng)** kết hợp với **Mean Reversion (Hồi quy về trung bình)** để tìm điểm vào lệnh khi giá điều chỉnh (pullback).

## Cấu Hình Kỹ Thuật (Technical Configuration)
- **Symbol**: XAUUSD (hoặc XAUUSDc, XAUUSDm tùy loại tài khoản).
- **Timeframes**:
  - **H1**: Xác định xu hướng chính.
  - **M1**: Tìm điểm vào lệnh (Entry) và tính toán SL/TP.
- **Khối lượng (Volume)**: 0.01 lot (mặc định).
- **Tần suất kiểm tra**: 10 giây/lần.

## Các Chỉ Báo Sử Dụng (Indicators)

1.  **EMA 50 (H1)**: Đường trung bình động lũy thừa chu kỳ 50 trên khung H1.
    - *Vai trò*: Bộ lọc xu hướng dài hạn.
2.  **EMA 20 (M1)**: Đường trung bình động lũy thừa chu kỳ 20 trên khung M1.
    - *Vai trò*: Xác định vùng giá trị (Value Area) để tìm điểm vào lệnh (Retest).
3.  **ADX 14 (M1)**: Chỉ báo sức mạnh xu hướng chu kỳ 14 trên khung M1.
    - *Vai trò*: Lọc thị trường đi ngang (Sideways). Chỉ giao dịch khi xu hướng đủ mạnh.
4.  **ATR 14 (M1)**: Khoảng biến động trung bình thực tế chu kỳ 14 trên khung M1.
    - *Vai trò*: Tính toán Stop Loss (SL) và Take Profit (TP) động theo biến động thị trường.

## Logic Giao Dịch (Trading Logic)

Hệ thống kiểm tra điều kiện theo 3 bước tuần tự:

### Bước 1: Xác định Xu Hướng H1 (H1 Trend Filter)
Bot so sánh giá hiện tại với đường EMA 50 trên khung H1:
- **XU HƯỚNG TĂNG (BUY Trend)**: Nếu Giá > EMA 50 (H1).
- **XU HƯỚNG GIẢM (SELL Trend)**: Nếu Giá < EMA 50 (H1).
- *Lưu ý*: Nếu giá bằng EMA 50, bot sẽ đứng ngoài.

### Bước 2: Kiểm Tra Sức Mạnh Xu Hướng (Trend Strength)
Bot kiểm tra chỉ báo ADX(14) trên khung M1:
- **Điều kiện**: `ADX >= 25`.
- Nếu `ADX < 25`, thị trường được coi là yếu hoặc đi ngang -> **Không giao dịch**.

### Bước 3: Tín Hiệu Vào Lệnh M1 (M1 Entry Signal)
Nếu xu hướng H1 rõ ràng và ADX mạnh, bot sẽ tìm điểm vào lệnh dựa trên sự hồi quy về EMA 20 trên M1 (Retest).

- **Điều kiện khoảng cách**: Giá phải nằm trong phạm vi `50 points` (5 pips) so với EMA 20.

#### Tín hiệu MUA (BUY Signal):
1.  **H1 Trend** là **TĂNG**.
2.  **ADX M1** >= 25.
3.  Giá M1 giảm xuống thấp hơn EMA 20 (`Price < EMA 20`).
    - *Ý nghĩa*: Mua khi giá điều chỉnh giảm (dip) về dưới đường trung bình trong xu hướng tăng.

#### Tín hiệu BÁN (SELL Signal):
1.  **H1 Trend** là **GIẢM**.
2.  **ADX M1** >= 25.
3.  Giá M1 tăng lên cao hơn EMA 20 (`Price > EMA 20`).
    - *Ý nghĩa*: Bán khi giá hồi phục tăng (rally) lên trên đường trung bình trong xu hướng giảm.

## Quản Lý Rủi Ro (Risk Management)

Bot sử dụng **ATR (Average True Range)** trên khung M1 để đặt SL/TP động, giúp thích nghi với biến động của thị trường.

- **Stop Loss (SL)**: `1.5 * ATR(14)`
- **Take Profit (TP)**: `2.0 * ATR(14)`
- **Tỷ lệ R:R**: Khoảng 1:1.33.

### Ví dụ:
Nếu ATR(14) trên M1 là 10 pips:
- SL = 15 pips.
- TP = 20 pips.

## Thông Báo (Notifications)
- Bot gửi thông báo qua **Telegram** khi:
  - Vào lệnh thành công (kèm chi tiết Entry, SL, TP, Order ID).
  - Gặp lỗi khi gửi lệnh.
