"""Absolute (non-sector-relative) revenue-growth consistency: the anti-cyclical
dampener on the growth axis. A one-year supercycle spike scores high on the global
growth percentile but, lacking multi-year consistency, is capped down here."""
from __future__ import annotations

from app.models.definedness import DefinednessOutcome
from app.screener.revenue_trajectory import classify_revenue_trajectory


def consistency_ratio(revenues: list[float]) -> float | None:
    """positive_years_ratio = (transitions - down_years) / transitions over the
    available fiscal years (oldest->newest). None when UNASSESSABLE (<4 GJ): the
    trajectory cannot establish durable growth."""
    cagr, down_years, definedness = classify_revenue_trajectory(revenues)
    if definedness is not DefinednessOutcome.DEFINED or down_years is None:
        return None
    transitions = len(revenues) - 1
    if transitions <= 0:
        return None
    return (transitions - down_years) / transitions


def consistency_cap(ratio: float | None) -> int:
    """Growth-score ceiling from consistency. None (UNASSESSABLE) -> 4 (conservative:
    an unprovable spin-off spike must not reach growth=5)."""
    if ratio is None:
        return 4
    if ratio >= 0.75:
        return 5
    if ratio >= 0.50:
        return 4
    return 3
