import os
from dotenv import load_dotenv

load_dotenv()

# Webull developer API credentials (from developer.webull.com)
APP_KEY = os.getenv("WEBULL_APP_KEY", "")
APP_SECRET = os.getenv("WEBULL_APP_SECRET", "")

# Webull account IDs (run step2_test.py to find yours)
_account_ids_raw = os.getenv("WEBULL_ACCOUNT_IDS", "")
ACCOUNT_IDS = [a.strip() for a in _account_ids_raw.split(",") if a.strip()]
DEFAULT_ACCOUNT_ID = os.getenv("WEBULL_DEFAULT_ACCOUNT_ID", ACCOUNT_IDS[0] if ACCOUNT_IDS else "")

# Firebase relay
FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase_credentials.json")

# Copy behaviour
SIZE_MULTIPLIER = float(os.getenv("SIZE_MULTIPLIER", "1.0"))
MAX_POSITION_VALUE = float(os.getenv("MAX_POSITION_VALUE", "5000"))
COPY_OPTIONS = os.getenv("COPY_OPTIONS", "true").lower() == "true"
COPY_STOCKS = os.getenv("COPY_STOCKS", "true").lower() == "true"

# Timing
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
SIGNAL_MAX_AGE_SECONDS = int(os.getenv("SIGNAL_MAX_AGE_SECONDS", "60"))
