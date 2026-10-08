from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

from app.config import settings
from app.logging_config import configure_logging
from app.screener.compose import build_github_client
from app.screener.monthly import run_monthly_pipeline

# Configure structured logging when uvicorn imports this module, so app.* INFO
# aggregates are actually emitted in production (otherwise the root last-resort
# handler drops everything below WARNING). force=True wins over prior basicConfig.
configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(title="FisherScreen")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


_SELFTEST_PUSH_PATH = "output/.smoke/push_selftest.md"


@app.post("/selftest/push")
def selftest_push() -> dict[str, str]:
    """Push one sentinel file to origin to prove prod GitHub egress works.

    Timeboxed proof-of-egress: $0, no Gemini/run-tracker/screener/yfinance/EDGAR.
    Side effect is limited to a single GitHub Contents-API PUT. Lets
    DataSourceError propagate so a failed push surfaces as a 500."""
    github = build_github_client()
    timestamp = datetime.now(timezone.utc).isoformat()
    content = (
        f"# Prod push self-test\n\n"
        f"Automated prod-egress self-test — this file proves the running service "
        f"can push to origin/main. Safe to delete.\n\n"
        f"timestamp: {timestamp}\n"
    )
    github.push_file(
        _SELFTEST_PUSH_PATH,
        content,
        f"chore: prod push self-test {timestamp} [skip ci]",
    )
    logger.info(
        "selftest push complete: path=%s timestamp=%s", _SELFTEST_PUSH_PATH, timestamp
    )
    return {
        "selftest": "push",
        "pushed_path": _SELFTEST_PUSH_PATH,
        "repo": settings.github_repo,
        "branch": settings.github_branch,
        "timestamp": timestamp,
    }


@app.post("/run/monthly")
def run_monthly(dry_run: bool = False) -> dict[str, Any]:
    """Manual monthly run / free dry-run. The scheduled run uses app.monthly_job;
    both share run_monthly_pipeline. Stays sync: FastAPI runs it in the threadpool."""
    return run_monthly_pipeline(dry_run=dry_run)
