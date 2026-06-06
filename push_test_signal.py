"""
Pushes a REAL test signal that follower_bot.py will actually process.
Use this to verify the follower bot reacts correctly (in DRY_RUN mode it just logs).

  python push_test_signal.py
"""

import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime, timezone
from config import FIREBASE_DATABASE_URL, FIREBASE_CREDENTIALS_PATH

FIREBASE_CREDENTIALS = FIREBASE_CREDENTIALS_PATH

cred = credentials.Certificate(FIREBASE_CREDENTIALS)
firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DATABASE_URL})

signal = {
    'event_type': 'OPEN',
    'is_option': True,
    'ticker': 'SPY',
    'action': 'BUY',
    'qty': 2,
    'price': 5.50,
    'option_type': 'CALL',
    'strike': 560.0,
    'expiry': '2026-06-20',
    'instrument_id': 'TEST123',
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'processed': False,
}

ref = db.reference('copy_trading/signals')
new_ref = ref.push(signal)
print(f"Signal pushed: {new_ref.key}")
print("Watch your follower_bot terminal — it should log this within 5 seconds.")
