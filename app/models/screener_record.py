from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.models.definedness import DefinednessOutcome


# Minor-unit quote normalization: some exchanges quote price in a minor unit while
# marketCap is in the major unit. London (GBp = pence) is the live case; ZAc (SA cents),
# ILA (Israeli agorot) are the same class — add when a listing actually appears.
_MINOR_UNIT: dict[str, tuple[str, int]] = {"GBp": ("GBP", 100)}


class ScreenerRecord(BaseModel):
    # Identity
    ticker: str
    name: str | None = None
    currency: str | None = None

    # Market data (from yfinance info)
    market_cap: float | None = None
    avg_daily_volume: float | None = None
    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    gics_sector: str | None = None
    gics_industry: str | None = None

    # Financial ratios (from yfinance info — populated in run_basis_filter)
    gross_margin: float | None = None          # info['grossMargins'] — decimal (0.45 = 45%)
    revenue_growth_yoy: float | None = None   # info['revenueGrowth'] — decimal YoY
    operating_margin: float | None = None      # info['operatingMargins']
    return_on_equity: float | None = None      # info['returnOnEquity']
    debt_to_equity: float | None = None        # info['debtToEquity']

    # FX-normalized market cap — computed in run_basis_filter, not from yfinance directly
    market_cap_eur: float | None = None
    fx_rate: float | None = None  # currency->EUR rate, carried from resolution (Punkt 1: value-gate primitive)

    # EDGAR fields (populated in Phase 1.2)
    cik: str | None = None
    has_restatement: bool | None = None
    has_going_concern: bool | None = None
    has_active_enforcement: bool = False
    edgar_skipped: bool = False
    edgar_skipped_reason: str | None = None  # "no_cik" | "data_source_error" — set in run_edgar_filter

    # Gemini scoring (populated in Phase 1.3; v2.1 flat, evidence-driven prompt)
    gemini_dimensions: dict[str, int] | None = None  # {"growth": 3, "profitability": 4, ...}
    gemini_evidence: dict[str, str] | None = None  # per-dimension one-line evidence notes
    gemini_weakest_dimension: str | None = None  # the lowest-scoring merit axis (self-reported)
    gemini_data_gaps: list[str] | None = None  # DATA fields the model flagged as missing

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
    multiyear_revenue_cagr: float | None = None      # endpoint CAGR over available fiscal years
    revenue_down_years: int | None = None            # count of negative YoY transitions (oldest->newest)
    revenue_growth_definedness: DefinednessOutcome | None = None  # DEFINED | UNASSESSABLE (3-state, never bool)
    revenue_growth_pass_reason: str | None = None    # TTM_PASS | TRAJECTORY_RESCUE | DECLINE_DROP | UNASSESSABLE_PASS
    resolution_detail: str | None = None  # 0b: sub-reason when diverted (NO_RAW_MC|NO_CURRENCY|NO_VOLUME|NO_PRICE|NO_FX)
    # CT-A: definedness verdict from the basis-stage income-statement pre-pass.
    # None = not assessed (non-suspect, or record did not reach the assessment).
    definedness: DefinednessOutcome | None = None

    # Metadata
    screened_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def from_yfinance_info(cls, ticker: str, info: dict[str, Any]) -> ScreenerRecord:
        """Create record from yfinance info dict. Gemini scoring fields default to None — set by scorer."""
        currency = info.get("currency")
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        # Normalize minor-unit quotes (e.g. London pence) to the major unit + ISO currency,
        # so price is consistent for every consumer and the FX lookup hits a real ISO code.
        # marketCap is already in the major unit — only price is rescaled.
        minor = _MINOR_UNIT.get(currency or "")
        if minor is not None:
            iso, divisor = minor
            currency = iso
            if price is not None:
                price = price / divisor
        return cls(
            ticker=ticker,
            name=info.get("shortName"),
            currency=currency,
            market_cap=info.get("marketCap") or None,
            avg_daily_volume=info.get("averageVolume") or None,
            price=price or None,
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
        )
