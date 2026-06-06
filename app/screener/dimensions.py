from typing import Final

from app.models.screener_record import ScreenerRecord

DIMENSIONS: Final[tuple[str, ...]] = (
    "growth",
    "profitability",
    "management",
    "innovation",
    "resilience",
)


def qualifying_dimensions(record: ScreenerRecord, score_threshold: float) -> list[str]:
    """Dimensions whose Gemini score meets the threshold. Empty if unscored."""
    dims = record.gemini_dimensions or {}
    return [d for d in DIMENSIONS if dims.get(d, 0) >= score_threshold]


def is_crosshit(record: ScreenerRecord, score_threshold: float, min_dimensions: int) -> bool:
    """True iff the record qualifies on >= min_dimensions (cap-independent — the
    display cap in crosshits_generator is presentation, not a funnel exit)."""
    return len(qualifying_dimensions(record, score_threshold)) >= min_dimensions
