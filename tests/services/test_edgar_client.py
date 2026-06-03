import pytest
from unittest.mock import MagicMock, patch

from app.errors import DataSourceError


from app.services.rate_limiter import RateLimiter


def _make_client(user_agent="Test Agent <test@example.com>"):
    from app.services.edgar_client import EdgarClientImpl
    return EdgarClientImpl(
        user_agent=user_agent,
        rate_limiter=RateLimiter(8.0, sleep=lambda _s: None),
    )


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


# --- SUB-PHASE 4: affirmative going-concern polarity discriminator ---
#
# Real filing excerpts (full governing sentences). Each healthy filing carries the
# ASC-205-40 boilerplate phrase in a NON-asserting form (evaluation duty / negation /
# hypothetical modal) → must be classified non-affirmative (False). FRQN is a real
# going-concern filing whose text contains BOTH the duty-intro AND an affirmative
# finding in the same document → must be True (proves ∃-over-all-occurrences).

ADC_TEXT = (
    "When preparing financial statements for each annual and interim reporting "
    "period, management has the responsibility to evaluate whether there are "
    "conditions or events, considered in the aggregate, that raise substantial "
    "doubt about the Company's ability to continue as a going concern within one "
    "year after the date that the financial statements are issued. No conditions "
    "or events that raised substantial doubt about the ability to continue as a "
    "going concern within one year were identified as of the issuance date of the "
    "condensed consolidated financial statements."
)

FR_TEXT = (
    "In preparing the consolidated financial statements, management is required to "
    "evaluate whether there are conditions or events, considered in the aggregate, "
    "that raise substantial doubt about the Company's ability to continue as a going "
    "concern for one year after the date the consolidated financial statements are "
    "available to be issued. Conclude whether, in our judgment, there are conditions "
    "or events, considered in the aggregate, that raise substantial doubt about the "
    "Company's ability to continue as a going concern for a reasonable period of time."
)

HIMS_TEXT = (
    "Management considers that there are no conditions or events in the aggregate "
    "that raise substantial doubt about the entity's ability to continue as a going "
    "concern for a period of at least one year from the date the consolidated "
    "financial statements are issued."
)

LIVN_TEXT = (
    "In addition, future unanticipated large liability claims may raise substantial "
    "doubt about LivaNova's ability to continue as a going concern."
)

WTW_TEXT = (
    "Going Concern — Management evaluates at each annual and interim period whether "
    "there are conditions or events, considered in the aggregate, that raise "
    "substantial doubt about our ability to continue as a going concern within one "
    "year after the date that the consolidated financial statements are issued. "
    "Management has concluded that there are no conditions or events, considered in "
    "the aggregate, that raise substantial doubt about our ability to continue as a "
    "going concern within one year after the date of these financial statements."
)

FRQN_TEXT = (
    "The Company has evaluated whether there are certain conditions and events, "
    "considered in the aggregate, that raise substantial doubt and the Company's "
    "ability to continue as a going concern within one year after the date that the "
    "financial statements are issued. These factors raise substantial doubt about "
    "the Company's ability to continue as a going concern. The Company's ability to "
    "continue as a going concern for the next twelve months is dependent upon its "
    "ability to generate sufficient cash flows from operations."
)


@pytest.mark.parametrize(
    "label,text",
    [
        ("ADC", ADC_TEXT),
        ("FR", FR_TEXT),
        ("HIMS", HIMS_TEXT),
        ("LIVN", LIVN_TEXT),
        ("WTW", WTW_TEXT),
    ],
)
def test_has_affirmative_going_concern_false_for_boilerplate(label, text):
    # Healthy filings: every "substantial doubt" occurrence is governed by a
    # whether-duty, a (possibly distant) negation, or a hypothetical modal → no
    # affirmative finding → False. WTW/HIMS are the distant-negation guards: "no"
    # sits ~10+ words before "raise", so a token-window check would wrongly pass.
    client = _make_client()
    assert client._has_affirmative_going_concern(text) is False, label


