# Sektor-relatives & deterministisches Scoring (Tool A) — Design

> Status: Design (zur Abnahme). Datum: 2026-06-16.
> Branch: `feature/sector-relative-scoring`.
> Baut auf Scoring-Prompt v2.1 auf (`[[scoring-prompt-v2-flat-state]]`, live seit 06-15).
> Verwandt: `app/screener/scorer.py`, `app/screener/dimensions.py`, `app/screener/runner.py`,
> `app/screener/filters.py`, `app/screener/revenue_trajectory.py`,
> `app/services/gemini_client.py`, `app/services/cached_yfinance_client.py`,
> `app/models/screener_record.py`, `app/output/crosshits_generator.py`,
> `app/output/dimensions_generator.py`.
> Memory: `[[adaptive-stat-swallows-judgment]]`, `[[prompt-objective-trigger-not-subjective-judgment]]`,
> `[[aggregate-metrics-dont-prove-mechanism]]`, `[[gemini-ttl-cold-monthly-scheduler-followup]]`,
> `[[punkt3-revenue-growth-floor-state]]`.
> Grounding-Artefakt: `scripts/analyze_sector_relative_evidence.py` (read-only Firestore-Härtung,
> reproduziert den 2026-06-Lauf bit-genau: growth≥4=573, profitability≥4=602, resilience≥4=460,
> Crosshit(all-3)=281).

---

## 1. Problem (gehärtet gegen den 2026-06-Lauf)

Drei der vier Argumente des ursprünglichen Backlog-Eintrags halten der Primär-Evidenz **nicht**
stand — die Härtung (Firestore-Reproduktion, volle Verteilung statt Top-50) hat sie widerlegt:

- **„Fast ausschließlich Tech/Healthcare / Industrials ~null"** → falsch. Über alle 281 Crosshits
  ist **Industrials der größte Sektor (72; 25.6 %)**, vor Technology (64; 22.8 %). Tech+Healthcare
  = 37 %, der Rest verteilt auf 8 Sektoren. Die einzigen real dünnen Sektoren sind Utilities (1)
  und Real Estate (0) — die der Backlog nicht einmal nennt.
- **„Interne Inkonsistenz: Gate rettet → Scorer killt"** → widerlegt. Von 138 gescorten
  RELATIVE_RESCUE-Titeln (sub-30%-Gross-Margin) werden **30 (21.7 %) Crosshit, alle über
  resilience≥4** (resilience faltet `debt_to_equity` UND `gross_margin` — niedriger Hebel trägt).
  Der linke Schwanz (50× resilience=2) ist *berechtigt* (z. B. 8TRA.DE: GM 16.9 % ∧ d/e 143.7 %),
  kein übersehener Klassenbester.
- **Miner-Beispiel motiviert sektor-relativ** → schwach. HL/NEM/EDV ranken auch *innerhalb* Basic
  Materials hoch (Superzyklus-Peak ist P90 auch sektor-relativ); sektor-relativ allein heilt das
  nicht.

**Was unwiderlegt bleibt — das eigentliche Problem: Score-Klumpung / 4-Inflation.** 69 % / 72 % /
55 % der 832 Survivor scoren ≥4 auf growth / profitability / resilience einzeln; **33.8 % auf allen
dreien.** Die Merit-Scores klumpen bei 4.33–4.67 (vgl. Crosshits-Header). Die gerankte Liste ist
dadurch kaum trennscharf. Plus zwei *strukturelle* Defekte, die das absolute Scoring erzeugt:

1. **Margen-Strukturnachteil (False Negative).** Kapitalintensive Sektoren (Industrials, Materials,
   Energy) tragen strukturell niedrige Margen/höheren Hebel — egal wie gut geführt. Absolute
   Margen-/Leverage-Anker bestrafen ihren Klassenbesten systematisch.
2. **Zyklik-Peak als Pseudo-Qualität (False Positive).** Ein Rohstofftitel mit einem
   Superzyklus-Jahr (TTM>0 → kein Mehrjahres-Check) zeigt kurzfristig Top-Wachstum, das nicht
   strukturell ist.

## 2. Leitprinzip

