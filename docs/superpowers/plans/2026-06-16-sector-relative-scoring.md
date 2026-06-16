# Sector-Relative Deterministic Scoring (Tool A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Tool A's Gemini-judged 0–5 scoring with deterministic, code-computed scores from within-run percentiles — `profitability`/`resilience` sector-relative, `growth` cohort-global plus an absolute revenue-growth consistency cap — making Tool A LLM-free and de-clustered by construction.

**Architecture:** A new `percentile_prep` stage (after EDGAR gates, on the pre-scoring cohort) groups records by raw yfinance sector, computes within-run percentile ranks, and annotates each `ScreenerRecord`. A new deterministic scorer maps those percentiles + an absolute consistency cap + absolute red-flag overlays to the existing `gemini_dimensions` schema (name kept for output-stability), and code-templates the evidence note. Multi-year revenue series are fetched through a new long-TTL Firestore cache (`dev_revenue_series`) with a one-time pre-warm backfill script.

**Tech Stack:** Python 3.12, pydantic, pytest (DI-mocked, no network), Firestore, yfinance via service-layer wrappers, uv.

**Spec:** `docs/superpowers/specs/2026-06-16-sector-relative-scoring-design.md`

**Local invocation (SOPRA-EPDR):** always `uv run python -m pytest ...` — never the `pytest` shim.

---

## File Structure

**Create:**
- `app/screener/percentiles.py` — pure: midrank percentile + percentile→score anchor table.
- `app/screener/growth_consistency.py` — pure: consistency ratio from a revenue series + consistency cap.
- `app/screener/sector_percentiles.py` — annotate records with `input_percentiles` + `score_basis` (sector vs global, N-guard, None/negative-d/e exclusion).
- `app/screener/deterministic_scorer.py` — per-axis score, red-flag overlay, consistency cap, weakest dim, data gaps, code-templated evidence; plus the `run_deterministic_scoring` Tool-A entry point.
- `app/services/revenue_series_cache.py` — `CachedRevenueSeries` Firestore wrapper (long TTL).
- `scripts/backfill_revenue_series.py` — one-time pre-warm of `dev_revenue_series`.
- Test files mirroring each (`tests/screener/...`, `tests/services/...`).

**Modify:**
- `app/models/screener_record.py` — 4 new annotation fields.
- `app/config.py` — `revenue_series_collection`, `revenue_series_ttl_days`.
- `app/screener/runner.py` — wire `run_deterministic_scoring` into `run_screener` (replace `run_gemini_scoring`); swap `gemini` param for `revenue_cache`.
- `app/screener/compose.py` — `build_revenue_series_cache`.
- `app/main.py` — build + pass `revenue_cache` instead of `gemini`.
- `app/output/crosshits_generator.py`, `app/output/dimensions_generator.py` — render `score_basis`/`data_confidence` markers.
- `CLAUDE.md` — Tool A is now deterministic / LLM-free.

---

## Task 1: ScreenerRecord annotation fields

**Files:**
- Modify: `app/models/screener_record.py` (after the Gemini scoring block, ~line 55)
- Test: `tests/models/test_screener_record.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/models/test_screener_record.py — append
def test_scoring_annotation_fields_default_none_and_ok():
    r = ScreenerRecord(ticker="AAA")
    assert r.input_percentiles is None
    assert r.growth_consistency is None
    assert r.score_basis is None
    assert r.data_confidence == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/models/test_screener_record.py::test_scoring_annotation_fields_default_none_and_ok -v`
Expected: FAIL (`AttributeError`/`ValidationError` — fields absent).

- [ ] **Step 3: Add the fields**

In `app/models/screener_record.py`, immediately after the `gemini_data_gaps` field (~line 55), add:

```python
    # Sector-relative deterministic scoring (2026-06): set in percentile_prep + scorer.
    input_percentiles: dict[str, float] | None = None  # metric -> within-run percentile (0..100)
    growth_consistency: float | None = None            # positive_years_ratio; None = UNASSESSABLE (<4 GJ)
    score_basis: dict[str, str] | None = None          # per axis: "global" | "sector_relative" | "global_fallback"
    data_confidence: str = "ok"                        # "ok" | "low"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/models/test_screener_record.py::test_scoring_annotation_fields_default_none_and_ok -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/screener_record.py tests/models/test_screener_record.py
git commit -m "Add deterministic-scoring annotation fields to ScreenerRecord"
```

---

## Task 2: Config — revenue-series cache settings

**Files:**
- Modify: `app/config.py` (in `FisherScreenSettings`, near the other collection/TTL fields)
- Test: `tests/test_config.py` (create if absent)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from app.config import FisherScreenSettings

def test_revenue_series_cache_defaults():
    s = FisherScreenSettings()
    assert s.revenue_series_collection == "dev_revenue_series"
    assert s.revenue_series_ttl_days == 400  # annual data -> long TTL (unlike Gemini 2d)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_config.py -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Add the settings**

In `app/config.py`, after `gemini_score_cache_ttl_days` (~line 27), add:

```python
    revenue_series_collection: str = "dev_revenue_series"
    revenue_series_ttl_days: int = 400  # annual revenue changes yearly; long TTL is correct here
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "Add dev_revenue_series cache config (collection + 400d TTL)"
```

---

## Task 3: percentiles.py — midrank percentile + anchor table

