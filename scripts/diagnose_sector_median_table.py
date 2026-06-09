"""Gate-A calibration probe A2 (Punkt 2): build the pinned sector-median table
on the CLEANED universe and emit the candidate JSON for the loader.

Run: uv run python scripts\\diagnose_sector_median_table.py [n_min]

Chain position: A1 -> A2 -> A3. MUST run AFTER A1.

Ordering pin: the medians MUST be computed over the Fisher-eligible universe
EXCLUDING the METRIK_NA set.  The METRIK_NA exclusion is re-derived here using
the same .info-only proxy as A1 (gm is None or gm <= 0) PLUS the
Financials/Real-Estate sector exclusion for records without a real waterfall.
For the purposes of this $0 script the combined proxy is:
  exclude if gm is None or gm <= 0
  exclude if gics_sector contains "Financ" or "Real Estate"
(The full waterfall-based exclusion would require live income_stmt fetches;
the .info-only proxy is the accepted approximation for Gate-A median computation.
See A1 output for confirmation that both edges are empty / non-empty.)
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from app.errors import DataSourceError, DegradedDataError
from app.models.screener_record import ScreenerRecord
from app.screener.compose import build_screener_pipeline
from app.screener.filters import _node_chain
from app.screener.sector_buckets import resolve_bucket

UNIVERSE = Path("data/universe.json")
AUDIT_DIR = Path("docs/superpowers/audits/2026-06-09-2-gross-margin-floor")
CANDIDATE_JSON = AUDIT_DIR / "sector_median_table.candidate.json"

# Default n_min: minimum peer count for a bucket to qualify for its own median.
# Overridable via sys.argv[1].
_DEFAULT_N_MIN = 8


def _is_excluded(rec: ScreenerRecord) -> bool:
    """Exclude records from the cleaned universe (METRIK_NA proxy):
    - gm is None or <= 0 (.info-only proxy for undefined/negative waterfall), OR
    - Financials / Real Estate sector (structural no-COGS sectors).
    This prevents contaminating the medians with sectors that should not be
    assessed against a gross-margin floor.
    Note: the full waterfall-based exclusion comes from A1's output; this proxy
    is the $0 approximation sufficient for Gate-A median computation."""
    gm = rec.gross_margin
    if gm is None or gm <= 0:
        return True
    sector = rec.gics_sector or ""
    if "Financ" in sector or "Real Estate" in sector:
        return True
    return False


def main() -> None:
    n_min: int = int(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_N_MIN

    tickers: list[str] = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    yf_cached = build_screener_pipeline()

    # Build all ScreenerRecords (warm cache, $0)
    all_records: list[ScreenerRecord] = []
    unresolved = 0
    for t in tickers:
        try:
            info = yf_cached.get_ticker_info(t)
        except (DataSourceError, DegradedDataError):
            unresolved += 1
            continue
        all_records.append(ScreenerRecord.from_yfinance_info(t, info))

    print(f"Universe loaded: {len(all_records)} records, {unresolved} unresolved")

    # --- GICS nest viability check ---
    # yfinance .info only surfaces 'sector' (gics_sector) and 'industry' (gics_industry).
    # No GICS Industry-Group or Sub-Industry is available from this source.
    has_industry = sum(1 for r in all_records if r.gics_industry)
    has_sector = sum(1 for r in all_records if r.gics_sector)
    has_neither = sum(1 for r in all_records if not r.gics_industry and not r.gics_sector)
    print(f"\n=== GICS NEST VIABILITY (Gate-A finding) ===")
    print(f"  gics_industry present: {has_industry}/{len(all_records)}")
    print(f"  gics_sector present:   {has_sector}/{len(all_records)}")
    print(f"  neither present:       {has_neither}/{len(all_records)}")
    print(
        "  Finding: yfinance .info provides exactly 2 GICS levels (sector + industry).\n"
        "  No Industry-Group or Sub-Industry is available.\n"
        "  node_chain = [gics_industry, gics_sector]  (finest -> coarsest, 2 levels).\n"
        "  CT-B decision: 2-level nest is confirmed as the maximum available depth."
    )

    # --- Cleaned universe ---
    cleaned: list[ScreenerRecord] = [r for r in all_records if not _is_excluded(r)]
    excluded_count = len(all_records) - len(cleaned)
    print(
        f"\nCleaned universe: {len(cleaned)} records "
        f"(excluded {excluded_count} METRIK_NA/Financials/REITs)"
    )

    # --- Build counts over cleaned universe ---
    counts: dict[str, int] = {}
    for rec in cleaned:
        for node in _node_chain(rec):
            counts[node] = counts.get(node, 0) + 1

    # --- Resolve bucket per record; group gross_margin by bucket ---
    bucket_gms: dict[str, list[float]] = {}
    no_bucket = 0
    for rec in cleaned:
        chain = _node_chain(rec)
        bucket = resolve_bucket(chain, counts, n_min=n_min)
        if bucket is None:
            no_bucket += 1
            continue
        gm = rec.gross_margin
        if gm is None:
            continue  # excluded above but defensive
        bucket_gms.setdefault(bucket, []).append(gm)

    print(f"  Records with no qualifying bucket (n_min={n_min}): {no_bucket}")

    # --- Compute medians and build the candidate table ---
    entries: dict[str, float] = {}
    bucket_counts: dict[str, int] = {}
    for bucket, gms in sorted(bucket_gms.items()):
        entries[bucket] = statistics.median(gms)
        bucket_counts[bucket] = counts.get(bucket, 0)

    # Ensure every entry key is also in counts (loader consistency requirement)
    for bucket in entries:
        if bucket not in bucket_counts:
            bucket_counts[bucket] = counts.get(bucket, 0)

    # --- Print dispersion/multimodality sanity per bucket ---
    print(f"\n=== PER-BUCKET DISPERSION (n_min={n_min}) ===")
    print(f"{'Bucket':<50} {'n_gm':>5} {'pop':>5} {'median':>8} {'min':>8} {'max':>8}")
    print("-" * 90)
    for bucket in sorted(entries.keys()):
        gms = bucket_gms[bucket]
        pop = bucket_counts[bucket]
        print(
            f"{bucket:<50} {len(gms):>5} {pop:>5} "
            f"{entries[bucket]:>8.4f} {min(gms):>8.4f} {max(gms):>8.4f}"
        )

    print(f"\nTotal buckets in table: {len(entries)}")

    # --- Emit candidate JSON ---
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    candidate = {
        "schema_version": 1,
        "vintage": "2026-06",
        "n_min": n_min,
        "entries": entries,
        "counts": bucket_counts,
    }
    CANDIDATE_JSON.write_text(
        json.dumps(candidate, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nCandidate table written to: {CANDIDATE_JSON}")
    print(
        "NOTE: This writes to the audit dir only. "
        "data/sector_median_table.json is NOT touched. "
        "Phase E is the deliberate activation step."
    )


if __name__ == "__main__":
    main()
