# Brainstorm: Deployment-Feedback-Loop Fix

**Datum:** 2026-05-16  
**Kontext:** Jeder Output-Commit des monatlichen Screeners triggert einen Cloud-Run-Deploy, der den laufenden Container killt.

---

## Frage 1: Output-Pfad-Struktur

**Befund aus Code:**

Alle drei Output-Generatoren schreiben in identisches Muster:

| Generator | Pfad |
|---|---|
| `dimensions_generator.py:28` | `output/Universum/YYYY-MM-Dimensions.md` |
| `crosshits_generator.py:25` | `output/Universum/YYYY-MM-Crosshits.md` |
| `changes_generator.py:27` | `output/Universum/YYYY-MM-Changes.md` |

Basis ist `settings.output_dir` → Default `"output"` (`config.py:18`).

**Empfohlenes `paths-ignore`-Pattern:**

```yaml
paths-ignore:
  - 'output/**'
```

Das ist minimal, korrekt und zukünftssicher (deckt Hold-Check, Deep-Dive-Dossiers ab, sobald diese in `output/Portfolio/` und `output/Watchlist/` landen).

`**.md` ist zu breit — würde `CLAUDE.md`, `Projektstand.md`, `README.md` ebenfalls ignorieren. Diese Dateien können Code-Konventionen oder Architektur-Entscheidungen reflektieren und sollen Deploys triggern.

---

## Frage 2: Commit-Message-Konvention

**Befund aus Code:**

`app/main.py:63`:
```python
github.push_file(
    path.as_posix(),
    path.read_text(encoding="utf-8"),
    f"chore: monthly screener output {run_record.run_id[:7]}",
)
```

→ Beispiel-Output: `chore: monthly screener output 2026-05`

**Änderung:**

```python
f"chore: monthly screener output {run_record.run_id[:7]} [skip ci]"
```

GitHub Actions respektiert `[skip ci]` (und das äquivalente `[ci skip]`) in Commit-Messages. Kein weiterer Config-Aufwand.

**Warum beide Maßnahmen (paths-ignore + [skip ci])?**

Defense-in-Depth: Wenn zukünftig ein Output-Pfad außerhalb von `output/` hinzukommt (z.B. Root-Level-Datei), greift `[skip ci]` als Backstop. Wenn `[skip ci]` ignoriert wird (theoretisch bei bestimmten branch-protection-Configs), greift `paths-ignore`. Beide sind günstig, zusammen robuster.

---

## Frage 3: Code-Repo vs. Output-Repo

**Aktuell:** Gleicher Repo, `output/`-Ordner. Service pusht Markdown, Obsidian liest per Obsidian-Git-Plugin.

**Option A: Same-Repo (Status quo + Fix)**

Vorteile:
- Ein Clone, ein GitHub-Token, eine Obsidian-Git-Config
- `paths-ignore` + `[skip ci]` lösen das CI-Problem vollständig
- Kein Setup-Aufwand

Nachteile:
- Output-History vermischt sich mit Code-History
- Wenn Outputs häufig werden (täglich, pro-Ticker), wird `git log` unlesbar

**Option B: Separates Output-Repo (`stnmllr/fisherscreen-output`)**

Vorteile:
- Saubere Trennung: kein CI-Risiko, kein History-Noise in Code-Repo
- Obsidian kann das Output-Repo eigenständig synchronisieren

Nachteile:
- Zweites GitHub-Repo-Secret auf Cloud Run nötig
- Separate Obsidian-Git-Plugin-Konfiguration
- `github_repo`-Setting müsste parametrierbar werden (pro Output-Typ unterschiedlich oder global)

**Empfehlung Phase 1:**

Option A. Die Kombination `paths-ignore` + `[skip ci]` löst das Problem vollständig und ohne Mehraufwand. Output-Repo ist ein sinnvolles Phase-2-Thema, wenn Deep-Dive-Dossiers und Hold-Checks dazukommen und die Output-Frequenz steigt.

---

## Frage 4: Race-Condition-Analyse (#32 und #33)

