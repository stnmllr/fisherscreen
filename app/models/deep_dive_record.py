from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.deepdive.filing_parser import SectionFlag

logger = logging.getLogger(__name__)

Confidence = Literal["🟢", "🟡", "🔴"]


class FisherPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1, le=15)
    title: str
    rating: int = Field(ge=1, le=5)
    confidence: Confidence
    reasoning: str
    sources: list[str] = Field(min_length=1)

    # Transforms (not rejects) — prevents run-killing on minor word-count overshoot.
    @field_validator("reasoning")
    @classmethod
    def _reasoning_word_cap(cls, v: str) -> str:
        words = v.split()
        if len(words) <= 70:
            return v
        truncated = " ".join(words[:70])
        last_boundary = max(
            truncated.rfind(". "),
            truncated.rfind("! "),
            truncated.rfind("? "),
        )
        if last_boundary > 0:
            truncated = truncated[: last_boundary + 1]
            boundary_mode = "sentence"
        else:
            truncated = truncated + " […]"
            boundary_mode = "hard-cut+ellipsis"
        logger.warning(
            "FisherPoint.reasoning truncated from %d words (boundary: %s)",
            len(words),
            boundary_mode,
        )
        return truncated

    @model_validator(mode="after")
    def _inference_only_caps_confidence(self) -> FisherPoint:
        # ADR-5c / spec §5: sources == ['Inferenz'] => never 🟢 (cap at 🟡).
        if self.sources == ["Inferenz"] and self.confidence == "🟢":
            self.confidence = "🟡"
        return self


class PointInTimeQuant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    name: str | None = None
    currency: str | None = None
    market_cap: float | None = None
    market_cap_eur: float | None = None
    price: float | None = None
    gics_sector: str | None = None
    gics_industry: str | None = None
    gross_margin: float | None = None
    revenue_growth_yoy: float | None = None
    operating_margin: float | None = None
    return_on_equity: float | None = None
    debt_to_equity: float | None = None
    # Stage 2a — valuation / capital-structure / shareholder-return (TTM)
    trailing_pe: float | None = None
    forward_pe: float | None = None
    enterprise_value: float | None = None
    ebit: float | None = None
    free_cashflow: float | None = None
    total_debt: float | None = None
    total_cash: float | None = None
    current_ratio: float | None = None
    interest_expense: float | None = None
    dividend_yield: float | None = None
    payout_ratio: float | None = None
    # Stage 2b — analyst consensus
    recommendation_key: str | None = None
    recommendation_mean: float | None = None
    target_mean_price: float | None = None
    target_median_price: float | None = None
    target_low_price: float | None = None
    target_high_price: float | None = None
    number_of_analyst_opinions: int | None = None


class ForwardEstimates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # cy = current fiscal year (yfinance period '0y'); ny = next ('+1y').
    # Growth values are fractions, e.g. 0.09.
    revenue_growth_cy: float | None = None
    revenue_growth_ny: float | None = None
    eps_growth_cy: float | None = None
    eps_growth_ny: float | None = None


class PeerQuant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    name: str | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    operating_margin: float | None = None
    gross_margin: float | None = None
    revenue_growth_yoy: float | None = None
    free_cashflow: float | None = None
    market_cap: float | None = None


class PeerComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peers: list[PeerQuant]  # expected length 3
    rationale: str | None = None


class HistoricalSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    financial_currency: str | None = None
    years: list[int] = Field(default_factory=list)
    revenue: list[float | None] = Field(default_factory=list)
    gross_margin: list[float | None] = Field(default_factory=list)
    operating_margin: list[float | None] = Field(default_factory=list)
    shares_outstanding: list[float | None] = Field(default_factory=list)
    buyback_cashflow: list[float | None] = Field(default_factory=list)


class TrendMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revenue_cagr_5y: float | None = None
    operating_margin_slope_5y: float | None = None
    dilution_pct_5y: float | None = None
    buyback_intensity_5y: float | None = None


class QuantSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point_in_time: PointInTimeQuant
    historical_series: HistoricalSeries | None = None
    trend_metrics: TrendMetrics | None = None
    gemini_dimensions: dict[str, Any] | None = None
    forward_estimates: ForwardEstimates | None = None
    peer_comparison: PeerComparison | None = None


class SourceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quant_pit_source: str = "unknown"          # "tool-a-cache" | "live-yfinance"
    gemini_dims: str = "absent"                # "present" | "absent (nicht im letzten Monatslauf)"
    historical: str = "absent"                 # "complete" | "partial (<5J, NJ)" | "absent"
    currency_note: str | None = None           # financialCurrency != listing currency
    edgar: str = "unknown"                     # e.g. "20-F via ADR"
    soft: str = "folgt B.3"
    sprache: str = "folgt B.4"
    insider: str = "folgt B.2"
    valuation: str = (
        "TTM vorhanden (KGV/EV-EBIT/FCF-Yield) · 5J-Range zurückgestellt "
        "(historische EPS-Rekonstruktion)"
    )


class DeepDiveRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    adr_ticker: str | None
    cik: str
    form_type: Literal["10-K", "20-F"]
    filing_sections: dict[str, str]
    section_flags: dict[str, SectionFlag]
    quant_snapshot: QuantSnapshot
    synthesis: list[FisherPoint]
    source_coverage: SourceCoverage
    filing_date: str | None = None
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def days_since_filing(self) -> int | None:
        """Days between the SEC filing_date and the quant snapshot.

        None if filing_date is absent or not an ISO date (fail-soft —
        legacy cache entries and malformed dates must not crash the dossier).
        """
        if self.filing_date is None:
            return None
        try:
            parsed = date.fromisoformat(self.filing_date)
        except ValueError:
            return None
        return (self.generated_at.date() - parsed).days
