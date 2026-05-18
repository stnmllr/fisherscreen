from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CachedHistoricalData:
    """ADR-5a local-FS cache: cache/yfinance_historical/<TICKER>.json with an
    embedded _cached_at timestamp (Tool-A pattern), default 90-day TTL."""

    def __init__(self, service: Any, cache_dir: Path, ttl_days: int = 90) -> None:
        self._svc = service
        self._dir = Path(cache_dir)
        self._ttl_days = ttl_days

    def get_annual_series(self, ticker: str, use_cache: bool = True) -> dict[str, Any]:
        path = self._dir / f"{ticker}.json"
        if use_cache and path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if self._fresh(payload.get("_cached_at", "")):
                logger.info("historical cache hit: %s", ticker)
                return payload["series"]

        series = self._svc.get_annual_series(ticker)
        if use_cache:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({
                    "_cached_at": datetime.now(timezone.utc).isoformat(),
                    "financial_currency": series.get("financial_currency"),
                    "series": series,
                }),
                encoding="utf-8",
            )
        return series

    def _fresh(self, cached_at: str) -> bool:
        if not cached_at:
            return False
        ts = datetime.fromisoformat(cached_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).days < self._ttl_days
