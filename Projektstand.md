# FisherScreen — Projektstand

> **Single Source of Truth für den aktuellen Stand.**
> Wird am Ende jeder Arbeitssession aktualisiert.
> Verwandte Dokumente: `D:\programme\stef-vault\10_Projekte\FisherScreen\FisherScreen_Architektur_v3.md` (Architektur, extern),
> `docs/superpowers/brainstorm/` (Architektur-Entscheidungen),
> `docs/superpowers/plans/` (ausgeführte Implementations-Pläne).

---

## Letztes Update: 2026-05-16

## Status

**Aktueller Phase**: Phase 1 vollständig implementiert, deployed und smoke-getestet. ✅
**Branch**: `main` — 226 Tests, 95.51% Coverage.
**Cloud Run**: `fisherscreen-service` läuft in europe-west3 (Projekt `fisherscreen-prod`, Projektnummer 896012696952).
**`/health`**: `{"status":"ok"}` — Service ist operational.
**Nächste Mini-Task**: Phase 3b (Cloud Function deployen für $10 Hard-Stop), dann Cloud Scheduler.

## Erledigt

- 2026-05-10: Repo-Setup (10 Tasks, 23 Tests)
- 2026-05-11: Phase-1-Master-Brainstorm
- 2026-05-12: **Phase 1.1** Data Pipeline + Basisfilter — `main`
- 2026-05-13: **Phase 1.2** EDGAR-Signale — `main`
- 2026-05-13: **Phase 1.3** Gemini Scoring — `main`
- 2026-05-15: **Phase-1.4-Output-Struktur-Brainstorm** — `docs/superpowers/brainstorm/2026-05-15-phase-1-4-output-structure.md`
- 2026-05-15: **Phase-1.4-Implementierungsplan** — `docs/superpowers/plans/2026-05-15-phase-1-4-markdown-output.md`
- 2026-05-15: **Phase 1.4** implementiert — PR #1, Squash-Merge, Commit `c5d8019`
- 2026-05-15: **GCP Bootstrap** abgeschlossen — `docs/infra/setup-gcp-project.md`
- 2026-05-15: **Cloud Run Deploy** erfolgreich — `fisherscreen-service` läuft
- 2026-05-16: **$5 Warning-Budget** angelegt in GCP Console (Scope: `fisherscreen-prod`, Threshold: $5 actual spend, Alert: E-Mail an stn.mueller@gmail.com)
- 2026-05-16: **Smoke-Test `/health`** ✅ — `{"status":"ok"}`, OIDC-Auth via `gcloud auth print-identity-token`, Cloud Run operational

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

### Phase-1.4-Details (2026-05-15)

| Datei | Was |
|---|---|
| `app/screener/dimensions.py` | `DIMENSIONS` Konstante — Single Source of Truth |
| `app/output/dimensions_generator.py` | `YYYY-MM-Dimensions.md` mit YAML-Frontmatter + 5 Dimensions-Tabellen |
| `app/output/crosshits_generator.py` | `YYYY-MM-Crosshits.md` — Ticker in ≥2 Dims mit Score ≥4 |
| `app/output/changes_generator.py` | `YYYY-MM-Changes.md` — Diff gegen jüngsten Vormonats-Run |
| `app/screener/runner.py` | `run_screener()` Orchestrator (Basis → EDGAR → Gemini → Output) |
| `app/services/github_client.py` | `GitHubClientImpl` — Push via REST API |
| `app/screener/compose.py` | `build_github_client()` |
| `app/main.py` | FastAPI `/health` + `/run/monthly` |
| `Dockerfile` | python:3.12-slim + uv, uvicorn Port 8080 |
| `.github/workflows/deploy.yml` | Push-to-main → Cloud Run Deploy (Workload Identity Federation) |
| `data/universe.json` | 10-Ticker Placeholder |
| `docs/infra/cloud-scheduler.md` | Cloud Scheduler Setup-Doku |
| `docs/infra/setup-gcp-project.md` | GCP Bootstrap Step 1–11 |

