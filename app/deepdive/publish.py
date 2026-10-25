from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)

DOSSIER_REPO_DIR: Final[str] = "Watchlist"


def publish_dossier(path: Path, *, github: GitHubClient, repo: str, host: str) -> str:
    """Push a dossier file to ``Watchlist/<name>`` in the dossier repo.

    The file name is ``<TICKER>_<YYYY-MM-DD>.md``; ticker and date are split at
    the last underscore. ``DataSourceError`` from the client propagates.
    Returns ``<repo>/Watchlist/<name>``.
    """
    ticker, date = path.stem.rsplit("_", 1)
    target = f"{DOSSIER_REPO_DIR}/{path.name}"
    github.push_file(
        target,
        path.read_text(encoding="utf-8"),
        f"Publish {ticker} deep dive {date} ({host})",
    )
    logger.info("Published dossier to %s/%s", repo, target)
    return f"{repo}/{target}"
