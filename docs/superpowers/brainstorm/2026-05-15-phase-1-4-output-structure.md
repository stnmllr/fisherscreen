# Phase 1.4 — Output-Struktur

**Datum:** 2026-05-15
**Status:** Entscheidungen getroffen, bereit für writing-plans-Session
**Verwandte Dokumente:**
- `docs/superpowers/brainstorm/2026-05-11-phase-1-structure.md` (Phase-1-Master)
- `PROJEKTSTAND.md` (aktueller Stand)
- `CLAUDE.md` (Projekt-Konventionen — Output-Pfad-Korrektur Teil dieses Brainstorms)

---

## Kontext

Phase 1.1–1.3 sind auf `main`. Tool A produziert pro Run intern eine vollständige
`ScreenerRecord`-Liste (~400 Ticker nach Negativfilter + Gemini-Scoring auf fünf Dimensionen).
Phase 1.4 generiert daraus die Markdown-Artefakte für Obsidian.

Der ursprüngliche Plan im Master-Brainstorm sah „ein File pro Ticker in `output/Universum/`"
vor (~400 Files/Monat). Eine Premortem-Diskussion am 2026-05-15 hat ergeben:
das skaliert kognitiv nicht — Stephan schaut realistisch maximal 10 Ticker pro Monat an.
Die 390 anderen Files verstecken die 10, die zählen.

Dieser Brainstorm definiert die korrigierte Output-Struktur.

---

## Leitprinzip: Trichter, nicht Bibliothek

Tool A produziert keine Bibliothek von 400 Ticker-Files. Es produziert ein **Briefing**
mit drei Sichten unterschiedlicher Detailtiefe:

```
~2.100 Universum   → intern, nie als Markdown
~400 nach Filtern  → in Dimensions.md als Tabellen
~Top-50 pro Dim.   → in Dimensions.md als gerankte Listen
~Crosshits         → in Crosshits.md als Aufmerksamkeits-Trigger
Veränderungen      → in Changes.md als Push-Layer
```

Markdown ist Briefing-Sicht, Firestore ist Cache + Cost-Log. Diese Trennung ist
das Kernprinzip der Architektur.

---

## Entschiedene Fragen

### A) Output-Pfad: `output/Universum/`

**Entscheidung:** Output-Pfade sind repo-relativ unter `output/`. Konkret:
`output/Universum/YYYY-MM-Dimensions.md` etc.

**Begründung:**
- `output/` ist ein klar definierter Container — separiert vom Code (`app/`, `tests/`),
  von Doku (`docs/`) und von generierten Logs/Temp-Files
- Top-Level `Universum/` macht das Repo-Root unübersichtlich; künftige `Watchlist/`,
  `Portfolio/`, `_runs/` werden alle Geschwister von `app/` und `tests/`
- Für Phase 2 (Cloud Run): `output/` mappt sauber auf einen GCS-Bucket-Prefix —
  kein Umbau des Output-Layers

