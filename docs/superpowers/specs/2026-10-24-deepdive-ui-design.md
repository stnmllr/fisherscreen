# Deep-Dive-Oberfläche: Vorprüfung + Start von Tool B aus dem Browser

Stand 2026-10-24 · Entscheidung Stephan · Stand des Codes: `main` @ `4cb713c`

## Problem

Tool B wird heute von Hand gestartet:

```
uv run python -m app.deepdive deepdive <TICKER> --peers A,B,C [--peer-rationale ...] [--no-cache] [--no-insider] [--site]
```

Ob der Ticker überhaupt existiert, entscheidet sich erst **im** Lauf: `ADRResolver.resolve()`
wirft für ein unbekanntes US-Symbol `DeepDiveError` (Exit 1), ein EU-Symbol wird über
OpenFIGI aufgelöst, die drei Peers prüft `peer_preflight._validate_resolvable` gegen yfinance.
Das alles kostet nichts (kein Gemini), passiert aber erst nach dem Start — ein Tippfehler
heißt: Lauf anstoßen, warten, Fehlermeldung lesen, nochmal. Außerdem muss man sich an die
Flags und das Peer-Format erinnern, und die zuletzt verwendeten Peers eines Tickers liegen
zwar in Firestore (`dev_deepdive_peers`), sind aber von der Kommandozeile aus unsichtbar.

Der Viewer (`app/viewer/`) ist bewusst reine Anzeige. CLAUDE.md sagt ausdrücklich: „Deep Dive
aus der App anstoßen … braucht eine eigene Entscheidung." Dieses Dokument ist diese Entscheidung.

## Entscheidung

Es gibt eine **kleine Weboberfläche** `app/deepdive_ui/`, die genau drei Dinge kann:

1. Eingaben für einen Deep Dive entgegennehmen (Ticker, drei Peers, Begründung, Flags).
2. **Vorprüfen**, bevor Geld ausgegeben wird: existieren Ticker und Peers, und was für ein
   Dossier käme heraus (vollständig / nur Quant / gar keins)?
3. Den Lauf **starten** — als Hintergrundprozess mit exakt dem heutigen CLI-Aufruf — und
   Fortschritt, Ergebnis und Verlauf anzeigen.

Mitentschieden (2026-10-24):

- **FastAPI im FisherScreen-Repo, nicht Flask aus RechPro.** Die Oberfläche muss Resolver und
  yfinance-Client *importieren*, also im uv-Umfeld von FisherScreen leben; FastAPI und uvicorn
  sind schon Abhängigkeiten. Von RechPro wird das **Betriebsmuster** übernommen (eine
  server-gerenderte Seite, lokal per `uv run`, auf Hetzner als systemd-Dienst hinter Caddy +
  oauth2-proxy, ohne Docker), nicht das Framework.
- **Jinja2** kommt als eine neue Laufzeit-Abhängigkeit dazu (`uv add jinja2`). Begründung:
  Formular + Statusanzeige + Verlauf sind als f-Strings (Viewer-Stil) nicht mehr lesbar.
  Es bleibt die einzige neue Abhängigkeit — Formulare werden per `fetch()` als JSON
  geschickt, damit `python-multipart` nicht nötig ist.
