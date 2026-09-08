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


def steadiness_is_assessable(record: ScreenerRecord) -> bool:
    """Whether the steadiness axis carries a measurement for this title.

    Read the REASON, never the score. A measured 3.0 and the sentinel 3.0 of a
    title with no usable series are the same number; deciding on the value
    merges them, and it merges them in favour of the cyclical title (spec 8.1).
    """
    return record.steadiness is not None and record.steadiness_reason is None


def is_crosshit(
    record: ScreenerRecord, score_threshold: float, min_dimensions: int
) -> bool:
    """True iff min_dimensions merit axes clear the threshold AND steadiness
    clears it too, where steadiness was measured (cap-independent — the display
    cap in crosshits_generator is presentation, not a funnel exit).

    Steadiness counts when it was measured and is skipped when it was not. A
    title with history therefore faces a stricter bar than before; a title
    without history faces exactly the previous one. That is "neutral = neither
    an advantage nor a penalty", stated precisely (spec 8).

    The spec words the rule as "all assessable merit axes, at least three". In
    production the two readings coincide: min_dimensions is 3 and there are
    exactly three yfinance axes, so "at least three of three" IS "all of them".
    They part only when min_dimensions is set below 3, which happens in local
    experiments (`.env` carries 2). Enforcing "all assessable" there would make
    that knob silently inert, so the yfinance axes keep their existing rule and
    steadiness is layered on top.
    """
    if len(qualifying_dimensions(record, score_threshold)) < min_dimensions:
        return False
    if steadiness_is_assessable(record):
        return (record.steadiness or 0.0) >= score_threshold
    return True
