"""
Slippage guard test — no real Webull/Firebase calls needed.

Patches get_current_ask() to return a fake live price so we can
verify the guard fires (or passes) at different slippage levels.

Run with:
    python -m tests.test_slippage
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
import follower_bot
from tests.helpers import section

# Fake signal: friend bought SPY CALL at $2.35
BASE_SIGNAL = {
    '_key':                   'TEST-SLIP-KEY',
    'event_type':             'OPEN',
    'action':                 'BUY',
    'ticker':                 'SPY',
    'symbol':                 'SPY',
    'qty':                    20,
    'price':                  2.35,
    'instrument_id':          'TEST_INSTRUMENT_001',
    'option_type':            'CALL',
    'strike_price':           '560.00',
    'option_expire_date':     '2026-06-20',
    'leader_client_order_id': 'TEST-SLIP-OPEN',
}

def run_case(label, live_price, max_slippage_pct, expect_skip):
    fake_client = MagicMock()

    marked = {}
    def fake_mark(key, status='ok'):
        marked['status'] = status

    slippage = abs(live_price - BASE_SIGNAL['price']) / BASE_SIGNAL['price'] * 100

    with patch('follower_bot.get_current_ask', return_value=live_price), \
         patch('follower_bot.mark_processed', side_effect=fake_mark):
        follower_bot.handle_open(
            trade_client=fake_client,
            signal=BASE_SIGNAL.copy(),
            size_mult=0.5,
            max_slippage_pct=max_slippage_pct,
            dry_run=True,
        )

    status = marked.get('status', '?')
    skipped = 'slippage' in status

    result = 'PASS' if (skipped == expect_skip) else 'FAIL'
    action = 'SKIPPED' if skipped else 'EXECUTED'
    print(f"  [{result}] {label}")
    print(f"         ref=$2.35  live=${live_price:.2f}  slippage={slippage:.1f}%  max={max_slippage_pct}%  → {action}  (status: {status})")
    print()


section("SLIPPAGE GUARD TESTS")
print("  Signal price (ref): $2.35")
print()

# Case 1: tiny move — should execute (2% < 20% limit)
run_case(
    label="Small move $2.35 → $2.40  (2.1%)  — should EXECUTE",
    live_price=2.40,
    max_slippage_pct=20.0,
    expect_skip=False,
)

# Case 2: big move — should be skipped (49% > 20% limit)
run_case(
    label="Big move  $2.35 → $3.50  (48.9%) — should SKIP",
    live_price=3.50,
    max_slippage_pct=20.0,
    expect_skip=True,
)

# Case 3: exactly at the edge — should execute (20% == 20% limit, not greater)
run_case(
    label="Edge case $2.35 → $2.82  (20.0%) — should EXECUTE (equal, not over)",
    live_price=round(2.35 * 1.20, 2),
    max_slippage_pct=20.0,
    expect_skip=False,
)

# Case 4: tight limit (5%) with moderate move — should skip
run_case(
    label="Tight limit (5%)  $2.35 → $2.50  (6.4%)  — should SKIP",
    live_price=2.50,
    max_slippage_pct=5.0,
    expect_skip=True,
)

# Case 5: price dropped (option lost value after signal)
run_case(
    label="Price drop  $2.35 → $1.80  (23.4%) — should SKIP",
    live_price=1.80,
    max_slippage_pct=20.0,
    expect_skip=True,
)
