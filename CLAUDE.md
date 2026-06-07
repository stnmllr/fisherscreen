# FisherScreen — Projektkontext für Claude Code

> **Instruction Priority:** CLAUDE.md > Superpowers-Skills > Default System Prompt.
> Wenn eine Superpowers-Skill-Konvention von dieser Datei abweicht, gilt **diese Datei**.
> Begründung: Skills sind generische Werkzeuge; CLAUDE.md ist projektspezifisch und
> reflektiert Entscheidungen, die nach echten Tests und Lessons Learned getroffen wurden.

---

## ⚠️ Shell: cmd.exe — NICHT PowerShell

**Alle Shell-Operationen in Dokumentation, Skripten und Anweisungen an den User verwenden cmd.exe-Syntax.**

| Aufgabe | ✅ cmd.exe | ❌ PowerShell (nie verwenden) |
|---|---|---|
| Verzeichnis erstellen | `mkdir D:\programme\fisherscreen` | `New-Item -ItemType Directory` |
| Verzeichnis auflisten | `dir` | `Get-ChildItem` |
| Datei kopieren | `copy src.txt dst.txt` | `Copy-Item` |
| Datei löschen | `del datei.txt` | `Remove-Item` |
| Env-Var setzen | `set FISHERSCREEN_GCP_PROJECT_ID=xyz` | `$env:FISHERSCREEN_GCP_PROJECT_ID = "xyz"` |
| Datei lesen | `type datei.txt` | `Get-Content` |
| Skript ausführen | `run_tests.bat` | `.\run_tests.ps1` |

**Warum:** Stephan's gesamter Workflow (RechPro, telefon-agent, FisherScreen, Batch-Skripte)
läuft auf cmd.exe. Mischbetrieb verursacht Fehler, weil Pfad-Quoting, Pipe-Verhalten und
Quote-Escaping zwischen cmd und PowerShell unterschiedlich sind. Konsistenz > Eleganz.

Kein `&`-Call-Operator, keine `;`-Verkettung im PowerShell-Stil, keine `@"..."@`-Here-Strings —
das ist alles PowerShell und gehört hier nicht hin.

---

## Projektüberblick

FisherScreen ist ein persönliches Werkzeug, das Phil Fishers 15 Prinzipien aus
*Common Stocks and Uncommon Profits* (1958) systematisch auf öffentliche Aktien-Daten anwendet.
**Pull statt Push:** Tool B läuft nur, wenn Stephan es aktiv auslöst.

**Drei Töpfe:**
- **Universum** — ~1.322 Titel (S&P 500 + S&P 400 + STOXX Europe 600), Negativ-Filter → ~100
<!-- Count nach 0a-Dedup festgeschrieben (Cold-Dry-Run 2026-06-07: 1332 → 1322, RIC-/FR-
     Kontaminanten korrigiert). Composition an Code-Realität angeglichen: build_universe.py
     nutzt S&P 400, nicht das ursprünglich genannte Russell 1000 — ob S&P 400 oder Russell 1000
     gewollt ist, ist eine separate Entscheidung (nicht 0a). -->
- **Watchlist** — 5–15 Titel, manuell von Stephan
- **Portfolio** — tatsächlich gehaltene Titel, Hold-Check

**Zwei Tools:**
- **Tool A — Monthly Screener:** Monatlich automatisch via Cloud Scheduler. Negativ-Filter-Kaskade,
  Gemini Flash Lite Scoring (mit Hard-Caps), fünf Dimensions-Listen + Querliste als Markdown in Obsidian.
- **Tool B — Deep Dive:** Manuell via `fisherscreen deepdive <ticker>`. Hard + Soft Scuttlebutt,
  Sprach-/Tonalitäts-Analyse CEO-Briefe + Earnings Calls, Gemini-Synthesis gegen Fishers 15 Punkte.

**Referenzdokument:** `D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\FisherScreen_Architektur_v3.md`

---

## Tech-Stack

