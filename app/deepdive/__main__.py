from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fisherscreen", description="FisherScreen CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    deepdive = subparsers.add_parser(
        "deepdive", help="Run a Tool B deep dive on one ticker"
    )
    deepdive.add_argument("ticker", help="Ticker symbol, e.g. NOVO-B.CO")
    deepdive.add_argument(
        "--model", default=None, help="Override the Gemini synthesis model"
    )
    deepdive.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore the local filing/historical caches",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger.info(
        "deepdive skeleton invoked for ticker=%s — pipeline lands in Phase B.1",
        args.ticker,
    )
    print(
        f"deepdive '{args.ticker}': Tool B skeleton (Phase B.0). "
        "The deep-dive pipeline is implemented in Phase B.1."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
