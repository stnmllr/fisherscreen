from __future__ import annotations

from app.deepdive.adr_table import load_adr_table
from app.screener.compose import build_github_client

__all__ = ["build_adr_table", "build_github_client"]


def build_adr_table() -> dict[str, dict[str, str]]:
    """Composition entrypoint for the static ADR table.

    B.1-2 builds the full resolve() service on top of this loader.
    """
    return load_adr_table()
