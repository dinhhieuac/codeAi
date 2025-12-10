import sqlite3
import datetime
import os
import json

class Database:
    def __init__(self, db_path=None):
        """Initialize database connection"""
        if db_path is None:
            # Default to trades.db in the same directory as this script
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.db")
        
        self.db_path = db_path
        self._create_tables()

    def _create_tables(self):
        """Create necessary tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table for logging signals (analysis)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                strategy_name TEXT,
                symbol TEXT,
                signal_type TEXT,
                price REAL,
                sl REAL,
                tp REAL,
                indicators TEXT,
                status TEXT
            )
        ''')

        # Table for logging executed orders
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                ticket INTEGER PRIMARY KEY,
                strategy_name TEXT,
                symbol TEXT,
                order_type TEXT,
                volume REAL,
                open_price REAL,
                sl REAL,
                tp REAL,
                open_time DATETIME,
                close_price REAL,
                profit REAL,
                comment TEXT
            )
        ''')
        
        conn.commit()
        conn.close()

    def log_signal(self, strategy_name, symbol, signal_type, price, sl, tp, indicators, status="PENDING"):
        """Log a trading signal"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Convert indicators dict to JSON string if needed
        if isinstance(indicators, dict):
            indicators = json.dumps(indicators)
            
        cursor.execute('''
            INSERT INTO signals (strategy_name, symbol, signal_type, price, sl, tp, indicators, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (strategy_name, symbol, signal_type, price, sl, tp, indicators, status))
        
        conn.commit()
        conn.close()

    def log_order(self, ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, comment=""):
        """Log an executed order"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO orders (ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, open_time, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
        ''', (ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, comment))
        
        conn.commit()
        conn.close()
    
    def update_order_profit(self, ticket, close_price, profit):
        """Update closed order with profit"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE orders 
            SET close_price = ?, profit = ? 
            WHERE ticket = ?
        ''', (close_price, profit, ticket))
        
        conn.commit()
        conn.close()
