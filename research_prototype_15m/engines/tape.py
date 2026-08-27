"""Tape-only view: strike + this-window structure + window VWAP. Not used to arm CALL."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TapeResult:
    label: str
    reason: str
    vwap: float | None
    vwap_side: str
    last: float | None
    vs_strike: str


def _vwap(candles: list[dict]) -> float | None:
    num = 0.0
    den = 0.0
    for c in candles:
        close = c.get("close")
        high = c.get("high", close)
        low = c.get("low", close)
        vol = c.get("volume") or 0.0
        if close is None:
            continue
        typical = (float(high) + float(low) + float(close)) / 3.0
        w = float(vol) if vol and vol > 0 else 1.0
        num += typical * w
        den += w
    if den <= 0:
        return None
    return num / den


def read_tape(
    *,
    strike: float | None,
    spot: float,
    closes: list[float] | None,
    candles: list[dict] | None = None,
) -> TapeResult:
    series = list(closes or [])
    window = series[-15:] if len(series) >= 15 else series
    last = float(spot) if spot else (float(window[-1]) if window else None)

    if last is None or len(window) < 3:
        return TapeResult("THIN", "Not enough 1-minute tape", None, "n/a", last, "n/a")

    if last > 0 and len(window) >= 5:
        diffs = [abs(window[i] - window[i - 1]) / last for i in range(1, len(window))]
        avg = sum(diffs) / len(diffs)
        if avg > 0.0035:
            vs = "above" if strike and last >= strike else ("below" if strike else "n/a")
            return TapeResult("JUMPY", "1-minute path too violent to call structure", None, "n/a", last, vs)

    vs_strike = "n/a"
    if strike and strike > 0 and last:
        vs_strike = "above" if last >= strike else "below"

    mid = max(len(window) // 2, 1)
    first, second = window[:mid], window[mid:]
    hh = max(second) > max(first)
    hl = min(second) > min(first)
    lh = max(second) < max(first)
    ll = min(second) < min(first)
    if hh and hl:
        structure = "higher highs and higher lows"
        struct_side = "up"
    elif lh and ll:
        structure = "lower highs and lower lows"
        struct_side = "down"
    else:
        structure = "mixed highs/lows"
        struct_side = "mixed"

    src = (candles or [])[-15:] or [{"close": x, "high": x, "low": x, "volume": 1} for x in window]
    vwap = _vwap(src)
    vwap_side = "n/a"
    if vwap and last:
        vwap_side = "above" if last >= vwap else "below"

    if vs_strike == "above" and struct_side != "down":
        label, reason = "UP", f"last {vs_strike} strike, {structure}"
    elif vs_strike == "below" and struct_side != "up":
        label, reason = "DOWN", f"last {vs_strike} strike, {structure}"
    elif vs_strike == "n/a" and struct_side == "up":
        label, reason = "UP", structure
    elif vs_strike == "n/a" and struct_side == "down":
        label, reason = "DOWN", structure
    else:
        label, reason = "SIDEWAYS", f"last {vs_strike} strike, {structure}"

    return TapeResult(label, reason, vwap, vwap_side, last, vs_strike)
