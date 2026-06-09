"""Validating loader for the pinned, vintage-stamped sector-median reference table
(Punkt 2 Mechanism 2). Absent file => None (fail-safe: relative arm stays dormant).
Malformed/version-mismatched file => FilterConfigError (fail loud). Mirrors the
ADR-table loader pattern (app/deepdive/adr_table.py)."""
from __future__ import annotations

import json
from pathlib import Path

from app.errors import FilterConfigError
from app.screener.sector_buckets import SectorMedianTable

SECTOR_TABLE_SCHEMA_VERSION = 1
_DEFAULT_PATH = Path("data/sector_median_table.json")


def load_sector_median_table(path: Path | None = None) -> SectorMedianTable | None:
    """Load and validate the pinned sector-median reference table.

    Returns the populated SectorMedianTable on success.
    Returns None when the file is absent (fail-safe: relative arm stays dormant).
    Raises FilterConfigError on any schema, version, or consistency violation.
    """
    p = path or _DEFAULT_PATH
    if not p.exists():
        return None  # fail-safe sentinel: no table => relative arm dormant
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FilterConfigError(f"sector_median_table unreadable: {exc}") from exc
    if not isinstance(data, dict) or "entries" not in data:
        raise FilterConfigError("sector_median_table: missing 'entries'")
    if data.get("schema_version") != SECTOR_TABLE_SCHEMA_VERSION:
        raise FilterConfigError(
            f"sector_median_table schema {data.get('schema_version')!r} != {SECTOR_TABLE_SCHEMA_VERSION}"
        )
    entries = data["entries"]
    counts = data.get("counts", {})
    n_min = data.get("n_min")
    if not isinstance(entries, dict) or not isinstance(counts, dict) or not isinstance(n_min, int):
        raise FilterConfigError("sector_median_table: bad entries/counts/n_min types")
    for node, med in entries.items():
        if not isinstance(med, (int, float)) or isinstance(med, bool):
            raise FilterConfigError(f"sector_median_table: non-numeric median for {node!r}")
        if node not in counts:
            raise FilterConfigError(f"sector_median_table: entry {node!r} missing from counts")
    return SectorMedianTable(
        entries={k: float(v) for k, v in entries.items()},
        n_min=n_min,
        counts={k: int(v) for k, v in counts.items()},
    )
