"""Shared bucket-acceptance metrics + verdict for the Punkt-2 relative arm (CT-B).

Centralizes the pure dispersion/shape helpers (previously defined inline in
scripts/diagnose_bucket_dispersion.py) so the calibration instrument and any
future consumer share one implementation. Then adds the acceptance verdict: an
ABSOLUTE below-median gross-margin regime-gap detector.

Background: the harm a bucket can do is to pin a structurally LOW-margin
subpopulation against a median that describes a different (higher) margin regime.
A scale-RELATIVE shape statistic (gap/median, gap/IQR, gap/std, KDE-trough /
bandwidth) cannot rank the critical buckets correctly: a human proof showed every
relative normalization ranks them BACKWARDS — benign Grocery looks more anomalous
than harmful SBS — because the gap and the spread co-scale. The discriminating
signal is gross-margin PERCENTAGE POINTS (absolute): a low subpopulation >= 10pp
below the bucket median is a real cost-structure / regime break (contract-mfr vs
brand, commodity vs specialty); < 10pp is sampling noise. A gap ABOVE the median
is harmless (those low names ARE the median region) and never fires — this
protects continuous wide buckets (e.g. Aerospace & Defense): wide != bimodal.

Margin-awareness here falls ONLY for the acceptance test, not the bucketing (GICS
stays exogenous) -> no circularity. BC remains an advisory metric (reported, not a
hard reject).
"""
from __future__ import annotations

import statistics

# --- Transparent thresholds (NOT margin-/ticker-tuned). ---
CONSTITUENT_SPREAD_THRESHOLD = 0.15   # max-min of constituent-industry medians
BIMODALITY_THRESHOLD = 0.555          # Pearson/SAS bimodality coefficient cutoff (advisory only)
HIST_BINS = 10                        # bins for the ASCII histogram (display only)
_MIN_N_FOR_SHAPE = 6                  # below this, distribution shape cannot be assessed

# Absolute below-median regime-gap detector (the harm discriminator).
GROSS_MARGIN_REGIME_GAP = 0.10        # >=10 gross-margin percentage points below the median
                                      # = a real cost-structure / regime break (contract-mfr vs
                                      # brand, commodity vs specialty). <10pp = sampling noise.
BELOW_MEDIAN_MIN_FRACTION = 0.20      # the separated low subpopulation must be non-trivial


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
# Absolute below-median regime-gap detector + acceptance verdict.
# --------------------------------------------------------------------------- #
def has_below_median_regime_gap(
    values: list[float],
    *,
    gap_threshold: float = GROSS_MARGIN_REGIME_GAP,
    min_below_fraction: float = BELOW_MEDIAN_MIN_FRACTION,
) -> bool:
    """True iff there is a gross-margin gap >= gap_threshold that lies BELOW the bucket
    median (the gap's upper edge is at or below the median) with at least
    min_below_fraction of the mass below it. This is THE harm: a low subpopulation in a
    structurally different margin regime, measured against a median that describes the
    population ABOVE the gap. A gap ABOVE the median is harmless (the low names ARE the
    median region); that direction never fires (protects continuous wide buckets like
    Aerospace & Defense, median in the dense core)."""
    n = len(values)
    if n < _MIN_N_FOR_SHAPE:
        return False
    s = sorted(values)
    m = statistics.median(s)
    min_below = n * min_below_fraction
    for i in range(n - 1):
        if s[i + 1] > m:          # sorted: once the gap's upper edge exceeds the median,
            break                  # no later gap is "below the median" either
        left = i + 1               # values strictly below the gap (s[0..i])
        if left < min_below:
            continue
        if s[i + 1] - s[i] >= gap_threshold:
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
      - has_below_median_regime_gap(values) (a low subpopulation >= 10 gross-margin
        percentage points below the bucket median, with >= 20% of the mass below it:
        a structural margin-regime break pinned against the wrong median).

    BC is intentionally NOT a hard reject (it under-detects) — it stays a
    separately-reported advisory metric. Raw width / IQR alone is NOT a reject
    reason: a wide-but-unimodal bucket passes (wide != bimodal). Returns
    (accept, reasons) where reasons name which rule(s) fired."""
    reasons: list[str] = []

    spread = constituent_median_spread(constituent_medians)
    if spread is not None and spread > constituent_spread_threshold:
        reasons.append(
            f"constituent-median-spread {spread:.4f} > {constituent_spread_threshold}"
        )

    if has_below_median_regime_gap(values):
        reasons.append(
            f"below-median regime gap >= {GROSS_MARGIN_REGIME_GAP:.2f} with "
            f">= {BELOW_MEDIAN_MIN_FRACTION:.0%} mass below"
        )

    return (len(reasons) == 0, reasons)
