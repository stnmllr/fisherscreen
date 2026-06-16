"""Calibration sweep for the percentile->score anchor bands (decision 3: loosen a bit).

Rebuilds the cohort + percentiles once (revenue cache is warm now -> fast), then reports
per-axis >=4 rate and the all-3 crosshit count for several candidate band tables, so the
loosened bands are chosen from data, not guessed. Read-only; no commits, no prod run.
Run: uv run python scripts/calibrate_anchor_bands.py
"""
from __future__ import annotations

from collections import Counter

from google.cloud import firestore

from app.config import settings
from app.models.screener_record import ScreenerRecord
from app.screener.growth_consistency import consistency_cap, consistency_ratio
from app.screener.sector_percentiles import annotate_percentiles
from app.services.firestore_client import FirestoreClientImpl
from app.services.revenue_series_cache import CachedRevenueSeries
from app.services.yfinance_client import YFinanceClientImpl

MERIT = ("growth", "profitability", "resilience")

# (label, bands) — bands are (threshold, score) descending; below lowest -> 1.
CANDIDATES = [
    ("current  5:90 4:75", ((90.0, 5), (75.0, 4), (40.0, 3), (15.0, 2))),
    ("loosenA  5:88 4:70", ((88.0, 5), (70.0, 4), (40.0, 3), (15.0, 2))),
    ("loosenB  5:85 4:65", ((85.0, 5), (65.0, 4), (40.0, 3), (15.0, 2))),
    ("loosenC  5:85 4:60", ((85.0, 5), (60.0, 4), (35.0, 3), (15.0, 2))),
]


def _band(p: float, bands) -> int:
    for thr, s in bands:
        if p >= thr:
            return s
    return 1


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _axis_scores(r: ScreenerRecord, bands) -> dict[str, int]:
    pcts = r.input_percentiles or {}
    # growth (global pct + consistency cap)
    g = _band(pcts["revenue_growth_yoy"], bands) if "revenue_growth_yoy" in pcts else 3
    g = min(g, consistency_cap(r.growth_consistency))
    # profitability
    pv = [pcts[f] for f in ("operating_margin", "return_on_equity") if f in pcts]
    prof = _band(_mean(pv), bands) if pv else 3
    if (r.operating_margin is not None and r.operating_margin < 0) or (
            r.return_on_equity is not None and r.return_on_equity < 0):
        prof = 0
    # resilience (gross_margin + inverted d/e)
    rv = []
    if "gross_margin" in pcts:
        rv.append(pcts["gross_margin"])
    if "debt_to_equity" in pcts:
        rv.append(100.0 - pcts["debt_to_equity"])
    resil = _band(_mean(rv), bands) if rv else 3
    if r.debt_to_equity is not None and r.debt_to_equity > 300.0:
        resil = 0
    return {"growth": g, "profitability": prof, "resilience": resil}


def main() -> None:
    db = firestore.Client(project=settings.gcp_project_id)
    cohort = [d.id for d in db.collection(settings.gemini_score_collection).stream()
              if isinstance((d.to_dict() or {}).get("dimensions"), dict)]
    records: list[ScreenerRecord] = []
    for ticker in cohort:
        snap = db.collection(settings.ticker_collection).document(ticker).get()
        if snap.exists:
            info = {k: v for k, v in snap.to_dict().items() if k != "_cached_at"}
            records.append(ScreenerRecord.from_yfinance_info(ticker, info))
    print(f"cohort {len(records)} records")

    rc = CachedRevenueSeries(YFinanceClientImpl(),
                             FirestoreClientImpl(project_id=settings.gcp_project_id),
                             settings.revenue_series_collection, settings.revenue_series_ttl_days)
    for r in records:
        r.growth_consistency = consistency_ratio(rc.get_revenue_series(r.ticker))
    annotate_percentiles(records)

    n = len(records)
    print(f"\n{'band table':<22} {'g>=4':>6} {'p>=4':>6} {'r>=4':>6} {'crosshits':>10}")
    for label, bands in CANDIDATES:
        scored = [_axis_scores(r, bands) for r in records]
        ge4 = {a: sum(1 for s in scored if s[a] >= 4) for a in MERIT}
        ch = sum(1 for s in scored if all(s[a] >= 4 for a in MERIT))
        print(f"{label:<22} {ge4['growth']:>6} {ge4['profitability']:>6} {ge4['resilience']:>6}"
              f" {ch:>4} ({100*ch/n:.1f}%)")


if __name__ == "__main__":
    main()
