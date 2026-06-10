"""Metric-definedness predicate + waterfall-shape discriminator for the
gross_margin gate (Punkt 2). The waterfall classifier and assess_definedness are
the runtime predicates wired by the basis-stage pre-pass (CT-A).
"""
from __future__ import annotations

from enum import Enum

from app.models.definedness import DefinednessOutcome  # noqa: F401 — re-export for callers


class WaterfallVerdict(str, Enum):
    DEFINED = "DEFINED"                     # real revenue->COGS->gross-profit waterfall
    UNDEFINED = "UNDEFINED"                 # no real COGS structure -> METRIK_NA
    DEFINED_NEGATIVE = "DEFINED_NEGATIVE"   # real waterfall, COGS>revenue -> FAIL (not NA)


# Relative tolerance for the consistency check gp == revenue - cost_of_revenue.
_WATERFALL_REL_TOL = 0.02
# A cost-of-revenue this small relative to revenue means there is no genuine COGS
# (bank/insurer/REIT signature: "revenue" is net interest/premium/rent, gp ~ rev).
_MIN_COR_FRACTION = 0.01


def classify_waterfall(
    total_revenue: float | None,
    cost_of_revenue: float | None,
    gross_profit: float | None,
    cost_of_revenue_present: bool,
) -> WaterfallVerdict:
    """Form-based discriminator. Reads the SHAPE of the income-statement waterfall,
    not the mere presence of a Cost-of-Revenue line (a presence test flips on the
    spurious-positive edge — see spec §3)."""
    if not cost_of_revenue_present or total_revenue is None or total_revenue <= 0:
        return WaterfallVerdict.UNDEFINED
    if cost_of_revenue is None or gross_profit is None:
        return WaterfallVerdict.UNDEFINED
    # No genuine COGS magnitude => not a real waterfall (claims/interest booked elsewhere).
    if abs(cost_of_revenue) < _MIN_COR_FRACTION * total_revenue:
        return WaterfallVerdict.UNDEFINED
    # Consistency: gross_profit must equal revenue - cost_of_revenue within tolerance.
    expected_gp = total_revenue - cost_of_revenue
    if abs(gross_profit - expected_gp) > _WATERFALL_REL_TOL * total_revenue:
        return WaterfallVerdict.UNDEFINED
    if gross_profit <= 0:
        return WaterfallVerdict.DEFINED_NEGATIVE
    return WaterfallVerdict.DEFINED


def assess_definedness(
    industry: str | None,
    statement_available: bool,
    total_revenue: float | None,
    cost_of_revenue: float | None,
    gross_profit: float | None,
    cost_of_revenue_present: bool,
) -> DefinednessOutcome:
    """Runtime 3-state definedness decision (CT-A).

    - REIT positive-edge cross-check (Property C) wins FIRST and needs no statement:
      any "REIT"-labelled industry is METRIK_NA (rent - property-opex satisfies the
      waterfall, but Fisher's margin framework does not apply to property rental).
    - A failed/unavailable statement (statement_available is False, or revenue is None)
      is UNASSESSABLE -> the caller diverts it to the resolution path. This is structurally
      distinct from a genuine UNDEFINED waterfall: do NOT let a fetch failure masquerade as
      a definedness verdict (distinguish-failure-from-empty-result).
    - Otherwise classify the waterfall: UNDEFINED -> METRIK_NA; DEFINED / DEFINED_NEGATIVE
      -> DEFINED (DEFINED_NEGATIVE is a real negative margin and must fail the gross_margin
      gate downstream, not be excluded as framework-n/a)."""
    if "REIT" in (industry or ""):
        return DefinednessOutcome.METRIK_NA
    if not statement_available or total_revenue is None:
        return DefinednessOutcome.UNASSESSABLE
    verdict = classify_waterfall(total_revenue, cost_of_revenue, gross_profit, cost_of_revenue_present)
    if verdict is WaterfallVerdict.UNDEFINED:
        return DefinednessOutcome.METRIK_NA
    return DefinednessOutcome.DEFINED
