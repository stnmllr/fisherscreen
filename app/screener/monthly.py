"""Tool-A monthly run as one callable pipeline.

Shared by the HTTP route ``POST /run/monthly`` (manual runs, dry-run) and the
Cloud Run Job entrypoint ``app.monthly_job`` (scheduled run). Keeping a single
body guarantees both paths screen, render and push identically.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import settings
from app.screener.compose import (
    build_edgar_annual_series,
    build_edgar_pipeline,
    build_github_client,
    build_revenue_series_cache,
    build_run_tracker,
    build_screener_pipeline,
)
from app.screener.runner import run_filter_preview, run_screener

logger = logging.getLogger(__name__)

# Repo root / data / universe.json. In the container WORKDIR is /app and the
# Dockerfile copies app/ and data/ side by side, so this resolves to
# /app/data/universe.json there as well.
_UNIVERSE_PATH = Path(__file__).resolve().parents[2] / "data" / "universe.json"


def _load_universe() -> list[str]:
    with _UNIVERSE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def run_monthly_pipeline(dry_run: bool = False) -> dict[str, Any]:
    """Run the monthly screener end to end and return a JSON-ready summary.

    dry_run=True runs only the free filter stages and writes funnel artifacts:
    no run tracker, no Firestore run doc, no GitHub push. The full run returns
    the RunRecord dump (incl. ``status``) after pushing every output file.
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

    records, run_record, paths = run_screener(
        tickers=tickers,
        yfinance=yfinance,
        edgar=edgar,
        revenue_cache=revenue_cache,
        annual_series=annual_series,
        run_tracker=tracker,
        output_dir=output_dir,
    )

    for path in paths:
        if not path.exists():
            logger.warning("monthly run: output file missing, skipping push: %s", path)
            continue
        github.push_file(
            path.as_posix(),
            path.read_text(encoding="utf-8"),
            f"chore: monthly screener output {run_record.run_id[:7]} [skip ci]",
        )

    logger.info(
        "monthly run complete: run_id=%s paths=%d", run_record.run_id, len(paths)
    )
    return run_record.model_dump(mode="json")
