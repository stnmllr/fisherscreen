from unittest.mock import MagicMock, patch

import pytest

from app.errors import DataSourceError


def _client():
    from app.services.openfigi_client import OpenFIGIClientImpl

    return OpenFIGIClientImpl(sleep=lambda _s: None)


def _line(name="ASML HOLDING NV", ticker="ASML", security_type="Common Stock"):
    """One OpenFIGI mapping datum. `securityType2` is spelled out on every
    fixture on purpose: the response-side allow-list reads it, so a fixture that
    omitted it would silently be testing the rejection path."""
    line = {"name": name, "ticker": ticker}
    if security_type is not None:
        line["securityType2"] = security_type
    return line


@patch("app.services.openfigi_client.httpx")
def test_map_ticker_returns_first_datum(mock_httpx):
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"data": [_line()]}]
    mock_httpx.post.return_value = resp
    out = _client().map_ticker("ASML", "NA")
    assert out["name"] == "ASML HOLDING NV"


@patch("app.services.openfigi_client.httpx")
def test_map_ticker_none_on_no_data(mock_httpx):
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"warning": "no identifier found"}]
    mock_httpx.post.return_value = resp
    assert _client().map_ticker("NOPE", "NA") is None


# ---------------------------------------------------------------------------
# `securityType2`: from a request filter to a response-side allow-list.
#
# The old request carried `securityType2: "Common Stock"`, which is what made
# BYG.L (Big Yellow Group, a REIT) unfindable — and OpenFIGI takes exactly ONE
# value per request, so a server-side filter can only ever be an allow-list of
# one. The decision therefore moved into the client, where a SET can decide.
# ---------------------------------------------------------------------------

_ALLOWED_TYPES = ["Common Stock", "REIT", "Preference", "Depositary Receipt"]
# Refused, and each for its own reason: a derivative ON the company (a warrant
# on Big Yellow carries Big Yellow's name, so the downstream name check cannot
# tell them apart), a fund, a pass-through vehicle, and a type nobody has ever
# seen.
_REFUSED_TYPES = ["Warrant", "Option", "Right", "Mutual Fund", "Ltd Part", "Nonesuch"]


@pytest.mark.parametrize("security_type", _ALLOWED_TYPES)
@patch("app.services.openfigi_client.httpx")
def test_map_ticker_accepts_every_allowed_home_listing_type(mock_httpx, security_type):
    """All four, one test each, because each is in the list for a different
    reason and dropping any one of them is a separate regression: REIT is the
    measured miss (BYG.L), Preference IS the listed line on several German and
    Nordic names, and Dutch/Belgian STAK structures list depositary receipts as
    the ordinary home line."""
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"data": [_line(security_type=security_type)]}]
    mock_httpx.post.return_value = resp

    out = _client().map_ticker("ASML", "NA")

    assert out is not None and out["securityType2"] == security_type


@pytest.mark.parametrize("security_type", _REFUSED_TYPES)
@patch("app.services.openfigi_client.httpx")
def test_map_ticker_refuses_a_type_that_is_not_a_home_listing(
    mock_httpx, security_type
):
    """FAIL CLOSED — the property that makes an allow-list worth having. An
    unknown type is refused exactly like a known-bad one, so a blind spot
    degrades the ticker to `unverifiable_identity` (honest ignorance) instead of
    letting a warrant answer for the company it is written on."""
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"data": [_line(security_type=security_type)]}]
    mock_httpx.post.return_value = resp

    assert _client().map_ticker("ASML", "NA") is None


@patch("app.services.openfigi_client.httpx")
def test_map_ticker_refuses_a_line_without_a_security_type_at_all(mock_httpx):
    """The absent key, separately from the unknown value: `.get` returns None
    and the allow-list must not be talked into treating that as 'unclassified,
    therefore probably fine'. A line that does not say what it is has not
    identified itself."""
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"data": [_line(security_type=None)]}]
    mock_httpx.post.return_value = resp

    assert _client().map_ticker("ASML", "NA") is None


