"""Direction B1: Kalshi midpoint + jumpy/quiet, trend/sideways, distance-to-strike."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class DirectionResult:
    p_up: float
    p_down: float
    mid: float
    gate_pass: bool
    picture: str          # "trend-up" | "trend-down" | "sideways" | "jumpy" | "thin"
    details: str
    dist_to_strike_pct: float | None


def _tape_picture(closes: list[float], strike: float | None) -> tuple[str, float]:
    """Return (picture, lean_score in [-1, 1])."""
    if not closes or len(closes) < 3:
        return "thin", 0.0
    arr = np.asarray(closes[-15:], dtype=float)
    if np.any(arr <= 0):
        return "thin", 0.0
    rets = np.diff(np.log(arr))
    vol = float(np.std(rets)) if len(rets) else 0.0
    if vol > 0.004:  # very jumpy 1-minute tape
        return "jumpy", 0.0

    slope = float(np.log(arr[-1] / arr[0])) if arr[0] > 0 else 0.0
    up_frac = float(np.mean(rets > 0)) if len(rets) else 0.5

    dist = 0.0
    if strike and strike > 0:
        dist = (arr[-1] - strike) / strike

    lean = 0.45 * np.tanh(slope * 80.0) + 0.35 * (up_frac - 0.5) * 2 + 0.20 * np.tanh(dist * 80.0)

    if abs(lean) < 0.12:
        return "sideways", float(lean)
    return ("trend-up" if lean > 0 else "trend-down"), float(lean)


def predict_direction(
    *,
    mid: float,
    strike: float | None,
    spot: float,
    recent_closes: list[float] | None,
    minutes_remaining: float,
    confidence_threshold: float = 0.56,
) -> DirectionResult:
    mid = min(max(mid if mid else 0.5, 0.02), 0.98)
    picture, lean = _tape_picture(recent_closes or [], strike)

    # B1: start at Kalshi midpoint, nudge with the three pictures
    nudge = 0.0
    if picture == "trend-up":
        nudge = min(0.08, abs(lean) * 0.12)
    elif picture == "trend-down":
        nudge = -min(0.08, abs(lean) * 0.12)
    elif picture == "jumpy":
        # pull toward 0.50 — less conviction
        mid = 0.5 * 0.35 + mid * 0.65
    elif picture == "sideways":
        mid = 0.5 * 0.20 + mid * 0.80

    dist_pct = None
    if strike and spot and strike > 0:
        dist_pct = 100.0 * (spot - strike) / strike
        # distance-to-strike: already above strike slightly favors up
        nudge += max(-0.04, min(0.04, dist_pct / 100.0 * 2.0))

    p_up = min(max(mid + nudge, 0.08), 0.92)

    # Last 90 seconds of the *hour* analog: last ~1.5 minutes of the 15m window
    if minutes_remaining < 1.5:
        blend = max(minutes_remaining / 1.5, 0.0)
        p_up = 0.5 * (1 - blend) + p_up * blend

    p_down = 1.0 - p_up
    conf = max(p_up, p_down)
    gate = conf >= confidence_threshold and picture != "jumpy" and minutes_remaining > 1.5

    details = f"B1 midpoint+pictures ({picture}, lean={lean:+.2f})"
    return DirectionResult(
        p_up=round(p_up, 4),
        p_down=round(p_down, 4),
        mid=round(mid, 4),
        gate_pass=gate,
        picture=picture,
        details=details,
        dist_to_strike_pct=round(dist_pct, 3) if dist_pct is not None else None,
    )
