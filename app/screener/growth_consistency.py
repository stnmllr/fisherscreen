"""Multi-year revenue growth from the fiscal-year series: the growth-axis input
(median annual growth) and its anti-cyclical dampener (consistency). A one-year
supercycle spike can still rank high on the median, but, lacking multi-year
consistency, is capped down here. Both are absolute (non-sector-relative) and both
need a DEFINED trajectory (>= 4 fiscal years)."""

from __future__ import annotations

from statistics import median

from app.models.definedness import DefinednessOutcome
from app.screener.revenue_trajectory import classify_revenue_trajectory


def median_annual_growth(revenues: list[float]) -> float | None:
    """Median of the annual growth rates revenues[i]/revenues[i-1] - 1
    (oldest->newest). None when UNASSESSABLE (<4 GJ), same rule as the consistency
    ratio. An even rate count takes the mean of the two middle rates.

    Median, not endpoint CAGR: an endpoint CAGR hangs on its first and last year,
    so a single definitional break in the series drags it. ADYEN.AS switched from
    gross to net revenue (8.94 -> 1.86 -> 2.23 -> 2.65 bn): endpoint CAGR -33 %,
    median +19 %. The median ignores one outlying transition."""
    _, _, definedness = classify_revenue_trajectory(revenues)
    if definedness is not DefinednessOutcome.DEFINED:
        return None
    return median(revenues[i] / revenues[i - 1] - 1 for i in range(1, len(revenues)))


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
