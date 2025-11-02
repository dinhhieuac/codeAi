"""
Telegram Trade Copy Bot
Receives trading signals from Telegram and executes them on MT5
"""

import MetaTrader5 as mt5
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging
import re
from typing import Optional

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class TelegramTradeCopyBot:
    """Bot for copying trades from Telegram signals to MT5"""
    
    def __init__(self, telegram_token: str, mt5_login: int, mt5_password: str, mt5_server: str):
        """
        Initialize the bot
        
        Args:
            telegram_token: Telegram bot token from @BotFather
            mt5_login: MT5 account login
            mt5_password: MT5 account password
            mt5_server: MT5 server name
        """
        self.telegram_token = telegram_token
        self.mt5_login = mt5_login
        self.mt5_password = mt5_password
        self.mt5_server = mt5_server
        self.mt5_connected = False
        self.lot_multiplier = 1.0  # Scale lot size (e.g., 0.5 = half the master lot)
        self.max_lot = 10.0  # Maximum lot size for safety
        
    def connect_mt5(self):
        """Connect to MT5 terminal"""
        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            return False
        
        if not mt5.login(login=self.mt5_login, password=self.mt5_password, server=self.mt5_server):
            logger.error(f"MT5 login failed: {mt5.last_error()}")
            mt5.shutdown()
            return False
        
        self.mt5_connected = True
        account_info = mt5.account_info()
        logger.info(f"Connected to MT5. Account: {account_info.login}, Balance: {account_info.balance}")
        return True
    
    def disconnect_mt5(self):
        """Disconnect from MT5"""
        mt5.shutdown()
        self.mt5_connected = False
        logger.info("Disconnected from MT5")
    
    def parse_signal(self, message_text: str) -> Optional[dict]:
        """
        Parse trading signal from message
        Supported formats:
        - "BUY EURUSD 0.01 SL=50 TP=100"
        - "SELL GBPUSD 0.1 SL=30 TP=60"
        - "BUY EURUSD 0.01"
        """
        # Remove extra whitespace and convert to uppercase
        text = ' '.join(message_text.upper().split())
        
        # Pattern matching
        pattern = r'(BUY|SELL)\s+([A-Z]{6})\s+([\d.]+)(?:\s+SL=(\d+))?(?:\s+TP=(\d+))?'
        match = re.match(pattern, text)
        
        if not match:
            return None
        
        order_type = match.group(1)  # BUY or SELL
        symbol = match.group(2)  # e.g., EURUSD
        lot = float(match.group(3))  # Lot size
        sl_points = int(match.group(4)) if match.group(4) else 50  # Default SL
        tp_points = int(match.group(5)) if match.group(5) else 100  # Default TP
        
        # Apply lot multiplier and cap max lot
        lot = min(lot * self.lot_multiplier, self.max_lot)
        
        return {
            'type': order_type,
            'symbol': symbol,
            'lot': lot,
            'sl_points': sl_points,
            'tp_points': tp_points
        }
    
    def execute_signal(self, signal: dict) -> bool:
        """Execute trading signal on MT5"""
        if not self.mt5_connected:
            logger.error("MT5 not connected")
            return False
        
        symbol = signal['symbol']
        lot = signal['lot']
        sl_points = signal['sl_points']
        tp_points = signal['tp_points']
        
        # Check if symbol exists
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"Symbol {symbol} not found")
            return False
        
        # Check if symbol is enabled
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                logger.error(f"Failed to enable symbol {symbol}")
                return False
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Failed to get tick for {symbol}")
            return False
        
        point = symbol_info.point
        order_type_str = signal['type']
        
        if order_type_str == 'BUY':
            price = tick.ask
            order_type = mt5.ORDER_TYPE_BUY
            sl = price - sl_points * point
            tp = price + tp_points * point
        else:  # SELL
            price = tick.bid
            order_type = mt5.ORDER_TYPE_SELL
            sl = price + sl_points * point
            tp = price - tp_points * point
        
        # Check margin
        check_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "deviation": 10,
            "magic": 123456,
            "comment": "Telegram Copy",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_check(check_request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order check failed: {result.comment}")
            return False
        
        # Send order
        request = {
            **check_request,
            "sl": sl,
            "tp": tp,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed. Retcode: {result.retcode}, Comment: {result.comment}")
            return False
        
        logger.info(f"Order executed: {order_type_str} {symbol} {lot} lots at {price}")
        return True
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "🤖 Trade Copy Bot started!\n\n"
            "Send trading signals in format:\n"
            "BUY EURUSD 0.01 SL=50 TP=100\n"
            "SELL GBPUSD 0.1 SL=30 TP=60\n\n"
            "Commands:\n"
            "/start - Start bot\n"
            "/status - Check MT5 connection\n"
            "/positions - Show open positions"
        )
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if self.mt5_connected:
            account_info = mt5.account_info()
            balance = account_info.balance
            equity = account_info.equity
            await update.message.reply_text(
                f"✅ MT5 Connected\n"
                f"Account: {account_info.login}\n"
                f"Balance: {balance:.2f}\n"
                f"Equity: {equity:.2f}"
            )
        else:
            await update.message.reply_text("❌ MT5 Not Connected")
    
    async def positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command"""
        if not self.mt5_connected:
            await update.message.reply_text("❌ MT5 Not Connected")
            return
        
        positions = mt5.positions_get()
        if positions is None or len(positions) == 0:
            await update.message.reply_text("No open positions")
            return
        
        message = f"Open Positions: {len(positions)}\n\n"
        for pos in positions:
            message += (
                f"{pos.type_string} {pos.symbol} {pos.volume} lots\n"
                f"Price: {pos.price_open}, Profit: {pos.profit:.2f}\n\n"
            )
        
        await update.message.reply_text(message)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle trading signal messages"""
        message_text = update.message.text.strip()
        
        # Try to parse as trading signal
        signal = self.parse_signal(message_text)
        
        if signal is None:
            await update.message.reply_text(
                "❌ Invalid signal format.\n\n"
                "Use: BUY/SELL SYMBOL LOT [SL=points] [TP=points]\n"
                "Example: BUY EURUSD 0.01 SL=50 TP=100"
            )
            return
        
        if not self.mt5_connected:
            await update.message.reply_text("❌ MT5 Not Connected. Cannot execute trade.")
            return
        
        # Execute signal
        success = self.execute_signal(signal)
        
        if success:
            await update.message.reply_text(
                f"✅ Signal executed:\n"
                f"{signal['type']} {signal['symbol']} {signal['lot']} lots\n"
                f"SL: {signal['sl_points']} points, TP: {signal['tp_points']} points"
            )
        else:
            await update.message.reply_text("❌ Failed to execute signal. Check logs for details.")
    
    def run(self):
        """Start the bot"""
        # Connect to MT5
        if not self.connect_mt5():
            logger.error("Failed to connect to MT5. Bot will not start.")
            return
        
        # Create Telegram application
        application = Application.builder().token(self.telegram_token).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("status", self.status))
        application.add_handler(CommandHandler("positions", self.positions))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Start bot
        logger.info("Telegram bot started")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


# Example usage
if __name__ == "__main__":
    # WARNING: Replace with your actual credentials
    # NEVER commit real credentials to version control
    
    BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # Get from @BotFather
    MT5_LOGIN = 12345678  # Your MT5 account number
    MT5_PASSWORD = "your_password"  # Your MT5 password
    MT5_SERVER = "Exness-MT5"  # Your MT5 server
    
    bot = TelegramTradeCopyBot(
        telegram_token=BOT_TOKEN,
        mt5_login=MT5_LOGIN,
        mt5_password=MT5_PASSWORD,
        mt5_server=MT5_SERVER
    )
    
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        bot.disconnect_mt5()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        bot.disconnect_mt5()

