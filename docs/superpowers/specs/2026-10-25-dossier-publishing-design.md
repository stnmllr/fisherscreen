# Dossiers veröffentlichen: ein Daten-Repo für Vault und Viewer

Stand 2026-10-25 · Entscheidung Stephan · Stand des Codes: `main` @ `d0c4a7e`
Phase 2 zu `2026-10-24-deepdive-ui-design.md` §7

## Problem

Deep-Dive-Dossiers entstehen jetzt an drei Orten — `D:\entwicklung\fisherscreen` (dieser PC),
`D:\programme\fisherscreen` (der andere Rechner) und `tools-prod-01` (seit 2026-10-24 über
die Start-Oberfläche) — und liegen jeweils nur dort, in `output/Watchlist/` (gitignored).

- **Viewer:** wird am PC gebaut und per `scp` nach `/var/www/fisher/` geladen. Ein Dossier vom
  Server erreicht ihn nie; der Viewer-Link der Oberfläche lief für SU.PA auf einen 404 und ist
  auf dem Server deshalb abgeschaltet.
- **Vault:** Obsidian liest nur am PC. Für `Universum` gibt es eine Junction auf den
  Code-Checkout und `git pull`; für Deep-Dive-Dossiers gibt es keinen gemeinsamen Ort.
- Bestand heute (2026-10-25): dieser PC 10 Dossiers (9 davon im Code-Repo getrackt, Mai 2026,
  plus EDV.L), Server dieselben 9 plus SU.PA, der Viewer zeigt 11 Ticker — ARGX, ASML.AS,
  FICO, MEDP, MSCI kommen **nur** vom anderen Rechner.

## Entscheidung

Ziel (Stephan, 2026-10-25): Jedes Dossier — egal wo es entsteht — landet **automatisch** im
Viewer **und** im Vault. Obsidian nur am PC; ein `git pull` dort ist zumutbar.

Ansatz A (gewählt): ein **eigenes privates Daten-Repo** `stnmllr/fisherscreen-dossiers` als
einziger gemeinsamer Ort. Verworfen:

- B — Dossiers ins Code-Repo (`output/Watchlist/` entsperren): Der Schreib-Token läge auf einem
  aus dem Internet erreichbaren Server und könnte Code auf `main` pushen; jeder Push dort löst
  den Cloud-Run-Deploy mit GCP-Rechten aus.
- C — `git push` mit Deploy-Key aus `/opt/fisherscreen`: Der Checkout ist zugleich der laufende
  Code des Dienstes; Daten-Commits und Konflikte dort mischen Daten mit Deploy-Stand. Dazu
  dasselbe Token-Problem wie B.

## Nicht-Ziele

- Keine Dossier-Inhalte in den Code-Repo. Keine Synchronisation in `stnmllr/stef-vault`
  (Obsidian nur am PC).
- Keine Echtzeit: Viewer-Aktualisierung bis zu 5 min nach dem Lauf ist ausreichend.
- Kein Webhook, kein GitHub-Action-Deploy auf den Server (bräuchte einen SSH-Schlüssel mit
  Schreibrecht auf den Server in GitHub).
- Das HTML des Viewers kommt nicht ins Repo — es wird auf dem Server gebaut.
- Keine Änderung am Viewer selbst (`app/viewer/`), nur an seinem Aufruf.

## 1. Datenfluss

```
Lauf (PC oder Server) ──► output/Watchlist/<T>_<D>.md          (wie heute)
        │
        └─ publish (GitHub-API, Token nur fürs Daten-Repo) ──► stnmllr/fisherscreen-dossiers
                                                                     Watchlist/<T>_<D>.md
                                   ┌─────────────────────────────────────┴──────────────┐
             PC: git pull im Klon D:\entwicklung\fisherscreen-dossiers      Server: Timer (5 min)
                 Vault-Junction …\FisherScreen\Watchlist ──► Klon\Watchlist     git pull (Read-only-Deploy-Key)
                                                                               Viewer bauen ─► /var/www/fisher
```

**Ablage:** Repo `stnmllr/fisherscreen-dossiers`, privat, Branch `main`, ein Ordner
`Watchlist/`, Dateinamen wie heute (`<TICKER>_<JJJJ-MM-TT>.md`). Nichts sonst außer einer
README, die sagt, woher die Dateien kommen und dass sie generiert sind.

## 2. Schreiben: Veröffentlichung nach dem Lauf

- Die CLI `deepdive` veröffentlicht nach `Dossier written to: …` das Dossier per GitHub-API
  (`GitHubClientImpl.push_file`, Ziel = Daten-Repo) nach `Watchlist/<Dateiname>`.
- **Aktiv, sobald konfiguriert:** `FISHERSCREEN_DOSSIER_REPO` (z. B.
  `stnmllr/fisherscreen-dossiers`) und `FISHERSCREEN_DOSSIER_TOKEN` gesetzt → veröffentlichen.
  Leer → nicht veröffentlichen, eine Zeile `Dossier not published (no dossier repo configured)`.
  `--no-publish` schaltet es für einen Lauf ab.
