"""Tool-A monthly run as one callable pipeline.

Shared by the HTTP route ``POST /run/monthly`` (manual runs, dry-run) and the
Cloud Run Job entrypoint ``app.monthly_job`` (scheduled run). Keeping a single
body guarantees both paths screen, render and push identically.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.errors import DataSourceError, OutputError
from app.screener.compose import (
    build_edgar_annual_series,
    build_edgar_pipeline,
    build_github_client,
    build_revenue_series_cache,
    build_run_tracker,
    build_screener_pipeline,
)
from app.screener.prior_run import check_prior_run
from app.screener.runner import run_filter_preview, run_screener

if TYPE_CHECKING:
    from app.screener.run_tracker import RunTracker
    from app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)

# Firestore doc field, not a log: keep it short enough to read at a glance.
_MAX_FAILURE_REASON_CHARS = 500

# Repo root / data / universe.json. In the container WORKDIR is /app and the
# Dockerfile copies app/ and data/ side by side, so this resolves to
# /app/data/universe.json there as well.
_UNIVERSE_PATH = Path(__file__).resolve().parents[2] / "data" / "universe.json"


def _load_universe() -> list[str]:
    with _UNIVERSE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _push_outputs(github: GitHubClient, paths: list[Path], run_id: str) -> None:
    """Push every output file; a missing file fails the run before any push."""
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise OutputError(
            "monthly run: output files missing, nothing pushed: "
            + ", ".join(p.as_posix() for p in missing)
        )
    for path in paths:
        github.push_file(
            path.as_posix(),
            path.read_text(encoding="utf-8"),
            f"chore: monthly screener output {run_id[:7]} [skip ci]",
        )


def _persist_aborted(tracker: RunTracker, exc: Exception) -> None:
    """Re-mark the finished run as aborted; never masks the original error."""
    reason = f"{type(exc).__name__}: {exc}"[:_MAX_FAILURE_REASON_CHARS]
    logger.error("monthly run failed after finish: %s", reason)
    try:
        tracker.mark_failed_after_finish(reason)
    except DataSourceError as persist_exc:
        logger.error(
            "monthly run: could not persist status=aborted (%s); original failure: %s",
            persist_exc,
            reason,
        )


def run_monthly_pipeline(dry_run: bool = False) -> dict[str, Any]:
    """Run the monthly screener end to end and return a JSON-ready summary.

    dry_run=True runs only the free filter stages and writes funnel artifacts:
    no run tracker, no Firestore run doc, no GitHub push. The full run checks
    the previous run doc (warning block in the outputs if it was incomplete),
    writes its own status="running" marker, screens, and returns the RunRecord
    dump (incl. ``status``) after pushing every output file.
    Exceptions propagate on purpose — callers decide how a failure surfaces
    (HTTP 500 for the route, non-zero exit code for the job).
    """
    tickers = _load_universe()
    yfinance = build_screener_pipeline()
    edgar = build_edgar_pipeline()

    if dry_run:
        output_dir = Path(settings.output_dir)
        report = run_filter_preview(tickers, yfinance, edgar, output_dir=output_dir)
        logger.info(
            "monthly run: free dry-run (filters only, $0) — funnel artifacts written, no Gemini/GitHub"
        )
        return {"dry_run": True, **report.to_dict()}

    revenue_cache = build_revenue_series_cache()
    annual_series = build_edgar_annual_series()
    tracker = build_run_tracker()
    github = build_github_client()
    output_dir = Path(settings.output_dir)

    # Order matters: read the prior run BEFORE writing our own start marker,
    # otherwise the newest doc would be this run's "running" marker.
    prior_run_warning = check_prior_run(tracker)
    tracker.start()

    try:
        _, run_record, paths = run_screener(
            tickers=tickers,
            yfinance=yfinance,
            edgar=edgar,
            revenue_cache=revenue_cache,
            annual_series=annual_series,
            run_tracker=tracker,
            output_dir=output_dir,
            prior_run_warning=prior_run_warning,
        )
        _push_outputs(github, paths, run_record.run_id)
    except Exception as exc:
        # Not swallowed: re-raised below. Before finish() the doc is still
        # "running", which already marks the failure; after finish() it says
        # "success" and has to be corrected, or the next run would not warn.
        if tracker.finished:
            _persist_aborted(tracker, exc)
        raise

    logger.info(
        "monthly run complete: run_id=%s paths=%d", run_record.run_id, len(paths)
    )
    return run_record.model_dump(mode="json")
