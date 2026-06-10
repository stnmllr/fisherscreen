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
the pre-committed verdict rule (clean-rescue-set headline number).

Read-only, warm-cache ($0). Excludes the A1 METRIK_NA set + Financials/REITs +
gm<=0, mirroring A2/A3.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from app.errors import DataSourceError, DegradedDataError
from app.models.screener_record import ScreenerRecord
from app.screener.compose import build_screener_pipeline
from app.screener.filters import MIN_GROSS_MARGIN, _node_chain
from app.screener.sector_buckets import resolve_bucket

UNIVERSE = Path("data/universe.json")
AUDIT_DIR = Path("docs/superpowers/audits/2026-06-09-2-gross-margin-floor")
METRIK_NA_JSON = AUDIT_DIR / "metrik_na_tickers.json"

_DEFAULT_N_MIN = 8

# Transparent acceptance thresholds (NOT margin-tuned — see map _meta).
CONSTITUENT_SPREAD_THRESHOLD = 0.15   # max-min of constituent-industry medians
BIMODALITY_THRESHOLD = 0.555          # Pearson/SAS bimodality coefficient cutoff
HIST_BINS = 10


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested in tests/screener/test_bucket_dispersion_helpers.py)
# --------------------------------------------------------------------------- #
def sample_skewness(values: list[float]) -> float | None:
    """Sample skewness (Fisher-Pearson, biased moment estimator g1).
    Returns None for n < 3 or zero variance (undefined)."""
    n = len(values)
    if n < 3:
        return None
    mean = statistics.fmean(values)
    m2 = sum((x - mean) ** 2 for x in values) / n
    m3 = sum((x - mean) ** 3 for x in values) / n
    if m2 == 0:
        return None
    return m3 / (m2 ** 1.5)


def sample_kurtosis(values: list[float]) -> float | None:
    """Sample kurtosis (NON-excess, i.e. m4/m2^2; normal == 3.0).
    Returns None for n < 4 or zero variance (undefined)."""
    n = len(values)
    if n < 4:
        return None
    mean = statistics.fmean(values)
    m2 = sum((x - mean) ** 2 for x in values) / n
    m4 = sum((x - mean) ** 4 for x in values) / n
    if m2 == 0:
        return None
    return m4 / (m2 ** 2)


def bimodality_coefficient(values: list[float]) -> float | None:
    """BC = (skewness^2 + 1) / kurtosis  (kurtosis NON-excess).
    BC > 0.555 (uniform-distribution reference) suggests bimodality.
    Returns None when skew/kurtosis are undefined (small n / zero variance)."""
    skew = sample_skewness(values)
    kurt = sample_kurtosis(values)
    if skew is None or kurt is None or kurt == 0:
        return None
    return (skew ** 2 + 1) / kurt


def constituent_median_spread(constituent_medians: list[float]) -> float | None:
    """max - min over the per-constituent-industry medians of a group bucket.
    Returns None for fewer than 2 constituents (a single-industry bucket cannot
    be multimodal across constituents)."""
    if len(constituent_medians) < 2:
        return None
    return max(constituent_medians) - min(constituent_medians)


def iqr(values: list[float]) -> float | None:
    """Inter-quartile range p75 - p25 (statistics.quantiles, exclusive method).
    Returns None for n < 2."""
    if len(values) < 2:
        return None
    qs = statistics.quantiles(values, n=4, method="exclusive")
    return qs[2] - qs[0]


def mad(values: list[float]) -> float | None:
    """Median absolute deviation about the median. None for empty input."""
    if not values:
        return None
    med = statistics.median(values)
    return statistics.median([abs(x - med) for x in values])


def ascii_histogram(values: list[float], *, bins: int = HIST_BINS, width: int = 40) -> list[str]:
    """Compact ASCII histogram so a human can eyeball unimodality directly.
    Returns a list of lines (bin range + bar)."""
    if not values:
        return ["  (no values)"]
    lo, hi = min(values), max(values)
    if hi == lo:
        return [f"  [{lo:.3f}] {'#' * min(width, len(values))} ({len(values)})"]
    span = hi - lo
    edges = [lo + span * i / bins for i in range(bins + 1)]
    counts = [0] * bins
    for x in values:
        idx = int((x - lo) / span * bins)
        if idx == bins:  # the maximum lands exactly on the top edge
            idx = bins - 1
        counts[idx] += 1
    peak = max(counts) or 1
    lines: list[str] = []
    for i in range(bins):
        bar = "#" * round(counts[i] / peak * width)
        lines.append(f"  [{edges[i]:6.3f},{edges[i + 1]:6.3f}) {bar} {counts[i]}")
    return lines


