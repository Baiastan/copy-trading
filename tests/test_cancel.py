"""Test CANCEL_ORDER signal — simulates friend cancelling a pending order."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import init, push, wait_for_processed, section, TEST_OPTION

section("TEST: CANCEL_ORDER signal")
print("  This simulates: friend cancels a pending limit/stop order.")
print("  Follower should: look up 'TEST-TP-001' in order_map and cancel it.")
print("  NOTE: Run test_take_profit.py first so the order exists in order_map.")
print()

init()

signal = {
    **TEST_OPTION,
    'event_type':             'CANCEL_ORDER',
    'action':                 'CANCEL',
    'qty':                    0,
    'price':                  0.0,
    'leader_client_order_id': 'TEST-TP-001',  # must match a previously placed order
}

key = push(signal)
wait_for_processed(key)
