from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


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

    # EDGAR fields (populated in Phase 1.2)
    cik: str | None = None
    has_restatement: bool | None = None
    has_going_concern: bool | None = None
    has_active_enforcement: bool = False
    edgar_skipped: bool = False
    edgar_skipped_reason: str | None = None  # "no_cik" | "data_source_error" — set in run_edgar_filter

    # Gemini scoring (populated in Phase 1.3)
    gemini_dimensions: dict[str, int] | None = None  # {"growth": 3, "profitability": 4, ...}
    gemini_summary: str | None = None

    # Filter tracking
    filter_passed_basis: bool | None = None
    filter_passed_edgar: bool | None = None
    filter_failed_reason: str | None = None

    # Metadata
    screened_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def from_yfinance_info(cls, ticker: str, info: dict[str, Any]) -> ScreenerRecord:
        """Create record from yfinance info dict. Gemini scoring fields default to None — set by scorer."""
        return cls(
            ticker=ticker,
            name=info.get("shortName"),
            currency=info.get("currency"),
            market_cap=info.get("marketCap") or None,
            avg_daily_volume=info.get("averageVolume") or None,
            price=info.get("currentPrice") or info.get("regularMarketPrice"),
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
