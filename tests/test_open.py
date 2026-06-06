"""Test OPEN signal — simulates friend buying a SPY CALL."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import init, push, wait_for_processed, section, TEST_OPTION

section("TEST: OPEN signal (Market Buy)")
print("  This simulates: friend opens a new options position.")
print("  Follower should log: [DRY RUN] Market BUY 5 contracts of SPY CALL ...")
print()

init()

signal = {
    **TEST_OPTION,
    'event_type': 'OPEN',
    'action':     'BUY',
    'qty':        20,
    'price':      2.35,
    'leader_client_order_id': 'TEST-OPEN-001',
}

key = push(signal)
wait_for_processed(key)
