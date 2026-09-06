# Ticket: Deploy the viewer as /fisher/ behind the existing OAuth gate

**Opened:** 2026-08-20
**Priority:** blocked on nothing technical; waiting for a deliberate deploy window.
**Status:** open — **aber nicht mehr aus dem Grund im Titel.** Der Deploy ist erfolgt; offen ist, dass niemand ihn nachgetragen hat und dass es keine Auffrischung gibt. Siehe „Befund 2026-09-06".

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
| `--site` als Opt-in in der Deep-Dive-CLI | ❌ nicht gebaut |
| **Auffrischung des ausgelieferten Inhalts** | ❌ **es gibt keine** — siehe unten |

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
