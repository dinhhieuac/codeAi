# BOT SCALP SIDEWAY – TÀI LIỆU CHUẨN

## 1. Mục tiêu chiến lược
Chiến lược **Bot Scalp Sideway** được thiết kế để giao dịch trong điều kiện thị trường đi ngang (sideway), khai thác sự suy yếu dần của lực mua/bán tại các vùng **Supply/Demand khung M5**, và tìm điểm vào lệnh chính xác trên **M1**.

---

## 2. Khung thời gian sử dụng
- **M5**: Xác định bối cảnh, vùng Supply/Demand
- **M1**: Tìm tín hiệu vào lệnh (Entry)

---

## 3. Các chỉ báo sử dụng
- **ATR** (M1, M5)
- **EMA 21 (M5)**

---

## 4. Trường hợp SELL (Supply)

### 4.1. Xác định Supply M5
Supply hợp lệ khi thỏa mãn đồng thời:
- `High_M5_current < High_M5_prev`
- `|High_M5_prev − High_M5_current| < 0.4 × ATR_M5`

> **High_M5_prev** được coi là **đỉnh Supply**.

---

### 4.2. Lọc thị trường xấu
Tính:
```
ATR_ratio = ATR_M1_current / ATR_M1_avg(20)
```

Điều kiện lọc:
- `High_M1 > High_M5_supply + 0.4 × ATR_M5` → **Dừng trade 40 phút**
- `ATR_ratio > 2.0` → **Tạm dừng trade 20 phút**
- `ATR_ratio < 0.5` → **Không trade**

---

### 4.3. Bối cảnh M5 (Market Context)
Thị trường được coi là sideway/ổn định khi:
- `|EMA21_M5[i] − EMA21_M5[i-3]| < 0.2 × ATR_M5`
- `|Close_M5 − EMA21_M5| < 0.5 × ATR_M5`

---

### 4.4. Tìm tín hiệu SELL trên M1 (trong vùng Supply M5)

#### a. Điều kiện vùng giá
- `High_M1_current < High_M5_supply + 0.2 × ATR_M5`
- (Nâng cao – chưa code): `Close_M1 < High_M5_supply + 0.1 × ATR_M5`

---

#### b. Logic DeltaHigh (đếm lực suy yếu)

Công thức:
```
DeltaHigh = High[i] − High[i-1]
```

Điều kiện hợp lệ:
```
0 < DeltaHigh < k × ATR_M1
```

Nếu:
- `DeltaHigh ≤ 0` → Reset Count
- `DeltaHigh ≥ k × ATR_M1` → Reset Count

##### Giá trị k theo thị trường
| Market | k |
|------|----|
| Forex | 0.30 |
| Gold | 0.33 |
| BTC | 0.48 |

---

#### c. Điều kiện vào lệnh SELL
- `Count ≥ 2` (2 lần liên tiếp DeltaHigh hợp lệ)

**Ý nghĩa**: Giá vẫn cố tạo đỉnh mới nhưng mỗi lần tăng yếu hơn → lực mua suy kiệt.

---

### 4.5. Quản lý lệnh SELL
- **Stop Loss**: `2 × ATR` = **1R**
- **TP1**: `+1R` (chốt 50%) → dời SL về **BE**
- **TP2**: `+2R`

Quy tắc:
- Tối đa **2 lệnh / 1 vùng Supply**
- Nếu **1 lệnh bị SL** → **Không vào lại** cho đến khi **M5 đổi nến**

---

### 4.6. Ví dụ DeltaHigh (SELL)

| Lần | High[i] − High[i-1] | Kết quả |
|----|----------------------|---------|
| 1 | +0.12 ATR | Count = 1 |
| 2 | −0.05 ATR | Reset = 0 |
| 3 | +0.10 ATR | Count = 1 |
| 4 | +0.08 ATR | Count = 2 → **SELL** |

---

## 5. Trường hợp BUY (Demand)

### 5.1. Xác định Demand M5
Demand hợp lệ khi:
- `Low_M5_current > Low_M5_prev`
- `|Low_M5_current − Low_M5_prev| < 0.4 × ATR_M5`

> **Low_M5_prev** được coi là **đáy Demand**.

---

### 5.2. Lọc thị trường xấu

- `Low_M1 < Low_M5_demand − 0.4 × ATR_M5` → **Dừng trade 40 phút**
- `ATR_ratio > 2.0` → **Tạm dừng trade 20 phút**
- `ATR_ratio < 0.5` → **Không trade**

---

### 5.3. Bối cảnh M5
- `|EMA21_M5[i] − EMA21_M5[i-3]| < 0.2 × ATR_M5`
- `|Close_M5 − EMA21_M5| < 0.5 × ATR_M5`

---

### 5.4. Tìm tín hiệu BUY trên M1 (trong vùng Demand M5)

#### a. Logic DeltaLow

Công thức:
```
DeltaLow = Low[i-1] − Low[i]
```

Điều kiện hợp lệ:
```
0 < DeltaLow < k × ATR_M1
```

Nếu:
- `DeltaLow ≤ 0` → Reset
- `DeltaLow ≥ k × ATR_M1` → Reset

Giá trị k: **giống SELL** (Forex / Gold / BTC).

---

#### b. Điều kiện vào lệnh BUY
- `Low_M1_current > Low_M5_demand + 0.2 × ATR_M5`
- (Nâng cao – chưa code): `Close_M1 > Low_M5_demand + 0.1 × ATR_M5`
- `Count ≥ 2`

**Ý nghĩa**: Giá vẫn bị đạp xuống nhưng mỗi lần đạp yếu hơn → lực bán suy kiệt.

---

### 5.5. Quản lý lệnh BUY
- **Stop Loss**: `2 × ATR` = **1R**
- **TP1**: `+1R` (chốt 50%) → dời SL về **BE**
- **TP2**: `+2R`

Quy tắc:
- Tối đa **2 lệnh / 1 vùng Demand**
- Nếu **1 lệnh bị SL** → **Không vào lại** cho đến khi **M5 đổi nến**

---

## 6. Ghi chú tổng quát
- Chiến lược **chỉ dùng cho thị trường sideway**
- Không dùng trong trend mạnh hoặc news lớn
- Phù hợp cho bot scalp tự động (EA / Bot)

---

**Kết thúc tài liệu**

