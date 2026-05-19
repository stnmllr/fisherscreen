from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.errors import DataSourceError
from app.models.deep_dive_record import ForwardEstimates
from app.services.yfinance_client import YFinanceClientImpl


def _estimate_frame(growth_by_period):
    """Build a yfinance-shaped estimate DataFrame (index='period')."""
    rows = {
        p: {"avg": 1.0, "low": 0.5, "high": 1.5, "numberOfAnalysts": 10,
            "growth": g, "currency": "USD"}
        for p, g in growth_by_period.items()
    }
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "period"
    return df


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_returns_info_dict(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = {"shortName": "Apple Inc.", "marketCap": 3_000_000_000_000}
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()
    result = client.get_ticker_info("AAPL")

    mock_yf.Ticker.assert_called_once_with("AAPL")
    assert result["shortName"] == "Apple Inc."
    assert result["marketCap"] == 3_000_000_000_000


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_raises_data_source_error_on_empty(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = {}
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()

    with pytest.raises(DataSourceError, match="empty info"):
        client.get_ticker_info("BADTICKER")


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_raises_data_source_error_on_exception(mock_yf):
    mock_yf.Ticker.side_effect = Exception("network error")

    client = YFinanceClientImpl()

    with pytest.raises(DataSourceError, match="yfinance failed"):
        client.get_ticker_info("AAPL")


@patch("app.services.yfinance_client.yf")
def test_get_historical_returns_dataframe(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame({"Close": [100.0, 101.0]})
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()
    result = client.get_historical("AAPL", "1mo")

    mock_ticker.history.assert_called_once_with(period="1mo")
    assert len(result) == 2


@patch("app.services.yfinance_client.yf")
def test_get_historical_raises_data_source_error_on_exception(mock_yf):
    mock_yf.Ticker.side_effect = Exception("network error")

    client = YFinanceClientImpl()

    with pytest.raises(DataSourceError, match="yfinance history failed"):
        client.get_historical("AAPL", "1mo")


@patch("app.services.yfinance_client.yf")
def test_get_financials_returns_dataframe(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.financials = pd.DataFrame({"Revenue": [394_000_000_000]})
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()
    result = client.get_financials("AAPL")

    assert len(result) == 1


@patch("app.services.yfinance_client.yf")
def test_get_financials_raises_data_source_error_on_exception(mock_yf):
    mock_yf.Ticker.side_effect = Exception("network error")

    client = YFinanceClientImpl()

    with pytest.raises(DataSourceError, match="yfinance financials failed"):
        client.get_financials("AAPL")


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_parses_growth_for_cy_and_ny(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.earnings_estimate = _estimate_frame(
        {"0q": 0.20, "+1q": 0.08, "0y": 0.1714, "+1y": 0.1023})
    mock_ticker.revenue_estimate = _estimate_frame(
        {"0q": 0.15, "+1q": 0.11, "0y": 0.1485, "+1y": 0.0809})
    mock_yf.Ticker.return_value = mock_ticker

    fe = YFinanceClientImpl().get_forward_estimates("AAPL")

    assert isinstance(fe, ForwardEstimates)
    assert fe.eps_growth_cy == 0.1714
    assert fe.eps_growth_ny == 0.1023
    assert fe.revenue_growth_cy == 0.1485
    assert fe.revenue_growth_ny == 0.0809


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_missing_index_yields_none_fields(mock_yf):
    mock_ticker = MagicMock()
    # only 0y present for EPS, revenue frame missing +1y
    mock_ticker.earnings_estimate = _estimate_frame({"0y": 0.17})
    mock_ticker.revenue_estimate = _estimate_frame({"0y": 0.14, "0q": 0.1})
    mock_yf.Ticker.return_value = mock_ticker

    fe = YFinanceClientImpl().get_forward_estimates("AAPL")

    assert fe.eps_growth_cy == 0.17
    assert fe.eps_growth_ny is None
    assert fe.revenue_growth_cy == 0.14
    assert fe.revenue_growth_ny is None


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_missing_growth_column_yields_none(mock_yf):
    mock_ticker = MagicMock()
    df = pd.DataFrame.from_dict(
        {"0y": {"avg": 1.0}, "+1y": {"avg": 2.0}}, orient="index")
    df.index.name = "period"
    mock_ticker.earnings_estimate = df
    mock_ticker.revenue_estimate = df
    mock_yf.Ticker.return_value = mock_ticker

    fe = YFinanceClientImpl().get_forward_estimates("AAPL")

    assert fe.eps_growth_cy is None
    assert fe.revenue_growth_ny is None


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_nan_growth_yields_none(mock_yf):
    import numpy as np
    mock_ticker = MagicMock()
    mock_ticker.earnings_estimate = _estimate_frame(
        {"0y": np.nan, "+1y": 0.10})
    mock_ticker.revenue_estimate = _estimate_frame(
        {"0y": 0.14, "+1y": np.nan})
    mock_yf.Ticker.return_value = mock_ticker

    fe = YFinanceClientImpl().get_forward_estimates("AAPL")

    assert fe.eps_growth_cy is None
    assert fe.eps_growth_ny == 0.10
    assert fe.revenue_growth_cy == 0.14
    assert fe.revenue_growth_ny is None


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_none_frames_yield_all_none(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.earnings_estimate = None
    mock_ticker.revenue_estimate = None
    mock_yf.Ticker.return_value = mock_ticker

    fe = YFinanceClientImpl().get_forward_estimates("AAPL")

    assert isinstance(fe, ForwardEstimates)
    assert fe.eps_growth_cy is None and fe.eps_growth_ny is None
    assert fe.revenue_growth_cy is None and fe.revenue_growth_ny is None


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_hard_failure_raises_data_source_error(mock_yf):
    mock_yf.Ticker.side_effect = Exception("network error")

    with pytest.raises(DataSourceError, match="forward estimates failed"):
        YFinanceClientImpl().get_forward_estimates("AAPL")
