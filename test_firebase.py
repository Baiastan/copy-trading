"""
Firebase Relay Test
====================
Tests that Firebase is working end-to-end:
  1. Pushes a fake test signal (pretends leader opened a trade)
  2. Reads it back (pretends follower received it)
  3. Marks it as processed
  4. Confirms everything worked

No Webull connection needed — pure Firebase test.

HOW TO RUN:
  python test_firebase.py

REQUIRES:
  - firebase_credentials.json in this folder
  - pip install firebase-admin
"""

import json
import time
from config import FIREBASE_DATABASE_URL, FIREBASE_CREDENTIALS_PATH
FIREBASE_CREDENTIALS = FIREBASE_CREDENTIALS_PATH
# ────────────────────────────────────────────────────────────────────────────

print("=" * 50)
print("Firebase Relay Test")
print("=" * 50)
print()

if not FIREBASE_DATABASE_URL:
    print("ERROR: Set FIREBASE_DATABASE_URL in your .env file.")
    exit(1)

# Init Firebase
try:
    import firebase_admin
    from firebase_admin import credentials, db
    cred = credentials.Certificate(FIREBASE_CREDENTIALS)
    firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DATABASE_URL})
    print("✓ Firebase connected")
except Exception as e:
    print(f"✗ Firebase connection failed: {e}")
    print()
    print("Make sure:")
    print("  1. firebase_credentials.json exists in this folder")
    print("  2. FIREBASE_DATABASE_URL is correct")
    print("  3. pip install firebase-admin")
    exit(1)

# Push a fake test signal
from datetime import datetime, timezone

fake_signal = {
    'event_type': 'OPEN',
    'is_option': False,
    'ticker': 'SPY',
    'action': 'BUY',
    'qty': 5,
    'price': 550.25,
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'processed': False,
    '_test': True,   # mark as test so follower bot can ignore it
}

print()
print("Pushing test signal...")
ref = db.reference('copy_trading/signals')
new_ref = ref.push(fake_signal)
signal_key = new_ref.key
print(f"✓ Signal pushed with key: {signal_key}")
print(f"  Signal: {json.dumps(fake_signal, indent=4)}")

# Wait a moment then read it back
time.sleep(1)

print()
print("Reading signal back from Firebase...")
data = db.reference(f'copy_trading/signals/{signal_key}').get()
if data:
    print(f"✓ Signal received:")
    print(f"  {json.dumps(data, indent=4)}")
else:
    print("✗ Could not read signal back — check Firebase rules (read/write allowed?)")
    exit(1)

# Mark as processed
db.reference(f'copy_trading/signals/{signal_key}/processed').set(True)
db.reference(f'copy_trading/signals/{signal_key}/follower_status').set('ok (test)')
print()
print("✓ Marked signal as processed")

# Write leader heartbeat
db.reference('copy_trading/status/leader_heartbeat').set(datetime.now(timezone.utc).isoformat())
db.reference('copy_trading/status/follower_heartbeat').set(datetime.now(timezone.utc).isoformat())
print("✓ Heartbeats written")

print()
print("=" * 50)
print("ALL TESTS PASSED — Firebase relay is working!")
print("You can now run: python follower_bot.py")
print("=" * 50)
