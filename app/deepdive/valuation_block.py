from __future__ import annotations

from app.models.deep_dive_record import QuantSnapshot

_HEADING = (
    "## Bewertung & Kapitalstruktur "
    "(TTM-Stand, ohne historischen 5J-Vergleich)"
)


def _fmt_ratio(v: float | None) -> str:
    """Raw ratio (e.g. P/E): plain `n/a` when missing, else 1 decimal."""
    return f"{v:.1f}" if v is not None else "n/a"


def _fmt_money(v: float | None) -> str:
    return f"{v:,.0f}" if v is not None else "n/a"


def _fmt_pct(v: float | None) -> str:
    return f"{v:.1%}" if v is not None else "n/a"


def _latest(seq: list[float | None] | None) -> float | None:
    for v in seq or []:
        if v is not None:
            return v
    return None


def render_valuation_block(quant: QuantSnapshot) -> str:
    """Pure renderer for the Stage-2a valuation / capital-structure block.

    Derived ratios are computed here, never persisted. Every derived field
    that cannot be computed renders `n/a (<reason>)` naming the missing input.
    """
    pit = quant.point_in_time
    ccy = pit.currency or ""
    hist = quant.historical_series
    trends = quant.trend_metrics

    ev = pit.enterprise_value
    ebit = pit.ebit
    fcf = pit.free_cashflow
    mcap = pit.market_cap
    ie = pit.interest_expense
    latest_rev = _latest(hist.revenue) if hist else None

    # EV/EBIT
    if ev is None:
        ev_ebit = "n/a (EV fehlt)"
    elif ebit is None:
        ev_ebit = "n/a (EBIT fehlt)"
    elif ebit == 0:
        ev_ebit = "n/a (EBIT=0)"
    else:
        ev_ebit = f"{ev / ebit:.1f}"

    # EV/Sales
    if ev is None:
        ev_sales = "n/a (EV fehlt)"
    elif latest_rev is None or latest_rev == 0:
        ev_sales = "n/a (Revenue fehlt)"
    else:
        ev_sales = f"{ev / latest_rev:.1f}"

    # FCF-Yield (fraction -> percent)
    if fcf is None:
        fcf_yield = "n/a (FCF fehlt)"
    elif mcap is None:
        fcf_yield = "n/a (Market Cap fehlt)"
    else:
        fcf_yield = _fmt_pct(fcf / mcap)

    # Interest Coverage = EBIT / abs(Interest Expense) — FY/filing vintage
    if ebit is None:
        interest_cov = "n/a (EBIT fehlt)"
    elif ie is None:
        interest_cov = "n/a (Interest Expense fehlt)"
    elif ie == 0:
        interest_cov = "n/a (Interest Expense=0)"
    else:
        interest_cov = f"{ebit / abs(ie):.1f}× (FY)"

    # Total Shareholder Yield = current div yield + annualized buyback
    div = pit.dividend_yield
    n_years = len(hist.years) if (hist and hist.years) else 5
    n_years = max(n_years, 1)
    cum_bb = trends.buyback_intensity_5y if trends else None
    ann_bb = None if cum_bb is None else cum_bb / n_years

    div_txt = _fmt_pct(div)
    bb_txt = _fmt_pct(ann_bb)
    if div is not None and ann_bb is not None:
        tsy_txt = _fmt_pct(div + ann_bb)
    else:
        tsy_txt = "n/a"
    tsy = (
        f"Total Shareholder Yield {tsy_txt} (Div {div_txt} aktuell + "
        f"Ø {n_years}J Buyback {bb_txt})"
    )

    bewertung = (
        f"Bewertung: P/E trail. {_fmt_ratio(pit.trailing_pe)} · "
        f"P/E fwd {_fmt_ratio(pit.forward_pe)} · "
        f"EV/EBIT {ev_ebit} · EV/Sales {ev_sales} · "
        f"FCF-Yield {fcf_yield} · Div-Yield {div_txt} · "
        f"Payout {_fmt_pct(pit.payout_ratio)}"
    )
    kapital = (
        f"Kapitalstruktur: Total Debt {_fmt_money(pit.total_debt)} {ccy} · "
        f"Cash {_fmt_money(pit.total_cash)} {ccy} · "
        f"D/E {_fmt_ratio(pit.debt_to_equity)} · "
        f"Current Ratio {_fmt_ratio(pit.current_ratio)} · "
        f"Interest Coverage {interest_cov} · {tsy}"
    )
    return f"{_HEADING}\n\n{bewertung}\n{kapital}"
