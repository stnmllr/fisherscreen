# Monatslauf vs. 1800-s-Scheduler-Deadline

Stand 2026-10-08 · **Vorschlag, wartet auf Stephans Entscheidung** · kein Code, keine Infra geändert

## Problem

Cloud Scheduler (`fisherscreen-monthly`, HTTP → `POST /run/monthly`) bricht seinen Versuch
nach **1800 s** ab (hartes Maximum für HTTP-Ziele). Cloud Run läuft weiter (Timeout 3600 s)
und pusht — der Job steht trotzdem auf rot. Ein dauerhaft roter Job meldet echte Fehler nicht mehr.

Laufzeiten aus `dev_screener_runs` (`started_at` → `completed_at`, Push danach ~25 s):

| Lauf | Dauer | ticker-Cache | EDGAR-Cache | Bemerkung |
|---|---|---|---|---|
| 07-01 (geplant) | **2380 s** | kalt | kalt | lag schon damals über 1800 s |
| 08-01 / 09-01 / 10-01 (geplant) | 983 / 1444 / 1098 s | kalt | kalt | |
| 10-05 (manuell) | 923 s | kalt | warm (10-01) | |
| 10-08 #1 (manuell, 16:58) | **2019 s** | kalt | **kalt** | |
| 10-08 #2 (manuell, 21:20) | 565 s | warm | warm | |

**Die Ausgangshypothese stimmt nur zum Teil.** Die `_cached_at`-Zeitstempel in Firestore
geben den Zeitverlauf von Lauf #1 wieder (Lauf #2 hat fast nichts überschrieben):

| Phase Lauf #1 | Zeit (UTC) | Dauer | Beleg |
|---|---|---|---|
| `.info` kalt, 1501 Ticker | 14:58:25–15:08:18 | **~590 s** | 1501 Schreibvorgänge in `dev_ticker_cache`, gleichmäßig ~150/min, größte Lücke 6 s |
| Vorabprüfungen (Prepasses), nicht gecacht | 15:08–15:21:45 | **~800 s** | keine Cache-Schreibvorgänge; abgeleitet |
| EDGAR kalt, 606 CIKs | 15:21:45–15:31:26 | **~580 s** | 606 Schreibvorgänge in `dev_edgar_cache` — die Einträge vom 10-01 waren seit 10-08 03:18 UTC abgelaufen |
| Scoring + Ausgaben | 15:31:26–15:32:04 | ~40 s | nur 13 Live-Abrufe in `dev_revenue_series` (warm) |

Kaltes `.info` macht also nur ~30 % aus. Die drei großen Blöcke sind etwa gleich groß.

## Bestätigter Ablauf im Code

- **Route synchron:** `app/main.py:80-81` ist `def` (nicht `async`). FastAPI führt sie im
  Threadpool aus, der Request bleibt bis zum Ende offen. Danach folgen `run_screener`
  (`:100-108`) und der GitHub-Push je Datei (`:110-118`).
- **Alles läuft sequentiell, ein Thread.** Es gibt kein Semaphore, kein `gather`, kein
  `to_thread` und keinen Thread-Pool im ganzen Pfad.
- **`.info`:** Schleife `runner.py:330-332` → `_fetch_and_resolve` (`:121`) →
  `CachedYFinanceClient.get_ticker_info` (`cached_yfinance_client.py:29-51`, TTL 24 h `:15`;
  Treffer nur mit verwertbarer Marktkapitalisierung, sonst neu abrufen) → `yf.Ticker(t).info`
  (`yfinance_client.py:205-220`). Bei yfinance gibt es **keinen Retry, keinen Backoff und
  keinen Rate-Limiter**. Ein NO_RAW_MC-Titel wird einmal sofort erneut abgerufen
  (`runner.py:333-335`).
- **Prepasses, bei jedem Lauf, ohne Cache:** `_assess_definedness_basket`
  (`runner.py:412`, Abruf `:214`) und `_assess_revenue_growth_trajectory` (`:415-417`,
  Abruf `:284`) rufen `get_annual_statements` auf, und zwar ohne Cache
  (`cached_yfinance_client.py:59-62`). Das holt **drei** Abschlüsse (`yfinance_client.py:251-259`:
  income_stmt, cashflow, balance_sheet). Verwendet wird nur `[0]`.
- **EDGAR:** `_evaluate_edgar` (`runner.py:438-449`) → `CachedEdgarClient` (TTL **7 Tage**,
  `cached_edgar_client.py:10`, `:34-45`). Kalt kostet ein CIK Submissions + EFTS-Suche +
  Abruf des Primärdokuments je Kandidat (`edgar_client.py:287-353`). Global gedrosselt auf
  **8 req/s** (`config.py:9`, `edgar_client.py:139-140`), EFTS-5xx bis zu 5 Versuche mit
  Jitter (`:197-230`). Gemessen ~1 s je CIK.
