# Punkt 3 — Revenue-Growth-Viabilitäts-Floor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `revenue_growth_yoy >= 0` TTM-snapshot knock-out with a structural multi-year viability floor: a hybrid lazy-fetch that pulls the annual income statement only for TTM<0/None survivors and drops a name only when three signals agree on decline (γ: `TTM<0 ∧ CAGR<0 ∧ down_years≥2`).

**Architecture:** Mirror the Punkt-2 definedness pre-pass (`runner._assess_definedness_basket`). A new runner pre-pass `_assess_revenue_growth_trajectory` fetches the annual `income_stmt` (free, yfinance) ONLY for vol+cap survivors that pass the gross-margin gate AND have `revenue_growth_yoy < 0` or `None`, computes multi-year CAGR + down-years, and stores the verdict on the record. The pure gate (`passes_revenue_growth_filter`) then reads the pre-computed fields — filters do no I/O. Missing/short-history data routes to the existing `DefinednessOutcome.UNASSESSABLE` and passes (floor logic), never an implicit fail.

**Tech Stack:** Python 3.12, pydantic `ScreenerRecord`, pandas (yfinance income_stmt DataFrame), pytest + DI mocks (`uv run python -m pytest`). All commands cmd.exe / `uv run python -m`.

**Spec:** `docs/superpowers/specs/2026-06-10-punkt-3-revenue-growth-viability-floor-design.md`. Branch `feature/revenue-growth-viability-floor` (already created; spec committed `8a0fe00`).

**Vintage-2026-06 acceptance identity (Task 8 re-verifies cold):** `189 = 81 DROP + 107 RESCUE + 1 UNASSESSABLE`; residuum X=54.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `app/models/screener_record.py` | Record schema | ADD 4 fields (Task 1) |
| `app/services/income_statement.py` | yfinance income_stmt → values | ADD `extract_revenue_series` (Task 2) |
| `app/screener/revenue_trajectory.py` | **NEW** — pure trajectory math + γ verdict | CREATE (Task 3) |
| `app/screener/filters.py` | Basis gates (pure, no I/O) | rewrite `passes_revenue_growth_filter` + ADD `revenue_growth_outcome` (Task 4) |
| `app/screener/runner.py` | Orchestration + fetch | ADD `_assess_revenue_growth_trajectory` pre-pass + wiring (Task 5); `apply_basis_filters` tags pass_reason (Task 4) |
| `tests/screener/conftest.py` | shared fixtures | ADD autouse fixture so the trajectory pre-pass stays inert unless a test opts in (Task 5) |
| existing tests | migration | update TTM<0 expectations to new semantics (Task 6) |
| `scripts/diagnose_revenue_growth_drops.py` | grounding/diagnostic | align α→γ, unify over 189 (Task 7) |
| `docs/.../2026-06-10-punkt-3-revenue-growth/calibration.md` | calibration record | CREATE (Task 8) |

**Short-circuit order is unchanged:** volume → market_cap → definedness(gross_margin) → gross_margin → revenue_growth. The new pre-pass runs after `_assess_definedness_basket`, before `apply_basis_filters`.

**Reason-code clarification (vs spec §7):** `UNASSESSABLE → pass` is NOT a funnel dropout, so it gets NO new `ReasonCode`. Its audit visibility is `record.revenue_growth_pass_reason = "UNASSESSABLE_PASS"` + a WARNING log. The γ-drop keeps the existing `"revenue_growth"` reason → `GATE_REVENUE_GROWTH`. **FLAG for Stephan at plan review:** the spec's "eigener Reason-Bucket" is realized as a pass-reason field, not a dropout code, because the outcome is a pass. Also confirm: a *transient* income_stmt fetch failure passes (floor logic, spec §4) — this differs from the Punkt-2 gross_margin handling, where a transient fetch failure DIVERTS to REVIEW. Implemented per spec (pass); confirm the asymmetry is intended.

---

## Task 1: Add trajectory fields to ScreenerRecord

**Files:**
- Modify: `app/models/screener_record.py` (after the `gross_margin_pass_reason` field, ~line 60)
- Test: `tests/models/test_screener_record.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/models/test_screener_record.py
from app.models.definedness import DefinednessOutcome
from app.models.screener_record import ScreenerRecord


def test_revenue_trajectory_fields_default_none():
    r = ScreenerRecord(ticker="X")
    assert r.multiyear_revenue_cagr is None
    assert r.revenue_down_years is None
    assert r.revenue_growth_definedness is None
    assert r.revenue_growth_pass_reason is None


def test_revenue_trajectory_fields_accept_values():
    r = ScreenerRecord(
        ticker="X",
        multiyear_revenue_cagr=-0.05,
        revenue_down_years=2,
        revenue_growth_definedness=DefinednessOutcome.DEFINED,
        revenue_growth_pass_reason="DECLINE_DROP",
    )
    assert r.revenue_down_years == 2
    assert r.revenue_growth_definedness is DefinednessOutcome.DEFINED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/models/test_screener_record.py -k revenue_trajectory -v`
Expected: FAIL (`ValidationError`/unexpected keyword — fields not defined).

- [ ] **Step 3: Add the fields**

In `app/models/screener_record.py`, immediately after the `gross_margin_pass_reason` field (it sits just below `filter_failed_reason`, ~line 60), add:

