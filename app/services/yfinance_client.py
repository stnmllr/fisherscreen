from typing import Any, Protocol

import yfinance as yf

from app.errors import DataSourceError


class YFinanceClient(Protocol):
    def get_ticker_info(self, ticker: str) -> dict[str, Any]: ...
    def get_historical(self, ticker: str, period: str) -> Any: ...
    def get_financials(self, ticker: str) -> Any: ...
    def get_fx_rate(self, currency: str) -> float: ...


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
