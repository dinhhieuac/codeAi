"""
Configuration file example
Copy this to config.py and fill in your actual credentials
NEVER commit config.py to version control!
"""

# MT5 Connection Settings
MT5_LOGIN = 272736909  # Your MT5 account number
MT5_PASSWORD = "@Dinhhieu273"  # Your MT5 password
MT5_SERVER = "Exness-MT5"  # Your MT5 server name

# Telegram Bot Settings (for trade copy)
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # Get from @BotFather
TELEGRAM_CHAT_ID = None  # Optional: specific chat ID to listen to

# Trading Settings
DEFAULT_LOT_SIZE = 0.01
DEFAULT_SL_POINTS = 50
DEFAULT_TP_POINTS = 100
MAGIC_NUMBER = 123456  # For EA identification

# Risk Management
MAX_LOT_SIZE = 10.0
MAX_DAILY_LOSS = 500.0  # Maximum daily loss in account currency
MAX_DRAWDOWN_PERCENT = 20.0  # Maximum drawdown percentage

# Lot Multiplier (for trade copy)
LOT_MULTIPLIER = 1.0  # Scale master lot size (1.0 = same, 0.5 = half)

# ML Trading Settings
ML_MODEL_PATH = "models/trading_model.pkl"
ML_CONFIDENCE_THRESHOLD = 0.6  # Minimum confidence to execute trade

# Logging
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FILE = "logs/trading_bot.log"

# API Settings
RETRY_ATTEMPTS = 3
RETRY_DELAY = 1  # seconds

