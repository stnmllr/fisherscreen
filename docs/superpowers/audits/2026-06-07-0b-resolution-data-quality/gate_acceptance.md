# 0b GATE Acceptance — Befund (Cold-Dry-Run 2026-06-08)

> Verifiziert mit `scripts/diagnose_0b_acceptance.py` über die Dry-Run-`dropouts.csv`.
> Acceptance = Menge + Postcondition (keine Zahl).

## Funnel vorher/nachher (0a-GATE-2 → 0b), survivor-neutral

| Stufe | 0a-GATE-2 | 0b | Δ |
|---|---|---|---|
| universe | 1322 | 1322 | — |
| resolution dropped | 5 | **8** | +3 Diverts |
| resolution remaining | 1317 | 1314 | −3 |
| basis_gates entered | 1317 | **1314** | = resolution.remaining (Guardrail 1) |
| basis_gates dropped | 621 | **618** | −3 (leaken nicht mehr) |
| **edgar remaining (Survivor)** | 688 | **688** | **0 — survivor-neutral** |
| review_flags | 113 | **116** | +3 |

Reconciliation: `1322 = 8 + 618 + 8 + 688` ✓.

## Acceptance-Kriterien

- **Mengen-Prognose ⊇ {ML.PA, RNL.PA, GLB.IR}:** ✓ — exakt diese 3, alle `RESOLUTION_NO_SYMBOL_DATA`,
  detail=`NO_RAW_MC` (ML.PA marketCap=0→None; RNL.PA/GLB.IR marketCap None), alle REVIEW. **Genau 3**
  (nicht >3) → in diesem Lauf keine *zusätzliche* bisher unsichtbare Maskierung; die 3 bekannten
  sind jetzt sichtbar statt still BENIGN.
- **Postcondition:** **0** `basis_gates`-Drops mit leerem `market_cap_eur` verbleibend → kein
  stiller BENIGN-Pfad mehr für fehlende Symboldaten.
- **RESOLUTION_FX_UNAVAILABLE = 0:** sauberer Lauf; der eigene Code steht als FX-Fix-Trigger bereit
  (Nicht-Null hätte hunderte Nicht-EUR-Symbole sichtbar gemacht statt still maskiert).
- **Alle Diverts REVIEW**, mc=None-sicher (kein Crash über is_large_cap/Tripwire).
- **Survivor 688 unverändert** ggü. 0a-GATE-2 — Divertierte waren immer Nicht-Survivor.

## Verdikt
**GATE 0b bestanden.** Der Masking-Bug ist generalisiert geschlossen: jedes Symbol mit
fehlendem/Null market_cap, fehlender currency oder fehlendem/Null Volumen landet jetzt als
Resolution-REVIEW (eigene Codes), nicht still BENIGN am Gate. Kein 0c/0d nötig. → frei für Punkt 1.

## Offen (wie 0a)
- `provenance: null` — Sidecar entsteht erst beim Gate-C-Live-Build (nicht gefaked).
