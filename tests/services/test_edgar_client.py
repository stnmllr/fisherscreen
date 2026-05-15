import pytest
from unittest.mock import MagicMock, patch

from app.errors import DataSourceError


def _make_client(user_agent="Test Agent <test@example.com>"):
    from app.services.edgar_client import EdgarClientImpl
    return EdgarClientImpl(user_agent=user_agent)


def test_init_raises_when_user_agent_empty():
    from app.services.edgar_client import EdgarClientImpl
    with pytest.raises(DataSourceError, match="user agent"):
        EdgarClientImpl(user_agent="")


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_restatement_returns_true_when_8k_item_4_02_found(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-K"],
                "filingDate": ["2025-03-15", "2025-02-01"],
                "items": ["4.02", ""],
            }
        }
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_restatement("320193", years=3) is True


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_restatement_returns_false_when_no_4_02(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "filingDate": ["2025-03-15"],
                "items": ["1.01"],
            }
        }
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_restatement("320193") is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_restatement_ignores_filings_outside_date_window(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "filingDate": ["2010-01-01"],  # well outside the 3-year window
                "items": ["4.02"],
            }
        }
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_restatement("320193", years=3) is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_restatement_returns_false_for_empty_filings(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"filings": {"recent": {}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_restatement("320193") is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_returns_true_when_hits_found(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"hits": {"total": {"value": 2}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_going_concern("320193") is True


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_returns_false_when_no_hits(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"hits": {"total": {"value": 0}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_going_concern("320193") is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_raises_data_source_error_on_non_200(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    with pytest.raises(DataSourceError, match="403"):
        client.has_restatement("320193")


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_raises_data_source_error_on_network_failure(mock_httpx, mock_time):
    mock_httpx.get.side_effect = Exception("connection refused")

    client = _make_client()
    with pytest.raises(DataSourceError, match="HTTP request failed"):
        client.has_restatement("320193")


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_cik_is_zero_padded_to_10_digits_in_url(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"filings": {"recent": {}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    client.has_restatement("320193")

    call_url = mock_httpx.get.call_args[0][0]
    assert "CIK0000320193" in call_url


def test_has_active_enforcement_returns_false_and_logs_warning(caplog):
    import logging
    client = _make_client()
    with caplog.at_level(logging.WARNING, logger="app.services.edgar_client"):
        result = client.has_active_enforcement("320193")
    assert result is False
    assert "not implemented" in caplog.text
