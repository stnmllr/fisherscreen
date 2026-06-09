from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.errors import DataSourceError, DegradedDataError
from app.models.definedness import DefinednessOutcome
from app.models.screener_record import ScreenerRecord
from app.screener import filters as _filters
from app.screener.compose import build_sector_median_table
from app.screener.filter_report import FilterReport, build_filter_report
from app.screener.filters import apply_basis_filters, apply_edgar_filters, passes_market_cap_filter, passes_volume_filter
from app.screener.metric_definedness import assess_definedness
from app.screener.sector_buckets import SectorMedianTable
from app.services.income_statement import extract_waterfall_inputs

if TYPE_CHECKING:
    from app.models.run_record import RunRecord
    from app.screener.run_tracker import RunTracker
    from app.services.edgar_client import EdgarClient
    from app.services.gemini_client import GeminiClient
    from app.services.yfinance_client import YFinanceClient

logger = logging.getLogger(__name__)


class ResolveReason(str, Enum):
    OK = "OK"
    NO_RAW_MC = "NO_RAW_MC"      # raw market_cap missing or 0 (collapsed to None at construction)
    NO_CURRENCY = "NO_CURRENCY"  # market_cap present but currency missing -> uninterpretable
    NO_FX = "NO_FX"             # mc + currency present, FX rate unavailable (infra, systemic)


def _load_provenance() -> dict | None:
    path = Path(__file__).parent.parent.parent / "data" / "universe_provenance.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("provenance: could not read %s", path)
        return None


@dataclass
class BasisFilterResult:
    """Result of the basis filter stage.

    `passed` survived the basis filters. `resolved` are the **gateable** records
    (constructed AND with usable core data); diverted data-quality records are NOT
    here. `unresolved`/`degraded` failed yfinance resolution. `no_symbol_data` and
    `fx_unavailable` are records diverted in resolution (0b) before any gate.
    """

    passed: list[ScreenerRecord] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    resolved: list[ScreenerRecord] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    no_symbol_data: list[ScreenerRecord] = field(default_factory=list)
    fx_unavailable: list[ScreenerRecord] = field(default_factory=list)


def _resolve_market_cap_eur(
    record: ScreenerRecord,
    yfinance: YFinanceClient,
    fx_cache: dict[str, float],
) -> tuple[float | None, ResolveReason]:
    if record.market_cap is None:
        return None, ResolveReason.NO_RAW_MC
    if record.currency is None:
        return None, ResolveReason.NO_CURRENCY
    currency = record.currency
    if currency not in fx_cache:
        try:
            fx_cache[currency] = yfinance.get_fx_rate(currency)
        except DataSourceError:
            logger.warning("ticker=%s FX rate unavailable for currency=%s", record.ticker, currency)
            fx_cache[currency] = None  # type: ignore[assignment]
    rate = fx_cache[currency]
    if rate is None:
        return None, ResolveReason.NO_FX
    return record.market_cap * rate, ResolveReason.OK


def _is_suspect(record: ScreenerRecord) -> bool:
    """True when the record belongs to the definedness suspect basket.

    Basket scoping (Financials/RE sector OR gm<=0) is FETCH-scoping, not a
    classification key (verdict stays the waterfall). It rests on Gate-A's vintage
    finding that the spurious-positive edge is subset of Financials/RE —
    RE-VERIFY this at table re-vintage; see calibration.md.
    """
    sector = record.gics_sector or ""
    if "Financ" in sector or "Real Estate" in sector:
        return True
    gm = record.gross_margin
    return gm is None or gm <= 0


def _assess_definedness_basket(
    records: list[ScreenerRecord],
    yfinance: "YFinanceClient",
) -> None:
    """Mutate definedness in-place for suspect basket ∩ volume+cap survivors.

    Non-suspect records and records that fail volume/cap are left with
    definedness=None (the gates will handle them in the normal order).
    """
    n_assessed = 0
    n_metrik_na = 0
    n_unassessable = 0
    n_defined = 0

    for record in records:
        # Only assess volume+cap survivors in the suspect basket.
        try:
            vol_passes = passes_volume_filter(record)
            cap_passes = passes_market_cap_filter(record)
        except Exception:
            # FilterConfigError (uncalibrated sentinel) or invariant violation —
            # leave definedness=None so the gate fires normally.
            continue

        if not (vol_passes and cap_passes):
            continue
        if not _is_suspect(record):
            continue

        n_assessed += 1

        # REIT short-circuit: no fetch needed.
        if "REIT" in (record.gics_industry or ""):
            record.definedness = DefinednessOutcome.METRIK_NA
            n_metrik_na += 1
            continue

        # Fetch the income statement and classify the waterfall.
        statement_available = False
        income_stmt = None
        try:
            income_stmt = yfinance.get_annual_statements(record.ticker)[0]
            statement_available = True
        except DataSourceError as exc:
            logger.warning(
                "ticker=%s income_stmt fetch failed (UNASSESSABLE): %s",
                record.ticker, exc,
            )

        _, total_revenue, cost_of_revenue, gross_profit, cor_present = (
            extract_waterfall_inputs(income_stmt if statement_available else None)
        )

        outcome = assess_definedness(
            record.gics_industry,
            statement_available,
            total_revenue,
            cost_of_revenue,
            gross_profit,
            cor_present,
        )
        record.definedness = outcome

        if outcome is DefinednessOutcome.METRIK_NA:
            n_metrik_na += 1
        elif outcome is DefinednessOutcome.UNASSESSABLE:
            n_unassessable += 1
        else:
            n_defined += 1

    logger.info(
        "definedness_prepass: assessed=%d METRIK_NA=%d UNASSESSABLE=%d DEFINED=%d",
        n_assessed, n_metrik_na, n_unassessable, n_defined,
    )


