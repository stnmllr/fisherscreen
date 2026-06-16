import base64
from unittest.mock import MagicMock

import httpx
import pytest

from app.errors import DataSourceError
from app.services.github_client import GitHubClientImpl


def _mock_http(get_status: int = 200, get_sha: str | None = "abc123") -> MagicMock:
    mock = MagicMock()
    get_resp = MagicMock()
    get_resp.status_code = get_status
    get_resp.json.return_value = {"sha": get_sha} if get_sha else {}
    mock.get.return_value = get_resp

    put_resp = MagicMock()
    put_resp.raise_for_status = MagicMock()
    mock.put.return_value = put_resp
    return mock


def test_push_file_calls_get_for_sha():
    http = _mock_http()
    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    client.push_file("output/Universum/2026-05-Dimensions.md", "# content", "chore: add monthly output")
    http.get.assert_called_once()


def test_push_file_sends_existing_sha_when_file_exists():
    http = _mock_http(get_status=200, get_sha="existing-sha")
    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    client.push_file("output/test.md", "content", "msg")
    put_call = http.put.call_args
    payload = put_call[1]["json"] if put_call[1] else put_call[0][1]
    assert payload.get("sha") == "existing-sha"


def test_push_file_omits_sha_when_file_does_not_exist():
    http = _mock_http(get_status=404, get_sha=None)
    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    client.push_file("output/new.md", "content", "msg")
    put_call = http.put.call_args
    payload = put_call[1]["json"] if put_call[1] else put_call[0][1]
    assert "sha" not in payload


def test_push_file_base64_encodes_content():
    http = _mock_http()
    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    client.push_file("output/test.md", "hello world", "msg")
    put_call = http.put.call_args
    payload = put_call[1]["json"] if put_call[1] else put_call[0][1]
    decoded = base64.b64decode(payload["content"]).decode()
    assert decoded == "hello world"


def test_push_file_wraps_http_error_in_data_source_error():
    http = _mock_http()
    http.put.return_value.raise_for_status.side_effect = Exception("HTTP 403")
    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    with pytest.raises(DataSourceError, match="GitHub push failed"):
        client.push_file("output/test.md", "content", "msg")


def test_push_file_http_error_includes_status_code_and_response_body():
    """A failing PUT must surface GitHub's status code AND response body.

    Regression for the 2026-06-12 prod incident: a 409 driven by a repo
    ruleset only carried its real cause in the response body, which httpx's
    generic HTTPStatusError message swallows.
    """
    http = _mock_http()
    put_resp = http.put.return_value
    put_resp.status_code = 409
    put_resp.text = '{"message": "Changes must be made through a pull request"}'
    request = httpx.Request("PUT", "https://api.github.com/repos/org/repo/contents/output/test.md")
    response = httpx.Response(409, request=request, text=put_resp.text)
    put_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Client error '409 Conflict' for url '...'",
        request=request,
        response=response,
    )

    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    with pytest.raises(DataSourceError) as exc_info:
        client.push_file("output/test.md", "content", "msg")

    message = str(exc_info.value)
    assert "409" in message
    assert "Changes must be made through a pull request" in message


def test_raises_on_empty_token():
    with pytest.raises(DataSourceError, match="GitHub token"):
        GitHubClientImpl(token="", repo="org/repo")


def test_push_file_strips_token_whitespace():
    """Token with trailing newline must not cause LocalProtocolError."""
    from unittest.mock import patch

    with patch("app.services.github_client.httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_client_cls.return_value = mock_http

        client = GitHubClientImpl(
            token="ghp_validtoken\n",  # newline as would come from echo | gcloud
            repo="owner/repo",
        )

        auth_header = client._headers["Authorization"]
        assert auth_header == "Bearer ghp_validtoken"
        assert "\n" not in auth_header


def test_push_file_retries_on_transient_timeout_and_refetches_sha():
    """A transient ReadTimeout on the first PUT must retry the WHOLE GET+PUT
    sequence (re-fetching the sha), then succeed without raising.

    Regression for the 2026-06-12 prod 500: a single transient network timeout
    must not throw away a ~31-minute run.
    """
    http = _mock_http(get_status=200, get_sha="existing-sha")
    http.put.side_effect = [httpx.ReadTimeout("timed out"), http.put.return_value]

    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    client.push_file("output/test.md", "content", "msg")  # must not raise

    # Re-fetching the sha on retry makes a possibly-applied PUT idempotent.
    assert http.get.call_count == 2
    assert http.put.call_count == 2


def test_push_file_exhausts_retries_on_persistent_timeout():
    """A persistent ReadTimeout exhausts the 3 attempts and raises DataSourceError."""
    http = _mock_http()
    http.put.side_effect = httpx.ReadTimeout("timed out")

    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    with pytest.raises(DataSourceError, match="GitHub push failed"):
        client.push_file("output/test.md", "content", "msg")

    assert http.put.call_count == 3  # stop_after_attempt(3)


def test_push_file_does_not_retry_http_status_error():
    """A 409 is deterministic: exactly ONE PUT attempt, body still surfaced."""
    http = _mock_http()
    put_resp = http.put.return_value
    put_resp.status_code = 409
    put_resp.text = '{"message": "Changes must be made through a pull request"}'
    request = httpx.Request("PUT", "https://api.github.com/repos/org/repo/contents/output/test.md")
    response = httpx.Response(409, request=request, text=put_resp.text)
    put_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Client error '409 Conflict' for url '...'",
        request=request,
        response=response,
    )

    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    with pytest.raises(DataSourceError) as exc_info:
        client.push_file("output/test.md", "content", "msg")

    assert http.put.call_count == 1  # not retried
    message = str(exc_info.value)
    assert "409" in message
    assert "Changes must be made through a pull request" in message


def test_default_client_gets_explicit_30s_timeout():
    """When no http client is injected, the self-built httpx.Client must use an
    explicit 30s timeout (httpx's default is 5s — the cause of the prod timeout)."""
    from unittest.mock import patch

    with patch("app.services.github_client.httpx.Client") as mock_client_cls:
        mock_client_cls.return_value = MagicMock()
        GitHubClientImpl(token="tok", repo="org/repo")

    _, kwargs = mock_client_cls.call_args
    assert kwargs.get("timeout") == 30.0
