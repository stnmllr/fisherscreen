import math

from app.deepdive.trend_metrics import (
    compute_buyback_intensity,
    compute_cagr,
    compute_dilution_pct,
    compute_margin_slope,
)


def test_cagr_basic_newest_first():
    # newest-first: [1464.1, 1000] over span 1 -> ~46.41%
    assert math.isclose(compute_cagr([1464.1, 1000.0]), 0.4641, abs_tol=1e-4)


def test_cagr_five_years():
    # 1000 -> 2000 over 4 year-steps
    assert math.isclose(compute_cagr([2000, 1500, 1300, 1100, 1000]),
                         2 ** (1 / 4) - 1, abs_tol=1e-6)


def test_cagr_none_when_insufficient_or_nonpositive():
    assert compute_cagr([100]) is None
    assert compute_cagr([]) is None
    assert compute_cagr([100, 0]) is None
    assert compute_cagr([100, None]) is None


def test_margin_slope_positive_trend_newest_first():
    # improving margins newest-first [0.5,0.4,0.3] -> positive slope per year
    s = compute_margin_slope([0.5, 0.4, 0.3])
    assert s is not None and s > 0


def test_margin_slope_none_when_too_few_points():
    assert compute_margin_slope([0.5]) is None
    assert compute_margin_slope([0.5, None]) is None


def test_dilution_pct_newest_vs_oldest():
    # shares grew 100 -> 110 (oldest->newest) = +10%
    assert math.isclose(compute_dilution_pct([110, 105, 100]), 0.10, abs_tol=1e-9)


def test_dilution_negative_means_buybacks():
    assert compute_dilution_pct([90, 95, 100]) < 0


def test_dilution_none_on_bad_input():
    assert compute_dilution_pct([100]) is None
    assert compute_dilution_pct([0, 100]) is None


def test_buyback_intensity_sum_over_marketcap():
    # cashflow repurchase entries are negative; intensity = |sum| / mcap
    assert math.isclose(
        compute_buyback_intensity([-50, -50, -50], market_cap=1000),
        150 / 1000, abs_tol=1e-9)


def test_buyback_intensity_none_when_no_mcap():
    assert compute_buyback_intensity([-50], market_cap=None) is None
    assert compute_buyback_intensity([], market_cap=1000) is None


def test_cagr_none_on_nan():
    assert compute_cagr([float("nan"), 100.0]) is None
