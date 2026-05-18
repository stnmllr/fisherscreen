from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.edgar_client import RawFiling

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient

logger = logging.getLogger(__name__)


def _load_meta(meta_path: Path) -> dict:
    """Per-cik meta map. Missing OR corrupt file -> empty cache (WARNING),
    never a raw json.JSONDecodeError escaping the FisherScreenError hierarchy
    (mirrors app/deepdive/adr_table.py's fail-soft-on-corrupt idiom)."""
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "filing cache: corrupt %s (%s) — treating as cache miss",
            meta_path,
            exc,
        )
        return {}


def _write_meta_atomic(meta_path: Path, meta: dict) -> None:
    tmp = meta_path.with_suffix(meta_path.suffix + ".tmp")
    tmp.write_text(json.dumps(meta), encoding="utf-8")
    os.replace(tmp, meta_path)


class CachedFilingFetcher:
    """Local-FS filing cache (Master ADR-4). cache/filings/<cik>/<accession>.txt
    with a per-cik _meta.json holding {form_type: {_cached_at, accession}}."""

    def __init__(
        self, edgar: "EdgarClient", cache_dir: Path, ttl_days: int = 30
    ) -> None:
        self._edgar = edgar
        self._cache_dir = Path(cache_dir)
        self._ttl_days = ttl_days

    def get(self, cik: str, form_type: str, use_cache: bool = True) -> RawFiling:
        cik_dir = self._cache_dir / cik
        meta_path = cik_dir / "_meta.json"
        if use_cache:
            meta = _load_meta(meta_path)
            entry = meta.get(form_type)
            if entry and self._fresh(entry["_cached_at"]):
                doc = cik_dir / f"{entry['accession']}.txt"
                if doc.exists():
                    logger.info(
                        "filing cache hit: cik=%s form=%s", cik, form_type
                    )
                    return RawFiling(
                        entry["accession"], doc.read_text(encoding="utf-8")
                    )

        filing = self._edgar.get_latest_annual_filing(cik, form_type)
        if use_cache:
            cik_dir.mkdir(parents=True, exist_ok=True)
            (cik_dir / f"{filing.accession_number}.txt").write_text(
                filing.document_text, encoding="utf-8"
            )
            meta = _load_meta(meta_path)
            meta[form_type] = {
                "_cached_at": datetime.now(timezone.utc).isoformat(),
                "accession": filing.accession_number,
            }
            _write_meta_atomic(meta_path, meta)
        return filing

    def _fresh(self, cached_at: str) -> bool:
        ts = datetime.fromisoformat(cached_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).days < self._ttl_days
