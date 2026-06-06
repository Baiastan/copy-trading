"""
Follower Bot — runs on Baiastan's computer
============================================
Reads trade signals from Firebase and copies them to your Webull account.

DRY_RUN = True  → just logs what it would do, NO real orders placed (safe for testing)
DRY_RUN = False → places real orders on your Webull account

Signal types handled:
  OPEN         → market BUY to open position
  CLOSE        → market SELL to close position + cancel any open stop/TP orders
  PLACE_ORDER  → place a limit/stop order (stop loss or take profit)
  CANCEL_ORDER → cancel a previously placed stop/TP order

HOW TO RUN:
  python follower_bot.py
"""

import time
import uuid
import json
import logging
from datetime import datetime, timezone
from webull.core.client import ApiClient
from webull.trade.trade_client import TradeClient
from config import (APP_KEY, APP_SECRET, DEFAULT_ACCOUNT_ID,
                    FIREBASE_DATABASE_URL, FIREBASE_CREDENTIALS_PATH,
                    SIZE_MULTIPLIER, POLL_INTERVAL, SIGNAL_MAX_AGE_SECONDS)

# ── CONFIG ───────────────────────────────────────────────────────────────────
DRY_RUN = True   # Set to False to place real orders
FIREBASE_CREDENTIALS = FIREBASE_CREDENTIALS_PATH
# ────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)

# Maps leader's client_order_id → follower's client_order_id
# Used to cancel the right order when leader cancels theirs
order_map: dict[str, str] = {}

# Maps ticker symbol → list of follower client_order_ids (for cancel-on-close)
symbol_orders: dict[str, list[str]] = {}


# ── Firebase ──────────────────────────────────────────────────────────────────

def init_firebase():
    import firebase_admin
    from firebase_admin import credentials
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS)
        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DATABASE_URL})
    log.info("Firebase connected.")


def get_pending_signals(max_age_seconds: int) -> list:
    from firebase_admin import db as fdb
    data = fdb.reference('copy_trading/signals').get() or {}
    pending = []
    now = datetime.now(timezone.utc)
    for key, val in data.items():
        if not isinstance(val, dict) or val.get('processed', False):
            continue
        if val.get('_test', False):
            fdb.reference(f'copy_trading/signals/{key}/processed').set(True)
            continue
        ts = val.get('timestamp', '')
        if ts:
            try:
                age = (now - datetime.fromisoformat(ts)).total_seconds()
                if age > max_age_seconds:
                    log.warning(f"Signal {key} is {age:.0f}s old — skipping")
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


# ── Order helpers ─────────────────────────────────────────────────────────────

def new_order_id() -> str:
    return str(uuid.uuid4()).replace('-', '')[:32]


def build_option_order(signal: dict, follower_order_id: str,
                       qty: int, size_mult: float, spread_buf: float) -> dict:
    """Build the new_orders list payload for order_v2.place_option()."""
    order_type  = signal.get('order_type', 'LIMIT')
    side        = signal.get('side', 'BUY')
    symbol      = signal.get('symbol') or signal.get('ticker', '')
    option_type = signal.get('option_type', '')
    strike      = signal.get('strike_price') or signal.get('strike', '')
    expiry      = signal.get('option_expire_date') or signal.get('expiry', '')
    tif         = signal.get('time_in_force', 'DAY')

    adjusted_qty = max(1, round(qty * size_mult))

    order = {
        'client_order_id':  follower_order_id,
        'combo_type':       'NORMAL',
        'order_type':       order_type,
        'quantity':         str(adjusted_qty),
        'option_strategy':  'SINGLE',
        'side':             side,
        'time_in_force':    tif,
        'entrust_type':     'QTY',
        'instrument_type':  'OPTION',
        'market':           'US',
        'symbol':           symbol,
        'legs': [{
            'side':               side,
            'quantity':           str(adjusted_qty),
            'symbol':             symbol,
            'strike_price':       str(strike),
            'option_expire_date': str(expiry),
            'instrument_type':    'OPTION',
            'option_type':        option_type,
            'market':             'US',
        }],
    }

    # Apply prices with spread buffer
    limit_price = signal.get('limit_price')
    stop_price  = signal.get('stop_price')

    if limit_price is not None:
        buf = spread_buf if side == 'BUY' else -spread_buf
        order['limit_price'] = str(round(float(limit_price) + buf, 2))
    if stop_price is not None:
        order['stop_price'] = str(stop_price)

    return order


# ── Price / slippage helpers ──────────────────────────────────────────────────

