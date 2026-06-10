"""Shared income-statement extractor for the screener runtime and calibration scripts.

Mirrors the _first_col_value logic from scripts/diagnose_gross_margin_definedness.py
(the script's copy is intentionally left until it is refactored in a later unit).
"""
from __future__ import annotations

from typing import Any


def _first_col_value(df: Any, label: str) -> float | None:
    """Return the newest-column (first column) value for *label* in *df*.

    Returns None when df is None/empty, the row label is absent, the value
    is NaN, or the value cannot be cast to float.
    """
    if df is None or getattr(df, "empty", True):
        return None
    if label not in df.index:
        return None
    row = df.loc[label]
    if not list(row.index):
        return None
    val = row.iloc[0]
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN guard
        return None
    return f


def extract_waterfall_inputs(
    income_stmt: Any,
) -> tuple[bool, float | None, float | None, float | None, bool]:
    """Extract waterfall inputs from a yfinance income_stmt DataFrame.

    Returns:
        (statement_available, total_revenue, cost_of_revenue, gross_profit,
         cost_of_revenue_present)

    - statement_available: False when income_stmt is None or empty (caller diverts
      to UNASSESSABLE — do NOT infer METRIK_NA from a missing statement).
    - total_revenue / cost_of_revenue / gross_profit: newest-column value for the
      respective row label; None when the row is absent or the value is NaN.
    - cost_of_revenue_present: True when "Cost Of Revenue" is in income_stmt.index
      (only meaningful when statement_available is True).
    """
    # Contract: we extract only from a 2-D income-statement frame. A Series/scalar
    # (an easy pandas slip at a call site) degrades to "not available" rather than
    # raising AttributeError downstream in _first_col_value.
    if getattr(income_stmt, "ndim", None) != 2:
        return False, None, None, None, False
    if income_stmt is None or getattr(income_stmt, "empty", True):
        return False, None, None, None, False

    cor_present = "Cost Of Revenue" in income_stmt.index
    total_revenue = _first_col_value(income_stmt, "Total Revenue")
    cost_of_revenue = _first_col_value(income_stmt, "Cost Of Revenue")
    gross_profit = _first_col_value(income_stmt, "Gross Profit")

    return True, total_revenue, cost_of_revenue, gross_profit, cor_present
