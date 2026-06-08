# Wert-basiertes Volumen-Gate (Ticket Punkt 1) — Design

> Status: Spec, vor Implementierung. Branch `feature/gate-universe-fixes`.
> Datum: 2026-06-08. Folge zu 0a/0b. **Erster survivor-ändernder Fix** (Acceptance dreht sich um:
> „das Richtige hat sich geändert", nicht „nichts").

## Ziel

Das Volumen-Gate misst **Stückzahl** (`avg_daily_volume ≥ 100k`). Hochpreisige Titel handeln
wenige Stück bei riesigem Wert (LISN/Lindt: CHF95.600/Aktie, 175 Stück/Tag = ~€18M/Tag echt) und
sterben am Stück-Floor, obwohl sie liquide sind. Umstellen auf **Ø-Tages-Handelswert in EUR**:
`avg_daily_volume × price_eur ≥ Schwelle`. Der Stück-Floor impliziert je nach Preis absurd
unterschiedliche Wert-Floors — die Metrik ist falsch, nicht die Schwelle.

## Befund aus der Kalibrierungs-Probe (Cold-Cache 2026-06-08)

22 GATE_VOLUME-REVIEW Large-Caps + 5 BENIGN, Ø-Tageswert berechnet. Zwei Daten-Kontaminationen,
die ein naives `volume × price × fx` zerlegen:

1. **Pence-Falle (bestätigt):** Londoner `.L`-Aktien quotieren in **Pence** — yfinance `currency='GBp'`,
   `price` in Pence (GAW.L price=18980 = £189,80), aber `marketCap` in **GBP** (6,27 Mrd). `volume ×
   price(pence) × fx(GBP→EUR)` ist **100× zu hoch** (GAW €2,05bn statt real ~€18M). Betrifft jede
   GBp-Aktie (FLTR.L, AZN.L …). 100× ist kein Rundungsfehler — ohne Fix wäre das Wert-Gate für jede
   London-Aktie kaputt.
2. **Kaputt/implausibles `averageVolume`:** FER.AS (€42 Mrd, avgVol=7309 → €0,43M/Tag), 1COV.DE
   (€11 Mrd, avgVol=14902 → €0,89M/Tag) — implausibel niedrig für diese Firmen. EUR-Listings → der
   Pence-Fix ändert sie nicht. Der Wert-Floor **erbt** `averageVolume` und kann kaputte Daten nicht
   heilen.

Verteilung: Universum p10=€25M, p50=€159M, p90=€1,7bn — die **Survivors sind alle massiv liquide**;
ein Floor von ~€1M bindet keinen echten Survivor, er trennt nur micro/kaputt von handelbar.

## Lösung

### (A) Pence-/Minor-Unit-Normalisierung bei der Konstruktion
In `ScreenerRecord.from_yfinance_info`: Minor-Unit ist eine **Eigenschaft der Daten**, nicht der
Berechnung → an der Grenze normalisieren, nicht beim Konsumenten. Kleine Map:

```python
_MINOR_UNIT = {"GBp": ("GBP", 100)}   # GBp→GBP ÷100; ZAc/ILA = dieselbe Klasse, dokumentiert nicht spekulativ gebaut
```
Wenn `currency` in `_MINOR_UNIT`: `currency = iso`, `price = price / divisor` (vor der `or None`-
Normalisierung). Effekt: `price` ist überall konsistent in Major-Unit; FX-Lookup trifft einen echten
ISO-Code (`GBP`) statt des Pseudo-Codes. **`price = … or None`** (0→None, spiegelt mc/vol).
- **Verifikation:** `market_cap_eur` bleibt unverändert korrekt — `marketCap` war immer in GBP,
  `currency='GBP'` trifft denselben FX-Rate (`get_fx_rate('GBp')` lieferte ohnehin ~die GBP-Rate;
  `market_cap_eur` für GBp-Aktien war schon korrekt, bleibt es).
- **Konsumenten-Audit (Pflicht, Schritt-0):** alle Leser von `price`/`currency` prüfen, ob jemand
  schon GBp behandelt (sonst ÷100 doppelt). Fast sicher keiner (der Bug existiert, weil niemand GBp
  behandelt) — aber dieselbe „Vertrag ändern → ferne Leser prüfen"-Regel wie 0b's `resolved`.

### (B) fx_rate als Primitiv am Record (carry, nicht re-derive)
`_resolve_market_cap_eur` fetcht den fx_rate bereits und wirft ihn weg. Den **fx_rate** am Record
tragen (`fx_rate: float | None = None`), nicht ein abgeleitetes `price_eur` — ein autoritativer
Input statt paralleler `_eur`-Felder; jede künftige EUR-Metrik keyt darauf. Garantiert da auf jedem
gate-baren Record (OK heißt FX war verfügbar). `price_eur = price × fx_rate` fällt trivial raus.
Das Wert-Gate rechnet `avg_daily_value_eur = avg_daily_volume × price × fx_rate`.

