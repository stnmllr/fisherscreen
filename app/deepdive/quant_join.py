from __future__ import annotations

import logging
from typing import Any

from app.models.deep_dive_record import (
    HistoricalSeries,
    PointInTimeQuant,
    QuantSnapshot,
    SourceCoverage,
    TrendMetrics,
)
from app.deepdive.trend_metrics import (
    compute_buyback_intensity,
    compute_cagr,
    compute_dilution_pct,
    compute_margin_slope,
)

logger = logging.getLogger(__name__)


def _pit_from_info(ticker: str, info: dict[str, Any]) -> PointInTimeQuant:
    return PointInTimeQuant(
        ticker=ticker,
        name=info.get("shortName"),
        currency=info.get("currency"),
        market_cap=info.get("marketCap") or None,
        price=info.get("currentPrice") or info.get("regularMarketPrice"),
        gics_sector=info.get("sector"),
        gics_industry=info.get("industry"),
        gross_margin=info.get("grossMargins"),
        revenue_growth_yoy=info.get("revenueGrowth"),
        operating_margin=info.get("operatingMargins"),
        return_on_equity=info.get("returnOnEquity"),
        debt_to_equity=info.get("debtToEquity"),
    )


def build_quant_snapshot(
    ticker: str,
    *,
    firestore: Any,
    yfinance: Any,
    historical: Any,
    pit_collection: str,
    dims_collection: str,
    use_cache: bool = True,
) -> tuple[QuantSnapshot, SourceCoverage]:
    cov = SourceCoverage()

    # 4a — point-in-time (cache, else live)
    cached = firestore.get(pit_collection, ticker)
    if cached:
        info = {k: v for k, v in cached.items() if k != "_cached_at"}
        cov.quant_pit_source = "tool-a-cache"
    else:
        logger.warning("quant: %s not in %s — live yfinance fallback",
                        ticker, pit_collection)
        info = yfinance.get_ticker_info(ticker)
        cov.quant_pit_source = "live-yfinance"
    pit = _pit_from_info(ticker, info)

    # 4b — multi-year historical (sequential after 4a)
    raw = historical.get_annual_series(ticker, use_cache=use_cache)
    hist = HistoricalSeries(
        financial_currency=raw.get("financial_currency"),
        years=raw.get("years", []),
        revenue=raw.get("revenue", []),
        gross_margin=raw.get("gross_margin", []),
        operating_margin=raw.get("operating_margin", []),
        shares_outstanding=raw.get("shares_outstanding", []),
        buyback_cashflow=raw.get("buyback_cashflow", []),
    )
    cov.historical = "complete" if raw.get("complete") else (
        f"partial (<5J, {len(hist.years)}J)")
    fc = raw.get("financial_currency")
    if fc and pit.currency and fc != pit.currency:
        cov.currency_note = (
            f"financialCurrency {fc} != Listing-Währung {pit.currency}")

    # 4c — trend metrics
    trends = TrendMetrics(
        revenue_cagr_5y=compute_cagr(hist.revenue),
        operating_margin_slope_5y=compute_margin_slope(hist.operating_margin),
        dilution_pct_5y=compute_dilution_pct(hist.shares_outstanding),
        buyback_intensity_5y=compute_buyback_intensity(
            hist.buyback_cashflow, pit.market_cap),
    )

    # Tool-A Gemini dims (secondary, ADR-5c) — no live re-derivation
    dims_doc = firestore.get(dims_collection, ticker)
    if dims_doc and dims_doc.get("dimensions"):
        gemini_dimensions: dict[str, Any] | None = dims_doc["dimensions"]
        cov.gemini_dims = "present"
    else:
        gemini_dimensions = None
        cov.gemini_dims = "absent (nicht im letzten Monatslauf)"

    snapshot = QuantSnapshot(
        point_in_time=pit,
        historical_series=hist,
        trend_metrics=trends,
        gemini_dimensions=gemini_dimensions,
    )
    return snapshot, cov
