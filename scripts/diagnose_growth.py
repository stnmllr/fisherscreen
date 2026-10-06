r"""Diagnose: Mehrjahres-Umsatz-CAGR statt Quartals-YoY in der growth-Achse --
Schritt 1, nur Analyse.

Bewertet den Monat mit dem Produktivcode (yoy) und den Varianten aus
simulate_month_scoring (`--growth cagr|blend`, `--growth-missing fallback|cap3`)
auf denselben Caches und beantwortet:

  A  Abdeckung: wie viele Geschaeftsjahre je Titel, wer hat keine CAGR (<4 GJ)?
  B  fehlende CAGR: wen trifft "Quartal mit Deckel 4" gegenueber "Deckel 3"?
  C  Zyklik: Preisnehmer-Anteil und die bekannten Rohstofffaelle
  D  Aktualitaet: Alter des Cache-Eintrags (das GJ-Datum steht nicht im Cache) und
     wie oft CAGR und Quartal sich stark widersprechen

NUR LESEN, $0 -- dieselben Read-only-Adapter wie die Simulation.

Aufruf:
    uv run python scripts\diagnose_growth.py --month 2026-10
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from simulate_month_scoring import (
    DEFAULT_CIK_MAP,
    MIN_DIMENSIONS,
    ROOT,
    THRESHOLD,
    build_and_score,
    load_inputs,
    revenue_cagrs,
)

from app.config import settings
from app.models.screener_record import ScreenerRecord
from app.screener.dimensions import is_crosshit
from app.screener.price_takers import is_price_taker, load_price_takers

sys.stdout.reconfigure(encoding="utf-8")

FOCUS = ["MA", "V", "MTD", "AAPL", "MSFT", "KLAC", "ISRG", "MCO"]
COUNTER_PROBES = [
    "HL", "EDV.L", "NEM", "RGLD",  # Rohstoffe
    "NVDA", "SNDK",  # Quartals-Ausreisser nach oben
    "NESN.SW", "MC.PA",  # Defensive mit schwachem Quartal
    "RDDT",  # junge Notierung
    "ADYEN.AS", "MNST", "KRYS",  # Wechsler laut Simulation
]
VARIANTS = [
    ("cagr", "fallback"),
    ("cagr", "cap3"),
    ("blend", "fallback"),
    ("cagr-median", "fallback"),
    ("blend-median", "fallback"),
]
# |CAGR - Quartals-YoY| ab hier gilt als starker Widerspruch
CONFLICT_GAP = 0.20


def dim(r: ScreenerRecord, axis: str) -> int | None:
    return (r.gemini_dimensions or {}).get(axis)


def cross(recs: dict[str, ScreenerRecord]) -> set[str]:
    return {t for t, r in recs.items() if is_crosshit(r, THRESHOLD, MIN_DIMENSIONS)}


def fmt(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def table(base, variants, cagrs, medians, years) -> None:
    keys = [f"{g}/{m}" for g, m in VARIANTS]
    print("\n## Tabelle growth: alt (Quartals-YoY) gegen Varianten\n")
    print("| Ticker | Sektor | GJ | YoY (P) | CAGR | Median-Wachstum | growth alt | " + " | ".join(keys)
          + " | Crosshit alt | Crosshit " + " | ".join(keys) + " |")
    print("|---|---|---|---|---|---|---|" + "---|" * len(keys) + "---|" + "---|" * len(keys))
    for t in FOCUS + ["—"] + COUNTER_PROBES:
        if t == "—":
            print("| **Gegenproben** |" + " |" * (7 + 2 * len(keys)))
            continue
        if t not in base:
            print(f"| {t} | nicht in der Scoring-Kohorte |" + " |" * (6 + 2 * len(keys)))
            continue
        b = base[t]
        p = (b.input_percentiles or {}).get("revenue_growth_yoy")
        yoy = f"{fmt(b.revenue_growth_yoy)} ({'—' if p is None else f'P{p:.0f}'})"
        scores = " | ".join(str(dim(variants[k][t], "growth")) for k in keys)
        ch = " | ".join("✅" if is_crosshit(variants[k][t], THRESHOLD, MIN_DIMENSIONS) else "—"
                        for k in keys)
        print(f"| {t} | {b.gics_sector} | {years[t]} | {yoy} | {fmt(cagrs[t])} | {fmt(medians[t])} | {dim(b, 'growth')} "
              f"| {scores} | {'✅' if is_crosshit(b, THRESHOLD, MIN_DIMENSIONS) else '—'} | {ch} |")


def effect(base, variants, takers_table) -> None:
    print("\n## Wirkung gegen Basis (main)\n")
    cb = cross(base)
    def taker_share(cs: set[str], recs) -> str:
        n = sum(1 for t in cs if is_price_taker(t, recs[t].gics_industry, takers_table))
        return f"{n}/{len(cs)} = {n / len(cs):.1%}" if cs else "—"
    print(f"Basis: {len(cb)} Crosshits, Preisnehmer {taker_share(cb, base)}")
    for k, recs in variants.items():
        cv = cross(recs)
        d = Counter(dim(r, "growth") for r in recs.values())
        print(f"\n### {k}\n- Crosshits {len(cb)} -> {len(cv)}; neu {sorted(cv - cb)}; raus {sorted(cb - cv)}")
        print(f"- Preisnehmer {taker_share(cv, recs)}")
        print("- growth: " + " ".join(f"{s}:{d[s]}" for s in range(6)) + f"  (>=4: {d[4] + d[5]})")
        for t in sorted(cb - cv):
            r = recs[t]
            print(f"  - raus {t}: {(r.gemini_evidence or {}).get('growth')} -> growth {dim(r, 'growth')}")


def coverage(base, years) -> None:
    print("\n## A — Abdeckung (Geschaeftsjahre in der Umsatzreihe)\n")
    by_region: dict[str, Counter] = defaultdict(Counter)
    by_sector: dict[str, Counter] = defaultdict(Counter)
    for t, r in base.items():
        by_region["EU" if "." in t else "US"][years[t]] += 1
        by_sector[r.gics_sector or "?"][years[t]] += 1
    for label, groups in (("Region", by_region), ("Sektor", by_sector)):
        for g, c in sorted(groups.items(), key=lambda kv: -sum(kv[1].values())):
            n = sum(c.values())
            ok = sum(v for y, v in c.items() if y >= 4)
            print(f"- {label} {g}: n={n}, CAGR definiert {ok} ({ok / n:.0%}); GJ-Verteilung "
                  + " ".join(f"{y}:{c[y]}" for y in sorted(c)))


def missing(base, variants, cagrs) -> None:
    print("\n## B — ohne CAGR (<4 GJ)\n")
    miss = sorted(t for t in base if cagrs[t] is None)
    print(f"{len(miss)} Titel. growth je Variante, nur wo sich fallback und cap3 unterscheiden:\n")
    print("| Ticker | Sektor | YoY | growth alt | cagr/fallback | cagr/cap3 | Crosshit fallback | Crosshit cap3 |")
    print("|---|---|---|---|---|---|---|---|")
    for t in miss:
        f, c = variants["cagr/fallback"][t], variants["cagr/cap3"][t]
        if dim(f, "growth") == dim(c, "growth"):
            continue
        print(f"| {t} | {base[t].gics_sector} | {fmt(base[t].revenue_growth_yoy)} | {dim(base[t], 'growth')} "
              f"| {dim(f, 'growth')} | {dim(c, 'growth')} "
              f"| {'✅' if is_crosshit(f, THRESHOLD, MIN_DIMENSIONS) else '—'} "
              f"| {'✅' if is_crosshit(c, THRESHOLD, MIN_DIMENSIONS) else '—'} |")


def cyclicals(base, variants, cagrs, takers_table) -> None:
    print("\n## C — Preisnehmer: growth alt gegen cagr/fallback\n")
    takers = sorted(t for t, r in base.items() if is_price_taker(t, r.gics_industry, takers_table))
    up = [t for t in takers if (dim(variants["cagr/fallback"][t], "growth") or 0) > (dim(base[t], "growth") or 0)]
    down = [t for t in takers if (dim(variants["cagr/fallback"][t], "growth") or 0) < (dim(base[t], "growth") or 0)]
    print(f"{len(takers)} Preisnehmer in der Kohorte; growth hoeher {len(up)}, niedriger {len(down)}")
    for t in up:
        print(f"- hoeher {t}: YoY {fmt(base[t].revenue_growth_yoy)}, CAGR {fmt(cagrs[t])}, "
              f"{dim(base[t], 'growth')} -> {dim(variants['cagr/fallback'][t], 'growth')}")


def staleness_and_conflict(base, cagrs, store) -> None:
    print("\n## D — Aktualitaet und Widersprueche\n")
    now = datetime.now(timezone.utc)
    ages = []
    for t in base:
        doc = store.peek(settings.revenue_series_collection, t) or {}
        raw = doc.get("_cached_at")
        if raw:
            ages.append((now - datetime.fromisoformat(raw)).days)
    ages.sort()
    if ages:
        q = lambda f: ages[min(len(ages) - 1, int(f * len(ages)))]  # noqa: E731
        print(f"Alter Cache-Eintrag (Tage): n={len(ages)}, Median {q(0.5)}, P90 {q(0.9)}, max {ages[-1]}; "
              f"> 365 d: {sum(1 for a in ages if a > 365)}")
    print("(Das Datum des letzten Geschaeftsjahres steht nicht im Cache; es liegt bis zu ~1 Jahr "
          "vor dem Eintrag.)\n")
    conflicts = [(t, base[t].revenue_growth_yoy, cagrs[t]) for t in base
                 if cagrs[t] is not None and base[t].revenue_growth_yoy is not None
                 and abs(base[t].revenue_growth_yoy - cagrs[t]) > CONFLICT_GAP]
    print(f"|YoY - CAGR| > {CONFLICT_GAP:.0%}: {len(conflicts)} Titel")
    weak_now = sorted((t for t, y, c in conflicts if y < c), key=lambda t: base[t].revenue_growth_yoy - cagrs[t])
    hot_now = sorted((t for t, y, c in conflicts if y > c), key=lambda t: cagrs[t] - base[t].revenue_growth_yoy)
    print(f"- Quartal deutlich schwaecher als CAGR ({len(weak_now)}): "
          + ", ".join(f"{t} ({fmt(base[t].revenue_growth_yoy)} vs {fmt(cagrs[t])})" for t in weak_now[:15]))
    print(f"- Quartal deutlich staerker als CAGR ({len(hot_now)}): "
          + ", ".join(f"{t} ({fmt(base[t].revenue_growth_yoy)} vs {fmt(cagrs[t])})" for t in hot_now[:15]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--cik-map", type=Path, default=DEFAULT_CIK_MAP)
    args = ap.parse_args()

    _, _, cohort, cik_map, store = load_inputs(args.month, args.cik_map, False)
    base = {r.ticker: r for r in build_and_score(store, cohort, cik_map)[0]}
    variants = {
        f"{g}/{m}": {r.ticker: r for r in build_and_score(store, cohort, cik_map, "roe", g, m)[0]}
        for g, m in VARIANTS
    }
    tickers = list(base)
    cagrs = revenue_cagrs(store, tickers)
    medians = revenue_cagrs(store, tickers, "median")
    years = {}
    for t in tickers:
        doc = store.peek(settings.revenue_series_collection, t) or {}
        years[t] = len(doc.get("revenues", []))
    takers_table = load_price_takers(ROOT / "data" / "price_takers.json")

    table(base, variants, cagrs, medians, years)
    effect(base, variants, takers_table)
    coverage(base, years)
    missing(base, variants, cagrs)
    cyclicals(base, variants, cagrs, takers_table)
    staleness_and_conflict(base, cagrs, store)


if __name__ == "__main__":
    main()
