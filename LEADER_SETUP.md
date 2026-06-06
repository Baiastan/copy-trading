# Leader Setup Guide (Windows)

## How the system works

This is a copy-trading relay. Two sides:

- **Leader** (you, this guide) — trades normally on Webull. A background script
  watches your positions and open orders, and pushes a signal to Firebase every
  time you open, close, or place a stop/TP order.
- **Follower** (Baiastan) — a bot on his machine reads those signals from
  Firebase and mirrors the trades on his own Webull account automatically.

You do not need to change how you trade. Just run the leader bot before you
start and it handles everything in the background.

### Signal flow
```
Your Webull account
       ↓  (leader bot polls every 1 second)
  Firebase Realtime Database  (relay — signals live here for ~4 seconds)
       ↓  (follower bot polls every 1 second)
  Baiastan's Webull account
```

### Signal types the bot detects automatically
| What you do in Webull | Signal pushed |
|-----------------------|---------------|
| Open a new options position | `OPEN` |
| Close / sell a position | `CLOSE` |
| Place a stop-loss or take-profit order | `PLACE_ORDER` |
| Cancel a pending order | `CANCEL_ORDER` |

---

## Files in this repo

| File | Purpose |
|------|---------|
| `step1_auth.py` | Run once — authenticates your Webull account and saves token |
| `step2_test.py` | Optional — verify your account connection is working |
| `step3_leader_bot.py` | **Main script** — run every trading day |
| `config.py` | Reads settings from `.env` |
| `relay.py` | Firebase helpers (push/read signals) |
| `.env` | Your credentials — never commit this file |
| `firebase_credentials.json` | Firebase write access — never commit this file |
| `conf/token.txt` | Your Webull session token — auto-created, never commit |

---

## What you need before starting

- Windows 10 or 11
- Your Webull account (the one you actively trade from)
- Two files from Baiastan (he sends these to you privately):
  - `firebase_credentials.json`
  - `.env` (pre-filled with your account ID once you complete Step 6)

---

## Step 1 — Install Python

1. Go to **https://www.python.org/downloads/**
2. Download the latest **Python 3.11** or newer
3. Run the installer — on the first screen, check **"Add Python to PATH"**

Verify in Command Prompt:
```
python --version
```
Expected output: `Python 3.12.x` (or similar)

---

## Step 2 — Install Git

1. Go to **https://git-scm.com/download/win**
2. Download and run the installer (all defaults are fine)

---

## Step 3 — Download the bot

Open **Command Prompt** and run:

```
cd %USERPROFILE%\Desktop
git clone https://github.com/Baiastan/copy-trading.git
cd copy-trading
```

---

## Step 4 — Place your credential files

Baiastan will send you two files. Put both inside the `copy-trading` folder on your Desktop:

- `firebase_credentials.json`
- `.env`

The `.env` file looks like this (Baiastan fills in the actual values for you):

```
WEBULL_APP_KEY=YOUR_APP_KEY_HERE
WEBULL_APP_SECRET=YOUR_APP_SECRET_HERE
WEBULL_ACCOUNT_IDS=YOUR_ACCOUNT_ID_HERE
WEBULL_DEFAULT_ACCOUNT_ID=YOUR_ACCOUNT_ID_HERE

FIREBASE_DATABASE_URL=https://copy-trading-45e77-default-rtdb.firebaseio.com
FIREBASE_CREDENTIALS_PATH=firebase_credentials.json

POLL_INTERVAL=1
SIGNAL_MAX_AGE_SECONDS=4
```

> `WEBULL_ACCOUNT_IDS` is found after you run Step 6. Send the ID to Baiastan
> and he will update your `.env`.

---

## Step 5 — Install dependencies

In Command Prompt inside the `copy-trading` folder:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

You should see `(venv)` appear at the start of the line.

> Every new Command Prompt session: run `venv\Scripts\activate` before the bot.

---

## Step 6 — Authenticate your Webull account (one time only)

```
python step1_auth.py
```

The script will pause and ask you to approve the connection:

1. Open Webull on your phone
2. Go to **Profile → Settings → API Permissions** (or check notifications)
3. Approve the pending request

Once approved, the script prints your account IDs — send them to Baiastan so
he can update your `.env`. The token is saved to `conf\token.txt` automatically.
You will not need to repeat this step.

---

## Step 7 — (Optional) Verify the connection

```
python step2_test.py
```

This prints your account balances and confirms Webull is connected. Not required
but useful if you want to double-check before going live.

---

## Step 8 — Run the leader bot

Every trading day, before you start trading:

```
venv\Scripts\activate
python step3_leader_bot.py
```

Expected output:
```
Leader Bot started. Polling every 1s...
Connected to Webull. Watching positions and orders...
```

Leave this window open all day. Trade normally in Webull — the bot detects your
moves automatically and pushes signals to Baiastan.

To stop: **Ctrl + C**

---

## Daily routine (30 seconds)

1. Open Command Prompt
2. `cd %USERPROFILE%\Desktop\copy-trading`
3. `venv\Scripts\activate`
4. `python step3_leader_bot.py`
5. Trade normally

---

## Troubleshooting

**"python is not recognized"**
→ Reinstall Python and check "Add Python to PATH" on the first installer screen.

**"venv\Scripts\activate" fails**
→ Make sure you are in the right folder: `cd %USERPROFILE%\Desktop\copy-trading`

**"No module named 'webull'"**
→ Virtual environment not activated. Run `venv\Scripts\activate` first.

**"Token still pending" loops forever**
→ Open Webull mobile → Profile → Settings → API Permissions and approve the request.

**Bot is running but Baiastan says signals aren't arriving**
→ Check that `firebase_credentials.json` is in the `copy-trading` folder and
`.env` has the correct `FIREBASE_DATABASE_URL`.

---

## Security notes

- The leader bot only **reads** your Webull positions — it cannot place, modify,
  or cancel any of your orders
- You trade completely normally; the bot is read-only
- Your credentials stay on your computer and are only sent to Webull's own servers
- Never share or upload `conf\token.txt`, `firebase_credentials.json`, or `.env`
- Those three files are excluded from Git automatically (`.gitignore`)

---

## For AI assistants reading this

If you are helping debug or extend this project, here is the full context:

- **Tech stack:** Python, Webull OpenAPI SDK (`webull-openapi-python-sdk`),
  Firebase Realtime Database (`firebase-admin`), Streamlit dashboard
- **Auth:** HMAC-SHA1 via `ApiClient(APP_KEY, APP_SECRET, 'us')`. Token stored
  in `conf/token.txt` after `step1_auth.py` approval flow
- **Leader bot:** `step3_leader_bot.py` — polls `account_v2.get_account_list()`
  and positions/orders every 1 second, diffs state, pushes signals to Firebase
- **Follower bot:** `follower_bot.py` — reads Firebase signals, applies size
  multiplier and slippage guard, places orders via `order_v2.place_option()`
- **Signal schema:** `{event_type, action, ticker, symbol, option_type,
  strike_price, option_expire_date, instrument_id, qty, price, order_type,
  stop_price, time_in_force, leader_client_order_id, timestamp, processed}`
- **Order tracking:** `order_map` dict (leader_oid → follower_oid),
  `symbol_orders` dict (symbol → [follower_oids]) for cancel-on-close
- **Market orders** for OPEN/CLOSE; **LIMIT/STOP_LOSS_LIMIT** for SL/TP
- **Slippage guard** on OPEN only — fetches live ask via
  `trade_instrument.get_trade_instrument_detail(instrument_id)`
- **Firebase path:** `copy_trading/signals` (signals), `copy_trading/status`
  (follower settings: `copy_enabled`, `dry_run`, `size_multiplier`,
  `spread_buffer`, `max_slippage_pct`, `max_signal_age`)
- **Test suite:** `tests/run_all.py` — run before enabling live trading each day
- **Future plans:** see `FUTURE_PLANS.md` — multi-follower SaaS roadmap
