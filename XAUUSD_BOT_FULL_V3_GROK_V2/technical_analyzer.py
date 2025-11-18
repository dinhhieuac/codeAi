"""
PHÂN TÍCH KỸ THUẬT - Technical Analyzer
========================================
Module này chứa các phương thức tính toán các chỉ báo kỹ thuật và phân tích tín hiệu giao dịch.
"""

import pandas as pd
import numpy as np
import logging
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
        import MetaTrader5 as mt5
        self.mt5 = mt5
        
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
    
    def check_pullback_to_ema21(self, df):
        """
        Kiểm tra pullback về EMA21 (vùng xác nhận entry)
        
        Pullback về EMA21: Giá đã tăng/giảm, sau đó quay lại chạm EMA21
        - BUY: Giá pullback về EMA21 từ trên xuống (sau khi đã tăng)
        - SELL: Giá pullback về EMA21 từ dưới lên (sau khi đã giảm)
        
        Args:
            df: DataFrame với EMA21 đã tính
            
        Returns:
            Tuple (bool, str): (has_pullback, direction) - 'BUY', 'SELL', hoặc None
        """
        if len(df) < 5:
            return False, None
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        ema21_current = current['ema_21']
        price_current = current['close']
        price_prev = prev['close']
        price_prev2 = prev2['close']
        
        # Kiểm tra pullback BUY: Giá đã tăng, sau đó quay lại chạm EMA21
        # Điều kiện: Giá trước đó > EMA21, giá hiện tại gần EMA21 (trong phạm vi 0.5%)
        if price_prev2 > ema21_current and abs(price_current - ema21_current) / ema21_current < 0.005:
            # Giá đang pullback về EMA21 từ trên xuống
            return True, 'BUY'
        
        # Kiểm tra pullback SELL: Giá đã giảm, sau đó quay lại chạm EMA21
        # Điều kiện: Giá trước đó < EMA21, giá hiện tại gần EMA21 (trong phạm vi 0.5%)
        if price_prev2 < ema21_current and abs(price_current - ema21_current) / ema21_current < 0.005:
            # Giá đang pullback về EMA21 từ dưới lên
            return True, 'SELL'
        
        return False, None
    
    def check_sweep_low(self, df):
        """
        Kiểm tra sweep đáy/swing low (vùng xác nhận entry cho BUY)
        
        Sweep low: Giá phá vỡ swing low (đáy) trước đó, sau đó quay lại tăng
        - Điều kiện: Giá tạo đáy mới thấp hơn đáy trước, sau đó đóng cửa trên đáy cũ
        
        Args:
            df: DataFrame với high, low, close
            
        Returns:
            bool: True nếu có sweep low (tín hiệu BUY)
        """
        if len(df) < 10:
            return False
        
        # Tìm swing low trong 10 nến gần nhất
        recent_lows = df['low'].tail(10)
        swing_low = recent_lows.min()
        swing_low_idx = recent_lows.idxmin()
        
        # Kiểm tra xem giá có phá vỡ swing low và quay lại không
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Nếu giá phá vỡ swing low (low < swing_low) nhưng đóng cửa trên swing_low
        if current['low'] < swing_low and current['close'] > swing_low:
            # Có sweep low → Tín hiệu BUY
            return True
        
        return False
    
    def check_break_retest(self, df):
        """
        Kiểm tra break retest zone (vùng xác nhận entry)
        
        Break retest: Giá phá vỡ một mức quan trọng, sau đó quay lại test lại mức đó
        - BUY: Giá phá vỡ resistance, sau đó pullback về test lại
        - SELL: Giá phá vỡ support, sau đó pullback về test lại
        
        Args:
            df: DataFrame với high, low, close, EMA21
            
        Returns:
            Tuple (bool, str): (has_break_retest, direction) - 'BUY', 'SELL', hoặc None
        """
        if len(df) < 10:
            return False, None
        
        # Tìm resistance (high) và support (low) trong 10 nến gần nhất
        recent_highs = df['high'].tail(10)
        recent_lows = df['low'].tail(10)
        resistance = recent_highs.max()
        support = recent_lows.min()
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        # Kiểm tra break retest BUY: Giá phá vỡ resistance, sau đó pullback về test
        # Điều kiện: Giá đã phá vỡ resistance (high > resistance), sau đó pullback về gần resistance
        if prev2['high'] > resistance and abs(current['close'] - resistance) / resistance < 0.003:
            # Giá đã phá vỡ resistance và đang test lại (trong phạm vi 0.3%)
            return True, 'BUY'
        
        # Kiểm tra break retest SELL: Giá phá vỡ support, sau đó pullback về test
        # Điều kiện: Giá đã phá vỡ support (low < support), sau đó pullback về gần support
        if prev2['low'] < support and abs(current['close'] - support) / support < 0.003:
            # Giá đã phá vỡ support và đang test lại (trong phạm vi 0.3%)
            return True, 'SELL'
        
        return False, None
    
    def check_ob_fvg(self, df):
        """
        Kiểm tra OB/FVG (Order Block/Fair Value Gap) rõ ràng
        
        Order Block (OB): Vùng giá có nến lớn với body lớn, thường là vùng entry của smart money
        Fair Value Gap (FVG): Khoảng trống giá giữa 3 nến (nến 1 và 3 không overlap với nến 2)
        
        Args:
            df: DataFrame với open, high, low, close
            
        Returns:
            Tuple (bool, str): (has_ob_fvg, direction) - 'BUY', 'SELL', hoặc None
        """
        if len(df) < 5:
            return False, None
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        # Kiểm tra Order Block BUY: Nến lớn với body lớn, đóng cửa cao
        current_body = abs(current['close'] - current['open'])
        current_range = current['high'] - current['low']
        if current_range > 0:
            body_ratio = current_body / current_range
            # Nến có body > 60% range và đóng cửa cao (bullish)
            if body_ratio > 0.6 and current['close'] > current['open']:
                return True, 'BUY'
        
        # Kiểm tra Order Block SELL: Nến lớn với body lớn, đóng cửa thấp
        if current_range > 0:
            body_ratio = current_body / current_range
            # Nến có body > 60% range và đóng cửa thấp (bearish)
            if body_ratio > 0.6 and current['close'] < current['open']:
                return True, 'SELL'
        
        # Kiểm tra Fair Value Gap BUY: Nến 1 và 3 không overlap với nến 2 (gap lên)
        if prev['high'] < prev2['low'] and prev['high'] < current['low']:
            # Có FVG lên → Tín hiệu BUY
            return True, 'BUY'
        
        # Kiểm tra Fair Value Gap SELL: Nến 1 và 3 không overlap với nến 2 (gap xuống)
        if prev['low'] > prev2['high'] and prev['low'] > current['high']:
            # Có FVG xuống → Tín hiệu SELL
            return True, 'SELL'
        
        return False, None
    
    def check_m15_range(self, df):
        """
        Kiểm tra range M15 (không vào lệnh khi sideway - range nhỏ < $12)
        
        Range = High - Low của nến hiện tại hoặc trung bình range của các nến gần đây
        
        Args:
            df: DataFrame với high, low
            
        Returns:
            Tuple (bool, float): (is_valid_range, range_usd) - True nếu range >= $12
        """
        if len(df) < 5:
            return False, 0.0
        
        # Tính range trung bình của 5 nến gần nhất (để tránh false signal từ 1 nến)
        recent_5 = df.tail(5)
        ranges = recent_5['high'] - recent_5['low']
        avg_range = ranges.mean()
        
        # Range >= $12 → Có thể trade (không sideway)
        # Range < $12 → Sideway, không trade
        min_range_usd = 12.0
        
        is_valid = avg_range >= min_range_usd
        
        return is_valid, avg_range
    
    def get_h1_trend(self, symbol):
        """
        Lấy trend từ H1 (EMA50 > EMA200 cho uptrend, EMA50 < EMA200 cho downtrend)
        
        Theo rule mới:
        - H1 trend tăng → ưu tiên Buy ở M15
        - H1 trend giảm → ưu tiên Sell ở M15
        
        Args:
            symbol: Symbol cần phân tích (ví dụ: "XAUUSDc")
            
        Returns:
            Dict với keys:
            - 'trend': 'BULLISH', 'BEARISH', hoặc 'NEUTRAL'
            - 'ema50': Giá trị EMA 50 trên H1
            - 'ema200': Giá trị EMA 200 trên H1
            - 'price': Giá hiện tại trên H1
            None nếu không lấy được dữ liệu
        """
        try:
            # Lấy dữ liệu H1 (1 giờ = 60 phút)
            h1_rates = self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_H1, 0, 200)
            if h1_rates is None or len(h1_rates) < 200:
                logging.warning("⚠️ Không lấy được đủ dữ liệu H1 cho trend analysis")
                return None
            
            h1_df = pd.DataFrame(h1_rates)
            h1_close = h1_df['close']
            h1_ema50 = self.calculate_ema(h1_close, 50).iloc[-1]
            h1_ema200 = self.calculate_ema(h1_close, 200).iloc[-1]
            h1_price = h1_close.iloc[-1]
            
            # Xác định trend H1: EMA50 > EMA200 = BULLISH, EMA50 < EMA200 = BEARISH
            if h1_ema50 > h1_ema200:
                h1_trend = 'BULLISH'
            elif h1_ema50 < h1_ema200:
                h1_trend = 'BEARISH'
            else:
                h1_trend = 'NEUTRAL'
            
            logging.info("=" * 60)
            logging.info("📊 H1 TREND ANALYSIS:")
            logging.info("=" * 60)
            logging.info(f"   📈 H1: Price={h1_price:.2f}, EMA50={h1_ema50:.2f}, EMA200={h1_ema200:.2f} → Trend: {h1_trend}")
            logging.info("=" * 60)
            
            return {
                'trend': h1_trend,
                'ema50': h1_ema50,
                'ema200': h1_ema200,
                'price': h1_price
            }
        except Exception as e:
            logging.error(f"❌ Lỗi khi lấy H1 trend: {e}")
            return None
    
    def get_multi_timeframe_bias(self, symbol):
        """
        Lấy bias từ multi-timeframe (D1/H4) theo grok.md
        
        Theo grok.md:
        - D1/H4 xác định bias (EMA 50/200 cho trend)
        - M15 cho entry
        - Chỉ BUY khi D1/H4 là uptrend, chỉ SELL khi D1/H4 là downtrend
        
        Args:
            symbol: Symbol cần phân tích (ví dụ: "XAUUSDc")
            
        Returns:
            Dict với keys:
            - 'bias': 'BULLISH', 'BEARISH', hoặc 'NEUTRAL'
            - 'h4_trend': 'BULLISH', 'BEARISH', hoặc 'NEUTRAL'
            - 'd1_trend': 'BULLISH', 'BEARISH', hoặc 'NEUTRAL'
            - 'h4_ema50': Giá trị EMA 50 trên H4
            - 'h4_ema200': Giá trị EMA 200 trên H4
            - 'd1_ema50': Giá trị EMA 50 trên D1
            - 'd1_ema200': Giá trị EMA 200 trên D1
            None nếu không lấy được dữ liệu
        """
        try:
            # Lấy dữ liệu H4 (4 giờ = 240 phút)
            h4_rates = self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_H4, 0, 200)
            if h4_rates is None or len(h4_rates) < 200:
                logging.warning("⚠️ Không lấy được đủ dữ liệu H4 cho multi-timeframe analysis")
                return None
            
            h4_df = pd.DataFrame(h4_rates)
            h4_close = h4_df['close']
            h4_ema50 = self.calculate_ema(h4_close, 50).iloc[-1]
            h4_ema200 = self.calculate_ema(h4_close, 200).iloc[-1]
            h4_price = h4_close.iloc[-1]
            
            # Xác định trend H4
            if h4_price > h4_ema50 and h4_ema50 > h4_ema200:
                h4_trend = 'BULLISH'
            elif h4_price < h4_ema50 and h4_ema50 < h4_ema200:
                h4_trend = 'BEARISH'
            else:
                h4_trend = 'NEUTRAL'
            
            # Lấy dữ liệu D1 (1 ngày = 1440 phút)
            d1_rates = self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_D1, 0, 200)
            if d1_rates is None or len(d1_rates) < 200:
                logging.warning("⚠️ Không lấy được đủ dữ liệu D1 cho multi-timeframe analysis")
                return None
            
            d1_df = pd.DataFrame(d1_rates)
            d1_close = d1_df['close']
            d1_ema50 = self.calculate_ema(d1_close, 50).iloc[-1]
            d1_ema200 = self.calculate_ema(d1_close, 200).iloc[-1]
            d1_price = d1_close.iloc[-1]
            
            # Xác định trend D1
            if d1_price > d1_ema50 and d1_ema50 > d1_ema200:
                d1_trend = 'BULLISH'
            elif d1_price < d1_ema50 and d1_ema50 < d1_ema200:
                d1_trend = 'BEARISH'
            else:
                d1_trend = 'NEUTRAL'
            
            # Xác định bias tổng thể (ưu tiên D1, nếu D1 neutral thì dùng H4)
            if d1_trend != 'NEUTRAL':
                bias = d1_trend
            elif h4_trend != 'NEUTRAL':
                bias = h4_trend
            else:
                bias = 'NEUTRAL'
            
            logging.info("=" * 60)
            logging.info("📊 MULTI-TIMEFRAME BIAS (theo grok.md):")
            logging.info("=" * 60)
            logging.info(f"   📈 D1: Price={d1_price:.2f}, EMA50={d1_ema50:.2f}, EMA200={d1_ema200:.2f} → Trend: {d1_trend}")
            logging.info(f"   📊 H4: Price={h4_price:.2f}, EMA50={h4_ema50:.2f}, EMA200={h4_ema200:.2f} → Trend: {h4_trend}")
            logging.info(f"   🎯 Overall Bias: {bias}")
            logging.info("=" * 60)
            
            return {
                'bias': bias,
                'h4_trend': h4_trend,
                'd1_trend': d1_trend,
                'h4_ema50': h4_ema50,
                'h4_ema200': h4_ema200,
                'd1_ema50': d1_ema50,
                'd1_ema200': d1_ema200,
                'h4_price': h4_price,
                'd1_price': d1_price
            }
        except Exception as e:
            logging.error(f"❌ Lỗi khi lấy multi-timeframe bias: {e}")
            return None
        
    def analyze(self, df, symbol=None, use_multi_timeframe=True):
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
            symbol: Symbol để lấy multi-timeframe bias (theo grok.md: D1/H4 cho bias)
            use_multi_timeframe: Có sử dụng multi-timeframe analysis không (theo grok.md)
            
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
        
        # ====================================================================
        # MULTI-TIMEFRAME BIAS - H1 TREND (Rule mới: H1 trend tăng → ưu tiên Buy, H1 trend giảm → ưu tiên Sell)
        # ====================================================================
        h1_trend_info = None
        if use_multi_timeframe and symbol:
            h1_trend_info = self.get_h1_trend(symbol)
            if h1_trend_info:
                logging.info(f"✅ H1 Trend: {h1_trend_info['trend']} (EMA50={h1_trend_info['ema50']:.2f}, EMA200={h1_trend_info['ema200']:.2f})")
            else:
                logging.warning("⚠️ Không lấy được H1 trend, tiếp tục phân tích M15")
        
        # ====================================================================
        # KIỂM TRA RANGE M15 (Không vào lệnh khi sideway - range < $12)
        # ====================================================================
        range_valid, range_usd = self.check_m15_range(df)
        if not range_valid:
            logging.warning(f"⚠️ M15 đang sideway (range ${range_usd:.2f} < $12) → Không trade")
            return {
                'action': 'HOLD',
                'strength': 0,
                'sl_pips': 0,
                'tp_pips': 0,
                'reason': f'M15 sideway (range ${range_usd:.2f} < $12)'
            }
        else:
            logging.info(f"✅ M15 range hợp lệ: ${range_usd:.2f} >= $12 (không sideway)")
        
        # ====================================================================
        # KIỂM TRA VÙNG XÁC NHẬN ENTRY
        # ====================================================================
        # 1. Pullback về EMA21
        has_pullback, pullback_direction = self.check_pullback_to_ema21(df)
        if has_pullback:
            logging.info(f"✅ Pullback về EMA21 phát hiện: {pullback_direction}")
        
        # 2. Sweep đáy/swing low (cho BUY)
        has_sweep_low = self.check_sweep_low(df)
        if has_sweep_low:
            logging.info(f"✅ Sweep low phát hiện → Tín hiệu BUY")
        
        # 3. Break retest zone
        has_break_retest, break_retest_direction = self.check_break_retest(df)
        if has_break_retest:
            logging.info(f"✅ Break retest phát hiện: {break_retest_direction}")
        
        # 4. OB/FVG rõ ràng
        has_ob_fvg, ob_fvg_direction = self.check_ob_fvg(df)
        if has_ob_fvg:
            logging.info(f"✅ OB/FVG phát hiện: {ob_fvg_direction}")
        
        # Tổng hợp vùng xác nhận entry
        entry_confirmation_buy = (has_pullback and pullback_direction == 'BUY') or has_sweep_low or (has_break_retest and break_retest_direction == 'BUY') or (has_ob_fvg and ob_fvg_direction == 'BUY')
        entry_confirmation_sell = (has_pullback and pullback_direction == 'SELL') or (has_break_retest and break_retest_direction == 'SELL') or (has_ob_fvg and ob_fvg_direction == 'SELL')
        
        if not entry_confirmation_buy and not entry_confirmation_sell:
            logging.warning("⚠️ Không có vùng xác nhận entry (pullback EMA21, sweep low, break retest, OB/FVG) → HOLD")
            return {
                'action': 'HOLD',
                'strength': 0,
                'sl_pips': 0,
                'tp_pips': 0,
                'reason': 'Không có vùng xác nhận entry'
            }
        
        # Lấy các cột giá cần thiết
        close = df['close']  # Giá đóng cửa
        high = df['high']   # Giá cao nhất
        low = df['low']     # Giá thấp nhất
        
        # ====================================================================
        # BƯỚC 1: TÍNH TOÁN CÁC CHỈ BÁO KỸ THUẬT
        # ====================================================================
        
        # RSI (Relative Strength Index) - chu kỳ 14
        df['rsi'] = self.calculate_rsi(close, 14)
        
        # EMA (Exponential Moving Average) - EMA 9/21 theo chiến lược ATR Momentum Breakout Scalping (grok.md)
        df['ema_9'] = self.calculate_ema(close, 9)   # EMA ngắn hạn (theo grok.md)
        df['ema_21'] = self.calculate_ema(close, 21)  # EMA dài hạn (theo grok.md)
        
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
        logging.info(f"   📊 EMA9: {current['ema_9']:.2f} | EMA21: {current['ema_21']:.2f}")
        logging.info(f"   📉 MACD: {current['macd']:.2f} | Signal: {current['macd_signal']:.2f} | Histogram: {current['macd_hist']:.2f}")
        logging.info(f"   🎯 Bollinger Bands: Upper={current['upper_bb']:.2f} | Middle={current['middle_bb']:.2f} | Lower={current['lower_bb']:.2f}")
        atr_value = current['atr'] / 0.01  # ATR tính bằng pips
        logging.info(f"   📏 ATR: {current['atr']:.2f} ({atr_value:.1f} pips)")
        # Volume confirmation (nếu có dữ liệu volume)
        if 'tick_volume' in df.columns:
            try:
                volume_current = float(current['tick_volume'])
                volume_prev = float(prev['tick_volume'])
                
                # Kiểm tra giá trị hợp lệ (không phải NaN, inf, hoặc quá lớn)
                if (not np.isnan(volume_current) and not np.isnan(volume_prev) and 
                    not np.isinf(volume_current) and not np.isinf(volume_prev) and
                    volume_prev > 0 and volume_current >= 0):
                    # Sử dụng safe division để tránh overflow
                    volume_diff = volume_current - volume_prev
                    if abs(volume_diff) < 1e10:  # Tránh overflow
                        volume_change = (volume_diff / volume_prev) * 100
                    else:
                        volume_change = 0  # Quá lớn, không tính được
                else:
                    volume_change = 0
                logging.info(f"   📊 Volume: {volume_current:.0f} (Thay đổi: {volume_change:+.1f}%)")
            except (ValueError, TypeError, OverflowError) as e:
                logging.warning(f"   ⚠️ Lỗi tính volume_change: {e}")
                volume_change = 0
                logging.info(f"   📊 Volume: {current['tick_volume']:.0f} (Không thể tính thay đổi)")
        logging.info("=" * 60)
        
        # ====================================================================
        # BƯỚC 3: ĐẾM SỐ LƯỢNG TÍN HIỆU MUA/BÁN
        # ====================================================================
        
        buy_signals = 0   # Số tín hiệu mua (cộng dồn)
        sell_signals = 0  # Số tín hiệu bán (cộng dồn)
        buy_reasons = []  # Danh sách lý do tín hiệu mua
        sell_reasons = []  # Danh sách lý do tín hiệu bán
        
        # --- Tín hiệu RSI (theo grok.md: RSI >30 cho BUY, RSI <70 cho SELL) ---
        # BUY: RSI > 30 (theo grok.md - không cần quá bán, chỉ cần không quá mua)
        if current['rsi'] > 30:
            buy_signals += 1
            buy_reasons.append(f"RSI > 30 (theo grok.md) - RSI: {current['rsi']:.2f} [1 điểm]")
        else:
            logging.debug(f"   ❌ RSI không có tín hiệu BUY: {current['rsi']:.2f} (cần > 30 theo grok.md)")
        
        # SELL: RSI < 70 (theo grok.md - không cần quá mua, chỉ cần không quá bán)
        if current['rsi'] < 70:
            sell_signals += 1
            sell_reasons.append(f"RSI < 70 (theo grok.md) - RSI: {current['rsi']:.2f} [1 điểm]")
        else:
            logging.debug(f"   ❌ RSI không có tín hiệu SELL: {current['rsi']:.2f} (cần < 70 theo grok.md)")
        
        # --- Tín hiệu EMA 9/21 (theo grok.md - ATR Momentum Breakout Scalping) ---
        # BUY: Giá breakout trên EMA 9, EMA 9 > EMA 21 (theo grok.md)
        price_above_ema9 = current['close'] > current['ema_9']
        price_prev_below_ema9 = prev['close'] <= prev['ema_9']
        ema9_above_ema21 = current['ema_9'] > current['ema_21']
        
        # Breakout trên EMA 9 (giá vừa vượt lên trên EMA 9) → Tín hiệu mua mạnh
        if price_above_ema9 and price_prev_below_ema9 and ema9_above_ema21:
            buy_signals += 2  # Breakout có trọng số cao hơn (2 điểm)
            buy_reasons.append(f"Giá breakout trên EMA 9 (EMA9 > EMA21) - Giá: {current['close']:.2f} > EMA9: {current['ema_9']:.2f} > EMA21: {current['ema_21']:.2f} [2 điểm]")
        # Giá đang ở trên EMA 9 và EMA 9 > EMA 21 → Uptrend → Tín hiệu mua
        elif price_above_ema9 and ema9_above_ema21:
            buy_signals += 1
            buy_reasons.append(f"Giá trên EMA 9, EMA9 > EMA21 (Uptrend) - Giá: {current['close']:.2f} > EMA9: {current['ema_9']:.2f} > EMA21: {current['ema_21']:.2f} [1 điểm]")
        else:
            logging.debug(f"   ❌ EMA không có tín hiệu BUY: Giá={current['close']:.2f}, EMA9={current['ema_9']:.2f}, EMA21={current['ema_21']:.2f}")
        
        # SELL: Giá breakout dưới EMA 9, EMA 9 < EMA 21
        price_below_ema9 = current['close'] < current['ema_9']
        price_prev_above_ema9 = prev['close'] >= prev['ema_9']
        ema9_below_ema21 = current['ema_9'] < current['ema_21']
        
        # Breakout dưới EMA 9 (giá vừa vượt xuống dưới EMA 9) → Tín hiệu bán mạnh
        if price_below_ema9 and price_prev_above_ema9 and ema9_below_ema21:
            sell_signals += 2  # Breakout có trọng số cao hơn (2 điểm)
            sell_reasons.append(f"Giá breakout dưới EMA 9 (EMA9 < EMA21) - Giá: {current['close']:.2f} < EMA9: {current['ema_9']:.2f} < EMA21: {current['ema_21']:.2f} [2 điểm]")
        # Giá đang ở dưới EMA 9 và EMA 9 < EMA 21 → Downtrend → Tín hiệu bán
        elif price_below_ema9 and ema9_below_ema21:
            sell_signals += 1
            sell_reasons.append(f"Giá dưới EMA 9, EMA9 < EMA21 (Downtrend) - Giá: {current['close']:.2f} < EMA9: {current['ema_9']:.2f} < EMA21: {current['ema_21']:.2f} [1 điểm]")
        else:
            logging.debug(f"   ❌ EMA không có tín hiệu SELL: Giá={current['close']:.2f}, EMA9={current['ema_9']:.2f}, EMA21={current['ema_21']:.2f}")
        
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
        
        # Chuyển đổi ATR từ giá trị giá sang pips (1 pip XAUUSD = 0.01)
        atr_value = current['atr'] / 0.01  # ATR tính bằng pips
        
        # Kiểm tra điều kiện ATR > 12 pips (theo grok.md)
        atr_min_pips = 12  # ATR tối thiểu theo grok.md
        
        # Kiểm tra volume confirmation (theo grok.md: volume tăng khi breakout)
        volume_confirmed = True  # Mặc định True nếu không có dữ liệu volume
        if 'tick_volume' in df.columns:
            try:
                volume_current = float(current['tick_volume'])
                volume_prev = float(prev['tick_volume'])
                
                # Kiểm tra giá trị hợp lệ (không phải NaN, inf, hoặc quá lớn)
                if (not np.isnan(volume_current) and not np.isnan(volume_prev) and 
                    not np.isinf(volume_current) and not np.isinf(volume_prev) and
                    volume_prev > 0 and volume_current >= 0):
                    # Volume tăng khi breakout (theo grok.md)
                    volume_confirmed = volume_current >= volume_prev * 0.9  # Cho phép giảm nhẹ 10%
                    if not volume_confirmed:
                        logging.debug(f"   ⚠️ Volume không xác nhận: {volume_current:.0f} < {volume_prev * 0.9:.0f}")
                else:
                    # Giá trị không hợp lệ, giữ mặc định True
                    logging.debug(f"   ⚠️ Volume không hợp lệ: current={volume_current}, prev={volume_prev}")
            except (ValueError, TypeError, OverflowError) as e:
                logging.warning(f"   ⚠️ Lỗi kiểm tra volume confirmation: {e}")
                # Giữ mặc định True khi có lỗi
        
        # --- Tín hiệu BUY: Rule mới - H1 trend tăng → ưu tiên Buy ở M15 ---
        # Điều kiện đầy đủ:
        # 1. H1 trend = BULLISH (EMA50 > EMA200)
        # 2. Có vùng xác nhận entry (pullback EMA21, sweep low, break retest, OB/FVG)
        # 3. buy_signals >= MIN_SIGNAL_STRENGTH, buy_signals > sell_signals
        # 4. ATR > 12 pips, Volume confirmed
        h1_allows_buy = True
        if h1_trend_info:
            if h1_trend_info['trend'] == 'BEARISH':
                h1_allows_buy = False
                logging.warning(f"⚠️ H1 trend là BEARISH → Không cho phép BUY (Rule mới)")
            elif h1_trend_info['trend'] == 'BULLISH':
                logging.info(f"✅ H1 trend là BULLISH → Ưu tiên BUY ở M15 (Rule mới)")
            else:
                logging.warning(f"⚠️ H1 trend là NEUTRAL → Không rõ xu hướng")
        else:
            logging.warning("⚠️ Không lấy được H1 trend → Bỏ qua filter H1")
        
        if buy_signals >= MIN_SIGNAL_STRENGTH and buy_signals > sell_signals and atr_value > atr_min_pips and volume_confirmed and h1_allows_buy and entry_confirmation_buy:
            # Tính SL/TP theo grok.md: SL = Entry ± 1.5×ATR
            use_atr_sl_tp = USE_ATR_BASED_SL_TP if 'USE_ATR_BASED_SL_TP' in globals() else True
            # Theo grok.md: SL = 1.5×ATR (thay vì 2.5×ATR hiện tại)
            atr_multiplier_sl = 1.5  # Theo grok.md
            atr_multiplier_tp = ATR_MULTIPLIER_TP if 'ATR_MULTIPLIER_TP' in globals() else 2.5
            
            if use_atr_sl_tp:
                # Tính SL/TP theo ATR động (theo grok.md)
                sl_pips = max(self.min_sl_pips, atr_value * atr_multiplier_sl)
                # TP sẽ được tính theo partial close strategy (TP1: +15 pips, TP2: +30 pips, TP3: trailing)
                # Tạm thời dùng ATR multiplier cho TP, sẽ được điều chỉnh trong partial close
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
        
        # --- Tín hiệu SELL: Rule mới - H1 trend giảm → ưu tiên Sell ở M15 ---
        # Điều kiện đầy đủ:
        # 1. H1 trend = BEARISH (EMA50 < EMA200)
        # 2. Có vùng xác nhận entry (pullback EMA21, break retest, OB/FVG)
        # 3. sell_signals >= MIN_SIGNAL_STRENGTH, sell_signals > buy_signals
        # 4. ATR > 12 pips, Volume confirmed
        h1_allows_sell = True
        if h1_trend_info:
            if h1_trend_info['trend'] == 'BULLISH':
                h1_allows_sell = False
                logging.warning(f"⚠️ H1 trend là BULLISH → Không cho phép SELL (Rule mới)")
            elif h1_trend_info['trend'] == 'BEARISH':
                logging.info(f"✅ H1 trend là BEARISH → Ưu tiên SELL ở M15 (Rule mới)")
            else:
                logging.warning(f"⚠️ H1 trend là NEUTRAL → Không rõ xu hướng")
        else:
            logging.warning("⚠️ Không lấy được H1 trend → Bỏ qua filter H1")
        
        if sell_signals >= MIN_SIGNAL_STRENGTH and sell_signals > buy_signals and atr_value > atr_min_pips and volume_confirmed and h1_allows_sell and entry_confirmation_sell:
            # Tính SL/TP theo grok.md: SL = Entry ± 1.5×ATR
            use_atr_sl_tp = USE_ATR_BASED_SL_TP if 'USE_ATR_BASED_SL_TP' in globals() else True
            # Theo grok.md: SL = 1.5×ATR (thay vì 2.5×ATR hiện tại)
            atr_multiplier_sl = 1.5  # Theo grok.md
            atr_multiplier_tp = ATR_MULTIPLIER_TP if 'ATR_MULTIPLIER_TP' in globals() else 2.5
            
            if use_atr_sl_tp:
                # Tính SL/TP theo ATR động (theo grok.md)
                sl_pips = max(self.min_sl_pips, atr_value * atr_multiplier_sl)
                # TP sẽ được tính theo partial close strategy (TP1: +15 pips, TP2: +30 pips, TP3: trailing)
                # Tạm thời dùng ATR multiplier cho TP, sẽ được điều chỉnh trong partial close
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