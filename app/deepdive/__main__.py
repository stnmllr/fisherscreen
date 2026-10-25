from __future__ import annotations

import argparse
import logging
import socket
import sys
from pathlib import Path

from app.deepdive.compose import (
    build_dossier_publisher,
    build_adr_resolver,
    build_filing_fetcher,
    build_insider_fetcher,
    build_peer_resolver,
    build_preflight_runner,
    build_quant_builder,
    build_synthesizer,
)

from app.deepdive.pipeline import run_deep_dive
from app.deepdive.publish import publish_dossier
from app.deepdive.preflight import format_preflight, parse_peer_arg
from app.config import settings
from app.errors import DataSourceError, DeepDiveError, GeminiError
from app.viewer.__main__ import main as render_site

logger = logging.getLogger(__name__)

# The viewer reads every dossier under <output_dir>/Watchlist and writes the
# site to <output_dir>/site — the same layout its own CLI defaults to.
WATCHLIST_DIRNAME = "Watchlist"
SITE_DIRNAME = "site"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fisherscreen", description="FisherScreen CLI"
    )
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
    deepdive.add_argument(
        "--site",
        action="store_true",
        help="After the dossier is written, re-render the static viewer site",
    )
    deepdive.add_argument(
        "--no-publish",
        action="store_true",
        help="Do not push the dossier to the dossier repo",
    )
    preflight = subparsers.add_parser(
        "preflight",
        help="Check ticker + peers and the expected dossier kind (no Gemini)",
    )
    preflight.add_argument("ticker", help="Ticker symbol, e.g. NOVO-B.CO")
    preflight.add_argument(
        "--peers",
        required=True,
        help="1-3 comma-separated peer tickers (fewer than 3 -> suggestions)",
    )
    return parser


def _run_preflight(args: argparse.Namespace) -> int:
    """Exit 0 if the deep dive could start, 1 otherwise (bad peers string or a
    failed check), 2 if a data source cannot even be set up (e.g. no EDGAR
    user agent) — the same code the deepdive command uses for that case."""
    try:
        peers = parse_peer_arg(args.peers)
    except DeepDiveError as exc:
        print(f"FEHLER: {exc}")
        return 1
    try:
        result = build_preflight_runner()(args.ticker, peers)
    except DataSourceError as exc:
        logger.error("preflight failed (data source): %s", exc)
        print(f"FEHLER: {exc}")
        return 2
    print(format_preflight(result))
    return 0 if result.can_start else 1


def _report_stale_site(dossier_path: Path) -> None:
    print(
        f"WARNING: the dossier is written to {dossier_path}, "
        "but the viewer site was NOT refreshed."
    )


def _refresh_site(output_dir: Path, dossier_path: Path) -> None:
    """Re-render the viewer site over the whole watchlist directory.

    Never raises and never propagates a failure into the exit code. By the
    time this runs, the dossier is on disk and a paid Gemini run has already
    happened; a broken renderer must not make that run look failed. Hence the
    broad `except Exception` — deliberate, and not a silent swallow: the
    traceback is logged and the user is told the site is stale. Do not "fix"
    this into a re-raise.
    """
    argv = [
        "--in",
        str(output_dir / WATCHLIST_DIRNAME),
        "--out",
        str(output_dir / SITE_DIRNAME),
    ]
    try:
        exit_code = render_site(argv)
    # SystemExit is in the net on purpose: the seam is a CLI entry point, so a
    # future argv change would surface as argparse calling sys.exit() — which
    # `except Exception` alone would let through and turn into exit code 2.
    # KeyboardInterrupt stays out: an abort by the user is not a renderer bug.
    except (Exception, SystemExit):
        logger.exception(
            "dossier written to %s, but the viewer site render crashed",
            dossier_path,
        )
        _report_stale_site(dossier_path)
        return
    # The viewer reports its own failures by returning non-zero, not by
    # raising, so the return value needs the same treatment as an exception.
    if exit_code != 0:
        logger.error(
            "dossier written to %s, but the viewer site render exited with %s",
            dossier_path,
            exit_code,
        )
        _report_stale_site(dossier_path)


def _publish(dossier_path: Path, *, no_publish: bool) -> None:
    """Push the dossier to the dossier repo and print exactly one status line.

    Never raises and never changes the exit code. By the time this runs, the
    dossier is on disk and a paid Gemini run has already happened; a publish
    problem must not make that run look failed. Hence the broad
    `except (Exception, SystemExit)` — deliberate, and not a silent swallow:
    the traceback is logged and the user gets a WARNING line. The builder is
    called here, after the run, so a half-configured setup (repo set, token
    empty) fails here instead of aborting before the paid run.
    """
    if no_publish:
        print("Dossier not published (--no-publish)")
        return
    try:
        github = build_dossier_publisher()
        if github is None:
            print("Dossier not published (no dossier repo configured)")
            return
        target = publish_dossier(
            dossier_path,
            github=github,
            repo=settings.dossier_repo,
            host=socket.gethostname(),
        )
    except (Exception, SystemExit) as exc:
        logger.exception("dossier written to %s, but publishing failed", dossier_path)
        print(f"WARNING: dossier NOT published: {_one_line_reason(exc)}")
        return
    print(f"Published to: {target}")


def _one_line_reason(exc: BaseException) -> str:
    """First non-empty line of the message, or the exception type name."""
    lines = [ln.strip() for ln in str(exc).splitlines() if ln.strip()]
    return lines[0] if lines else type(exc).__name__


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "preflight":
        return _run_preflight(args)
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
    # Flush first: the result the user paid for must be on screen before a
    # slow or chatty publisher/renderer gets a chance to bury it.
    sys.stdout.flush()
    _publish(out, no_publish=args.no_publish)
    if args.site:
        _refresh_site(Path(settings.output_dir), out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
