import sqlite3
import datetime
import os
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

class Database:
    def __init__(self, db_path=None):
        """Initialize database connection"""
        if db_path is None:
            # Default to trades.db in the same directory as this script
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.db")
        
        self.db_path = db_path
        self._create_tables()
        self._migrate_tables()

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
                status TEXT,
                account_id INTEGER DEFAULT 0
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
                close_time DATETIME,
                comment TEXT,
                account_id INTEGER DEFAULT 0,
                initial_sl REAL
            )
        ''')
        
        conn.commit()
        conn.close()

    def _migrate_tables(self):
        """Add account_id, close_time, and initial_sl columns to existing tables if missing"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check orders table
        cursor.execute("PRAGMA table_info(orders)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'account_id' not in columns:
            print("📦 Migrating DB: Adding account_id to orders table...")
            cursor.execute("ALTER TABLE orders ADD COLUMN account_id INTEGER DEFAULT 0")
            
        if 'close_time' not in columns:
            print("📦 Migrating DB: Adding close_time to orders table...")
            cursor.execute("ALTER TABLE orders ADD COLUMN close_time DATETIME")

        if 'initial_sl' not in columns:
            print("📦 Migrating DB: Adding initial_sl to orders table...")
            cursor.execute("ALTER TABLE orders ADD COLUMN initial_sl REAL")
            cursor.execute("UPDATE orders SET initial_sl = sl WHERE initial_sl IS NULL AND sl IS NOT NULL")
            
        # Check signals table
        cursor.execute("PRAGMA table_info(signals)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'account_id' not in columns:
            print("📦 Migrating DB: Adding account_id to signals table...")
            cursor.execute("ALTER TABLE signals ADD COLUMN account_id INTEGER DEFAULT 0")
            
        conn.commit()
        conn.close()

    def log_signal(self, strategy_name, symbol, signal_type, price, sl, tp, indicators, status="PENDING", account_id=0):
        """Log a trading signal"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Convert indicators dict to JSON string if needed
        if isinstance(indicators, dict):
            indicators = json.dumps(indicators)
            
        cursor.execute('''
            INSERT INTO signals (strategy_name, symbol, signal_type, price, sl, tp, indicators, status, account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (strategy_name, symbol, signal_type, price, sl, tp, indicators, status, account_id))
        
        conn.commit()
        conn.close()

    def log_order(self, ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, comment="", account_id=0, initial_sl=None):
        """Log an executed order"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if initial_sl is None:
            initial_sl = sl
            
        cursor.execute('''
            INSERT OR REPLACE INTO orders (ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, open_time, comment, account_id, initial_sl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
        ''', (ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, comment, account_id, initial_sl))
        
        conn.commit()
        conn.close()
    
    def get_initial_sl(self, ticket):
        """Get initial SL and open price for a given ticket from DB"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT initial_sl, sl, open_price FROM orders WHERE ticket = ?", (ticket,))
        row = cursor.fetchone()
        conn.close()
        if row:
            init_sl = row[0] if (row[0] is not None and row[0] > 0) else row[1]
            return init_sl, row[2]
        return None, None
    
    def update_order_profit(self, ticket, close_price, profit, close_time=None):
        """Update closed order with profit and optional close_time"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if close_time is not None:
            cursor.execute('''
                UPDATE orders 
                SET close_price = ?, profit = ?, close_time = ? 
                WHERE ticket = ?
            ''', (close_price, profit, close_time, ticket))
        else:
            cursor.execute('''
                UPDATE orders 
                SET close_price = ?, profit = ? 
                WHERE ticket = ?
            ''', (close_price, profit, ticket))
        
        conn.commit()
        conn.close()