| Komponente | Technologie | Anmerkung |
|---|---|---|
| Backend | FastAPI (Python 3.12) | async/await durchgängig |
| Hosting | Cloud Run (europe-west3) | Free-Tier reicht |
| Datenbank | Firestore (Native Mode) | 2 Collections |
| Scheduler | Cloud Scheduler | 1 Job, gratis |
| Secrets | Secret Manager | Nie `.env` auf Cloud Run |
| LLM Bulk | Gemini Flash Lite | Tool A (Scoring, mit Hard-Caps) + Tool B |
| LLM Synthesis | Gemini Pro | Nur Tool B |
| Package Manager | uv | Nur FisherScreen — RechPro/telefon-agent bleiben pip |
| CI/CD | GitHub Actions | Deploy auf Cloud Run |
| Output | Markdown → GitHub → Obsidian Git Plugin | |
| Testing | pytest | Dependency-Injection-Pattern |

---

## Entwicklungsumgebung

- **Betriebssystem:** Windows 11
- **Shell:** `cmd.exe` (siehe Abschnitt oben)
- **Python-Aufruf:** IMMER `uv run python -m <modul>` — **nie `python3`, nie nacktes `python`.**
  - `python3` trifft auf dieser Maschine zuerst den WindowsApps-Store-Stub
    (`…\WindowsApps\python3.exe`, *vor* dem echten Interpreter im PATH) und öffnet die
    Microsoft-Store-Seite statt zu laufen. Es gibt kein venv-`python3`.
  - Nacktes `python` zeigt nur bei *aktiver* venv auf den richtigen Interpreter, sonst auf das
    globale `C:\Python314` → falsches Environment, lautlos.
  - `uv run python -m` umgeht das PATH-Lotto komplett (uv löst Interpreter + venv selbst auf)
    und dodgt zugleich die EPDR-.exe-Shim-Sperre (siehe SOPRA-EPDR).
- **Lokaler Repo-Pfad:** `D:\programme\fisherscreen\`
- **Python-Version:** 3.12, fixiert via `uv python pin 3.12` (`.python-version` im Repo-Root)

### uv-Grundbefehle (cmd.exe)

```
uv sync                              Abhängigkeiten aus uv.lock installieren
uv add <paket>                       Paket hinzufügen (aktualisiert pyproject.toml + uv.lock)
uv add --dev <paket>                 Dev-Abhängigkeit
uv run python -m pytest              Tests ausführen (siehe SOPRA-EPDR unten)
uv run python -m app.deepdive ...    Tool B CLI (siehe SOPRA-EPDR unten)
uv python pin 3.12                   Python-Version fixieren
```

### uv und Cloud Run

**Kein requirements.txt.** Cloud Run Deploys nutzen uv direkt im Dockerfile:

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
```

Falls ein Build-System explizit requirements.txt braucht:
```
uv export --format requirements-txt --no-dev -o requirements.txt
```
Das ist ein bewusster manueller Schritt — niemals automatisch generiert oder committed.

**Bestandsprojekte bleiben unverändert:** RechPro und telefon-agent verwenden weiterhin
`venv` + `pip` + `requirements.txt`. Keine Migration, kein Mischbetrieb.

---

## Architektur-Konventionen

### Service-Layer (Thin Wrappers)

Alle externen API-Calls laufen ausschließlich durch einen thin Wrapper. **Niemals direkter
API-Aufruf aus Tool-A- oder Tool-B-Logik heraus.**

```
services/
  yfinance_client.py      yfinance-Wrapper
  edgar_client.py         SEC EDGAR
  gemini_client.py        Gemini Flash Lite + Pro
  apify_client.py         Glassdoor / Kununu
  marketaux_client.py     News
  firestore_client.py     Firestore-Operationen
```

**Warum:** Tests mocken die Service-Klassen via Dependency-Injection. Kein echter Netzwerk-Call
in Unit-Tests. Wer einen direkten `yfinance.download()`-Aufruf in Tool-A-Code sieht: das ist ein Bug.

### Tool A / Tool B Separation

Tool A (Monthly Screener) verarbeitet das gesamte Universum
(~1.322 Stocks) automatisiert. Tool B (Deep Dive) läuft manuell
auf einzelne Stocks.

#### Kostenkontrolle Tool A

