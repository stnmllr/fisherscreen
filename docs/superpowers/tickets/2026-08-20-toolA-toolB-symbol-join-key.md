# Ticket: Tool A / Tool B disagree on the symbol for dual-listed names (ARGX vs ARGX.BR)

**Opened:** 2026-08-20
**Priority:** non-blocking; data-completeness follow-up. No wrong numbers are produced —
a correct join is silently skipped.
**Status:** open

## Context

The 2026-08-20 deep dive on argenx ran as ticker `ARGX` (Nasdaq, CIK 0001697862, 20-F).
Two lines in its Source Coverage record the consequence:

```
- Quant (Punkt-in-Zeit): live-yfinance
- Tool-A-Dimensionen: absent (nicht im letzten Monatslauf)
```

Neither is a failure of the deep dive. Both follow from a **namespace mismatch between the
two tools**:

- `data/universe.json:105` carries the name as **`ARGX.BR`** (Euronext Brussels) — that is
  the symbol Tool A screens, caches (`dev_ticker_cache`, `dev_revenue_series`) and scores.
- Tool B was invoked as **`ARGX`**, which is the correct symbol for the EDGAR/ADR path
  (`app/deepdive/adr_resolver.py` routes dotted tickers to the EU-ADR resolver; the
  undotted US symbol resolves directly to the CIK).

So the deep dive looked up `ARGX` in the Tool-A cache, found nothing, and correctly fell
back to a live yfinance fetch plus an honest `absent` label. The screener's dimension
scores for the same company — filed under `ARGX.BR` — were never joined.

## Not a duplicate of the stale-symbol sweep

`tickets/2026-06-22-universe-stale-symbol-sweep.md` covers **8 tickers whose yfinance
income statement comes back empty** (`AMS.VI`, `GLB.IR`, `OVV`, `RIGN.SW`, `RNL.PA`,
`ROL.L`, `SANO.HE`, `SCHA.OL`) — suspected stale or wrong exchange symbols. `ARGX.BR` is
not among them: it resolves fine and has a revenue series. The defect here is not a *wrong*
symbol; it is **two correct symbols for one company with no mapping between them**.

## Why it matters more than one missing label

1. The `Tool-A-Dimensionen: absent` line reads like "this name was not screened last
   month". For argenx that is false — it was screened, and it scored well enough to reach
   the 07/2026 crosshits. The honest label is honest about the *join*, not about the
   *company*, and a reader cannot tell the difference.
2. Every dual-listed EU name reachable through a US filing has the same shape. The deep
   dives run so far include `ASML` and `ASML.AS` as **separate dossiers** for one issuer —
   same root cause, visible in `output/Watchlist/`.

   **Refinement found while building the viewer (2026-08-20):** those two are not simply
   one company under two symbols. Their H1 lines read

   ```
   ASML_2026-05-26.md     # Deep Dive: ASML Holding N.V. - New York Re (ASML)
   ASML.AS_2026-06-18.md  # Deep Dive: ASML HOLDING (ASML.AS)
   ```

   The first name is Yahoo's `shortName`, truncated at 31 characters from "…New York
   Registry Shares". So the two dossiers cover **two different share lines of the same
   issuer** — the New York registry line and the Amsterdam ordinary. Any join key must
   therefore resolve to the *issuer*, not to a security: ISIN identifies the line, not the
   company, and would keep these two apart. CIK or LEI identifies the issuer. That is a
   real constraint on the choice below, and it is the reason the viewer deliberately shows
   both rows rather than merging them.

   It also means the truncated `shortName` is itself worth a look: it is the only
   human-readable identity the dossier carries, and it arrives pre-mangled from Yahoo.
3. The Tool-A cache miss forces a live yfinance fetch on every such run. Harmless today,
   but it silently removes the cache's consistency guarantee (screener and deep dive can
   then disagree on the same quarter's numbers).

## Scope (this ticket)

- Decide the canonical join key — and note the ASML finding above narrows the field:
  the key must identify the **issuer**, not the security.

  This exposes a latent tension in `tickets/2026-06-03-isin-canonical-anchor-openfigi.md`.
  That ticket states plainly that "die ISIN identifiziert das **Wertpapier** eindeutig",
  yet frames its goal as a universe that is "company-identity-getrieben statt
  symbol-getrieben". For a single-line issuer those coincide, which is why the tension
  never surfaced. ASML shows where they part: its New York registry line and its Amsterdam
  ordinary carry different ISINs, so an ISIN anchor keeps the two dossiers apart — correct
  for that ticket's purpose (survive renames and exchange moves for *one* line), wrong for
  this one (recognise one issuer across lines).

  Candidates, then: CIK identifies the issuer but exists only for SEC filers. LEI
  identifies the issuer generally but is not in the pipeline today. An explicit alias map
  `US-symbol ↔ universe-symbol` sidesteps identity entirely at the cost of manual upkeep.
  Decide deliberately; do not inherit the ISIN choice by default.
- Make the Tool-A lookup in the deep dive alias-aware, so `ARGX` finds `ARGX.BR`.
- Distinguish the two cases in `SourceCoverage.gemini_dims`: *not screened last month* vs
  *screened under a different symbol, join failed*. Today both render as `absent`. Same
  failure class as `distinguish-failure-from-empty-result`.
- Sweep `output/Watchlist/` for further split identities (`ASML` / `ASML.AS` confirmed) and
  count how many universe entries carry a non-US listing while having a US filing path.

## Out of scope

The ISIN anchor itself — that is `tickets/2026-06-03-isin-canonical-anchor-openfigi.md`.
This ticket should either consume that decision or explicitly choose the cheaper alias map
and say why.
