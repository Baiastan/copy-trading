"""Test CLOSE signal — simulates friend closing / selling their position."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import init, push, wait_for_processed, section, TEST_OPTION

section("TEST: CLOSE signal (Market Sell)")
print("  This simulates: friend closes their position (market sell).")
print("  Follower should: cancel any open SL/TP orders for SPY, then market SELL.")
print()

init()

signal = {
    **TEST_OPTION,
    'event_type': 'CLOSE',
    'action':     'SELL',
    'qty':        10,
    'price':      2.80,
    'leader_client_order_id': 'TEST-CLOSE-001',
}

key = push(signal)
wait_for_processed(key)
