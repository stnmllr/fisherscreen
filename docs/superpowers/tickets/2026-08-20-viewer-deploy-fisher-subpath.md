# Ticket: Deploy the viewer as /fisher/ behind the existing OAuth gate

**Opened:** 2026-08-20
**Priority:** blocked on nothing technical; waiting for a deliberate deploy window.
**Status:** CLOSED 2026-09-07 — siehe „Abschluss 2026-09-07" unten. Der Deploy war seit August live; die Auffrischung ist nachgeholt und dokumentiert.

## Abschluss 2026-09-07: die Seite trägt den aktuellen Stand

Der letzte offene Punkt — der ausgelieferte Inhalt — ist erledigt. `output/site` ist neu
gebaut und hochgeladen (14 Dateien), und **an der ausgelieferten Seite gegengeprüft**, nicht
am Upload-Protokoll:

- `https://macro.stnmllr.com/fisher/` listet **11 Ticker inklusive `EDV.L`** (vorher 10).
- Auf `…/ticker/EDV.L.html` steht `Bewertungs-Range: n/a (FX: Listing≠Reporting)` **ohne ⚠**,
  und die Fußnote nennt nur noch den echten D/E-Defekt (PR #57).

Der Schritt hat jetzt eine Stelle: `Vault/Wissen/Finanzen/FisherScreen/fisherscreen Tool B
manueller Lauf.md`, Abschnitt „Veröffentlichen (Viewer)", direkt neben dem Tool-B-Aufruf.
Damit ist die im Befund unten gestellte Frage beantwortet — **dokumentierte Stelle**, nicht
sichtbares Erzeugungsdatum. Ein Automatismus bleibt ausgeschlossen.

### Drei Dinge, die der erste echte Upload zutage gefördert hat

1. **`/var/www/fisher/` gehörte `root`.** Der August-Deploy lief laut `AUTH.md` als Root, also
   scheiterte `scp` als `stef` mit `dest open …: Permission denied` — pro Datei, während die
   drei Dateien der obersten Ebene teils schon durch waren. Einmalig behoben mit
   `ssh -t … "sudo chown -R stef:stef /var/www/fisher"`. Das `-t` ist nötig, sonst kann
   `sudo` nicht fragen. Kommt wieder, falls das Verzeichnis je neu als root angelegt wird.

2. **Der `!`-Prefix in Claude Code hat kein TTY.** `ssh` kann dort nicht nach der Passphrase
   fragen und scheitert mit `Permission denied (publickey)` — das sieht wie ein
   Schlüsselproblem aus und ist keines. Deploy-Schritte gehören in ein echtes `cmd.exe`-Fenster.

3. **Für `/fisher/` setzt Caddy keinen `Cache-Control`-Header.** Unmittelbar nach dem Upload
   zeigte die Übersicht noch zehn Ticker, während die Detailseiten bereits neu waren — ein
   gemischtes Bild, das in sich stimmig aussieht. Es lag am Browser-Cache, nicht am Server;
   mit `?cachebust=1` erschienen alle elf. **Das ist dieselbe Ausfallart wie die veraltete
   Seite selbst, eine Ebene tiefer: es sieht aktuell aus.** Ein `header /fisher/*
   Cache-Control "no-cache"` im Caddyfile würde es abstellen — die Datei liegt im
   macro-dashboard-Repo, also gilt dort dieselbe Vorsicht wie unten: eine Auflage, die in
   einem anderen Repo abgehakt wird, kommt von selbst nicht zurück. Nicht gebaut, bewusst:
   erst beobachten, ob es im Alltag stört.

### Weiterhin offen, aber nicht in diesem Ticket

Die Probe im **frischen privaten Fenster** ist nach wie vor nicht nachgeholt. Alle Prüfungen
liefen mit bestehender Sitzung und umgehen damit `/oauth2/start` → Google → Rücksprung, also
genau den Pfad der dokumentierten Redirect-Schleife. Sie ist vermutlich am 21.08. erfüllt
worden, nur nicht vermerkt; ein einmaliger Handgriff bei nächster Gelegenheit.

## Befund 2026-09-06: der Deploy ist längst passiert

Dieses Ticket galt bis heute als „ältester offener Punkt, gemergt aber nicht deployt".
Nachgeprüft am 2026-09-06, im Browser hinter dem echten Google-Gate:

**`https://macro.stnmllr.com/fisher/` liefert den Viewer.** Die Seite lädt, die Sitzung
greift, die Übersichtstabelle steht. Die Auflagen unten sind zum größten Teil bereits
erfüllt — nur hat das niemand hier vermerkt, und `Projektstand.md` trug den falschen Stand
weiter.

| Auflage / Punkt | Stand |
|---|---|
| Caddy-Block `/fisher/*` hinter `import authgate` | ✅ live, Seite lädt hinter dem Gate |
| `AUTH.md` im macro-dashboard-Repo nachgezogen | ✅ Abschnitt „Stand 21.08.2026", inkl. Caddyfile-Block und Tests |
| Rücklink auf der Dashboard-Seite | ✅ „FisherScreen Deep Dives →" → `/fisher/` |
| Login-Flow von Hand durchgegangen | ✅ Seite lädt mit bestehender Sitzung; die Probe im **frischen privaten Fenster** bleibt Stephans Schritt (siehe unten) |
| `--site` als Opt-in in der Deep-Dive-CLI | ✅ gebaut 2026-09-06, siehe unten |
| **Auffrischung des ausgelieferten Inhalts** | ✅ nachgeholt 2026-09-07, siehe „Abschluss" oben |

### `--site` ist gebaut

`uv run python -m app.deepdive deepdive <TICKER> --site` rendert nach dem Dossier die
Site neu. Opt-in, nie Vorgabe — ohne die Flag ist der Pfad byte-identisch zu vorher.

Die Auflage des Tickets („ein Renderer-Bug darf den Exit-Code eines 20-Minuten-Laufs nicht
ändern") ist an drei Stellen ernst genommen worden, zwei davon über den Wortlaut hinaus:

- Der **Rückgabewert** des Viewers wird wie eine Exception behandelt. `app.viewer.__main__`
  meldet eigene Fehler durch `return 1`, nicht durch Werfen — ein reiner `except`-Wrapper
  hätte ausgerechnet den wahrscheinlichsten Renderer-Fehler durchgelassen.
- **`SystemExit`** liegt mit im Netz: der Seam ist ein CLI-Einstiegspunkt, eine künftige
  argv-Änderung im Viewer käme als `argparse`-`sys.exit(2)`. `KeyboardInterrupt` bleibt
  bewusst draußen — ein Abbruch durch den Nutzer ist kein Renderer-Bug.
- **`sys.stdout.flush()`** vor dem Render, nur im `--site`-Zweig: bei Umleitung in eine
  Datei ist stdout blockgepuffert, und ein hängender Renderer verschluckte sonst genau die
  Zeile, für die bezahlt wurde.

Scheitert der Render, sagt die Ausgabe, wo das Dossier liegt **und** dass die Site nicht
aufgefrischt wurde. Der Exit-Code bleibt der des Laufs ohne die Flag — so getestet, nicht
gegen die Konstante 0 behauptet.

### Das eigentliche verbliebene Problem: der Inhalt altert still

Die ausgelieferte Seite zeigt **10 Ticker**. Ein lokaler Build aus demselben Repo
(`uv run python -m app.viewer --in output\Watchlist --out output\site`) erzeugt **11** —
`EDV.L` fehlt, das erste Quant-only- und erste London-Dossier vom 2026-09-03. Der Stand
draußen ist der vom Deploy-Tag.

Das ist der Preis der bewussten Entscheidung, keinen Deploy-Code in den Generator zu legen:
ein manuelles `scp` passiert einmal und dann nicht mehr. Der Viewer behauptet nichts
Falsches — er zeigt schlicht einen älteren Bestand, ohne dass ihm das anzusehen wäre. Für
einen Lesekanal „für unterwegs" ist genau das die gefährliche Ausfallart: er sieht aktuell
aus.

**Zwei Wege, und die Wahl ist nicht offensichtlich.** Entweder das `scp` bleibt manuell und
bekommt eine Stelle, an der es *steht* (README des Repos, neben dem Tool-B-Aufruf) — dann
ist die Auffrischung ein bewusster Schritt und der Viewer darf altern. Oder die Seite
bekommt ein sichtbares Erzeugungsdatum, damit „alt" im Produkt steht und nicht nur im Kopf
des Betreibers. Das Zweite ist billiger als es klingt und passt zur Ehrlichkeits-Linie des
Projekts; das Erste ändert am Verhalten nichts. Beides schließt einen Automatismus nicht
ein — der bleibt ausgeschlossen, siehe „Context" unten.

### Was noch offen bleibt

- **`--site` als Opt-in** — der einzige unerledigte Punkt aus der ursprünglichen Liste.
- **Die Probe im frischen privaten Fenster** ist nicht nachgeholt worden und lässt sich von
  außen auch nicht ersetzen: die heutige Prüfung lief mit bestehender Sitzung, das umgeht
  genau den Pfad (`/oauth2/start` → Google → Rücksprung), auf dem die dokumentierte
  Redirect-Schleife entstünde. `curl -sI` fängt sie ebenfalls nicht — deshalb steht die
  Auflage weiter. Sie ist vermutlich am 21.08. erfüllt worden, nur nicht vermerkt.

## Context

`app/viewer` renders the Tool-B dossiers into a self-contained static site
(`uv run python -m app.viewer --in output\Watchlist --out output\site`). Everything it
emits uses relative paths and an external stylesheet and script, so it works from
`file://` and from any sub-path without change. Deploying it is therefore a file-sync
problem, deliberately kept out of the generator: a generator that writes to a production
server unasked is a surprise, and the target was never specified in code.

## The target is not what the original spec assumed

The spec described nginx with Basic Auth and "extend the existing deploy script". None of
that holds. Verified against `D:\programme\macro-dashboard` (`AUTH.md`, `README.md`):

| assumed | actual |
|---|---|
| nginx | **Caddy 2.11.2**, `/etc/caddy/Caddyfile`, automatic HTTPS |
| Basic Auth | **Google login via `oauth2-proxy`** since 2026-08-12; `basic_auth` was removed outright |
| an existing deploy script | **none exists** — the README documents a manual `scp` |
| — | host `macro.stnmllr.com`, docroot `/var/www/macro-dashboard`, server `tools-prod-01` |

## Plan

Serve the site at `/fisher/` on `macro.stnmllr.com` from `/var/www/fisher/`, inside the
existing `handle {}` block behind `import authgate`. No new DNS record, no second OAuth
redirect URI, same session (the cookie is scoped to `.stnmllr.com`). The access gate is
therefore stronger than the spec assumed, not weaker.

## Two obligations that belong in the same working session

1. **Update `AUTH.md` in the macro-dashboard repo.** The `/fisher/` route lives in *that*
   repo's configuration, not this one. A Caddyfile change recorded nowhere is the kind of
   drift that produced the nginx/Basic-Auth mismatch above in the first place.

2. **Walk the login flow by hand after the reload — `curl -sI` returning 302 is not
   enough.** `AUTH.md` documents the precedent: with directives written flat instead of
   inside `handle` blocks, `/oauth2/start` ran through the gate itself, answered 401, and
   redirected to itself — `ERR_TOO_MANY_REDIRECTS`, with an URL carrying dozens of nested
   `rd=` parameters. A status-line check does not catch that; opening the page in a fresh
   private window does. Use a fresh window: one that has already been in a redirect loop
   caches it.

Alongside those, the usual proof that nothing is served unauthenticated:

```
curl -sI https://macro.stnmllr.com/fisher/            # expect 302, never 200
curl -sI https://macro.stnmllr.com/fisher/index.html  # expect 302
```

## Also then

Add the reciprocal link on the dashboard side (`/fisher/`), matching the "← Macro Risk
Monitor" link the viewer already renders in its header.

Wire `--site` into the deep-dive CLI as an **opt-in**, never a default: a renderer bug
must not be able to change the exit code of a 20-minute paid Gemini run.
