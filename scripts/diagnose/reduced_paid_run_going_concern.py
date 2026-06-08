"""Reduced PAID acceptance run for the going-concern residual fix.

Runs the REAL end-to-end screener pipeline (yfinance + EDGAR + Gemini Flash Lite +
Firestore dev_ collections) over a SMALL basket of formerly-poisoned healthy US
large-caps + EU context — NOT the full universe (that is the budget/hard-stop risk
this whole gate sequence avoids). Output → output-test/, NO GitHub push.

Two-sided proof:
  (paid) Healthy US (esp. JNJ, the headline false-positive) now SURVIVE the EDGAR
         going-concern filter and reach Gemini scoring → appear in scored output.
  (free) Positive control FRQN (CIK 1624517) still flags has_going_concern=True →
         the fix did not neutralise genuine detection.

cmd.exe:  uv run python scripts/reduced_paid_run_going_concern.py
Requires: .env (FISHERSCREEN_*) + GCP ADC.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

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

# Small basket: formerly-poisoned healthy US large-caps (high-margin → pass basis
# filter → reach EDGAR → Gemini) + EU sanity. JNJ is the headline FP.
BASKET = ["MSFT", "AAPL", "JNJ", "KO", "PG", "V", "HON", "NOVO-B.CO", "SAP.DE"]
FRQN_CIK = "1624517"


def _us(tickers: list[str]) -> int:
    return sum(1 for t in tickers if "." not in t)


def main() -> None:
    output_dir = Path("output-test")
    output_dir.mkdir(exist_ok=True)

    screener = build_screener_pipeline()
    edgar = build_edgar_pipeline()
    gemini = build_gemini_pipeline()
    tracker = build_run_tracker()

    print(f"Reduced basket: {BASKET}\n")
    records, run_record, paths = run_screener(
        tickers=BASKET,
        yfinance=screener,
        edgar=edgar,
        gemini=gemini,
        run_tracker=tracker,
        output_dir=output_dir,
    )

    scored = [r.ticker for r in records]
    scored_us = [t for t in scored if "." not in t]
    jnj_scored = "JNJ" in scored

    print("\n" + "=" * 62)
    print("REDUCED PAID RUN — SUMMARY")
    print("=" * 62)
    print(f"Run ID     : {run_record.run_id}")
    print(f"Status     : {run_record.status}")
    print(f"Processed  : {run_record.tickers_processed} tickers")
    print(f"Tokens     : in={run_record.tokens_in_total} out={run_record.tokens_out_total}")
    print(f"Est. cost  : ${run_record.estimated_cost_usd:.5f}")
    print()
    print(f"Scored survivors ({len(scored)}): {scored}")
    print(f"  US scored: {scored_us}")
    print()
    print("=== TWO-SIDED ACCEPTANCE ===")
    print(f"  [{'OK' if scored_us else 'FAIL'}] Healthy US reach Gemini scoring (got {len(scored_us)})")
    print(f"  [{'OK' if jnj_scored else 'FAIL'}] JNJ (headline FP) NOT dropped — present in scored output")

    # Free positive control: genuine going-concern detection still fires.
    try:
        frqn = edgar.has_going_concern(FRQN_CIK)
    except Exception as exc:  # noqa: BLE001
        frqn = f"ERROR {exc}"
    print(f"  [{'OK' if frqn is True else 'FAIL'}] FRQN positive control has_going_concern={frqn} (expect True)")
    print()
    print("Output (output-test/, NOT pushed):")
    for p in paths:
        print(f"  {p}")
    print("=" * 62)


if __name__ == "__main__":
    main()
