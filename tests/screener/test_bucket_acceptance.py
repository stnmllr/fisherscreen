"""Unit tests for the shared bucket-acceptance module (Punkt 2, CT-B).

DEFECT 1 fix: the acceptance gate must reject single-industry multimodal buckets
that the bimodality coefficient under-detects. The discriminator is an
ANTIMODE / GAP — an empty histogram bin separating two populated regions — NOT
raw width. Wide-but-UNIMODAL buckets must still PASS ("weit ist erlaubt,
multimodal nicht").

Synthetic fixtures only (no real tickers; thresholds are not fitted to them).
"""
from __future__ import annotations

from app.screener.bucket_acceptance import (
    has_antimode_gap,
    is_bucket_acceptable,
)


# --- has_antimode_gap: real-case regression (acceptance spec) ---
# Reconstructed from the human review of actual GICS sector-median buckets.
# These are the acceptance spec, not outcome-tuning: 2 must reject, 2 must pass.

def test_antimode_gap_real_sbs_like_rejects():
    # "Specialized Business Services"-like: a low cluster (~0.11-0.25) and a
    # separate upper region (~0.46-0.75) with a clear valley between -> reject.
    vals = [0.11, 0.11, 0.14, 0.15, 0.25,
            0.46, 0.48, 0.49, 0.52, 0.55, 0.58, 0.62, 0.66, 0.70, 0.75]
    assert has_antimode_gap(vals) is True


def test_antimode_gap_real_travel_like_rejects():
    # "Travel Services"-like (n=9): a lone low point (0.083), a mid cluster
    # (~0.49-0.58) and an upper cluster (~0.82-0.90). The mid->upper jump is a
    # real valley separating two non-trivial sides -> reject. (Old sqrt(n)
    # binning aliased this boundary into a bin and MISSED it.)
    vals = [0.083, 0.49, 0.51, 0.53, 0.55, 0.58, 0.82, 0.86, 0.90]
    assert has_antimode_gap(vals) is True


def test_antimode_gap_real_chem_wide_unimodal_passes():
    # Chemicals-like: wide but continuous (neighbour spacings all comparable) ->
    # no valley -> PASS. Width alone is not a reject reason.
    vals = [0.14, 0.18, 0.20, 0.23, 0.25, 0.28, 0.30, 0.33, 0.33, 0.36, 0.40, 0.44, 0.50]
    assert has_antimode_gap(vals) is False


def test_antimode_gap_real_grocery_tight_passes():
    # Grocery-like (n=8): two low points then a tight cluster; no neighbour gap
    # reaches 4x the typical spacing with both sides non-trivial -> PASS.
    vals = [0.067, 0.076, 0.14, 0.18, 0.21, 0.24, 0.27, 0.29]
    assert has_antimode_gap(vals) is False


# --- has_antimode_gap ---

def test_antimode_gap_two_clusters_with_empty_separation():
    # Two tight clusters near 0.1 and 0.9 with nothing in between -> empty middle
    # bins, each side roughly half the mass -> antimode gap present.
    low = [0.10, 0.11, 0.12, 0.13, 0.14]
    high = [0.86, 0.87, 0.88, 0.89, 0.90]
    assert has_antimode_gap(low + high) is True


def test_antimode_gap_false_for_wide_continuous_unimodal():
    # Wide spread but continuous (every bin populated): no empty separating bin.
    vals = [0.10, 0.18, 0.27, 0.33, 0.41, 0.50, 0.58, 0.66, 0.74, 0.83, 0.90]
    assert has_antimode_gap(vals) is False


def test_antimode_gap_false_for_tight_cluster():
    vals = [0.40, 0.41, 0.42, 0.43, 0.44, 0.45, 0.46]
    assert has_antimode_gap(vals) is False


def test_antimode_gap_false_for_small_n():
    # n < 6 cannot be assessed -> always False.
    assert has_antimode_gap([0.1, 0.9, 0.1, 0.9, 0.1]) is False


def test_antimode_gap_false_for_all_equal_values():
    # Degenerate: all neighbour gaps are zero -> cannot assess -> False.
    assert has_antimode_gap([0.30] * 8) is False


def test_antimode_gap_false_for_single_left_edge_outlier():
    # A lone low outlier then a dense upper cluster: only ONE value sits on the
    # left side of the big gap (< 20% of the mass) -> not a non-trivial split.
    vals = [0.05] + [0.80, 0.81, 0.82, 0.83, 0.84, 0.85, 0.86, 0.87, 0.88]
    assert has_antimode_gap(vals) is False


def test_antimode_gap_false_when_one_side_below_min_fraction():
    # A single far outlier (one point on the far side) is NOT a cluster: the outlier
    # side holds < min_side_fraction of the mass -> no qualifying antimode gap.
    main = [0.40, 0.41, 0.42, 0.43, 0.44, 0.45, 0.46, 0.47, 0.48]
    outlier = [0.95]
    assert has_antimode_gap(main + outlier) is False


# --- is_bucket_acceptable ---

def test_acceptable_false_via_antimode_gap():
    low = [0.10, 0.11, 0.12, 0.13, 0.14]
    high = [0.86, 0.87, 0.88, 0.89, 0.90]
    values = low + high
    # single-industry: one constituent median, no spread
    accept, reasons = is_bucket_acceptable(values, [0.50])
    assert accept is False
    assert any("antimode" in r.lower() for r in reasons)


def test_acceptable_true_for_wide_continuous_unimodal():
    values = [0.10, 0.18, 0.27, 0.33, 0.41, 0.50, 0.58, 0.66, 0.74, 0.83, 0.90]
    accept, reasons = is_bucket_acceptable(values, [0.50])
    assert accept is True
    assert reasons == []


def test_acceptable_true_for_tight_cluster():
    values = [0.40, 0.41, 0.42, 0.43, 0.44, 0.45, 0.46]
    accept, reasons = is_bucket_acceptable(values, [0.43])
    assert accept is True
    assert reasons == []


def test_acceptable_false_via_constituent_spread_even_without_gap():
    # Continuous values (no antimode gap) but constituent medians span > 0.15
    # (multi-industry heterogeneity) -> reject via spread.
    values = [0.20, 0.28, 0.36, 0.44, 0.52, 0.60, 0.68, 0.76]
    constituent_medians = [0.22, 0.40, 0.74]  # spread 0.52 > 0.15
    accept, reasons = is_bucket_acceptable(values, constituent_medians)
    assert accept is False
    assert any("spread" in r.lower() for r in reasons)


def test_acceptable_small_n_no_gap_passes():
    # n < 6: antimode can't fire, single constituent -> no spread -> accept.
    values = [0.40, 0.42, 0.44, 0.46]
    accept, reasons = is_bucket_acceptable(values, [0.43])
    assert accept is True
    assert reasons == []
