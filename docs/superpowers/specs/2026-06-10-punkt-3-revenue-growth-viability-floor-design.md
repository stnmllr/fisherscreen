# Punkt 3 — Revenue-Growth-Viabilitäts-Floor — Design

> Status: Design (zur Abnahme). Datum: 2026-06-10.
> Branch: `feature/revenue-growth-viability-floor`.
> Tier-B-Zyklus, Punkt 3 von {2, 3}. Punkt 2 (gross_margin-Floor) ist LIVE — Punkt 3
> kalibriert auf dem von Punkt 2 umgeformten, überlebenden Universum (731 Basis-Survivors).
> Verwandt: `app/screener/filters.py`, `app/screener/runner.py`, `app/services/income_statement.py`,
> `app/models/definedness.py`, `app/models/screener_record.py`, `docs/negative-filters-status.md`,
> Memory `[[adaptive-stat-swallows-judgment]]`, `[[distinguish-failure-from-empty-result]]`,
> `[[punkt2-sector-gross-margin-floor-state]]`.
> Grounding-Artefakte: `scripts/diagnose_revenue_growth_drops.py`,
> `docs/superpowers/audits/2026-06-10-punkt-3-revenue-growth/` (`revenue_growth_drops.csv`,
> `full_sweep_slipthrough.csv`).

---

## 1. Problem

Das Basis-Filter-Gate `passes_revenue_growth_filter` (`filters.py:106`) ist ein flacher
Hard-Knock-out auf einem **einzigen TTM-Snapshot**: pass ⟺ `revenue_growth_yoy >= 0`, wobei
`revenue_growth_yoy = info["revenueGrowth"]` (yfinance, ein rollierender Trailing-Twelve-Month-
YoY-Decimal). Das ist aus zwei Gründen brüchig — beide am realen Drop-Korb des aktivierten
Produktivlaufs vermessen (Vintage 2026-06, warmer Cache, $0):

**Der Gate droppt 189 Titel** (134 ABSOLUTE_PASS margin-stark + 55 RELATIVE_RESCUE = die
margin-schwachen Punkt-2-Zykliker). **105 davon sind >10B Large-Caps** — Roche, Novartis, Nestlé,
LVMH. Viele sterben an Mini-Dellen: Beiersdorf −0,2 %, CNH −0,1 %, Halliburton/Telia −0,3 %,
Geberit −0,6 %, Roche −0,4 %, Novartis −0,7 %.

1. **Snapshot-Brüchigkeit (False Negatives).** Von 175 echt-negativen TTM-Drops mit auswertbarer
   Trajektorie (176 negativ, davon 1 mit zu wenig GJ) haben **87 einen positiven Mehrjahres-CAGR**
   (intakter Trend, einzelnes schwaches TTM-Fenster) gegen 88 echte Mehrjahres-Schrumpfer. Der
   harte Snapshot trennt die beiden nicht — er killt sie gleich.
   Lehrbuch-Fall: Novartis (CAGR +9,2 % / TTM −0,7 %), United Therapeutics (+18 % / −1,6 %),
   Acciona (+21,8 % / −1,7 %) — exakt die Titel, die Fisher *kaufen* würde.
2. **Missing-Data als getarntes Fail.** 13 Titel failen, weil `revenueGrowth` schlicht `None`
   ist (`filters.py:107-109` → return False) — **Unilever, Kering, Infineon, Lonza, Reckitt**,
   Orange, Vivendi, Vodafone, Carrefour, DSM-Firmenich, GF, Pure Storage, Sonova. Das ist ein
   yfinance-Daten-Artefakt, **kein Wachstumsurteil** — und wie bei Punkt 1/2 als generischer
   Drop-Reason getarnt.

Der Sektor-Spread ist **breit, nicht zyklisch dominiert** (Industrials 40 / Cons. Cyclical 31 /
Basic Materials 22, aber Utilities 17, Cons. Defensive 17, Comm 15, Healthcare 12, Tech 12). Eine
sektor-relative Wachstumsnorm wäre damit von vornherein falsch — sie würde Defensives gegen
schrumpfende Peers „retten" und Compounder gegen Wachstums-Peers killen.

V3-Soll war ohnehin ein mehrjähriges Wachstumskriterium; der Single-TTM-Knock-out ist die
dokumentierte **Vereinfachung**, nicht das Ziel.

## 2. Leitprinzip

