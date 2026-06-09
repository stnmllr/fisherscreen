"""Tests for app.services.income_statement.extract_waterfall_inputs."""
import math

import pandas as pd
import pytest

from app.services.income_statement import extract_waterfall_inputs


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
