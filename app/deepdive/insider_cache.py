from __future__ import annotations

import json
import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.deepdive.insider_parser import parse_form4
from app.errors import DataSourceError
from app.models.deep_dive_record import InsiderCoverage, InsiderTransaction

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient

logger = logging.getLogger(__name__)

# bump on any Add/Remove/Rename of a read-path InsiderTransaction field.
INSIDER_CACHE_SCHEMA_VERSION = 1


@dataclass
class InsiderFetchResult:
    transactions: list[InsiderTransaction] = field(default_factory=list)
    coverage_state: InsiderCoverage = "empty"
    n_filings_total: int = 0
    n_parsed: int = 0


class CachedInsiderFetcher:
    """Accession-keyed, immutable, pre-netting Form-4 cache.
    cache/insider/<cik>/<accession>.json. Form-4 are immutable after filing ->
    no TTL freshness check, only a schema_version gate. The accession LIST is
    re-derived each run from submissions.json (picks up new filings)."""

    def __init__(self, edgar: "EdgarClient", cache_dir: Path) -> None:
        self._edgar = edgar
        self._dir = Path(cache_dir)

    def get_summary_input(
        self, cik: str, since: str, use_cache: bool = True
    ) -> InsiderFetchResult:
        # Index errors propagate -> the pipeline's fail-soft wrap turns them
        # into coverage_state="fetch_failed". Per-XML errors are caught below.
        refs = self._edgar.get_form4_index(cik, since)
        n_total = len(refs)
        if n_total == 0:
            return InsiderFetchResult([], "empty", 0, 0)
        txns: list[InsiderTransaction] = []
        n_parsed = 0
        for ref in refs:
            try:
                txns.extend(self._load_or_fetch(cik, ref, use_cache))
                n_parsed += 1
            except (DataSourceError, ET.ParseError, ValidationError) as exc:
                logger.warning(
                    "insider: skip accession %s (%s)", ref.accession_number, exc
                )
        if n_parsed == 0:
            return InsiderFetchResult([], "fetch_failed", n_total, 0)
        state: InsiderCoverage = "ok" if n_parsed == n_total else "partial"
        return InsiderFetchResult(txns, state, n_total, n_parsed)

    def _load_or_fetch(
        self, cik: str, ref, use_cache: bool
    ) -> list[InsiderTransaction]:
        path = self._dir / cik / f"{ref.accession_number}.json"
        if use_cache:
            cached = self._load(path)
            if cached is not None:
                return [InsiderTransaction(**t) for t in cached]
        xml = self._edgar.get_form4_document(
            cik, ref.accession_number, ref.primary_document
        )
        txns = parse_form4(xml)
        if use_cache:
            self._write(path, txns)
        return txns

    def _load(self, path: Path) -> list[dict] | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("insider cache: corrupt %s (%s) — cache miss", path, exc)
            return None
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != INSIDER_CACHE_SCHEMA_VERSION
        ):
            return None
        return data.get("transactions", [])

    def _write(self, path: Path, txns: list[InsiderTransaction]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": INSIDER_CACHE_SCHEMA_VERSION,
            "_cached_at": datetime.now(timezone.utc).isoformat(),
            "transactions": [t.model_dump() for t in txns],
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)
