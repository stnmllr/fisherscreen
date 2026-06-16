"""Firestore-backed cache for multi-year revenue series (oldest->newest).

Annual data changes yearly, so the TTL is long (default 400d) — unlike the deliberately
short Gemini score TTL. Only non-empty series are persisted: a failed/empty fetch is left
uncached so it retries next run rather than masking as a 400-day-stale empty."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.errors import DataSourceError
from app.services.income_statement import extract_revenue_series

if TYPE_CHECKING:
    from app.services.firestore_client import FirestoreClient
    from app.services.yfinance_client import YFinanceClient


class CachedRevenueSeries:
    def __init__(
        self,
        yfinance: "YFinanceClient",
        firestore: "FirestoreClient",
        collection: str,
        ttl_days: int = 400,
    ) -> None:
        self._yfinance = yfinance
        self._firestore = firestore
        self._collection = collection
        self._ttl_seconds = ttl_days * 24 * 3600

    def get_revenue_series(self, ticker: str) -> list[float]:
        cached = self._firestore.get(self._collection, ticker)
        if cached and "revenues" in cached and self._is_fresh(cached):
            return [float(x) for x in cached["revenues"]]
        try:
            stmt = self._yfinance.get_annual_statements(ticker)[0]
            revenues = extract_revenue_series(stmt)
        except DataSourceError:
            revenues = []
        if revenues:  # persist only successful, non-empty fetches
            self._firestore.set(
                self._collection,
                ticker,
                {
                    "revenues": revenues,
                    "_cached_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        return revenues

    def _is_fresh(self, cached: dict[str, Any]) -> bool:
        raw = cached.get("_cached_at")
        if not raw:
            return False
        try:
            cached_at = datetime.fromisoformat(raw)
        except ValueError:
            return False
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - cached_at).total_seconds() < self._ttl_seconds
