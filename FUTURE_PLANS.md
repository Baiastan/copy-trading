# Future Plans — Multi-Follower / SaaS

## Current State (v1)
- One leader (friend trades on Webull)
- One follower (Baiastan copies via Firebase relay)
- Follower bot runs locally on Baiastan's machine
- Firebase is the signal broadcast channel
- Dashboard (Streamlit) controls: on/off, dry run, size multiplier, slippage guard, signal age

---

## Goal: Sell access to other followers

Allow paying customers to also copy the same leader's trades automatically.

---

## Architecture (what needs to change)

### What already scales for free
- Firebase signals are a broadcast — 100 followers can read the same signal simultaneously
- No changes needed to the leader bot (`step3_leader_bot.py`)
- The follower bot code is the same for every customer — only their `.env` differs

### What needs to be built

#### 1. Per-customer Firebase namespace
Right now all settings live at `copy_trading/status`. With multiple followers each needs
their own settings (size multiplier, dry run toggle, etc.):

```
copy_trading/
  signals/              ← shared, all followers read this
  followers/
    {customer_id}/
      status/           ← each customer's own controls
      heartbeat/
```

#### 2. Firebase access control
Add security rules so only verified subscribers can read `copy_trading/signals`.
Options:
- Issue each customer a read-only Firebase service account JSON
- Use Firebase custom tokens tied to a subscription status
- Revoke access instantly when subscription lapses

#### 3. Per-customer dashboard
Each customer gets their own Streamlit dashboard pointed at their
`copy_trading/followers/{customer_id}/` namespace.

#### 4. Subscription management
Simple approach: maintain a list of active customer IDs in Firebase.
Follower bot checks its own ID is still active on each poll cycle.
If revoked, bot stops and logs "subscription inactive."

---

## Webull Developer Credentials

### Current understanding
- `APP_KEY` / `APP_SECRET` identify the **application**, not the trader
- Each follower authenticates with their **own Webull account** (their own token)
- They could technically use Baiastan's developer keys as the app gateway

### Recommended approach for paying customers
Each customer registers their own free developer account at `developer.webull.com`
and gets their own APP_KEY / APP_SECRET. Benefits:
- Fully independent — Baiastan's account issues don't affect them
- No liability for how others use the API under Baiastan's key
- Webull ToS compliance (each developer registers their own app)

Applying is free and takes 1-2 days to approve.

---

## Two Business Models

| Model | Customer does | Baiastan runs | Complexity |
|-------|--------------|---------------|------------|
| **Self-hosted** | Runs bot on their own machine | Firebase + leader bot | Low — sell the bot + Firebase access |
| **Hosted SaaS** | Nothing (web UI only) | Everything on a server | High — cloud infra, encrypted credential storage |

**Start with self-hosted.** Customer downloads the bot, runs `step1_auth.py` once
to authenticate their Webull account, and the bot runs on their machine.
No server costs beyond Firebase (free tier handles high volume).

---

## Onboarding Flow for a New Customer (self-hosted)

1. Customer signs up / pays
2. They get: the bot repo + a Firebase credentials JSON (read-only, their own)
3. They apply for Webull developer credentials (or use a shared key for early testers)
4. They fill in their `.env` with their own Webull keys and account ID
5. They run `step1_auth.py` once to authenticate
6. They run `python follower_bot.py` — done, they're live
7. They get access to their own dashboard URL

---

## Files to Create When Ready

- `onboarding/setup_customer.py` — script to provision a new customer in Firebase
- `onboarding/revoke_customer.py` — script to revoke access
- `firebase_rules.json` — security rules template
- `dashboard_customer.py` — per-customer dashboard variant
- `follower_bot.py` — update to read from `followers/{customer_id}/` namespace

---

## Notes from original build

- Signal max age: 4 seconds (critical for 0DTE options with 0.2-0.3 delta)
- Market orders for OPEN/CLOSE (safe on 0DTE — spreads are 0.01 cents)
- Limit/stop orders for SL/TP (mirrored exactly from leader, no price adjustment for now)
- Slippage guard on OPEN only — if price moved more than X% from leader's fill, skip
- Size multiplier: follower copies a fraction of leader's size (e.g., 0.5x = half)
- SL/TP prices are copied exactly as leader placed them (no offset adjustment yet)
  → Future: optionally shift SL by the entry price delta if follower fills at different price
