"""0b GATE acceptance check (offline, reads the dry-run dropouts.csv):
(1) list the resolution data-quality diverts with their detail sub-reason;
(2) assert the predicted set {ML.PA, RNL.PA, GLB.IR} is among NO_SYMBOL_DATA;
(3) postcondition: zero basis_gates dropouts with empty market_cap_eur remain
    (= no missing-data symbol leaks to a gate anymore);
(4) report the FX_UNAVAILABLE count (non-zero = FX-fix trigger, not a 0b defect).
Run: uv run python scripts\\diagnose_0b_acceptance.py"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

DROPOUTS = Path("output/Universum/2026-06-dropouts.csv")
PREDICTED = {"ML.PA", "RNL.PA", "GLB.IR"}


def main() -> None:
    rows = list(csv.DictReader(DROPOUTS.open(encoding="utf-8")))
    nsd = [r for r in rows if r["reason_code"] == "RESOLUTION_NO_SYMBOL_DATA"]
    fxu = [r for r in rows if r["reason_code"] == "RESOLUTION_FX_UNAVAILABLE"]

    print("=== RESOLUTION_NO_SYMBOL_DATA diverts ===")
    for r in sorted(nsd, key=lambda r: r["ticker"]):
        print(f"  {r['ticker']:10} detail={r['detail']:12} severity={r['severity_bucket']}")
    print(f"detail breakdown: {dict(Counter(r['detail'] for r in nsd))}")
    print(f"\n=== RESOLUTION_FX_UNAVAILABLE diverts: {len(fxu)} ===")
    for r in sorted(fxu, key=lambda r: r["ticker"]):
        print(f"  {r['ticker']:10} severity={r['severity_bucket']}")

    nsd_set = {r["ticker"] for r in nsd}
    print(f"\nPredicted set {{ML,RNL,GLB}} subset of NO_SYMBOL_DATA? "
          f"{PREDICTED <= nsd_set}  (missing: {PREDICTED - nsd_set or 'none'})")

    # Postcondition: no basis_gates dropout with empty market_cap_eur leaks anymore.
    leaks = [r for r in rows if r["stage"] == "basis_gates" and not r["market_cap_eur"]]
    print(f"\nPOSTCONDITION basis_gates drops with empty market_cap_eur: {len(leaks)} "
          f"(expect 0)  {[r['ticker'] for r in leaks]}")

    # Severity sanity: all diverts must be REVIEW.
    bad = [r for r in nsd + fxu if r["severity_bucket"] != "REVIEW"]
    print(f"diverts NOT marked REVIEW (expect none): {[r['ticker'] for r in bad] or 'none'}")


if __name__ == "__main__":
    main()
