import os
from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
ALPACA_DATA_URL = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./trader.db")

# Paper trading by default
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
