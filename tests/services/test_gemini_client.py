import json
from unittest.mock import MagicMock, patch

import pytest

from google.genai.errors import ClientError, ServerError

from app.errors import GeminiError
from app.models.screener_record import ScreenerRecord
from app.services.gemini_client import DIMENSIONS, GeminiClientImpl, GeminiScoreResult


def _record(**kwargs) -> ScreenerRecord:
    defaults = {
        "ticker": "TEST",
        "name": "Test Corp",
        "gics_sector": "Technology",
        "gics_industry": "Software",
        "market_cap": 1_000_000_000,
        "revenue_growth_yoy": 0.15,
        "operating_margin": 0.25,
        "return_on_equity": 0.20,
        "debt_to_equity": 30.0,
    }
    return ScreenerRecord(**{**defaults, **kwargs})


def _mock_token_resp(count: int) -> MagicMock:
    r = MagicMock()
    r.total_tokens = count
    return r


def _flat_payload(dims: dict) -> dict:
    """Build the FLAT v2 JSON payload from a dimensions dict."""
    payload: dict = {"ticker": "TEST"}
    for dim, score in dims.items():
        payload[dim] = score
        payload[f"{dim}_evidence"] = f"{dim} cites a figure"
    payload["weakest_dimension"] = "profitability"
    payload["data_gaps"] = []
    return payload


def _mock_generate_resp(
    dims: dict,
    tokens_in: int = 500,
    tokens_out: int = 80,
    raw_text: str | None = None,
) -> MagicMock:
    r = MagicMock()
    r.text = raw_text if raw_text is not None else json.dumps(_flat_payload(dims))
    r.usage_metadata.prompt_token_count = tokens_in
    r.usage_metadata.candidates_token_count = tokens_out
    return r


def _valid_dims() -> dict:
    return {"growth": 4, "profitability": 3, "management": 3, "innovation": 3, "resilience": 3}


def _server_error(code: int) -> ServerError:
    return ServerError(code, {"error": {"status": "UNAVAILABLE", "message": "high demand"}})


def _client_error(code: int) -> ClientError:
    return ClientError(code, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "rate"}})


@pytest.fixture
def fast_retry(monkeypatch):
    """Neutralisiert tenacity-Sleep, damit Retry-Tests nicht real warten."""
    monkeypatch.setattr(GeminiClientImpl._count_tokens.retry, "sleep", lambda _: None)
    monkeypatch.setattr(GeminiClientImpl._generate.retry, "sleep", lambda _: None)


@patch("app.services.gemini_client._genai")
def test_raises_on_empty_api_key(mock_genai):
    with pytest.raises(GeminiError, match="API key"):
        GeminiClientImpl(api_key="")


@patch("app.services.gemini_client._genai")
def test_score_ticker_returns_valid_result(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.return_value = _mock_generate_resp(_valid_dims())

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())

    assert isinstance(result, GeminiScoreResult)
    assert result.dimensions == _valid_dims()
    assert result.tokens_in == 500
    assert result.tokens_out == 80


@patch("app.services.gemini_client._genai")
def test_raises_when_prompt_exceeds_token_limit(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(9999)

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="too large"):
        impl.score_ticker("TEST", _record(), max_input_tokens=3000)


@patch("app.services.gemini_client._genai")
def test_raises_on_invalid_json_response(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    bad = MagicMock()
    bad.text = "not-json"
    mock_client.models.generate_content.return_value = bad

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="invalid JSON"):
        impl.score_ticker("TEST", _record())


@patch("app.services.gemini_client._genai")
def test_clamps_out_of_range_dimension_scores(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.return_value = _mock_generate_resp(
        {"growth": 10, "profitability": -3, "management": 3, "innovation": 3, "resilience": 3}
    )

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())
    assert result.dimensions["growth"] == 5
    assert result.dimensions["profitability"] == 0  # clamped to 0-floor, not 1


@patch("app.services.gemini_client._genai")
def test_zero_red_flag_score_is_preserved(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.return_value = _mock_generate_resp(
        {"growth": 0, "profitability": 2, "management": 3, "innovation": 3, "resilience": 1}
    )

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())
    assert result.dimensions["growth"] == 0
    assert result.dimensions["resilience"] == 1