**Files:**
- Create: `app/screener/percentiles.py`
- Test: `tests/screener/test_percentiles.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/screener/test_percentiles.py
import pytest
from app.screener.percentiles import percentile_rank, percentile_to_score

def test_percentile_rank_midrank_handles_ties():
    dist = [1.0, 2.0, 2.0, 4.0]
    # below=1 (the 1.0), equal=2 (the two 2.0s) -> (1 + 0.5*2)/4 = 50.0
    assert percentile_rank(2.0, dist) == 50.0

def test_percentile_rank_max_and_min():
    dist = [10.0, 20.0, 30.0, 40.0]
    assert percentile_rank(40.0, dist) == pytest.approx(87.5)  # (3 + 0.5)/4
    assert percentile_rank(10.0, dist) == pytest.approx(12.5)  # (0 + 0.5)/4

def test_percentile_to_score_anchor_bands():
    assert percentile_to_score(95.0) == 5
    assert percentile_to_score(90.0) == 5
    assert percentile_to_score(75.0) == 4
    assert percentile_to_score(40.0) == 3
    assert percentile_to_score(15.0) == 2
    assert percentile_to_score(14.9) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_percentiles.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation**

```python
# app/screener/percentiles.py
"""Pure percentile math for deterministic sector-relative scoring.

percentile_rank uses the midrank convention (ties share a rank), so the score is
stable under duplicate metric values. No I/O, no record types."""
from __future__ import annotations

# Pinned percentile -> score anchor bands (descending). P below the lowest band -> 1.
_ANCHOR_BANDS: tuple[tuple[float, int], ...] = ((90.0, 5), (75.0, 4), (40.0, 3), (15.0, 2))


def percentile_rank(value: float, distribution: list[float]) -> float:
    """Midrank percentile (0..100) of `value` within `distribution`.

    `distribution` must be non-empty and already filtered to comparable (non-None)
    values; `value` is normally itself a member. Ties: 0.5 weight (standard midrank)."""
    n = len(distribution)
    below = sum(1 for v in distribution if v < value)
    equal = sum(1 for v in distribution if v == value)
    return 100.0 * (below + 0.5 * equal) / n


def percentile_to_score(p: float) -> int:
    """Map a percentile rank (0..100) to a 0–5 anchor score (1..5; 0 is red-flag-only)."""
    for threshold, score in _ANCHOR_BANDS:
        if p >= threshold:
            return score
    return 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/screener/test_percentiles.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/screener/percentiles.py tests/screener/test_percentiles.py
git commit -m "Add pure percentile-rank + anchor-table primitives"
```

---

## Task 4: growth_consistency.py — ratio + cap

**Files:**
- Create: `app/screener/growth_consistency.py`
- Test: `tests/screener/test_growth_consistency.py`

Depends on `classify_revenue_trajectory` (`app/screener/revenue_trajectory.py`), which returns `(cagr, down_years, definedness)` and is `DEFINED` only for ≥4 fiscal years.

- [ ] **Step 1: Write the failing test**

```python
# tests/screener/test_growth_consistency.py
from app.screener.growth_consistency import consistency_ratio, consistency_cap

def test_ratio_full_growth_four_years():
    # 4 revenues -> 3 transitions, all up -> ratio 1.0
    assert consistency_ratio([100.0, 110.0, 120.0, 130.0]) == 1.0

def test_ratio_one_spike_otherwise_flat_or_down():
    # 4 revenues, transitions: +,-,- -> down_years=2 -> (3-2)/3
    assert consistency_ratio([100.0, 200.0, 150.0, 120.0]) == 1.0 / 3.0

def test_ratio_unassessable_under_four_years_is_none():
    assert consistency_ratio([100.0, 130.0]) is None       # only 2 points
    assert consistency_ratio([]) is None

def test_consistency_cap_bands():
    assert consistency_cap(1.0) == 5
    assert consistency_cap(0.75) == 5
    assert consistency_cap(0.50) == 4
    assert consistency_cap(0.49) == 3
    assert consistency_cap(None) == 4   # UNASSESSABLE -> conservative ceiling
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_growth_consistency.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation**

```python
# app/screener/growth_consistency.py
"""Absolute (non-sector-relative) revenue-growth consistency: the anti-cyclical
dampener on the growth axis. A one-year supercycle spike scores high on the global
growth percentile but, lacking multi-year consistency, is capped down here."""
from __future__ import annotations

from app.models.definedness import DefinednessOutcome
from app.screener.revenue_trajectory import classify_revenue_trajectory


def consistency_ratio(revenues: list[float]) -> float | None:
    """positive_years_ratio = (transitions - down_years) / transitions over the
    available fiscal years (oldest->newest). None when UNASSESSABLE (<4 GJ): the
    trajectory cannot establish durable growth."""
    cagr, down_years, definedness = classify_revenue_trajectory(revenues)
    if definedness is not DefinednessOutcome.DEFINED or down_years is None:
        return None
    transitions = len(revenues) - 1
    if transitions <= 0:
        return None
    return (transitions - down_years) / transitions


def consistency_cap(ratio: float | None) -> int:
    """Growth-score ceiling from consistency. None (UNASSESSABLE) -> 4 (conservative:
    an unprovable spin-off spike must not reach growth=5)."""
    if ratio is None:
        return 4
    if ratio >= 0.75:
        return 5
    if ratio >= 0.50:
        return 4
    return 3
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/screener/test_growth_consistency.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/screener/growth_consistency.py tests/screener/test_growth_consistency.py
git commit -m "Add absolute revenue-growth consistency ratio + cap"
```

---

## Task 5: sector_percentiles.py — annotate input_percentiles + score_basis

**Files:**
- Create: `app/screener/sector_percentiles.py`
- Test: `tests/screener/test_sector_percentiles.py`

Rules: `growth` input (`revenue_growth_yoy`) is always cohort-global. `profitability`/`resilience` inputs are sector-relative iff the record's sector has ≥ `MIN_SECTOR_N` members, else global fallback. `None` values are excluded from distributions. `debt_to_equity < 0` is excluded from its distribution AND from the record (buyback-driven negative equity is not distress).

