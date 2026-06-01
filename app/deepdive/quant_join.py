from __future__ import annotations

import logging
from typing import Any

from app.errors import DataSourceError
from app.models.deep_dive_record import (
    ForwardEstimates,
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

_DY_GLITCH_FACTOR = 10  # normalized yield > 10x payout/PE-implied => .info percent-units glitch


def _norm_dividend_yield(raw: float | None) -> float | None:
    """yfinance returns dividendYield sometimes as a fraction (0.024) and
    sometimes as a percent (2.4). Normalize to a fraction so _fmt_pct works."""
    if raw is None:
        return None
    return raw / 100 if raw > 1 else raw


def _resolve_dividend_yield(
    raw: float | None,
    payout_ratio: float | None,
    trailing_pe: float | None,
) -> float | None:
    """Resolve yfinance .info dividendYield, which is in PERCENT units.

    Sub-1% yields (raw < 1) slip past the magnitude heuristic in
    _norm_dividend_yield and render ~100x too big (GOOGL 0.23 -> 23%,
    MSFT 0.81 -> 81%). A single magnitude cannot disambiguate 0.23 (a legit
    23% fraction vs a mis-read 0.23%); the independent estimate
    ``payout_ratio / trailing_pe`` supplies the missing bit (dividend yield
    ~= payout/PE). payout/PE is ONLY the trigger — the correction is the exact
    inverse of the bug (``raw / 100``), never payout/PE itself (too imprecise;
    Novo would be 3.99% vs the true 5.43%)."""
    if raw is None:
        return None
    norm = _norm_dividend_yield(raw)
    assert norm is not None  # raw is float here, so norm is float
    if norm == 0:
        return norm  # 0.0; genuine non-payer, unambiguous
    implied: float | None = None
    if (
        payout_ratio is not None
        and trailing_pe is not None
        and payout_ratio > 0
        and trailing_pe > 0
    ):
        implied = payout_ratio / trailing_pe
    if implied is not None:
        if norm > _DY_GLITCH_FACTOR * implied:
            corrected = raw / 100
            logger.warning(
                "quant: dividend_yield .info percent-units glitch — "
                "normalized %.4f vs payout/PE-implied %.4f (>%dx) — "
                "auto-corrected to %.4f",
                norm,
                implied,
                _DY_GLITCH_FACTOR,
                corrected,
            )
            return corrected
        return norm
    if raw >= 1:
        return norm  # >=1% class, magnitude already divided — not the bug class
    logger.warning(
        "quant: dividend_yield %.4f sub-1 with no payout/PE cross-check — "
        "not disambiguable, rendering n/a",
        raw,
    )
    return None


def _latest_non_none(seq: Any) -> float | None:
    """Newest-first sequence -> first non-None value (= latest FY)."""
    for v in seq or []:
        if v is not None:
            return v
    return None


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
        trailing_pe=info.get("trailingPE"),
        forward_pe=info.get("forwardPE"),
        enterprise_value=info.get("enterpriseValue"),
        free_cashflow=info.get("freeCashflow"),
        total_debt=info.get("totalDebt"),
        total_cash=info.get("totalCash"),
        current_ratio=info.get("currentRatio"),
        payout_ratio=info.get("payoutRatio"),
        dividend_yield=_resolve_dividend_yield(
            info.get("dividendYield"),
            info.get("payoutRatio"),
            info.get("trailingPE"),
        ),
        recommendation_key=info.get("recommendationKey"),
        recommendation_mean=info.get("recommendationMean"),
        target_mean_price=info.get("targetMeanPrice"),
        target_median_price=info.get("targetMedianPrice"),
        target_low_price=info.get("targetLowPrice"),
        target_high_price=info.get("targetHighPrice"),
        number_of_analyst_opinions=info.get("numberOfAnalystOpinions"),
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
    # ebit / interest_expense come from the historical income statement
    # (latest FY = first non-None, newest-first), not from .info.
    pit.ebit = _latest_non_none(raw.get("ebit", []))
    pit.interest_expense = _latest_non_none(raw.get("interest_expense", []))

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

    # Stage 2b — forward consensus (fail-soft, never aborts the deep dive)
    forward_estimates: ForwardEstimates | None
    try:
        forward_estimates = yfinance.get_forward_estimates(ticker)
    except DataSourceError as exc:
        logger.warning(
            "quant: %s forward estimates unavailable — %s", ticker, exc)
        forward_estimates = None

    snapshot = QuantSnapshot(
        point_in_time=pit,
        historical_series=hist,
        trend_metrics=trends,
        gemini_dimensions=gemini_dimensions,
        forward_estimates=forward_estimates,
        valuation_history=raw.get("valuation_history"),
    )
    return snapshot, cov
