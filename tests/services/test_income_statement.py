"""Tests for app.services.income_statement.extract_waterfall_inputs."""
import math

import pandas as pd
import pytest

from app.services.income_statement import extract_revenue_series, extract_waterfall_inputs


def _make_stmt(rows: dict) -> pd.DataFrame:
    """Build a minimal income-statement DataFrame with one column (most-recent period)."""
    return pd.DataFrame(rows, index=list(rows.keys())) if False else pd.DataFrame(
        {col: [v] for col, v in rows.items()},
        index=["placeholder"],
    )


def _stmt(**kwargs: float | None) -> pd.DataFrame:
    """Return a DataFrame where each kwarg key is a row label and its value is the
    first-column value.  Uses a single date column ('2024') so iloc[0] is unambiguous."""
    # pd.DataFrame({"2024": data}) has index=row_labels, columns=["2024"] — correct shape.
    return pd.DataFrame({"2024": dict(kwargs)})


# --- statement_available=False cases ---

def test_none_stmt_returns_not_available():
    available, rev, cor, gp, cor_present = extract_waterfall_inputs(None)
    assert available is False
    assert rev is None
    assert cor is None
    assert gp is None
    assert cor_present is False


def test_empty_dataframe_returns_not_available():
    available, rev, cor, gp, cor_present = extract_waterfall_inputs(pd.DataFrame())
    assert available is False


# --- full waterfall available ---

def test_full_row_stmt_extracts_all_values():
    stmt = _stmt(**{
        "Total Revenue": 1_000.0,
        "Cost Of Revenue": 300.0,
        "Gross Profit": 700.0,
    })
    available, rev, cor, gp, cor_present = extract_waterfall_inputs(stmt)
    assert available is True
    assert rev == pytest.approx(1_000.0)
    assert cor == pytest.approx(300.0)
    assert gp == pytest.approx(700.0)
    assert cor_present is True


# --- absent rows ---

def test_absent_cor_row_returns_none_and_cor_present_false():
    stmt = _stmt(**{"Total Revenue": 500.0, "Gross Profit": 500.0})
    available, rev, cor, gp, cor_present = extract_waterfall_inputs(stmt)
    assert available is True
    assert cor is None
    assert cor_present is False


def test_absent_revenue_row_returns_none():
    stmt = _stmt(**{"Cost Of Revenue": 200.0, "Gross Profit": 300.0})
    available, rev, cor, gp, cor_present = extract_waterfall_inputs(stmt)
    assert available is True
    assert rev is None


def test_absent_gross_profit_row_returns_none():
    stmt = _stmt(**{"Total Revenue": 1_000.0, "Cost Of Revenue": 300.0})
    available, rev, cor, gp, cor_present = extract_waterfall_inputs(stmt)
    assert available is True
    assert gp is None


# --- NaN safety ---

def test_nan_value_in_row_returns_none():
    stmt = _stmt(**{"Total Revenue": float("nan"), "Cost Of Revenue": 300.0, "Gross Profit": 700.0})
    available, rev, cor, gp, cor_present = extract_waterfall_inputs(stmt)
    assert available is True
    assert rev is None   # NaN coerced to None


def test_none_value_in_row_returns_none():
    stmt = _stmt(**{"Total Revenue": None, "Cost Of Revenue": 300.0, "Gross Profit": 700.0})
    available, rev, cor, gp, cor_present = extract_waterfall_inputs(stmt)
    assert available is True
    assert rev is None


# --- SEAM-4 contract guard: non-2-D inputs degrade gracefully ---

def test_series_input_returns_not_available():
    """A pandas Series (1-D) is a contract violation; degrade to not-available
    instead of raising AttributeError downstream in _first_col_value."""
    series = pd.Series({"Total Revenue": 1_000.0, "Cost Of Revenue": 300.0})
    available, rev, cor, gp, cor_present = extract_waterfall_inputs(series)
    assert available is False
    assert rev is None
    assert cor is None
    assert gp is None
    assert cor_present is False


def test_scalar_input_returns_not_available():
    """A scalar (no ndim) degrades to not-available."""
    available, rev, cor, gp, cor_present = extract_waterfall_inputs(42.0)
    assert available is False
    assert rev is None
    assert cor is None
    assert gp is None
    assert cor_present is False


# --- extract_revenue_series: multi-year Total Revenue, oldest->newest ---

def _multi_year_stmt(rev_by_year: dict) -> pd.DataFrame:
    """rev_by_year keyed newest-first, e.g. {'2024': 100, '2023': 90}. One row: Total Revenue."""
    return pd.DataFrame({col: {"Total Revenue": v} for col, v in rev_by_year.items()})


def test_extract_revenue_series_oldest_to_newest():
    stmt = _multi_year_stmt({"2024": 130.0, "2023": 120.0, "2022": 110.0, "2021": 100.0})
    assert extract_revenue_series(stmt) == [100.0, 110.0, 120.0, 130.0]


def test_extract_revenue_series_drops_nan_and_nonpositive():
    stmt = _multi_year_stmt({"2024": 130.0, "2023": float("nan"), "2022": -5.0, "2021": 100.0})
    assert extract_revenue_series(stmt) == [100.0, 130.0]


def test_extract_revenue_series_none_stmt_empty():
    assert extract_revenue_series(None) == []


def test_extract_revenue_series_missing_row_empty():
    stmt = pd.DataFrame({"2024": {"Gross Profit": 50.0}})
    assert extract_revenue_series(stmt) == []


def test_extract_revenue_series_series_input_empty():
    assert extract_revenue_series(pd.Series({"Total Revenue": 100.0})) == []
