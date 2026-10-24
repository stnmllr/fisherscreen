# Runbook: Deep-Dive-Oberfläche auf Hetzner (`tools-prod-01`) einrichten

Stand 2026-10-24 · gehört zu `2026-10-24-deepdive-ui-design.md` §7 (Phase 1)

Ziel: `https://macro.stnmllr.com/deepdive/` zeigt die Start-Oberfläche hinter dem vorhandenen
Google-Gate. Dossiers bleiben auf dem Server (`/opt/fisherscreen/output/Watchlist/`). Der Weg
zurück in den Vault ist Phase 2 und nicht Teil dieses Runbooks.

Die Dateien für den Server liegen im Repo unter `infra/hetzner/`:

| Datei | Ziel auf dem Server |
|---|---|
| `fisherscreen-deepdive.service` | `/etc/systemd/system/fisherscreen-deepdive.service` |
| `env.example` | Vorlage für `/etc/fisherscreen/env` (Werte von Hand eintragen) |
| `Caddyfile.deepdive.snippet` | Abschnitt in `/etc/caddy/Caddyfile`, Site-Block `macro.stnmllr.com` |

Feste Werte:

| | |
|---|---|
| Server | `tools-prod-01`, `macro.stnmllr.com` (178.105.88.72), Benutzer `stef` |
| Checkout | `/opt/fisherscreen` (gehört `stef`) |
| Dienst | `fisherscreen-deepdive`, lauscht auf `127.0.0.1:8765` |
| Service-Account | `fisherscreen-deepdive-ui@fisherscreen-prod.iam.gserviceaccount.com` |
| Caddy | `/etc/caddy/Caddyfile`, Gate-Snippets `oauth2endpoints` + `authgate` (macro-dashboard `AUTH.md`) |

Zwei Sorten Befehle:

- **cmd.exe** auf dem PC (gcloud, scp, ssh). Bleibt `gcloud` stumm, wie auf `pcstef`
  beobachtet: über `"%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\platform\bundledpython\python.exe" "%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\lib\gcloud.py"` aufrufen.
- **bash auf dem Server**, nach `ssh -t stef@macro.stnmllr.com`. `-t` ist Pflicht, sonst kann
  `sudo` nicht nach dem Passwort fragen (Ticket 2026-08-20).

Deploy-Schritte aus einem echten Terminalfenster, nicht über den `!`-Prefix in Claude Code: dort
gibt es kein TTY, `ssh` kann die Passphrase nicht abfragen und meldet `Permission denied
(publickey)`.

---

## Schritt 0: Ist-Zustand sichern und ansehen

```
ssh -t stef@macro.stnmllr.com "sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.pre-deepdive && sudo cat /etc/caddy/Caddyfile"
```

Den ausgegebenen Inhalt aufheben. Er wird in Schritt 6 gebraucht und gehört danach in
`AUTH.md` im macro-dashboard-Repo — dort fehlt bis heute die `/fisher/`-Route vom
Viewer-Deploy (2026-08-20); `AUTH.md` beschreibt nur Dashboard und xrechnung.

Außerdem prüfen, was schon da ist:

```
ssh stef@macro.stnmllr.com "which git; ls ~/.local/bin/uv; ls -d /opt/fisherscreen; ss -ltnp | grep 8765"
```

Erwartung: `git` vorhanden, Port 8765 frei. `uv` und `/opt/fisherscreen` dürfen fehlen.

---

## Schritt 1: Service-Account für Firestore (PC, cmd.exe)

```
gcloud config set project fisherscreen-prod
gcloud iam service-accounts create fisherscreen-deepdive-ui --display-name "FisherScreen deep-dive UI (Hetzner)"
gcloud projects add-iam-policy-binding fisherscreen-prod ^
  --member serviceAccount:fisherscreen-deepdive-ui@fisherscreen-prod.iam.gserviceaccount.com ^
  --role roles/datastore.user --condition None
gcloud iam service-accounts keys create %USERPROFILE%\fisherscreen-deepdive-sa.json ^
  --iam-account fisherscreen-deepdive-ui@fisherscreen-prod.iam.gserviceaccount.com
```

