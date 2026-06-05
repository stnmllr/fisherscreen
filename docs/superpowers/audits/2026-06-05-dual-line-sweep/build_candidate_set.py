"""Dual-line sweep — STEP 1 (offline, no network).

Question being set up: is the Roche pattern (universe anchors the ILLIQUID
share-class line of an issuer that also has a liquid line) a one-off or a class?

This instrument builds the deterministic CANDIDATE SET for that question:
every ticker that RESOLVES in yfinance but dies at the volume gate
(avg_daily_volume < MIN_AVG_DAILY_VOLUME = 100_000). These are the only tickers
where a "wrong/illiquid line is anchored" defect could exist — a resolving but
illiquid line is exactly the Roche shape.

Sources (both already in-repo, no live calls):
  - re_resolution.json  : independent per-ticker yfinance probe from the
                          2026-06-03 completeness audit. Vintage = universe N=1349
                          (pre PR #22). Carries exactly the basis-filter fields,
                          incl. averageVolume.
  - data/universe.json  : CURRENT universe (N=1332, post PR #22). Used to INTERSECT
                          so pruned/deduped 1349-era tickers don't leak into the set.

Why this is sound despite the 1349 vintage: PR #22 only removed/renamed 17
tickers; intersecting against the current 1332 universe drops any candidate that
is no longer a member. A candidate that survived PR #22 and was illiquid in the
audit probe is a valid Step-2 input. (Volume figures are audit-time; Step 2
re-verifies the SISTER line live anyway.)

NOT production code. Read-only.
Run: uv run python docs/superpowers/audits/2026-06-05-dual-line-sweep/build_candidate_set.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent
UNIVERSE = ROOT / "data" / "universe.json"
RERES = HERE.parent / "2026-06-03-universe-completeness" / "re_resolution.json"
OUT_CSV = HERE / "candidate_set.csv"

# Mirror app/screener/filters.py exactly (verified against source on 2026-06-05).
MIN_AVG_DAILY_VOLUME = 100_000


def main() -> int:
    universe = set(json.loads(UNIVERSE.read_text(encoding="utf-8")))
    reres = json.loads(RERES.read_text(encoding="utf-8"))

    candidates: list[dict] = []
    resolved_not_in_universe = 0
    none_volume_resolved = 0

    for ticker, rec in reres.items():
        if not rec.get("resolved"):
            continue
        if ticker not in universe:
            # pruned / deduped / renamed by PR #22 — not a current member
            resolved_not_in_universe += 1
            continue
        vol = rec.get("averageVolume")
        if vol is None:
            # missing-volume is a different failure mode (not illiquidity) —
            # excluded from the dual-line candidate set by design.
            none_volume_resolved += 1
            continue
        if vol < MIN_AVG_DAILY_VOLUME:
            candidates.append(
                {
                    "ticker": ticker,
                    "name": rec.get("longName") or rec.get("shortName") or "",
                    "avg_volume": vol,
                    "market_cap": rec.get("marketCap"),
                    "currency": rec.get("currency"),
                    "gross_margin": rec.get("grossMargins"),
                    "revenue_growth": rec.get("revenueGrowth"),
                    "sector": rec.get("sector"),
                    "suffix": ticker.split(".", 1)[1] if "." in ticker else "(US)",
                }
            )

    candidates.sort(key=lambda c: (c["suffix"], c["ticker"]))

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "ticker", "name", "avg_volume", "market_cap", "currency",
                "gross_margin", "revenue_growth", "sector", "suffix",
            ],
        )
        w.writeheader()
        w.writerows(candidates)

    # Console summary for the gate review.
    print(f"re_resolution.json records : {len(reres)} (vintage N=1349)")
    print(f"current universe.json      : {len(universe)} (N=1332)")
    print(f"resolved-but-not-in-1332   : {resolved_not_in_universe} (pruned/deduped)")
    print(f"resolved w/ None volume    : {none_volume_resolved} (excluded: missing-data)")
    print(f"CANDIDATE SET (resolved & avg_volume < {MIN_AVG_DAILY_VOLUME}): {len(candidates)}")
    print()

    by_suffix: dict[str, int] = {}
    for c in candidates:
        by_suffix[c["suffix"]] = by_suffix.get(c["suffix"], 0) + 1
    print("by exchange suffix:")
    for sfx, n in sorted(by_suffix.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {sfx:8s} {n}")
    print()

    print(f"{'ticker':14s} {'avgVol':>9s} {'mcap(B)':>8s} {'cur':4s} {'gm':>6s} {'name'}")
    for c in candidates:
        mcap = c["market_cap"]
        mcap_b = f"{mcap/1e9:.2f}" if isinstance(mcap, (int, float)) else "?"
        gm = c["gross_margin"]
        gm_s = f"{gm:.2f}" if isinstance(gm, (int, float)) else "?"
        print(
            f"{c['ticker']:14s} {c['avg_volume']:>9d} {mcap_b:>8s} "
            f"{str(c['currency'] or '?'):4s} {gm_s:>6s} {c['name']}"
        )

    print(f"\nwritten: {OUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
