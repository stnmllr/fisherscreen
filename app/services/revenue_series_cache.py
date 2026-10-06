"""Firestore-backed cache for multi-year revenue series (oldest->newest).

The series drives the growth axis (median annual revenue growth), so the newest
fiscal year must not sit stale for long: TTL 120 days, not 400. With 400 days a
fiscal year could be up to ~17 months old before its successor was fetched.

**Jitter, derived from the ticker.** A backfill writes every entry on one day (all
~1,000 entries on 2026-06-22); with a flat TTL they would all expire in the same
monthly run and hand it ~1,000 live yfinance fetches against the hard 1800 s
deadline. +/- 30 days spreads the expiries over two months. The offset is a hash
of the ticker, not a random draw stored at write time (the pattern of
CachedEdgarAnnualSeries): the existing entries carry only `_cached_at`, so a
stored expiry would leave the whole backlog on one flat TTL. A ticker hash spreads the backlog
too, without a schema change, and is stable between reads -- the same entry never
flips between fresh and stale. hashlib, not hash(): str hashing is salted per
process.

Only non-empty series are persisted: a failed/empty fetch is left uncached so it
retries next run rather than masking as a stale empty."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from app.errors import DataSourceError
from app.services.income_statement import extract_revenue_series

if TYPE_CHECKING:
    from app.services.firestore_client import FirestoreClient
    from app.services.yfinance_client import YFinanceClient

DEFAULT_TTL_DAYS = 120
DEFAULT_TTL_JITTER_DAYS = 30
_HASH_BYTES = 8


def ttl_jitter_offset_days(ticker: str, jitter_days: int) -> float:
    """Deterministic TTL offset in [-jitter_days, +jitter_days) for `ticker`,
    uniformly spread across tickers."""
    digest = hashlib.sha256(ticker.encode("utf-8")).digest()[:_HASH_BYTES]
    unit = int.from_bytes(digest, "big") / 2 ** (8 * _HASH_BYTES)  # [0, 1)
    return jitter_days * (2 * unit - 1)


class CachedRevenueSeries:
    def __init__(
        self,
        yfinance: "YFinanceClient",
        firestore: "FirestoreClient",
        collection: str,
        ttl_days: int = DEFAULT_TTL_DAYS,
        ttl_jitter_days: int = DEFAULT_TTL_JITTER_DAYS,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not 0 <= ttl_jitter_days < ttl_days:
            # A jitter as large as the TTL could expire an entry on write.
            raise ValueError(
                f"ttl_jitter_days ({ttl_jitter_days}) must be in [0, ttl_days "
                f"({ttl_days}))"
            )
        self._yfinance = yfinance
        self._firestore = firestore
        self._collection = collection
        self._ttl_days = ttl_days
        self._jitter_days = ttl_jitter_days
        self._now = now if now is not None else (lambda: datetime.now(timezone.utc))

    def get_revenue_series(self, ticker: str) -> list[float]:
        cached = self._firestore.get(self._collection, ticker)
        if cached and "revenues" in cached and self._is_fresh(ticker, cached):
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
                    "_cached_at": self._now().isoformat(),
                },
            )
        return revenues

    def _is_fresh(self, ticker: str, cached: dict[str, Any]) -> bool:
        raw = cached.get("_cached_at")
        if not raw:
            return False
        try:
            cached_at = datetime.fromisoformat(raw)
        except ValueError:
            return False
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        ttl = self._ttl_days + ttl_jitter_offset_days(ticker, self._jitter_days)
        return self._now() - cached_at < timedelta(days=ttl)
