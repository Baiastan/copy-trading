"""
Full trade cycle test — runs all signal types in the correct order:
  1. OPEN  (market buy)
  2. PLACE_ORDER stop-loss
  3. PLACE_ORDER take-profit
  4. CANCEL_ORDER (cancel take-profit)
  5. CLOSE (market sell)

Keep follower_bot.py running in another terminal while this runs.
Watch follower logs to confirm each step is handled correctly.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import init, push, wait_for_processed, section, TEST_OPTION

DELAY = 2  # seconds between steps

init()

# ── Step 1: Open position ─────────────────────────────────────────────────────
section("STEP 1 / 5 — OPEN (Market Buy 10 contracts)")
key1 = push({
    **TEST_OPTION,
    'event_type': 'OPEN',
    'action':     'BUY',
    'qty':        10,
    'price':      2.35,
    'leader_client_order_id': 'CYCLE-OPEN-001',
})
wait_for_processed(key1)
time.sleep(DELAY)

# ── Step 2: Place stop-loss ───────────────────────────────────────────────────
section("STEP 2 / 5 — PLACE_ORDER Stop-Loss @ $1.50")
key2 = push({
    **TEST_OPTION,
    'event_type':             'PLACE_ORDER',
    'action':                 'SELL',
    'order_type':             'STOP_LOSS_LIMIT',
    'qty':                    10,
    'price':                  1.50,
    'stop_price':             1.45,
    'time_in_force':          'GTC',
    'leader_client_order_id': 'CYCLE-SL-001',
})
wait_for_processed(key2)
time.sleep(DELAY)

# ── Step 3: Place take-profit ─────────────────────────────────────────────────
section("STEP 3 / 5 — PLACE_ORDER Take-Profit Limit @ $4.00")
key3 = push({
    **TEST_OPTION,
    'event_type':             'PLACE_ORDER',
    'action':                 'SELL',
    'order_type':             'LIMIT',
    'qty':                    10,
    'price':                  4.00,
    'time_in_force':          'GTC',
    'leader_client_order_id': 'CYCLE-TP-001',
})
wait_for_processed(key3)
time.sleep(DELAY)

# ── Step 4: Cancel take-profit ────────────────────────────────────────────────
section("STEP 4 / 5 — CANCEL_ORDER (cancel take-profit)")
key4 = push({
    **TEST_OPTION,
    'event_type':             'CANCEL_ORDER',
    'action':                 'CANCEL',
    'qty':                    0,
    'price':                  0.0,
    'leader_client_order_id': 'CYCLE-TP-001',
})
wait_for_processed(key4)
time.sleep(DELAY)

# ── Step 5: Close position ────────────────────────────────────────────────────
section("STEP 5 / 5 — CLOSE (Market Sell, cancels remaining SL first)")
key5 = push({
    **TEST_OPTION,
    'event_type': 'CLOSE',
    'action':     'SELL',
    'qty':        10,
    'price':      3.10,
    'leader_client_order_id': 'CYCLE-CLOSE-001',
})
wait_for_processed(key5)

section("FULL CYCLE COMPLETE")
print("  Check follower_bot terminal for all 5 steps handled in dry-run mode.")
