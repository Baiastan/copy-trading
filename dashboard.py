"""
Copy-Trading Dashboard
Run with:  streamlit run dashboard.py
"""

import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime, timezone
import pandas as pd

from config import FIREBASE_DATABASE_URL, FIREBASE_CREDENTIALS_PATH
FIREBASE_CREDENTIALS = FIREBASE_CREDENTIALS_PATH

st.set_page_config(page_title="Copy Trading", page_icon="📈", layout="wide")


# ── Firebase init ─────────────────────────────────────────────────────────────

@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS)
        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DATABASE_URL})
    return db

firebase_db = init_firebase()


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_status() -> dict:
    return firebase_db.reference('copy_trading/status').get() or {}


def get_recent_signals(limit=30) -> list:
    data = firebase_db.reference('copy_trading/signals').get() or {}
    signals = []
    for key, val in data.items():
        if isinstance(val, dict):
            val['_key'] = key
            signals.append(val)
    signals.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return signals[:limit]


def seconds_ago(iso_ts: str) -> float | None:
    if not iso_ts:
        return None
    try:
        t = datetime.fromisoformat(iso_ts)
        return (datetime.now(timezone.utc) - t).total_seconds()
    except Exception:
        return None


def heartbeat_badge(label: str, iso_ts: str, threshold: int = 30):
    age = seconds_ago(iso_ts)
    if age is None:
        st.error(f"🔴 {label}: Never connected")
    elif age < threshold:
        st.success(f"🟢 {label}: Online ({int(age)}s ago)")
    else:
        st.warning(f"🟡 {label}: Last seen {int(age)}s ago")


# ── Layout ────────────────────────────────────────────────────────────────────

st.title("📈 Copy Trading Dashboard")

status = get_status()

# ── Status row ───────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    heartbeat_badge("Leader", status.get('leader_heartbeat', ''))
with col2:
    heartbeat_badge("Follower", status.get('follower_heartbeat', ''))
with col3:
    copy_on = status.get('copy_enabled', True)
    if copy_on:
        st.success("🟢 Copy Trading: ENABLED")
    else:
        st.error("🔴 Copy Trading: DISABLED")

st.divider()

# ── Controls ─────────────────────────────────────────────────────────────────
left, right = st.columns([1, 2])

with left:
    st.subheader("Controls")

    # On/Off toggle
    new_enabled = st.toggle(
        "Copy Trading Enabled",
        value=bool(status.get('copy_enabled', True)),
        key='copy_toggle'
    )
    if new_enabled != bool(status.get('copy_enabled', True)):
        firebase_db.reference('copy_trading/status/copy_enabled').set(new_enabled)
        st.rerun()

    st.divider()

    # Size multiplier
    current_mult = float(status.get('size_multiplier', 1.0))
    new_mult = st.slider(
        "Size Multiplier",
        min_value=0.1,
        max_value=3.0,
        value=current_mult,
        step=0.1,
        help="1.0 = copy exact size. 0.5 = half size. 2.0 = double."
    )
    if abs(new_mult - current_mult) > 0.001:
        firebase_db.reference('copy_trading/status/size_multiplier').set(round(new_mult, 2))
        st.success(f"Multiplier set to {new_mult:.1f}x")

    st.divider()

    # Spread buffer
    current_buf = float(status.get('spread_buffer', 0.05))
    new_buf = st.number_input(
        "Spread Buffer ($)",
        min_value=0.0,
        max_value=2.0,
        value=current_buf,
        step=0.01,
        format="%.2f",
        help="Added to BUY limit price, subtracted from SELL. Compensates for latency."
    )
    if abs(new_buf - current_buf) > 0.001:
        firebase_db.reference('copy_trading/status/spread_buffer').set(round(new_buf, 3))
        st.success(f"Spread buffer set to ${new_buf:.2f}")

    st.divider()

    # Max signal age
    current_age = int(status.get('max_signal_age', 60))
    new_age = st.number_input(
        "Max Signal Age (seconds)",
        min_value=5,
        max_value=300,
        value=current_age,
        step=5,
        help="Ignore signals older than this. Prevents stale fills after a disconnect."
    )
    if new_age != current_age:
        firebase_db.reference('copy_trading/status/max_signal_age').set(new_age)
        st.success(f"Max signal age set to {new_age}s")

    st.divider()

    if st.button("🔄 Refresh Now"):
        st.rerun()


# ── Signal feed ───────────────────────────────────────────────────────────────
with right:
    st.subheader("Recent Signals")

    signals = get_recent_signals(30)

    if not signals:
        st.info("No signals yet. Waiting for leader to trade...")
    else:
        rows = []
        for s in signals:
            ts = s.get('timestamp', '')
            age = seconds_ago(ts)
            age_str = f"{int(age)}s ago" if age is not None else '—'

            if s.get('is_option'):
                asset = f"{s.get('ticker')} {s.get('option_type','')} ${s.get('strike','')} {s.get('expiry','')}"
            else:
                asset = s.get('ticker', '—')

            processed = s.get('processed', False)
            follower_status = s.get('follower_status', '—')

            if processed:
                status_icon = "✅" if 'ok' in str(follower_status).lower() else "⚠️"
            else:
                status_icon = "⏳"

            rows.append({
                'Time': age_str,
                'Event': s.get('event_type', ''),
                'Action': s.get('action', ''),
                'Asset': asset,
                'Qty': s.get('qty', ''),
                'Price': f"${s.get('price', 0):.2f}",
                'Status': f"{status_icon} {follower_status}",
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)


# ── Auto-refresh ──────────────────────────────────────────────────────────────
st.caption("Auto-refreshes every 10 seconds")

import time
time.sleep(10)
st.rerun()
