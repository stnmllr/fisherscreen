"""CLI of the viewer: read dossiers, write the static site.

Deliberately without a deploy step. Phase 1 produces files; uploading them
happens outside, because a generator that writes to a server without being
asked is a surprise, not a convenience.

Local invocation (EPDR blocks the console-script shims):
    uv run python -m app.viewer --in output\\Watchlist --out build\\site
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.config import settings
from app.errors import ViewerError
from app.viewer.dossier_parser import iter_dossiers
from app.viewer.site_generator import generate_site, skipped_filenames

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fisherscreen-viewer",
        description="Render the static deep-dive viewer site",
    )
    parser.add_argument(
        "--in",
        dest="input_dir",
        type=Path,
        default=Path(settings.output_dir) / "Watchlist",
        help="Directory holding the Tool-B dossiers",
    )
    parser.add_argument(
        "--out",
        dest="output_dir",
        type=Path,
        default=Path(settings.output_dir) / "site",
        help="Directory the site is written to",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dossiers = iter_dossiers(args.input_dir)
        skipped = skipped_filenames(args.input_dir, dossiers)
        index_path = generate_site(dossiers, args.output_dir, skipped=skipped)
    except ViewerError as exc:
        logger.error("viewer failed: %s", exc)
        print(f"ERROR: {exc}")
        return 1
    read = len(list(args.input_dir.glob("*.md"))) - len(skipped)
    print(
        f"Site written to: {index_path} · tickers: {len(dossiers)} · "
        f"dossiers read: {read} · files skipped: {len(skipped)}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
