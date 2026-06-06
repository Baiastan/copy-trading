from webull.core.client import ApiClient
from webull.trade.trade_client import TradeClient

APP_KEY = 'c2fd9793a4855fa9d07f461896cefc8f'
APP_SECRET = '2dfe5e2c804317231c7410d7d8db0e0c'

# Use the margin account (change to CASH account ID if preferred)
ACCOUNT_ID = 'AHG40OF74T140U1HK87V7AQGB9'

api_client = ApiClient(APP_KEY, APP_SECRET, 'us')
api_client.add_endpoint('us', 'api.webull.com')

trade_client = TradeClient(api_client)

# Test: get positions
res = trade_client.account_v2.get_positions(account_id=ACCOUNT_ID)
print("Positions:", res.json())

# Test: get open orders
res2 = trade_client.order.get_open_orders(account_id=ACCOUNT_ID)
print("Open orders:", res2.json())
