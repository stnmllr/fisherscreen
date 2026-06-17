from unittest.mock import MagicMock, patch

import pytest

from app.errors import DataSourceError


def _client():
    from app.services.openfigi_client import OpenFIGIClientImpl
    return OpenFIGIClientImpl(sleep=lambda _s: None)


@patch("app.services.openfigi_client.httpx")
def test_map_ticker_returns_first_datum(mock_httpx):
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"data": [{"name": "ASML HOLDING NV", "ticker": "ASML"}]}]
    mock_httpx.post.return_value = resp
    out = _client().map_ticker("ASML", "NA")
    assert out["name"] == "ASML HOLDING NV"


@patch("app.services.openfigi_client.httpx")
def test_map_ticker_none_on_no_data(mock_httpx):
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"warning": "no identifier found"}]
    mock_httpx.post.return_value = resp
    assert _client().map_ticker("NOPE", "NA") is None


@patch("app.services.openfigi_client.httpx")
def test_search_issuer_returns_data_list(mock_httpx):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"data": [{"ticker": "ASML", "exchCode": "US"}]}
    mock_httpx.post.return_value = resp
    out = _client().search_issuer("ASML HOLDING NV")
    assert out == [{"ticker": "ASML", "exchCode": "US"}]


@patch("app.services.openfigi_client.httpx")
def test_raises_datasourceerror_after_retries_on_429(mock_httpx):
    resp = MagicMock(status_code=429)
    resp.headers = {}
    mock_httpx.post.return_value = resp
    with pytest.raises(DataSourceError, match="OpenFIGI"):
        _client().map_ticker("X", "NA")
