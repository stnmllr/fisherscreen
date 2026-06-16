"""Read-only evidence harness for the sector-relative-scoring TODO critique.

Streams dev_gemini_scores (per-ticker dimension scores) and dev_ticker_cache
(yfinance sector) from Firestore, joins against the relative_rescues list in the
2026-06 funnel summary, and reports:

  1. Full sector distribution of ALL crosshits (not just the rendered top-50).
  2. RELATIVE_RESCUE cohort: how many were scored, their resilience-score
     distribution, how many cleared resilience >= 4, how many became crosshits.

No writes, no Gemini calls. Firestore reads only (free tier, read-only).
Run: uv run python scripts/analyze_sector_relative_evidence.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from google.cloud import firestore

from app.config import settings

THRESHOLD = settings.crosshits_score_threshold  # 4.0
# HARDCODE 3 (prod/render value). Local .env sets crosshits_min_dimensions=2 — the
# documented stale-gotcha — which would mis-reproduce the funnel (594 vs 281).
MIN_DIMS = 3
MERIT_AXES = ("growth", "profitability", "resilience")  # management/innovation forced to 3
FUNNEL = Path("output/Universum/2026-06-funnel_summary.json")


def is_crosshit(dims: dict) -> bool:
    hits = sum(1 for a in MERIT_AXES if float(dims.get(a, 0)) >= THRESHOLD)
    return hits >= MIN_DIMS


def main() -> None:
    project = settings.gcp_project_id
    if not project:
        raise SystemExit("FISHERSCREEN_GCP_PROJECT_ID not set — cannot reach Firestore")
    db = firestore.Client(project=project)

    # --- pull scores ---
    scores: dict[str, dict] = {}
    for doc in db.collection(settings.gemini_score_collection).stream():
        d = doc.to_dict() or {}
        dims = d.get("dimensions")
        if isinstance(dims, dict):
            scores[doc.id] = dims
    print(f"dev_gemini_scores: {len(scores)} scored tickers")

    # --- pull sectors ---
    sectors: dict[str, str] = {}
    for doc in db.collection(settings.ticker_collection).stream():
        d = doc.to_dict() or {}
        sec = d.get("sector")
        if sec:
            sectors[doc.id] = sec
    print(f"dev_ticker_cache: {len(sectors)} tickers with sector\n")

    # --- crosshits (recomputed from scores) ---
    crosshits = [t for t, dims in scores.items() if is_crosshit(dims)]
    print(f"=== CROSSHITS recomputed: {len(crosshits)} (funnel says 281) ===")
    csec = Counter(sectors.get(t, "n/a") for t in crosshits)
    total = len(crosshits)
    for sec, n in csec.most_common():
        print(f"  {sec:<26} {n:>4}  ({100*n/total:4.1f}%)")

    # --- RELATIVE_RESCUE cohort ---
    funnel = json.loads(FUNNEL.read_text(encoding="utf-8"))
    rescues = funnel.get("relative_rescues", [])
    print(f"\n=== RELATIVE_RESCUE cohort: {len(rescues)} titles ===")
    scored_rescues = [t for t in rescues if t in scores]
    print(f"  scored (present in dev_gemini_scores): {len(scored_rescues)}/{len(rescues)}")

    resil_dist = Counter(int(scores[t].get("resilience", -1)) for t in scored_rescues)
    print("  resilience score distribution:")
    for s in sorted(resil_dist, reverse=True):
        print(f"    resilience={s}: {resil_dist[s]}")
    resil_ge4 = [t for t in scored_rescues if float(scores[t].get("resilience", 0)) >= THRESHOLD]
    print(f"  resilience >= {THRESHOLD}: {len(resil_ge4)}/{len(scored_rescues)} "
          f"({100*len(resil_ge4)/max(1,len(scored_rescues)):.1f}%)")

    rescue_crosshits = [t for t in scored_rescues if is_crosshit(scores[t])]
    print(f"  BECAME CROSSHIT: {len(rescue_crosshits)}/{len(scored_rescues)} "
          f"({100*len(rescue_crosshits)/max(1,len(scored_rescues)):.1f}%)")
    print(f"  rescue-crosshit examples: {sorted(rescue_crosshits)[:15]}")

    # cross-check: gross_margin axis is NOT directly scored; resilience folds it with leverage.
    # Show the resilience scores of rescue-crosshits to confirm they cleared it absolutely.
    print("\n=== sanity: do rescue-crosshits clear resilience absolutely? ===")
    rc_resil = Counter(int(scores[t].get("resilience", -1)) for t in rescue_crosshits)
    for s in sorted(rc_resil, reverse=True):
        print(f"    resilience={s}: {rc_resil[s]}")


if __name__ == "__main__":
    main()
