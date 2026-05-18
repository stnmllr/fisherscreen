from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from app.deepdive.dossier_generator import generate_dossier
from app.deepdive.filing_parser import parse_filing
from app.deepdive.synthesis import run_synthesis
from app.models.deep_dive_record import DeepDiveRecord

logger = logging.getLogger(__name__)


def run_deep_dive(
    ticker: str,
    *,
    output_dir: Path,
    resolver: Any,
    filing_fetcher: Any,
    build_quant: Callable[..., tuple[Any, Any]],
    synthesizer: Any,
    token_cap: int,
    use_cache: bool,
) -> Path:
    logger.info("deepdive: start ticker=%s", ticker)

    # [1] ADR-Lookup
    resolved = resolver.resolve(ticker)

    # [2] EDGAR-Pull (local-FS cache, ADR-4)
    raw = filing_fetcher.get(resolved.cik, resolved.form_type, use_cache=use_cache)

    # [3] Filing-Parse
    parsed = parse_filing(raw.document_text, resolved.form_type)

    # [4] Quant-Join
    quant, coverage = build_quant(ticker)
    coverage.edgar = f"{resolved.form_type} via ADR"

    # [5] Gemini-Synthesis
    synthesis = run_synthesis(
        ticker=ticker,
        form_type=resolved.form_type,
        sections=parsed.sections,
        quant=quant,
        synthesizer=synthesizer,
        max_input_tokens=token_cap,
    )

    record = DeepDiveRecord(
        ticker=ticker,
        adr_ticker=resolved.adr_ticker,
        cik=resolved.cik,
        form_type=resolved.form_type,
        filing_sections=parsed.sections,
        section_flags=parsed.section_flags,
        quant_snapshot=quant,
        synthesis=synthesis,
        source_coverage=coverage,
    )

    # [6] Markdown-Output
    out = generate_dossier(record, output_dir)
    logger.info("deepdive: done ticker=%s -> %s", ticker, out.name)
    return out
