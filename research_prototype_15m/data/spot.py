"""Public spot + short 1-minute series. Read-only."""
from __future__ import annotations

import requests

from config import COMMODITY_ASSETS, SPOT_SYMBOLS


def fetch_coinbase_spot(product_id: str) -> float | None:
    url = f"https://api.coinbase.com/v2/prices/{product_id}/spot"
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        amount = r.json().get("data", {}).get("amount")
        return float(amount) if amount is not None else None
    except Exception:
        return None


def fetch_spot(asset: str) -> float | None:
    if asset in COMMODITY_ASSETS:
        return None
    product = SPOT_SYMBOLS.get(asset)
    if not product:
        return None
    px = fetch_coinbase_spot(product)
    if px is not None:
        return px
    return None


def fetch_recent_closes(asset: str, granularity: int = 60, limit: int = 30) -> list[float]:
    if asset in COMMODITY_ASSETS:
        return []
    product = SPOT_SYMBOLS.get(asset)
    if not product:
        return []
    url = f"https://api.exchange.coinbase.com/products/{product}/candles"
    try:
        r = requests.get(url, params={"granularity": granularity}, timeout=10)
        r.raise_for_status()
        rows = r.json()
        if not isinstance(rows, list) or not rows:
            return []
        closes = [float(row[4]) for row in rows[:limit] if len(row) >= 5]
        closes.reverse()
        return closes
    except Exception:
        return []


def price_action_levels(closes: list[float]) -> dict[str, float | None]:
    if not closes or len(closes) < 3:
        return {"window_high": None, "window_low": None, "prior_high": None, "prior_low": None}
    window = closes[-15:] if len(closes) >= 15 else closes
    prior = closes[-30:-15] if len(closes) >= 30 else closes[:-len(window)] if len(closes) > len(window) else []
    return {
        "window_high": max(window),
        "window_low": min(window),
        "prior_high": max(prior) if prior else None,
        "prior_low": min(prior) if prior else None,
    }
