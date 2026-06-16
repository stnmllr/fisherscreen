from __future__ import annotations

import base64
import logging
from typing import Protocol

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.errors import DataSourceError

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"

# httpx's default timeout is 5s; the monthly run's PUT to the ruleset-protected
# main branch exceeded that and raised ReadTimeout -> 500, killing a ~31-min run.
_HTTP_TIMEOUT_SECONDS = 30.0

# Retry the WHOLE GET-sha + PUT sequence on transient transport errors only.
# Re-fetching the sha each attempt keeps a possibly-applied PUT idempotent
# (a stale sha would 409). HTTPStatusError (e.g. a deterministic 409/403) is
# NOT retried — the existing body-surfacing must stay immediate.
_GITHUB_RETRY = dict(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.05),
    reraise=True,
)


class GitHubClient(Protocol):
    def push_file(self, path: str, content: str, commit_message: str) -> None: ...


class GitHubClientImpl:
    def __init__(
        self,
        token: str,
        repo: str,
        branch: str = "main",
        http: httpx.Client | None = None,
    ) -> None:
        if not token:
            raise DataSourceError("GitHub token not set — configure FISHERSCREEN_GITHUB_TOKEN")
        self._headers = {
            "Authorization": f"Bearer {token.strip()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._repo = repo
        self._branch = branch
        self._http = http or httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS)

    def push_file(self, path: str, content: str, commit_message: str) -> None:
        try:
            self._get_sha_and_put(path, content, commit_message)
        except httpx.HTTPStatusError as exc:
            # Surface the response body: httpx's generic message omits GitHub's
            # actual reason (e.g. a ruleset 409), which only lives in the body.
            raise DataSourceError(
                f"GitHub push failed for {path}: "
                f"{exc.response.status_code} {exc.response.text}"
            ) from exc
        except Exception as exc:
            raise DataSourceError(f"GitHub push failed for {path}: {exc}") from exc

        logger.info("github: pushed %s to %s@%s", path, self._repo, self._branch)

    @retry(**_GITHUB_RETRY)
    def _get_sha_and_put(self, path: str, content: str, commit_message: str) -> None:
        """GET the current sha then PUT the new content as one retryable unit.

        Retried as a whole on transient transport errors: the sha is re-fetched
        each attempt so a PUT that reached GitHub but timed out on the response
        does not 409 on retry with a stale sha.
        """
        url = f"{_GITHUB_API}/repos/{self._repo}/contents/{path}"
        get_resp = self._http.get(url, params={"ref": self._branch}, headers=self._headers)
        sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

        payload: dict[str, str] = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode(),
            "branch": self._branch,
        }
        if sha:
            payload["sha"] = sha

        put_resp = self._http.put(url, json=payload, headers=self._headers)
        put_resp.raise_for_status()
