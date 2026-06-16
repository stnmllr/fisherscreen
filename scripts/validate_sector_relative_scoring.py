"""Local (offline) validation of the new deterministic sector-relative scorer (T12, Way A).

Reconstructs the last run's pre-scoring cohort (the dev_gemini_scores keys) from the
read-only Firestore caches, applies the NEW deterministic scorer, and reports the
acceptance criteria from spec §13 plus the deferred partial-evidence measurement.

Side effects: writes dev_revenue_series (the cohort backfill — harmless, long-TTL).
No prod run, no GitHub push, no Gemini. Run: uv run python scripts/validate_sector_relative_scoring.py
"""
from __future__ import annotations

from collections import Counter

from google.cloud import firestore

from app.config import settings
from app.models.screener_record import ScreenerRecord
from app.screener.deterministic_scorer import score_record
from app.screener.growth_consistency import consistency_ratio
from app.screener.sector_percentiles import annotate_percentiles
from app.services.firestore_client import FirestoreClientImpl
from app.services.revenue_series_cache import CachedRevenueSeries
from app.services.yfinance_client import YFinanceClientImpl

MERIT = ("growth", "profitability", "resilience")


def _is_crosshit(dims: dict) -> bool:
    return sum(1 for a in MERIT if float(dims.get(a, 0)) >= 4.0) >= 3


def _de_usable(r: ScreenerRecord) -> bool:
    return r.debt_to_equity is not None and r.debt_to_equity >= 0


