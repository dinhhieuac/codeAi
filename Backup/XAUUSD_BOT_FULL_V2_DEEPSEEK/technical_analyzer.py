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
        
    def detect_engulfing(self, df):
        """
        Phát hiện nến Engulfing (Bullish hoặc Bearish)
        
        Bullish Engulfing:
        - Nến trước là nến giảm (red)
        - Nến hiện tại là nến tăng (green)
        - Nến hiện tại "nuốt" nến trước (high > prev_high, low < prev_low)
        
        Bearish Engulfing:
        - Nến trước là nến tăng (green)
        - Nến hiện tại là nến giảm (red)
        - Nến hiện tại "nuốt" nến trước (high > prev_high, low < prev_low)
        
        Args:
            df: DataFrame với columns: open, high, low, close
            
        Returns:
            'BULLISH': Bullish Engulfing
            'BEARISH': Bearish Engulfing
            None: Không có Engulfing
        """
        if len(df) < 2:
            return None
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Kiểm tra Bullish Engulfing
        prev_is_bearish = prev['close'] < prev['open']  # Nến trước giảm
        current_is_bullish = current['close'] > current['open']  # Nến hiện tại tăng
        current_engulfs = (current['high'] > prev['high'] and current['low'] < prev['low'])
        
        if prev_is_bearish and current_is_bullish and current_engulfs:
            return 'BULLISH'
        
        # Kiểm tra Bearish Engulfing
        prev_is_bullish = prev['close'] > prev['open']  # Nến trước tăng
        current_is_bearish = current['close'] < current['open']  # Nến hiện tại giảm
        current_engulfs = (current['high'] > prev['high'] and current['low'] < prev['low'])
        
        if prev_is_bullish and current_is_bearish and current_engulfs:
            return 'BEARISH'
        
        return None
    
    def get_h1_bias(self, symbol):
        """
        Lấy bias từ H1 timeframe (theo pullback.md: H1 xác định xu hướng)
        
        Theo pullback.md:
        - H1: UPTREND = giá trên 3 EMA (21, 50, 200)
        - H1: DOWNTREND = giá dưới 3 EMA (21, 50, 200)
        - M15: Vào lệnh
        
        Args:
            symbol: Symbol cần phân tích (ví dụ: "XAUUSDc")
            
        Returns:
            Dict với keys:
            - 'bias': 'BULLISH', 'BEARISH', hoặc 'NEUTRAL'
            - 'h1_price': Giá hiện tại trên H1
            - 'h1_ema21': EMA 21 trên H1
            - 'h1_ema50': EMA 50 trên H1
            - 'h1_ema200': EMA 200 trên H1
            None nếu không lấy được dữ liệu
        """
        try:
            # Lấy dữ liệu H1 (1 giờ = 60 phút)
            h1_rates = self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_H1, 0, 200)
            if h1_rates is None or len(h1_rates) < 200:
                logging.warning("⚠️ Không lấy được đủ dữ liệu H1 cho multi-timeframe analysis")
                return None
            
            h1_df = pd.DataFrame(h1_rates)
            h1_close = h1_df['close']
            h1_ema21 = self.calculate_ema(h1_close, 21).iloc[-1]
            h1_ema50 = self.calculate_ema(h1_close, 50).iloc[-1]
            h1_ema200 = self.calculate_ema(h1_close, 200).iloc[-1]
            h1_price = h1_close.iloc[-1]
            
            # Xác định trend H1 (theo pullback.md: giá trên 3 EMA = UPTREND, giá dưới 3 EMA = DOWNTREND)
            if h1_price > h1_ema21 and h1_price > h1_ema50 and h1_price > h1_ema200:
                h1_bias = 'BULLISH'  # UPTREND
            elif h1_price < h1_ema21 and h1_price < h1_ema50 and h1_price < h1_ema200:
                h1_bias = 'BEARISH'  # DOWNTREND
            else:
                h1_bias = 'NEUTRAL'
            
            logging.info("=" * 60)
            logging.info("📊 H1 TIMEFRAME BIAS (theo pullback.md):")
            logging.info("=" * 60)
            logging.info(f"   📈 H1: Price={h1_price:.2f}, EMA21={h1_ema21:.2f}, EMA50={h1_ema50:.2f}, EMA200={h1_ema200:.2f}")
            logging.info(f"   🎯 H1 Bias: {h1_bias} (UPTREND = giá trên 3 EMA, DOWNTREND = giá dưới 3 EMA)")
            logging.info("=" * 60)
            
            return {
                'bias': h1_bias,
                'h1_price': h1_price,
                'h1_ema21': h1_ema21,
                'h1_ema50': h1_ema50,
                'h1_ema200': h1_ema200
            }
        except Exception as e:
            logging.error(f"❌ Lỗi khi lấy H1 bias: {e}", exc_info=True)
            return None
    
    def detect_pullback(self, current_price, ema_fast, ema_mid, ema_slow, tolerance_pips=30):
        """
        Phát hiện pullback về EMA (theo pullback.md)
        
        BUY: Giá pullback về EMA 21/50 trong xu hướng tăng (EMA21 > EMA50 > EMA200)
        SELL: Giá pullback về EMA 21/50 trong xu hướng giảm (EMA21 < EMA50 < EMA200)
        
        Args:
            current_price: Giá hiện tại
            ema_fast: EMA ngắn hạn (21)
            ema_mid: EMA trung bình (50)
            ema_slow: EMA dài hạn (200)
            tolerance_pips: Khoảng cách tối đa để coi là pullback (pips)
            
        Returns:
            'BUY': Pullback BUY (giá pullback về EMA trong uptrend)
            'SELL': Pullback SELL (giá pullback về EMA trong downtrend)
            None: Không có pullback
        """
        tolerance = tolerance_pips * 0.01  # Chuyển pips sang giá
        
        # Kiểm tra xu hướng tăng: EMA21 > EMA50 > EMA200
        uptrend = (ema_fast > ema_mid > ema_slow)
        
        # Kiểm tra xu hướng giảm: EMA21 < EMA50 < EMA200
        downtrend = (ema_fast < ema_mid < ema_slow)
        
        # BUY: Uptrend và giá pullback về EMA50 hoặc EMA21 (theo pullback.md)
        if uptrend:
            # Giá pullback về EMA50
            if abs(current_price - ema_mid) <= tolerance:
                return 'BUY'
            # Giá pullback về EMA21
            if abs(current_price - ema_fast) <= tolerance:
                return 'BUY'
        
        # SELL: Downtrend và giá pullback về EMA50 hoặc EMA21 (theo pullback.md)
        if downtrend:
            # Giá pullback về EMA50
            if abs(current_price - ema_mid) <= tolerance:
                return 'SELL'
            # Giá pullback về EMA21
            if abs(current_price - ema_fast) <= tolerance:
                return 'SELL'
        
        return None
    
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
        
        # EMA (Exponential Moving Average) - Cho chiến thuật Pullback
        use_pullback = USE_PULLBACK_STRATEGY if 'USE_PULLBACK_STRATEGY' in globals() else False
        if use_pullback:
            # Chiến thuật Pullback: EMA 20, 34, 89
            ema_fast = EMA_FAST if 'EMA_FAST' in globals() else 20
            ema_mid = EMA_MID if 'EMA_MID' in globals() else 34
            ema_slow = EMA_SLOW if 'EMA_SLOW' in globals() else 89
            df['ema_fast'] = self.calculate_ema(close, ema_fast)  # EMA ngắn hạn (20)
            df['ema_mid'] = self.calculate_ema(close, ema_mid)    # EMA trung bình (34)
            df['ema_slow'] = self.calculate_ema(close, ema_slow)   # EMA dài hạn (89)
            # Giữ lại ema_20 và ema_50 cho tương thích
            df['ema_20'] = df['ema_fast']
            df['ema_50'] = df['ema_mid']
        else:
            # Logic cũ: EMA20 và EMA50
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
        # BƯỚC 2.5: KIỂM TRA CHIẾN THUẬT PULLBACK (nếu bật)
        # ====================================================================
        use_pullback = USE_PULLBACK_STRATEGY if 'USE_PULLBACK_STRATEGY' in globals() else False
        if use_pullback:
            # Lấy H1 bias để xác định xu hướng (theo pullback.md)
            symbol = SYMBOL if 'SYMBOL' in globals() else "XAUUSDc"
            h1_bias_data = self.get_h1_bias(symbol)
            h1_bias = h1_bias_data['bias'] if h1_bias_data else 'NEUTRAL'
            
            # Kiểm tra pullback về EMA
            tolerance_pips = PULLBACK_TOLERANCE_PIPS if 'PULLBACK_TOLERANCE_PIPS' in globals() else 30
            pullback_signal = self.detect_pullback(
                current['close'],
                current['ema_fast'] if 'ema_fast' in current else current['ema_20'],
                current['ema_mid'] if 'ema_mid' in current else current['ema_50'],
                current['ema_slow'] if 'ema_slow' in current else current.get('ema_50', current['ema_20']),
                tolerance_pips
            )
            
            # Kiểm tra nến đóng trên/dưới EMA (theo pullback.md)
            ema_fast_val = current['ema_fast'] if 'ema_fast' in current else current['ema_20']
            ema_mid_val = current['ema_mid'] if 'ema_mid' in current else current['ema_50']
            candle_close_above_ema = current['close'] > ema_fast_val or current['close'] > ema_mid_val
            candle_close_below_ema = current['close'] < ema_fast_val or current['close'] < ema_mid_val
            
            # Kiểm tra nến Engulfing
            require_engulfing = REQUIRE_ENGULFING if 'REQUIRE_ENGULFING' in globals() else True
            engulfing = self.detect_engulfing(df)
            
            # Kiểm tra MACD confirmation (theo best practices)
            require_macd = REQUIRE_MACD_CONFIRMATION if 'REQUIRE_MACD_CONFIRMATION' in globals() else True
            macd_current = current['macd']
            macd_signal_current = current['macd_signal']
            macd_hist_current = current['macd_hist']
            macd_hist_prev = prev['macd_hist'] if len(df) > 1 else 0
            
            # MACD confirmation: Histogram chuyển từ âm sang dương (BUY) hoặc từ dương sang âm (SELL)
            macd_buy_ok = (not require_macd) or (macd_hist_current > 0 and macd_hist_prev <= 0) or (macd_current > macd_signal_current)
            macd_sell_ok = (not require_macd) or (macd_hist_current < 0 and macd_hist_prev >= 0) or (macd_current < macd_signal_current)
            
            # Kiểm tra Volume confirmation (theo best practices)
            require_volume = REQUIRE_VOLUME_CONFIRMATION if 'REQUIRE_VOLUME_CONFIRMATION' in globals() else False
            volume_ok = True  # Mặc định True nếu không yêu cầu volume
            if require_volume and 'tick_volume' in df.columns:
                volume_current = current['tick_volume']
                volume_prev = prev['tick_volume'] if len(df) > 1 else volume_current
                # Volume tăng khi bounce từ pullback
                volume_ok = volume_current >= volume_prev * 0.9  # Cho phép giảm nhẹ 10%
            
            # Kiểm tra RSI (theo pullback.md: BUY < 30, SELL > 70)
            rsi_buy_max = PULLBACK_RSI_BUY_MAX if 'PULLBACK_RSI_BUY_MAX' in globals() else 30
            rsi_sell_min = PULLBACK_RSI_SELL_MIN if 'PULLBACK_RSI_SELL_MIN' in globals() else 70
            
            rsi_current = current['rsi']
            
            # Tính SL/TP theo pullback (nếu bật)
            use_pullback_sl = USE_PULLBACK_SL if 'USE_PULLBACK_SL' in globals() else True
            use_ema_tp = USE_EMA_TP if 'USE_EMA_TP' in globals() else False
            
            # Kiểm tra điều kiện BUY (theo pullback.md)
            if pullback_signal == 'BUY':
                # Điều kiện BUY:
                # 1. H1: UPTREND (giá trên 3 EMA)
                # 2. M15: Giá hồi về EMA 21/50
                # 3. RSI: Dưới 30 (quá bán)
                # 4. Xác nhận: Nến đóng trên EMA
                h1_ok = (h1_bias == 'BULLISH')
                rsi_ok = rsi_current < rsi_buy_max  # RSI < 30
                candle_ok = candle_close_above_ema  # Nến đóng trên EMA
                engulfing_ok = (not require_engulfing) or (engulfing == 'BULLISH')
                
                if h1_ok and rsi_ok and candle_ok and engulfing_ok and macd_buy_ok and volume_ok:
                    # Tính SL/TP
                    atr_value = current['atr'] / 0.01
                    current_price = current['close']
                    ema_slow_val = current['ema_slow'] if 'ema_slow' in current else current.get('ema_50', current['ema_20'])
                    
                    # SL: Dưới đáy pullback (theo pullback.md) hoặc theo ATR
                    if use_pullback_sl:
                        # Tìm đáy pullback (low nhất trong 5 nến gần nhất)
                        recent_lows = df['low'].tail(5)
                        pullback_low = recent_lows.min()
                        sl_price = pullback_low - (10 * 0.01)  # Dưới đáy 10 pips
                        sl_pips = abs(current_price - sl_price) / 0.01
                        sl_pips = max(self.min_sl_pips, sl_pips)  # Đảm bảo >= min_sl_pips
                    else:
                        # SL theo ATR
                        use_atr_sl_tp = USE_ATR_BASED_SL_TP if 'USE_ATR_BASED_SL_TP' in globals() else True
                        atr_multiplier_sl = ATR_MULTIPLIER_SL if 'ATR_MULTIPLIER_SL' in globals() else 1.5
                        if use_atr_sl_tp:
                            sl_pips = max(self.min_sl_pips, atr_value * atr_multiplier_sl)
                        else:
                            sl_pips = max(self.min_sl_pips, atr_value * 1.5)
                    
                    # TP: Tại EMA kế tiếp (EMA200) hoặc theo ATR/R:R
                    if use_ema_tp:
                        # TP tại EMA200 (EMA kế tiếp sau EMA50)
                        tp_price = ema_slow_val
                        tp_pips = abs(tp_price - current_price) / 0.01
                        tp_pips = max(self.min_tp_pips, tp_pips)  # Đảm bảo >= min_tp_pips
                    else:
                        # TP theo ATR hoặc R:R ratio
                        use_atr_sl_tp = USE_ATR_BASED_SL_TP if 'USE_ATR_BASED_SL_TP' in globals() else True
                        atr_multiplier_tp = ATR_MULTIPLIER_TP if 'ATR_MULTIPLIER_TP' in globals() else 2.5
                        if use_atr_sl_tp:
                            tp_pips = max(self.min_tp_pips, int(atr_value * atr_multiplier_tp))
                        else:
                            tp_pips = max(self.min_tp_pips, int(sl_pips * MIN_RR_RATIO))
                    
                    logging.info("=" * 60)
                    logging.info("✅ TÍN HIỆU PULLBACK BUY (theo pullback.md):")
                    logging.info("=" * 60)
                    logging.info(f"   • H1: UPTREND (giá trên 3 EMA) ✅")
                    logging.info(f"   • M15: Pullback về EMA 21/50 ✅")
                    logging.info(f"   • RSI: {rsi_current:.2f} < {rsi_buy_max} (quá bán) ✅")
                    logging.info(f"   • Nến đóng trên EMA ✅")
                    if require_engulfing:
                        logging.info(f"   • Engulfing: {engulfing} ✅")
                    if require_macd:
                        logging.info(f"   • MACD: Histogram={macd_hist_current:.2f} (xác nhận momentum) ✅")
                    if require_volume:
                        logging.info(f"   • Volume: Tăng khi bounce ✅")
                    logging.info(f"   • SL: {sl_pips:.1f} pips ({'dưới đáy pullback' if use_pullback_sl else 'theo ATR'})")
                    logging.info(f"   • TP: {tp_pips:.1f} pips ({'tại EMA200' if use_ema_tp else 'theo ATR/R:R'})")
                    logging.info("=" * 60)
                    
                    return {
                        'action': 'BUY',
                        'strength': 3,  # Pullback strategy = 3 điểm
                        'sl_pips': sl_pips,
                        'tp_pips': tp_pips
                    }
                else:
                    logging.info("⚠️ Pullback BUY nhưng thiếu điều kiện:")
                    if not h1_ok:
                        logging.info(f"   • H1: {h1_bias} (cần BULLISH/UPTREND)")
                    if not rsi_ok:
                        logging.info(f"   • RSI: {rsi_current:.2f} (cần < {rsi_buy_max})")
                    if not candle_ok:
                        logging.info(f"   • Nến đóng: {current['close']:.2f} (cần trên EMA)")
                    if require_engulfing and engulfing != 'BULLISH':
                        logging.info(f"   • Engulfing: {engulfing} (cần BULLISH)")
                    if require_macd and not macd_buy_ok:
                        logging.info(f"   • MACD: Histogram={macd_hist_current:.2f} (cần chuyển từ âm sang dương)")
                    if require_volume and not volume_ok:
                        logging.info(f"   • Volume: Không tăng khi bounce")
            
            # Kiểm tra điều kiện SELL (theo pullback.md)
            elif pullback_signal == 'SELL':
                # Điều kiện SELL:
                # 1. H1: DOWNTREND (giá dưới 3 EMA)
                # 2. M15: Giá hồi về EMA 21/50
                # 3. RSI: Trên 70 (quá mua)
                # 4. Xác nhận: Nến đóng dưới EMA
                h1_ok = (h1_bias == 'BEARISH')
                rsi_ok = rsi_current > rsi_sell_min  # RSI > 70
                candle_ok = candle_close_below_ema  # Nến đóng dưới EMA
                engulfing_ok = (not require_engulfing) or (engulfing == 'BEARISH')
                
                if h1_ok and rsi_ok and candle_ok and engulfing_ok and macd_sell_ok and volume_ok:
                    # Tính SL/TP
                    atr_value = current['atr'] / 0.01
                    current_price = current['close']
                    ema_slow_val = current['ema_slow'] if 'ema_slow' in current else current.get('ema_50', current['ema_20'])
                    
                    # SL: Trên đỉnh pullback (theo pullback.md) hoặc theo ATR
                    if use_pullback_sl:
                        # Tìm đỉnh pullback (high nhất trong 5 nến gần nhất)
                        recent_highs = df['high'].tail(5)
                        pullback_high = recent_highs.max()
                        sl_price = pullback_high + (10 * 0.01)  # Trên đỉnh 10 pips
                        sl_pips = abs(sl_price - current_price) / 0.01
                        sl_pips = max(self.min_sl_pips, sl_pips)  # Đảm bảo >= min_sl_pips
                    else:
                        # SL theo ATR
                        use_atr_sl_tp = USE_ATR_BASED_SL_TP if 'USE_ATR_BASED_SL_TP' in globals() else True
                        atr_multiplier_sl = ATR_MULTIPLIER_SL if 'ATR_MULTIPLIER_SL' in globals() else 1.5
                        if use_atr_sl_tp:
                            sl_pips = max(self.min_sl_pips, atr_value * atr_multiplier_sl)
                        else:
                            sl_pips = max(self.min_sl_pips, atr_value * 1.5)
                    
                    # TP: Tại EMA kế tiếp (EMA200) hoặc theo ATR/R:R
                    if use_ema_tp:
                        # TP tại EMA200 (EMA kế tiếp sau EMA50)
                        tp_price = ema_slow_val
                        tp_pips = abs(current_price - tp_price) / 0.01
                        tp_pips = max(self.min_tp_pips, tp_pips)  # Đảm bảo >= min_tp_pips
                    else:
                        # TP theo ATR hoặc R:R ratio
                        use_atr_sl_tp = USE_ATR_BASED_SL_TP if 'USE_ATR_BASED_SL_TP' in globals() else True
                        atr_multiplier_tp = ATR_MULTIPLIER_TP if 'ATR_MULTIPLIER_TP' in globals() else 2.5
                        if use_atr_sl_tp:
                            tp_pips = max(self.min_tp_pips, int(atr_value * atr_multiplier_tp))
                        else:
                            tp_pips = max(self.min_tp_pips, int(sl_pips * MIN_RR_RATIO))
                    
                    logging.info("=" * 60)
                    logging.info("✅ TÍN HIỆU PULLBACK SELL (theo pullback.md):")
                    logging.info("=" * 60)
                    logging.info(f"   • H1: DOWNTREND (giá dưới 3 EMA) ✅")
                    logging.info(f"   • M15: Pullback về EMA 21/50 ✅")
                    logging.info(f"   • RSI: {rsi_current:.2f} > {rsi_sell_min} (quá mua) ✅")
                    logging.info(f"   • Nến đóng dưới EMA ✅")
                    if require_engulfing:
                        logging.info(f"   • Engulfing: {engulfing} ✅")
                    if require_macd:
                        logging.info(f"   • MACD: Histogram={macd_hist_current:.2f} (xác nhận momentum) ✅")
                    if require_volume:
                        logging.info(f"   • Volume: Tăng khi bounce ✅")
                    logging.info(f"   • SL: {sl_pips:.1f} pips ({'trên đỉnh pullback' if use_pullback_sl else 'theo ATR'})")
                    logging.info(f"   • TP: {tp_pips:.1f} pips ({'tại EMA200' if use_ema_tp else 'theo ATR/R:R'})")
                    logging.info("=" * 60)
                    
                    return {
                        'action': 'SELL',
                        'strength': 3,  # Pullback strategy = 3 điểm
                        'sl_pips': sl_pips,
                        'tp_pips': tp_pips
                    }
                else:
                    logging.info("⚠️ Pullback SELL nhưng thiếu điều kiện:")
                    if not h1_ok:
                        logging.info(f"   • H1: {h1_bias} (cần BEARISH/DOWNTREND)")
                    if not rsi_ok:
                        logging.info(f"   • RSI: {rsi_current:.2f} (cần > {rsi_sell_min})")
                    if not candle_ok:
                        logging.info(f"   • Nến đóng: {current['close']:.2f} (cần dưới EMA)")
                    if require_engulfing and engulfing != 'BEARISH':
                        logging.info(f"   • Engulfing: {engulfing} (cần BEARISH)")
                    if require_macd and not macd_sell_ok:
                        logging.info(f"   • MACD: Histogram={macd_hist_current:.2f} (cần chuyển từ dương sang âm)")
                    if require_volume and not volume_ok:
                        logging.info(f"   • Volume: Không tăng khi bounce")
            
            # Không có pullback signal → tiếp tục với logic cũ
            else:
                logging.debug("   ⚠️ Không có pullback signal, tiếp tục với logic cũ")
        
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
        atr_value = current['atr'] / 0.01  # ATR tính bằng pips
        logging.info(f"   📏 ATR: {current['atr']:.2f} ({atr_value:.1f} pips)")
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
        
        # Chuyển đổi ATR từ giá trị giá sang pips (1 pip XAUUSD = 0.01)
        atr_value = current['atr'] / 0.01  # ATR tính bằng pips
        
        # Kiểm tra ATR filter: Tránh vào lệnh khi volatility quá cao
        max_atr = MAX_ATR if 'MAX_ATR' in globals() else 500
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