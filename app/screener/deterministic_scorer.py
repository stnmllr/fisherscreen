"""Deterministic Tool-A scorer (Approach B / A1 — no LLM).

Maps the percentile annotations (sector_percentiles.annotate_percentiles) + the absolute
growth-consistency cap + absolute red-flag overlays to the ScreenerRecord.gemini_*
fields (schema name kept for output stability). Evidence is code-templated, citing the
absolute figure AND its percentile. debt_to_equity is in percent-points (45.0 = 45%)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.screener.growth_consistency import consistency_cap
from app.screener.percentiles import percentile_to_score

if TYPE_CHECKING:
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)

_RED_FLAG = 0
_DE_REDFLAG_THRESHOLD = 300.0  # percent-points: >300% (3x equity)


def _mean_axis_score(pcts: dict[str, float], fields: tuple[str, ...],
                     invert: tuple[str, ...] = ()) -> int | None:
    vals = []
    for f in fields:
        if f in pcts:
            p = pcts[f]
            vals.append(100.0 - p if f in invert else p)
    if not vals:
        return None
    return percentile_to_score(sum(vals) / len(vals))


def _pct_decimal(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def _evidence(record: "ScreenerRecord", pcts: dict[str, float],
              specs: list[tuple[str, str, str]]) -> str:
    """specs: list of (field, label, formatter) where formatter in {"decimal","de"}."""
    parts = []
    for field, label, kind in specs:
        raw = getattr(record, field)
        if field == "debt_to_equity" and raw is not None and raw < 0:
            parts.append(f"{label} n/a (negative book equity)")
            continue
        if raw is None:
            parts.append(f"{label} n/a")
            continue
        shown = f"{raw:.1f}%" if kind == "de" else _pct_decimal(raw)
        p = pcts.get(field)
        parts.append(f"{label} {shown}" + (f" (P{p:.0f})" if p is not None else ""))
    return ", ".join(parts)


def score_record(record: "ScreenerRecord") -> None:
    pcts = record.input_percentiles or {}
    dims: dict[str, int] = {}
    evidence: dict[str, str] = {}
    data_gaps: list[str] = []

    # growth — global percentile, then absolute consistency cap
    if "revenue_growth_yoy" in pcts:
        growth = percentile_to_score(pcts["revenue_growth_yoy"])
    else:
        growth = 3  # no percentile available: neutral sentinel (same as profitability/resilience)
        data_gaps.append("revenue_growth_yoy")
    growth = min(growth, consistency_cap(record.growth_consistency))
    dims["growth"] = growth
    cons = record.growth_consistency
    evidence["growth"] = _evidence(record, pcts, [("revenue_growth_yoy", "rev growth", "decimal")]) + (
        f", consistency {cons:.2f}" if cons is not None else ", consistency n/a (<4 GJ)")

    # profitability — sector/global percentile; red-flag on absolute losses
    prof = _mean_axis_score(pcts, ("operating_margin", "return_on_equity"))
    if prof is None:
        prof = 3
        data_gaps.append("operating_margin/return_on_equity")
    if (record.operating_margin is not None and record.operating_margin < 0) or (
            record.return_on_equity is not None and record.return_on_equity < 0):
        prof = _RED_FLAG
    dims["profitability"] = prof
    evidence["profitability"] = _evidence(record, pcts, [
        ("operating_margin", "op margin", "decimal"), ("return_on_equity", "ROE", "decimal")])

    # resilience — gross_margin + inverted d/e (d/e<0 already excluded upstream);
    # red-flag on extreme positive leverage
    resil = _mean_axis_score(pcts, ("gross_margin", "debt_to_equity"), invert=("debt_to_equity",))
    if resil is None:
        resil = 3
        data_gaps.append("gross_margin/debt_to_equity")
    if record.debt_to_equity is not None and record.debt_to_equity > _DE_REDFLAG_THRESHOLD:
        resil = _RED_FLAG
    dims["resilience"] = resil
    evidence["resilience"] = _evidence(record, pcts, [
        ("gross_margin", "gross margin", "decimal"), ("debt_to_equity", "d/e", "de")])

    # sentinels (not merit; mirror dimensions.py)
    dims["management"] = 3
    dims["innovation"] = 3
    evidence["management"] = "insufficient data: governance screened upstream"
    evidence["innovation"] = "insufficient data: no R&D data"

    merit = {"growth": dims["growth"], "profitability": dims["profitability"],
             "resilience": dims["resilience"]}
    record.gemini_dimensions = dims
    record.gemini_evidence = evidence
    record.gemini_weakest_dimension = min(merit, key=lambda k: merit[k])
    record.gemini_data_gaps = data_gaps
    record.data_confidence = "low" if (record.growth_consistency is None or data_gaps) else "ok"

    partial = []
    if sum(1 for f in ("operating_margin", "return_on_equity") if f in pcts) == 1:
        partial.append("profitability")
    if sum(1 for f in ("gross_margin", "debt_to_equity") if f in pcts) == 1:
        partial.append("resilience")
    record.partial_evidence_axes = partial


def run_deterministic_scoring(records, revenue_cache, run_tracker):
    """Tool-A scoring entry point (replaces run_gemini_scoring). For each record:
    fetch its multi-year revenue series (cached), compute growth_consistency, then
    annotate percentiles across the whole cohort, then score each deterministically.
    Records zero tokens per ticker (LLM-free) so cost tracking stays accurate."""
    from app.screener.growth_consistency import consistency_ratio
    from app.screener.sector_percentiles import annotate_percentiles

    for record in records:
        revenues = revenue_cache.get_revenue_series(record.ticker)
        record.growth_consistency = consistency_ratio(revenues)
    annotate_percentiles(records)
    for record in records:
        score_record(record)
        run_tracker.record_ticker(0, 0)
    logger.info("deterministic_scorer: scored %d records (LLM-free)", len(records))
    return records
