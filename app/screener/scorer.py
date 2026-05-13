from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.errors import FisherScreenError, GeminiError
from app.models.screener_record import ScreenerRecord

if TYPE_CHECKING:
    from app.screener.run_tracker import RunTracker
    from app.services.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

MAX_TICKERS_PER_RUN = 3_000
MAX_INPUT_TOKENS_PER_TICKER = 3_000
MAX_OUTPUT_TOKENS_PER_TICKER = 1_000


def run_gemini_scoring(
    records: list[ScreenerRecord],
    gemini: GeminiClient,
    run_tracker: RunTracker,
) -> list[ScreenerRecord]:
    """Score each record with Gemini Flash Lite against Fisher's five dimensions.

    Hard cap: raises FisherScreenError if len(records) > MAX_TICKERS_PER_RUN.
    Per-ticker: GeminiError is caught, logged as WARNING, and the ticker is skipped
    (gemini_dimensions stays None). All records are returned, including skipped ones.

    Contract for GeminiClient implementors: score_ticker() MUST wrap all exceptions
    as GeminiError. Raw SDK or network exceptions will abort the entire run.
    """
    if len(records) > MAX_TICKERS_PER_RUN:
        raise FisherScreenError(
            f"Too many tickers for Gemini scoring: {len(records)} > {MAX_TICKERS_PER_RUN}. "
            "Run basis + EDGAR filters first."
        )
    for record in records:
        try:
            result = gemini.score_ticker(
                record.ticker,
                record,
                max_input_tokens=MAX_INPUT_TOKENS_PER_TICKER,
                max_output_tokens=MAX_OUTPUT_TOKENS_PER_TICKER,
            )
            record.gemini_dimensions = result.dimensions
            record.gemini_summary = result.summary
            run_tracker.record_ticker(result.tokens_in, result.tokens_out)
        except GeminiError as exc:
            logger.warning("ticker=%s gemini scoring skipped: %s", record.ticker, exc)
            run_tracker.record_skip()
    logger.info("scorer: gemini scoring complete for %d records", len(records))
    return records