@patch("app.services.gemini_client._genai")
def test_parses_flat_schema_with_evidence_weakest_and_gaps(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    payload = _flat_payload(_valid_dims())
    payload["weakest_dimension"] = "resilience"
    payload["data_gaps"] = ["operating_margin", "return_on_equity"]
    resp = MagicMock()
    resp.text = json.dumps(payload)
    resp.usage_metadata.prompt_token_count = 500
    resp.usage_metadata.candidates_token_count = 80
    mock_client.models.generate_content.return_value = resp

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())

    assert result.dimensions == _valid_dims()
    assert result.evidence["growth"] == "growth cites a figure"
    assert result.weakest_dimension == "resilience"
    assert result.data_gaps == ["operating_margin", "return_on_equity"]


@patch("app.services.gemini_client._genai")
def test_management_and_innovation_present_in_output(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.return_value = _mock_generate_resp(_valid_dims())

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())
    assert result.dimensions["management"] == 3
    assert result.dimensions["innovation"] == 3


@patch("app.services.gemini_client._genai")
def test_truncate_retry_recovers_from_trailing_extra_data(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    valid_json = json.dumps(_flat_payload(_valid_dims()))
    # Model appended prose after the JSON → bare json.loads raises "Extra data".
    polluted = valid_json + "\n\nHere is my reasoning: the company looks solid."
    mock_client.models.generate_content.return_value = _mock_generate_resp(
        _valid_dims(), raw_text=polluted
    )

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())
    assert result.dimensions == _valid_dims()


@patch("app.services.gemini_client._genai")
def test_truncate_retry_still_raises_on_unrecoverable_json(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    bad = MagicMock()
    bad.text = "{not even close to json"
    mock_client.models.generate_content.return_value = bad

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="invalid JSON"):
        impl.score_ticker("TEST", _record())


@patch("app.services.gemini_client._genai")
def test_wraps_api_exception_in_gemini_error(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.side_effect = RuntimeError("network failure")

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="API call failed"):
        impl.score_ticker("TEST", _record())


@patch("app.services.gemini_client._genai")
def test_raises_on_missing_dimension_in_response(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    incomplete = {"growth": 4, "profitability": 3}  # missing 3 dimensions
    mock_client.models.generate_content.return_value = _mock_generate_resp(incomplete)

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="dimension"):
        impl.score_ticker("TEST", _record())


@patch("app.services.gemini_client._genai")
def test_score_ticker_handles_none_financial_ratios(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(400)
    mock_client.models.generate_content.return_value = _mock_generate_resp(_valid_dims())

    impl = GeminiClientImpl(api_key="key")
    record = _record(revenue_growth_yoy=None, operating_margin=None, market_cap=None)
    result = impl.score_ticker("TEST", record)
    assert result.dimensions == _valid_dims()


@patch("app.services.gemini_client._genai")
def test_retries_generate_on_503_then_succeeds(mock_genai, fast_retry):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.side_effect = [
        _server_error(503),
        _server_error(503),
        _mock_generate_resp(_valid_dims()),
    ]

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())

    assert result.dimensions == _valid_dims()
    assert mock_client.models.generate_content.call_count == 3


@patch("app.services.gemini_client._genai")
def test_retries_count_tokens_on_503_then_succeeds(mock_genai, fast_retry):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.side_effect = [
        _server_error(503),
        _mock_token_resp(500),
    ]
    mock_client.models.generate_content.return_value = _mock_generate_resp(_valid_dims())

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())

    assert result.dimensions == _valid_dims()
    assert mock_client.models.count_tokens.call_count == 2


@patch("app.services.gemini_client._genai")
def test_persistent_503_raises_gemini_error_after_4_calls(mock_genai, fast_retry):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.side_effect = [_server_error(503)] * 4

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="API call failed"):
        impl.score_ticker("TEST", _record())
    assert mock_client.models.generate_content.call_count == 4


@patch("app.services.gemini_client._genai")
def test_retries_on_429(mock_genai, fast_retry):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.side_effect = [
        _client_error(429),
        _mock_generate_resp(_valid_dims()),
    ]

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())

    assert result.dimensions == _valid_dims()
    assert mock_client.models.generate_content.call_count == 2


@patch("app.services.gemini_client._genai")
def test_no_retry_on_client_error_400(mock_genai, fast_retry):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.side_effect = _client_error(400)

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="API call failed"):
        impl.score_ticker("TEST", _record())
    assert mock_client.models.generate_content.call_count == 1


@patch("app.services.gemini_client._genai")
def test_no_retry_on_server_error_500(mock_genai, fast_retry):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.side_effect = _server_error(500)

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="API call failed"):
        impl.score_ticker("TEST", _record())
    assert mock_client.models.generate_content.call_count == 1