def main() -> None:
    db = firestore.Client(project=settings.gcp_project_id)

    # --- cohort + old scores ---
    old_scores: dict[str, dict] = {}
    for doc in db.collection(settings.gemini_score_collection).stream():
        d = doc.to_dict() or {}
        if isinstance(d.get("dimensions"), dict):
            old_scores[doc.id] = d["dimensions"]
    print(f"cohort (dev_gemini_scores): {len(old_scores)} tickers")

    # --- rebuild records from dev_ticker_cache (read-only) ---
    records: list[ScreenerRecord] = []
    missing = 0
    for ticker in old_scores:
        snap = db.collection(settings.ticker_collection).document(ticker).get()
        info = snap.to_dict() if snap.exists else None
        if not info:
            missing += 1
            continue
        info = {k: v for k, v in info.items() if k != "_cached_at"}
        records.append(ScreenerRecord.from_yfinance_info(ticker, info))
    print(f"rebuilt {len(records)} records ({missing} missing from ticker cache)\n")

    # --- new deterministic scoring (revenue series via real cache; backfills dev_revenue_series) ---
    revenue_cache = CachedRevenueSeries(
        YFinanceClientImpl(),
        FirestoreClientImpl(project_id=settings.gcp_project_id),
        settings.revenue_series_collection,
        ttl_days=settings.revenue_series_ttl_days,
    )
    for i, r in enumerate(records, 1):
        r.growth_consistency = consistency_ratio(revenue_cache.get_revenue_series(r.ticker))
        if i % 100 == 0:
            print(f"  revenue/consistency {i}/{len(records)}")
    annotate_percentiles(records)
    for r in records:
        score_record(r)

    # --- 1. de-clustering: per-axis score distribution OLD vs NEW ---
    print("\n=== ACCEPTANCE 1 — de-clustering (per-axis score histogram) ===")
    for axis in MERIT:
        old = Counter(int(old_scores[r.ticker].get(axis, -1)) for r in records)
        new = Counter(r.gemini_dimensions[axis] for r in records)
        old_ge4 = sum(v for k, v in old.items() if k >= 4)
        new_ge4 = sum(v for k, v in new.items() if k >= 4)
        n = len(records)
        print(f"\n  {axis}:")
        print(f"    OLD  " + " ".join(f"{s}:{old.get(s,0)}" for s in range(6))
              + f"   (>=4: {old_ge4} = {100*old_ge4/n:.0f}%)")
        print(f"    NEW  " + " ".join(f"{s}:{new.get(s,0)}" for s in range(6))
              + f"   (>=4: {new_ge4} = {100*new_ge4/n:.0f}%)")

    # --- crosshit rate OLD vs NEW ---
    old_ch = [t for t in old_scores if _is_crosshit(old_scores[t])]
    new_ch = [r for r in records if _is_crosshit(r.gemini_dimensions)]
    n = len(records)
    print(f"\n=== crosshit rate: OLD {len(old_ch)} ({100*len(old_ch)/len(old_scores):.1f}%)"
          f"  ->  NEW {len(new_ch)} ({100*len(new_ch)/n:.1f}%) ===")

    # --- 2. PARTIAL-EVIDENCE measurement (deferred decision input) ---
    print("\n=== DEFERRED DECISION — partial-evidence rate (exactly one of two axis inputs) ===")
    prof_full = sum(1 for r in records if r.operating_margin is not None and r.return_on_equity is not None)
    prof_partial = sum(1 for r in records if (r.operating_margin is None) != (r.return_on_equity is None))
    prof_none = sum(1 for r in records if r.operating_margin is None and r.return_on_equity is None)
    resil_full = sum(1 for r in records if r.gross_margin is not None and _de_usable(r))
    resil_partial = sum(1 for r in records if (r.gross_margin is not None) != _de_usable(r))
    resil_none = sum(1 for r in records if r.gross_margin is None and not _de_usable(r))
    print(f"  profitability: full(both)={prof_full}  PARTIAL(one)={prof_partial}  none={prof_none}")
    print(f"  resilience:    full(both)={resil_full}  PARTIAL(one)={resil_partial}  none={resil_none}")
    # how many crosshits rest on a partial axis?
    ch_on_partial = sum(1 for r in new_ch
                        if (r.operating_margin is None) != (r.return_on_equity is None)
                        or (r.gross_margin is not None) != _de_usable(r))
    print(f"  NEW crosshits resting on >=1 partial axis: {ch_on_partial}/{len(new_ch)}")

    # --- 3. flags ---
    low = sum(1 for r in records if r.data_confidence == "low")
    fallback = sum(1 for r in records if any(v == "global_fallback" for v in (r.score_basis or {}).values()))
    print(f"\n=== flags: data_confidence=low {low}  |  global_fallback (>=1 axis) {fallback} ===")
    fb_sectors = Counter(r.gics_sector for r in records
                         if any(v == "global_fallback" for v in (r.score_basis or {}).values()))
    print(f"  global_fallback by sector: {dict(fb_sectors)}")

    # --- 4. anti-cyclical counter-probe ---
    print("\n=== ACCEPTANCE — anti-cyclical counter-probe (cyclical miners) ===")
    for t in ("HL", "NEM", "EDV.L"):
        r = next((x for x in records if x.ticker == t), None)
        if r is None:
            print(f"  {t}: not in cohort")
            continue
        cons = r.growth_consistency
        print(f"  {t}: growth OLD={old_scores.get(t,{}).get('growth')} NEW={r.gemini_dimensions['growth']}"
              f"  consistency={'n/a' if cons is None else f'{cons:.2f}'}"
              f"  rev_growth={r.revenue_growth_yoy}")

    # --- 5. spin-off / data_confidence on crosshits ---
    ch_low = [r.ticker for r in new_ch if r.data_confidence == "low"]
    print(f"\n=== NEW crosshits with data_confidence=low (must be flagged, not hidden): {len(ch_low)} ===")
    print(f"  {sorted(ch_low)[:20]}")

    # --- new crosshit sector spread ---
    print("\n=== NEW crosshit sector spread ===")
    for sec, c in Counter(r.gics_sector for r in new_ch).most_common():
        print(f"  {sec or 'n/a':<24} {c}")


if __name__ == "__main__":
    main()
