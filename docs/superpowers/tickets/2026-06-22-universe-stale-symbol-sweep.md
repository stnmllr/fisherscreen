# Ticket: Universe symbol-hygiene sweep — 8 tickers yield an empty revenue series (suspected stale/wrong symbols)

**Opened:** 2026-06-22
**Priority:** non-blocking for the 01.07 monthly run; data-quality follow-up.
**Status:** open

## Context

The pre-01.07 warm-up of `dev_revenue_series`
(`scripts/backfill_revenue_series.py`, verified via `scripts/backfill_verify.py`)
covered **1314 / 1322** universe tickers with real multi-year revenue data.
The remaining **8 return an empty income statement from yfinance** —
consistently, not transiently:

```
AMS.VI  GLB.IR  OVV  RIGN.SW  RNL.PA  ROL.L  SANO.HE  SCHA.OL
```

`CachedRevenueSeries.get_revenue_series` correctly leaves empty fetches uncached
(fail-distinct-from-empty, `revenue_series_cache.py:41`), so these are not masked
as stale — they simply have no revenue series and will be skipped by the
monthly run's missing-data path. **No deadline or correctness impact on the
monthly run** (8 cold fast no-data fetches are negligible against the 1800s budget).

## Suspicion: stale/wrong exchange symbols

At least two look like the **same bug class as Roche `RO.SW` → `ROP.SW`**
(see memory `roche-dual-line-fix-and-sweep-n1`; OpenFIGI method reusable):

- `RIGN.SW` — Richemont trades on SIX as **`CFR.SW`**, not `RIGN.SW`.
- `AMS.VI` — ams-OSRAM moved its primary listing from Vienna to SIX (**`AMS.SW`**).

If the symbol is wrong, the ticker is silently dataless across *every* gate
(revenue series, EDGAR, peer-quant), i.e. effectively absent from the universe
while still counted in the 1322. The other six (`GLB.IR`, `OVV`, `RNL.PA`,
`ROL.L`, `SANO.HE`, `SCHA.OL`) need the same check — each could be a genuine
yfinance coverage gap or a wrong/relisted symbol.

## Scope (this ticket)

1. For each of the 8, determine **wrong-symbol vs genuine-data-gap**:
   - Resolve the correct primary-exchange symbol (OpenFIGI / issuer lookup, reuse
     the Roche-sweep method).
   - Confirm whether the corrected symbol yields a yfinance revenue series.
2. **Fix wrong symbols at the source** (`data/universe.json` and wherever the
   universe is generated) — do not patch per-call.
3. Leave genuine data-gaps documented (acceptable attrition) so they are not
   re-investigated each run.
4. Re-run `scripts/backfill_verify.py`; coverage should rise by the number of
   corrected symbols.

## Acceptance

- [ ] Each of the 8 is classified: corrected-symbol or confirmed-data-gap.
- [ ] Corrected symbols land in the universe source and resolve to a non-empty
      revenue series (verified via `backfill_verify.py`).
- [ ] Confirmed data-gaps recorded here so the residual is a known, bounded set.
- [ ] No regression: the 1314 already-covered tickers stay covered.

## Related

- Method precedent: `roche-dual-line-fix-and-sweep-n1` (RO.SW→ROP.SW, OpenFIGI sweep).
- Universe attrition precedent: `universe-completeness-degraded-dict-masking-closed`
  (yfinance silent attrition → fail-loud on no-name∧no-marketCap; 5 UNCLEAR residual).
- Warm-up + verify: `scripts/backfill_revenue_series.py`, `scripts/backfill_verify.py`.
- Cache fail-distinct-from-empty: `app/services/revenue_series_cache.py:41`.
