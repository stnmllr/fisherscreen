import json
from unittest.mock import MagicMock, patch

import pytest

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


def _mock_generate_resp(
    dims: dict,
    summary: str = "Solid company",
    tokens_in: int = 500,
    tokens_out: int = 80,
) -> MagicMock:
    r = MagicMock()
    r.text = json.dumps({"dimensions": dims, "summary": summary})
    r.usage_metadata.prompt_token_count = tokens_in
    r.usage_metadata.candidates_token_count = tokens_out
    return r


def _valid_dims() -> dict:
    return {"growth": 4, "profitability": 3, "management": 4, "innovation": 5, "resilience": 3}


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
        {"growth": 10, "profitability": 0, "management": 3, "innovation": 3, "resilience": 3}
    )

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())
    assert result.dimensions["growth"] == 5
    assert result.dimensions["profitability"] == 1


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
