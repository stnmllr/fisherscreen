import json
from unittest.mock import MagicMock, patch

import pytest

from app.errors import GeminiError
from app.services.gemini_deepdive_client import GeminiDeepDiveClient


def _client(model="gemini-2.5-pro"):
    with patch("app.services.gemini_deepdive_client._genai") as g:
        c = GeminiDeepDiveClient(api_key="k", model=model)
        return c, g


def test_raises_without_api_key():
    with pytest.raises(GeminiError, match="API key"):
        GeminiDeepDiveClient(api_key="", model="gemini-2.5-pro")


def test_token_cap_exceeded_raises_no_generate():
    c, g = _client()
    c._client.models.count_tokens.return_value = MagicMock(total_tokens=999)
    with pytest.raises(GeminiError, match="prompt too large"):
        c.synthesize("sys", "user", max_input_tokens=10)
    c._client.models.generate_content.assert_not_called()


def test_returns_parsed_json_on_success():
    c, g = _client()
    c._client.models.count_tokens.return_value = MagicMock(total_tokens=5)
    resp = MagicMock()
    resp.text = json.dumps({"points": [{"number": 1}]})
    resp.usage_metadata = MagicMock(prompt_token_count=5, candidates_token_count=3)
    c._client.models.generate_content.return_value = resp
    out = c.synthesize("sys", "user", max_input_tokens=100)
    assert out["points"] == [{"number": 1}]


def test_invalid_json_raises_geminierror():
    c, g = _client()
    c._client.models.count_tokens.return_value = MagicMock(total_tokens=5)
    resp = MagicMock()
    resp.text = "not json"
    c._client.models.generate_content.return_value = resp
    with pytest.raises(GeminiError, match="invalid JSON"):
        c.synthesize("sys", "user", max_input_tokens=100)


def test_safety_filtered_empty_text_raises():
    c, g = _client()
    c._client.models.count_tokens.return_value = MagicMock(total_tokens=5)
    resp = MagicMock()
    resp.text = None
    c._client.models.generate_content.return_value = resp
    with pytest.raises(GeminiError, match="empty response"):
        c.synthesize("sys", "user", max_input_tokens=100)


def test_warns_at_80_percent_of_cap(caplog):
    import logging
    c, g = _client()
    c._client.models.count_tokens.return_value = MagicMock(total_tokens=85)
    resp = MagicMock()
    resp.text = '{"ok": true}'
    resp.usage_metadata = MagicMock(prompt_token_count=85, candidates_token_count=1)
    c._client.models.generate_content.return_value = resp
    with caplog.at_level(logging.WARNING,
                         logger="app.services.gemini_deepdive_client"):
        c.synthesize("sys", "user", max_input_tokens=100)
    assert ">80%" in caplog.text or "80%" in caplog.text
