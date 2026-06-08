## STUFE B — universe.json corrections/prune + generator normalization

Follows STUFE A (#21, degraded-dict masking). Applies the **verified** delta from the independent completeness audit (`docs/superpowers/audits/2026-06-03-universe-completeness/unresolved35_classified.csv`) and closes the systematic generator gap that produced the broken Nordic class-share tickers.

### 1. universe.json data delta — `1349 → 1332`
Assertion-guarded transform (`apply_universe_corrections.py`); every change sourced from the verified classification.

| Action | n | Tickers |
|---|---|---|
| **Correct in place** (real co, verified yfinance ticker) | 13 | AKERBP.OL→AKRBP.OL, ASMI.AS→ASM.AS, ATCOa.ST→ATCO-A.ST, BDEV.L→BTRW.L, DSM.SW→DSFIR.AS, EFGI.PA→EFGN.SW, ERICb.ST→ERIC-B.ST, FLTR.IR→FLTR.L, HMB.ST→HM-B.ST, ICP.L→ICG.L, INDV.L→INDV, INP.L→INVP.L, TEV→TEVA |
| **Delete benign dup** (correct ticker already in universe) | 5 | ELUXb.ST, LIN.L, NGG.L, SKFb.ST, TEL2b.ST |
| **Prune delisted/acquired** | 12 | DLG.L, LUN.ST, MAN.DE, MOR.DE, MRW.L, NEOEN.PA, SMDS.L, SOW.DE, SWMA.ST, TPG.L, UN01.DE, VAR1.DE |
| **UNCLEAR — left untouched** | 5 | AMS.VI, RIGN.SW, ROL.L, SANO.HE, SCHA.OL |

Decomposition: `1349 − 5 (benign) − 12 (prune) + 13 − 13 (corrections net 0) = 1332`. The transform asserts no unintended add/remove (symmetric diff = exactly these edits) and fails loud otherwise.

The 13 corrected names are real, healthy companies (Ericsson, Atlas Copco, H&M, ASM International, DSM-Firmenich, Flutter, ICG, Teva, Indivior, Barratt Redrow, Aker BP, EFG, Investec) that previously resolved to degraded yfinance dicts and were silently dropped — exactly the attrition STUFE A made visible.

### 2. Generator normalization (`scripts/build_universe.py`)
`build_universe.py` only normalised space-separated multi-class tickers. Nordic class shares with a trailing lowercase letter (`ERICb`) passed through unnormalised → don't resolve. Added a conservative `_normalise_class_suffix` (fires only on `^[A-Z0-9]{2,}[abc]$`) wired into both ticker-building paths. All-caps concatenated forms (`HMB`) are deliberately **not** split (ambiguous; fixed at the data level above).

**Honesty note:** the generator change is defense-in-depth and could **not** be validated against the live Wikipedia/iShares source in the sandbox (no network). Over-reach is fenced by tests (`BRK-B`, `AAPL`, `HMB`, `Ab`, `ABCd` unchanged).

### Tests (TDD, fixtures-only)
17 new cases in `tests/test_build_universe.py` (5 positive, 10 over-reach guards, 2 integration). Full suite **739 passed, coverage 97.26 %** (verified locally).

### Out of scope (separate decisions/tickets)
Financials/gross_margin scope, revenue_growth≥0 on a TTM snapshot, resolving the 5 UNCLEAR (data-source), affirmative GC TRUE branch.

### Verification gate (post-merge/deploy)
Cold dry-run with caches purged: pipeline `yfinance_unresolved` must **converge** with the independent `re_resolution.py` count — no longer falsely 0, but the honest residual (~the 5 UNCLEAR), and the 13 corrected names resolve with full data.

Refs: `report.md`, `unresolved35_classified.csv`.
