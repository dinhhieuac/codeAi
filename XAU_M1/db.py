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
                comment TEXT,
                account_id INTEGER DEFAULT 0
            )
        ''')

        # Lệnh chờ Grid Step: BUY_STOP / SELL_STOP, cập nhật status khi khớp hoặc hủy
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS grid_pending_orders (
                ticket INTEGER PRIMARY KEY,
                strategy_name TEXT,
                symbol TEXT,
                order_type TEXT,
                price REAL,
                sl REAL,
                tp REAL,
                volume REAL,
                status TEXT DEFAULT 'PENDING',
                position_ticket INTEGER,
                placed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                filled_at DATETIME,
                account_id INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()

    def _migrate_tables(self):
        """Add account_id column to existing tables if missing"""
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

    def order_exists(self, ticket):
        """Kiểm tra order đã tồn tại trong bảng orders chưa."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM orders WHERE ticket = ?", (ticket,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def log_order(self, ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, comment="", account_id=0):
        """Log an executed order"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO orders (ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, open_time, comment, account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)
        ''', (ticket, strategy_name, symbol, order_type, volume, open_price, sl, tp, comment, account_id))
        
        conn.commit()
        conn.close()
    
    def update_order_profit(self, ticket, close_price, profit, close_time=None):
        """Update closed order with profit and close_time (giờ đóng lệnh, dùng cho pause tính từ lệnh thua cuối)."""
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

    def log_grid_pending(self, ticket, strategy_name, symbol, order_type, price, sl, tp, volume, account_id=0):
        """Lưu lệnh chờ BUY_STOP / SELL_STOP (status PENDING)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO grid_pending_orders
            (ticket, strategy_name, symbol, order_type, price, sl, tp, volume, status, account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
        ''', (ticket, strategy_name, symbol, order_type, price, sl, tp, volume, account_id))
        conn.commit()
        conn.close()

    def update_grid_pending_status(self, ticket, status, position_ticket=None):
        """Cập nhật status: FILLED (khi khớp) hoặc CANCELLED (khi hủy)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE grid_pending_orders
            SET status = ?, position_ticket = ?,
                filled_at = CASE WHEN ? = 'FILLED' THEN datetime('now') ELSE filled_at END
            WHERE ticket = ?
        ''', (status, position_ticket or 0, status, ticket))
        conn.commit()
        conn.close()

    def get_grid_pending_by_status(self, strategy_name, symbol, status='PENDING'):
        """Lấy danh sách lệnh chờ theo status (để kiểm tra và cập nhật)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ticket, order_type, price FROM grid_pending_orders
            WHERE strategy_name = ? AND symbol = ? AND status = ?
        ''', (strategy_name, symbol, status))
        rows = cursor.fetchall()
        conn.close()
        return [{"ticket": r[0], "order_type": r[1], "price": r[2]} for r in rows]

    def get_last_closed_orders(self, strategy_name, limit=10, account_id=None):
        """Lấy các lệnh đã đóng gần nhất (profit IS NOT NULL), sắp theo thời gian đóng (close_time hoặc open_time) DESC."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Ưu tiên close_time (giờ server đóng lệnh) để tính pause từ lệnh thua cuối
        order_col = "COALESCE(close_time, open_time) DESC"
        if account_id is not None:
            cursor.execute(f'''
                SELECT profit, open_time, close_time FROM orders
                WHERE strategy_name = ? AND profit IS NOT NULL AND account_id = ?
                ORDER BY {order_col} LIMIT ?
            ''', (strategy_name, account_id, limit))
        else:
            cursor.execute(f'''
                SELECT profit, open_time, close_time FROM orders
                WHERE strategy_name = ? AND profit IS NOT NULL
                ORDER BY {order_col} LIMIT ?
            ''', (strategy_name, limit))
        rows = cursor.fetchall()
        conn.close()
        return [{"profit": r[0], "open_time": r[1], "close_time": r[2]} for r in rows]