Tool A sucht die **besten Titel für langfristige Investition** nach Fishers 15 Punkten — als
Recall-Vorfilter für Runde 2 (Watchlist/Deep Dive). **Ziel ist nicht Sektor-Breite oder -Fairness.**
Ein Sektor darf komplett leer bleiben. Was zählt: **ein genuiner Klassenbester darf nicht durch ein
Metrik-Artefakt aus Runde 2 fallen** — weder (a) weil ein anderer Sektor gerade zyklisch heiß läuft,
noch (b) weil Tool As absolute Schwellen seinen Sektor strukturell benachteiligen.

Daraus folgt die Zwei-Achsen-Behandlung (bewusst *nicht* alle drei gleich):

- **Marge/Hebel ist strukturell sektor-gebunden** → `profitability` und `resilience` werden
  **sektor-relativ** (Perzentil im eigenen Sektor). Das heilt Defekt (1).
- **Wachstum ist *nicht* sektor-gebunden** — „ein großer Wachser ist großartig, egal in welchem
  Sektor", und ein strukturell langsam wachsender Sektor *soll* niedrig scoren. Konsistent mit der
  Punkt-3-Spec (2026-06-10, §1): „eine sektor-relative Wachstumsnorm wäre von vornherein falsch".
  → `growth` bleibt **sektor-blind**. Defekt (2) — der Zyklik-Peak — wird durch einen **absoluten
  Konsistenz-Dämpfer** über die verfügbaren Geschäftsjahre gefangen, nicht durch Sektor-Relativierung.

Und gegen die Klumpung: **der Score wird deterministisch aus der (uniformen) Perzentil-Verteilung
gerechnet, nicht vom LLM geschätzt** — Entklumpung per Konstruktion (Approach B, siehe §9). Deckt
sich mit `[[adaptive-stat-swallows-judgment]]` (Urteil explizit/gepinnt erzwingen statt einer
adaptiven Statistik überlassen).

## 3. Architektur & Datenfluss

Eine neue Stufe `percentile_prep` zwischen Gates und Scoring, auf der **Pre-Scoring-Kohorte** (die
~832, die das Scoring erreichen — **nicht** die fertige Crosshit-Liste; das wäre zirkulär):

```
gates → [NEU: percentile_prep] → [NEU: deterministic_scorer] → crosshits/dimensions
```

`percentile_prep`:
1. Mehrjahres-Revenue-Serie für **alle** Kohorten-Titel sicherstellen (Cache/Fetch, §7) →
   `growth_consistency`.
2. Kohorte nach **rohem yfinance-`sector`-String** gruppieren (§4).
3. Pro Sektor die within-run-Perzentil-Ränge der sektor-relativen Inputs berechnen
   (`operating_margin`, `return_on_equity`, `gross_margin`, `debt_to_equity`).
4. `revenue_growth_yoy`-Perzentil **kohorten-global** (sektor-blind) berechnen.
5. Annotationen auf den `ScreenerRecord` schreiben.

Neue Felder auf `ScreenerRecord`:

```python
input_percentiles: dict[str, float] | None  # {"operating_margin": 82.0, "revenue_growth_yoy": 71.0, ...}
growth_consistency: float | None            # positive_years_ratio; None = UNASSESSABLE (<4 GJ)
score_basis: dict[str, str] | None          # PER ACHSE: {"growth":"global",
                                            #   "profitability":"sector_relative"|"global_fallback",
                                            #   "resilience":"sector_relative"|"global_fallback"}
data_confidence: str                        # "ok" | "low"  (default "ok")
```

`deterministic_scorer` ersetzt `run_gemini_scoring`: rechnet `gemini_dimensions` (Name bleibt
schemastabil) aus den Annotationen, setzt `gemini_evidence` (code-getemplatet), `weakest_dimension`
(= argmin der drei Merit-Achsen), `gemini_data_gaps` (= Merit-Inputs, die `None` sind).

## 4. Sektor-Gruppierung, Guards, Fallback

