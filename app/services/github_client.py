from __future__ import annotations

import base64
import logging
from typing import Protocol

import httpx

from app.errors import DataSourceError

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


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
        self._http = http or httpx.Client()

    def push_file(self, path: str, content: str, commit_message: str) -> None:
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

        try:
            put_resp = self._http.put(url, json=payload, headers=self._headers)
            put_resp.raise_for_status()
        except Exception as exc:
            raise DataSourceError(f"GitHub push failed for {path}: {exc}") from exc

        logger.info("github: pushed %s to %s@%s", path, self._repo, self._branch)
