r"""Wo liegen die Referenz-Titel auf der growth-Achse? (nur lesen, $0)

Liest die Umsatzreihen der Scoring-Kohorte eines Monats aus Firestore
(settings.revenue_series_collection, Batch-get_all, kein Schreiben, kein yfinance),
rechnet je Ticker das Median-Jahreswachstum wie der Scorer
(app.screener.growth_consistency.median_annual_growth) und das globale Perzentil
(app.screener.percentiles). Ausgabe: die Bandgrenzen in Wachstum ausgedrueckt und
je Referenz-Titel Median, Perzentil, Score und Abstand zur 4er-Schwelle.

Aufruf:
    uv run python -m scripts.diagnose_growth_reference --month 2026-10
"""
from __future__ import annotations

import argparse
import json
import sys

from google.cloud import firestore

from app.config import settings
from app.screener.growth_consistency import consistency_ratio, median_annual_growth
from app.screener.percentiles import percentile_rank, percentile_to_score
from scripts.simulate_month_scoring import (
    PRE_SCORING_STAGES,
    ROOT,
    prefetch,
    read_dropouts,
)

sys.stdout.reconfigure(encoding="utf-8")


def quantile(sorted_vals: list[float], p: float) -> float:
    """Smallest value whose midrank percentile reaches p."""
    for v in sorted_vals:
        if percentile_rank(v, sorted_vals) >= p:
            return v
    return sorted_vals[-1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    args = ap.parse_args()

    universe: list[str] = json.loads((ROOT / "data" / "universe.json").read_text("utf-8"))
    dropped = {r["ticker"] for r in read_dropouts(args.month) if r["stage"] in PRE_SCORING_STAGES}
    cohort = [t for t in universe if t not in dropped]

    db = firestore.Client(project=settings.gcp_project_id)
    docs = prefetch(db, settings.revenue_series_collection, cohort)
    medians: dict[str, float] = {}
    ratios: dict[str, float | None] = {}
    for t in cohort:
        doc = docs.get((settings.revenue_series_collection, t)) or {}
        revs = [float(x) for x in doc.get("revenues", [])]
        m = median_annual_growth(revs) if revs else None
        if m is not None:
            medians[t] = m
            ratios[t] = consistency_ratio(revs)

    dist = sorted(medians.values())
    print(f"Kohorte {len(cohort)}, mit Median {len(dist)}")
    for p, s in ((88.0, 5), (70.0, 4), (40.0, 3), (15.0, 2)):
        print(f"  Score {s} ab P{p:.0f}: Median-Wachstum >= {quantile(dist, p):+.1%}")

    reference = json.loads((ROOT / "data" / "reference_fisher.json").read_text("utf-8"))["tickers"]
    p70 = quantile(dist, 70.0)
    print("\nTicker      Median    P     Score  Abstand zu P70  Konsistenz")
    rows = []
    for group, tickers in reference.items():
        for t in tickers:
            if t not in medians:
                rows.append((t, None, None, None, None, None))
                continue
            m = medians[t]
            p = percentile_rank(m, dist)
            rows.append((t, m, p, percentile_to_score(p), m - p70, ratios[t]))
    for t, m, p, s, gap, r in sorted(rows, key=lambda x: (x[1] is None, -(x[1] or 0))):
        if m is None:
            print(f"{t:<11} n/a (nicht in Kohorte oder <4 GJ)")
        else:
            rs = "—" if r is None else f"{r:.2f}"
            print(f"{t:<11} {m:+7.1%}  {p:5.1f}  {s}      {gap:+7.1%}        {rs}")

    report_variants(args.month, medians, ratios, reference)


def _axes(detail: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in detail.split() if "=" in part)


def report_variants(
    month: str,
    medians: dict[str, float],
    ratios: dict[str, float | None],
    reference: dict[str, list[str]],
) -> None:
    """Titles that fail the crosshit gate ONLY on growth (profitability and
    resilience >= 4, steadiness >= 4 or unmeasured): how many would a growth
    variant lift to growth >= 4? Approximation on the run's own axis scores --
    the exact count needs simulate_month_scoring."""
    ref = {t for ts in reference.values() for t in ts}
    only_growth: list[str] = []
    for r in read_dropouts(month):
        if r["stage"] != "crosshits" or r["reason_code"] != "SCORE_BELOW_THRESHOLD":
            continue
        a = _axes(r["detail"])
        if float(a.get("growth", 5)) >= 4:
            continue
        if float(a.get("profitability", 0)) < 4 or float(a.get("resilience", 0)) < 4:
            continue
        st = a.get("steadiness", "n/a")
        if not st.startswith("n/a") and float(st) < 4:
            continue
        only_growth.append(r["ticker"])

    variants = {
        "P60 (knapp ~7,3 %)": lambda m, r: m >= quantile(sorted(medians.values()), 60.0),
        "Median >= 7 %": lambda m, r: m >= 0.07,
        "stetig (1.00) & >= 5 %": lambda m, r: r == 1.0 and m >= 0.05,
        "stetig (1.00) & >= 3,5 %": lambda m, r: r == 1.0 and m >= 0.035,
    }
    print(f"\nNur an growth gescheitert: {len(only_growth)} Titel (Basis 46 Crosshits)")
    for name, rule in variants.items():
        lifted = sorted(
            t for t in only_growth if t in medians and rule(medians[t], ratios[t])
        )
        hits = [t for t in lifted if t in ref]
        print(f"  {name:<26} +{len(lifted):>3} Crosshits -> {46 + len(lifted)}, "
              f"Referenz +{len(hits)} {hits}")
        print("      " + ", ".join(f"{t} {medians[t]:+.1%}" for t in lifted))


if __name__ == "__main__":
    main()
