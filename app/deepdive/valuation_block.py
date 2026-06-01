from __future__ import annotations

from typing import Any

from app.models.deep_dive_record import QuantSnapshot, ValuationHistory

_HEADING = (
    "## Bewertung & Kapitalstruktur "
    "(TTM-Stand + Mehrjahres-Median/Perzentil-Vergleich)"
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


def _ev_ebit_ttm(pit: Any) -> float | None:
    ev, ebit = pit.enterprise_value, pit.ebit
    if ev is None or ebit is None or ebit == 0:
        return None
    return ev / ebit


def _fcf_yield_ttm(pit: Any) -> float | None:
    fcf, mcap = pit.free_cashflow, pit.market_cap
    if fcf is None or mcap is None or mcap == 0:
        return None
    return fcf / mcap


def _range_segment(label: str, ttm: float | None, stats: Any, pct: bool) -> str:
    """Ein Multiple-Segment der Range-Zeile nach status (Spec §10). Die Spanne
    steht im Zeilen-Prefix, daher hier KEIN per-Segment-Wo-Suffix."""
    def f(v: float | None) -> str:
        if v is None:
            return "n/a"
        return f"{v:.1%}" if pct else f"{v:.1f}"
    if stats.status == "skipped_fx":
        return f"{label} n/a (FX: Listing≠Reporting)"
    if stats.status == "na_data":
        return f"{label} n/a (Historie unvollständig)"
    return (f"{label} TTM {f(ttm)} vs Median {f(stats.median)} "
            f"(25-Perz. {f(stats.p25)})")


def _range_prefix(vh: ValuationHistory) -> str | None:
    """Repräsentative Spanne für den Zeilen-Prefix: P/E bevorzugt, sonst das
    erste complete/partial-Multiple. None, wenn keines Werte trägt."""
    for stats in (vh.pe, vh.ev_ebit, vh.fcf_yield):
        if stats.status in ("complete", "partial") and stats.span_years:
            return f"(~{round(stats.span_years)}J, {stats.n_obs} Wo)"
    return None


def _render_valuation_range(quant: QuantSnapshot) -> str:
    vh = quant.valuation_history
    if vh is None:
        return "Bewertungs-Range: n/a (Historie nicht verfügbar)"
    statuses = {vh.pe.status, vh.ev_ebit.status, vh.fcf_yield.status}
    if statuses == {"skipped_fx"}:
        return "Bewertungs-Range: n/a (FX: Listing≠Reporting)"
    if statuses == {"na_data"}:
        return "Bewertungs-Range: n/a (Mehrjahres-Historie unvollständig)"
    pit = quant.point_in_time
    segs = [
        _range_segment("P/E", pit.trailing_pe, vh.pe, pct=False),
        _range_segment("EV/EBIT", _ev_ebit_ttm(pit), vh.ev_ebit, pct=False),
        _range_segment("FCF-Yield", _fcf_yield_ttm(pit), vh.fcf_yield,
                       pct=True),
    ]
    prefix = _range_prefix(vh)
    head = f"Bewertungs-Range {prefix}: " if prefix else "Bewertungs-Range: "
    return head + " · ".join(segs)


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

    valuation_range = _render_valuation_range(quant)
    consensus = _render_consensus(pit)
    forward = _render_forward(quant.forward_estimates)
    block = (f"{_HEADING}\n\n{bewertung}\n{valuation_range}\n{kapital}\n"
             f"{consensus}\n{forward}")
    peers = _render_peer_table(quant)
    if peers:
        block = f"{block}\n{peers}"
    return block


def _fcf_yield(fcf: float | None, mcap: float | None) -> str:
    if fcf is None or mcap is None or mcap == 0:
        return "n/a"
    return _fmt_pct(fcf / mcap)


def _render_peer_table(quant: QuantSnapshot) -> str:
    """Stage-2c user-selected peer comparison table. Appended after the
    forward line; absent entirely when quant.peer_comparison is None.

    Deliberate deviation: the column is `Rev-Growth (yoy)` from `.info`
    revenueGrowth for ALL rows incl. the main ticker — peers only have
    `.info` (yoy); honest-label precedent from 2a/2b; avoids extra
    per-peer historical pulls.
    """
    pc = quant.peer_comparison
    if pc is None:
        return ""
    pit = quant.point_in_time
    header = (
        "Peer-Vergleich (Nutzer-Auswahl):\n"
        "| Ticker | P/E tr. | P/E fwd | Op-Margin | Gross-M. | "
        "Rev-Growth (yoy) | FCF-Yield |\n"
        "|--------|--------:|--------:|----------:|---------:|"
        "-----------------:|----------:|"
    )
    rows = [
        "| {t} | {pe} | {pef} | {om} | {gm} | {rg} | {fy} |".format(
            t=pit.ticker,
            pe=_fmt_ratio(pit.trailing_pe),
            pef=_fmt_ratio(pit.forward_pe),
            om=_fmt_pct(pit.operating_margin),
            gm=_fmt_pct(pit.gross_margin),
            rg=_fmt_pct(pit.revenue_growth_yoy),
            fy=_fcf_yield(pit.free_cashflow, pit.market_cap),
        )
    ]
    for p in pc.peers:
        rows.append(
            "| {t} | {pe} | {pef} | {om} | {gm} | {rg} | {fy} |".format(
                t=p.ticker,
                pe=_fmt_ratio(p.trailing_pe),
                pef=_fmt_ratio(p.forward_pe),
                om=_fmt_pct(p.operating_margin),
                gm=_fmt_pct(p.gross_margin),
                rg=_fmt_pct(p.revenue_growth_yoy),
                fy=_fcf_yield(p.free_cashflow, p.market_cap),
            )
        )
    table = header + "\n" + "\n".join(rows)
    if pc.rationale is not None:
        table += f'\nPeer-Begründung (Nutzer): "{pc.rationale}"'
    return table


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
