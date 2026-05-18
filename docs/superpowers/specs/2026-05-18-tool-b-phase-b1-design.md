# Tool B (Deep Dive) — Phase B.1: Design-Spec

**Datum:** 2026-05-18
**Status:** Design-Spec, brainstorm-validiert. Terminiert in einer `writing-plans`-Session.
**Vorlauf:** Master-Brainstorm `docs/superpowers/brainstorm/2026-05-18-tool-b-master.md` (rev4).
**Referenz-Spec:** `D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\FisherScreen_Architektur_v3.md`
(insb. §5 Tool B, §5.3 Dossier-Struktur, §14 Fishers 15 Punkte).
**Bezug:** Diese Spec setzt die ADRs 1–4 des Master-Brainstorms als gesetzten Rahmen
voraus und ergänzt **ADR-5** (Mehrjahres-Quant). Sie schärft die in Master §5.1 als
*„offene Feinheiten, in der B.1-Brainstorm-Session zu schärfen"* markierten Punkte.

> **Reihenfolge:** Diese Spec → eigene kurze `B.0`-Plan-Session (Gerüst, ohne
> Brainstorm) → `B.1`-Plan-Session → B.1-TDD pro Task → B.1-Akzeptanz-Skript.

---

## 1. Zweck & Scope von B.1

B.1 ist der **vertikale Durchstich** von Tool B: aus **einem** CLI-Aufruf ein
vollständiges, entscheidungs-nützliches Markdown-Dossier zu **einem** Ticker
(MVP-Kandidat Novo Nordisk, `NOVO-B.CO`), gemessen an Fishers 15 Punkten.

**Nur trusted sources** (reguliertes Emittenten-Filing 10-K/20-F + yfinance-Quant).
Keine Subagent-Isolation (Master Grundsatz §2.8 — durch *untrusted* Inputs motiviert,
die erst B.3 einführt). Aufruf vollständig **lokal in-process** (ADR-2).

**Akzeptanztest (Exit-Kriterium):**

> Ein einziger `uv run python -m app.deepdive deepdive NOVO-B.CO` erzeugt
> `output/Watchlist/NOVO-B.CO_2026-05-XX.md`. Stephan liest das Dossier und sagt
> entweder *„das ist entscheidungs-nützlich"* oder *„Synthesis/Struktur muss anders"*.
> Erst danach wird auf weitere Ticker skaliert (B.2).

---

## 2. Gefällte Entscheidungen (die §5.1-Feinheiten)

Brainstorm-Konsens 2026-05-18. Diese Entscheidungen sind für B.1 gesetzt.

### E1 — Filing-Parser: Hybrid HTML→Text + Anker-Regex + Flag

EDGAR-Primärdokumente (10-K/20-F) sind großes HTML mit inline XBRL, ohne
einheitliches Schema über Filer hinweg. DOM-aware-Parsing wäre überspezifiziert
(pro Filer eigene Strategie); reine Regex auf Roh-HTML scheitert an Tags
(`<b>Item 4</b>`, `&nbsp;`).

- **Konvertierung:** `html2text` (leichtgewichtig, deterministisch, strukturerhaltend).
  Fallback `BeautifulSoup.get_text()`. **Nicht** `unstructured` (zu schwergewichtig,
  viele transitive Deps).
- **Anker-Regex:** case-insensitive, Toleranz für `Item 4.` / `ITEM 4` / `Item 4 —` /
  `Item 4:`. Zwei Anker-Listen, Form-Type-Weiche (ADR-1):
  - **10-K:** Items 1, 1A, 7, 7A, 8
  - **20-F:** Items 4, 5, 18
- **Section-Slice:** Text zwischen Anker N und Anker N+1.
- **Längen-Cap als Token-Hebel (Pre-Stage-5):** überschreitet eine extrahierte
  Section das Token-Budget `FISHERSCREEN_DEEPDIVE_SECTION_TOKEN_CAP` (Default
  `50000` — eine 20-F-Item-5-Section liegt realistisch bei 10k–40k Tokens; 50k
  gibt Puffer, ohne den 200k-Gesamt-Cap zu sprengen, selbst bei 3–4 Sections im
  Prompt), wird sie mit Marker `[... section truncated for token budget]`
  abgeschnitten. **Stage 3 darf nicht annehmen, dass „extrahiert = klein genug"
  ist** — das ist der eigentliche Kosten-Hebel gegen Premortem #1. Geschwister-Cap
  zu `FISHERSCREEN_DEEPDIVE_TOKEN_CAP` (E2, Gesamt-Call): der Section-Cap sorgt
  dafür, dass der Gesamt-Cap verlässlich greift.
