"""
Gold Auto Trader - Hệ thống giao dịch tự động cho vàng (XAUUSD)
Tự động phân tích và thực thi lệnh Buy/Sell dựa trên phân tích kỹ thuật
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import logging
from typing import Optional, Dict, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/gold_trader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """Phân tích kỹ thuật với các chỉ báo"""
    
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Tính RSI (Relative Strength Index)"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        """Tính MACD"""
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_hist = macd - macd_signal
        return {'macd': macd, 'signal': macd_signal, 'hist': macd_hist}
    
    @staticmethod
    def calculate_ma(df: pd.DataFrame, periods: list) -> Dict[str, pd.Series]:
        """Tính Moving Averages"""
        mas = {}
        for period in periods:
            mas[f'MA_{period}'] = df['close'].rolling(window=period).mean()
        return mas
    
    @staticmethod
    def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> Dict[str, pd.Series]:
        """Tính Bollinger Bands"""
        sma = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return {'upper': upper, 'middle': sma, 'lower': lower}
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Tính ATR (Average True Range)"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr
    
    @staticmethod
    def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Dict[str, pd.Series]:
        """Tính Stochastic Oscillator"""
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        k = 100 * ((df['close'] - low_min) / (high_max - low_min))
        d = k.rolling(window=d_period).mean()
        return {'k': k, 'd': d}


class GoldAutoTrader:
    """Hệ thống giao dịch tự động cho vàng"""
    
    def __init__(self, login: int, password: str, server: str, symbol: str = "XAUUSD"):
        """
        Khởi tạo Gold Auto Trader
        
        Args:
            login: MT5 account login
            password: MT5 account password
            server: MT5 server name
            symbol: Symbol để giao dịch (mặc định XAUUSD)
        """
        self.login = login
        self.password = password
        self.server = server
        self.symbol = symbol
        self.magic_number = 888888  # Magic number cho vàng
        self.connected = False
        self.analyzer = TechnicalAnalyzer()
        
        # Cấu hình giao dịch
        self.default_lot = 0.01  # Lot size cố định 0.01
        self.max_lot = 0.01  # Giới hạn tối đa = 0.01 (không cho phép lớn hơn)
        self.max_positions = 10  # Số lượng vị thế tối đa cùng lúc (tối đa 10 lệnh)
        
        # Ngưỡng phân tích
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        self.stoch_oversold = 20
        self.stoch_overbought = 80
        
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
        logger.info(f"✅ Đã kết nối MT5. Tài khoản: {account_info.login}, Số dư: {account_info.balance:.2f}")
        
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
    
    def get_historical_data(self, timeframe: int = mt5.TIMEFRAME_H1, bars: int = 200) -> Optional[pd.DataFrame]:
        """Lấy dữ liệu lịch sử"""
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
        rsi = self.analyzer.calculate_rsi(df, period=14)
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
        mas = self.analyzer.calculate_ma(df, periods=[20, 50, 200])
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
        
        # Đếm tín hiệu
        buy_count = signals.count('BUY')
        sell_count = signals.count('SELL')
        
        # Quyết định cuối cùng
        if buy_count > sell_count and buy_count >= 2:
            signal = 'BUY'
            strength = buy_count
        elif sell_count > buy_count and sell_count >= 2:
            signal = 'SELL'
            strength = sell_count
        else:
            signal = 'HOLD'
            strength = 0
        
        return {
            'signal': signal,
            'strength': strength,
            'buy_signals': buy_count,
            'sell_signals': sell_count,
            'reasons': reasons,
            'current_price': price,
            'rsi': rsi_current if not np.isnan(rsi_current) else None,
            'macd_hist': macd_hist if not np.isnan(macd_hist) else None
        }
    
    def calculate_risk_parameters(self, df: pd.DataFrame) -> Tuple[float, float]:
        """
        Tính toán SL và TP dựa trên ATR
        
        Returns:
            (sl_points, tp_points)
        """
        atr = self.analyzer.calculate_atr(df, period=14)
        atr_current = atr.iloc[-1]
        
        if np.isnan(atr_current) or atr_current == 0:
            # Default values cho vàng (XAUUSD)
            # 1 point = 0.01 (ví dụ: 2000.01 -> 2000.02)
            sl_points = 100  # ~$1 cho 0.01 lot
            tp_points = 200  # ~$2 cho 0.01 lot
        else:
            # Sử dụng ATR để tính SL/TP động
            # SL = 2 * ATR, TP = 3 * ATR
            symbol_info = mt5.symbol_info(self.symbol)
            point = symbol_info.point
            
            sl_points = int((2 * atr_current) / point)
            tp_points = int((3 * atr_current) / point)
            
            # Giới hạn min/max
            sl_points = max(50, min(sl_points, 500))  # Min 50, Max 500 points
            tp_points = max(100, min(tp_points, 1000))  # Min 100, Max 1000 points
        
        return sl_points, tp_points
    
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
    
    def place_buy_order(self, lot: float = None, sl_points: float = None, tp_points: float = None) -> Optional[dict]:
        """Đặt lệnh Buy"""
        # Luôn sử dụng lot size cố định 0.01
        lot = self.default_lot  # 0.01 cố định
        
        symbol_info = mt5.symbol_info(self.symbol)
        tick = mt5.symbol_info_tick(self.symbol)
        
        if tick is None or symbol_info is None:
            logger.error(f"Không thể lấy thông tin giá cho {self.symbol}")
            return None
        
        price = tick.ask
        
        # Tính SL/TP nếu chưa có
        if sl_points is None or tp_points is None:
            df = self.get_historical_data()
            if df is not None:
                sl_points, tp_points = self.calculate_risk_parameters(df)
        
        point = symbol_info.point
        sl = price - sl_points * point
        tp = price + tp_points * point
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 10,
            "magic": self.magic_number,
            "comment": "Gold Auto Buy",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"❌ Lệnh Buy thất bại. Code: {result.retcode}, Lý do: {result.comment}")
            return None
        
        logger.info(f"✅ Đã mở lệnh BUY {self.symbol} {lot} lots tại {price:.2f}, SL: {sl:.2f}, TP: {tp:.2f}")
        return result
    
    def place_sell_order(self, lot: float = None, sl_points: float = None, tp_points: float = None) -> Optional[dict]:
        """Đặt lệnh Sell"""
        # Luôn sử dụng lot size cố định 0.01
        lot = self.default_lot  # 0.01 cố định
        
        symbol_info = mt5.symbol_info(self.symbol)
        tick = mt5.symbol_info_tick(self.symbol)
        
        if tick is None or symbol_info is None:
            logger.error(f"Không thể lấy thông tin giá cho {self.symbol}")
            return None
        
        price = tick.bid
        
        # Tính SL/TP nếu chưa có
        if sl_points is None or tp_points is None:
            df = self.get_historical_data()
            if df is not None:
                sl_points, tp_points = self.calculate_risk_parameters(df)
        
        point = symbol_info.point
        sl = price + sl_points * point
        tp = price - tp_points * point
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 10,
            "magic": self.magic_number,
            "comment": "Gold Auto Sell",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"❌ Lệnh Sell thất bại. Code: {result.retcode}, Lý do: {result.comment}")
            return None
        
        logger.info(f"✅ Đã mở lệnh SELL {self.symbol} {lot} lots tại {price:.2f}, SL: {sl:.2f}, TP: {tp:.2f}")
        return result
    
    def run_auto_trading(self, interval_seconds: int = 60):
        """
        Chạy giao dịch tự động
        
        Args:
            interval_seconds: Thời gian chờ giữa các lần kiểm tra (giây)
        """
        logger.info(f"🚀 Bắt đầu giao dịch tự động cho {self.symbol}")
        logger.info(f"⏱️  Kiểm tra tín hiệu mỗi {interval_seconds} giây")
        logger.info(f"📋 Quy tắc giao dịch:")
        logger.info(f"   - Lot size cố định: {self.default_lot} (không thay đổi)")
        logger.info(f"   - Số lệnh tối đa: {self.max_positions} lệnh cùng lúc")
        
        try:
            while True:
                # Kiểm tra số lượng vị thế hiện tại
                positions = self.get_open_positions()
                num_positions = len(positions)
                
                # Log thông tin vị thế nếu có
                if num_positions > 0:
                    logger.info(f"📊 Đang có {num_positions}/{self.max_positions} vị thế mở")
                    for pos in positions:
                        profit = pos.profit
                        logger.info(f"   - {pos.type_string} {pos.volume} lots, P&L: {profit:.2f}")
                
                # Chỉ phân tích và đặt lệnh mới nếu chưa đạt giới hạn (tối đa 10 lệnh)
                if num_positions < self.max_positions:
                    # Lấy dữ liệu và phân tích
                    df = self.get_historical_data(timeframe=mt5.TIMEFRAME_H1, bars=200)
                    
                    if df is not None:
                        analysis = self.analyze_market(df)
                        
                        logger.info(f"📈 Phân tích: Signal={analysis['signal']}, Strength={analysis['strength']}")
                        logger.info(f"   RSI: {analysis['rsi']:.2f}" if analysis['rsi'] else "   RSI: N/A")
                        logger.info(f"   Lý do: {', '.join(analysis['reasons'])}")
                        
                        # Kiểm tra lại số lượng vị thế trước khi đặt lệnh (đảm bảo < 10)
                        current_positions = len(self.get_open_positions())
                        if current_positions >= self.max_positions:
                            logger.warning(f"⚠️  Đã đạt giới hạn {self.max_positions} lệnh. Bỏ qua tín hiệu này.")
                        # Thực thi lệnh nếu có tín hiệu mạnh và chưa đạt giới hạn
                        elif analysis['signal'] == 'BUY' and analysis['strength'] >= 2:
                            logger.info(f"📊 Hiện có {current_positions}/{self.max_positions} lệnh. Cho phép mở lệnh mới.")
                            self.place_buy_order()
                        elif analysis['signal'] == 'SELL' and analysis['strength'] >= 2:
                            logger.info(f"📊 Hiện có {current_positions}/{self.max_positions} lệnh. Cho phép mở lệnh mới.")
                            self.place_sell_order()
                
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
        login=272736909,  # Thay bằng số tài khoản MT5 của bạn
        password="@Dinhhieu273",  # Thay bằng mật khẩu MT5 của bạn
        server="Exness-MT5Trial14",  # Thay bằng tên server của bạn
        symbol="XAUUSD"  # Symbol vàng (có thể đổi thành XAUUSDm nếu cần)
    )
    
    # Kết nối
    if not TRADER.connect():
        logger.error("Không thể kết nối MT5. Thoát chương trình.")
        exit(1)
    
    # Chạy giao dịch tự động
    # Kiểm tra mỗi 60 giây (có thể thay đổi)
    TRADER.run_auto_trading(interval_seconds=60)

