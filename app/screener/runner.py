from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.errors import DataSourceError
from app.models.screener_record import ScreenerRecord
from app.screener.filters import apply_basis_filters, apply_edgar_filters

if TYPE_CHECKING:
    from app.models.run_record import RunRecord
    from app.screener.run_tracker import RunTracker
    from app.services.edgar_client import EdgarClient
    from app.services.gemini_client import GeminiClient
    from app.services.yfinance_client import YFinanceClient

logger = logging.getLogger(__name__)


def run_basis_filter(
    tickers: list[str],
    yfinance: YFinanceClient,
) -> list[ScreenerRecord]:
    records: list[ScreenerRecord] = []
    for ticker in tickers:
        try:
            info = yfinance.get_ticker_info(ticker)
            records.append(ScreenerRecord.from_yfinance_info(ticker, info))
        except (DataSourceError, ValidationError) as exc:
            logger.warning("ticker=%s data fetch failed: %s", ticker, exc)
    logger.info("runner: fetched %d/%d records", len(records), len(tickers))
    return apply_basis_filters(records)


def run_edgar_filter(
    records: list[ScreenerRecord],
    edgar: EdgarClient,
) -> list[ScreenerRecord]:
    for record in records:
        if record.cik is None:
            logger.warning("ticker=%s has no CIK — skipping EDGAR check", record.ticker)
            record.edgar_skipped = True
            continue
        try:
            record.has_restatement = edgar.has_restatement(record.cik)
            record.has_going_concern = edgar.has_going_concern(record.cik)
            record.has_active_enforcement = edgar.has_active_enforcement(record.cik)
        except DataSourceError as exc:
            logger.warning("ticker=%s EDGAR fetch failed: %s — skipping", record.ticker, exc)
            record.edgar_skipped = True
    logger.info("runner: EDGAR lookup complete for %d records", len(records))
    return apply_edgar_filters(records)


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

    records = run_basis_filter(tickers, yfinance)
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
