"""Public Kalshi 15-minute Up/Down discovery. Read-only. No authentication."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from config import SERIES_TICKERS, SKIP_SERIES
from utils import window_bounds

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
HEADERS = {"User-Agent": "PM15-research/0.1", "Accept": "application/json"}


def _normalize_price(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        x = float(val)
    except (TypeError, ValueError):
        return 0.0
    if x > 1.5:
        x = x / 100.0
    return max(0.0, min(1.0, x))


def _get_json(path: str, params: dict | None = None, retries: int = 3) -> dict:
    url = f"{BASE_URL}{path}"
    last_exc: Exception | None = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=12)
            if r.status_code == 429:
                time.sleep(2 ** (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(0.6 * (i + 1))
    if last_exc:
        raise last_exc
    return {}


def _get_markets(series_ticker: str, status: str = "open", limit: int = 200) -> list[dict]:
    if series_ticker in SKIP_SERIES:
        return []
    markets: list[dict] = []
    cursor = None
    params: dict[str, Any] = {"series_ticker": series_ticker, "status": status, "limit": limit}
    for _ in range(4):
        if cursor:
            params["cursor"] = cursor
        try:
            data = _get_json("/markets", params)
        except Exception:
            break
        batch = data.get("markets") or []
        markets.extend(batch)
        cursor = data.get("cursor")
        if not cursor or not batch:
            break
    return markets


def _which_window(close_time_str: str, now: datetime) -> str | None:
    try:
        close = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
    except Exception:
        return None
    if close.tzinfo is None:
        close = close.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    current_start, current_end, next_end = window_bounds(now)
    if current_start < close <= current_end:
        return "current"
    if current_end < close <= next_end:
        return "next"
    return None


def _extract_strike(m: dict) -> float | None:
    for key in ("floor_strike", "cap_strike", "strike_price", "strike"):
        val = m.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None


def fetch_15m_market(asset: str, which: str = "current") -> dict | None:
    """
    Return the live Up/Down ticket for current or next 15-minute window.

    Fields: ticker, event_ticker, strike, yes_bid, yes_ask, mid, volume,
            close_time, title, n_raw
    """
    series = SERIES_TICKERS.get(asset)
    if not series:
        return None
    now = datetime.now(timezone.utc)
    try:
        markets = _get_markets(series)
    except Exception:
        return None

    candidates = []
    for m in markets:
        close_time = m.get("close_time") or m.get("expected_expiration_time") or m.get("latest_expiration_time")
        if not close_time:
            continue
        bucket = _which_window(str(close_time), now)
        if bucket != which:
            continue
        strike = _extract_strike(m)
        yes_bid = _normalize_price(m.get("yes_bid_dollars") or m.get("yes_bid"))
        yes_ask = _normalize_price(m.get("yes_ask_dollars") or m.get("yes_ask"))
        mid = 0.0
        if yes_bid > 0 and yes_ask > 0:
            mid = (yes_bid + yes_ask) / 2.0
        elif yes_ask > 0:
            mid = yes_ask
        elif yes_bid > 0:
            mid = yes_bid
        candidates.append(
            {
                "ticker": m.get("ticker"),
                "event_ticker": m.get("event_ticker"),
                "title": m.get("title") or m.get("yes_sub_title") or "",
                "strike": strike,
                "yes_bid": yes_bid,
                "yes_ask": yes_ask,
                "mid": round(mid, 4),
                "spread": round(max(0.0, yes_ask - yes_bid), 4) if yes_ask and yes_bid else 0.0,
                "volume": m.get("volume_fp") or m.get("volume"),
                "close_time": close_time,
                "status": m.get("status"),
            }
        )

    if not candidates:
        return None
    # Prefer the market that looks like the "Yes / Up" side (higher mid if two)
    candidates.sort(key=lambda x: (x["strike"] is not None, x["mid"]), reverse=True)
    return candidates[0]


def fetch_official_candles(ticker: str, period_interval: int = 1) -> list[dict]:
    """Best-effort official 1-minute candles for an open market ticker."""
    if not ticker:
        return []
    try:
        data = _get_json(
            f"/markets/{ticker}/candlesticks",
            params={"period_interval": period_interval},
        )
    except Exception:
        return []
    rows = data.get("candlesticks") or data.get("candles") or []
    out = []
    for row in rows:
        # Support a few shapes
        close = None
        ts = None
        if isinstance(row, dict):
            price = row.get("price") or row.get("yes_bid") or {}
            if isinstance(price, dict):
                close = price.get("close_dollars") or price.get("close")
            close = close or row.get("close_dollars") or row.get("close")
            ts = row.get("end_period_ts") or row.get("ts") or row.get("time")
        if close is None:
            continue
        try:
            close_f = float(close)
        except (TypeError, ValueError):
            continue
        if close_f > 1.5:
            close_f = close_f / 100.0
        out.append({"ts": ts, "close": max(0.0, min(1.0, close_f))})
    return out