**Qualitäts-Korrekturen durch Code-Review (nicht im Plan):**
- `GeminiClientImpl._parse_response`: `ValueError` in except-Tuple ergänzt (safety-filtered responses)
- `RunTracker.finish()`: delegiert zu `RunRecord.compute_cost()` statt Formel duplizieren
- `RunTracker`: `Literal["success","partial","aborted"]`-Typ, `_finished`-Guard gegen Doppelaufruf
- Alle `build_*()` geben Protocol-Typen zurück, nicht konkrete Klassen
- `spec=True` auf Pydantic-Settings-Mock (16 harmlose Pydantic-v2-Deprecation-Warnings — bekannt)
- `budget_stop.py`: `os.environ.get()` statt `[]` (kein KeyError beim Cold Start), `GoogleAPICallError`-Catch
- `DimensionsGenerator`: `qualifying_count` ist pre-cap (nicht post-cap) — durch Review-Loop gefunden

## Nächste Session

**Ziel**: Phase 3b (Hard-Stop Cloud Function), dann Cloud Scheduler, dann reduzierter /run/monthly-Test.

**Infrastruktur-Phasen-Status:**

| Phase | Status |
|---|---|
| Phase 1 (Bootstrap): `docs/infra/setup-gcp-project.md` | ✅ ausgeführt |
| Phase 2 (Deploy): `deploy.yml` + Cloud Run Service | ✅ läuft, `/health` grün |
| Phase 3a (Budget Warning $5): GCP Console | ✅ aktiv für `fisherscreen-prod` |
| Phase 3b (Hard Stop $10): Cloud Function + Pub/Sub | ❌ noch offen |
| Phase 3c (Cloud Scheduler monthly) | ❌ noch offen |

**Schritt 1 — Phase 3b: Cloud Function deployen** (`infra/budget_stop.py` ist vorhanden):
- `gcloud functions deploy fisherscreen-budget-stop ...` mit Trigger auf Pub/Sub-Topic `fisherscreen-budget-alerts`
- Anleitung: `docs/infra/budget-alerts.md` Step 4
- Test via Pub/Sub Manual-Publish (Step 5 in `docs/infra/budget-alerts.md`)

**Schritt 2 — $10 Hard-Stop-Budget anlegen** in GCP Console (jetzt wo Cloud Function vorhanden):
- Scope: `fisherscreen-prod`, Threshold: $10 actual spend
- Pub/Sub-Topic: `fisherscreen-budget-alerts` als Notification-Channel
- ⚠️ Reaktivierung des Cloud Schedulers nach Hard-Stop: ausschließlich manuell in GCP Console nach Ursachenanalyse

**Schritt 3 — Reduzierter Smoke-Test `/run/monthly`** (5–10 Ticker):
- **Nicht** vor aktivem Hard-Stop (Schritt 2) — Bug im Gemini-Loop könnte Budget reißen
- Möglicher Ansatz: temporäres `data/universe.json` mit 5 Tickern committen, Run starten, revertieren
- Beim Test beobachten: kompletter Pipeline-Run (Basis → EDGAR → Gemini → Output → GitHub-Push)
- Falls Markdown-Files generiert werden: landen im `fisherscreen`-Output-Repo — ist OK, echte Daten

**Schritt 4 — Phase 3c: Cloud Scheduler anlegen** (siehe `docs/infra/cloud-scheduler.md`):
- Erst nach grünem `/run/monthly`-Test (Schritt 3)
- Danach ist der automatische monatliche Lauf scharfgeschaltet

**Schritt 5 — Voller Monatslauf** (~2.100 Ticker):
- Erst NACH Cloud Scheduler Setup und mit aktivem Hard-Stop (Schritt 2)
- `data/universe.json` mit echten ~2.100 Tickern (S&P 500 + Russell 1000 + STOXX 600) befüllen
- Crosshits-Schwelle ≥4 nach erstem Lauf empirisch validieren — ggf. auf ≥4.5 erhöhen

## Offene Punkte (nicht-blockierend)

