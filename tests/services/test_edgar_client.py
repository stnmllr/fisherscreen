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


# --- get_cik ---

@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_cik_returns_cik_for_known_ticker(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.get_cik("AAPL") == "320193"
    assert client.get_cik("MSFT") == "789019"


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_cik_is_case_insensitive(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.get_cik("aapl") == "320193"
    assert client.get_cik("Aapl") == "320193"


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_cik_returns_none_for_unknown_ticker(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.get_cik("UNKN") is None


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_cik_loads_ticker_map_only_once(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    client.get_cik("AAPL")
    client.get_cik("AAPL")
    client.get_cik("MSFT")

    # _get is called for each has_restatement etc., but company_tickers.json
    # should only be fetched once regardless of how many get_cik calls happen.
    assert mock_httpx.get.call_count == 1


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_cik_returns_none_gracefully_on_http_failure(mock_httpx, mock_time):
    mock_httpx.get.side_effect = Exception("connection refused")

    client = _make_client()
    result = client.get_cik("AAPL")

    assert result is None  # no exception raised; graceful degradation


# --- get_latest_annual_filing ---

@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_latest_annual_filing_returns_text_for_20f(mock_httpx, mock_time):
    submissions = MagicMock()
    submissions.status_code = 200
    submissions.json.return_value = {
        "filings": {"recent": {
            "form": ["6-K", "20-F", "20-F"],
            "accessionNumber": ["0000-24-1", "0000353278-25-000020", "0000353278-24-000010"],
            "primaryDocument": ["a.htm", "novo-20f.htm", "old.htm"],
            "filingDate": ["2025-05-01", "2025-02-05", "2024-02-07"],
        }}
    }
    doc = MagicMock()
    doc.status_code = 200
    doc.text = "<html><body>ITEM 5. OPERATING REVIEW ...</body></html>"
    mock_httpx.get.side_effect = [submissions, doc]

    client = _make_client()
    result = client.get_latest_annual_filing("0000353278", "20-F")
    assert result.accession_number == "0000353278-25-000020"
    assert "OPERATING REVIEW" in result.document_text
    # newest 20-F chosen (first matching form in recent[] which is newest-first)
    doc_url = mock_httpx.get.call_args_list[1][0][0]
    assert "000035327825000020" in doc_url
    assert "novo-20f.htm" in doc_url


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_latest_annual_filing_populates_filing_date(mock_httpx, mock_time):
    submissions = MagicMock()
    submissions.status_code = 200
    submissions.json.return_value = {
        "filings": {"recent": {
            "form": ["6-K", "20-F", "20-F"],
            "accessionNumber": ["0000-24-1", "0000353278-25-000020", "0000353278-24-000010"],
            "primaryDocument": ["a.htm", "novo-20f.htm", "old.htm"],
            "filingDate": ["2025-05-01", "2025-02-05", "2024-02-07"],
        }}
    }
    doc = MagicMock()
    doc.status_code = 200
    doc.text = "<html>ITEM 5</html>"
    mock_httpx.get.side_effect = [submissions, doc]

    client = _make_client()
    result = client.get_latest_annual_filing("0000353278", "20-F")
    # aligned with the chosen (first matching) 20-F at index 1
    assert result.filing_date == "2025-02-05"


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_latest_annual_filing_filing_date_none_when_array_absent(mock_httpx, mock_time):
    submissions = MagicMock()
    submissions.status_code = 200
    submissions.json.return_value = {
        "filings": {"recent": {
            "form": ["10-K"],
            "accessionNumber": ["0001-25-1"],
            "primaryDocument": ["k.htm"],
            # no filingDate key at all
        }}
    }
    doc = MagicMock()
    doc.status_code = 200
    doc.text = "<html>k</html>"
    mock_httpx.get.side_effect = [submissions, doc]

    client = _make_client()
    result = client.get_latest_annual_filing("0000000001", "10-K")
    assert result.filing_date is None


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_latest_annual_filing_filing_date_none_when_array_short(mock_httpx, mock_time):
    submissions = MagicMock()
    submissions.status_code = 200
    submissions.json.return_value = {
        "filings": {"recent": {
            "form": ["6-K", "10-K"],
            "accessionNumber": ["0000-24-1", "0001-25-1"],
            "primaryDocument": ["a.htm", "k.htm"],
            "filingDate": ["2025-05-01"],  # shorter than form[] — index 1 missing
        }}
    }
    doc = MagicMock()
    doc.status_code = 200
    doc.text = "<html>k</html>"
    mock_httpx.get.side_effect = [submissions, doc]

    client = _make_client()
    result = client.get_latest_annual_filing("0000000001", "10-K")
    assert result.filing_date is None


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_latest_annual_filing_missing_form_raises(mock_httpx, mock_time):
    submissions = MagicMock()
    submissions.status_code = 200
    submissions.json.return_value = {
        "filings": {"recent": {"form": ["6-K"], "accessionNumber": ["x"],
                               "primaryDocument": ["a.htm"], "filingDate": ["2025-01-01"]}}
    }
    mock_httpx.get.return_value = submissions
    client = _make_client()
    with pytest.raises(DataSourceError, match="no 10-K filing found"):
        client.get_latest_annual_filing("0000000001", "10-K")


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_latest_annual_filing_doc_fetch_failure_raises(mock_httpx, mock_time):
    submissions = MagicMock()
    submissions.status_code = 200
    submissions.json.return_value = {
        "filings": {"recent": {"form": ["10-K"], "accessionNumber": ["0001-25-1"],
                               "primaryDocument": ["k.htm"], "filingDate": ["2025-01-01"]}}
    }
    bad = MagicMock()
    bad.status_code = 404
    mock_httpx.get.side_effect = [submissions, bad]
    client = _make_client()
    with pytest.raises(DataSourceError, match="404"):
        client.get_latest_annual_filing("0000000001", "10-K")
