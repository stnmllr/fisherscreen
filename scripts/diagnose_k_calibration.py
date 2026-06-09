"""Gate-A calibration probe A3 (Punkt 2): calibrate the relative-arm k factor
against the A2 candidate sector-median table.

Run: uv run python scripts\\diagnose_k_calibration.py

Chain position: A1 -> A2 -> A3. MUST run AFTER A2 has written the candidate JSON.

For each k in K_CANDIDATES: for every cleaned record with gm < MIN_GROSS_MARGIN,
compute whether gm >= k * bucket_median(chain, table).
  - "rescued": gm < MIN_GROSS_MARGIN BUT gm >= k * median (relative arm saves it)
  - "still-failing": gm < MIN_GROSS_MARGIN AND gm < k * median (absolute + relative both fail)

Acceptance criterion: pick the LARGEST k whose sub-k band (still-failing) is dominated
by real broken-margin cases and is near-empty in healthy sectors.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.errors import DataSourceError, DegradedDataError
from app.models.screener_record import ScreenerRecord
from app.screener.compose import build_screener_pipeline
from app.screener.filters import MIN_GROSS_MARGIN, _node_chain
from app.screener.sector_buckets import SectorMedianTable, bucket_median
from app.screener.sector_median_table import load_sector_median_table

UNIVERSE = Path("data/universe.json")
CANDIDATE_JSON = Path(
    "docs/superpowers/audits/2026-06-09-2-gross-margin-floor/"
    "sector_median_table.candidate.json"
)

K_CANDIDATES: list[float] = [0.3, 0.4, 0.5, 0.6, 0.7]


def _is_excluded_proxy(rec: ScreenerRecord) -> bool:
    """Same exclusion proxy as A2: drop METRIK_NA / Financials / REITs."""
    gm = rec.gross_margin
    if gm is None or gm <= 0:
        return True
    sector = rec.gics_sector or ""
    if "Financ" in sector or "Real Estate" in sector:
        return True
    return False


def _load_candidate_table() -> tuple[SectorMedianTable, str]:
    """Load the A2 candidate JSON; return (SectorMedianTable, vintage string)."""
    if not CANDIDATE_JSON.exists():
        raise FileNotFoundError(
            f"Candidate table not found at {CANDIDATE_JSON}. "
            "Run A2 (diagnose_sector_median_table.py) first."
        )
    data = json.loads(CANDIDATE_JSON.read_text(encoding="utf-8"))
    table = SectorMedianTable(
        entries={k: float(v) for k, v in data["entries"].items()},
        n_min=int(data["n_min"]),
        counts={k: int(v) for k, v in data["counts"].items()},
    )
    vintage: str = data.get("vintage", "")
    return table, vintage


def main() -> None:
    table, vintage = _load_candidate_table()
    print(
        f"Candidate table loaded: {len(table.entries)} buckets, "
        f"n_min={table.n_min}, vintage={vintage}"
    )

    tickers: list[str] = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    yf_cached = build_screener_pipeline()

    # Build cleaned universe (warm cache, $0)
    all_records: list[ScreenerRecord] = []
    unresolved = 0
    for t in tickers:
        try:
            info = yf_cached.get_ticker_info(t)
        except (DataSourceError, DegradedDataError):
            unresolved += 1
            continue
        all_records.append(ScreenerRecord.from_yfinance_info(t, info))

    cleaned = [r for r in all_records if not _is_excluded_proxy(r)]
    print(f"Cleaned universe: {len(cleaned)} records ({unresolved} unresolved)")

    # Sub-floor band: cleaned records with gm < MIN_GROSS_MARGIN (the relative arm matters here)
    sub_floor = [r for r in cleaned if r.gross_margin is not None and r.gross_margin < MIN_GROSS_MARGIN]
    print(
        f"Sub-absolute-floor band (gm < {MIN_GROSS_MARGIN}): "
        f"{len(sub_floor)} records — these are what the relative arm operates on\n"
    )

    # Per-k analysis
    for k in K_CANDIDATES:
        rescued: list[ScreenerRecord] = []
        still_failing: list[ScreenerRecord] = []
        no_bucket: list[ScreenerRecord] = []

        for rec in sub_floor:
            gm = rec.gross_margin
            assert gm is not None  # guaranteed by sub_floor construction
            chain = _node_chain(rec)
            med = bucket_median(chain, table)
            if med is None:
                # No qualifying bucket: relative arm does not fire -> stays failing
                no_bucket.append(rec)
                continue
            if gm >= k * med:
                rescued.append(rec)
            else:
                still_failing.append(rec)

        print(f"{'='*70}")
        print(f"k = {k}")
        print(f"  Rescued (gm >= k*median):            {len(rescued)}")
        print(f"  Still-failing (gm < k*median):       {len(still_failing)}")
        print(f"  No qualifying bucket (arm dormant):  {len(no_bucket)}")

        if rescued:
            print("  --- Rescued names ---")
            for rec in sorted(rescued, key=lambda r: r.ticker):
                med = bucket_median(_node_chain(rec), table)
                med_str = f"{med:.4f}" if med is not None else "None"
                print(
                    f"    {rec.ticker:<14} {rec.name or '':<40} "
                    f"gm={rec.gross_margin:.4f}  sector={rec.gics_sector or ''}"
                    f"  industry={rec.gics_industry or ''}"
                    f"  bucket_median={med_str}"
                )

        if still_failing:
            print("  --- Sub-k band (still-failing) composition ---")
            for rec in sorted(still_failing, key=lambda r: r.ticker):
                med = bucket_median(_node_chain(rec), table)
                med_str = f"{med:.4f}" if med is not None else "None"
                print(
                    f"    {rec.ticker:<14} {rec.name or '':<40} "
                    f"gm={rec.gross_margin:.4f}  sector={rec.gics_sector or ''}"
                    f"  industry={rec.gics_industry or ''}"
                    f"  bucket_median={med_str}"
                )
        print()

    print(
        "=== ACCEPTANCE CRITERION ===\n"
        "Pick the LARGEST k whose sub-k band (still-failing) is dominated by real\n"
        "broken-margin cases and is near-empty in healthy sectors.\n"
        "Expected rescued names at moderate k: Colruyt, DIA, Maersk, NVR, etc.\n"
        "(Low-margin legitimate businesses in structurally low-margin industries.)\n"
        "If the sub-k band at the chosen k still contains healthy-sector names,\n"
        "lower k or investigate those tickers before activating the table."
    )


if __name__ == "__main__":
    main()
