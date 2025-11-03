"""
Gold Auto Trader - Hệ thống giao dịch tự động cho vàng (BTCUSD)
Tự động phân tích và thực thi lệnh Buy/Sell dựa trên phân tích kỹ thuật
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import time
import logging
import csv
import sys
from pathlib import Path
from typing import Optional, Dict, Tuple
import requests

# Import config
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir))
try:
    import configbtc
    from configbtc import *
except ImportError:
    print("⚠️  File config.py không tìm thấy! Sử dụng giá trị mặc định.")
    # Fallback values
    MT5_LOGIN = 272736909
    MT5_PASSWORD = "@Dinhhieu273"
    MT5_SERVER = "Exness-MT5Trial14"
    SYMBOL = "BTCUSD"
    TIMEFRAME = "M15"
    RISK_PER_TRADE = 0.015
    MIN_LOT_SIZE = 0.01
    MAX_LOT_SIZE = 0.1
    MAX_POSITIONS = 5
    MAX_DAILY_TRADES = 100
    MIN_EQUITY_RATIO = 0.9
    USE_ATR_SL_TP = True
    ATR_SL_MULTIPLIER = 2.0
    ATR_TP_MULTIPLIER = 3.0
    MIN_SL_POINTS = 50
    MAX_SL_POINTS = 500
    MIN_TP_POINTS = 100
    MAX_TP_POINTS = 1000
    RSI_PERIOD = 14
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    MA_TYPE = 'EMA'
    MA_PERIODS = [20, 50, 200]
    BB_PERIOD = 20
    BB_STD_DEV = 2.0
    ATR_PERIOD = 14
    STOCH_K_PERIOD = 14
    STOCH_D_PERIOD = 3
    STOCH_OVERSOLD = 20
    STOCH_OVERBOUGHT = 80
    MIN_SIGNAL_STRENGTH = 2
    INTERVAL_SECONDS = 60
    HISTORICAL_BARS = 200
    MAGIC_NUMBER = 888888
    BUY_COMMENT = "Gold Auto Buy"
    SELL_COMMENT = "Gold Auto Sell"
    LOG_LEVEL = "INFO"
    LOG_FILE = "logs/gold_trader.log"
    CSV_LOG_FILE = "logs/trades_log.csv"
    DEVIATION = 10

# Setup logging
logs_dir = script_dir / 'logs'
logs_dir.mkdir(exist_ok=True)
log_file = logs_dir / Path(LOG_FILE).name

# Convert log level string to logging constant
log_level_map = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR
}
log_level = log_level_map.get(LOG_LEVEL.upper(), logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """Phân tích kỹ thuật với các chỉ báo"""
    
    def __init__(self, trader_instance):
        """Nhận trader instance để truy cập config"""
        self.trader = trader_instance
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = None) -> pd.Series:
        """Tính RSI (Relative Strength Index)"""
        if period is None:
            period = self.trader.rsi_period
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd(self, df: pd.DataFrame, fast: int = None, slow: int = None, signal: int = None) -> Dict[str, pd.Series]:
        """Tính MACD"""
        if fast is None:
            fast = self.trader.macd_fast
        if slow is None:
            slow = self.trader.macd_slow
        if signal is None:
            signal = self.trader.macd_signal
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_hist = macd - macd_signal
        return {'macd': macd, 'signal': macd_signal, 'hist': macd_hist}
    
    def calculate_ma(self, df: pd.DataFrame, periods: list = None, ma_type: str = None) -> Dict[str, pd.Series]:
        """Tính Moving Averages - hỗ trợ cả SMA và EMA"""
        if periods is None:
            periods = self.trader.ma_periods
        if ma_type is None:
            ma_type = self.trader.ma_type
        
        mas = {}
        for period in periods:
            if ma_type.upper() == 'EMA':
                # EMA (Exponential Moving Average) - nhạy hơn với biến động giá
                mas[f'MA_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
            else:
                # SMA (Simple Moving Average) - mặc định
                mas[f'MA_{period}'] = df['close'].rolling(window=period).mean()
        return mas
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = None, std_dev: float = None) -> Dict[str, pd.Series]:
        """Tính Bollinger Bands"""
        if period is None:
            period = self.trader.bb_period
        if std_dev is None:
            std_dev = self.trader.bb_std_dev
        sma = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return {'upper': upper, 'middle': sma, 'lower': lower}
    
    def calculate_atr(self, df: pd.DataFrame, period: int = None) -> pd.Series:
        """Tính ATR (Average True Range)"""
        if period is None:
            period = self.trader.atr_period
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr
    
    def calculate_stochastic(self, df: pd.DataFrame, k_period: int = None, d_period: int = None) -> Dict[str, pd.Series]:
        """Tính Stochastic Oscillator"""
        if k_period is None:
            k_period = self.trader.stoch_k_period
        if d_period is None:
            d_period = self.trader.stoch_d_period
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        k = 100 * ((df['close'] - low_min) / (high_max - low_min))
        d = k.rolling(window=d_period).mean()
        return {'k': k, 'd': d}

    def calculate_fibonacci_levels(self, df: pd.DataFrame, lookback: int = None) -> Dict[str, any]:
        """
        Tính Fibonacci Retracement levels từ swing high/low
        
        Args:
            df: DataFrame với OHLC data
            lookback: Số nến để tìm swing high/low (mặc định từ config)
        
        Returns:
            Dict với các Fibonacci levels và thông tin swing
        """
        if lookback is None:
            lookback = getattr(self.trader, 'fibonacci_lookback', 100)
        
        # Chỉ lấy số nến cần thiết
        df_analysis = df.tail(min(lookback, len(df))).copy()
        
        if len(df_analysis) < 10:
            return {'levels': {}, 'swing_high': None, 'swing_low': None, 'trend': 'UNKNOWN'}
        
        # Tìm swing high và swing low
        swing_high = df_analysis['high'].max()
        swing_low = df_analysis['low'].min()
        swing_high_idx = df_analysis['high'].idxmax()
        swing_low_idx = df_analysis['low'].idxmin()
        
        # Xác định xu hướng: uptrend nếu swing high mới hơn swing low
        if swing_high_idx > swing_low_idx:
            trend = 'UPTREND'  # Đang trong xu hướng tăng
            diff = swing_high - swing_low
            # Tính Fibonacci từ swing low lên swing high (retracement từ đỉnh)
            base = swing_low
        else:
            trend = 'DOWNTREND'  # Đang trong xu hướng giảm
            diff = swing_high - swing_low
            # Tính Fibonacci từ swing high xuống swing low (retracement từ đáy)
            base = swing_high
        
        # Tính các mức Fibonacci
        fib_levels = getattr(self.trader, 'fibonacci_levels', [0.236, 0.382, 0.5, 0.618, 0.786])
        levels = {}
        
        for fib_ratio in fib_levels:
            if trend == 'UPTREND':
                # Fibonacci từ swing low: level = base + diff * fib_ratio
                levels[f'FIB_{int(fib_ratio * 1000)}'] = base + diff * fib_ratio
            else:
                # Fibonacci từ swing high: level = base - diff * fib_ratio
                levels[f'FIB_{int(fib_ratio * 1000)}'] = base - diff * fib_ratio
        
        return {
            'levels': levels,
            'swing_high': swing_high,
            'swing_low': swing_low,
            'trend': trend,
            'diff': diff
        }
    
    def check_fibonacci_level(self, current_price: float, fib_data: Dict) -> Optional[str]:
        """
        Kiểm tra giá hiện tại có chạm mức Fibonacci nào không
        
        Args:
            current_price: Giá hiện tại
            fib_data: Kết quả từ calculate_fibonacci_levels()
        
        Returns:
            Tên mức Fibonacci nếu chạm (ví dụ: 'FIB_618'), None nếu không chạm
        """
        if not fib_data or not fib_data.get('levels'):
            return None
        
        tolerance = getattr(self.trader, 'fibonacci_tolerance', 0.02)
        
        for level_name, level_price in fib_data['levels'].items():
            # Tính % chênh lệch
            diff_pct = abs(current_price - level_price) / level_price
            if diff_pct <= tolerance:
                return level_name
        
        return None
    
    def analyze_volume(self, df: pd.DataFrame) -> Dict[str, any]:
        """
        Phân tích khối lượng giao dịch
        
        Args:
            df: DataFrame với tick_volume hoặc real_volume
        
        Returns:
            Dict với thông tin volume analysis
        """
        # Kiểm tra cột volume (có thể là 'tick_volume' hoặc 'volume')
        volume_col = 'tick_volume' if 'tick_volume' in df.columns else 'volume'
        
        if volume_col not in df.columns:
            return {'volume_status': 'UNKNOWN', 'volume_ratio': 1.0, 'is_high_volume': False}
        
        current_volume = df[volume_col].iloc[-1]
        
        # Tính MA của volume
        volume_ma_period = getattr(self.trader, 'volume_ma_period', 20)
        volume_ma = df[volume_col].rolling(window=volume_ma_period).mean().iloc[-1]
        
        if pd.isna(volume_ma) or volume_ma == 0:
            return {'volume_status': 'UNKNOWN', 'volume_ratio': 1.0, 'is_high_volume': False}
        
        # Tính tỷ lệ volume
        volume_ratio = current_volume / volume_ma
        
        # Xác định trạng thái volume
        volume_high_threshold = getattr(self.trader, 'volume_high_threshold', 1.5)
        volume_low_threshold = getattr(self.trader, 'volume_low_threshold', 0.5)
        
        if volume_ratio >= volume_high_threshold:
            volume_status = 'HIGH'
            is_high_volume = True
        elif volume_ratio <= volume_low_threshold:
            volume_status = 'LOW'
            is_high_volume = False
        else:
            volume_status = 'NORMAL'
            is_high_volume = False
        
        return {
            'volume_status': volume_status,
            'volume_ratio': volume_ratio,
            'current_volume': current_volume,
            'volume_ma': volume_ma,
            'is_high_volume': is_high_volume
        }
    
    def find_support_resistance_zones(self, df: pd.DataFrame, lookback: int = None, num_zones: int = None) -> Dict[str, list]:
        """
        Tìm vùng hỗ trợ (Support) và kháng cự (Resistance) bằng cách xác định các mức giá
        có nhiều lần chạm nhất (cluster analysis)
        
        Args:
            df: DataFrame với OHLC data
            lookback: Số nến để phân tích (mặc định từ config)
            num_zones: Số lượng vùng S/R tối đa (mặc định từ config)
        
        Returns:
            Dict với danh sách support và resistance zones
        """
        if lookback is None:
            lookback = getattr(self.trader, 'sr_lookback', 200)
        if num_zones is None:
            num_zones = getattr(self.trader, 'sr_zones_count', 5)
        
        # Chỉ lấy số nến cần thiết
        df_analysis = df.tail(min(lookback, len(df))).copy()
        
        if len(df_analysis) < 20:
            return {'support': [], 'resistance': []}
        
        tolerance = getattr(self.trader, 'sr_tolerance', 0.01)
        min_touches = getattr(self.trader, 'sr_touch_min', 2)
        
        # Thu thập tất cả các mức giá high và low
        highs = df_analysis['high'].values
        lows = df_analysis['low'].values
        
        # Tìm các cluster (nhóm) giá gần nhau
        def find_clusters(prices, is_resistance=True):
            """Tìm các cluster giá"""
            clusters = {}
            
            for price in prices:
                # Tìm cluster gần nhất
                found = False
                for cluster_price in clusters.keys():
                    # Kiểm tra giá có trong cluster không (dung sai tolerance)
                    diff_pct = abs(price - cluster_price) / price
                    if diff_pct <= tolerance:
                        clusters[cluster_price].append(price)
                        found = True
                        break
                
                if not found:
                    # Tạo cluster mới
                    clusters[price] = [price]
            
            # Tính trung bình cho mỗi cluster và số lần chạm
            zone_data = []
            for cluster_price, price_list in clusters.items():
                if len(price_list) >= min_touches:  # Phải có ít nhất min_touches lần chạm
                    avg_price = np.mean(price_list)
                    touches = len(price_list)
                    zone_data.append({
                        'price': avg_price,
                        'touches': touches,
                        'strength': touches  # Strength = số lần chạm
                    })
            
            # Sắp xếp theo strength (số lần chạm) giảm dần
            zone_data.sort(key=lambda x: x['strength'], reverse=True)
            
            # Chỉ lấy num_zones zones mạnh nhất
            return zone_data[:num_zones]
        
        # Tìm Resistance từ highs
        resistance_zones = find_clusters(highs, is_resistance=True)
        
        # Tìm Support từ lows
        support_zones = find_clusters(lows, is_resistance=False)
        
        return {
            'support': support_zones,
            'resistance': resistance_zones
        }
    
    def check_support_resistance(self, current_price: float, sr_data: Dict) -> Dict[str, any]:
        """
        Kiểm tra giá hiện tại có gần vùng Support/Resistance nào không
        
        Args:
            current_price: Giá hiện tại
            sr_data: Kết quả từ find_support_resistance_zones()
        
        Returns:
            Dict với thông tin zone gần nhất (nếu có)
        """
        if not sr_data:
            return {'near_zone': None, 'zone_type': None, 'distance_pct': None}
        
        tolerance = getattr(self.trader, 'sr_tolerance', 0.01)
        nearest_zone = None
        nearest_distance = float('inf')
        zone_type = None
        
        # Kiểm tra Resistance zones (giá chạm từ dưới lên = có thể là resistance)
        for zone in sr_data.get('resistance', []):
            zone_price = zone['price']
            distance_pct = abs(current_price - zone_price) / zone_price
            
            if distance_pct <= tolerance and distance_pct < nearest_distance:
                nearest_zone = zone
                nearest_distance = distance_pct
                zone_type = 'RESISTANCE'
        
        # Kiểm tra Support zones (giá chạm từ trên xuống = có thể là support)
        for zone in sr_data.get('support', []):
            zone_price = zone['price']
            distance_pct = abs(current_price - zone_price) / zone_price
            
            if distance_pct <= tolerance and distance_pct < nearest_distance:
                nearest_zone = zone
                nearest_distance = distance_pct
                zone_type = 'SUPPORT'
        
        if nearest_zone:
            return {
                'near_zone': nearest_zone,
                'zone_type': zone_type,
                'distance_pct': nearest_distance,
                'price': nearest_zone['price'],
                'strength': nearest_zone['strength']
            }
        
        return {'near_zone': None, 'zone_type': None, 'distance_pct': None}
    
    def calculate_adx(self, df: pd.DataFrame, period: int = None) -> Dict[str, pd.Series]:
        """
        Tính ADX (Average Directional Index) - Đo lường strength của trend
        ADX cao = Trend mạnh, ADX thấp = Sideways (không có trend rõ ràng)
        
        Args:
            df: DataFrame với OHLC data
            period: Chu kỳ tính ADX (mặc định từ config)
        
        Returns:
            Dict với ADX, +DI, -DI
        """
        if period is None:
            period = getattr(self.trader, 'adx_period', 14)
        
        # Tính True Range
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        tr = np.max(ranges, axis=1)
        
        # Tính Directional Movement
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        # Smoothing
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        
        # Tính ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return {
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di
        }


class GoldAutoTrader:
    """
    Hệ thống giao dịch tự động cho BTC/XAU
    
    Tự động phân tích thị trường bằng các chỉ báo kỹ thuật (RSI, MACD, MA, BB, Stochastic)
    và thực thi lệnh Buy/Sell dựa trên tín hiệu từ nhiều chỉ báo đồng thuận.
    
    Tính năng:
    - Risk Management: Tự động tính lot size từ % rủi ro
    - ATR-based SL/TP: Tính SL/TP động dựa trên volatility
    - Multiple Indicators: RSI, MACD, MA, Bollinger Bands, Stochastic
    - Position Management: Giới hạn số lệnh cùng lúc và số lệnh/ngày
    - Equity Protection: Circuit breaker khi Equity giảm quá nhiều
    - CSV Logging: Ghi lại mọi lệnh để phân tích
    """
    
    def __init__(self, login: int, password: str, server: str, symbol: str = "BTCUSD"):
        """
        Khởi tạo Gold Auto Trader
        
        Args:
            login (int): Số tài khoản MT5
            password (str): Mật khẩu đăng nhập MT5
            server (str): Tên server MT5 (ví dụ: "Exness-MT5Trial14")
            symbol (str): Symbol để giao dịch (mặc định "BTCUSD")
        """
        # Thông tin đăng nhập MT5
        self.login = login              # Số tài khoản MT5
        self.password = password        # Mật khẩu MT5
        self.server = server            # Tên server MT5
        self.symbol = symbol            # Symbol giao dịch (BTCUSD, XAUUSD, ...)
        self.magic_number = MAGIC_NUMBER  # Magic number để nhận diện lệnh của bot
        self.connected = False         # Trạng thái kết nối MT5 (True/False)
        
        # Timeframe - Khung thời gian phân tích
        self.timeframe_str = TIMEFRAME  # Timeframe dạng string (ví dụ: "M15")
        try:
            # Thử import hàm từ configbtc.py để convert timeframe
            import configbtc as config
            self.timeframe = config.get_timeframe_mt5()  # Convert "M15" → mt5.TIMEFRAME_M15
        except:
            # Fallback: Nếu không có hàm, tự mapping
            timeframe_map = {
                "M1": mt5.TIMEFRAME_M1,
                "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "M30": mt5.TIMEFRAME_M30,
                "H1": mt5.TIMEFRAME_H1,
                "H4": mt5.TIMEFRAME_H4,
                "D1": mt5.TIMEFRAME_D1,
            }
            self.timeframe = timeframe_map.get(TIMEFRAME.upper(), mt5.TIMEFRAME_M1)
        
        # Cấu hình giao dịch - Risk Management (load từ configbtc.py)
        self.risk_per_trade = RISK_PER_TRADE      # Tỷ lệ rủi ro mỗi lệnh (0.01 = 1%)
        self.min_lot = MIN_LOT_SIZE                # Lot size tối thiểu (0.01)
        self.max_lot = MAX_LOT_SIZE                # Lot size tối đa (0.01)
        self.max_positions = MAX_POSITIONS         # Số vị thế tối đa cùng lúc (3)
        self.max_daily_trades = MAX_DAILY_TRADES  # Giới hạn lệnh/ngày (300)
        self.min_equity_ratio = MIN_EQUITY_RATIO  # Tỷ lệ Equity tối thiểu (0.9 = 90%)
        
        # Biến theo dõi Risk Management (sẽ được set khi connect)
        self.initial_balance = None                # Balance ban đầu khi bot khởi động
        self.safe_equity_threshold = None          # Ngưỡng Equity an toàn (90% Balance ban đầu)
        
        # SL/TP Settings - Cài đặt Stop Loss và Take Profit
        self.use_atr_sl_tp = USE_ATR_SL_TP              # True: Dùng ATR để tính SL/TP động
        self.atr_sl_multiplier = ATR_SL_MULTIPLIER     # Hệ số nhân ATR cho SL (6.0)
        self.atr_tp_multiplier = ATR_TP_MULTIPLIER     # Hệ số nhân ATR cho TP (10.0)
        
        # Giá trị SL/TP cố định (chỉ dùng khi USE_ATR_SL_TP = False)
        try:
            self.fixed_sl_points = FIXED_SL_POINTS if not USE_ATR_SL_TP else None
            self.fixed_tp_points = FIXED_TP_POINTS if not USE_ATR_SL_TP else None
        except:
            self.fixed_sl_points = None
            self.fixed_tp_points = None
        
        # Giới hạn min/max cho SL/TP (points)
        self.min_sl_points = MIN_SL_POINTS             # SL tối thiểu (2000 points)
        self.max_sl_points = MAX_SL_POINTS             # SL tối đa (8000 points)
        self.min_tp_points = MIN_TP_POINTS             # TP tối thiểu (3000 points)
        self.max_tp_points = MAX_TP_POINTS             # TP tối đa (15000 points)
        
        # SL tối thiểu dựa trên % giá (để đảm bảo SL không quá gần)
        self.min_sl_percent = MIN_SL_PERCENT if 'MIN_SL_PERCENT' in dir() else 0.018  # 1.8% giá
        
        # Risk:Reward Ratio (chỉ dùng khi USE_RISK_REWARD_RATIO = True)
        self.use_risk_reward_ratio = USE_RISK_REWARD_RATIO if 'USE_RISK_REWARD_RATIO' in dir() else False
        self.risk_reward_ratio = RISK_REWARD_RATIO if 'RISK_REWARD_RATIO' in dir() else 1.5
        
        # Technical Analysis Settings - Cài đặt các chỉ báo kỹ thuật (load từ config)
        # RSI (Relative Strength Index)
        self.rsi_period = RSI_PERIOD                   # Chu kỳ RSI (14)
        self.rsi_oversold = RSI_OVERSOLD                # Ngưỡng oversold (30)
        self.rsi_overbought = RSI_OVERBOUGHT           # Ngưỡng overbought (70)
        
        # MACD (Moving Average Convergence Divergence)
        self.macd_fast = MACD_FAST                     # EMA nhanh (12)
        self.macd_slow = MACD_SLOW                     # EMA chậm (26)
        self.macd_signal = MACD_SIGNAL                 # Signal line (9)
        
        # Moving Average
        self.ma_type = MA_TYPE if 'MA_TYPE' in dir() else 'EMA'  # Loại MA: EMA hoặc SMA
        self.ma_periods = MA_PERIODS                   # Danh sách chu kỳ MA [20, 50, 200]
        
        # Bollinger Bands
        self.bb_period = BB_PERIOD                     # Chu kỳ BB (20)
        self.bb_std_dev = BB_STD_DEV                   # Độ lệch chuẩn (2.0)
        
        # ATR (Average True Range) - dùng để tính SL/TP
        self.atr_period = ATR_PERIOD                   # Chu kỳ ATR (14)
        
        # Stochastic Oscillator
        self.stoch_k_period = STOCH_K_PERIOD           # Chu kỳ %K (14)
        self.stoch_d_period = STOCH_D_PERIOD           # Chu kỳ %D (3)
        self.stoch_oversold = STOCH_OVERSOLD           # Ngưỡng oversold (20)
        self.stoch_overbought = STOCH_OVERBOUGHT       # Ngưỡng overbought (80)
        
        # Logic quyết định tín hiệu
        self.min_signal_strength = MIN_SIGNAL_STRENGTH  # Số chỉ báo tối thiểu phải đồng thuận (2)
        self.require_trend_confirmation = REQUIRE_TREND_CONFIRMATION if 'REQUIRE_TREND_CONFIRMATION' in dir() else True
        self.require_momentum_confirmation = REQUIRE_MOMENTUM_CONFIRMATION if 'REQUIRE_MOMENTUM_CONFIRMATION' in dir() else True
        
        # Fibonacci Settings (từ config)
        self.use_fibonacci = USE_FIBONACCI if 'USE_FIBONACCI' in dir() else False
        self.fibonacci_lookback = FIBONACCI_LOOKBACK if 'FIBONACCI_LOOKBACK' in dir() else 100
        self.fibonacci_levels = FIBONACCI_LEVELS if 'FIBONACCI_LEVELS' in dir() else [0.236, 0.382, 0.5, 0.618, 0.786]
        self.fibonacci_tolerance = FIBONACCI_TOLERANCE if 'FIBONACCI_TOLERANCE' in dir() else 0.02
        
        # Volume Analysis Settings (từ config)
        self.use_volume_analysis = USE_VOLUME_ANALYSIS if 'USE_VOLUME_ANALYSIS' in dir() else False
        self.volume_ma_period = VOLUME_MA_PERIOD if 'VOLUME_MA_PERIOD' in dir() else 20
        self.volume_high_threshold = VOLUME_HIGH_THRESHOLD if 'VOLUME_HIGH_THRESHOLD' in dir() else 1.5
        self.volume_low_threshold = VOLUME_LOW_THRESHOLD if 'VOLUME_LOW_THRESHOLD' in dir() else 0.5
        self.require_volume_confirmation = REQUIRE_VOLUME_CONFIRMATION if 'REQUIRE_VOLUME_CONFIRMATION' in dir() else False
        
        # Support/Resistance Settings (từ config)
        self.use_support_resistance = USE_SUPPORT_RESISTANCE if 'USE_SUPPORT_RESISTANCE' in dir() else False
        self.sr_lookback = SR_LOOKBACK if 'SR_LOOKBACK' in dir() else 200
        self.sr_zones_count = SR_ZONES_COUNT if 'SR_ZONES_COUNT' in dir() else 5
        self.sr_touch_min = SR_TOUCH_MIN if 'SR_TOUCH_MIN' in dir() else 2
        self.sr_tolerance = SR_TOLERANCE if 'SR_TOLERANCE' in dir() else 0.01
        self.use_sr_when_no_fib = USE_SR_WHEN_NO_FIB if 'USE_SR_WHEN_NO_FIB' in dir() else True
        
        # ADX Settings (từ config) - Filter Sideways Market
        self.use_adx_filter = USE_ADX_FILTER if 'USE_ADX_FILTER' in dir() else False
        self.adx_period = ADX_PERIOD if 'ADX_PERIOD' in dir() else 14
        self.adx_min_threshold = ADX_MIN_THRESHOLD if 'ADX_MIN_THRESHOLD' in dir() else 25
        self.adx_strong_trend = ADX_STRONG_TREND if 'ADX_STRONG_TREND' in dir() else 40
        
        # Logic quyết định - TỐI ƯU ĐỂ GIẢM TỶ LỆ THUA
        self.require_both_trend_and_momentum = REQUIRE_BOTH_TREND_AND_MOMENTUM if 'REQUIRE_BOTH_TREND_AND_MOMENTUM' in dir() else True
        
        # Trading Settings - Cài đặt giao dịch
        self.interval_seconds = INTERVAL_SECONDS       # Thời gian chờ giữa các lần kiểm tra (30 giây)
        self.historical_bars = HISTORICAL_BARS         # Số nến lịch sử để phân tích (500)
        self.buy_comment = BUY_COMMENT                # Comment cho lệnh BUY
        self.sell_comment = SELL_COMMENT              # Comment cho lệnh SELL
        self.deviation = DEVIATION                    # Độ lệch giá cho phép khi đặt lệnh (100 points)
        
        # Theo dõi giao dịch trong ngày
        self.daily_trades_count = 0                   # Đếm số lệnh đã mở hôm nay
        self.last_trade_date = None                   # Ngày giao dịch cuối cùng (để reset counter)
        
        # CSV logging
        self.csv_log_file = logs_dir / Path(CSV_LOG_FILE).name
        self._init_csv_log()
        
        # Telegram Notifications Settings (từ config)
        self.use_telegram = USE_TELEGRAM_NOTIFICATIONS if 'USE_TELEGRAM_NOTIFICATIONS' in dir() else False
        self.telegram_bot_token = TELEGRAM_BOT_TOKEN if 'TELEGRAM_BOT_TOKEN' in dir() else ""
        self.telegram_chat_id = TELEGRAM_CHAT_ID if 'TELEGRAM_CHAT_ID' in dir() else ""
        self.telegram_send_on_open = TELEGRAM_SEND_ON_ORDER_OPEN if 'TELEGRAM_SEND_ON_ORDER_OPEN' in dir() else True
        self.telegram_send_on_close = TELEGRAM_SEND_ON_ORDER_CLOSE if 'TELEGRAM_SEND_ON_ORDER_CLOSE' in dir() else False
        
        # Khởi tạo TechnicalAnalyzer sau khi đã có config
        self.analyzer = TechnicalAnalyzer(self)
        
    def connect(self) -> bool:
        """Kết nối MT5"""
        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            return False
        
        if not mt5.login(login=self.login, password=self.password, server=self.server):
            logger.error(f"MT5 login failed: {mt5.last_error()}")
            mt5.shutdown()
            return False
        
        self.connected = True
        account_info = mt5.account_info()
        self.initial_balance = account_info.balance
        self.safe_equity_threshold = self.initial_balance * self.min_equity_ratio
        
        logger.info(f"✅ Đã kết nối MT5. Tài khoản: {account_info.login}, Số dư: {account_info.balance:.2f}")
        logger.info(f"📊 Risk Management:")
        logger.info(f"   - Rủi ro mỗi lệnh: {self.risk_per_trade*100:.1f}%")
        logger.info(f"   - Ngưỡng Equity an toàn: {self.safe_equity_threshold:.2f} ({self.min_equity_ratio*100}% Balance)")
        logger.info(f"   - Tối đa {self.max_daily_trades} lệnh/ngày")
        
        # Kiểm tra symbol
        if not self._enable_symbol():
            return False
        
        return True
    
    def disconnect(self):
        """Ngắt kết nối MT5"""
        mt5.shutdown()
        self.connected = False
        logger.info("Đã ngắt kết nối MT5")
    
    def _enable_symbol(self) -> bool:
        """Kích hoạt symbol nếu chưa được enable"""
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None:
            logger.error(f"Symbol {self.symbol} không tồn tại!")
            return False
        
        if not symbol_info.visible:
            if not mt5.symbol_select(self.symbol, True):
                logger.error(f"Không thể kích hoạt symbol {self.symbol}")
                return False
        
        logger.info(f"✅ Symbol {self.symbol} đã sẵn sàng")
        return True
    
    def send_telegram_message(self, message: str) -> bool:
        """
        Gửi thông báo qua Telegram
        
        Args:
            message: Nội dung tin nhắn cần gửi
            
        Returns:
            True nếu gửi thành công, False nếu thất bại
        """
        if not self.use_telegram:
            logger.warning("⚠️ Telegram notifications đã bị tắt (USE_TELEGRAM_NOTIFICATIONS = False)")
            return False
        
        if not self.telegram_bot_token or not self.telegram_chat_id:
            logger.error("❌ Telegram chưa được cấu hình (thiếu BOT_TOKEN hoặc CHAT_ID)")
            logger.error(f"   Bot Token: {'✅ Có' if self.telegram_bot_token else '❌ Không có'}")
            logger.error(f"   Chat ID: {'✅ Có' if self.telegram_chat_id else '❌ Không có'}")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            logger.info(f"📤 Đang gửi thông báo Telegram...")
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
            
            result = response.json()
            if result.get('ok'):
                message_id = result.get('result', {}).get('message_id', 'N/A')
                logger.info(f"✅ Đã gửi thông báo Telegram thành công! Message ID: {message_id}")
                return True
            else:
                error_desc = result.get('description', 'Unknown error')
                logger.error(f"❌ Telegram API trả về lỗi: {error_desc}")
                return False
            
        except requests.exceptions.Timeout:
            logger.error(f"❌ Timeout khi gửi thông báo Telegram (quá 5 giây)")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Không thể gửi thông báo Telegram: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Lỗi không mong đợi khi gửi Telegram: {e}", exc_info=True)
            return False
    
    def get_historical_data(self, timeframe: int = None, bars: int = None) -> Optional[pd.DataFrame]:
        """Lấy dữ liệu lịch sử"""
        if timeframe is None:
            timeframe = self.timeframe
        if bars is None:
            bars = self.historical_bars
        rates = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, bars)
        
        if rates is None or len(rates) == 0:
            logger.error(f"Không thể lấy dữ liệu cho {self.symbol}")
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df
    
    def analyze_market(self, df: pd.DataFrame) -> Dict[str, any]:
        """Phân tích thị trường và tạo tín hiệu"""
        if len(df) < 50:
            return {'signal': 'HOLD', 'strength': 0, 'reason': 'Không đủ dữ liệu'}
        
        signals = []
        reasons = []
        
        # 1. RSI
        rsi = self.analyzer.calculate_rsi(df)
        rsi_current = rsi.iloc[-1]
        
        if not np.isnan(rsi_current):
            if rsi_current < self.rsi_oversold:
                signals.append('BUY')
                reasons.append(f'RSI oversold ({rsi_current:.2f})')
            elif rsi_current > self.rsi_overbought:
                signals.append('SELL')
                reasons.append(f'RSI overbought ({rsi_current:.2f})')
        
        # 2. MACD
        macd_data = self.analyzer.calculate_macd(df)
        macd = macd_data['macd'].iloc[-1]
        macd_signal = macd_data['signal'].iloc[-1]
        macd_hist = macd_data['hist'].iloc[-1]
        macd_hist_prev = macd_data['hist'].iloc[-2] if len(df) > 1 else 0
        
        if not np.isnan(macd_hist):
            if macd_hist > 0 and macd_hist_prev <= 0:
                signals.append('BUY')
                reasons.append('MACD crossover bullish')
            elif macd_hist < 0 and macd_hist_prev >= 0:
                signals.append('SELL')
                reasons.append('MACD crossover bearish')
        
        # 3. Moving Averages
        mas = self.analyzer.calculate_ma(df)
        ma20 = mas['MA_20'].iloc[-1]
        ma50 = mas['MA_50'].iloc[-1]
        price = df['close'].iloc[-1]
        
        if not np.isnan(ma20) and not np.isnan(ma50):
            if price > ma20 and ma20 > ma50:
                signals.append('BUY')
                reasons.append('Price above MA20>MA50 (Uptrend)')
            elif price < ma20 and ma20 < ma50:
                signals.append('SELL')
                reasons.append('Price below MA20<MA50 (Downtrend)')
        
        # 4. Bollinger Bands
        bb = self.analyzer.calculate_bollinger_bands(df)
        bb_upper = bb['upper'].iloc[-1]
        bb_lower = bb['lower'].iloc[-1]
        bb_middle = bb['middle'].iloc[-1]
        
        if not np.isnan(bb_lower) and not np.isnan(bb_upper):
            if price <= bb_lower:
                signals.append('BUY')
                reasons.append('Price at BB lower band')
            elif price >= bb_upper:
                signals.append('SELL')
                reasons.append('Price at BB upper band')
        
        # 5. Stochastic
        stoch = self.analyzer.calculate_stochastic(df)
        stoch_k = stoch['k'].iloc[-1]
        stoch_d = stoch['d'].iloc[-1]
        
        if not np.isnan(stoch_k) and not np.isnan(stoch_d):
            if stoch_k < self.stoch_oversold and stoch_k > stoch_d:
                signals.append('BUY')
                reasons.append(f'Stoch oversold ({stoch_k:.2f})')
            elif stoch_k > self.stoch_overbought and stoch_k < stoch_d:
                signals.append('SELL')
                reasons.append(f'Stoch overbought ({stoch_k:.2f})')
        
        # 6. Fibonacci Retracement Analysis
        fib_signal = None
        fib_reason = None
        fib_level_hit = None
        
        if self.use_fibonacci:
            fib_data = self.analyzer.calculate_fibonacci_levels(df)
            fib_level_hit = self.analyzer.check_fibonacci_level(price, fib_data)
            
            if fib_level_hit:
                # Giá chạm mức Fibonacci - có thể là vùng hỗ trợ/kháng cự
                # Logic: Nếu giá chạm Fibonacci và có các tín hiệu khác đồng thuận
                # ⚠️ CẢI THIỆN: Thêm các mức Fibonacci khác nhưng ưu tiên 0.618, 0.786
                if fib_data['trend'] == 'UPTREND':
                    # Trong uptrend: Fibonacci từ dưới lên = hỗ trợ khi pullback
                    if 'FIB_618' in fib_level_hit or 'FIB_786' in fib_level_hit:
                        # Mức Fibonacci sâu (61.8%, 78.6%) = hỗ trợ mạnh nhất trong uptrend
                        fib_signal = 'BUY'
                        fib_reason = f'Price at Fibonacci {fib_level_hit} support (Uptrend - Strong)'
                    elif 'FIB_382' in fib_level_hit or 'FIB_500' in fib_level_hit:
                        # Mức Fibonacci nhẹ (38.2%, 50%) = hỗ trợ trung bình (tín hiệu yếu hơn)
                        fib_signal = 'BUY'
                        fib_reason = f'Price at Fibonacci {fib_level_hit} support (Uptrend - Moderate)'
                elif fib_data['trend'] == 'DOWNTREND':
                    # Trong downtrend: Fibonacci từ trên xuống = kháng cự khi bounce
                    if 'FIB_618' in fib_level_hit or 'FIB_786' in fib_level_hit:
                        # Mức Fibonacci sâu = kháng cự mạnh nhất trong downtrend
                        fib_signal = 'SELL'
                        fib_reason = f'Price at Fibonacci {fib_level_hit} resistance (Downtrend - Strong)'
                    elif 'FIB_382' in fib_level_hit or 'FIB_500' in fib_level_hit:
                        # Mức Fibonacci nhẹ = kháng cự trung bình (tín hiệu yếu hơn)
                        fib_signal = 'SELL'
                        fib_reason = f'Price at Fibonacci {fib_level_hit} resistance (Downtrend - Moderate)'
        
        # 7. ADX Filter - Lọc Sideways Market (QUAN TRỌNG để giảm tỷ lệ thua)
        adx_data = None
        adx_ok = True  # Mặc định cho phép trade
        
        if self.use_adx_filter:
            adx_data = self.analyzer.calculate_adx(df)
            adx_current = adx_data['adx'].iloc[-1]
            
            if not np.isnan(adx_current):
                # ADX >= threshold = Có trend mạnh → Cho phép trade
                # ADX < threshold = Sideways → Chặn trade (giảm false signals)
                adx_ok = (adx_current >= self.adx_min_threshold)
                
                if not adx_ok:
                    logger.debug(f"⚠️ ADX thấp ({adx_current:.2f} < {self.adx_min_threshold}) - Sideways market, không trade")
            else:
                adx_ok = True  # Nếu không tính được ADX, cho phép trade (fallback)
        
        # 8. Volume Analysis
        volume_data = None
        volume_confirmed = True  # Mặc định cho phép trade
        
        if self.use_volume_analysis:
            volume_data = self.analyzer.analyze_volume(df)
            
            if self.require_volume_confirmation:
                # Yêu cầu volume cao để xác nhận tín hiệu
                volume_confirmed = volume_data.get('is_high_volume', False)
                if not volume_confirmed:
                    # Volume thấp = tín hiệu yếu, có thể là false signal
                    logger.debug(f"⚠️ Volume thấp ({volume_data.get('volume_ratio', 1.0):.2f}), tín hiệu có thể yếu")
        
        # 9. Support/Resistance Analysis (fallback khi không có Fibonacci hoặc khi USE_SR_WHEN_NO_FIB = False)
        sr_signal = None
        sr_reason = None
        sr_check = None
        use_sr_analysis = False
        
        if self.use_support_resistance:
            if self.use_sr_when_no_fib:
                # Chỉ dùng S/R khi không có tín hiệu Fibonacci
                use_sr_analysis = (fib_level_hit is None)
            else:
                # Luôn dùng S/R
                use_sr_analysis = True
        
        if use_sr_analysis:
            sr_data = self.analyzer.find_support_resistance_zones(df)
            sr_check = self.analyzer.check_support_resistance(price, sr_data)
            
            if sr_check and sr_check.get('near_zone'):
                zone_type = sr_check['zone_type']
                zone_price = sr_check['price']
                zone_strength = sr_check['strength']
                
                if zone_type == 'SUPPORT':
                    # Giá gần vùng hỗ trợ = có thể bounce lên
                    sr_signal = 'BUY'
                    sr_reason = f'Price near Support zone at {zone_price:.2f} (strength: {zone_strength})'
                elif zone_type == 'RESISTANCE':
                    # Giá gần vùng kháng cự = có thể reject xuống
                    sr_signal = 'SELL'
                    sr_reason = f'Price near Resistance zone at {zone_price:.2f} (strength: {zone_strength})'
        
        # Đếm tín hiệu
        buy_count = signals.count('BUY')
        sell_count = signals.count('SELL')
        
        # Thêm tín hiệu Fibonacci và S/R vào signals nếu có
        if fib_signal:
            signals.append(fib_signal)
            reasons.append(fib_reason)
            if fib_signal == 'BUY':
                buy_count += 1
            else:
                sell_count += 1
        
        if sr_signal:
            signals.append(sr_signal)
            reasons.append(sr_reason)
            if sr_signal == 'BUY':
                buy_count += 1
            else:
                sell_count += 1
        
        # CẢI THIỆN LOGIC QUYẾT ĐỊNH - Kiểm tra kỹ hơn để giảm false signals
        
        # 1. Kiểm tra xu hướng từ Moving Averages (làm mềm điều kiện)
        trend_buy = False
        trend_sell = False
        if not np.isnan(ma20) and not np.isnan(ma50):
            # Xu hướng tăng: Price > MA20 > MA50 (không cần MA phải đang tăng)
            trend_buy = (price > ma20 and ma20 > ma50)  # Uptrend
            trend_sell = (price < ma20 and ma20 < ma50)  # Downtrend
        
        # 2. Kiểm tra MACD momentum (phải có momentum rõ ràng)
        macd_bullish = False
        macd_bearish = False
        if not np.isnan(macd_hist):
            # MACD phải trên/below zero và tăng/giảm
            macd_bullish = (macd_hist > 0 and macd > macd_signal)
            macd_bearish = (macd_hist < 0 and macd < macd_signal)
        
        # 3. Kiểm tra RSI không ở vùng quá cực đoan
        rsi_extreme_buy = False
        rsi_extreme_sell = False
        if not np.isnan(rsi_current):
            # Chỉ trade khi RSI ở vùng cực đoan (oversold/overbought)
            rsi_extreme_buy = (rsi_current < self.rsi_oversold)
            rsi_extreme_sell = (rsi_current > self.rsi_overbought)
        
        # 4. Đếm tín hiệu nhưng loại bỏ các tín hiệu yếu/không đồng thuận
        strong_buy_signals = 0
        strong_sell_signals = 0
        strong_reasons = []
        
        # RSI - chỉ tính khi cực đoan
        if rsi_extreme_buy:
            strong_buy_signals += 1
            strong_reasons.append(f'RSI oversold ({rsi_current:.2f})')
        elif rsi_extreme_sell:
            strong_sell_signals += 1
            strong_reasons.append(f'RSI overbought ({rsi_current:.2f})')
        
        # MACD - chỉ tính khi có momentum rõ ràng
        if macd_bullish and macd_hist > 0:
            strong_buy_signals += 1
            strong_reasons.append('MACD bullish momentum')
        elif macd_bearish and macd_hist < 0:
            strong_sell_signals += 1
            strong_reasons.append('MACD bearish momentum')
        
        # MA Trend - chỉ tính khi xu hướng rõ ràng
        if trend_buy:
            strong_buy_signals += 1
            strong_reasons.append('Strong Uptrend (Price>MA20>MA50)')
        elif trend_sell:
            strong_sell_signals += 1
            strong_reasons.append('Strong Downtrend (Price<MA20<MA50)')
        
        # Bollinger Bands - giá chạm biên là signal mạnh (sửa logic)
        if not np.isnan(bb_lower) and not np.isnan(bb_upper):
            # Giá chạm BB lower = oversold = BUY signal
            if price <= bb_lower:
                strong_buy_signals += 1
                strong_reasons.append(f'Price at BB lower ({price:.2f} <= {bb_lower:.2f})')
            # Giá chạm BB upper = overbought = SELL signal
            elif price >= bb_upper:
                strong_sell_signals += 1
                strong_reasons.append(f'Price at BB upper ({price:.2f} >= {bb_upper:.2f})')
        
        # Stochastic - đơn giản hóa: chỉ cần oversold/overbought
        if not np.isnan(stoch_k) and not np.isnan(stoch_d):
            # Stochastic oversold = BUY signal
            if stoch_k < self.stoch_oversold and stoch_k > stoch_d:
                strong_buy_signals += 1
                strong_reasons.append(f'Stoch oversold ({stoch_k:.2f} < {stoch_d:.2f})')
            # Stochastic overbought = SELL signal
            elif stoch_k > self.stoch_overbought and stoch_k < stoch_d:
                strong_sell_signals += 1
                strong_reasons.append(f'Stoch overbought ({stoch_k:.2f} > {stoch_d:.2f})')
        
        # Fibonacci - tín hiệu mạnh khi giá chạm mức Fibonacci quan trọng
        if self.use_fibonacci and fib_level_hit:
            if fib_signal == 'BUY':
                strong_buy_signals += 1
                strong_reasons.append(fib_reason)
            elif fib_signal == 'SELL':
                strong_sell_signals += 1
                strong_reasons.append(fib_reason)
        
        # Support/Resistance - tín hiệu mạnh khi giá ở vùng S/R
        if self.use_support_resistance and sr_signal:
            if sr_signal == 'BUY':
                strong_buy_signals += 1
                strong_reasons.append(sr_reason)
            elif sr_signal == 'SELL':
                strong_sell_signals += 1
                strong_reasons.append(sr_reason)
        
        # QUYẾT ĐỊNH CUỐI CÙNG - Kết hợp tất cả tín hiệu
        final_signal = 'HOLD'
        final_strength = 0
        
        require_trend = getattr(self, 'require_trend_confirmation', True)
        require_momentum = getattr(self, 'require_momentum_confirmation', True)
        
        # Điều kiện vào lệnh - TỐI ƯU ĐỂ GIẢM TỶ LỆ THUA:
        # 1. Có đủ signals (>= min_signal_strength) - ĐÃ TĂNG lên 3
        # 2. ADX >= 25 (có trend mạnh, không sideways) - ⚠️ MỚI
        # 3. Volume confirmation (nếu REQUIRE_VOLUME_CONFIRMATION = True) - BẮT BUỘC
        # 4. Trend VÀ Momentum (nếu REQUIRE_BOTH_TREND_AND_MOMENTUM = True) - ⚠️ MỚI: AND logic thay vì OR
        
        # Kiểm tra ADX filter (chặn trade trong sideways market)
        if not adx_ok:
            strong_reasons.append(f'ADX thấp - Sideways market, không trade')
        
        # Kiểm tra volume confirmation
        volume_ok = True
        if self.use_volume_analysis and self.require_volume_confirmation:
            volume_ok = volume_confirmed
            if not volume_ok:
                strong_reasons.append('Volume thấp - tín hiệu không được xác nhận')
        
        # ⚠️ QUAN TRỌNG: Chỉ trade khi ADX OK (có trend) và Volume OK
        if strong_buy_signals >= self.min_signal_strength and adx_ok and volume_ok:
            # Kiểm tra điều kiện bổ sung
            trend_ok = not require_trend or trend_buy
            momentum_ok = not require_momentum or macd_bullish
            
            # ⚠️ THAY ĐỔI: REQUIRE_BOTH_TREND_AND_MOMENTUM
            # True = CẦN CẢ trend VÀ momentum (AND logic) → Tăng độ chính xác
            # False = Chỉ cần 1 trong 2 (OR logic) → Nhiều cơ hội nhưng có thể thua nhiều hơn
            require_both = getattr(self, 'require_both_trend_and_momentum', True)
            
            if require_both:
                # CẦN CẢ trend VÀ momentum (AND logic)
                if trend_ok and momentum_ok:
                    final_signal = 'BUY'
                    final_strength = strong_buy_signals
                else:
                    missing = []
                    if require_trend and not trend_ok:
                        missing.append('no trend')
                    if require_momentum and not momentum_ok:
                        missing.append('no momentum')
                    strong_reasons.append(f'HOLD: Missing {", ".join(missing)} (cần cả 2)')
            else:
                # Chỉ cần 1 trong 2 (OR logic) - Logic cũ
                if trend_ok or momentum_ok:
                    final_signal = 'BUY'
                    final_strength = strong_buy_signals
                    if not trend_ok and not momentum_ok:
                        strong_reasons.append('Warning: No trend or momentum')
                else:
                    missing = []
                    if require_trend and not trend_ok:
                        missing.append('no trend')
                    if require_momentum and not momentum_ok:
                        missing.append('no momentum')
                    strong_reasons.append(f'HOLD: Missing {", ".join(missing)}')
        
        elif strong_sell_signals >= self.min_signal_strength and adx_ok and volume_ok:
            # Kiểm tra điều kiện bổ sung
            trend_ok = not require_trend or trend_sell
            momentum_ok = not require_momentum or macd_bearish
            
            # ⚠️ THAY ĐỔI: REQUIRE_BOTH_TREND_AND_MOMENTUM
            require_both = getattr(self, 'require_both_trend_and_momentum', True)
            
            if require_both:
                # CẦN CẢ trend VÀ momentum (AND logic)
                if trend_ok and momentum_ok:
                    final_signal = 'SELL'
                    final_strength = strong_sell_signals
                else:
                    missing = []
                    if require_trend and not trend_ok:
                        missing.append('no trend')
                    if require_momentum and not momentum_ok:
                        missing.append('no momentum')
                    strong_reasons.append(f'HOLD: Missing {", ".join(missing)} (cần cả 2)')
            else:
                # Chỉ cần 1 trong 2 (OR logic) - Logic cũ
                if trend_ok or momentum_ok:
                    final_signal = 'SELL'
                    final_strength = strong_sell_signals
                    if not trend_ok and not momentum_ok:
                        strong_reasons.append('Warning: No trend or momentum')
                else:
                    missing = []
                    if require_trend and not trend_ok:
                        missing.append('no trend')
                    if require_momentum and not momentum_ok:
                        missing.append('no momentum')
                    strong_reasons.append(f'HOLD: Missing {", ".join(missing)}')
        
        return {
            'signal': final_signal,
            'strength': final_strength,
            'buy_signals': strong_buy_signals,
            'sell_signals': strong_sell_signals,
            'reasons': strong_reasons,
            'current_price': price,
            'rsi': rsi_current if not np.isnan(rsi_current) else None,
            'macd_hist': macd_hist if not np.isnan(macd_hist) else None,
            'trend': 'UP' if trend_buy else 'DOWN' if trend_sell else 'NEUTRAL',
            'momentum': 'BULLISH' if macd_bullish else 'BEARISH' if macd_bearish else 'NEUTRAL',
            # Thêm thông tin Fibonacci, Volume, ADX và S/R
            'fibonacci': {
                'level_hit': fib_level_hit,
                'signal': fib_signal,
                'reason': fib_reason
            } if self.use_fibonacci else None,
            'volume': volume_data,
            'adx': {
                'value': adx_data['adx'].iloc[-1] if (adx_data is not None and len(adx_data['adx']) > 0 and not pd.isna(adx_data['adx'].iloc[-1])) else None,
                'is_strong_trend': adx_ok,
                'plus_di': adx_data['plus_di'].iloc[-1] if (adx_data is not None and len(adx_data['plus_di']) > 0 and not pd.isna(adx_data['plus_di'].iloc[-1])) else None,
                'minus_di': adx_data['minus_di'].iloc[-1] if (adx_data is not None and len(adx_data['minus_di']) > 0 and not pd.isna(adx_data['minus_di'].iloc[-1])) else None
            } if self.use_adx_filter else None,
            'support_resistance': {
                'signal': sr_signal,
                'reason': sr_reason,
                'zone_type': sr_check.get('zone_type') if use_sr_analysis else None
            } if self.use_support_resistance else None
        }
    
    def calculate_risk_parameters(self, df: pd.DataFrame) -> Tuple[float, float, float]:
        """
        Tính toán SL, TP và Lot size dựa trên ATR và Risk Management
        
        Returns:
            (sl_points, tp_points, lot_size)
        """
        symbol_info = mt5.symbol_info(self.symbol)
        point = symbol_info.point
        tick_value = symbol_info.trade_tick_value
        
        # Kiểm tra Risk:Reward Ratio (đã được load từ config trong __init__)
        use_rr_ratio = getattr(self, 'use_risk_reward_ratio', False)
        rr_ratio = getattr(self, 'risk_reward_ratio', 1.5)
        
        if self.use_atr_sl_tp:
            # Tính SL/TP từ ATR
            atr = self.analyzer.calculate_atr(df)
            atr_current = atr.iloc[-1]
            
            if np.isnan(atr_current) or atr_current == 0:
                # Default values nếu ATR không hợp lệ
                sl_points = self.fixed_sl_points if self.fixed_sl_points else self.min_sl_points
                if use_rr_ratio:
                    tp_points = int(sl_points * rr_ratio)
                else:
                    tp_points = self.fixed_tp_points if self.fixed_tp_points else self.min_tp_points
            else:
                # R2: Sử dụng ATR để tính SL/TP rõ ràng
                sl_points = int((self.atr_sl_multiplier * atr_current) / point)
                
                if use_rr_ratio:
                    # Tính TP từ SL theo Risk:Reward ratio
                    tp_points = int(sl_points * rr_ratio)
                else:
                    # Tính TP từ ATR
                    tp_points = int((self.atr_tp_multiplier * atr_current) / point)
                
                # ⚠️ QUAN TRỌNG: Kiểm tra SL tối thiểu dựa trên % giá (để tránh SL quá gần)
                current_price = df['close'].iloc[-1]
                min_sl_from_price = int((current_price * self.min_sl_percent) / point)
                
                # Log thông tin tính SL
                sl_from_atr = sl_points
                
                # Giới hạn min/max - Đảm bảo SL không nhỏ hơn cả MIN_SL_POINTS và MIN_SL_PERCENT × giá
                sl_points = max(self.min_sl_points, min_sl_from_price, min(sl_points, self.max_sl_points))
                tp_points = max(self.min_tp_points, min(tp_points, self.max_tp_points))
                
                # Log nếu SL được điều chỉnh
                if sl_points != sl_from_atr:
                    logger.debug(f"📊 SL điều chỉnh: {sl_from_atr} → {sl_points} points (min: {self.min_sl_points}, min từ giá: {min_sl_from_price})")
        else:
            # Sử dụng giá trị cố định
            sl_points = self.fixed_sl_points
            
            if use_rr_ratio:
                # Tính TP từ SL theo Risk:Reward ratio
                tp_points = int(sl_points * rr_ratio)
            else:
                tp_points = self.fixed_tp_points
            
            # ⚠️ QUAN TRỌNG: Kiểm tra SL tối thiểu dựa trên % giá (cho trường hợp fixed SL)
            # Lấy giá hiện tại từ symbol info hoặc df
            tick = mt5.symbol_info_tick(self.symbol)
            if tick:
                current_price = tick.bid if tick.bid > 0 else tick.ask
            else:
                current_price = df['close'].iloc[-1] if df is not None and len(df) > 0 else 0
            
            if current_price > 0:
                min_sl_from_price = int((current_price * self.min_sl_percent) / point)
                sl_points = max(self.min_sl_points, min_sl_from_price, min(sl_points, self.max_sl_points))
            else:
                sl_points = max(self.min_sl_points, min(sl_points, self.max_sl_points))
            
            tp_points = max(self.min_tp_points, min(tp_points, self.max_tp_points))
        
        # R1: Tính lot size dựa trên risk 1-2% per trade
        account_info = mt5.account_info()
        current_equity = account_info.equity
        risk_amount = current_equity * self.risk_per_trade
        
        # Tính lot size: risk_amount / (sl_points * tick_value * lot_size_factor)
        # Cho BTCUSD: 1 lot = 100 oz, tick_value thường là $1 per point per lot
        if tick_value > 0 and sl_points > 0:
            # Tính lot size từ risk amount
            lot_size = risk_amount / (sl_points * tick_value)
        else:
            # Fallback: sử dụng lot size nhỏ
            lot_size = self.min_lot
        
        # Làm tròn theo bước lot size của broker
        lot_step = symbol_info.volume_step
        lot_size = round(lot_size / lot_step) * lot_step
        
        # Giới hạn min/max
        lot_size = max(self.min_lot, min(lot_size, self.max_lot))
        
        return sl_points, tp_points, lot_size
    
    def get_open_positions(self) -> list:
        """Lấy danh sách vị thế mở"""
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None:
            return []
        
        # Lọc theo magic number
        my_positions = [pos for pos in positions if pos.magic == self.magic_number]
        return my_positions
    
    def has_open_position(self) -> bool:
        """Kiểm tra có vị thế mở không"""
        return len(self.get_open_positions()) > 0
    
    def _check_equity_safety(self) -> Tuple[bool, float]:
        """
        R4: Kiểm tra Equity trước khi trade
        
        Returns:
            (is_safe, current_equity)
        """
        account_info = mt5.account_info()
        if account_info is None:
            return False, 0.0
        
        current_equity = account_info.equity
        
        if current_equity < self.safe_equity_threshold:
            logger.warning(f"⚠️ EQUITY AN TOÀN: {current_equity:.2f} < {self.safe_equity_threshold:.2f}")
            return False, current_equity
        
        return True, current_equity
    
    def _reset_daily_counter(self):
        """Reset daily trade counter nếu sang ngày mới"""
        today = date.today()
        if self.last_trade_date != today:
            self.daily_trades_count = 0
            self.last_trade_date = today
            logger.info(f"🔄 Reset counter ngày mới. Cho phép {self.max_daily_trades} lệnh hôm nay")
    
    def _check_daily_trade_limit(self) -> bool:
        """
        R3: Kiểm tra giới hạn số lệnh trong ngày
        
        Returns:
            True nếu còn có thể trade
        """
        self._reset_daily_counter()
        
        if self.daily_trades_count >= self.max_daily_trades:
            logger.warning(f"⚠️ Đã đạt giới hạn {self.max_daily_trades} lệnh/ngày. Đã trade: {self.daily_trades_count}")
            return False
        
        return True
    
    def _init_csv_log(self):
        """R5: Khởi tạo file CSV log"""
        if not self.csv_log_file.exists():
            with open(self.csv_log_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Time', 'Type', 'Symbol', 'Volume', 'Price', 'SL', 'TP', 
                    'Ticket', 'Equity', 'Balance', 'Profit', 'Status', 'Reason'
                ])
    
    def _log_trade_to_csv(self, order_result: dict, order_type: str, reason: str):
        """
        R5: Log lệnh vào CSV
        
        Args:
            order_result: Kết quả từ order_send
            order_type: 'BUY' hoặc 'SELL'
            reason: Lý do đặt lệnh
        """
        try:
            account_info = mt5.account_info()
            ticket = order_result.order if order_result else 0
            
            # Lấy thông tin lệnh nếu có ticket
            if ticket > 0:
                deals = mt5.history_deals_get(ticket, ticket)
                if deals and len(deals) > 0:
                    deal = deals[0]
                    volume = deal.volume
                    price = deal.price
                else:
                    # Fallback từ request
                    volume = order_result.volume if hasattr(order_result, 'volume') else 0
                    price = order_result.price if hasattr(order_result, 'price') else 0
            else:
                volume = 0
                price = 0
            
            with open(self.csv_log_file, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    order_type,
                    self.symbol,
                    volume,
                    price,
                    order_result.request.sl if order_result and hasattr(order_result, 'request') else 0,
                    order_result.request.tp if order_result and hasattr(order_result, 'request') else 0,
                    ticket,
                    account_info.equity if account_info else 0,
                    account_info.balance if account_info else 0,
                    0,  # Profit (sẽ cập nhật khi đóng)
                    'OPENED',
                    reason
                ])
        except Exception as e:
            logger.error(f"Lỗi khi log CSV: {e}")
    
    def place_buy_order(self, lot: float = None, sl_points: float = None, tp_points: float = None, reason: str = "") -> Optional[dict]:
        """Đặt lệnh Buy với Risk Management"""
        # R4: Kiểm tra Equity trước khi trade
        is_safe, current_equity = self._check_equity_safety()
        if not is_safe:
            logger.error(f"❌ DỪNG TRADE: Equity không an toàn ({current_equity:.2f})")
            return None
        
        # R3: Kiểm tra giới hạn lệnh trong ngày
        if not self._check_daily_trade_limit():
            return None
        
        symbol_info = mt5.symbol_info(self.symbol)
        tick = mt5.symbol_info_tick(self.symbol)
        
        if tick is None or symbol_info is None:
            logger.error(f"Không thể lấy thông tin giá cho {self.symbol}")
            return None
        
        price = tick.ask
        
        # R1 & R2: Tính SL/TP và Lot size từ Risk Management
        if sl_points is None or tp_points is None or lot is None:
            df = self.get_historical_data(timeframe=mt5.TIMEFRAME_M15)
            if df is not None:
                sl_points, tp_points, lot = self.calculate_risk_parameters(df)
            else:
                logger.error("Không thể tính risk parameters")
                return None
        
        point = symbol_info.point
        sl = price - sl_points * point
        tp = price + tp_points * point
        
        # Tính risk amount thực tế
        risk_amount = current_equity * self.risk_per_trade
        logger.info(f"💰 Risk per trade: {risk_amount:.2f} ({self.risk_per_trade*100:.1f}% Equity)")
        logger.info(f"📊 Lot size: {lot:.2f} (tự động tính từ risk)")
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": self.deviation,
            "magic": self.magic_number,
            "comment": self.buy_comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"❌ Lệnh Buy thất bại. Code: {result.retcode}, Lý do: {result.comment}")
            return None
        
        # Tăng counter và log CSV
        self.daily_trades_count += 1
        logger.info(f"✅ Đã mở lệnh BUY {self.symbol} {lot:.2f} lots tại {price:.2f}, SL: {sl:.2f}, TP: {tp:.2f}")
        logger.info(f"📈 Lệnh hôm nay: {self.daily_trades_count}/{self.max_daily_trades}")
        
        # R5: Log vào CSV
        self._log_trade_to_csv(result, 'BUY', reason)
        
        # Gửi thông báo Telegram
        logger.info(f"📱 Kiểm tra Telegram: use_telegram={self.use_telegram}, send_on_open={self.telegram_send_on_open}")
        if self.telegram_send_on_open:
            try:
                account_info = mt5.account_info()
                ticket = result.order if result else 0
                message = (
                    f"🟢 <b>LỆNH MỚI: BUY {self.symbol}</b>\n\n"
                    f"📊 <b>Thông tin lệnh:</b>\n"
                    f"   • Ticket: <code>{ticket}</code>\n"
                    f"   • Volume: <b>{lot:.2f}</b> lots\n"
                    f"   • Giá vào: <b>{price:.2f}</b>\n"
                    f"   • SL: <b>{sl:.2f}</b> ({sl_points} points)\n"
                    f"   • TP: <b>{tp:.2f}</b> ({tp_points} points)\n"
                    f"   • Risk: <b>{current_equity * self.risk_per_trade:.2f}</b> ({self.risk_per_trade*100:.1f}%)\n\n"
                    f"📈 <b>Thông tin tài khoản:</b>\n"
                    f"   • Equity: <b>{account_info.equity:.2f}</b>\n"
                    f"   • Balance: <b>{account_info.balance:.2f}</b>\n"
                    f"   • Lệnh hôm nay: {self.daily_trades_count}/{self.max_daily_trades}\n\n"
                    f"💡 <b>Lý do:</b>\n{reason[:200] if reason else 'Technical Analysis'}"
                )
                telegram_success = self.send_telegram_message(message)
                if not telegram_success:
                    logger.warning(f"⚠️ Không thể gửi thông báo Telegram cho lệnh BUY")
            except Exception as e:
                logger.error(f"❌ Lỗi khi chuẩn bị gửi Telegram: {e}", exc_info=True)
        else:
            logger.info("ℹ️  Telegram notifications đã bị tắt (TELEGRAM_SEND_ON_ORDER_OPEN = False)")
        
        return result
    
    def place_sell_order(self, lot: float = None, sl_points: float = None, tp_points: float = None, reason: str = "") -> Optional[dict]:
        """Đặt lệnh Sell với Risk Management"""
        # R4: Kiểm tra Equity trước khi trade
        is_safe, current_equity = self._check_equity_safety()
        if not is_safe:
            logger.error(f"❌ DỪNG TRADE: Equity không an toàn ({current_equity:.2f})")
            return None
        
        # R3: Kiểm tra giới hạn lệnh trong ngày
        if not self._check_daily_trade_limit():
            return None
        
        symbol_info = mt5.symbol_info(self.symbol)
        tick = mt5.symbol_info_tick(self.symbol)
        
        if tick is None or symbol_info is None:
            logger.error(f"Không thể lấy thông tin giá cho {self.symbol}")
            return None
        
        price = tick.bid
        
        # R1 & R2: Tính SL/TP và Lot size từ Risk Management
        if sl_points is None or tp_points is None or lot is None:
            df = self.get_historical_data(timeframe=mt5.TIMEFRAME_M15)
            if df is not None:
                sl_points, tp_points, lot = self.calculate_risk_parameters(df)
            else:
                logger.error("Không thể tính risk parameters")
                return None
        
        point = symbol_info.point
        sl = price + sl_points * point
        tp = price - tp_points * point
        
        # Tính risk amount thực tế
        risk_amount = current_equity * self.risk_per_trade
        logger.info(f"💰 Risk per trade: {risk_amount:.2f} ({self.risk_per_trade*100:.1f}% Equity)")
        logger.info(f"📊 Lot size: {lot:.2f} (tự động tính từ risk)")
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": self.deviation,
            "magic": self.magic_number,
            "comment": self.sell_comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"❌ Lệnh Sell thất bại. Code: {result.retcode}, Lý do: {result.comment}")
            return None
        
        # Tăng counter và log CSV
        self.daily_trades_count += 1
        logger.info(f"✅ Đã mở lệnh SELL {self.symbol} {lot:.2f} lots tại {price:.2f}, SL: {sl:.2f}, TP: {tp:.2f}")
        logger.info(f"📈 Lệnh hôm nay: {self.daily_trades_count}/{self.max_daily_trades}")
        
        # R5: Log vào CSV
        self._log_trade_to_csv(result, 'SELL', reason)
        
        # Gửi thông báo Telegram
        logger.info(f"📱 Kiểm tra Telegram: use_telegram={self.use_telegram}, send_on_open={self.telegram_send_on_open}")
        if self.telegram_send_on_open:
            try:
                account_info = mt5.account_info()
                ticket = result.order if result else 0
                message = (
                    f"🔴 <b>LỆNH MỚI: SELL {self.symbol}</b>\n\n"
                    f"📊 <b>Thông tin lệnh:</b>\n"
                    f"   • Ticket: <code>{ticket}</code>\n"
                    f"   • Volume: <b>{lot:.2f}</b> lots\n"
                    f"   • Giá vào: <b>{price:.2f}</b>\n"
                    f"   • SL: <b>{sl:.2f}</b> ({sl_points} points)\n"
                    f"   • TP: <b>{tp:.2f}</b> ({tp_points} points)\n"
                    f"   • Risk: <b>{current_equity * self.risk_per_trade:.2f}</b> ({self.risk_per_trade*100:.1f}%)\n\n"
                    f"📈 <b>Thông tin tài khoản:</b>\n"
                    f"   • Equity: <b>{account_info.equity:.2f}</b>\n"
                    f"   • Balance: <b>{account_info.balance:.2f}</b>\n"
                    f"   • Lệnh hôm nay: {self.daily_trades_count}/{self.max_daily_trades}\n\n"
                    f"💡 <b>Lý do:</b>\n{reason[:200] if reason else 'Technical Analysis'}"
                )
                telegram_success = self.send_telegram_message(message)
                if not telegram_success:
                    logger.warning(f"⚠️ Không thể gửi thông báo Telegram cho lệnh SELL")
            except Exception as e:
                logger.error(f"❌ Lỗi khi chuẩn bị gửi Telegram: {e}", exc_info=True)
        else:
            logger.info("ℹ️  Telegram notifications đã bị tắt (TELEGRAM_SEND_ON_ORDER_OPEN = False)")
        
        return result
    
    def run_auto_trading(self, interval_seconds: int = 60):
        """
        Chạy giao dịch tự động với Risk Management
        
        Args:
            interval_seconds: Thời gian chờ giữa các lần kiểm tra (giây)
        """
        logger.info(f"🚀 Bắt đầu giao dịch tự động cho {self.symbol} - TIMEFRAME {self.timeframe_str}")
        logger.info(f"⏱️  Kiểm tra tín hiệu mỗi {interval_seconds} giây")
        logger.info(f"📋 Quy tắc Risk Management:")
        logger.info(f"   - Risk mỗi lệnh: {self.risk_per_trade*100:.1f}% (tự động tính lot size)")
        logger.info(f"   - Số lệnh tối đa cùng lúc: {self.max_positions}")
        logger.info(f"   - Tối đa {self.max_daily_trades} lệnh/ngày")
        logger.info(f"   - Equity an toàn: {self.min_equity_ratio*100}% Balance")
        logger.info(f"   - CSV log: {self.csv_log_file}")
        
        try:
            while True:
                # R4: Kiểm tra Equity trước mỗi chu kỳ
                is_safe, current_equity = self._check_equity_safety()
                if not is_safe:
                    logger.error(f"🛑 DỪNG BOT: Equity không an toàn. Equity: {current_equity:.2f}, Threshold: {self.safe_equity_threshold:.2f}")
                    logger.info("⏸️  Bot sẽ tạm dừng. Chờ Equity cải thiện...")
                    time.sleep(interval_seconds * 5)  # Chờ lâu hơn nếu equity không an toàn
                    continue
                
                # Kiểm tra số lượng vị thế hiện tại
                positions = self.get_open_positions()
                num_positions = len(positions)
                
                # Log thông tin vị thế và Equity
                account_info = mt5.account_info()
                logger.info(f"💵 Equity: {account_info.equity:.2f} | Balance: {account_info.balance:.2f} | Margin: {account_info.margin:.2f}")
                
                if num_positions > 0:
                    logger.info(f"📊 Đang có {num_positions}/{self.max_positions} vị thế mở")
                    total_profit = 0
                    for pos in positions:
                        profit = pos.profit
                        total_profit += profit
                        # Xác định loại lệnh từ pos.type
                        order_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
                        logger.info(f"   - {order_type} {pos.volume:.2f} lots, P&L: {profit:.2f}")
                    logger.info(f"   Tổng P&L: {total_profit:.2f}")
                
                # R3: Kiểm tra daily limit
                self._reset_daily_counter()
                logger.info(f"📅 Lệnh hôm nay: {self.daily_trades_count}/{self.max_daily_trades}")
                
                # Chỉ phân tích và đặt lệnh mới nếu chưa đạt giới hạn
                if num_positions < self.max_positions and self._check_daily_trade_limit():
                    # Lấy dữ liệu và phân tích
                    df = self.get_historical_data()
                    
                    if df is not None:
                        analysis = self.analyze_market(df)
                        reason_str = ', '.join(analysis['reasons']) if analysis['reasons'] else 'No signals'
                        
                        logger.info(f"Phan tich ({self.timeframe_str}): Signal={analysis['signal']}, Strength={analysis['strength']}")
                        logger.info(f"   RSI: {analysis['rsi']:.2f}" if analysis['rsi'] else "   RSI: N/A")
                        logger.info(f"   MA Type: {self.ma_type}, Trend: {analysis.get('trend', 'N/A')}, Momentum: {analysis.get('momentum', 'N/A')}")
                        logger.info(f"   Buy signals: {analysis['buy_signals']}, Sell signals: {analysis['sell_signals']}")
                        
                        # Log Fibonacci
                        if analysis.get('fibonacci') and analysis['fibonacci'].get('level_hit'):
                            fib_info = analysis['fibonacci']
                            logger.info(f"   📊 Fibonacci: {fib_info.get('level_hit', 'N/A')} - {fib_info.get('reason', '')}")
                        
                        # Log Volume
                        if analysis.get('volume'):
                            vol_info = analysis['volume']
                            logger.info(f"   📈 Volume: {vol_info.get('volume_status', 'N/A')} (Ratio: {vol_info.get('volume_ratio', 1.0):.2f})")
                        
                        # Log ADX (quan trọng để biết có trend hay sideways)
                        if analysis.get('adx') and analysis['adx'].get('value') is not None:
                            adx_info = analysis['adx']
                            adx_value = adx_info.get('value', 0)
                            trend_status = "✅ Strong Trend" if adx_info.get('is_strong_trend') else "❌ Sideways"
                            logger.info(f"   📊 ADX: {adx_value:.2f} - {trend_status}")
                        
                        # Log Support/Resistance
                        if analysis.get('support_resistance') and analysis['support_resistance'].get('signal'):
                            sr_info = analysis['support_resistance']
                            logger.info(f"   🎯 S/R: {sr_info.get('zone_type', 'N/A')} - {sr_info.get('reason', '')}")
                        
                        logger.info(f"   Ly do: {reason_str}")
                        
                        # Debug log - tại sao không vào lệnh
                        if analysis['signal'] == 'HOLD':
                            if analysis['buy_signals'] > 0 or analysis['sell_signals'] > 0:
                                logger.info(f"   DEBUG: Co {analysis['buy_signals'] + analysis['sell_signals']} signal nhung khong du dieu kien")
                            else:
                                logger.info(f"   DEBUG: Khong co signal nao")
                        
                        # Kiểm tra lại số lượng vị thế và daily limit trước khi đặt lệnh
                        current_positions = len(self.get_open_positions())
                        if current_positions >= self.max_positions:
                            logger.warning(f"⚠️  Đã đạt giới hạn {self.max_positions} vị thế. Bỏ qua tín hiệu này.")
                        # Thực thi lệnh nếu có tín hiệu mạnh
                        # ⚠️ Đã kiểm tra strength >= MIN_SIGNAL_STRENGTH trong analyze_market()
                        # Nếu đến đây và signal != HOLD nghĩa là đã đủ điều kiện
                        elif analysis['signal'] == 'BUY' and analysis['strength'] >= self.min_signal_strength:
                            logger.info(f"📊 Hiện có {current_positions}/{self.max_positions} vị thế. Cho phép mở lệnh mới.")
                            logger.info(f"✅ Đủ điều kiện: {analysis['strength']} signals (>= {self.min_signal_strength}), ADX OK, Volume OK")
                            self.place_buy_order(reason=reason_str)
                        elif analysis['signal'] == 'SELL' and analysis['strength'] >= self.min_signal_strength:
                            logger.info(f"📊 Hiện có {current_positions}/{self.max_positions} vị thế. Cho phép mở lệnh mới.")
                            logger.info(f"✅ Đủ điều kiện: {analysis['strength']} signals (>= {self.min_signal_strength}), ADX OK, Volume OK")
                            self.place_sell_order(reason=reason_str)
                
                # Chờ trước lần kiểm tra tiếp theo
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            logger.info("⏹️  Dừng giao dịch tự động (Ctrl+C)")
        except Exception as e:
            logger.error(f"❌ Lỗi: {e}", exc_info=True)
        finally:
            self.disconnect()


# Example usage
if __name__ == "__main__":
    # ⚠️ CẢNH BÁO: Thay thế bằng thông tin thực của bạn
    # ⚠️ KHÔNG bao giờ commit thông tin đăng nhập vào git!
    
    TRADER = GoldAutoTrader(
        login=MT5_LOGIN,
        password=MT5_PASSWORD,
        server=MT5_SERVER,
        symbol=SYMBOL
    )
    
    # Kết nối
    if not TRADER.connect():
        logger.error("Không thể kết nối MT5. Thoát chương trình.")
        exit(1)
    
    # Chạy giao dịch tự động
    # Interval được lấy từ config
    TRADER.run_auto_trading(interval_seconds=TRADER.interval_seconds)

