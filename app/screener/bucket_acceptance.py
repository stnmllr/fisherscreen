"""Shared bucket-acceptance metrics + verdict for the Punkt-2 relative arm (CT-B).

Centralizes the pure dispersion/shape helpers (previously defined inline in
scripts/diagnose_bucket_dispersion.py) so the calibration instrument and any
future consumer share one implementation. Then adds the DEFECT-1 fix: an
ANTIMODE / GAP detector and the acceptance verdict.

DEFECT 1 background: the bimodality coefficient (BC) under-detects single-industry
multimodality — clearly multimodal buckets (e.g. a low cluster plus a separate
upper region with an empty histogram bin between them) passed as "clean". The
robust discriminator is an antimode: an EMPTY bin separating two populated regions,
each holding a non-trivial share of the mass. Raw width is NOT a reject reason —
wide-but-unimodal buckets must pass ("weit ist erlaubt, multimodal nicht"). BC is
demoted to an advisory metric, reported but not a hard reject.
"""
from __future__ import annotations

import statistics

# --- Transparent thresholds (NOT margin-/ticker-tuned). ---
CONSTITUENT_SPREAD_THRESHOLD = 0.15   # max-min of constituent-industry medians
BIMODALITY_THRESHOLD = 0.555          # Pearson/SAS bimodality coefficient cutoff (advisory only)
HIST_BINS = 10                        # bins for the ASCII histogram (display only)
ANTIMODE_MIN_SIDE_FRACTION = 0.20     # each side of an antimode must hold >= this mass share
ANTIMODE_MIN_N = 6                    # below this, distribution shape cannot be assessed
ANTIMODE_GAP_RATIO = 4.0              # a neighbour gap >= this x the typical spacing is a valley


# --------------------------------------------------------------------------- #
# Relocated pure helpers (behavior preserved; instrument imports these).
# --------------------------------------------------------------------------- #
def sample_skewness(values: list[float]) -> float | None:
    """Sample skewness (Fisher-Pearson, biased moment estimator g1).
    Returns None for n < 3 or zero variance (undefined)."""
    n = len(values)
    if n < 3:
        return None
    mean = statistics.fmean(values)
    m2 = sum((x - mean) ** 2 for x in values) / n
    m3 = sum((x - mean) ** 3 for x in values) / n
    if m2 == 0:
        return None
    return m3 / (m2 ** 1.5)


def sample_kurtosis(values: list[float]) -> float | None:
    """Sample kurtosis (NON-excess, i.e. m4/m2^2; normal == 3.0).
    Returns None for n < 4 or zero variance (undefined)."""
    n = len(values)
    if n < 4:
        return None
    mean = statistics.fmean(values)
    m2 = sum((x - mean) ** 2 for x in values) / n
    m4 = sum((x - mean) ** 4 for x in values) / n
    if m2 == 0:
        return None
    return m4 / (m2 ** 2)


def bimodality_coefficient(values: list[float]) -> float | None:
    """BC = (skewness^2 + 1) / kurtosis  (kurtosis NON-excess).
    BC > 0.555 (uniform-distribution reference) suggests bimodality. Advisory only.
    Returns None when skew/kurtosis are undefined (small n / zero variance)."""
    skew = sample_skewness(values)
    kurt = sample_kurtosis(values)
    if skew is None or kurt is None or kurt == 0:
        return None
    return (skew ** 2 + 1) / kurt


def constituent_median_spread(constituent_medians: list[float]) -> float | None:
    """max - min over the per-constituent-industry medians of a group bucket.
    Returns None for fewer than 2 constituents (a single-industry bucket cannot
    be multimodal across constituents)."""
    if len(constituent_medians) < 2:
        return None
    return max(constituent_medians) - min(constituent_medians)


def iqr(values: list[float]) -> float | None:
    """Inter-quartile range p75 - p25 (statistics.quantiles, exclusive method).
    Returns None for n < 2."""
    if len(values) < 2:
        return None
    qs = statistics.quantiles(values, n=4, method="exclusive")
    return qs[2] - qs[0]


def mad(values: list[float]) -> float | None:
    """Median absolute deviation about the median. None for empty input."""
    if not values:
        return None
    med = statistics.median(values)
    return statistics.median([abs(x - med) for x in values])


