"""
PHÂN TÍCH KỸ THUẬT - Technical Analyzer
========================================
Module này chứa các phương thức tính toán các chỉ báo kỹ thuật và phân tích tín hiệu giao dịch.
"""

import pandas as pd
import numpy as np
from config_xauusd import *

class TechnicalAnalyzer:
    """
    Lớp phân tích kỹ thuật cho bot giao dịch XAUUSD
    
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
        - Cần tối thiểu 3 tín hiệu đồng thuận để mở lệnh
        - RSI có trọng số x2 (2 điểm) vì là chỉ báo mạnh
        - EMA, MACD, BB mỗi cái 1 điểm
        
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
        df['lower_bb'] = lower_bb    # Dải dưới
        
        # ATR (Average True Range) - để tính SL/TP dựa trên độ biến động
        df['atr'] = self.calculate_atr(high, low, close)
        
        # ====================================================================
        # BƯỚC 2: LẤY GIÁ TRỊ HIỆN TẠI VÀ TRƯỚC ĐÓ
        # ====================================================================
        
        current = df.iloc[-1]  # Nến hiện tại (mới nhất)
        prev = df.iloc[-2]     # Nến trước đó (để so sánh)
        
        # ====================================================================
        # BƯỚC 3: ĐẾM SỐ LƯỢNG TÍN HIỆU MUA/BÁN
        # ====================================================================
        
        buy_signals = 0   # Số tín hiệu mua (cộng dồn)
        sell_signals = 0  # Số tín hiệu bán (cộng dồn)
        
        # --- Tín hiệu RSI (trọng số x2 = 2 điểm) ---
        # RSI cắt từ trên xuống dưới 30 → Quá bán → Tín hiệu mua mạnh
        if current['rsi'] < 30 and prev['rsi'] >= 30:
            buy_signals += 2  # RSI có trọng số cao hơn (2 điểm)
        
        # RSI cắt từ dưới lên trên 70 → Quá mua → Tín hiệu bán mạnh
        elif current['rsi'] > 70 and prev['rsi'] <= 70:
            sell_signals += 2  # RSI có trọng số cao hơn (2 điểm)
        
        # --- Tín hiệu EMA (trọng số x1 = 1 điểm) ---
        # EMA20 cắt EMA50 từ dưới lên → Uptrend mới → Tín hiệu mua
        if current['ema_20'] > current['ema_50'] and prev['ema_20'] <= prev['ema_50']:
            buy_signals += 1
        
        # EMA20 cắt EMA50 từ trên xuống → Downtrend mới → Tín hiệu bán
        elif current['ema_20'] < current['ema_50'] and prev['ema_20'] >= prev['ema_50']:
            sell_signals += 1
        
        # --- Tín hiệu MACD (trọng số x1 = 1 điểm) ---
        # MACD cắt Signal từ dưới lên → Momentum tăng → Tín hiệu mua
        if current['macd'] > current['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            buy_signals += 1
        
        # MACD cắt Signal từ trên xuống → Momentum giảm → Tín hiệu bán
        elif current['macd'] < current['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            sell_signals += 1
        
        # --- Tín hiệu Bollinger Bands (trọng số x1 = 1 điểm) ---
        # Giá chạm Lower Band → Quá bán → Tín hiệu mua
        if current['close'] < current['lower_bb']:
            buy_signals += 1
        
        # Giá chạm Upper Band → Quá mua → Tín hiệu bán
        elif current['close'] > current['upper_bb']:
            sell_signals += 1
        
        # ====================================================================
        # BƯỚC 4: XÁC ĐỊNH TÍN HIỆU CUỐI CÙNG VÀ TÍNH SL/TP
        # ====================================================================
        
        # Chuyển đổi ATR từ giá trị giá sang pips (1 pip XAUUSD = 0.01)
        atr_value = current['atr'] / 0.01  # ATR tính bằng pips
        
        # --- Tín hiệu BUY: Cần tối thiểu 3 tín hiệu mua và nhiều hơn tín hiệu bán ---
        if buy_signals >= 3 and buy_signals > sell_signals:
            # Tính SL: Tối thiểu MIN_SL_PIPS hoặc ATR * 1.5 (lấy giá trị lớn hơn)
            sl_pips = max(self.min_sl_pips, atr_value * 1.5)
            
            # Tính TP: Tối thiểu MIN_TP_PIPS hoặc SL * MIN_RR_RATIO (lấy giá trị lớn hơn)
            tp_pips = max(self.min_tp_pips, int(sl_pips * MIN_RR_RATIO))
            
            return {
                'action': 'BUY',           # Hành động: Mua
                'strength': buy_signals,   # Sức mạnh tín hiệu (số lượng tín hiệu đồng thuận)
                'sl_pips': sl_pips,       # Stop Loss (pips)
                'tp_pips': tp_pips        # Take Profit (pips)
            }
        
        # --- Tín hiệu SELL: Cần tối thiểu 3 tín hiệu bán và nhiều hơn tín hiệu mua ---
        elif sell_signals >= 3 and sell_signals > buy_signals:
            # Tính SL: Tối thiểu MIN_SL_PIPS hoặc ATR * 1.5 (lấy giá trị lớn hơn)
            sl_pips = max(self.min_sl_pips, atr_value * 1.5)
            
            # Tính TP: Tối thiểu MIN_TP_PIPS hoặc SL * MIN_RR_RATIO (lấy giá trị lớn hơn)
            tp_pips = max(self.min_tp_pips, int(sl_pips * MIN_RR_RATIO))
            
            return {
                'action': 'SELL',          # Hành động: Bán
                'strength': sell_signals,  # Sức mạnh tín hiệu (số lượng tín hiệu đồng thuận)
                'sl_pips': sl_pips,       # Stop Loss (pips)
                'tp_pips': tp_pips        # Take Profit (pips)
            }
        
        # --- Không có tín hiệu rõ ràng → HOLD (giữ nguyên, không giao dịch) ---
        else:
            return {
                'action': 'HOLD',  # Hành động: Không giao dịch
                'strength': 0,      # Không có tín hiệu (strength = 0)
                'sl_pips': 0,      # Không có SL (vì không có lệnh)
                'tp_pips': 0       # Không có TP (vì không có lệnh)
            }