# Runbook: Dossier-Veröffentlichung einrichten (Daten-Repo, Server-Viewer, Vault)

Stand 2026-10-25 · gehört zu `2026-10-25-dossier-publishing-design.md` (§3, §4, §8)

Ziel: Jedes Deep-Dive-Dossier — am PC oder auf `tools-prod-01` — landet im privaten Repo
`stnmllr/fisherscreen-dossiers`, erscheint nach `git pull` im Vault (`FisherScreen\Deep Dives`)
und binnen ca. 5 min im Viewer unter `https://macro.stnmllr.com/fisher/`.

Die Dateien für den Server liegen im Repo unter `infra/hetzner/`:

| Datei | Ziel auf dem Server |
|---|---|
| `fisherscreen-viewer-refresh.sh` | bleibt im Checkout, wird per `/bin/bash` aufgerufen |
| `fisherscreen-viewer.service` | `/etc/systemd/system/fisherscreen-viewer.service` |
| `fisherscreen-viewer.timer` | `/etc/systemd/system/fisherscreen-viewer.timer` |
| `env.example` | Vorlage für `/etc/fisherscreen/env` (drei Zeilen neu bzw. geändert) |

Feste Werte:

| | |
|---|---|
| Daten-Repo | `stnmllr/fisherscreen-dossiers`, privat, Branch `main`, Ordner `Watchlist/` |
| Server | `tools-prod-01`, `macro.stnmllr.com`, Benutzer `stef` |
| Code-Checkout | `/opt/fisherscreen` (venv `/opt/fisherscreen/.venv`) |
| Daten-Klon (Server) | `/opt/fisherscreen-dossiers`, Read-only-Deploy-Key `~stef/.ssh/fisherscreen-dossiers-ro`, Host-Alias `github-dossiers` |
| Builds | `/var/www/fisher-builds/<short-sha>/`, Zeiger `/var/www/fisher-builds/current`, Stempel `/var/www/fisher-builds/.built-sha` |
| Web-Pfad | `/var/www/fisher` → Symlink auf `/var/www/fisher-builds/current` |
| Alte Seite | `/var/www/fisher-builds/legacy-2026-10-25` (wird nie gelöscht) |
| Klon (PC) | `D:\entwicklung\fisherscreen-dossiers` |
| Vault-Junction | `D:\Obsidian\stef_remote\Wissen\Finanzen\FisherScreen\Deep Dives` → `D:\entwicklung\fisherscreen-dossiers\Watchlist` |

Zwei Sorten Befehle: **cmd.exe** am PC, **bash** auf dem Server nach
`ssh -t stef@macro.stnmllr.com` (`-t` ist Pflicht, sonst fragt `sudo` nicht nach dem Passwort).
Server-Schritte aus einem echten Terminalfenster, nicht über den `!`-Prefix in Claude Code.

**Reihenfolge:** Schritt 4 (Umschalten) macht den Viewer leer — es wird nichts nachträglich
veröffentlicht (Spec §5). Wer vorher noch etwas am alten Viewer braucht: jetzt erledigen.

---

## Schritt 1: Repo und Token (PC, cmd.exe, GitHub-Oberfläche)

```
gh repo create stnmllr/fisherscreen-dossiers --private --description "Generated FisherScreen deep-dive dossiers"
```

Eine `README.md` einchecken (Inhalt: die Dateien unter `Watchlist/` sind generiert vom
FisherScreen-Deep-Dive und werden nicht von Hand bearbeitet) und den Ordner `Watchlist/`
anlegen — Git kennt keine leeren Ordner, die erste Datei legt ihn an; der Server-Viewer
braucht ihn aber schon vorher. Deshalb eine Platzhalterdatei `Watchlist/.gitkeep` mit committen.

Fein eingeschränkter Token — **Stephan, im Browser** (GitHub → Settings → Developer settings →
Fine-grained tokens → Generate new token):

- Repository access: *Only select repositories* → `stnmllr/fisherscreen-dossiers`
- Permissions: *Contents: Read and write* (Metadata: Read-only kommt automatisch), sonst nichts
- Ablauf: nach Wunsch (z. B. 1 Jahr), Termin notieren

Den Token einmal anzeigen lassen und für Schritt 3 und 5 bereithalten. Nicht in Chat oder Repo.

---

## Schritt 2: Server — Deploy-Key und Klon

```bash
ssh-keygen -t ed25519 -N "" -C "tools-prod-01 dossiers read-only" -f ~/.ssh/fisherscreen-dossiers-ro
cat ~/.ssh/fisherscreen-dossiers-ro.pub
```

Den öffentlichen Schlüssel auf GitHub eintragen (Stephan): Repo `fisherscreen-dossiers` →
Settings → Deploy keys → Add deploy key, **„Allow write access" NICHT ankreuzen**.

