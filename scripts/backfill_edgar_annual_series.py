r"""Vorwaermen von `dev_edgar_annual_series` fuer das gesamte Universum.

VOR dem Scharfschalten der Stetigkeits-Dimension laufen lassen, damit kein
Monatslauf den kalten companyfacts-Abruf bezahlt. Gemessen dauert der kalte
Durchlauf ueber die US-Titel 6,8 Minuten; der Monatslauf liegt bei ~23 Minuten
gegen eine harte 1800-s-Scheduler-Deadline (Spec 9.3). Ein Monatslauf, der den
Cache erstmalig fuellt, kaeme dieser Grenze gefaehrlich nahe.

Resumierbar ohne eigenen Zwischenstand: ein bereits gecachter Eintrag ist ein
Treffer und kostet keinen Request. Ein erneuter Aufruf holt also nur nach, was
fehlt oder abgelaufen ist.

Ein transienter Fehler bricht den Lauf NICHT ab -- bei 600+ Titeln ist ein
Netzaussetzer normal, und ein Abbruch nach 500 Titeln waere teurer als ein
zweiter Aufruf. Gezaehlt und am Ende benannt wird er trotzdem, und der
Exit-Code wird ungleich null, damit ein unvollstaendiger Lauf nicht wie ein
vollstaendiger aussieht.

Aufruf (cmd.exe):
  uv run python -m scripts.backfill_edgar_annual_series
  uv run python -m scripts.backfill_edgar_annual_series --limit 20
  uv run python -m scripts.backfill_edgar_annual_series --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_JSON = REPO_ROOT / "data" / "universe.json"

# Ab hier wird der Monatslauf knapp: 23 min Grundlast plus Nachladen gegen eine
# harte 1800-s-Deadline. Der Backfill warnt, wenn seine eigene Laufzeit zeigt,
# dass ein kalter Monatslauf das reissen wuerde.
COLD_RUN_BUDGET_SECONDS = 5 * 60


def is_us_ticker(ticker: str) -> bool:
    """Konvention aus app/screener/runner.py:263 -- ein Punkt markiert eine
    Nicht-US-Boerse, US-Klassenaktien tragen einen Bindestrich (BRK-B)."""
    return "." not in ticker


@dataclass
class BackfillStats:
    resolved: int = 0
    unresolved: list[str] = field(default_factory=list)
    warmed: int = 0
    negative: int = 0
    failed: list[str] = field(default_factory=list)
    seconds: float = 0.0


def resolve_ciks(tickers: Sequence[str], edgar: Any) -> tuple[list[str], list[str]]:
    """US-Ticker -> eindeutige CIK-Liste, plus die nicht aufloesbaren Ticker.

    Die CIKs werden dedupliziert: GOOG und GOOGL sind derselbe Emittent und
    teilen sich ein Dokument. Ohne das laedt der Backfill dieselbe Reihe
    zweimal."""
    ciks: list[str] = []
    seen: set[str] = set()
    unresolved: list[str] = []
    for ticker in tickers:
        if not is_us_ticker(ticker):
            continue
        cik = edgar.get_cik(ticker)
        if not cik:
            unresolved.append(ticker)
            continue
        padded = cik.zfill(10)
        if padded not in seen:
            seen.add(padded)
            ciks.append(padded)
    return ciks, unresolved


def backfill(ciks: Sequence[str], cache: Any, *, log_every: int = 25) -> BackfillStats:
    """Jede CIK einmal durch den Cache ziehen. Treffer kosten nichts."""
    stats = BackfillStats(resolved=len(ciks))
    started = time.monotonic()
    for n, cik in enumerate(ciks, start=1):
        try:
            record = cache.get_annual_series(cik)
        except Exception as exc:  # transient: zaehlen, weiterlaufen
            stats.failed.append(f"{cik}: {exc}")
            continue
        if record.usable:
            stats.warmed += 1
        else:
            stats.negative += 1
        if n % log_every == 0 or n == len(ciks):
            print(
                f"  [{n}/{len(ciks)}] warm {stats.warmed}, "
                f"negativ {stats.negative}, Fehler {len(stats.failed)}"
            )
    stats.seconds = round(time.monotonic() - started, 1)
    return stats


def report(stats: BackfillStats) -> None:
    print("")
    print(f"CIKs aufgeloest       {stats.resolved}")
    print(f"  davon mit Reihen    {stats.warmed}")
    print(f"  davon ohne Konzept  {stats.negative}")
    print(f"Ticker ohne CIK       {len(stats.unresolved)}")
    if stats.unresolved:
        print("  " + ", ".join(stats.unresolved[:25]))
    print(f"Fehler (nicht gecacht) {len(stats.failed)}")
    for line in stats.failed[:25]:
        print(f"  {line}")
    print(f"Laufzeit              {stats.seconds / 60:.1f} min")
    if stats.seconds > COLD_RUN_BUDGET_SECONDS:
        print(
            f"WARNUNG: {stats.seconds / 60:.1f} min kalt. Ein Monatslauf, der diesen "
            "Cache erstmalig fuellt, kommt der 1800-s-Deadline nahe (Spec 9.3) -- "
            "der Cache MUSS vor dem Scharfschalten warm sein."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="nur die ersten N CIKs")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="nur CIKs aufloesen und zaehlen, nichts abrufen und nichts schreiben",
    )
    args = parser.parse_args()

    from app.screener.compose import build_edgar_annual_series
    from app.services.edgar_client import EdgarClientImpl
    from app.config import settings

    if not settings.edgar_user_agent:
        print("FEHLER: FISHERSCREEN_EDGAR_USER_AGENT ist nicht gesetzt")
        return 2

    tickers = json.loads(UNIVERSE_JSON.read_text(encoding="utf-8"))
    edgar = EdgarClientImpl(
        user_agent=settings.edgar_user_agent,
        max_requests_per_second=settings.edgar_max_requests_per_second,
    )
    print(f"Universum {len(tickers)} Ticker -- loese CIKs auf ...")
    ciks, unresolved = resolve_ciks(tickers, edgar)
    if args.limit:
        ciks = ciks[: args.limit]
    print(f"{len(ciks)} eindeutige CIKs, {len(unresolved)} US-Ticker ohne CIK")

    if args.dry_run:
        stats = BackfillStats(resolved=len(ciks), unresolved=unresolved)
        report(stats)
        return 0

    cache = build_edgar_annual_series()
    stats = backfill(ciks, cache)
    stats.unresolved = unresolved
    report(stats)
    return 1 if stats.failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