def test_has_affirmative_going_concern_true_for_frqn_mixed_doc():
    # FRQN contains the duty-intro ("evaluated whether … raise substantial doubt")
    # AND an affirmative finding ("These factors raise substantial doubt …") in the
    # same text. The helper MUST iterate every occurrence and OR the results, so the
    # affirmative one wins → True. Classifying only the first occurrence would be False.
    client = _make_client()
    assert client._has_affirmative_going_concern(FRQN_TEXT) is True


def test_has_affirmative_going_concern_true_for_there_is_form():
    client = _make_client()
    text = "There is substantial doubt about the Company's ability to continue as a going concern."
    assert client._has_affirmative_going_concern(text) is True


def test_has_affirmative_going_concern_true_for_exists_form():
    client = _make_client()
    text = "substantial doubt exists about the Company's ability to continue as a going concern."
    assert client._has_affirmative_going_concern(text) is True


def test_has_affirmative_going_concern_false_for_empty_text():
    client = _make_client()
    assert client._has_affirmative_going_concern("") is False


def test_has_affirmative_going_concern_strips_html_tags():
    # The doc arrives as raw HTML; the helper must strip tags before scanning so the
    # negation governing the phrase is not severed by intervening markup.
    client = _make_client()
    html = (
        "<p>Management has concluded that there are "
        "<b>no</b> conditions or events that <span>raise "
        "substantial doubt</span> about our ability to continue as a going concern.</p>"
    )
    assert client._has_affirmative_going_concern(html) is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_returns_true_when_hits_found(mock_httpx, mock_time):
    # A qualifying hit = in-window AND a primary form document (10-K/10-Q) whose
    # fetched primary doc carries an AFFIRMATIVE going-concern finding.
    from datetime import date
    today = date.today().isoformat()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "hits": {
            "total": {"value": 2, "relation": "eq"},
            "hits": [
                {
                    "_id": "0000320193-26-000010:doc.htm",
                    "_source": {"file_date": today, "file_type": "10-K"},
                }
            ],
        }
    }
    mock_resp.text = FRQN_TEXT
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
def test_has_going_concern_scopes_query_with_ciks_param(mock_httpx, mock_time):
    # Root-cause fix: the query MUST be CIK-scoped via the valid EFTS `ciks=`
    # parameter. The bug used `entity=`, which EFTS silently ignores, letting the
    # query run unscoped over the whole corpus (10000 hits → False-Positive True).
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"hits": {"total": {"value": 0, "relation": "eq"}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    client.has_going_concern("320193")

    call_url = mock_httpx.get.call_args[0][0]
    assert "ciks=0000320193" in call_url  # padded CIK passed through to the valid param
    assert "entity=" not in call_url       # the invalid, silently-ignored param is gone


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_false_for_scoped_healthy_eq_zero(mock_httpx, mock_time):
    # Sentinel trennschärfe (negative half): a correctly-scoped healthy large-cap
    # returns {'value': 0, 'relation': 'eq'} → no going-concern doubt → False.
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"hits": {"total": {"value": 0, "relation": "eq"}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_going_concern("320193") is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_true_for_scoped_genuine_hit_eq_relation(mock_httpx, mock_time):
    # Sentinel trennschärfe (the legitimate-positive branch): a correctly-scoped
    # query with a small EXACT count ({'relation': 'eq'}) whose hit is in-window AND
    # in a primary form document → True. Pins the True branch explicitly, since the
    # refactor reworked the True/raise split; relation == 'eq' must reach True (not
    # raise), and the qualifying hit drives it (not the bare total count).
    from datetime import date
    today = date.today().isoformat()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "hits": {
            "total": {"value": 3, "relation": "eq"},
            "hits": [
                {
                    "_id": "0000320193-26-000011:doc.htm",
                    "_source": {"file_date": today, "file_type": "10-Q"},
                }
            ],
        }
    }
    mock_resp.text = FRQN_TEXT
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_going_concern("320193") is True


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_raises_on_overbroad_gte_relation(mock_httpx, mock_time):
    # Sentinel trennschärfe (positive half): an over-broad / unscoped result is
    # EDGAR-canonically signalled by relation == 'gte' (count capped/approximate).
    # That must NOT be read as "going concern True for everyone" — it is a scoping
    # failure and must fail LOUD (DataSourceError → runner skips+keeps, logs),
    # never silently drop the whole universe.
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"hits": {"total": {"value": 10000, "relation": "gte"}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    with pytest.raises(DataSourceError, match="over-broad"):
        client.has_going_concern("320193")


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_retries_on_efts_500_then_succeeds(mock_httpx, mock_time, caplog):
    # EFTS sporadically returns 500 (observed in diagnosis E5). A transient 5xx
    # must not randomly flip a ticker between dropped/kept — retry with backoff.
    # The retry MUST log a WARNING so a genuine persistent EFTS outage is not masked.
    import logging

    resp500 = MagicMock()
    resp500.status_code = 500
    resp200 = MagicMock()
    resp200.status_code = 200
    resp200.json.return_value = {"hits": {"total": {"value": 0, "relation": "eq"}}}
    mock_httpx.get.side_effect = [resp500, resp200]

    client = _make_client()
    with caplog.at_level(logging.WARNING, logger="app.services.edgar_client"):
        result = client.has_going_concern("320193")

    assert result is False
    assert mock_httpx.get.call_count == 2
    assert "500" in caplog.text
    assert "retry" in caplog.text.lower()


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_raises_after_efts_500_exhausted(mock_httpx, mock_time):
    # Persistent 5xx exhausts retries → DataSourceError (runner skips+keeps).
    resp500 = MagicMock()
    resp500.status_code = 500
    mock_httpx.get.return_value = resp500

    client = _make_client()
    with pytest.raises(DataSourceError, match="500"):
        client.has_going_concern("320193")


# --- EFTS exponential full-jitter backoff (SUB-PHASE 2) ---


class _StubRng:
    """Deterministic RNG stub: uniform(lo, hi) returns hi (the cap), so the
    full-jitter schedule collapses to its upper bound and is assertable."""

    def uniform(self, lo: float, hi: float) -> float:
        return hi


def _make_client_with_efts(efts_sleep, rng):
    from app.services.edgar_client import EdgarClientImpl

    return EdgarClientImpl(
        user_agent="Test Agent <test@example.com>",
        rate_limiter=RateLimiter(8.0, sleep=lambda _s: None),
        efts_sleep=efts_sleep,
        rng=rng,
    )


@patch("app.services.edgar_client.httpx")
def test_efts_500_then_200_recovers(mock_httpx):
    # 500 then 200 → recovery path: going_concern_hit succeeds, exactly one sleep.
    resp500 = MagicMock()
    resp500.status_code = 500
    resp200 = MagicMock()
    resp200.status_code = 200
    resp200.json.return_value = {"hits": {"total": {"value": 0, "relation": "eq"}}}
    mock_httpx.get.side_effect = [resp500, resp200]

    delays: list[float] = []
    client = _make_client_with_efts(efts_sleep=delays.append, rng=_StubRng())
    result = client.going_concern_hit("320193")

    assert result is None
    assert mock_httpx.get.call_count == 2
    assert len(delays) == 1  # one retry → one sleep


@patch("app.services.edgar_client.httpx")
def test_efts_full_jitter_exponential_schedule(mock_httpx):
    # rng.uniform stubbed to its upper bound → captured caps are the exponential
    # full-jitter upper bounds: base*2**(n-1) for attempts 1..4 = [1, 2, 4, 8].
    # 5 consecutive 500s → exhausted (attempt 5 raises, no 5th sleep).
    resp500 = MagicMock()
    resp500.status_code = 500
    mock_httpx.get.return_value = resp500

    delays: list[float] = []
    client = _make_client_with_efts(efts_sleep=delays.append, rng=_StubRng())
    with pytest.raises(DataSourceError):
        client.going_concern_hit("320193")

    assert delays == [1.0, 2.0, 4.0, 8.0]


@patch("app.services.edgar_client.httpx")
def test_efts_full_jitter_is_within_bounds(mock_httpx):
    # Real seeded RNG → each slept delay must lie in [0, cap_n] where
    # cap_n = base*2**(n-1). Pins full jitter (uniform 0..cap), not a fixed value.
    import random

    resp500 = MagicMock()
    resp500.status_code = 500
    mock_httpx.get.return_value = resp500

    delays: list[float] = []
    client = _make_client_with_efts(
        efts_sleep=delays.append, rng=random.Random(0)
    )
    with pytest.raises(DataSourceError):
        client.going_concern_hit("320193")

    caps = [1.0, 2.0, 4.0, 8.0]
    assert len(delays) == len(caps)
    for delay, cap in zip(delays, caps):
        assert 0.0 <= delay <= cap
    # full jitter must actually vary, not collapse to the caps
    assert delays != caps


@patch("app.services.edgar_client.httpx")
def test_efts_500_exhausted_raises_data_source_error(mock_httpx, caplog):
    # 5x500 → fail-safe DataSourceError, 5 attempts made, per-retry WARNING loud.
    import logging

    resp500 = MagicMock()
    resp500.status_code = 500
    mock_httpx.get.return_value = resp500

    delays: list[float] = []
    client = _make_client_with_efts(efts_sleep=delays.append, rng=_StubRng())
    with caplog.at_level(logging.WARNING, logger="app.services.edgar_client"):
        with pytest.raises(DataSourceError, match="500"):
            client.going_concern_hit("320193")

    assert mock_httpx.get.call_count == 5  # _EFTS_MAX_ATTEMPTS
    assert len(delays) == 4  # sleeps before retries 1..4; attempt 5 raises
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 4
    assert "500" in caplog.text
    assert "retry" in caplog.text.lower()


@patch("app.services.edgar_client.httpx")
def test_efts_non_5xx_not_retried(mock_httpx):
    # 404 → immediate DataSourceError, NO sleep, NO retry (preserve behavior).
    resp404 = MagicMock()
    resp404.status_code = 404
    mock_httpx.get.return_value = resp404

    delays: list[float] = []
    client = _make_client_with_efts(efts_sleep=delays.append, rng=_StubRng())
    with pytest.raises(DataSourceError, match="404"):
        client.going_concern_hit("320193")

    assert mock_httpx.get.call_count == 1
    assert delays == []


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_false_when_all_hits_out_of_window(mock_httpx, mock_time):
    # Defekt A (residual): EFTS silently ignores `startdt`, so the CIK-scoped query
    # returns the CIK's ALL-TIME phrase hits, not the 24-month window (byte-proven:
    # WITH vs WITHOUT startdt identical). A healthy large-cap (JNJ class) whose only
    # "raise substantial doubt" hits are OLD 10-K/10-Q must be False. The window is
    # therefore enforced CLIENT-SIDE on each hit's file_date.
    old = "2017-02-27"  # years before any plausible today−24mo startdt
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "hits": {
            "total": {"value": 2, "relation": "eq"},
            "hits": [
                {"_source": {"file_date": old, "file_type": "10-K"}},
                {"_source": {"file_date": "2016-11-04", "file_type": "10-Q"}},
            ],
        }
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_going_concern("200406") is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_false_for_in_window_exhibit_boilerplate(mock_httpx, mock_time):
    # Defekt B (observed at AWI): an IN-WINDOW hit can be auditor-responsibility
    # BOILERPLATE ("required to evaluate whether there are conditions … that raise
    # substantial doubt …") living in an EX-99.1 exhibit attached to a 10-K — NOT a
    # genuine going-concern qualification. Only PRIMARY form documents (10-K/10-Q)
    # count; exhibits (EX-*) are excluded. AWI is mixed: in-window exhibit +
    # out-of-window primary → both rejected → False (proves BOTH axes are required).
    from datetime import date
    today = date.today().isoformat()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "hits": {
            "total": {"value": 2, "relation": "eq"},
            "hits": [
                {"_source": {"file_date": today, "file_type": "EX-99.1"}},
                {"_source": {"file_date": "2006-02-24", "file_type": "10-K"}},
            ],
        }
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_going_concern("7431") is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_true_for_in_window_primary_form_hit(mock_httpx, mock_time):
    # Positive control (FRQN class): genuine going-concern language in an IN-WINDOW
    # PRIMARY 10-Q document → True. The fix must NOT neutralise real detection.
    from datetime import date
    today = date.today().isoformat()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_id": "0001624517-26-000001:frqn.htm",
                    "_source": {"file_date": today, "file_type": "10-Q"},
                },
            ],
        }
    }
    mock_resp.text = FRQN_TEXT
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_going_concern("1624517") is True


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


