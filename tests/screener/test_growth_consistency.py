from app.screener.growth_consistency import consistency_ratio, consistency_cap


def test_ratio_full_growth_four_years():
    # 4 revenues -> 3 transitions, all up -> ratio 1.0
    assert consistency_ratio([100.0, 110.0, 120.0, 130.0]) == 1.0


def test_ratio_one_spike_otherwise_flat_or_down():
    # 4 revenues, transitions: +,-,- -> down_years=2 -> (3-2)/3
    assert consistency_ratio([100.0, 200.0, 150.0, 120.0]) == 1.0 / 3.0


def test_ratio_unassessable_under_four_years_is_none():
    assert consistency_ratio([100.0, 130.0]) is None       # only 2 points
    assert consistency_ratio([]) is None


def test_consistency_cap_bands():
    assert consistency_cap(1.0) == 5
    assert consistency_cap(0.75) == 5
    assert consistency_cap(0.50) == 4
    assert consistency_cap(0.49) == 3
    assert consistency_cap(None) == 4   # UNASSESSABLE -> conservative ceiling