- **Gleicher Tag, zweiter Lauf:** überschreibt die Datei (wie lokal). Git behält die alte Fassung.
- **Commit-Nachricht:** `Publish <TICKER> deep dive <JJJJ-MM-TT> (<host>)`, `<host>` =
  Rechnername (`pcstef`, `tools-prod-01`), damit die Herkunft im Log steht. Ob neu oder
  überschrieben, zeigt die Git-Historie; dafür kein zusätzlicher API-Aufruf.
- **Fehlschlag:** Das Dossier ist auf der Platte, der Gemini-Lauf bezahlt — der Exit-Code bleibt 0
  (gleiches Prinzip wie `_refresh_site`). Aber laut: `WARNING: dossier NOT published: <Grund>` auf
  stdout, `logger.error` mit Traceback. Kein stilles Weiterlaufen.
- **Ausgabezeilen** (die Oberfläche parst sie, genau eine pro Lauf):

  | Zeile | Bedeutung | `RunRecord.published` |
  |---|---|---|
  | `Published to: <repo>/Watchlist/<Datei>` | veröffentlicht | `True` |
  | `WARNING: dossier NOT published: <Grund>` | Versuch gescheitert | `False` |
  | `Dossier not published (--no-publish)` / `(no dossier repo configured)` | bewusst nicht | `None` |
  | keine der Zeilen (Lauf vorher abgebrochen) | — | `None` |
- **Token:** fein eingeschränkter GitHub-Token (fine-grained PAT), Repository-Zugriff **nur**
  `stnmllr/fisherscreen-dossiers`, Berechtigung *Contents: Read and write*, sonst nichts. Am PC
  in `.env`, auf dem Server in `/etc/fisherscreen/env`. Getrennt von `FISHERSCREEN_GITHUB_TOKEN`
  (Tool A), damit keiner der beiden mehr kann als nötig.

## 3. Lesen: Vault am PC

- Klon `D:\entwicklung\fisherscreen-dossiers` (nur dieser PC).
- Junction im Vault: `<Vault>\Wissen\Finanzen\FisherScreen\Watchlist` → `<Klon>\Watchlist`
  (`mklink /J`, wie bei `Universum`), Eintrag in `stef-vault/.gitignore`.
- Aktualisieren: `git -C D:\entwicklung\fisherscreen-dossiers pull` — gehört in dieselbe
  Sichtungsroutine wie der `Universum`-Pull.
- Die CLI schreibt weiterhin nach `output/Watchlist/` im Code-Checkout (Arbeitskopie,
  gitignored); der Klon ist die gemeinsame Fassung.

## 4. Lesen: Viewer auf dem Server

- Klon `/opt/fisherscreen-dossiers`, gezogen mit einem **Read-only-Deploy-Key** des Daten-Repos
  (`~stef/.ssh/fisherscreen-dossiers-ro`, Eintrag in `~stef/.ssh/config`).
- `infra/hetzner/fisherscreen-viewer-refresh.sh` + `fisherscreen-viewer.service` (oneshot,
  `User=stef`) + `fisherscreen-viewer.timer` (alle 5 min):
  1. `git pull --ff-only`; unverändert (HEAD gleich dem zuletzt gebauten) und Site vorhanden → Ende.
  2. Viewer bauen: `/opt/fisherscreen/.venv/bin/python -m app.viewer --in
     /opt/fisherscreen-dossiers/Watchlist --out /var/www/fisher-builds/<HEAD>`.
  3. **Atomarer Tausch:** `/var/www/fisher` ist ein Symlink auf `fisher-builds/current`, und
     `current` ist ein Symlink auf den Build. Umschalten mit `ln -sfn <build> current.tmp && mv -T
     current.tmp current` — nie eine halbfertige Seite. Alte Builds bis auf die letzten zwei
     löschen.
  4. Fehler (Pull, Build) → Exit ≠ 0, steht im Journal, die alte Seite bleibt.
- Einmalig mit `sudo`: `/var/www/fisher-builds` anlegen (`stef:stef`), bisheriges
  `/var/www/fisher` beiseite legen, Symlink setzen. Caddy bleibt unverändert (`root * /var/www`,
  `handle /fisher/*`) — **vor dem Umschalten prüfen**, dass Caddys `file_server` dem Symlink folgt.
- Der Viewer-Link in der Start-Oberfläche kommt auf dem Server zurück
  (`FISHERSCREEN_DEEPDIVE_UI_VIEWER_URL=https://macro.stnmllr.com/fisher`), mit dem Hinweis
  „erscheint im Viewer innerhalb von ~5 min" und nur, wenn der Lauf **veröffentlicht** wurde.
- Der `scp`-Upload des Viewers vom PC entfällt. `--site` bleibt als lokale Vorschau.

## 5. Kein Umzug des Bestands