def ascii_histogram(values: list[float], *, bins: int = HIST_BINS, width: int = 40) -> list[str]:
    """Compact ASCII histogram so a human can eyeball unimodality directly.
    Returns a list of lines (bin range + bar)."""
    if not values:
        return ["  (no values)"]
    lo, hi = min(values), max(values)
    if hi == lo:
        return [f"  [{lo:.3f}] {'#' * min(width, len(values))} ({len(values)})"]
    span = hi - lo
    edges = [lo + span * i / bins for i in range(bins + 1)]
    counts = [0] * bins
    for x in values:
        idx = int((x - lo) / span * bins)
        if idx == bins:  # the maximum lands exactly on the top edge
            idx = bins - 1
        counts[idx] += 1
    peak = max(counts) or 1
    lines: list[str] = []
    for i in range(bins):
        bar = "#" * round(counts[i] / peak * width)
        lines.append(f"  [{edges[i]:6.3f},{edges[i + 1]:6.3f}) {bar} {counts[i]}")
    return lines


# --------------------------------------------------------------------------- #
# DEFECT-1 fix: antimode-gap detector + acceptance verdict.
# --------------------------------------------------------------------------- #
def has_antimode_gap(
    values: list[float],
    *,
    min_side_fraction: float = ANTIMODE_MIN_SIDE_FRACTION,
    gap_ratio: float = ANTIMODE_GAP_RATIO,
) -> bool:
    """True iff the sorted distribution contains an ANTIMODE / valley: a single
    neighbour gap that is large relative to the typical spacing AND that splits
    the sample into two non-trivial sides.

    BIN-FREE detector (no bin-alignment artifact). The data is sorted; the gap
    between each adjacent pair is compared against the *typical* neighbour
    spacing (median of the non-zero gaps). A gap >= ``gap_ratio`` x typical that
    leaves at least ``min_side_fraction`` of the mass on EACH side is a valley
    between two clusters -> reject.

    This is robust where adaptive binning failed: a real valley registers as one
    oversized neighbour gap regardless of where bin edges would have fallen. A
    lone far outlier does NOT qualify (its side holds < min_side_fraction); a
    wide-but-continuous unimodal spread does NOT qualify (no single gap dominates
    the typical spacing). Guarded: n < ANTIMODE_MIN_N or degenerate (all gaps
    zero) -> False (cannot assess)."""
    n = len(values)
    if n < ANTIMODE_MIN_N:
        return False
    s = sorted(values)
    gaps = [s[i + 1] - s[i] for i in range(n - 1)]
    nonzero = [g for g in gaps if g > 0]
    if not nonzero:
        return False
    typical = statistics.median(nonzero)  # typical neighbour spacing
    if typical <= 0:
        return False
    min_mass = n * min_side_fraction
    for i, g in enumerate(gaps):
        left = i + 1            # count of values at/left of this gap (s[0..i])
        right = n - left
        if left >= min_mass and right >= min_mass and g >= gap_ratio * typical:
            return True
    return False


def is_bucket_acceptable(
    values: list[float],
    constituent_medians: list[float],
    *,
    constituent_spread_threshold: float = CONSTITUENT_SPREAD_THRESHOLD,
) -> tuple[bool, list[str]]:
    """Acceptance verdict for a candidate sector-median bucket.

    REJECT (False) when either:
      - constituent_median_spread(constituent_medians) > threshold
        (multi-industry heterogeneity: a catch-all/group bucket mixing
        structurally different margin regimes), OR
      - has_antimode_gap(values) (multimodal distribution within the bucket).

    BC is intentionally NOT a hard reject (it under-detects) — it stays a
    separately-reported advisory metric. Raw width / IQR alone is NOT a reject
    reason: a wide-but-unimodal bucket passes. Returns (accept, reasons) where
    reasons name which rule(s) fired."""
    reasons: list[str] = []

    spread = constituent_median_spread(constituent_medians)
    if spread is not None and spread > constituent_spread_threshold:
        reasons.append(
            f"constituent-median-spread {spread:.4f} > {constituent_spread_threshold}"
        )

    if has_antimode_gap(values):
        reasons.append("antimode-gap (empty bin separating two populated clusters)")

    return (len(reasons) == 0, reasons)
