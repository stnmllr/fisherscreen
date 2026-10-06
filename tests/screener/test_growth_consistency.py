import pytest

from app.screener.growth_consistency import (
    consistency_cap,
    consistency_ratio,
    median_annual_growth,
)


def test_ratio_full_growth_four_years():
    # 4 revenues -> 3 transitions, all up -> ratio 1.0
    assert consistency_ratio([100.0, 110.0, 120.0, 130.0]) == 1.0


def test_ratio_one_spike_otherwise_flat_or_down():
    # 4 revenues, transitions: +,-,- -> down_years=2 -> (3-2)/3
    assert consistency_ratio([100.0, 200.0, 150.0, 120.0]) == 1.0 / 3.0


def test_ratio_unassessable_under_four_years_is_none():
    assert consistency_ratio([100.0, 130.0]) is None  # only 2 points
    assert consistency_ratio([]) is None


def test_consistency_cap_bands():
    assert consistency_cap(1.0) == 5
    assert consistency_cap(0.75) == 5
    assert consistency_cap(0.50) == 4
    assert consistency_cap(0.49) == 3
    assert consistency_cap(None) == 4  # UNASSESSABLE -> conservative ceiling


# --- median annual revenue growth (growth-axis input) -------------------------


def test_median_four_years_takes_middle_of_three_rates():
    # rates: +10 %, +50 %, -20 % -> sorted -20/+10/+50 -> middle +10 %
    assert median_annual_growth([100.0, 110.0, 165.0, 132.0]) == pytest.approx(0.10)


def test_median_even_rate_count_is_mean_of_middle_two():
    # 5 GJ -> 4 rates: +10 %, +20 %, +30 %, +40 % -> (20 + 30) / 2
    series = [100.0, 110.0, 132.0, 171.6, 240.24]
    assert median_annual_growth(series) == pytest.approx(0.25)


def test_median_under_four_years_is_none():
    assert median_annual_growth([100.0, 110.0, 120.0]) is None
    assert median_annual_growth([100.0]) is None
    assert median_annual_growth([]) is None


def test_median_survives_a_first_year_definitional_break():
    # ADYEN.AS gross->net revenue switch: endpoint CAGR -33 %, median +19 %
    adyen = [8.94, 1.86, 2.23, 2.65]
    median = median_annual_growth(adyen)
    assert median is not None and median > 0
    # rates -79 %, +19.9 %, +18.8 % -> middle +18.8 %
    assert median == pytest.approx(2.65 / 2.23 - 1)
