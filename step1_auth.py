"""
STEP 1 - Authentication Setup
==============================
Run this ONCE to connect your Webull account.

BEFORE running:
  1. Install Python 3.11+ from https://python.org
  2. Open Terminal (Mac) or Command Prompt (Windows) in this folder
  3. Run:  pip install webull-openapi-python-sdk

HOW TO RUN:
  python step1_auth.py

WHAT WILL HAPPEN:
  1. Script creates a PENDING token request
  2. You will see a message to approve in your Webull app
  3. Open Webull app → Profile → Settings → API Permissions (or check notifications)
  4. Approve the pending request
  5. Script will detect approval automatically and print your accounts
  6. Token is saved to conf/token.txt — you won't need to re-login
"""

import time
from webull.core.client import ApiClient
from webull.trade.trade_client import TradeClient
from config import APP_KEY, APP_SECRET

print("=" * 50)
print("STEP 1: Webull Authentication")
print("=" * 50)
print()
print("Connecting to Webull...")

api_client = ApiClient(APP_KEY, APP_SECRET, 'us')
api_client.add_endpoint('us', 'api.webull.com')

trade_client = TradeClient(api_client)

print()
print(">>> ACTION REQUIRED <<<")
print("Open your Webull mobile app and approve the API access request.")
print("Look for a notification or go to: Profile → Settings → API Permissions")
print()
print("Waiting for you to approve (checking every 5 seconds)...")
print()

# Poll until approved
attempt = 0
while True:
    attempt += 1
    try:
        res = trade_client.account_v2.get_account_list()
        data = res.json()

        accounts = data if isinstance(data, list) else data.get('data', [])
        if accounts:
            print("SUCCESS! Token approved!")
            print()
            print("Your accounts:")
            for acc in accounts:
                acc_id = acc.get('accountId', acc.get('account_id', 'N/A'))
                acc_type = acc.get('accountType', acc.get('account_type', 'N/A'))
                currency = acc.get('currency', 'N/A')
                print(f"  - ID: {acc_id}  |  Type: {acc_type}  |  Currency: {currency}")
            print()
            print("Token saved to conf/token.txt")
            print("You can now run: python step2_test.py")
            break
        else:
            print(f"Attempt {attempt}: Still pending... please approve in the Webull app.")
            time.sleep(5)

    except Exception as e:
        msg = str(e).lower()
        if 'pending' in msg or 'token' in msg or 'unauthorized' in msg or '401' in msg:
            print(f"Attempt {attempt}: Token still pending, please approve in the Webull app.")
            time.sleep(5)
        else:
            print(f"Attempt {attempt}: Error - {e}")
            time.sleep(5)
