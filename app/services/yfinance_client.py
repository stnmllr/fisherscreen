from typing import Any, Protocol

import yfinance as yf

from app.errors import DataSourceError


class YFinanceClient(Protocol):
    def get_ticker_info(self, ticker: str) -> dict[str, Any]: ...
    def get_historical(self, ticker: str, period: str) -> Any: ...
    def get_financials(self, ticker: str) -> dict[str, Any]: ...


class YFinanceClientImpl:
    def get_ticker_info(self, ticker: str) -> dict[str, Any]:
        try:
            data = yf.Ticker(ticker).info
        except Exception as exc:
            raise DataSourceError(f"yfinance failed for {ticker}: {exc}") from exc
        if not data:
            raise DataSourceError(f"yfinance returned empty info for {ticker}")
        return data

    def get_historical(self, ticker: str, period: str) -> Any:
        try:
            return yf.Ticker(ticker).history(period=period)
        except Exception as exc:
            raise DataSourceError(f"yfinance history failed for {ticker}: {exc}") from exc

    def get_financials(self, ticker: str) -> dict[str, Any]:
        try:
            return yf.Ticker(ticker).financials
        except Exception as exc:
            raise DataSourceError(f"yfinance financials failed for {ticker}: {exc}") from exc
