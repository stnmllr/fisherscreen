## STUFE A — Fix yfinance degraded-dict masking (silent attrition)

### Problem
The independent universe-completeness audit (`docs/superpowers/audits/2026-06-03-universe-completeness/`) found that the cold-run's `yfinance_unresolved = 0` was **misleading**. Independently, **35 of 1349** universe tickers do not cleanly resolve — and **0 of them were transient** (each confirmed by a clean re-probe).

Root cause: `YFinanceClientImpl.get_ticker_info` only rejected the *empty* dict. On HTTP 404, `yf.Ticker(t).info` often returns a **non-empty but degraded** dict (a few keys, **no `shortName`/`longName` and no `marketCap`**). These passed as successful resolutions and were later dropped at the basis filter as generic missing-field misses, so the resolution aggregate (`run_basis_filter` `unresolved` list) wrongly reported **0**.

### Fix
Treat a dict with **no name and no marketCap** as unresolved (raise `DataSourceError`). `run_basis_filter` already collects `DataSourceError` into `unresolved` and logs it loud, so the attrition now surfaces instead of being masked. Criterion is intentionally minimal (`shortName` OR `longName` OR `marketCap` = valid) to avoid over-reach on real tickers (AAPL, BRK-B unaffected).

```
if not (data.get("shortName") or data.get("longName") or data.get("marketCap")):
    raise DataSourceError(f"yfinance returned degraded info for {ticker}")
```

### Tests (TDD red→green, fixtures-only, no network)
- `test_get_ticker_info_raises_on_degraded_dict_no_name_no_marketcap` (raise)
- `test_get_ticker_info_resolves_with_name_only` / `_marketcap_only` / `_with_longname` (over-reach guards)
- `test_run_basis_filter_collects_unresolved_on_degraded_dict` (aggregate propagation)

Verified independently: red without the fix (`DID NOT RAISE`), green with it — full suite **722 passed, coverage 97.26 %**.

### Scope
Bug only. Filter-design questions surfaced by the audit (financials/gross_margin, revenue_growth≥0 on a TTM snapshot) are **out of scope** and tracked separately. `universe.json` corrections/prune are STUFE B (separate PR).

### Verification gate (post-merge/deploy)
Cold dry-run with caches purged: pipeline `yfinance_unresolved` must now **converge** with the independent `re_resolution.py` count (no longer falsely 0).

Refs: `docs/superpowers/audits/2026-06-03-universe-completeness/report.md`, `unresolved35_classified.csv`.
