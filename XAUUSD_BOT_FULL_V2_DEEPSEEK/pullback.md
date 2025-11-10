# CHIẾN THUẬT GIAO DỊCH VÀNG (XAU/USD) M15
# PULLBACK KẾT HỢP EMA & RSI

## THIẾT LẬP
- **Khung H1**: Xác định xu hướng chính
- **Khung M15**: Vào lệnh (entry)
- **EMA**: 21, 50, 200
- **RSI**: 14 (vùng quá bán < 30, quá mua > 70)
- **MACD**: Xác nhận momentum (12, 26, 9)
- **Volume**: Xác nhận sức mạnh bounce (tùy chọn)

---

## QUY TẮC VÀO LỆNH

### 📈 LỆNH BUY

**Điều kiện bắt buộc:**
1. **H1: UPTREND** - Giá trên 3 EMA (21, 50, 200)
2. **M15: Pullback** - Giá hồi về EMA 21 hoặc EMA 50
3. **RSI: Quá bán** - RSI < 30
4. **Xác nhận nến** - Nến đóng trên EMA (21 hoặc 50)

**Điều kiện xác nhận (có thể bật/tắt):**
5. **Engulfing** - Bullish Engulfing tại vùng EMA (mặc định: BẬT)
6. **MACD** - Histogram chuyển từ âm sang dương, hoặc MACD > Signal (mặc định: BẬT)
7. **Volume** - Volume tăng khi giá bounce từ pullback (mặc định: TẮT)

**Vào lệnh:** Khi đủ tất cả điều kiện bắt buộc và điều kiện xác nhận (nếu bật)

---

### 📉 LỆNH SELL

**Điều kiện bắt buộc:**
1. **H1: DOWNTREND** - Giá dưới 3 EMA (21, 50, 200)
2. **M15: Pullback** - Giá hồi về EMA 21 hoặc EMA 50
3. **RSI: Quá mua** - RSI > 70
4. **Xác nhận nến** - Nến đóng dưới EMA (21 hoặc 50)

**Điều kiện xác nhận (có thể bật/tắt):**
5. **Engulfing** - Bearish Engulfing tại vùng EMA (mặc định: BẬT)
6. **MACD** - Histogram chuyển từ dương sang âm, hoặc MACD < Signal (mặc định: BẬT)
7. **Volume** - Volume tăng khi giá bounce từ pullback (mặc định: TẮT)

**Vào lệnh:** Khi đủ tất cả điều kiện bắt buộc và điều kiện xác nhận (nếu bật)

---

## QUẢN LÝ LỆNH

### 🛡️ CẮT LỖ (STOP LOSS)

**Phương pháp 1: Theo Pullback Structure (Khuyến nghị)**
- **BUY**: SL đặt dưới đáy pullback (low nhất trong 5 nến gần nhất) - 10 pips
- **SELL**: SL đặt trên đỉnh pullback (high nhất trong 5 nến gần nhất) + 10 pips
- **Ưu điểm**: SL chính xác hơn, tránh bị quét bởi noise
- **Config**: `USE_PULLBACK_SL = True`

**Phương pháp 2: Theo ATR (Dự phòng)**
- SL = Entry ± (ATR × 1.5)
- **Config**: `USE_PULLBACK_SL = False`

**Risk Management:**
- Risk: 1-2% tài khoản mỗi lệnh
- SL tối thiểu: 250 pips (đảm bảo đủ không gian cho biến động)

---

### 💰 CHỐT LỜI (TAKE PROFIT)

**Phương pháp 1: Theo ATR/R:R Ratio (Mặc định)**
- TP = Entry ± (ATR × 2.5) hoặc SL × R:R ratio (1:1.5 đến 1:2)
- **Config**: `USE_EMA_TP = False`

