Documents the universe-completeness closure and tracks the reproducible
cold-run verification kit.

**Projektstand.md** — new top-of-mind entry: silent-attrition fix (STUFE A
PR #21 / STUFE B PR #22) and its cold-run convergence verification
(yfinance_unresolved 0 -> 5 UNCLEAR, basis 695, restatement 8 bit-exact,
GC drops 0). The degraded-404-dict masking is closed and verified live.

**Scripts** — track the executable form of the cold-run-after-purge lesson:
- `scripts/purge_ticker_cache_all.py` (new)
- `scripts/trigger_cold_dry_run.py` (new)
- `scripts/purge_edgar_cache_all.py` (was untracked)

A warm cache returns degraded dicts WITHOUT calling the fixed raw client, so
verifying against a warm cache silently bypasses the fix. The purge tooling is
the durable safeguard against that failure mode reappearing; leaving it
untracked would make the lesson hollow. The one-off `diagnose_*.py` scripts
stay untracked (throwaway).

No production code touched. Reviewed hunk-by-hunk: no hardcoded project IDs or
paths in code (project/collection from settings, service URL is a CLI arg);
the only literals are in docstrings/usage examples.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
