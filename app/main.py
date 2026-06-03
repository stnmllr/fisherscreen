from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.config import settings
from app.logging_config import configure_logging
from app.screener.compose import (
    build_edgar_pipeline,
    build_gemini_pipeline,
    build_github_client,
    build_run_tracker,
    build_screener_pipeline,
)
from app.screener.runner import run_filter_preview, run_screener

# Configure structured logging when uvicorn imports this module, so app.* INFO
# aggregates are actually emitted in production (otherwise the root last-resort
# handler drops everything below WARNING). force=True wins over prior basicConfig.
configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(title="FisherScreen")

_UNIVERSE_PATH = Path(__file__).parent.parent / "data" / "universe.json"


def _load_universe() -> list[str]:
    with _UNIVERSE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run/monthly")
def run_monthly(dry_run: bool = False) -> dict[str, Any]:
    tickers = _load_universe()
    yfinance = build_screener_pipeline()
    edgar = build_edgar_pipeline()

    if dry_run:
        report = run_filter_preview(tickers, yfinance, edgar)
        logger.info("monthly run: free dry-run (filters only, $0) — no Gemini, no GitHub push")
        return {"dry_run": True, **report.to_dict()}

    gemini = build_gemini_pipeline()
    tracker = build_run_tracker()
    github = build_github_client()
    output_dir = Path(settings.output_dir)

    records, run_record, paths = run_screener(
        tickers=tickers,
        yfinance=yfinance,
        edgar=edgar,
        gemini=gemini,
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

    logger.info("monthly run complete: run_id=%s paths=%d", run_record.run_id, len(paths))
    return run_record.model_dump(mode="json")
