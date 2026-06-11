from app.models.definedness import DefinednessOutcome
from app.screener.revenue_trajectory import classify_revenue_trajectory, is_gamma_decline


def test_genuine_multiyear_decline_is_defined():
    cagr, dy, defn = classify_revenue_trajectory([100.0, 90.0, 80.0, 70.0])
    assert defn is DefinednessOutcome.DEFINED
    assert cagr < 0
    assert dy == 3
    assert is_gamma_decline(cagr, dy) is True


def test_positive_cagr_choppy_is_not_gamma():
    cagr, dy, defn = classify_revenue_trajectory([100.0, 95.0, 105.0, 102.0])
    assert defn is DefinednessOutcome.DEFINED
    assert cagr > 0
    assert dy == 2
    assert is_gamma_decline(cagr, dy) is False


def test_negative_cagr_single_down_year_is_not_gamma():
    cagr, dy, defn = classify_revenue_trajectory([100.0, 70.0, 72.0, 74.0])
    assert cagr < 0
    assert dy == 1
    assert is_gamma_decline(cagr, dy) is False


def test_short_history_is_unassessable():
    cagr, dy, defn = classify_revenue_trajectory([100.0, 90.0, 80.0])
    assert defn is DefinednessOutcome.UNASSESSABLE


def test_too_few_points_unassessable():
    cagr, dy, defn = classify_revenue_trajectory([100.0])
    assert defn is DefinednessOutcome.UNASSESSABLE
    assert cagr is None and dy is None


def test_empty_unassessable():
    cagr, dy, defn = classify_revenue_trajectory([])
    assert defn is DefinednessOutcome.UNASSESSABLE


def test_is_gamma_decline_none_inputs_false():
    assert is_gamma_decline(None, None) is False
    assert is_gamma_decline(-0.1, None) is False
    assert is_gamma_decline(None, 3) is False


def test_gamma_true_at_dy2_negative_cagr_boundary():
    # the exact gamma lower edge: CAGR<0 AND dy==2 -> drop
    cagr, dy, defn = classify_revenue_trajectory([100.0, 80.0, 85.0, 75.0])
    assert defn is DefinednessOutcome.DEFINED
    assert cagr < 0
    assert dy == 2
    assert is_gamma_decline(cagr, dy) is True


def test_flat_year_not_counted_as_down():
    # g == 0 is NOT a down year -> [100,100,90,80] has dy==2 (the two declines), not 3
    cagr, dy, defn = classify_revenue_trajectory([100.0, 100.0, 90.0, 80.0])
    assert dy == 2


def test_three_points_compute_values_but_unassessable():
    # 2..3 points: cagr/down_years are computed for audit, definedness still UNASSESSABLE
    cagr, dy, defn = classify_revenue_trajectory([100.0, 90.0, 80.0])
    assert defn is DefinednessOutcome.UNASSESSABLE
    assert cagr is not None
    assert dy == 2
