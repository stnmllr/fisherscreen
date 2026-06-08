"""Punkt 1 GATE-A: survivor-split prognosis. For the GATE_VOLUME-dropped set
(22 REVIEW + 5 BENIGN from dropouts.csv), at a candidate value floor, compute who
the value-floor RESCUES, then apply the follow-on gates (market_cap, gross_margin,
revenue_growth — unchanged) to predict who actually reaches scoring (= survivor
delta M) vs who falls at which follow-on gate. Pence-fixed (uses from_yfinance_info).
$0 (warm cache). Run: uv run python scripts\\diagnose_p1_survivor_split.py [threshold_eur]"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from app.errors import DataSourceError, DegradedDataError
from app.models.screener_record import ScreenerRecord
from app.screener.compose import build_screener_pipeline
from app.screener.filters import (
    passes_gross_margin_filter,
    passes_market_cap_filter,
    passes_revenue_growth_filter,
)
from app.services.yfinance_client import YFinanceClientImpl

DROPOUTS = Path("output/Universum/2026-06-dropouts.csv")
THRESHOLD = float(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000.0


def main() -> None:
    gv = [(r["ticker"], r["severity_bucket"])
          for r in csv.DictReader(DROPOUTS.open(encoding="utf-8"))
          if r["reason_code"] == "GATE_VOLUME"]
    yf = build_screener_pipeline()
    raw = YFinanceClientImpl()
    fx: dict[str, float] = {}
    print(f"threshold = EUR {THRESHOLD:,.0f}/day | GATE_VOLUME set = {len(gv)}\n")
    rescued_survivor, rescued_drop, stay_out = [], [], []
    for t, sev in sorted(gv):
        try:
            info = yf.get_ticker_info(t)
        except (DataSourceError, DegradedDataError):
            stay_out.append((t, sev, "unresolved")); continue
        rec = ScreenerRecord.from_yfinance_info(t, info)
        cur = rec.currency
        if rec.price is None or rec.avg_daily_volume is None or cur is None:
            stay_out.append((t, sev, "no_value_input")); continue
        if cur not in fx:
            try: fx[cur] = raw.get_fx_rate(cur)
            except DataSourceError: fx[cur] = None
        if fx[cur] is None:
            stay_out.append((t, sev, "no_fx")); continue
        rec.fx_rate = fx[cur]
        rec.market_cap_eur = (rec.market_cap * fx[cur]) if rec.market_cap else None
        value = rec.avg_daily_volume * rec.price * fx[cur]
        if value < THRESHOLD:
            stay_out.append((t, sev, f"value {value/1e6:.2f}M < floor")); continue
        # rescued by value floor -> apply follow-on gates (order: market_cap, gross_margin, rev_growth)
        if not passes_market_cap_filter(rec):
            rescued_drop.append((t, sev, "GATE_MARKET_CAP"))
        elif not passes_gross_margin_filter(rec):
            rescued_drop.append((t, sev, "GATE_GROSS_MARGIN"))
        elif not passes_revenue_growth_filter(rec):
            rescued_drop.append((t, sev, "GATE_REVENUE_GROWTH(REVIEW if large-cap)"))
        else:
            rescued_survivor.append((t, sev))

    print(f"=== SURVIVORS (rescued + pass all follow-on gates) = M = {len(rescued_survivor)} ===")
    for t, s in rescued_survivor: print(f"  {t:12} ({s})")
    print(f"\n=== RESCUED but fall at follow-on gate (Punkt 2/3 territory) = {len(rescued_drop)} ===")
    for t, s, g in rescued_drop: print(f"  {t:12} ({s}) -> {g}")
    print(f"\n=== STAY OUT (below floor / broken / micro) = {len(stay_out)} ===")
    for t, s, why in stay_out: print(f"  {t:12} ({s}) -> {why}")


if __name__ == "__main__":
    main()
