from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from app.deepdive.adr_resolver import NO_SEC_SOURCE_REASONS, NoSecSourceReason
from app.deepdive.dossier_generator import generate_dossier
from app.errors import DataSourceError
from app.deepdive.filing_parser import parse_filing
from app.deepdive.insider_block import insider_coverage_label
from app.deepdive.insider_summary import compute_insider_summary
from app.deepdive.synthesis import run_synthesis
from app.models.deep_dive_record import (
    DeepDiveRecord,
    InsiderCoverage,
    InsiderSummary,
)

logger = logging.getLogger(__name__)

# Why this mapping exists: the four no-SEC-source reasons do not license the same
# insider sentence. The first three are checked statements about the ISSUER — it
# has no Form-4 duty — while `unverifiable_identity` is a statement about US: we
# never identified the company, so its reporting duty is unknown, not absent.
# Collapsing them into one state is exactly how the dossier came to contradict
# its own Executive Summary.
_INSIDER_STATE_BY_REASON: dict[NoSecSourceReason, InsiderCoverage] = {
    "no_us_line": "no_sec_source",
    "not_sec_registrant": "no_sec_source",
    "no_annual_form": "no_sec_source",
    "unverifiable_identity": "issuer_unidentified",
}

# Totality, checked at import: a fifth reason must break here loudly instead of
# inheriting a wording nobody chose for it.
assert (
    set(_INSIDER_STATE_BY_REASON) == NO_SEC_SOURCE_REASONS
), "insider coverage mapping is not total over NoSecSourceReason"


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


def _quant_only_dossier(
    ticker: str,
    *,
    resolved: Any,
    output_dir: Path,
    build_quant: Callable[..., tuple[Any, Any]],
    use_cache: bool,
    peers: str | None,
    peer_rationale: str | None,
    is_tty: bool,
    peer_resolver: Callable[..., Any],
) -> Path:
    """Dossier for a ticker without any SEC filing source: quant + valuation +
    peers, honestly labelled, no synthesis.

    Gemini is unreachable here BY CONSTRUCTION — this helper never receives the
    synthesizer, the filing fetcher or the insider fetcher. Rule "no Gemini in the
    quant-only path" is therefore a property of the call graph, not of a branch
    that someone can later simplify away."""
    logger.warning(
        "deepdive: no SEC filing source for %s (%s) — quant-only dossier",
        ticker,
        resolved.no_sec_source_reason,
    )

    # Not wrapped: a DataSourceError still aborts (exit 2). A quant-only dossier
    # without quant would be worthless — degrading twice is the phantom-data slide.
    quant, coverage = build_quant(ticker, use_cache=use_cache)

    # No CIK exists, so no fetcher call is even possible. Which of the two
    # honest states applies depends on WHY there is no source — see
    # _INSIDER_STATE_BY_REASON. Unknown reason: KeyError, never a default.
    insider_summary = InsiderSummary(
        coverage_state=_INSIDER_STATE_BY_REASON[resolved.no_sec_source_reason]
    )

    # The resolver's note is the single source of truth for the wording.
    coverage.edgar = resolved.no_sec_source_note
    coverage.insider = insider_coverage_label(insider_summary)

    quant.peer_comparison = peer_resolver(
        ticker=ticker,
        peers_arg=peers,
        rationale_arg=peer_rationale,
        is_tty=is_tty,
    )

    record = DeepDiveRecord(
        ticker=ticker,
        adr_ticker=resolved.adr_ticker,
        cik=None,
        form_type=None,
        no_sec_source_reason=resolved.no_sec_source_reason,
        no_sec_source_note=resolved.no_sec_source_note,
        filing_sections={},
        section_flags={},
        quant_snapshot=quant,
        synthesis=[],
        source_coverage=coverage,
        filing_date=None,
        insider_summary=insider_summary,
    )
    return generate_dossier(record, output_dir)


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
    if not resolved.has_filing_source:
        return _quant_only_dossier(
            ticker,
            resolved=resolved,
            output_dir=output_dir,
            build_quant=build_quant,
            use_cache=use_cache,
            peers=peers,
            peer_rationale=peer_rationale,
            is_tty=is_tty,
            peer_resolver=peer_resolver,
        )

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
