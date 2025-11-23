"""
PHÂN TÍCH KỸ THUẬT - Technical Analyzer
========================================
Module này chứa các phương thức tính toán các chỉ báo kỹ thuật và phân tích tín hiệu giao dịch.
"""

import pandas as pd
import numpy as np
import logging
from config_btcusd import *

class TechnicalAnalyzer:
    """
    Lớp phân tích kỹ thuật cho bot giao dịch BTCUSD
    
    Chức năng:
    - Tính toán các chỉ báo kỹ thuật: RSI, EMA, MACD, Bollinger Bands, ATR
    - Phân tích tín hiệu mua/bán dựa trên sự kết hợp của các chỉ báo
    - Tính toán SL/TP dựa trên ATR và Risk/Reward ratio
    """
    
    def __init__(self):
        """
        Khởi tạo Technical Analyzer
        
        Load các tham số từ config:
        - min_sl_pips: Stop Loss tối thiểu (pips)
        - min_tp_pips: Take Profit tối thiểu (pips)
        """
        self.min_sl_pips = MIN_SL_PIPS  # SL tối thiểu từ config
        self.min_tp_pips = MIN_TP_PIPS  # TP tối thiểu từ config
        
    def calculate_rsi(self, prices, period=14):
        """
        Tính Relative Strength Index (RSI) - Chỉ số sức mạnh tương đối
        
        RSI đo lường tốc độ và mức độ thay đổi giá, giá trị từ 0-100.
        - RSI < 30: Quá bán (oversold) → Tín hiệu mua
        - RSI > 70: Quá mua (overbought) → Tín hiệu bán
        
        Args:
            prices: Series giá đóng cửa (close prices)
            period: Chu kỳ tính RSI (mặc định: 14)
            
        Returns:
            Series RSI với giá trị từ 0-100
        """
        # Tính độ thay đổi giá (delta)
        delta = prices.diff()
        
        # Tách thành gain (tăng) và loss (giảm)
        gain = (delta.where(delta > 0, 0)).fillna(0)  # Chỉ lấy giá trị tăng
        loss = (-delta.where(delta < 0, 0)).fillna(0)  # Chỉ lấy giá trị giảm (đổi dấu)
        
        # Tính trung bình gain và loss trong chu kỳ
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        # Tính Relative Strength (RS) = avg_gain / avg_loss
        rs = avg_gain / avg_loss
        
        # Tính RSI = 100 - (100 / (1 + RS))
        rsi = 100 - (100 / (1 + rs))
        return rsi
        
    def calculate_ema(self, prices, period):
        """
        Tính Exponential Moving Average (EMA) - Trung bình động hàm mũ
        
        EMA là trung bình động có trọng số cao hơn cho giá gần đây.
        Phản ứng nhanh hơn SMA với biến động giá.
        
        Args:
            prices: Series giá đóng cửa (close prices)
            period: Chu kỳ tính EMA (ví dụ: 20 = EMA20)
            
        Returns:
            Series EMA
        """
        return prices.ewm(span=period, adjust=False).mean()
        
    def calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """
        Tính MACD (Moving Average Convergence Divergence) - Chỉ báo hội tụ/phân kỳ
        
        MACD gồm 3 thành phần:
        - MACD line: EMA(fast) - EMA(slow)
        - Signal line: EMA của MACD line
        - Histogram: MACD - Signal (thể hiện momentum)
        
        Tín hiệu:
        - MACD cắt Signal từ dưới lên → Tín hiệu mua
        - MACD cắt Signal từ trên xuống → Tín hiệu bán
        
        Args:
            prices: Series giá đóng cửa (close prices)
            fast: Chu kỳ EMA nhanh (mặc định: 12)
            slow: Chu kỳ EMA chậm (mặc định: 26)
            signal: Chu kỳ EMA cho signal line (mặc định: 9)
            
        Returns:
            Tuple (macd_line, signal_line, histogram)
        """
        # Tính EMA nhanh và EMA chậm
        ema_fast = self.calculate_ema(prices, fast)
        ema_slow = self.calculate_ema(prices, slow)
        
        # MACD line = EMA nhanh - EMA chậm
        macd = ema_fast - ema_slow
        
        # Signal line = EMA của MACD line
        signal_line = self.calculate_ema(macd, signal)
        
        # Histogram = MACD - Signal (thể hiện momentum)
        histogram = macd - signal_line
        
        return macd, signal_line, histogram
        
    def calculate_bollinger_bands(self, prices, period=20, std_dev=2):
        """
        Tính Bollinger Bands - Dải bollinger
        
        Bollinger Bands gồm 3 đường:
        - Upper Band: SMA + (Std * std_dev)
        - Middle Band (SMA): Trung bình giá
        - Lower Band: SMA - (Std * std_dev)
        
        Tín hiệu:
        - Giá chạm Lower Band → Có thể tăng (tín hiệu mua)
        - Giá chạm Upper Band → Có thể giảm (tín hiệu bán)
        
        Args:
            prices: Series giá đóng cửa (close prices)
            period: Chu kỳ tính SMA (mặc định: 20)
            std_dev: Độ lệch chuẩn (mặc định: 2)
            
        Returns:
            Tuple (upper_band, middle_band (SMA), lower_band)
        """
        # Tính SMA (Simple Moving Average)
        sma = prices.rolling(period).mean()
        
        # Tính độ lệch chuẩn (standard deviation)
        std = prices.rolling(period).std()
        
        # Tính Upper và Lower Band
        upper_band = sma + (std * std_dev)  # SMA + 2*Std
        lower_band = sma - (std * std_dev)  # SMA - 2*Std
        
        return upper_band, sma, lower_band
        
    def calculate_atr(self, high, low, close, period=14):
        """
        Tính Average True Range (ATR) - Phạm vi biến động trung bình
        
        ATR đo lường mức độ biến động của giá, không chỉ hướng.
        Dùng để tính SL/TP dựa trên độ biến động thực tế của thị trường.
        
        True Range = max của:
        - High - Low (phạm vi trong nến)
        - |High - Close trước| (gap lên)
        - |Low - Close trước| (gap xuống)
        
        Args:
            high: Series giá cao nhất (high prices)
            low: Series giá thấp nhất (low prices)
            close: Series giá đóng cửa (close prices)
            period: Chu kỳ tính ATR (mặc định: 14)
            
        Returns:
            Series ATR
        """
        # Tính True Range (TR) - phạm vi thực tế
        tr1 = high - low  # Phạm vi trong nến
        tr2 = abs(high - close.shift())  # Gap lên (nếu có)
        tr3 = abs(low - close.shift())  # Gap xuống (nếu có)
        
        # True Range = max của 3 giá trị trên
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR = Trung bình của True Range trong chu kỳ
        atr = tr.rolling(period).mean()
        return atr
        
    def analyze(self, df):
        """
        Phân tích kỹ thuật toàn diện và tạo tín hiệu giao dịch
        
        Quy trình:
        1. Tính toán tất cả các chỉ báo kỹ thuật (RSI, EMA, MACD, BB, ATR)
        2. Đếm số lượng tín hiệu mua/bán từ mỗi chỉ báo
        3. Xác định tín hiệu cuối cùng (BUY/SELL/HOLD) dựa trên số lượng tín hiệu
        4. Tính toán SL/TP dựa trên ATR và Risk/Reward ratio
        
        Điều kiện tín hiệu:
        - Cần tối thiểu 2 tín hiệu đồng thuận để mở lệnh (đã giảm từ 3 xuống 2)
        - RSI có trọng số x2 (2 điểm) khi cắt ngưỡng, x1 (1 điểm) khi đang ở vùng
        - EMA, MACD, BB mỗi cái 1 điểm (kích hoạt cả khi cắt và khi đang ở trạng thái)
        
        Args:
            df: DataFrame chứa dữ liệu giá (columns: open, high, low, close, time)
                Cần tối thiểu 50 nến để tính toán đầy đủ các chỉ báo
            
        Returns:
            Dict với các keys:
            - 'action': 'BUY', 'SELL', hoặc 'HOLD'
            - 'strength': Số lượng tín hiệu đồng thuận (0-6)
            - 'sl_pips': Stop Loss tính bằng pips
            - 'tp_pips': Take Profit tính bằng pips
            
            None nếu không đủ dữ liệu (< 50 nến)
        """
        # Kiểm tra dữ liệu đủ để tính toán
        if len(df) < 50:
            return None  # Cần ít nhất 50 nến để tính các chỉ báo chính xác
        
        # Lấy các cột giá cần thiết
        close = df['close']  # Giá đóng cửa
        high = df['high']   # Giá cao nhất
        low = df['low']     # Giá thấp nhất
        
        # ====================================================================
        # BƯỚC 1: TÍNH TOÁN CÁC CHỈ BÁO KỸ THUẬT
        # ====================================================================
        
        # RSI (Relative Strength Index) - chu kỳ 14
        df['rsi'] = self.calculate_rsi(close, 14)
        
        # EMA (Exponential Moving Average) - EMA20 và EMA50 để xác định trend
        df['ema_20'] = self.calculate_ema(close, 20)  # EMA ngắn hạn
        df['ema_50'] = self.calculate_ema(close, 50)  # EMA dài hạn
        
        # MACD (Moving Average Convergence Divergence)
        macd, macd_signal, macd_hist = self.calculate_macd(close)
        df['macd'] = macd           # MACD line
        df['macd_signal'] = macd_signal  # Signal line
        df['macd_hist'] = macd_hist      # Histogram (momentum)
        
        # Bollinger Bands - để xác định vùng quá mua/quá bán
        upper_bb, middle_bb, lower_bb = self.calculate_bollinger_bands(close)
        df['upper_bb'] = upper_bb   # Dải trên
        df['middle_bb'] = middle_bb    # Dải giữa (SMA)
        df['lower_bb'] = lower_bb    # Dải dưới
        
        # ATR (Average True Range) - để tính SL/TP dựa trên độ biến động
        df['atr'] = self.calculate_atr(high, low, close)
        
        # ====================================================================
        # BƯỚC 2: LẤY GIÁ TRỊ HIỆN TẠI VÀ TRƯỚC ĐÓ
        # ====================================================================
        
        current = df.iloc[-1]  # Nến hiện tại (mới nhất)
        prev = df.iloc[-2]     # Nến trước đó (để so sánh)
        
        # ====================================================================
        # LOG CHI TIẾT CÁC CHỈ BÁO KỸ THUẬT
        # ====================================================================
        logging.info("=" * 60)
        logging.info("📊 CHI TIẾT CHỈ BÁO KỸ THUẬT:")
        logging.info("=" * 60)
        logging.info(f"   💰 Giá hiện tại: {current['close']:.2f}")
        logging.info(f"   📈 RSI: {current['rsi']:.2f} (Trước: {prev['rsi']:.2f})")
        logging.info(f"   📊 EMA20: {current['ema_20']:.2f} | EMA50: {current['ema_50']:.2f}")
        logging.info(f"   📉 MACD: {current['macd']:.2f} | Signal: {current['macd_signal']:.2f} | Histogram: {current['macd_hist']:.2f}")
        logging.info(f"   🎯 Bollinger Bands: Upper={current['upper_bb']:.2f} | Middle={current['middle_bb']:.2f} | Lower={current['lower_bb']:.2f}")
        # ⚠️ VỚI ETHUSD: 1 pip = 1 USD (không phải 0.01 như XAUUSD)
        # Vậy ATR đã là pips rồi (ATR = 38.87 USD → 38.87 pips)
        atr_value = current['atr']  # ATR tính bằng pips (1 USD = 1 pip cho ETHUSD)
        logging.info(f"   📏 ATR: {current['atr']:.2f} USD ({atr_value:.1f} pips)")
        logging.info("=" * 60)
        
        # ====================================================================
        # BƯỚC 3: ĐẾM SỐ LƯỢNG TÍN HIỆU MUA/BÁN
        # ====================================================================
        
        buy_signals = 0   # Số tín hiệu mua (cộng dồn)
        sell_signals = 0  # Số tín hiệu bán (cộng dồn)
        buy_reasons = []  # Danh sách lý do tín hiệu mua
        sell_reasons = []  # Danh sách lý do tín hiệu bán
        
        # --- Tín hiệu RSI (trọng số x2 = 2 điểm) ---
        # RSI cắt từ trên xuống dưới 30 → Quá bán → Tín hiệu mua mạnh (ưu tiên)
        if current['rsi'] < 30 and prev['rsi'] >= 30:
            buy_signals += 2  # RSI có trọng số cao hơn (2 điểm)
            buy_reasons.append(f"RSI cắt xuống dưới 30 (Quá bán) - RSI: {current['rsi']:.2f} [2 điểm]")
        # RSI đang ở vùng quá bán (< 35) → Tín hiệu mua (chỉ khi chưa cắt)
        elif current['rsi'] < 35:
            buy_signals += 1  # RSI đang ở vùng quá bán (1 điểm)
            buy_reasons.append(f"RSI đang ở vùng quá bán (< 35) - RSI: {current['rsi']:.2f} [1 điểm]")
        else:
            logging.debug(f"   ❌ RSI không có tín hiệu BUY: {current['rsi']:.2f} (cần < 35)")
        
        # RSI cắt từ dưới lên trên 70 → Quá mua → Tín hiệu bán mạnh (ưu tiên)
        if current['rsi'] > 70 and prev['rsi'] <= 70:
            sell_signals += 2  # RSI có trọng số cao hơn (2 điểm)
            sell_reasons.append(f"RSI cắt lên trên 70 (Quá mua) - RSI: {current['rsi']:.2f} [2 điểm]")
        # RSI đang ở vùng quá mua (> 65) → Tín hiệu bán (chỉ khi chưa cắt)
        elif current['rsi'] > 65:
            sell_signals += 1  # RSI đang ở vùng quá mua (1 điểm)
            sell_reasons.append(f"RSI đang ở vùng quá mua (> 65) - RSI: {current['rsi']:.2f} [1 điểm]")
        else:
            logging.debug(f"   ❌ RSI không có tín hiệu SELL: {current['rsi']:.2f} (cần > 65)")
        
        # --- Tín hiệu EMA (trọng số x1 = 1 điểm) ---
        # EMA20 cắt EMA50 từ dưới lên → Uptrend mới → Tín hiệu mua (ưu tiên)
        if current['ema_20'] > current['ema_50'] and prev['ema_20'] <= prev['ema_50']:
            buy_signals += 1
            buy_reasons.append(f"EMA20 cắt EMA50 từ dưới lên (Uptrend mới) - EMA20: {current['ema_20']:.2f} > EMA50: {current['ema_50']:.2f} [1 điểm]")
        # EMA20 đang ở trên EMA50 → Uptrend đang diễn ra → Tín hiệu mua
        elif current['ema_20'] > current['ema_50']:
            buy_signals += 1
            buy_reasons.append(f"EMA20 đang trên EMA50 (Uptrend) - EMA20: {current['ema_20']:.2f} > EMA50: {current['ema_50']:.2f} [1 điểm]")
        else:
            logging.debug(f"   ❌ EMA không có tín hiệu BUY: EMA20={current['ema_20']:.2f} <= EMA50={current['ema_50']:.2f}")
        
        # EMA20 cắt EMA50 từ trên xuống → Downtrend mới → Tín hiệu bán (ưu tiên)
        if current['ema_20'] < current['ema_50'] and prev['ema_20'] >= prev['ema_50']:
            sell_signals += 1
            sell_reasons.append(f"EMA20 cắt EMA50 từ trên xuống (Downtrend mới) - EMA20: {current['ema_20']:.2f} < EMA50: {current['ema_50']:.2f} [1 điểm]")
        # EMA20 đang ở dưới EMA50 → Downtrend đang diễn ra → Tín hiệu bán
        elif current['ema_20'] < current['ema_50']:
            sell_signals += 1
            sell_reasons.append(f"EMA20 đang dưới EMA50 (Downtrend) - EMA20: {current['ema_20']:.2f} < EMA50: {current['ema_50']:.2f} [1 điểm]")
        else:
            logging.debug(f"   ❌ EMA không có tín hiệu SELL: EMA20={current['ema_20']:.2f} >= EMA50={current['ema_50']:.2f}")
        
        # --- Tín hiệu MACD (trọng số x1 = 1 điểm) ---
        # MACD cắt Signal từ dưới lên → Momentum tăng → Tín hiệu mua (ưu tiên)
        if current['macd'] > current['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            buy_signals += 1
            buy_reasons.append(f"MACD cắt Signal từ dưới lên - MACD: {current['macd']:.2f} > Signal: {current['macd_signal']:.2f}, Histogram: {current['macd_hist']:.2f} [1 điểm]")
        # MACD đang ở trên Signal → Momentum tăng → Tín hiệu mua
        elif current['macd'] > current['macd_signal']:
            buy_signals += 1
            buy_reasons.append(f"MACD đang trên Signal (Momentum tăng) - MACD: {current['macd']:.2f} > Signal: {current['macd_signal']:.2f}, Histogram: {current['macd_hist']:.2f} [1 điểm]")
        else:
            logging.debug(f"   ❌ MACD không có tín hiệu BUY: MACD={current['macd']:.2f} <= Signal={current['macd_signal']:.2f}")
        
        # MACD cắt Signal từ trên xuống → Momentum giảm → Tín hiệu bán (ưu tiên)
        if current['macd'] < current['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            sell_signals += 1
            sell_reasons.append(f"MACD cắt Signal từ trên xuống - MACD: {current['macd']:.2f} < Signal: {current['macd_signal']:.2f}, Histogram: {current['macd_hist']:.2f} [1 điểm]")
        # MACD đang ở dưới Signal → Momentum giảm → Tín hiệu bán
        elif current['macd'] < current['macd_signal']:
            sell_signals += 1
            sell_reasons.append(f"MACD đang dưới Signal (Momentum giảm) - MACD: {current['macd']:.2f} < Signal: {current['macd_signal']:.2f}, Histogram: {current['macd_hist']:.2f} [1 điểm]")
        else:
            logging.debug(f"   ❌ MACD không có tín hiệu SELL: MACD={current['macd']:.2f} >= Signal={current['macd_signal']:.2f}")
        
        # --- Tín hiệu Bollinger Bands (trọng số x1 = 1 điểm) ---
        # Giá chạm Lower Band → Quá bán → Tín hiệu mua
        if current['close'] < current['lower_bb']:
            buy_signals += 1
            buy_reasons.append(f"Giá chạm Lower BB (Quá bán) - Giá: {current['close']:.2f} < Lower BB: {current['lower_bb']:.2f} [1 điểm]")
        # Giá chạm Upper Band → Quá mua → Tín hiệu bán
        elif current['close'] > current['upper_bb']:
            sell_signals += 1
            sell_reasons.append(f"Giá chạm Upper BB (Quá mua) - Giá: {current['close']:.2f} > Upper BB: {current['upper_bb']:.2f} [1 điểm]")
        else:
            logging.debug(f"   ❌ BB không có tín hiệu: Giá={current['close']:.2f} nằm giữa Lower={current['lower_bb']:.2f} và Upper={current['upper_bb']:.2f}")
        
        # ====================================================================
        # LOG KẾT QUẢ ĐẾM TÍN HIỆU
        # ====================================================================
        logging.info("=" * 60)
        logging.info("📊 TỔNG HỢP TÍN HIỆU:")
        logging.info("=" * 60)
        logging.info(f"   ✅ Tín hiệu BUY: {buy_signals} điểm (cần >= {MIN_SIGNAL_STRENGTH})")
        if buy_reasons:
            for reason in buy_reasons:
                logging.info(f"      • {reason}")
        else:
            logging.info(f"      ❌ Không có tín hiệu BUY nào")
        
        logging.info(f"   ❌ Tín hiệu SELL: {sell_signals} điểm (cần >= {MIN_SIGNAL_STRENGTH})")
        if sell_reasons:
            for reason in sell_reasons:
                logging.info(f"      • {reason}")
        else:
            logging.info(f"      ❌ Không có tín hiệu SELL nào")
        logging.info("=" * 60)
        
        # ====================================================================
        # BƯỚC 4: XÁC ĐỊNH TÍN HIỆU CUỐI CÙNG VÀ TÍNH SL/TP
        # ====================================================================
        
        # Chuyển đổi ATR từ giá trị giá sang pips
        # ⚠️ VỚI ETHUSD: 1 pip = 1 USD (không phải 0.01 như XAUUSD)
        # Vậy ATR đã là pips rồi (ATR = 38.87 USD → 38.87 pips)
        atr_value = current['atr']  # ATR tính bằng pips (1 USD = 1 pip cho ETHUSD)
        
        # Kiểm tra ATR filter: Tránh vào lệnh khi volatility quá cao
        max_atr = MAX_ATR if 'MAX_ATR' in globals() else 2000
        if atr_value > max_atr:
            logging.warning(f"⚠️ ATR quá cao: {atr_value:.1f} pips > {max_atr} pips → Bỏ qua tín hiệu (volatility cực đại)")
            return {
                'action': 'HOLD',
                'strength': 0,
                'reason': f'ATR quá cao: {atr_value:.1f} > {max_atr}'
            }
        
        # Kiểm tra tín hiệu mạnh: RSI cắt hoặc EMA cắt
        require_strong_signal = REQUIRE_STRONG_SIGNAL if 'REQUIRE_STRONG_SIGNAL' in globals() else True
        if require_strong_signal:
            # Tín hiệu mạnh BUY: RSI cắt xuống dưới 30 HOẶC EMA20 cắt EMA50 từ dưới lên
            buy_strong_signal = (current['rsi'] < 30 and prev['rsi'] >= 30) or \
                                (current['ema_20'] > current['ema_50'] and prev['ema_20'] <= prev['ema_50'])
            # Tín hiệu mạnh SELL: RSI cắt lên trên 70 HOẶC EMA20 cắt EMA50 từ trên xuống
            sell_strong_signal = (current['rsi'] > 70 and prev['rsi'] <= 70) or \
                                 (current['ema_20'] < current['ema_50'] and prev['ema_20'] >= prev['ema_50'])
        else:
            buy_strong_signal = True
            sell_strong_signal = True
        
        # --- Tín hiệu BUY: Cần tối thiểu MIN_SIGNAL_STRENGTH tín hiệu mua, nhiều hơn tín hiệu bán, và có tín hiệu mạnh ---
        if buy_signals >= MIN_SIGNAL_STRENGTH and buy_signals > sell_signals:
            if require_strong_signal and not buy_strong_signal:
                logging.warning(f"⚠️ BUY signals đủ ({buy_signals} >= {MIN_SIGNAL_STRENGTH}) nhưng thiếu tín hiệu mạnh (RSI cắt hoặc EMA cắt) → Bỏ qua")
                return {
                    'action': 'HOLD',
                    'strength': buy_signals,
                    'reason': 'Thiếu tín hiệu mạnh (RSI cắt hoặc EMA cắt)'
                }
            # Tính SL/TP theo ATR động hoặc công thức cố định
            use_atr_sl_tp = USE_ATR_BASED_SL_TP if 'USE_ATR_BASED_SL_TP' in globals() else True
            atr_multiplier_sl = ATR_MULTIPLIER_SL if 'ATR_MULTIPLIER_SL' in globals() else 1.5
            atr_multiplier_tp = ATR_MULTIPLIER_TP if 'ATR_MULTIPLIER_TP' in globals() else 2.5
            
            if use_atr_sl_tp:
                # Tính SL/TP theo ATR động
                sl_pips = max(self.min_sl_pips, atr_value * atr_multiplier_sl)
                tp_pips = max(self.min_tp_pips, int(atr_value * atr_multiplier_tp))
            else:
                # Tính SL/TP theo công thức cố định (giữ nguyên logic cũ)
                sl_pips = max(self.min_sl_pips, atr_value * 1.5)
                tp_pips = max(self.min_tp_pips, int(sl_pips * MIN_RR_RATIO))
            
            # TP Boost: Tăng TP khi trend mạnh (nếu bật)
            enable_tp_boost = ENABLE_TP_BOOST if 'ENABLE_TP_BOOST' in globals() else True
            if enable_tp_boost:
                rsi_current = current['rsi']
                rsi_threshold_up = RSI_TREND_THRESHOLD_UP if 'RSI_TREND_THRESHOLD_UP' in globals() else 65
                strong_trend_boost = STRONG_TREND_TP_BOOST if 'STRONG_TREND_TP_BOOST' in globals() else 0.3
                
                # Nếu RSI > threshold (uptrend mạnh) → Tăng TP
                if rsi_current > rsi_threshold_up:
                    tp_pips = int(tp_pips * (1 + strong_trend_boost))
                    logging.info(f"📈 TP Boost kích hoạt: RSI={rsi_current:.2f} > {rsi_threshold_up} → TP tăng {strong_trend_boost*100}%: {tp_pips} pips")
            
            return {
                'action': 'BUY',           # Hành động: Mua
                'strength': buy_signals,   # Sức mạnh tín hiệu (số lượng tín hiệu đồng thuận)
                'sl_pips': sl_pips,       # Stop Loss (pips)
                'tp_pips': tp_pips        # Take Profit (pips)
            }
        
        # --- Tín hiệu SELL: Cần tối thiểu MIN_SIGNAL_STRENGTH tín hiệu bán, nhiều hơn tín hiệu mua, và có tín hiệu mạnh ---
        elif sell_signals >= MIN_SIGNAL_STRENGTH and sell_signals > buy_signals:
            if require_strong_signal and not sell_strong_signal:
                logging.warning(f"⚠️ SELL signals đủ ({sell_signals} >= {MIN_SIGNAL_STRENGTH}) nhưng thiếu tín hiệu mạnh (RSI cắt hoặc EMA cắt) → Bỏ qua")
                return {
                    'action': 'HOLD',
                    'strength': sell_signals,
                    'reason': 'Thiếu tín hiệu mạnh (RSI cắt hoặc EMA cắt)'
                }
            # Tính SL/TP theo ATR động hoặc công thức cố định
            use_atr_sl_tp = USE_ATR_BASED_SL_TP if 'USE_ATR_BASED_SL_TP' in globals() else True
            atr_multiplier_sl = ATR_MULTIPLIER_SL if 'ATR_MULTIPLIER_SL' in globals() else 1.5
            atr_multiplier_tp = ATR_MULTIPLIER_TP if 'ATR_MULTIPLIER_TP' in globals() else 2.5
            
            if use_atr_sl_tp:
                # Tính SL/TP theo ATR động
                sl_pips = max(self.min_sl_pips, atr_value * atr_multiplier_sl)
                tp_pips = max(self.min_tp_pips, int(atr_value * atr_multiplier_tp))
            else:
                # Tính SL/TP theo công thức cố định (giữ nguyên logic cũ)
                sl_pips = max(self.min_sl_pips, atr_value * 1.5)
                tp_pips = max(self.min_tp_pips, int(sl_pips * MIN_RR_RATIO))
            
            # TP Boost: Tăng TP khi trend mạnh (nếu bật)
            enable_tp_boost = ENABLE_TP_BOOST if 'ENABLE_TP_BOOST' in globals() else True
            if enable_tp_boost:
                rsi_current = current['rsi']
                rsi_threshold_down = RSI_TREND_THRESHOLD_DOWN if 'RSI_TREND_THRESHOLD_DOWN' in globals() else 35
                strong_trend_boost = STRONG_TREND_TP_BOOST if 'STRONG_TREND_TP_BOOST' in globals() else 0.3
                
                # Nếu RSI < threshold (downtrend mạnh) → Tăng TP
                if rsi_current < rsi_threshold_down:
                    tp_pips = int(tp_pips * (1 + strong_trend_boost))
                    logging.info(f"📉 TP Boost kích hoạt: RSI={rsi_current:.2f} < {rsi_threshold_down} → TP tăng {strong_trend_boost*100}%: {tp_pips} pips")
            
            return {
                'action': 'SELL',          # Hành động: Bán
                'strength': sell_signals,  # Sức mạnh tín hiệu (số lượng tín hiệu đồng thuận)
                'sl_pips': sl_pips,       # Stop Loss (pips)
                'tp_pips': tp_pips        # Take Profit (pips)
            }
        
        # --- Không có tín hiệu rõ ràng → HOLD (giữ nguyên, không giao dịch) ---
        else:
            # Log chi tiết lý do HOLD
            logging.warning("=" * 60)
            logging.warning("⚠️  HOLD - Không đủ điều kiện vào lệnh:")
            logging.warning("=" * 60)
            logging.warning(f"   - Buy signals: {buy_signals}/{MIN_SIGNAL_STRENGTH} (cần >= {MIN_SIGNAL_STRENGTH})")
            logging.warning(f"   - Sell signals: {sell_signals}/{MIN_SIGNAL_STRENGTH} (cần >= {MIN_SIGNAL_STRENGTH})")
            
            if buy_signals >= MIN_SIGNAL_STRENGTH and sell_signals >= MIN_SIGNAL_STRENGTH:
                logging.warning(f"   - Lý do: Cả BUY và SELL đều đủ điểm ({buy_signals} vs {sell_signals}) → Mâu thuẫn")
            elif buy_signals >= MIN_SIGNAL_STRENGTH and buy_signals <= sell_signals:
                logging.warning(f"   - Lý do: BUY đủ điểm ({buy_signals}) nhưng không nhiều hơn SELL ({sell_signals})")
            elif sell_signals >= MIN_SIGNAL_STRENGTH and sell_signals <= buy_signals:
                logging.warning(f"   - Lý do: SELL đủ điểm ({sell_signals}) nhưng không nhiều hơn BUY ({buy_signals})")
            else:
                logging.warning(f"   - Lý do: Không đủ tín hiệu (BUY: {buy_signals}/{MIN_SIGNAL_STRENGTH}, SELL: {sell_signals}/{MIN_SIGNAL_STRENGTH})")
            
            if buy_reasons:
                logging.warning(f"   - Chi tiết BUY signals:")
                for reason in buy_reasons:
                    logging.warning(f"      • {reason}")
            
            if sell_reasons:
                logging.warning(f"   - Chi tiết SELL signals:")
                for reason in sell_reasons:
                    logging.warning(f"      • {reason}")
            
            logging.warning("=" * 60)
            
            return {
                'action': 'HOLD',  # Hành động: Không giao dịch
                'strength': 0,      # Không có tín hiệu (strength = 0)
                'sl_pips': 0,      # Không có SL (vì không có lệnh)
                'tp_pips': 0       # Không có TP (vì không có lệnh)
            }