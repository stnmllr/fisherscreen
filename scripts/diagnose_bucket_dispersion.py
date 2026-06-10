"""Gate-A acceptance instrument (Punkt 2, CT-B): the INDEPENDENT dispersion /
unimodality gate over the new GICS-industry-group backbone.

Run: uv run python scripts\\diagnose_bucket_dispersion.py [n_min]

This is the acceptance gate that decides whether the relative arm is justified.
For the cleaned 2026-06 universe it resolves each record's bucket via the
production `_node_chain` (industry -> GICS group, NO sector) and, for every
bucket clearing n_min, reports:

  - n, median gm, IQR (p75-p25), std, MAD.
  - the constituent yfinance industries with each industry's own median gm and
    count — the catch-all/heterogeneity detector. A group-bucket whose
    constituent industries have widely-divergent individual medians is
    multimodal (e.g. Transportation = Railroads ~0.46 vs Trucking/Marine ~0.24).
    Flagged MULTIMODAL-SUSPECT when max-min of constituent medians > 0.15.
  - bimodality coefficient BC = (skew^2 + 1) / kurtosis (sample moments,
    small-n guarded); BC > 0.555 flagged bimodal-suspect. Plus a compact ASCII
    mini-histogram of the raw gm values for a human eyeball check.

Then a RESCUE-SET section over sub-floor records (gm < MIN_GROSS_MARGIN) feeding
the pre-committed verdict rule (clean-rescue-set headline number). The
clean-rescue-set is now defined as sub-floor names landing in an
is_bucket_acceptable bucket — so the antimode gate (DEFECT-1 fix) excludes the
single-industry multimodal buckets (e.g. Specialty Business Services, Travel
Services) that the bimodality coefficient alone let slip through.

Read-only, warm-cache ($0). Cleaning is the SHARED clean_universe definition
(METRIK_NA out, negatives out, NO sector-string filter) — identical to A2/A3, so
the rescue analysis is evaluated against the medians that would deploy.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from app.errors import DataSourceError, DegradedDataError
from app.models.screener_record import ScreenerRecord
from app.screener.bucket_acceptance import (
    ascii_histogram,
    bimodality_coefficient,
    constituent_median_spread,
    iqr,
    is_bucket_acceptable,
    mad,
)
from app.screener.compose import build_screener_pipeline
from app.screener.filters import MIN_GROSS_MARGIN, _node_chain
from app.screener.sector_buckets import resolve_bucket
from app.screener.universe_cleaning import clean_universe

UNIVERSE = Path("data/universe.json")
AUDIT_DIR = Path("docs/superpowers/audits/2026-06-09-2-gross-margin-floor")
METRIK_NA_JSON = AUDIT_DIR / "metrik_na_tickers.json"

_DEFAULT_N_MIN = 8


# --------------------------------------------------------------------------- #
# Universe cleaning (shared clean_universe — mirrors A2/A3)
# --------------------------------------------------------------------------- #
def _load_metrik_na() -> set[str]:
    if not METRIK_NA_JSON.exists():
        raise SystemExit(
            f"A1 output missing: {METRIK_NA_JSON} — run A1 (definedness probe) first."
        )
    return set(json.loads(METRIK_NA_JSON.read_text(encoding="utf-8"))["metrik_na"])


def main() -> None:
    n_min: int = int(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_N_MIN

    metrik_na = _load_metrik_na()
    print(f"Loaded {len(metrik_na)} METRIK_NA tickers from A1 output.")

    tickers: list[str] = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    yf_cached = build_screener_pipeline()

    all_records: list[ScreenerRecord] = []
    unresolved = 0
    for t in tickers:
        try:
            info = yf_cached.get_ticker_info(t)
        except (DataSourceError, DegradedDataError):
            unresolved += 1
            continue
        all_records.append(ScreenerRecord.from_yfinance_info(t, info))

    cleaned = clean_universe(all_records, metrik_na, include_defined_negative=False)
    print(
        f"Universe: {len(all_records)} records ({unresolved} unresolved); "
        f"cleaned: {len(cleaned)} (shared clean_universe: METRIK_NA out, negatives out, "
        "NO sector-string filter)"
    )

    # --- Counts over the production chain (industry -> group, NO sector) ---
    counts: dict[str, int] = {}
    for rec in cleaned:
        for node in _node_chain(rec):
            counts[node] = counts.get(node, 0) + 1

    # --- Resolve bucket per record; collect gm per bucket and the constituent
    #     yfinance industries that fed each bucket. ---
    bucket_gms: dict[str, list[float]] = {}
    bucket_constituent_gms: dict[str, dict[str, list[float]]] = {}
    no_bucket = 0
    for rec in cleaned:
        chain = _node_chain(rec)
        bucket = resolve_bucket(chain, counts, n_min=n_min)
        gm = rec.gross_margin
        if bucket is None or gm is None:
            if bucket is None:
                no_bucket += 1
            continue
        bucket_gms.setdefault(bucket, []).append(gm)
        industry = rec.gics_industry or "(none)"
        bucket_constituent_gms.setdefault(bucket, {}).setdefault(industry, []).append(gm)

    print(f"Records with no qualifying bucket (n_min={n_min}): {no_bucket}")

    # --- Per-bucket dispersion + acceptance report ---
    # ACCEPTANCE drives the rescue set: is_bucket_acceptable rejects on
    # constituent-median-spread (multi-industry heterogeneity) OR an antimode gap
    # (the DEFECT-1 fix: an empty bin separating two populated clusters, which the
    # bimodality coefficient under-detects). BC is reported as advisory only. Raw
    # width/IQR is NOT a reject reason — wide-but-unimodal buckets pass.
    rejected_buckets: set[str] = set()
    print(f"\n=== PER-BUCKET DISPERSION (n_min={n_min}) ===")
    for bucket in sorted(bucket_gms.keys()):
        gms = bucket_gms[bucket]
        med = statistics.median(gms)
        std = statistics.pstdev(gms) if len(gms) > 1 else 0.0
        b_iqr = iqr(gms)
        b_mad = mad(gms)
        bc = bimodality_coefficient(gms)

        # constituent-industry medians (heterogeneity detector)
        constituents = bucket_constituent_gms[bucket]
        constituent_medians = [statistics.median(v) for v in constituents.values()]
        spread = constituent_median_spread(constituent_medians)

        accept, reasons = is_bucket_acceptable(gms, constituent_medians)
        if not accept:
            rejected_buckets.add(bucket)

        iqr_str = f"{b_iqr:.4f}" if b_iqr is not None else "n/a"
        mad_str = f"{b_mad:.4f}" if b_mad is not None else "n/a"
        bc_str = f"{bc:.4f}" if bc is not None else "n/a"
        spread_str = f"{spread:.4f}" if spread is not None else "n/a"

        verdict = "ACCEPT" if accept else "REJECT-FAIL-SAFE"
        print(f"\n{bucket}  (n={len(gms)})  [{verdict}]")
        print(
            f"  median={med:.4f}  IQR={iqr_str}  std={std:.4f}  MAD={mad_str}  "
            f"BC={bc_str}(advisory)  constituent-spread={spread_str}"
        )
        if reasons:
            print(f"  REJECT REASONS: {', '.join(reasons)}")
        print("  constituent industries (median gm, n):")
        for industry, v in sorted(
            constituents.items(), key=lambda kv: statistics.median(kv[1])
        ):
            print(f"    {industry:<46} median={statistics.median(v):.4f}  n={len(v)}")
        print("  gm histogram:")
        for line in ascii_histogram(gms):
            print(line)

    print(f"\nBuckets clearing n_min: {len(bucket_gms)}")
    print(f"Rejected (fail-safe) buckets: {len(rejected_buckets)} -> {sorted(rejected_buckets)}")

    # --- RESCUE-SET section: feeds the pre-committed verdict rule ---
    sub_floor = [
        r for r in cleaned
        if r.gross_margin is not None and r.gross_margin < MIN_GROSS_MARGIN
    ]
    # Clean-rescue-set := sub-floor names landing in an is_bucket_acceptable bucket.
    # The antimode gate now excludes the multimodal single-industry buckets (SBS,
    # Travel Services) that BC alone passed.
    clean_rescuable: list[tuple[ScreenerRecord, str]] = []
    suspect_or_no_bucket: list[ScreenerRecord] = []
    for rec in sub_floor:
        bucket = resolve_bucket(_node_chain(rec), counts, n_min=n_min)
        if bucket is not None and bucket not in rejected_buckets:
            clean_rescuable.append((rec, bucket))
        else:
            suspect_or_no_bucket.append(rec)

    print(f"\n=== RESCUE SET (sub-floor gm < {MIN_GROSS_MARGIN}) ===")
    print(f"Sub-floor records: {len(sub_floor)}")
    print(f"Candidate-rescuable on an ACCEPTED bucket: {len(clean_rescuable)}")
    print(f"Only in a REJECTED (fail-safe) bucket or no bucket: "
          f"{len(suspect_or_no_bucket)}")
    if clean_rescuable:
        print("  --- clean-rescuable names ---")
        for rec, bucket in sorted(clean_rescuable, key=lambda rb: rb[0].ticker):
            med = statistics.median(bucket_gms[bucket])
            print(
                f"    {rec.ticker:<14} {rec.name or '':<40} "
                f"gm={rec.gross_margin:.4f}  clean_bucket={bucket}  bucket_median={med:.4f}"
            )

    print(f"\n>>> clean-rescue-set size = {len(clean_rescuable)}")
    print(
        "\nVerdict rule: non-trivial clean-rescue-set (several homogeneous low-margin\n"
        "groups n>=8) -> relative arm justified; quasi-empty -> relative arm is\n"
        "vestigial, ship Punkt 2 with definedness-exclusion + absolute floor only\n"
        "(drop the relative arm)."
    )
    print(
        "\nNOTE: read-only acceptance probe. Touches no committed table; "
        "the relative arm stays DORMANT (GROSS_MARGIN_RELATIVE_K=None) regardless."
    )


if __name__ == "__main__":
    main()
