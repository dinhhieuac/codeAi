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
    
    def _is_candle_closed(self, df, symbol=None):
        """
        Kiểm tra xem nến cuối cùng đã đóng chưa
        
        Logic:
        - Lấy thời gian của nến cuối cùng trong df
        - Lấy thời gian hiện tại từ MT5 server
        - Tính timeframe (từ TIMEFRAME_MT5)
        - Nếu thời gian hiện tại - thời gian nến cuối >= timeframe, thì nến đã đóng
        
        Args:
            df: DataFrame chứa dữ liệu giá (có column 'time')
            symbol: Symbol để lấy tick time (nếu None, dùng SYMBOL từ config)
            
        Returns:
            True nếu nến đã đóng, False nếu nến chưa đóng
        """
        if len(df) == 0:
            return False
        
        try:
            # Lấy thời gian của nến cuối cùng (timestamp UTC từ MT5)
            last_candle_time_raw = df.iloc[-1]['time']
            
            # Chuyển đổi sang int (Unix timestamp) nếu là pandas Timestamp
            if isinstance(last_candle_time_raw, pd.Timestamp):
                last_candle_time = int(last_candle_time_raw.timestamp())
            elif hasattr(last_candle_time_raw, 'timestamp'):
                # Nếu là datetime object
                last_candle_time = int(last_candle_time_raw.timestamp())
            else:
                # Nếu đã là int hoặc float
                last_candle_time = int(last_candle_time_raw)
            
            # Lấy thời gian hiện tại từ MT5 server (UTC)
            # Sử dụng symbol từ tham số hoặc config
            symbol_to_check = symbol if symbol else (SYMBOL if 'SYMBOL' in globals() else 'XAUUSDc')
            tick = self.mt5.symbol_info_tick(symbol_to_check)
            if tick is None:
                # Fallback: dùng datetime.utcnow()
                from datetime import datetime
                now_time = int(datetime.utcnow().timestamp())
            else:
                now_time = int(tick.time)  # Đảm bảo là int
            
            # Tính timeframe (giây)
            timeframe_minutes = TIMEFRAME_MT5.get(TIMEFRAME, 15)  # Mặc định 15 phút
            timeframe_seconds = timeframe_minutes * 60
            
            # Kiểm tra: nếu thời gian hiện tại - thời gian nến cuối >= timeframe, thì nến đã đóng
            time_diff = now_time - last_candle_time
            
            # Nến đã đóng nếu time_diff >= timeframe (cho phép sai số 5 giây)
            is_closed = time_diff >= (timeframe_seconds - 5)
            
            if not is_closed:
                remaining_seconds = timeframe_seconds - time_diff
                remaining_minutes = int(remaining_seconds // 60)
                remaining_secs = int(remaining_seconds % 60)
                logging.debug(f"⏳ Nến chưa đóng - Còn {remaining_minutes}m {remaining_secs}s")
            
            return is_closed
        except Exception as e:
            logging.warning(f"⚠️ Lỗi khi kiểm tra nến đóng: {e}")
            # Nếu có lỗi, cho phép tiếp tục (fail-safe)
            return True
        
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
            
            None nếu không đủ dữ liệu (< 50 nến) hoặc nến chưa đóng (nếu ENABLE_WAIT_FOR_CANDLE_CLOSE = True)
        """
        # Kiểm tra dữ liệu đủ để tính toán
        if len(df) < 50:
            return None  # Cần ít nhất 50 nến để tính các chỉ báo chính xác
        
        # ====================================================================
        # KIỂM TRA NẾN ĐÃ ĐÓNG CHƯA (nếu rule được bật)
        # ====================================================================
        enable_wait_candle = ENABLE_WAIT_FOR_CANDLE_CLOSE if 'ENABLE_WAIT_FOR_CANDLE_CLOSE' in globals() else False
        if enable_wait_candle:
            if not self._is_candle_closed(df, symbol):
                logging.debug("⏳ Nến hiện tại chưa đóng - Chờ nến đóng để check tín hiệu")
                return None  # Chờ nến đóng
        
        # ====================================================================
        # MULTI-TIMEFRAME BIAS (theo grok.md: D1/H4 cho bias, M15 cho entry)
        # ====================================================================
        bias_info = None
        if use_multi_timeframe and symbol:
            bias_info = self.get_multi_timeframe_bias(symbol)
            if bias_info:
                logging.info(f"✅ Multi-timeframe bias: {bias_info['bias']} (D1: {bias_info['d1_trend']}, H4: {bias_info['h4_trend']})")
            else:
                logging.warning("⚠️ Không lấy được multi-timeframe bias, tiếp tục phân tích M15")
        
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
        
        # --- Tín hiệu BUY: Theo grok.md - Giá breakout trên EMA 9, RSI >30, ATR >12 pips, Volume tăng ---
        # Điều kiện đầy đủ: buy_signals >= MIN_SIGNAL_STRENGTH, buy_signals > sell_signals, ATR > 12 pips, Volume confirmed
        # Multi-timeframe filter: Chỉ BUY khi bias là BULLISH (theo grok.md)
        bias_allows_buy = True
        if bias_info and bias_info['bias'] == 'BEARISH':
            bias_allows_buy = False
            logging.warning(f"⚠️ Multi-timeframe bias là BEARISH → Không cho phép BUY (theo grok.md)")
        elif bias_info and bias_info['bias'] == 'BULLISH':
            logging.info(f"✅ Multi-timeframe bias là BULLISH → Cho phép BUY (theo grok.md)")
        
        if buy_signals >= MIN_SIGNAL_STRENGTH and buy_signals > sell_signals and atr_value > atr_min_pips and volume_confirmed and bias_allows_buy:
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
        
        # --- Tín hiệu SELL: Theo grok.md - Giá breakout dưới EMA 9, RSI <70, ATR >12 pips, Volume tăng ---
        # Điều kiện đầy đủ: sell_signals >= MIN_SIGNAL_STRENGTH, sell_signals > buy_signals, ATR > 12 pips, Volume confirmed
        # Multi-timeframe filter: Chỉ SELL khi bias là BEARISH (theo grok.md)
        bias_allows_sell = True
        if bias_info and bias_info['bias'] == 'BULLISH' and sell_signals>=3:
            logging.warning(f"⚠️ Multi-timeframe bias là BULLISH → Không cho phép SELL (theo grok.md) nhưng tín hiệu cực mạnh sell")
            
        if bias_info and bias_info['bias'] == 'BULLISH' and sell_signals<3:
            bias_allows_sell = False
            logging.warning(f"⚠️ Multi-timeframe bias là BULLISH → Không cho phép SELL (theo grok.md)")
        
        elif bias_info and bias_info['bias'] == 'BEARISH':
            logging.info(f"✅ Multi-timeframe bias là BEARISH → Cho phép SELL (theo grok.md)")
        
        elif sell_signals >= MIN_SIGNAL_STRENGTH and sell_signals > buy_signals and atr_value > atr_min_pips and volume_confirmed and bias_allows_sell:
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