SSH-Alias (damit dieser Schlüssel nur für dieses Repo benutzt wird):

```bash
cat >> ~/.ssh/config <<'EOF'

Host github-dossiers
    HostName github.com
    User git
    IdentityFile ~/.ssh/fisherscreen-dossiers-ro
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

sudo install -d -o stef -g stef /opt/fisherscreen-dossiers
git clone git@github-dossiers:stnmllr/fisherscreen-dossiers.git /opt/fisherscreen-dossiers
ls /opt/fisherscreen-dossiers/Watchlist
```

Erwartung: Clone ohne Passwortfrage (beim ersten Mal den GitHub-Host-Key bestätigen);
`Watchlist` enthält mindestens `.gitkeep`. Schreibprobe, die scheitern muss:
`git -C /opt/fisherscreen-dossiers push --dry-run` meldet nichts zu pushen; ein echter Push
(`git commit --allow-empty -m x && git push`) wird abgelehnt — danach `git reset --hard HEAD~1`.

---

## Schritt 3: Server — Umgebung und Code aktualisieren

```bash
sudo nano /etc/fisherscreen/env
```

Drei Zeilen (Vorlage: `infra/hetzner/env.example`):

```
FISHERSCREEN_DEEPDIVE_UI_VIEWER_URL=https://macro.stnmllr.com/fisher
FISHERSCREEN_DOSSIER_REPO=stnmllr/fisherscreen-dossiers
FISHERSCREEN_DOSSIER_TOKEN=<Token aus Schritt 1>
```

Dann den Code mit der Veröffentlichung holen (der Branch muss gemergt sein; sonst
`git fetch` + `git checkout` des Feature-Branches nur für den Test):

```bash
cd /opt/fisherscreen
git pull --ff-only
~/.local/bin/uv sync --frozen --no-default-groups
sudo systemctl restart fisherscreen-deepdive
systemctl status fisherscreen-deepdive --no-pager
```

Nicht während eines laufenden Deep Dives neu starten.

---

## Schritt 4: Server — Symlink-Test, dann Umschalten

**Zuerst prüfen, dass Caddys `file_server` einem Symlink folgt** — sonst ist nach dem
Umschalten `/fisher/` kaputt. Caddy bleibt unverändert (`handle /fisher/*`, `root * /var/www`).

Der Testlink liegt **unter** `/var/www/fisher/` (dem noch echten, `stef` gehörenden Ordner), damit
er vom Matcher `handle /fisher/*` erfasst wird:

```bash
sudo install -d -o stef -g stef /var/www/fisher-builds
mkdir /var/www/fisher-builds/symtest
echo symlink-ok > /var/www/fisher-builds/symtest/index.html
ln -s /var/www/fisher-builds/symtest /var/www/fisher/symtest
```

`https://macro.stnmllr.com/fisher/symtest/` im Browser (mit Google-Sitzung) muss `symlink-ok`
zeigen. Dann aufräumen:

```bash
rm /var/www/fisher/symtest
rm -r /var/www/fisher-builds/symtest
```

Zeigt es 404 oder eine Fehlerseite: **abbrechen**. Dann Caddy-Block anpassen (z. B.
`root * /var/www/fisher-builds` plus Rewrite) — das ist eine eigene Entscheidung.

Units installieren und **den ersten Build von Hand laufen lassen, bevor irgendetwas
umgeschaltet wird**. Das Skript fasst `/var/www/fisher` nie an; die alte Seite bleibt
währenddessen online:

```bash
sudo cp /opt/fisherscreen/infra/hetzner/fisherscreen-viewer.service         /opt/fisherscreen/infra/hetzner/fisherscreen-viewer.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start fisherscreen-viewer.service
journalctl -u fisherscreen-viewer -n 20 --no-pager
ls -l /var/www/fisher-builds
test -e /var/www/fisher-builds/current/index.html && echo build-ok
```

Erwartung: Journal `viewer switched to <sha>-<epoch>`, `current` → dieser Build, `build-ok`.
Fehlt `build-ok` oder schlägt der Dienst fehl: **hier abbrechen**, Journal lesen — `/fisher/`
ist noch unverändert die alte Seite. Erst bei `build-ok` umschalten (ab hier zeigt der Viewer
nur noch neue Dossiers):

```bash
sudo mv /var/www/fisher /var/www/fisher-builds/legacy-2026-10-25
sudo ln -s /var/www/fisher-builds/current /var/www/fisher
ls -l /var/www/fisher
```

Zwischen den beiden Befehlen liefert `/fisher/` für einen Augenblick 404 (Sekundenbruchteile,
einmalig; beide Ziele existieren bereits). `https://macro.stnmllr.com/fisher/` zeigt jetzt die
(leere) Übersicht, `legacy-2026-10-25` liegt daneben. Erst danach den Timer einschalten:

```bash
sudo systemctl enable --now fisherscreen-viewer.timer
systemctl list-timers fisherscreen-viewer --no-pager
```

Ein weiterer Handlauf muss ohne Build enden (Journal bleibt still, Exit 0): unverändert → kein Build.

---

## Schritt 5: PC — Klon, Junction, Token (cmd.exe)

```
git clone https://github.com/stnmllr/fisherscreen-dossiers.git D:\entwicklung\fisherscreen-dossiers
mklink /J "D:\Obsidian\stef_remote\Wissen\Finanzen\FisherScreen\Deep Dives" "D:\entwicklung\fisherscreen-dossiers\Watchlist"
dir "D:\Obsidian\stef_remote\Wissen\Finanzen\FisherScreen\Deep Dives"
```

Der Ordner `Deep Dives` darf noch nicht existieren (`mklink` legt ihn an). **`FisherScreen\Watchlist`
nicht anfassen** — das ist ein echter Ordner mit eigenen Notizen (Spec §3). In `Deep Dives` nichts
von Hand ablegen.

`D:\entwicklung\fisherscreen\.env` ergänzen:

```
FISHERSCREEN_DOSSIER_REPO=stnmllr/fisherscreen-dossiers
FISHERSCREEN_DOSSIER_TOKEN=<Token aus Schritt 1>
```

Dossiers abholen: `git -C D:\entwicklung\fisherscreen-dossiers pull`.

---

## Schritt 6: Abnahme (Spec §8)

1. **PC-Lauf:** `uv run python -m app.deepdive deepdive EDV.L --peers HL,NEM,AEM --quant-only --no-insider`
   (kostenfrei) → Ausgabe `Published to: stnmllr/fisherscreen-dossiers/Watchlist/EDV.L_<Datum>.md`.
   `git -C D:\entwicklung\fisherscreen-dossiers pull` → Datei erscheint in Obsidian unter
   `FisherScreen\Deep Dives`; ≤ 5 min später im Viewer `https://macro.stnmllr.com/fisher/`.
2. **Server-Lauf:** über `https://macro.stnmllr.com/deepdive/` (z. B. SU.PA, quant-only) →
   Anzeige „ok · veröffentlicht", Viewer-Link führt ≤ 5 min später auf die Seite (kein 404).
3. **Ungültiger Token:** am PC `set FISHERSCREEN_DOSSIER_TOKEN=ungueltig` und denselben Lauf
   wiederholen → `WARNING: dossier NOT published: …`, Exit 0, Dossier liegt unter
   `output\Watchlist\`. (Auf dem Server analog über die Seite: „ok · nicht veröffentlicht".)
4. **Legacy bleibt:** `ls /var/www/fisher-builds/legacy-2026-10-25` zeigt die alte Seite;
   der Viewer listet genau die seit der Umstellung veröffentlichten Dossiers.
5. **Refresh-Skript:** unverändert → kein neuer Build (`ls /var/www/fisher-builds` gleich);
   neues Dossier → neuer Build, `current` zeigt darauf; nach mehreren Builds bleiben `current`,
   die zwei neuesten Builds und `legacy-*`.

---

## Aktualisieren

Skript oder Units geändert (nach Merge):

```bash
cd /opt/fisherscreen && git pull --ff-only
sudo cp infra/hetzner/fisherscreen-viewer.service infra/hetzner/fisherscreen-viewer.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

Das Skript wird bei jedem Lauf frisch aus dem Checkout gelesen. Ein `git pull` im Code-Checkout
(`/opt/fisherscreen`) löst binnen ≤ 5 min einen Neubau des Viewers aus (der Stempel
`.built-sha` merkt sich Daten- und Code-Stand); sofort: `sudo systemctl start fisherscreen-viewer.service`.

Token erneuern: neuen Token in
`/etc/fisherscreen/env` und `.env` eintragen, `sudo systemctl restart fisherscreen-deepdive`.

---

## Rollback

Zurück zur alten Seite (ein Befehl) und Timer aus:

```bash
sudo systemctl disable --now fisherscreen-viewer.timer
sudo ln -sfn /var/www/fisher-builds/legacy-2026-10-25 /var/www/fisher
```

Der Symlink `/var/www/fisher` zeigt dann direkt auf die alte Seite; `current` wird nicht mehr
beschrieben. Die Veröffentlichung selbst abschalten: `FISHERSCREEN_DOSSIER_TOKEN` leeren (oder
am PC `--no-publish`) und den Dienst neu starten; den Viewer-Link in `env` wieder leeren.
Token bei Bedarf auf GitHub widerrufen, Deploy-Key im Repo löschen.