def test_has_active_enforcement_is_silent(caplog):
    import logging

    client = _make_client()
    with caplog.at_level(logging.DEBUG, logger="app.services.edgar_client"):
        result = client.has_active_enforcement("123")
    assert result is False
    # Deliberately inert no-op: must not emit a per-CIK log record (was 538-line spam).
    assert [r for r in caplog.records if r.name == "app.services.edgar_client"] == []


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


# --- Form-4 index & document ---

from app.services.edgar_client import EdgarClientImpl, Form4Ref


def _client():
    return EdgarClientImpl(
        user_agent="FisherScreen test test@example.com",
        rate_limiter=RateLimiter(8.0, sleep=lambda _s: None),
    )


def test_get_form4_index_filters_form_and_date():
    c = _client()
    payload = {"filings": {"recent": {
        "form": ["10-K", "4", "4", "8-K"],
        "accessionNumber": ["a0", "a1", "a2", "a3"],
        "primaryDocument": ["d0", "xslF345X06/d1.xml", "d2.xml", "d3"],
        "filingDate": ["2026-05-01", "2026-04-01", "2024-01-01", "2026-03-01"],
    }}}
    with patch.object(c, "_get", return_value=payload):
        refs = c.get_form4_index("789019", since="2025-06-01")
    assert [r.accession_number for r in refs] == ["a1"]
    assert refs[0].primary_document == "xslF345X06/d1.xml"