Ehrliche Einschränkung: Die Spec nennt die drei Collections, auf die der Dienst zugreift.
Firestore-IAM kennt aber keine Rechte pro Collection — `roles/datastore.user` gilt für die
ganze Datenbank des Projekts. Enger geht es nur über Security Rules, und die greifen für
Service-Accounts nicht. Der Schlüssel ist deshalb so schützenswert wie der Gemini-Key.

---

## Schritt 2: Checkout und Umgebung (Server)

```
ssh -t stef@macro.stnmllr.com
```

```bash
# uv nur, falls Schritt 0 es nicht gefunden hat (offizieller Installer, landet in ~/.local/bin)
curl -LsSf https://astral.sh/uv/install.sh | sh

sudo install -d -o stef -g stef /opt/fisherscreen
git clone https://github.com/stnmllr/fisherscreen.git /opt/fisherscreen
cd /opt/fisherscreen
~/.local/bin/uv sync --frozen --no-default-groups

.venv/bin/python -m app.deepdive --help        # muss die Hilfe mit deepdive/preflight zeigen
```

`uv` lädt dabei Python 3.12 nach `~stef/.local/share/uv/python/` — die `.venv` verweist
dorthin. Deshalb läuft der Dienst als `stef` und nicht als eigener Systembenutzer.

---

## Schritt 3: Zugangsdaten (PC, dann Server)

Schlüsseldatei hochladen (PC, cmd.exe):

```
scp %USERPROFILE%\fisherscreen-deepdive-sa.json stef@macro.stnmllr.com:/tmp/fisherscreen-sa.json
```

Auf dem Server einsortieren:

```bash
sudo install -d -m 0750 -o root -g stef /etc/fisherscreen
sudo install -m 0640 -o root -g stef /tmp/fisherscreen-sa.json /etc/fisherscreen/sa.json
rm /tmp/fisherscreen-sa.json
sudo install -m 0600 -o root -g root /opt/fisherscreen/infra/hetzner/env.example /etc/fisherscreen/env
sudo nano /etc/fisherscreen/env       # FISHERSCREEN_GEMINI_API_KEY eintragen, Rest prüfen
```

Danach die lokale Kopie löschen (PC, cmd.exe):

```
del %USERPROFILE%\fisherscreen-deepdive-sa.json
```

Rechte, kurz begründet: `env` liest systemd als root, bevor es auf `stef` wechselt → `0600
root:root`. `sa.json` öffnet der Python-Prozess selbst → `0640 root:stef`, und das Verzeichnis
`0750 root:stef`, damit `stef` hineinkommt, aber sonst niemand.

---

## Schritt 4: Dienst starten (Server)

```bash
sudo cp /opt/fisherscreen/infra/hetzner/fisherscreen-deepdive.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fisherscreen-deepdive
systemctl status fisherscreen-deepdive --no-pager
```

Prüfen, noch ohne Caddy (direkt auf dem Server):

```bash
curl -s http://127.0.0.1:8765/deepdive/health
# {"status":"ok"}
curl -s -X POST http://127.0.0.1:8765/deepdive/api/preflight \
  -H 'content-type: application/json' \
  -d '{"ticker":"NOVO-B.CO","peers":["LLY","PFE","MRK"]}' | head -c 400; echo
curl -s http://127.0.0.1:8765/deepdive/api/peers/EDV.L; echo
```

Erwartung: Vorprüfung mit `"dossier_kind":"full"` und `can_start:true`; die Peers von EDV.L
(HL, NEM, AEM) kommen aus Firestore — das beweist, dass der Service-Account greift. Ein 503
bei `/api/peers` heißt: `sa.json` oder `GOOGLE_APPLICATION_CREDENTIALS` stimmt nicht
(`journalctl -u fisherscreen-deepdive -n 50`).

Der Pfad `/deepdive/...` funktioniert hier, weil die App den Präfix über
`FISHERSCREEN_DEEPDIVE_UI_ROOT_PATH` selbst auflöst (lokal geprüft 2026-10-24: mit gesetztem
`root_path` antworten `/deepdive/health`, `/deepdive/`, `/deepdive/api/runs` mit 200, die
Seite setzt `data-base="/deepdive"`, `/deepdive` leitet auf `/deepdive/` um).

---

## Schritt 5: Caddy (Server)

