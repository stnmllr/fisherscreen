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
    GATE_VOLUME = "GATE_VOLUME"
    GATE_MARKET_CAP = "GATE_MARKET_CAP"
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
    "gross_margin": ReasonCode.GATE_GROSS_MARGIN,
    "revenue_growth": ReasonCode.GATE_REVENUE_GROWTH,
}
_EDGAR_REASON: dict[str, ReasonCode] = {
    "restatement": ReasonCode.GATE_RESTATEMENT,
    "going_concern": ReasonCode.GATE_GOING_CONCERN,
    "enforcement": ReasonCode.GATE_ENFORCEMENT,
}

_ALWAYS_REVIEW = {ReasonCode.RESOLUTION_DEGRADED_DICT, ReasonCode.SCORE_NOT_SCORED}


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
