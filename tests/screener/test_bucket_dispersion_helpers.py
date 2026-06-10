"""Unit tests for the pure helpers extracted into the CT-B acceptance instrument
scripts/diagnose_bucket_dispersion.py. The live sweep is Stephan's calibration run;
only the math helpers are unit-tested here (no warm cache, no universe)."""
import importlib.util
import statistics
from pathlib import Path

import pytest

# Load the script module by path (it lives under scripts/, not an importable package).
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "diagnose_bucket_dispersion.py"
_spec = importlib.util.spec_from_file_location("diagnose_bucket_dispersion", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


# --- sample_skewness ---

def test_skewness_none_for_small_n():
    assert mod.sample_skewness([1.0, 2.0]) is None


def test_skewness_none_for_zero_variance():
    assert mod.sample_skewness([0.3, 0.3, 0.3, 0.3]) is None


def test_skewness_symmetric_is_near_zero():
    vals = [-2.0, -1.0, 0.0, 1.0, 2.0]
    s = mod.sample_skewness(vals)
    assert s is not None and abs(s) < 1e-9


def test_skewness_right_tail_is_positive():
    vals = [1.0, 1.0, 1.0, 1.0, 10.0]
    s = mod.sample_skewness(vals)
    assert s is not None and s > 0


# --- sample_kurtosis ---

def test_kurtosis_none_for_small_n():
    assert mod.sample_kurtosis([1.0, 2.0, 3.0]) is None


def test_kurtosis_none_for_zero_variance():
    assert mod.sample_kurtosis([0.5, 0.5, 0.5, 0.5]) is None


def test_kurtosis_two_point_is_one():
    # A symmetric two-mass distribution has non-excess kurtosis == 1.0 (hard floor).
    vals = [0.0, 0.0, 1.0, 1.0]
    k = mod.sample_kurtosis(vals)
    assert k is not None and abs(k - 1.0) < 1e-9


# --- bimodality_coefficient ---

def test_bc_none_when_moments_undefined():
    assert mod.bimodality_coefficient([1.0, 2.0]) is None


def test_bc_two_mass_distribution_exceeds_threshold():
    # Perfect two-mass split: BC -> (0 + 1) / 1 = 1.0 > 0.555 (bimodal).
    vals = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
    bc = mod.bimodality_coefficient(vals)
    assert bc is not None and bc > mod.BIMODALITY_THRESHOLD


def test_bc_matches_definition():
    vals = [0.1, 0.2, 0.2, 0.25, 0.3, 0.31, 0.4, 0.9]
    skew = mod.sample_skewness(vals)
    kurt = mod.sample_kurtosis(vals)
    expected = (skew ** 2 + 1) / kurt
    assert mod.bimodality_coefficient(vals) == pytest.approx(expected)


# --- constituent_median_spread ---

def test_spread_none_for_single_constituent():
    assert mod.constituent_median_spread([0.30]) is None


def test_spread_is_max_minus_min():
    # Railroads ~0.46 vs Marine ~0.24 -> spread 0.22 (> 0.15 threshold).
    spread = mod.constituent_median_spread([0.46, 0.24, 0.30])
    assert spread == pytest.approx(0.22)
    assert spread > mod.CONSTITUENT_SPREAD_THRESHOLD


# --- iqr / mad ---

def test_iqr_none_for_single_value():
    assert mod.iqr([0.3]) is None


def test_iqr_matches_quantiles():
    vals = [0.1, 0.2, 0.3, 0.4, 0.5]
    qs = statistics.quantiles(vals, n=4, method="exclusive")
    assert mod.iqr(vals) == pytest.approx(qs[2] - qs[0])


def test_mad_none_for_empty():
    assert mod.mad([]) is None


def test_mad_about_median():
    vals = [1.0, 2.0, 3.0, 4.0, 100.0]  # median 3 -> deviations [2,1,0,1,97] -> MAD 1
    assert mod.mad(vals) == pytest.approx(1.0)


# --- ascii_histogram ---

def test_histogram_empty():
    assert mod.ascii_histogram([]) == ["  (no values)"]


def test_histogram_constant_single_line():
    out = mod.ascii_histogram([0.3, 0.3, 0.3])
    assert len(out) == 1 and "0.300" in out[0]


def test_histogram_has_bins_lines_and_counts_all_values():
    vals = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    out = mod.ascii_histogram(vals, bins=10)
    assert len(out) == 10
    # the maximum value must be counted (top-edge guard), so total binned == len(vals)
    total = sum(int(line.rsplit(" ", 1)[1]) for line in out)
    assert total == len(vals)
