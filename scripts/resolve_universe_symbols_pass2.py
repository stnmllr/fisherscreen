#!/usr/bin/env python3
"""Read-only diagnostic (SUB-PHASE 1, pass 2): expanded candidate resolution for
the 56 symbols pass 1 could not fix. Each candidate is verified by yfinance
resolution + longName so a correction can be trusted by name.

NOT production code. Run: uv run python scripts/resolve_universe_symbols_pass2.py
"""
from __future__ import annotations

import sys
import time

import yfinance as yf

# 56 still-unresolved after pass 1. Value = ordered candidate list (best guess
# from company knowledge / exchange conventions). Empty list = no good guess yet
# (likely delisted/acquired -> drop candidate).
CANDIDATES: dict[str, list[str]] = {
    "ADH.OL": ["ADE.OL", "ADEA.OL"],                 # ?
    "AHT.L": ["AHT.L", "ASHTY"],                       # Ashtead -> moving US listing
    "ALLFG.MC": ["ALLFG.AS"],                          # Allfunds (Amsterdam)
    "ARGX.AS": ["ARGX.BR", "ARGX"],                    # argenx (Brussels / Nasdaq)
    "ARND.DE": ["AT1.DE"],                             # Aroundtown?
    "BALN.SW": ["BALN.SW", "BALOISE.SW"],              # Baloise
    "BEB.SW": ["BION.SW", "BBN.SW"],                   # ?
    "BRNW.MI": ["BC.MI"],                              # Brunello Cucinelli?
    "CASP.ST": ["CAST.ST"],                            # ?
    "CCH.SW": ["CCH.L"],                               # Coca-Cola HBC (London)
    "DASH.DE": ["DHER.DE"],                            # Delivery Hero?
    "EFGI.PA": ["EFGI.SW", "EFGN.SW"],                 # EFG?
    "EVR.L": [],                                        # Evraz - sanctioned/suspended -> drop
    "FALK.CO": [],                                      # ?
    "FERR.MI": ["RACE.MI", "FBK.MI"],                  # Ferrari/Ferrari? FinecoBank?
    "FOR.MC": ["FDR.MC", "LOG.MC"],                    # ?
    "GFT.IR": ["GL9.IR", "GVR.IR"],                    # ?
    "GREG.L": ["GRG.L"],                               # Greggs
    "GRLS.MC": ["GRF.MC"],                             # Grifols
    "GWI.MI": ["GWT.MI"],                              # ?
    "HELN.SW": ["HELN.SW", "HELV.SW"],                 # Helvetia
    "HLI.L": ["HLN.L"],                                # Haleon?
    "HNR.DE": ["HNR1.DE"],                             # Hannover Re
    "IDP.MI": ["IP.MI", "INW.MI"],                     # Interpump? Inwit?
    "IGGI.L": ["IGG.L"],                               # IG Group
    "INP.L": ["INPP.L"],                               # International Public Partnerships?
    "IPX.PA": ["IPN.PA"],                              # Ipsen (already IPN.PA in universe -> dup)
    "JUST.AS": [],                                      # Just Eat Takeaway - acquired by Prosus -> drop
    "LANV.PA": ["LANV"],                               # Lanvin (NYSE)?
    "LIF.IR": ["GL9.IR"],                              # ?
    "LUMI.PA": ["COFA.PA"],                            # ?
    "MGG.L": ["MGGT.L"],                               # Meggitt (acquired 2022) -> likely drop
    "NAB.AT": ["NABLTD"],                              # ?
    "NSN.HE": ["NESTE.HE"],                            # ?
    "ONT.BR": ["ONTEX.BR"],                            # Ontex
    "PHNX.L": ["PHNX.L"],                              # Phoenix Group (retest)
    "PLPH.SW": ["PEHN.SW", "PLPH.SW"],                 # ?
    "PSN.PA": ["PSN.L"],                               # Persimmon (London not Paris)
    "QIA.AS": ["QIA.DE", "QGEN"],                      # Qiagen (Frankfurt / Nasdaq)
    "ROG.SW": ["RO.SW", "ROG.SW"],                     # Roche
    "S4.L": ["SFOR.L"],                                # S4 Capital
    "SEB.ST": ["SEB-A.ST", "SEB-C.ST"],                # SEB bank
    "SIG.SW": ["SIGN.SW"],                             # SIG Group
    "SKG.IR": ["SW18.IR", "SWR"],                      # Smurfit Kappa -> Smurfit WestRock
    "SON.SW": ["SOON.SW"],                             # Sonova
    "SRB.OL": ["SRBNK.OL"],                            # SpareBank?
    "SRENH.SW": ["SREN.SW"],                           # Swiss Re
    "STER.HE": ["STERV.HE"],                           # Stora Enso?
    "SXS.L": ["SXS.L"],                                # Spectris (being acquired) retest
    "THL.PA": ["HO.PA"],                               # Thales?
    "TIGO.ST": ["TIGO-SDB.ST"],                        # Millicom
    "TJW.L": ["TW.L"],                                 # Taylor Wimpey?
    "TOM.AS": ["TOM2.AS"],                             # TomTom
    "UC.MI": ["UCG.MI"],                               # UniCredit (already UCG.MI -> dup)
    "UPW.L": ["UU.L"],                                 # United Utilities?
    "WEND.PA": ["MF.PA"],                              # Wendel
}


def _try(sym: str) -> tuple[bool, str]:
    try:
        info = yf.Ticker(sym).get_info()
    except Exception as exc:  # noqa: BLE001
        return False, f"<exc {type(exc).__name__}>"
    if not info:
        return False, "<empty>"
    name = info.get("longName") or info.get("shortName") or ""
    price = (
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or info.get("regularMarketPreviousClose")
    )
    if name and price is not None:
        return True, f"{name} ({price} {info.get('currency','?')})"
    return False, "<no name/price>"


def main() -> None:
    fixed: list[tuple[str, str, str]] = []
    drop: list[str] = []
    for sym, cands in CANDIDATES.items():
        hit = None
        for cand in cands:
            ok, detail = _try(cand)
            if ok:
                hit = (cand, detail)
                break
            time.sleep(0.3)
        if hit:
            fixed.append((sym, hit[0], hit[1]))
            print(f"FIXED {sym:12s} -> {hit[0]:14s} {hit[1]}", flush=True)
        else:
            drop.append(sym)
            print(f"DROP? {sym:12s} (tried {cands})", flush=True)

    print("\n===== PASS-2 SUMMARY =====", flush=True)
    print(f"fixed-by-candidate: {len(fixed)}   still-unresolved: {len(drop)}", flush=True)
    print(f"still-unresolved: {drop}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
