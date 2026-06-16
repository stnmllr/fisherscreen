from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.gemini_client import GeminiScoreResult

if TYPE_CHECKING:
    from app.models.screener_record import ScreenerRecord
    from app.services.firestore_client import FirestoreClient
    from app.services.gemini_client import GeminiClient


class CachedGeminiClient:
    """Firestore-backed cache wrapper for GeminiClient.

    A fresh cache entry (within the configurable TTL, default 2 days) is returned
    with tokens_in=0 and tokens_out=0 to signal that no Gemini API call was made,
    keeping cost accounting accurate at the call site. TTL is kept below the monthly
    run cadence so each monthly run re-scores with current numbers.
    """

    def __init__(
        self,
        gemini: GeminiClient,
        firestore: FirestoreClient,
        collection: str,
        ttl_days: int = 2,
    ) -> None:
        self._gemini = gemini
        self._firestore = firestore
        self._collection = collection
        self._ttl_seconds = ttl_days * 24 * 3600

    def score_ticker(
        self,
        ticker: str,
        record: ScreenerRecord,
        max_input_tokens: int = 3000,
        max_output_tokens: int = 1000,
    ) -> GeminiScoreResult:
        cached = self._firestore.get(self._collection, ticker)
        dims = cached.get("dimensions") if cached else None
        if cached and dims is not None and self._is_fresh(cached):
            # Defensive: pre-v2 entries lack evidence/weakest/data_gaps — fall back
            # to empty so old cache docs don't crash. Still usable iff dimensions present.
            return GeminiScoreResult(
                dimensions=dims,
                evidence=cached.get("evidence") or {},
                weakest_dimension=cached.get("weakest_dimension", ""),
                data_gaps=cached.get("data_gaps") or [],
                tokens_in=0,
                tokens_out=0,
            )
        result = self._gemini.score_ticker(ticker, record, max_input_tokens, max_output_tokens)
        self._firestore.set(self._collection, ticker, {
            "dimensions": result.dimensions,
            "evidence": result.evidence,
            "weakest_dimension": result.weakest_dimension,
            "data_gaps": result.data_gaps,
            "_cached_at": datetime.now(timezone.utc).isoformat(),
        })
        return result

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
