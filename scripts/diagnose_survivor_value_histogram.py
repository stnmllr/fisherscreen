"""Punkt 1 GATE-A robustness: avg-daily-VALUE (EUR) distribution over the 688
EDGAR-survivors (= universe minus all dropouts), NOT the contaminated ~30. Answers:
is a candidate floor robustly BELOW the whole viable population (so it binds nothing
across market phases / universe drift, only excludes micro/broken)? And the
bidirectional survivor-level check: would the floor newly drop any CURRENT survivor?
Pence-fixed. $0 (warm cache). Run: uv run python scripts\\diagnose_survivor_value_histogram.py"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from app.errors import DataSourceError, DegradedDataError
from app.models.screener_record import ScreenerRecord
from app.screener.compose import build_screener_pipeline
from app.services.yfinance_client import YFinanceClientImpl

UNIVERSE = Path("data/universe.json")
DROPOUTS = Path("output/Universum/2026-06-dropouts.csv")
BUCKETS = [0.5, 1, 2, 5, 10, 25, 50, 100, 250, 1000]  # EUR Mio/day edges


def main() -> None:
    universe = set(json.loads(UNIVERSE.read_text(encoding="utf-8")))
    dropped = {r["ticker"] for r in csv.DictReader(DROPOUTS.open(encoding="utf-8"))}
    survivors = sorted(universe - dropped)
    yf = build_screener_pipeline()
    raw = YFinanceClientImpl()
    fx: dict[str, float] = {}
    vals: dict[str, float] = {}
    no_value = []
    for t in survivors:
        try:
            info = yf.get_ticker_info(t)
        except (DataSourceError, DegradedDataError):
            no_value.append(t); continue
        rec = ScreenerRecord.from_yfinance_info(t, info)
        cur = rec.currency
        if not rec.price or not rec.avg_daily_volume or cur is None:
            no_value.append(t); continue
        if cur not in fx:
            try: fx[cur] = raw.get_fx_rate(cur)
            except DataSourceError: fx[cur] = None
        if fx[cur] is None:
            no_value.append(t); continue
        vals[t] = rec.avg_daily_volume * rec.price * fx[cur]

    xs = sorted(vals.values())
    n = len(xs)
    print(f"survivors={len(survivors)} value_computed={n} no_value={len(no_value)}")
    if no_value:
        print(f"  no_value tickers: {no_value}")

    def pct(p): return xs[min(n - 1, int(p / 100 * n))] / 1e6
    print("\npercentiles (EUR Mio/day): "
          f"min={xs[0]/1e6:.3f} p1={pct(1):.3f} p5={pct(5):.2f} p10={pct(10):.2f} "
          f"p25={pct(25):.1f} p50={pct(50):.1f}")

    print("\nhistogram (EUR Mio/day):")
    edges = [0] + BUCKETS + [float("inf")]
    labels = ([f"<{BUCKETS[0]}"] +
              [f"{edges[i]}-{edges[i+1]}" for i in range(1, len(BUCKETS))] +
              [f">{BUCKETS[-1]}"])
    for i, lab in enumerate(labels):
        lo, hi = edges[i] * 1e6, edges[i + 1] * 1e6
        c = sum(1 for v in xs if lo <= v < hi)
        print(f"  {lab:>12} Mio : {'#' * c}  ({c})")

    print("\n=== CURRENT survivors with value < EUR 5M (floor-danger zone) ===")
    low = sorted(((v, t) for t, v in vals.items() if v < 5e6))
    for v, t in low:
        print(f"  {t:12} {v/1e6:7.3f} M")
    print(f"  ({len(low)} survivors below 5M; below 1M: "
          f"{sum(1 for v, _ in low if v < 1e6)}; below 2M: {sum(1 for v, _ in low if v < 2e6)})")


if __name__ == "__main__":
    main()