- **Scoring:** `CachedRevenueSeries.get_revenue_series` je bewertetem Titel
  (`deterministic_scorer.py:479-480`). Abgelaufene Einträge holen live
  `get_annual_statements` (`revenue_series_cache.py:71-89`, ~2 s/Titel). Die
  Stetigkeitsachse **liest nur**, ohne SEC-Zugriff (`deterministic_scorer.py:423-447`).
  Die geplante Verdrahtung von `dev_edgar_annual_series` ändert daran nichts.
- **Zeitmessung je Phase:** nur INFO-Zeilen am Phasenende (`runner.py:376`, `:244`, `:303`,
  `:456`, `deterministic_scorer.py:493`). Dauern werden nicht geloggt.
- **Cloud Run:** `deploy.yml:33-41` setzt nur `--timeout=3600`, also CPU, Speicher,
  Concurrency und Billing auf Standardwerten (live nicht geprüft, gcloud war nicht freigegeben).
  Der Service heißt `fisherscreen-service`.

**Latenz je Ticker, `.info` kalt:** 590 s / 1501 ≈ **0,39 s** einschließlich Firestore get+set.
Die Rate ist flach, es gibt keine Stillstände. Es gibt also **kein Yahoo-Throttling (429/Crumb)**.
Die Grenze ist unsere eigene sequentielle Schleife. Bei EDGAR setzt dagegen das SEC-Limit
(10 req/s) die Grenze, da hilft Parallelisierung nicht.

## Was am 2026-11-01 kalt sein wird

- `dev_ticker_cache`: kalt (24 h) — **~600 s**
- `dev_edgar_cache`: **immer kalt** bei Monatsabstand > 7 d — **~600 s**
- Prepasses: nie gecacht — **~400–800 s**
- `dev_revenue_series`: am 11-01 sind **527** Universumseinträge abgelaufen, am 12-01 773.
  Rund zwei Drittel davon sind im Scoring → ~350 × 2 s ≈ **~700 s**, wenn vorher kein Backfill läuft.

**Prognose ohne Maßnahme: ~2300–2700 s** → Scheduler rot, nur ~15–20 min Puffer bis 3600 s.
Der Juli-Lauf (2380 s) zeigt, wie stark die Laufzeit streut.

## Optionen

| | Lauf 11-01 | Kosten | Bewegliche Teile | Fehler-Sichtbarkeit | Wachstum |
|---|---|---|---|---|---|
| (a) Pre-Warm per 2. Scheduler-Job | ~600 s, grün | 0 | +1 Job, TTL-Choreografie; Pre-Warm (= Dry-Run) ist selbst ~1500–1800 s kalt → läuft in **dieselbe** Deadline, außer man stückelt ihn | Job-Status bleibt aussagekräftig, solange beide in 1800 s passen | schlecht: Prepasses nicht vorwärmbar, Pre-Warm wächst mit |
| (b) Mehr Parallelität (`.info`-Pool 4) | ~1900–2300 s, rot | 0 | Thread-Pool; Thread-Sicherheit von yfinance 1.3 (geteilte Session/Crumb) | **Risiko:** 429 → `DataSourceError` → still in `unresolved` (`runner.py:370-372`), Lauf geht mit dünnerem Universum weiter | spart ~450 s, EDGAR nicht beschleunigbar |
| (c) 202 + Hintergrund-Task | läuft evtl. nicht zu Ende | Request-Billing drosselt CPU nach der Antwort; Instanz ohne offenen Request kann beendet werden → CPU dauerhaft zuteilen (Instanz-Billing) | gering | **schlecht:** Scheduler immer grün, egal was passiert | Laufzeitgrenze unklar |
| **(d) Cloud Run Job** | ~2500 s, **Job-Ausführung grün** | Free Tier (~2500 vCPU-s je Lauf) | +1 Job-Ressource, CLI-Einstieg, Image-Update in `deploy.yml` | **gut:** Exit-Code ≠ 0 → Ausführung „Failed“; Scheduler = „gestartet“ | Task-Timeout bis 24 h, unabhängig von 1800/3600 s |

Höhere Timeouts sind nicht möglich: Scheduler-HTTP hat höchstens 1800 s, Cloud Run-Request höchstens 3600 s (beides ist schon ausgereizt).

## Empfehlung: (d) Cloud Run Job

Das Problem liegt in der Struktur, nicht beim Cache. Drei gleich große Blöcke sind bei jedem
Monatslauf kalt, und jede neue Abfrage je Titel schiebt die Laufzeit weiter hoch. Pre-Warm
verlagert die Deadline nur auf einen zweiten Job. Mehr Parallelität spart höchstens ~450 s und
bringt ein stilles Ausdünnungsrisiko mit. Der Cloud Run Job entkoppelt die Laufzeit von beiden
Grenzen. Der Status wird wieder ehrlich: Die Ausführung schlägt fehl, wenn der Lauf fehlschlägt.
Damit ist das Backlog-Ticket `docs/superpowers/tickets/2026-06-03-toolA-run-as-cloud-run-job.md`
umgesetzt. (b) und die Prepass-Optimierung unten bleiben spätere, eigenständige Verbesserungen.

