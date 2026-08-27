"""Phase 2R overlays — hidden stubs. Not applied to P(up) in v1."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OverlayAdjustment:
    cvd_delta_p: float = 0.0
    funding_delta_p: float = 0.0
    applied: bool = False
    note: str = "Phase 2R overlays hidden (CVD / funding Z-score not wired)"


def experimental_adjustments(
    p_up: float,
    cvd_1h: float | None = None,
    funding_z: float | None = None,
    enabled: bool = False,
) -> OverlayAdjustment:
    """
    Stubs only. When enabled later:

    - CVD: if P(up)>0.5 and 1h CVD < 0 → subtract 0.05; opposite +0.05
    - Funding Z: Z>+1.8 → subtract 0.08 from P(up); Z<-1.8 → add 0.08
    """
    if not enabled:
        return OverlayAdjustment()
    adj = OverlayAdjustment(applied=True, note="experimental overlays ON")
    if cvd_1h is not None:
        if p_up > 0.5 and cvd_1h < 0:
            adj.cvd_delta_p = -0.05
        elif p_up < 0.5 and cvd_1h > 0:
            adj.cvd_delta_p = 0.05
    if funding_z is not None:
        if funding_z > 1.8:
            adj.funding_delta_p = -0.08
        elif funding_z < -1.8:
            adj.funding_delta_p = 0.08
    return adj