Tool A darf Gemini Flash Lite für Massen-Scoring verwenden, unter
folgenden nicht-verhandelbaren Bedingungen:

1. Hard Cap Ticker-Anzahl: max. 3.000 Ticker pro Run.
   Bei Überschreitung: Run-Abbruch mit AppError, kein Fallback.

2. Token-Budget pro Ticker: max. 3.000 Input, 1.000 Output Tokens.
   Bei Überschreitung: Ticker übersprungen, Warning geloggt,
   Run läuft weiter.

3. GCP Budget-Alerts (Setup ist Teil von Phase 1.3):
   - $5/Monat → E-Mail-Warnung
   - $10/Monat → Hard Stop via Cloud Function (deaktiviert
     Cloud Scheduler). Reaktivierung erfolgt ausschließlich manuell
     in der GCP Console nach Ursachenanalyse.

4. Erlaubte APIs in Tool A: yfinance (kostenfrei), Gemini Flash Lite.
   Verboten in Tool A: Gemini Pro, Search Grounding, andere
   LLM-Modelle, jede API mit Per-Request-Kosten über $0.001.

5. Logging-Pflicht: Jeder Run protokolliert in Firestore
   (Collection dev_screener_runs):
   - tickers_processed (int)
   - tokens_in_total (int)
   - tokens_out_total (int)
   - estimated_cost_usd (float)
   - run_id (string, ISO-Timestamp)
   - status (success | partial | aborted)

   Wird für monatlichen Soll-Ist-Vergleich genutzt.

Tool B (Deep Dive) hat keine API-Beschränkungen — Kosten sind dort
durch manuelle Bedienung implizit gekappt.

| API | Tool A | Tool B |
|---|---|---|
| yfinance | ✅ | ✅ |
| SEC EDGAR | ✅ | ✅ |
| Firestore | ✅ | ✅ |
| GitHub | ✅ | ✅ |
| Gemini Flash Lite | ✅ (mit Hard-Caps) | ✅ |
| Gemini Pro | ❌ BUG | ✅ |
| Apify (Glassdoor/Kununu) | ❌ BUG | ✅ |
| Marketaux | ❌ BUG | ✅ |

### Cost-Caps

Cost-Caps sind **Hard-Limits im Code**, nicht nur Config-Werte. Nimm nie an, dass der
Aufrufer sie setzt.

```python
GEMINI_MAX_TOKENS_PER_RUN = int(os.environ.get("FISHERSCREEN_GEMINI_TOKEN_CAP", "500000"))
APIFY_MAX_RUNS_PER_DEEPDIVE = int(os.environ.get("FISHERSCREEN_APIFY_RUN_CAP", "3"))
```

- Bei 80%-Erreichung: `logging.warning(...)` mit aktuellem Verbrauch
- Bei Überschreitung: `GeminiError` / `DataSourceError` — kein stilles Weiterlaufen
- Budget-Alert in GCP zusätzlich, aber nicht als Ersatz für Code-Caps

### Firestore Collections

<!-- ⚠️ TODO: dev_edgar_cache fehlt in dieser Tabelle, wird aber im Funnel-Cold-Run gepurgt.
     Falls Firestore-Collection → eintragen; falls lokaler File-Cache → "2 Collections" oben und
     "keine weiteren Collections" unten sind dann irreführend, klarstellen.
     Erledigt: dev_screener_runs ist jetzt auch im Kostenkontroll-Abschnitt konsistent benannt. -->
| Collection | Zweck | Schlüssel |
|---|---|---|
| `universe_cache` | yfinance-Daten mit TTL | ticker |
| `buy_snapshots` | Kennzahlen-Snapshot bei Kauf | ticker |
| `dev_gemini_scores` | Gemini-Scores per Ticker (TTL 30d) | ticker |
| `dev_screener_runs` | Cost-Tracking pro Run | run_id (ISO-Timestamp) |

Naming: snake_case lowercase. Keine weiteren Collections ohne explizite Architektur-Entscheidung.

---

## Konventionen

### Sprache

