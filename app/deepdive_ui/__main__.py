"""Entry point of the deep-dive start UI.

Local (cmd.exe, EPDR blocks the console-script shims):
    uv run python -m app.deepdive_ui

Listens on 127.0.0.1:8765 by default (FISHERSCREEN_DEEPDIVE_UI_HOST/_PORT).
This is the only place that wires the real dependencies.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI

from app.config import FisherScreenSettings, settings
from app.deepdive.compose import build_preflight_runner
from app.deepdive_ui.runs import REPO_ROOT, RunManager
from app.deepdive_ui.server import PeersLookup, create_app
from app.logging_config import configure_logging
from app.services.firestore_client import FirestoreClientImpl


def build_peers_lookup(cfg: FisherScreenSettings) -> PeersLookup:
    """Firestore get on the peers collection, with a fresh client per call.

    Lazy on purpose: a Firestore outage at UI start must not keep the page
    from loading, and FirestoreClientImpl raises DataSourceError (-> 503).
    """

    def lookup(ticker: str) -> dict[str, Any] | None:
        client = FirestoreClientImpl(cfg.gcp_project_id)
        return client.get(cfg.deepdive_peers_collection, ticker)

    return lookup


def resolve_runs_dir(cfg: FisherScreenSettings) -> Path:
    runs_dir = Path(cfg.deepdive_ui_runs_dir)
    return runs_dir if runs_dir.is_absolute() else REPO_ROOT / runs_dir


def build_app(cfg: FisherScreenSettings) -> FastAPI:
    return create_app(
        preflight=build_preflight_runner(),
        peers_lookup=build_peers_lookup(cfg),
        run_manager=RunManager(resolve_runs_dir(cfg)),
        root_path=cfg.deepdive_ui_root_path,
        viewer_url=cfg.deepdive_ui_viewer_url,
        preflight_ttl_minutes=cfg.deepdive_ui_preflight_ttl_minutes,
    )


def build_parser(cfg: FisherScreenSettings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fisherscreen-deepdive-ui",
        description="Start the local deep-dive UI (pre-check + start of Tool B)",
    )
    parser.add_argument("--host", default=cfg.deepdive_ui_host)
    parser.add_argument("--port", type=int, default=cfg.deepdive_ui_port)
    return parser


def main(argv: list[str] | None = None, cfg: FisherScreenSettings = settings) -> int:
    args = build_parser(cfg).parse_args(argv)
    configure_logging()
    uvicorn.run(build_app(cfg), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