### (C) NO_PRICE-Divert (Geschwister-Bedingung an 0b)
Sobald `price` load-bearing wird (jetzt, durch Punkt 1), ist ein Record mit mc+vol da, aber `price`
fehlend/0, dieselbe Klasse, die 0b killt (value = vol × None → still am Gate maskiert). Punkt 1
führt die price-Abhängigkeit ein → Punkt 1 liefert den Guard im selben Change. 0b's Resolution-Divert
um `price` erweitern: in der Divert-Kette nach `NO_VOLUME`, vor `NO_FX`:
```python
elif record.price is None:            # 0->None schon bei Konstruktion -> fängt price=0 mit
    record.resolution_detail = "NO_PRICE"
    no_symbol_data.append(record)
```
→ `RESOLUTION_NO_SYMBOL_DATA`, detail `NO_PRICE`, REVIEW. Kein 0c. **Detail-Präzedenz
deterministisch + getestet:** `NO_RAW_MC → NO_CURRENCY → NO_VOLUME → NO_PRICE` (price zuletzt, da
separater `elif`). **Notiz:** Das verhindert eine *künftige* Maskierung, keine aktuelle (der jetzige
Stück-Floor nutzt price nicht). Tauchen am Cold-Run NO_PRICE-Diverts auf, ist das ein **Fund**, kein
Defekt (Divert-Menge darf über 3 wachsen).

### (D) Wert-Gate
`passes_volume_filter` rechnet `avg_daily_value_eur = avg_daily_volume × price × fx_rate ≥
MIN_AVG_DAILY_VALUE_EUR`. reason_code bleibt `GATE_VOLUME` (es ist weiter der Liquiditäts-Gate),
Gate-Reihenfolge unverändert (zuerst). Records am Gate haben vol+price (sonst divertiert) und fx_rate
(OK) → Wert berechenbar.

**Schwelle = fail-loud Sentinel in der Bauphase:** `MIN_AVG_DAILY_VALUE_EUR: float | None = None`.
Das Gate **raised** „threshold not calibrated", wenn es mit dem Sentinel in einem echten Lauf
aufgerufen wird → eine unkalibrierte Zahl zu shippen ist **unmöglich** (genau die „Rateversuch
maskiert sich als kalibriert"-Falle dieses Tickets). **Kein** plausibler Platzhalter (nicht
`1_000_000`). Tests injizieren Fixture-Schwellen → TDD ist nicht blockiert. Das Kalibrierungs-Gate
ersetzt den Sentinel durch die abgenommene Zahl.

**Defensiver Guard RAISED, droppt NICHT still:** Ein Record am Wert-Gate ohne berechenbaren Wert
(vol/price/fx_rate fehlt) ist **keine** Liquiditäts-Verfehlung, sondern eine **Invarianten-Verletzung**
(0b+NO_PRICE garantieren alle drei → der Guard kann legitim nie feuern). → laut `raise`, **niemals**
stiller BENIGN-Drop (das wäre exakt die Maskierungs-Hintertür, die 0a/0b geschlossen haben). Feuert
er doch, ist es ein Bug, der schreien soll.

### (E) Severity folgt der Metrik — verifizieren
`_severity(GATE_VOLUME)` keyt auf `market_cap_eur` (≥ LARGE_CAP_VOLUME_EUR → REVIEW), **unabhängig**
von der Gate-Metrik. → FER/1COV (mc €42/11 Mrd) bleiben bei Wert-Floor-Fail automatisch REVIEW. Das
ist die Sichtbarkeit, die Decision (B-broken) rechtfertigt → **als Test gesichert**, nicht angenommen.

## Schwelle — eigenes Kalibrierungs-Gate (NICHT auf hand-korrigierten Zahlen)

Die Schwelle wird **nach** dem Pence-Fix gesetzt, auf dem, was der Code dann produziert (GAW/FLTR/CTG
sauber), nicht auf meiner Vorab-Rechnung (Probe ist der Schiedsrichter, GATE-2-Lehre).

- **Anker:** Liquiditäts-Ökonomie — minimaler Ø-EUR-Tagesumsatz, um eine sinnvolle Position
  (~€10–50k über wenige Tage bei <10% Tagesumsatz) ein-/auszusteigen. Die Verteilung **validiert**
  (natürliche Lücke), **leitet nicht ab**. **Nicht** auf „genau die 22 durchlassen" back-solven.
- **Untere Schranke (Junktim zu B-broken):** Floor **≥ ~€0,9M**, damit FER/1COV (€0,43/0,89M,
  pence-fix-invariant) **über** dem Floor-Fail liegen und korrekt REVIEW werden. Ein zu niedriger
  Floor ließe ihre Brokenness unsichtbar.