**Konsequenz / Nebenwirkung:**
- `CLAUDE.md` Zeile 388 (Tabelle „Output-Dateinamen-Konventionen") muss von
  `Universum/YYYY-MM-Dimensions.md` auf `output/Universum/YYYY-MM-Dimensions.md` korrigiert
  werden. Dasselbe für `Portfolio/` und `Watchlist/`-Zeilen.
- Konsistent mit Phase-1-Master-Brainstorm Decision D (war dort schon korrekt).

### B) Drei Output-Files pro Monatslauf

**Entscheidung:** Jeder Monatslauf produziert genau drei Files:

```
output/Universum/
  YYYY-MM-Dimensions.md   ← die Datenbank-Sicht (alle ~400)
  YYYY-MM-Crosshits.md    ← die natürliche Watchlist-Aufmerksamkeit
  YYYY-MM-Changes.md      ← der Einstieg: was hat sich verändert
```

**Funktion jedes Files:**

- **Dimensions.md** — V3-konform: fünf Dimensions-Listen + Querliste. Alle Ticker,
  die durch die Negativfilter gekommen sind, mit Pro-Dimension-Ranking.
- **Crosshits.md** — Ticker, die in ≥2 Dimensionen Score-Schwelle ≥4 erreichen.
  Ersetzt funktional einen Composite-Score, ohne dessen ideologische Probleme
  (Fisher-Prinzipien sind nicht stetig aggregierbar). Crosshits sind die
  natürliche Schnittmenge — wenn ein Ticker in „Management" UND „Margin" UND
  „R&D" hoch scort, ist das ein stärkeres Signal als ein gemittelter Composite.
- **Changes.md** — Push-Layer. Was ist neu in Top-50, was ist rausgefallen, größte
  Score-Sprünge vs. Vormonat. Der eigentliche Einstiegspunkt für die monatliche
  Review-Routine.

**Reihenfolge der Aufmerksamkeit:** Changes → Crosshits → Dimensions.
Stephan beginnt mit Changes (5 Min Skim), wechselt zu Crosshits für Watchlist-Pflege,
springt nach Dimensions nur bei konkreten Rückfragen.

### C) Ranking pro Dimension: Score-Schwelle + Cap

**Entscheidung:** Pro Dimension werden alle Ticker mit Gemini-Score ≥4 (auf 1–5-Skala)
gelistet, gecappt auf 50.

**Begründung:**
- Score-Schwelle ist Fisher-konform: Gemini scort ordinal, „≥4" ist eine
  inhaltliche Aussage, nicht ein arbiträrer Ranglisten-Cut
- Variable Listenlänge ist *informativ*: Wenn „Management Integrity" 12 Ticker hat
  und „Margin Profile" 50, weißt du sofort, wo das Universum dünn ist
- Cap auf 50 schützt vor Ausreißer-Monaten mit ungewöhnlich vielen Top-Scores

**Abgelehnte Alternativen:**

| Variante | Abgelehnt weil |
|----------|----------------|
| Feste Zahl (Top-50) | Künstlicher Cut wenn 200 Ticker fast gleichauf liegen, oder zu lange Liste wenn nur 30 sinnvoll scoren |
| Top-Quartil | 25% von 400 = 100 — zu viele für eine „Top-Liste" |
| Score-Schwelle ohne Cap | Risiko: Ausreißer-Monat mit 150 Tickern auf Score 4–5 |

### D) Crosshits-Definition

**Entscheidung:** Crosshits = Ticker, die in **≥2 Dimensionen** Score-Schwelle ≥4 erreichen.

Die Crosshits-Tabelle zeigt pro Ticker:
- Ticker, Name, GICS-Sektor
- Anzahl Crosshits (2–5)
- Welche Dimensionen — als Spalten- oder Tag-Liste
- Gesamt-Crosshit-Rang (sortiert nach Anzahl Crosshits, dann Durchschnitts-Score)

**Erwartete Größe:** 5–30 Ticker pro Monat. Wenn Crosshits >50 wird, ist die
Schwelle ≥4 zu locker und muss neu evaluiert werden (kommt in „Offene Punkte").

### E) Snapshot-Persistenz: keine — Markdown ist Snapshot

**Entscheidung:** Pro Run werden in Firestore nur Metadaten persistiert
(`dev_screener_runs.RunRecord`), keine vollständigen `ScreenerRecord`-Snapshots.

Die generierten Markdown-Files in `output/Universum/` sind das Audit-Trail.
Sie werden via Git versioniert und über GitHub-Push (Phase 1.4) an Obsidian Git Plugin
geliefert.

**Begründung:**
1. **Markdown ist der Snapshot.** Vollständig, versioniert, lesbar. Firestore wäre
   Redundanz.
2. **Schreibkosten.** ~400 Records × alle Felder × monatlich = spürbarer Firestore-Write-Cost
   bei einem persönlichen Tool mit Free-Tier-Mindset.
3. **Kein Anwendungsfall.** FisherScreen hat explizit „Kein Backtesting" (CLAUDE.md
   Zeile 431). Soll-Ist-Vergleich läuft über `RunRecord.tickers_processed` +
   `estimated_cost_usd` — mehr ist nicht erforderlich.

**Aktueller Firestore-Stand bestätigt das Design:**

| Collection | Schlüssel | Zweck |
|---|---|---|
| `dev_screener_runs` | run_id (ISO-Timestamp) | Kosten-Tracking |
| `dev_gemini_scores` | ticker | Letzter Score pro Ticker, 30d TTL |
| `dev_ticker_cache` | ticker | Letztes yfinance-Snapshot, 24h TTL |
| `dev_edgar_cache` | cik | EDGAR-Signale, 7d TTL |

Per-Ticker-Daten werden überschrieben, kein History-Stack. Bewusste Entscheidung.

### F) Changes-Generator liest YAML-Frontmatter des Vormonats

**Entscheidung:** `Changes.md` wird durch Diff zwischen aktuellem In-Memory-Run-Ergebnis
und YAML-Frontmatter der Vormonats-`Dimensions.md` erzeugt.

**Frontmatter-Format in `YYYY-MM-Dimensions.md`:**

```yaml
---
run_id: 2026-05-13T08:00:00Z
generated_at: 2026-05-13T08:42:15Z
universum_size: 412
score_threshold: 4
cap_per_dimension: 50
dimensions:
  management_quality:
    qualifying_count: 23
    tickers: [AAPL, MSFT, NVDA, ...]
  margin_profile:
    qualifying_count: 47
    tickers: [...]
  rd_efficiency:
    qualifying_count: 18
    tickers: [...]
  # ... fünf insgesamt
crosshits:
  - ticker: AAPL
    dimensions: [management_quality, margin_profile, rd_efficiency]
    avg_score: 4.7
  - ticker: MSFT
    dimensions: [management_quality, margin_profile]
    avg_score: 4.5
---

# Universum 2026-05 — Dimensions

## Management Quality (n=23)
...
```

**Begründung der Frontmatter-Variante:**

| Variante | Trade-off | Entscheidung |
|---|---|---|
| YAML-Frontmatter | Maschinen-lesbar + Mensch-lesbar in einer Datei; Obsidian rendert Frontmatter sauber | ✅ |
| Markdown-Tabellen parsen | Funktioniert, aber fragil bei Format-Änderungen | abgelehnt |
| Sidecar JSON | Redundant — zwei Snapshots pro Monat | abgelehnt |

**Implementierungs-Hinweis:** Library `python-frontmatter` oder PyYAML auf den Header.
Der Changes-Generator liest *nur* den Frontmatter, nie den Body — Body ist Mensch-Sicht.

### G) Edge Cases für Changes.md

**G.1 Erster Run / kein Vormonat vorhanden**

Datei wird trotzdem generiert, mit Inhalt:

```markdown
# Changes 2026-05

> Erster verfügbarer Run. Keine Vergleichsbasis vorhanden.
> Alle 412 Ticker sind neu im Universum.
```

Begründung: Einheitliches File-Set pro Monat (immer drei Files) ist test-freundlicher
und dokumentiert klar, dass die Pipeline lief.

**G.2 Lücken in der Historie (z.B. nach Budget-Stop)**

Changes-Generator diffed gegen das **alphabetisch jüngste** `YYYY-MM-Dimensions.md`
in `output/Universum/`, das vor dem aktuellen Run-Datum liegt — nicht stur gegen
„aktueller Monat minus 1".

Beispiel: Wenn April-Run wegen Budget-Stop ausfiel, diffed Mai gegen März.
Das Changes.md vermerkt das transparent im Header: „Vergleichsbasis: 2026-03-Dimensions.md
(April-Run nicht verfügbar)."

---

## Architektur-Hinweise (keine offenen Fragen, nur Notizen für die Implementierung)

### Dimensions-Konstante zentral halten

Die fünf Dimensionsnamen kommen aus einer zentralen Konstante, nicht hardcoded im
Markdown-Generator. Vorschlag: `app/screener/dimensions.py`:

```python
from typing import Final

DIMENSIONS: Final[tuple[str, ...]] = (
    "management_quality",
    "margin_profile",
    "rd_efficiency",
    "growth_runway",
    "competitive_position",
)
```

Begründung: Umbenennen, Ergänzen oder Streichen einer Dimension darf nicht
ein Refactoring quer durch den Markdown-Generator erfordern. Die Frontmatter-Keys
in `Dimensions.md` ziehen sich aus dieser Konstante.

> **Hinweis:** Die konkreten Dimensionsnamen oben sind ein **Platzhalter-Vorschlag**
> auf Basis der V3-Architektur. Die finalen Namen sind noch nicht fixiert und werden
> in der writing-plans-Session der Phase 1.4 (oder ggf. in einer separaten kleinen
> Brainstorm-Session) festgelegt. Bis dahin: Der Markdown-Generator referenziert
> stets `DIMENSIONS` aus der Konstante.

### Drei Generatoren statt einem

Implementierungsvorschlag für `app/output/`:

| Modul | Verantwortlich für |
|---|---|
| `dimensions_generator.py` | `YYYY-MM-Dimensions.md` inkl. YAML-Frontmatter |
| `crosshits_generator.py` | `YYYY-MM-Crosshits.md` |
| `changes_generator.py` | `YYYY-MM-Changes.md` (liest Vormonats-Frontmatter) |

Composition Root in `app/screener/compose.py`: `build_output_pipeline()`.

Drei kleine fokussierte Generatoren statt eines großen — leichter testbar, klarere
Verantwortlichkeit. Jeder Generator hat eine einzige öffentliche Funktion:
`generate(run_records: list[ScreenerRecord], run_record: RunRecord, output_dir: Path) -> Path`.

---

## Risiko-Mapping

| Risiko | W'keit | Impact | Mitigation |
|--------|--------|--------|-----------|
| Frontmatter-Parsing scheitert (Format-Drift) | Niedrig | Mittel | Schema-Test in `tests/output/test_frontmatter_schema.py`; bei Parse-Fehler `FisherScreenError` — Changes.md fällt sauber auf „kein Vormonat verfügbar" zurück |
| Crosshits-Liste leer (Universum zu klein nach Filter) | Mittel | Niedrig | Datei wird trotzdem erzeugt mit Hinweistext, einheitliches File-Set bleibt |
| Schwelle ≥4 zu locker → 150 Crosshits | Niedrig | Niedrig | Nach erstem Lauf evaluieren; ggf. auf ≥4.5 erhöhen oder zusätzlichen Cap einführen |
| YAML im Frontmatter zu groß (5000+ Ticker-IDs) | Niedrig | Niedrig | Nicht erwartet bei ~400 nach Filter; falls Phase 2 das Universum auf 5000 erweitert: dann re-evaluieren |
| Vormonats-File existiert aber ist korrupt | Niedrig | Niedrig | `FisherScreenError` → Fallback auf nächst-älteres File |

---

## Was Phase 1.4 NICHT enthält

- **Kein Per-Ticker-File.** Ein `output/Universum/AAPL.md` gibt es bewusst nicht.
  Ticker-Detail-Sicht ist Sache von Tool B (Deep Dive, Phase 2+).
- **Kein Composite-Score.** V3-Entscheidung bleibt — Crosshits ersetzen die
  funktionale Rolle eines Composite ohne dessen ideologische Probleme.
- **Kein Watchlist-Management.** `output/Watchlist/` ist Phase 2 / Tool B Trigger.
- **Kein History-Visualisierung.** Trend-Plots o.ä. = Phase 3+, wenn überhaupt.

---

## Updates an bestehenden Dokumenten

Aus diesem Brainstorm folgt:

1. **`CLAUDE.md`** — Zeile 388 (Tabelle „Output-Dateinamen-Konventionen") korrigieren:
   `Universum/YYYY-MM-Dimensions.md` → `output/Universum/YYYY-MM-Dimensions.md`.
   Analog für `Portfolio/` und `Watchlist/`-Einträge.

2. **`PROJEKTSTAND.md`** — Abschnitt „Nächste Session / Phase-1.4-Scope" ersetzen
   durch die hier definierte Struktur. Output-Pfad-Konflikt aus „Offene Punkte"
   streichen (durch Punkt 1 oben aufgelöst).

3. **`docs/superpowers/brainstorm/2026-05-11-phase-1-structure.md`** — Phase-1.4-Block
   bleibt als historische Ursprungsannahme, aber bekommt eine Notiz am Anfang:
   *„Phase-1.4-Scope wurde am 2026-05-15 präzisiert. Siehe
   `2026-05-15-phase-1-4-output-structure.md`."*

---

## Nächster Schritt: writing-plans-Session Phase 1.4

Mit diesem Brainstorm als Grundlage kann die writing-plans-Session den
Implementations-Plan schreiben. Empfohlene Eckpunkte für den Plan:

- Feature-Branch: `feature/phase-1-4-markdown-output`
- Plan-Datei: `docs/superpowers/plans/2026-05-XX-phase-1-4-markdown-output.md`
- Lies vorab: dieses Brainstorm-Doc + `PROJEKTSTAND.md` + `CLAUDE.md`
- Sub-Phasen vorschlagen: (a) Dimensions-Generator + Frontmatter, (b) Crosshits-Generator,
  (c) Changes-Generator + Vormonats-Diff-Logik, (d) GitHub-Push, (e) Cloud Run Deploy
- Vor (d): Output-Pfad-Korrektur in CLAUDE.md committen
