# growth: Stetigkeits-Untergrenze (steady-growth floor)

Stand 2026-10-08 · Entscheidung Stephan · wirkt ab dem nächsten Monatslauf

## Problem

growth = Perzentil des Median-Jahreswachstums über die Kohorte (seit PR #75). Die
Kohorte ist durch die Basis-Gates vorselektiert, P70 (Score 4) liegt im Lauf 2026-10
bei **+9,4 %**. Ein Unternehmen, das Jahr für Jahr ohne Rückschlag 7–9 % wächst,
bekommt growth = 3 und ist kein Crosshit — bestraft wird knappes Verfehlen eines
relativen Bandes, nicht fehlende Qualität.

Vorab-Diagnose (`scripts/diagnose_growth_reference.py`, Lauf 2026-10): 39 der 52 am
Crosshit-Gate gescheiterten Referenztitel liegen auf growth unter 4; 9 scheitern
**nur** an growth. Von den 47 Titeln der Kohorte, die nur an growth scheitern,
fallen viele ruhige Compounder (CTAS, VRSK, ITX.MC, ASM.AS, FAST, PAYX …).

## Entscheidung

Stetiges Wachstum ist für Fisher (P1) das eigentliche Signal — es spricht für ein
gutes Unternehmen und für Resilienz. Fisher wäre bei der Höhe nicht dogmatisch.

**Regel:** Ist der Median-Jahreswachstumsmedian **≥ 5 %** und das Fenster **ohne
Minusjahr** (`growth_consistency == 1.0`), ist growth **mindestens 4**. Sonst gilt
unverändert das Perzentil samt Konsistenz-Cap.

- Absolut, nicht relativ: eine relative Schwelle verschluckt das Urteil „wächst
  stetig genug“ (gleiches Muster wie Tier-B-Punkt-2).
- Nur Untergrenze (`max`), hebt nie über das Perzentil hinaus, senkt nichts.
- Greift nur auf dem Median-Pfad (≥ 4 GJ). Der Quartals-Fallback bleibt bei 3
  gedeckelt — dort gibt es keine messbare Stetigkeit.
- Konstanten fest im Code (`STEADY_GROWTH_MIN_MEDIAN = 0.05`,
  `STEADY_GROWTH_FLOOR = 4`), nicht konfigurierbar.
- Evidenz-Text nennt die Untergrenze, wenn sie den Score anhebt
  (z. B. `— steady-growth floor 4`), damit der Report zeigt, woher die 4 kommt.

Verworfen: P60 bzw. Median ≥ 7 % (holt die knappen, ignoriert Stetigkeit);
stetig & ≥ 3,5 % (holt YETI, VRSN, GWW — zu lauwarm).

## Erwartete Wirkung (Näherung, Lauf 2026-10)

46 → ~63 Crosshits (ANTO.L fällt als Preisnehmer wieder heraus), Referenz
14 → 20/74 (+ASM.AS, CTAS, FAST, ITX.MC, RAA.DE, VRSK). SAP.DE bleibt draußen
(scheitert zusätzlich an profitability). Exakte Zahl vor dem Merge per
`scripts/simulate_month_scoring.py`.

## Bekannte Grenze

„Stetig“ beruht auf nur 3 Jahresschritten (yfinance, ~4 GJ). Das längere
EDGAR-Fenster (US) ist ein eigener Folgeschritt mit eigenem Spec; die
US/EU-Asymmetrie wird dann je Titel im Report sichtbar markiert.
