import logging
from unittest.mock import MagicMock

import pytest

from app.deepdive.quant_join import (
    _latest_non_none,
    _norm_dividend_yield,
    _resolve_dividend_yield,
    build_quant_snapshot,
)
from app.errors import DataSourceError
from app.models.deep_dive_record import (
    ForwardEstimates,
    MultipleStats,
    ValuationHistory,
)


def _deps(pit_cache=None, dims=None):
    firestore = MagicMock()
    firestore.get.side_effect = lambda coll, doc: (
        pit_cache if coll == "dev_ticker_cache" else dims
    )
    yfinance = MagicMock()
    yfinance.get_forward_estimates.return_value = ForwardEstimates()
    yfinance.get_ticker_info.return_value = {
        "shortName": "Novo", "currency": "DKK", "marketCap": 3e11,
        "sector": "Healthcare", "grossMargins": 0.84}
    historical = MagicMock()
    historical.get_annual_series.return_value = {
        "financial_currency": "DKK", "years": [2024, 2023, 2022, 2021, 2020],
        "revenue": [5, 4, 3, 2, 1], "gross_margin": [0.84] * 5,
        "operating_margin": [0.45, 0.44, 0.43, 0.42, 0.41],
        "shares_outstanding": [100, 101, 102, 103, 104],
        "buyback_cashflow": [-10] * 5,
        "ebit": [50, 45, 40, 35, 30],
        "interest_expense": [-3, -3, -3, -3, -3],
        "complete": True,
        "valuation_history": ValuationHistory(
            pe=MultipleStats(median=21.4, p25=12.1, n_obs=164,
                             span_years=3.1, status="complete"))}
    return firestore, yfinance, historical


def test_pit_from_cache_when_present():
    fs, yf, hist = _deps(pit_cache={"shortName": "Novo Cached",
                                    "marketCap": 2.9e11, "currency": "DKK"},
                          dims={"dimensions": {"growth": 5}, "summary": "s"})
    qs, cov = build_quant_snapshot(
        "NOVO-B.CO", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.point_in_time.name == "Novo Cached"
    assert cov.quant_pit_source == "tool-a-cache"
    yf.get_ticker_info.assert_not_called()
    assert qs.gemini_dimensions == {"growth": 5}
    assert cov.gemini_dims == "present"


def test_pit_live_fallback_when_cache_miss():
    fs, yf, hist = _deps(pit_cache=None, dims=None)
    qs, cov = build_quant_snapshot(
        "NOVO-B.CO", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.point_in_time.name == "Novo"
    assert cov.quant_pit_source == "live-yfinance"
    assert qs.gemini_dimensions is None
    assert "nicht im letzten Monatslauf" in cov.gemini_dims


def test_trend_metrics_computed():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1000}, dims=None)
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.trend_metrics is not None
    assert qs.trend_metrics.revenue_cagr_5y is not None
    assert qs.trend_metrics.dilution_pct_5y < 0  # shares shrank 104->100


def test_currency_note_when_financial_currency_differs():
    fs, yf, hist = _deps(pit_cache={"currency": "USD", "marketCap": 1},
                          dims=None)
    qs, cov = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert cov.currency_note is not None
    assert "DKK" in cov.currency_note and "USD" in cov.currency_note


def test_partial_historical_flagged():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    hist.get_annual_series.return_value = {
        "financial_currency": "DKK", "years": [2024, 2023], "revenue": [2, 1],
        "gross_margin": [0.8, 0.8], "operating_margin": [0.4, 0.4],
        "shares_outstanding": [9, 9], "buyback_cashflow": [0, 0],
        "complete": False}
    _, cov = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert cov.historical.startswith("partial")


def test_norm_dividend_yield_branches():
    assert _norm_dividend_yield(None) is None
    assert _norm_dividend_yield(0.024) == 0.024  # already a fraction
    assert _norm_dividend_yield(2.4) == 0.024    # percent -> fraction
    assert _norm_dividend_yield(1.0) == 1.0      # boundary: not > 1


def test_resolve_dividend_yield_googl_class_glitch_corrected():
    # real GOOGL .info: payout/PE implies ~0.22%; magnitude-norm 0.23 is
    # ~100x too big (yfinance percent-units glitch) -> /100
    assert _resolve_dividend_yield(0.23, 0.0641, 28.99) == pytest.approx(
        0.0023, abs=1e-5)


def test_resolve_dividend_yield_msft_class_glitch_corrected():
    # MSFT same sub-1% class: 0.81 percent-units -> 0.0081 fraction
    assert _resolve_dividend_yield(0.81, 0.25, 28.0) == pytest.approx(
        0.0081, abs=1e-5)


def test_resolve_dividend_yield_ko_no_double_correction():
    # KO raw 2.68 > 1 -> magnitude already /100 = 0.0268; cross-check agrees
    # (ratio ~1) -> guard MUST stay silent, no second /100
    assert _resolve_dividend_yield(2.68, 0.70, 26.0) == pytest.approx(
        0.0268, abs=1e-4)


def test_resolve_dividend_yield_legit_fraction_regime_untouched():
    # old fraction regime: implied 0.025, ratio < 10 -> kept untouched
    assert _resolve_dividend_yield(0.024, 0.30, 12.0) == pytest.approx(
        0.024, abs=1e-4)


def test_resolve_dividend_yield_fallback_ge1_passes_through():
    # no usable cross-check, raw >= 1 -> magnitude-normalized passthrough
    assert _resolve_dividend_yield(2.4, None, None) == pytest.approx(0.024)
    # payout <= 0 -> no cross-check, raw >= 1 passthrough
    assert _resolve_dividend_yield(2.4, 0.0, 30.0) == pytest.approx(0.024)


