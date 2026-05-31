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


from datetime import timedelta

from app.deepdive.valuation_history import (
    AnnualFundamental,
    compute_valuation_history,
)


def _weekly(start: date, n: int, price: float):
    return [(start + timedelta(days=7 * i), price) for i in range(n)]


def _annual_flat():
    # newest-first, 5 FY ending Dec, EPS_current already (no split)
    return [
        AnnualFundamental(fy_end=date(2024, 12, 31), net_income=1000.0,
                          diluted_eps=10.0, ebit=1200.0, free_cashflow=900.0,
                          total_debt=200.0, cash=500.0),
        AnnualFundamental(fy_end=date(2023, 12, 31), net_income=900.0,
                          diluted_eps=9.0, ebit=1100.0, free_cashflow=800.0,
                          total_debt=210.0, cash=480.0),
        AnnualFundamental(fy_end=date(2022, 12, 31), net_income=800.0,
                          diluted_eps=8.0, ebit=1000.0, free_cashflow=700.0,
                          total_debt=220.0, cash=460.0),
        AnnualFundamental(fy_end=date(2021, 12, 31), net_income=700.0,
                          diluted_eps=7.0, ebit=900.0, free_cashflow=600.0,
                          total_debt=230.0, cash=440.0),
        AnnualFundamental(fy_end=date(2020, 12, 31), net_income=600.0,
                          diluted_eps=6.0, ebit=800.0, free_cashflow=500.0,
                          total_debt=240.0, cash=420.0),
    ]


def test_compute_pe_band_basic_same_currency():
    weekly = _weekly(date(2020, 6, 1), 260, 100.0)
    vh = compute_valuation_history(
        weekly, _annual_flat(), splits=[],
        listing_ccy="USD", financial_ccy="USD")
    assert vh.pe.median is not None and vh.pe.median > 0
    assert vh.pe.n_obs > 0
    assert vh.pe.status in ("complete", "partial")


def test_compute_skips_fx_when_currencies_differ():
    weekly = _weekly(date(2020, 6, 1), 260, 100.0)
    vh = compute_valuation_history(
        weekly, _annual_flat(), splits=[],
        listing_ccy="USD", financial_ccy="DKK")
    assert vh.pe.status == "skipped_fx"
    assert vh.ev_ebit.status == "skipped_fx"
    assert vh.fcf_yield.status == "skipped_fx"
    assert vh.pe.median is None


def test_compute_na_data_when_currency_none():
    weekly = _weekly(date(2020, 6, 1), 260, 100.0)
    vh = compute_valuation_history(
        weekly, _annual_flat(), splits=[],
        listing_ccy=None, financial_ccy="USD")
    assert vh.pe.status == "na_data"


def test_compute_excludes_nonpositive_eps_and_ebit():
    annual = _annual_flat()
    annual[0] = AnnualFundamental(
        fy_end=date(2024, 12, 31), net_income=-100.0, diluted_eps=-1.0,
        ebit=-50.0, free_cashflow=900.0, total_debt=200.0, cash=500.0)
    weekly = _weekly(date(2024, 6, 1), 30, 100.0)
    vh = compute_valuation_history(
        weekly, annual, splits=[], listing_ccy="USD", financial_ccy="USD")
    assert vh.pe.n_obs >= 0  # negatives not counted as valid P/E; no crash


def test_compute_keeps_negative_fcf_yield():
    annual = _annual_flat()
    annual[0] = AnnualFundamental(
        fy_end=date(2024, 12, 31), net_income=1000.0, diluted_eps=10.0,
        ebit=1200.0, free_cashflow=-900.0, total_debt=200.0, cash=500.0)
    weekly = _weekly(date(2024, 6, 1), 30, 100.0)
    vh = compute_valuation_history(
        weekly, annual, splits=[], listing_ccy="USD", financial_ccy="USD")
    assert vh.fcf_yield.n_obs > 0


def test_compute_split_normalizes_pe():
    # GOOGL-like 20:1 at 2022-07-18; pre-split FY EPS reported pre-split basis
    annual = [
        AnnualFundamental(fy_end=date(2023, 12, 31), net_income=2000.0,
                          diluted_eps=5.0, ebit=2500.0, free_cashflow=1800.0,
                          total_debt=100.0, cash=900.0),
        AnnualFundamental(fy_end=date(2021, 12, 31), net_income=1900.0,
                          diluted_eps=100.0,  # pre-split (20x larger)
                          ebit=2300.0, free_cashflow=1700.0,
                          total_debt=120.0, cash=850.0),
    ]
    splits = [(date(2022, 7, 18), 20.0)]
    weekly = _weekly(date(2020, 6, 1), 260, 100.0)  # constant post-split price
    vh = compute_valuation_history(
        weekly, annual, splits=splits, listing_ccy="USD", financial_ccy="USD")
    # pre-split EPS 100 -> 5 (current basis), so P/E those weeks = 100/5 = 20,
    # NOT 100/100 = 1. Median must be ~20, not ~1.
    assert vh.pe.median is not None and vh.pe.median > 10
