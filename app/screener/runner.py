from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.errors import DataSourceError
from app.models.screener_record import ScreenerRecord
from app.screener.filters import apply_basis_filters, apply_edgar_filters

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient
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
