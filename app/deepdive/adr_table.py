from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.errors import DeepDiveError

DEFAULT_ADR_TABLE_PATH = Path(__file__).resolve().parents[2] / "data" / "adr_table.json"
_VALID_FORM_TYPES = {"10-K", "20-F"}


def load_adr_table(path: Path | None = None) -> dict[str, dict[str, str]]:
    """Load and validate the static ADR mapping table.

    Returns the ``entries`` mapping (ticker -> {adr_ticker, cik, form_type}).
    Raises DeepDiveError on a missing file, invalid JSON, or any schema violation
    — fail loud, never return a partial/empty table silently.
    """
    table_path = path or DEFAULT_ADR_TABLE_PATH
    try:
        raw: Any = json.loads(table_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DeepDiveError(f"ADR table not found: {table_path}") from exc
    except json.JSONDecodeError as exc:
        raise DeepDiveError(f"ADR table is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict) or "entries" not in raw:
        raise DeepDiveError("ADR table missing top-level 'entries' object")
    entries = raw["entries"]
    if not isinstance(entries, dict):
        raise DeepDiveError("ADR table 'entries' must be an object")

    for ticker, entry in entries.items():
        _validate_entry(ticker, entry)
    return entries


def _validate_entry(ticker: str, entry: Any) -> None:
    if not isinstance(entry, dict):
        raise DeepDiveError(f"ADR entry for {ticker} must be an object")
    adr = entry.get("adr_ticker")
    cik = entry.get("cik")
    form = entry.get("form_type")
    if not isinstance(adr, str) or not adr:
        raise DeepDiveError(f"ADR entry for {ticker}: 'adr_ticker' must be a non-empty string")
    if not isinstance(cik, str) or not (cik.isdigit() and len(cik) == 10):
        raise DeepDiveError(f"ADR entry for {ticker}: 'cik' must be a 10-digit zero-padded string")
    if form not in _VALID_FORM_TYPES:
        raise DeepDiveError(
            f"ADR entry for {ticker}: 'form_type' must be one of {sorted(_VALID_FORM_TYPES)}"
        )
