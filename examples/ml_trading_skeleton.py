"""
Machine Learning Trading Skeleton
Example pipeline for ML-based trading strategy
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import MetaTrader5 as mt5
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MLTrader:
    """Machine Learning Trading System"""
    
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_columns = []
        
    def calculate_indicators(self, df):
        """
        Calculate technical indicators
        
        Args:
            df: DataFrame with OHLCV data (columns: open, high, low, close, tick_volume)
        
        Returns:
            DataFrame with added indicator columns
        """
        # Moving Averages
        df['MA_10'] = df['close'].rolling(window=10).mean()
        df['MA_20'] = df['close'].rolling(window=20).mean()
        df['MA_50'] = df['close'].rolling(window=50).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = ema_12 - ema_26
        df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_hist'] = df['MACD'] - df['MACD_signal']
        
        # ATR (Average True Range)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(window=14).mean()
        
        # Bollinger Bands
        df['BB_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['BB_upper'] = df['BB_middle'] + (bb_std * 2)
        df['BB_lower'] = df['BB_middle'] - (bb_std * 2)
        df['BB_width'] = (df['BB_upper'] - df['BB_lower']) / df['BB_middle']
        
        # Price changes
        df['price_change'] = df['close'].pct_change()
        df['high_low_ratio'] = (df['high'] - df['low']) / df['close']
        
        return df
    
    def create_features(self, df):
        """Create feature matrix from indicators"""
        feature_cols = [
            'MA_10', 'MA_20', 'MA_50',
            'RSI', 'MACD', 'MACD_signal', 'MACD_hist',
            'ATR', 'BB_middle', 'BB_upper', 'BB_lower', 'BB_width',
            'price_change', 'high_low_ratio', 'tick_volume'
        ]
        
        # Select available columns
        available_cols = [col for col in feature_cols if col in df.columns]
        self.feature_columns = available_cols
        
        X = df[available_cols].copy()
        X = X.dropna()
        
        return X
    
    def create_labels(self, df, lookahead=1, threshold=0.001):
        """
        Create labels for classification
        1 = Buy (price goes up > threshold)
        0 = Hold (price change within threshold)
        -1 = Sell (price goes down > threshold)
        
        Args:
            df: DataFrame with close prices
            lookahead: Number of bars to look ahead
            threshold: Minimum price change to trigger signal
        """
        future_prices = df['close'].shift(-lookahead)
        price_change = (future_prices - df['close']) / df['close']
        
        y = np.zeros(len(price_change))
        y[price_change > threshold] = 1   # Buy
        y[price_change < -threshold] = -1  # Sell
        # y = 0 for hold (already initialized)
        
        # Align with feature data (remove NaN rows)
        y = y[:len(price_change)]
        
        return y
    
    def prepare_data(self, symbol, timeframe=mt5.TIMEFRAME_M1, n_bars=10000):
        """
        Fetch and prepare data from MT5
        
        Args:
            symbol: Trading symbol
            timeframe: MT5 timeframe
            n_bars: Number of historical bars to fetch
        """
        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            return None, None
        
        # Fetch historical data
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_bars)
        
        if rates is None or len(rates) == 0:
            logger.error(f"Failed to fetch data for {symbol}")
            return None, None
        
        # Convert to DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Calculate indicators
        df = self.calculate_indicators(df)
        
        # Create features and labels
        X = self.create_features(df)
        y = self.create_labels(df)
        
        # Align X and y (remove NaN rows)
        min_len = min(len(X), len(y))
        X = X.iloc[:min_len]
        y = y[:min_len]
        
        # Remove rows where features or labels are NaN
        mask = ~(X.isna().any(axis=1) | np.isnan(y))
        X = X[mask]
        y = y[mask]
        
        logger.info(f"Prepared data: {len(X)} samples, {X.shape[1]} features")
        
        return X, y
    
    def train(self, X, y):
        """Train the ML model"""
        if len(X) == 0:
            logger.error("No data to train on")
            return False
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, random_state=42, stratify=None
        )
        
        # Train model
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1
        )
        
        self.model.fit(X_train, y_train)
        
        # Evaluate
        train_score = self.model.score(X_train, y_train)
        test_score = self.model.score(X_test, y_test)
        
        logger.info(f"Model trained - Train score: {train_score:.4f}, Test score: {test_score:.4f}")
        
        return True
    
    def predict(self, X):
        """Make prediction on new data"""
        if self.model is None:
            logger.error("Model not trained yet")
            return None
        
        X_scaled = self.scaler.transform(X)
        prediction = self.model.predict(X_scaled)
        probabilities = self.model.predict_proba(X_scaled)
        
        return prediction, probabilities
    
    def get_latest_features(self, symbol, timeframe=mt5.TIMEFRAME_M1, n_bars=100):
        """Get latest features for live trading"""
        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            return None
        
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_bars)
        
        if rates is None:
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = self.calculate_indicators(df)
        
        X = self.create_features(df)
        
        if len(X) == 0:
            return None
        
        # Get the most recent row
        latest_features = X.iloc[-1:].copy()
        
        return latest_features


# Example usage
if __name__ == "__main__":
    # Initialize ML Trader
    ml_trader = MLTrader()
    
    # Prepare data (example with EURUSD)
    logger.info("Preparing data...")
    X, y = ml_trader.prepare_data("EURUSD", mt5.TIMEFRAME_M1, n_bars=5000)
    
    if X is not None and len(X) > 0:
        # Train model
        logger.info("Training model...")
        ml_trader.train(X, y)
        
        # Get latest features for prediction
        logger.info("Getting latest features...")
        latest = ml_trader.get_latest_features("EURUSD", mt5.TIMEFRAME_M1)
        
        if latest is not None:
            # Make prediction
            prediction, probabilities = ml_trader.predict(latest)
            logger.info(f"Prediction: {prediction[0]} (Buy=1, Hold=0, Sell=-1)")
            logger.info(f"Probabilities: {probabilities[0]}")
    
    mt5.shutdown()

