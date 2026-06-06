"""
Follower Bot — runs on Baiastan's computer
============================================
Reads trade signals from Firebase and copies them to your Webull account.

DRY_RUN = True  → just logs what it would do, NO real orders placed (safe for testing)
DRY_RUN = False → places real orders on your Webull account

HOW TO RUN:
  python follower_bot.py

REQUIRES:
  - step1_auth.py must have been run on this machine (token in conf/token.txt)
  - firebase_credentials.json in this folder
  - pip install firebase-admin webull-openapi-python-sdk
"""

import time
import json
import logging
from datetime import datetime, timezone, timedelta
from webull.core.client import ApiClient
from webull.trade.trade_client import TradeClient
from config import (APP_KEY, APP_SECRET, ACCOUNT_IDS, DEFAULT_ACCOUNT_ID,
                    FIREBASE_DATABASE_URL, FIREBASE_CREDENTIALS_PATH,
                    SIZE_MULTIPLIER, POLL_INTERVAL, SIGNAL_MAX_AGE_SECONDS)

# ── CONFIG ───────────────────────────────────────────────────────────────────
DRY_RUN = True   # Set to False to place real orders

FIREBASE_CREDENTIALS = FIREBASE_CREDENTIALS_PATH

SIZE_MULTIPLIER = 1.0     # copy same size as leader; set 0.5 to copy half
MAX_SIGNAL_AGE_SECONDS = 60   # ignore signals older than this many seconds
POLL_INTERVAL = 5         # seconds between Firebase checks
# ────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)


# ── Firebase ─────────────────────────────────────────────────────────────────

def init_firebase():
    import firebase_admin
    from firebase_admin import credentials, db as fdb
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS)
        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DATABASE_URL})
    log.info("Firebase connected.")


def get_pending_signals(max_age_seconds: int = MAX_SIGNAL_AGE_SECONDS) -> list:
    from firebase_admin import db as fdb
    ref = fdb.reference('copy_trading/signals')
    data = ref.get() or {}
    pending = []
    now = datetime.now(timezone.utc)
    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        if val.get('processed', False):
            continue
        if val.get('_test', False):
            fdb.reference(f'copy_trading/signals/{key}/processed').set(True)
            continue
        ts = val.get('timestamp', '')
        if ts:
            try:
                sig_time = datetime.fromisoformat(ts)
                age = (now - sig_time).total_seconds()
                if age > max_age_seconds:
                    log.warning(f"Signal {key} is {age:.0f}s old — skipping (too stale)")
                    fdb.reference(f'copy_trading/signals/{key}/processed').set(True)
                    fdb.reference(f'copy_trading/signals/{key}/follower_status').set('skipped: stale')
                    continue
            except Exception:
                pass
        val['_key'] = key
        pending.append(val)
    pending.sort(key=lambda x: x.get('timestamp', ''))
    return pending


def mark_processed(key: str, status: str = 'ok'):
    from firebase_admin import db as fdb
    fdb.reference(f'copy_trading/signals/{key}/processed').set(True)
    fdb.reference(f'copy_trading/signals/{key}/follower_status').set(status)


def update_follower_heartbeat():
    try:
        from firebase_admin import db as fdb
        fdb.reference('copy_trading/status/follower_heartbeat').set(
            datetime.now(timezone.utc).isoformat()
        )
    except Exception:
        pass


# ── Order placement ───────────────────────────────────────────────────────────

