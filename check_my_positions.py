"""
Quick check of YOUR current positions and open orders.
Run this anytime to see what's in your accounts.

  python check_my_positions.py
"""

import json
from webull.core.client import ApiClient
from webull.trade.trade_client import TradeClient
from config import APP_KEY, APP_SECRET, ACCOUNT_IDS

ACCOUNT_IDS = {acc_id: f"Account {i+1}" for i, acc_id in enumerate(ACCOUNT_IDS)}

api_client = ApiClient(APP_KEY, APP_SECRET, 'us')
api_client.add_endpoint('us', 'api.webull.com')
trade_client = TradeClient(api_client)

print("=" * 55)
print("Your Webull Positions")
print("=" * 55)

for acc_id, label in ACCOUNT_IDS.items():
    print(f"\n── {label} Account ({acc_id}) ──")

    # Positions
    try:
        res = trade_client.account.get_account_position(acc_id, page_size=100)
        data = res.json()
        holdings = data.get('holdings', [])
        if holdings:
            print(f"  Open positions ({len(holdings)}):")
            for h in holdings:
                symbol = h.get('symbol', 'N/A')
                itype = h.get('instrument_type', '')
                qty = h.get('qty', 0)
                cost = h.get('unit_cost', 0)
                price = h.get('last_price', 0)
                pnl = h.get('unrealized_profit_loss', 'N/A')
                mktval = h.get('market_value', 'N/A')
                iid = h.get('instrument_id', '')
                print(f"    {itype:6}  {symbol:6}  qty={qty}  cost=${cost}  last=${price}  P&L=${pnl}  mktval=${mktval}  id={iid}")
        else:
            print("  No open positions.")
    except Exception as e:
        print(f"  Error fetching positions: {e}")

    # Open orders
    try:
        res2 = trade_client.order.list_open_orders(acc_id, page_size=50)
        data2 = res2.json()
        orders = data2.get('orders', data2.get('data', []))
        if isinstance(orders, list) and orders:
            print(f"  Open orders ({len(orders)}):")
            for o in orders:
                print(f"    {json.dumps(o)}")
        else:
            print("  No open orders.")
    except Exception as e:
        print(f"  Error fetching orders: {e}")

print()
print("=" * 55)
