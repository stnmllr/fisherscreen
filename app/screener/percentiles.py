"""Pure percentile math for deterministic sector-relative scoring.

percentile_rank uses the midrank convention (ties share a rank), so the score is
stable under duplicate metric values. No I/O, no record types."""
from __future__ import annotations

# Pinned percentile -> score anchor bands (descending). P below the lowest band -> 1.
# Adjusted thresholds: 90→88 (≥5), 75→70 (≥4) for a modestly larger crosshit set (~25 vs 15).
_ANCHOR_BANDS: tuple[tuple[float, int], ...] = ((88.0, 5), (70.0, 4), (40.0, 3), (15.0, 2))


def percentile_rank(value: float, distribution: list[float]) -> float:
    """Midrank percentile (0..100) of `value` within `distribution`.

    `distribution` must be non-empty and already filtered to comparable (non-None)
    values; `value` is normally itself a member. Ties: 0.5 weight (standard midrank)."""
    n = len(distribution)
    below = sum(1 for v in distribution if v < value)
    equal = sum(1 for v in distribution if v == value)
    return 100.0 * (below + 0.5 * equal) / n


def percentile_to_score(p: float) -> int:
    """Map a percentile rank (0..100) to a 0–5 anchor score (1..5; 0 is red-flag-only)."""
    for threshold, score in _ANCHOR_BANDS:
        if p >= threshold:
            return score
    return 1