Entscheidung Stephan (2026-10-25): **Nur künftige Deep Dives** zählen. Es wird nichts
nachträglich veröffentlicht, der andere Rechner (`D:\programme\fisherscreen`) bleibt außen vor.

Folgen, bewusst in Kauf genommen:

- **Der Viewer startet leer.** Sobald `/var/www/fisher` auf die Builds aus dem Daten-Repo
  umgeschaltet ist, verschwinden die 11 heutigen Ticker (ARGX, ASML, ASML.AS, EDV.L, FICO, GOOGL,
  KO, MEDP, MSCI, MSFT, NOVO-B.CO). Die bisherige Seite wird beim Umschalten nach
  `/var/www/fisher-builds/legacy-2026-10-25` verschoben, nicht gelöscht — Rückweg in einem Befehl.
- Die vorhandenen Dossier-Dateien bleiben unangetastet, wo sie liegen (beide PCs, Server, die 9
  im Code-Repo getrackten vom Mai 2026). Sie erscheinen nur nicht im Viewer und nicht im Klon.
- Bis zum ersten veröffentlichten Lauf zeigt der Viewer eine leere Übersicht. Geprüft
  2026-10-25: `python -m app.viewer` mit leerem `--in` baut `index.html`, `site.css`, `sort.js`,
  `ticker/` und loggt „overview rendered without any dossier" — das Refresh-Skript braucht dafür
  keinen Sonderfall.

## 6. Bausteine im Code

| Baustein | Inhalt |
|---|---|
| `app/config.py` | `dossier_repo: str = ""`, `dossier_token: str = ""`, `dossier_branch: str = "main"` |
| `app/deepdive/publish.py` (neu) | `publish_dossier(path, *, github, host) -> str` (Ziel-Pfad im Repo; wirft `DataSourceError`) |
| `app/deepdive/compose.py` | `build_dossier_publisher() -> GitHubClientImpl \| None` (`None`, wenn nicht konfiguriert) |
| `app/deepdive/__main__.py` | `deepdive`: `--no-publish`, Veröffentlichung nach dem Schreiben, Ausgabezeilen wie §2 |
| `app/deepdive_ui/` | `RunRecord.published: bool \| None` aus den Ausgabezeilen (§2); Anzeige „ok · veröffentlicht" (`True`) / „ok · **nicht veröffentlicht**" in Warnfarbe (`False`) / nur „ok" (`None`); Haken „Nicht veröffentlichen (`--no-publish`)"; Viewer-Link nur bei `published is True` |
| `infra/hetzner/` | `fisherscreen-viewer-refresh.sh`, `fisherscreen-viewer.service`, `fisherscreen-viewer.timer`, `env.example` um `FISHERSCREEN_DOSSIER_REPO`/`_TOKEN` und den Viewer-Link |
| Runbook | `docs/superpowers/specs/2026-10-25-dossier-publishing-runbook.md`: Repo + Token + Deploy-Key anlegen, Server einrichten (inkl. Legacy-Seite beiseite), PC-Klon + Junction |

## 7. Tests

- `publish_dossier`: Erfolg (Pfad, Commit-Nachricht mit Host), `DataSourceError` wird durchgereicht.
- CLI: Veröffentlichung an/aus (`--no-publish`, nicht konfiguriert), Fehlschlag → Exit 0 +
  `WARNING`-Zeile + `logger.error`; genau eine der Zeilen aus §2 pro erfolgreichem Lauf.
- UI: `published` aus den Zeilen geparst (ja / nein / keine Zeile → `None`), Anzeige und Link.
- Fakes für GitHub, kein Netz. Coverage ≥ 90 %, `black --check .` sauber.
- Das Refresh-Skript ist Shell (in `infra/`, nicht im Coverage-Maß): Abnahme auf dem Server —
  unverändert → kein Build; neues Dossier → neuer Build, Symlink umgeschaltet; kaputter Build →
  alte Seite bleibt.

## 8. Abnahme

- Lauf am PC → `Published to: …`; nach `git pull` im Klon in Obsidian sichtbar; ≤ 5 min später im
  Viewer.
- Lauf auf dem Server über die Oberfläche → „ok · veröffentlicht", Viewer-Link führt ≤ 5 min
  später auf die Seite (kein 404).
- Token absichtlich ungültig → Lauf „ok · nicht veröffentlicht", Dossier lokal vorhanden, Warnung
  im Log.
- Umschalten: Die Legacy-Seite liegt unter `/var/www/fisher-builds/legacy-2026-10-25`; der Viewer
  zeigt danach genau die seit der Umstellung veröffentlichten Dossiers.

## Offene Punkte

- Pfad des Vaults auf **diesem** PC (die Junction-Angabe oben folgt dem anderen Rechner,
  `D:\programme\stef-vault\…`) — beim Einrichten klären.
- Sollen Gemini-Läufe am PC, die nicht veröffentlicht werden sollen (Experimente), Standard
  `--no-publish` sein? Vorschlag: nein — veröffentlicht wird standardmäßig, Experimente bekommen
  den Schalter.
