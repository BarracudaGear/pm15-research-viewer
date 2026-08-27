"""Safety / Volatility engine retuned for a 15-minute remaining window."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from config import (
    ASSET_TO_EXCHANGE_SYMBOL,
    CoverageStatus,
    DB_PATH,
    SAFETY_QUIET_MAX_MOVE_PCT,
    WINDOW_SECONDS,
    assess_coverage,
)

Condition = Literal["quiet", "normal", "shock", "stale", "incomplete"]
Regime = Literal["low", "mid-low", "mid-high", "high", "unknown"]


@dataclass
class SafetyResult:
    magnitude_pct: float
    uncertainty_pct: float
    condition: Condition
    regime: Regime
    regime_percentile: float | None
    gate_pass: bool
    degraded: bool
    details: str
    coverage_message: str


def _percentile_to_regime(p: float) -> Regime:
    if p < 25:
        return "low"
    if p < 50:
        return "mid-low"
    if p < 75:
        return "mid-high"
    return "high"


def _live_fallback_magnitude(recent_closes: list[float] | None, minutes_remaining: float) -> tuple[float, float]:
    remaining_frac = max(minutes_remaining / 15.0, 0.05)
    if not recent_closes or len(recent_closes) < 5:
        mag = 0.25 * remaining_frac
        return max(mag, 0.02), mag * 0.6
    rets = np.diff(np.log(np.asarray(recent_closes[-30:], dtype=float)))
    if len(rets) < 3:
        mag = 0.25 * remaining_frac
        return max(mag, 0.02), mag * 0.6
    vol_15 = float(np.std(rets)) * math.sqrt(15)
    mag = vol_15 * 100.0 * math.sqrt(remaining_frac) * 1.1
    return max(mag, 0.02), max(mag * 0.45, 0.015)


def predict_safety(
    asset: str,
    spot: float,
    minutes_remaining: float,
    recent_closes: list[float] | None = None,
) -> SafetyResult:
    coverage = assess_coverage(asset)
    degraded = coverage["status"] != CoverageStatus.FULL

    if minutes_remaining <= 0.4:
        return SafetyResult(
            0.01, 0.02, "incomplete", "unknown", None, False, degraded,
            "Too little time remaining", coverage["message"],
        )

    if coverage["status"] in (CoverageStatus.FULL, CoverageStatus.PARTIAL):
        try:
            from btcq.data.storage import load_ohlcv

            exchange, symbol = ASSET_TO_EXCHANGE_SYMBOL[asset]
            start = (pd.Timestamp.utcnow() - pd.Timedelta(days=45)).isoformat()
            df = load_ohlcv(DB_PATH, exchange, symbol, start=start, read_only=True)
            if len(df) > 50:
                df = df.copy()
                df["range_pct"] = 100.0 * (df["high"] - df["low"]) / df["open"].replace(0, np.nan)
                df = df.dropna(subset=["range_pct"])
                # Hourly ranges scaled down to a 15-minute slice
                now = pd.Timestamp.utcnow()
                df["dow"] = df["ts_utc"].dt.dayofweek
                df["hour"] = df["ts_utc"].dt.hour
                same_cell = df[(df["dow"] == now.dayofweek) & (df["hour"] == now.hour)]["range_pct"]
                if len(same_cell) >= 8:
                    hour_mag = float(same_cell.median())
                    unc_h = float(same_cell.quantile(0.75) - same_cell.quantile(0.25)) / 2.0
                    ref = same_cell
                else:
                    hour_mag = float(df["range_pct"].median())
                    unc_h = float(df["range_pct"].std()) * 0.45
                    ref = df["range_pct"]

                remaining_frac = max(minutes_remaining / 15.0, 0.05)
                # 15-min piece of an hour ≈ 0.5 * hourly range as a starting scale
                mag_full_15 = hour_mag * 0.5
                mag = mag_full_15 * math.sqrt(remaining_frac)
                unc = max(unc_h * 0.5 * math.sqrt(remaining_frac), 0.02)

                recent_vol = float(df["range_pct"].tail(24).median()) * 0.5
                if mag < 0.45 * recent_vol or mag < SAFETY_QUIET_MAX_MOVE_PCT:
                    condition: Condition = "quiet"
                elif mag > 1.9 * recent_vol:
                    condition = "shock"
                else:
                    condition = "normal"

                try:
                    pct = float((ref * 0.5 < mag_full_15).mean() * 100.0)
                    regime = _percentile_to_regime(pct)
                    regime_pct = round(pct, 1)
                except Exception:
                    regime, regime_pct = "unknown", None

                gate = condition in ("quiet", "normal") and minutes_remaining > 1.5
                is_partial = coverage["status"] == CoverageStatus.PARTIAL
                return SafetyResult(
                    magnitude_pct=round(mag, 3),
                    uncertainty_pct=round(unc, 3),
                    condition=condition,
                    regime=regime,
                    regime_percentile=regime_pct,
                    gate_pass=gate,
                    degraded=is_partial,
                    details=f"Hourly history scaled to 15m (n={len(df)})" + (" [partial]" if is_partial else ""),
                    coverage_message=coverage["message"],
                )
        except Exception as exc:  # noqa: BLE001
            coverage = {**coverage, "message": coverage["message"] + f" | hist error: {exc}"}

    mag, unc = _live_fallback_magnitude(recent_closes, minutes_remaining)
    if coverage["status"] == CoverageStatus.MISSING:
        condition = "stale"
    elif minutes_remaining < 2:
        condition = "incomplete"
    else:
        condition = "normal"
    gate = condition in ("quiet", "normal") and minutes_remaining > 2 and mag < 1.2
    return SafetyResult(
        magnitude_pct=round(mag, 3),
        uncertainty_pct=round(unc, 3),
        condition=condition,
        regime="unknown",
        regime_percentile=None,
        gate_pass=gate,
        degraded=True,
        details="Live-only or commodity / thin-history estimate",
        coverage_message=coverage["message"],
    )
