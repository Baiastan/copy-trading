"""
Daily pre-trade test suite — run this before enabling copy trading.

Usage:
    python -m tests.run_all

What it checks:
  1. Slippage guard logic (no services needed)
  2. Firebase connectivity
  3. Follower bot is live (heartbeat check)
  4. All signal types round-trip through Firebase (requires follower_bot running)
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from tests.helpers import init, push, wait_for_processed, section, TEST_OPTION

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"

results: list[tuple[str, str]] = []

def _show_summary():
    section("SUMMARY")
    passed = sum(1 for tag, _ in results if tag == PASS)
    failed = sum(1 for tag, _ in results if tag == FAIL)
    for tag, label in results:
        print(f"  {tag} {label}")
    print()
    if failed == 0:
        print(f"  All {passed} checks passed — safe to enable copy trading.")
    else:
        print(f"  {failed} check(s) FAILED — do NOT enable live trading until fixed.")

def record(label, ok, note=''):
    tag = PASS if ok else FAIL
    results.append((tag, label))
    suffix = f"  ({note})" if note else ''
    print(f"  {tag} {label}{suffix}")

# ─────────────────────────────────────────────────────────────────────────────
# 1. SLIPPAGE GUARD (pure logic, no network)
# ─────────────────────────────────────────────────────────────────────────────
section("1 / 4  Slippage guard logic")

import follower_bot

BASE_SIGNAL = {
    '_key': 'RUN-ALL-SLIP',
    'event_type': 'OPEN', 'action': 'BUY',
    'ticker': 'SPY', 'symbol': 'SPY',
    'qty': 20, 'price': 2.35,
    'instrument_id': 'TEST_INSTRUMENT_001',
    'option_type': 'CALL', 'strike_price': '560.00',
    'option_expire_date': '2026-06-20',
    'leader_client_order_id': 'RUN-ALL-OPEN',
}

def _run_slip(live_price, max_pct) -> str:
    marked = {}
    def fake_mark(key, status='ok'):
        marked['status'] = status
    with patch('follower_bot.get_current_ask', return_value=live_price), \
         patch('follower_bot.mark_processed', side_effect=fake_mark):
        follower_bot.handle_open(MagicMock(), BASE_SIGNAL.copy(), 0.5, max_pct, True)
    return marked.get('status', '?')

s = _run_slip(2.40, 20.0)
record("Small move (2%) executes at 20% limit", 'slippage' not in s, f"status={s}")

s = _run_slip(3.50, 20.0)
record("Big move (49%) skipped at 20% limit",   'slippage' in s,     f"status={s}")

s = _run_slip(2.50, 5.0)
record("Moderate move (6%) skipped at 5% limit", 'slippage' in s,    f"status={s}")

s = _run_slip(1.80, 20.0)
record("Price drop (23%) skipped at 20% limit",  'slippage' in s,    f"status={s}")

# ─────────────────────────────────────────────────────────────────────────────
# 2. FIREBASE CONNECTIVITY
# ─────────────────────────────────────────────────────────────────────────────
section("2 / 4  Firebase connectivity")

firebase_ok = False
try:
    init()
    from firebase_admin import db as fdb
    fdb.reference('copy_trading/status').get()
    firebase_ok = True
    record("Firebase reachable", True)
except Exception as e:
    record("Firebase reachable", False, str(e))
    print()
    print("  Cannot continue without Firebase. Check firebase_credentials.json and .env")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 3. FOLLOWER BOT HEARTBEAT
# ─────────────────────────────────────────────────────────────────────────────
section("3 / 4  Follower bot heartbeat")

status = fdb.reference('copy_trading/status').get() or {}
hb = status.get('follower_heartbeat', '')
follower_live = False

if hb:
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(hb)).total_seconds()
        follower_live = age < 10
        record(f"Follower bot online (last seen {int(age)}s ago)", follower_live)
    except Exception:
        record("Follower heartbeat parseable", False, hb)
else:
    record("Follower bot online", False, "no heartbeat — start follower_bot.py first")

if not follower_live:
    print()
    print("  Signal tests skipped — start follower_bot.py then re-run.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 4. SIGNAL ROUND-TRIPS
# ─────────────────────────────────────────────────────────────────────────────
section("4 / 4  Signal round-trips (dry run)")

TIMEOUT = 12  # seconds per signal

def signal_test(label, signal):
    key = push(signal)
    status = wait_for_processed(key, timeout=TIMEOUT)
    ok = status is not None and 'error' not in str(status).lower() and 'skipped' not in str(status).lower()
    record(label, ok, f"status={status}")
    return status

# 4a. OPEN
signal_test("OPEN signal processed", {
    **TEST_OPTION,
    'event_type': 'OPEN', 'action': 'BUY',
    'qty': 20, 'price': 2.35,
    'leader_client_order_id': 'RUN-ALL-OPEN',
})
time.sleep(1)

# 4b. PLACE_ORDER stop-loss
signal_test("PLACE_ORDER (stop-loss) processed", {
    **TEST_OPTION,
    'event_type': 'PLACE_ORDER', 'action': 'SELL',
    'order_type': 'STOP_LOSS_LIMIT',
    'qty': 20, 'price': 1.50, 'stop_price': 1.45,
    'time_in_force': 'GTC',
    'leader_client_order_id': 'RUN-ALL-SL',
})
time.sleep(1)

# 4c. PLACE_ORDER take-profit
signal_test("PLACE_ORDER (take-profit) processed", {
    **TEST_OPTION,
    'event_type': 'PLACE_ORDER', 'action': 'SELL',
    'order_type': 'LIMIT',
    'qty': 20, 'price': 4.00,
    'time_in_force': 'GTC',
    'leader_client_order_id': 'RUN-ALL-TP',
})
time.sleep(1)

# 4d. CANCEL_ORDER
signal_test("CANCEL_ORDER processed", {
    **TEST_OPTION,
    'event_type': 'CANCEL_ORDER', 'action': 'CANCEL',
    'qty': 0, 'price': 0.0,
    'leader_client_order_id': 'RUN-ALL-TP',
})
time.sleep(1)

# 4e. CLOSE
signal_test("CLOSE signal processed", {
    **TEST_OPTION,
    'event_type': 'CLOSE', 'action': 'SELL',
    'qty': 20, 'price': 3.10,
    'leader_client_order_id': 'RUN-ALL-CLOSE',
})

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
_show_summary()
