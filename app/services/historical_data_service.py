from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_MIN_COMPLETE_YEARS = 3
_MAX_YEARS = 5


class HistoricalDataService(Protocol):
    def get_annual_series(self, ticker: str) -> dict[str, Any]: ...


def _row(df: Any, label: str) -> dict[Any, float | None]:
    if df is None or getattr(df, "empty", True) or label not in df.index:
        return {}
    return df.loc[label].to_dict()


class HistoricalDataServiceImpl:
    """ADR-5a: live multi-year quant from yfinance. Graceful on partial data."""

    def __init__(self, yfinance: Any) -> None:
        self._yf = yfinance

    def get_annual_series(self, ticker: str) -> dict[str, Any]:
        income, cash, bal = self._yf.get_annual_statements(ticker)
        info = self._yf.get_ticker_info(ticker)

        cols = list(getattr(income, "columns", []))[:_MAX_YEARS]
        years = [c.year for c in cols]

        rev = _row(income, "Total Revenue")
        gp = _row(income, "Gross Profit")
        oi = _row(income, "Operating Income")
        bb = _row(cash, "Repurchase Of Capital Stock")
        sh = _row(bal, "Share Issued")

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
            "shares_outstanding": [col(sh, c) for c in cols],
            "buyback_cashflow": [col(bb, c) for c in cols],
            "complete": len(years) >= _MIN_COMPLETE_YEARS,
        }
        if not series["complete"]:
            logger.warning(
                "historical: %s only %d years (<%d) — flagged partial",
                ticker, len(years), _MIN_COMPLETE_YEARS,
            )
        return series
