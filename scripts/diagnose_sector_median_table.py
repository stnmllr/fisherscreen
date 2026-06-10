"""Gate-A calibration probe A2 (Punkt 2): build the pinned sector-median table
on the CLEANED universe and emit the candidate JSON for the loader.

Run: uv run python scripts\\diagnose_sector_median_table.py [n_min]

Chain position: A1 -> A2 -> A3. MUST run AFTER A1.

Ordering pin: the medians MUST be computed over the Fisher-eligible universe
EXCLUDING the METRIK_NA set.  The METRIK_NA set is loaded from A1's output file:
  docs/superpowers/audits/2026-06-09-2-gross-margin-floor/metrik_na_tickers.json

Cleaning: the SHARED clean_universe definition (include_defined_negative=False)
— ticker ∈ A1's METRIK_NA set is excluded, gm<=0/None is excluded (negatives OUT:
the median anchors "normal-low-but-viable", gm<=0 are the pathological tail the
gate exists to exclude), and NO sector-string filter is applied. Capital-Markets
financials (S&P Global, Moody's, MSCI, exchanges, asset managers) have a real
revenue→COGS→gross-profit waterfall, are classified DEFINED by A1 (NOT in
METRIK_NA), and therefore stay in their own bucket — otherwise the relative arm
silently FAILs every sub-30%-margin compounder there. This is the IDENTICAL
cleaning A3 and the dispersion instrument use, so the medians pinned here are the
medians the rescue analysis is evaluated against.

Acceptance: each bucket's gm distribution is passed through is_bucket_acceptable
(constituent-median-spread OR antimode-gap reject). Only ACCEPTED buckets are
pinned in `entries`; REJECTED buckets are left out of the table -> the relative
arm cannot fire on them (runtime fail-safe by construction).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from app.errors import DataSourceError, DegradedDataError
from app.models.screener_record import ScreenerRecord
from app.screener.bucket_acceptance import is_bucket_acceptable
from app.screener.compose import build_screener_pipeline
from app.screener.filters import _node_chain
from app.screener.sector_buckets import resolve_bucket
from app.screener.universe_cleaning import clean_universe

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
    # yfinance .info surfaces 'sector' (gics_sector) and 'industry' (gics_industry).
    # CT-B does NOT use the sector: _node_chain rolls the industry up to its GICS
    # INDUSTRY GROUP via INDUSTRY_GROUP_MAP -> chain = [industry, group]. The group
    # is the exogenous, margin-blind intermediate node; the sector (multimodal
    # catch-all) is never consulted.
    has_industry = sum(1 for r in all_records if r.gics_industry)
    has_sector = sum(1 for r in all_records if r.gics_sector)
    has_neither = sum(1 for r in all_records if not r.gics_industry and not r.gics_sector)
    print(f"\n=== GICS NEST VIABILITY (Gate-A finding) ===")
    print(f"  gics_industry present: {has_industry}/{len(all_records)}")
    print(f"  gics_sector present:   {has_sector}/{len(all_records)}")
    print(f"  neither present:       {has_neither}/{len(all_records)}")
    print(
        "  node_chain = [gics_industry, gics_group]  (finest -> coarsest, 2 levels).\n"
        "  The coarsest node is the GICS industry GROUP, NOT the sector. A bucket that\n"
        "  resolves at the coarsest node is a GROUP rollup (the industry was below\n"
        "  n_min). Whether such a bucket is pinned is decided by the ACCEPTANCE GATE\n"
        "  (constituent-spread + antimode-gap), NOT by nest depth: a clean group\n"
        "  rollup is pinned, a multimodal one is left out (fail-safe)."
    )

    # --- Cleaned universe (shared clean_universe; negatives OUT, no sector string) ---
    cleaned: list[ScreenerRecord] = clean_universe(
        all_records, metrik_na, include_defined_negative=False
    )
    excluded_count = len(all_records) - len(cleaned)
    print(
        f"\nCleaned universe: {len(cleaned)} records "
        f"(excluded {excluded_count}: METRIK_NA per A1 + gm<=0/None; NO sector-string filter)"
    )

    # --- Build counts over cleaned universe ---
    counts: dict[str, int] = {}
    for rec in cleaned:
        for node in _node_chain(rec):
            counts[node] = counts.get(node, 0) + 1

    # --- Resolve bucket per record; group gm by bucket; track group rollups + constituents ---
    bucket_gms: dict[str, list[float]] = {}
    # A bucket is a GROUP rollup when resolve_bucket returns the coarsest node of the
    # chain (the industry was below n_min, so it rolled up to its GICS industry GROUP).
    group_rollup_buckets: set[str] = set()
    # Per-bucket constituent-industry gm lists feed the acceptance gate's spread test.
    bucket_constituent_gms: dict[str, dict[str, list[float]]] = {}
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
        industry = rec.gics_industry or "(none)"
        bucket_constituent_gms.setdefault(bucket, {}).setdefault(industry, []).append(gm)
        # Flag as a GROUP rollup if the bucket is the coarsest node of a multi-node chain.
        if chain and bucket == chain[-1] and len(chain) > 1:
            group_rollup_buckets.add(bucket)

    print(f"  Records with no qualifying bucket (n_min={n_min}): {no_bucket}")

    # --- Acceptance gate: only ACCEPTED buckets are pinned; rejected -> fail-safe ---
    # is_bucket_acceptable rejects on constituent-median-spread (multi-industry
    # heterogeneity) OR antimode-gap (multimodal distribution; the DEFECT-1 fix that
    # catches single-industry multimodality BC alone misses). A rejected bucket is
    # NOT pinned, so the relative arm cannot fire on it at runtime (fail-safe by
    # construction). Acceptance — not nest depth / group-rollup status — decides.
    entries: dict[str, float] = {}
    bucket_counts: dict[str, int] = {}
    bucket_verdict: dict[str, tuple[bool, list[str]]] = {}
    for bucket, gms in sorted(bucket_gms.items()):
        constituents = bucket_constituent_gms[bucket]
        constituent_medians = [statistics.median(v) for v in constituents.values()]
        accept, reasons = is_bucket_acceptable(gms, constituent_medians)
        bucket_verdict[bucket] = (accept, reasons)
        if accept:
            entries[bucket] = statistics.median(gms)
            bucket_counts[bucket] = counts.get(bucket, 0)

    # --- Print per-bucket dispersion + PIN/REJECT verdict ---
    print(f"\n=== PER-BUCKET DISPERSION + ACCEPTANCE (n_min={n_min}) ===")
    print(
        f"{'Bucket':<46} {'n_gm':>5} {'pop':>5} {'median':>8} {'min':>8} {'max':>8} {'verdict'}"
    )
    print("-" * 110)
    pinned = 0
    rejected = 0
    for bucket in sorted(bucket_gms.keys()):
        gms = bucket_gms[bucket]
        pop = counts.get(bucket, 0)
        accept, reasons = bucket_verdict[bucket]
        rollup = " GROUP-ROLLUP" if bucket in group_rollup_buckets else ""
        if accept:
            pinned += 1
            verdict = "PINNED" + rollup
        else:
            rejected += 1
            verdict = "REJECTED-FAIL-SAFE" + rollup
        print(
            f"{bucket:<46} {len(gms):>5} {pop:>5} "
            f"{statistics.median(gms):>8.4f} {min(gms):>8.4f} {max(gms):>8.4f} {verdict}"
        )
        if reasons:
            print(f"    -> reject reasons: {', '.join(reasons)}")

    print(f"\nBuckets clearing n_min: {len(bucket_gms)}")
    print(f"  PINNED (accepted, in table): {pinned}")
    print(f"  REJECTED-FAIL-SAFE (not pinned, relative arm cannot fire): {rejected}")
    print(f"  of which GROUP rollups (industry below n_min -> rolled to GICS group): "
          f"{len(group_rollup_buckets)}")
    print(
        "Note: a GROUP rollup is NOT rejected for being a rollup — the acceptance gate\n"
        "(constituent-spread + antimode-gap), not nest depth, decides pinning. A clean\n"
        "group rollup is pinned; a multimodal one is left out (fail-safe by construction)."
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
