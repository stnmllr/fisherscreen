from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.models.definedness import DefinednessOutcome
from app.services.yfinance_client import quoted_price, resolve_market_cap


def _num(value: Any) -> float | None:
    """A real number as float, else None. bool is excluded although it is an int
    subclass, and numeric strings are not parsed: yfinance serves either a number
    or junk, and junk must read as missing, not as a coerced value."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


class ScreenerRecord(BaseModel):
    # Identity
    ticker: str
    name: str | None = None
    currency: str | None = None

    # Market data (from yfinance info)
    market_cap: float | None = None
    # "REPORTED" (Yahoo marketCap) | "DERIVED" (sharesOutstanding x price, when Yahoo
    # serves marketCap 0/missing) | None (no usable cap). Same unit either way.
    market_cap_source: str | None = None
    avg_daily_volume: float | None = None
    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    gics_sector: str | None = None
    gics_industry: str | None = None

    # Financial ratios (from yfinance info — populated in run_basis_filter)
    gross_margin: float | None = None  # info['grossMargins'] — decimal (0.45 = 45%)
    revenue_growth_yoy: float | None = None  # info['revenueGrowth'] — decimal YoY
    operating_margin: float | None = None  # info['operatingMargins']
    return_on_equity: float | None = None  # info['returnOnEquity']
    # info['debtToEquity'] — kept for Tool B / viewer; Tool A scoring no longer reads
    # it (buyback cosmetics: tiny or negative book equity distorts the ratio).
    debt_to_equity: float | None = None
    # Leverage inputs for Tool-A resilience (net debt / EBITDA), absolute currency units.
    total_debt: float | None = None  # info['totalDebt']
    total_cash: float | None = None  # info['totalCash']
    ebitda: float | None = None  # info['ebitda'] — may be <= 0
    # ROIC inputs for Tool-A profitability (see app/screener/roic.py). Non-numeric
    # yfinance values become None (see _num).
    total_revenue: float | None = None  # info['totalRevenue'] — financial currency
    book_value_per_share: float | None = None  # info['bookValue'] — QUOTE currency
    shares_outstanding: float | None = None  # info['sharesOutstanding'] — one class
    financial_currency: str | None = None  # info['financialCurrency']
    # Computed by app.screener.roic.annotate_roic before the percentiles, not from
    # info. Exactly one is set: the ROIC (decimal) or why it is missing
    # ("no_ebit" | "no_equity" | "no_debt_cash" | "invested_capital_nonpositive").
    return_on_invested_capital: float | None = None
    roic_missing_reason: str | None = None

    # FX-normalized market cap — computed in run_basis_filter, not from yfinance directly
    market_cap_eur: float | None = None
    fx_rate: float | None = (
        None  # currency->EUR rate, carried from resolution (Punkt 1: value-gate primitive)
    )

    # EDGAR fields (populated in Phase 1.2)
    cik: str | None = None
    has_restatement: bool | None = None
    has_going_concern: bool | None = None
    has_active_enforcement: bool = False
    edgar_skipped: bool = False
    edgar_skipped_reason: str | None = (
        None  # "no_cik" | "data_source_error" — set in run_edgar_filter
    )

    # Gemini scoring (populated in Phase 1.3; v2.1 flat, evidence-driven prompt)
    gemini_dimensions: dict[str, int] | None = (
        None  # {"growth": 3, "profitability": 4, ...}
    )
    gemini_evidence: dict[str, str] | None = (
        None  # per-dimension one-line evidence notes
    )
    gemini_weakest_dimension: str | None = (
        None  # the lowest-scoring merit axis (self-reported)
    )
    gemini_data_gaps: list[str] | None = (
        None  # DATA fields the model flagged as missing
    )

    # Sector-relative deterministic scoring (2026-06): set in percentile_prep + scorer.
    input_percentiles: dict[str, float] | None = (
        None  # metric -> within-run percentile (0..100)
    )
    growth_consistency: float | None = (
        None  # positive_years_ratio; None = UNASSESSABLE (<4 GJ)
    )
    # Growth-axis input, computed from the fiscal-year revenue series (not from
    # info): median annual growth rate; None = UNASSESSABLE (<4 GJ).
    revenue_growth_median: float | None = None
    score_basis: dict[str, str] | None = (
        None  # per axis: "global" | "sector_relative" | "global_fallback"
    )
    data_confidence: str = "ok"  # "ok" | "low"
    partial_evidence_axes: list[str] | None = (
        None  # merit axes scored on only 1 of 2 inputs
    )
    # Why resilience was forced to 0 by the leverage red flag, else None:
    # "net_debt_to_ebitda_above_4" | "net_debt_with_nonpositive_ebitda".
    resilience_red_flag: str | None = None
    # Vierte Achse. Der SCORE allein sagt nicht, ob sie bewertbar war: ein
    # gemessener 3,0-Titel und ein neutral gestellter tragen dieselbe Zahl.
    # Bewertbar ist ausschliesslich, wo `steadiness_reason is None` (Spec 8.1).
    steadiness: float | None = None
    steadiness_reason: str | None = (
        None  # "no_sec_registrant" | "series_too_short" | "no_concept"
    )

    # Filter tracking
    filter_passed_basis: bool | None = None
    filter_passed_edgar: bool | None = None
    filter_failed_reason: str | None = None
    # Punkt 2 Phase E: how a basis-passing record cleared the gross-margin gate.
    # "ABSOLUTE_PASS" (gm >= floor) | "RELATIVE_RESCUE" (sub-floor, rescued by the
    # relative arm) | None (not applicable / did not pass the basis filter).
    gross_margin_pass_reason: str | None = None
    # Punkt 3 Phase: multi-year revenue-growth viability floor.
    # Populated in the runner pre-pass (_assess_revenue_growth_trajectory) ONLY for
    # vol+cap survivors that clear the gross-margin gate AND have revenue_growth_yoy < 0
    # or None (the lazy-fetch cohort). Left None for everyone else (TTM-pass / not reached).
    multiyear_revenue_cagr: float | None = (
        None  # endpoint CAGR over available fiscal years
    )
    revenue_down_years: int | None = (
        None  # count of negative YoY transitions (oldest->newest)
    )
    revenue_growth_definedness: DefinednessOutcome | None = (
        None  # DEFINED | UNASSESSABLE (3-state, never bool)
    )
    revenue_growth_pass_reason: str | None = (
        None  # TTM_PASS | TRAJECTORY_RESCUE | DECLINE_DROP | UNASSESSABLE_PASS
    )
    resolution_detail: str | None = (
        None  # 0b: sub-reason when diverted (NO_RAW_MC|NO_CURRENCY|NO_VOLUME|NO_PRICE|NO_FX)
    )
    # CT-A: definedness verdict from the basis-stage income-statement pre-pass.
    # None = not assessed (non-suspect, or record did not reach the assessment).
    definedness: DefinednessOutcome | None = None

    # Metadata
    screened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_yfinance_info(cls, ticker: str, info: dict[str, Any]) -> ScreenerRecord:
        """Create record from yfinance info dict. Gemini scoring fields default to None — set by scorer.

        Plain field mapper: minor-unit quotes (London pence) are already normalized by
        the yfinance adapter, which is the single home for that rule. Do not re-add a
        rescale here — two normalizations of the same quantity in two layers is how a
        double division gets introduced.

        market_cap is the reported cap, else shares x price when derivable — the rule
        (and its unit guard) lives in `resolve_market_cap`, shared with the cache.
        """
        market_cap, market_cap_source = resolve_market_cap(info)
        return cls(
            ticker=ticker,
            name=info.get("shortName"),
            currency=info.get("currency"),
            market_cap=market_cap,
            market_cap_source=market_cap_source,
            avg_daily_volume=info.get("averageVolume") or None,
            price=quoted_price(info),
            bid=info.get("bid") or None,
            ask=info.get("ask") or None,
            gics_sector=info.get("sector"),
            gics_industry=info.get("industry"),
            cik=info.get("cik"),
            gross_margin=info.get("grossMargins"),
            revenue_growth_yoy=info.get("revenueGrowth"),
            operating_margin=info.get("operatingMargins"),
            return_on_equity=info.get("returnOnEquity"),
            debt_to_equity=info.get("debtToEquity"),
            total_debt=info.get("totalDebt"),
            total_cash=info.get("totalCash"),
            ebitda=info.get("ebitda"),
            total_revenue=_num(info.get("totalRevenue")),
            book_value_per_share=_num(info.get("bookValue")),
            shares_outstanding=_num(info.get("sharesOutstanding")),
            financial_currency=info.get("financialCurrency"),
        )