In `/etc/caddy/Caddyfile`, Site-Block `macro.stnmllr.com`, den Abschnitt aus
`infra/hetzner/Caddyfile.deepdive.snippet` einfügen — **nach** `import oauth2endpoints` und
**vor** dem allgemeinen `handle { … }`. `handle`-Blöcke schließen sich gegenseitig aus und
werden in der geschriebenen Reihenfolge geprüft; hinter dem Sammelblock würde die Route nie
erreicht. Liegt die `/fisher/`-Route als eigener `handle`-Block vor dem Sammelblock, kommt
`/deepdive` gleichrangig daneben.

```bash
sudo nano /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Zwei Entscheidungen im Snippet, nicht „vereinfachen":

- `handle`, nicht `handle_path`: Der Präfix muss bei der App ankommen.
- Der Matcher enthält auch `/deepdive` ohne Schrägstrich, sonst landet diese Adresse im
  Sammelblock (Dateiserver, 404) statt bei der App, die auf `/deepdive/` umleitet.

---

## Schritt 6: Gate prüfen

Ohne Sitzung darf **nichts** durchkommen (PC, cmd.exe):

```
curl -sI https://macro.stnmllr.com/deepdive/
curl -sI https://macro.stnmllr.com/deepdive
curl -sI https://macro.stnmllr.com/deepdive/api/runs
```

Erwartung jeweils `302` — und **den `Location`-Header lesen**: Er muss auf `/oauth2/start?rd=…`
zeigen. `302` auf sich selbst wäre die Redirect-Schleife aus `AUTH.md`; der Statuscode allein
unterscheidet die beiden Fälle nicht.

Dann im **frischen privaten Fenster**: `https://macro.stnmllr.com/deepdive/` → Google-Login →
die Seite. Ein Fenster, das schon einmal in einer Schleife war, hat sie gecacht.

Gegenprobe, dass nichts kaputt ist: `https://macro.stnmllr.com/` (Dashboard) und
`https://macro.stnmllr.com/fisher/` (Viewer) laden weiter.

---

## Schritt 7: Abnahme-Lauf

Über die Seite: `EDV.L` mit HL, NEM, AEM, Haken „nur Quant", `--no-insider`. Erwartung: Lauf
endet „ok", Dossier unter `/opt/fisherscreen/output/Watchlist/EDV.L_<Datum>.md`. Kein Gemini,
keine Kosten. Die Caches unter `/opt/fisherscreen/cache/` sind anfangs leer; der erste Lauf je
Ticker dauert länger als am PC.

Der Viewer-Link auf der Seite zeigt auf `https://macro.stnmllr.com/fisher/` — das ist der vom PC
hochgeladene Stand. Dossiers vom Server erscheinen dort **nicht** (auch nicht mit `--site`, das
baut nach `/opt/fisherscreen/output/site/`). Das ist Phase 2.

---

## Schritt 8: Doku nachziehen

- macro-dashboard `AUTH.md`: Abschnitt 4 um die tatsächliche `macro.stnmllr.com`-Konfiguration
  ergänzen — `/fisher/` (fehlt bisher) und `/deepdive` —, Inhalt aus Schritt 0 plus Snippet.
- FisherScreen `Projektstand.md`: Server-Betrieb vermerken.

---

## Aktualisieren (nach jedem Merge, der die UI oder die CLI ändert)

```bash
cd /opt/fisherscreen
git pull --ff-only
~/.local/bin/uv sync --frozen --no-default-groups
sudo systemctl restart fisherscreen-deepdive
```

Nicht während eines laufenden Deep Dives: Der Neustart beendet den Unterprozess, der Lauf
erscheint danach als „failed — Dienst wurde neu gestartet".

---

## Rollback

```bash
sudo cp /etc/caddy/Caddyfile.pre-deepdive /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl disable --now fisherscreen-deepdive
```

Schlüssel des Service-Accounts zurückziehen (PC, cmd.exe):

```
gcloud iam service-accounts keys list --iam-account fisherscreen-deepdive-ui@fisherscreen-prod.iam.gserviceaccount.com
gcloud iam service-accounts keys delete <KEY_ID> --iam-account fisherscreen-deepdive-ui@fisherscreen-prod.iam.gserviceaccount.com
```
