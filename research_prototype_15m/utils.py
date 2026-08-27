"""Shared helpers for the 15-minute research prototype."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def window_bounds(now: datetime | None = None) -> tuple[datetime, datetime, datetime]:
    """Return (current_start, current_end, next_end) on the 15-minute grid (UTC)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    minute = (now.minute // 15) * 15
    current_start = now.replace(minute=minute, second=0, microsecond=0)
    current_end = current_start + timedelta(minutes=15)
    next_end = current_end + timedelta(minutes=15)
    return current_start, current_end, next_end


def seconds_remaining_in_window(now: datetime | None = None) -> float:
    _, current_end, _ = window_bounds(now)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0.0, (current_end - now.astimezone(timezone.utc)).total_seconds())


def minutes_remaining_in_window(now: datetime | None = None) -> float:
    return seconds_remaining_in_window(now) / 60.0


def format_mmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


def format_pct(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}%"


def format_price(x: float) -> str:
    if x >= 1000:
        return f"{x:,.0f}"
    if x >= 50:
        return f"{x:,.2f}"
    if x >= 1:
        return f"{x:,.3f}"
    return f"{x:.4f}"


def fmt_mag_pct(x: float) -> str:
    if x >= 0.10:
        return f"{x:.2f}%"
    if x >= 0.01:
        return f"{x:.3f}%"
    return f"{x:.4f}%"


def fmt_usd(x: float, spot: float) -> str:
    if spot >= 1000:
        return f"${x:,.0f}"
    if spot >= 50:
        return f"${x:,.2f}"
    return f"${x:.4f}"