- [ ] **Step 1: Write the failing test**

```python
# tests/screener/test_sector_percentiles.py
from app.models.screener_record import ScreenerRecord
from app.screener.sector_percentiles import annotate_percentiles, MIN_SECTOR_N

def _rec(ticker, sector, op=None, roe=None, gm=None, de=None, rg=None):
    return ScreenerRecord(ticker=ticker, gics_sector=sector,
                          operating_margin=op, return_on_equity=roe,
                          gross_margin=gm, debt_to_equity=de, revenue_growth_yoy=rg)

def test_small_sector_falls_back_to_global():
    # One Tech record, but a 30+ member global pool via other sectors.
    recs = [_rec(f"P{i}", "Industrials", op=0.10 + i * 0.001, rg=0.05) for i in range(MIN_SECTOR_N)]
    tech = _rec("TECH", "Technology", op=0.40, rg=0.05)
    recs.append(tech)
    annotate_percentiles(recs)
    assert tech.score_basis["profitability"] == "global_fallback"  # Technology has 1 < 30
    assert recs[0].score_basis["profitability"] == "sector_relative"  # Industrials has 30
    assert tech.score_basis["growth"] == "global"

def test_negative_debt_to_equity_excluded():
    recs = [_rec(f"I{i}", "Industrials", gm=0.30, de=50.0) for i in range(MIN_SECTOR_N)]
    buyback = _rec("SBUX", "Industrials", gm=0.30, de=-150.0)
    recs.append(buyback)
    annotate_percentiles(recs)
    assert "debt_to_equity" not in buyback.input_percentiles  # excluded from its own annotation
    # and excluded from the distribution: a normal d/e still ranks against positives only
    assert "debt_to_equity" in recs[0].input_percentiles

def test_none_metric_not_annotated():
    recs = [_rec(f"I{i}", "Industrials", op=0.10, rg=0.05) for i in range(MIN_SECTOR_N)]
    recs.append(_rec("NA", "Industrials", op=None, rg=0.05))
    annotate_percentiles(recs)
    assert "operating_margin" not in recs[-1].input_percentiles

def test_growth_is_global_across_sectors():
    recs = [_rec(f"A{i}", "Industrials", rg=0.01) for i in range(20)]
    recs += [_rec(f"B{i}", "Technology", rg=0.50) for i in range(20)]
    annotate_percentiles(recs)
    hi = next(r for r in recs if r.ticker == "B0")
    lo = next(r for r in recs if r.ticker == "A0")
    assert hi.input_percentiles["revenue_growth_yoy"] > lo.input_percentiles["revenue_growth_yoy"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_sector_percentiles.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation**

```python
# app/screener/sector_percentiles.py
"""percentile_prep: annotate the pre-scoring cohort with within-run percentile ranks.

growth (revenue_growth_yoy) is ALWAYS cohort-global. profitability/resilience inputs
are sector-relative iff the record's sector has >= MIN_SECTOR_N members, else they fall
back to the global pool (score_basis records which). None values are excluded from
distributions; debt_to_equity < 0 is excluded entirely (negative book equity is
ambiguous, not distress — see spec §5)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.screener.percentiles import percentile_rank

if TYPE_CHECKING:
    from app.models.screener_record import ScreenerRecord

MIN_SECTOR_N = 30
_GLOBAL_INPUT = "revenue_growth_yoy"
_SECTOR_RELATIVE_INPUTS = ("operating_margin", "return_on_equity", "gross_margin", "debt_to_equity")
_AXIS_INPUTS = {
    "profitability": ("operating_margin", "return_on_equity"),
    "resilience": ("gross_margin", "debt_to_equity"),
}


def _usable(field: str, value: float | None) -> bool:
    if value is None:
        return False
    if field == "debt_to_equity" and value < 0:  # negative book equity -> excluded
        return False
    return True


def _distribution(records: list["ScreenerRecord"], field: str) -> list[float]:
    return [getattr(r, field) for r in records if _usable(field, getattr(r, field))]


def annotate_percentiles(records: list["ScreenerRecord"]) -> None:
    """Set `input_percentiles` and `score_basis` on each record in place."""
    global_dist = {f: _distribution(records, f) for f in (_GLOBAL_INPUT, *_SECTOR_RELATIVE_INPUTS)}

    sector_members: dict[str | None, list["ScreenerRecord"]] = {}
    for r in records:
        sector_members.setdefault(r.gics_sector, []).append(r)
    sector_dist: dict[tuple[str | None, str], list[float]] = {}
    for sector, members in sector_members.items():
        for f in _SECTOR_RELATIVE_INPUTS:
            sector_dist[(sector, f)] = _distribution(members, f)

    for r in records:
        pcts: dict[str, float] = {}
        basis: dict[str, str] = {"growth": "global"}

        gv = getattr(r, _GLOBAL_INPUT)
        if _usable(_GLOBAL_INPUT, gv) and global_dist[_GLOBAL_INPUT]:
            pcts[_GLOBAL_INPUT] = percentile_rank(gv, global_dist[_GLOBAL_INPUT])

        sector = r.gics_sector
        use_sector = sector is not None and len(sector_members.get(sector, [])) >= MIN_SECTOR_N
        for axis, fields in _AXIS_INPUTS.items():
            basis[axis] = "sector_relative" if use_sector else "global_fallback"
            for f in fields:
                v = getattr(r, f)
                if not _usable(f, v):
                    continue
                dist = sector_dist[(sector, f)] if use_sector else global_dist[f]
                if dist:
                    pcts[f] = percentile_rank(v, dist)

        r.input_percentiles = pcts
        r.score_basis = basis
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/screener/test_sector_percentiles.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/screener/sector_percentiles.py tests/screener/test_sector_percentiles.py
git commit -m "Add percentile_prep: annotate cohort with sector/global percentiles"
```

---

## Task 6: deterministic_scorer.py — axis scores + run entry point

**Files:**
- Create: `app/screener/deterministic_scorer.py`
- Test: `tests/screener/test_deterministic_scorer.py`

`debt_to_equity` is in **percent-points** (45.0 = 45%); the red-flag threshold is `> 300`.

- [ ] **Step 1: Write the failing test (scoring logic)**

```python
# tests/screener/test_deterministic_scorer.py
from app.models.screener_record import ScreenerRecord
from app.screener.deterministic_scorer import score_record

def _scored(**kw):
    r = ScreenerRecord(ticker="X", **kw)
    score_record(r)
    return r

def test_top_decile_profitability_scores_5():
    r = _scored(input_percentiles={"operating_margin": 92.0, "return_on_equity": 88.0},
                operating_margin=0.4, return_on_equity=0.3)
    assert r.gemini_dimensions["profitability"] == 5

def test_negative_operating_margin_red_flags_to_zero():
    r = _scored(input_percentiles={"operating_margin": 95.0}, operating_margin=-0.05)
    assert r.gemini_dimensions["profitability"] == 0

def test_high_leverage_red_flags_resilience_to_zero():
    # d/e in percent-points: 350 = 3.5x -> red flag
    r = _scored(input_percentiles={"gross_margin": 80.0}, gross_margin=0.5, debt_to_equity=350.0)
    assert r.gemini_dimensions["resilience"] == 0

def test_growth_capped_by_consistency():
    # P92 growth -> anchor 5, but ratio 0.25 -> cap 3
    r = _scored(input_percentiles={"revenue_growth_yoy": 92.0},
                revenue_growth_yoy=0.6, growth_consistency=0.25)
    assert r.gemini_dimensions["growth"] == 3

def test_unassessable_consistency_caps_growth_at_4_and_flags_low():
    r = _scored(input_percentiles={"revenue_growth_yoy": 99.0},
                revenue_growth_yoy=0.6, growth_consistency=None)
    assert r.gemini_dimensions["growth"] == 4
    assert r.data_confidence == "low"

def test_missing_axis_inputs_score_3_and_listed_as_gap():
    r = _scored(input_percentiles={}, growth_consistency=1.0)
    assert r.gemini_dimensions["profitability"] == 3
    assert "operating_margin/return_on_equity" in r.gemini_data_gaps

def test_sentinels_and_weakest_dimension():
    r = _scored(input_percentiles={"revenue_growth_yoy": 95.0, "operating_margin": 30.0,
                                   "gross_margin": 95.0},
                revenue_growth_yoy=0.3, operating_margin=0.1, gross_margin=0.7,
                growth_consistency=1.0)
    assert r.gemini_dimensions["management"] == 3
    assert r.gemini_dimensions["innovation"] == 3
    # profitability is the lone low merit axis (P30 -> 2)
    assert r.gemini_weakest_dimension == "profitability"

def test_evidence_cites_absolute_and_percentile():
    r = _scored(input_percentiles={"operating_margin": 82.0, "return_on_equity": 79.0},
                operating_margin=0.18, return_on_equity=0.22, growth_consistency=1.0)
    assert "18.0%" in r.gemini_evidence["profitability"]
    assert "P82" in r.gemini_evidence["profitability"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_deterministic_scorer.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation**

```python
# app/screener/deterministic_scorer.py
"""Deterministic Tool-A scorer (Approach B / A1 — no LLM).

