# Ticket: Scope the `main` ruleset bypass — replace admin bypass with a dedicated automation identity

**Opened:** 2026-06-12
**Priority:** do after 01.07 (first paid monthly run); not blocking that run
**Status:** open

## Context

The prod push self-test (`POST /selftest/push`, PR #33) surfaced that the
repository ruleset **"main"** (id `17168890`, created 2026-06-02 alongside the
CI required-check bootstrap) blocks all direct Contents-API pushes to `main`
with **409 Conflict** via its `pull_request` rule. This affected not only the
self-test but the **monthly output push** (`app/main.py:run_monthly` →
`github_client.push_file` → `branch=main`), which would have failed mid-run on
01.07 after the paid Gemini scoring.

## Temporary fix in place (2026-06-12)

A bypass actor was added to ruleset `17168890`:

```json
{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
```

i.e. the **admin** repository role bypasses the ruleset. Since the only repo
collaborator is `stnmllr` (admin) and the `fisherscreen-github-token` acts as
`stnmllr`, the service can now push directly to `main`. Re-test green: HTTP 200,
sentinel commit `5e2dc98` on `origin/main`.

**Trade-off accepted until this ticket is resolved:** there is no longer a
technical gate against admin-authenticated direct pushes to `main`. The
"no push without explicit go" convention applies in a strengthened form to
compensate.

## Target state (this ticket)

Replace the broad admin bypass with a **scoped** bypass so the technical
backstop for agentic pushes to `main` returns while only the automation can
bypass:

- **Option 1 — GitHub App:** register a dedicated App, install it on the repo
  with contents:write, issue the service token from the App, and add the App as
  the only bypass actor (`actor_type: Integration`). Cleanest separation; humans
  stay fully PR-gated.
- **Option 2 — Machine user:** create a dedicated machine-user account, grant it
  `maintain` on the repo, move `fisherscreen-github-token` to that user, and set
  the bypass to `{actor_type: RepositoryRole, actor_id: 4 (maintain), bypass_mode: always}`.
  Admin (human) no longer bypasses; the machine user does.

Either way: remove the admin (id 5) bypass actor afterwards.

## Acceptance

- [ ] Dedicated automation identity issues the GitHub token (App or machine user).
- [ ] Ruleset `17168890` bypass list contains only the scoped automation actor
      (no `RepositoryRole: admin`).
- [ ] `POST /selftest/push` against prod returns 200 and lands a sentinel commit
      on `origin/main` (proves the scoped identity can push).
- [ ] A direct push to `main` by `stnmllr` (admin, human) is **rejected** by the
      ruleset (proves the human gate is back).
- [ ] PROJEKTSTAND.md decisions log updated; the 2026-06-12 temporary entry
      marked resolved.

## Reverting the temporary bypass

```
gh api repos/stnmllr/fisherscreen/rulesets/17168890 -X PUT --input <ruleset-body-with-scoped-or-empty-bypass>
```

## Related

- Self-test endpoint: `app/main.py:selftest_push` (PR #33).
- Observability follow-up: `github_client` should include the GitHub response
  body in `DataSourceError` (this 409 was diagnosed only via `gh api`, not from
  the prod log) — separate mini-PR.
