# FisherScreen — Projektstand

> **Single Source of Truth für den aktuellen Stand.**
> Wird am Ende jeder Arbeitssession aktualisiert.
> Verwandte Dokumente: `D:\programme\stef-vault\10_Projekte\FisherScreen\FisherScreen_Architektur_v3.md` (Architektur, extern),
> `docs/superpowers/brainstorm/` (Architektur-Entscheidungen),
> `docs/superpowers/plans/` (ausgeführte Implementations-Pläne).

---

## Letztes Update: 2026-05-16

## Top of mind

FisherScreen Phase 1 ist produktiv. Erster Lauf am 2026-05-16 erfolgreich durchgeführt nach Fix eines kritischen Feedback-Loop-Bugs. Monatlicher Scheduler-Job läuft, drei Markdown-Outputs (Dimensions, Crosshits, Changes) werden via GitHub Sync ins Obsidian-Repo gepusht. Nächster regulärer Lauf: 2026-06-01 03:00 UTC.

## Status

**Aktueller Phase**: Phase 1 produktiv ✅ — Erster Lauf 2026-05-16, Feedback-Loop-Bug behoben.
**Branch**: `main` — 234 Tests, 95.35% Coverage.
**Cloud Run**: `fisherscreen-service` Revision `00030-jnv` in europe-west3 (Projekt `fisherscreen-prod`, Projektnummer 896012696952).
**Gemini-Modell**: `gemini-2.5-flash-lite` (konfigurierbar via `FISHERSCREEN_GEMINI_MODEL`)
**Cloud Scheduler**: `fisherscreen-monthly` aktiv — läuft automatisch am 1. jeden Monats um 05:00 Europe/Berlin. Retry-Policy gehärtet: max 2 Retries, 60s minBackoff.
**Hard-Stop**: Cloud Function + $10-Budget mit Pub/Sub-Hook — verifiziert.
**EDGAR CIK-Lookup**: Funktioniert in Production ✅ — CIKs für US-Ticker aus `company_tickers.json`.
**Universe**: 1.389 Ticker (S&P 500 + S&P 400 + STOXX Europe 600) in `data/universe.json` ✅
**Erster Output**: Top-Crosshit NOVO-B.CO (Score 4.6, alle 5 Dimensionen), 50 Crosshit-Kandidaten aus 160 Vorfilter-Tickern.
**Nächster Lauf**: 2026-06-01 03:00 UTC (automatisch via Cloud Scheduler)

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
- 2026-05-16: **Phase 3 vollständig abgeschlossen** ✅ — Cloud Function, Hard-Stop Budget, reduzierter Run, Cloud Scheduler
- 2026-05-16: **EDGAR CIK-Lookup** gefixt — `get_cik()` via `www.sec.gov/files/company_tickers.json`, URL-Bug (`data.sec.gov` → `www.sec.gov`) behoben, Production verifiziert
- 2026-05-16: **GitHub-Token `.strip()`** — defense-in-depth gegen PAT-Newline-Bug deployed
- 2026-05-16: **Universe-Erweiterung** auf 1.389 Ticker — `scripts/build_universe.py`, S&P 500 + S&P 400 + STOXX 600
- 2026-05-16: **Cloud Run Timeout** auf 3600s erhöht — `--timeout=3600` in `deploy.yml`
- 2026-05-16: **Deployment-Feedback-Loop** gefixt — `paths-ignore: output/**` + `[skip ci]`, PR #2, Commit `9b64007`
- 2026-05-16: **Scheduler Retry-Policy** gehärtet — `--max-retry-attempts=2 --min-backoff=60s --max-backoff=300s --max-retry-duration=1800s`
- 2026-05-16: **Erster produktiver Lauf** ✅ — Verifikations-Run 15:36 UTC, kein Retry, drei Output-Commits mit `[skip ci]`, kein Deploy getriggert

### Mai 2026 — Produktivgang und Feedback-Loop-Fix

