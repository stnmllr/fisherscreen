"""Acceptance gate for Tool B Phase B.1 (manual, NOT a unit test).

Runs a real deep dive on Novo Nordisk against live EDGAR + Firestore +
yfinance + Gemini Pro and writes the dossier. Stephan reads the dossier
and judges decision-usefulness (spec §1 exit criterion).

SOPRA-EPDR: invoke as a module, never the .exe shim (CLAUDE.md):
  uv run python -m scripts.acceptance_deepdive
or:
  uv run python scripts/acceptance_deepdive.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.config import settings
from app.deepdive.compose import (
    build_adr_resolver,
    build_filing_fetcher,
    build_quant_builder,
    build_synthesizer,
)
from app.deepdive.pipeline import run_deep_dive

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

_TICKER = "NOVO-B.CO"


def main() -> int:
    print(f"\nRunning real deep dive for {_TICKER} "
          f"(model={settings.deepdive_gemini_model}, "
          f"token_cap={settings.deepdive_token_cap})\n")
    try:
        out = run_deep_dive(
            _TICKER,
            output_dir=Path(settings.output_dir),
            resolver=build_adr_resolver(),
            filing_fetcher=build_filing_fetcher(),
            build_quant=build_quant_builder(),
            synthesizer=build_synthesizer(None),
            token_cap=settings.deepdive_token_cap,
            use_cache=True,
        )
    except Exception as exc:
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"\nDossier written: {out}")
    print("Manual gate: Stephan liest das Dossier und urteilt "
          "(entscheidungs-nützlich? / Synthesis-Struktur anders?).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
