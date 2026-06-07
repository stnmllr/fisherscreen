"""Diagnose: enumerate non-EQUITY symbol contaminants across the universe and
support ISIN-anchored verification of correction candidates. $0 probe (yfinance
only). Diagnostic script — the pure helpers below are unit-tested; the live
main() is a probe like scripts/trigger_cold_dry_run.py (added in a later task).
"""
from __future__ import annotations

from typing import Any


def classify_info(info: dict[str, Any]) -> str:
    """EQUITY | CONTAMINANT | INCONCLUSIVE from a yfinance .info dict.

    - quoteType == 'EQUITY'         -> EQUITY (clean)
    - quoteType present & != EQUITY  -> CONTAMINANT (e.g. MUTUALFUND)
    - quoteType missing/None/empty   -> INCONCLUSIVE (transient hiccup; retry/manual)
    """
    if not info:
        return "INCONCLUSIVE"
    quote_type = info.get("quoteType")
    if not quote_type:
        return "INCONCLUSIVE"
    return "EQUITY" if quote_type == "EQUITY" else "CONTAMINANT"


def isin_matches(a: str | None, b: str | None) -> bool:
    """True iff both ISINs are present and equal (normalized). Missing or
    whitespace-only -> False (caller falls back to name-match + manual confirmation)."""
    if not a or not b:
        return False
    a_norm, b_norm = a.strip().upper(), b.strip().upper()
    if not a_norm or not b_norm:
        return False
    return a_norm == b_norm
