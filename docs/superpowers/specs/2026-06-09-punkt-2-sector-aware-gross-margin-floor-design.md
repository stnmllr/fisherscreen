# Punkt 2 — Sektor-bewusster gross_margin-Floor — Design

> Status: Design (zur Abnahme). Datum: 2026-06-09.
> Branch: `feature/sector-aware-gross-margin-floor`.
> Tier-B-Zyklus, Punkt 2 von {2, 3}. Punkt 3 (revenue_growth) folgt als **eigener** Zyklus
> NACH Punkt 2 — Universe-Ordering: Punkt 2 formt das Universum um (Financials/REITs raus aus
> dem Metrik-Artefakt, Niedrigmargen-Sektoren rein), Punkt 3 kalibriert dann auf dem
> sauberen, überlebenden Universum.
> Verwandt: `app/screener/filters.py`, `app/models/screener_record.py`, `docs/negative-filters-status.md`
> (§2 Z3/Z4), `Projektstand.md` (Tier-B-Lead), Memory `[[adaptive-stat-swallows-judgment]]`,
> `[[distinguish-failure-from-empty-result]]`.

---

## 1. Problem

Das Basis-Filter-Gate `passes_gross_margin_filter` (`filters.py:46`) ist ein flacher Knock-out:
`gm >= MIN_GROSS_MARGIN (0.30)`. Es wirft zwei Klassen von Qualitätsfirmen falsch raus:

1. **Metrik-undefiniert (Financials/REITs).** yfinance `grossMargins` ist für Banken/Versicherer/REITs
   strukturell undefiniert (kein COGS-Konzept). Beobachtet: der gross_margin-Knock-out trifft ~103
   Financials, **74 mit gm=0**. Das ist ein **Metrik-Artefakt**, kein Qualitätssignal — und der
   Drop ist heute als `gross_margin`-Reason getarnt (unsichtbar).
2. **Strukturell niedrigmargige Sektoren.** Legitime Niedrigmargen-Geschäfte (Retail: Colruyt/DIA;
   Auto: Renault; Shipping: Maersk; Homebuilder: NVR) liegen branchenbedingt unter 30 % und werden
   gedroppt, obwohl sie für ihre Branche normal bis stark sind.

V3-Soll (negative-filters-status.md §2 Z3) war ohnehin „gm < 30 % in 8/10 Jahren" — der flache
Single-Value-30%-Floor ist die dokumentierte **Vereinfachung**, nicht das Ziel.

## 2. Leitprinzip

**Das gross_margin-Gate ist ein struktureller Viabilitäts-Floor, kein Relativ-Qualitäts-Screen.**
Relative Margenqualität wird bereits im Gemini-5-Dimensionen-Raster (Profitability) bewertet,
nuanciert und gegen die anderen Dimensionen gewichtet. Macht das harte Gate dieselbe relative
Diskriminierung, zählt es dasselbe Signal doppelt und presst eine weiche, gescorte Dimension in
einen binären Knock-out. **Harte Gates kodieren notwendige Struktur** (richtige Firmenklasse,
liquide, Marge definiert und nicht pathologisch); **Qualitätsgrade gehören in den Scorer.**

Korollar (Memory `[[adaptive-stat-swallows-judgment]]`): jede adaptive/relative Form, die ein Urteil
lautlos verschlucken würde, wird zugunsten der **expliziten** Variante verworfen. Das hat in diesem
Design dieselbe Weiche dreimal entschieden (Floor statt Relativ; Bruchteil-des-Medians statt
Perzentil; gepinnt statt live).

---

## 3. Mechanismus 1 — Definiertheits-Ausschluss

Wenn `gm` strukturell undefiniert ist, ist der Titel **out-of-scope für das Fisher-Raster** — und
das gilt nicht nur fürs gross_margin-Gate, sondern fürs ganze 5-Dimensionen-Scoring (das Fisher-Raster
passt für Banken/Versicherer/REITs ebenso wenig wie die Bruttomarge). Der Definiertheits-Schlüssel
verdoppelt sich damit als **Fisher-Anwendbarkeits-Proxy**: er schließt die nicht nur am Gate-Artefakt,
sondern verhindert, dass sie mit bedeutungslosen Scores in den Dimensions-Listen landen
(die ursprüngliche BNP/ACA-Sorge — geschlossen, nicht nur das Gate-Artefakt).

