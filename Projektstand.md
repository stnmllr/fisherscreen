# FisherScreen — Projektstand

> **Single Source of Truth für den aktuellen Stand.**
> Wird am Ende jeder Arbeitssession aktualisiert.
> Verwandte Dokumente: `D:\programme\stef-vault\10_Projekte\FisherScreen\FisherScreen_Architektur_v3.md` (Architektur, extern),
> `docs/superpowers/brainstorm/` (Architektur-Entscheidungen),
> `docs/superpowers/plans/` (ausgeführte Implementations-Pläne).

---

## Letztes Update: 2026-05-15

## Status

**Aktueller Phase**: Phases 1.1, 1.2 und 1.3 vollständig implementiert und auf `main` gemergt.
**Branch**: `main` — 172 Tests, 97.9% Coverage.
**Nächste Phase**: 1.4 (Markdown-Output + GitHub-Push + Cloud Run Deploy) — Scope am 2026-05-15 präzisiert.

## Erledigt

- 2026-05-10: Repo-Setup (10 Tasks, 23 Tests)
- 2026-05-11: Phase-1-Master-Brainstorm
- 2026-05-12: **Phase 1.1** Data Pipeline + Basisfilter — `main`
- 2026-05-13: **Phase 1.2** EDGAR-Signale — `main`
- 2026-05-13: **Phase 1.3** Gemini Scoring — `main`
- 2026-05-15: **Phase-1.4-Output-Struktur-Brainstorm** — `docs/superpowers/brainstorm/2026-05-15-phase-1-4-output-structure.md`
- 2026-05-15: **Phase-1.4-Implementierungsplan** — `docs/superpowers/plans/2026-05-15-phase-1-4-markdown-output.md`

### Phase-1.2-Details (2026-05-13)

| Datei | Was |
|---|---|
| `app/services/edgar_client.py` | `EdgarClientImpl`: `has_restatement` (submissions.json → 8-K Item 4.02), `has_going_concern` (EFTS Full-Text), `has_active_enforcement` Stub |
| `app/services/cached_edgar_client.py` | 7-Tage-TTL-Cache in `dev_edgar_cache` |
| `app/screener/filters.py` | `apply_edgar_filters()` ergänzt |
| `app/screener/runner.py` | `run_edgar_filter()` — läuft nur auf Phase-1.1-Restmenge |
| `app/screener/compose.py` | `build_edgar_pipeline()` Composition Root |
| `app/config.py` | `edgar_collection`-Setting |

### Phase-1.3-Details (2026-05-13)

| Datei | Was |
|---|---|
| `app/services/gemini_client.py` | `GeminiClientImpl`: Token-Counting vor API-Call, strukturiertes JSON-Output, `GeminiError`-Wrapping; `GeminiScoreResult` Dataclass |
| `app/services/cached_gemini_client.py` | 30-Tage-TTL-Cache in `dev_gemini_scores` |
| `app/models/run_record.py` | `RunRecord` Pydantic-Modell mit `compute_cost()` |
| `app/screener/run_tracker.py` | Token-Akkumulation, `finish()` schreibt in `dev_screener_runs` |
| `app/screener/scorer.py` | `run_gemini_scoring()`: 3.000-Ticker Hard-Cap, per-Ticker `GeminiError`-Guard, Run-Level Token-Budget (80% Warning + Hard Stop bei 500k) |
| `app/screener/compose.py` | `build_gemini_pipeline()`, `build_run_tracker()` |
| `app/config.py` | `gemini_api_key`, `gemini_score_collection`, `screener_runs_collection` |
| `infra/budget_stop.py` | Cloud Function: pausiert Cloud Scheduler wenn $10/Monat überschritten |
| `infra/requirements.txt` | `google-cloud-scheduler` Dependency für Cloud Function |
| `docs/infra/budget-alerts.md` | Setup-Doku für GCP Budget Alerts ($5 E-Mail, $10 Hard Stop) |

**Qualitäts-Korrekturen durch Code-Review (nicht im Plan):**
- `GeminiClientImpl._parse_response`: `ValueError` in except-Tuple ergänzt (safety-filtered responses)
- `RunTracker.finish()`: delegiert zu `RunRecord.compute_cost()` statt Formel duplizieren
- `RunTracker`: `Literal["success","partial","aborted"]`-Typ, `_finished`-Guard gegen Doppelaufruf
- Alle `build_*()` geben Protocol-Typen zurück, nicht konkrete Klassen
- `spec=True` auf Pydantic-Settings-Mock (16 harmlose Pydantic-v2-Deprecation-Warnings — bekannt)
- `budget_stop.py`: `os.environ.get()` statt `[]` (kein KeyError beim Cold Start), `GoogleAPICallError`-Catch

