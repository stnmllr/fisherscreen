# Ticket: Tool B labels GBP figures as `GBp` for London listings — the minor-unit normalisation exists only in Tool A

**Opened:** 2026-09-03
**Priority:** correctness, but narrow: only listings quoted in a minor unit are affected, and today that is London (`GBp`) alone. Not a regression — the defect is as old as the deep-dive quant block; it was simply unreachable until the first LSE dossier could be produced. Fix before an LSE title reaches the Watchlist for a real decision.
**Status:** open

## Context

The first-ever London deep dive (`EDV.L`, Endeavour Mining, 2026-09-03, produced by
the quant-only path) renders:

```
*Market Cap: 11,429,440,512 GBp · Gross Margin: 64.4% · Op. Margin: 46.9%*
Kapitalstruktur: Total Debt 1,079,699,968 GBp · Cash 1,251,800,064 GBp · …
Analyst Consensus: buy · Target: 4640.11 (Median 4574.016) · 9 Analysten
```

Read literally, the market cap is 11.4 billion **pence** — £114 million. Endeavour
Mining is a ~£11 billion company. The number is right; the **unit label is wrong by a
factor of 100**.

### Proof

Straight from `yfinance` for `EDV.L`:

```
currency          = GBp
financialCurrency = USD
price             = 4632.199
sharesOutstanding = 241025722
marketCap         = 11164791808
price * shares    = 1,116,479,108,423
marketCap / (price * shares) = 0.0100
```

The ratio is exactly 1/100. So within one `info` dict yfinance mixes units:

- `price` is in the **minor** unit (pence)
- `marketCap` is in the **major** unit (pounds)
- `currency` reports `GBp`, which is true for the price and false for the market cap

A single dossier therefore prints both units under one label: `Market Cap … GBp` is
pounds, while `Target: 4640.11` on the next line really is pence.

### Root cause

Tool A already solves this, and documents the exact semantics
(`app/models/screener_record.py:12-13` and `:121-128`):

```python
_MINOR_UNIT: dict[str, tuple[str, int]] = {"GBp": ("GBP", 100)}
...
# Normalize minor-unit quotes (e.g. London pence) to the major unit + ISO currency,
# so price is consistent for every consumer and the FX lookup hits a real ISO code.
# marketCap is already in the major unit — only price is rescaled.
```

`ScreenerRecord.from_yfinance_info` rescales the price and relabels the currency to
the ISO code. **Tool B does neither.** `app/deepdive/quant_join.py::_pit_from_info`
copies `info["currency"]` through unchanged, and `app/deepdive/valuation_block.py:102`
renders it verbatim (`ccy = pit.currency or ""`). The normalisation lives in a Tool-A
*model*, not in a shared place, so the deep-dive path never sees it.

### Why it stayed invisible until now

There has never been a London dossier. `output/Watchlist/` contains only US tickers
plus `ASML.AS` (EUR) and `NOVO-B.CO` (DKK) — both major-unit quotes, where
pass-through is correct. `ULVR.L` sits in the static ADR table but was never run.
The quant-only path is what finally made an LSE deep dive producible, which is how
this surfaced; the defect itself predates it and is independent of it.

## Not the same as the FX gate

`compute_valuation_history` already refuses the multi-year bands when
`listing_ccy != financial_ccy` (`app/deepdive/valuation_history.py:117`), and it fired
correctly here — the dossier says `Bewertungs-Range: n/a (FX: Listing≠Reporting)`.
That gate is about **listing currency vs. reporting currency** (GBp vs. USD) and works
as designed. This ticket is about **minor vs. major unit within the listing currency**
(GBp vs. GBP), which no gate covers. Fixing one does not fix the other.

Note that the FX gate masks part of the damage today: the multiples that would mix a
pence price with a pound cap are skipped anyway for `EDV.L`. A London issuer that
*reports in GBP* would not be skipped — and would produce silently wrong multiples.
That case has not been observed yet; see Scope.

## Scope (this ticket)

- **Decide where the normalisation belongs.** It is currently a private constant in a
  Tool-A model. Candidates: a shared helper both tools call; normalising inside
  `yfinance_client` so every consumer is served (widest blast radius, but the single
  honest place — the client is the thin wrapper that owns the external contract); or
  duplicating it into `quant_join`. Per CLAUDE.md's service-layer rule the wrapper is
  the natural home, but that changes Tool A's input too and needs its own verification.
- **Establish whether a GBP-reporting London issuer produces wrong multiples**, i.e.
  whether the pence price is combined with pound-denominated fundamentals anywhere the
  FX gate does not already stop. Construct the case from the 111 `.L` tickers in
  `data/universe.json` rather than reasoning about it — `scripts/diagnose_price_units.py`
  already exists and may cover part of this.
- **Extend the currency map only for listings that actually occur.** The Tool-A comment
  names `ZAc` and `ILA` as the same class with the explicit instruction to add them
  when a listing appears. Do not add them speculatively.
- **Regression fence:** `ASML.AS` (EUR) and `NOVO-B.CO` (DKK) dossiers must be
  bit-identical after the change — major-unit quotes must not be touched.

## Out of scope

- The `D/E` unit question. `EDV.L` renders `D/E 29.4`, which is the known
  altbestand defect already recorded for every existing dossier; it is a separate
  quantity with a separate cause.
- The FX gate itself (`valuation_history.py:117`) — it is correct and should stay.
- Backfilling existing dossiers. None are affected: no London dossier exists apart
  from `EDV.L_2026-09-03.md`, which should simply be regenerated after the fix.

## Reproduction

```
uv run python -m app.deepdive deepdive EDV.L --peers "HL,NEM,AEM"
type output\Watchlist\EDV.L_2026-09-03.md
```
The `Market Cap: … GBp` line in `## Bewertung` is the defect.