Maps the percentile annotations (sector_percentiles.annotate_percentiles) + the absolute
growth-consistency cap + absolute red-flag overlays to the ScreenerRecord.gemini_*
fields (schema name kept for output stability). Evidence is code-templated, citing the
absolute figure AND its percentile. debt_to_equity is in percent-points (45.0 = 45%)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.screener.growth_consistency import consistency_cap
from app.screener.percentiles import percentile_to_score

if TYPE_CHECKING:
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)

_RED_FLAG = 0
_DE_REDFLAG_THRESHOLD = 300.0  # percent-points: >300% (3x equity)


def _mean_axis_score(pcts: dict[str, float], fields: tuple[str, ...],
                     invert: tuple[str, ...] = ()) -> int | None:
    vals = []
    for f in fields:
        if f in pcts:
            p = pcts[f]
            vals.append(100.0 - p if f in invert else p)
    if not vals:
        return None
    return percentile_to_score(sum(vals) / len(vals))


def _pct_decimal(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def _evidence(record: "ScreenerRecord", pcts: dict[str, float],
              specs: list[tuple[str, str, str]]) -> str:
    """specs: list of (field, label, formatter) where formatter in {"decimal","de"}."""
    parts = []
    for field, label, kind in specs:
        raw = getattr(record, field)
        if field == "debt_to_equity" and raw is not None and raw < 0:
            parts.append(f"{label} n/a (negative book equity)")
            continue
        if raw is None:
            parts.append(f"{label} n/a")
            continue
        shown = f"{raw:.1f}%" if kind == "de" else _pct_decimal(raw)
        p = pcts.get(field)
        parts.append(f"{label} {shown}" + (f" (P{p:.0f})" if p is not None else ""))
    return ", ".join(parts)


def score_record(record: "ScreenerRecord") -> None:
    pcts = record.input_percentiles or {}
    dims: dict[str, int] = {}
    evidence: dict[str, str] = {}
    data_gaps: list[str] = []

    # growth — global percentile, then absolute consistency cap
    if "revenue_growth_yoy" in pcts:
        growth = percentile_to_score(pcts["revenue_growth_yoy"])
    else:
        growth = 3
        data_gaps.append("revenue_growth_yoy")
    growth = min(growth, consistency_cap(record.growth_consistency))
    dims["growth"] = growth
    cons = record.growth_consistency
    evidence["growth"] = _evidence(record, pcts, [("revenue_growth_yoy", "rev growth", "decimal")]) + (
        f", consistency {cons:.2f}" if cons is not None else ", consistency n/a (<4 GJ)")

    # profitability — sector/global percentile; red-flag on absolute losses
    prof = _mean_axis_score(pcts, ("operating_margin", "return_on_equity"))
    if prof is None:
        prof = 3
        data_gaps.append("operating_margin/return_on_equity")
    if (record.operating_margin is not None and record.operating_margin < 0) or (
            record.return_on_equity is not None and record.return_on_equity < 0):
        prof = _RED_FLAG
    dims["profitability"] = prof
    evidence["profitability"] = _evidence(record, pcts, [
        ("operating_margin", "op margin", "decimal"), ("return_on_equity", "ROE", "decimal")])

    # resilience — gross_margin + inverted d/e (d/e<0 already excluded upstream);
    # red-flag on extreme positive leverage
    resil = _mean_axis_score(pcts, ("gross_margin", "debt_to_equity"), invert=("debt_to_equity",))
    if resil is None:
        resil = 3
        data_gaps.append("gross_margin/debt_to_equity")
    if record.debt_to_equity is not None and record.debt_to_equity > _DE_REDFLAG_THRESHOLD:
        resil = _RED_FLAG
    dims["resilience"] = resil
    evidence["resilience"] = _evidence(record, pcts, [
        ("gross_margin", "gross margin", "decimal"), ("debt_to_equity", "d/e", "de")])

    # sentinels (not merit; mirror dimensions.py)
    dims["management"] = 3
    dims["innovation"] = 3
    evidence["management"] = "insufficient data: governance screened upstream"
    evidence["innovation"] = "insufficient data: no R&D data"

    merit = {"growth": dims["growth"], "profitability": dims["profitability"],
             "resilience": dims["resilience"]}
    record.gemini_dimensions = dims
    record.gemini_evidence = evidence
    record.gemini_weakest_dimension = min(merit, key=lambda k: merit[k])
    record.gemini_data_gaps = data_gaps
    record.data_confidence = "low" if (record.growth_consistency is None or data_gaps) else "ok"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/screener/test_deterministic_scorer.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing test for the run entry point**

```python
# tests/screener/test_deterministic_scorer.py — append
class _FakeRevenueCache:
    def __init__(self, series): self._series = series
    def get_revenue_series(self, ticker): return self._series.get(ticker, [])

class _FakeTracker:
    def __init__(self): self.calls = []
    def record_ticker(self, tin, tout): self.calls.append((tin, tout))

def test_run_deterministic_scoring_end_to_end():
    from app.screener.deterministic_scorer import run_deterministic_scoring
    recs = [ScreenerRecord(ticker=f"I{i}", gics_sector="Industrials",
                           operating_margin=0.1 + i * 0.001, return_on_equity=0.1,
                           gross_margin=0.3, debt_to_equity=40.0,
                           revenue_growth_yoy=0.05 + i * 0.001) for i in range(30)]
    cache = _FakeRevenueCache({r.ticker: [100.0, 110.0, 120.0, 130.0] for r in recs})
    tracker = _FakeTracker()
    out = run_deterministic_scoring(recs, cache, tracker)
    assert all(r.gemini_dimensions is not None for r in out)
    assert all(r.growth_consistency == 1.0 for r in out)
    assert tracker.calls == [(0, 0)] * 30  # LLM-free: zero tokens per ticker
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_deterministic_scorer.py::test_run_deterministic_scoring_end_to_end -v`
Expected: FAIL (`run_deterministic_scoring` not defined).

- [ ] **Step 7: Add the run entry point**

Append to `app/screener/deterministic_scorer.py`:

```python
def run_deterministic_scoring(records, revenue_cache, run_tracker):
    """Tool-A scoring entry point (replaces run_gemini_scoring). For each record:
    fetch its multi-year revenue series (cached), compute growth_consistency, then
    annotate percentiles across the whole cohort, then score each deterministically.
    Records zero tokens per ticker (LLM-free) so cost tracking stays accurate."""
    from app.screener.growth_consistency import consistency_ratio
    from app.screener.sector_percentiles import annotate_percentiles

    for record in records:
        revenues = revenue_cache.get_revenue_series(record.ticker)
        record.growth_consistency = consistency_ratio(revenues)
    annotate_percentiles(records)
    for record in records:
        score_record(record)
        run_tracker.record_ticker(0, 0)
    logger.info("deterministic_scorer: scored %d records (LLM-free)", len(records))
    return records
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run python -m pytest tests/screener/test_deterministic_scorer.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/screener/deterministic_scorer.py tests/screener/test_deterministic_scorer.py
git commit -m "Add deterministic scorer + LLM-free Tool-A scoring entry point"
```

---

## Task 7: revenue_series_cache.py — CachedRevenueSeries

**Files:**
- Create: `app/services/revenue_series_cache.py`
- Test: `tests/services/test_revenue_series_cache.py`

Mirrors `CachedGeminiClient` (Firestore get/set + TTL freshness). Only **non-empty** series are cached — a failed/empty fetch is NOT persisted, so it is retried next run (avoid masking a transient failure as a 400-day-stale empty; see `[[distinguish-failure-from-empty-result]]`).

- [ ] **Step 1: Write the failing test**

```python
# tests/services/test_revenue_series_cache.py
from datetime import datetime, timezone, timedelta
from app.services.revenue_series_cache import CachedRevenueSeries

class _FakeFirestore:
    def __init__(self, docs=None): self.docs = docs or {}; self.sets = {}
    def get(self, collection, doc_id): return self.docs.get(doc_id)
    def set(self, collection, doc_id, data): self.sets[doc_id] = data; self.docs[doc_id] = data
    def delete(self, collection, doc_id): self.docs.pop(doc_id, None)

class _FakeYF:
    def __init__(self, series): self._series = series; self.calls = 0
    def get_annual_statements(self, ticker):
        self.calls += 1
        return [self._series]  # a stand-in DataFrame consumed by extract_revenue_series

import pandas as pd

def _frame(values_newest_first):
    return pd.DataFrame({c: [v] for c, v in enumerate(values_newest_first)}, index=["Total Revenue"])

def test_fresh_cache_hit_skips_fetch():
    fs = _FakeFirestore({"AAA": {"revenues": [100.0, 130.0, 140.0, 150.0],
                                 "_cached_at": datetime.now(timezone.utc).isoformat()}})
    yf = _FakeYF(_frame([150, 140, 130, 100]))
    cache = CachedRevenueSeries(yf, fs, "dev_revenue_series", ttl_days=400)
    assert cache.get_revenue_series("AAA") == [100.0, 130.0, 140.0, 150.0]
    assert yf.calls == 0

def test_stale_cache_refetches_and_persists():
    old = (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()
    fs = _FakeFirestore({"AAA": {"revenues": [1.0], "_cached_at": old}})
    yf = _FakeYF(_frame([150, 140, 130, 100]))
    cache = CachedRevenueSeries(yf, fs, "dev_revenue_series", ttl_days=400)
    out = cache.get_revenue_series("AAA")
    assert out == [100.0, 130.0, 140.0, 150.0]
    assert yf.calls == 1
    assert "AAA" in fs.sets

def test_empty_fetch_not_persisted():
    fs = _FakeFirestore({})
    yf = _FakeYF(pd.DataFrame())  # extract_revenue_series -> []
    cache = CachedRevenueSeries(yf, fs, "dev_revenue_series", ttl_days=400)
    assert cache.get_revenue_series("AAA") == []
    assert "AAA" not in fs.sets   # not cached -> retried next run
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/services/test_revenue_series_cache.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation**

```python
# app/services/revenue_series_cache.py
"""Firestore-backed cache for multi-year revenue series (oldest->newest).

Annual data changes yearly, so the TTL is long (default 400d) — unlike the deliberately
short Gemini score TTL. Only non-empty series are persisted: a failed/empty fetch is left
uncached so it retries next run rather than masking as a 400-day-stale empty."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.errors import DataSourceError
from app.services.income_statement import extract_revenue_series

if TYPE_CHECKING:
    from app.services.firestore_client import FirestoreClient
    from app.services.yfinance_client import YFinanceClient


class CachedRevenueSeries:
    def __init__(self, yfinance: "YFinanceClient", firestore: "FirestoreClient",
                 collection: str, ttl_days: int = 400) -> None:
        self._yfinance = yfinance
        self._firestore = firestore
        self._collection = collection
        self._ttl_seconds = ttl_days * 24 * 3600

    def get_revenue_series(self, ticker: str) -> list[float]:
        cached = self._firestore.get(self._collection, ticker)
        if cached and "revenues" in cached and self._is_fresh(cached):
            return [float(x) for x in cached["revenues"]]
        try:
            stmt = self._yfinance.get_annual_statements(ticker)[0]
            revenues = extract_revenue_series(stmt)
        except DataSourceError:
            revenues = []
        if revenues:  # persist only successful, non-empty fetches
            self._firestore.set(self._collection, ticker, {
                "revenues": revenues,
                "_cached_at": datetime.now(timezone.utc).isoformat(),
            })
        return revenues

    def _is_fresh(self, cached: dict[str, Any]) -> bool:
        raw = cached.get("_cached_at")
        if not raw:
            return False
        try:
            cached_at = datetime.fromisoformat(raw)
        except ValueError:
            return False
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - cached_at).total_seconds() < self._ttl_seconds
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/services/test_revenue_series_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/revenue_series_cache.py tests/services/test_revenue_series_cache.py
git commit -m "Add long-TTL Firestore cache for multi-year revenue series"
```

---

## Task 8: Wire into runner + compose + main

**Files:**
- Modify: `app/screener/compose.py` (add `build_revenue_series_cache`)
- Modify: `app/screener/runner.py` (`run_screener`: swap `gemini` → `revenue_cache`, call `run_deterministic_scoring`)
- Modify: `app/main.py` (build + pass `revenue_cache`)
- Test: `tests/screener/test_runner_scoring_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/screener/test_runner_scoring_wiring.py
import inspect
from app.screener.runner import run_screener

def test_run_screener_takes_revenue_cache_not_gemini():
    params = inspect.signature(run_screener).parameters
    assert "revenue_cache" in params
    assert "gemini" not in params
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_runner_scoring_wiring.py -v`
Expected: FAIL (`gemini` still present).

- [ ] **Step 3: Add `build_revenue_series_cache` to compose.py**

In `app/screener/compose.py`, add the import and builder:

```python
from app.services.revenue_series_cache import CachedRevenueSeries
```

```python
def build_revenue_series_cache() -> CachedRevenueSeries:
    yfinance = YFinanceClientImpl()
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    return CachedRevenueSeries(
        yfinance=yfinance,
        firestore=firestore,
        collection=settings.revenue_series_collection,
        ttl_days=settings.revenue_series_ttl_days,
    )
```

- [ ] **Step 4: Update `run_screener` in runner.py**

Replace the `gemini: GeminiClient` parameter with `revenue_cache: "CachedRevenueSeries"` in the signature (~line 407), update the import line (~419) and the scoring call (~431):

Change the local import block:
```python
    from app.screener.deterministic_scorer import run_deterministic_scoring
```
(remove `from app.screener.scorer import run_gemini_scoring`)

Change the scoring call:
```python
    scored = run_deterministic_scoring(edgar_passed, revenue_cache, run_tracker)
```

Add to the `TYPE_CHECKING` block (~line 31):
```python
    from app.services.revenue_series_cache import CachedRevenueSeries
```
(and drop the now-unused `from app.services.gemini_client import GeminiClient`).

- [ ] **Step 5: Update main.py call site**

In `app/main.py`, replace `build_gemini_pipeline` import (line 15) with `build_revenue_series_cache`, and replace lines 89 + 98:

```python
    revenue_cache = build_revenue_series_cache()
```

```python
    records, run_record, paths = run_screener(
        tickers=tickers,
        yfinance=yfinance,
        edgar=edgar,
        revenue_cache=revenue_cache,
        run_tracker=tracker,
        output_dir=output_dir,
    )
```

- [ ] **Step 6: Run the wiring test + full suite**

Run: `uv run python -m pytest tests/screener/test_runner_scoring_wiring.py -v`
Expected: PASS.
Run: `uv run python -m pytest -q`
Expected: PASS (fix any test that constructed `run_screener(gemini=...)` to pass a fake `revenue_cache` with a `get_revenue_series` method; fix any `main` import test).

- [ ] **Step 7: Commit**

```bash
git add app/screener/compose.py app/screener/runner.py app/main.py tests/screener/test_runner_scoring_wiring.py
git commit -m "Wire deterministic scorer + revenue cache into run_screener/main (LLM-free Tool A)"
```

---

## Task 9: Output markers — score_basis + data_confidence

**Files:**
- Modify: `app/output/crosshits_generator.py` (`_build_body` row, ~line 92-98)
- Modify: `app/output/dimensions_generator.py` (`_build_markdown_body` row, ~line 142-147)
- Test: `tests/output/test_crosshits_generator.py`

A title is marked `score_basis=global_fallback` (flag `⌖`) iff any of its sector-relative axes fell back to global; `data_confidence=low` shows a `⚠` flag.

- [ ] **Step 1: Write the failing test**

```python
# tests/output/test_crosshits_generator.py — append (mirror existing fixtures in this file)
from app.output.crosshits_generator import _flags  # helper added in this task

def test_flags_global_fallback_and_low_confidence():
    from app.models.screener_record import ScreenerRecord
    r = ScreenerRecord(ticker="X",
                       score_basis={"growth": "global", "profitability": "global_fallback",
                                    "resilience": "sector_relative"},
                       data_confidence="low")
    out = _flags(r)
    assert "⌖" in out  # global fallback on >=1 sector-relative axis
    assert "⚠" in out  # low data confidence

def test_flags_clean_record_empty():
    from app.models.screener_record import ScreenerRecord
    r = ScreenerRecord(ticker="Y",
                       score_basis={"growth": "global", "profitability": "sector_relative",
                                    "resilience": "sector_relative"},
                       data_confidence="ok")
    assert _flags(r) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/output/test_crosshits_generator.py::test_flags_global_fallback_and_low_confidence -v`
Expected: FAIL (`_flags` not defined).

- [ ] **Step 3: Add the `_flags` helper and use it in the row**

In `app/output/crosshits_generator.py`, add:

```python
def _flags(record) -> str:
    """Audit markers: ⌖ = a sector-relative axis fell back to the global pool;
    ⚠ = low data confidence (e.g. <4 fiscal years / consistency unprovable)."""
    basis = record.score_basis or {}
    flags = ""
    if any(v == "global_fallback" for v in basis.values()):
        flags += "⌖"
    if getattr(record, "data_confidence", "ok") == "low":
        flags += "⚠"
    return flags
```

In `_build_body`, change the row append (currently the `f"| {i} | {r.ticker} | ..."` line) to include the flags after the ticker:

```python
            lines.append(
                f"| {i} | {r.ticker} {_flags(r)} | {r.name or ''} | {r.gics_sector or ''} "
                f"| {len(entry['qualifying_dims'])} | {dims_str} | {entry['avg_score']} |"
            )
```

- [ ] **Step 4: Mirror the marker in dimensions_generator.py**

In `app/output/dimensions_generator.py` `_build_markdown_body`, change the row to append the same flags (import `_flags` from crosshits_generator at top of file: `from app.output.crosshits_generator import _flags`):

```python
                lines.append(f"| {i} | {ticker} {_flags(r) if r else ''} | {name} | {sector} | {score} |")
```

- [ ] **Step 5: Run tests**

Run: `uv run python -m pytest tests/output/ -v`
Expected: PASS (adjust any existing assertion that pinned the exact ticker-cell string to tolerate the trailing flag space).

- [ ] **Step 6: Commit**

```bash
git add app/output/crosshits_generator.py app/output/dimensions_generator.py tests/output/test_crosshits_generator.py
git commit -m "Render score_basis (global fallback) + data_confidence markers in output"
```

---

## Task 10: Pre-warm backfill script

**Files:**
- Create: `scripts/backfill_revenue_series.py`
- Test: `tests/scripts/test_backfill_revenue_series.py`

Populates `dev_revenue_series` for the whole universe once, so no monthly run pays the cold income-statement cost (protects the 1800s Cloud Run deadline). Reuses `data/universe.json` (a JSON list of tickers).

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_backfill_revenue_series.py
from scripts.backfill_revenue_series import backfill

class _Cache:
    def __init__(self): self.seen = []
    def get_revenue_series(self, ticker): self.seen.append(ticker); return [1.0, 2.0, 3.0, 4.0]

def test_backfill_iterates_all_tickers():
    cache = _Cache()
    n = backfill(["AAA", "BBB", "CCC"], cache)
    assert n == 3
    assert cache.seen == ["AAA", "BBB", "CCC"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/scripts/test_backfill_revenue_series.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the script**

```python
# scripts/backfill_revenue_series.py
"""One-time pre-warm of the dev_revenue_series Firestore cache for the whole universe.

Run manually BEFORE the first prod monthly run after this feature ships, so no monthly
run pays the cold income-statement fetch cost (protects the 1800s Cloud Run deadline).

Usage (cmd.exe): uv run python scripts/backfill_revenue_series.py
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def backfill(tickers: list[str], revenue_cache) -> int:
    """Fetch (and thereby cache) the revenue series for each ticker. Returns count."""
    for i, ticker in enumerate(tickers, 1):
        revenue_cache.get_revenue_series(ticker)
        if i % 100 == 0:
            logger.info("backfill: %d/%d", i, len(tickers))
    return len(tickers)


def main() -> None:
    from app.logging_config import configure_logging
    from app.screener.compose import build_revenue_series_cache

    configure_logging()
    universe_path = Path(__file__).parent.parent / "data" / "universe.json"
    tickers = json.loads(universe_path.read_text(encoding="utf-8"))
    cache = build_revenue_series_cache()
    n = backfill(tickers, cache)
    logger.info("backfill complete: %d tickers warmed into dev_revenue_series", n)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/scripts/test_backfill_revenue_series.py -v`
Expected: PASS. (Add an empty `tests/scripts/__init__.py` if the suite needs it to import.)

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_revenue_series.py tests/scripts/test_backfill_revenue_series.py
git commit -m "Add one-time revenue-series backfill script (pre-warm cache)"
```

---

## Task 11: Docs — Tool A is now deterministic / LLM-free

**Files:**
- Modify: `CLAUDE.md` (Tech-Stack + Tool A description + the API table)

- [ ] **Step 1: Update the API table and Tool A description**

In `CLAUDE.md`, in the Tool A / cost-control section and the API table, change the Gemini-Flash-Lite-for-Tool-A entries to reflect that **Tool A scoring is now deterministic (code-computed sector-relative percentiles), no LLM**. Concretely:

- In the API table row `| Gemini Flash Lite | ✅ (mit Hard-Caps) | ✅ |`, change Tool A's cell to: `| Gemini Flash Lite | ❌ (Tool A jetzt deterministisch, kein LLM) | ✅ |`.
- In the "Tool A — Monthly Screener" overview bullet, replace "Gemini Flash Lite Scoring (mit Hard-Caps)" with "deterministisches sektor-relatives Perzentil-Scoring (kein LLM)".
- Add a one-line note that the Gemini token-cap machinery now applies only to Tool B.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Doc: Tool A scoring is deterministic (LLM-free) after sector-relative rewrite"
```

---

## Task 12: Cold dry-run validation (manual gate — not TDD)

**Files:** none (operational verification before the paid/real run)

- [ ] **Step 1: Run the full unit suite**

Run: `uv run python -m pytest -q`
Expected: PASS, coverage ≥ 90% (project threshold).

- [ ] **Step 2: Pre-warm the cache locally (read-only build of dev_revenue_series)**

Run: `uv run python scripts/backfill_revenue_series.py`
Expected: log line `backfill complete: <N> tickers warmed`.

- [ ] **Step 3: Cold dry-run + measure de-clustering**

Trigger a local screener run against the warmed caches. Then, using a read-only Firestore harness modelled on `scripts/analyze_sector_relative_evidence.py`, confirm the acceptance criteria from spec §13:
- per-axis score distribution is now ~uniform across 1–5 (NOT 55–72% at ≥4);
- crosshit rate dropped markedly from 33.8%;
- HL/NEM/EDV growth is capped by the consistency dampener (inspect their `growth_consistency`);
- no `<4 GJ` title is a crosshit without a `data_confidence=low` (⚠) flag.

- [ ] **Step 4: Record findings**

Write a short audit note under `docs/superpowers/audits/2026-06-16-sector-relative-scoring/` with the before/after score distribution and the four checks. This note is the merge gate.

---

## Self-Review notes (author)

- **Spec coverage:** §3 fields → T1; §2/§7 config+cache → T2/T7; §5 anchor+axes+red-flags → T3/T6; §6 consistency → T4/T6; §4 sector grouping/guards/fallback → T5; §7 fetch+backfill → T7/T10; §9 LLM-free wiring → T8; §10 output markers → T9; §9/CLAUDE.md doc → T11; §12 tests throughout; §13 acceptance → T12.
- **Unit guard:** `debt_to_equity` percent-points is encoded once (`_DE_REDFLAG_THRESHOLD = 300.0`) and the negative-exclusion lives once in `sector_percentiles._usable`; the scorer never re-derives the threshold.
- **Type consistency:** `score_basis` is `dict[str,str]` everywhere (T1 field, T5 writer, T9 reader); `get_revenue_series(ticker)->list[float]` is the single cache interface used by T6/T8/T10; `gemini_dimensions` schema name is retained so T9 output and the funnel's `is_crosshit` keep working unchanged.
