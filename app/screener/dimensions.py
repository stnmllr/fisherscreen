from typing import Final

from app.models.screener_record import ScreenerRecord

DIMENSIONS: Final[tuple[str, ...]] = (
    "growth",
    "profitability",
    "management",
    "innovation",
    "resilience",
)

# Tool A is honestly a three-axis screen. `management` is screened upstream by the
# EDGAR gate (every survivor has already passed governance checks), and `innovation`
# has no R&D data here — it is deferred to the Deep Dive. Both are emitted as fixed
# sentinel-3 scores and MUST NOT count toward crosshit merit. Only these three axes
# carry data-backed merit.
MERIT_DIMENSIONS: Final[tuple[str, ...]] = ("growth", "profitability", "resilience")


def qualifying_dimensions(record: ScreenerRecord, score_threshold: float) -> list[str]:
    """Merit dimensions whose Gemini score meets the threshold. Empty if unscored.

    Only MERIT_DIMENSIONS count — management/innovation are sentinel-3 and excluded.
    """
    dims = record.gemini_dimensions or {}
    return [d for d in MERIT_DIMENSIONS if dims.get(d, 0) >= score_threshold]


def is_crosshit(record: ScreenerRecord, score_threshold: float, min_dimensions: int) -> bool:
    """True iff the record qualifies on >= min_dimensions (cap-independent — the
    display cap in crosshits_generator is presentation, not a funnel exit)."""
    return len(qualifying_dimensions(record, score_threshold)) >= min_dimensions
