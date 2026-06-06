"""Shared helpers for all test scripts."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime, timezone
from config import FIREBASE_DATABASE_URL, FIREBASE_CREDENTIALS_PATH

# ── A fake SPY CALL option used across all tests ──────────────────────────────
TEST_OPTION = {
    'symbol':             'SPY',
    'ticker':             'SPY',
    'option_type':        'CALL',
    'strike_price':       '560.00',
    'option_expire_date': '2026-06-20',
    'instrument_id':      'TEST_INSTRUMENT_001',
    'instrument_type':    'OPTION',
}

def init():
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DATABASE_URL})

def push(signal: dict) -> str:
    signal['timestamp'] = datetime.now(timezone.utc).isoformat()
    signal['processed'] = False
    ref = db.reference('copy_trading/signals')
    key = ref.push(signal).key
    print(f"  → Signal pushed: {key}")
    return key

def wait_for_processed(key: str, timeout: int = 10):
    import time
    print(f"  → Waiting for follower to process {key}...")
    for i in range(timeout):
        time.sleep(1)
        val = db.reference(f'copy_trading/signals/{key}').get() or {}
        if val.get('processed'):
            status = val.get('follower_status', '?')
            print(f"  ✓ Processed in {i+1}s — status: {status}")
            return status
    print(f"  ✗ Not processed within {timeout}s — is follower_bot running?")
    return None

def section(title: str):
    print()
    print("=" * 50)
    print(f"  {title}")
    print("=" * 50)
