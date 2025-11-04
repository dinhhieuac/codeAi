import pandas as pd
import numpy as np
from config_xauusd import *

class TechnicalAnalyzer:
    def __init__(self):
        self.min_sl_pips = MIN_SL_PIPS
        self.min_tp_pips = MIN_TP_PIPS
        
    def calculate_rsi(self, prices, period=14):
        """Tính RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
        
    def calculate_ema(self, prices, period):
        """Tính EMA"""
        return prices.ewm(span=period, adjust=False).mean()
        
    def calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """Tính MACD"""
        ema_fast = self.calculate_ema(prices, fast)
        ema_slow = self.calculate_ema(prices, slow)
        macd = ema_fast - ema_slow
        signal_line = self.calculate_ema(macd, signal)
        histogram = macd - signal_line
        return macd, signal_line, histogram
        
    def calculate_bollinger_bands(self, prices, period=20, std_dev=2):
        """Tính Bollinger Bands"""
        sma = prices.rolling(period).mean()
        std = prices.rolling(period).std()
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        return upper_band, sma, lower_band
        
    def calculate_atr(self, high, low, close, period=14):
        """Tính Average True Range"""
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        return atr
        
    def analyze(self, df):
        """Phân tích kỹ thuật toàn diện"""
        if len(df) < 50:
            return None
            
        close = df['close']
        high = df['high']
        low = df['low']
        
        # Tính các indicator
        df['rsi'] = self.calculate_rsi(close, 14)
        df['ema_20'] = self.calculate_ema(close, 20)
        df['ema_50'] = self.calculate_ema(close, 50)
        macd, macd_signal, macd_hist = self.calculate_macd(close)
        df['macd'] = macd
        df['macd_signal'] = macd_signal
        df['macd_hist'] = macd_hist
        
        upper_bb, middle_bb, lower_bb = self.calculate_bollinger_bands(close)
        df['upper_bb'] = upper_bb
        df['lower_bb'] = lower_bb
        
        df['atr'] = self.calculate_atr(high, low, close)
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Tính điểm tín hiệu
        buy_signals = 0
        sell_signals = 0
        
        # Tín hiệu RSI
        if current['rsi'] < 30 and prev['rsi'] >= 30:
            buy_signals += 2
        elif current['rsi'] > 70 and prev['rsi'] <= 70:
            sell_signals += 2
            
        # Tín hiệu EMA
        if current['ema_20'] > current['ema_50'] and prev['ema_20'] <= prev['ema_50']:
            buy_signals += 1
        elif current['ema_20'] < current['ema_50'] and prev['ema_20'] >= prev['ema_50']:
            sell_signals += 1
            
        # Tín hiệu MACD
        if current['macd'] > current['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            buy_signals += 1
        elif current['macd'] < current['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            sell_signals += 1
            
        # Tín hiệu Bollinger Bands
        if current['close'] < current['lower_bb']:
            buy_signals += 1
        elif current['close'] > current['upper_bb']:
            sell_signals += 1
            
        # Xác định tín hiệu cuối cùng
        atr_value = current['atr'] / 0.01  # Convert to pips
        
        if buy_signals >= 3 and buy_signals > sell_signals:
            sl_pips = max(self.min_sl_pips, atr_value * 1.5)
            tp_pips = max(self.min_tp_pips, int(sl_pips * MIN_RR_RATIO))
            return {
                'action': 'BUY',
                'strength': buy_signals,
                'sl_pips': sl_pips,
                'tp_pips': tp_pips
            }
        elif sell_signals >= 3 and sell_signals > buy_signals:
            sl_pips = max(self.min_sl_pips, atr_value * 1.5)
            tp_pips = max(self.min_tp_pips, int(sl_pips * MIN_RR_RATIO))
            return {
                'action': 'SELL', 
                'strength': sell_signals,
                'sl_pips': sl_pips,
                'tp_pips': tp_pips
            }
        else:
            return {
                'action': 'HOLD',
                'strength': 0,
                'sl_pips': 0,
                'tp_pips': 0
            }