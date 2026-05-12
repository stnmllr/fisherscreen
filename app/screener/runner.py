from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.errors import DataSourceError
from app.models.screener_record import ScreenerRecord
from app.screener.filters import apply_basis_filters

if TYPE_CHECKING:
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