def test_get_form4_document_strips_xsl_prefix():
    c = _client()
    captured = {}

    def fake_text(url):
        captured["url"] = url
        return "<ownershipDocument/>"

    with patch.object(c, "_get_text", side_effect=fake_text):
        xml = c.get_form4_document("789019", "0000789019-26-000075", "xslF345X06/form4.xml")
    assert xml == "<ownershipDocument/>"
    assert captured["url"].endswith("/000078901926000075/form4.xml")
    assert "xslF345X06" not in captured["url"]


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_going_concern_hit_returns_hit_with_accession_for_primary_form(mock_httpx, mock_time):
    from datetime import date

    from app.services.edgar_client import GoingConcernHit

    today = date.today().isoformat()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_id": "0000320193-26-000010:doc.htm",
                    "_source": {
                        "file_date": today,
                        "file_type": "10-K",
                        "adsh": "0000320193-26-000010",
                    },
                }
            ],
        }
    }
    mock_resp.text = FRQN_TEXT
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    hit = client.going_concern_hit("320193")

    assert isinstance(hit, GoingConcernHit)
    assert hit.accession_number == "0000320193-26-000010"
    assert hit.file_type == "10-K"
    assert hit.file_date == today


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_going_concern_hit_returns_none_when_no_qualifying_hit(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"hits": {"total": {"value": 0, "relation": "eq"}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.going_concern_hit("320193") is None


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_going_concern_hit_returns_none_for_in_window_primary_boilerplate(
    mock_httpx, mock_time
):
    # SUB-PHASE 4 core fix: an in-window primary-form candidate (passes the cheap
    # window + form pre-filter) whose FETCHED primary doc is ASC-205-40 boilerplate
    # (no affirmative finding) → None. This is the healthy mega-cap FP path (ADC/FR/
    # HIMS/LIVN/WTW) that previously dropped the ticker.
    from datetime import date

    today = date.today().isoformat()
    efts_resp = MagicMock()
    efts_resp.status_code = 200
    efts_resp.json.return_value = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_id": "0001140536-25-026278:wtw.htm",
                    "_source": {
                        "file_date": today,
                        "file_type": "10-K",
                        "adsh": "0001140536-25-026278",
                    },
                }
            ],
        }
    }
    doc_resp = MagicMock()
    doc_resp.status_code = 200
    doc_resp.text = WTW_TEXT  # distant-negation boilerplate → not affirmative
    mock_httpx.get.side_effect = [efts_resp, doc_resp]

    client = _make_client()
    assert client.going_concern_hit("1140536") is None


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_going_concern_hit_returns_hit_for_in_window_primary_affirmative(
    mock_httpx, mock_time
):
    # The fetched primary doc carries an affirmative finding (FRQN) → the hit is
    # returned (going-concern True → ticker dropped). Positive control for the
    # fetch+polarity wiring.
    from datetime import date

    from app.services.edgar_client import GoingConcernHit

    today = date.today().isoformat()
    efts_resp = MagicMock()
    efts_resp.status_code = 200
    efts_resp.json.return_value = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_id": "0001829126-25-009309:frqn.htm",
                    "_source": {
                        "file_date": today,
                        "file_type": "10-Q",
                        "adsh": "0001829126-25-009309",
                    },
                }
            ],
        }
    }
    doc_resp = MagicMock()
    doc_resp.status_code = 200
    doc_resp.text = FRQN_TEXT
    mock_httpx.get.side_effect = [efts_resp, doc_resp]

    client = _make_client()
    hit = client.going_concern_hit("1624517")
    assert isinstance(hit, GoingConcernHit)
    assert hit.file_type == "10-Q"


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_going_concern_hit_builds_archive_url_from_hit_id(mock_httpx, mock_time):
    # The doc-fetch URL is derived from the EFTS hit _id ("{accession}:{filename}"):
    # https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{filename}
    from datetime import date

    today = date.today().isoformat()
    efts_resp = MagicMock()
    efts_resp.status_code = 200
    efts_resp.json.return_value = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_id": "0000320193-26-000010:aapl-20260101.htm",
                    "_source": {"file_date": today, "file_type": "10-K"},
                }
            ],
        }
    }
    doc_resp = MagicMock()
    doc_resp.status_code = 200
    doc_resp.text = WTW_TEXT
    mock_httpx.get.side_effect = [efts_resp, doc_resp]

    client = _make_client()
    client.going_concern_hit("320193")

    doc_url = mock_httpx.get.call_args_list[1][0][0]
    assert doc_url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019326000010/aapl-20260101.htm"
    )


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_going_concern_hit_doc_fetch_failure_propagates(mock_httpx, mock_time):
    # Fail-safe: a primary-doc fetch failure raises DataSourceError (runner keeps the
    # ticker, no silent drop) rather than being swallowed into a false negative.
    from datetime import date

    today = date.today().isoformat()
    efts_resp = MagicMock()
    efts_resp.status_code = 200
    efts_resp.json.return_value = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_id": "0000320193-26-000010:doc.htm",
                    "_source": {"file_date": today, "file_type": "10-K"},
                }
            ],
        }
    }
    doc_resp = MagicMock()
    doc_resp.status_code = 404
    mock_httpx.get.side_effect = [efts_resp, doc_resp]

    client = _make_client()
    with pytest.raises(DataSourceError, match="404"):
        client.going_concern_hit("320193")


@patch("app.services.edgar_client.httpx")
def test_rate_limiter_acquire_invoked_on_request_path(mock_httpx):
    # The injected rate limiter MUST be consulted before each EDGAR HTTP call —
    # proves the throttle is wired into the request path, not just constructed.
    from app.services.edgar_client import EdgarClientImpl

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "filings": {"recent": {"form": [], "filingDate": [], "items": []}}
    }
    mock_httpx.get.return_value = mock_resp

    spy = MagicMock()
    client = EdgarClientImpl(
        user_agent="Test Agent <test@example.com>", rate_limiter=spy
    )
    client.has_restatement("320193")

    assert spy.acquire.called
