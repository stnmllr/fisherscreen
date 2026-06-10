"""Validating loader for the CT-B exogenous backbone (Punkt 2): the
yfinance gics_industry -> GICS Industry Group map. This is the MARGIN-BLIND
intermediate node the dual-arm relative bucket rolls up to, replacing the
multimodal GICS-sector catch-all.

Absent file => empty dict {} (fail-safe: no group rollup, so a thin industry
gets no group node and the relative arm simply does not fire — dormant by
construction, mirroring sector_median_table's None sentinel).
Malformed/corrupt committed data => FilterConfigError (fail loud). Mirrors the
sector_median_table loader pattern."""
from __future__ import annotations

import json
from pathlib import Path

from app.errors import FilterConfigError

_DEFAULT_PATH = Path("data/gics_industry_group_map.json")


def load_industry_group_map(path: Path | None = None) -> dict[str, str]:
    """Load and validate the industry -> GICS-group map.

    Returns the `map` sub-dict on success (the top-level `_meta` is ignored).
    Returns an empty dict when the file is absent (fail-safe: no rollup =>
    relative arm dormant).
    Raises FilterConfigError on any corruption of the committed data: unreadable
    JSON, missing `map` key, `map` not a dict, or any key/value not a str.
    """
    p = path or _DEFAULT_PATH
    if not p.exists():
        return {}  # fail-safe sentinel: no rollup => relative arm dormant
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FilterConfigError(f"gics_industry_group_map unreadable: {exc}") from exc
    if not isinstance(data, dict) or "map" not in data:
        raise FilterConfigError("gics_industry_group_map: missing 'map'")
    group_map = data["map"]
    if not isinstance(group_map, dict):
        raise FilterConfigError("gics_industry_group_map: 'map' is not a dict")
    for industry, group in group_map.items():
        if not isinstance(industry, str) or not isinstance(group, str):
            raise FilterConfigError(
                f"gics_industry_group_map: non-string key/value at {industry!r}"
            )
    return dict(group_map)


# Loaded once at import (like the other static reference tables in the codebase).
INDUSTRY_GROUP_MAP: dict[str, str] = load_industry_group_map()
