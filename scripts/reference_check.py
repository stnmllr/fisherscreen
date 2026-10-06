"""Gegentest (Recall) fuer Tool A: wo bleiben bekannte Qualitaetsfirmen haengen?

Liest NUR die Artefakte eines fertigen Monatslaufs -- kein Netz, kein Geld:

  data/universe.json                       Universum des Laufs
  data/reference_fisher.json               handverlesene Referenzliste
  output/Universum/<Monat>-dropouts.csv    Stufe + Grund jedes ausgeschiedenen Titels

Fuer jeden Referenz-Titel: nicht im Universum / an welcher Stufe ausgeschieden /
Crosshit. Bei Titeln, die erst am Crosshit-Gate scheitern, zeigt die Spalte
"Achsen" die Scores und markiert die Achsen unter der Schwelle -- das setzt voraus,
dass der Lauf die Achsen-Scores in die `detail`-Spalte schreibt (ab Branch
bugfix/crosshits-list-honours-steadiness-gate). Aeltere Laeufe zeigen dort "—".

Aufruf:
    uv run python scripts\\reference_check.py                 (juengster Lauf)
    uv run python scripts\\reference_check.py --month 2026-10
    uv run python scripts\\reference_check.py --month 2026-10 ^
        --dropouts <sim-dir>\\2026-10-dropouts.csv --out <sim-dir>\\2026-10-Referenzcheck.md

Schreibt output/Universum/<Monat>-Referenzcheck.md und eine Kurzfassung auf die Konsole.
`--dropouts` / `--out` lenken Ein- und Ausgabe um -- fuer die Offline-Simulation
(scripts/simulate_month_scoring.py), die einen Lauf neu bewertet, ohne die echten
Artefakte anzufassen.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
UNIVERSUM_DIR = ROOT / "output" / "Universum"
THRESHOLD = 4.0

STAGE_LABEL = {
    "resolution": "Datenauflösung",
    "basis_gates": "Basis-Gates",
    "edgar_gates": "EDGAR-Gates",
    "scoring": "Scoring",
    "crosshits": "Crosshit-Gate",
}


def latest_month() -> str:
    months = sorted(p.name[:7] for p in UNIVERSUM_DIR.glob("????-??-dropouts.csv"))
    if not months:
        sys.exit(f"keine *-dropouts.csv in {UNIVERSUM_DIR}")
    return months[-1]


def parse_axes(detail: str) -> dict[str, str]:
    """'growth=4 profitability=5 resilience=3 steadiness=4.67' -> dict."""
    axes = {}
    for part in detail.split():
        if "=" in part:
            key, value = part.split("=", 1)
            axes[key] = value
    return axes


def failing_axes(axes: dict[str, str]) -> list[str]:
    failing = []
    for key, value in axes.items():
        try:
            if float(value) < THRESHOLD:
                failing.append(key)
        except ValueError:  # n/a, n/a(<reason>) -> neutral, never a failure
            continue
    return failing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--month", help="YYYY-MM (Default: juengster Lauf)")
    parser.add_argument(
        "--dropouts",
        type=Path,
        help="dropouts-CSV (Default: output/Universum/<Monat>-dropouts.csv)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Ausgabe-Markdown (Default: output/Universum/<Monat>-Referenzcheck.md)",
    )
    args = parser.parse_args()
    month = args.month or latest_month()

    universe = set(json.loads((ROOT / "data" / "universe.json").read_text("utf-8")))
    reference = json.loads(
        (ROOT / "data" / "reference_fisher.json").read_text("utf-8")
    )["tickers"]
    dropouts_path = args.dropouts or UNIVERSUM_DIR / f"{month}-dropouts.csv"
    with dropouts_path.open(encoding="utf-8", newline="") as fh:
        dropouts = {row["ticker"]: row for row in csv.DictReader(fh)}

    rows = []
    for group, tickers in reference.items():
        for ticker in tickers:
            if ticker not in universe:
                rows.append((group, ticker, "nicht im Universum", "", "", []))
                continue
            drop = dropouts.get(ticker)
            if drop is None:
                rows.append((group, ticker, "✅ Crosshit", "", "", []))
                continue
            axes = parse_axes(drop.get("detail", "")) if drop["stage"] == "crosshits" else {}
            rows.append(
                (
                    group,
                    ticker,
                    STAGE_LABEL.get(drop["stage"], drop["stage"]),
                    drop["reason_code"],
                    drop.get("detail", ""),
                    failing_axes(axes),
                )
            )

    by_stage = Counter(r[2] for r in rows)
    by_axis = Counter(a for r in rows for a in r[5])
    at_gate = sum(1 for r in rows if r[2] == STAGE_LABEL["crosshits"])
    with_axes = sum(1 for r in rows if r[2] == STAGE_LABEL["crosshits"] and r[4])

    lines = [
        f"# Referenzcheck {month}",
        "",
        f"Referenzliste: `data/reference_fisher.json` · {len(rows)} Titel · "
        f"Schwelle {THRESHOLD}",
        "",
        "## Wo die Referenz-Titel bleiben",
        "",
        "| Stufe | Anzahl |",
        "|---|---|",
    ]
    lines += [f"| {stage} | {n} |" for stage, n in by_stage.most_common()]
    if at_gate:
        lines += ["", "## Woran sie am Crosshit-Gate scheitern", ""]
        if with_axes:
            lines += [
                f"Achsen unter {THRESHOLD} (ein Titel kann an mehreren scheitern; "
                f"{with_axes} von {at_gate} Titeln mit Achsen-Detail):",
                "",
                "| Achse | Titel |",
                "|---|---|",
            ]
            lines += [f"| {axis} | {n} |" for axis, n in by_axis.most_common()]
        else:
            lines += [
                "> Dieser Lauf schreibt noch keine Achsen-Scores in die dropouts-CSV "
                "— erst ab dem naechsten Lauf mit dem Fix sichtbar."
            ]
    lines += [
        "",
        "## Alle Titel",
        "",
        "| Gruppe | Ticker | Stufe | Grund | Achsen | unter Schwelle |",
        "|---|---|---|---|---|---|",
    ]
    for group, ticker, stage, reason, detail, failing in rows:
        lines.append(
            f"| {group} | {ticker} | {stage} | {reason} | {detail or '—'} "
            f"| {', '.join(failing) or '—'} |"
        )

    out = args.out or UNIVERSUM_DIR / f"{month}-Referenzcheck.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Referenzcheck {month}: {len(rows)} Titel")
    for stage, n in by_stage.most_common():
        print(f"  {stage:<22} {n}")
    if by_axis:
        print("  Achsen unter Schwelle: " + ", ".join(f"{a} {n}" for a, n in by_axis.most_common()))
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"geschrieben: {shown}")


if __name__ == "__main__":
    main()
