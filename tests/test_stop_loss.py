"""Test PLACE_ORDER signal — simulates friend placing a stop-loss order."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import init, push, wait_for_processed, section, TEST_OPTION

section("TEST: PLACE_ORDER signal (Stop Loss)")
print("  This simulates: friend sets a stop-loss limit order after opening.")
print("  Follower should: place a matching stop-loss limit order (scaled by multiplier).")
print()

init()

signal = {
    **TEST_OPTION,
    'event_type':             'PLACE_ORDER',
    'action':                 'SELL',
    'order_type':             'STOP_LOSS_LIMIT',
    'qty':                    10,
    'price':                  1.50,
    'stop_price':             1.45,
    'time_in_force':          'GTC',
    'leader_client_order_id': 'TEST-SL-001',
}

key = push(signal)
wait_for_processed(key)
