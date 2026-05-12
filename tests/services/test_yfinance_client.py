from unittest.mock import MagicMock, patch

import pytest

from app.errors import DataSourceError
from app.services.yfinance_client import YFinanceClientImpl


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
    import pandas as pd

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame({"Close": [100.0, 101.0]})
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()
    result = client.get_historical("AAPL", "1mo")

    mock_ticker.history.assert_called_once_with(period="1mo")
    assert len(result) == 2


@patch("app.services.yfinance_client.yf")
def test_get_financials_returns_dict(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.financials = {"Revenue": 394_000_000_000}
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()
    result = client.get_financials("AAPL")

    assert result == {"Revenue": 394_000_000_000}
