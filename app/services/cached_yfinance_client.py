from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.firestore_client import FirestoreClient
    from app.services.yfinance_client import YFinanceClient

_TTL_SECONDS = 24 * 3600  # 24 hours


class CachedYFinanceClient:
    def __init__(
        self,
        yfinance: YFinanceClient,
        firestore: FirestoreClient,
        collection: str,
    ) -> None:
        self._yfinance = yfinance
        self._firestore = firestore
        self._collection = collection

    def get_ticker_info(self, ticker: str) -> dict[str, Any]:
        cached = self._firestore.get(self._collection, ticker)
        if cached and self._is_fresh(cached):
            return {k: v for k, v in cached.items() if k != "_cached_at"}
        data = self._yfinance.get_ticker_info(ticker)
        self._firestore.set(
            self._collection,
            ticker,
            {**data, "_cached_at": datetime.now(timezone.utc).isoformat()},
        )
        return data

    def get_historical(self, ticker: str, period: str) -> Any:
        return self._yfinance.get_historical(ticker, period)

    def get_financials(self, ticker: str) -> Any:
        return self._yfinance.get_financials(ticker)

    def _is_fresh(self, cached: dict[str, Any]) -> bool:
        cached_at_str = cached.get("_cached_at")
        if not cached_at_str:
            return False
        cached_at = datetime.fromisoformat(cached_at_str)
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - cached_at).total_seconds() < _TTL_SECONDS
