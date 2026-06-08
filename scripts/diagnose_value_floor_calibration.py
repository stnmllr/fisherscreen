"""Punkt 1 calibration probe: compute avg-daily-trading-VALUE in EUR
(avg_daily_volume x price x fx) for the whole universe from the warm
dev_ticker_cache ($0), to set the value-floor. Shows the distribution, where the
22 GATE_VOLUME-REVIEW large-caps sit, where the 5 genuine-illiquid BENIGN sit,
and a threshold sweep — so the floor is anchored on liquidity economics and the
distribution VALIDATES it (it does not back-solve it). Reusable to re-check after
the value-floor lands. Run: uv run python scripts\\diagnose_value_floor_calibration.py"""
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
THRESHOLDS_EUR = [250_000, 500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000]


def _value_eur(rec: ScreenerRecord, fx: dict, raw: YFinanceClientImpl) -> float | None:
    vol = rec.avg_daily_volume
    price = rec.price or None  # mirror the planned 0->None normalization
    if not vol or not price or rec.currency is None:
        return None
    cur = rec.currency
    if cur not in fx:
        try:
            fx[cur] = raw.get_fx_rate(cur)
        except DataSourceError:
            fx[cur] = None
    if fx[cur] is None:
        return None
    return vol * price * fx[cur]


def main() -> None:
    tickers = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    yf = build_screener_pipeline()
    raw = YFinanceClientImpl()
    fx: dict[str, float] = {}
    values: dict[str, float] = {}
    no_value = 0
    for t in tickers:
        try:
            info = yf.get_ticker_info(t)
        except (DataSourceError, DegradedDataError):
            no_value += 1
            continue
        rec = ScreenerRecord.from_yfinance_info(t, info)
        v = _value_eur(rec, fx, raw)
        if v is None:
            no_value += 1
        else:
            values[t] = v

    vals = sorted(values.values())
    n = len(vals)
    def pct(p): return vals[min(n - 1, int(p / 100 * n))] / 1e6
    print(f"computed value for {n}/{len(tickers)} (no_value={no_value})")
    print("percentiles (EUR Mio/Tag): "
          f"p10={pct(10):.2f} p25={pct(25):.2f} p50={pct(50):.2f} "
          f"p75={pct(75):.1f} p90={pct(90):.1f}")

    gv = {r["ticker"]: r["severity_bucket"]
          for r in csv.DictReader(DROPOUTS.open(encoding="utf-8"))
          if r["reason_code"] == "GATE_VOLUME"}
    rev = sorted(((values.get(t), t) for t, s in gv.items() if s == "REVIEW"),
                 key=lambda x: (x[0] is None, x[0] or 0))
    ben = sorted(((values.get(t), t) for t, s in gv.items() if s == "BENIGN"),
                 key=lambda x: (x[0] is None, x[0] or 0))
    print("\n=== 22 REVIEW large-caps: avg daily VALUE (EUR Mio) ===")
    for v, t in rev:
        print(f"  {t:12} {('%.3f' % (v/1e6)) if v else 'NO-VALUE':>10}")
    print("\n=== 5 BENIGN genuine-illiquid: avg daily VALUE (EUR Mio) ===")
    for v, t in ben:
        print(f"  {t:12} {('%.3f' % (v/1e6)) if v else 'NO-VALUE':>10}")

    print("\n=== threshold sweep (EUR/day) ===")
    print(f"{'threshold':>12} {'univ_pass':>9} {'22_pass':>7} {'5BEN_pass':>9}")
    rv = [v for v, _ in rev if v]
    bv = [v for v, _ in ben if v]
    for th in THRESHOLDS_EUR:
        up = sum(1 for v in vals if v >= th)
        rp = sum(1 for v in rv if v >= th)
        bp = sum(1 for v in bv if v >= th)
        print(f"{th:>12,} {up:>9} {rp:>7} {bp:>9}")


if __name__ == "__main__":
    main()
