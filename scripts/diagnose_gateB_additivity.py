"""Gate-B additivity verification (Punkt 2 Phase E): prove the dual-arm gross-margin
gate is an OR-extension of the absolute arm, and that RELATIVE_RESCUE is tagged on
EXACTLY the sub-floor names the relative arm adds.

Run: uv run python scripts\\diagnose_gateB_additivity.py

$0, read-only, warm cache via build_screener_pipeline(). NO deploy, NO income_stmt
fetch — gross_margin comes from yfinance .info. This script uses the REAL activated
production config: the table from load_sector_median_table() and the live
filters.GROSS_MARGIN_RELATIVE_K. It runs OUTSIDE pytest, so the dormant
autouse fixture does NOT apply — that is intentional: this tests the real activation.

Domain: every universe record with a non-None gross_margin (the gross-margin gate's
domain). METRIK_NA / volume / market_cap diverts are orthogonal to this arm and are not
modelled here — we ask only "does the gross-margin gate let this gm through?".

Invariants printed and asserted:
  ADDITIVITY (load-bearing): pass_none==True  =>  pass_k==True for every record.
     The relative arm is an OR-extension; it must NEVER turn an absolute pass into a
     fail. Any violation is an OR-arm bug -> STOP (do not swallow).
  DELTA = {pass_k} \\ {pass_none}: names that pass ONLY with the relative arm.
  IDENTITY: count(reason=="RELATIVE_RESCUE") == |DELTA|. A mismatch means the
     RELATIVE_RESCUE definition is miscounting (e.g. tagging absolute-passers).
"""
from __future__ import annotations

import json
from pathlib import Path

from app.errors import DataSourceError, DegradedDataError
from app.models.screener_record import ScreenerRecord
from app.screener import filters
from app.screener.compose import build_screener_pipeline
from app.screener.filters import (
    _node_chain,
    gross_margin_pass_reason,
    passes_gross_margin_filter,
)
from app.screener.sector_buckets import bucket_median
from app.screener.sector_median_table import load_sector_median_table

UNIVERSE = Path("data/universe.json")


def main() -> None:
    # REAL activated config — no fixture, no override. If the table is absent the
    # relative arm is dormant and DELTA must be empty (additivity still holds trivially).
    table = load_sector_median_table()
    k = filters.GROSS_MARGIN_RELATIVE_K
    print(
        f"Activated config: table={'loaded' if table else 'ABSENT (arm dormant)'}, "
        f"GROSS_MARGIN_RELATIVE_K={k}"
    )
    if table is not None:
        print(f"  table: {len(table.entries)} buckets, n_min={table.n_min}")

    tickers: list[str] = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    yf_cached = build_screener_pipeline()

    records: list[ScreenerRecord] = []
    unresolved = 0
    for t in tickers:
        try:
            info = yf_cached.get_ticker_info(t)
        except (DataSourceError, DegradedDataError):
            unresolved += 1
            continue
        records.append(ScreenerRecord.from_yfinance_info(t, info))

    # Domain of the gross-margin gate: records with a non-None gross_margin.
    domain = [r for r in records if r.gross_margin is not None]
    print(
        f"\nUniverse: {len(tickers)} tickers, {unresolved} unresolved, "
        f"{len(records)} resolved, {len(domain)} with non-None gross_margin (gate domain)\n"
    )

    pass_none: set[str] = set()   # absolute arm only (table=None, k=None)
    pass_k: set[str] = set()      # dual arm, real activated config
    rescue_tags: set[str] = set()  # records tagged RELATIVE_RESCUE under the dual arm

    for rec in domain:
        if passes_gross_margin_filter(rec, table=None, k=None):
            pass_none.add(rec.ticker)
        if passes_gross_margin_filter(rec, table, k):
            pass_k.add(rec.ticker)
        if gross_margin_pass_reason(rec, table, k) == "RELATIVE_RESCUE":
            rescue_tags.add(rec.ticker)

    # --- ADDITIVITY: every absolute pass is still a pass under the dual arm ---
    additivity_offenders = sorted(pass_none - pass_k)
    additivity_ok = not additivity_offenders

    # --- DELTA: names that pass ONLY with the relative arm ---
    delta = sorted(pass_k - pass_none)

    # --- IDENTITY: RELATIVE_RESCUE count == |DELTA| ---
    identity_ok = len(rescue_tags) == len(delta)

    by_ticker = {r.ticker: r for r in domain}

    print("=" * 72)
    print("GATE-B INVARIANTS")
    print("=" * 72)
    print(f"|pass_none| (absolute arm only):      {len(pass_none)}")
    print(f"|pass_k|    (dual arm, k={k}):          {len(pass_k)}")
    print(f"|DELTA|     (relative-only passers):   {len(delta)}")
    print(f"RELATIVE_RESCUE tag count:            {len(rescue_tags)}")
    print(f"ADDITIVITY: {'ok' if additivity_ok else 'VIOLATED'}")
    print(f"IDENTITY:   {'ok' if identity_ok else 'MISMATCH'}")

    if not additivity_ok:
        print("\n*** ADDITIVITY VIOLATED ***")
        print("These records pass the absolute arm but FAIL the dual arm (OR-arm bug):")
        for t in additivity_offenders:
            r = by_ticker[t]
            print(f"    {t:<14} gm={r.gross_margin}")

    if not identity_ok:
        print("\n*** TAGGING MISMATCH ***")
        print("RELATIVE_RESCUE count != |DELTA| — the RELATIVE_RESCUE definition is wrong")
        print(f"    tagged-but-not-in-delta: {sorted(rescue_tags - set(delta))}")
        print(f"    in-delta-but-not-tagged: {sorted(set(delta) - rescue_tags)}")

    # --- DELTA roster (eyeball against A3 k=0.5 prediction of 175 sub-floor rescues) ---
    print("\n--- DELTA (relative-only passers) ---")
    for t in delta:
        r = by_ticker[t]
        med = bucket_median(_node_chain(r), table) if table is not None else None
        med_str = f"{med:.4f}" if med is not None else "None"
        print(
            f"    {t:<14} {r.name or '':<36} "
            f"gm={r.gross_margin:.4f}  bucket_median={med_str}  "
            f"sector={r.gics_sector or ''}  industry={r.gics_industry or ''}"
        )

    print(
        "\nNote: A3 (diagnose_k_calibration.py) counts sub-floor-only rescues; this script's\n"
        "DELTA is the same sub-floor rescue set (ABSOLUTE_PASS names are in BOTH pass_none\n"
        "and pass_k, so they cancel out of DELTA). They should align on ~175 at k=0.5."
    )


if __name__ == "__main__":
    main()
