"""
MetaTrader5 Python Module - Basic Trading Example
Example script for connecting to Exness MT5 and placing orders
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MT5Trader:
    """Wrapper class for MT5 trading operations"""
    
    def __init__(self, login, password, server):
        """
        Initialize MT5 connection
        
        Args:
            login: MT5 account login number
            password: MT5 account password
            server: Server name (e.g., "Exness-MT5")
        """
        self.login = login
        self.password = password
        self.server = server
        self.connected = False
    
    def connect(self):
        """Connect to MT5 terminal"""
        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            return False
        
        if not mt5.login(login=self.login, password=self.password, server=self.server):
            logger.error(f"MT5 login failed. Error: {mt5.last_error()}")
            mt5.shutdown()
            return False
        
        self.connected = True
        account_info = mt5.account_info()
        logger.info(f"Connected successfully. Account: {account_info.login}, Balance: {account_info.balance}")
        return True
    
    def disconnect(self):
        """Disconnect from MT5 terminal"""
        mt5.shutdown()
        self.connected = False
        logger.info("Disconnected from MT5")
    
    def get_symbol_info(self, symbol):
        """Get symbol information"""
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"Symbol {symbol} not found")
            return None
        return symbol_info
    
    def get_current_price(self, symbol):
        """Get current tick price for symbol"""
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Failed to get tick for {symbol}")
            return None
        return {'ask': tick.ask, 'bid': tick.bid, 'time': tick.time}
    
    def place_buy_order(self, symbol, lot, sl_points=50, tp_points=100, comment="Python EA"):
        """
        Place a buy order
        
        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            lot: Lot size
            sl_points: Stop loss in points
            tp_points: Take profit in points
            comment: Order comment
        """
        if not self.connected:
            logger.error("Not connected to MT5")
            return None
        
        # Get symbol info
        symbol_info = self.get_symbol_info(symbol)
        if symbol_info is None:
            return None
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        
        price = tick.ask
        point = symbol_info.point
        
        # Calculate SL and TP
        sl = price - sl_points * point
        tp = price + tp_points * point
        
        # Normalize prices
        sl = mt5.symbol_info_tick(symbol).bid - sl_points * point
        tp = mt5.symbol_info_tick(symbol).bid + tp_points * point
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 10,
            "magic": 123456,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed. Retcode: {result.retcode}, Comment: {result.comment}")
            return None
        
        logger.info(f"Buy order placed successfully. Ticket: {result.order}, Price: {result.price}")
        return result
    
    def place_sell_order(self, symbol, lot, sl_points=50, tp_points=100, comment="Python EA"):
        """
        Place a sell order
        
        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            lot: Lot size
            sl_points: Stop loss in points
            tp_points: Take profit in points
            comment: Order comment
        """
        if not self.connected:
            logger.error("Not connected to MT5")
            return None
        
        # Get symbol info
        symbol_info = self.get_symbol_info(symbol)
        if symbol_info is None:
            return None
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        
        price = tick.bid
        point = symbol_info.point
        
        # Calculate SL and TP
        sl = price + sl_points * point
        tp = price - tp_points * point
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 10,
            "magic": 123456,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed. Retcode: {result.retcode}, Comment: {result.comment}")
            return None
        
        logger.info(f"Sell order placed successfully. Ticket: {result.order}, Price: {result.price}")
        return result
    
    def get_positions(self, symbol=None):
        """Get open positions"""
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        
        if positions is None:
            logger.error("No positions found or error occurred")
            return []
        
        return positions
    
    def close_position(self, ticket):
        """Close a position by ticket"""
        position = mt5.positions_get(ticket=ticket)
        if position is None or len(position) == 0:
            logger.error(f"Position {ticket} not found")
            return None
        
        pos = position[0]
        symbol = pos.symbol
        lot = pos.volume
        order_type = pos.type
        
        if order_type == mt5.ORDER_TYPE_BUY:
            price = mt5.symbol_info_tick(symbol).bid
            type_order = mt5.ORDER_TYPE_SELL
        else:
            price = mt5.symbol_info_tick(symbol).ask
            type_order = mt5.ORDER_TYPE_BUY
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": type_order,
            "position": ticket,
            "price": price,
            "deviation": 10,
            "magic": 123456,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Close position failed. Retcode: {result.retcode}")
            return None
        
        logger.info(f"Position {ticket} closed successfully")
        return result


# Example usage
if __name__ == "__main__":
    # WARNING: Replace with your actual credentials
    # NEVER commit real credentials to version control
    
    TRADER = MT5Trader(
        login=12345678,  # Replace with your account number
        password="your_password_here",  # Replace with your password
        server="Exness-MT5"  # Replace with your server name
    )
    
    try:
        # Connect
        if not TRADER.connect():
            exit(1)
        
        # Get current price
        symbol = "EURUSD"
        price_info = TRADER.get_current_price(symbol)
        if price_info:
            logger.info(f"Current {symbol} price - Ask: {price_info['ask']}, Bid: {price_info['bid']}")
        
        # Example: Place a buy order (commented out for safety)
        # result = TRADER.place_buy_order(symbol="EURUSD", lot=0.01, sl_points=50, tp_points=100)
        
        # Check positions
        positions = TRADER.get_positions()
        logger.info(f"Open positions: {len(positions)}")
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        TRADER.disconnect()

