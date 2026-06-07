# 0a GATE-2 Acceptance — Befund (Cold-Dry-Run 2026-06-07)

> Verifiziert mit `scripts/diagnose_0a_acceptance.py` (offline Landing aus dropouts.csv +
> Live-Klassifikation). Reconciliation: `1322 = 5 + 621 + 8 + 688` ✓.

## Survivor-Delta M=1 — vollständig erklärt, kein versteckter Defekt

Twin-Kollaps (8) + Drops (2) sind survivor-neutral → gesamtes Survivor-Delta = Rehab-Adds,
die die Gates passieren = M. Beobachtet: **M = 1 = ENX.PA (Euronext)**.

**Landing der 12 Rehab-Adds (echte Daten, kein Fund-Müll mehr):**

| Symbol | Firma | Landing | Scope |
|---|---|---|---|
| ENX.PA | Euronext | **SURVIVED** (688) | ✓ rehabilitiert |
| BNP.PA | BNP Paribas | gross_margin BENIGN | Punkt 2 (Bank) |
| ACA.PA | Crédit Agricole | gross_margin BENIGN | Punkt 2 (Bank) |
| CAP.PA | Capgemini | gross_margin BENIGN | Punkt 2 |
| CA.PA | Carrefour | gross_margin BENIGN | Punkt 2 (Retail, legitim) |
| EVD.DE | CTS Eventim | gross_margin BENIGN | Punkt 2 |
| RNO.PA | Renault | gross_margin BENIGN | Punkt 2 (Auto, legitim) |
| AI.PA | Air Liquide | rev_growth REVIEW | Punkt 3 |
| BN.PA | Danone | rev_growth REVIEW | Punkt 3 |
| RI.PA | Pernod Ricard | rev_growth REVIEW | Punkt 3 |
| ATO.PA | Atos | market_cap BENIGN | korrekt (real <2 Mrd) |
| ML.PA | Michelin | market_cap BENIGN | **yfinance `marketCap=0`-Quirk** (real Vol vorhanden) → fälschlich raus, drückt M; 0b/Daten-Qualität |

**Schlüssel-Befunde:**
- **Null Rehab-Adds starben am `GATE_VOLUME`** → die Volumen-Stück-Floor drückt M **nicht**; Punkt-1
  ist hier nicht die Ursache. M=1 ist erklärt durch gross_margin (Punkt 2) + rev_growth (Punkt 3)
  + ML-Datenquirk, nicht durch einen Bug.
- **Korrektur meiner Prognose-Sprache:** Banken (BNP/ACA) **fallen** am gross_margin-Gate (der Gate
  läuft im aktuellen Design auf alle Sektoren; die Sektor-Ausnahme betrifft nur die REVIEW-Schwere,
  nicht den Drop). Das ist die konkrete Motivation für **Punkt 2**, kein 0a-Defekt.
- 0a validiert: reale Firmen werden jetzt korrekt gescreent; M steigt mit Punkt 2/3.

## RNL.PA / GLB.IR — 0b-Fälle, KEIN 0a-Leck

Live-klassifiziert:
- `RNL.PA` → quoteType=EQUITY, name „RENAULTPFRN24OCT49" = **Renault-Nachranganleihe/Note** (nicht
  die Aktie RNO.PA), kein market_cap/Volumen.
- `GLB.IR` → quoteType=EQUITY, name „Beacon Hill CBO III Ltd" = **CBO-Verbriefungs-SPV**, kein
  operatives Equity.

Beide quoteType=EQUITY → außerhalb von 0a's MUTUALFUND-Klasse (quoteType≠EQUITY). Die
0a-Enumeration „22 MUTUALFUND-Kontaminanten, INCONCLUSIVE=0" bleibt **vollständig korrekt**.
RNL/GLB sind **echte 0b-Fälle** (EQUITY-förmige Leer-Dicts) — Resolution muss partielle/leere Dicts
als REVIEW klassifizieren (genau 0b). ML.PA (`marketCap=0` trotz Volumen) gehört in dieselbe Klasse.

## Offen / Notiz
- `funnel_summary.json` hat `provenance: null` — der Sidecar `data/universe_provenance.json`
  existiert noch nicht (universe.json wurde hand-ediert, nie frisch gebaut). Korrekt befüllt wird er
  erst beim **Gate-C-Live-Build** (`build_universe`, der jetzt durch die 0a-Map die RICs selbst
  korrigiert). Bis dahin ist `null` ehrlich (kein Fake-Sidecar).

## Verdikt
**GATE 2 bestanden.** 0a-Ziel erfüllt (22 Kontaminanten eliminiert, Reconciliation hält, reale
Firmen rehabilitiert und fundamentaldaten-korrekt verortet). M=1 erklärt und unbedenklich. RNL/GLB
sauber als 0b abgegrenzt. → frei für Punkt 0b.