- [ ] **Phase 3b Hard-Stop** Cloud Function deployen — BLOCKIEREND vor erstem echten Monatslauf
- [ ] **$10 Hard-Stop-Budget** in GCP Console anlegen (nach Phase 3b) — BLOCKIEREND vor erstem echten Monatslauf
- [ ] **Smoke-Test `/run/monthly`** mit 5–10 Tickern — BLOCKIEREND vor Cloud Scheduler
- [ ] **GitHub Token Rotation** — `fisherscreen-github-token` läuft am **2027-05-15** ab. Kalender-Reminder setzen.
- [ ] **`scripts/smoke-test.cmd`** schreiben — kapselt gcloud-Token + curl /health, für wiederholbare manuelle Tests
- [ ] **Default Compute SA prüfen** — `896012696952-compute@developer.gserviceaccount.com` hat GCP-default `roles/editor`; nicht genutzt (Cloud Run läuft mit `fisherscreen-runtime`). Evaluieren ob `roles/editor` sicher entfernt werden kann.
- [ ] **`data/universe.json`** mit echten ~2.100 Tickern (S&P 500 + Russell 1000 + STOXX 600) befüllen — vor erstem Monatslauf
- [ ] IT-Ticket WatchGuard EPDR (strukturelle Lösung statt Workaround)
- [ ] **Kalender-Reminder ~10. Mai 2027** — GitHub Token Rotation fällig (`fisherscreen-github-token` läuft 2027-05-15 ab)
- [ ] mypy strict / `@runtime_checkable` auf Protocols erwägen — vor Phase 2
- [ ] GICS-50 (Communication Services) zu F&E-Branchen hinzufügen? — nach erstem Lauf bewerten
- [ ] `has_active_enforcement` ist Stub mit Logger-Warnung — SEC EDGAR hat keine direkte Enforcement-API; Lösung vor Phase 2 evaluieren
- [ ] Schwelle ≥4 für Crosshits nach erstem Lauf evaluieren — ggf. auf ≥4.5 erhöhen wenn Liste >50 wird
- [ ] Status Telefon-Agent-Migration prüfen (Memory sagt Deadline 1.6.2026)
- [ ] **V3-Architektur-Doc aktualisieren** (`D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\FisherScreen_Architektur_v3.md`): Section 4.2 beschreibt L1-L5 quant-basierte Listen. Implementiert wurden Gemini-Assessment-Dimensionen — Doku-Drift vermerken; V3-Quant-Listen als Phase-2/3-Backlog-Kandidat.

## Lessons Learned — GCP Bootstrap

Aufgezeichnet nach dem ersten Deploy-Versuch (2026-05-15). Für künftige Projekte mit ähnlichem Stack.

### a) Bootstrap-Doku gehört zur gleichen Phase wie der Code

Wenn eine Phase Infrastruktur-Code generiert (`Dockerfile`, `deploy.yml`, Cloud-Function-Code), muss die **gleiche Phase** auch das Bootstrap-Setup dokumentieren — nicht nur nachgelagerte Schritte. `docs/infra/setup-gcp-project.md` hätte Teil der Phase-1.4-Lieferung sein müssen, nicht ein Add-on nach dem ersten fehlgeschlagenen Deploy.

### b) GitHub-Actions-Workflows immer auf Secret-Namen prüfen vor Merge

Ungetestete Workflows zu mergen ist riskant. Mindestens: alle referenzierten Secrets (`${{ secrets.XYZ }}`) vor dem Merge verifizieren. Falls möglich, `act` lokal für Trockenlauf nutzen.

### c) `uvicorn` explizit als Prod-Dependency eintragen

`uvicorn[standard]` muss explizit in `pyproject.toml` stehen. Der Container baut durch, weil `uv sync` keinen Fehler wirft wenn `uvicorn` fehlt — der Crash kommt erst zur Container-Startzeit. Cloud Run Logs zeigen dann kein stdout, weil der Crash vor jedem Python-Output passiert.

### d) `gcloud builds submit` braucht `roles/viewer` für Log-Streaming

Nicht nur `logging.viewer`. Diese Anforderung ist in der GCP-Doku nicht prominent dokumentiert. Alternative bei Least-Privilege-Präferenz: `--async` Flag im Workflow.

### e) WIF Service Account braucht 8 Rollen für funktionierende CI/CD

Vollständige Liste (in `docs/infra/setup-gcp-project.md` dokumentiert):
`run.admin`, `artifactregistry.writer`, `iam.serviceAccountUser`, `cloudbuild.builds.editor`, `cloudbuild.builds.viewer`, `serviceusage.serviceUsageConsumer`, `storage.admin`, `viewer`

### f) `--service-account=...` explizit im deploy-Befehl angeben