def run_basis_filter(
    tickers: list[str],
    yfinance: "YFinanceClient",
    sector_table: SectorMedianTable | None = None,
) -> BasisFilterResult:
    us_input = sum(1 for t in tickers if "." not in t)
    eu_input = len(tickers) - us_input
    logger.info("runner: universe input US=%d EU=%d total=%d", us_input, eu_input, len(tickers))

    records: list[ScreenerRecord] = []
    unresolved: list[str] = []
    degraded: list[str] = []
    no_symbol_data: list[ScreenerRecord] = []
    fx_unavailable: list[ScreenerRecord] = []
    fx_cache: dict[str, float] = {}
    for ticker in tickers:
        try:
            info = yfinance.get_ticker_info(ticker)
            record = ScreenerRecord.from_yfinance_info(ticker, info)
            record.market_cap_eur, reason = _resolve_market_cap_eur(record, yfinance, fx_cache)
            # 0b: divert unusable-data records out of the gate path (symbol-data first, then FX).
            if reason == ResolveReason.NO_RAW_MC:
                record.resolution_detail = "NO_RAW_MC"
                no_symbol_data.append(record)
            elif reason == ResolveReason.NO_CURRENCY:
                record.resolution_detail = "NO_CURRENCY"
                no_symbol_data.append(record)
            elif record.avg_daily_volume is None:
                record.resolution_detail = "NO_VOLUME"
                no_symbol_data.append(record)
            elif record.price is None:
                record.resolution_detail = "NO_PRICE"
                no_symbol_data.append(record)
            elif reason == ResolveReason.NO_FX:
                record.resolution_detail = "NO_FX"
                fx_unavailable.append(record)
            else:
                record.fx_rate = fx_cache.get(record.currency)
                records.append(record)
        except DegradedDataError as exc:  # MUST precede DataSourceError (subclass)
            logger.warning("ticker=%s degraded dict: %s", ticker, exc)
            unresolved.append(ticker)
            degraded.append(ticker)
        except (DataSourceError, ValidationError) as exc:
            logger.warning("ticker=%s data fetch failed: %s", ticker, exc)
            unresolved.append(ticker)

    us_fetched = sum(1 for r in records if "." not in r.ticker)
    eu_fetched = len(records) - us_fetched
    logger.info("runner: fetched US=%d EU=%d total=%d/%d", us_fetched, eu_fetched, len(records), len(tickers))

    if unresolved:
        unresolved.sort()
        # WARNING level is deliberate: an unresolved universe symbol is silent
        # attrition and must be visible regardless of any INFO logging config.
        logger.warning(
            "resolution: %d/%d universe symbols unresolved by yfinance: %s",
            len(unresolved),
            len(tickers),
            unresolved,
        )

    if no_symbol_data or fx_unavailable:
        logger.warning(
            "resolution data-quality: %d no_symbol_data, %d fx_unavailable (diverted to REVIEW)",
            len(no_symbol_data), len(fx_unavailable),
        )

    # CT-A pre-pass: assess income-statement definedness for the suspect basket
    # BEFORE apply_basis_filters. Only fetch for records that pass BOTH volume and
    # market_cap (saves fetches; avoids over-diverting names that fail those gates
    # anyway; keeps stage arithmetic monotone).
    _assess_definedness_basket(records, yfinance)

    table = sector_table if sector_table is not None else build_sector_median_table()
    return BasisFilterResult(
        passed=apply_basis_filters(
            records,
            sector_table=table,
            relative_k=_filters.GROSS_MARGIN_RELATIVE_K,
        ),
        unresolved=unresolved,
        resolved=records,
        degraded=sorted(degraded),
        no_symbol_data=no_symbol_data,
        fx_unavailable=fx_unavailable,
    )