- **Code, Commits, Docstrings, Dateinamen, technische Bezeichner:** Englisch
- **Kommunikation mit dem User (Erklärungen, Zusammenfassungen, Rückfragen):** Deutsch
- **Domänen-Begriffe im Code:** Englisch — `universe`, `watchlist`, `portfolio`,
  `negative_filter`, `hold_check`, `deep_dive`, `dimensions_list`

### Git

**Kein `develop`-Branch.** Alle Branches gehen direkt in `main`.

**Branch-Typen** (kebab-case Englisch):

| Präfix | Wann |
|---|---|
| `feature/<beschreibung>` | Neue Funktionalität |
| `bugfix/<beschreibung>` | Fehlerbehebung |
| `refactor/<beschreibung>` | Umstrukturierung ohne Funktionsänderung |
| `chore/<beschreibung>` | Wartung, Dependencies, Dokumentation |
| `hotfix/<beschreibung>` | Produktions-Notfall (selten) |

```
✅ feature/apify-glassdoor-client
✅ bugfix/negative-filter-nan-on-missing-margin
✅ chore/update-uv-lock
❌ feature/ApifyGlassdoorClient
❌ bugfix/Apify-fix
```

- **Commits:** Englisch, Präsens, Imperativ — `"Add yfinance client wrapper"`,
  `"Fix EDGAR restatement flag logic"`, `"Add cost cap for Gemini token usage"`
- **Niemals direkt auf `main` committen** ohne explizite Freigabe von Stephan.
- **Tags:** `v0.1.0`, `v0.2.0` bei Phasen-Abschluss (Phase 1 → v0.1.0 etc.)

### Code-Stil

- **PEP 8**, Black-formatiert
- **Type Hints überall** — FastAPI und pytest-DI erfordern sie; keine ungetypten Funktionen
- **Kein `print()` in Produktiv-Code** — immer `logging` (siehe Logging-Abschnitt)
- Keine neue Abhängigkeit ohne explizite Diskussion (`uv add` → kurze Begründung)

### async/await-Konsistenz

Alle FastAPI-Routen sind `async def`. Keine synchronen Blocking-Calls in async Context:

```python
# ✅ richtig
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get(url)

# ❌ falsch — blockiert den Event-Loop
import requests
response = requests.get(url)
```

Für yfinance (kein async-Support): in `asyncio.to_thread()` wrappen oder aus async-Routen
heraus via Service-Layer aufrufen, der das kapselt.

### Fehlerbehandlung

**AppError-Hierarchie:**

```python
class FisherScreenError(Exception):
    """Basis-Exception für alle FisherScreen-Fehler."""

class DataSourceError(FisherScreenError):
    """Fehler bei externen Datenquellen: yfinance, EDGAR, Apify, Marketaux."""

class GeminiError(FisherScreenError):
    """Fehler bei Gemini-API-Calls (Flash Lite oder Pro)."""

class FilterConfigError(FisherScreenError):
    """Ungültige oder widersprüchliche Negativ-Filter-Konfiguration."""
```

**Regeln:**
- Externe APIs immer validieren — kein blindes Vertrauen auf Antwortstruktur
- `except Exception: pass` ist verboten
- Fehler explizit werfen (`raise DataSourceError(...)`) — niemals still schlucken
- Fail loud: lieber abbrechen als mit Phantomdaten weiterlaufen

### Logging

**Stdlib `logging` mit JSON-Formatter.** Kein `print()`, kein `loguru`.
Cloud Run erwartet strukturierte JSON-Logs für Cloud Logging.

```python
import json
import logging

class CloudJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "severity": record.levelname,      # Cloud Logging erwartet "severity", nicht "level"
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
        }
        # Trace-Korrelation: ohne dieses Feld keine Request-Korrelation in Cloud Logging
        trace = getattr(record, "trace", None)
        if trace:
            log_entry["logging.googleapis.com/trace"] = trace
        return json.dumps(log_entry)
```

Log-Level-Konvention:

| Level | Wann |
|---|---|
| `ERROR` / `CRITICAL` | Exceptions, Hard-Failures, Abbruch des Laufs |
| `WARNING` | Cost-Cap bei 80%, Fallback zu Backup-Quelle, fehlende Daten für einzelnen Titel |
| `INFO` | Start/Ende Tool-A-Lauf, Start/Ende Deep Dive, Negativ-Filter-Stufen-Ergebnis |
| `DEBUG` | Nur lokal — niemals in Produktiv-Deployment aktiv |

### Secrets und Umgebungsvariablen

**Env-Var-Prefix:** `FISHERSCREEN_` für alle projektspezifischen Variablen.

```
FISHERSCREEN_GCP_PROJECT_ID
FISHERSCREEN_FIRESTORE_COLLECTION_UNIVERSE
FISHERSCREEN_GEMINI_TOKEN_CAP
FISHERSCREEN_EDGAR_USER_AGENT
FISHERSCREEN_APIFY_API_KEY
FISHERSCREEN_GITHUB_TOKEN
```

**Auf Cloud Run:** Secrets ausschließlich via Secret Manager — niemals `.env` auf Cloud Run.
**Lokal:** `.env` erlaubt und in `.gitignore`. `.env.example` mit Platzhaltern wird versioniert.

---

## Tests

**pytest mit Dependency-Injection ab Phase 1.** Tests kommen nicht "später".

- Service-Klassen (`yfinance_client` etc.) via DI injiziert → in Tests mit Fixtures gemockt
- **Kein echter Netzwerk-Call in Unit-Tests** (kein echtes yfinance, kein echtes Firestore)
- Integration-Tests separat markiert: `@pytest.mark.integration`
- Test-Datei-Struktur spiegelt Source-Struktur:
  `tests/services/test_yfinance_client.py` für `services/yfinance_client.py`

```
uv run python -m pytest                          Unit-Tests
uv run python -m pytest -m integration           Integration-Tests (echte APIs)
```

Coverage-Threshold (90%) und Marker sind in `[tool.pytest.ini_options]` zentral konfiguriert —
kein `-cov`-Flag nötig.

### SOPRA-EPDR: keine .exe-Shims — `python -m <modul>` als kanonische Aufrufform

