"""Gate logic: UP / DOWN / SIDEWAYS / NO CALL for 15-minute tickets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from config import (
    DIRECTION_CONFIDENCE_THRESHOLD,
    EDGE_BUFFER,
    MIN_CANDLES_FOR_CALL,
    NO_NEW_TICKET_SECONDS,
    is_book_a,
    spread_cap,
    taker_fee,
)

Outcome = Literal["UP", "DOWN", "SIDEWAYS", "NO_CALL"]


@dataclass
class GateResult:
    call: bool
    outcome: Outcome
    reason: str
    side: str | None = None  # "yes" (up) | "no" (down)


def evaluate_gates(
    *,
    asset: str,
    safety_pass: bool,
    direction_pass: bool,
    p_up: float,
    p_down: float,
    regime: str,
    seconds_left: float,
    n_candles: int,
    yes_bid: float,
    yes_ask: float,
    spread: float,
    book_a: bool | None = None,
) -> GateResult:
    if book_a is None:
        book_a = is_book_a(asset)
    if not book_a:
        return GateResult(False, "NO_CALL", "Book B – quotes only")

    if seconds_left <= NO_NEW_TICKET_SECONDS:
        return GateResult(False, "NO_CALL", "Inside last 90 seconds – no new call")

    if n_candles < MIN_CANDLES_FOR_CALL:
        return GateResult(
            False,
            "NO_CALL",
            f"Need {MIN_CANDLES_FOR_CALL} official 1-minute candles (have {n_candles})",
        )

    cap = spread_cap(asset)
    if spread > cap:
        return GateResult(False, "NO_CALL", f"Spread {spread:.3f} wider than cap {cap:.3f}")

    if not safety_pass and regime not in ("low", "mid-low"):
        if direction_pass:
            return GateResult(False, "NO_CALL", "Safety gate failed")
        return GateResult(False, "NO_CALL", "Safety and direction gates failed")

    # After-fee test vs actual asks
    fee_yes = taker_fee(yes_ask if yes_ask > 0 else 0.5)
    no_ask = max(0.0, 1.0 - yes_bid) if yes_bid > 0 else (1.0 - (yes_ask or 0.5))
    fee_no = taker_fee(no_ask if no_ask > 0 else 0.5)

    yes_clears = p_up >= (yes_ask + fee_yes + EDGE_BUFFER) if yes_ask > 0 else False
    no_clears = p_down >= (no_ask + fee_no + EDGE_BUFFER) if no_ask > 0 else False

    lean_up = p_up >= DIRECTION_CONFIDENCE_THRESHOLD and p_up >= p_down
    lean_down = p_down >= DIRECTION_CONFIDENCE_THRESHOLD and p_down > p_up

    if safety_pass and lean_up and yes_clears:
        return GateResult(True, "UP", "Safety pass + lean up + after-fee test cleared", side="yes")
    if safety_pass and lean_down and no_clears:
        return GateResult(True, "DOWN", "Safety pass + lean down + after-fee test cleared", side="no")

    if safety_pass and regime in ("low", "mid-low") and not lean_up and not lean_down:
        return GateResult(
            True,
            "SIDEWAYS",
            f"Low/mid-low regime ({regime}) + no directional lean → SIDEWAYS",
        )

    if lean_up or lean_down:
        return GateResult(False, "NO_CALL", "Lean present but after-fee test did not clear (likely lopsided tape)")
    if not safety_pass:
        return GateResult(False, "NO_CALL", "Safety gate failed")
    return GateResult(False, "NO_CALL", "No directional lean and not a sideways regime")
