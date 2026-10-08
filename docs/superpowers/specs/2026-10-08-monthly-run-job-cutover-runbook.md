# Runbook: Monatslauf auf Cloud Run Job umstellen

Stand 2026-10-08 · gehört zu `2026-10-08-monthly-run-deadline-design.md` (Option d)

Der Monatslauf (Tool A) läuft künftig als Cloud Run Job `fisherscreen-monthly-job`.
Bisher rief der Scheduler per HTTP `POST /run/monthly` auf dem Service auf. Nach dem Merge
legt `deploy.yml` den Job an bzw. aktualisiert ihn auf das neue Image. Die Umstellung des
Schedulers erfolgt **manuell**, und zwar nach diesem Runbook, in genau dieser Reihenfolge.

Alle Befehle sind für cmd.exe geschrieben. Mehrzeilige Befehle werden mit `^` fortgesetzt.

Feste Werte:

| | |
|---|---|
| Projekt | `fisherscreen-prod` |
| Region | `europe-west3` |
| Job | `fisherscreen-monthly-job` |
| Scheduler-Job | `fisherscreen-monthly` (Name bleibt, die Budget-Stop-Function pausiert ihn über den Namen) |
| Scheduler-SA | `fisherscreen-scheduler@fisherscreen-prod.iam.gserviceaccount.com` (laut `docs/infra/cloud-scheduler.md`, in Schritt 0 gegenprüfen) |
| Runtime-SA (Job und Service) | `fisherscreen-runtime@fisherscreen-prod.iam.gserviceaccount.com` |

```
gcloud config set project fisherscreen-prod
```

---

## Schritt 0: Ist-Zustand sichern (für den Rollback)

```
gcloud scheduler jobs describe fisherscreen-monthly --location europe-west3 --format=yaml > %USERPROFILE%\fisherscreen-scheduler-before-cutover.yaml
type %USERPROFILE%\fisherscreen-scheduler-before-cutover.yaml
```

Notiere aus der Ausgabe:

- `httpTarget.uri`: die Service-URL inkl. `/run/monthly`. Sie wird für den Rollback gebraucht.
- `httpTarget.oidcToken.serviceAccountEmail`: Das ist die Scheduler-SA. Weicht sie von der
  Tabelle oben ab, ersetze sie in **allen** folgenden Befehlen.
- `httpTarget.oidcToken.audience`: wird ebenfalls für den Rollback gebraucht.
- `schedule`, `timeZone`, `retryConfig.retryCount` (erwartet `0`), `attemptDeadline`.
  Diese Werte müssen nach der Umstellung unverändert sein.
- `state`: Steht hier `PAUSED`, war vorher der Budget-Stop aktiv. In dem Fall **abbrechen**
  und zuerst die Ursache klären.

## Schritt 1: Voraussetzung prüfen (PR gemergt, Deploy grün)

1. Der PR `feature/monthly-run-job` ist in `main` gemergt.
2. Der Workflow „Deploy to Cloud Run" für den Merge-Commit ist grün, **auch der Schritt
   „Deploy monthly job"** (GitHub → Actions).
3. Der Job existiert und läuft auf dem Image des Merge-Commits:

```
gcloud run jobs describe fisherscreen-monthly-job --region europe-west3 ^
  --format="yaml(spec.template.spec.template.spec.containers[0].image,spec.template.spec.template.spec.containers[0].command,spec.template.spec.template.spec.serviceAccountName,spec.template.spec.template.spec.timeoutSeconds,spec.template.spec.template.spec.maxRetries)"
```

Erwartung:

- `image` endet auf `app:<Merge-Commit-SHA>` (SHA aus `git log -1 origin/main`)
- `command` = `/app/.venv/bin/python`, `-m`, `app.monthly_job`
- `serviceAccountName` = Runtime-SA
- `timeoutSeconds: '7200'`, `maxRetries: 0`

Ist die Ausgabe leer oder das Format unklar, zeigt `gcloud run jobs describe fisherscreen-monthly-job --region europe-west3` ohne `--format` alles.

## Schritt 2: Testlauf als Dry-Run über den Job

