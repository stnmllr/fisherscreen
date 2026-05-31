from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Bump bei jedem Schema-Change (Add/Remove/Rename eines im Read-Pfad
# genutzten series-Feldes). Lese-Pfad behandelt jeden Mismatch (!=) als
# Cache-Miss → lazy refetch + Re-Write mit aktueller Version.
CACHE_SCHEMA_VERSION = 3


def _load_payload(path: Path) -> dict:
    """Missing OR corrupt/schema-wrong cache file -> empty (cache miss, WARNING),
    never a raw json.JSONDecodeError escaping the FisherScreenError hierarchy
    (mirrors app/deepdive/filing_cache.py._load_meta / adr_table.py idiom)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "historical cache: corrupt %s (%s) — treating as cache miss",
            path,
            exc,
        )
        return {}
    if not (isinstance(data, dict) and "series" in data):
        return {}
    cached_version = data.get("schema_version", 1)
    if cached_version != CACHE_SCHEMA_VERSION:
        logger.info(
            "historical cache: schema v%s (need v%s) for %s — refetching",
            cached_version,
            CACHE_SCHEMA_VERSION,
            path.name,
        )
        return {}
    return data


def _write_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


class CachedHistoricalData:
    """ADR-5a local-FS cache: cache/yfinance_historical/<TICKER>.json with an
    embedded _cached_at timestamp (Tool-A pattern), default 90-day TTL."""

    def __init__(self, service: Any, cache_dir: Path, ttl_days: int = 90) -> None:
        self._svc = service
        self._dir = Path(cache_dir)
        self._ttl_days = ttl_days

    def get_annual_series(self, ticker: str, use_cache: bool = True) -> dict[str, Any]:
        path = self._dir / f"{ticker}.json"
        if use_cache:
            payload = _load_payload(path)
            if payload and self._fresh(payload.get("_cached_at", "")):
                logger.info("historical cache hit: %s", ticker)
                cached_series = payload["series"]
                vh = cached_series.get("valuation_history")
                if isinstance(vh, dict):
                    from app.models.deep_dive_record import ValuationHistory

                    cached_series["valuation_history"] = ValuationHistory(**vh)
                return cached_series

        series = self._svc.get_annual_series(ticker)
        if use_cache:
            self._dir.mkdir(parents=True, exist_ok=True)
            to_store = dict(series)
            vh = to_store.get("valuation_history")
            if vh is not None and not isinstance(vh, dict):
                to_store["valuation_history"] = vh.model_dump()
            _write_atomic(
                path,
                {
                    "_cached_at": datetime.now(timezone.utc).isoformat(),
                    "schema_version": CACHE_SCHEMA_VERSION,
                    "financial_currency": series.get("financial_currency"),
                    "series": to_store,
                },
            )
        return series

    def _fresh(self, cached_at: str) -> bool:
        if not cached_at:
            return False
        ts = datetime.fromisoformat(cached_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).days < self._ttl_days
