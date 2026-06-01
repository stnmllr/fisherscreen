from __future__ import annotations

import logging
from typing import Any, Protocol

from app.errors import DataSourceError
from app.deepdive.valuation_history import (
    AnnualFundamental,
    compute_valuation_history,
)
from app.models.deep_dive_record import MultipleStats, ValuationHistory

logger = logging.getLogger(__name__)

_MIN_COMPLETE_YEARS = 3
_MAX_YEARS = 5


class HistoricalDataService(Protocol):
    # Cache-aware implementors (CachedHistoricalData) accept use_cache; the raw
    # HistoricalDataServiceImpl ignores it (no caching at that layer).
    def get_annual_series(
        self, ticker: str, use_cache: bool = True
    ) -> dict[str, Any]: ...


def _row(df: Any, label: str, ticker: str) -> dict[Any, float | None]:
    if df is None or getattr(df, "empty", True):
        return {}
    if label not in df.index:
        logger.warning(
            "historical: %s: row %r absent in non-empty statement — "
            "column values will be None",
            ticker,
            label,
        )
        return {}
    return df.loc[label].to_dict()


class HistoricalDataServiceImpl:
    """ADR-5a: live multi-year quant from yfinance. Graceful on partial data."""

    def __init__(self, yfinance: Any) -> None:
        self._yf = yfinance

    def get_annual_series(
        self, ticker: str, use_cache: bool = True
    ) -> dict[str, Any]:  # use_cache ignored: raw impl has no cache layer
        income, cash, bal = self._yf.get_annual_statements(ticker)
        info = self._yf.get_ticker_info(ticker)

        cols = list(getattr(income, "columns", []))[:_MAX_YEARS]
        years = [c.year for c in cols]

        rev = _row(income, "Total Revenue", ticker)
        gp = _row(income, "Gross Profit", ticker)
        oi = _row(income, "Operating Income", ticker)
        ebit = _row(income, "EBIT", ticker) or oi
        ie = _row(income, "Interest Expense", ticker)
        bb = _row(cash, "Repurchase Of Capital Stock", ticker)
        sh = _row(bal, "Share Issued", ticker)

        ni = _row(income, "Net Income", ticker)
        eps = _row(income, "Diluted EPS", ticker)
        fcf = _row(cash, "Free Cash Flow", ticker)
        td = _row(bal, "Total Debt", ticker)
        cce = _row(bal, "Cash And Cash Equivalents", ticker)

        def col(d: dict[Any, float | None], c: Any) -> float | None:
            v = d.get(c)
            return None if v is None else float(v)

        def margin(num: dict, c: Any) -> float | None:
            r, n = col(rev, c), col(num, c)
            if r in (None, 0) or n is None:
                return None
            return n / r

        series = {
            "financial_currency": info.get("financialCurrency"),
            "years": years,
            "revenue": [col(rev, c) for c in cols],
            "gross_margin": [margin(gp, c) for c in cols],
            "operating_margin": [margin(oi, c) for c in cols],
            "ebit": [col(ebit, c) for c in cols],
            "interest_expense": [col(ie, c) for c in cols],
            "shares_outstanding": [col(sh, c) for c in cols],
            "buyback_cashflow": [col(bb, c) for c in cols],
            "net_income": [col(ni, c) for c in cols],
            "diluted_eps": [col(eps, c) for c in cols],
            "free_cashflow": [col(fcf, c) for c in cols],
            "total_debt": [col(td, c) for c in cols],
            "cash": [col(cce, c) for c in cols],
            "complete": len(years) >= _MIN_COMPLETE_YEARS,
        }
        if not series["complete"]:
            logger.warning(
                "historical: %s only %d years (<%d) — flagged partial",
                ticker, len(years), _MIN_COMPLETE_YEARS,
            )
        series["valuation_history"] = self._build_valuation_history(
            ticker, cols, ni, eps, ebit, fcf, td, cce, info)
        return series

    def _build_valuation_history(
        self, ticker, cols, ni, eps, ebit, fcf, td, cce, info
    ) -> ValuationHistory:
        """Pullt Wochen-Preis + Splits und ruft die pure-Funktion. Preis-/Split-
        Pull-Fehler -> ValuationHistory(all na_data) + WARNING (fail-soft)."""
        def col(d, c):
            v = d.get(c)
            return None if v is None else float(v)

        annual = [
            AnnualFundamental(
                fy_end=c.date() if hasattr(c, "date") else c,
                net_income=col(ni, c), diluted_eps=col(eps, c),
                ebit=col(ebit, c), free_cashflow=col(fcf, c),
                total_debt=col(td, c), cash=col(cce, c))
            for c in cols
        ]
        try:
            weekly = self._yf.get_weekly_close_5y(ticker)
            splits = self._yf.get_splits(ticker)
        except DataSourceError as exc:
            logger.warning(
                "valuation history: %s price/split pull failed — %s "
                "(na_data)", ticker, exc)
            na = MultipleStats(status="na_data")
            return ValuationHistory(pe=na, ev_ebit=na, fcf_yield=na)
        return compute_valuation_history(
            weekly, annual, splits,
            listing_ccy=info.get("currency"),
            financial_ccy=info.get("financialCurrency"))