Ein Dry-Run schreibt keinen `dev_screener_runs`-Eintrag, ruft kein Gemini auf und pusht nicht
nach GitHub. Er kostet $0 und füllt nebenbei `dev_ticker_cache` und `dev_edgar_cache`.
`--args` wird an den eingebauten Befehl angehängt, ausgeführt wird also
`python -m app.monthly_job --dry-run`.

```
gcloud run jobs execute fisherscreen-monthly-job --region europe-west3 --args=--dry-run --wait
```

`--wait` blockiert bis zum Ende. Kalt dauert das ~25–40 min. Ohne `--wait` kehrt der Befehl
sofort zurück. Den Status liest man dann so:

```
gcloud run jobs executions list --job fisherscreen-monthly-job --region europe-west3 --limit 5
gcloud run jobs executions describe <EXECUTION-NAME> --region europe-west3
```

Erfolg heißt: Die Ausführung steht auf **Succeeded** (in der Liste `✔` bzw. `SUCCEEDED: 1`)
und `--wait` endet ohne Fehler. **Failed** heißt: Der Prozess endete mit Exit-Code ≠ 0. Den
Grund zeigen die Logs:

```
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=fisherscreen-monthly-job" ^
  --freshness 2h --limit 100 --format "value(timestamp,severity,jsonPayload.message)"
```

Nur Fehler anzeigen: Filter um ` AND severity>=WARNING` ergänzen. Wie beim Service erwartet
man INFO-Zeilen für Basisfilter, EDGAR, Scoring und Output (letzterer ohne Push).

**Erst weitermachen, wenn der Dry-Run „Succeeded" ist.**

## Schritt 3: IAM — Scheduler-SA darf den Job starten

```
gcloud run jobs add-iam-policy-binding fisherscreen-monthly-job ^
  --region europe-west3 ^
  --member=serviceAccount:fisherscreen-scheduler@fisherscreen-prod.iam.gserviceaccount.com ^
  --role=roles/run.invoker
```

`roles/run.invoker` enthält neben `run.routes.invoke` auch `run.jobs.run` und
`run.jobs.runWithOverrides`. Eine stärkere Rolle wie `run.developer` ist dafür nicht nötig.
Die Bindung gilt nur für diesen einen Job, nicht projektweit. Die bestehende Bindung auf dem
Service bleibt bestehen: Rollback und manuelle HTTP-Läufe brauchen sie.

Prüfen:

```
gcloud run jobs get-iam-policy fisherscreen-monthly-job --region europe-west3
```

## Schritt 4: Scheduler-Ziel umstellen (HTTP → Jobs-API, OAuth statt OIDC)

```
gcloud scheduler jobs update http fisherscreen-monthly ^
  --location europe-west3 ^
  --uri="https://run.googleapis.com/v2/projects/fisherscreen-prod/locations/europe-west3/jobs/fisherscreen-monthly-job:run" ^
  --http-method=POST ^
  --oauth-service-account-email=fisherscreen-scheduler@fisherscreen-prod.iam.gserviceaccount.com ^
  --oauth-token-scope=https://www.googleapis.com/auth/cloud-platform
```

Warum OAuth: Ein `*.googleapis.com`-Endpunkt erwartet ein OAuth-Access-Token. Ein
OIDC-ID-Token wird dort abgelehnt (401). OIDC und OAuth schließen sich im Scheduler gegenseitig
aus, deshalb ersetzt das Setzen von OAuth das bisherige OIDC-Token. Schritt 5 prüft, ob davon
nichts übrig bleibt. Ein Body ist nicht nötig, `jobs:run` akzeptiert einen leeren POST.
`schedule`, `time-zone`, `retry`- und `attempt-deadline`-Einstellungen werden nicht angefasst,
ein `update` ändert nur die übergebenen Felder.

Zur Deadline: `jobs:run` antwortet sofort mit einer Operation und wartet nicht auf das Ende
des Laufs. Die 1800-s-Grenze des Schedulers spielt damit keine Rolle mehr.

## Schritt 5: Prüfen

```
gcloud scheduler jobs describe fisherscreen-monthly --location europe-west3 --format=yaml
```

Erwartung im Vergleich zu Schritt 0:

- `httpTarget.uri` = die `run.googleapis.com/...:run`-URL
- `httpTarget.httpMethod: POST`
- `httpTarget.oauthToken.serviceAccountEmail` = Scheduler-SA, **kein** `oidcToken`-Block mehr
- `schedule`, `timeZone`, `retryConfig.retryCount: 0` und `attemptDeadline` unverändert
- `state: ENABLED`

### Optional: echter Lauf sofort

**Nur auf ausdrücklichen Wunsch.** Der Lauf ist LLM-frei und kostet etwa $0, er ist aber ein
**voller Lauf**: Er schreibt einen `dev_screener_runs`-Eintrag und pusht die drei Monatsdateien
für **2026-10** erneut nach `main` (`chore: monthly screener output 2026-10 [skip ci]`).
Ohne diesen Lauf ist der erste echte Test der geplante Lauf am 01.11. um 05:00 MEZ.

```
gcloud scheduler jobs run fisherscreen-monthly --location europe-west3
```

Woran man den Erfolg erkennt, in dieser Reihenfolge:

1. **Scheduler-Versuch grün** (Console → Cloud Scheduler → „Letzte Ausführung“). Das bestätigt
   **nur**, dass der Job gestartet wurde, nicht dass der Lauf gelungen ist. Rot heißt hier fast
   immer IAM (Schritt 3) oder Token-Typ (Schritt 4).
2. **Job-Ausführung „Succeeded“:**
   ```
   gcloud run jobs executions list --job fisherscreen-monthly-job --region europe-west3 --limit 3
   ```
3. **Neuer `dev_screener_runs`-Eintrag** mit `status: success` (Firestore-Console, Collection
   `dev_screener_runs`, jüngste `run_id`).
4. **Push in GitHub:** neuer Commit `chore: monthly screener output 2026-10 [skip ci]` auf `main`.

Diese vier Punkte gelten auch nach dem geplanten Lauf am 01.11.

## Rollback

Die URI und die Audience stehen in der Datei aus Schritt 0. `<SERVICE-URL>` ist die URI
**ohne** `/run/monthly`.

```
gcloud scheduler jobs update http fisherscreen-monthly ^
  --location europe-west3 ^
  --uri="<SERVICE-URL>/run/monthly" ^
  --http-method=POST ^
  --oidc-service-account-email=fisherscreen-scheduler@fisherscreen-prod.iam.gserviceaccount.com ^
  --oidc-token-audience="<AUDIENCE aus Schritt 0>"
```

Danach `describe` wie in Schritt 5 ausführen. Erwartet wird wieder der Stand aus Schritt 0
(`oidcToken`, kein `oauthToken`). Damit gilt wieder die alte 1800-s-Grenze, siehe die
Notlösung im Design-Dokument. Job und IAM-Bindung können stehen bleiben, sie stören nicht.

## Hinweise

- **Die HTTP-Route `POST /run/monthly` bleibt bestehen**, für manuelle Läufe und den Dry-Run über
  den Service-Proxy (`scripts\trigger_cold_dry_run.py`). Für lange Läufe ist der Job-Weg aus
  Schritt 2 jetzt aber der bessere.
- **Budget-Hard-Stop:** Die Cloud Function `fisherscreen-budget-stop` pausiert den
  Scheduler-Job `fisherscreen-monthly` über seinen Namen (`infra/main.py`,
  `SCHEDULER_JOB_NAME`). Der Name bleibt gleich, deshalb muss dort nichts geändert werden.
  Ein pausierter Scheduler startet auch den Job nicht mehr. Ein manuelles
  `gcloud run jobs execute` umgeht den Stop allerdings.
- **Kein E-Mail-Alarm** (Entscheidung 2026-10-08). Ein fehlgeschlagener Lauf wird beim nächsten
  Lauf als Warnblock in den Monatsdateien sichtbar (`status` `running`/`aborted`/`partial` im
  jüngsten `dev_screener_runs`-Eintrag).
- **Image-Aktualität:** Jeder Deploy auf `main` aktualisiert den Job automatisch
  (`deploy.yml`, Schritt „Deploy monthly job"). Ist dieser Schritt rot, läuft der Job auf dem
  alten Image. Das heißt: auf den Schritt achten, nicht nur auf den Service-Deploy.