- **Fail loud:** fehlender Anker → `section_missing`-Flag im `DeepDiveRecord`, **kein
  stilles Leerfeld, kein Crash** (Premortem #2).

DOM-aware bleibt isolierter B.2-Refactor, falls Section-Missing-Flags häufig werden.

### E2 — Synthesis: ein kombinierter `gemini-2.5-pro`-Call

Fishers Punkte sind nicht orthogonal (5↔6, 14↔15) — ganzheitliches Reasoning über
Punkte hinweg ist nötig. Gruppierte/Punkt-für-Punkt-Calls lösen das Token-Problem
nicht (Cluster brauchen denselben Section-Kontext) und addieren Komplexität.

- **Prompt-Struktur:** System-Prompt (Fisher-15-Methodik + Quellen-Marker-Regeln +
  JSON-Schema-Erklärung) + User-Prompt (Filing-Sections als strukturiertes Dict +
  Quant-Snapshot als JSON).
- **Strukturierte Ausgabe (Amendment 2026-05-18, Option A):** Gemini liefert JSON
  via `response_mime_type="application/json"` + Schema-Erklärung im System-Prompt;
  die Vertrags-**Durchsetzung** erfolgt **post-parse** durch zwei unabhängige
  Schichten — (1) Task-B.1-1 `FisherPoint`-Pydantic-Validierung (`extra="forbid"`,
  Rating-Range, Confidence-Literal, 70-Wörter-Cap, Inferenz→🟡-Cap, 15-Punkte-Count)
  und (2) den Post-Hoc-Quellen-Validator. **Ursprünglich** verlangte E2 zusätzlich
  Gemini `response_schema` (Pydantic aus B.1-1). Das wurde verworfen, weil
  `google-genai` `response_schema` Emoji-`Literal`-Enums (`🟢/🟡/🔴`) und
  `model_validator`/`field_validator` nicht sauber abbildet — ein eigenes flaches
  Wire-Modell + Mapping wäre nötig, mit google-genai-Risiko auf dem
  B.1-Akzeptanzpfad, ohne Mehrwert (die zwei Validierungs-Schichten erzwingen den
  Vertrag bereits strukturell, nicht „nur per Prompt"). **`response_schema` ist
  nach B.2 verschoben** (eigenes stabiles Wire-Modell, wenn das Schema fix ist).
- **Token-Cap:** `count_tokens` vor dem Call (Tool-A-Pattern); Hard-Cap
  `FISHERSCREEN_DEEPDIVE_TOKEN_CAP` (Default `200000`; `gemini-2.5-pro` hat 1M-Kontext,
  200k ist großzügiger Sicherheits-Cap); `logging.warning` bei 80 % (160k);
  Überschreitung → sofort `GeminiError`, **kein Retry**.
- **Retry:** Tool-A-Wrapper wiederverwenden (tenacity, 1s/4s/16s, max 4,
  `reraise=True`, retry nur bei 503/429 — `app/services/gemini_client.py`).
- **Modell:** Default `gemini-2.5-pro` (Pre-Flight §7a bestätigt); Override via
  `FISHERSCREEN_DEEPDIVE_GEMINI_MODEL` (modell-agnostisch).
- **Post-Hoc-Quellen-Validator** (Master Task B.1-6, Premortem #2a): Regex auf im
  `reasoning` zitierte Sections (`20-F §X` / `10-K §X`), Abgleich gegen die tatsächlich
  gesendeten Section-Keys; Mismatch → Source-Marker auf `['Inferenz']` herabstufen +
  Confidence-Cap 🟡 + WARNING (kein Hard-Fail — Halluzination ist erwartbarer Modus).

### E3 — CLI: `argparse` (stdlib)

CLAUDE.md: keine neue Abhängigkeit ohne Diskussion. Tool B hat genau einen Befehl mit
einem Argument; `typer`+`click` wäre Overkill. Bei späterem HTTP-Endpoint (B.5+) wird
der CLI-Entrypoint Thin-Wrapper über dieselbe Composition-Root — Framework-Wechsel
trivial bei sauberem Service-Layer (Master §2.1).

- **Entrypoint:** `app/deepdive/__main__.py`, `argparse` mit `add_subparsers()` von
  Anfang an (`deepdive`-Subcommand), damit spätere Befehle ohne Refactor dazukommen.
- **`pyproject.toml`:** `[project.scripts] fisherscreen = "app.deepdive.__main__:main"`.
- **Argumente B.1:** `TICKER` (positional, required), `--model` (optional, überschreibt
  Env-Var), `--no-cache` (optional, ignoriert Filing- und Mehrjahres-Cache).
- **Exit-Codes:** `0` Erfolg · `1` `DeepDiveError` (Ticker nicht auflösbar) ·
  `2` `DataSourceError` (EDGAR/Firestore/yfinance) · `3` `GeminiError`
  (Token-Cap, Safety-Filter).
- **Aufrufform lokal:** `uv run python -m app.deepdive deepdive <TICKER>` wegen
  SOPRA-EPDR-Blocker für `.exe`-Shims (siehe CLAUDE.md). Die
  `[project.scripts]`-Deklaration bleibt für CI/Container ohne EPDR.

### E4 — B.0 = separate kurze Plan-Session zuerst

Master §10 ist explizit (rev1-Korrektur 5): B.0 ist klein genug für eine reine
Plan-Session ohne Brainstorm; B.1 startet mit fertigem Gerüst und fokussiert seinen
Akzeptanztest auf **Synthesis-Qualität**, nicht Infra-Setup. Saubere Trennung der
Test-Strategien (B.0 = Unit-Tests Infra; B.1 = Akzeptanz-Skript). Diese Spec ist
**B.1-only**; B.0 bekommt seine eigene `writing-plans`-Session.

### E5 — Quant-Umfang: angereichert (live Mehrjahres-Quant) → siehe ADR-5

Der Tool-A-Cache hat strukturell keine Mehrjahres-Reihen. Fisher 1/6/13 brauchen
Trend-Signale; ADR-3 verlangt Buyback-/Verwässerungs-Proxies für 3/8/9/13. Ohne
Mehrjahres-Quant wäre ADR-3 inhaltlich leer und Punkt 6 nur ein Niveau-Datenpunkt
(Bibliothek-vs-Briefing-Fehlmodus, den Rev3 verhindern soll). Auflösung: **ADR-5**.

---

## 3. ADR-5 — Mehrjahres-Quant (B.1-lokal, gebündelt)

**Status:** gesetzt (Brainstorm 2026-05-18). ADR-5 bündelt drei Sub-Entscheidungen,
die zusammen die Antwort auf *„Wie kommt B.1 an mehrjahres-fähige Quant-Daten und
wie verarbeitet es sie?"* sind. Kein ADR-6 (hält die ADR-Liste kompakt; ADR-1…4
unberührt).

### ADR-5a — Mehrjahres-Quant kommt live aus yfinance

**Kontext.** `dev_ticker_cache` speichert nur den Punkt-in-Zeit-`info`-Dict
(`grossMargins`, `revenueGrowth`, `operatingMargins`, `returnOnEquity`,
`debtToEquity`, `marketCap`, Sektor/Industrie) + `_cached_at`, 24 h TTL.
`dev_gemini_scores` speichert nur `{dimensions, summary}`, 30 d TTL. Mehrjahres-Reihen
(Umsatz-CAGR, Margen-Slope, Shares-Outstanding-Historie) berechnet Tool A nur
transient in `run_basis_filter` und verwirft sie.

**Entscheidung.** B.1 zieht Mehrjahres-Quant **live** über einen neuen
`historical_data_service` (yfinance `financials`/`income_stmt`/`cashflow`/
`balance_sheet`), getrennt vom Punkt-in-Zeit-`yfinance_client`. Gecacht **lokal**
unter `cache/yfinance_historical/<TICKER>.json`, **ADR-4-analog**, TTL 90 Tage
(Reihen ändern sich quartalsweise), Env-Var `FISHERSCREEN_HISTORICAL_CACHE_TTL_DAYS`
(Default 90). `cache/` ist bereits in `.gitignore`.

**Cache-Format (Tool-A-konsistent):** eingebetteter Timestamp im JSON, Feldname
`_cached_at` (exakt das Pattern aus `cached_yfinance_client.py` /
`cached_gemini_client.py` — Unterstrich-Präfix), **nicht** mtime (mtime ist fragil
bei File-Sync/Backup/Cloud-Drive):

```json
{"_cached_at": "<ISO-8601>", "financial_currency": "<XYZ>", "series": { ... }}
```

TTL-Check liest `_cached_at`, nicht das Dateialter.

**Konsequenzen.**
- Konsistent mit ADR-2 (CLI-lokal) und ADR-4 (Lokal-FS-Cache statt Firestore-Roundtrip).
- Eigener Service, weil die Cache-Strategie sich vom Punkt-in-Zeit-Client unterscheidet
  (24 h vs. 90 d).
- yfinance-Mehrjahres-Calls sind weniger stabil als `info` → graceful degradation
  (siehe §8 Risiken).

### ADR-5b — `quant_snapshot` ist strukturiert (vier Sub-Felder)

**Entscheidung.** `DeepDiveRecord.quant_snapshot` ist **nicht flach**, sondern:

```
quant_snapshot:
  point_in_time:    yfinance-info-Subset (aus dev_ticker_cache oder live-Fallback)
  historical_series: rohe Mehrjahres-Reihen (aus historical_data_service)
  trend_metrics:    berechnete Metriken (aus trend_metrics.py, transient)
  gemini_dimensions: Tool-A 5-Dimensionen + summary (aus dev_gemini_scores) — Sekundär
```

**Konsequenzen.** Klare Trennung Datenherkunft ↔ Verarbeitung; jede Klasse trägt im
`source_coverage` ihren eigenen Herkunfts-/Vollständigkeits-Marker; der
Synthesis-Prompt kann pro Fisher-Punkt gezielt die passende Klasse referenzieren.

### ADR-5c — Tool-A-Gemini-Dimensions nur als `[Inferenz]`-Kontext

**Kontext.** Die fünf Tool-A-Dimensions-Scores sind selbst LLM-Inferenz (Flash Lite).
Sie im B.1-Reasoning als Primär-Evidenz zu zitieren wäre Inferenz-auf-Inferenz.

**Entscheidung.** `gemini_dimensions` darf im `reasoning` nur als **Kontext**
referenziert werden, nie als Primär-Evidenz; im Quellen-Marker-Vokabular (Rev3) sind
sie `[Inferenz]` — Confidence dort ohnehin auf 🟡 gekappt. Als Code-Regel im
System-Prompt + Post-Hoc-Validator behandelt (Dimensions-Zitat ⇒ kein 🟢).

**Fallback bei Tool-A-Cache-Miss.** Ist der Ticker **nicht** im letzten Monatslauf,
bleibt `gemini_dimensions` **leer** — **kein Live-Nachziehen** (Tool A ist ein anderer
Lauf mit anderer Logik). `source_coverage` markiert: *„Tool-A-Dimensionen nicht
verfügbar (Ticker nicht im letzten Monatslauf)"*. Verhindert einen subtilen Bug beim
ersten Nicht-Top-30-Ticker.

---

## 4. Pipeline (6 Stages)

```
[1] ADR-Lookup        TICKER → (adr_ticker, cik, form_type)
        │              statische Tabelle (ADR-1). NOVO-B.CO → NVO → 0000353278 → 20-F
        ▼
[2] EDGAR-Pull        cik + form_type → jüngstes 10-K|20-F Volltext (Filing-Cache ADR-4)
        │              edgar_client erweitern (User-Agent/Rate-Limit aus Phase 1.2)
        ▼
[3] Filing-Parse      Roh-Filing → {section_key: text}  (E1: Hybrid + Längen-Cap + Flag)
        │              10-K: 1,1A,7,7A,8 · 20-F: 4,5,18
        ▼
[4] Quant-Join        4a Punkt-in-Zeit (dev_ticker_cache; Miss → live get_ticker_info + Marker)
        │              4b Mehrjahres live (historical_data_service, lokaler 90d-Cache)
        │              4c Trend-Metriken (trend_metrics.py, transient)
        │              ── 4a → 4b SEQUENZIELL, 4c danach ──
        ▼
[5] Gemini-Synthesis  Sections + Quant → 15-Punkte-JSON (E2: 1 Call, prompt-JSON
        │              + post-parse FisherPoint-Validierung, Token-Cap,
        │              Confidence-Regel, Post-Hoc-Quellen-Validator)
        ▼
[6] Markdown-Output   15-Punkte-JSON + Quant → Dossier (Mini-Blöcke, §6)
                       output/Watchlist/<TICKER>_YYYY-MM-DD.md → Repo-Sync → Obsidian
```

**Stage 4 Reihenfolge — explizit:** `4a → 4b` **sequenziell**, `4c` danach.
Parallelisierung von 4a/4b ist in B.1 **verworfen** (asyncio/futures erhöht
DI-Test-Komplexität; bei Einzel-Ticker-Deep-Dive ist Gemini-Synthesis der
Bottleneck, nicht yfinance-Latenz — verfrühte Optimierung). → B.2-Kandidat (§9).

**Stage 4a Fallback.** Ticker nicht im letzten Tool-A-Lauf: WARNING loggen, live
`get_ticker_info` via bestehenden Service, `source_coverage` markiert
„live, nicht aus Monatslauf". Graceful degradation, nie Abbruch.

---

## 5. Datenmodell — `DeepDiveRecord`

Pydantic, `extra="forbid"`, analog `ScreenerRecord`. Felder:

| Feld | Typ | Quelle |
|---|---|---|
| `ticker` | `str` | CLI-Arg |
| `adr_ticker` | `str \| None` | ADR-Resolver (US-Passthrough → `None`) |
| `cik` | `str` | ADR-Resolver |
| `form_type` | `Literal["10-K","20-F"]` | ADR-Resolver |
| `filing_sections` | `dict[str, str]` | Filing-Parser (Key z. B. `"20-F_item5"`) |
| `section_flags` | `dict[str, str]` | Filing-Parser (`"missing"` / `"truncated"`) |
| `quant_snapshot` | `QuantSnapshot` | Stage 4 (vier Sub-Felder, ADR-5b) |
| `synthesis` | `list[FisherPoint]` (15) | Gemini-Synthesis |
| `source_coverage` | `SourceCoverage` | über alle Stages aggregiert |
| `generated_at` | `datetime` | `default_factory` UTC |

`QuantSnapshot`: `point_in_time`, `historical_series`, `trend_metrics`,
`gemini_dimensions` (optional, leer bei Cache-Miss — ADR-5c).
None-Toleranz für optionale Quant-Felder.

`FisherPoint` (pro Punkt 1–15): `{number: int, title: str, rating: int (1–5),
confidence: Literal["🟢","🟡","🔴"], reasoning: str (≤70 Wörter), sources: list[str]
(nicht leer)}`. Erzwingt den Synthesis-Vertrag **post-parse** (E2-Amendment,
Option A) — nicht als Gemini `response_schema` (nach B.2 verschoben).
Fisher-Titel aus V3 §14 (deutsch).

`SourceCoverage`: pro Quellklasse Herkunfts-/Vollständigkeits-Marker, u. a.
`quant_pit_source` (`"tool-a-cache"`/`"live-yfinance"`), `gemini_dims`
(`"present"`/`"absent (nicht im letzten Monatslauf)"`), `historical`
(`"complete"`/`"partial (<5J)"`), `currency_note` (financialCurrency ≠ Listing),
plus die ehrlichen Lücken-Marker (Soft → B.3, Sprach → B.4, Insider → B.2).

**Confidence-Regel (Code-erzwungen, nicht Soft-Konvention):** enthält `sources` nur
`['Inferenz']` (inkl. Dimensions-Referenz, ADR-5c) → Confidence max 🟡, nie 🟢.
Fisher 14/15 (Offenheit/Integrität) → 🔴 + expliziter Verweis
„Insider-Transaktionen folgen B.2, Sprach-/Tonalitäts-Analyse folgt B.4".

---

## 6. Dossier-Render-Format (Task B.1-7)

Markdown nach V3 §5.3, mit Rev3-Reasoning-Erweiterung. **15 Punkte je als eigener
Mini-Block, NICHT als Tabellenzeile:**

```
### Punkt N — <Titel>
**Bewertung:** ⭐⭐⭐⭐ · **Confidence:** 🟢

<Reasoning, 2–3 Sätze Prosa, max 70 Wörter> [Quellen-Marker]
```

Struktur: YAML-Frontmatter · `# Deep Dive: <Name> (<Ticker>)` · Executive Summary
(**3 Sätze, hart**) · Bewertung (KGV/EV-EBIT/FCF-Yield aktuell vs. 5J) · Fishers
15 Punkte (Mini-Blöcke) · **source_coverage-Sektion** (EDGAR: 20-F via ADR · Soft:
folgt B.3 · Sprach: folgt B.4 · Insider: folgt B.2 · Quant-Herkunft/-Lücken) ·
leere „Stef's Notizen". Pfad `output/Watchlist/<TICKER>_YYYY-MM-DD.md`.

---

## 7. Task-Struktur — 10 Tasks (war 9)

Jeder Task: Plan → TDD via Subagent (`backend-developer` Logik, `qa-engineer`
Fixtures/DI-Mocks; CLAUDE.md Multi-Agent). Tests via `uv run python -m pytest`.
**Kein echter Netzwerk-Call in Unit-Tests.** 90 %-Coverage zentral.

| # | Task | Kern | Testing-Strategie |
|---|---|---|---|
| **B.1-1** | `DeepDiveRecord`-Datenmodell | §5: strukturiertes `quant_snapshot` (4 Sub-Felder), `FisherPoint`, `SourceCoverage`, `extra="forbid"` | Modell-Validierung; `extra="forbid"`; None-Toleranz optionale Quant-Felder; Confidence-Regel als Validator (Inferenz-only ⇒ kein 🟢) |
| **B.1-2** | ADR-Resolver (`adr_resolver.py`) | Lädt statische YAML/JSON (ADR-1). `resolve(ticker)→(adr,cik,form_type)`. US = Passthrough (10-K) | `NOVO-B.CO`→`NVO/0000353278/20-F`; US-Passthrough; unbekannt → `DeepDiveError` mit handlungsleitender Message; DI-mockbar; Tabellen-Format-Test |
| **B.1-3** | Filing-Fetcher (`edgar_client`+) | Neue Methode `get_latest_annual_filing(cik, form_type)` — Volltext-Dokument. User-Agent/Rate-Limit aus Phase 1.2. Filing-Cache ADR-4 | Gemockte EDGAR-Responses 10-K **und** 20-F; fehlendes Filing → `DataSourceError`; Cache-Hit/Miss |
| **B.1-4** | Filing-Parser | E1: `html2text`→Anker-Regex→Section-Slice. Form-Type-Weiche. Längen-Cap mit Truncation-Marker. Fehlende Section → Flag | Fixture-10-K + Fixture-20-F → erwartete Keys; fehlende Section → geflaggt, kein Crash; Truncation-Marker bei Über-Cap; TOC-Fehltreffer-Fixture |
| **B.1-5** | Quant-Join | 4a Punkt-in-Zeit (`dev_ticker_cache`; Miss → live + Marker) **+ 4b** Mehrjahres live via neuem `historical_data_service` + lokalem 90d-Cache (ADR-5a, `_cached_at`-Format) | Cache-vorhanden; Ticker-abwesend → Fallback; Firestore via DI; Mehrjahres leer/partiell (≥3J ok, sonst Flag); Währungs-Marker (Novo DKK vs. USD); Cache-TTL via `_cached_at` |
| **B.1-5a** | Trend-Metriken (`trend_metrics.py`) | **Reine Funktionen, keine externen Calls:** `compute_cagr`, `compute_margin_slope` (lin. Regression), `compute_dilution_pct`, `compute_buyback_intensity` (vs. Marktkap.) | Pure-Function-Tests; bekannte Reihen → bekannte Ergebnisse; Edge: <3J, Nullen, negative Werte, leere Reihe; keine DI nötig |
| **B.1-6** | Gemini-15-Punkte-Synthesis | E2: 1 Call, System+User-Prompt, prompt-JSON + post-parse `FisherPoint`-Validierung (E2-Amendment Option A; `response_schema` → B.2), `count_tokens`, Token-Cap, Tool-A-Retry, Modell-Env. Post-Hoc-Quellen-Validator. ADR-5c + 14/15→🔴 code-erzwungen | Gemini gemockt; Cap überschritten → `GeminiError`; Schema-Validierung (15 Punkte, `extra='forbid'`, Reasoning ≤70 W., `sources` nicht leer); Inferenz-only → 🟡-Downgrade; halluzinierte Section (`Item 99`) → `['Inferenz']`-Downgrade + WARNING; safety-filtered (ValueError-Pfad wie Phase 1.4) |
| **B.1-7** | Dossier-Generator | §6: Mini-Blöcke (NICHT Tabelle), Exec ≤3 Sätze hart, source_coverage-Sektion, leere Notizen, YAML-Frontmatter, Pfad-Konvention | Golden-File mit 15 Mini-Blöcken; Längen-Budgets erzwungen (Test bricht bei Über-Cap); Frontmatter-Schema; jeder Punkt rendert ≥1 Quellen-Marker am Reasoning-Ende |
| **B.1-8** | CLI-Entrypoint + Composition Root | E3: `argparse` + `add_subparsers()`, `app/deepdive/__main__.py`, `[project.scripts]` (lokale Aufrufform `python -m app.deepdive` — siehe E3), Args `TICKER/--model/--no-cache`, compose-Analog (Service-Verdrahtung) | Arg-Parsing; End-to-End mit allen Services gemockt → Dossier in tmp; Exit-Codes 0/1/2/3 |
| **B.1-9** | Akzeptanz-Skript (manuell) | `scripts/acceptance_deepdive.py` — echter Lauf `uv run python -m app.deepdive deepdive NOVO-B.CO` gegen reales EDGAR + Firestore-Read + live yfinance + Gemini. Analog `scripts/acceptance_basis_filter.py` | **Kein** Unit-Test: dokumentiertes manuelles Gate. Stephan liest das Dossier und urteilt |

---

## 8. Risiko-Mapping (B.1-Ergänzungen)

Master §8 Risiken 1–8 (inkl. #2a) gelten unverändert. Ergänzungen aus ADR-5:

| # | Risiko | W'keit | Impact | Gegenmittel |
|---|---|---|---|---|
| 9 | yfinance-Mehrjahres-Calls instabil (leere/partielle DataFrames, nur 4J statt 5J, ADR-Übergangsphase) | Hoch | Mittel | `historical_data_service` graceful: ≥3J → ok, sonst `source_coverage`-Flag; nie Abbruch; Fixtures für leer + partiell |
| 10 | Währungs-Mismatch: `financialCurrency` ≠ Listing-Währung (Novo: DKK vs. USD) | Hoch | Mittel | `financial_currency` explizit im Cache-Payload + Quant-Snapshot; `currency_note` in `source_coverage`; Test-Fixtures Novo (DKK) + US-Ticker (USD) |
| 11 | Inferenz-auf-Inferenz: Tool-A-Dimensions als Primär-Evidenz zitiert | Mittel | Mittel | ADR-5c: System-Prompt-Regel + Post-Hoc-Validator (Dimensions-Zitat ⇒ kein 🟢) |

---

## 9. Offene Fragen (bewusst nach B.1 verschoben)

1. **Parallelisierung Stage 4a/4b** — in B.1 verworfen (DI-Test-Komplexität,
   yfinance nicht der Bottleneck). B.2-Kandidat, falls Latenz real stört.
2. **DOM-aware Filing-Parser** — B.2-Refactor, falls Section-Missing-Flags häufig.
3. Master §7 Punkte (EU-Voll-Abdeckung B.2, Transkript-Quelle B.4b, Tool-A→B
   Hand-off) bleiben offen — eigene künftige Brainstorm-Runden.

---

## 10. Nicht-Ziele B.1 (Recap Master §9)

Soft Scuttlebutt (B.3) · Subagent-Isolation (B.3) · Sprach-/Tonalitätsanalyse (B.4) ·
Insider-Transaktionen (B.2) · reine EU-Titel ohne US-ADR (B.2) · HTTP-Endpoint/Cloud
Run (B.5+) · dynamische ADR-Resolution (B.2) · 10-Q (B.2) · Multi-Ticker-Batch (nie,
V3 Prinzip 7) · Composite-Score (V3-Entscheidung) · Portfolio-Hold-Check (Tool A) ·
Parallelisierung Stage 4 (§9).

---

## 11. Nächster Schritt

Diese Spec terminiert. Reihenfolge:

1. **Spec-Review durch Stephan** (Review-Gate vor Plan).
2. **B.0-Plan-Session** (`writing-plans`, ohne Brainstorm — Master liefert
   Festlegung): CLI-Package-Skeleton, `output/Watchlist/`-Junction + GitHub-Push-Pfad,
   statische ADR-Tabelle (Seed: NOVO-Eintrag), `DeepDiveError`-Klasse,
   `compose.py`-Analog.
3. **B.1-Plan-Session** (`writing-plans`): die 10 Tasks aus §7.
4. B.1-TDD pro Task → B.1-9 Akzeptanz-Skript → Stephan-Urteil.

---

*Ende der Spec.*
