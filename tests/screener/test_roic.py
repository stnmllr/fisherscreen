import pytest

from app.models.screener_record import ScreenerRecord
from app.screener.roic import (
    INVESTED_CAPITAL_NONPOSITIVE,
    NO_DEBT_CASH,
    NO_EBIT,
    NO_EQUITY,
    annotate_roic,
    compute_roic,
    equity,
)


def _rec(**kw) -> ScreenerRecord:
    return ScreenerRecord(ticker="X", **kw)


# --- equity -------------------------------------------------------------------


def test_equity_primary_from_debt_and_debt_to_equity():
    # D/E is in percent: 50 -> equity = debt / 0.5
    assert equity(_rec(total_debt=100.0, debt_to_equity=50.0)) == pytest.approx(200.0)


def test_negative_debt_to_equity_gives_negative_equity():
    assert equity(_rec(total_debt=20.0, debt_to_equity=-200.0)) == pytest.approx(-10.0)


def test_primary_wins_over_book_value():
    r = _rec(
        total_debt=100.0,
        debt_to_equity=50.0,
        book_value_per_share=1.0,
        shares_outstanding=1.0,
    )
    assert equity(r) == pytest.approx(200.0)


@pytest.mark.parametrize("fin", [None, "USD"])
def test_fallback_to_book_value_when_currencies_agree(fin):
    r = _rec(
        currency="USD",
        financial_currency=fin,
        total_debt=0.0,
        book_value_per_share=10.0,
        shares_outstanding=5.0,
    )
    assert equity(r) == pytest.approx(50.0)


def test_fallback_when_debt_to_equity_is_zero():
    r = _rec(
        currency="USD",
        total_debt=100.0,
        debt_to_equity=0.0,
        book_value_per_share=10.0,
        shares_outstanding=5.0,
    )
    assert equity(r) == pytest.approx(50.0)


def test_currency_mismatch_without_debt_is_unknown():
    # EQNR.OL: bookValue in NOK, balance sheet in USD -> never mix them
    r = _rec(
        currency="NOK",
        financial_currency="USD",
        total_debt=None,
        book_value_per_share=10.0,
        shares_outstanding=5.0,
    )
    assert equity(r) is None


def test_fallback_needs_both_book_value_and_shares():
    assert equity(_rec(currency="USD", book_value_per_share=10.0)) is None


# --- compute_roic -------------------------------------------------------------


def test_roic_is_ebit_over_invested_capital():
    # EBIT 0.2 * 1000 = 200; IC = 100 + 200 - 50 = 250
    r = _rec(
        operating_margin=0.2,
        total_revenue=1000.0,
        total_debt=100.0,
        debt_to_equity=50.0,
        total_cash=50.0,
    )
    assert compute_roic(r) == (pytest.approx(0.8), None)


def test_negative_equity_with_positive_ebit_still_has_a_roic():
    # debt 20, D/E -200 -> equity -10, cash 5 -> IC 5; EBIT 0.1 * 100 = 10
    r = _rec(
        operating_margin=0.1,
        total_revenue=100.0,
        total_debt=20.0,
        debt_to_equity=-200.0,
        total_cash=5.0,
    )
    assert compute_roic(r) == (pytest.approx(2.0), None)


def test_missing_cash_counts_as_zero_when_debt_present():
    r = _rec(
        operating_margin=0.1,
        total_revenue=100.0,
        total_debt=50.0,
        debt_to_equity=100.0,
    )
    assert compute_roic(r) == (pytest.approx(0.1), None)


def test_missing_debt_counts_as_zero_when_cash_present():
    r = _rec(
        currency="USD",
        operating_margin=0.1,
        total_revenue=100.0,
        total_cash=10.0,
        book_value_per_share=11.0,
        shares_outstanding=10.0,
    )
    assert compute_roic(r) == (pytest.approx(0.1), None)


@pytest.mark.parametrize(
    "fields",
    [
        {"total_revenue": 100.0},
        {"operating_margin": 0.1},
        {},
    ],
)
def test_no_ebit(fields):
    r = _rec(total_debt=50.0, debt_to_equity=100.0, **fields)
    assert compute_roic(r) == (None, NO_EBIT)


def test_no_ebit_is_checked_before_equity():
    assert compute_roic(_rec()) == (None, NO_EBIT)


def test_no_equity():
    r = _rec(
        currency="NOK",
        financial_currency="USD",
        operating_margin=0.1,
        total_revenue=100.0,
        total_cash=10.0,
        book_value_per_share=1.0,
        shares_outstanding=1.0,
    )
    assert compute_roic(r) == (None, NO_EQUITY)


def test_no_debt_cash():
    r = _rec(
        currency="USD",
        operating_margin=0.1,
        total_revenue=100.0,
        book_value_per_share=1.0,
        shares_outstanding=10.0,
    )
    assert compute_roic(r) == (None, NO_DEBT_CASH)


@pytest.mark.parametrize("cash", [300.0, 400.0])
def test_invested_capital_nonpositive(cash):
    # IC = 100 + 200 - cash <= 0 (FTNT/BKNG pattern: cash exceeds debt + equity)
    r = _rec(
        operating_margin=0.1,
        total_revenue=100.0,
        total_debt=100.0,
        debt_to_equity=50.0,
        total_cash=cash,
    )
    assert compute_roic(r) == (None, INVESTED_CAPITAL_NONPOSITIVE)


def test_negative_ebit_gives_negative_roic():
    r = _rec(
        operating_margin=-0.1,
        total_revenue=100.0,
        total_debt=50.0,
        debt_to_equity=100.0,
    )
    assert compute_roic(r) == (pytest.approx(-0.1), None)


def test_annotate_roic_sets_value_and_reason():
    ok = _rec(
        operating_margin=0.2,
        total_revenue=1000.0,
        total_debt=100.0,
        debt_to_equity=50.0,
        total_cash=50.0,
    )
    missing = _rec(roic_missing_reason="stale", return_on_invested_capital=9.9)
    annotate_roic([ok, missing])
    assert ok.return_on_invested_capital == pytest.approx(0.8)
    assert ok.roic_missing_reason is None
    assert missing.return_on_invested_capital is None
    assert missing.roic_missing_reason == NO_EBIT
