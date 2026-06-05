# Known Data Limitations — accepted artifacts (not bugs)

Living registry of universe entries that are **deliberately accepted** as-is
because the better data point has no resolving source symbol. Each entry names
the reason, the evidence, and why no code/data fix applies. Analogous to how the
5 UNCLEAR tickers are left in place and documented rather than guessed.

A name here is **not** a pipeline bug: the pipeline behaves correctly given the
data it can reach. The limitation is upstream (Yahoo/yfinance symbology coverage).

---

## ~~Roche Holding AG — no resolving liquid line~~ — RETRACTED 2026-06-05

> **This entry was wrong.** It claimed Roche's liquid Genussschein had no
> resolving yfinance symbol. That conclusion rested on **incomplete probing**:
> only `ROG.SW` (404), `ROG.VX`, `ROGZF`, `ROG.DE`, `RHHBY`, `RHHBF` were tested —
> **`ROP.SW` was never tried.** The systematic dual-line sweep
> (`audits/2026-06-05-dual-line-sweep/`, OpenFIGI sibling discovery) found it.
>
> **`ROP.SW`** = Roche participation certificate (Genussschein), the liquid SMI
> line: resolves in yfinance as "Roche Holding AG", 324.6 CHF, **avgVol
> 1,018,486** on SIX (exch EBS) — vs the anchored bearer `RO.SW` (330.8 CHF,
> avgVol 36,420). Verified live 2026-06-05.
>
> **Roche is therefore Bucket A (FIXABLE), not Bucket B.** Proposed swap:
> `RO.SW → ROP.SW`. **Not yet applied** — queued in the dual-line-sweep Bucket-A
> proposal list; applying swaps + cold re-verification is a separate go-point.
>
> Lesson: manual symbol-probing missed a non-obvious ticker that systematic
> OpenFIGI enumeration caught. Don't trust an incomplete manual probe to declare
> a coverage gap.

---

## Volume gate is share-count based (structural note, not a per-name fix)

`MIN_AVG_DAILY_VOLUME = 100_000` counts **shares**, not traded value. High
nominal-price European shares (e.g. Lindt `LISN.SW` ~176 shares/day at ~CHF 100k
per share, mcap ~103 bn) fail this on share count while being highly liquid in
value terms. This is independent of the dual-line question and is recorded as an
observation for the separate volume-gate filter-design ticket. Not fixed here.
