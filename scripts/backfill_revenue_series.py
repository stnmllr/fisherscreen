"""One-time pre-warm of the dev_revenue_series Firestore cache for the whole universe.

Run manually BEFORE the first prod monthly run after this feature ships, so no monthly
run pays the cold income-statement fetch cost (protects the 1800s Cloud Run deadline).

Usage (cmd.exe): uv run python -m scripts.backfill_revenue_series
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def backfill(tickers: list[str], revenue_cache) -> int:
    """Fetch (and thereby cache) the revenue series for each ticker. Returns count."""
    for i, ticker in enumerate(tickers, 1):
        revenue_cache.get_revenue_series(ticker)
        if i % 100 == 0:
            logger.info("backfill: %d/%d", i, len(tickers))
    return len(tickers)


def main() -> None:
    from app.logging_config import configure_logging
    from app.screener.compose import build_revenue_series_cache

    configure_logging()
    universe_path = Path(__file__).parent.parent / "data" / "universe.json"
    tickers = json.loads(universe_path.read_text(encoding="utf-8"))
    cache = build_revenue_series_cache()
    n = backfill(tickers, cache)
    logger.info("backfill complete: %d tickers warmed into dev_revenue_series", n)


if __name__ == "__main__":
    main()
