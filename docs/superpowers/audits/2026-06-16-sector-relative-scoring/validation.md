# Sector-Relative Deterministic Scoring — Validation (Merge Gate)

> Date: 2026-06-16. Branch: `feature/sector-relative-scoring`.
> Method: local/offline (Way A). `scripts/validate_sector_relative_scoring.py` rebuilds the
> last run's 832-ticker pre-scoring cohort from the read-only Firestore caches
> (`dev_gemini_scores` keys + `dev_ticker_cache` metrics), applies the NEW deterministic
> scorer, and compares against the OLD (Gemini) scores. No prod run, no GitHub push, no Gemini.
> Band calibration: `scripts/calibrate_anchor_bands.py`.

## Result: PASS (with one honest, documented limitation)

Final config: anchor bands `P>=88->5, >=70->4, >=40->3, >=15->2, else 1` (loosened from 90/75).

### 1. De-clustering (spec §13.1) — STRONG PASS

The >=4 clustering is gone; distributions are now spread (mode at 3), not piled at 4.

| axis | OLD >=4 | NEW >=4 | NEW histogram (0..5) |
|---|---|---|---|
| growth | 69% | 25% | 0,125,203,293,151,60 |
| profitability | 72% | 27% | 67,38,203,299,167,58 |
| resilience | 55% | 20% | 58,26,214,367,122,45 |

(profitability 0:67 and resilience 0:58 are the absolute red-flag overlays — negative
op_margin/ROE, and d/e>300% respectively.)

### 2. Selectivity (spec §13.1) — PASS

Crosshit rate 33.8% -> 3.0% (281 -> 25). Calibration sweep that produced the choice:

| bands (>=5 / >=4) | crosshits |
|---|---|
| current 90/75 | 15 (1.8%) |
| **chosen 88/70** | **25 (3.0%)** |
| 85/65 | 43 (5.2%) |
| 85/60 | 69 (8.3%) |

Decision (Stephan): loosen "a bit" -> 88/70 (25). Still selective, no re-clustering.

### 3. Structural-bias fix / recall (spec §13.2) — PASS

- `global_fallback` fires for 6 titles, ALL Real Estate (the only sector with <30 members in
  the cohort). The N>=30 guard fires exactly where intended; profitability/resilience for those
  fall back to the global pool (marked with `⌖`).
- NEW crosshit sector spread across 9 sectors: Technology 7, Basic Materials 4,
  Communication Services 4, Healthcare 3, Consumer Cyclical 2, Energy 2, Consumer Defensive 1,
  Financial Services 1, Industrials 1. Broad, not Tech-dominated.

### 4. Spin-off safeguard (spec §13.5) — PASS (live confirmation)

Under the loosened bands, **SNDK** (Sandisk, carved out 2024, <4 fiscal years) IS a crosshit —
and it carries `data_confidence=low` (rendered `⚠`). The criterion "no <4-GJ title reaches
crosshit WITHOUT the flag" holds: it reaches crosshit but is flagged, never hidden.

### 5. Anti-cyclical (spec §13.4) — PARTIAL (documented v1 boundary)

| ticker | growth OLD->NEW | consistency | rev_growth |
|---|---|---|---|
| NEM | 5 -> **4** (capped) | 0.67 (one down year) | +45.8% |
| HL | 5 -> 5 (not capped) | 1.00 | +100.4% |
| EDV.L | 4 -> 5 | 1.00 | +29.5% |

The consistency cap catches a SINGLE spike amid flat/down years (NEM), but a MULTI-year
commodity uptrend grows revenue every year -> consistency=1.00 -> not capped (HL, EDV.L).
This is the documented v1 limitation, not a defect: revenue-growth consistency != non-cyclical.
**Decision (Stephan): accept v1; full cyclicality fix (margin consistency / multi-year price
normalization) is deferred to v2.**

## Deferred decision resolved: partial-evidence flagging

Measured: profitability partial (exactly 1 of 2 inputs) = 46/832 (5.5%), resilience = 39/832
(4.7%), none all-empty. Among the 25 crosshits, **7 rest on >=1 partial axis**. Low cohort
volume but concentrated on the high-stakes candidate list.
**Decision (Stephan): flag it** — own marker `~` (implemented T14), independent of `⌖`/`⚠`.

## Output markers (legend)

- `⌖` — a sector-relative axis fell back to the global pool (thin/absent sector).
- `⚠` — `data_confidence=low` (e.g. <4 fiscal years / consistency unprovable).
- `~` — a merit axis scored on only one of its two inputs (partial evidence).

## Carried to v2 (not in this branch)

- Margin / multi-year price-normalized consistency (the full cyclicality fix).
- Possible per-metric (not per-sector-headcount) thin-distribution guard.

## Reproduce

```
uv run python scripts/validate_sector_relative_scoring.py   # full before/after + checks
uv run python scripts/calibrate_anchor_bands.py             # band sweep
```
(Both read-only except the harmless `dev_revenue_series` cache backfill.)