- **Schlüssel = Metrik-Definiertheit, NICHT Sektor.** Undefinierte gm → eigener, **sichtbarer**
  Funnel-ReasonCode `FRAMEWORK/METRIK_NA`, sektor-unabhängig. Kein getarnter gross_margin-Drop.
- **Sektor-listen-frei (unbedingt robust).** Ein Definiertheits-Schlüssel fängt Banken UND
  REITs/Real Estate (eigener GICS-Sektor seit 2016, gleiche undefinierte-Marge-Krankheit) gratis mit.
  Auch der COGS-Fallback (s. u.) ist sektor-agnostisch → **nie eine gepflegte Bank-/Financials-Liste.**
- **Zwei symmetrische Kanten, ein Test.** „gm undefiniert" hat zwei Erscheinungsformen, die `.info`
  allein nicht von echten Signalen trennt:
  - *undefiniert-via-Null:* gm=0/≤0. Konflation mit einem **realen** Industrie-Negativmarger
    (real unter Selbstkosten → echtes Negativsignal, gehört zu FAIL, nicht METRIK_NA).
  - *undefiniert-via-spuriös-positiv:* yfinance verrechnet claims/benefits als „cost of revenue" und
    meldet einem Versicherer/REIT eine plausible, aber bedeutungslose gm>0 → rutscht durch ein
    Null-Prädikat, besteht den 30%-Arm, landet doch im Fisher-Scoring.
  - **Beide löst derselbe Test:** „gibt es im `income_stmt` eine echte *Cost-of-Revenue*-Zeile?"
    Ein Daten-/Indexhaus hat eine (Fisher-tauglich); eine Bank/ein REIT hat keine (METRIK_NA,
    egal welche Zahl `.info` meldet). Das ist exakt das `[[distinguish-failure-from-empty-result]]`-
    Muster auf Metrik-Ebene: undefiniert und real-schlecht dürfen nicht dieselbe Form haben.

### Prädikat — Default-Lean, kontingent (s. §6, Property A)

Default-Prädikat = **`.info`-only** (`grossMargins` null/≤0 → METRIK_NA), KEIN neuer Fetch.
Gültig im Runtime **nur, wenn die Gate-A-Probe beide Kanten empirisch leer findet** (kein €2-Mrd-
Industrie-Negativmarger bei gm≤0; kein spuriös-positiver Financial/REIT). Findet die Probe reale
Fälle, kippt das Prädikat auf den **COGS-Struktur-Test** und wandert damit in den Produktionspfad
(income_stmt-Fetch) — siehe §6.

### Downstream

Financials mit **realer, definierter positiver gm** (Prior: schief Richtung Capital Markets —
Börsenbetreiber, S&P Global/Moody's/MSCI, Asset Manager; analytisch Produkt-/Servicefirmen mit
echter Marge, Pricing Power, Burggraben) sind Fisher-tauglich → fließen in Mechanismus 2 und
bestehen auf eigenen Merkmalen.

---

## 4. Mechanismus 2 — Sektor-bewusster Floor (monotone Dual-Arm-Form)

Für Titel mit realer positiver gm.

**Pass, wenn `gm ≥ 0.30` ODER `gm ≥ k × gepinnter_Sektor-Median`.**

- **Monoton (Dual-Arm).** Der absolute 30%-Arm bleibt → hochmargige Sektoren werden nie strenger.
  Der sektor-relative Arm ist ein **zusätzlicher Rettungs-Pfad** → strukturell niedrigmargige Sektoren
  qualifizieren auf branchen-normaler Marge. Strikt additiv (innerhalb Mechanismus 2): droppt nie
  einen aktuellen Survivor.
- **Bauform = Bruchteil-des-Medians, NICHT Perzentil.** `k × Median` schneidet in einem gesunden,
  dicht clusternden Sektor **null** Firmen (Schnittmenge hängt an der Verteilungsform, nicht an einer
  fixen Sektor-Fraktion) — feuert nur am echten Tail. Ein Live-Perzentil wäre eine Relativ-Quote
  (schneidet per Definition ~X % *jedes* Sektors, auch gesunder) = das Median-Problem in leichterer
  Kleidung. Robust-Spread (Median − c·MAD) verworfen: zwei Parameter, MAD an dünnem n instabil,
  Streuungs-Adaptivität re-importiert Quoten-Verhalten. Ein Lageparameter gewinnt für einen Floor.
