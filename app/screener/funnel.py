from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.models.screener_record import ScreenerRecord

# --- Tunable instrumentation constants (severity only; no gate touches these) ---
LARGE_CAP_VOLUME_EUR = 3_000_000_000     # GATE_VOLUME: a big name failing volume ~ data bug
LARGE_CAP_GROWTH_EUR = 10_000_000_000    # GATE_REVENUE_GROWTH: big mature firm can really shrink
SECTOR_WIDE_FRACTION = 0.5
SECTOR_WIDE_MIN_SIZE = 5
SECTORS_WITHOUT_GROSS_MARGIN = {"Financial Services", "Real Estate"}  # yfinance taxonomy


class ReasonCode(str, Enum):
    RESOLUTION_DEGRADED_DICT = "RESOLUTION_DEGRADED_DICT"
    RESOLUTION_UNRESOLVED = "RESOLUTION_UNRESOLVED"
    RESOLUTION_NO_SYMBOL_DATA = "RESOLUTION_NO_SYMBOL_DATA"
    RESOLUTION_FX_UNAVAILABLE = "RESOLUTION_FX_UNAVAILABLE"
    GATE_VOLUME = "GATE_VOLUME"
    GATE_MARKET_CAP = "GATE_MARKET_CAP"
    FRAMEWORK_METRIK_NA = "FRAMEWORK_METRIK_NA"  # Fisher-Raster nicht anwendbar (gm strukturell undefiniert)
    # Transient/retryable: income-statement could not be fetched this run — not a quality-fail.
    # RESOLUTION_ prefix follows the reason's SEMANTICS (a needed data fetch failed → divert →
    # retry), not the stage it is reported at: it is the sibling of RESOLUTION_FX_UNAVAILABLE /
    # RESOLUTION_NO_SYMBOL_DATA, and deliberately NOT grouped with the permanent, structural
    # FRAMEWORK_METRIK_NA. It is still diverted at the BASIS stage (metric_na position).
    RESOLUTION_STATEMENT_UNAVAILABLE = "RESOLUTION_STATEMENT_UNAVAILABLE"
    GATE_GROSS_MARGIN = "GATE_GROSS_MARGIN"
    GATE_REVENUE_GROWTH = "GATE_REVENUE_GROWTH"
    GATE_RESTATEMENT = "GATE_RESTATEMENT"
    GATE_GOING_CONCERN = "GATE_GOING_CONCERN"
    GATE_ENFORCEMENT = "GATE_ENFORCEMENT"
    SCORE_BELOW_THRESHOLD = "SCORE_BELOW_THRESHOLD"
    SCORE_NOT_SCORED = "SCORE_NOT_SCORED"


class SeverityBucket(str, Enum):
    BENIGN = "BENIGN"
    REVIEW = "REVIEW"


class Stage(str, Enum):
    UNIVERSE = "universe"
    RESOLUTION = "resolution"
    BASIS_GATES = "basis_gates"
    EDGAR_GATES = "edgar_gates"
    SCORING = "scoring"
    CROSSHITS = "crosshits"


# Map the code's filter_failed_reason -> reason_code (1:1, no invented codes).
_BASIS_REASON: dict[str, ReasonCode] = {
    "avg_volume": ReasonCode.GATE_VOLUME,
    "market_cap": ReasonCode.GATE_MARKET_CAP,
    "metric_na": ReasonCode.FRAMEWORK_METRIK_NA,
    "statement_unavailable": ReasonCode.RESOLUTION_STATEMENT_UNAVAILABLE,
    "gross_margin": ReasonCode.GATE_GROSS_MARGIN,
    "revenue_growth": ReasonCode.GATE_REVENUE_GROWTH,
}
_EDGAR_REASON: dict[str, ReasonCode] = {
    "restatement": ReasonCode.GATE_RESTATEMENT,
    "going_concern": ReasonCode.GATE_GOING_CONCERN,
    "enforcement": ReasonCode.GATE_ENFORCEMENT,
}

_ALWAYS_REVIEW = {
    ReasonCode.RESOLUTION_DEGRADED_DICT,
    ReasonCode.RESOLUTION_NO_SYMBOL_DATA,
    ReasonCode.RESOLUTION_FX_UNAVAILABLE,
    ReasonCode.RESOLUTION_STATEMENT_UNAVAILABLE,  # transient/retryable — must not silently disappear
    ReasonCode.SCORE_NOT_SCORED,
}


