"""Punkt 1 GATE-B acceptance: reconcile the cold-run dropouts.csv against the
GATE-A prognosis. Checks (1) GATE_VOLUME now == {FER.AS,1COV.DE,CTG.L,LANV};
(2) resolution NO_PRICE divert count (find, not defect); (3) the 10 predicted
survivors are NOT in dropouts (= survivors); (4) the 13 doomed-rescued now drop at
gross_margin/rev_growth, not volume. Run: uv run python scripts\\diagnose_p1_gateB_acceptance.py"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

UNIVERSE = Path("data/universe.json")
DROPOUTS = Path("output/Universum/2026-06-dropouts.csv")

EXP_VOLUME = {"FER.AS", "1COV.DE", "CTG.L", "LANV"}
EXP_SURVIVORS = {"FLTR.L", "GAW.L", "GHC", "LISN.SW", "LPP.WA",
                 "MELE.BR", "SIX2.DE", "SLHN.SW", "VACN.SW", "VCT.PA"}
EXP_DOOMED = {"ANA.MC", "BARN.SW", "COLR.BR", "DIA.MC", "DIE.BR", "EMSN.SW",
              "GIVN.SW", "MAERSK-B.CO", "MF.PA", "NVR", "RCO.PA", "SCMN.SW", "VIG.VI"}


def main() -> None:
    rows = list(csv.DictReader(DROPOUTS.open(encoding="utf-8")))
    universe = set(json.loads(UNIVERSE.read_text(encoding="utf-8")))
    by_t = {r["ticker"]: r for r in rows}
    survivors = universe - set(by_t)

    vol = {r["ticker"] for r in rows if r["reason_code"] == "GATE_VOLUME"}
    print(f"GATE_VOLUME drops = {len(vol)}: {sorted(vol)}")
    print(f"  == expected {{FER,1COV,CTG,LANV}}? {vol == EXP_VOLUME}  "
          f"(unexpected: {vol - EXP_VOLUME or 'none'}; missing: {EXP_VOLUME - vol or 'none'})")

    nsd = [r for r in rows if r["reason_code"] == "RESOLUTION_NO_SYMBOL_DATA"]
    print(f"\nRESOLUTION_NO_SYMBOL_DATA detail breakdown: "
          f"{dict(Counter(r['detail'] for r in nsd))}")
    no_price = [r["ticker"] for r in nsd if r["detail"] == "NO_PRICE"]
    print(f"  NO_PRICE diverts (find, not defect): {no_price or 'none'}")

    print(f"\nPredicted 10 survivors present (not dropped)? {EXP_SURVIVORS <= survivors}")
    missing = EXP_SURVIVORS - survivors
    if missing:
        for t in sorted(missing):
            print(f"  MISSING SURVIVOR {t} -> dropped at {by_t[t]['reason_code']}")

    print(f"\n13 doomed-rescued now drop at follow-on gate (not GATE_VOLUME):")
    for t in sorted(EXP_DOOMED):
        rc = by_t[t]["reason_code"] if t in by_t else "NOT DROPPED (survivor!)"
        print(f"  {t:12} -> {rc}")


if __name__ == "__main__":
    main()