### Umsetzung — Code (ein PR, `refactor/monthly-run-job`)
1. Den Rumpf von `run_monthly` (`app/main.py:82-123`) nach `app/screener/monthly.py::run_monthly_pipeline(dry_run: bool) -> dict`
   extrahieren. Die Route ruft nur noch diese Funktion auf. Das ändert das Verhalten nicht.
2. Neuen Einstieg `app/monthly_job.py` (`main()`) anlegen: `configure_logging()`, Pipeline
   aufrufen, `sys.exit(1)` bei Exception oder `status != "success"`. Lokal aufrufen mit
   `uv run python -m app.monthly_job`.
3. Tests (qa-engineer): CLI ruft die Pipeline auf und liefert Exit-Code 0/1 (gemockt per DI).
   Die Route-Tests bleiben unverändert grün.

### Umsetzung — Infra (devops-engineer, nach dem Merge)
1. `gcloud run jobs create fisherscreen-monthly-job` mit demselben Image, Service-Account,
   denselben Secrets und Env-Vars wie der Service, Befehl `uv run python -m app.monthly_job`,
   `--task-timeout 7200`, `--max-retries 0`, `--tasks 1`.
2. In `deploy.yml` nach dem Service-Deploy `gcloud run jobs update … --image …:${{ github.sha }}`
   ergänzen. **Ohne diesen Schritt läuft der Job auf einem alten Image.**
3. Das Scheduler-Ziel von `fisherscreen-monthly` umstellen auf
   `https://run.googleapis.com/v2/projects/fisherscreen-prod/locations/europe-west3/jobs/fisherscreen-monthly-job:run`
   mit **OAuth** (statt OIDC). Der Jobname bleibt, damit die Budget-Stop-Function weiter
   denselben Job pausiert. IAM: Der Scheduler-SA braucht `run.jobs.run` auf dem Job. Rolle vor
   der Umsetzung prüfen.
4. Alarm bei fehlgeschlagener Job-Ausführung (Cloud Monitoring, E-Mail, kostenlos). Die
   HTTP-Route bleibt für manuelle Läufe und den Dry-Run erhalten.

### Spätere Optimierung (eigenes Ticket, optional)
Die Prepasses und `CachedRevenueSeries` brauchen nur `income_stmt`. Ein eigener
`get_income_statement` spart ~2/3 der ~800 s. Der Trajectory-Prepass könnte die Reihe aus
`dev_revenue_series` lesen. Das ist allerdings **keine** reine Strukturänderung, weil eine
gecachte Reihe bis zu 150 Tage alt sein kann.

## Notlösung für 2026-11-01 (falls (d) nicht rechtzeitig fertig wird)

Am **31.10. nachmittags**: der ticker-Cache muss jünger als 24 h sein, wenn der Lauf am 1.11.
um 05:00 MEZ = 04:00 UTC liest; die Sommerzeit endet am 25.10. Zuerst den Revenue-Backfill
laufen lassen, dann einen warmen Dry-Run (**ohne** Purge). Der Dry-Run füllt `dev_ticker_cache`
und `dev_edgar_cache` für $0, ohne Push:

```
uv run python -m scripts.backfill_revenue_series
gcloud run services proxy fisherscreen-service --region europe-west3 --port 8080
uv run python scripts\trigger_cold_dry_run.py http://localhost:8080
```

(Proxy in Fenster A, Trigger in Fenster B. Die Purge-Vorbedingung im Docstring des Skripts
hier **nicht** ausführen.) Erwartung für den Lauf am 1.11.: ~600 s, Scheduler grün. Ohne Dry-Run,
nur mit Backfill: ~1900 s, Job rot, Lauf fertig. Rot in Kauf nehmen ist vertretbar,
**wenn** danach `dev_screener_runs` (status, completed_at) und der Push geprüft werden.

## Offene Fragen an Stephan

1. (d) jetzt umsetzen oder bis nach dem 1.11. die Notlösung fahren?
2. Alarm bei Job-Fehlschlag per E-Mail gewünscht, oder genügt der Blick auf die Ausgaben?
3. Den EDGAR-TTL bei 7 Tagen lassen? Ein längerer TTL würde ~600 s sparen, aber
   Going-Concern-/Restatement-Signale später erkennen. Das ist eine fachliche Entscheidung.
4. Die Prepass-Optimierung (`income_stmt` only) als eigenes Ticket aufnehmen?
