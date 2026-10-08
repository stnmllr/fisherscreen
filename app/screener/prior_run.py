"""Surface an incomplete previous monthly run in this month's outputs.

Stephan's decision (spec 2026-10-08, "Entscheidungen" 2): no e-mail alert.
The next run reads the newest `dev_screener_runs` doc before writing its own
start marker; if that run did not end in `success`, a warning block goes to the
top of the three monthly Markdown files and a WARNING is logged. The run is
never blocked — blocking would turn a one-off failure into a permanent outage.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.errors import DataSourceError

if TYPE_CHECKING:
    from app.screener.run_tracker import RunTracker

logger = logging.getLogger(__name__)

_INCOMPLETE_STATUSES = frozenset({"running", "aborted", "partial"})
_CLEAN_STATUS = "success"

_STATUS_HINT = {
    "running": " (`running` heißt: der Lauf ist abgestürzt oder wurde beendet, "
    "bevor er seinen Abschluss schreiben konnte)",
}


def _incomplete_block(run_id: str, status: str) -> str:
    return (
        f"> ⚠️ **Vorlauf unvollständig:** Der Lauf vom {run_id} endete mit Status "
        f"`{status}`{_STATUS_HINT.get(status, '')}. Ergebnisse dieses Monats prüfen; "
        f"Ursache in Cloud Logging / Job-Ausführungen."
    )


def _unchecked_block(reason: str) -> str:
    return (
        f"> ⚠️ **Vorlauf nicht geprüft:** Der Status des vorigen Laufs konnte nicht "
        f"ermittelt werden ({reason}). Ob er vollständig war, ist unbekannt; "
        f"`dev_screener_runs` und Cloud Logging prüfen."
    )


def check_prior_run(tracker: RunTracker) -> str | None:
    """Return a Markdown warning block, or None if the prior run is clean/absent.

    Must run before tracker.start(). A failed Firestore read does not abort the
    run but yields its own "nicht geprüft" block, distinct from "no prior run"
    (None). Exceptions other than DataSourceError propagate."""
    try:
        prior = tracker.latest_prior_run()
    except DataSourceError as exc:
        logger.warning("prior run: status could not be read — %s", exc)
        return _unchecked_block("Firestore-Lesefehler")

    if prior is None:
        logger.info("prior run: none found — first tracked run")
        return None
    if not isinstance(prior, dict):
        logger.warning("prior run: unexpected doc type %s", type(prior).__name__)
        return _unchecked_block("Eintrag unlesbar")

    run_id = str(prior.get("run_id", "?"))
    status = prior.get("status")
    if status == _CLEAN_STATUS:
        logger.info("prior run: run_id=%s status=success", run_id)
        return None
    if status in _INCOMPLETE_STATUSES:
        logger.warning(
            "prior run incomplete: run_id=%s status=%s — warning rendered into outputs",
            run_id,
            status,
        )
        return _incomplete_block(run_id, status)

    logger.warning("prior run: run_id=%s has unknown status %r", run_id, status)
    return _unchecked_block(f"unbekannter Status `{status}`")
