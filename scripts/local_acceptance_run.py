"""
Local acceptance test for the V3 basis-filter fix.

Runs the full screening pipeline against the real universe.
- Output goes to output-test/ (NOT output/)
- No GitHub push
- Real yfinance, EDGAR, Gemini, Firestore (dev_ collections)

Usage:
  uv run python scripts/local_acceptance_run.py

Requires: .env file with FISHERSCREEN_* variables + GCP Application Default Credentials
  gcloud auth application-default login
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Load .env before importing app modules so settings picks them up
from dotenv import load_dotenv

load_dotenv()

from app.logging_config import configure_logging
from app.screener.compose import (
    build_edgar_pipeline,
    build_gemini_pipeline,
    build_run_tracker,
    build_screener_pipeline,
)
from app.screener.runner import run_screener

configure_logging()
logger = logging.getLogger(__name__)


def _count_us_eu(tickers: list[str]) -> tuple[int, int]:
    us = sum(1 for t in tickers if "." not in t)
    return us, len(tickers) - us


def main() -> None:
    universe_path = Path("data/universe.json")
    with open(universe_path, encoding="utf-8") as f:
        tickers: list[str] = json.load(f)

    us_in, eu_in = _count_us_eu(tickers)
    logger.info("Universe loaded: %d tickers (US=%d, EU=%d)", len(tickers), us_in, eu_in)

    output_dir = Path("output-test")
    output_dir.mkdir(exist_ok=True)

    screener = build_screener_pipeline()
    edgar = build_edgar_pipeline()
    gemini = build_gemini_pipeline()
    tracker = build_run_tracker()

    records, run_record, paths = run_screener(
        tickers=tickers,
        yfinance=screener,
        edgar=edgar,
        gemini=gemini,
        run_tracker=tracker,
        output_dir=output_dir,
    )

    us_out, eu_out = _count_us_eu([r.ticker for r in records])

    # Crosshit analysis from the Crosshits file
    crosshits_file = next((p for p in paths if "Crosshits" in p.name), None)
    top50_us = 0
    top50_eu = 0
    if crosshits_file and crosshits_file.exists():
        content = crosshits_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "| " in line and line.strip().startswith("|"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2 and parts[0].isdigit():
                    ticker = parts[1]
                    if "." not in ticker:
                        top50_us += 1
                    else:
                        top50_eu += 1

    print("\n" + "=" * 60)
    print("LOCAL ACCEPTANCE RUN — SUMMARY")
    print("=" * 60)
    print(f"Run ID       : {run_record.run_id}")
    print(f"Status       : {run_record.status}")
    print(f"Processed    : {run_record.tickers_processed} tickers")
    print(f"Est. cost    : ${run_record.estimated_cost_usd:.4f}")
    print()
    print(f"Universe in  : {len(tickers)} (US={us_in}, EU={eu_in})")
    print(f"Scored out   : {len(records)} (US={us_out}, EU={eu_out})")
    print()
    print(f"Top-50 Crosshits: US={top50_us}, EU={top50_eu}")
    print()
    print("Acceptance criteria:")
    ok_region_log = us_out > 0
    ok_top50 = top50_us >= 15
    print(f"  [{'OK' if ok_region_log else 'FAIL'}] US tickers in Gemini-scored output (got {us_out})")
    print(f"  [{'OK' if ok_top50 else 'FAIL'}] >= 15 US in Top-50 Crosshits (got {top50_us})")
    print()
    print(f"Output files written to output-test/ (NOT synced to GitHub):")
    for p in paths:
        print(f"  {p}")
    print("=" * 60)

    if not ok_region_log or not ok_top50:
        sys.exit(1)


if __name__ == "__main__":
    main()
