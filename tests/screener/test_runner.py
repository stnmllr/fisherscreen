from unittest.mock import MagicMock

from app.errors import DataSourceError
from app.screener.runner import run_basis_filter


def _make_yf_mock(info: dict) -> MagicMock:
    mock = MagicMock()
    mock.get_ticker_info.return_value = info
    return mock


_PASSING_INFO = {
    "shortName": "Big Corp",
    "currency": "USD",
    "marketCap": 500_000_000,
    "averageVolume": 200_000,
    "currentPrice": 50.0,
    "bid": 49.8,
    "ask": 50.2,
}


def test_run_returns_passing_records():
    mock_yf = _make_yf_mock(_PASSING_INFO)
    result = run_basis_filter(["BIGC"], mock_yf)

    assert len(result) == 1
    assert result[0].ticker == "BIGC"
    assert result[0].filter_passed_basis is True


def test_run_skips_tickers_with_data_source_errors():
    mock_yf = MagicMock()
    mock_yf.get_ticker_info.side_effect = DataSourceError("network error")

    result = run_basis_filter(["FAIL"], mock_yf)

    assert result == []


def test_run_processes_multiple_tickers():
    mock_yf = MagicMock()

    def side_effect(ticker):
        if ticker == "GOOD":
            return _PASSING_INFO
        return {**_PASSING_INFO, "currentPrice": 0.50}  # penny stock

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["GOOD", "PENY"], mock_yf)

    assert len(result) == 1
    assert result[0].ticker == "GOOD"


def test_run_returns_empty_for_empty_ticker_list():
    mock_yf = MagicMock()
    result = run_basis_filter([], mock_yf)
    assert result == []


def test_run_continues_after_individual_data_source_error():
    mock_yf = MagicMock()

    def side_effect(ticker):
        if ticker == "FAIL":
            raise DataSourceError("bad ticker")
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["FAIL", "GOOD"], mock_yf)

    assert len(result) == 1
    assert result[0].ticker == "GOOD"


def test_run_skips_ticker_with_malformed_yfinance_data():
    # yfinance can return strings where floats are expected — Pydantic raises ValidationError
    # The runner should treat this as a per-ticker failure, not crash the whole run
    mock_yf = MagicMock()

    def side_effect(ticker):
        if ticker == "MALFORMED":
            return {**_PASSING_INFO, "marketCap": "n/a"}
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["MALFORMED", "GOOD"], mock_yf)

    assert len(result) == 1
    assert result[0].ticker == "GOOD"
