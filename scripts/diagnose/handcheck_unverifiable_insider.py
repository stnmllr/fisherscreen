"""Hand-check: print the Insider line and the Executive Summary of a
quant-only dossier built from an `unverifiable_identity` verdict, so the
former contradiction between the two is visible (or visibly gone).

Run: uv run python scripts\\handcheck_unverifiable_insider.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.deepdive.eu_adr_resolution import unverifiable_identity  # noqa: E402
from app.deepdive.pipeline import run_deep_dive  # noqa: E402
from app.models.deep_dive_record import (  # noqa: E402
    PointInTimeQuant,
    QuantSnapshot,
    SourceCoverage,
)

TICKER = "EDV.L"


def _section(content: str, heading: str) -> str:
    return content.split(heading, 1)[1].split("\n## ", 1)[0].strip()


def main() -> None:
    verdict = unverifiable_identity(
        TICKER,
        cause="keine OpenFIGI-Heimatlinie stimmte mit dem Referenznamen überein",
    )
    resolver = MagicMock()
    resolver.resolve.return_value = verdict

    def build_quant(ticker, *, use_cache):
        return (
            QuantSnapshot(
                point_in_time=PointInTimeQuant(ticker=ticker, name="Endeavour Mining")
            ),
            SourceCoverage(),
        )

    with tempfile.TemporaryDirectory() as tmp:
        out = run_deep_dive(
            TICKER,
            output_dir=Path(tmp),
            resolver=resolver,
            filing_fetcher=None,
            build_quant=build_quant,
            synthesizer=None,
            token_cap=1,
            use_cache=True,
            peers=None,
            peer_rationale=None,
            is_tty=False,
            peer_resolver=lambda **_: None,
        )
        text = out.read_text(encoding="utf-8")

    body = text.split("---", 2)[2]
    print("=== Quellenlage (source_coverage.insider) ===")
    for line in body.splitlines():
        if "Insider" in line and not line.startswith("**"):
            print(line)
    print()
    print("=== ## Insider-Transaktionen ===")
    print(_section(body, "## Insider-Transaktionen"))
    print()
    print("=== ## Executive Summary ===")
    print(_section(body, "## Executive Summary"))


if __name__ == "__main__":
    main()