Ohne dieses Flag läuft Cloud Run mit dem Default Compute SA (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`), der projektweit `roles/editor` hat — Security-Issue. Immer explizit `fisherscreen-runtime@fisherscreen-prod.iam.gserviceaccount.com` setzen.

### g) GitHub Token: immer 1 Jahr + Kalender-Reminder

GitHub erlaubt max 1 Jahr für fine-grained Tokens. Default ist 30 Tage — viel zu kurz für Production. Immer 1 Jahr setzen und sofort einen Kalender-Reminder ~2 Wochen vor Ablauf eintragen.

### h) Nach Squash-Merge sofort lokalen Branch aufräumen

```
git checkout main
git pull
git branch -D feature/<branch-name>
```

Ohne diesen Schritt entstehen divergierende Histories (Squash-Commit hat andere SHA als die WIP-Commits). Führt zu `unmerged-paths`-State, der nur via `git reset --hard origin/main` reparierbar ist.

### i) Pfade mit Sonderzeichen in der Working Copy prüfen

Kaputte Verzeichnisse (z.B. `D:programmefisherscreendata`) entstehen, wenn ein Tool in einer Bash-Umgebung Windows-Pfade mit `\` als Escape-Zeichen interpretiert. Vor Commit prüfen und ggf. löschen.

### j) Konsolidiertes Budget ≠ projektspezifischer Hard-Stop

Ein konsolidiertes GCP-Budget (Scope: "Alle Projekte") ist ein brauchbares Sicherheitsnetz, aber für project-spezifisches Hard-Stop-Verhalten ungeeignet: Die Pub/Sub-Notification enthält keine Projekt-ID mit der man zuverlässig unterscheiden kann, welches Projekt das Budget gerissen hat — Fehlauslösung durch andere Projekte ist möglich. Immer ein zweites, projektspezifisches Budget anlegen (`Scope: fisherscreen-prod`), auch wenn ein konsolidiertes bereits existiert. Beide koexistieren problemlos.

### k) OIDC-Token auf Windows/cmd.exe: robuster Ansatz via Zwischenspeicher

`gcloud auth print-identity-token | curl` ist auf Windows/cmd.exe fragil (Pipe-Timing, Quote-Escaping). Robuster ist:

```
gcloud auth print-identity-token > %TEMP%\token.txt
set /p TOKEN=<%TEMP%\token.txt
curl -H "Authorization: Bearer %TOKEN%" https://<SERVICE_URL>/health
```

Für wiederholbare Tests lohnt sich ein kleines `scripts\smoke-test.cmd`, das diesen Boilerplate kapselt.

### l) Kein /run/monthly-Test mit vollem Universum vor aktivem Hard-Stop

Bei einem Bug im Gemini-Calling-Loop (~2.100 Ticker × mehrere API-Calls) kann das $5-Budget binnen Stunden gerissen werden. Der E-Mail-Alert trifft mit ~24 h Verzögerung ein. Reihenfolge nicht verhandelbar:
1. Hard-Stop Cloud Function deployen (Phase 3b)
2. $10 Hard-Stop-Budget anlegen (GCP Console)
3. Reduzierter Test mit 5–10 Tickern
4. Voller Lauf erst danach

## GCP-Infrastruktur (Stand 2026-05-15)

| Ressource | Wert |
|---|---|
| Projekt | `fisherscreen-prod` (896012696952) |
| Region | `europe-west3` |
| Cloud Run Service | `fisherscreen-service` |
| Runtime SA | `fisherscreen-runtime@fisherscreen-prod.iam.gserviceaccount.com` |
| Deploy SA | `github-deploy@fisherscreen-prod.iam.gserviceaccount.com` |
| Scheduler SA | `fisherscreen-scheduler@fisherscreen-prod.iam.gserviceaccount.com` |
| WIF Pool | `github-pool` / Provider `github-provider` |
| Artifact Registry | `europe-west3-docker.pkg.dev/fisherscreen-prod/fisherscreen` |
| Secrets | `fisherscreen-gemini-api-key`, `fisherscreen-github-token` (läuft ab: 2027-05-15) |
| Gemini SDK | `google-genai` mit API-Key (nicht Vertex AI) |
| Budget Warning | $5/Monat actual spend → E-Mail stn.mueller@gmail.com (Scope: `fisherscreen-prod`, aktiv seit 2026-05-16) |
| Budget Hard Stop | ❌ noch offen — $10/Monat + Cloud Function `fisherscreen-budget-stop` (Phase 3b) |
| Konsolidiertes Budget | €10/Monat alle Projekte — grobes Sicherheitsnetz, kein projekt-spezifischer Stop |

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
- **Gemini via API-Key, nicht Vertex AI**: `google-genai` SDK mit `FISHERSCREEN_GEMINI_API_KEY`. Kein Service-Account für Gemini-Calls nötig.
