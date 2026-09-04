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


@patch("app.services.openfigi_client.httpx")
def test_lines_by_share_class_posts_the_share_class_id_type(mock_httpx):
    """The payload is the whole contract of this method: a mapping call keyed by
    ID_BB_GLOBAL_SHARE_CLASS_LEVEL on the value the home line carries."""
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"data": []}]
    mock_httpx.post.return_value = resp

    _client().lines_by_share_class("BBG001S6ZD33")

    url = mock_httpx.post.call_args.args[0]
    payload = mock_httpx.post.call_args.kwargs["json"]
    assert url.endswith("/mapping")
    assert payload == [
        {"idType": "ID_BB_GLOBAL_SHARE_CLASS_LEVEL", "idValue": "BBG001S6ZD33"}
    ]


@patch("app.services.openfigi_client.httpx")
def test_lines_by_share_class_sends_no_security_type_filter(mock_httpx):
    """Explicit fence, deliberately separate from the payload test above: unlike
    `map_ticker` this must NOT constrain securityType2. The share class is
    already the anchor, and pre-filtering to 'Common Stock' would discard the
    sponsored ADR (a Depositary Receipt) — i.e. exactly the line being sought.
    Equality alone would let that regress under a payload rewrite."""
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"data": []}]
    mock_httpx.post.return_value = resp

    _client().lines_by_share_class("BBG001S6ZD33")

    payload = mock_httpx.post.call_args.kwargs["json"]
    assert "securityType2" not in payload[0]
    assert set(payload[0]) == {"idType", "idValue"}


@patch("app.services.openfigi_client.httpx")
def test_lines_by_share_class_returns_every_line_not_just_the_first(mock_httpx):
    """Differs from `map_ticker`, which returns data[0]: the caller needs the
    whole sibling set, since the US lines are what it is looking for and the
    home line is usually not first."""
    resp = MagicMock(status_code=200)
    resp.json.return_value = [
        {
            "data": [
                {"ticker": "REL", "exchCode": "LN"},
                {"ticker": "RLXXF", "exchCode": "US"},
                {"ticker": "RELXY", "exchCode": "US"},
            ]
        }
    ]
    mock_httpx.post.return_value = resp

    out = _client().lines_by_share_class("BBG001S6ZD33")

    assert [ln["ticker"] for ln in out] == ["REL", "RLXXF", "RELXY"]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param([{"warning": "No identifier found."}], id="warning_no_data"),
        pytest.param([{"data": []}], id="empty_data"),
        pytest.param([{"data": None}], id="null_data"),
        pytest.param([], id="empty_envelope"),
        pytest.param({"data": []}, id="dict_instead_of_list"),
    ],
)
@patch("app.services.openfigi_client.httpx")
def test_lines_by_share_class_returns_empty_list_when_data_is_missing(mock_httpx, body):
    """A 200 without usable data is an empty result, not a failure — a real
    failure comes out of `_post` as DataSourceError. Every degenerate envelope
    shape must yield [], never None and never an IndexError/AttributeError:
    the caller iterates the return value unguarded."""
    resp = MagicMock(status_code=200)
    resp.json.return_value = body
    mock_httpx.post.return_value = resp

    assert _client().lines_by_share_class("BBG000NOPE00") == []


@patch("app.services.openfigi_client.httpx")
def test_lines_by_share_class_raises_datasourceerror_after_retries(mock_httpx):
    """Failure != empty on the new call surface too: an exhausted 503 must not
    read as 'this issuer has no US line'."""
    resp = MagicMock(status_code=503)
    resp.headers = {}
    mock_httpx.post.return_value = resp

    with pytest.raises(DataSourceError, match="OpenFIGI"):
        _client().lines_by_share_class("BBG001S6ZD33")
