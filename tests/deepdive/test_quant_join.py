from unittest.mock import MagicMock

from app.deepdive.quant_join import build_quant_snapshot


def _deps(pit_cache=None, dims=None):
    firestore = MagicMock()
    firestore.get.side_effect = lambda coll, doc: (
        pit_cache if coll == "dev_ticker_cache" else dims
    )
    yfinance = MagicMock()
    yfinance.get_ticker_info.return_value = {
        "shortName": "Novo", "currency": "DKK", "marketCap": 3e11,
        "sector": "Healthcare", "grossMargins": 0.84}
    historical = MagicMock()
    historical.get_annual_series.return_value = {
        "financial_currency": "DKK", "years": [2024, 2023, 2022, 2021, 2020],
        "revenue": [5, 4, 3, 2, 1], "gross_margin": [0.84] * 5,
        "operating_margin": [0.45, 0.44, 0.43, 0.42, 0.41],
        "shares_outstanding": [100, 101, 102, 103, 104],
        "buyback_cashflow": [-10] * 5, "complete": True}
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


def test_use_cache_false_threads_to_historical():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores",
        use_cache=False)
    hist.get_annual_series.assert_called_once_with("X", use_cache=False)