def get_current_ask(trade_client: TradeClient, instrument_id: str) -> float | None:
    """Fetch live ask (or last) price for an option contract by instrument_id."""
    if not instrument_id:
        return None
    try:
        res = trade_client.trade_instrument.get_trade_instrument_detail(instrument_id)
        data = res.json()
        price = (data.get('askPrice') or data.get('ask') or
                 data.get('lastPrice') or data.get('last_price') or
                 data.get('close'))
        if price is not None:
            return float(str(price))
    except Exception as e:
        log.debug(f"Could not fetch live price for {instrument_id}: {e}")
    return None


# ── Signal handlers ───────────────────────────────────────────────────────────

def handle_open(trade_client: TradeClient, signal: dict, size_mult: float,
                max_slippage_pct: float, dry_run: bool):
    """Open a new position — MARKET BUY with slippage guard."""
    key           = signal['_key']
    symbol        = signal.get('ticker', '') or signal.get('symbol', '')
    qty           = max(1, round(int(signal.get('qty', 1)) * size_mult))
    ref_price     = float(signal.get('price', 0))
    instrument_id = signal.get('instrument_id', '')

    # ── Slippage check ────────────────────────────────────────────────────────
    if ref_price > 0 and instrument_id:
        live_price = get_current_ask(trade_client, instrument_id)
        if live_price is not None:
            slippage = abs(live_price - ref_price) / ref_price * 100
            log.info(f"Slippage check: ref=${ref_price:.2f}  live=${live_price:.2f}  slippage={slippage:.1f}%  max={max_slippage_pct}%")
            if slippage > max_slippage_pct:
                log.warning(f"OPEN {symbol} SKIPPED — slippage {slippage:.1f}% > {max_slippage_pct}%")
                mark_processed(key, f'skipped: slippage {slippage:.1f}%')
                return
        else:
            log.debug("Could not fetch live price — proceeding without slippage check")

    log.info(f"OPEN  {symbol}  qty={qty}  MARKET")

    if dry_run:
        log.info(f"[DRY RUN] MARKET BUY {qty} {symbol}")
        mark_processed(key, 'ok (dry run)')
        return

    try:
        follower_oid = new_order_id()
        new_orders = [build_option_order(
            {**signal, 'order_type': 'MARKET', 'side': 'BUY', 'time_in_force': 'DAY'},
            follower_oid, qty, 1.0, 0.0
        )]
        res = trade_client.order_v2.place_option(DEFAULT_ACCOUNT_ID, new_orders)
        log.info(f"OPEN placed: {res.json()}")
        mark_processed(key, 'ok')
    except Exception as e:
        log.error(f"OPEN failed: {e}")
        mark_processed(key, f'error: {e}')


def handle_close(trade_client: TradeClient, signal: dict, size_mult: float, dry_run: bool):
    """Close a position — cancel open stop/TP orders first, then MARKET SELL."""
    key    = signal['_key']
    symbol = signal.get('ticker', '') or signal.get('symbol', '')
    qty    = max(1, round(int(signal.get('qty', 1)) * size_mult))

    log.info(f"CLOSE {symbol}  qty={qty}  MARKET")

    # Cancel any outstanding stop/TP orders for this symbol first
    to_cancel = symbol_orders.pop(symbol, [])
    for foid in to_cancel:
        if dry_run:
            log.info(f"[DRY RUN] Would cancel order {foid} for {symbol}")
        else:
            try:
                trade_client.order_v2.cancel_option(DEFAULT_ACCOUNT_ID, foid)
                log.info(f"Cancelled order {foid}")
            except Exception as e:
                log.warning(f"Cancel {foid} failed (may have already filled): {e}")

    if dry_run:
        log.info(f"[DRY RUN] MARKET SELL {qty} {symbol}")
        mark_processed(key, 'ok (dry run)')
        return

    try:
        follower_oid = new_order_id()
        new_orders = [build_option_order(
            {**signal, 'order_type': 'MARKET', 'side': 'SELL', 'time_in_force': 'DAY'},
            follower_oid, qty, 1.0, 0.0
        )]
        res = trade_client.order_v2.place_option(DEFAULT_ACCOUNT_ID, new_orders)
        log.info(f"CLOSE placed: {res.json()}")
        mark_processed(key, 'ok')
    except Exception as e:
        log.error(f"CLOSE failed: {e}")
        mark_processed(key, f'error: {e}')


