from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from app.models.run_record import RunRecord

if TYPE_CHECKING:
    from app.services.firestore_client import FirestoreClient

logger = logging.getLogger(__name__)


class RunTracker:
    def __init__(self, firestore: FirestoreClient, collection: str) -> None:
        self._firestore = firestore
        self._collection = collection
        now = datetime.now(timezone.utc)
        self._run_id = now.isoformat()
        self._started_at = now
        self._tickers_processed = 0
        self._tickers_skipped = 0
        self._tokens_in = 0
        self._tokens_out = 0
        self._finished = False
        self._truncated = False

    def record_ticker(self, tokens_in: int, tokens_out: int) -> None:
        self._tickers_processed += 1
        self._tokens_in += tokens_in
        self._tokens_out += tokens_out

    def record_skip(self) -> None:
        self._tickers_skipped += 1

    def mark_truncated(self) -> None:
        """Signal that the run stopped early (e.g. token cap hit) — derives status=partial."""
        self._truncated = True

    def finish(
        self, status: Literal["success", "partial", "aborted"] | None = None
    ) -> RunRecord:
        if self._finished:
            raise RuntimeError("RunTracker.finish() called more than once")
        self._finished = True
        if status is None:
            status = "partial" if self._truncated else "success"
        completed_at = datetime.now(timezone.utc)
        record = RunRecord(
            run_id=self._run_id,
            tickers_processed=self._tickers_processed,
            tickers_skipped=self._tickers_skipped,
            tokens_in_total=self._tokens_in,
            tokens_out_total=self._tokens_out,
            status=status,
            started_at=self._started_at,
            completed_at=completed_at,
        )
        record.estimated_cost_usd = record.compute_cost()
        # Firestore failure propagates intentionally — fail loud (CLAUDE.md convention)
        self._firestore.set(self._collection, self._run_id, record.model_dump(mode="json"))
        logger.info(
            "run=%s status=%s tickers=%d skipped=%d tokens_in=%d tokens_out=%d cost=$%.4f",
            self._run_id,
            status,
            self._tickers_processed,
            self._tickers_skipped,
            self._tokens_in,
            self._tokens_out,
            record.estimated_cost_usd,
        )
        return record
