"""Read-only verification that backfill_revenue_series actually warmed the cache.

Counts docs in dev_revenue_series, compares coverage against the universe, and
spot-checks a sample of tickers for non-empty revenue series. No writes.

Usage (cmd.exe): uv run python -m scripts.backfill_verify
"""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    from app.config import settings
    from app.services.firestore_client import FirestoreClientImpl

    coll = settings.revenue_series_collection
    fs = FirestoreClientImpl(project_id=settings.gcp_project_id)

    universe_path = Path(__file__).parent.parent / "data" / "universe.json"
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    universe_set = set(universe)

    cached_ids = {d.id for d in fs._db.collection(coll).stream()}
    covered = universe_set & cached_ids
    missing = sorted(universe_set - cached_ids)

    print(f"project            : {settings.gcp_project_id}")
    print(f"collection         : {coll}")
    print(f"universe           : {len(universe_set)}")
    print(f"docs in collection : {len(cached_ids)}")
    print(f"universe covered   : {len(covered)}/{len(universe_set)}")
    print(f"missing            : {len(missing)}")
    if missing:
        print(f"  first 20 missing : {missing[:20]}")

    # Spot-check: do a sample of covered tickers hold a non-empty series?
    sample = sorted(covered)[:: max(1, len(covered) // 8)][:8]
    print("spot-check (non-empty revenue series):")
    for t in sample:
        doc = fs._db.collection(coll).document(t).get().to_dict() or {}
        # series payload key may vary; report what is present + a length-ish hint
        keys = list(doc.keys())
        series = doc.get("series") or doc.get("revenue_series") or doc.get("values")
        n = len(series) if isinstance(series, (list, dict)) else "?"
        print(f"  {t:12s} keys={keys} series_len={n}")


if __name__ == "__main__":
    main()
