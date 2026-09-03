# Ticket: Deploy the viewer as /fisher/ behind the existing OAuth gate

**Opened:** 2026-08-20
**Priority:** blocked on nothing technical; waiting for a deliberate deploy window.
**Status:** open — phase 1 of the viewer ships **without** any deploy code, on purpose.

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
