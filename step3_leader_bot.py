"""
STEP 3 - Leader Bot (runs on YOUR friend's computer)
======================================================
Run this AFTER step1_auth.py and step2_test.py succeed.

BEFORE running:
  1. Install Firebase: pip install firebase-admin
  2. Get the Firebase credentials JSON file from Baiastan (the follower)
     and save it as:  firebase_credentials.json  (in this same folder)
  3. Copy .env.example to .env and fill in your credentials

HOW TO RUN:
  python step3_leader_bot.py

WHAT THIS DOES:
  - Watches your Webull positions AND open orders every second
  - New position    → signals follower to BUY
  - Closed position → signals follower to SELL (market close)
  - New open order (stop loss / take profit) → signals follower to place same order
  - Cancelled order → signals follower to cancel their matching order
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


# ── Position helpers ──────────────────────────────────────────────────────────

def extract_positions(raw_data: dict) -> dict:
    """Return {instrument_id: holding_dict} from API response."""
    holdings = raw_data.get('holdings', [])
    return {h['instrument_id']: h for h in holdings if 'instrument_id' in h}


def make_signal_from_position(pos: dict, event_type: str) -> dict:
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
    return {
        'event_type': event_type,       # 'OPEN' or 'CLOSE'
        'is_option': is_option,
        'ticker': symbol,
        'action': 'BUY' if event_type == 'OPEN' else 'SELL',
        'qty': qty,
        'price': price,
        'instrument_id': pos.get('instrument_id', ''),
    }


# ── Open order helpers ────────────────────────────────────────────────────────

def extract_open_orders(raw_data: dict) -> dict:
    """Return {client_order_id: order_dict} from list_open_orders response."""
    orders = {}
    items = raw_data.get('orders', raw_data.get('data', raw_data.get('items', [])))
    if isinstance(items, dict):
        items = items.get('items', [])
    if not isinstance(items, list):
        return orders
    for order in items:
        oid = order.get('clientOrderId') or order.get('client_order_id', '')
        if oid:
            orders[oid] = order
    return orders


def make_signal_from_order(order: dict, event_type: str) -> dict:
    """Build a PLACE_ORDER or CANCEL_ORDER signal from a Webull open order."""
    ticker = order.get('ticker', {}) or {}
    if not isinstance(ticker, dict):
        ticker = {}

    symbol       = ticker.get('symbol') or order.get('symbol', '')
    option_type  = ticker.get('optionType') or order.get('optionType') or order.get('option_type', '')
    strike       = ticker.get('strikePrice') or order.get('strikePrice') or order.get('strike_price', '')
    expiry       = ticker.get('expireDate') or order.get('expireDate') or order.get('option_expire_date', '')
    order_type   = order.get('orderType') or order.get('order_type', '')
    side         = order.get('side') or order.get('orderSide', '')
    tif          = order.get('timeInForce') or order.get('time_in_force', 'DAY')
    client_oid   = order.get('clientOrderId') or order.get('client_order_id', '')

    try:
        qty = abs(int(float(str(order.get('quantity') or order.get('qty', 1)))))
    except (ValueError, TypeError):
        qty = 1

    def to_float(val):
        try:
            return float(str(val)) if val is not None else None
        except (ValueError, TypeError):
            return None

    limit_price = to_float(order.get('limitPrice') or order.get('limit_price'))
    stop_price  = to_float(order.get('stopPrice') or order.get('stop_price'))

    signal = {
        'event_type':            event_type,   # 'PLACE_ORDER' or 'CANCEL_ORDER'
        'leader_client_order_id': client_oid,
        'order_type':            order_type,
        'side':                  side,
        'qty':                   qty,
        'symbol':                symbol,
        'option_type':           option_type,
        'strike_price':          str(strike),
        'option_expire_date':    str(expiry),
        'time_in_force':         tif,
        '_raw_order':            order,         # full raw for debugging
    }
    if limit_price is not None:
        signal['limit_price'] = limit_price
    if stop_price is not None:
        signal['stop_price'] = stop_price
    return signal


# ── Firebase ──────────────────────────────────────────────────────────────────

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
        return False


def push_signal(signal: dict):
    from firebase_admin import db as fdb
    from datetime import datetime, timezone
    signal['timestamp'] = datetime.now(timezone.utc).isoformat()
    signal['processed'] = False
    ref = fdb.reference('copy_trading/signals')
    new_ref = ref.push(signal)
    log.info(f"Signal pushed: {json.dumps({k: v for k, v in signal.items() if k != '_raw_order'})}")
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


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_all_positions(trade_client: TradeClient) -> dict:
    all_positions = {}
    for acc_id in ACCOUNT_IDS:
        try:
            res = trade_client.account.get_account_position(acc_id, page_size=100)
            all_positions.update(extract_positions(res.json()))
        except Exception as e:
            log.warning(f"Could not fetch positions for {acc_id}: {e}")
    return all_positions


def fetch_all_open_orders(trade_client: TradeClient) -> dict:
    all_orders = {}
    for acc_id in ACCOUNT_IDS:
        try:
            res = trade_client.order.list_open_orders(acc_id, page_size=100)
            data = res.json()
            orders = extract_open_orders(data)
            if orders:
                all_orders.update(orders)
        except Exception as e:
            log.warning(f"Could not fetch open orders for {acc_id}: {e}")
    return all_orders


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("STEP 3: Leader Bot - Starting")
    print("=" * 55)
    print()

    if not FIREBASE_DATABASE_URL:
        print("ERROR: Set FIREBASE_DATABASE_URL in your .env file.")
        return

    log.info("Connecting to Webull...")
    api_client = ApiClient(APP_KEY, APP_SECRET, 'us')
    api_client.add_endpoint('us', 'api.webull.com')
    trade_client = TradeClient(api_client)

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
        return

    if not init_firebase():
        return

    log.info(f"Polling every {POLL_INTERVAL}s. Press Ctrl+C to stop.")
    print()

    prev_positions = {}
    prev_orders = {}
    first_run = True

    while True:
        try:
            cur_positions = fetch_all_positions(trade_client)
            cur_orders    = fetch_all_open_orders(trade_client)
            update_heartbeat()

            if first_run:
                log.info(f"Snapshot: {len(cur_positions)} position(s), {len(cur_orders)} open order(s).")
                for k in cur_positions:
                    log.info(f"  Position: {k}")
                for k in cur_orders:
                    log.info(f"  Open order: {k}")
                first_run = False
                prev_positions = cur_positions
                prev_orders    = cur_orders
                time.sleep(POLL_INTERVAL)
                continue

            # ── Position changes ──────────────────────────────────────────
            for key, pos in cur_positions.items():
                if key not in prev_positions:
                    log.info(f"NEW POSITION: {key}")
                    push_signal(make_signal_from_position(pos, 'OPEN'))

            for key, pos in prev_positions.items():
                if key not in cur_positions:
                    log.info(f"POSITION CLOSED: {key}")
                    push_signal(make_signal_from_position(pos, 'CLOSE'))

            # ── Open order changes ────────────────────────────────────────
            for oid, order in cur_orders.items():
                if oid not in prev_orders:
                    log.info(f"NEW ORDER: {oid}  {order.get('orderType','')} {order.get('side','')} {order.get('symbol','')}")
                    push_signal(make_signal_from_order(order, 'PLACE_ORDER'))

            for oid, order in prev_orders.items():
                if oid not in cur_orders:
                    # Filled orders disappear too — only send CANCEL if position still open
                    symbol = (order.get('ticker') or {}).get('symbol') or order.get('symbol', '')
                    position_still_open = any(
                        p.get('symbol') == symbol for p in cur_positions.values()
                    )
                    if position_still_open:
                        log.info(f"ORDER CANCELLED: {oid} (position still open, propagating cancel)")
                        push_signal(make_signal_from_order(order, 'CANCEL_ORDER'))
                    else:
                        log.info(f"ORDER FILLED/CLOSED: {oid} (position gone, no cancel needed)")

            prev_positions = cur_positions
            prev_orders    = cur_orders

        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception as e:
            log.error(f"Unexpected error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()