@patch("app.services.openfigi_client.httpx")
def test_map_ticker_skips_a_refused_line_to_reach_the_allowed_one(mock_httpx):
    """It is a FILTER, not `data[0]` with an afterthought. One symbol on one
    exchange can answer with several lines, and the warrant is not guaranteed to
    come last — returning the first datum and then checking it would drop the
    home line whenever it does not."""
    resp = MagicMock(status_code=200)
    resp.json.return_value = [
        {
            "data": [
                _line(name="BIG YELLOW GROUP PLC-WT", security_type="Warrant"),
                _line(name="BIG YELLOW GROUP PLC", ticker="BYG", security_type="REIT"),
            ]
        }
    ]
    mock_httpx.post.return_value = resp

    out = _client().map_ticker("BYG", "LN")

    assert out["ticker"] == "BYG"
    assert out["securityType2"] == "REIT"


@patch("app.services.openfigi_client.httpx")
def test_map_ticker_sends_no_security_type_filter_in_the_request(mock_httpx):
    """The move itself, pinned on the payload. As long as the request still
    named a type, the allow-list below it could only ever narrow that one value
    — BYG.L would stay unfindable however the set is spelled, and the tests
    above would pass while production did not."""
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"data": [_line()]}]
    mock_httpx.post.return_value = resp

    _client().map_ticker("ASML", "NA")

    payload = mock_httpx.post.call_args.kwargs["json"]
    assert payload == [{"idType": "TICKER", "idValue": "ASML", "exchCode": "NA"}]


@patch("app.services.openfigi_client.httpx")
def test_map_ticker_logs_the_types_it_refused(mock_httpx, caplog):
    """What makes a fail-closed blind spot findable at all. Refusing everything
    and returning None is indistinguishable from 'this symbol does not exist'
    unless the types that were on offer are written down — this log line is the
    only place a wrongly-omitted type would ever surface."""
    import logging

    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"data": [_line(security_type="Warrant")]}]
    mock_httpx.post.return_value = resp

    with caplog.at_level(logging.DEBUG, logger="app.services.openfigi_client"):
        assert _client().map_ticker("BYG", "LN") is None

    assert any(
        "BYG" in rec.getMessage() and "Warrant" in rec.getMessage()
        for rec in caplog.records
    )


def test_the_prefix_tolerant_search_path_is_gone_for_good():
    """`search_issuer` is DELETED, not merely unused — from the Protocol as well
    as from the implementation.

    It fed `_same_issuer`, the prefix-tolerant comparison that accepts
    'ROCHE HOLDING AG' as 'ROCHE BOBOIS SA-UNSPON ADR', and it read only the
    first page of a paginated result (the RELX defect). Absence from the
    Protocol is the load-bearing half: while the method is declared, a client
    can implement it and a caller can reach for it in good faith."""
    from app.services.openfigi_client import OpenFIGIClient

    assert not hasattr(_client(), "search_issuer")
    assert "search_issuer" not in dir(OpenFIGIClient)


@patch("app.services.openfigi_client.httpx")
def test_a_transport_failure_is_a_datasourceerror_not_an_empty_result(mock_httpx):
    """Failure != empty, at the lowest surface there is. A connection reset
    escaping as a bare exception would abort the deep dive with a stack trace
    instead of the classified DataSourceError the CLI maps to exit 2 — and any
    later `except Exception` around the call would turn it into 'this issuer has
    no home line', which is the one reading it must never get."""
    mock_httpx.post.side_effect = OSError("connection reset by peer")

    with pytest.raises(DataSourceError, match="connection reset by peer"):
        _client().map_ticker("ASML", "NA")


@patch("app.services.openfigi_client.httpx")
def test_an_api_key_is_sent_as_the_openfigi_header(mock_httpx):
    """The key is what raises the rate limit, and a key that is accepted but
    never sent looks exactly like no key at all: the client keeps working and
    only the throttling gets worse. Asserted on the header of the real request,
    since that is the only place the difference is observable."""
    from app.services.openfigi_client import OpenFIGIClientImpl

    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"data": [_line()]}]
    mock_httpx.post.return_value = resp

    OpenFIGIClientImpl("secret-key", sleep=lambda _s: None).map_ticker("ASML", "NA")

    headers = mock_httpx.post.call_args.kwargs["headers"]
    assert headers["X-OPENFIGI-APIKEY"] == "secret-key"


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
