from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.models.run_record import FinalRunStatus, RunRecord

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
        self._started = False
        self._finished = False
        self._truncated = False
        self._steadiness_stale = 0
        self._steadiness_missing = 0

    def latest_prior_run(self) -> dict[str, Any] | None:
        """Newest run doc in the collection, read BEFORE start().

        After start() the newest doc is this run's own marker, hence the guard.
        Firestore failures propagate (DataSourceError) — the caller decides
        whether a failed read blocks the run."""
        if self._started:
            raise RuntimeError("latest_prior_run() must be called before start()")
        return self._firestore.get_latest(self._collection, order_by="run_id")

    def start(self) -> None:
        """Persist a status="running" marker under this run's id.

        finish() overwrites the same doc. A doc left at "running" therefore
        proves the run died before finish() — the next run surfaces it."""
        if self._started or self._finished:
            raise RuntimeError("RunTracker.start() called after start() or finish()")
        self._started = True
        marker = RunRecord(
            run_id=self._run_id, status="running", started_at=self._started_at
        )
        # Firestore failure propagates intentionally — fail loud, same as finish()
        self._firestore.set(
            self._collection, self._run_id, marker.model_dump(mode="json")
        )
        logger.info("run=%s status=running (start marker written)", self._run_id)

    def record_ticker(self, tokens_in: int, tokens_out: int) -> None:
        self._tickers_processed += 1
        self._tokens_in += tokens_in
        self._tokens_out += tokens_out

    def record_skip(self) -> None:
        self._tickers_skipped += 1

    def record_steadiness_lookup(self, status: str) -> None:
        """Zaehlt, wie oft die Jahresreihe abgelaufen (`stale`) oder gar nicht
        vorhanden (`missing`) war. Der Monatslauf laedt nicht nach, also ist das
        das einzige Signal dafuer, dass der Backfill faellig wird."""
        if status == "stale":
            self._steadiness_stale += 1
        elif status == "missing":
            self._steadiness_missing += 1

    def mark_truncated(self) -> None:
        """Signal that the run stopped early (e.g. token cap hit) — derives status=partial."""
        self._truncated = True

    def finish(self, status: FinalRunStatus | None = None) -> RunRecord:
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
            steadiness_stale=self._steadiness_stale,
            steadiness_missing=self._steadiness_missing,
        )
        record.estimated_cost_usd = record.compute_cost()
        # Firestore failure propagates intentionally — fail loud (CLAUDE.md convention)
        self._firestore.set(
            self._collection, self._run_id, record.model_dump(mode="json")
        )
        logger.info(
            "run=%s status=%s tickers=%d skipped=%d tokens_in=%d tokens_out=%d "
            "cost=$%.4f steadiness_stale=%d steadiness_missing=%d",
            self._run_id,
            status,
            self._tickers_processed,
            self._tickers_skipped,
            self._tokens_in,
            self._tokens_out,
            record.estimated_cost_usd,
            self._steadiness_stale,
            self._steadiness_missing,
        )
        return record