def test_resolve_dividend_yield_fallback_sub1_no_crosscheck_is_na():
    # 0 < raw < 1 without a usable 2nd signal is not disambiguable -> None
    assert _resolve_dividend_yield(0.23, None, None) is None
    assert _resolve_dividend_yield(0.5, 0.3, None) is None    # PE missing
    assert _resolve_dividend_yield(0.23, 0.5, -10.0) is None  # PE<=0 unusable
    assert _resolve_dividend_yield(0.23, 0.0, 30.0) is None   # payout<=0


def test_resolve_dividend_yield_zero_and_none_unambiguous():
    # raw == 0 -> genuine non-payer, unambiguous (NOT n/a)
    assert _resolve_dividend_yield(0.0, None, None) == 0.0
    # raw is None -> None
    assert _resolve_dividend_yield(None, None, None) is None


def test_latest_non_none_helper():
    assert _latest_non_none([None, None, 7, 5]) == 7
    assert _latest_non_none([3, 2, 1]) == 3
    assert _latest_non_none([None, None]) is None
    assert _latest_non_none([]) is None


def test_new_valuation_info_fields_mapped_onto_pit():
    fs, yf, hist = _deps(pit_cache=None, dims=None)
    yf.get_ticker_info.return_value = {
        "shortName": "Novo", "currency": "DKK", "marketCap": 3e11,
        "trailingPE": 30.0, "forwardPE": 25.0, "enterpriseValue": 3.2e11,
        "freeCashflow": 1e10, "totalDebt": 2e9, "totalCash": 5e9,
        "currentRatio": 1.5, "payoutRatio": 0.4, "dividendYield": 2.4}
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    pit = qs.point_in_time
    assert pit.trailing_pe == 30.0
    assert pit.forward_pe == 25.0
    assert pit.enterprise_value == 3.2e11
    assert pit.free_cashflow == 1e10
    assert pit.total_debt == 2e9
    assert pit.total_cash == 5e9
    assert pit.current_ratio == 1.5
    assert pit.payout_ratio == 0.4
    assert pit.dividend_yield == 0.024  # 2.4 normalized to fraction


def test_ebit_interest_expense_from_historical_latest_non_none():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.point_in_time.ebit == 50            # newest-first first non-None
    assert qs.point_in_time.interest_expense == -3


def test_ebit_interest_expense_none_when_historical_lacks_them():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    hist.get_annual_series.return_value = {
        "financial_currency": "DKK", "years": [2024, 2023], "revenue": [2, 1],
        "gross_margin": [0.8, 0.8], "operating_margin": [0.4, 0.4],
        "shares_outstanding": [9, 9], "buyback_cashflow": [0, 0],
        "ebit": [None, None], "complete": False}
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.point_in_time.ebit is None
    assert qs.point_in_time.interest_expense is None


def test_consensus_info_fields_mapped_onto_pit():
    fs, yf, hist = _deps(pit_cache=None, dims=None)
    yf.get_ticker_info.return_value = {
        "shortName": "Novo", "currency": "DKK", "marketCap": 3e11,
        "recommendationKey": "buy", "recommendationMean": 1.8,
        "targetMeanPrice": 111.0, "targetMedianPrice": 110.0,
        "targetLowPrice": 90.0, "targetHighPrice": 140.0,
        "numberOfAnalystOpinions": 42}
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    pit = qs.point_in_time
    assert pit.recommendation_key == "buy"
    assert pit.recommendation_mean == 1.8
    assert pit.target_mean_price == 111.0
    assert pit.target_median_price == 110.0
    assert pit.target_low_price == 90.0
    assert pit.target_high_price == 140.0
    assert pit.number_of_analyst_opinions == 42


def test_consensus_fields_default_none_when_absent_from_info():
    fs, yf, hist = _deps(pit_cache=None, dims=None)
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    pit = qs.point_in_time
    assert pit.recommendation_key is None
    assert pit.target_mean_price is None
    assert pit.number_of_analyst_opinions is None


def test_forward_estimates_wired_onto_snapshot():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    fe = ForwardEstimates(
        revenue_growth_cy=0.1485, eps_growth_cy=0.1714)
    yf.get_forward_estimates.return_value = fe
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    yf.get_forward_estimates.assert_called_once_with("X")
    assert qs.forward_estimates is fe


def test_forward_estimates_failsoft_on_data_source_error(caplog):
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    yf.get_forward_estimates.side_effect = DataSourceError("boom")
    with caplog.at_level(logging.WARNING, logger="app.deepdive.quant_join"):
        qs, _ = build_quant_snapshot(
            "X", firestore=fs, yfinance=yf, historical=hist,
            pit_collection="dev_ticker_cache",
            dims_collection="dev_gemini_scores")
    assert qs.forward_estimates is None
    assert "forward estimates" in caplog.text.lower()
    # deep dive continues: snapshot still fully built
    assert qs.point_in_time.ticker == "X"


def test_forward_estimates_none_when_client_returns_none():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    yf.get_forward_estimates.return_value = None
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.forward_estimates is None


def test_use_cache_false_threads_to_historical():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores",
        use_cache=False)
    hist.get_annual_series.assert_called_once_with("X", use_cache=False)


def test_valuation_history_wired_onto_snapshot():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.valuation_history is not None
    assert qs.valuation_history.pe.median == 21.4
    assert qs.valuation_history.pe.status == "complete"


def test_valuation_history_none_when_absent_from_series():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    series = dict(hist.get_annual_series.return_value)
    del series["valuation_history"]
    hist.get_annual_series.return_value = series
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.valuation_history is None
