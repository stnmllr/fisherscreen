"""Gate-A calibration probe A2 (Punkt 2): build the pinned sector-median table
on the CLEANED universe and emit the candidate JSON for the loader.

Run: uv run python scripts\\diagnose_sector_median_table.py [n_min]

Chain position: A1 -> A2 -> A3. MUST run AFTER A1.

Ordering pin: the medians MUST be computed over the Fisher-eligible universe
EXCLUDING the METRIK_NA set.  The METRIK_NA set is loaded from A1's output file:
  docs/superpowers/audits/2026-06-09-2-gross-margin-floor/metrik_na_tickers.json

Exclusion predicate: ticker ∈ A1's METRIK_NA set (tickers classified UNDEFINED by
the waterfall probe — no genuine COGS structure).  DEFINED_NEGATIVE tickers (real
industrial negative-margin businesses) are explicitly KEPT so they contribute to
their own sector-bucket median; the median is robust to occasional negative outliers.
The Financials/Real-Estate sector string exclusion is removed: Capital-Markets
financials (S&P Global, Moody's, MSCI, exchanges, asset managers) have a real
revenue→COGS→gross-profit waterfall, are classified DEFINED by A1, and MUST remain
so their sector bucket median is built — otherwise the relative arm silently
FAILs every sub-30%-margin compounder in that sector.
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
METRIK_NA_JSON = AUDIT_DIR / "metrik_na_tickers.json"

# Default n_min: minimum peer count for a bucket to qualify for its own median.
# Overridable via sys.argv[1].
_DEFAULT_N_MIN = 8


def main() -> None:
    n_min: int = int(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_N_MIN

    # --- Load A1's METRIK_NA set (enforces A1→A2 chain ordering) ---
    if not METRIK_NA_JSON.exists():
        raise SystemExit(
            f"A1 output missing: {METRIK_NA_JSON} — "
            "run diagnose_gross_margin_definedness.py (A1) first."
        )
    metrik_na: set[str] = set(
        json.loads(METRIK_NA_JSON.read_text(encoding="utf-8"))["metrik_na"]
    )
    print(f"Loaded {len(metrik_na)} METRIK_NA tickers from A1 output.")

    # Exclusion predicate: ticker ∈ A1's waterfall-based METRIK_NA set.
    # DEFINED_NEGATIVE tickers (real negative-margin industrials) stay in the universe.
    # No sector-string sweep — Capital-Markets financials with a real COGS waterfall
    # are classified DEFINED by A1 and must contribute to their own sector bucket.
    def _is_excluded(rec: ScreenerRecord) -> bool:
        return rec.ticker in metrik_na

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
        "  Finding: yfinance .info exposes only 2 GICS levels (sector + industry).\n"
        "  No Industry-Group or Sub-Industry is available from this source.\n"
        "  node_chain = [gics_industry, gics_sector]  (finest -> coarsest, 2 levels).\n"
        "  CT-B decision: inspect the dispersion (min/max span) of the SECTOR-level\n"
        "  fallback buckets reported in the dispersion table below. Wide/bimodal spans\n"
        "  -> the 2-level nest is insufficient -> CT-B (Ticker->GICS-node mapping layer)\n"
        "  is due. Do NOT conclude CT-B unnecessary from nest depth alone — let the\n"
        "  dispersion decide."
    )

    # --- Cleaned universe ---
    cleaned: list[ScreenerRecord] = [r for r in all_records if not _is_excluded(r)]
    excluded_count = len(all_records) - len(cleaned)
    print(
        f"\nCleaned universe: {len(cleaned)} records "
        f"(excluded {excluded_count} METRIK_NA tickers per A1 waterfall classification)"
    )

    # --- Build counts over cleaned universe ---
    counts: dict[str, int] = {}
    for rec in cleaned:
        for node in _node_chain(rec):
            counts[node] = counts.get(node, 0) + 1

    # --- Resolve bucket per record; group gross_margin by bucket; track sector fallbacks ---
    bucket_gms: dict[str, list[float]] = {}
    # A bucket is a sector-level fallback when resolve_bucket returns the last element of
    # the node_chain (i.e. the coarsest/sector level, because the industry was below n_min).
    sector_fallback_buckets: set[str] = set()
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
        # Flag as sector-level fallback if bucket is the last (coarsest) node in the chain
        if chain and bucket == chain[-1] and len(chain) > 1:
            sector_fallback_buckets.add(bucket)

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
    # Buckets marked [SECTOR-FALLBACK] resolved at the coarsest level because the
    # industry bucket was below n_min. These are multimodal risk: the relative arm
    # FIRES (bucket_median returns a value) but the median may be meaningless if the
    # sector mixes structurally different businesses (e.g. luxury+auto+retail).
    # Wide min/max spans on these buckets are the CT-B trigger signal.
    print(f"\n=== PER-BUCKET DISPERSION (n_min={n_min}) ===")
    print(
        f"{'Bucket':<50} {'n_gm':>5} {'pop':>5} {'median':>8} {'min':>8} {'max':>8} {'note'}"
    )
    print("-" * 100)
    for bucket in sorted(entries.keys()):
        gms = bucket_gms[bucket]
        pop = bucket_counts[bucket]
        note = "[SECTOR-FALLBACK]" if bucket in sector_fallback_buckets else ""
        print(
            f"{bucket:<50} {len(gms):>5} {pop:>5} "
            f"{entries[bucket]:>8.4f} {min(gms):>8.4f} {max(gms):>8.4f} {note}"
        )

    print(f"\nTotal buckets in table: {len(entries)}")
    print(f"Sector-level fallback buckets: {len(sector_fallback_buckets)}")
    if sector_fallback_buckets:
        print(
            "CT-B decision: inspect the [SECTOR-FALLBACK] rows above. "
            "Wide/bimodal min/max spans indicate the 2-level nest is insufficient "
            "and CT-B (Ticker->GICS-node mapping layer) is due. "
            "Do NOT conclude CT-B unnecessary from nest depth alone — let the dispersion decide."
        )

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
