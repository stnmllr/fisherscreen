# Punkt 1 — GATE B Acceptance (Cold-Dry-Run 2026-06-08)

> Bidirektional, survivor-ändernd. Verifiziert mit `scripts/diagnose_p1_gateB_acceptance.py`
> + `diagnose_newly_caught.py` über die Cold-Run-`dropouts.csv`/`funnel_summary.json`.
> Reconciliation-Anker = die GATE-A-Prognose (`calibration.md`), **nicht** „was rauskommt".

## Funnel 0b → Punkt 1 (survivor-ändernd, wie beabsichtigt)

| Stufe | 0b | Punkt 1 | Δ |
|---|---|---|---|
| resolution dropped | 8 | 8 | — (keine NO_PRICE-Diverts) |
| basis_gates entered | 1314 | 1314 | = resolution.remaining ✓ |
| basis_gates dropped | 618 | 608 | −10 |
| edgar dropped | 8 | 8 | — (keiner der 10 edgar-gedroppt) |
| **edgar-Survivor** | 688 | **698** | **+10 — exakt prognostiziert** |

Arithmetik: `1322 = 8 + 608 + 8 + 698` ✓. Lauf 200 OK → **Wert-Gate raised nirgends** (keine
Invarianten-Verletzung live). `going_concern_drops=0`, `data_source_error=0`, `unresolved=5`
(UNCLEAR-Set unverändert).

## Reconciliation gegen GATE-A-Prognose

- **Survivor +10:** die 10 prognostizierten (FLTR, GAW, GHC, LISN, LPP, MELE, SIX2, SLHN, VACN, VCT)
  sind **alle** present (nicht gedroppt). ✓
- **13 gerettet-aber-doomed** fallen **alle** am Folge-Gate (Punkt-2/3-Territorium, nicht vermischt): ✓
  gross_margin (BARN, COLR, DIA, DIE, MAERSK, MF, NVR, VIG), rev_growth (ANA, EMSN, GIVN, RCO, SCMN).
- **NO_PRICE-Diverts: keine** (RESOLUTION_NO_SYMBOL_DATA = 3× NO_RAW_MC, unverändert ggü. 0b).
- **GATE_VOLUME-Drops: 6** = die prognostizierten **4** {FER €0,43M, 1COV €0,89M (broken-avgVol →
  REVIEW), CTG, LANV (micro)} **+ 2 Funde** {BPOST.BR, ONTEX.BR}.

## Fund (kein Defekt): 2 von außerhalb neu eingefangen — bidirektionale Korrektheit

BPOST.BR (€1,70 × 214k = **€0,365M**, mc €0,34B) und ONTEX.BR (€2,50 × 265k = **€0,662M**, mc €0,20B)
**passierten den alten Stück-Floor** (>100k Stück) bei echtem <€1M-Wert → der Wert-Floor fängt sie
korrekt (niedrigpreisig/viel-Stück = genuin geringe Wert-Liquidität). Beide BENIGN-Small-Caps (<€2B)
→ wären ohnehin am market_cap-Gate gefallen → **null Survivor-Effekt** (deshalb +10 exakt). Das ist
die *andere* Richtung des ATO-Tests: der Floor rettet nicht nur (LISN), er fängt auch korrekt.

**Prognose-Scope-Nuance (ehrlich):** Die GATE-A-Prognose enumerierte das GATE_VOLUME-*Drop*-Set
(die 27) → wer von *außerhalb* neu eingefangen wird (Stück-Floor-Passer mit <€1M-Wert), war nicht
abgedeckt. Survivor-neutral und korrekt, aber für künftige Kalibrierungen: „wer neu eingefangen wird"
braucht die Wert-Verteilung über *alle* Stück-Floor-Passer, nicht nur die Survivor + das Drop-Set.

## Verdikt
**GATE B bestanden.** Survivor +10 bitgenau gegen Prognose; die 10 Namen present; die 13 doomed an
den korrekten Folge-Gates (Punkt 2/3); FER/1COV broken-avgVol sichtbar REVIEW; 2 saubere bidirektionale
Funde ohne Survivor-Effekt; Reconciliation hält; Wert-Gate raised nirgends. → frei für den
gebündelten Remote-PR {Funnel + 0a + 0b + Punkt 1}.