def _severity(
    reason_code: ReasonCode,
    *,
    market_cap_eur: float | None,
    sector_wide: bool,
) -> SeverityBucket:
    """Fixed table. market_cap_eur=None is treated as 'not large-cap' (never None>=int)."""
    mc = market_cap_eur if market_cap_eur is not None else -1.0
    if reason_code == ReasonCode.GATE_VOLUME:
        return SeverityBucket.REVIEW if mc >= LARGE_CAP_VOLUME_EUR else SeverityBucket.BENIGN
    if reason_code == ReasonCode.GATE_REVENUE_GROWTH:
        return SeverityBucket.REVIEW if mc >= LARGE_CAP_GROWTH_EUR else SeverityBucket.BENIGN
    if reason_code == ReasonCode.GATE_GROSS_MARGIN:
        return SeverityBucket.REVIEW if sector_wide else SeverityBucket.BENIGN
    if reason_code in _ALWAYS_REVIEW:
        return SeverityBucket.REVIEW
    return SeverityBucket.BENIGN


@dataclass(frozen=True)
class Dropout:
    ticker: str
    stage: Stage
    reason_code: ReasonCode
    severity_bucket: SeverityBucket
    is_large_cap: bool            # market_cap_eur >= LARGE_CAP_VOLUME_EUR (descriptive floor)
    sector_wide: bool
    market_cap_eur: float | None
    gics_sector: str | None
    detail: str = ""  # 0b sub-reason for RESOLUTION_NO_SYMBOL_DATA (NO_RAW_MC|NO_CURRENCY|NO_VOLUME); else ""


@dataclass(frozen=True)
class FunnelStage:
    stage: Stage
    entered: int
    dropped: int
    remaining: int
    ran: bool = True


@dataclass
class FunnelSummary:
    stages: list[FunnelStage]
    review_flags: int
    pass_through_count: int
    provenance: dict[str, Any] | None = field(default=None)

    def stage(self, stage: Stage) -> FunnelStage:
        for s in self.stages:
            if s.stage == stage:
                return s
        raise KeyError(stage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stages": [
                {"stage": s.stage.value, "entered": s.entered, "dropped": s.dropped,
                 "remaining": s.remaining, "ran": s.ran}
                for s in self.stages
            ],
            "review_flags": self.review_flags,
            "pass_through_count": self.pass_through_count,
            "provenance": self.provenance,
        }


def _is_large_cap(market_cap_eur: float | None) -> bool:
    return market_cap_eur is not None and market_cap_eur >= LARGE_CAP_VOLUME_EUR


def _compute_sector_wide(resolved: list[ScreenerRecord]) -> set[str]:
    """Return the set of sectors flagged sector_wide for GATE_GROSS_MARGIN.

    Denominator = records that REACHED the margin gate = basis-passed
    + gross_margin drops + revenue_growth drops (short-circuit order:
    volume->market_cap->gross_margin->revenue_growth, so volume/market_cap
    drops never reached margin). Margin-free sectors are excluded outright.
    """
    reached: dict[str, int] = {}
    margin_drops: dict[str, int] = {}
    for r in resolved:
        sector = r.gics_sector
        if sector in SECTORS_WITHOUT_GROSS_MARGIN:
            continue
        reason = r.filter_failed_reason
        reached_gate = (
            r.filter_passed_basis is True
            or reason in ("gross_margin", "revenue_growth")
        )
        if reached_gate:
            reached[sector] = reached.get(sector, 0) + 1
        if reason == "gross_margin":
            margin_drops[sector] = margin_drops.get(sector, 0) + 1
    flagged: set[str] = set()
    for sector, n in reached.items():
        m = margin_drops.get(sector, 0)
        if n >= SECTOR_WIDE_MIN_SIZE and n > 0 and (m / n) >= SECTOR_WIDE_FRACTION:
            flagged.add(sector)
    return flagged


def _make_dropout(record: ScreenerRecord, stage: Stage, reason_code: ReasonCode,
                  sector_wide_sectors: set[str], detail: str = "") -> Dropout:
    sector_wide = (reason_code == ReasonCode.GATE_GROSS_MARGIN
                   and record.gics_sector in sector_wide_sectors)
    severity = _severity(reason_code, market_cap_eur=record.market_cap_eur,
                         sector_wide=sector_wide)
    return Dropout(
        ticker=record.ticker, stage=stage, reason_code=reason_code,
        severity_bucket=severity, is_large_cap=_is_large_cap(record.market_cap_eur),
        sector_wide=sector_wide, market_cap_eur=record.market_cap_eur,
        gics_sector=record.gics_sector, detail=detail,
    )


