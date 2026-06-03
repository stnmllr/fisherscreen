"""Emit the final classification of the 35 unresolved universe tickers as a
committed CSV. Encodes the verified results from confirm35.py + supplementary
probes + universe-coverage check. Uncertain cases are marked HONESTLY.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
u = set(json.loads((HERE.parent.parent.parent.parent / "data" / "universe.json").read_text("utf-8")))

# (universe_ticker, real_company, correct_ticker_or_None, category, note)
# category: WRONG_TICKER (real co, a live correct ticker exists) | DELISTED (M&A/
#           take-private/nationalised) | UNCLEAR (could not confirm a live alias)
ROWS = [
    ("ATCOa.ST", "Atlas Copco A", "ATCO-A.ST", "WRONG_TICKER", "lowercase class suffix; -A.ST resolves"),
    ("ERICb.ST", "Ericsson B", "ERIC-B.ST", "WRONG_TICKER", "lowercase class suffix"),
    ("ELUXb.ST", "Electrolux B", "ELUX-B.ST", "WRONG_TICKER", "ELUX-B.ST ALSO in universe -> benign dup"),
    ("SKFb.ST", "SKF B", "SKF-B.ST", "WRONG_TICKER", "SKF-B.ST ALSO in universe -> benign dup"),
    ("TEL2b.ST", "Tele2 B", "TEL2-B.ST", "WRONG_TICKER", "TEL2-B.ST ALSO in universe -> benign dup"),
    ("HMB.ST", "H&M B", "HM-B.ST", "WRONG_TICKER", "correct ticker MISSING -> silently excluded"),
    ("ASMI.AS", "ASM International", "ASM.AS", "WRONG_TICKER", "ticker renamed ASMI->ASM; MISSING"),
    ("DSM.SW", "DSM-Firmenich", "DSFIR.AS", "WRONG_TICKER", "merger/rename+exchange; MISSING"),
    ("FLTR.IR", "Flutter Entertainment", "FLTR.L", "WRONG_TICKER", "moved listing IR->L; MISSING"),
    ("ICP.L", "ICG plc (Intermediate Capital)", "ICG.L", "WRONG_TICKER", "wrong ticker; MISSING"),
    ("INDV.L", "Indivior", "INDV", "WRONG_TICKER", "moved primary listing L->US; MISSING"),
    ("BDEV.L", "Barratt Redrow", "BTRW.L", "WRONG_TICKER", "2024 merger renamed BDEV->BTRW; MISSING"),
    ("TEV", "Teva Pharmaceutical", "TEVA", "WRONG_TICKER", "wrong US ticker (TEV vs TEVA); MISSING"),
    ("EFGI.PA", "EFG International", "EFGN.SW", "WRONG_TICKER", "wrong exchange; financial (gm=0, drops anyway)"),
    ("INP.L", "Investec", "INVP.L", "WRONG_TICKER", "wrong ticker; financial (gm=0, drops anyway)"),
    ("LIN.L", "Linde plc", "LIN", "WRONG_TICKER", "LIN ALSO in universe -> benign dup"),
    ("NGG.L", "National Grid", "NG.L", "WRONG_TICKER", "NG.L ALSO in universe -> benign dup"),
    ("AMS.VI", "ams-OSRAM / Amadeus?", None, "UNCLEAR", "AMS.VI stale; AMS.MC=Amadeus is a DIFFERENT co"),
    ("MAN.DE", "MAN SE", None, "DELISTED", "taken private by VW/Traton ~2021"),
    ("MOR.DE", "MorphoSys", None, "DELISTED", "acquired by Novartis 2024"),
    ("MRW.L", "Wm Morrison", None, "DELISTED", "taken private (CD&R) 2021"),
    ("NEOEN.PA", "Neoen", None, "DELISTED", "taken private (Brookfield) 2024"),
    ("SMDS.L", "DS Smith", None, "DELISTED", "acquired by International Paper 2025"),
    ("SWMA.ST", "Swedish Match", None, "DELISTED", "taken private (Philip Morris) 2022"),
    ("DLG.L", "Direct Line", None, "DELISTED", "acquired by Aviva 2025"),
    ("UN01.DE", "Uniper", None, "DELISTED", "nationalised by German govt 2022/23; illiquid/delisted"),
    ("VAR1.DE", "Varta", None, "DELISTED", "2024/25 restructuring/delisting"),
    ("LUN.ST", "Lundin Energy", None, "DELISTED", "merged into Aker BP 2022 (LUMI.ST=Lundin Mining is a diff co)"),
    ("AKERBP.OL", "Aker BP", "AKRBP.OL", "WRONG_TICKER", "ticker AKERBP.OL stale; AKRBP.OL resolves"),
    ("SCHA.OL", "Schibsted A", None, "UNCLEAR", "degraded; Schibsted/Adevinta reorg — alias not confirmed"),
    ("ROL.L", "unidentified", None, "UNCLEAR", "no live alias found (RR.L=Rolls-Royce is a diff co)"),
    ("RIGN.SW", "unidentified", None, "UNCLEAR", "no live alias confirmed"),
    ("SANO.HE", "Sanofi/Sanoma?", None, "UNCLEAR", "SAN.PA=Sanofi already in universe; SAA1V.HE=Sanoma fails too"),
    ("SOW.DE", "Software AG", None, "DELISTED", "taken private by Silver Lake 2024"),
    ("TPG.L", "TP Group plc (likely)", None, "DELISTED", "likely taken private ~2023; TCAP.L=TP ICAP is a different co"),
]
ROWS = [r for r in ROWS if r[0] and r[1]]

# completeness guard: every actually-unresolved symbol MUST be classified
_res = json.loads((HERE / "re_resolution.json").read_text("utf-8"))
_unres = {t for t, r in _res.items() if not r["resolved"]}
_classified = {r[0] for r in ROWS}
_missing = _unres - _classified
_extra = _classified - _unres
if _missing:
    print("!! UNCLASSIFIED unresolved symbols (AUDIT GAP):", sorted(_missing))
if _extra:
    print("!! classified but not actually unresolved:", sorted(_extra))

out = []
for utick, company, correct, cat, note in ROWS:
    covered = (correct in u) if correct else False
    if cat == "DELISTED":
        materiality = "PRUNE (delisted/acquired)"
    elif cat == "UNCLEAR":
        materiality = "INVESTIGATE"
    elif covered:
        materiality = "BENIGN (correct ticker already in universe)"
    else:
        materiality = "SILENTLY EXCLUDED (real co, correct ticker absent)"
    out.append((utick, company, correct or "", "YES" if covered else "NO", cat, materiality, note))

out.sort(key=lambda r: (r[4], r[0]))
with (HERE / "unresolved35_classified.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["universe_ticker", "real_company", "correct_ticker",
                "correct_in_universe", "category", "materiality", "note"])
    w.writerows(out)

from collections import Counter
cats = Counter(r[4] for r in out)
mats = Counter(r[5] for r in out)
print("classified", len(out), "of 35")
print("categories:", dict(cats))
print("materiality:", dict(mats))
print("\nSILENTLY EXCLUDED real companies:")
for r in out:
    if r[5].startswith("SILENTLY"):
        print(f"  {r[0]:10} {r[1]:30} -> {r[2]}")
