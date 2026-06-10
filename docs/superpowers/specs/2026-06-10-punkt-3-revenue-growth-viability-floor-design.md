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

**Warum lazy statt Voll-Universum:** Der Fetch ist auf ~200 Titel (heutige 189 + 13) gebounded
statt ~700, und — load-bearing — die Änderungsmenge ist **strikt eine Teilmenge der heutigen
Drops**. Jeder heutige Pass bleibt ein Pass (Monotonie); der Prod-Diff ist vollständig
vorhersagbar und gegen die Diagnose-CSV reconcilierbar (wie die 112 relative_rescues bei Punkt 2).
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
Co. liegen die annualen Daten ja vor). Bleibt auch der annuale Fetch leer → `UNASSESSABLE` → pass.

**No-op-Hinweis Vintage 2026-06:** die gesamte 175er-Negativ-Kohorte hat `n_years=4` — die ≥4-GJ-
Regel verschiebt heute *keine* Zahl. Sie ist rein struktureller Schutz für künftige Kurzhistorie-
Titel (und re-verifiziert beim jährlichen Re-Sweep §5).

---

## 5. Akzeptiertes Residuum X — die Hybrid-B-Asymmetrie

Hybrid B prüft Titel mit **TTM ≥ 0 nie nach**. Ein Titel mit positivem TTM, aber negativer
Mehrjahres-Trajektorie, rutscht damit durch. Der Voll-Universum-Sweep (alle 731 Survivors, offline,
$0) beziffert den Korb:

**X = 76 Survivors** (TTM≥0 heute, aber MULTI_YEAR_DECLINE), davon **42 >10B Large-Caps**, **54
γ-bestätigt** (CAGR<0 ∧ down_years≥2). Beispiele: XOM (TTM +2,6 % / CAGR −6,7 %), Albemarle
(+33 % / −11 %), Fortum (+21 % / −14 %), Kraft Heinz, J.B. Hunt, Illumina, Viatris.

**Bewusst akzeptiert — und zwar *wegen* der Richtung, nicht *trotz* der Größe:** Alle 76 haben
**positives TTM** — ihr Niedergang liegt im Rückspiegel, das jüngste rollierende Fenster wächst
wieder (erholende/inflektierende Titel, kein schleichender Schrumpfer). „Erholt sich gerade — wie
nachhaltig?" ist die Lehrbuch-Scorer-Frage, nicht die Floor-Frage.

Die Alternative A wäre **nicht „strenger"**, sondern würde eine *rückwärtsgewandte* Fehlerklasse
(erholende Titel auf historischem CAGR droppen) gegen eine *vorwärtsgerichtete* eintauschen. Fisher
gewichtet „poised for increase", nicht „war mal größer" — bei Konflikt zwischen jüngerem (TTM) und
älterem (CAGR) Signal gewinnt die Gegenwart. Dass 42/76 Large-Caps sind, ist *Bestätigung*: bei
reifen Zyklikern (Öl, Lithium, Konsum) ist Erholung-nach-Einbruch der Normalfall, den ein
Fisher-Screen sehen *will*.

**Spec-Auflagen zum Residuum:**
1. **Vintage-gestempelt dokumentiert** in `calibration.md` (X=76, davon 54 γ-bestätigt, Stand
   2026-06), `full_sweep_slipthrough.csv` als Provenance-Blob eingefroren — analog Punkt-2-Tabelle.
2. **Jährlicher Re-Sweep** als stehender Monitoring-Posten neben dem Index-Drift-Sweep (Korb
   verschiebt sich mit dem Zyklus).
3. **Vorprüfung „die 76 erreichen den Scorer"** (sonst ist die Erholungs-Begründung hohl): am
   Cold-Run verifizieren, dass keiner der 76 strukturell an einem nachgelagerten Gate (EDGAR)
   hängenbleibt. Legitime EDGAR-Inhalts-Drops (Restatement/Going-Concern) sind orthogonal und in
   Ordnung; nur ein *Artefakt*-Block widerlegte die Begründung.

---

## 6. Kalibrierung & Akzeptanz (Cold-Run, $0)

