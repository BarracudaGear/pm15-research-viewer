"""Kalshi 15-minute research dashboard. Read-only. Password gated."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import streamlit as st

from config import ASSETS, BOOK_A, COMMODITY_ASSETS, assess_coverage, is_book_a, taker_fee
from data.kalshi_live import fetch_15m_market, fetch_official_candles
from data.spot import fetch_recent_closes, fetch_spot, price_action_levels
from engines.direction import predict_direction
from engines.safety import predict_safety
from gates import evaluate_gates
from overlays import experimental_adjustments
from utils import (
    fmt_mag_pct,
    fmt_usd,
    format_mmss,
    format_price,
    minutes_remaining_in_window,
    seconds_remaining_in_window,
)

st.set_page_config(page_title="Kalshi 15-Min Research", page_icon="P", layout="wide")


def _gate() -> bool:
    if st.session_state.get("authed"):
        return True
    try:
        expected = st.secrets["APP_PASSWORD"]
    except Exception:
        expected = None
    st.title("15-Min Research")
    st.caption("Private viewer.")
    if not expected:
        st.error("APP_PASSWORD is not set in Streamlit secrets.")
        return False
    pwd = st.text_input("Password", type="password")
    if pwd == str(expected):
        st.session_state.authed = True
        st.rerun()
    if pwd:
        st.error("Wrong password")
    return False


if not _gate():
    st.stop()

st.sidebar.title("15-Min Research")
st.sidebar.caption("Read-only | Brain B1 | No keys | No paper")

asset = st.sidebar.selectbox("Asset", ASSETS, index=0)
which = st.sidebar.radio("Window", ["current", "next"], index=0, horizontal=True)

st.sidebar.markdown("### Coverage")
rows = []
for a in ASSETS:
    info = assess_coverage(a)
    rows.append(
        {
            "Asset": a,
            "Book": "A" if a in BOOK_A else "B",
            "Status": info["status"].value if hasattr(info["status"], "value") else info["status"],
            "Rows": info["row_count"],
        }
    )
st.sidebar.dataframe(rows, hide_index=True, use_container_width=True)

auto = st.sidebar.checkbox("Auto-refresh (while tab open)", value=True)
if st.sidebar.button("Refresh now"):
    st.rerun()

now = datetime.now(timezone.utc)
secs_left = seconds_remaining_in_window(now)
mins_left = minutes_remaining_in_window(now)

with st.spinner("Fetching 15-minute ticket and spot..."):
    market = fetch_15m_market(asset, which)
    spot = fetch_spot(asset)
    recent_closes = fetch_recent_closes(asset, granularity=60, limit=30)
    pa = price_action_levels(recent_closes)
    official_candles = fetch_official_candles(market["ticker"]) if market and market.get("ticker") else []
    n_candles = len(official_candles) if official_candles else min(len(recent_closes), 15)

if spot is None:
    spot = 0.0

strike = market.get("strike") if market else None
yes_bid = market.get("yes_bid", 0.0) if market else 0.0
yes_ask = market.get("yes_ask", 0.0) if market else 0.0
mid = market.get("mid", 0.5) if market else 0.5
spread = market.get("spread", 0.0) if market else 0.0

safety = predict_safety(asset, spot, mins_left if which == "current" else 15.0, recent_closes or None)
direction = predict_direction(
    mid=mid,
    strike=strike,
    spot=spot,
    recent_closes=recent_closes or None,
    minutes_remaining=mins_left if which == "current" else 15.0,
)

_ = experimental_adjustments(direction.p_up, enabled=False)

gate = evaluate_gates(
    asset=asset,
    safety_pass=safety.gate_pass,
    direction_pass=direction.gate_pass,
    p_up=direction.p_up,
    p_down=direction.p_down,
    regime=safety.regime,
    seconds_left=secs_left if which == "current" else 15 * 60,
    n_candles=n_candles,
    yes_bid=yes_bid,
    yes_ask=yes_ask,
    spread=spread,
)

fee_yes = taker_fee(yes_ask if yes_ask > 0 else 0.5)
need_yes = (yes_ask + fee_yes + 0.01) if yes_ask > 0 else None

anchor = strike if strike else spot
half = (safety.magnitude_pct + safety.uncertainty_pct) / 100.0 * anchor if anchor else 0.0
stat_floor = anchor - half if anchor else None
stat_ceil = anchor + half if anchor else None

book_tag = "Book A" if is_book_a(asset) else "Book B (quotes only)"
st.title(f"{asset} | 15-Minute Up/Down")
st.caption(f"{book_tag} | Brain B1 | Read-only research viewer")
st.markdown(
    f"**UTC now:** `{now.strftime('%Y-%m-%d %H:%M:%S')}` | "
    f"**Time left in current window:** `{format_mmss(secs_left)}`"
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Spot (public proxy)", format_price(spot) if spot else "-")
c2.metric("Price-to-beat", format_price(strike) if strike else "-")
c3.metric("Kalshi mid", f"{mid:.3f}" if market else "-")
c4.metric("Yes bid / ask", f"{yes_bid:.2f} / {yes_ask:.2f}" if market else "-")

if asset in COMMODITY_ASSETS and spot == 0.0:
    st.info("No public spot proxy for this metal/oil name. Using Kalshi tape only.")
if market is None:
    st.warning("No open 15-minute ticket found for this asset/window (or API throttled).")

left, right = st.columns([3, 2])
mag_pct = safety.magnitude_pct
unc_pct = safety.uncertainty_pct
mag_usd = spot * (mag_pct / 100.0) if spot else 0.0
unc_usd = spot * (unc_pct / 100.0) if spot else 0.0

with left:
    st.subheader("Safety / Volatility")
    if safety.degraded:
        st.warning(f"Degraded / partial - {safety.coverage_message}")
    else:
        st.success(safety.coverage_message)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Magnitude", fmt_mag_pct(mag_pct))
    m2.metric("In $", fmt_usd(mag_usd, spot) if spot else "-")
    m3.metric("Uncertainty %", f"+/-{fmt_mag_pct(unc_pct)}")
    m4.metric("Uncertainty $", fmt_usd(unc_usd, spot) if spot else "-")
    regime_str = safety.regime.upper() if safety.regime != "unknown" else "UNKNOWN"
    if safety.degraded and safety.regime != "unknown":
        regime_str += "*"
    pct_str = f" (p{safety.regime_percentile:.0f})" if safety.regime_percentile is not None else ""
    st.caption(
        f"Condition: `{safety.condition}` | Regime: **{regime_str}**{pct_str} | "
        f"Gate: {'PASS' if safety.gate_pass else 'FAIL'}"
    )
    st.caption(safety.details)

with right:
    st.subheader("Direction / Trend (B1)")
    d1, d2, d3 = st.columns(3)
    d1.metric("P(up)", f"{direction.p_up:.3f}")
    d2.metric("P(down)", f"{direction.p_down:.3f}")
    d3.metric("Kalshi mid", f"{direction.mid:.3f}")
    st.caption(
        f"Picture: `{direction.picture}` | Gate: {'PASS' if direction.gate_pass else 'FAIL'}"
    )
    if direction.dist_to_strike_pct is not None:
        st.caption(f"Spot vs strike: {direction.dist_to_strike_pct:+.3f}%")
    st.caption(direction.details)

st.markdown("#### Floors and Ceilings")
fc1, fc2 = st.columns(2)
with fc1:
    st.markdown("**Statistical band**")
    if stat_floor is not None and stat_ceil is not None:
        st.write(f"Floor ~ `{format_price(stat_floor)}`")
        st.write(f"Ceiling ~ `{format_price(stat_ceil)}`")
        st.caption("anchor (strike or spot) +/- (magnitude + uncertainty)")
    else:
        st.write("-")
with fc2:
    st.markdown("**Price-action levels**")
    if pa.get("window_low") is not None:
        st.write(f"Window low  ~ `{format_price(pa['window_low'])}`")
        st.write(f"Window high ~ `{format_price(pa['window_high'])}`")
        if pa.get("prior_low") is not None:
            st.caption(
                f"Prior 15m low `{format_price(pa['prior_low'])}` | "
                f"high `{format_price(pa['prior_high'])}`"
            )
    else:
        st.write("No short tape yet")
        st.caption("Needs a public 1-minute series")

st.markdown("#### After-fee strip (1 ticket, taker)")
if market and yes_ask > 0:
    st.write(
        f"Yes ask `{yes_ask:.3f}` + taker fee `{fee_yes:.4f}` + 1c buffer "
        f"= need **P(up) >= {need_yes:.3f}** to even consider a YES call."
    )
    st.caption("Lopsided tape (90c+) almost never clears this test. That is intentional.")
else:
    st.caption("No live ask to score.")

st.markdown("---")
if gate.outcome == "UP":
    st.success(f"**UP** - {gate.reason}")
elif gate.outcome == "DOWN":
    st.success(f"**DOWN** - {gate.reason}")
elif gate.outcome == "SIDEWAYS":
    st.success(f"**SIDEWAYS** - {gate.reason}")
else:
    st.info(f"**NO CALL** - {gate.reason}")

if market:
    st.caption(
        f"Ticker `{market.get('ticker')}` | event `{market.get('event_ticker')}` | "
        f"close `{market.get('close_time')}` | official candles seen `{n_candles}`"
    )

st.markdown("---")
st.caption(
    "Research prototype only. Public spot is a proxy, not the official print. "
    "No trading, no keys, no paper journal writes."
)

if auto:
    time.sleep(25)
    st.rerun()
