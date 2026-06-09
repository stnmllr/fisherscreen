"""Punkt 1 context: list GATE_VOLUME dropouts from the dry-run dropouts.csv,
split by severity. Re-confirms the 22 REVIEW large-caps dying at the share-count
floor (unchanged by 0a/0b). Reusable to track the volume-gate transition after
the value-floor change. Run: uv run python scripts\\diagnose_volume_review.py"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

DROPOUTS = Path("output/Universum/2026-06-dropouts.csv")


def main() -> None:
    rows = [r for r in csv.DictReader(DROPOUTS.open(encoding="utf-8"))
            if r["reason_code"] == "GATE_VOLUME"]
    by_sev = Counter(r["severity_bucket"] for r in rows)
    print(f"GATE_VOLUME total={len(rows)} by_severity={dict(by_sev)}")
    print("\n=== GATE_VOLUME REVIEW (large-caps dying at share-count floor) ===")
    rev = [r for r in rows if r["severity_bucket"] == "REVIEW"]
    for r in sorted(rev, key=lambda r: -float(r["market_cap_eur"] or 0)):
        mc = float(r["market_cap_eur"] or 0) / 1e9
        print(f"  {r['ticker']:12} {mc:7.1f} Mrd  {r['gics_sector']}")
    print(f"\nREVIEW count = {len(rev)}")


if __name__ == "__main__":
    main()
