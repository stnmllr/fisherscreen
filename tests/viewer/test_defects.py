"""Tests for the dated data-defect table.

Invariant under test: a defect marks a value, it never hides one. The table
is therefore consulted by key + ticker + quant_date only — it must not look
at the value itself, because the viewer does not compute.
"""
import dataclasses
from datetime import date

import pytest

from app.viewer.defects import DataDefect, defects_for


def test_data_defect_is_frozen():
    defect = DataDefect(
        metric_key="x", tickers=None, quant_date_until=None, note="n"
    )

    assert dataclasses.is_dataclass(defect)
    with pytest.raises(dataclasses.FrozenInstanceError):
        defect.metric_key = "y"


def test_unknown_ticker_without_quant_date_is_clean():
    assert defects_for("X", None) == {}


def test_dividend_yield_defect_applies_inside_the_buggy_window():
    """GOOGL's last pre-fix run rendered `Div-Yield 23.0%` for a sub-1 % payer."""
    marked = defects_for("GOOGL", date(2026, 6, 1))

    assert "dividend_yield" in marked
    assert "total_shareholder_yield" in marked


def test_dividend_yield_defect_stops_after_the_fix():
    marked = defects_for("MSFT", date(2026, 6, 18))

    assert "dividend_yield" not in marked
    assert "total_shareholder_yield" not in marked


def test_dividend_yield_note_talks_about_the_run_not_the_number():
    """KO's 2.6 % is correct and still marked — the note must not call the
    value wrong, or the marker lies about every correct value in the window."""
    note = defects_for("KO", date(2026, 5, 26))["dividend_yield"].note

    assert "Zeitraum" in note
    assert "falsch" not in note.lower()


def test_enterprise_value_defect_is_scoped_to_argx():
    """Yahoo builds ARGX's EV from floatShares (1.56 bn) instead of
    sharesOutstanding (62.6 mn) — factor ~27. GOOGL's EV is plausible, so a
    global marker would cry wolf on four out of five dossiers."""
    marked = defects_for("ARGX", date(2026, 8, 20))

    assert "ev_ebit" in marked
    assert "ev_sales" in marked
    assert "ev_ebit" not in defects_for("GOOGL", date(2026, 8, 20))


def test_open_ended_defects_apply_to_the_newest_run():
    """D/E and the valuation range have no fix date yet; `quant_date_until`
    is None, so recency must not clear them."""
    marked = defects_for("MSFT", date(2026, 8, 20))

    assert "debt_to_equity" in marked
    assert "valuation_range" in marked
    assert marked["debt_to_equity"].quant_date_until is None
