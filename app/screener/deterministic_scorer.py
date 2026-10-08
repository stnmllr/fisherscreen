"""Deterministic Tool-A scorer (Approach B / A1 — no LLM).

Maps the percentile annotations (sector_percentiles.annotate_percentiles) + the absolute
growth-consistency cap + absolute red-flag overlays to the ScreenerRecord.gemini_*
fields (schema name kept for output stability). Evidence is code-templated, citing the
absolute figure AND its percentile (or band).

Growth = percentile of the MEDIAN ANNUAL revenue growth over the fiscal-year
series (>= 4 GJ), under the consistency cap. It replaced yfinance revenueGrowth,
which is a single quarter vs the year-ago quarter: one soft quarter put MA and V at
3, one-quarter spikes put VAR.OL (+103 %) and AKER.OL (+361 %) at 5. Without a
median (<4 GJ) the quarterly percentile stands in, capped at neutral -- the cap only
lowers. The basis gate's revenue-growth floor (filters/runner) still reads the
quarterly figure; that is a different question (viability, not merit).

Resilience = gross-margin percentile averaged with a FIXED ABSOLUTE leverage band on
net debt / EBITDA. Debt/equity was dropped: buybacks shrink book equity to near zero
or below, so D/E measured cosmetics (MA scored 0, TDG at 6x net debt/EBITDA scored 5).
Net debt / EBITDA does not depend on book equity.

Profitability = operating-margin percentile averaged with the ROIC percentile
(app.screener.roic). ROE was dropped for the same reason as D/E: buybacks shrink
book equity to ~0 or below. 31 profitability red flags came from negative equity
alone, and FTNT's ROE of 117 % was cosmetic. A missing ROIC caps the axis at
neutral -- except invested capital <= 0 outside Financial Services, which means a
near-zero capital need (FTNT, BKNG); there the axis runs on operating margin alone."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.screener.growth_consistency import consistency_cap
from app.screener.percentiles import percentile_to_score
from app.screener.price_takers import (
    PriceTakerTable,
    is_price_taker,
    load_price_takers,
)
from app.screener.roic import (
    INVESTED_CAPITAL_NONPOSITIVE,
    NO_DEBT_CASH,
    NO_EBIT,
    NO_EQUITY,
    annotate_roic,
)

if TYPE_CHECKING:
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)

_RED_FLAG = 0
_NEUTRAL_AXIS = 3
# Sentinel der nicht bewertbaren Stetigkeit. Traegt bewusst dieselbe Zahl wie
# ein gemessener mittelmaessiger Titel -- unterschieden wird am Grund, nie am
# Wert (Spec 8.1).
NEUTRAL_STEADINESS = 3.0

# --- resilience leverage: net debt / EBITDA ----------------------------------
# Fixed, deliberately not configurable: a knob would let the red flag drift with
# whatever a given month seems to need.
LEVERAGE_REDFLAG_THRESHOLD = 4.0
# (inclusive upper bound of net debt / EBITDA, band). Net cash (ratio <= 0) earns
# the full band. Above the last bound: red flag, or band 0 in structural sectors.
_LEVERAGE_BANDS: tuple[tuple[float, float], ...] = (
    (0.0, 100.0),
    (1.0, 85.0),
    (2.0, 65.0),
    (3.0, 45.0),
    (LEVERAGE_REDFLAG_THRESHOLD, 25.0),
)
_STRUCTURAL_BAND = 0.0
# Regulated / asset-backed balance sheets carry high leverage by design (yfinance
# sector labels). They get band 0 instead of the red flag.
STRUCTURAL_LEVERAGE_SECTORS: frozenset[str] = frozenset({"Utilities", "Real Estate"})
RED_FLAG_RATIO_ABOVE_THRESHOLD = "net_debt_to_ebitda_above_4"
RED_FLAG_NET_DEBT_NONPOSITIVE_EBITDA = "net_debt_with_nonpositive_ebitda"
# A missing input -- leverage OR gross margin -- must never score better than
# neutral (IBKR: a broker without EBITDA and gross margin P95 would otherwise score
# 5 on margin alone; symmetrically, net cash alone must not score 5).
_MISSING_INPUT_CAP = 3

# --- growth: median annual revenue growth -------------------------------------
# Both cohort-global percentiles (sector_percentiles). The quarterly YoY only
# stands in when the fiscal-year series is too short for a median (<4 GJ).
MEDIAN_GROWTH_INPUT = "revenue_growth_median"
QUARTER_GROWTH_INPUT = "revenue_growth_yoy"
# Steady-growth floor (median path only): a median >= 5 % without a single down
# year scores at least 4. Absolute, fixed, not configurable -- a relative band
# would swallow the judgment "grows steadily enough" (spec 2026-10-08).
STEADY_GROWTH_MIN_MEDIAN = 0.05
STEADY_GROWTH_FLOOR = 4

# --- profitability: operating margin + ROIC -----------------------------------
_PROFITABILITY_INPUTS = ("operating_margin", "return_on_invested_capital")
ROIC_GAP = "roic"
# Invested capital <= 0 with EBIT > 0 normally means a near-zero capital need
# (FTNT, BKNG): the axis runs on operating margin alone. In these sectors it is
# client money on the balance sheet (IBKR, XTB.WA), so the missing-input cap
# applies. Fixed, not configurable, like the structural leverage sectors.
ROIC_IC_NONPOSITIVE_CAPPED_SECTORS: frozenset[str] = frozenset({"Financial Services"})
_ROIC_MISSING_TEXT = {
    NO_EBIT: "no EBIT",
    NO_EQUITY: "no equity",
    NO_DEBT_CASH: "no debt/cash data",
    INVESTED_CAPITAL_NONPOSITIVE: "invested capital <= 0",
}


@dataclass(frozen=True)
class LeverageAssessment:
    """Leverage half of resilience. Exactly one of three outcomes: a `band`, a
    `red_flag`, or neither (missing -> `gaps` name what is missing)."""

    text: str
    band: float | None = None
    red_flag: str | None = None
    gaps: tuple[str, ...] = field(default_factory=tuple)

    @property
    def known(self) -> bool:
        return self.band is not None or self.red_flag is not None


def net_debt(record: "ScreenerRecord") -> float | None:
    """total_debt - total_cash; a missing side counts as 0 only if the other is
    present. Both missing -> None (unknown, not zero)."""
    if record.total_debt is None and record.total_cash is None:
        return None
    return (record.total_debt or 0.0) - (record.total_cash or 0.0)


def leverage_ratio(record: "ScreenerRecord") -> float | None:
    """Net debt / EBITDA, defined only for EBITDA > 0 and known net debt."""
    nd = net_debt(record)
    if nd is None or record.ebitda is None or record.ebitda <= 0:
        return None
    return nd / record.ebitda


def _band_for(ratio: float) -> float | None:
    for upper, band in _LEVERAGE_BANDS:
        if ratio <= upper:
            return band
    return None  # above the red-flag threshold


def _missing_leverage(nd: float | None, ebitda: float | None) -> LeverageAssessment:
    gaps = []
    reasons = []
    if ebitda is None:
        gaps.append("ebitda")
        reasons.append("no EBITDA")
    if nd is None:
        gaps.append("net_debt")
        reasons.append("no debt/cash data")
    return LeverageAssessment(
        text=f"net debt/EBITDA n/a ({', '.join(reasons)})", gaps=tuple(gaps)
    )


def assess_leverage(record: "ScreenerRecord") -> LeverageAssessment:
    nd = net_debt(record)
    ebitda = record.ebitda
    if nd is None or ebitda is None:
        return _missing_leverage(nd, ebitda)
    structural = record.gics_sector in STRUCTURAL_LEVERAGE_SECTORS
    exempt = "(band 0, structural sector — no red flag)"
    if ebitda <= 0:
        if nd <= 0:
            # Net cash without earnings power: leverage is undefined, not good.
            return LeverageAssessment(
                text="net cash with EBITDA <= 0, net debt/EBITDA n/a",
                gaps=("ebitda_nonpositive",),
            )
        if structural:
            return LeverageAssessment(
                text=f"net debt with EBITDA <= 0 {exempt}", band=_STRUCTURAL_BAND
            )
        return LeverageAssessment(
            text="net debt with EBITDA <= 0 — RED FLAG",
            red_flag=RED_FLAG_NET_DEBT_NONPOSITIVE_EBITDA,
        )
    ratio = nd / ebitda
    band = _band_for(ratio)
    if band is None:
        if structural:
            return LeverageAssessment(
                text=f"net debt/EBITDA {ratio:.1f}x {exempt}", band=_STRUCTURAL_BAND
            )
        return LeverageAssessment(
            text=(
                f"net debt/EBITDA {ratio:.1f}x — RED FLAG > "
                f"{LEVERAGE_REDFLAG_THRESHOLD:.1f}x"
            ),
            red_flag=RED_FLAG_RATIO_ABOVE_THRESHOLD,
        )
    if nd <= 0:
        text = f"net cash (net debt/EBITDA {ratio:.1f}x, band {band:.0f})"
    else:
        text = f"net debt/EBITDA {ratio:.1f}x (band {band:.0f})"
    return LeverageAssessment(text=text, band=band)


def _resilience_score(gm_p: float | None, lev: LeverageAssessment) -> int:
    if lev.red_flag is not None:
        return _RED_FLAG
    if lev.band is not None:
        if gm_p is None:
            # Symmetric to the missing-leverage cap: one missing input never
            # scores better than neutral.
            return min(_MISSING_INPUT_CAP, percentile_to_score(lev.band))
        return percentile_to_score((lev.band + gm_p) / 2)
    if gm_p is None:
        return _MISSING_INPUT_CAP
    return min(_MISSING_INPUT_CAP, percentile_to_score(gm_p))


def _mean_axis_score(pcts: dict[str, float], fields: tuple[str, ...]) -> int | None:
    vals = [pcts[f] for f in fields if f in pcts]
    if not vals:
        return None
    return percentile_to_score(sum(vals) / len(vals))


def _pct_decimal(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def _evidence(
    record: "ScreenerRecord", pcts: dict[str, float], specs: list[tuple[str, str]]
) -> str:
    """specs: list of (field, label) for decimal-ratio fields (0.45 -> 45.0%)."""
    parts = []
    for field_name, label in specs:
        raw = getattr(record, field_name)
        if raw is None:
            parts.append(f"{label} n/a")
            continue
        p = pcts.get(field_name)
        parts.append(
            f"{label} {_pct_decimal(raw)}" + (f" (P{p:.0f})" if p is not None else "")
        )
    return ", ".join(parts)


def _roic_cap_applies(record: "ScreenerRecord") -> bool:
    """A missing ROIC caps profitability at neutral, except invested capital <= 0
    outside the client-money sectors (see ROIC_IC_NONPOSITIVE_CAPPED_SECTORS)."""
    if record.roic_missing_reason != INVESTED_CAPITAL_NONPOSITIVE:
        return True
    return record.gics_sector in ROIC_IC_NONPOSITIVE_CAPPED_SECTORS


def _roic_text(record: "ScreenerRecord", pcts: dict[str, float]) -> str:
    if record.return_on_invested_capital is not None:
        return _evidence(record, pcts, [("return_on_invested_capital", "ROIC")])
    reason = _ROIC_MISSING_TEXT.get(record.roic_missing_reason or "")
    return f"ROIC n/a ({reason})" if reason else "ROIC n/a"


def _score_profitability(
    record: "ScreenerRecord",
    pcts: dict[str, float],
    data_gaps: list[str],
) -> tuple[int, str, bool]:
    """(score, evidence, partial). Red flag on an absolute loss: operating margin
    or ROIC below 0. A missing ROIC is a data gap and, unless exempt, caps the
    axis at neutral -- the cap only lowers, never raises."""
    score = _mean_axis_score(pcts, _PROFITABILITY_INPUTS)
    if score is None:
        score = _NEUTRAL_AXIS
        data_gaps.append("operating_margin/return_on_invested_capital")
    roic = record.return_on_invested_capital
    if (record.operating_margin is not None and record.operating_margin < 0) or (
        roic is not None and roic < 0
    ):
        score = _RED_FLAG
    evidence = _evidence(record, pcts, [("operating_margin", "op margin")])
    evidence += f", {_roic_text(record, pcts)}"
    if roic is None:
        data_gaps.append(ROIC_GAP)
        if _roic_cap_applies(record) and score > _MISSING_INPUT_CAP:
            score = _MISSING_INPUT_CAP
            evidence += f" — capped at {_MISSING_INPUT_CAP}"
    partial = sum(1 for f in _PROFITABILITY_INPUTS if f in pcts) == 1
    return score, evidence, partial


def _score_resilience(
    record: "ScreenerRecord",
    pcts: dict[str, float],
    data_gaps: list[str],
) -> tuple[int, str, bool]:
    """(score, evidence, partial). Sets record.resilience_red_flag."""
    gm_p = pcts.get("gross_margin")
    lev = assess_leverage(record)
    record.resilience_red_flag = lev.red_flag
    data_gaps.extend(lev.gaps)
    if gm_p is None:
        data_gaps.append("gross_margin")
    evidence = _evidence(record, pcts, [("gross_margin", "gross margin")])
    evidence += f", {lev.text}"
    # Either input missing caps at neutral; a red flag stays 0 and needs no note.
    if lev.red_flag is None and (gm_p is None or not lev.known):
        evidence += f" — capped at {_MISSING_INPUT_CAP}"
    partial = (gm_p is not None) != lev.known
    return _resilience_score(gm_p, lev), evidence, partial


def _quarter_text(record: "ScreenerRecord", pcts: dict[str, float]) -> str:
    return _evidence(record, pcts, [(QUARTER_GROWTH_INPUT, "latest quarter YoY")])


def _is_steady_grower(record: "ScreenerRecord") -> bool:
    """Median annual growth >= STEADY_GROWTH_MIN_MEDIAN and no down year in the
    window (consistency 1.0, whose cap is 5 -- the floor never fights the cap)."""
    median = record.revenue_growth_median
    return (
        median is not None
        and median >= STEADY_GROWTH_MIN_MEDIAN
        and record.growth_consistency == 1.0
    )


def _score_growth(
    record: "ScreenerRecord",
    pcts: dict[str, float],
    data_gaps: list[str],
) -> tuple[int, str]:
    """(score, evidence). Median annual growth percentile; without it, the
    quarterly YoY percentile (else neutral) capped at neutral -- the cap only
    lowers. The consistency cap applies on top either way; on the median path a
    steady grower is then floored at STEADY_GROWTH_FLOOR."""
    cons = record.growth_consistency
    if MEDIAN_GROWTH_INPUT in pcts:
        score = percentile_to_score(pcts[MEDIAN_GROWTH_INPUT])
        evidence = (
            _evidence(record, pcts, [(MEDIAN_GROWTH_INPUT, "rev growth median")])
            + (
                f", consistency {cons:.2f}"
                if cons is not None
                else ", consistency n/a (<4 GJ)"
            )
            + f", latest quarter YoY {_pct_decimal(record.revenue_growth_yoy)}"
        )
        capped = min(score, consistency_cap(cons))
        if _is_steady_grower(record) and capped < STEADY_GROWTH_FLOOR:
            evidence += f" — steady-growth floor {STEADY_GROWTH_FLOOR}"
            return STEADY_GROWTH_FLOOR, evidence
        return capped, evidence

    data_gaps.append(MEDIAN_GROWTH_INPUT)
    if QUARTER_GROWTH_INPUT in pcts:
        base = percentile_to_score(pcts[QUARTER_GROWTH_INPUT])
    else:
        base = _NEUTRAL_AXIS
        data_gaps.append(QUARTER_GROWTH_INPUT)
    median_text = (
        "rev growth median n/a (<4 GJ)"
        if record.revenue_growth_median is None
        else f"rev growth median {_pct_decimal(record.revenue_growth_median)}"
    )
    evidence = f"{median_text}, {_quarter_text(record, pcts)}"
    if cons is not None:
        evidence += f", consistency {cons:.2f}"
    if base > _MISSING_INPUT_CAP:
        evidence += f" — capped at {_MISSING_INPUT_CAP}"
    score = min(base, _MISSING_INPUT_CAP, consistency_cap(cons))
    return score, evidence


def score_record(record: "ScreenerRecord") -> None:
    pcts = record.input_percentiles or {}
    dims: dict[str, int] = {}
    evidence: dict[str, str] = {}
    data_gaps: list[str] = []

    # growth — global median-growth percentile (YoY fallback), consistency cap
    dims["growth"], evidence["growth"] = _score_growth(record, pcts, data_gaps)

    # profitability — op margin + ROIC percentiles; red-flag on absolute losses
    prof, evidence["profitability"], prof_partial = _score_profitability(
        record, pcts, data_gaps
    )
    dims["profitability"] = prof

    # resilience — gross-margin percentile + absolute net debt/EBITDA band
    resil, evidence["resilience"], resil_partial = _score_resilience(
        record, pcts, data_gaps
    )
    dims["resilience"] = resil

    # sentinels (not merit; mirror dimensions.py)
    dims["management"] = _NEUTRAL_AXIS
    dims["innovation"] = _NEUTRAL_AXIS
    evidence["management"] = "insufficient data: governance screened upstream"
    evidence["innovation"] = "insufficient data: no R&D data"

    merit = {
        "growth": dims["growth"],
        "profitability": dims["profitability"],
        "resilience": dims["resilience"],
    }
    record.gemini_dimensions = dims
    record.gemini_evidence = evidence
    record.gemini_weakest_dimension = min(merit, key=lambda k: merit[k])
    record.gemini_data_gaps = data_gaps
    record.data_confidence = (
        "low" if (record.growth_consistency is None or data_gaps) else "ok"
    )

    partial = []
    if prof_partial:
        partial.append("profitability")
    if resil_partial:
        partial.append("resilience")
    record.partial_evidence_axes = partial


def annotate_steadiness(records, annual_series, run_tracker=None) -> None:
    """Vierte Achse aus den EDGAR-Jahresreihen.

    LIEST NUR (Spec 9.3.1): ein abgelaufener Eintrag wird benutzt, ein fehlender
    stellt den Titel neutral. Der Monatslauf geht hier unter keinen Umstaenden
    zur SEC -- sonst haenge die 1800-s-Deadline am Cache-Zustand.

    Ohne CIK gibt es keine Reihe: der Titel ist kein SEC-Registrant. Das ist ein
    eigener Grund und keine schlechte Bewertung."""
    from app.screener.steadiness import (
        NO_SEC_REGISTRANT,
        steadiness_from_record,
    )

    for record in records:
        if not record.cik:
            record.steadiness = NEUTRAL_STEADINESS
            record.steadiness_reason = NO_SEC_REGISTRANT
            continue
        lookup = annual_series.read_annual_series(record.cik)
        if run_tracker is not None:
            run_tracker.record_steadiness_lookup(lookup.status)
        result = steadiness_from_record(lookup.record)
        record.steadiness = result.score
        record.steadiness_reason = result.reason


def run_deterministic_scoring(
    records,
    revenue_cache,
    run_tracker,
    annual_series=None,
    price_takers: PriceTakerTable | None = None,
):
    """Tool-A scoring entry point (replaces run_gemini_scoring). For each record:
    fetch its multi-year revenue series (cached), compute growth_consistency, the
    median annual revenue growth and ROIC, then annotate percentiles across the
    whole cohort (they rank the ROIC and the median), then score each
    deterministically, then flag price takers.
    Records zero tokens per ticker (LLM-free) so cost tracking stays accurate.

    `annual_series` ist optional: fehlt es, bleibt die Stetigkeits-Achse
    unbesetzt und das Gate verhaelt sich exakt wie vor ihrer Einfuehrung.

    `price_takers` defaults to the committed `data/price_takers.json`, loaded
    once per run and before any work (fail loud on an absent table). Price
    takers stay in the cohort: removing them before the percentiles would
    shrink Energy below MIN_SECTOR_N and shift ~90 other scores. The flag only
    bars them from the crosshits (`is_crosshit`)."""
    from app.screener.growth_consistency import (
        consistency_ratio,
        median_annual_growth,
    )
    from app.screener.sector_percentiles import annotate_percentiles

    table = price_takers if price_takers is not None else load_price_takers()
    for record in records:
        revenues = revenue_cache.get_revenue_series(record.ticker)
        record.growth_consistency = consistency_ratio(revenues)
        record.revenue_growth_median = median_annual_growth(revenues)
    annotate_roic(records)
    annotate_percentiles(records)
    if annual_series is not None:
        annotate_steadiness(records, annual_series, run_tracker)
    for record in records:
        score_record(record)
        record.price_taker = is_price_taker(record.ticker, record.gics_industry, table)
        run_tracker.record_ticker(0, 0)
    n_flags = sum(1 for r in records if r.resilience_red_flag)
    n_takers = sum(1 for r in records if r.price_taker)
    logger.info(
        "deterministic_scorer: scored %d records (LLM-free), %d leverage red flags, "
        "%d price takers",
        len(records),
        n_flags,
        n_takers,
    )
    return records
