"""Return on invested capital for Tool-A profitability (pure, no I/O).

ROIC = EBIT / invested capital, EBIT = operating margin x total revenue, invested
capital = debt + equity - cash. It replaces ROE in the profitability axis: buybacks
shrink book equity to ~0 or below, so ROE measured cosmetics. Invested capital
still contains equity, but next to debt and cash, so a buyback-thinned equity no
longer dominates the ratio.

A missing ROIC is never 0: `compute_roic` returns the value OR the reason it is
missing, and the scorer decides what a missing value means (deterministic_scorer)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from app.models.screener_record import ScreenerRecord

# Missing reasons, checked in this order.
NO_EBIT = "no_ebit"
NO_EQUITY = "no_equity"
NO_DEBT_CASH = "no_debt_cash"
INVESTED_CAPITAL_NONPOSITIVE = "invested_capital_nonpositive"

_PERCENT = 100.0


def equity(record: "ScreenerRecord") -> float | None:
    """Book equity in the balance-sheet currency, for the whole company.

    Primary: total_debt / (debt_to_equity / 100). Both come from the balance sheet,
    so the result is in the financial currency and covers every share class. A
    negative D/E yields a negative equity, which is kept (buyback-heavy companies).

    Fallback: book_value_per_share x shares_outstanding, but ONLY when the quote
    and the financial currency agree. Two measured defects make it second choice
    (scripts/diagnose_roic.py, 2026-10): bookValue is in the QUOTE currency while
    debt and cash are in the financial currency (EQNR.OL: NOK vs USD, ~x10 off),
    and sharesOutstanding counts a single share class (GOOG: equity too small,
    ROIC 95 % instead of 29 %). With a currency mismatch equity is unknown."""
    debt, de = record.total_debt, record.debt_to_equity
    if debt is not None and debt > 0 and de is not None and de != 0:
        return debt / (de / _PERCENT)
    if (
        record.financial_currency is not None
        and record.financial_currency != record.currency
    ):
        return None
    book, shares = record.book_value_per_share, record.shares_outstanding
    if book is None or shares is None:
        return None
    return book * shares


def compute_roic(record: "ScreenerRecord") -> tuple[float | None, str | None]:
    """(ROIC, None) or (None, reason). A missing debt or cash side counts as 0
    only if the other is present (same rule as deterministic_scorer.net_debt)."""
    margin, revenue = record.operating_margin, record.total_revenue
    if margin is None or revenue is None:
        return None, NO_EBIT
    eq = equity(record)
    if eq is None:
        return None, NO_EQUITY
    debt, cash = record.total_debt, record.total_cash
    if debt is None and cash is None:
        return None, NO_DEBT_CASH
    invested_capital = (debt or 0.0) + eq - (cash or 0.0)
    if invested_capital <= 0:
        return None, INVESTED_CAPITAL_NONPOSITIVE
    return margin * revenue / invested_capital, None


def annotate_roic(records: Iterable["ScreenerRecord"]) -> None:
    """Set return_on_invested_capital / roic_missing_reason on each record in
    place. Must run before the percentiles, which rank the ROIC."""
    for record in records:
        roic, reason = compute_roic(record)
        record.return_on_invested_capital = roic
        record.roic_missing_reason = reason
