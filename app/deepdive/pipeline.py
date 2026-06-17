from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from app.deepdive.dossier_generator import generate_dossier
from app.errors import DataSourceError
from app.deepdive.filing_parser import parse_filing
from app.deepdive.insider_block import insider_coverage_label
from app.deepdive.insider_summary import compute_insider_summary
from app.deepdive.synthesis import run_synthesis
from app.models.deep_dive_record import DeepDiveRecord, InsiderSummary

logger = logging.getLogger(__name__)


def _build_insider_summary(
    *,
    cik: str,
    form_type: str,
    no_insider: bool,
    insider_fetcher: Any,
    use_cache: bool,
    lookback_days: int,
) -> InsiderSummary:
    """Stage [2b]: additive, fail-soft. NEVER aborts the deep dive — only
    DataSourceError degrades to fetch_failed; logic bugs propagate (fail-loud).
    A None fetcher is treated like --no-insider (skipped)."""
    if no_insider or insider_fetcher is None:
        return InsiderSummary(coverage_state="skipped")
    if form_type == "20-F":
        return InsiderSummary(coverage_state="fpi_exempt")
    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    try:
        res = insider_fetcher.get_summary_input(cik, since, use_cache=use_cache)
    except DataSourceError as exc:
        logger.warning("deepdive: insider stage failed (%s) — fetch_failed", exc)
        return InsiderSummary(coverage_state="fetch_failed")
    return compute_insider_summary(
        res.transactions,
        coverage_state=res.coverage_state,
        n_filings_total=res.n_filings_total,
        n_parsed=res.n_parsed,
    )


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
    peers: str | None,
    peer_rationale: str | None,
    is_tty: bool,
    peer_resolver: Callable[..., Any],
    insider_fetcher: Any = None,
    insider_lookback_days: int = 365,
    no_insider: bool = False,
) -> Path:
    logger.info("deepdive: start ticker=%s", ticker)

    # [1] ADR-Lookup
    resolved = resolver.resolve(ticker)

    # [2] EDGAR-Pull (local-FS cache, ADR-4)
    raw = filing_fetcher.get(resolved.cik, resolved.form_type, use_cache=use_cache)

    # [2b] Insider Form-4 (additive mini-subsystem, fail-soft)
    insider_summary = _build_insider_summary(
        cik=resolved.cik,
        form_type=resolved.form_type,
        no_insider=no_insider,
        insider_fetcher=insider_fetcher,
        use_cache=use_cache,
        lookback_days=insider_lookback_days,
    )

    # [3] Filing-Parse
    parsed = parse_filing(raw.document_text, resolved.form_type)

    # [4] Quant-Join
    quant, coverage = build_quant(ticker, use_cache=use_cache)
    coverage.edgar = (
        f"{resolved.form_type} via ADR"
        if resolved.adr_ticker
        else f"{resolved.form_type} (US direct)"
    )
    coverage.insider = insider_coverage_label(insider_summary)

    # [4b] Peer pre-flight — attach to the QuantSnapshot so it flows into
    # both the synthesis prompt and the DeepDiveRecord (shared wiring).
    quant.peer_comparison = peer_resolver(
        ticker=ticker,
        peers_arg=peers,
        rationale_arg=peer_rationale,
        is_tty=is_tty,
    )

    # [5] Gemini-Synthesis
    synthesis = run_synthesis(
        ticker=ticker,
        form_type=resolved.form_type,
        sections=parsed.sections,
        quant=quant,
        synthesizer=synthesizer,
        max_input_tokens=token_cap,
        filing_date=raw.filing_date,
        insider_summary=insider_summary,
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
        filing_date=raw.filing_date,
        insider_summary=insider_summary,
    )

    # [6] Markdown-Output
    out = generate_dossier(record, output_dir)
    logger.info("deepdive: done ticker=%s -> %s", ticker, out.name)
    return out