- **Gepinnt, NICHT live.** Versions-kontrollierter Sektor-Median-Referenz-Table mit **Vintage-Stempel**.
  Ein Live-Median erodiert den Floor synchron zum Sektor-Verfall (Latte sinkt genau im Moment der
  Verschlechterung — lautlose Kapitulation); Pinnen macht den sektorweiten Shift zum sichtbaren,
  bewussten Rekalibrierungs-Ereignis. Zugleich wird „besteht Ticker X den Floor?" eine Eigenschaft
  von X gegen eine fixe Latte, nicht davon, welche anderen Ticker zufällig im Monatslauf sind
  (ein Floor, dessen Urteil über X von Ys Membership abhängt, ist als Floor inkohärent).
  - **Caveat:** Pinnen entkommt dem Snapshot-Problem nicht, es friert einen Snapshot ein. Pinnt man
    mitten im Verfall, bäckt man den verfallenen Median ein → Vintage-Stempel + Rekalibrierungs-Sweep
    prüft „war der Pin-Moment repräsentativ?", nicht nur „veraltet?".
  - **Datenquelle:** Table aus demselben `.info['grossMargins']`-Snapshot des Universums gebaut →
    **kein neuer Datenfetch**, Punkt 2 bleibt (modulo §6 Property A) von Punkt 3 entkoppelt.
- **Granularität = feinster GICS-Knoten, der n_min klärt.** Roll up Sub-Industry → Industry →
  Industry-Group → Sektor, bis die Bucket-Population n ≥ n_min. Jeder Ticker landet im homogensten
  Bucket mit noch stabiler Median-Basis; gut besetzte homogene Gruppen dürfen fein bleiben
  (Table-Zeilen sind bei gepinnt billig). Begründung: GICS-Sektor (11) ist multimodal
  (Consumer Discretionary = Luxus+Auto+Retail; IT = Software ~70 % vs. Hardware ~40 %) → der
  Sektor-Median wäre bedeutungslos; schon ein, zwei Stufen tiefer trennt GICS das auf.
  Datenfelder vorhanden: `gics_sector`, `gics_industry` (`screener_record.py:27-28`). Feinere
  GICS-Knoten (Industry-Group, Sub-Industry) ggf. aus `.info` ergänzen (Gate-A klärt Verfügbarkeit).
- **Dünn-Sektor-Fallback = fail-safe by construction.** Klärt ein Bucket selbst auf Sektor-Ebene
  kein n_min (oder ist die Referenz nicht vertrauenswürdig), feuert der relative Arm einfach **nicht**
  → der Ticker wird am absoluten 30%-Arm allein gemessen. Weil der relative Arm ein Rettungs-Pfad ist,
  heißt „keine valide Referenz → keine Rettung" nie einen Fehl-Reject — schlimmstenfalls entgeht eine
  Rettung. Kein riskanter Notbehelf für n=1/2-Knoten nötig.

---

## 5. Gate-A — Kalibrierung ($0, evidenz-basiert)

Ein Probe-Schritt (analog Punkt-1-Kalibrierung, `scripts/`-Diagnose, kein Gemini) liefert in einem Zug
alle nicht jetzt-blind-setzbaren Werte:

1. **COGS-Struktur-Probe über die Financials/REITs + den gm≤0-Korb + die ~29 real-gm-Financials.**
   Klassifiziert beide Kanten aus §3 → fixiert das Definiertheits-Prädikat (`.info`-only vs.
   COGS-Struktur). Akzeptanz-Erwartung: gm≤0-Korb dominiert von Financials/REITs; die ~29 dominiert
   von Capital-Markets-Compoundern.
2. **Bau des gepinnten Sektor-Median-Tables** (Vintage-gestempelt) inkl. Level-Wahl + n_min,
   sanity-gecheckt an Within-Bucket-Streuung/Multimodalität.
3. **Kalibrierung von k.** Akzeptanzkriterium gespiegelt von Mechanismus 1: **das Sub-k-Band muss
   von echten Kaputt-Margern dominiert und in gesunden Sektoren nahezu leer sein — ist es das nicht,
   ist k falsch.**

Artefakt: `docs/superpowers/audits/2026-06-09-2-gross-margin-floor/calibration.md` (+ reproduzierbare
`scripts/`-Proben), analog zu Punkt 1.

---

## 6. Kontingente Properties — Default-Lean X, Gate-A kann nach Y kippen

Drei Properties reiten auf derselben Wette „die Financials/REITs sind sauber trennbar und die ~29 sind
alle Fisher-tauglich". Der Spec weist sie ehrlich als **kontingent** aus, nicht als Garantie:

| # | Property | Default-Lean (X) | Kippt nach (Y), wenn Gate-A … |
|---|---|---|---|
| A | Datenkopplung | `.info`-only, **kein** neuer Fetch; Punkt 2 von Punkt 3 entkoppelt | … eine Kante real findet → COGS-Struktur-Test in den Produktionspfad → income_stmt-Fetch → Punkt 2 koppelt an Punkt 3. (War ein tragender Grund für „Punkt 2 zuerst" — daher als Bedingung schreiben.) |
| B | Survivor-Delta | **rein additiv**: Mechanismus 2 isoliert additiv (absoluter Arm); Mechanismus 1 droppt keinen aktuellen Survivor, weil die gm≤0-Financials heute schon vom 30%-Floor draußen sind (= Relabeling) | … ein **defined-positive-gm-Financial** nach METRIK_NA umklassifiziert wird → ein kleiner, **expliziter** Drop-Satz (diese Financials raus, mit Grund), kein vermischtes Ledger im „additiv"-Gewand. |
| C | Sektor-Hardcoding | **sektor-listen-frei** — auch der COGS-Fallback ist sektor-agnostisch | **unbedingt robust** — kippt NICHT. Nur A ist kontingent, nie C. |

---

## 7. Gate-B — Cold-Run-Akzeptanz

- Survivor-Delta gemäß §6 Property B (additiv, oder additiv + expliziter kleiner Financials-Drop-Satz).
  Die geretteten Niedrigmargen-Namen **namentlich** identifiziert (erwartet: Colruyt/DIA/Maersk/NVR …).
- Die `METRIK_NA`-Ausschlüsse **sichtbar und korrekt** im Funnel (Financials/REITs raus über
  expliziten Reason, NICHT über gross_margin-Drop). Zweiseitig: die erwarteten raus ∧ kein
  Fisher-tauglicher Capital-Markets-Titel fälschlich als METRIK_NA.
- Reconciliation schließt (Summe der Funnel-Eimer = Universum).
- Verifikation **kalt** (Cache-Purge vorab) — warme Caches maskieren (`[[prod-logging-dormant-and-cache-masks-verification]]`).

Artefakt: `docs/superpowers/audits/2026-06-09-2-gross-margin-floor/gateB_acceptance.md`.

---

## 8. Berührte Komponenten

- `app/screener/filters.py` — `passes_gross_margin_filter` (Dual-Arm + METRIK_NA-Divert);
  `_get_fail_reason` (neuer Reason-Pfad, METRIK_NA vor dem gross_margin-Check).
- `app/models/screener_record.py` — ggf. Feld für den METRIK_NA-Grund / die zugeordnete Bucket-Referenz
  (analog `resolution_detail`, `filter_failed_reason`).
- Funnel-Instrumentierung (`app/screener/funnel.py`, `app/output/funnel_artifacts.py`) — neuer
  ReasonCode `FRAMEWORK/METRIK_NA` als eigener Eimer; gross_margin-Drops bleiben sichtbar getrennt.
- Sektor-Median-Referenz-Table — neues versions-kontrolliertes Datenartefakt (Vintage-gestempelt),
  geladen + validiert wie die ADR-Tabelle (statischer Loader).
- Tests (pytest, DI-Mocks): Dual-Arm-Trennschärfe (absolut-pass / relativ-pass / beide-fail);
  METRIK_NA-Divert (gm≤0 → NA; spuriös-positiv → NA via COGS-Test, falls aktiv); Dünn-Sektor-Fallback
  (kein n_min → relativer Arm feuert nicht → absoluter Arm allein); Pin-Determinismus (gleicher Ticker,
  gleiche Latte unabhängig von Peer-Membership).

---

## 9. Out of Scope — bewusst geparkt

**Mechanismus 3 „eigene Bank-Kennzahl" (ROE / Net Interest Margin / Cost-Income-Ratio)** ist aus
diesem Zyklus geparkt. Nur die Kennzahl zu tauschen heilt den Downstream nicht: das Gemini-5-
Dimensionen-Raster ist genauso Fisher-spezifisch wie das Gate → es bräuchte einen **parallelen
Scoring-Track**. Park-Frage: „Wollen wir Bank-Coverage überhaupt?" — Fishers Philosophie tendiert zu
nein, was den Definiertheits-Ausschluss (Mechanismus 1) zur **terminalen** Antwort macht, nicht zum
Stopgap Richtung Mechanismus 3.

Ebenfalls nicht in diesem Zyklus: Punkt 3 (revenue_growth Mehrjahres-Glättung) — eigener Spec NACH
Punkt 2.