def handle_place_order(trade_client: TradeClient, signal: dict, size_mult: float, spread_buf: float, dry_run: bool):
    """Mirror a stop loss or take profit order from the leader."""
    key              = signal['_key']
    leader_oid       = signal.get('leader_client_order_id', '')
    order_type       = signal.get('order_type', '')
    side             = signal.get('side', '')
    symbol           = signal.get('symbol', '')
    qty              = int(signal.get('qty', 1))
    limit_price      = signal.get('limit_price')
    stop_price       = signal.get('stop_price')

    desc = f"{order_type} {side} {symbol}"
    if limit_price:
        desc += f" limit=${limit_price}"
    if stop_price:
        desc += f" stop=${stop_price}"

    log.info(f"PLACE_ORDER  {desc}  qty={qty}")

    if dry_run:
        log.info(f"[DRY RUN] Would place: {desc}")
        mark_processed(key, 'ok (dry run)')
        return

    try:
        follower_oid = new_order_id()
        new_orders = [build_option_order(signal, follower_oid, qty, size_mult, spread_buf)]
        res = trade_client.order_v2.place_option(DEFAULT_ACCOUNT_ID, new_orders)
        log.info(f"Limit/stop order placed: {res.json()}")

        # Track mapping for future cancellation
        order_map[leader_oid] = follower_oid
        symbol_orders.setdefault(symbol, []).append(follower_oid)

        mark_processed(key, 'ok')
    except Exception as e:
        log.error(f"PLACE_ORDER failed: {e}")
        mark_processed(key, f'error: {e}')


def handle_cancel_order(trade_client: TradeClient, signal: dict, dry_run: bool):
    """Cancel the follower's matching order when leader cancels theirs."""
    key        = signal['_key']
    leader_oid = signal.get('leader_client_order_id', '')
    follower_oid = order_map.pop(leader_oid, None)

    if not follower_oid:
        log.warning(f"CANCEL_ORDER: no matching follower order for leader={leader_oid}")
        mark_processed(key, 'skipped: no matching order')
        return

    log.info(f"CANCEL_ORDER  leader={leader_oid}  follower={follower_oid}")

    # Remove from symbol_orders too
    for orders in symbol_orders.values():
        if follower_oid in orders:
            orders.remove(follower_oid)

    if dry_run:
        log.info(f"[DRY RUN] Would cancel {follower_oid}")
        mark_processed(key, 'ok (dry run)')
        return

    try:
        trade_client.order_v2.cancel_option(DEFAULT_ACCOUNT_ID, follower_oid)
        log.info(f"Order {follower_oid} cancelled.")
        mark_processed(key, 'ok')
    except Exception as e:
        log.error(f"Cancel failed (may have already filled): {e}")
        mark_processed(key, f'error: {e}')


def execute_signal(trade_client: TradeClient, signal: dict, size_mult: float, spread_buf: float,
                   dry_run: bool, max_slippage_pct: float = 20.0):
    event_type = signal.get('event_type', '')
    if event_type == 'OPEN':
        handle_open(trade_client, signal, size_mult, max_slippage_pct, dry_run)
    elif event_type == 'CLOSE':
        handle_close(trade_client, signal, size_mult, dry_run)
    elif event_type == 'PLACE_ORDER':
        handle_place_order(trade_client, signal, size_mult, spread_buf, dry_run)
    elif event_type == 'CANCEL_ORDER':
        handle_cancel_order(trade_client, signal, dry_run)
    else:
        log.warning(f"Unknown event_type: {event_type}")
        mark_processed(signal['_key'], f'skipped: unknown event_type {event_type}')


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("Follower Bot — mode controlled by dashboard (starts in DRY RUN)")
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

    try:
        init_firebase()
    except Exception as e:
        print(f"ERROR connecting to Firebase: {e}")
        return

    log.info(f"Polling Firebase every {POLL_INTERVAL}s. Press Ctrl+C to stop.")
    log.info("DRY RUN starts ON — toggle it off in the dashboard to go live.")
    print()

    while True:
        try:
            update_follower_heartbeat()

            from firebase_admin import db as fdb
            live       = fdb.reference('copy_trading/status').get() or {}
            copy_on          = live.get('copy_enabled', True)
            dry_run          = live.get('dry_run', True)
            size_mult        = float(live.get('size_multiplier', SIZE_MULTIPLIER))
            spread_buf       = float(live.get('spread_buffer', 0.05))
            max_age          = int(live.get('max_signal_age', SIGNAL_MAX_AGE_SECONDS))
            max_slippage_pct = float(live.get('max_slippage_pct', 20.0))

            if not copy_on:
                log.info("Copy trading DISABLED via dashboard — skipping.")
                time.sleep(POLL_INTERVAL)
                continue

            pending = get_pending_signals(max_age_seconds=max_age)
            if pending:
                log.info(f"{len(pending)} pending signal(s).")
                for signal in pending:
                    execute_signal(trade_client, signal, size_mult, spread_buf,
                                   dry_run, max_slippage_pct)

        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception as e:
            log.error(f"Error in main loop: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()