# --------------------------------------------------------------------------- #
# Universe cleaning (mirrors A2/A3)
# --------------------------------------------------------------------------- #
def _load_metrik_na() -> set[str]:
    if not METRIK_NA_JSON.exists():
        raise SystemExit(
            f"A1 output missing: {METRIK_NA_JSON} — run A1 (definedness probe) first."
        )
    return set(json.loads(METRIK_NA_JSON.read_text(encoding="utf-8"))["metrik_na"])


def _is_excluded(rec: ScreenerRecord, metrik_na: set[str]) -> bool:
    """METRIK_NA set + Financials/REITs + gm<=0/missing. Same cleaned-universe
    definition the calibration probes use."""
    if rec.ticker in metrik_na:
        return True
    gm = rec.gross_margin
    if gm is None or gm <= 0:
        return True
    sector = rec.gics_sector or ""
    if "Financ" in sector or "Real Estate" in sector:
        return True
    return False


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

    cleaned = [r for r in all_records if not _is_excluded(r, metrik_na)]
    print(
        f"Universe: {len(all_records)} records ({unresolved} unresolved); "
        f"cleaned: {len(cleaned)} (excluded METRIK_NA/Financials/REIT/gm<=0)"
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

    # --- Per-bucket dispersion + multimodality report ---
    multimodal_suspect: set[str] = set()
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

        flags: list[str] = []
        if spread is not None and spread > CONSTITUENT_SPREAD_THRESHOLD:
            flags.append("MULTIMODAL-SUSPECT(constituent-spread)")
            multimodal_suspect.add(bucket)
        if bc is not None and bc > BIMODALITY_THRESHOLD:
            flags.append("BIMODAL-SUSPECT(BC)")
            multimodal_suspect.add(bucket)

        iqr_str = f"{b_iqr:.4f}" if b_iqr is not None else "n/a"
        mad_str = f"{b_mad:.4f}" if b_mad is not None else "n/a"
        bc_str = f"{bc:.4f}" if bc is not None else "n/a"
        spread_str = f"{spread:.4f}" if spread is not None else "n/a"

        print(f"\n{bucket}  (n={len(gms)})")
        print(
            f"  median={med:.4f}  IQR={iqr_str}  std={std:.4f}  MAD={mad_str}  "
            f"BC={bc_str}  constituent-spread={spread_str}"
        )
        if flags:
            print(f"  FLAGS: {', '.join(flags)}")
        print("  constituent industries (median gm, n):")
        for industry, v in sorted(
            constituents.items(), key=lambda kv: statistics.median(kv[1])
        ):
            print(f"    {industry:<46} median={statistics.median(v):.4f}  n={len(v)}")
        print("  gm histogram:")
        for line in ascii_histogram(gms):
            print(line)

    print(f"\nBuckets clearing n_min: {len(bucket_gms)}")
    print(f"Multimodal-suspect buckets: {len(multimodal_suspect)} -> {sorted(multimodal_suspect)}")

    # --- RESCUE-SET section: feeds the pre-committed verdict rule ---
    sub_floor = [
        r for r in cleaned
        if r.gross_margin is not None and r.gross_margin < MIN_GROSS_MARGIN
    ]
    clean_rescuable: list[tuple[ScreenerRecord, str]] = []
    suspect_or_no_bucket: list[ScreenerRecord] = []
    for rec in sub_floor:
        bucket = resolve_bucket(_node_chain(rec), counts, n_min=n_min)
        if bucket is not None and bucket not in multimodal_suspect:
            clean_rescuable.append((rec, bucket))
        else:
            suspect_or_no_bucket.append(rec)

    print(f"\n=== RESCUE SET (sub-floor gm < {MIN_GROSS_MARGIN}) ===")
    print(f"Sub-floor records: {len(sub_floor)}")
    print(f"Candidate-rescuable on a CLEAN bucket: {len(clean_rescuable)}")
    print(f"Only in a multimodal-suspect bucket or no bucket (fail-safe): "
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
