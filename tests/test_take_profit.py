"""Test PLACE_ORDER signal — simulates friend placing a take-profit limit order."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import init, push, wait_for_processed, section, TEST_OPTION

section("TEST: PLACE_ORDER signal (Take Profit)")
print("  This simulates: friend sets a limit sell order to take profit.")
print("  Follower should: place a matching limit SELL order (scaled by multiplier).")
print()

init()

signal = {
    **TEST_OPTION,
    'event_type':             'PLACE_ORDER',
    'action':                 'SELL',
    'order_type':             'LIMIT',
    'qty':                    10,
    'price':                  4.00,
    'time_in_force':          'GTC',
    'leader_client_order_id': 'TEST-TP-001',
}

key = push(signal)
wait_for_processed(key)