Wie Punkt-2-Gate-B: kalter Lauf gegen das aktivierte Produktivverhalten, Identitäten asserted.

**Diagnose-Klassifikator auf γ angleichen** (heute α): `scripts/diagnose_revenue_growth_drops.py`
`fetch_trend` von α (`MULTI_YEAR_DECLINE = latest_down ∧ (down_years≥2 ∨ CAGR<0)`) auf γ
(`CAGR<0 ∧ down_years≥2`, kein latest_down) umstellen + ≥4-GJ→UNASSESSABLE. Danach teilen Diagnose
und Prod **dieselbe** (korrigierte) Semantik; die 175er-CSV wird Test-Fixture.

**Akzeptanz-Identitäten (erwartetes Vintage-2026-06-Ergebnis, am Cold-Run re-verifiziert):**
- **Monotonie/Additivität:** jeder heutige revenue_growth-Pass bleibt Pass; Änderungsmenge ⊆ {189+13}.
- **Drop/Rescue-Identität:** exakt **76 gedroppt**, **99 gerettet** (von 175 mit Trenddaten),
  **13 Missing-Data** im UNASSESSABLE/eigenen Zweig (nicht als negatives Urteil gezählt).
- **Residuum:** Voll-Sweep reproduziert **X=76** (54 γ-bestätigt).
- **Reach-Scorer:** die 76 X-Titel überleben EDGAR strukturell (§5.3).

Reduzierter bezahlter Lauf (optional, wie Punkt 2): zweiseitig grün — ein γ-Drop bestätigt
gedroppt, ein Rescue scored.

---

## 7. Berührte Komponenten

| Datei | Änderung |
|---|---|
| `app/screener/filters.py` | `passes_revenue_growth_filter` → γ-Drei-Signal-Konjunktion; Lazy-Fetch-Hook; Missing-TTM nicht mehr implizit False |
| `app/screener/runner.py` | Lazy-`income_stmt`-Fetch für TTM<0/None ∩ Survivors (analog `_assess_definedness_basket`-Pre-Pass); Trajektorie berechnen; `revenue_growth_definedness` setzen |
| `app/services/income_statement.py` | Mehrjahres-Extraktor: `"Total Revenue"` über *alle* GJ-Spalten (heute nur newest via `_first_col_value`) → CAGR + down_years |
| `app/models/screener_record.py` | Felder: `multiyear_revenue_cagr`, `revenue_down_years`, `revenue_growth_definedness` (Enum), `revenue_growth_pass_reason` (Prod-Audit-Primitiv: ABSOLUTE_PASS \| RECOVERED \| DECLINE_DROP \| UNASSESSABLE_PASS) |
| `app/screener/funnel.py` | Reason-Bucket für UNASSESSABLE (retrybar, Geschwister von `RESOLUTION_STATEMENT_UNAVAILABLE`); γ-Drops bleiben `GATE_REVENUE_GROWTH` |
| `scripts/diagnose_revenue_growth_drops.py` | Klassifikator α→γ angleichen + ≥4-GJ-Routing (Diagnose=Prod-Semantik) |
| `data/` + `calibration.md` | `full_sweep_slipthrough.csv` als Provenance-Blob; Residuum-Rationale |
| Tests | `tests/screener/test_filters.py`, `test_runner.py`, `tests/services/test_income_statement.py`; 175er-CSV als Fixture, Identitäts-Asserts §6 |

---

## 8. Out of Scope — bewusst geparkt

- **Voll-Universum-Mehrjahres-Maß (A).** Verworfen zugunsten Hybrid B (§3.2/§5).
- **Regressions-Slope / geglättetes CAGR / mehr GJ.** yfinance liefert ~4 GJ; Endpunkt-CAGR +
  down_years ist die ehrliche Form bei 4 Punkten.
- **Wachstums-Qualitäts-Abstufung im Gate.** Gehört in den Gemini-Scorer (§2).
- **Sektor-relative Wachstumsnorm.** Per Leitprinzip + breitem Sektor-Spread ausgeschlossen.
- **Earnings-Call-/Forward-Guidance-Wachstum.** Tool-B-Tiefe, nicht Tool-A-Floor.