**Phương pháp 2: Tại EMA Kế Tiếp (Tùy chọn)**
- **BUY**: TP tại EMA 200 (EMA kế tiếp sau EMA 50)
- **SELL**: TP tại EMA 200 (EMA kế tiếp sau EMA 50)
- **Ưu điểm**: Chốt lời tại vùng kháng cự/hỗ trợ quan trọng
- **Config**: `USE_EMA_TP = True`

**Partial Close Strategy:**
- Chốt 50% tại R:R 1:1
- Cho 50% còn lại chạy tiếp đến TP cuối cùng
- **Config**: `ENABLE_PARTIAL_CLOSE = True`

---

## CẤU HÌNH NÂNG CAO

### Bật/Tắt Điều Kiện Xác Nhận

```python
# Engulfing Pattern
REQUIRE_ENGULFING = True  # True: Bắt buộc, False: Không bắt buộc

# MACD Confirmation
REQUIRE_MACD_CONFIRMATION = True  # True: Bắt buộc, False: Không bắt buộc

# Volume Confirmation
REQUIRE_VOLUME_CONFIRMATION = False  # True: Bắt buộc, False: Không bắt buộc (tắt mặc định)

# SL Placement
USE_PULLBACK_SL = True  # True: SL theo pullback, False: SL theo ATR

# TP Placement
USE_EMA_TP = False  # True: TP tại EMA, False: TP theo ATR/R:R
```

### Tham Số Pullback

```python
# EMA Periods
EMA_FAST = 21   # EMA ngắn hạn
EMA_MID = 50    # EMA trung bình
EMA_SLOW = 200  # EMA dài hạn

# RSI Thresholds
PULLBACK_RSI_BUY_MAX = 30   # RSI tối đa cho BUY (quá bán)
PULLBACK_RSI_SELL_MIN = 70  # RSI tối thiểu cho SELL (quá mua)

# Pullback Tolerance
PULLBACK_TOLERANCE_PIPS = 30  # Khoảng cách tối đa để coi là pullback về EMA
```

---

## LƯU Ý QUAN TRỌNG

✅ **Best Practices:**
- Chỉ giao dịch khi xu hướng rõ ràng trên H1
- Đợi pullback về EMA, không FOMO vào lệnh
- Luôn kiểm tra MACD để xác nhận momentum
- Sử dụng SL theo pullback structure để tối ưu risk/reward

⚠️ **Cảnh Báo:**
- Không risk quá 2% tài khoản mỗi lệnh
- Tránh giao dịch trong thời gian tin tức quan trọng
- Luôn tuân thủ kỷ luật, không override bot
- Giao dịch vàng có rủi ro cao, chiến thuật không đảm bảo lợi nhuận

---

## TỔNG HỢP ĐIỀU KIỆN ENTRY

### ✅ BUY Signal Checklist:
- [ ] H1: UPTREND (giá trên 3 EMA)
- [ ] M15: Pullback về EMA 21/50
- [ ] RSI < 30 (quá bán)
- [ ] Nến đóng trên EMA
- [ ] Bullish Engulfing (nếu bật)
- [ ] MACD histogram chuyển từ âm sang dương (nếu bật)
- [ ] Volume tăng khi bounce (nếu bật)

### ✅ SELL Signal Checklist:
- [ ] H1: DOWNTREND (giá dưới 3 EMA)
- [ ] M15: Pullback về EMA 21/50
- [ ] RSI > 70 (quá mua)
- [ ] Nến đóng dưới EMA
- [ ] Bearish Engulfing (nếu bật)
- [ ] MACD histogram chuyển từ dương sang âm (nếu bật)
- [ ] Volume tăng khi bounce (nếu bật)

---

## CẢNH BÁO RỦI RO

⚠️ **Giao dịch vàng có rủi ro cao. Chiến thuật không đảm bảo lợi nhuận.**

- Luôn sử dụng Stop Loss
- Không risk quá 2% tài khoản
- Backtest trước khi giao dịch thật
- Quản lý vốn hợp lý

---

**File được cập nhật:** 2025  
**Version:** 2.0 (với MACD, Volume confirmation, và cải thiện SL/TP)