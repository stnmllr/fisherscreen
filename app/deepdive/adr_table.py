from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.deepdive.adr_resolver import NO_SEC_SOURCE_REASONS
from app.errors import DeepDiveError

DEFAULT_ADR_TABLE_PATH = Path(__file__).resolve().parents[2] / "data" / "adr_table.json"
_VALID_FORM_TYPES = {"10-K", "20-F"}

# The table is a TAGGED UNION of two entry shapes, and `no_sec_source_reason` is
# the tag: present -> negative entry ("this issuer is provably not an SEC
# registrant"), absent -> positive entry (adr_ticker + cik + form_type).
#
# Each arm below validates its own required fields AND rejects the other arm's
# fields, so a mixed entry fails whichever arm it is routed to — the tag can
# never be used to smuggle half a mapping past the check. Two named validators
# rather than one branching function: each arm reads as a complete statement of
# one legal shape, which is what a hand-maintained file needs, since the only
# reader who ever debugs it is a human holding a malformed row.
_POSITIVE_FIELDS = frozenset({"adr_ticker", "cik", "form_type"})
_PROVENANCE_FIELDS = frozenset({"note", "verified_on"})
_REASON_TAG = "no_sec_source_reason"


def load_adr_table(path: Path | None = None) -> dict[str, dict[str, str]]:
    """Load and validate the static ADR mapping table.

    Returns the ``entries`` mapping, whose values are either a positive mapping
    (ticker -> {adr_ticker, cik, form_type}) or a negative verdict
    (ticker -> {no_sec_source_reason, note, verified_on}).
    Raises DeepDiveError on a missing file, invalid JSON, or any schema violation
    — fail loud, never return a partial/empty table silently.

    Validation is deliberately load-time and total: this file is hand-maintained,
    and a typo in a row must surface when the resolver is built, not halfway
    through a paid deep dive that has already spent EDGAR and Gemini calls.
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
    """Route an entry to the validator for its shape (see the tag comment above)."""
    if not isinstance(entry, dict):
        raise DeepDiveError(f"ADR entry for {ticker} must be an object")
    if _REASON_TAG in entry:
        _validate_negative_entry(ticker, entry)
        return
    _validate_positive_entry(ticker, entry)


def _validate_positive_entry(ticker: str, entry: dict[str, Any]) -> None:
    """A usable filing source: which ADR line, which CIK, which annual form."""
    _reject_unknown_fields(ticker, entry, _POSITIVE_FIELDS | _PROVENANCE_FIELDS)
    adr = entry.get("adr_ticker")
    cik = entry.get("cik")
    form = entry.get("form_type")
    if not isinstance(adr, str) or not adr:
        raise DeepDiveError(
            f"ADR entry for {ticker}: 'adr_ticker' must be a non-empty string"
        )
    if not isinstance(cik, str) or not (cik.isdigit() and len(cik) == 10):
        raise DeepDiveError(
            f"ADR entry for {ticker}: 'cik' must be a 10-digit zero-padded string"
        )
    if form not in _VALID_FORM_TYPES:
        raise DeepDiveError(
            f"ADR entry for {ticker}: 'form_type' must be one of {sorted(_VALID_FORM_TYPES)}"
        )
    # Optional here, mandatory on the negative arm — a positive mapping predates
    # the field, and demanding it would break the five entries this change must
    # leave untouched. If it is there, it must still be a real date.
    if "verified_on" in entry:
        _require_iso_date(ticker, entry["verified_on"])


def _validate_negative_entry(ticker: str, entry: dict[str, Any]) -> None:
    """A hand-verified "this issuer files nothing with the SEC" verdict.

    Carries no filing handles by construction: if a cik existed, the entry would
    be a positive mapping. Rejecting the positive fields here is what makes the
    biconditional in ResolvedTicker unreachable from the table side."""
    # Checked BEFORE the unknown-field sweep: a positive field on a negative
    # entry is a mixed entry, and the reader deserves that diagnosis rather than
    # "unknown field 'cik'", which would send them looking for a typo.
    clash = sorted(_POSITIVE_FIELDS & entry.keys())
    if clash:
        raise DeepDiveError(
            f"ADR entry for {ticker}: an entry is either positive "
            f"(adr_ticker/cik/form_type) or negative ('{_REASON_TAG}'), never "
            f"both — remove {clash}"
        )
    _reject_unknown_fields(ticker, entry, {_REASON_TAG} | _PROVENANCE_FIELDS)
    reason = entry[_REASON_TAG]
    if not isinstance(reason, str) or reason not in NO_SEC_SOURCE_REASONS:
        raise DeepDiveError(
            f"ADR entry for {ticker}: '{_REASON_TAG}' must be one of "
            f"{sorted(NO_SEC_SOURCE_REASONS)}"
        )
    note = entry.get("note")
    if not isinstance(note, str) or not note:
        raise DeepDiveError(
            f"ADR entry for {ticker}: 'note' must be a non-empty string — a "
            f"hand-maintained verdict has to state its evidence"
        )
    # MANDATORY: "not an SEC registrant" is a statement about a point in time.
    # Adyen can register tomorrow, and a pinned negative would never notice; the
    # date is what lets a later reader see how stale the hand decision is.
    if "verified_on" not in entry:
        raise DeepDiveError(
            f"ADR entry for {ticker}: 'verified_on' is required for a negative "
            f"entry — a no-SEC-source verdict is only true as of a date"
        )
    _require_iso_date(ticker, entry["verified_on"])


def _require_iso_date(ticker: str, value: Any) -> None:
    if not isinstance(value, str):
        raise DeepDiveError(
            f"ADR entry for {ticker}: 'verified_on' must be an ISO date string"
        )
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise DeepDiveError(
            f"ADR entry for {ticker}: 'verified_on' is not an ISO date: {value}"
        ) from exc


def _reject_unknown_fields(
    ticker: str, entry: dict[str, Any], allowed: set[str] | frozenset[str]
) -> None:
    """A misspelt key is the failure mode of a hand-maintained file: it does not
    contradict anything, it just silently does nothing (a mistyped
    'no_sec_source_reasons' would make a negative row read as a broken positive
    one). Unknown fields are therefore an error, not tolerated extra data."""
    unknown = sorted(set(entry) - set(allowed))
    if unknown:
        raise DeepDiveError(
            f"ADR entry for {ticker}: unknown field(s) {unknown} — allowed are "
            f"{sorted(allowed)}"
        )
