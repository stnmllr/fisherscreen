# Punkt 1 — Wert-Floor-Kalibrierung (GATE A, abgenommen 2026-06-08)

> Schwelle auf sauberen (pence-gefixten) Zahlen gesetzt, von Stephan abgenommen.
> Probe ist Schiedsrichter (`scripts/diagnose_value_floor_calibration.py`,
> `diagnose_survivor_value_histogram.py`, `diagnose_p1_survivor_split.py`,
> `diagnose_canary_fx.py`). **Nie auf hand-korrigierten Zahlen kalibriert.**

## ABGENOMMENE SCHWELLE: `MIN_AVG_DAILY_VALUE_EUR = 1_000_000.0` (€1M/Tag)

## Begründung — strukturell, nicht 30-Namen-optimiert

**Histogramm über alle 688 EDGAR-Survivors** (= Universum minus Dropouts):
- `min=€2,45M · p1=€9,2M · p5=€20,8M · p10=€32M · p25=€73,8M · p50=€169,6M`
- **Null** Survivors unter €2M; nur 3 unter €5M (LSG.OL 2,45 · WIHL.ST 3,72 · SWEC-B.ST 4,64).

**Das leere Band ist der Anker, nicht die Zahl.** Broken/Micro enden bei €0,89M (1COV),
Survivors beginnen bei €2,45M (LSG.OL) — eine **2,75×-Lücke ohne einen einzigen Titel dazwischen**.
In Finanzdaten ist das eine echte Liquiditäts-Schichtgrenze (unter €1M: nur Broken-Tickers,
Micro-Caps, delistete Reste; ab ~€2M: unteres Ende handelbarer Mid-Caps). €1M sitzt am unteren
Rand dieses leeren Bands, **2,45× unter dem nächsten Survivor**.

**Drift-robust, weil absolut:** €1M ist ein Liquiditäts-Ökonomie-Floor (Minimum, um eine
~€10–50k-Position über wenige Tage bei <10% Beteiligung handelbar auf-/abzubauen), kein relativer
Inter-Cluster-Punkt. Damit er je *bindet*, müsste ein €2-Mrd-Quality-Titel auf <€1M/Tag fallen =
genuin unhandelbar → korrekte Exklusion. Universen-Drift/Marktphase verschiebt das nicht.

**Bidirektional sauber:** droppt **null** aktuelle Survivors (alle ≥€2,45M); FER (€0,43M) +
1COV (€0,89M) bleiben drunter → korrekt GATE_VOLUME REVIEW (Broken-avgVol sichtbar).

**€1M vs €2M survivor-irrelevant** (beide im leeren Band). €1M gewählt = kanonische
Mindest-Handelbarkeit, unterer Rand des Bands.

## FX-Pfad verifiziert (nicht-EUR/USD)
Die 3 Kanarienvögel sind NOK/SEK. `get_fx_rate` liefert **EUR-pro-Einheit** korrekt:
NOK=0,0915 · SEK=0,0914 (nicht invertiert ~11). Werte matchen das Histogramm bitgenau.

## Survivor-Split-Prognose @ €1M (Reconciliation-Anker für GATE B)
- **SURVIVORS (M = +10):** FLTR, GAW, GHC, LISN, LPP, MELE, SIX2, SLHN, VACN, VCT (BENIGN).
  → edgar-Survivor 688 → **~698** (minus etwaiger EDGAR-Drops auf die 10; Large-Caps selten geflaggt).
- **Gerettet, fällt an Folge-Gate (Punkt 2/3, nicht vermischt) = 13:** gross_margin (BARN, COLR,
  DIA, DIE, MAERSK, MF, NVR, VIG), rev_growth (ANA, EMSN, GIVN, RCO, SCMN).
- **Bleibt draußen = 4:** FER €0,43M + 1COV €0,89M (broken → REVIEW), CTG €0,01M + LANV €0,09M (micro).
- **GATE_VOLUME-Drops:** 27 → **4** (FER, 1COV, CTG, LANV).

## Reversibilitäts-Trigger (für Future-Stef — nicht wegrationalisieren)
1. **Anker = die Lücke, nicht €1M.** Re-Evaluieren, wenn `min(Survivors) < 2× max(Broken/Micro)`
   (heute: 2,45M vs 2×0,89M=1,78M → komfortabel). Schrumpft das Band, neu entscheiden.
2. **Kanarienvögel namentlich tracken:** LSG.OL · WIHL.ST · SWEC-B.ST. Fällt einer raus ohne
   Ersatz, ist das Verteilungsdrift-Signal — **nicht** Floor-Anpassung. (Fällt LSG.OL weg, beginnt
   die Survivor-Verteilung bei €3,72M → Marge 3,72× → Floor bleibt robust.)
3. **Pence/Minor-Unit-FX bei Universen-Erweiterung:** neue Märkte mit Minor-Unit-Quotes (ZAc, ILA…)
   oder exotische Währungen → FX-Richtung gegen den Anker verifizieren (wie hier NOK/SEK), bevor
   Survivor-nahe Werte vertraut werden.
