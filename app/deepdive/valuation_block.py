from __future__ import annotations

from typing import Any

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

    consensus = _render_consensus(pit)
    forward = _render_forward(quant.forward_estimates)
    return f"{_HEADING}\n\n{bewertung}\n{kapital}\n{consensus}\n{forward}"


def _render_consensus(pit: Any) -> str:
    """Stage-2b analyst-consensus line. STRICT n/a: when target_mean_price
    is missing the ENTIRE line is `Analyst Consensus: n/a` (no partial fill).
    implied_upside is computed here, never persisted."""
    target = pit.target_mean_price
    if target is None:
        return "Analyst Consensus: n/a"
    price = pit.price
    if price is None or price == 0:
        upside = "n/a (Kurs fehlt)"
    else:
        upside = _fmt_pct((target - price) / price)
    median = (
        f"{pit.target_median_price}"
        if pit.target_median_price is not None else "n/a"
    )
    opinions = (
        f"{pit.number_of_analyst_opinions}"
        if pit.number_of_analyst_opinions is not None else "n/a"
    )
    return (
        f"Analyst Consensus: {pit.recommendation_key or 'n/a'} · "
        f"Target: {target:.2f} (Median {median}) · "
        f"{opinions} Analysten · Upside {upside}"
    )


def _render_forward(fe: Any) -> str:
    """Stage-2b forward-consensus line. Generic period labels (`lfd. GJ` /
    `Folge-GJ`) — yfinance gives no reliable calendar-year mapping, so no
    fabricated `FY26e` (honest-label precedent from 2a's `Ø 4J Buyback`)."""
    if fe is None or all(
        v is None for v in (
            fe.revenue_growth_cy, fe.revenue_growth_ny,
            fe.eps_growth_cy, fe.eps_growth_ny)
    ):
        return "Forward-Konsens: n/a"
    return (
        f"Forward-Konsens: Revenue {_fmt_pct(fe.revenue_growth_cy)} "
        f"(lfd. GJ), {_fmt_pct(fe.revenue_growth_ny)} (Folge-GJ) · "
        f"EPS {_fmt_pct(fe.eps_growth_cy)} (lfd. GJ)"
    )
