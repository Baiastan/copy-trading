"""
STEP 2 - Verify Connection
===========================
Run this AFTER step1_auth.py succeeds.

HOW TO RUN:
  python step2_test.py

WHAT THIS DOES:
  - Reads your saved token (no re-login needed)
  - Fetches your account list
  - Fetches your current positions
  - Fetches your open orders
  - Prints everything so you can confirm the bot can see your trades
"""

import json
from webull.core.client import ApiClient
from webull.trade.trade_client import TradeClient
from config import APP_KEY, APP_SECRET

print("=" * 50)
print("STEP 2: Verify Connection & Data Access")
print("=" * 50)
print()

api_client = ApiClient(APP_KEY, APP_SECRET, 'us')
api_client.add_endpoint('us', 'api.webull.com')
trade_client = TradeClient(api_client)


# ── 1. Account List ──────────────────────────────────────────────────────────
print("[ Fetching accounts... ]")
res = trade_client.account_v2.get_account_list()
accounts_data = res.json()
print(json.dumps(accounts_data, indent=2))
print()

# Collect account IDs
account_ids = []
if 'data' in accounts_data and accounts_data['data']:
    for acc in accounts_data['data']:
        acc_id = acc.get('accountId') or acc.get('account_id')
        if acc_id:
            account_ids.append(acc_id)
            acc_type = acc.get('accountType') or acc.get('account_type', 'N/A')
            print(f"Found account: {acc_id} ({acc_type})")

if not account_ids:
    print("ERROR: No accounts found. Make sure step1_auth.py succeeded.")
    exit(1)

print()


# ── 2. Positions ─────────────────────────────────────────────────────────────
for acc_id in account_ids:
    print(f"[ Fetching positions for account: {acc_id} ]")
    try:
        res = trade_client.account.get_account_position(acc_id, page_size=50)
        pos_data = res.json()
        print(json.dumps(pos_data, indent=2))
    except Exception as e:
        print(f"Error fetching positions: {e}")
    print()


# ── 3. Open Orders ───────────────────────────────────────────────────────────
for acc_id in account_ids:
    print(f"[ Fetching open orders for account: {acc_id} ]")
    try:
        res = trade_client.order.list_open_orders(acc_id, page_size=50)
        orders_data = res.json()
        print(json.dumps(orders_data, indent=2))
    except Exception as e:
        print(f"Error fetching open orders: {e}")
    print()


# ── 4. Today's Orders ────────────────────────────────────────────────────────
for acc_id in account_ids:
    print(f"[ Fetching today's orders for account: {acc_id} ]")
    try:
        res = trade_client.order.list_today_orders(acc_id, page_size=50)
        today_data = res.json()
        print(json.dumps(today_data, indent=2))
    except Exception as e:
        print(f"Error fetching today's orders: {e}")
    print()


print("=" * 50)
print("If you see account/position/order data above, everything works!")
print("Next step: run python step3_leader_bot.py to start the copy-trading bot.")
print("=" * 50)
