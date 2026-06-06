from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.errors import DataSourceError, DegradedDataError
from app.models.screener_record import ScreenerRecord
from app.screener.filter_report import FilterReport, build_filter_report
from app.screener.filters import apply_basis_filters, apply_edgar_filters

if TYPE_CHECKING:
    from app.models.run_record import RunRecord
    from app.screener.run_tracker import RunTracker
    from app.services.edgar_client import EdgarClient
    from app.services.gemini_client import GeminiClient
    from app.services.yfinance_client import YFinanceClient

logger = logging.getLogger(__name__)


@dataclass
class BasisFilterResult:
    """Result of the basis filter stage.

    `passed` survived the basis filters. `resolved` are ALL records that yfinance
    resolved (passed + gate-failed) — gate-failed ones carry filter_failed_reason.
    `unresolved` are symbols yfinance could not resolve at all (the attrition
    signal); `degraded` is the subset of `unresolved` that raised DegradedDataError.
    """

    passed: list[ScreenerRecord] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    resolved: list[ScreenerRecord] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)


def _resolve_market_cap_eur(
    record: ScreenerRecord,
    yfinance: YFinanceClient,
    fx_cache: dict[str, float],
) -> float | None:
    if record.market_cap is None or record.currency is None:
        return None
    currency = record.currency
    if currency not in fx_cache:
        try:
            fx_cache[currency] = yfinance.get_fx_rate(currency)
        except DataSourceError:
            logger.warning("ticker=%s FX rate unavailable for currency=%s", record.ticker, currency)
            fx_cache[currency] = None  # type: ignore[assignment]
    rate = fx_cache[currency]
    if rate is None:
        return None
    return record.market_cap * rate


def run_basis_filter(
    tickers: list[str],
    yfinance: YFinanceClient,
) -> BasisFilterResult:
    us_input = sum(1 for t in tickers if "." not in t)
    eu_input = len(tickers) - us_input
    logger.info("runner: universe input US=%d EU=%d total=%d", us_input, eu_input, len(tickers))

    records: list[ScreenerRecord] = []
    unresolved: list[str] = []
    degraded: list[str] = []
    fx_cache: dict[str, float] = {}
    for ticker in tickers:
        try:
            info = yfinance.get_ticker_info(ticker)
            record = ScreenerRecord.from_yfinance_info(ticker, info)
            record.market_cap_eur = _resolve_market_cap_eur(record, yfinance, fx_cache)
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

    return BasisFilterResult(
        passed=apply_basis_filters(records),
        unresolved=unresolved,
        resolved=records,
        degraded=sorted(degraded),
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
) -> FilterReport:
    """Free ($0) filters-only preview: basis + EDGAR filters, no Gemini, no
    run-tracker, no output. Returns a FilterReport for dry-run visibility."""
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

    records = run_basis_filter(tickers, yfinance).passed
    records = run_edgar_filter(records, edgar)
    records = run_gemini_scoring(records, gemini, run_tracker)
    run_record = run_tracker.finish()

    paths = [
        generate_dimensions(records, run_record, output_dir, score_threshold=threshold, cap=cap),
        generate_crosshits(records, run_record, output_dir, score_threshold=threshold, min_dimensions=min_dims, cap=cap),
        generate_changes(records, run_record, output_dir, score_threshold=threshold, cap=cap),
    ]

    logger.info("run_screener: complete — %d records, %d output files", len(records), len(paths))
    return records, run_record, paths