- **Gruppierung auf rohem yfinance-`sector`-String** (`ScreenerRecord.gics_sector`). Für
  within-run-Perzentile ist **keine** Normalisierung auf kanonische GICS-11 nötig — die Labels sind
  innerhalb eines Laufs selbst-konsistent (verifiziert: 10 saubere Buckets + Real Estate). Die im
  Backlog skizzierte „Technology→IT"-Lookup entfällt ersatzlos (weniger Code, eine Fehlerquelle
  weniger). Dies betrifft **nur** die sektor-relativen Achsen (profitability, resilience).
- **Min-Sektor-N-Guard: N = 30.** Sektor mit < 30 Membern in der Pre-Scoring-Kohorte → Sektor-
  Perzentile instabil → profitability/resilience fallen für diesen Sektor auf **kohorten-globales
  Perzentil** (sektor-blind, dieselbe Ankertabelle) zurück, `score_basis[axis] = "global_fallback"`.
  Kein Magic-Number-Absolut-Anker (es gibt mit A1 keinen v2.1-Prompt mehr) — der globale Perzentil-
  Fallback bleibt deterministisch und entklumpt, genau wie growth.
- **Sektor fehlt/unmappbar** (die ~10 Titel ohne `sector`-Label): ebenfalls globaler Perzentil-
  Fallback, `score_basis[axis] = "global_fallback"`, Sektor-Anzeige `n/a`. **Nicht gedroppt,
  crosshit-fähig** — bekommt nur die sektor-relative Behandlung nicht (keine vergleichbare
  Peer-Group). Kein „various"-Sammeltopf (heterogene Peer-Group → bedeutungsloses Perzentil); der
  globale Pool ist die ehrlichere Vergleichsbasis.
- **`score_basis` ist PER ACHSE** (dict), nicht ein Titel-String: profitability und resilience können
  unabhängig auf global_fallback fallen (heute v. a. via N-Guard gemeinsam, aber der dict hält das
  Audit-Trail eindeutig und ist v2-fest). `growth` ist konstruktionsbedingt immer `"global"`.
- **growth** ist sektor-blind und damit vom N-Guard **nicht** betroffen — immer kohorten-global.

## 5. Score-Mechanik je Achse (deterministisch, 0–5)

### Gepinnte Perzentil→Score-Ankertabelle (sektor-relative Achsen + globales growth)

| Perzentil P | Score |
|---|---|
| P ≥ 90 | 5 |
| P ≥ 75 | 4 |
| P ≥ 40 | 3 |
| P ≥ 15 | 2 |
| P < 15 | 1 |

Uniform verteilte Perzentile ⇒ grob 10 % → 5, 15 % → 4, 35 % → 3, 25 % → 2, 15 % → 1 je Achse.
**Das ist die kalibrierte Selektivität** (Schwellen calibrierbar; siehe Akzeptanzlauf).

