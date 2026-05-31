import math
from datetime import date

from app.deepdive.valuation_history import (
    REPORTING_LAG_DAYS,
    VALUATION_COMPLETE_MIN_DENSITY,
    VALUATION_COMPLETE_MIN_SPAN_YEARS,
    VALUATION_PARTIAL_MIN_OBS,
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
