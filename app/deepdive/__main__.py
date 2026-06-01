from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.deepdive.compose import (
    build_adr_resolver,
    build_filing_fetcher,
    build_insider_fetcher,
    build_peer_resolver,
    build_quant_builder,
    build_synthesizer,
)
from app.deepdive.pipeline import run_deep_dive
from app.config import settings
from app.errors import DataSourceError, DeepDiveError, GeminiError

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
    deepdive.add_argument(
        "--peers",
        default=None,
        help="Exactly 3 comma-separated peer tickers (non-interactive)",
    )
    deepdive.add_argument(
        "--peer-rationale",
        default=None,
        help="Optional rationale for the peer selection (<=200 chars)",
    )
    deepdive.add_argument(
        "--no-insider",
        action="store_true",
        help="Skip the Form-4 insider stage (faster iteration)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        out = run_deep_dive(
            args.ticker,
            output_dir=Path(settings.output_dir),
            resolver=build_adr_resolver(),
            filing_fetcher=build_filing_fetcher(),
            build_quant=build_quant_builder(),
            synthesizer=build_synthesizer(args.model),
            token_cap=settings.deepdive_token_cap,
            use_cache=not args.no_cache,
            peers=args.peers,
            peer_rationale=args.peer_rationale,
            is_tty=sys.stdin.isatty(),
            peer_resolver=build_peer_resolver(),
            insider_fetcher=build_insider_fetcher(),
            insider_lookback_days=settings.insider_lookback_days,
            no_insider=args.no_insider,
        )
    except DeepDiveError as exc:
        logger.error("deepdive failed (ticker): %s", exc)
        print(f"ERROR: {exc}")
        return 1
    except DataSourceError as exc:
        logger.error("deepdive failed (data source): %s", exc)
        print(f"ERROR: {exc}")
        return 2
    except GeminiError as exc:
        logger.error("deepdive failed (gemini): %s", exc)
        print(f"ERROR: {exc}")
        return 3
    print(f"Dossier written to: {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