### growth (sektor-blind)
- **Realisierung von „growth absolut":** kohorten-**globales** Perzentil
  `P_global(revenue_growth_yoy)` → Ankertabelle. Bewusst *globales Perzentil* statt fixer
  Absolut-Schwellen (z. B. 25 %/15 %/5 %): entklumpt wie die anderen Achsen und vermeidet
  willkürliche Magic-Numbers, bleibt aber sektor-blind („großer Wachser, egal welcher Sektor").
  Falls stattdessen fixe Schwellen gewollt sind → Review-Gate.
- **Konsistenz-Cap** (§6) wird *danach* angewandt: `growth = min(anchor_score, consistency_cap)`.

### profitability (sektor-relativ)
- Mittel der vorhandenen Input-Perzentile: `mean(P_sector(operating_margin), P_sector(return_on_equity))`
  → Ankertabelle.
- **Red-Flag-Overlay → 0** (absolut, überschreibt): `operating_margin < 0` **oder**
  `return_on_equity < 0`.

### resilience (sektor-relativ)
> **Einheiten-Warnung (`[[quant-field-guard-data-layer]]`):** `debt_to_equity` ist als rohe
> yfinance-Zahl in **Prozent-Punkten** (z. B. `45.0` = 45 % = 0,45×; Fixtures: 45/30/40), während
> `operating_margin`/`return_on_equity`/`gross_margin`/`revenue_growth_yoy` **Dezimal** sind
> (0,18 = 18 %). Absolute d/e-Schwellen daher in Prozent-Punkten. Perzentil-Ränge sind
> skaleninvariant — nur die absoluten Red-Flag-/Vorzeichen-Schwellen sind einheitenabhängig.

- `mean(P_sector(gross_margin), 100 − P_sector(debt_to_equity))` → Ankertabelle.
  (Der invertierte d/e-Term: niedriger Hebel = höheres Perzentil = besser.)
- **`debt_to_equity < 0` → aus dem resilience-Perzentil ganz ausschließen** (Titel-Wert *und*
  Sektor-/Global-Verteilung): resilience dann nur aus `P(gross_margin)`, Evidenz vermerkt
  `„d/e n/a (negatives Buchkapital)"`. **Kein** Red-Flag. Begründung: negatives d/e ist überwiegend
  **buyback-getriebenes negatives Buchkapital** (SBUX/MCD/HD/AZO — Qualitäts-Cash-Generatoren, nicht
  Distressed); es als 0 zu werten würde sie fälschlich killen, und negative Werte in der Verteilung
  würden „am negativsten = am sichersten" ranken. Echte Distress-Fälle (going concern) sind upstream
  im EDGAR-Gate gefangen.
- **Red-Flag-Overlay → 0** (absolut, nur positiver Extrem-Hebel): `debt_to_equity > 300`
  (= >300 % = 3× Eigenkapital; Prozent-Punkte!). Kalibrierbar im Akzeptanzlauf.

### management / innovation
- Unverändert Sentinel-3, zählen nicht zum Crosshit (siehe `dimensions.py`).

### Fehlende Inputs
- Perzentil wird nur über **nicht-`None`-Werte** der Kohorte gebildet; ein Titel mit `None` für einen
  Input geht **nicht** in dessen Verteilung ein und bekommt dafür kein Perzentil.
- Sind **alle** Inputs einer Achse `None` → Achse = 3, Input in `gemini_data_gaps` gelistet,
  `data_confidence = "low"`. Die Achse treibt dann faktisch keinen Crosshit (3 < 4).

## 6. Konsistenz-Dämpfer (anti-zyklisch, absolut, nur growth in v1)

- **Metrik:** `growth_consistency = (transitions − down_years) / transitions`, berechnet aus
  `classify_revenue_trajectory` (existiert; liefert `down_years` über n−1 YoY-Transitionen).
  DEFINED nur bei ≥ 4 GJ (`MIN_FISCAL_YEARS`), sonst `UNASSESSABLE` → `None`.
- **Absolut, nicht sektor-relativ** — bewusst: sektor-relativ würde den Superzyklus-Peak gegen
  ebenso spiky Miner-Peers messen und durchwinken. Die Level-Achsen sind sektor-relativ; Konsistenz
  ist der absolute Zyklik-Filter obendrauf.
- **Cap (koppelt an objektives, code-gerechnetes Signal — `[[prompt-objective-trigger-not-subjective-judgment]]`):**

  | `growth_consistency` | consistency_cap |
  |---|---|
  | ≥ 0.75 | 5 |
  | ≥ 0.50 | 4 |
  | < 0.50 | 3 |
  | `None` (UNASSESSABLE, <4 GJ) | **4** (konservative Schranke) + `data_confidence = "low"` |

  `growth = min(anchor_score, consistency_cap)`. Beispiel: P90-Einjahres-Spike (anchor 5) mit
  ratio 0.25 (1 von 4 Jahren gewachsen) → growth = 3.
  **UNASSESSABLE-Schranke (Spin-off-Blindfleck):** Ein Titel mit zu kurzer Historie (z. B. SNDK,
  1 Datenpunkt) kann strukturell *nicht* belegen, dass ein hohes Perzentil-Wachstum dauerhaft ist —
  ein Superzyklus-Spinoff-Jahr darf daher nicht growth=5 erzeugen. Cap=4 deckelt das deterministisch,
  ohne neue Logikschicht, und lässt den Titel via `data_confidence=low`-Flag sichtbar (§8). Echte
  Mehrjahres-Konsistenz (≥0,75) bleibt nötig, um growth=5 zu erreichen.
- Punkt 3 droppt γ-Decline (cagr<0 ∧ down_years≥2) bereits upstream; der Cap fängt den **Rest**
  (flach + ein Spike). **Margen-Konsistenz ist v2** (bräuchte Mehrjahres-Margendaten).

## 7. Mehrjahres-Daten & Caching

- Der Trajektorien-Pre-Pass (`_assess_revenue_growth_trajectory`) wird von der Decline-Kohorte auf
  **alle Kohorten-Titel** ausgeweitet — nötig, weil die Zyklik-Peaks (TTM>0) heute gar nicht geholt
  werden.
- **Neue Firestore-Collection `dev_revenue_series`** (doc-id = ticker): nur die extrahierte
  Revenue-Liste (~4 Floats) + `_cached_at`. **TTL ~400 Tage** (Jahresdaten ändern sich jährlich —
  langer TTL ist hier *korrekt*, anders als die bewusst kurze Gemini-2d-Logik). Konfigurierbar via
  `FISHERSCREEN_REVENUE_SERIES_TTL_DAYS`.
- **Pre-Warm-Backfill-Skript** (`scripts/backfill_revenue_series.py`, manuell vor dem ersten
  Prod-Monatslauf): füllt `dev_revenue_series`, damit **kein Monatslauf** je den vollen kalten
  Income-Statement-Preis zahlt. Schützt die harte 1800s-Cloud-Run-Deadline
  (`[[gemini-ttl-cold-monthly-scheduler-followup]]`).

## 8. Track-Record / Spin-offs

- < 4 GJ als eigenständige Gesellschaft → `growth_consistency = None` (UNASSESSABLE) →
  `data_confidence = "low"`.
- **Verhalten:** weiter gescort, **crosshit-fähig, aber mit sichtbarem `data_confidence=low`-Flag**
  in der Ausgabe. **Konsistenz-Cap = 4** (konservative Schranke, §6) — growth kann ohne belegbare
  Mehrjahres-Konsistenz nicht 5 erreichen (schließt den Spin-off-Superzyklus-Blindfleck). Erfüllt das
  Backlog-Kriterium „kein Spin-off erreicht Crosshit *ohne* Flag", ohne genuine Qualitäts-Spin-offs
  dauerhaft zu verlieren (Recall-Ziel). Beispiel: SNDK (Abspaltung 2024).

## 9. Tool A wird LLM-frei (Approach B / A1)

Da der Code scort, sind Score, `weakest_dimension` (= argmin der drei) und `data_gaps` (= `None`-
Inputs) code-ableitbar. Die Evidenz-Note zitiert nur code-bekannte Zahlen und wird **deterministisch
code-getemplatet**, z. B.:
`"operating_margin 18% (sector P82), return_on_equity 22% (sector P79)"`.

**Folge: Tool A ruft Gemini nicht mehr auf.** `app/services/gemini_client.py` bleibt für Tool B
unangetastet; in Tool A entfällt der Aufruf. Token-Cap-Maschinerie wird in Tool A gegenstandslos
(bleibt im Code für Tool B). Cost-Tracking (`dev_screener_runs`) protokolliert weiterhin, jetzt mit
`tokens_in=tokens_out=0` / `estimated_cost_usd=0.0`. CLAUDE.md-Tabelle „Gemini Flash Lite ✅ Tool A"
wird in einem Doc-Update nachgezogen (Tool A = deterministisch, kein LLM).

## 10. Output / Audit

- `crosshits_generator` / `dimensions_generator`: zusätzliche Marker aus `score_basis` (per-Achse;
  ein Titel wird als `global_fallback` markiert, sobald *eine* sektor-relative Achse global gefallen
  ist) und `data_confidence` (Flag nur wenn `low`).
- Evidenz-Note zitiert **Absolutzahl + Perzentil** (Auditierbarkeit bleibt erhalten — die
  Backlog-Anforderung).
- **Die Crosshit-Quote fällt deutlich** (von 33.8 %): bei ~25 % je Achse über P75 und drei
  geforderten Achsen grob auf einstellige Prozent. **Das ist das gewünschte Selektivitäts-Signal,
  kein Bug.** Gearbeitet wird ohnehin mit der gerankten Ø-Score-Top-Liste, die jetzt trennscharf
  ist, nicht mit dem Gate-Count.

## 11. Bewusst NICHT in v1 (→ v2)

- **Margen-/Profitabilitäts-Konsistenz** über mehrere Jahre (zweiter Zyklik-Vektor).
- **Historischer Perzentil-Store** (within-run reicht für v1).
- **Normalisierung auf kanonische GICS-11** (für within-run unnötig).
- **Kalibrierung der Anker-Schwellen** über den ersten Akzeptanzlauf hinaus.

## 12. Tests (TDD, DI-gemockt, kein Netz)

- **Unit — Perzentil:** Gruppierung nach Sektor, Ties (gleiche Werte → gleiches Perzentil),
  `None`-Ausschluss aus der Verteilung, Min-N=30-Fallback, fehlender Sektor → absoluter Fallback,
  growth global vs. profitability/resilience sektoral.
- **Unit — Anker-Mapping:** Grenz-P-Werte exakt (90/75/40/15), Monotonie.
- **Unit — Konsistenz:** ratio-Berechnung, Cap-Bänder (0.75/0.50), `None`→**cap=4**+low,
  `min(anchor, cap)`.
- **Unit — Red-Flag-Overlay & d/e-Einheit:** `op_margin<0` / `roe<0` → profitability 0;
  `d/e>300` (Prozent-Punkte) → resilience 0; `d/e<0` → **aus Perzentil ausgeschlossen** (Titel +
  Verteilung), resilience aus `gross_margin` allein (**nicht** 0); growth ohne Overlay. Fixture mit
  d/e=45.0 (=45 %) als Einheits-Anker.
- **Unit — Evidenz-Template:** zitiert Absolut + Perzentil, deterministisch.
- **Unit — Cache:** `dev_revenue_series` get/set, TTL-Frische, Backfill-Pfad.
- **Integration (kalter Dry-Run, $0):** misst die **Entklumpung** (Score-Verteilung je Achse ~uniform
  statt 55–72 % bei ≥4); prüft den **Recall-Gegenprobe-Fall** (struktureller Niedrigmargen-Industrieller
  ≈ Software-Qualitätsname auf profitability); verifiziert den **HL/NEM/EDV-Konsistenz-Cap** (deren
  `down_years`/ratio); prüft, dass kein <4-GJ-Titel Crosshit wird ohne `data_confidence=low`.

## 13. Akzeptanzkriterien (Recall-Ziel — *nicht* Sektor-Count)

1. **Selektivität:** Crosshit-Quote fällt messbar von 33.8 %; je Achse keine 55–72 %-Klumpung bei
   ≥4 mehr, sondern ~uniforme 1–5-Verteilung.
2. **Recall / False Negative:** ein bekannter struktureller Niedrigmargen-Qualitätsführer (Industrials)
   scort auf profitability vergleichbar mit einem Software-Qualitätsnamen — Perzentil treibt, nicht
   Absolutmarge.
3. **Gegenrichtung:** ein mittelmäßiger Hochmargen-Operator (niedriges Sektor-Perzentil trotz ok
   Absolutmarge) scort niedriger als heute.
4. **Anti-Zyklik:** HL/NEM/EDV growth wird durch den Konsistenz-Cap gedeckelt (gegen den
   2026-06-Lauf verifiziert).
5. **Spin-off:** kein <4-GJ-Titel erreicht Crosshit ohne `data_confidence=low`-Flag.
6. **Bezahlter Validierungslauf** ($0, da LLM-frei — faktisch nur Compute/yfinance) als Gate, mit
   Vorher/Nachher-Score-Verteilung.

## 14. Sequenzierung

- Eigener Branch `feature/sector-relative-scoring`, TDD, gegated. Direkt-Commit auf `main` nur mit
  expliziter Freigabe (CLAUDE.md).
- Reihenfolge: (a) Perzentil-Engine + Tests → (b) deterministischer Scorer + Red-Flag/Konsistenz +
  Tests → (c) `dev_revenue_series`-Cache + Backfill-Skript → (d) Runner-Verdrahtung +
  Output-Marker → (e) kalter Dry-Run (Entklumpung messen) → (f) Akzeptanzlauf-Gate → (g) Doc-Updates
  (CLAUDE.md Tool-A-LLM-frei, negative-filters-status).
```
