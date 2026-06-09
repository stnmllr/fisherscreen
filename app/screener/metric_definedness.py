"""Metric-definedness predicate + waterfall-shape discriminator for the
gross_margin gate (Punkt 2). The .info-only predicate is the runtime DEFAULT;
the waterfall classifier is used by the Gate-A calibration probe and becomes the
runtime predicate only if Gate-A finds a non-empty edge (spec §6 Property A)."""
from __future__ import annotations

from enum import Enum

from app.models.screener_record import ScreenerRecord


def is_gross_margin_undefined_info_only(record: ScreenerRecord) -> bool:
    """Runtime DEFAULT definedness predicate (.info-only, no fetch).
    gm is None or <= 0 => treat as structurally undefined => METRIK_NA."""
    gm = record.gross_margin
    return gm is None or gm <= 0.0


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
