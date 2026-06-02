from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient, GoingConcernHit
    from app.services.firestore_client import FirestoreClient

_TTL_SECONDS = 7 * 24 * 3600  # 7 days


class CachedEdgarClient:
    """Firestore-backed cache wrapper for EdgarClient.

    Both EDGAR signals (has_restatement, has_going_concern) are stored together
    in a single Firestore document keyed by CIK, so the second method call for
    the same CIK within the TTL window never hits the EDGAR API.

    has_active_enforcement is a stub that always delegates to EDGAR without
    caching — it always returns False and is not worth caching.
    """

    def __init__(
        self,
        edgar: EdgarClient,
        firestore: FirestoreClient,
        collection: str,
    ) -> None:
        self._edgar = edgar
        self._firestore = firestore
        self._collection = collection

    def _fetch_and_cache(self, cik: str) -> dict[str, Any]:
        """Return cached EDGAR signals for cik, re-fetching from EDGAR if stale or absent."""
        cached = self._firestore.get(self._collection, cik)
        if cached and self._is_fresh(cached):
            return cached
        data: dict[str, Any] = {
            "has_restatement": self._edgar.has_restatement(cik),
            "has_going_concern": self._edgar.has_going_concern(cik),
            "_cached_at": datetime.now(timezone.utc).isoformat(),
        }
        self._firestore.set(self._collection, cik, data)
        return data

    def get_cik(self, ticker: str) -> str | None:
        """Delegate directly to the underlying EDGAR client — not cached."""
        return self._edgar.get_cik(ticker)

    def has_restatement(self, cik: str, years: int = 3) -> bool:
        return self._fetch_and_cache(cik)["has_restatement"]

    def has_going_concern(self, cik: str, months: int = 24) -> bool:
        return self._fetch_and_cache(cik)["has_going_concern"]

    def going_concern_hit(self, cik: str, months: int = 24) -> GoingConcernHit | None:
        """Delegate directly to EDGAR — used only for the going-concern drop report
        (the few dropped names), so re-scanning uncached is acceptable."""
        return self._edgar.going_concern_hit(cik, months)

    def has_active_enforcement(self, cik: str) -> bool:
        """Delegate directly to EDGAR — not cached (always returns False stub)."""
        return self._edgar.has_active_enforcement(cik)

    def _is_fresh(self, cached: dict[str, Any]) -> bool:
        """Return True if cached entry exists and is within the 7-day TTL."""
        cached_at_str = cached.get("_cached_at")
        if not cached_at_str:
            return False
        cached_at = datetime.fromisoformat(cached_at_str)
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - cached_at).total_seconds() < _TTL_SECONDS
