# Bot Scalp Sideway Strategy

## Trường hợp Sell

### Xác định Supply M5
- High_M5_current < High_M5_prev  
- |High_M5_prev - High_M5_current| < 0.4 × ATR_M5  

### Lọc thị trường xấu
- ATR_ratio = ATR_M1_current / ATR_M1_avg(20)  
- ATR_ratio > 1.5 → Tạm dừng trade 40 phút  
- ATR_ratio < 0.5 → Không trade  
- ATR_M1 tăng liên tiếp 3 nến và ATR_M1 > ATR_M1_avg(20) → Dừng trade 40 phút  
- BodySize(M1) > 1.2 × ATR_M1 → Tạm dừng trade 15 phút  

### Bối cảnh Sideway (M5)
- |EMA21_M5[i] - EMA21_M5[i-3]| < 0.2 × ATR_M5  
- |Close_M5 - EMA21_M5| < 0.5 × ATR_M5  

### Supply M5 → Tìm Sell M1
- M1: Giá đóng cửa ≥ EMA9 → Cho phép tính DeltaHigh  
- Nếu DeltaHigh hợp lệ → Count++  
- Ngược lại → Count = 0  

**DeltaHigh = High[i] - High[i-1]**

Điều kiện hợp lệ:
- 0 < DeltaHigh < 0.3 × ATR(M1)  

Reset:
- DeltaHigh ≤ 0 → RESET  
- DeltaHigh ≥ 0.3 × ATR → RESET  

### Điều kiện Sell
- High_M1_current < High_M5_supply + 0.2 × ATR_M5  
- Count ≥ 2 (liên tiếp) → SELL  

**Ý nghĩa:** Giá vẫn cố tạo đỉnh mới nhưng mỗi lần yếu hơn → lực mua cạn dần.

### Quản lý lệnh
- SL = 2 ATR = 1R  
- TP1 = +1R (chốt 50%, dời SL về BE)  
- TP2 = 2R  
- Max 2 lệnh / vùng Supply  
- Nếu 1 lệnh SL → không vào lại cho đến khi M5 đổi nến  

---

## Trường hợp Buy

### Xác định Demand M5
- Low_M5_current > Low_M5_prev  
- |Low_M5_current - Low_M5_prev| < 0.4 × ATR_M5  

### Lọc thị trường xấu
*(Giống Sell)*

### Bối cảnh Sideway (M5)
- |EMA21_M5[i] - EMA21_M5[i-3]| < 0.2 × ATR_M5  
- |Close_M5 - EMA21_M5| < 0.5 × ATR_M5  

### Demand M5 → Tìm Buy M1
- M1: Giá đóng cửa ≤ EMA9 → Cho phép tính DeltaLow  
- Nếu DeltaLow hợp lệ → Count++  
- Ngược lại → Count = 0  

**DeltaLow = Low[i-1] - Low[i]**

Điều kiện hợp lệ:
- 0 < DeltaLow < 0.3 × ATR(M1)  

Reset:
- DeltaLow ≤ 0 → RESET  
- DeltaLow ≥ 0.3 × ATR → RESET  

### Điều kiện Buy
- Low_M1_current > Low_M5_demand + 0.2 × ATR_M5  
- Count ≥ 2 (liên tiếp) → BUY  

**Ý nghĩa:** Giá vẫn bị đạp xuống nhưng mỗi lần đạp yếu hơn → lực bán suy kiệt.

### Quản lý lệnh
- SL = 2 ATR = 1R  
- TP1 = +1R (chốt 50%, dời SL về BE)  
- TP2 = 2R  
- Max 2 lệnh / vùng Demand  
- Nếu 1 lệnh SL → không vào lại cho đến khi M5 đổi nến  
