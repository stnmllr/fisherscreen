# Ticket: `app/deepdive/compose.py` sits at 71 % coverage — visible only after the `exclude_lines` anchor fix

**Opened:** 2026-09-03
**Priority:** low, but real. Wiring code, no logic — yet it is the layer that assembles every Tool-B collaborator, so a wrong wire fails at runtime with no test to catch it.
**Status:** open

> **The config defect that surfaced this is FIXED in the quant-only-dossier PR**, not left
> open. `[tool.coverage.report] exclude_lines` was the unanchored `"\.\.\."`, which matched
> `Callable[..., X]` in signatures; coverage.py then dropped the **entire enclosing
> function** from the measurement. `app/deepdive/pipeline.py` reported 25 statements for a
> 209-line file — both `run_deep_dive` and `_quant_only_dossier` were invisible. The
> anchored form `"^\s*\.\.\.$"` still excludes every genuine Protocol/stub body while no
> longer matching a `...` inside a subscript. Measured before landing: denominator 3969 →
> 4105 statements, total coverage 98 %, so the 90 % floor is not endangered.
>
> This ticket carries only what the fix *revealed*.

## Context

With the honest pattern, `app/deepdive/pipeline.py` turns out to be genuinely at
**51 statements / 100 %** — the hidden code was covered, it just was not counted. One file
does not come out well:

```
app\deepdive\compose.py         62   18    71%   56, 77-78, 91-112, 116-133, 137
```

The uncovered ranges are the bodies of `build_quant_builder` (91-112) and
`build_peer_resolver` (116-133) — the two builders that return closures — plus
`build_synthesizer` (137) and parts of `build_eu_resolver` (56) and
`build_filing_fetcher` (77-78).

## Why it is worth something despite being "just wiring"

`compose.py` is where every collaborator is constructed and handed to `run_deep_dive`.
There is no logic to get wrong, but there is plenty of *wiring* to get wrong: a
cache-directory constant pointed at the wrong path, a TTL passed in the wrong argument
slot, a settings field renamed on one side only. All of those pass type checking, pass
every unit test that mocks the collaborators, and fail at runtime on a paid run.

`tests/deepdive/test_compose.py` already establishes the pattern that works here:
`patch("app.deepdive.compose.EdgarClientImpl")` and friends, keeping the real wrapper
object under test while stubbing only the config-dependent leaf client. The closure
builders are simply not covered by it yet.

Precedent for the risk: the `negative_ttl_days` parameter added in the quant-only change
is passed from `build_eu_resolver` and is deliberately keyword-only *without* a default,
precisely so caller and tests cannot drift apart silently. That guard exists because the
wiring layer is untested.

## Scope (this ticket)

- Extend `tests/deepdive/test_compose.py` to cover the closure builders: assert that
  calling the returned closure forwards the expected arguments to the underlying function
  (`build_quant_snapshot`, `resolve_peers`), including the settings-derived values
  (collection names, TTLs, cache paths).
- Decide explicitly whether `build_synthesizer` deserves a test or is trivial enough to
  leave — do not cover it just to move the number.
- Do **not** chase 100 %. The goal is that a mis-wired argument fails a test, not a
  percentage.

## The same gap, one layer up: nothing tests resolver-to-pipeline

Surfaced while deciding *against* adding a US-path pipeline test for the quant-only
change. `run_deep_dive` branches on `resolved.has_filing_source` and never reads the
reason code (grep over `app/` shows every consumer of `no_sec_source_reason` merely
passing it through into the record, the front matter or the cache). So a second
pipeline test per reason code would be duplication.

But that reasoning exposed something real: **`tests/deepdive/test_pipeline.py` mocks the
resolver away entirely** (`resolver.resolve.return_value = no_sec_source(...)`), and no
test anywhere wires the real `ADRResolver` into `run_deep_dive`. That holds for the
normal path as much as for the degraded one. Each part is tested; the seam between them
is not — which is the same class of risk as the untested builders above, one layer up.

Worth deciding together with the builder tests, since a single test that composes the
real resolver, a stubbed EDGAR client and the pipeline would close both at once.

## Out of scope

- Raising or lowering the 90 % floor. The floor is policy; the anchor fix only made the
  number it is applied to honest.
- `app/services/*`, which is deliberately in `[tool.coverage.run] omit`.

## Reproduction

```
uv run python -m pytest -m "not integration" -q
```
and read the `app\deepdive\compose.py` row of the coverage table.