def execute_signal(trade_client: TradeClient, signal: dict,
                   size_mult: float = SIZE_MULTIPLIER, spread_buf: float = 0.05):
    """Execute a copy-trade signal. In DRY_RUN mode, just logs the action."""
    key = signal.get('_key', 'unknown')
    event_type = signal.get('event_type', '')
    ticker = signal.get('ticker', '')
    action = signal.get('action', '')
    is_option = signal.get('is_option', False)
    qty = int(signal.get('qty', 1))
    price = float(signal.get('price', 0))

    adjusted_qty = max(1, round(qty * size_mult))
    # Apply spread buffer: pay a little more on buys, accept a little less on sells
    adjusted_price = price + spread_buf if action == 'BUY' else price - spread_buf

    if is_option:
        strike = signal.get('strike', 0)
        expiry = signal.get('expiry', '')
        option_type = signal.get('option_type', '')
        desc = f"{ticker} {option_type} ${strike} exp {expiry}"
    else:
        desc = ticker

    log.info(f"--- Signal received: {event_type} {action} {adjusted_qty}x {desc} @ ~${adjusted_price:.2f} (buf +${spread_buf}) ---")

    if DRY_RUN:
        log.info(f"[DRY RUN] Would place order: {action} {adjusted_qty} {desc} @ ${adjusted_price:.2f}")
        log.info(f"[DRY RUN] Account: {DEFAULT_ACCOUNT_ID}")
        mark_processed(key, 'ok (dry run)')
        return

    # Real order placement
    try:
        import uuid
        client_order_id = str(uuid.uuid4()).replace('-', '')[:32]

        if not is_option:
            # Stock order
            from webull.trade.common.order_side import OrderSide
            from webull.trade.common.order_type import OrderType
            from webull.trade.common.time_in_force import TimeInForce

            side = OrderSide.BUY if action == 'BUY' else OrderSide.SELL

            # Get current price for limit order
            # Using a market order as fallback
            res = trade_client.order.place_order(
                account_id=DEFAULT_ACCOUNT_ID,
                qty=adjusted_qty,
                instrument_id=signal.get('instrument_id', ''),
                side=side,
                client_order_id=client_order_id,
                order_type=OrderType.MARKET,
                extended_hours_trading=False,
                tif=TimeInForce.DAY,
            )
            log.info(f"Stock order placed: {res.json()}")
            mark_processed(key, 'ok')
        else:
            # Options — log a warning since US options API is limited
            log.warning("Options order placement via API is limited for US accounts.")
            log.warning(f"Manually place: {action} {adjusted_qty}x {desc}")
            mark_processed(key, 'manual: options not auto-traded')

    except Exception as e:
        log.error(f"Order placement failed: {e}")
        mark_processed(key, f'error: {e}')


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print(f"Follower Bot — {'DRY RUN (no real orders)' if DRY_RUN else 'LIVE MODE'}")
    print("=" * 55)
    print()

    if 'YOUR-PROJECT' in FIREBASE_DATABASE_URL:
        print("ERROR: Set FIREBASE_DATABASE_URL at the top of this file.")
        return

    # Connect Webull
    log.info("Connecting to Webull...")
    api_client = ApiClient(APP_KEY, APP_SECRET, 'us')
    api_client.add_endpoint('us', 'api.webull.com')
    trade_client = TradeClient(api_client)

    try:
        res = trade_client.account_v2.get_account_list()
        data = res.json()
        # API returns a plain list or a dict with 'data' key
        accounts = data if isinstance(data, list) else data.get('data', [])
        if not accounts:
            print("ERROR: No accounts found. Run step1_auth.py first.")
            return
        log.info("Webull connected.")
        for acc in accounts:
            acc_id = acc.get('accountId') or acc.get('account_id', '')
            acc_type = acc.get('accountType') or acc.get('account_type', '')
            log.info(f"  Account: {acc_id} ({acc_type})")
    except Exception as e:
        print(f"ERROR connecting to Webull: {e}")
        return

    # Connect Firebase
    try:
        init_firebase()
    except Exception as e:
        print(f"ERROR connecting to Firebase: {e}")
        print("Run python test_firebase.py first to diagnose.")
        return

    log.info(f"Polling Firebase every {POLL_INTERVAL}s. Press Ctrl+C to stop.")
    if DRY_RUN:
        log.info("DRY RUN is ON — no real orders will be placed.")
    print()

    while True:
        try:
            update_follower_heartbeat()

            # Read live settings from Firebase (dashboard controls these)
            from firebase_admin import db as fdb
            live = fdb.reference('copy_trading/status').get() or {}
            copy_enabled = live.get('copy_enabled', True)
            size_mult = float(live.get('size_multiplier', SIZE_MULTIPLIER))
            spread_buf = float(live.get('spread_buffer', 0.05))
            max_age = int(live.get('max_signal_age', MAX_SIGNAL_AGE_SECONDS))

            if not copy_enabled:
                log.info("Copy trading DISABLED via dashboard — skipping.")
                time.sleep(POLL_INTERVAL)
                continue

            pending = get_pending_signals(max_age_seconds=max_age)

            if pending:
                log.info(f"{len(pending)} pending signal(s) found.")
                for signal in pending:
                    execute_signal(trade_client, signal, size_mult, spread_buf)
            else:
                log.debug("No pending signals.")

        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception as e:
            log.error(f"Error in main loop: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()
