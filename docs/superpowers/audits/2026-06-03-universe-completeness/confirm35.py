"""Confirmation re-probe of the 35 re-resolution failures — disambiguate
throttle-residue from genuine non-resolution. Probes each original ticker once
more (clean IP, generous spacing) AND a curated set of corrected/alternate
tickers for format/exchange suspects. Read-only.

Output: confirm35.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import yfinance as yf

HERE = Path(__file__).resolve().parent

UNRES = ['AKERBP.OL', 'AMS.VI', 'ASMI.AS', 'ATCOa.ST', 'BDEV.L', 'DLG.L',
         'DSM.SW', 'EFGI.PA', 'ELUXb.ST', 'ERICb.ST', 'FLTR.IR', 'HMB.ST',
         'ICP.L', 'INDV.L', 'INP.L', 'LIN.L', 'LUN.ST', 'MAN.DE', 'MOR.DE',
         'MRW.L', 'NEOEN.PA', 'NGG.L', 'RIGN.SW', 'ROL.L', 'SANO.HE',
         'SCHA.OL', 'SKFb.ST', 'SMDS.L', 'SOW.DE', 'SWMA.ST', 'TEL2b.ST',
         'TEV', 'UN01.DE', 'VAR1.DE']

# curated alternates for format/exchange/alias suspects
ALT = {
    'ATCOa.ST': ['ATCO-A.ST'], 'ERICb.ST': ['ERIC-B.ST'],
    'ELUXb.ST': ['ELUX-B.ST'], 'SKFb.ST': ['SKF-B.ST'],
    'TEL2b.ST': ['TEL2-B.ST'], 'HMB.ST': ['HM-B.ST'],
    'ATCOa.ST '.strip(): ['ATCO-A.ST'],
    'FLTR.IR': ['FLTR.L'], 'DSM.SW': ['DSFIR.AS'],
    'RIGN.SW': ['RIGN.VX'], 'SWMA.ST': ['SWMA.ST'],
    'AMS.VI': ['AMS.MC'], 'TEV': ['TEVA.TA'],
    'INP.L': ['INVP.L'], 'EFGI.PA': ['EFGN.SW'],
    'SANO.HE': ['SAA1V.HE'], 'LIN.L': ['LIN'],
    'ELUXb.ST ' .strip(): ['ELUX-B.ST'],
    'NGG.L': ['NG.L'], 'MAN.DE': ['MAN.SG'], 'MOR.DE': ['MOR.F'],
    'SOW.DE': ['SOW.F'], 'VAR1.DE': ['VAR1.F'], 'UN01.DE': ['UN01.F'],
}


def probe(t: str) -> dict:
    try:
        info = yf.Ticker(t).info
    except Exception as exc:  # noqa: BLE001
        return {"keys": 0, "error": repr(exc)[:120], "resolved": False}
    if not info:
        return {"keys": 0, "error": "empty", "resolved": False}
    k = len(info)
    name = info.get("shortName") or info.get("longName")
    return {"keys": k, "name": name, "marketCap": info.get("marketCap"),
            "currency": info.get("currency"), "quoteType": info.get("quoteType"),
            "resolved": k > 5 and bool(name or info.get("marketCap"))}


out: dict = {}
for t in UNRES:
    r = probe(t)
    r["alternates"] = {}
    if not r["resolved"]:
        for alt in ALT.get(t, []):
            time.sleep(2.0)
            r["alternates"][alt] = probe(alt)
    out[t] = r
    flag = "OK-NOW" if r["resolved"] else "still-fail"
    altinfo = {a: (v["resolved"], v.get("name")) for a, v in r["alternates"].items()}
    print(f"{t:12} keys={r['keys']:<3} {flag:10} name={str(r.get('name'))[:28]:28} alt={altinfo}")
    time.sleep(2.5)

(HERE / "confirm35.json").write_text(json.dumps(out, indent=1, default=str), "utf-8")
res_now = [t for t, r in out.items() if r["resolved"]]
alt_ok = {t: [a for a, v in r["alternates"].items() if v["resolved"]]
          for t, r in out.items() if not r["resolved"] and any(v["resolved"] for v in r["alternates"].values())}
hard = [t for t, r in out.items() if not r["resolved"] and not any(v["resolved"] for v in r["alternates"].values())]
print(f"\nRESOLVES-NOW (transient, NOT attrition): {len(res_now)} {res_now}")
print(f"ALTERNATE-RESOLVES (wrong ticker in universe): {alt_ok}")
print(f"HARD-FAIL (no original, no alternate): {len(hard)} {hard}")