- **Quant-only-Fälle dürfen gestartet werden**, aber nur mit ausdrücklichem Haken
  („Ich weiß, dass es kein SEC-Filing gibt — nur Quant-Dossier bauen").
- **Die CLI bleibt der eigentliche Lauf.** Die Oberfläche ruft sie als Unterprozess auf.
  Kein zweiter Code-Pfad für den Deep Dive, keine Pipeline-Logik in der UI.

## Nicht-Ziele

- Kein Einbau in `app/main.py` (Cloud-Run-Dienst). Die UI ist ein eigener Prozess mit eigenem
  Entry-Point; Cloud Run bekommt sie nie zu sehen.
- Kein Git-Push der Dossiers aus der UI heraus. Lokal landet das Dossier wie heute in
  `output/Watchlist/` und geht den gewohnten Weg; auf Hetzner ist der Rückweg in den Vault
  Phase 2 (siehe unten).
- Keine Parallel-Läufe. Ein Lauf zur Zeit — das deckt sich mit „Kosten durch manuelle
  Bedienung gekappt".
- Keine Benutzerverwaltung, kein eigener Login. Lokal lauscht der Dienst nur auf
  `127.0.0.1`; auf Hetzner steht das vorhandene Google-Gate davor.
- Kein Umbau des Viewers. Die UI verlinkt nur dorthin.
- Kein Abbrechen laufender Prozesse aus der UI in v1 (Gemini-Kosten sind beim Abbruch ohnehin
  schon entstanden; ein halbfertiger Lauf hinterlässt nichts Falsches, nur nichts).

## Aufbau

```
app/deepdive/preflight.py          Vorprüfung als reine Funktion (DI, testbar), auch CLI-Unterbefehl
app/deepdive_ui/
  __init__.py
  __main__.py                      `uv run python -m app.deepdive_ui` → uvicorn auf 127.0.0.1:8765
  server.py                        FastAPI-App, Routen, Jinja2-Templates
  runs.py                          RunManager: Unterprozess starten, Log schreiben, Status halten
  templates/index.html             die eine Seite
  templates/_run.html              Status-Teilansicht (wird per Polling nachgeladen)
runs/                              Laufprotokolle (JSON + Log je Lauf), gitignored
```

### 1. Vorprüfung — `app/deepdive/preflight.py`

Reine Funktion, bekommt alle Abhängigkeiten injiziert (gleiches Muster wie `run_deep_dive`):

```python
@dataclass(frozen=True)
class SymbolCheck:
    symbol: str
    ok: bool
    name: str | None          # shortName/longName aus yfinance
    currency: str | None
    market_cap: float | None
    message: str              # eine Zeile für den Menschen, deutsch

@dataclass(frozen=True)
class PreflightResult:
    ticker: SymbolCheck
    peers: list[SymbolCheck]                 # genau 3
    dossier_kind: Literal["full", "quant_only", "none", "unknown"]
    dossier_note: str                        # z. B. "20-F via ADR NVO (CIK 0000353278)"
    no_sec_source_reason: str | None         # aus ResolvedTicker, wenn quant_only
    can_start: bool                          # ticker.ok und alle peers.ok und dossier_kind != "none"
    needs_quant_only_ack: bool               # dossier_kind == "quant_only"

def run_preflight(
    ticker: str,
    peers: list[str],
    *,
    resolver: Any,            # ADRResolver (build_adr_resolver())
    yfinance: Any,            # YFinanceClient
    edgar_map_available: Callable[[], bool],
) -> PreflightResult: ...
```

Regeln:

- **Peers:** genau drei, nicht leer, keine Dubletten, keiner gleich dem Ticker. Jeder Peer
  wird über `yfinance.get_ticker_info()` geprüft — dieselbe Prüfung wie
  `peer_preflight._validate_resolvable`, nur ohne Abbruch beim ersten Fehler: alle drei
  werden geprüft und einzeln gemeldet. `DataSourceError`/`DegradedDataError` → `ok=False`
  mit der Fehlermeldung, kein Durchreichen.
- **Ticker, Schritt 1 (yfinance):** wie Peers. Ohne yfinance-Treffer gibt es kein Quant,
  also kein Dossier → `dossier_kind="none"`.
- **Ticker, Schritt 2 (Resolver):** `resolver.resolve(ticker)`:
  - liefert `has_filing_source` → `"full"`, Note aus `form_type`/`adr_ticker`/`cik`;
  - liefert `no_sec_source_reason` → `"quant_only"`, Note = `no_sec_source_note`;
  - wirft `DeepDiveError` (US-Symbol nicht in der SEC-Map) → `"none"`, Note = Meldung
    plus Hinweis „Schreibweise prüfen (US-Klassen ohne Punkt: BRK-B) oder Eintrag in
    `data/adr_table.json`";
  - wirft `DataSourceError` (OpenFIGI/EDGAR vorübergehend weg) → `"unknown"`,
    `can_start=False`, Note „Quelle nicht erreichbar, später erneut prüfen". **Nicht**
    als „existiert nicht" ausgeben — Ausfall ≠ leer.
- **Stolperstein SEC-Map:** `EdgarClientImpl.get_cik()` gibt `None` zurück, wenn die
  `company_tickers.json` nicht geladen werden konnte — für den Resolver sieht das aus wie
  „Ticker unbekannt". Deshalb bekommt `EdgarClientImpl` eine kleine öffentliche Methode
  `ticker_map_available() -> bool` (lädt die Map bei Bedarf, `False` bei Ladefehler). Die
  Vorprüfung ruft sie **vor** dem Resolver; ist sie `False`, wird für undotted Ticker
  `"unknown"` statt `"none"` gemeldet. Ohne diesen Griff würde ein SEC-Schluckauf als
  Tippfehler angezeigt.
- Die Vorprüfung ruft **nie** Gemini, schreibt **nie** nach Firestore und legt **keine**
  Peers ab. Das Speichern der Peers bleibt Sache der CLI (`_persist` in `peer_preflight`),
  damit es genau eine Stelle gibt, die `dev_deepdive_peers` schreibt.
- Dauer: Peers und Ticker gegen yfinance sind 4 Netzaufrufe, der Resolver für ein EU-Symbol
  ohne Cache ein paar Sekunden. Kein Caching in der UI — der Lauf danach wärmt die Caches
  ohnehin.

**CLI-Unterbefehl dazu** (gleicher Parser in `app/deepdive/__main__.py`):

```
uv run python -m app.deepdive preflight NOVO-B.CO --peers LLY,PFE,MRK
```

Gibt die Prüfung als Text aus, Exit 0 wenn `can_start`, sonst 1. Nützlich auch ohne Browser
und macht die Vorprüfung unabhängig von der UI testbar und nutzbar.

### 2. Läufe — `app/deepdive_ui/runs.py`

```python
@dataclass
class RunRecord:
    run_id: str               # "2026-10-24T20-31-07_NOVO-B.CO"
    ticker: str
    peers: list[str]
    rationale: str | None
    flags: dict[str, bool]    # no_cache, no_insider, site
    quant_only_ack: bool
    started_at: str
    finished_at: str | None
    exit_code: int | None
    status: Literal["running", "ok", "failed"]
    dossier_path: str | None  # aus der Zeile "Dossier written to: ..." geparst
    log_path: str
```

- `RunManager.start(request) -> RunRecord` baut die Argumentliste **aus den Feldern**, nie
  aus einem zusammengesetzten String:
  `[sys.executable, "-m", "app.deepdive", "deepdive", ticker, "--peers", ",".join(peers)]`
  plus `--peer-rationale`, `--no-cache`, `--no-insider`, `--site` je nach Flag.
  `sys.executable` ist der Interpreter der laufenden uv-Umgebung — damit läuft der
  Unterprozess in derselben venv wie die UI, lokal wie auf dem Server, und es gibt keine
  Abhängigkeit vom `uv`-Binary im PATH des Dienstes. `cwd` = Repo-Root (Caches, `output/`,
  `.env` werden relativ aufgelöst). Umgebung: die eigene plus `PYTHONUNBUFFERED=1`, damit das
  Log live ankommt. `stdin` = `DEVNULL`, dadurch ist `is_tty` falsch und die CLI verlangt
  `--peers` — genau das, was wir übergeben.
- stdout und stderr gehen zusammen in `runs/<run_id>.log`; die Metadaten in
  `runs/<run_id>.json`, bei Start und bei Ende geschrieben. Kein SQLite — zwei Dateien pro
  Lauf reichen für einen Einzelnutzer und sind mit `type` lesbar.
- **Ein Lauf zur Zeit.** Der Manager hält den laufenden Prozess im Speicher; `start()` bei
  laufendem Prozess → `RunBusyError` (neue Exception in `app/errors.py`, Unterklasse von
  `FisherScreenError`) → HTTP 409. Nach Neustart des Dienstes gilt ein `running`-Eintrag,
  dessen Prozess nicht mehr existiert, als `failed` mit Hinweis „Dienst wurde neu gestartet".
- Ende des Prozesses wird von einem Hintergrund-Thread (`Popen.wait()`) festgestellt;
  Exit-Code-Übersetzung aus `app/deepdive/__main__.py` übernehmen:
  0 ok · 1 Ticker/Peers (`DeepDiveError`) · 2 Datenquelle · 3 Gemini · sonst „unerwartet".
- `RunManager.list(limit=20)` liest die JSON-Dateien, neueste zuerst.
- `RunManager.tail(run_id, max_bytes=16_000)` liefert das Log-Ende für die Anzeige.

### 3. HTTP — `app/deepdive_ui/server.py`

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/` | Seite mit Formular, aktuellem Lauf, Verlauf |
| GET | `/api/peers/{ticker}` | zuletzt gespeicherte Peers + Begründung aus `dev_deepdive_peers` (Firestore), `{}` wenn keine |
| POST | `/api/preflight` | JSON `{ticker, peers[3]}` → `PreflightResult` als JSON |
| POST | `/api/runs` | JSON `{ticker, peers, rationale, no_cache, no_insider, site, quant_only_ack, preflight_token}` → 201 + `RunRecord`; 409 wenn ein Lauf läuft; 422 wenn die Vorprüfung fehlt |
| GET | `/api/runs` | Verlauf |
| GET | `/api/runs/{run_id}` | Status + Log-Ende |
| GET | `/runs/{run_id}` | HTML-Teilansicht für das Polling (`_run.html`) |
| GET | `/health` | `{"status": "ok"}` |

- **Start nur nach bestandener Vorprüfung.** Der Server merkt sich pro erfolgreichem
  Preflight einen kurzlebigen Token (Ticker + Peers + Zeitstempel, 15 min gültig, im
  Speicher). `POST /api/runs` ohne passenden Token → 422. So kann niemand — auch kein
  JavaScript-Fehler — am Preflight vorbei starten. Bei `needs_quant_only_ack` muss
  `quant_only_ack=true` mitkommen, sonst 422.
- Alle Routen `async def`; yfinance/EDGAR/Firestore laufen über `asyncio.to_thread()`
  (CLAUDE.md-Regel, keine blockierenden Aufrufe im Event-Loop).
- Abhängigkeiten (Resolver, yfinance, Firestore, RunManager) hängen an `app.state` und
  werden in `create_app(...)` übergeben — Tests reichen Fakes hinein, kein Netzwerk.
- `root_path` aus Setting (siehe Konfiguration), damit der Dienst hinter Caddy unter einem
  Unterpfad laufen kann.

### 4. Die Seite — `templates/index.html`

Eine Seite, drei Kästen von oben nach unten, kein Framework, ein `<script>` mit `fetch()`:

1. **Eingabe:** Ticker · Peer 1–3 · Begründung (≤ 200 Zeichen, wie `_RATIONALE_MAX`) ·
   Haken „Caches ignorieren (`--no-cache`)", „Insider-Stufe überspringen (`--no-insider`)",
   „Viewer danach neu bauen (`--site`)". Beim Verlassen des Ticker-Felds `GET /api/peers/…`;
   gibt es gespeicherte Peers, werden sie eingetragen und mit Datum angezeigt
   („zuletzt 2026-09-04: LLY, PFE, MRK").
2. **Vorprüfung:** Button „Prüfen". Ergebnis als Tabelle — je Zeile Symbol, ✓/✗, Name,
   Währung, Market Cap, Meldung. Darunter das Dossier-Urteil in einem Satz:
   „Vollständiges Dossier: 20-F via ADR NVO" / „Nur Quant-Dossier: kein SEC-Jahresformular
   (Grund …)" / „✗ Kein Dossier möglich: …" / „? Quelle nicht erreichbar". Bei „nur Quant"
   erscheint der Bestätigungshaken. Der Start-Button ist bis zur grünen Prüfung
   deaktiviert; **jede Änderung an Ticker oder Peers setzt die Prüfung zurück.**
3. **Lauf:** Button „Deep Dive starten". Danach: Status (läuft seit …), Log-Ende in einem
   `<pre>`, alle 3 s per Polling nachgeladen (`GET /runs/{id}`), bis `status != running`.
   Am Ende: Exit-Code übersetzt, Pfad des Dossiers, Link auf den Viewer
   (`{viewer_url}/ticker/{TICKER}.html`, nur wenn `--site` gesetzt war oder der Viewer
   ohnehin extern gebaut wird — der Link ist ein Komfort, keine Zusage).
   Darunter der **Verlauf** (letzte 20 Läufe: Zeit, Ticker, Peers, Status, Dossier).

Gestaltung: schlicht, lesbar auf dem Handy (eine Spalte, 16 px Rand), System-Schrift,
keine externen Skripte oder Fonts — die Seite läuft später hinter einem Gate, da soll
nichts nachladen müssen.

### 5. Konfiguration (`app/config.py`, Prefix `FISHERSCREEN_`)

| Setting | Default | Zweck |
|---|---|---|
| `deepdive_ui_host` | `127.0.0.1` | nie `0.0.0.0` als Default — lokal soll nichts von außen erreichbar sein |
| `deepdive_ui_port` | `8765` | |
| `deepdive_ui_root_path` | `""` | z. B. `/deepdive` hinter Caddy |
| `deepdive_ui_runs_dir` | `runs` | Laufprotokolle |
| `deepdive_ui_viewer_url` | `""` | z. B. `https://macro.stnmllr.com/fisher`; leer = kein Link |
| `deepdive_ui_preflight_ttl_minutes` | `15` | Gültigkeit des Preflight-Tokens |

`.env.example` um die Zeilen ergänzen; `/runs/` in `.gitignore` (root-anchored, wie
`/output/`).

### 6. Tests (`tests/deepdive/test_preflight.py`, `tests/deepdive_ui/`)

Alles mit Fakes, kein Netz:

- Preflight: drei gültige Peers / einer ungültig / Dublette / Peer = Ticker; Resolver
  liefert full / quant_only / wirft `DeepDiveError` / wirft `DataSourceError`; SEC-Map
  nicht verfügbar → `unknown`, nicht `none`; `can_start` und `needs_quant_only_ack`
  für jede Kombination.
- CLI: `preflight`-Unterbefehl parst, Exit 0/1 — im Stil von `tests/deepdive/test_cli.py`.
- RunManager: startet ein kleines Fixture-Skript (`tests/deepdive_ui/fake_deepdive.py`,
  das „Dossier written to: …" druckt und mit wählbarem Exit-Code endet — der Befehl ist
  injizierbar, damit der Test nicht die echte CLI startet); Log und JSON entstehen;
  zweiter Start während des ersten → `RunBusyError`; Status nach Ende korrekt;
  verwaister `running`-Eintrag nach „Neustart" → `failed`.
- Routen über `fastapi.testclient.TestClient` (httpx ist vorhanden): Preflight-Token-Pflicht
  (422 ohne), Quant-only-Haken-Pflicht, 409 bei laufendem Prozess, `/api/peers` mit und ohne
  Firestore-Eintrag.
- Coverage-Schwelle 90 % bleibt; `app/deepdive_ui/` ist Teil von `app/`, also voll im Maß
  und in `black .`.

### 7. Betrieb

**Lokal (cmd.exe):**

```
uv add jinja2
uv sync
uv run python -m app.deepdive_ui
```

Browser: `http://127.0.0.1:8765/`. Voraussetzungen wie heute für die CLI: `.env` mit
`FISHERSCREEN_GEMINI_API_KEY`, `FISHERSCREEN_EDGAR_USER_AGENT`, GCP-Zugang (ADC) für
Firestore.

**Hetzner (`tools-prod-01`), Phase 1 — Dienst läuft, Dossiers bleiben auf dem Server:**

- Checkout nach `/opt/fisherscreen` (User `stef`), `uv sync --no-default-groups`.
- Zugangsdaten in `/etc/fisherscreen/env` (Rechte 0600): `FISHERSCREEN_GEMINI_API_KEY`,
  `FISHERSCREEN_EDGAR_USER_AGENT`, `FISHERSCREEN_GCP_PROJECT_ID`,
  `GOOGLE_APPLICATION_CREDENTIALS=/etc/fisherscreen/sa.json` (Service-Account mit
  Firestore-Lese-/Schreibrecht auf `dev_deepdive_peers`, `dev_ticker_cache`,
  `dev_gemini_scores`), `FISHERSCREEN_DEEPDIVE_UI_ROOT_PATH=/deepdive`,
  `FISHERSCREEN_DEEPDIVE_UI_VIEWER_URL=https://macro.stnmllr.com/fisher`.
  Das ist kein Widerspruch zu „nie `.env` auf Cloud Run" — hier ist nicht Cloud Run, und
  `EnvironmentFile=` in systemd ist das RechPro-Muster.
- systemd-Unit `fisherscreen-deepdive.service`: `WorkingDirectory=/opt/fisherscreen`,
  `EnvironmentFile=/etc/fisherscreen/env`,
  `ExecStart=/opt/fisherscreen/.venv/bin/python -m app.deepdive_ui`, `Restart=on-failure`.
  (Auf dem Server gibt es kein EPDR — der direkte venv-Interpreter ist hier die saubere
  Form; `uv run` würde beim Start neu syncen wollen.)
- Caddy (im macro-dashboard-Repo, wie der Viewer): `handle /deepdive/*` hinter
  `import authgate`, `reverse_proxy 127.0.0.1:8765`. Dieselben Fallen wie beim Viewer-Deploy
  (Ticket 2026-08-20): `-t` für sudo, Login im frischen Privatfenster probieren.
- Die Caches unter `cache/` sind auf dem Server anfangs leer; der erste Lauf je Ticker
  dauert länger. Das Dossier liegt danach in `/opt/fisherscreen/output/Watchlist/`.

**Hetzner, Phase 2 (eigene Entscheidung, nicht Teil dieser Spec):** Rückweg der Dossiers in
den Vault — Deploy-Key mit Push-Recht und `git commit && git push` nach erfolgreichem Lauf,
oder Abholen per `scp` am PC. Bis dahin ist der Server-Betrieb für „unterwegs mal einen Lauf
anstoßen und im Viewer lesen" brauchbar, nicht für den Vault.

### 8. Änderung an CLAUDE.md (im selben PR)

Im Abschnitt „Was wir NICHT bauen" den Viewer-Punkt ergänzen:

> **Revidiert 2026-10-24:** Es gibt zusätzlich eine kleine Start-Oberfläche
> (`app/deepdive_ui/`), die einen Deep Dive **vorprüft und anstößt** — als Unterprozess der
> CLI, ein Lauf zur Zeit, lokal auf `127.0.0.1`, auf Hetzner hinter dem Google-Gate. Grenze:
> sie rechnet nichts, zeigt keine Dossier-Inhalte (das bleibt der Viewer) und schreibt nicht
> nach Firestore. Spec: `docs/superpowers/specs/2026-10-24-deepdive-ui-design.md`.
> Vergleichs-/Verlaufsansichten über Dossiers hinweg bleiben Feature-Creep.

Außerdem in der Tabelle „Tool B CLI" den neuen Unterbefehl `preflight` und den Start
`uv run python -m app.deepdive_ui` aufnehmen.

## Umsetzungsreihenfolge (ein Branch `feature/deepdive-ui`, drei PR-fähige Schritte)

1. **`preflight.py` + `ticker_map_available()` + CLI-Unterbefehl** mit Tests. Das ist für
   sich schon nützlich und ohne UI prüfbar:
   `uv run python -m app.deepdive preflight NOVO-B.CO --peers LLY,PFE,MRK`.
2. **`runs.py` + `server.py` + Templates**, `jinja2` hinzufügen, `/runs/` in `.gitignore`,
   Settings, `.env.example`. Lokal gegen einen echten, billigen Lauf abnehmen
   (`--no-insider`, bekannter Ticker mit warmem Cache).
3. **CLAUDE.md + Projektstand.md** nachziehen; Hetzner-Deploy von Hand nach Abschnitt 7
   (bewusst ohne Deploy-Code, wie beim Viewer).

## Abnahme

- Tippfehler-Ticker (`NOVOB.CO`, `APLE`) → Prüfung rot, Start-Button bleibt gesperrt, **kein**
  Prozess gestartet, kein Gemini-Aufruf (Log leer).
- `EDV.L` (bekannter Quant-only-Fall) → „nur Quant", Start nur mit Haken, Lauf endet mit
  Exit 0 und Quant-Dossier.
- US-Ticker bei abgeschalteter SEC-Map (im Test per Fake) → „Quelle nicht erreichbar",
  nicht „existiert nicht".
- Zweiter Start während eines Laufs → 409 und sichtbare Meldung, der erste Lauf läuft
  ungestört weiter.
- Peers eines schon einmal gelaufenen Tickers werden vorgeschlagen; Begründung ≤ 200 Zeichen.
- `uv run python -m pytest` grün, Coverage ≥ 90 %, `uv run python -m black --check .` sauber.
- Nach Dienst-Neustart zeigt der Verlauf den unterbrochenen Lauf als „failed — Dienst neu
  gestartet", nicht als ewig „running".

## Offene Punkte (bewusst nicht entschieden)

- Abbrechen eines laufenden Prozesses aus der UI (Button „Stop"): erst, wenn er fehlt.
- Mehrere Ticker in einer Warteschlange: verlockend, widerspricht aber „ein Lauf, bewusst
  ausgelöst"; wenn, dann als eigene Entscheidung mit Kostenblick.
- Vault-Rückweg vom Server (Phase 2, oben).

## Prüfung gegen den Code (2026-10-24, vor der Umsetzung)

Abgeglichen mit `app/deepdive/__main__.py`, `peer_preflight.py`, `adr_resolver.py`,
`compose.py`, `app/services/edgar_client.py`, `yfinance_client.py`, `firestore_client.py`,
`app/viewer/site_generator.py`. Die Spec trägt; folgende Präzisierungen gelten für die Umsetzung:

1. **SEC-Map-Griff: dieselbe Instanz, frisch pro Prüfung.** `get_cik()` merkt sich einen
   Ladefehler als leere Map (`{}`) für die Lebensdauer der Instanz. In einem langlebigen
   UI-Prozess hieße das: ein SEC-Schluckauf, und bis zum Neustart ist jeder US-Ticker
   „unbekannt". Deshalb: (a) `EdgarClientImpl` merkt sich den Ladefehler in einem eigenen
   Flag, `ticker_map_available()` liest dieses Flag (statt „Map leer?"); (b) Resolver und
   Map-Check teilen **eine** `EdgarClientImpl` (`build_adr_resolver(edgar=...)`), sonst
   prüft der Check eine andere Map als der Resolver benutzt hat; (c) die UI baut die
   Abhängigkeiten **pro Vorprüfung** neu (`build_preflight_deps()` in `compose.py`), nicht
   einmal beim Start. Die Map wird nur befragt, wenn der Resolver für einen Ticker ohne
   Punkt `DeepDiveError` wirft — Tabellen- und EU-Treffer kosten so keinen SEC-Abruf
   zusätzlich. Ergebnis wie in der Spec: Map weg → `unknown`, nicht `none`.
2. **Zeichensatz des Unterprozesses (Windows).** stdout in eine Datei umgeleitet → Python
   schreibt in cp1252, und die CLI-Meldungen mit „✗" brechen mit `UnicodeEncodeError` ab —
   ausgerechnet auf dem Fehlerpfad. Unterprozess-Umgebung daher zusätzlich
   `PYTHONIOENCODING=utf-8`; das Log wird als UTF-8 mit `errors="replace"` gelesen.
3. **Symbole sind argv.** Ticker und Peers landen als eigene Argumente in der CLI; ein Wert
   wie `--site` würde argparse als Flag lesen. Symbole werden getrimmt, großgeschrieben und
   gegen `^[A-Z0-9][A-Z0-9.\-=]{0,19}$` geprüft — in der Vorprüfung (`ok=False`,
   Meldung) und noch einmal in `RunManager.start()`.
4. **Begründung > 200 Zeichen → 422**, nicht still kürzen (die CLI kürzt still; die
   Oberfläche soll es sagen). Das Eingabefeld hat `maxlength=200`.
5. **Preflight-Token** ist an normalisierten Ticker + Peer-Liste gebunden, merkt sich
   `needs_quant_only_ack` und wird beim erfolgreichen Start **verbraucht** (einmalig).
6. **Verwaiste Läufe:** Der Dienst ist eine Instanz. Beim Anlegen des `RunManager` wird
   jeder `running`-Eintrag auf `failed` gesetzt, Hinweis „Dienst wurde neu gestartet".
7. **`/api/peers` bei Firestore-Ausfall → 503** mit Meldung, nicht `{}`. Ausfall ≠ leer;
   die Seite zeigt „gespeicherte Peers nicht abrufbar".
8. **Viewer-Link** `{viewer_url}/ticker/{TICKER}.html` stimmt mit
   `site_generator.TICKER_DIRNAME = "ticker"` überein — bestätigt.
9. Exit-Code 2 kommt auch von argparse (Usage-Fehler), nicht nur von `DataSourceError`.
   Da die Argumente aus geprüften Feldern gebaut werden, tritt das nicht auf; die
   Übersetzung bleibt wie in der Spec.
10. **APLE ist kein Tippfehler-Beispiel** für die Abnahme: es ist Apple Hospitality REIT und
    besteht die Prüfung zu Recht. Die Absicherung dagegen ist der angezeigte Firmenname.
    Tippfehler-Beispiel bleibt `NOVOB.CO`.

## Nachtrag 2026-10-24: Peer-Vorschlag bei weniger als drei Peers

Entscheidung Stephan nach dem ersten Browser-Test (Ticker SAF.PA, nur zwei Peers eingegeben):

- **Weniger als drei Peers ist kein Fehler der Vorprüfung, sondern ein Hinweis.** Die Prüfung
  läuft mit den vorhandenen Peers durch; leere Plätze erscheinen als „Peer N fehlt — Vorschlag
  unten", nicht als rote Fehlerzeile. **Gestartet wird weiterhin nur mit genau drei Peers** —
  CLI (`_parse_triplet`), Dossier und `dev_deepdive_peers` bleiben unverändert.
- **Vorschlag = gleiche Branche aus dem yfinance-Cache.** Quelle ist `dev_ticker_cache`
  (Firestore, volles `.info` je Ticker). Kandidaten: Titel aus `data/universe.json` mit
  derselben yfinance-`industry` wie der Ticker, ohne Ticker selbst und ohne schon eingetragene
  Peers, sortiert nach Nähe der Market Cap (|log(mcap_k / mcap_t)|), höchstens 5. Reicht die
  Branche nicht für 3 Kandidaten, wird mit gleichem `sector` aufgefüllt und so markiert.
  Kein Gemini, keine neue Abhängigkeit, kein Schreiben.
- Cache-Einträge werden **unabhängig vom 24-h-TTL** gelesen: Branche ändert sich praktisch
  nie, die Market Cap dient nur der Reihenfolge. Der Vorschlag nennt den Stand (`_cached_at`).
- **Ausfall ≠ leer:** Ist Firestore nicht erreichbar, meldet die Prüfung „Vorschläge nicht
  abrufbar", nicht „keine Vorschläge". Ohne `industry` beim Ticker: „keine Branche bekannt —
  kein Vorschlag".
- Die Vorschläge werden nur **angeboten**: ein Klick trägt den Kandidaten in das erste leere
  Peer-Feld ein, danach läuft die Prüfung automatisch neu. Jeder vorgeschlagene Peer durchläuft
  dieselbe yfinance-Prüfung wie ein getippter.
- CLI: `preflight` akzeptiert 1–3 Peers und druckt die Vorschläge; Exit 1, solange nicht drei
  gültige Peers da sind. `deepdive` bleibt bei genau drei.

Schnittstelle (Ergänzung zu Abschnitt 1):

```python
@dataclass(frozen=True)
class PeerSuggestion:
    symbol: str
    name: str | None
    market_cap: float | None
    match: Literal["industry", "sector"]
    industry: str | None
    cached_at: str | None        # ISO, Stand des Cache-Eintrags

SymbolCheck  += industry: str | None, sector: str | None
PreflightResult += missing_peer_slots: list[int]          # 1-basiert, z. B. [3]
                += peer_suggestions: list[PeerSuggestion]  # leer, wenn keine Plätze fehlen
                += suggestion_note: str | None             # Hinweis/Ausfallmeldung, sonst None

run_preflight(..., suggest: Callable[[SymbolCheck, list[str]], list[PeerSuggestion]] | None = None)
# app/deepdive/peer_suggest.py
def suggest_peers(ticker_check: SymbolCheck, exclude: list[str], *, firestore, collection: str,
                  universe: frozenset[str], limit: int = 5) -> list[PeerSuggestion]
FirestoreClientImpl.query_equal(collection, field, value, limit) -> list[tuple[str, dict]]
```
