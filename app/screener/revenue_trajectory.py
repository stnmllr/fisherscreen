"""Pure multi-year revenue-trajectory classifier for the Punkt-3 viability floor.

No I/O, no record types — list of revenues (oldest->newest) -> (cagr, down_years,
definedness). The >=4-fiscal-years minimum is the SEAM-2 safeguard: with fewer points
the trajectory criterion cannot apply, so the outcome is UNASSESSABLE (deliberate
routing to a pass downstream), never a silent verdict.
"""
from __future__ import annotations

from app.models.definedness import DefinednessOutcome

MIN_FISCAL_YEARS = 4  # >=4 GJ == >=3 YoY transitions; needed for a down_years>=2 verdict


def classify_revenue_trajectory(
    revenues: list[float],
) -> tuple[float | None, int | None, DefinednessOutcome]:
    """Return (endpoint_cagr, down_years, definedness) for an oldest->newest revenue list.

    - <2 points: (None, None, UNASSESSABLE) — no trajectory at all.
    - 2..3 points: cagr/down_years computed for audit, but definedness=UNASSESSABLE
      (too short for a down_years>=2 verdict).
    - >=4 points: definedness=DEFINED; the gamma verdict may fire.
    Inputs are assumed positive (extract_revenue_series drops NaN/<=0).
    """
    n = len(revenues)
    if n < 2:
        return None, None, DefinednessOutcome.UNASSESSABLE
    yoy = [(revenues[i] - revenues[i - 1]) / revenues[i - 1] for i in range(1, n)]
    down_years = sum(1 for g in yoy if g < 0)
    years = n - 1
    cagr = (revenues[-1] / revenues[0]) ** (1 / years) - 1
    definedness = (
        DefinednessOutcome.DEFINED if n >= MIN_FISCAL_YEARS else DefinednessOutcome.UNASSESSABLE
    )
    return cagr, down_years, definedness


def is_gamma_decline(cagr: float | None, down_years: int | None) -> bool:
    """γ core: a genuine multi-year decline requires BOTH endpoint and trajectory to agree —
    CAGR < 0 AND down_years >= 2. Either signal missing -> not a decline (floor: in dubio pass)."""
    if cagr is None or down_years is None:
        return False
    return cagr < 0 and down_years >= 2