**Das revenue_growth-Gate ist ein struktureller Mehrjahres-Viabilitäts-Floor, kein
Wachstums-Qualitäts-Screen.** Es eliminiert nur Titel, die über den Messzeitraum *strukturell
schrumpfen*. Die Frage „wie *gut* ist dieses Wachstum?" ist bei Fisher untrennbar vom
Qualitätskontext (Markt, Margenhebel, Management, neue Produktlinien) — Fisher definiert nie
einen Mindest-Wachstumssatz. Sie gehört in die Gemini-Growth-Dimension (sieht Filings/Kontext),
nicht in eine kontextlose Gate-Zahl.

Fisher-Begründung: Punkt 1 der 15 fragt nach „a sizable increase in sales **for at least several
years**" — ein mehrjähriger, vorwärtsgewandter Horizont, nie ein Snapshot. Fisher warnt explizit,
Wachstum nicht an einem einzelnen Jahr zu messen, weil auch exzellente Firmen schwache Einzeljahre
haben (Produktzyklen, Werks-Anlaufkosten, konjunkturelle Dellen).

Korollar (`[[adaptive-stat-swallows-judgment]]`): die Kill-Regel ist **rein absolut/strukturell**
(Vorzeichen + Zähl-Schwelle), keine relative, live-berechnete oder perzentil-basierte Statistik.
Sie verschluckt kein Urteil und braucht — anders als die Punkt-2-Sektor-Median-Tabelle — **kein
Pinning/Vintage-Stempel auf den Schwellwerten** (nur das *Residuum* §5 wird vintage-gestempelt).
Dieselbe Arbeitsteilung wie Punkt 2 (Gate = Struktur, Scorer = Qualitätsgrad) → kohärentes System.

---

## 3. Mechanismus — Hybrid Lazy-Fetch + γ-Drei-Signal-Konjunktion

### 3.1 Datenquellen

| Signal | Quelle | Bemerkung |
|---|---|---|
| TTM-YoY (`revenue_growth_yoy`) | `info["revenueGrowth"]` | bereits vorhanden, ein Decimal |
| Mehrjahres-Umsatz | annual `income_stmt`, Zeile `"Total Revenue"` | via `get_annual_statements(t)[0]`, ~4 GJ |