## Nächste Session

**Ziel**: Phase 1.4 implementieren — Markdown-Output + GitHub-Push + Cloud Run Deploy
**Plan**: `docs/superpowers/plans/2026-05-15-phase-1-4-markdown-output.md`

**Pflicht-Lektüre vorab für Claude Code:**
- `docs/superpowers/brainstorm/2026-05-15-phase-1-4-output-structure.md` (Langfassung der Entscheidungen)
- `docs/superpowers/brainstorm/2026-05-11-phase-1-structure.md` (Phase-1-Master)
- `CLAUDE.md`

**Vorbereitung vorab:**
- [ ] Firestore-API im Projekt `fisherscreen-prod` aktivieren (GCP Console → APIs)
- [ ] `.env` mit `FISHERSCREEN_GCP_PROJECT_ID=fisherscreen-prod` und `FISHERSCREEN_GEMINI_API_KEY` befüllen
- [ ] `CLAUDE.md` Zeile 388 (Output-Dateinamen-Tabelle) auf `output/Universum/` etc. korrigieren — eigener kleiner Commit vor 1.4-Implementierung

**Phase-1.4-Scope (präzisiert 2026-05-15):**

Pro Monatslauf werden **drei** Markdown-Files erzeugt, nicht ein File pro Ticker:

| File | Inhalt | Funktion |
|---|---|---|
| `output/Universum/YYYY-MM-Dimensions.md` | Fünf Dimensions-Listen + Querliste, YAML-Frontmatter mit maschinen-lesbarer Sicht | Datenbank-Sicht (~400 Ticker) |
| `output/Universum/YYYY-MM-Crosshits.md` | Ticker in ≥2 Dimensionen mit Score ≥4 | Natürliche Watchlist-Aufmerksamkeit |
| `output/Universum/YYYY-MM-Changes.md` | Diff vs. Vormonat: neu/raus aus Top-50, größte Score-Sprünge | Push-Layer / Einstiegspunkt |

**Ranking-Logik pro Dimension:**
- Score-Schwelle ≥4 als Primärfilter
- Cap auf 50 als Sekundärfilter
- Variable Listenlänge ist informativ (zeigt wo das Universum dünn ist)

**Snapshot-Persistenz:** Keine. Markdown ist der Snapshot, Firestore nur Cache + Cost-Log.
Bewusste Entscheidung — siehe Brainstorm Decision E.

**Changes-Diff-Logik:** Liest YAML-Frontmatter des **alphabetisch jüngsten** Vormonats-Files
(robust gegen Lücken nach Budget-Stop). Erster Run: Datei wird mit Hinweis erzeugt,
einheitliches File-Set.

**Implementierungsvorschlag — drei Generatoren in `app/output/`:**
- `dimensions_generator.py`
- `crosshits_generator.py`
- `changes_generator.py`
- Composition Root: `build_output_pipeline()` in `app/screener/compose.py`

**Anschließend in derselben Phase:**
- GitHub-Push via API (Obsidian Git Plugin liest)
- Cloud Run Deploy + Cloud Scheduler-Job
- `SCHEDULER_JOB_NAME` in `budget_stop.py` eintragen (erst wenn Scheduler-Job existiert)

## Offene Punkte (nicht-blockierend)

- [ ] IT-Ticket WatchGuard EPDR (strukturelle Lösung statt Workaround)
- [ ] mypy strict / `@runtime_checkable` auf Protocols erwägen — vor Phase 2
- [ ] GICS-50 (Communication Services) zu F&E-Branchen hinzufügen? — nach erstem Lauf bewerten
- [ ] `has_active_enforcement` ist Stub mit Logger-Warnung — SEC EDGAR hat keine direkte Enforcement-API; Lösung vor Phase 2 evaluieren
- [ ] Schwelle ≥4 für Crosshits nach erstem Lauf evaluieren — ggf. auf ≥4.5 erhöhen wenn Liste >50 wird
- [ ] Status Telefon-Agent-Migration prüfen (Memory sagt Deadline 1.6.2026)
- [ ] **V3-Architektur-Doc aktualisieren** (`D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\FisherScreen_Architektur_v3.md`): Section 4.2 beschreibt L1-L5 quant-basierte Listen (Margin-Champions, Margin-Trend, Anti-Verwässerer, F&E-Effektivität, Wachstum). Implementiert wurden in Phase 1.3 stattdessen Gemini-Assessment-Dimensionen (`growth`, `profitability`, `management`, `innovation`, `resilience`). Doku-Drift in V3 vermerken; V3-Quant-Listen als Phase-2/3-Backlog-Kandidat erfassen — entweder als zusätzliche Sicht neben Gemini-Assessment oder als Quant-Vorfilter vor Gemini-Scoring. Designfrage offen.

