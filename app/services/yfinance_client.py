from typing import Any, Protocol

import yfinance as yf

from app.errors import DataSourceError
from app.models.deep_dive_record import ForwardEstimates


def _growth_at(frame: Any, period: str) -> float | None:
    """Defensively pull the 'growth' value for a yfinance estimate
    DataFrame index label (e.g. '0y', '+1y'). Tolerates None frame,
    missing index, missing 'growth' column, NaN -> None."""
    if frame is None:
        return None
    try:
        if "growth" not in getattr(frame, "columns", []):
            return None
        if period not in frame.index:
            return None
        val = frame.loc[period, "growth"]
    except Exception:
        return None
    try:
        if val is None:
            return None
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


class YFinanceClient(Protocol):
    def get_ticker_info(self, ticker: str) -> dict[str, Any]: ...
    def get_historical(self, ticker: str, period: str) -> Any: ...
    def get_financials(self, ticker: str) -> Any: ...
    def get_annual_statements(self, ticker: str) -> Any: ...
    def get_fx_rate(self, currency: str) -> float: ...
    def get_forward_estimates(
        self, ticker: str
    ) -> ForwardEstimates | None: ...


class YFinanceClientImpl:
    def get_ticker_info(self, ticker: str) -> dict[str, Any]:
        try:
            data = yf.Ticker(ticker).info
        except Exception as exc:
            raise DataSourceError(f"yfinance failed for {ticker}: {exc}") from exc
        # NOTE: does not catch partial-data dicts (e.g. single-key responses from degraded yfinance state)
        if not data:
            raise DataSourceError(f"yfinance returned empty info for {ticker}")
        return data

    def get_historical(self, ticker: str, period: str) -> Any:
        # Empty DataFrame (delisted ticker) is a valid result; callers decide how to handle it
        try:
            return yf.Ticker(ticker).history(period=period)
        except Exception as exc:
            raise DataSourceError(f"yfinance history failed for {ticker}: {exc}") from exc

    def get_financials(self, ticker: str) -> Any:
        # Returns a pandas DataFrame, not a dict
        try:
            return yf.Ticker(ticker).financials
        except Exception as exc:
            raise DataSourceError(f"yfinance financials failed for {ticker}: {exc}") from exc

    def get_annual_statements(self, ticker: str) -> Any:
        # Returns (income_stmt, cashflow, balance_sheet) DataFrames.
        try:
            t = yf.Ticker(ticker)
            return (t.income_stmt, t.cashflow, t.balance_sheet)
        except Exception as exc:
            raise DataSourceError(
                f"yfinance statements failed for {ticker}: {exc}"
            ) from exc

    def get_forward_estimates(self, ticker: str) -> ForwardEstimates | None:
        """Best-effort forward-consensus growth (fractions). Hard yfinance
        failure -> DataSourceError; any missing piece -> that field None."""
        try:
            t = yf.Ticker(ticker)
            eps = t.earnings_estimate
            rev = t.revenue_estimate
        except Exception as exc:
            raise DataSourceError(
                f"yfinance forward estimates failed for {ticker}: {exc}"
            ) from exc
        return ForwardEstimates(
            eps_growth_cy=_growth_at(eps, "0y"),
            eps_growth_ny=_growth_at(eps, "+1y"),
            revenue_growth_cy=_growth_at(rev, "0y"),
            revenue_growth_ny=_growth_at(rev, "+1y"),
        )

    def get_fx_rate(self, currency: str) -> float:
        """Return conversion rate from `currency` to EUR (e.g. USD → 0.92)."""
        if currency == "EUR":
            return 1.0
        fx_ticker = f"{currency}EUR=X"
        try:
            data = yf.Ticker(fx_ticker).info
            rate = data.get("regularMarketPrice") or data.get("price")
            if not rate:
                raise DataSourceError(f"No FX rate found for {fx_ticker}")
            return float(rate)
        except DataSourceError:
            raise
        except Exception as exc:
            raise DataSourceError(f"yfinance FX rate failed for {currency}: {exc}") from exc