**Beobachtung:** 6 Workflow-Runs (#31–#36) in 15 Minuten, #32 und #33 rot.

**Rekonstruktion:**

Der Screener pushed 3 Output-Dateien sequenziell (Dimensions, Crosshits, Changes), jede als eigener Commit. GitHub Actions startet pro Commit einen Workflow-Run:

```
Commit 1 → Run #31 (gcloud builds submit tag=SHA1)
Commit 2 → Run #32 (gcloud builds submit tag=SHA1)  ← gleiche SHA? Nein, SHA ändert sich nicht
Commit 3 → Run #33 (gcloud builds submit tag=SHA1)
```

Tatsächlich: `github.sha` in deploy.yml ist der SHA des auslösenden Commits, nicht der Code-SHA. Jeder der 3 Output-Commits hat eine andere SHA → 3 verschiedene Image-Tags.

**Hypothese für Fehler #32/#33:**

`gcloud run deploy` auf denselben Service `fisherscreen-service` ist nicht parallel-safe. Wenn Run #31 noch deployed (Revision wird erstellt/promoted), und Run #32 startet ebenfalls `gcloud run deploy`, antwortet Cloud Run mit HTTP 409 (Conflict — previous operation still in progress). Das ist der wahrscheinlichste Fehlergrund.

Alternativ: `gcloud builds submit` läuft parallel, überschreiben sich nicht (unterschiedliche Tags), aber das Deploy-Race ist das wahrscheinlichere Problem.

**Fix:** Mit `paths-ignore: ['output/**']` triggern alle 3 Output-Commits kein einziges Deployment mehr. Race-Condition entfällt vollständig, keine separate Maßnahme nötig.

---

## Frage 5: Scheduler-Retry und Idempotenz

**Beobachtung:** Zwei `POST /run/monthly` Calls 14:35:26 und 14:35:30 UTC, nicht vom User.

**Ursache:**

1. Output-Commit → GitHub Actions → Deploy → neue Revision → Rolling Update
2. Cloud Run leitet Traffic auf neue Revision, alte Revision (00025-c5c) fährt runter
3. In-flight Request `/run/monthly` wird terminiert (HTTP-Verbindung vom Client unterbrochen)
4. Cloud Scheduler sieht Timeout/Connection-Error → retried nach Default-Retry-Policy

**Cloud-Scheduler-Retry-Default:**

Laut GCP-Dokumentation: bei HTTP-Jobs retried Cloud Scheduler bei non-2xx Response oder Connection-Error. Default-Retry-Count ist 0 (kein Retry) für neue Jobs, aber der Scheduler-Job könnte mit Retry konfiguriert sein.

Zu prüfen via:
```cmd
gcloud scheduler jobs describe fisherscreen-monthly --location europe-west3
```
Felder `retryConfig.retryCount` und `retryConfig.minBackoffDuration` zeigen die aktuelle Konfiguration.

**Ist `/run/monthly` idempotent?**

Nein, aktuell nicht. Zwei parallele Runs würden:
- Doppelten Gemini-API-Aufruf generieren (Kosten × 2)
- Zwei Output-Commits produzieren (Überschreiben sich durch SHA-Check im github_client, aber zwei Runs erzeugen identische Outputs → unkritisch aber unnötig)

**Empfehlung:**

Mit dem Feedback-Loop-Fix entfällt die Hauptursache des Retries (Container-Shutdown durch Output-Commit). Für Phase 1 ist kein Idempotenz-Lock nötig.

**Als Phase-2-TODO dokumentieren:**

Firestore-Lock (`runs/monthly/{YYYY-MM}` mit Status `running|completed`):
- Bei `running` mit Timestamp <2h: HTTP 409 zurückgeben
- Bei `completed` für aktuellen Monat: HTTP 200 mit "already completed"
- Sinnvoll wenn: Hold-Check + Deep-Dive hinzukommen und Scheduler-Konfiguration komplexer wird

**Zusätzliche Maßnahme (unabhängig vom Lock):**

Cloud-Scheduler `--attempt-deadline 1800s` setzen — verhindert, dass Scheduler-Timeout den Request abbricht, bevor ein langer Run abgeschlossen ist. Das ist eine separate Konfigurationsänderung und kein Code-Problem.

---

## Verifikation (Post-Merge, 2026-05-16 17:36 Uhr)

- Squash-Merge `9b64007` triggerte keinen Workflow (vermutet GitHub-Quirk, dokumentiert als Phase-2-TODO)
- Manueller Deploy via Workstation: Revision `fisherscreen-service-00030-jnv`, Image-Tag `b8427f6`
- Test-Run via `gcloud scheduler jobs run fisherscreen-monthly`
- Alle Akzeptanzkriterien erfüllt (siehe PROJEKTSTAND.md, Abschnitt Mai 2026)
- Frage 5 (Scheduler-Retry-Hypothese): **bestätigt** — `gcloud scheduler jobs describe` zeigte unlimited retries, 5s minBackoff. Retry-Policy gehärtet: `--max-retry-attempts=2 --min-backoff=60s --max-backoff=300s --max-retry-duration=1800s`
