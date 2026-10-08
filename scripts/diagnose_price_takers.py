r"""Diagnose: Preisnehmer ausschliessen statt nur kennzeichnen -- Schritt 1, nur Analyse.

Bewertet den Monat auf EINEM Cache-Snapshot dreimal:

  base  Produktivcode (Preisnehmer nur markiert)
  gate  Preisnehmer zaehlen nicht als Crosshit; Scores und Perzentile unveraendert
  cut   Preisnehmer vor dem Scoring aus der Kohorte -- die Perzentile der uebrigen
        Titel verschieben sich, kleine Sektoren koennen unter MIN_SECTOR_N fallen

Dazu: wer laut Tabelle Preisnehmer ist (je Industrie), welche Rohstoff-nahen
Industrien NICHT in der Tabelle stehen, und die Industrien der Crosshits.
NUR LESEN, $0.

Aufruf:
    uv run python scripts\diagnose_price_takers.py --month 2026-10
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from simulate_month_scoring import (
    DEFAULT_CIK_MAP,
    MIN_DIMENSIONS,
    ROOT,
    THRESHOLD,
    build_and_score,
    load_inputs,
)

from app.config import settings
from app.models.screener_record import ScreenerRecord
from app.screener.dimensions import is_crosshit
from app.screener.price_takers import is_price_taker, load_price_takers
from app.screener.sector_percentiles import MIN_SECTOR_N

sys.stdout.reconfigure(encoding="utf-8")

COMMODITY_SECTORS = ("Basic Materials", "Energy")


def axes(r: ScreenerRecord) -> str:
    d = r.gemini_dimensions or {}
    st = "n/a" if r.steadiness is None else f"{r.steadiness:.2f}"
    return f"g{d.get('growth')} p{d.get('profitability')} r{d.get('resilience')} s{st}"


def crosshits(recs: dict[str, ScreenerRecord]) -> set[str]:
    return {t for t, r in recs.items() if is_crosshit(r, THRESHOLD, MIN_DIMENSIONS)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--cik-map", type=Path, default=DEFAULT_CIK_MAP)
    args = ap.parse_args()

    _, _, cohort, cik_map, store = load_inputs(args.month, args.cik_map, False)
    table = load_price_takers(ROOT / "data" / "price_takers.json")
    reference = {
        t
        for group in json.loads((ROOT / "data" / "reference_fisher.json").read_text("utf-8"))[
            "tickers"
        ].values()
        for t in group
    }

    base = {r.ticker: r for r in build_and_score(store, cohort, cik_map)[0]}
    takers = {t for t, r in base.items() if is_price_taker(t, r.gics_industry, table)}
    cut = {
        r.ticker: r
        for r in build_and_score(store, [t for t in cohort if t not in takers], cik_map)[0]
    }

    cb = crosshits(base)
    cg = cb - takers
    cc = crosshits(cut)

    print("## Wirkung\n")
    print("| Variante | Crosshits | Referenz | Preisnehmer unter den Crosshits |")
    print("|---|---|---|---|")
    for name, cs in (("base (nur markiert)", cb), ("gate (nicht als Crosshit)", cg),
                     ("cut (vor dem Scoring raus)", cc)):
        print(f"| {name} | {len(cs)} | {len(cs & reference)}/{len(reference)} "
              f"| {len(cs & takers)} |")
    print(f"\nPreisnehmer-Crosshits in base: {sorted(cb & takers)}")
    print(f"cut gegen gate: neu {sorted(cc - cg)}; raus {sorted(cg - cc)}")
    for t in sorted((cc - cg) | (cg - cc)):
        print(f"  - {t} ({base[t].gics_sector} / {base[t].gics_industry}): "
              f"base {axes(base[t])} -> cut {axes(cut[t])}")

    print("\n## Sektorgroessen (cut) und globaler Rueckfall\n")
    size_b = Counter(r.gics_sector for r in base.values())
    size_c = Counter(r.gics_sector for r in cut.values())
    for s in sorted(size_b, key=lambda s: -size_b[s]):
        flag = " ← unter MIN_SECTOR_N, faellt auf global zurueck" if (
            size_b[s] >= MIN_SECTOR_N > size_c[s]) else ""
        if size_b[s] != size_c[s]:
            print(f"- {s}: {size_b[s]} -> {size_c[s]}{flag}")
    moved = Counter()
    for t, r in cut.items():
        b = base[t].gemini_dimensions or {}
        c = r.gemini_dimensions or {}
        for axis in ("growth", "profitability", "resilience"):
            if b.get(axis) != c.get(axis):
                moved[(r.gics_sector, axis)] += 1
    print("Score-Aenderungen der Nicht-Preisnehmer durch den Schnitt (Sektor, Achse): "
          + (", ".join(f"{s}/{a}: {n}" for (s, a), n in moved.most_common()) or "keine"))

    print("\n## Preisnehmer in der Kohorte nach Industrie\n")
    by_ind: dict[str, list[str]] = defaultdict(list)
    for t in sorted(takers):
        key = base[t].gics_industry if base[t].gics_industry in table.industries else f"Override ({t})"
        by_ind[key].append(t)
    for ind, ts in sorted(by_ind.items(), key=lambda kv: -len(kv[1])):
        shown = ", ".join(f"{t}{' ✅' if t in cb else ''}" for t in ts)
        print(f"- **{ind}** ({len(ts)}): {shown}")
    print("\n(✅ = Crosshit in base)")

    print("\n## Rohstoff-Sektoren: Industrien NICHT in der Tabelle\n")
    rest: dict[tuple[str, str], list[str]] = defaultdict(list)
    for t, r in base.items():
        if r.gics_sector in COMMODITY_SECTORS and t not in takers:
            rest[(r.gics_sector, r.gics_industry or "?")].append(t)
    for (s, ind), ts in sorted(rest.items()):
        shown = ", ".join(f"{t}{' ✅' if t in cb else ''}" for t in sorted(ts))
        print(f"- {s} / **{ind}** ({len(ts)}): {shown}")

    print("\n## Industrien der Crosshits (base)\n")
    for ind, n in Counter(base[t].gics_industry for t in cb).most_common():
        members = sorted(t for t in cb if base[t].gics_industry == ind)
        print(f"- {ind}: {n} — {', '.join(members)}")

    cached = sum(1 for t in cohort if store.peek(settings.revenue_series_collection, t))
    print(f"\n(Snapshot: {len(base)} bewertet, {cached} Umsatzreihen im Cache)")


if __name__ == "__main__":
    main()
