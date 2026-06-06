"""
STEP 3 - Leader Bot (runs on YOUR friend's computer)
======================================================
Run this AFTER step1_auth.py and step2_test.py succeed.

BEFORE running:
  1. Install Firebase: pip install firebase-admin
  2. Get the Firebase credentials JSON file from Baiastan (the follower)
     and save it as:  firebase_credentials.json  (in this same folder)
  3. Ask Baiastan for the Firebase database URL and paste it below

HOW TO RUN:
  python step3_leader_bot.py

WHAT THIS DOES:
  - Watches your Webull positions every few seconds
  - When you open or close a position, it sends a signal to Firebase
  - The follower bot on Baiastan's computer reads those signals and copies your trade
  - Runs continuously until you press Ctrl+C to stop
"""

import time
import json
import logging
from webull.core.client import ApiClient
from webull.trade.trade_client import TradeClient
from config import APP_KEY, APP_SECRET, ACCOUNT_IDS, FIREBASE_DATABASE_URL, FIREBASE_CREDENTIALS_PATH, POLL_INTERVAL

FIREBASE_CREDENTIALS = FIREBASE_CREDENTIALS_PATH

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)

APP_KEY = 'c2fd9793a4855fa9d07f461896cefc8f'
APP_SECRET = '2dfe5e2c804317231c7410d7d8db0e0c'


def extract_positions(raw_data: dict) -> dict:
    """Return {instrument_id: holding_dict} from API response."""
    holdings = raw_data.get('holdings', [])
    return {h['instrument_id']: h for h in holdings if 'instrument_id' in h}


def make_signal_from_position(pos: dict, event_type: str) -> dict:
    """Convert a Webull holding dict into a relay signal."""
    symbol = pos.get('symbol', 'UNKNOWN')
    is_option = pos.get('instrument_type', '').upper() == 'OPTION'

    try:
        qty = abs(int(float(str(pos.get('qty', 1)))))
    except (ValueError, TypeError):
        qty = 1

    try:
        price = float(str(pos.get('last_price', 0)))
    except (ValueError, TypeError):
        price = 0.0

    signal = {
        'event_type': event_type,
        'is_option': is_option,
        'ticker': symbol,
        'action': 'BUY' if event_type == 'OPEN' else 'SELL',
        'qty': qty,
        'price': price,
        'instrument_id': pos.get('instrument_id', ''),
    }
    return signal


def init_firebase():
    try:
        import firebase_admin
        from firebase_admin import credentials, db as fdb
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_CREDENTIALS)
            firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DATABASE_URL})
        log.info("Firebase connected.")
        return True
    except Exception as e:
        log.error(f"Firebase init failed: {e}")
        log.error("Make sure firebase_credentials.json exists and FIREBASE_DATABASE_URL is set correctly.")
        return False


def push_signal(signal: dict):
    from firebase_admin import db as fdb
    from datetime import datetime, timezone
    signal['timestamp'] = datetime.now(timezone.utc).isoformat()
    signal['processed'] = False
    ref = fdb.reference('copy_trading/signals')
    new_ref = ref.push(signal)
    log.info(f"Signal pushed to Firebase: {json.dumps(signal)}")
    return new_ref.key


def update_heartbeat():
    try:
        from firebase_admin import db as fdb
        from datetime import datetime, timezone
        fdb.reference('copy_trading/status/leader_heartbeat').set(
            datetime.now(timezone.utc).isoformat()
        )
    except Exception:
        pass


def fetch_all_positions(trade_client: TradeClient) -> dict:
    """Fetch positions across all accounts. Returns {position_key: position_dict}."""
    all_positions = {}
    for acc_id in ACCOUNT_IDS:
        try:
            res = trade_client.account.get_account_position(acc_id, page_size=100)
            data = res.json()
            positions = extract_positions(data)
            all_positions.update(positions)
        except Exception as e:
            log.warning(f"Could not fetch positions for {acc_id}: {e}")
    return all_positions


def main():
    print("=" * 55)
    print("STEP 3: Leader Bot - Starting")
    print("=" * 55)
    print()

    # Check Firebase config
    if 'YOUR-PROJECT' in FIREBASE_DATABASE_URL:
        print("ERROR: You need to set FIREBASE_DATABASE_URL at the top of this file.")
        print("Ask Baiastan for the Firebase database URL.")
        return

    # Connect to Webull
    log.info("Connecting to Webull...")
    api_client = ApiClient(APP_KEY, APP_SECRET, 'us')
    api_client.add_endpoint('us', 'api.webull.com')
    trade_client = TradeClient(api_client)

    # Test Webull connection
    try:
        res = trade_client.account_v2.get_account_list()
        data = res.json()
        accounts = data if isinstance(data, list) else data.get('data', [])
        if not accounts:
            print("ERROR: Could not get account list. Run step1_auth.py first.")
            return
        log.info(f"Webull connected. Watching {len(ACCOUNT_IDS)} account(s).")
    except Exception as e:
        print(f"ERROR connecting to Webull: {e}")
        print("Make sure you ran step1_auth.py first.")
        return

    # Connect to Firebase
    if not init_firebase():
        return

    log.info(f"Polling every {POLL_INTERVAL} seconds. Press Ctrl+C to stop.")
    print()

    previous_positions = {}
    first_run = True

    while True:
        try:
            current_positions = fetch_all_positions(trade_client)
            update_heartbeat()

            if first_run:
                log.info(f"Initial snapshot: {len(current_positions)} open position(s).")
                for key in current_positions:
                    log.info(f"  Existing position: {key}")
                first_run = False
                previous_positions = current_positions
                time.sleep(POLL_INTERVAL)
                continue

            # Detect new positions (OPEN)
            for key, pos in current_positions.items():
                if key not in previous_positions:
                    log.info(f"NEW POSITION DETECTED: {key}")
                    signal = make_signal_from_position(pos, 'OPEN')
                    push_signal(signal)

            # Detect closed positions (CLOSE)
            for key, pos in previous_positions.items():
                if key not in current_positions:
                    log.info(f"POSITION CLOSED: {key}")
                    signal = make_signal_from_position(pos, 'CLOSE')
                    push_signal(signal)

            previous_positions = current_positions

        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception as e:
            log.error(f"Unexpected error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()