## Decisions Log

| Datum | Entscheidung | Begründung | Trade-off |
|---|---|---|---|
| 2026-05-13 | `google-genai` SDK statt `google-generativeai` | Offizielle neue Bibliothek für Gemini; unterstützt `count_tokens()` vor API-Call | Breaking changes bei zukünftigen SDK-Updates wahrscheinlich — aber kein Weg zurück zur alten SDK sinnvoll |
| 2026-05-13 | Token-Counting vor jedem API-Call | Verhindert übergroße Prompts; kein verlorenes API-Budget | Zusätzlicher API-Call pro Ticker (~100ms Latenz) |
| 2026-05-13 | Run-Level Token-Budget in `run_gemini_scoring()`, nicht im Aufrufer | Fail-safe auf dem niedrigsten Level; Aufrufer kann die Cap nicht vergessen | Parameter `token_cap` am Aufrufpunkt sichtbar — könnte versehentlich überschrieben werden |
| 2026-05-13 | `RunRecord.compute_cost()` als Single Source für Kostenformel | Formel-Duplikation zwischen `RunTracker` und `RunRecord` vermieden | `RunRecord.estimated_cost_usd` wird nach Konstruktion nachträglich gesetzt — leicht unintuitiv |
| 2026-05-13 | `budget_stop.py` als eigenständige Cloud Function (kein FastAPI-Route) | Pub/Sub-Trigger erfordert separaten Entrypoint; Cloud Function ist günstiger als zweiter Cloud Run Dienst | Separate Deployment-Pipeline nötig; `infra/requirements.txt` separat von `pyproject.toml` halten |
| 2026-05-15 | Drei Output-Files pro Monatslauf (Dimensions/Crosshits/Changes) statt File-pro-Ticker | Kognitiv skalierbarer Output — Stephan schaut realistisch max. 10 Ticker/Monat; 400 Files verstecken die wenigen relevanten | Mehr Generator-Code als ein einziger Per-Ticker-Renderer; drei kleinere Module statt einem großen |
| 2026-05-15 | Crosshits-Logik (≥2 Dimensionen mit Score ≥4) statt Composite-Score | Bleibt V3-konform (kein Composite); Schnittmenge ist Fisher-konformeres Signal als gemittelter Score | Schwelle muss nach erstem Lauf empirisch validiert werden |
| 2026-05-15 | Markdown ist Snapshot, kein Firestore-Snapshot pro Run | Vermeidet Schreibkosten + Redundanz; Git versioniert die Markdowns ohnehin | Changes-Diff muss aus Markdown-Frontmatter lesen statt aus Firestore — leichte Mehrarbeit im Generator |
| 2026-05-15 | YAML-Frontmatter in `Dimensions.md` als maschinen-lesbare Sicht | Eine Datei für Mensch + Maschine; Obsidian rendert Frontmatter sauber | Format-Drift muss durch Schema-Test gesichert werden |

## Parallele Projekte

- **Telefon-Agent**: Gemini-Migration. Memory sagt "anstehend, Deadline 1.6.2026". **Beim nächsten Login prüfen.**
- **RechPro**: Stabil, keine Aktivität geplant.

## Geänderte Annahmen / Pivots

- **2026-05-15:** Phase-1.4-Scope geändert von „ein File pro Ticker in `output/Universum/`" auf „drei aggregierte Files pro Monatslauf". Ursache: Premortem-Diskussion identifizierte „Pull-Philosophie kollabiert in der Praxis" als Top-Risiko. 400 Markdown-Files = Bibliothek, nicht Briefing. Siehe `docs/superpowers/brainstorm/2026-05-15-phase-1-4-output-structure.md`.
- **`filter_passed_basis` ist binär nach apply_basis_filters**: `None` = "nicht geprüft", `True`/`False` = Ergebnis. Unveränderlich.
- **`get_financials` Rückgabetyp `Any`**: yfinance liefert pandas DataFrame, kein dict.
- **Kein Composite-Score in Tool A**: fünf Dimensions-Listen nebeneinander — V3-Entscheidung, kein Scoring-Aggregat. Crosshits ersetzen die funktionale Rolle ohne Composite-Probleme.
- **`screened_at` Timestamp in `ScreenerRecord` ist `default_factory`**: Objekte, die zu verschiedenen Zeiten erstellt werden, sind nicht gleich. In Tests: Record-Instanz einmal erstellen und wiederverwenden, nicht mehrfach `_record()` aufrufen.