def _evaluate_edgar(records: list[ScreenerRecord], edgar: EdgarClient) -> None:
    """Mutate each record in place with EDGAR signals (or a skip reason).

    Keeps using has_going_concern (the bool); the going-concern hit detail is
    fetched only in build_filter_report for the small set of dropped names.
    """
    for record in records:
        if record.cik is None:
            record.cik = edgar.get_cik(record.ticker)
        if record.cik is None:
            logger.warning("ticker=%s has no CIK — skipping EDGAR check", record.ticker)
            record.edgar_skipped = True
            record.edgar_skipped_reason = "no_cik"
            continue
        try:
            record.has_restatement = edgar.has_restatement(record.cik)
            record.has_going_concern = edgar.has_going_concern(record.cik)
            record.has_active_enforcement = edgar.has_active_enforcement(record.cik)
        except DataSourceError as exc:
            logger.warning("ticker=%s EDGAR fetch failed: %s — skipping", record.ticker, exc)
            record.edgar_skipped = True
            record.edgar_skipped_reason = "data_source_error"
    logger.info("runner: EDGAR lookup complete for %d records", len(records))


def run_edgar_filter(
    records: list[ScreenerRecord],
    edgar: EdgarClient,
) -> list[ScreenerRecord]:
    _evaluate_edgar(records, edgar)
    passed = apply_edgar_filters(records)
    report = build_filter_report(records, edgar)
    report.log(logger)
    return passed


def run_filter_preview(
    tickers: list[str],
    yfinance: YFinanceClient,
    edgar: EdgarClient,
    *,
    output_dir: Path | None = None,
    run_month: str | None = None,
) -> FilterReport:
    """Free ($0) filters-only preview: basis + EDGAR filters, no Gemini, no
    run-tracker. Emits funnel artifacts (stages through EDGAR) when output_dir
    is given — for cold-run visibility."""
    from app.config import settings

    basis = run_basis_filter(tickers, yfinance)
    records = basis.passed
    _evaluate_edgar(records, edgar)
    apply_edgar_filters(records)
    report = build_filter_report(records, edgar)
    report.yfinance_unresolved = basis.unresolved
    report.log(logger)
    logger.info(
        "filter_preview: %d gc-drops, %d skipped",
        len(report.going_concern_drops),
        report.total_skipped(),
    )
    if output_dir is not None:
        from app.output.funnel_artifacts import write_funnel_artifacts
        from app.screener.funnel import build_funnel
        month = run_month or datetime.now(timezone.utc).strftime("%Y-%m")
        summary, dropouts = build_funnel(
            universe=tickers, basis=basis, scored=None,
            score_threshold=settings.crosshits_score_threshold,
            crosshits_min_dimensions=settings.crosshits_min_dimensions,
            provenance=_load_provenance(),
        )
        write_funnel_artifacts(summary, dropouts, output_dir, month)
    return report


def run_screener(
    tickers: list[str],
    yfinance: YFinanceClient,
    edgar: EdgarClient,
    gemini: GeminiClient,
    run_tracker: RunTracker,
    output_dir: Path,
    *,
    score_threshold: float | None = None,
    crosshits_min_dimensions: int | None = None,
    crosshits_cap: int | None = None,
) -> tuple[list[ScreenerRecord], RunRecord, list[Path]]:
    from app.config import settings
    from app.output.changes_generator import generate as generate_changes
    from app.output.crosshits_generator import generate as generate_crosshits
    from app.output.dimensions_generator import generate as generate_dimensions
    from app.screener.scorer import run_gemini_scoring

    threshold = score_threshold if score_threshold is not None else settings.crosshits_score_threshold
    min_dims = crosshits_min_dimensions if crosshits_min_dimensions is not None else settings.crosshits_min_dimensions
    cap = crosshits_cap if crosshits_cap is not None else settings.crosshits_cap

    from app.output.funnel_artifacts import write_funnel_artifacts
    from app.output.report_header import render_header
    from app.screener.funnel import build_funnel

    basis = run_basis_filter(tickers, yfinance)
    edgar_passed = run_edgar_filter(basis.passed, edgar)
    scored = run_gemini_scoring(edgar_passed, gemini, run_tracker)
    run_record = run_tracker.finish()
    run_month = run_record.run_id[:7]

    summary, dropouts = build_funnel(
        universe=tickers, basis=basis, scored=scored,
        score_threshold=threshold, crosshits_min_dimensions=min_dims,
        provenance=_load_provenance(),
    )
    funnel_paths = write_funnel_artifacts(summary, dropouts, output_dir, run_month)
    header = render_header(summary, run_month)

    paths = [
        generate_dimensions(scored, run_record, output_dir, score_threshold=threshold, cap=cap),
        generate_crosshits(scored, run_record, output_dir, score_threshold=threshold,
                           min_dimensions=min_dims, cap=cap, header=header),
        generate_changes(scored, run_record, output_dir, score_threshold=threshold, cap=cap),
        *funnel_paths,
    ]

    logger.info("run_screener: complete — %d records, %d output files", len(scored), len(paths))
    return scored, run_record, paths
