#!/usr/bin/env python3
"""Read-only diagnostic (SUB-PHASE 1): probe yfinance resolution for the 79
symbols that 404'd ('Quote not found') in the 2026-06-02 cold dry-run.

Goal: classify each as
  RESOLVES  — yfinance returns a real quote now (transient 06-02 404), keep as-is
  BROKEN    — still no quote (candidate for generator-fix / rename / drop)

For BROKEN ones it also tries deterministic + curated candidate corrections and
reports the first that resolves (with longName, so the correction can be verified
by name).

NOT production code. Run: uv run python scripts/resolve_universe_symbols.py
"""
from __future__ import annotations

import sys
import time

import yfinance as yf

# The 79 unresolved symbols harvested from the 2026-06-02 16:26 cold run logs.
FAILED: list[str] = [
    "ADH.OL", "AHT.L", "ALLFG.MC", "ARGX.AS", "ARND.DE", "BA..L", "BALN.SW",
    "BEB.SW", "BRNW.MI", "BT.A.L", "CASP.ST", "CCH.SW", "DASH.DE", "EFGI.PA",
    "ENGIE.PA", "ESLX.PA", "EVR.L", "FALK.CO", "FERR.MI", "FOR.MC", "GFT.IR",
    "GREG.L", "GRLS.MC", "GWI.MI", "HELN.SW", "HLI.L", "HLM.L", "HNR.DE",
    "IDP.MI", "IGGI.L", "INP.L", "INPST.LU", "IPX.PA", "JUST.AS", "LANV.PA",
    "LIF.IR", "LIN.L", "LUMI.PA", "MGG.L", "MT.LU", "NAB.AT", "NDA-SE.HE",
    "NOV-N.SW", "NSN.HE", "ONT.BR", "ORAN.PA", "PANDORA.CO", "PHNX.L", "PLPH.SW",
    "PSN.PA", "QIA.AS", "ROG.SW", "RR..L", "S4.L", "SANO.HE", "SEB.ST", "SIG.SW",
    "SKG.IR", "SN..L", "SNY.PA", "SON.SW", "SRB.OL", "SRENH.SW", "STER.HE",
    "STLAM.AS", "STMPA.AS", "STMPA.SW", "SWECO-B.ST", "SXS.L", "TEN.LU",
    "THL.PA", "TIGO.ST", "TJW.L", "TOM.AS", "TUI.DE", "UC.MI", "UPW.L",
    "VESTAS.CO", "WEND.PA",
]

# Curated rename/convention candidates (company knowledge; each still verified by
# resolution + longName below). Key = original failing symbol; value = list of
# candidates to try in order.
CANDIDATES: dict[str, list[str]] = {
    "BA..L": ["BA.L"],            # BAE Systems (Wikipedia 'BA.' + .L double-dot)
    "RR..L": ["RR.L"],           # Rolls-Royce
    "SN..L": ["SN.L"],           # Smith & Nephew
    "BT.A.L": ["BT-A.L"],        # BT Group (yfinance dash form)
    "SNY.PA": ["SAN.PA"],        # Sanofi (SNY is the US ADR)
    "ENGIE.PA": ["ENGI.PA"],     # Engie
    "ORAN.PA": ["ORA.PA"],       # Orange (ORAN is US ADR)
    "ESLX.PA": ["EL.PA"],        # EssilorLuxottica
    "SANO.HE": ["SANOMA.HE"],    # Sanoma
    "NDA-SE.HE": ["NDA-FI.HE", "NDA-SE.ST"],  # Nordea
    "VESTAS.CO": ["VWS.CO"],     # Vestas Wind Systems
    "PANDORA.CO": ["PNDORA.CO"], # Pandora A/S
    "ROG.SW": ["ROG.SW"],        # Roche (retest; likely transient)
    "NOV-N.SW": ["NOVN.SW"],     # Novartis
    "MT.LU": ["MT.AS"],          # ArcelorMittal (Amsterdam primary)
    "STLAM.AS": ["STLAM.MI", "STLA"],  # Stellantis
    "STMPA.AS": ["STMPA.PA", "STM.PA"],  # STMicroelectronics
    "STMPA.SW": ["STMPA.PA", "STM.PA"],
    "TEN.LU": ["TEN.MI"],        # Tenaris (Milan)
    "INPST.LU": ["INPST.AS"],    # InPost (Amsterdam)
    "TUI.DE": ["TUI1.DE", "TUI.L"],  # TUI moved primary listing to London
    "LIN.L": ["LIN"],            # Linde (US-listed)
    "HLM.L": ["HLMA.L"],         # Halma (HLM is wrong)
    "SWECO-B.ST": ["SWEC-B.ST"], # Sweco
}


def _try(sym: str) -> tuple[bool, str]:
    """Return (resolved, longName-or-reason). Resolved = yfinance gives a quote."""
    try:
        t = yf.Ticker(sym)
        info = t.get_info()
    except Exception as exc:  # noqa: BLE001 - diagnostic
        return False, f"<exc {type(exc).__name__}: {str(exc)[:60]}>"
    if not info:
        return False, "<empty info>"
    name = info.get("longName") or info.get("shortName") or ""
    price = (
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or info.get("regularMarketPreviousClose")
    )
    if name and price is not None:
        cur = info.get("currency", "?")
        return True, f"{name} ({price} {cur})"
    if name:
        return True, f"{name} (no price field)"
    return False, "<no name/price>"


def main() -> None:
    resolves: list[tuple[str, str]] = []
    broken: list[str] = []
    print(f"Probing {len(FAILED)} symbols against yfinance (local)...\n", flush=True)
    for sym in FAILED:
        ok, detail = _try(sym)
        status = "OK  " if ok else "FAIL"
        print(f"{status} {sym:14s} {detail}", flush=True)
        (resolves if ok else broken).append((sym, detail) if ok else sym)
        time.sleep(0.4)

    print("\n================ SUMMARY ================", flush=True)
    print(f"RESOLVES AS-IS ({len(resolves)}):", flush=True)
    for sym, detail in resolves:
        print(f"  {sym:14s} {detail}", flush=True)

    print(f"\nSTILL BROKEN ({len(broken)}) — trying candidates:", flush=True)
    fixed: list[tuple[str, str, str]] = []
    still: list[str] = []
    for sym in broken:
        cands = CANDIDATES.get(sym, [])
        # deterministic trailing-dot-before-suffix fix as an extra candidate
        if ".." in sym:
            cands = [sym.replace("..", ".")] + [c for c in cands if c != sym.replace("..", ".")]
        hit = None
        for cand in cands:
            ok, detail = _try(cand)
            if ok:
                hit = (cand, detail)
                break
            time.sleep(0.3)
        if hit:
            fixed.append((sym, hit[0], hit[1]))
            print(f"  {sym:14s} -> {hit[0]:14s} {hit[1]}", flush=True)
        else:
            still.append(sym)
            print(f"  {sym:14s} -> NO CANDIDATE RESOLVED (tried {cands})", flush=True)

    print("\n================ FINAL ================", flush=True)
    print(f"resolves-as-is: {len(resolves)}  fixed-by-candidate: {len(fixed)}  "
          f"unresolved: {len(still)}", flush=True)
    print(f"unresolved (delisted/drop candidates): {still}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