WatchGuard EPDR (SOPRA-Endpoint-Schutz) blockiert **alle** von uv generierten
`.exe`-Shims aus `venv\Scripts\` — nicht nur `pytest.exe`, sondern auch
`fisherscreen.exe` und jeden künftigen Console-Script-Shim. `python.exe` selbst
ist freigegeben. Workaround ist **nicht** shim-spezifisch: immer das Modul direkt
aufrufen.

| Zweck | ✅ kanonisch (lokal) | ❌ blockiert |
|---|---|---|
| Tests | `uv run python -m pytest` | `uv run pytest` |
| Integration-Tests | `uv run python -m pytest -m integration` | — |
| Tool B CLI | `uv run python -m app.deepdive deepdive <TICKER>` | `uv run fisherscreen ...` |

**Keine Heredocs, keine langen Inline-Skripte.** `python3 << 'EOF'` (Bash-Heredoc) läuft unter
cmd.exe ohnehin nicht, und lange `-c "..."`-Blöcke sprengen zudem CCs Befehls-Parser (erzwingen
manuelle Freigabe ab ~965 Byte). Diagnose- und Mehrzeilen-Skripte als `.py` unter `scripts/`
ablegen und mit `uv run python scripts\<name>.py` ausführen — kürzer, parsebar, kanonische
Invocation, und wiederverwendbare Checks werden so zu echten Tests statt Wegwerf-Kommandos.

Die `[project.scripts]`-Deklaration in `pyproject.toml`
(`fisherscreen = "app.deepdive.__main__:main"`) **bleibt** bestehen — sie gilt für
CI, Container und andere Maschinen ohne EPDR. Lokal auf der SOPRA-Maschine ist die
Aufrufkonvention `python -m <modul>`.

Zusätzlich blockiert der AV `coverage/tracer.cp312-win_amd64.pyd` (C-Extension für schnelles
Tracing). Coverage.py fällt dann automatisch auf den reinen Python-Tracer zurück — Tests und
Coverage-Messung funktionieren weiterhin korrekt, nur etwas langsamer. Keine Aktion nötig.

---

## Output-Dateinamen-Konventionen

Markdown-Outputs folgen festen Mustern (Cloud Run schreibt, Obsidian liest):

| Output | Pfad im Repo | Beispiel |
|---|---|---|
| Dimensions-Listen | `output/Universum/YYYY-MM-Dimensions.md` | `output/Universum/2026-06-Dimensions.md` |
| Crosshits | `output/Universum/YYYY-MM-Crosshits.md` | `output/Universum/2026-06-Crosshits.md` |
| Changes (Diff zum Vormonat) | `output/Universum/YYYY-MM-Changes.md` | `output/Universum/2026-06-Changes.md` |
| Hold-Check | `output/Portfolio/YYYY-MM-HoldCheck.md` | `output/Portfolio/2026-06-HoldCheck.md` |
| Deep-Dive-Dossier | `output/Watchlist/<TICKER>_YYYY-MM-DD.md` | `output/Watchlist/ASML.AS_2026-06-12.md` |

**Output-Container:** Alle generierten Markdowns liegen unter `output/`. Damit bleibt das
Repo-Root sauber (`app/`, `tests/`, `docs/` sind Geschwister von `output/`), und für
Phase 2 (Cloud Run) mappt `output/` 1:1 auf einen GCS-Bucket-Prefix.

**Drei Files pro Monatslauf** (Phase 1.4): Dimensions, Crosshits, Changes — bewusst statt
File-pro-Ticker. Begründung in `docs/superpowers/brainstorm/2026-05-15-phase-1-4-output-structure.md`.

---

## Multi-Agent-Setup

Claude Code als Orchestrator. Produktiv-Code wird an spezialisierte Sub-Agents delegiert —
Claude Code schreibt selbst keinen Produktiv-Code.

| Sub-Agent | Zuständigkeit |
|---|---|
| `backend-developer` | FastAPI, Firestore, Screener-Logik, CLI-Wrapper |
| `qa-engineer` | pytest, Fixtures, DI-Mocks, Coverage |
| `devops-engineer` | Dockerfile, GitHub Actions, Cloud Run Deploy, Cloud Scheduler |
| `software-architect` | Architektur-Entscheidungen, Refactoring-Strategie |

Sub-Agents kommunizieren nicht miteinander — Claude Code ist das Drehkreuz.
Aufgaben-Briefings auf Englisch sind in Ordnung; Berichte an Stephan auf Deutsch.

---

<!-- ⚠️ TODO: Phasen-Framing veraltet. GICS vs. ICB ist faktisch entschieden (der Code nutzt
     gics_sector). Tool A läuft seit Mitte Mai 2026 produktiv. Diesen Abschnitt + die
     "drei Monate Produktiv-Betrieb"-Klausel unten reconcilen. -->
## Offene Punkte vor Phase 1

Diese Punkte sind bewusst noch offen — vor dem jeweiligen Phasen-Start klären:

1. **GICS vs. ICB** (vor Phase 1) — yfinance liefert GICS-Sektoren. Konsistenz für
   Branchenmedian-Berechnung festlegen. Empfehlung: GICS, da yfinance-nativ.
2. **Earnings-Call-Transkript-Quelle** (vor Phase 3) — SEC EDGAR hat keine Transkripte.
   Optionen: Quartr-API, Investor-Relations-PDFs, Seeking Alpha. Entscheidung ausstehend.
3. **F&E-Quote Branchen** (vor Phase 1) — Vorschlag: GICS 35 (Health Care) + 45 (IT).
   Bestätigen nach erstem Lauf.
4. **portfolio_normalized.json Schema** (vor Phase 2) — Schnittstelle zum Portfolio-Analyzer
   noch nicht spezifiziert.

---

## Was wir NICHT bauen

- Keine eigene Web-UI — Obsidian + Portfolio-Analyzer reichen
- Kein Composite-Scoring in Tool A — fünf Dimensions-Listen nebeneinander (V3-Entscheidung)
- Kein tägliches Monitoring, kein automatisches Watchlist-Monitoring
- Kein Backtesting
- Keine Multi-User-Logik
- Kein Feature-Creep vor drei Monaten Produktiv-Betrieb