```python
    # Punkt 3 Phase: multi-year revenue-growth viability floor.
    # Populated in the runner pre-pass (_assess_revenue_growth_trajectory) ONLY for
    # vol+cap survivors that clear the gross-margin gate AND have revenue_growth_yoy < 0
    # or None (the lazy-fetch cohort). Left None for everyone else (TTM-pass / not reached).
    multiyear_revenue_cagr: float | None = None      # endpoint CAGR over available fiscal years
    revenue_down_years: int | None = None            # count of negative YoY transitions (oldest->newest)
    revenue_growth_definedness: DefinednessOutcome | None = None  # DEFINED | UNASSESSABLE (3-state, never bool)
    revenue_growth_pass_reason: str | None = None    # TTM_PASS | TRAJECTORY_RESCUE | DECLINE_DROP | UNASSESSABLE_PASS
```

(`DefinednessOutcome` is already imported at the top of the file — it is used by the existing `definedness` field.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/models/test_screener_record.py -k revenue_trajectory -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```
git add app/models/screener_record.py tests/models/test_screener_record.py
git commit -m "Add multi-year revenue-growth trajectory fields to ScreenerRecord"
```

---

## Task 2: `extract_revenue_series` — multi-year Total Revenue from income_stmt

**Files:**
- Modify: `app/services/income_statement.py` (add a function next to `extract_waterfall_inputs`)
- Test: `tests/services/test_income_statement.py`

The existing `_first_col_value` returns only the newest column. We need ALL fiscal-year columns, oldest→newest, NaN/non-positive dropped. yfinance `income_stmt` columns are newest-first.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/services/test_income_statement.py
import pandas as pd
from app.services.income_statement import extract_revenue_series


def _multi_year_stmt(rev_by_year: dict) -> pd.DataFrame:
    """rev_by_year keyed newest-first, e.g. {'2024': 100, '2023': 90}. One row: Total Revenue."""
    return pd.DataFrame({col: {"Total Revenue": v} for col, v in rev_by_year.items()})


def test_extract_revenue_series_oldest_to_newest():
    # newest-first columns -> returned oldest->newest
    stmt = _multi_year_stmt({"2024": 130.0, "2023": 120.0, "2022": 110.0, "2021": 100.0})
    assert extract_revenue_series(stmt) == [100.0, 110.0, 120.0, 130.0]


def test_extract_revenue_series_drops_nan_and_nonpositive():
    stmt = _multi_year_stmt({"2024": 130.0, "2023": float("nan"), "2022": -5.0, "2021": 100.0})
    assert extract_revenue_series(stmt) == [100.0, 130.0]


def test_extract_revenue_series_none_stmt_empty():
    assert extract_revenue_series(None) == []


def test_extract_revenue_series_missing_row_empty():
    stmt = pd.DataFrame({"2024": {"Gross Profit": 50.0}})
    assert extract_revenue_series(stmt) == []


def test_extract_revenue_series_series_input_empty():
    # SEAM-4 contract guard: a 1-D Series degrades to [] (no AttributeError downstream)
    assert extract_revenue_series(pd.Series({"Total Revenue": 100.0})) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/services/test_income_statement.py -k revenue_series -v`
Expected: FAIL (`ImportError: cannot import name 'extract_revenue_series'`).

- [ ] **Step 3: Implement**

In `app/services/income_statement.py`, add:

```python
def extract_revenue_series(income_stmt: Any) -> list[float]:
    """Return annual Total Revenue oldest->newest from a yfinance income_stmt DataFrame.

    yfinance columns are newest-first; we reverse to oldest->newest for trajectory
    reasoning. NaN and non-positive values are dropped (a non-positive revenue is a
    data artefact, not a real fiscal year). Returns [] when the frame is None/empty/
    non-2-D (SEAM-4 contract guard) or the 'Total Revenue' row is absent.
    """
    if getattr(income_stmt, "ndim", None) != 2:
        return []
    if income_stmt is None or getattr(income_stmt, "empty", True):
        return []
    if "Total Revenue" not in income_stmt.index:
        return []
    row = income_stmt.loc["Total Revenue"]
    series: list[float] = []
    for val in reversed(list(row)):  # newest-first -> oldest-first
        try:
            f = float(val)
        except (TypeError, ValueError):
            continue
        if f == f and f > 0:  # NaN guard (f != f) + positive only
            series.append(f)
    return series
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/services/test_income_statement.py -k revenue_series -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```
git add app/services/income_statement.py tests/services/test_income_statement.py
git commit -m "Add extract_revenue_series multi-year extractor for the revenue-growth floor"
```

---

## Task 3: `revenue_trajectory.py` — pure trajectory classifier (γ core)

**Files:**
- Create: `app/screener/revenue_trajectory.py`
- Test: `tests/screener/test_revenue_trajectory.py`

Pure math: a list of revenues (oldest→newest) → `(cagr, down_years, definedness)`. The ≥4-fiscal-years (≥3 YoY) minimum is the SEAM-2 safeguard: fewer points → `UNASSESSABLE` (the criterion could not apply), never a silent verdict.

- [ ] **Step 1: Write the failing test**

```python
# tests/screener/test_revenue_trajectory.py
import math
import pytest

from app.models.definedness import DefinednessOutcome
from app.screener.revenue_trajectory import classify_revenue_trajectory, is_gamma_decline


def test_genuine_multiyear_decline_is_defined():
    # 4 GJ, falling: CAGR<0, down_years=3
    cagr, dy, defn = classify_revenue_trajectory([100.0, 90.0, 80.0, 70.0])
    assert defn is DefinednessOutcome.DEFINED
    assert cagr < 0
    assert dy == 3
    assert is_gamma_decline(cagr, dy) is True


def test_positive_cagr_choppy_is_not_gamma():
    # grew net but 2 down years (LVMH-shape): CAGR>0 -> NOT a gamma drop
    cagr, dy, defn = classify_revenue_trajectory([100.0, 95.0, 105.0, 102.0])
    assert defn is DefinednessOutcome.DEFINED
    assert cagr > 0
    assert dy == 2
    assert is_gamma_decline(cagr, dy) is False  # positive CAGR overrides


def test_negative_cagr_single_down_year_is_not_gamma():
    # base-year artefact (Roche-shape): one bad first step, then recovery -> dy=1
    cagr, dy, defn = classify_revenue_trajectory([100.0, 70.0, 72.0, 74.0])
    assert cagr < 0
    assert dy == 1
    assert is_gamma_decline(cagr, dy) is False  # needs dy>=2


def test_short_history_is_unassessable():
    # only 3 fiscal years (<4) -> UNASSESSABLE, no verdict forced
    cagr, dy, defn = classify_revenue_trajectory([100.0, 90.0, 80.0])
    assert defn is DefinednessOutcome.UNASSESSABLE


def test_too_few_points_unassessable():
    cagr, dy, defn = classify_revenue_trajectory([100.0])
    assert defn is DefinednessOutcome.UNASSESSABLE
    assert cagr is None and dy is None


def test_empty_unassessable():
    cagr, dy, defn = classify_revenue_trajectory([])
    assert defn is DefinednessOutcome.UNASSESSABLE


def test_is_gamma_decline_none_inputs_false():
    assert is_gamma_decline(None, None) is False
    assert is_gamma_decline(-0.1, None) is False
    assert is_gamma_decline(None, 3) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_revenue_trajectory.py -v`
Expected: FAIL (`ModuleNotFoundError: app.screener.revenue_trajectory`).

- [ ] **Step 3: Implement**

```python
# app/screener/revenue_trajectory.py
"""Pure multi-year revenue-trajectory classifier for the Punkt-3 viability floor.

No I/O, no record types — list of revenues (oldest->newest) -> (cagr, down_years,
definedness). The >=4-fiscal-years minimum is the SEAM-2 safeguard: with fewer points
the trajectory criterion cannot apply, so the outcome is UNASSESSABLE (deliberate
routing to a pass downstream), never a silent verdict.
"""
from __future__ import annotations

from app.models.definedness import DefinednessOutcome

MIN_FISCAL_YEARS = 4  # >=4 GJ == >=3 YoY transitions; needed for a down_years>=2 verdict


def classify_revenue_trajectory(
    revenues: list[float],
) -> tuple[float | None, int | None, DefinednessOutcome]:
    """Return (endpoint_cagr, down_years, definedness) for an oldest->newest revenue list.

    - <2 points: (None, None, UNASSESSABLE) — no trajectory at all.
    - 2..3 points: cagr/down_years computed for audit, but definedness=UNASSESSABLE
      (too short for a down_years>=2 verdict).
    - >=4 points: definedness=DEFINED; the gamma verdict may fire.
    Inputs are assumed positive (extract_revenue_series drops NaN/<=0).
    """
    n = len(revenues)
    if n < 2:
        return None, None, DefinednessOutcome.UNASSESSABLE
    yoy = [(revenues[i] - revenues[i - 1]) / revenues[i - 1] for i in range(1, n)]
    down_years = sum(1 for g in yoy if g < 0)
    years = n - 1
    cagr = (revenues[-1] / revenues[0]) ** (1 / years) - 1
    definedness = (
        DefinednessOutcome.DEFINED if n >= MIN_FISCAL_YEARS else DefinednessOutcome.UNASSESSABLE
    )
    return cagr, down_years, definedness


def is_gamma_decline(cagr: float | None, down_years: int | None) -> bool:
    """γ core: a genuine multi-year decline requires BOTH endpoint and trajectory to agree —
    CAGR < 0 AND down_years >= 2. Either signal missing -> not a decline (floor: in dubio pass)."""
    if cagr is None or down_years is None:
        return False
    return cagr < 0 and down_years >= 2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/screener/test_revenue_trajectory.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```
git add app/screener/revenue_trajectory.py tests/screener/test_revenue_trajectory.py
git commit -m "Add pure revenue-trajectory classifier with gamma decline core"
```

---

## Task 4: Rewrite the gate — `revenue_growth_outcome` + `passes_revenue_growth_filter`

**Files:**
- Modify: `app/screener/filters.py` (replace `passes_revenue_growth_filter`, lines 106-110; add `revenue_growth_outcome`)
- Modify: `app/screener/runner.py` (`apply_basis_filters` — tag `revenue_growth_pass_reason` on passers)
- Test: `tests/screener/test_filters.py`

The gate is now PURE — it reads pre-computed `revenue_growth_definedness` / `multiyear_revenue_cagr` / `revenue_down_years` (set by the Task-5 pre-pass) plus the raw `revenue_growth_yoy`.

- [ ] **Step 1: Write the failing test**

```python
# tests/screener/test_filters.py — add near the existing revenue_growth tests
from app.models.definedness import DefinednessOutcome
from app.screener.filters import revenue_growth_outcome, passes_revenue_growth_filter


def _rec(**kw):
    from app.models.screener_record import ScreenerRecord
    return ScreenerRecord(ticker="X", **kw)


def test_outcome_ttm_pass_positive_snapshot_no_trajectory_needed():
    r = _rec(revenue_growth_yoy=0.01)
    assert revenue_growth_outcome(r) == "TTM_PASS"
    assert passes_revenue_growth_filter(r) is True


def test_outcome_ttm_zero_passes():
    r = _rec(revenue_growth_yoy=0.0)
    assert revenue_growth_outcome(r) == "TTM_PASS"


def test_outcome_decline_drop_gamma():
    # TTM<0 + DEFINED + CAGR<0 + dy>=2 -> drop
    r = _rec(revenue_growth_yoy=-0.05, revenue_growth_definedness=DefinednessOutcome.DEFINED,
             multiyear_revenue_cagr=-0.06, revenue_down_years=2)
    assert revenue_growth_outcome(r) == "DECLINE_DROP"
    assert passes_revenue_growth_filter(r) is False


def test_outcome_trajectory_rescue_positive_cagr():
    # TTM<0 but multi-year CAGR>0 -> rescue
    r = _rec(revenue_growth_yoy=-0.05, revenue_growth_definedness=DefinednessOutcome.DEFINED,
             multiyear_revenue_cagr=0.03, revenue_down_years=2)
    assert revenue_growth_outcome(r) == "TRAJECTORY_RESCUE"
    assert passes_revenue_growth_filter(r) is True


def test_outcome_trajectory_rescue_single_down_year():
    # TTM<0, CAGR<0 but dy=1 (base-year artefact) -> rescue
    r = _rec(revenue_growth_yoy=-0.05, revenue_growth_definedness=DefinednessOutcome.DEFINED,
             multiyear_revenue_cagr=-0.02, revenue_down_years=1)
    assert revenue_growth_outcome(r) == "TRAJECTORY_RESCUE"


def test_outcome_unassessable_pass():
    # TTM<0 but trajectory unassessable (fetch failed / short history) -> pass
    r = _rec(revenue_growth_yoy=-0.05, revenue_growth_definedness=DefinednessOutcome.UNASSESSABLE)
    assert revenue_growth_outcome(r) == "UNASSESSABLE_PASS"
    assert passes_revenue_growth_filter(r) is True


def test_outcome_missing_ttm_judged_on_trajectory_drop():
    # revenue_growth_yoy=None + DEFINED + gamma -> DECLINE_DROP (missing data is NOT auto-pass)
    r = _rec(revenue_growth_yoy=None, revenue_growth_definedness=DefinednessOutcome.DEFINED,
             multiyear_revenue_cagr=-0.10, revenue_down_years=3)
    assert revenue_growth_outcome(r) == "DECLINE_DROP"
    assert passes_revenue_growth_filter(r) is False


def test_outcome_missing_ttm_trajectory_rescue():
    r = _rec(revenue_growth_yoy=None, revenue_growth_definedness=DefinednessOutcome.DEFINED,
             multiyear_revenue_cagr=0.02, revenue_down_years=2)
    assert revenue_growth_outcome(r) == "TRAJECTORY_RESCUE"


def test_outcome_missing_ttm_unassessable_pass():
    # missing TTM AND no usable statement -> UNASSESSABLE -> pass
    r = _rec(revenue_growth_yoy=None, revenue_growth_definedness=DefinednessOutcome.UNASSESSABLE)
    assert revenue_growth_outcome(r) == "UNASSESSABLE_PASS"
    assert passes_revenue_growth_filter(r) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_filters.py -k outcome -v`
Expected: FAIL (`ImportError: cannot import name 'revenue_growth_outcome'`).

- [ ] **Step 3: Implement**

In `app/screener/filters.py`, add the import at the top (next to the other `app.screener` imports):

```python
from app.screener.revenue_trajectory import is_gamma_decline
```

Replace the existing `passes_revenue_growth_filter` (lines 106-110) with:

```python
TTM_PASS = "TTM_PASS"
TRAJECTORY_RESCUE = "TRAJECTORY_RESCUE"
DECLINE_DROP = "DECLINE_DROP"
UNASSESSABLE_PASS = "UNASSESSABLE_PASS"


def revenue_growth_outcome(record: ScreenerRecord) -> str:
    """Why a record clears (or fails) the multi-year revenue-growth viability floor — the
    audit primitive. Reads the pre-computed trajectory (set by the runner pre-pass); does
    NO I/O. Returns one of TTM_PASS | TRAJECTORY_RESCUE | DECLINE_DROP | UNASSESSABLE_PASS.

    - TTM_PASS: revenue_growth_yoy >= 0 — positive snapshot is affirmative recovery
      evidence; the multi-year look is never triggered (lazy, monotone).
    - Otherwise (TTM < 0 OR TTM is None) the verdict rests on the trajectory:
        UNASSESSABLE_PASS  - criterion could not apply (no statement / <4 GJ) -> pass (floor).
        DECLINE_DROP       - DEFINED and gamma (CAGR<0 AND down_years>=2) -> the ONLY drop.
        TRAJECTORY_RESCUE  - DEFINED but not gamma (positive CAGR or single down-year).
    A missing TTM is data-absence, never a down-signal: it is judged on the trajectory,
    not auto-passed (the inverse of the original missing-data bug)."""
    ttm = record.revenue_growth_yoy
    if ttm is not None and ttm >= MIN_REVENUE_GROWTH:
        return TTM_PASS
    if record.revenue_growth_definedness is DefinednessOutcome.UNASSESSABLE:
        return UNASSESSABLE_PASS
    if is_gamma_decline(record.multiyear_revenue_cagr, record.revenue_down_years):
        return DECLINE_DROP
    return TRAJECTORY_RESCUE


def passes_revenue_growth_filter(record: ScreenerRecord) -> bool:
    return revenue_growth_outcome(record) != DECLINE_DROP
```

(`DefinednessOutcome` is already imported in `filters.py` at line 4.)

Now tag the pass-reason on basis-passers. In `app/screener/runner.py`, `apply_basis_filters`, the `else` branch already sets `record.gross_margin_pass_reason`. Add directly below it:

```python
            record.revenue_growth_pass_reason = revenue_growth_outcome(record)
```

Add the import to `runner.py` (with the other `from app.screener.filters import ...`): `revenue_growth_outcome`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/screener/test_filters.py -k outcome -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```
git add app/screener/filters.py app/screener/runner.py tests/screener/test_filters.py
git commit -m "Rewrite revenue_growth gate as pure gamma-trajectory outcome + tag pass_reason"
```

---

## Task 5: Runner pre-pass `_assess_revenue_growth_trajectory` + wiring + dormant fixture

**Files:**
- Modify: `app/screener/runner.py` (add pre-pass fn; call it in `run_basis_filter`)
- Modify: `tests/screener/conftest.py` (autouse fixture: keep pre-pass inert by default)
- Test: `tests/screener/test_runner.py`

The pre-pass mirrors `_assess_definedness_basket`: fetch ONLY for the lazy cohort = vol+cap survivors, not diverted by definedness, that PASS gross-margin AND have `revenue_growth_yoy < 0` or `None`. `passes_gross_margin_filter` is pure (no I/O), so it can gate the fetch.

- [ ] **Step 1: Write the failing test**

```python
# tests/screener/test_runner.py — add after the definedness pre-pass tests (~line 845).
# Reuses _make_full_yf_mock / _make_income_stmt / _suspect_info / _non_suspect_info helpers.

def _make_revenue_stmt(revs_newest_first: list[float]):
    import pandas as pd
    cols = {str(2024 - i): {"Total Revenue": v} for i, v in enumerate(revs_newest_first)}
    return pd.DataFrame(cols)


def _growth_info(ttm, gm=0.5, **ov):
    # a clean non-suspect record (Technology, positive gm) with a settable revenueGrowth
    info = _non_suspect_info(**ov)
    info["revenueGrowth"] = ttm
    info["grossMargins"] = gm
    return info


def test_revenue_prepass_no_fetch_when_ttm_positive():
    infos = {"GROW": _growth_info(0.05)}
    mock = _make_full_yf_mock(infos)  # get_annual_statements raises if called
    result = run_basis_filter(["GROW"], mock)
    mock.get_annual_statements.assert_not_called()
    rec = result.resolved[0]
    assert rec.revenue_growth_pass_reason == "TTM_PASS"


def test_revenue_prepass_fetches_and_drops_gamma():
    # TTM<0, multi-year decline 4 GJ -> DECLINE_DROP
    infos = {"DECL": _growth_info(-0.05)}
    stmts = {"DECL": _make_revenue_stmt([70.0, 80.0, 90.0, 100.0])}  # newest-first, falling
    mock = _make_full_yf_mock(infos, stmts=stmts)
    result = run_basis_filter(["DECL"], mock)
    mock.get_annual_statements.assert_called_once_with("DECL")
    rec = result.resolved[0]
    assert rec.revenue_growth_definedness is DefinednessOutcome.DEFINED
    assert rec.filter_failed_reason == "revenue_growth"
    assert rec.filter_passed_basis is False


def test_revenue_prepass_fetches_and_rescues_positive_cagr():
    infos = {"RESC": _growth_info(-0.05)}
    stmts = {"RESC": _make_revenue_stmt([130.0, 90.0, 105.0, 100.0])}  # net growth, choppy
    mock = _make_full_yf_mock(infos, stmts=stmts)
    result = run_basis_filter(["RESC"], mock)
    rec = result.resolved[0]
    assert rec.revenue_growth_pass_reason == "TRAJECTORY_RESCUE"
    assert rec.filter_passed_basis is True


def test_revenue_prepass_fetch_failure_unassessable_pass():
    infos = {"FAIL": _growth_info(-0.05)}
    mock = MagicMock()
    mock.get_ticker_info.side_effect = lambda t: infos[t]
    mock.get_fx_rate.return_value = 1.0
    mock.get_annual_statements.side_effect = DataSourceError("timeout")
    result = run_basis_filter(["FAIL"], mock)
    rec = result.resolved[0]
    assert rec.revenue_growth_definedness is DefinednessOutcome.UNASSESSABLE
    assert rec.revenue_growth_pass_reason == "UNASSESSABLE_PASS"
    assert rec.filter_passed_basis is True


def test_revenue_prepass_missing_ttm_fetches_and_drops():
    # revenueGrowth=None -> still fetched, judged on trajectory -> gamma drop
    infos = {"NONE": _growth_info(None)}
    stmts = {"NONE": _make_revenue_stmt([60.0, 80.0, 90.0, 100.0])}
    mock = _make_full_yf_mock(infos, stmts=stmts)
    result = run_basis_filter(["NONE"], mock)
    mock.get_annual_statements.assert_called_once_with("NONE")
    rec = result.resolved[0]
    assert rec.filter_failed_reason == "revenue_growth"


def test_revenue_prepass_no_fetch_when_gross_margin_fails():
    # TTM<0 but gm below floor -> fails gross_margin first -> never reaches revenue_growth -> no fetch
    infos = {"LOWGM": _growth_info(-0.05, gm=0.05)}
    mock = _make_full_yf_mock(infos)
    result = run_basis_filter(["LOWGM"], mock)
    mock.get_annual_statements.assert_not_called()
    rec = result.resolved[0]
    assert rec.filter_failed_reason == "gross_margin"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_runner.py -k revenue_prepass -v`
Expected: FAIL (`get_annual_statements` called when it should not be / fields unset — pre-pass not wired).

- [ ] **Step 3: Implement the pre-pass + wiring + dormant fixture**

In `app/screener/runner.py`:

(a) Imports — add `passes_gross_margin_filter` to the existing `from app.screener.filters import ...` line. Add `extract_revenue_series` to the **existing** `from app.services.income_statement import extract_waterfall_inputs` line (do NOT add a second import line — extend it to `import extract_revenue_series, extract_waterfall_inputs`). Add one new line for the classifier:

```python
from app.screener.revenue_trajectory import classify_revenue_trajectory
```

(`revenue_growth_outcome` was already added to the filters import in Task 4.)

(b) Add the pre-pass function (next to `_assess_definedness_basket`):

```python
def _assess_revenue_growth_trajectory(
    records: list["ScreenerRecord"],
    yfinance: "YFinanceClient",
    table: "SectorMedianTable | None",
    relative_k: float | None,
) -> None:
    """Lazy multi-year fetch for the revenue-growth viability floor (Punkt 3).

    Fetch the annual income statement and classify the trajectory ONLY for the cohort that
    will actually reach the revenue_growth gate AND needs the multi-year look:
      vol+cap survivors, not diverted by definedness, clearing the gross-margin gate,
      with revenue_growth_yoy < 0 or None.
    A positive TTM short-circuits (no fetch — affirmative recovery evidence, monotone).
    Sets multiyear_revenue_cagr / revenue_down_years / revenue_growth_definedness in place.
    """
    n_fetched = n_decline = n_rescue = n_unassessable = 0
    for record in records:
        if not (passes_volume_filter(record) and passes_market_cap_filter(record)):
            continue
        if record.definedness in (DefinednessOutcome.UNASSESSABLE, DefinednessOutcome.METRIK_NA):
            continue
        if not passes_gross_margin_filter(record, table, relative_k):
            continue
        ttm = record.revenue_growth_yoy
        if ttm is not None and ttm >= 0:
            continue  # TTM-pass: lazy short-circuit, no fetch
        revenues: list[float] = []
        try:
            income_stmt = yfinance.get_annual_statements(record.ticker)[0]
            revenues = extract_revenue_series(income_stmt)
            n_fetched += 1
        except DataSourceError as exc:
            logger.warning(
                "ticker=%s income_stmt fetch failed (revenue_growth UNASSESSABLE): %s",
                record.ticker, exc,
            )
        cagr, down_years, definedness = classify_revenue_trajectory(revenues)
        record.multiyear_revenue_cagr = cagr
        record.revenue_down_years = down_years
        record.revenue_growth_definedness = definedness
        if definedness is DefinednessOutcome.UNASSESSABLE:
            n_unassessable += 1
        elif cagr is not None and cagr < 0 and (down_years or 0) >= 2:
            n_decline += 1
        else:
            n_rescue += 1
    logger.info(
        "revenue_growth_prepass: fetched=%d DECLINE=%d RESCUE=%d UNASSESSABLE=%d",
        n_fetched, n_decline, n_rescue, n_unassessable,
    )
```

(c) Wire it in `run_basis_filter`. Replace the block at lines 251-259 (the definedness pre-pass + table build + return) with:

```python
    _assess_definedness_basket(records, yfinance)

    table = sector_table if sector_table is not None else build_sector_median_table()
    _assess_revenue_growth_trajectory(records, yfinance, table, _filters.GROSS_MARGIN_RELATIVE_K)

    return BasisFilterResult(
        passed=apply_basis_filters(
            records,
            sector_table=table,
            relative_k=_filters.GROSS_MARGIN_RELATIVE_K,
        ),
```

(`_filters`, `build_sector_median_table`, `passes_volume_filter`, `passes_market_cap_filter`, `DataSourceError`, `DefinednessOutcome` are already imported/used in this file.)

In `tests/screener/conftest.py`, add an autouse fixture so existing tests' MagicMock yfinance (whose `get_annual_statements` raises by default) does not get exercised unless a test opts in. Mirror `_dormant_gross_margin_relative_arm`:

```python
@pytest.fixture(autouse=True)
def _inert_revenue_trajectory_prepass(monkeypatch):
    """Keep the Punkt-3 multi-year revenue pre-pass inert by default: with the relative
    arm dormant and most fixtures' gross_margin below 0.30 OR TTM>=0, the cohort is empty.
    Tests exercising the floor set revenue_growth_yoy<0 AND a clearing gross_margin AND
    provide get_annual_statements stubs explicitly (see test_runner revenue_prepass tests).
    No global patch needed — this fixture documents intent and is a hook if a future
    fixture default starts triggering fetches."""
    yield
```

(Pragmatic note for the implementer: the dormant gross-margin arm + the fact that most existing fixtures use `revenue_growth_yoy >= 0` or a gross_margin below the floor means the cohort is naturally empty in legacy tests. If any legacy test DOES trigger an unexpected fetch, Task 6 handles it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/screener/test_runner.py -k revenue_prepass -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```
git add app/screener/runner.py tests/screener/test_runner.py tests/screener/conftest.py
git commit -m "Add lazy revenue-growth trajectory pre-pass and wire into run_basis_filter"
```

---

## Task 6: Migrate existing tests to the new semantics + full suite green

**Files:**
- Modify: any existing test asserting the OLD flat `revenue_growth_yoy >= 0` knock-out
- Test: the whole suite

The behavior change: a record with `revenue_growth_yoy < 0` is **no longer dropped by the snapshot alone**. It is dropped only if the pre-pass fetched a DEFINED trajectory and γ fired. Legacy tests that set `revenue_growth_yoy < 0` and expect `filter_failed_reason == "revenue_growth"` (or expect the record to fail basis) without providing a `get_annual_statements` stub will now see either UNASSESSABLE_PASS (fetch raised) or a different outcome.

- [ ] **Step 1: Find the affected tests**

Run: `uv run python -m pytest -q 2>&1 | tail -40` and, separately, locate the call sites:
Use Grep: pattern `revenue_growth` in `tests/`, and pattern `revenueGrowth` in `tests/`.
Expected: a list of failing tests, all in the "negative revenue growth → drop" family.

- [ ] **Step 2: Update each affected test to the new contract**

For each legacy test that intends "this negative-growth name is dropped", make the intent explicit by giving it a DEFINED γ trajectory via a `get_annual_statements` stub (falling revenue, ≥4 GJ), exactly as in Task 5's `test_revenue_prepass_fetches_and_drops_gamma`. For tests that only meant "TTM≥0 passes", leave them — they still pass via `TTM_PASS`. Do NOT weaken an assertion to make it green; encode the real new behavior. If a legacy test asserted a negative-TTM drop purely as a side-detail (the test is about something else), set its `revenue_growth_yoy` to a positive value so the record passes the growth gate without needing a statement stub.

- [ ] **Step 3: Run the full suite**

Run: `uv run python -m pytest -q`
Expected: all green. Note coverage threshold (90%) is enforced centrally — the new modules need their tests (Tasks 2-5 provide them).

- [ ] **Step 4: Commit**

```
git add tests/
git commit -m "Migrate existing tests to the multi-year revenue-growth floor semantics"
```

---

## Task 7: Hermetic acceptance test — the 189-CSV as a network-free identity lock

**Files:**
- Create: `tests/screener/test_revenue_growth_acceptance.py`

The committed `revenue_growth_drops.csv` carries the raw trajectory numbers (`revenue_growth_yoy`, `multiyear_cagr`, `down_years`, `n_years`) — classifier-independent. Feeding each of the 189 rows through the pure production gate must reproduce the vintage-2026-06 identity **81 / 107 / 1**, with NO network. This is the spec §6 "189er-CSV als Fixture, Identitäts-Asserts" requirement, and it locks the gate against silent regression.

- [ ] **Step 1: Write the test (it will fail until Task 4 is in)**

```python
# tests/screener/test_revenue_growth_acceptance.py
"""Network-free acceptance lock: the vintage-2026-06 drop cohort (189) must split
81 DECLINE_DROP / 107 TRAJECTORY_RESCUE / 1 UNASSESSABLE_PASS under the production gate.
Reconstructs each record from the committed diagnostic CSV's raw trajectory columns."""
import csv
from collections import Counter
from pathlib import Path

from app.models.definedness import DefinednessOutcome
from app.models.screener_record import ScreenerRecord
from app.screener.filters import revenue_growth_outcome

CSV = Path("docs/superpowers/audits/2026-06-10-punkt-3-revenue-growth/revenue_growth_drops.csv")


def _f(x):
    return float(x) if x not in ("", "None", None) else None


def _i(x):
    return int(x) if x not in ("", "None", None) else None


def _outcome_for_row(row: dict) -> str:
    cagr, dy, ny = _f(row["multiyear_cagr"]), _i(row["down_years"]), _i(row["n_years"])
    defn = (
        DefinednessOutcome.DEFINED
        if (cagr is not None and ny is not None and ny >= 4)
        else DefinednessOutcome.UNASSESSABLE
    )
    rec = ScreenerRecord(
        ticker=row["ticker"],
        revenue_growth_yoy=_f(row["revenue_growth_yoy"]),
        multiyear_revenue_cagr=cagr,
        revenue_down_years=dy,
        revenue_growth_definedness=defn,
    )
    return revenue_growth_outcome(rec)


def test_vintage_2026_06_cohort_splits_81_107_1():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    assert len(rows) == 189
    dist = Counter(_outcome_for_row(r) for r in rows)
    assert dist["DECLINE_DROP"] == 81
    assert dist["TRAJECTORY_RESCUE"] == 107
    assert dist["UNASSESSABLE_PASS"] == 1
    assert dist.get("TTM_PASS", 0) == 0  # all 189 had TTM<0 or None -> none short-circuit
```

- [ ] **Step 2: Run it**

Run: `uv run python -m pytest tests/screener/test_revenue_growth_acceptance.py -v`
Expected: PASS (the CSV is committed; the gate is in from Task 4). If it fails on counts, the gate logic or the CSV diverged — investigate before proceeding (do NOT adjust the asserted counts to match).

- [ ] **Step 3: Commit**

```
git add tests/screener/test_revenue_growth_acceptance.py
git commit -m "Add hermetic 189-CSV acceptance lock for the revenue-growth floor (81/107/1)"
```

---

## Task 8: Align the diagnostic script to γ + unified 189 reconciliation

**Files:**
- Modify: `scripts/diagnose_revenue_growth_drops.py`

The diagnostic currently classifies via the α heuristic in `fetch_trend`. Align it to the production γ core (reuse `classify_revenue_trajectory` + `is_gamma_decline`) and apply it uniformly to ALL 189 drops (including the 13 missing-TTM), so the diagnostic and prod share one semantics and the 189-CSV is the acceptance fixture.

- [ ] **Step 1: Replace `fetch_trend`'s classification with the production primitives**

In `scripts/diagnose_revenue_growth_drops.py`, import the prod primitives and rewrite the trajectory part of `fetch_trend` to call `extract_revenue_series` + `classify_revenue_trajectory`, and set `trend_class` from `is_gamma_decline` / definedness:

```python
from app.services.income_statement import extract_revenue_series
from app.screener.revenue_trajectory import classify_revenue_trajectory, is_gamma_decline
from app.models.definedness import DefinednessOutcome
```

Replace the body of `fetch_trend` after fetching `income_stmt` with:

```python
    revenues = extract_revenue_series(income_stmt)
    cagr, down_years, defn = classify_revenue_trajectory(revenues)
    if defn is DefinednessOutcome.UNASSESSABLE:
        trend_class = "UNASSESSABLE_PASS"
    elif is_gamma_decline(cagr, down_years):
        trend_class = "DECLINE_DROP"
    else:
        trend_class = "TRAJECTORY_RESCUE"
    return {"trend_class": trend_class, "revenues": revenues, "cagr": cagr,
            "down_years": down_years}
```

- [ ] **Step 2: Run the diagnostic with trend (warm cache, $0) and confirm the unified identity**

Run: `uv run python scripts\diagnose_revenue_growth_drops.py --with-trend`
Expected: across all 189 — DECLINE_DROP=81, TRAJECTORY_RESCUE=107, UNASSESSABLE_PASS=1 (the vintage-2026-06 identity). Eyeball that TREL-B.ST is the lone UNASSESSABLE and the 5 missing-TTM γ-drops (Kering/Unilever/Vivendi/Georg Fischer/Sonova) show DECLINE_DROP.

- [ ] **Step 3: Commit**

```
git add scripts/diagnose_revenue_growth_drops.py
git commit -m "Align diagnostic classifier to production gamma core; unified 189 reconciliation"
```

---

## Task 9: Cold-run acceptance + calibration record + provenance freeze

**Files:**
- Create: `docs/superpowers/audits/2026-06-10-punkt-3-revenue-growth/calibration.md`
- Freeze: `revenue_growth_drops.csv`, `full_sweep_slipthrough.csv` (already committed) as provenance blobs

This is the Punkt-2-Gate-B equivalent: prove the activated production behavior matches the spec identities, $0, cold cache.

- [ ] **Step 1: Cold reconciliation run**

Run the diagnostic (Task 7) and capture the headline. Assert the identity **189 = 81 DROP + 107 RESCUE + 1 UNASSESSABLE** and the residuum **X=54** (γ-consistent) via `--full-sweep`.
Run: `uv run python scripts\diagnose_revenue_growth_drops.py --with-trend --full-sweep`
Expected: drop/rescue/unassessable = 81/107/1; full-sweep slip-through (re-filter with `is_gamma_decline`) = 54.

- [ ] **Step 2: Reach-scorer verification (spec §5.3)**

Confirm the 54 slip-through survivors are not structurally blocked downstream: they are basis-passers; the only gates between basis and Gemini are the EDGAR content filters (restatement/going-concern/enforcement), which are orthogonal and legitimate. Document that no *artefact* blocks them (a legitimate EDGAR drop of any individual name does not invalidate the residuum reasoning). If a reduced paid run is performed, assert at least one γ-drop stays dropped and at least one TRAJECTORY_RESCUE reaches scoring.

- [ ] **Step 3: Write `calibration.md`**

Record: the γ core and its three-signal justification; the identity 81/107/1 with the missing-TTM split (5 drop / 8 rescue); the accepted residuum X=54 (33 large-cap) with the forward-looking reframe near-verbatim from spec §5; vintage stamp 2026-06; the annual re-sweep as a standing monitoring item; `full_sweep_slipthrough.csv` as the frozen provenance blob (γ subset = `CAGR<0 ∧ down_years≥2` filter on it).

- [ ] **Step 4: Commit**

```
git add docs/superpowers/audits/2026-06-10-punkt-3-revenue-growth/calibration.md
git commit -m "Record Punkt-3 calibration: identity 81/107/1, residuum X=54, reach-scorer verified"
```

---

## After implementation

- Full suite green (`uv run python -m pytest -q`), coverage ≥ 90%.
- The arm is **active by construction** (no dormant sentinel — unlike Punkt 2 there is no pinned table or k; the γ thresholds are absolute structural constants). Reversibility is therefore NOT trivial-toggle: a revert would restore the flat gate. Note this in the PR body so Stephan knows the rollback path is a code revert, not a config flip.
- PR to `main`, reduced paid cold smoke (optional), then live verification of `revenue_growth_prepass` log line on the next run.