Der annuale `income_stmt` divergiert teils stark vom TTM-Snapshot (im Sweep: 79 Titel „letztes GJ
annual positiv trotz negativem TTM"). Das ist gewollt verwertet, nicht ignoriert (s. §3.3).

### 3.2 Hybrid Lazy-Fetch (Fetch-Strategie)

```
TTM-Vorcheck mit der vorhandenen .info-Zahl:
  revenue_growth_yoy >= 0   → PASS, KEIN income_stmt-Fetch
  revenue_growth_yoy <  0   → income_stmt nachladen, γ anwenden (§3.3)
  revenue_growth_yoy is None→ income_stmt nachladen, γ anwenden (§3.3)
```

**Warum lazy statt Voll-Universum:** Der Fetch-Korb ist auf die **189** heutigen Drops gebounded
(= 176 negativ-TTM + 13 Missing-TTM; die 13 sind *Teilmenge* der 189, nicht zusätzlich) statt
~700, und — load-bearing — die Änderungsmenge ist **strikt eine Teilmenge der 189**. Jeder heutige
Pass bleibt ein Pass (Monotonie); der Prod-Diff ist vollständig vorhersagbar und gegen die
Diagnose-CSV reconcilierbar (wie die 112 relative_rescues bei Punkt 2).
Voll-Universum (A) würde die Messgröße für alle ~700 wechseln, einen bidirektionalen Diff und ein
neues False-Positive-Risiko in die Gegenrichtung einbauen (s. §5).

**Bekannte Eigenschaft — zyklusabhängige Fetch-Last:** ~200 ist der Stand 2026-06. In einer
Rezession kippen deutlich mehr Titel TTM-negativ; der Lazy-Fetch nähert sich dann (A) an —
ausgerechnet wenn yfinance-Daten am volatilsten sind. Worst Case = Kosten von A (erwogen, gedeckelt
via `[project.scripts]`/Code-Caps). Dokumentiert als bekannte Eigenschaft, nicht als Überraschung
im ersten Krisenlauf.

### 3.3 Kill-Regel γ — Drei-Signal-Konjunktion

Effektiv unter Hybrid B (Mehrjahres-Check läuft *nur* bei TTM<0):

```
DROP  ⟺  TTM < 0  ∧  multiyear_CAGR < 0  ∧  down_years >= 2
```

Drei **unabhängige** Messungen müssen *alle* „Niedergang" sagen: das jüngste rollierende Fenster
(TTM), der Endpunkt-Trend (CAGR über die GJ), die Trajektorien-Zählung (Anzahl down-Jahre).

**Missing-TTM-Sonderfall (`revenueGrowth is None`, die 13):** das TTM-Signal *fehlt*, ist nicht
negativ — der Lazy-Fetch wird trotzdem ausgelöst (§3.2), und der applizierte Drop-Test ist der
Post-Fetch-Kern `CAGR<0 ∧ down_years>=2` (zwei statt drei Signale). Ein fehlendes TTM darf nie
selbst als „down"-Signal zählen (Daten-Artefakt ≠ Urteil); im Zweifel passt der Floor durch.
Damit ist der applizierte Kern in *beiden* Fetch-Zweigen identisch (`CAGR<0 ∧ down_years>=2`);
TTM<0 ist beim Negativ-Zweig das dritte (und frischeste) bestätigende Signal, beim None-Zweig
schlicht abwesend.

**Epistemische Rechtfertigung der Zwei-vs-drei-Signal-Asymmetrie** (sieht auf den ersten Blick
komisch aus — ein Titel mit TTM +0,1 % wird nie geprüft, einer mit TTM=None kann auf CAGR∧dy
fallen — ist aber korrekt): ein vorhandenes positives TTM ist *affirmative Evidenz für Erholung*
und rettet (§5); ein fehlendes TTM ist *keine Evidenz für irgendetwas* — es darf weder als
down-Signal zählen (steht oben) noch als fingiertes Erholungssignal wirken.
**Evidenz für Erholung rettet; Abwesenheit von Evidenz rettet nicht.**

- **Kein separates `latest_down`-Kriterium** (das der α-Variante): das negative TTM *ist* das
  „aktuell down"-Signal — und das *frischeste*. Ein letztes-abgeschlossenes-GJ-down wäre redundant
  bis irreführend, weil das TTM-Fenster aktueller ist als das letzte GJ.
- `multiyear_CAGR` = Endpunkt-CAGR über die verfügbaren GJ (oldest→newest); bei ~4 Punkten ehrlicher
  als eine Regressions-Slope (Scheingenauigkeit). Basisjahr-Sensitivität ist genau der Grund für
  die Konjunktion mit `down_years` (s.u.).
- `down_years` = Anzahl negativer YoY-Übergänge oldest→newest.

**Warum die Konjunktion (γ), nicht CAGR-Vorzeichen (β) oder der Diagnose-Klassifikator (α):**
γ ist die einzige der drei Regeln, die in *beiden* Streit-Kohorten floor-konform entscheidet —
das folgt direkt aus der Konjunktiv-Struktur, kein Zufall:

| Streit-Kohorte (Vintage 2026-06) | β droppt | α droppt | γ | Floor-Urteil |
|---|---|---|---|---|
| **Positiv-CAGR, ≥2 down-years** (LVMH +0,7 %, HAL +3,0 %, Volvo, WBD, Pernod, …; n=11) | ja | ja | **pass** | choppy-aber-*gewachsen* = kein Schrumpfer → Scorer-Urteil, nicht Floor |
| **Negativ-CAGR, 1 down-year** (Roche −1,3 %, Telia −1,8 %, Geberit −2,3 %, Devon, …; n=12) | ja | (teils) | **pass** | einzelnes Einbruchs-*Basisjahr* drückt CAGR negativ → Basisjahr-Artefakt, nicht Niedergang |

β bestraft den Basisjahr-Artefakt; α verlässt die Floor-Rolle, indem es choppy-aber-wachsende
Qualität (LVMH) killt — exakt das Urteil, das wir dem Scorer zugewiesen haben. γ verlangt
Übereinstimmung von Endpunkt *und* Trajektorie → maximal basisjahr-robust UND treu zu „in dubio
durchlassen, der Scorer urteilt".

---

## 4. Mindestdatenbasis & Definedness-Routing

`down_years >= 2` braucht ≥3 YoY-Punkte, also **≥4 Geschäftsjahre**. Bei Titeln mit nur 2–3
verfügbaren GJ (junge Listings, Spin-offs) ist die Schwelle strukturell unerreichbar. Sie dürfen
**nicht stillschweigend als pass durchlaufen** — das wäre die SEAM-2-Silent-Pass-Falle aus Punkt 2,
nur eine Ebene höher (Kriterium *konnte nicht greifen* ≠ Kriterium *bestanden*).

**Routing über die vorhandene Definedness-Enum** (`app/models/definedness.py` —
`DEFINED | METRIK_NA | UNASSESSABLE`, `[[distinguish-failure-from-empty-result]]`):

| Lage | Outcome | Gate-Verhalten |
|---|---|---|
| `income_stmt`-Fetch schlägt fehl (TTM<0/None, aber kein Statement) | `UNASSESSABLE` | pass (Floor-Logik, **bewusstes Routing**) + WARNING + eigener Reason-Bucket |
| <4 GJ verfügbar (Kurzhistorie) | `UNASSESSABLE` | pass (Floor-Logik, bewusstes Routing) |
| ≥4 GJ, γ ausgewertet | `DEFINED` | DROP gdw. γ, sonst pass |

Die Missing-TTM-Fälle (`revenueGrowth is None`, die 13) lösen denselben Lazy-Fetch aus — sie sind
*kein* implizites Fail mehr, sondern werden am Mehrjahres-Maß beurteilt (für Unilever/Infineon &
Co. liegen die annualen Daten ja vor). Mit ≥4 GJ ist das Ergebnis **`DEFINED`** (das Kriterium
*konnte greifen* — vollständiges γ-Verdikt aus echten Statements), **nicht `UNASSESSABLE`**: die 5
γ-Drops darunter (Kering/Unilever/Vivendi/Georg Fischer/Sonova) wegen des fehlenden `.info`-Felds
auf pass umzurouten hieße, ein Daten-Artefakt ein *berechnetes* Urteil überstimmen zu lassen — die
exakte Inversion des ursprünglichen Missing-Data-Bugs (dort täuschte das Artefakt ein Fail vor;
hier verhinderte es ein legitimes). Nur wenn auch der annuale Fetch leer bleibt oder <4 GJ liefert
→ `UNASSESSABLE` → pass.

**Wirkung Vintage 2026-06:** die ≥4-GJ-Regel betrifft heute **genau 1 Titel — TREL-B.ST**
(Trelleborg, `n_years=1`, TTM −2,9 %): er wandert von heutigem implizitem Fail auf
UNASSESSABLE→pass. Das ist *keine* No-op — der eine Titel muss in der Akzeptanz-Identität (§6)
bilanziert sein, sonst ist es genau die unbilanzierte Lücke, die bei Punkt 2 divergente Universen
erzeugte. Re-verifiziert am Cold-Run; ansonsten struktureller Schutz für künftige
Kurzhistorie-Titel (Spin-offs/junge Listings), re-geprüft beim jährlichen Re-Sweep §5.

---

## 5. Akzeptiertes Residuum X — die Hybrid-B-Asymmetrie

Hybrid B prüft Titel mit **TTM ≥ 0 nie nach**. Ein Titel mit positivem TTM, aber negativer
Mehrjahres-Trajektorie, rutscht damit durch. Der Voll-Universum-Sweep (alle 731 Survivors, offline,
$0) beziffert den Korb:

**X = 54 Survivors** (TTM≥0 heute, aber γ-Decline `CAGR<0 ∧ down_years≥2` — also der Korb, den
die γ-Regel bei Nachprüfung selbst droppen würde; die lockerere α-`MULTI_YEAR_DECLINE`-Zählung war
76, davon 22 γ gar nicht droppt). Davon **33 >10B Large-Caps**. Beispiele: XOM (TTM +2,6 % /
CAGR −6,7 %), Intel (+7,2 % / −5,7 %), Chevron (+2,3 % / −7,9 %), Shell (+0,7 % / −11,2 %),
TotalEnergies (+3,4 % / −11,5 %), Pfizer (+5,4 % / −14,8 %).

**Bewusst akzeptiert — und zwar *wegen* der Richtung, nicht *trotz* der Größe:** Alle 76 haben
**positives TTM** — ihr Niedergang liegt im Rückspiegel, das jüngste rollierende Fenster wächst
wieder (erholende/inflektierende Titel, kein schleichender Schrumpfer). „Erholt sich gerade — wie
nachhaltig?" ist die Lehrbuch-Scorer-Frage, nicht die Floor-Frage.

Die Alternative A wäre **nicht „strenger"**, sondern würde eine *rückwärtsgewandte* Fehlerklasse
(erholende Titel auf historischem CAGR droppen) gegen eine *vorwärtsgerichtete* eintauschen. Fisher
gewichtet „poised for increase", nicht „war mal größer" — bei Konflikt zwischen jüngerem (TTM) und
älterem (CAGR) Signal gewinnt die Gegenwart. Dass 33/54 Large-Caps sind (XOM, Intel, Chevron,
Shell, Total, Pfizer), ist *Bestätigung*: bei reifen Zyklikern (Öl) und Pharma (Patent-Klippen)
ist Erholung-nach-Einbruch der Normalfall, den ein Fisher-Screen sehen *will*.

**Spec-Auflagen zum Residuum:**
1. **Vintage-gestempelt dokumentiert** in `calibration.md` (X=54 γ-konsistent, davon 33 Large-Cap;
   Stand 2026-06), `full_sweep_slipthrough.csv` als Provenance-Blob eingefroren (76 α-Zeilen, der
   γ-Korb = `CAGR<0 ∧ down_years≥2`-Filter darauf) — analog Punkt-2-Tabelle.
2. **Jährlicher Re-Sweep** als stehender Monitoring-Posten neben dem Index-Drift-Sweep (Korb
   verschiebt sich mit dem Zyklus).
3. **Vorprüfung „die 76 erreichen den Scorer"** (sonst ist die Erholungs-Begründung hohl): am
   Cold-Run verifizieren, dass keiner der 54 strukturell an einem nachgelagerten Gate (EDGAR)
   hängenbleibt. Legitime EDGAR-Inhalts-Drops (Restatement/Going-Concern) sind orthogonal und in
   Ordnung; nur ein *Artefakt*-Block widerlegte die Begründung.

---

## 6. Kalibrierung & Akzeptanz (Cold-Run, $0)

Wie Punkt-2-Gate-B: kalter Lauf gegen das aktivierte Produktivverhalten, Identitäten asserted.

**Diagnose-Klassifikator auf γ angleichen** (heute α): `scripts/diagnose_revenue_growth_drops.py`
`fetch_trend` von α (`MULTI_YEAR_DECLINE = latest_down ∧ (down_years≥2 ∨ CAGR<0)`) auf γ
(`CAGR<0 ∧ down_years≥2`, kein latest_down) umstellen + ≥4-GJ→UNASSESSABLE + γ einheitlich auch
auf die Missing-TTM-Fälle anwenden (nicht als monolithischen Rescue-Bucket behandeln). Danach
teilen Diagnose und Prod **dieselbe** (korrigierte) Semantik; die volle **189er-CSV** wird
Test-Fixture (Assertion = 81/107/1, s.u.).

**Akzeptanz-Identitäten (erwartetes Vintage-2026-06-Ergebnis, am Cold-Run re-verifiziert):**
- **Monotonie/Additivität:** jeder heutige revenue_growth-Pass bleibt Pass; Änderungsmenge ⊆ den
  189 (107 neu pass + 1 UNASSESSABLE-pass, 81 weiterhin drop). Die 5 missing-TTM-γ-Drops waren
  heute schon Drops (`None→False`) — sie bleiben Drops, nur mit jetzt legitimem statt
  artefaktischem Grund; **kein heutiger Pass kippt** (kein Titel wird neu rausgeworfen).
- **Voll-bilanzierte Drop/Rescue-Identität (γ einheitlich über alle 189):**

  **189 = 81 DROP + 107 RESCUE + 1 UNASSESSABLE** (geht voll auf — kein unbilanzierter Titel)
  - negativ-TTM (176) → **76 DROP + 99 RESCUE + 1 UNASSESSABLE** (= TREL-B.ST, Kurzhistorie §4)
  - missing-TTM (13) → **5 DROP + 8 RESCUE** (γ-Drops: Kering/Unilever/Vivendi/Georg Fischer/Sonova
    = echte Mehrjahres-Schrumpfer, floor-korrekt — *nicht* monolithischer Rescue-Bucket; alle 13
    bleiben via `revenue_growth_yoy=None` identifizierbar)
- **Residuum:** Voll-Sweep reproduziert **X=54** γ-konsistent (33 Large-Cap).
- **Reach-Scorer:** die 54 X-Titel überleben EDGAR strukturell (§5.3).

Reduzierter bezahlter Lauf (optional, wie Punkt 2): zweiseitig grün — ein γ-Drop bestätigt
gedroppt, ein Rescue scored.

---

## 7. Berührte Komponenten

| Datei | Änderung |
|---|---|
| `app/screener/filters.py` | `passes_revenue_growth_filter` → γ-Drei-Signal-Konjunktion; Lazy-Fetch-Hook; Missing-TTM nicht mehr implizit False |
| `app/screener/runner.py` | Lazy-`income_stmt`-Fetch für TTM<0/None ∩ Survivors (analog `_assess_definedness_basket`-Pre-Pass); Trajektorie berechnen; `revenue_growth_definedness` setzen |
| `app/services/income_statement.py` | Mehrjahres-Extraktor: `"Total Revenue"` über *alle* GJ-Spalten (heute nur newest via `_first_col_value`) → CAGR + down_years |
| `app/models/screener_record.py` | Felder: `multiyear_revenue_cagr`, `revenue_down_years`, `revenue_growth_definedness` (Enum), `revenue_growth_pass_reason` (Prod-Audit-Primitiv: **`TTM_PASS` \| `TRAJECTORY_RESCUE` \| `DECLINE_DROP` \| `UNASSESSABLE_PASS`**). Bewusst **kein** `ABSOLUTE_PASS`/`RECOVERED`: `ABSOLUTE_PASS` ist bereits das Punkt-2-gross_margin-Clearance-Token (dasselbe Token für zwei Gates macht Reconciliation-Queries mehrdeutig); `RECOVERED` ist im Diagnose-Skript schon eine `trend_class` mit *engerer* Bedeutung (letztes GJ annual up) — als pass_reason würde es fälschlich auch SINGLE_YEAR_DIP/MIXED-Passes einschließen. Die 13 Missing-TTM bleiben orthogonal via `revenue_growth_yoy=None` identifizierbar (sie verteilen sich auf TRAJECTORY_RESCUE und DECLINE_DROP, sind kein eigener Code). |
| `app/screener/funnel.py` | Reason-Bucket für UNASSESSABLE (retrybar, Geschwister von `RESOLUTION_STATEMENT_UNAVAILABLE`); γ-Drops bleiben `GATE_REVENUE_GROWTH` |
| `scripts/diagnose_revenue_growth_drops.py` | Klassifikator α→γ angleichen + ≥4-GJ-Routing (Diagnose=Prod-Semantik) |
| `data/` + `calibration.md` | `full_sweep_slipthrough.csv` als Provenance-Blob; Residuum-Rationale |
| Tests | `tests/screener/test_filters.py`, `test_runner.py`, `tests/services/test_income_statement.py`; 189er-CSV als Fixture, Identitäts-Asserts §6 (81/107/1) |

---

## 8. Out of Scope — bewusst geparkt

- **Voll-Universum-Mehrjahres-Maß (A).** Verworfen zugunsten Hybrid B (§3.2/§5).
- **Regressions-Slope / geglättetes CAGR / mehr GJ.** yfinance liefert ~4 GJ; Endpunkt-CAGR +
  down_years ist die ehrliche Form bei 4 Punkten.
- **Wachstums-Qualitäts-Abstufung im Gate.** Gehört in den Gemini-Scorer (§2).
- **Sektor-relative Wachstumsnorm.** Per Leitprinzip + breitem Sektor-Spread ausgeschlossen.
- **Earnings-Call-/Forward-Guidance-Wachstum.** Tool-B-Tiefe, nicht Tool-A-Floor.
- **Corporate-Action-Bereinigung (Spin-offs/Divestitures).** Extreme CAGR-Ausschläge können
  abgespaltenen statt verlorenen Umsatz reflektieren (Vivendi −68 %/dy=2 = Aufspaltung Ende 2024).
  Der γ-Drop ist trotzdem richtig — eine Holding, die den Großteil ihres Geschäfts abgegeben hat,
  ist kein Fisher-Kandidat im Sinne des Screens. Der Floor unterscheidet organischen Schrumpf von
  Corporate-Action **nicht** und **soll** es nicht (das wäre Tool-B-Tiefe). Als bekannte
  Eigenschaft dokumentiert, kein Sonderpfad.