- **Region ~€1M:** schließt nur echtes Micro aus (LANV €0,095M), bindet keinen Survivor (p10=€25M,
  25× drüber). €1M vs €2M = nur „DIA.MC rein/raus" (distressed Retailer, stirbt ohnehin am
  gross_margin) → nicht zerdenken; an der **unteren Kante der natürlichen Lücke** ansetzen, auf
  sauberen Zahlen abgelesen. Die Konstante (Sentinel→Zahl) = Gate-Artefakt, von Stephan abgenommen
  (wie die 0a-Tabelle).
- **Gerettetes Set EXAKT am Gate nachzählen (nicht annehmen):** Das survivor-ändernde Delta umfasst
  **auch die fälschlich-BENIGN-Gedroppten** (VCT/RCO/DIA), nicht nur die 22 REVIEW. Von den 5
  GATE_VOLUME-BENIGN sind LANV und CTG.L per market_cap echte Micro-Caps (CTG.L's €1,34M ist zudem
  pence-inflationiert → real Micro) → bleiben draußen. ⇒ **3 gerettet (VCT/RCO/DIA), DIA
  schwellenwert-grenzwertig** (drin bei €1M, raus bei €2M) — **nicht** „4 von 5". Die Rescued-/
  Stay-out-Mitgliedschaft wird am Kalibrierungs-Gate auf **sauberen (pence-gefixten) Zahlen exakt
  enumeriert** (REVIEW/BENIGN/broken sauber getrennt), und die Survivor-Split-Prognose daraus gebaut —
  sonst reconciled das Survivor-Delta nicht gegen die Prognose.

## Broken-avgVol — nur REVIEW-flaggen (Decision 2)

FER/1COV: der Wert-Floor erbt avgVol, rettet sie nicht — aber flaggt sie als GATE_VOLUME REVIEW
(large-cap unter Floor) → sichtbar für menschliche Prüfung. **Keine** Plausibilitäts-Heuristik in
Punkt 1 (cap-impliziertes Volumen-Modell streut pro Titel massiv → Fehlalarme + Scope-Creep in eine
andere Daten-Klasse: Plausibilität ≠ Fehlend). Sichtbar-machen genügt; nicht auto-klassifizieren.

## Tests (Pflicht)

- **Pence:** GBp → currency=GBP + price÷100; GBP unverändert; nicht-gelistete Minor-Unit unberührt;
  `market_cap_eur` für eine GBp-Aktie unverändert (Regressions-Wächter).
- **price=0 → None → NO_PRICE-Divert**; price=None → NO_PRICE; **Anti-Over-Fire:** realer price →
  gated, nicht divertiert. Reconciliation mit ggf. größerer Divert-Menge.
- **fx_rate** am Record gesetzt (OK-Record) / None bei Divert.
- **Wert-Gate:** value≥Schwelle → pass; value<Schwelle → GATE_VOLUME fail; LISN-Klasse (hoher Wert,
  wenige Stück) → pass; genuin micro (LANV-Klasse) → fail. **Anti-Over-Fire** beidseitig.
- **Severity-folgt-Metrik:** large-cap (mc≥3B) mit Wert-Floor-Fail → GATE_VOLUME **REVIEW**.

## Acceptance (Cold-Run) — bidirektional, survivor-ändernd

- **Survivor steigt** (688 → 688+M); die 22 verlassen GATE_VOLUME-REVIEW — **aber nicht alle 22
  überleben**: wer den Wert-Gate passiert, trifft danach gross_margin/rev_growth; Financials/
  Niedrigmargige (VIG.VI, SLHN.SW, MF.PA …) fallen dort **legitim = Punkt-2/3-Input, nicht
  vermischt**. Acceptance = korrekte Volumen-Transition + Survivor-Anstieg = die Teilmenge, die auch
  die Folge-Gates passiert. **Split aus dem sauberen Re-Run vorhersagen**, keine review_flags-Zielzahl.
- **Bidirektional (kein Müll schlüpft):** nur micro (LANV-Klasse) + Broken-avgVol bleiben unter dem
  Floor; FER/1COV korrekt GATE_VOLUME **REVIEW** (sichtbar, nicht maskiert).
- **NO_PRICE-Diverts** (falls am Cold-Run auftauchend) = Fund, kein Defekt.
- Reconciliation hält; Severity-folgt-Metrik am Lauf bestätigt.

## Disziplin / Scope

Strikt das Volumen-Gate. Folge-Gate-Fates (gross_margin/rev_growth) = **Punkt 2/3**, nicht mischen.
Eigener TDD + Kalibrierungs-Gate + Cold-Run-Acceptance. Kein Push/Merge ohne Stephans Go.
