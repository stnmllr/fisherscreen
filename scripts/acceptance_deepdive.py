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

from google.auth import default as _google_auth_default
from google.auth.exceptions import DefaultCredentialsError

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


def check_prerequisites() -> list[str]:
    """Return a list of human-readable 'missing prerequisite' messages for a
    local Tool B deep-dive run. Empty list = all prerequisites satisfied.
    No network calls except google.auth.default() credential resolution
    (local, no API request)."""
    missing: list[str] = []

    if not settings.edgar_user_agent:
        missing.append(
            "FISHERSCREEN_EDGAR_USER_AGENT not set (.env) — SEC EDGAR requires "
            "a User-Agent. .env.example has a valid value."
        )
    if not settings.gemini_api_key:
        missing.append(
            "FISHERSCREEN_GEMINI_API_KEY not set (.env) — required for Gemini "
            "Pro synthesis."
        )
    if not settings.gcp_project_id:
        missing.append(
            "FISHERSCREEN_GCP_PROJECT_ID not set (.env, e.g. fisherscreen-prod) "
            "— required for the Firestore PIT-cache read."
        )

    try:
        _google_auth_default()
    except DefaultCredentialsError:
        missing.append(
            "GCP ADC not configured — run: gcloud auth application-default login"
        )

    return missing


def main() -> int:
    problems = check_prerequisites()
    if problems:
        print("PRE-FLIGHT FAILED — local prerequisites missing:")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nFix (cmd.exe):\n"
            "  copy .env.example .env   &  edit FISHERSCREEN_GEMINI_API_KEY\n"
            "  gcloud auth application-default login\n"
            "  uv run python -m scripts.acceptance_deepdive"
        )
        return 2

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
