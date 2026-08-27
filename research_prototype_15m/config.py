"""Configuration for the 15-minute research prototype."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "market.db"

BOOK_A = ["BTC", "ETH", "SOL", "ZEC", "XRP", "NEAR", "HYPE", "DOGE", "BNB", "GOLD", "SILVER", "WTI"]
BOOK_B = ["ADA", "BCH", "TON"]
ASSETS = BOOK_A + BOOK_B

SERIES_TICKERS: dict[str, str] = {
    "BTC": "KXBTC15M",
    "ETH": "KXETH15M",
    "SOL": "KXSOL15M",
    "ZEC": "KXZEC15M",
    "XRP": "KXXRP15M",
    "NEAR": "KXNEAR15M",
    "HYPE": "KXHYPE15M",
    "DOGE": "KXDOGE15M",
    "BNB": "KXBNB15M",
    "GOLD": "KXGOLD15M",
    "SILVER": "KXSILVER15M",
    "WTI": "KXWTI15M",
    "ADA": "KXADA15M",
    "BCH": "KXBCH15M",
    "TON": "KXTON15M",
}

SKIP_SERIES = {"KXCRYPTOLEAD15M", "KXCRYPTOCOMP15M"}

ASSET_TO_EXCHANGE_SYMBOL: dict[str, tuple[str, str]] = {
    "BTC": ("coinbase", "BTC/USD"),
    "ETH": ("coinbase", "ETH/USD"),
    "SOL": ("coinbase", "SOL/USD"),
    "XRP": ("coinbase", "XRP/USD"),
    "DOGE": ("coinbase", "DOGE/USD"),
    "BNB": ("binance", "BNB/USD"),
    "HYPE": ("hyperliquid", "HYPE/USD"),
    "ZEC": ("coinbase", "ZEC/USD"),
    "NEAR": ("coinbase", "NEAR/USD"),
    "ADA": ("coinbase", "ADA/USD"),
    "BCH": ("coinbase", "BCH/USD"),
    "TON": ("coinbase", "TON/USD"),
}

SPOT_SYMBOLS: dict[str, str] = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "BNB": "BNB-USD",
    "HYPE": "HYPE-USD",
    "ZEC": "ZEC-USD",
    "NEAR": "NEAR-USD",
    "ADA": "ADA-USD",
    "BCH": "BCH-USD",
    "TON": "TON-USD",
}

COMMODITY_ASSETS = {"GOLD", "SILVER", "WTI"}

DIRECTION_CONFIDENCE_THRESHOLD = 0.56
SAFETY_QUIET_MAX_MOVE_PCT = 0.12
SPREAD_CAP_BTC_ETH = 0.04
SPREAD_CAP_OTHER = 0.06
TAKER_FEE_K = 0.07
EDGE_BUFFER = 0.01
MIN_CANDLES_FOR_CALL = 5
NO_NEW_TICKET_SECONDS = 90
WINDOW_SECONDS = 15 * 60

MIN_HOURS_FOR_FULL = 1500
MIN_HOURS_FOR_PARTIAL = 200
RECENT_DAYS = 30


class CoverageStatus(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    MISSING = "missing"


def is_book_a(asset: str) -> bool:
    return asset in BOOK_A


def spread_cap(asset: str) -> float:
    return SPREAD_CAP_BTC_ETH if asset in ("BTC", "ETH") else SPREAD_CAP_OTHER


def taker_fee(price: float) -> float:
    p = min(max(price, 0.01), 0.99)
    return TAKER_FEE_K * p * (1.0 - p)


def assess_coverage(asset: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    if asset in COMMODITY_ASSETS:
        return {
            "status": CoverageStatus.MISSING,
            "row_count": 0,
            "last_ts": None,
            "has_recent": False,
            "message": "No coin-style history for this commodity – degraded mode",
        }
    if not db_path.exists():
        return {
            "status": CoverageStatus.MISSING,
            "row_count": 0,
            "last_ts": None,
            "has_recent": False,
            "message": "No historical database found – degraded mode",
        }
    mapping = ASSET_TO_EXCHANGE_SYMBOL.get(asset)
    if mapping is None:
        return {
            "status": CoverageStatus.MISSING,
            "row_count": 0,
            "last_ts": None,
            "has_recent": False,
            "message": f"Asset {asset} not mapped – degraded mode",
        }
    exchange, symbol = mapping
    try:
        from btcq.data.storage import count_rows, load_ohlcv
        import pandas as pd

        n = count_rows(db_path, exchange=exchange, symbol=symbol)
        start = (pd.Timestamp.utcnow() - pd.Timedelta(days=30)).isoformat()
        recent = load_ohlcv(db_path, exchange, symbol, start=start, read_only=True)
        last_ts = recent["ts_utc"].max() if not recent.empty else None
        has_recent = last_ts is not None and (pd.Timestamp.utcnow() - last_ts).days < RECENT_DAYS
    except Exception as exc:  # noqa: BLE001
        return {
            "status": CoverageStatus.MISSING,
            "row_count": 0,
            "last_ts": None,
            "has_recent": False,
            "message": f"Could not read historical data ({exc}) – degraded mode",
        }

    if n >= MIN_HOURS_FOR_FULL and has_recent:
        status, msg = CoverageStatus.FULL, f"Full historical context ({n:,} hours)"
    elif n >= MIN_HOURS_FOR_FULL:
        status, msg = CoverageStatus.PARTIAL, f"Solid history ({n:,} hours) but not recent – partial"
    elif n >= MIN_HOURS_FOR_PARTIAL:
        status, msg = CoverageStatus.PARTIAL, f"Partial history ({n:,} hours) – some degradation"
    else:
        status, msg = CoverageStatus.MISSING, "Insufficient historical data – degraded mode"

    return {
        "status": status,
        "row_count": n,
        "last_ts": last_ts,
        "has_recent": has_recent,
        "message": msg,
    }
