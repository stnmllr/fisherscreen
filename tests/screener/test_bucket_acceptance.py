"""Unit tests for the shared bucket-acceptance module (Punkt 2, CT-B).

The acceptance gate's harm-discriminator is an ABSOLUTE below-median gross-margin
regime gap, NOT a scale-relative shape statistic. A human proof showed every
scale-RELATIVE normalization (gap/median, gap/IQR, gap/std, KDE-trough/bandwidth)
ranks the two critical buckets BACKWARDS — benign Grocery looks more anomalous
than harmful SBS — because the gap and the spread co-scale. The discriminating
signal is gross-margin PERCENTAGE POINTS: a low subpopulation >= 10pp below the
bucket median is a real cost-structure / regime break (contract-mfr vs brand,
commodity vs specialty); < 10pp is sampling noise. A gap ABOVE the median is
harmless (the low names ARE the median region) and never fires.

Margin-awareness falls ONLY for the acceptance test, not the bucketing (GICS
stays exogenous) -> no circularity.

Synthetic fixtures only (no real tickers; thresholds are not fitted to them).
The shapes are labelled by the real bucket they abstract.
"""
from __future__ import annotations

from app.screener.bucket_acceptance import (
    has_below_median_regime_gap,
    is_bucket_acceptable,
)


# --- has_below_median_regime_gap: acceptance spec (abstract shapes) ---

def test_regime_gap_sbs_shape_rejects():
    # SBS-shape: a low cluster + a >=0.10 gap BELOW the median + an upper body.
    # gap 0.30->0.42 = 0.12, below median ~0.52, 5/13 = 38% below -> reject.
    vals = [0.11, 0.12, 0.13, 0.25, 0.30,
            0.42, 0.48, 0.52, 0.58, 0.62, 0.66, 0.70, 0.75]
    assert has_below_median_regime_gap(vals) is True


def test_regime_gap_computer_hardware_shape_rejects():
    # ComputerHardware-shape: gap 0.20->0.39 = 0.19 below median 0.43,
    # 3/9 = 33% below -> reject.
    vals = [0.084, 0.19, 0.20, 0.39, 0.43, 0.47, 0.52, 0.60, 0.70]
    assert has_below_median_regime_gap(vals) is True


def test_regime_gap_aero_defense_shape_accepts():
    # A&D-shape: continuous, dense core, thin right tail. NO >=0.10 gap below the
    # median; the only larger gaps are ABOVE the median in the tail. Wide != bimodal
    # (Correction 1) -> must stay accepted.
    vals = [0.05, 0.10, 0.13, 0.15, 0.18, 0.20, 0.22, 0.24, 0.26, 0.30, 0.34, 0.40, 0.48, 0.60]
    assert has_below_median_regime_gap(vals) is False


def test_regime_gap_grocery_shape_accepts():
    # Grocery-shape: largest sub-median gap 0.064 < 0.10 -> noise -> accept.
    vals = [0.067, 0.076, 0.14, 0.18, 0.21, 0.24, 0.27, 0.29]
    assert has_below_median_regime_gap(vals) is False


def test_regime_gap_airlines_shape_accepts():
    # Airlines-shape: the >=0.10 gap (0.23->0.33) is ABOVE the median ~0.225 ->
    # never fires above the median -> accept.
    vals = [0.19, 0.20, 0.21, 0.22, 0.23, 0.33, 0.36, 0.39]
    assert has_below_median_regime_gap(vals) is False


def test_regime_gap_single_low_outlier_accepts():
    # A big gap below the median (0.08->0.50 = 0.42) but only 1/8 = 12.5% mass below
    # it (< 20%) -> a lone outlier is not a subpopulation -> accept.
    vals = [0.08, 0.50, 0.52, 0.54, 0.56, 0.58, 0.60, 0.62]
    assert has_below_median_regime_gap(vals) is False


def test_regime_gap_false_for_small_n():
    # n < 6 cannot be assessed -> always False.
    assert has_below_median_regime_gap([0.10, 0.11, 0.50, 0.60, 0.61]) is False


def test_regime_gap_false_for_all_equal_values():
    # Degenerate: no gap at all -> False.
    assert has_below_median_regime_gap([0.30] * 8) is False


def test_regime_gap_gap_exactly_at_threshold_rejects():
    # gap exactly 0.10 below the median with >= 20% mass below -> reject (>=).
    # low cluster 0.10,0.12,0.15 then 0.25 (gap 0.15->0.25 = 0.10), median ~0.40.
    vals = [0.10, 0.12, 0.15, 0.25, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
    assert has_below_median_regime_gap(vals) is True


# --- is_bucket_acceptable ---

def test_acceptable_false_via_regime_gap():
    values = [0.11, 0.12, 0.13, 0.25, 0.30,
              0.42, 0.48, 0.52, 0.58, 0.62, 0.66, 0.70, 0.75]
    # single-industry: one constituent median, no spread
    accept, reasons = is_bucket_acceptable(values, [0.52])
    assert accept is False
    assert any("regime gap" in r.lower() for r in reasons)


def test_acceptable_true_for_continuous_dense_core():
    values = [0.05, 0.10, 0.13, 0.15, 0.18, 0.20, 0.22, 0.24, 0.26, 0.30, 0.34, 0.40, 0.48, 0.60]
    accept, reasons = is_bucket_acceptable(values, [0.23])
    assert accept is True
    assert reasons == []


def test_acceptable_true_for_grocery_shape():
    values = [0.067, 0.076, 0.14, 0.18, 0.21, 0.24, 0.27, 0.29]
    accept, reasons = is_bucket_acceptable(values, [0.20])
    assert accept is True
    assert reasons == []


def test_acceptable_false_via_constituent_spread_even_without_gap():
    # Continuous values (no regime gap) but constituent medians span > 0.15
    # (multi-industry heterogeneity) -> reject via spread.
    values = [0.20, 0.28, 0.36, 0.44, 0.52, 0.60, 0.68, 0.76]
    constituent_medians = [0.22, 0.40, 0.74]  # spread 0.52 > 0.15
    accept, reasons = is_bucket_acceptable(values, constituent_medians)
    assert accept is False
    assert any("spread" in r.lower() for r in reasons)


def test_acceptable_small_n_no_gap_passes():
    # n < 6: regime gap can't fire, single constituent -> no spread -> accept.
    values = [0.40, 0.42, 0.44, 0.46]
    accept, reasons = is_bucket_acceptable(values, [0.43])
    assert accept is True
    assert reasons == []
