"""Cloud Run Job entrypoint for the scheduled Tool-A monthly run.

Invocation: ``uv run python -m app.monthly_job [--dry-run]``.

The exit code IS the failure signal: Cloud Run marks the execution "Failed"
on a non-zero exit, so anything other than a full run ending in status
"success" returns 1. The HTTP route POST /run/monthly shares the same
pipeline and stays for manual runs and the dry-run.
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.logging_config import configure_logging
from app.screener.monthly import run_monthly_pipeline

logger = logging.getLogger(__name__)

_EXIT_OK = 0
_EXIT_FAILED = 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.monthly_job",
        description="Run the Tool-A monthly screener once (Cloud Run Job).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="filters only, $0: no run doc, no scoring outputs, no GitHub push",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_logging()
    logger.info("monthly job: start (dry_run=%s)", args.dry_run)

    try:
        result = run_monthly_pipeline(dry_run=args.dry_run)
    except Exception:
        # Not swallowed: logged with traceback, and the non-zero exit fails the
        # Cloud Run Job execution. The run doc (if started) stays "running",
        # which the next run surfaces as a warning in its outputs.
        logger.exception("monthly job: run failed with an exception")
        return _EXIT_FAILED

    if args.dry_run:
        logger.info("monthly job: dry-run complete")
        return _EXIT_OK

    status = result.get("status")
    if status != "success":
        logger.error(
            "monthly job: run %s finished with status=%s — exiting non-zero",
            result.get("run_id"),
            status,
        )
        return _EXIT_FAILED

    logger.info(
        "monthly job: run %s finished with status=success", result.get("run_id")
    )
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
