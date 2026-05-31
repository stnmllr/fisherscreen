import math
from datetime import date

from app.deepdive.valuation_history import (
    REPORTING_LAG_DAYS,
    VALUATION_COMPLETE_MIN_DENSITY,
    VALUATION_COMPLETE_MIN_SPAN_YEARS,
    VALUATION_PARTIAL_MIN_OBS,
    _as_of_index,
    _cum_split_factor,
    _median_p25,
)


def test_constants_are_policy_values():
    assert VALUATION_COMPLETE_MIN_DENSITY == 40
    assert VALUATION_PARTIAL_MIN_OBS == 52
    assert REPORTING_LAG_DAYS == 90


def test_min_span_is_data_capped_value():
    # Task-0-Probe: freie yfinance = 4 GJ -> ~3,1J reale Tiefe -> 2.8 (Spec §5).
    assert VALUATION_COMPLETE_MIN_SPAN_YEARS == 2.8


def test_median_p25_hand_computed():
    # 1..9 inclusive: median=5, p25 (inclusive method) = 3.0
    med, p25 = _median_p25([5, 1, 9, 3, 7, 2, 8, 4, 6])
    assert med == 5.0
    assert math.isclose(p25, 3.0, abs_tol=1e-9)


def test_median_p25_empty_returns_none():
    assert _median_p25([]) == (None, None)


def test_median_p25_single_value():
    med, p25 = _median_p25([42.0])
    assert med == 42.0 and p25 == 42.0


def test_cum_split_factor_after_split():
    # 20:1 split ex-date 2022-07-18; a FY ending 2021-12-31 predates it
    splits = [(date(2022, 7, 18), 20.0)]
    assert _cum_split_factor(date(2021, 12, 31), splits) == 20.0
    # a FY ending 2023-12-31 is AFTER the split -> factor 1.0
    assert _cum_split_factor(date(2023, 12, 31), splits) == 1.0


def test_cum_split_factor_no_splits_is_one():
    assert _cum_split_factor(date(2021, 12, 31), []) == 1.0


def test_cum_split_factor_multiple_splits_multiply():
    splits = [(date(2022, 7, 18), 20.0), (date(2014, 4, 3), 2.0)]
    # FY end 2013-12-31 predates both -> 40.0
    assert _cum_split_factor(date(2013, 12, 31), splits) == 40.0


def test_as_of_index_respects_reporting_lag():
    # FY ends newest-first; lag 90d. A week at 2023-02-01 must NOT yet see the
    # FY ending 2022-12-31 (available only ~2023-03-31); it takes 2021-12-31.
    fy_ends = [date(2022, 12, 31), date(2021, 12, 31), date(2020, 12, 31)]
    idx = _as_of_index(date(2023, 2, 1), fy_ends)
    assert fy_ends[idx] == date(2021, 12, 31)
    # a week well after the lag sees the latest FY
    idx2 = _as_of_index(date(2023, 6, 1), fy_ends)
    assert fy_ends[idx2] == date(2022, 12, 31)


def test_as_of_index_none_before_any_available():
    fy_ends = [date(2022, 12, 31), date(2021, 12, 31)]
    # before even the oldest FY + lag
    assert _as_of_index(date(2021, 1, 1), fy_ends) is None
