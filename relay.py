"""
Firebase Realtime Database relay.
Leader pushes trade signals here; follower reads and marks them processed.

Database structure:
  copy_trading/
    signals/{id}/         ← one entry per trade event
      timestamp           ← ISO string, ET
      event_type          ← "OPEN" | "CLOSE"
      is_option           ← bool
      ticker              ← underlying symbol (e.g. "SPY")
      action              ← "BUY" | "SELL"
      qty                 ← int (contracts or shares)
      price               ← float (entry/exit price for reference)
      option_type         ← "CALL" | "PUT" (options only)
      strike              ← float (options only)
      expiry              ← "YYYY-MM-DD" (options only)
      option_id           ← int Webull tickerId (options only)
      processed           ← bool (follower sets true after executing)
      follower_status     ← "ok" | "error: <msg>" (follower writes back)
    status/
      leader_heartbeat    ← ISO timestamp (leader updates every poll cycle)
      follower_heartbeat  ← ISO timestamp (follower updates every poll cycle)
      copy_enabled        ← bool (dashboard can toggle)
      size_multiplier     ← float (dashboard can adjust)
"""

import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

_initialized = False


def init_firebase(credentials_path: str, database_url: str):
    global _initialized
    if _initialized:
        return
    cred = credentials.Certificate(credentials_path)
    firebase_admin.initialize_app(cred, {"databaseURL": database_url})
    _initialized = True
    logger.info("Firebase initialized.")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Leader helpers ──────────────────────────────────────────────────────────

def push_signal(signal: dict) -> str:
    """Push a trade signal and return its Firebase key."""
    signal["timestamp"] = _now_iso()
    signal["processed"] = False
    ref = db.reference("copy_trading/signals")
    new_ref = ref.push(signal)
    logger.info(f"Signal pushed: {signal}")
    return new_ref.key


def update_leader_heartbeat():
    db.reference("copy_trading/status/leader_heartbeat").set(_now_iso())


# ─── Follower helpers ─────────────────────────────────────────────────────────

def get_pending_signals() -> list[dict]:
    """Return all unprocessed signals ordered by timestamp."""
    ref = db.reference("copy_trading/signals")
    data = ref.get() or {}
    pending = []
    for key, val in data.items():
        if isinstance(val, dict) and not val.get("processed", False):
            val["_key"] = key
            pending.append(val)
    # Process oldest first
    pending.sort(key=lambda x: x.get("timestamp", ""))
    return pending


def mark_signal_processed(key: str, status: str = "ok"):
    db.reference(f"copy_trading/signals/{key}").update({
        "processed": True,
        "follower_status": status,
        "processed_at": _now_iso(),
    })


def update_follower_heartbeat():
    db.reference("copy_trading/status/follower_heartbeat").set(_now_iso())


# ─── Shared / dashboard helpers ───────────────────────────────────────────────

def get_status() -> dict:
    return db.reference("copy_trading/status").get() or {}


def set_copy_enabled(enabled: bool):
    db.reference("copy_trading/status/copy_enabled").set(enabled)


def set_size_multiplier(multiplier: float):
    db.reference("copy_trading/status/size_multiplier").set(multiplier)


def set_spread_buffer(buffer: float):
    """Extra $ added to BUY limit price (and subtracted from SELL) to improve fill chance."""
    db.reference("copy_trading/status/spread_buffer").set(buffer)


def get_recent_signals(limit: int = 20) -> list[dict]:
    ref = db.reference("copy_trading/signals")
    data = ref.get() or {}
    signals = []
    for key, val in data.items():
        if isinstance(val, dict):
            val["_key"] = key
            signals.append(val)
    signals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return signals[:limit]
