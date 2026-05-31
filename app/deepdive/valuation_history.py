from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from app.models.deep_dive_record import MultipleStats, ValuationHistory

# POLICY — fixiert, NICHT an Ticker-Pulls kalibriert (Spec §5).
VALUATION_COMPLETE_MIN_DENSITY = 40     # obs pro Jahr
VALUATION_PARTIAL_MIN_OBS = 52          # >= 1 Jahr wöchentlich

# DATEN-GEDECKELT — der realen GJ-Fundamental-Tiefe folgend (Task 0 / Spec §5).
# Probe-Pull: freie yfinance income_stmt = nur 4 GJ -> mit Lag ~3,1J nutzbare
# Tiefe -> 2.8 (knapp unter ~3J: complete = volle verfügbare Tiefe; IPO-junger
# 2J-Ticker bleibt korrekt partial).
VALUATION_COMPLETE_MIN_SPAN_YEARS = 2.8

# Look-ahead-Milderung: Fundamental erst ~1 Quartal nach Periodenende verfügbar.
REPORTING_LAG_DAYS = 90


def _median_p25(values: list[float]) -> tuple[float | None, float | None]:
    """Median + unteres 25-Perzentil (inclusive). Leere Liste -> (None, None);
    Einzelwert -> (v, v) (quantiles braucht >=2 Punkte)."""
    if not values:
        return None, None
    if len(values) == 1:
        return float(values[0]), float(values[0])
    med = statistics.median(values)
    p25 = statistics.quantiles(values, n=4, method="inclusive")[0]
    return float(med), float(p25)


def _cum_split_factor(
    fy_end: date, splits: list[tuple[date, float]]
) -> float:
    """Kumulativer Split-Faktor für ein GJ: Produkt aller Split-Ratios mit
    Ex-Datum NACH dem GJ-Periodenende. EPS_current = EPS_reported / factor
    bringt as-reported EPS auf current (back-adjusted) Basis (Spec §3a)."""
    factor = 1.0
    for ex_date, ratio in splits:
        if ex_date > fy_end:
            factor *= ratio
    return factor


def _as_of_index(week: date, fy_ends_newest_first: list[date]) -> int | None:
    """Index des jüngsten GJ, dessen (Periodenende + REPORTING_LAG_DAYS) <= week.
    None, wenn kein GJ verfügbar ist (Wochenpunkt vor erstem Lag-Ende)."""
    for i, fy_end in enumerate(fy_ends_newest_first):
        if fy_end + timedelta(days=REPORTING_LAG_DAYS) <= week:
            return i
    return None


@dataclass(frozen=True)
class AnnualFundamental:
    """Ein GJ-Datensatz (newest-first geliefert). diluted_eps ist as-reported
    (wird via cum_split auf current basis gebracht); net_income/ebit/debt/cash
    sind Währungs-Aggregate (split-invariant)."""
    fy_end: date
    net_income: float | None
    diluted_eps: float | None
    ebit: float | None
    free_cashflow: float | None
    total_debt: float | None
    cash: float | None


def _finite(*vals: float | None) -> bool:
    return all(v is not None and math.isfinite(v) for v in vals)


def _span_years(weeks: list[date]) -> float:
    if len(weeks) < 2:
        return 0.0
    return (max(weeks) - min(weeks)).days / 365.25


def _classify(values: list[float], obs_weeks: list[date]) -> MultipleStats:
    n = len(values)
    span = _span_years(obs_weeks)
    if n < VALUATION_PARTIAL_MIN_OBS:
        return MultipleStats(n_obs=n, span_years=span or None, status="na_data")
    med, p25 = _median_p25(values)
    density = (n / span) if span > 0 else 0.0
    if span >= VALUATION_COMPLETE_MIN_SPAN_YEARS and density >= VALUATION_COMPLETE_MIN_DENSITY:
        status = "complete"
    else:
        status = "partial"
    return MultipleStats(median=med, p25=p25, n_obs=n,
                         span_years=round(span, 2), status=status)


def compute_valuation_history(
    weekly_close: list[tuple[date, float]],
    annual: list[AnnualFundamental],          # newest-first
    splits: list[tuple[date, float]],
    listing_ccy: str | None,
    financial_ccy: str | None,
) -> ValuationHistory:
    """Mehrjahres-Multiple-Bänder (Spec §2/§3). FX-/None-Gates zuerst; dann pro
    Wochenpunkt as-of-Fundamental + cum_split-Normalisierung + implizite-EV-
    Brücke; Ausschluss EPS<=0 / EBIT<=0; FCF-Yield-Negative bleiben."""
    # FX-/None-Gates (Spec §3c/§3d)
    if listing_ccy is None or financial_ccy is None:
        return ValuationHistory(
            pe=MultipleStats(status="na_data"),
            ev_ebit=MultipleStats(status="na_data"),
            fcf_yield=MultipleStats(status="na_data"))
    if listing_ccy != financial_ccy:
        return ValuationHistory(
            pe=MultipleStats(status="skipped_fx"),
            ev_ebit=MultipleStats(status="skipped_fx"),
            fcf_yield=MultipleStats(status="skipped_fx"))

    fy_ends = [a.fy_end for a in annual]

    pe_vals: list[float] = []; pe_weeks: list[date] = []
    ev_vals: list[float] = []; ev_weeks: list[date] = []
    fcf_vals: list[float] = []; fcf_weeks: list[date] = []

    for week, price in weekly_close:
        if not _finite(price) or price <= 0:
            continue
        idx = _as_of_index(week, fy_ends)
        if idx is None:
            continue
        a = annual[idx]
        factor = _cum_split_factor(a.fy_end, splits)

        # P/E — EPS auf current basis; EPS<=0 ausgeschlossen
        if _finite(a.diluted_eps):
            eps_cur = a.diluted_eps / factor
            if eps_cur > 0:
                pe_vals.append(price / eps_cur)
                pe_weeks.append(week)

        # implizite Shares -> Markt-Kap -> EV (Spec §3b)
        if (_finite(a.diluted_eps, a.net_income) and a.diluted_eps != 0):
            eps_cur = a.diluted_eps / factor
            if eps_cur != 0:
                shares = a.net_income / eps_cur
                # Vorzeichen-Mismatch -> shares negativ/unsinnig: überspringen
                if shares > 0 and _finite(a.ebit, a.total_debt, a.cash) \
                        and a.ebit > 0:
                    mcap = price * shares
                    ev = mcap + a.total_debt - a.cash
                    ev_vals.append(ev / a.ebit)
                    ev_weeks.append(week)

        # FCF-Yield — Negative behalten (Spec §2)
        if (_finite(a.diluted_eps, a.net_income, a.free_cashflow)
                and a.diluted_eps != 0):
            eps_cur = a.diluted_eps / factor
            if eps_cur != 0:
                shares = a.net_income / eps_cur
                if shares > 0:
                    mcap = price * shares
                    if mcap > 0:
                        fcf_vals.append(a.free_cashflow / mcap)
                        fcf_weeks.append(week)

    return ValuationHistory(
        pe=_classify(pe_vals, pe_weeks),
        ev_ebit=_classify(ev_vals, ev_weeks),
        fcf_yield=_classify(fcf_vals, fcf_weeks))