Erster Scheduler-Run produzierte Output, aber löste eine Feedback-Schleife aus: jeder der drei Output-Commits (Dimensions, Crosshits, Changes) auf `main` triggerte den `Deploy to Cloud Run` Workflow, der eine neue Cloud-Run-Revision deployte und den laufenden Container mit `SIGTERM` killte. Cloud Scheduler mit aggressiver Retry-Policy retriede den Request → zweiter `POST /run/monthly` 4 Sekunden nach dem ersten. Sechs GitHub-Actions-Workflow-Runs in 15 Minuten, zwei davon HTTP 409 wegen paralleler `gcloud run deploy`-Calls auf denselben Service.

**Fix (PR #2, Commit `9b64007`):**
- `.github/workflows/deploy.yml`: `paths-ignore: ['output/**']`
- `app/main.py:63`: Commit-Message ergänzt um `[skip ci]`-Suffix
- Tests erweitert (`test_monthly_run_commit_message_includes_skip_ci`)
- Defense-in-Depth: beide Maßnahmen aktiv, jede für sich allein würde reichen

**Cloud Scheduler Retry-Policy gehärtet:**
- Vorher: unlimited retries, 5s minBackoff, kein maxRetryDuration
- Nachher: `--max-retry-attempts=2 --min-backoff=60s --max-backoff=300s --max-retry-duration=1800s`

**Deployment-Quirk:** Squash-Merge-Commit `9b64007` und nachfolgender Empty-Commit `b8427f6` haben den `Deploy to Cloud Run` Workflow nicht getriggert (Ursache unklar — möglicher GitHub-Actions-Trigger-Bug bei zeitlich engem Aufeinanderfolgen). Workaround: manueller Deploy via `gcloud builds submit` + `gcloud run deploy` von der Workstation. Resultierende Revision: `fisherscreen-service-00030-jnv`, Image-Tag `b8427f6`.

**Verifikations-Lauf (15:36 UTC):**
- ✅ Genau ein `POST /run/monthly` 200 OK (kein Retry)
- ✅ Keine doppelten EDGAR-Calls (jeder CIK genau einmal)
- ✅ Drei Output-Commits mit `[skip ci]` Suffix gepusht
- ✅ Kein neuer GitHub-Actions-Workflow trotz Output-Commits
- ✅ Cloud Run Revision blieb stabil bis zum Lauf-Ende (kein Mid-Run-Shutdown)

**Erster echter Phil-Fisher-Output:**
- Universum-Größe nach Vorfilter: 160 Tickers (aus ~1.389 S&P 500 + S&P 400 + STOXX 600)
- Top-Crosshit: **Novo Nordisk (NOVO-B.CO)** mit Score 4.6 und allen 5 Dimensionen positiv — einziges Unternehmen mit Full-House-Hit
- Weitere Top-Kandidaten: DB1.DE, ITX.MC, MONC.MI, SAP.DE (alle 4 Dimensionen)
- Insgesamt 50 Crosshit-Kandidaten in der Top-50-Liste
- Changes-Datei korrekt leer (erster Lauf, kein Vormonat-Vergleich möglich)

---

### Phase-3-Details (2026-05-16)

| Schritt | Was |
|---|---|
| Phase 3b — Cloud Function | `fisherscreen-budget-stop` deployed (Gen 2, europe-west3), Trigger: Pub/Sub `fisherscreen-budget-alerts` |
| Phase 3b — $10 Budget | Hard-Stop-Budget mit Pub/Sub-Hook aktiv für `fisherscreen-prod` |
| Phase 3c — /run/monthly Test | Revision 00006, 9 Ticker processed (1 filtered), Markdown-Files in `stnmllr/fisherscreen/output/Universum/` committed |
| Phase 3c — Cloud Scheduler | `fisherscreen-monthly` aktiv, Schedule `0 5 1 * *` Europe/Berlin, OIDC-Auth mit `fisherscreen-scheduler` SA |
| Phase 3c — Hard-Stop-Verifikation | Pub/Sub-Test pausierte Scheduler korrekt; manuell resumed — End-to-End bestätigt |
| Gemini-Migration | `gemini-2.0-flash-lite` → `gemini-2.5-flash-lite`; `FISHERSCREEN_GEMINI_MODEL` Env-Var eingebaut |
| Cloud Function Rename | `infra/budget_stop.py` → `infra/main.py` (Cloud Functions Python-Konvention) |

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

## Nächste Session — Phase 2 TODOs

Phase 1 ist vollständig. Nächster regulärer Lauf automatisch 2026-06-01 03:00 UTC. Die folgenden Phase-2-Punkte sind nach Priorität geordnet — kein Blocking-Item für den Juni-Lauf.

**Infra-Phasen-Status (vollständig):**

| Phase | Status |
|---|---|
| Phase 1 (Bootstrap) | ✅ |
| Phase 2 (Deploy) | ✅ |
| Phase 3a ($5 Warning) | ✅ |
| Phase 3b ($10 Hard Stop) | ✅ |
| Phase 3c (Cloud Scheduler) | ✅ |
| Phase 4 (Universe + Bugfixes + Produktivgang) | ✅ |

**Phase-2-Backlog:**

1. **Cloud Run Jobs statt Cloud Run Service für Tool A** — entkoppelt den Monatslauf von Deployments, eliminiert Deployment-Race-Risiko bei zukünftigen Architekturänderungen, höheres Timeout (24h statt 60min). Setzt voraus: Cloud Run Jobs Migration, Scheduler-Trigger auf Job-Execution statt HTTP.

2. **Gemini 503-Retry mit tenacity** — beim ersten Lauf wurde ALV.DE aus dem Scoring rausgeworfen wegen "503 UNAVAILABLE - high demand". Retry mit exponentiellem Backoff (3 Versuche: 1s, 4s, 16s) für 503/429.

3. **`has_active_enforcement` ausimplementieren** — derzeit Phase-1-Platzhalter, gibt für alle CIKs `False` zurück. Bei US-Tickern via SEC EDGAR, bei EU-Tickern via BaFin/FCA/AMF/CNMV.

4. **Idempotenz-Lock auf `/run/monthly`** — Firestore-Dokument `runs/monthly/{YYYY-MM}` mit Status `running|completed`. Verhindert Doppelaufrufe falls Scheduler-Retry trotz neuer Policy noch zuschlägt.

5. **Output-Repo-Trennung** — `stnmllr/fisherscreen-output` als separates Repo, wenn Output-Frequenz steigt (Deep-Dives, Hold-Checks). Aktuell nicht nötig.

6. **GitHub-Actions-Trigger-Quirk** — Untersuchen, warum Squash-Merge-Commit `9b64007` keinen Workflow ausgelöst hat. Mögliche Ursache: zeitliches Aufeinanderfolgen von Commits.

7. **Vorfilter-Dokumentation** — Universum reduziert sich von ~1.389 auf 160 Tickers in der Basis-Filter-Phase. Filter-Logik in `app/screener/filters.py` lokalisieren und in `docs/` dokumentieren (Threshold-Werte, Ausschluss-Gründe).

8. **Name-Cleanup im Output** — yfinance liefert Listing-Suffixe ("N", "I", "V") und kaputte Encodings ("DISE...O" statt "DISEÑO"). In `dimensions_generator.py` und `crosshits_generator.py` rstrip/encoding-Cleanup.

## Offene Punkte (nicht-blockierend)

### Erster Lauf — Offene Punkte
- [ ] **TSMC market_cap missing** — yfinance-Bug oder Ticker-Format-Issue (TSM vs TSMC)? Klären.
- [ ] **Cache-TTL bei Monatswechsel** — greift Mai-Cache am 1. Juni? TTL-Logik im Firestore-Client prüfen
- [ ] **`dev_` Collection-Prefix** evaluieren — für Production auf `prod_` umstellen?
- [ ] Crosshits-Schwelle ≥4 nach erstem echten Lauf validieren — ggf. auf ≥4.5 wenn >50 Kandidaten

### Infra / Sicherheit
- [ ] **GitHub Token Rotation** — `fisherscreen-github-token` läuft am **2027-05-15** ab. Kalender-Reminder setzen.
- [ ] **Default Compute SA prüfen** — `896012696952-compute@developer.gserviceaccount.com` hat GCP-default `roles/editor`; evaluieren ob sicher entfernbar
- [ ] **`scripts/smoke-test.cmd`** schreiben — kapselt gcloud-Token + curl /health, für wiederholbare Tests

### Backlog (nicht-blockierend)
- [ ] IT-Ticket WatchGuard EPDR (strukturelle Lösung statt Workaround)
- [ ] mypy strict / `@runtime_checkable` auf Protocols erwägen
- [ ] GICS-50 (Communication Services) zu F&E-Branchen hinzufügen? — nach erstem Lauf bewerten
- [ ] `has_active_enforcement` ist Stub — SEC EDGAR hat keine direkte Enforcement-API; Lösung evaluieren
- [ ] Status Telefon-Agent-Migration prüfen (Deadline 1.6.2026)
- [ ] **V3-Architektur-Doc aktualisieren** (`D:\programme\stef-vault\...\FisherScreen_Architektur_v3.md`): Section 4.2 beschreibt L1-L5 quant-basierte Listen. Implementiert wurden Gemini-Assessment-Dimensionen — Doku-Drift vermerken.

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

## Lessons Learned — Phase 3 (Cloud Function, Run, Scheduler)

Aufgezeichnet 2026-05-16. Ergänzung zu GCP-Bootstrap-Lessons a–l.

### m) GitHub-PAT-Newline-Bug: `echo` hängt `\n` an → httpx-Crash

`echo "token" | gcloud secrets versions add` speichert das Secret mit abschließendem Newline. httpx wirft dann beim ersten Request `LocalProtocolError` (invalider HTTP-Header). **Fix:** Secret mit Binary-Write ohne Newline speichern:
- PowerShell: `[System.IO.File]::WriteAllText("token.txt", "ghp_...", [System.Text.Encoding]::ASCII)`
- Alternativ: VS Code → neue Datei, LF-Encoding, **kein** trailing newline → `gcloud secrets versions add ... --data-file=token.txt`
- Code-seitig als Defense-in-depth: `token = token.strip()` beim Laden des Secrets.

### n) Token-Leak in Cloud Logging via httpx-Exceptions

Wenn httpx eine Exception wirft (z.B. nach Newline-Bug), schreibt es den vollständigen Request-Header in die Exception-Message — inkl. `Authorization: Bearer ghp_...`. Landet ungefiltert in Cloud Logging, ist öffentlich lesbar wenn Logs-Viewer falsch konfiguriert. **Mitigation:** `.strip()` verhindert den Crash; bei echter Token-Exposition sofort revoken + neues Secret anlegen.

### o) Gemini 2.0 Flash-Lite deprecated ab 1. Juni 2026

`gemini-2.0-flash-lite` wird June 1, 2026 eingestellt. Migration auf `gemini-2.5-flash-lite` (GA seit Feb 2026). `3.1-preview` übersprungen wegen Account-Zugriff (gleiches Muster wie bei anderen Projekten — Preview-Modelle oft quota-restricted). **Pattern für die Zukunft:** Gemini-Modell nie hardcoden — immer `FISHERSCREEN_GEMINI_MODEL` als Env-Var in Cloud Run setzen, Fallback im Code.

### p) Cloud Run Secret-Caching: Update wirkt erst nach Container-Restart

Wenn ein Secret in Secret Manager aktualisiert wird, cached der laufende Container die alte Version bis zum nächsten Kaltstart. `gcloud run services update --update-secrets=KEY=secret:latest` erzwingt einen Restart — auch wenn der Secret-Name identisch bleibt. Ohne diesen Schritt testet man gegen das alte Secret.

### q) Cloud Functions Python: Entrypoint muss `main.py` heißen

Cloud Functions (Python Runtime) erwartet den Source-Code in einer Datei namens `main.py`. Eine Datei `budget_stop.py` als `--source=infra` wird nicht gefunden — Cloud Function startet, findet aber den Entrypoint nicht. Fix: Datei in `main.py` umbenennen.

### r) cmd.exe interaktiv vs. Batch: `%{variable}` vs. `%%{variable}`

In interaktiver cmd.exe-Session: `%{http_code}` (einfaches Prozentzeichen).  
In `.bat`-Skripten: `%%{http_code}` (doppeltes Prozentzeichen, weil Batch-Parser ein `%` konsumiert).  
Verwirrungsquelle wenn man Befehle zwischen interaktiver Session und `.bat`-Datei kopiert.

## GCP-Infrastruktur (Stand 2026-05-16)

| Ressource | Wert |
|---|---|
| Projekt | `fisherscreen-prod` (896012696952) |
| Region | `europe-west3` |
| Cloud Run Service | `fisherscreen-service` (aktuell: Revision `00030-jnv`, Image `b8427f6`) |
| Runtime SA | `fisherscreen-runtime@fisherscreen-prod.iam.gserviceaccount.com` |
| Deploy SA | `github-deploy@fisherscreen-prod.iam.gserviceaccount.com` |
| Scheduler SA | `fisherscreen-scheduler@fisherscreen-prod.iam.gserviceaccount.com` |
| WIF Pool | `github-pool` / Provider `github-provider` |
| Artifact Registry | `europe-west3-docker.pkg.dev/fisherscreen-prod/fisherscreen` |
| Secrets | `fisherscreen-gemini-api-key`, `fisherscreen-github-token` (läuft ab: 2027-05-15) |
| Gemini SDK | `google-genai` mit API-Key (nicht Vertex AI) |
| Gemini Modell | `gemini-2.5-flash-lite` (via `FISHERSCREEN_GEMINI_MODEL` Env-Var) |
| Budget Warning | $5/Monat actual spend → E-Mail stn.mueller@gmail.com (aktiv) |
| Budget Hard Stop | ✅ $10/Monat + Pub/Sub `fisherscreen-budget-alerts` → Cloud Function (verifiziert) |
| Cloud Function | `fisherscreen-budget-stop` (Gen 2, europe-west3, `infra/main.py`) |
| Cloud Scheduler | `fisherscreen-monthly` — `0 5 1 * *` Europe/Berlin → POST `/run/monthly` (max 2 Retries, 60s–300s Backoff) |
| Konsolidiertes Budget | €10/Monat alle Projekte — grobes Sicherheitsnetz |

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
| 2026-05-16 | `gemini-2.5-flash-lite` statt `gemini-2.0-flash-lite` | 2.0 Flash-Lite deprecated ab 1. Juni 2026; 2.5 ist GA und kostengleich | Preview-Modelle (3.1) wegen Account-Quota-Beschränkung übersprungen |
| 2026-05-16 | `FISHERSCREEN_GEMINI_MODEL` als Env-Var statt Hardcode | Modell-Updates ohne Code-Deploy; ermöglicht A/B-Testing per Cloud Run Revision | Default `gemini-2.5-flash-lite` im Code — Env-Var nur wenn Abweichung nötig |
| 2026-05-16 | `paths-ignore: output/**` + `[skip ci]` als Defense-in-Depth gegen Feedback-Loop | Output-Commits dürfen keinen Deploy triggern; `paths-ignore` ist primärer Schutz, `[skip ci]` Backstop falls Output-Pfad je außerhalb `output/` landet | Beide Maßnahmen sind unabhängig voneinander wirksam — keine Doppelarbeit, aber leicht mehr Konfigurations-Surface |

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