def build_funnel(
    universe: list[str],
    basis: "BasisFilterResult",
    scored: list[ScreenerRecord] | None,
    *,
    score_threshold: float,
    crosshits_min_dimensions: int,
    provenance: dict[str, Any] | None = None,
) -> tuple[FunnelSummary, list[Dropout]]:
    from app.screener.dimensions import is_crosshit  # local import avoids cycle

    n_universe = len(universe)
    dropouts: list[Dropout] = []
    sector_wide_sectors = _compute_sector_wide(basis.resolved)

    # --- Resolution ---
    for t in basis.degraded:
        dropouts.append(Dropout(t, Stage.RESOLUTION, ReasonCode.RESOLUTION_DEGRADED_DICT,
                                SeverityBucket.REVIEW, False, False, None, None))
    for t in basis.unresolved:
        if t in basis.degraded:
            continue
        dropouts.append(Dropout(t, Stage.RESOLUTION, ReasonCode.RESOLUTION_UNRESOLVED,
                                SeverityBucket.BENIGN, False, False, None, None))
    for r in basis.no_symbol_data:
        dropouts.append(_make_dropout(r, Stage.RESOLUTION, ReasonCode.RESOLUTION_NO_SYMBOL_DATA,
                                      sector_wide_sectors, detail=r.resolution_detail or ""))
    for r in basis.fx_unavailable:
        dropouts.append(_make_dropout(r, Stage.RESOLUTION, ReasonCode.RESOLUTION_FX_UNAVAILABLE,
                                      sector_wide_sectors, detail=r.resolution_detail or ""))
    n_resolved = len(basis.resolved)

    # --- Basis gates ---
    basis_drops = [r for r in basis.resolved if r.filter_passed_basis is False]
    for r in basis_drops:
        rc = _BASIS_REASON[r.filter_failed_reason]
        dropouts.append(_make_dropout(r, Stage.BASIS_GATES, rc, sector_wide_sectors))
    n_basis_passed = len(basis.passed)

    # --- EDGAR gates (pass-throughs are NOT drops) ---
    edgar_drops = [r for r in basis.passed if r.filter_passed_edgar is False]
    for r in edgar_drops:
        rc = _EDGAR_REASON[r.filter_failed_reason]
        dropouts.append(_make_dropout(r, Stage.EDGAR_GATES, rc, sector_wide_sectors))
    pass_through = [r for r in basis.passed if r.edgar_skipped]
    n_edgar_remaining = n_basis_passed - len(edgar_drops)

    stages = [
        FunnelStage(Stage.UNIVERSE, n_universe, 0, n_universe),
        FunnelStage(Stage.RESOLUTION, n_universe,
                    len(basis.unresolved) + len(basis.no_symbol_data) + len(basis.fx_unavailable),
                    n_resolved),
        FunnelStage(Stage.BASIS_GATES, n_resolved, len(basis_drops), n_basis_passed),
        FunnelStage(Stage.EDGAR_GATES, n_basis_passed, len(edgar_drops), n_edgar_remaining),
    ]

    # --- Scoring + Crosshits (only if scoring ran) ---
    if scored is None:
        stages.append(FunnelStage(Stage.SCORING, n_edgar_remaining, 0, n_edgar_remaining, ran=False))
        stages.append(FunnelStage(Stage.CROSSHITS, n_edgar_remaining, 0, n_edgar_remaining, ran=False))
    else:
        not_scored = [r for r in scored if r.gemini_dimensions is None]
        for r in not_scored:
            dropouts.append(_make_dropout(r, Stage.SCORING, ReasonCode.SCORE_NOT_SCORED,
                                          sector_wide_sectors))
        successfully_scored = [r for r in scored if r.gemini_dimensions is not None]
        crosshits = [r for r in successfully_scored
                     if is_crosshit(r, score_threshold, crosshits_min_dimensions)]
        below = [r for r in successfully_scored
                 if not is_crosshit(r, score_threshold, crosshits_min_dimensions)]
        for r in below:
            dropouts.append(_make_dropout(r, Stage.CROSSHITS, ReasonCode.SCORE_BELOW_THRESHOLD,
                                          sector_wide_sectors))
        stages.append(FunnelStage(Stage.SCORING, n_edgar_remaining, len(not_scored),
                                  len(successfully_scored)))
        stages.append(FunnelStage(Stage.CROSSHITS, len(successfully_scored), len(below),
                                  len(crosshits)))

    review_flags = sum(1 for d in dropouts if d.severity_bucket == SeverityBucket.REVIEW)
    summary = FunnelSummary(stages=stages, review_flags=review_flags,
                            pass_through_count=len(pass_through), provenance=provenance)
    return summary, dropouts
