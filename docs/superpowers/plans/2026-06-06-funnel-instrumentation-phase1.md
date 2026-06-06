# Funnel-Instrumentierung Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jeder Funnel-Austritt des Monthly Screeners bekommt einen benannten `reason_code` + `severity_bucket`, plus ein Report-Header und STOXX-Provenienz — reine Instrumentierung, keine Gate-/Filter-/Score-Logik wird angefasst.

**Architecture:** Ein neues Modul `app/screener/funnel.py` (reiner Datensammler) leitet Stufen-Counts und pro-Ticker-Dropouts deterministisch aus den bereits vorhandenen Pipeline-Records ab. `BasisFilterResult` wird additiv um `resolved`/`degraded` erweitert, damit ausgeschiedene Records nicht mehr verworfen werden. Artefakte (`funnel_summary.json`, `dropouts.csv`) und ein Crosshits-Report-Header rendern aus der `FunnelSummary`. `build_universe.py` schreibt ein Provenienz-Sidecar.

**Tech Stack:** Python 3.12, pydantic, dataclasses, pytest (DI-Mocks, offline). cmd.exe lokal; Tests via `uv run python -m pytest` (SOPRA-EPDR: kein `.exe`-Shim).

> **Disziplin (gilt für ALLE Tasks):** Null Änderung an Gate-/Filter-/Score-Bedingungen. Kein Drop-Ergebnis, kein Stufen-Count darf sich ändern. Bei jedem Hinweis auf nötigen Logik-Eingriff: STOP/BLOCKED an Stephan melden. Kein Push/Merge ohne Stephans Go. Nach jedem Subagent `git status`/`git log` prüfen (Commit-Hygiene). Spec: `docs/superpowers/specs/2026-06-06-funnel-instrumentation-design.md`.

---

## File Structure

**Neu:**
- `app/screener/funnel.py` — `ReasonCode`, `SeverityBucket`, `Stage`, `Dropout`, `FunnelStage`, `FunnelSummary`, Konstanten, `_severity()`, `build_funnel()`.
- `app/output/funnel_artifacts.py` — `write_funnel_artifacts()` (JSON + CSV).
- `app/output/report_header.py` — `render_header()`.
- `tests/screener/test_funnel.py`
- `tests/output/test_funnel_artifacts.py`
- `tests/output/test_report_header.py`

**Modifiziert:**
- `app/errors.py` — `DegradedDataError`.
- `app/services/yfinance_client.py:58-59` — `DegradedDataError` statt generischem `DataSourceError`.
- `app/screener/dimensions.py` — `is_crosshit()` + `qualifying_dimensions()` (DRY-Extraktion).
- `app/output/crosshits_generator.py` — nutzt extrahierte Prädikate; neuer `header`-Parameter.
- `app/screener/runner.py` — `BasisFilterResult` erweitert; `run_basis_filter` Split; `run_screener` + `run_filter_preview` verdrahten Funnel.
- `app/main.py:43-79` — Dry-Run-Pfad reicht `output_dir` durch.
- `scripts/build_universe.py` — `fetch_stoxx600()` gibt Tier zurück; `main()` schreibt Sidecar.

**Test-Anpassungen (bestehende):**
- `tests/screener/test_runner.py` — `BasisFilterResult`-Felder.

---

## Task 1: `DegradedDataError` + typisierter yfinance-Raise

**Files:**
- Modify: `app/errors.py`
- Modify: `app/services/yfinance_client.py:58-59`
- Test: `tests/services/test_yfinance_client.py`

- [ ] **Step 1: Write the failing test**

In `tests/services/test_yfinance_client.py` ergänzen (Imports oben sicherstellen: `import pytest`, `from app.errors import DataSourceError, DegradedDataError`, `from app.services.yfinance_client import YFinanceClientImpl`, `from unittest.mock import patch`):

```python
def test_degraded_dict_raises_degraded_data_error():
    client = YFinanceClientImpl()
    with patch("app.services.yfinance_client.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.info = {"symbol": "ZZZZ", "exchange": "NMS"}
        with pytest.raises(DegradedDataError):
            client.get_ticker_info("ZZZZ")


def test_degraded_data_error_is_data_source_error():
    # Subclass invariant: all existing `except DataSourceError` must still catch it.
    assert issubclass(DegradedDataError, DataSourceError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/services/test_yfinance_client.py::test_degraded_dict_raises_degraded_data_error -v`
Expected: FAIL — `ImportError: cannot import name 'DegradedDataError'`.

- [ ] **Step 3: Add the exception**

In `app/errors.py` nach `DataSourceError` einfügen:

```python
class DegradedDataError(DataSourceError):
    """Raised when yfinance returns a non-empty but degraded info dict (no
    identity, no marketCap). Subclass of DataSourceError so existing handlers
    still catch it; lets the resolution stage distinguish DEGRADED_DICT from
    generic unresolved attrition."""
```

- [ ] **Step 4: Raise the typed error**

In `app/services/yfinance_client.py`: Import ergänzen (Zeile 5):

```python
from app.errors import DataSourceError, DegradedDataError
```

Zeile 58-59 ersetzen:

```python
        if not (data.get("shortName") or data.get("longName") or data.get("marketCap")):
            raise DegradedDataError(f"yfinance returned degraded info for {ticker}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/services/test_yfinance_client.py -v`
Expected: PASS (alle, inkl. bestehender — die degraded-Tests fingen bisher `DataSourceError` und fangen die Subklasse weiterhin).

- [ ] **Step 6: Commit**

```bash
git add app/errors.py app/services/yfinance_client.py tests/services/test_yfinance_client.py
git commit -m "Add DegradedDataError to distinguish degraded yfinance dict from generic attrition"
```

---

## Task 2: `BasisFilterResult` erweitern + Resolution-Split

**Files:**
- Modify: `app/screener/runner.py:25-94`
- Test: `tests/screener/test_runner.py`

- [ ] **Step 1: Write the failing test**

In `tests/screener/test_runner.py` ergänzen (Imports: `from app.errors import DataSourceError, DegradedDataError`, `from app.screener.runner import run_basis_filter, BasisFilterResult`). Fake-Client:

```python
class _FunnelYF:
    """Resolves GOOD; raises DegradedDataError for DEGR; DataSourceError for GONE."""
    def get_ticker_info(self, ticker):
        if ticker == "DEGR":
            raise DegradedDataError("degraded")
        if ticker == "GONE":
            raise DataSourceError("404")
        return {"shortName": ticker, "marketCap": 5e9, "averageVolume": 5e5,
                "currency": "EUR", "grossMargins": 0.5, "revenueGrowth": 0.1,
                "sector": "Technology"}
    def get_fx_rate(self, currency):
        return 1.0


def test_basis_result_splits_degraded_from_unresolved():
    result = run_basis_filter(["GOOD", "DEGR", "GONE"], _FunnelYF())
    assert result.degraded == ["DEGR"]
    assert set(result.unresolved) == {"DEGR", "GONE"}  # unresolved = all that failed resolution
    assert [r.ticker for r in result.resolved] == ["GOOD"]
    assert [r.ticker for r in result.passed] == ["GOOD"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_runner.py::test_basis_result_splits_degraded_from_unresolved -v`
Expected: FAIL — `AttributeError: 'BasisFilterResult' object has no attribute 'degraded'`.

- [ ] **Step 3: Extend the dataclass**

In `app/screener/runner.py` `BasisFilterResult` (Zeile 25-35) ersetzen:

```python
@dataclass
class BasisFilterResult:
    """Result of the basis filter stage.

    `passed` survived the basis filters. `resolved` are ALL records that yfinance
    resolved (passed + gate-failed) — gate-failed ones carry filter_failed_reason.
    `unresolved` are symbols yfinance could not resolve at all (the attrition
    signal); `degraded` is the subset of `unresolved` that raised DegradedDataError.
    """

    passed: list[ScreenerRecord] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    resolved: list[ScreenerRecord] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Split the catch + populate resolved**

Import ergänzen (Zeile 10): `from app.errors import DataSourceError, DegradedDataError`.

In `run_basis_filter` (Zeile 66-94) den Loop-Block + Return ersetzen:

```python
    records: list[ScreenerRecord] = []
    unresolved: list[str] = []
    degraded: list[str] = []
    fx_cache: dict[str, float] = {}
    for ticker in tickers:
        try:
            info = yfinance.get_ticker_info(ticker)
            record = ScreenerRecord.from_yfinance_info(ticker, info)
            record.market_cap_eur = _resolve_market_cap_eur(record, yfinance, fx_cache)
            records.append(record)
        except DegradedDataError as exc:  # MUST precede DataSourceError (subclass)
            logger.warning("ticker=%s degraded dict: %s", ticker, exc)
            unresolved.append(ticker)
            degraded.append(ticker)
        except (DataSourceError, ValidationError) as exc:
            logger.warning("ticker=%s data fetch failed: %s", ticker, exc)
            unresolved.append(ticker)

    us_fetched = sum(1 for r in records if "." not in r.ticker)
    eu_fetched = len(records) - us_fetched
    logger.info("runner: fetched US=%d EU=%d total=%d/%d", us_fetched, eu_fetched, len(records), len(tickers))

    if unresolved:
        unresolved.sort()
        # WARNING level is deliberate: an unresolved universe symbol is silent
        # attrition and must be visible regardless of any INFO logging config.
        logger.warning(
            "resolution: %d/%d universe symbols unresolved by yfinance: %s",
            len(unresolved),
            len(tickers),
            unresolved,
        )

    return BasisFilterResult(
        passed=apply_basis_filters(records),
        unresolved=unresolved,
        resolved=records,
        degraded=sorted(degraded),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/screener/test_runner.py -v`
Expected: PASS. Falls ein bestehender Test `BasisFilterResult(passed=..., unresolved=...)` positional/per-Keyword baut: bleibt gültig (neue Felder haben Defaults).

- [ ] **Step 6: Commit**

```bash
git add app/screener/runner.py tests/screener/test_runner.py
git commit -m "Extend BasisFilterResult with resolved/degraded; split resolution attrition"
```

---

## Task 3: Crosshit-Prädikat DRY extrahieren

**Files:**
- Modify: `app/screener/dimensions.py`
- Modify: `app/output/crosshits_generator.py:41-59`
- Test: `tests/screener/test_dimensions.py` (neu), `tests/output/test_crosshits_generator.py` (Regression)

- [ ] **Step 1: Write the failing test**

`tests/screener/test_dimensions.py` (neu):

```python
from app.models.screener_record import ScreenerRecord
from app.screener.dimensions import is_crosshit, qualifying_dimensions


def _rec(**dims):
    return ScreenerRecord(ticker="X", gemini_dimensions=dims or None)


def test_qualifying_dimensions_filters_by_threshold():
    rec = _rec(growth=4, profitability=5, management=3)
    assert set(qualifying_dimensions(rec, 4.0)) == {"growth", "profitability"}


def test_is_crosshit_needs_min_dimensions():
    assert is_crosshit(_rec(growth=4, profitability=4), 4.0, 2) is True
    assert is_crosshit(_rec(growth=4, management=3), 4.0, 2) is False


def test_is_crosshit_false_when_no_dimensions():
    assert is_crosshit(_rec(), 4.0, 2) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_dimensions.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_crosshit'`.

- [ ] **Step 3: Add the predicates**

In `app/screener/dimensions.py` anhängen:

```python
from app.models.screener_record import ScreenerRecord


def qualifying_dimensions(record: ScreenerRecord, score_threshold: float) -> list[str]:
    """Dimensions whose Gemini score meets the threshold. Empty if unscored."""
    dims = record.gemini_dimensions or {}
    return [d for d in DIMENSIONS if dims.get(d, 0) >= score_threshold]


def is_crosshit(record: ScreenerRecord, score_threshold: float, min_dimensions: int) -> bool:
    """True iff the record qualifies on >= min_dimensions (cap-independent — the
    display cap in crosshits_generator is presentation, not a funnel exit)."""
    return len(qualifying_dimensions(record, score_threshold)) >= min_dimensions
```

- [ ] **Step 4: Refactor `_compute_crosshits` to reuse the predicate**

In `app/output/crosshits_generator.py` Import (Zeile 7) ersetzen:

```python
from app.screener.dimensions import DIMENSIONS, is_crosshit, qualifying_dimensions
```

`_compute_crosshits` (Zeile 41-59) Körper ersetzen — Verhalten identisch:

```python
def _compute_crosshits(
    scored: list[ScreenerRecord],
    score_threshold: float,
    min_dimensions: int,
    cap: int,
) -> list[dict]:
    result = []
    for record in scored:
        qualifying = qualifying_dimensions(record, score_threshold)
        if len(qualifying) >= min_dimensions:
            dims = record.gemini_dimensions or {}
            avg = sum(dims.get(d, 0) for d in qualifying) / len(qualifying)
            result.append({
                "record": record,
                "qualifying_dims": qualifying,
                "avg_score": round(avg, 2),
            })
    result.sort(key=lambda x: (-len(x["qualifying_dims"]), -x["avg_score"]))
    return result[:cap]
```

- [ ] **Step 5: Run tests to verify all pass (regression on crosshits output)**

Run: `uv run python -m pytest tests/screener/test_dimensions.py tests/output/test_crosshits_generator.py -v`
Expected: PASS — bestehende Crosshits-Tests unverändert grün (Output identisch).

- [ ] **Step 6: Commit**

```bash
git add app/screener/dimensions.py app/output/crosshits_generator.py tests/screener/test_dimensions.py
git commit -m "Extract is_crosshit/qualifying_dimensions predicates (DRY) — crosshits output unchanged"
```

---

## Task 4: `funnel.py` — Enums, Dropout, Konstanten, Severity

**Files:**
- Create: `app/screener/funnel.py`
- Test: `tests/screener/test_funnel.py`

- [ ] **Step 1: Write the failing test**

`tests/screener/test_funnel.py` (neu):

```python
from app.screener.funnel import (
    LARGE_CAP_GROWTH_EUR,
    LARGE_CAP_VOLUME_EUR,
    ReasonCode,
    SeverityBucket,
    _severity,
)


def test_volume_threshold_decoupled_from_growth():
    # market cap between the two thresholds (3B..10B): REVIEW for volume, BENIGN for growth.
    mc = 5_000_000_000
    assert LARGE_CAP_VOLUME_EUR < mc < LARGE_CAP_GROWTH_EUR
    assert _severity(ReasonCode.GATE_VOLUME, market_cap_eur=mc, sector_wide=False) == SeverityBucket.REVIEW
    assert _severity(ReasonCode.GATE_REVENUE_GROWTH, market_cap_eur=mc, sector_wide=False) == SeverityBucket.BENIGN


def test_growth_review_above_growth_threshold():
    assert _severity(ReasonCode.GATE_REVENUE_GROWTH, market_cap_eur=20_000_000_000, sector_wide=False) == SeverityBucket.REVIEW


def test_market_cap_none_is_benign_never_crashes():
    assert _severity(ReasonCode.GATE_VOLUME, market_cap_eur=None, sector_wide=False) == SeverityBucket.BENIGN


def test_gross_margin_review_only_when_sector_wide():
    assert _severity(ReasonCode.GATE_GROSS_MARGIN, market_cap_eur=None, sector_wide=True) == SeverityBucket.REVIEW
    assert _severity(ReasonCode.GATE_GROSS_MARGIN, market_cap_eur=None, sector_wide=False) == SeverityBucket.BENIGN


def test_always_review_codes():
    for rc in (ReasonCode.RESOLUTION_DEGRADED_DICT, ReasonCode.SCORE_NOT_SCORED):
        assert _severity(rc, market_cap_eur=None, sector_wide=False) == SeverityBucket.REVIEW


def test_always_benign_codes():
    for rc in (ReasonCode.GATE_MARKET_CAP, ReasonCode.GATE_GOING_CONCERN,
               ReasonCode.GATE_ENFORCEMENT, ReasonCode.GATE_RESTATEMENT,
               ReasonCode.RESOLUTION_UNRESOLVED, ReasonCode.SCORE_BELOW_THRESHOLD):
        assert _severity(rc, market_cap_eur=None, sector_wide=False) == SeverityBucket.BENIGN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_funnel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.screener.funnel'`.

- [ ] **Step 3: Create the module skeleton**

`app/screener/funnel.py` (neu):

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.models.screener_record import ScreenerRecord

# --- Tunable instrumentation constants (severity only; no gate touches these) ---
LARGE_CAP_VOLUME_EUR = 3_000_000_000     # GATE_VOLUME: a big name failing volume ~ data bug
LARGE_CAP_GROWTH_EUR = 10_000_000_000    # GATE_REVENUE_GROWTH: big mature firm can really shrink
SECTOR_WIDE_FRACTION = 0.5
SECTOR_WIDE_MIN_SIZE = 5
SECTORS_WITHOUT_GROSS_MARGIN = {"Financial Services", "Real Estate"}  # yfinance taxonomy


class ReasonCode(str, Enum):
    RESOLUTION_DEGRADED_DICT = "RESOLUTION_DEGRADED_DICT"
    RESOLUTION_UNRESOLVED = "RESOLUTION_UNRESOLVED"
    GATE_VOLUME = "GATE_VOLUME"
    GATE_MARKET_CAP = "GATE_MARKET_CAP"
    GATE_GROSS_MARGIN = "GATE_GROSS_MARGIN"
    GATE_REVENUE_GROWTH = "GATE_REVENUE_GROWTH"
    GATE_RESTATEMENT = "GATE_RESTATEMENT"
    GATE_GOING_CONCERN = "GATE_GOING_CONCERN"
    GATE_ENFORCEMENT = "GATE_ENFORCEMENT"
    SCORE_BELOW_THRESHOLD = "SCORE_BELOW_THRESHOLD"
    SCORE_NOT_SCORED = "SCORE_NOT_SCORED"


class SeverityBucket(str, Enum):
    BENIGN = "BENIGN"
    REVIEW = "REVIEW"


class Stage(str, Enum):
    UNIVERSE = "universe"
    RESOLUTION = "resolution"
    BASIS_GATES = "basis_gates"
    EDGAR_GATES = "edgar_gates"
    SCORING = "scoring"
    CROSSHITS = "crosshits"


# Map the code's filter_failed_reason -> reason_code (1:1, no invented codes).
_BASIS_REASON: dict[str, ReasonCode] = {
    "avg_volume": ReasonCode.GATE_VOLUME,
    "market_cap": ReasonCode.GATE_MARKET_CAP,
    "gross_margin": ReasonCode.GATE_GROSS_MARGIN,
    "revenue_growth": ReasonCode.GATE_REVENUE_GROWTH,
}
_EDGAR_REASON: dict[str, ReasonCode] = {
    "restatement": ReasonCode.GATE_RESTATEMENT,
    "going_concern": ReasonCode.GATE_GOING_CONCERN,
    "enforcement": ReasonCode.GATE_ENFORCEMENT,
}

_ALWAYS_REVIEW = {ReasonCode.RESOLUTION_DEGRADED_DICT, ReasonCode.SCORE_NOT_SCORED}


def _severity(
    reason_code: ReasonCode,
    *,
    market_cap_eur: float | None,
    sector_wide: bool,
) -> SeverityBucket:
    """Fixed table. market_cap_eur=None is treated as 'not large-cap' (never None>=int)."""
    mc = market_cap_eur if market_cap_eur is not None else -1.0
    if reason_code == ReasonCode.GATE_VOLUME:
        return SeverityBucket.REVIEW if mc >= LARGE_CAP_VOLUME_EUR else SeverityBucket.BENIGN
    if reason_code == ReasonCode.GATE_REVENUE_GROWTH:
        return SeverityBucket.REVIEW if mc >= LARGE_CAP_GROWTH_EUR else SeverityBucket.BENIGN
    if reason_code == ReasonCode.GATE_GROSS_MARGIN:
        return SeverityBucket.REVIEW if sector_wide else SeverityBucket.BENIGN
    if reason_code in _ALWAYS_REVIEW:
        return SeverityBucket.REVIEW
    return SeverityBucket.BENIGN
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/screener/test_funnel.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/screener/funnel.py tests/screener/test_funnel.py
git commit -m "Add funnel reason codes, severity table with decoupled large-cap thresholds"
```

---

## Task 5: `funnel.py` — `build_funnel` + Reconciliation + sector_wide

**Files:**
- Modify: `app/screener/funnel.py`
- Test: `tests/screener/test_funnel.py`

- [ ] **Step 1: Write the failing tests**

In `tests/screener/test_funnel.py` ergänzen (Imports oben: `from app.models.screener_record import ScreenerRecord`, `from app.screener.runner import BasisFilterResult`, `from app.screener.funnel import build_funnel, Stage`):

```python
def _resolved(ticker, sector="Technology", mc=5e9, *, basis_reason=None,
              edgar_reason=None, edgar_skipped=None, dims=None):
    r = ScreenerRecord(ticker=ticker, gics_sector=sector, market_cap_eur=mc)
    if basis_reason:
        r.filter_passed_basis = False
        r.filter_failed_reason = basis_reason
        return r
    r.filter_passed_basis = True
    if edgar_skipped:
        r.edgar_skipped = True
        r.edgar_skipped_reason = edgar_skipped
        r.filter_passed_edgar = None
    elif edgar_reason:
        r.filter_passed_edgar = False
        r.filter_failed_reason = edgar_reason
    else:
        r.filter_passed_edgar = True
    r.gemini_dimensions = dims
    return r


def test_reconciliation_invariant_full_run():
    # Universe of 7: 1 degraded, 1 unresolved, 1 volume-drop, 1 gc-drop,
    # 1 skipped pass-through, 1 below-threshold, 1 crosshit.
    skipped = _resolved("SKIP", edgar_skipped="no_cik", dims={"growth": 4, "profitability": 4})
    below = _resolved("LOW", dims={"growth": 4})
    hit = _resolved("HIT", dims={"growth": 4, "profitability": 4})
    vol = _resolved("VOL", basis_reason="avg_volume")
    gc = _resolved("GC", edgar_reason="going_concern")
    resolved = [vol, skipped, gc, below, hit]
    passed = [skipped, gc, below, hit]              # basis survivors
    scored = [skipped, below, hit]                  # edgar survivors (incl. skipped pass-through)
    basis = BasisFilterResult(passed=passed, unresolved=["DEGR", "GONE"],
                              resolved=resolved, degraded=["DEGR"])
    summary, dropouts = build_funnel(
        universe=["VOL", "SKIP", "GC", "LOW", "HIT", "DEGR", "GONE"],
        basis=basis, scored=scored,
        score_threshold=4.0, crosshits_min_dimensions=2,
    )
    # Reconciliation: |universe| == Σ drops + |crosshits übrig|
    crosshit_uebrig = summary.stage(Stage.CROSSHITS).remaining
    assert len(dropouts) + crosshit_uebrig == 7
    # No double counting; all dropouts are universe members; disjoint from crosshits.
    drop_tickers = [d.ticker for d in dropouts]
    assert len(drop_tickers) == len(set(drop_tickers))
    assert set(drop_tickers) <= set(["VOL", "SKIP", "GC", "LOW", "HIT", "DEGR", "GONE"])
    assert "HIT" not in drop_tickers
    # Pass-through is NOT a drop and counts toward edgar 'remaining'.
    assert "SKIP" not in drop_tickers
    assert summary.pass_through_count == 1


def test_dry_run_omits_scoring_stages():
    vol = _resolved("VOL", basis_reason="avg_volume")
    ok = _resolved("OK")
    basis = BasisFilterResult(passed=[ok], unresolved=[], resolved=[vol, ok], degraded=[])
    summary, dropouts = build_funnel(universe=["VOL", "OK"], basis=basis, scored=None,
                                     score_threshold=4.0, crosshits_min_dimensions=2)
    assert summary.stage(Stage.SCORING).ran is False
    assert summary.stage(Stage.CROSSHITS).ran is False
    # Reconciliation only up to last run stage (EDGAR remaining = 1).
    assert summary.stage(Stage.EDGAR_GATES).remaining == 1


def test_sector_wide_excludes_margin_free_sectors():
    # 6 Financials all margin-dropped -> all BENIGN, no sector_wide.
    fin = [_resolved(f"F{i}", sector="Financial Services", basis_reason="gross_margin")
           for i in range(6)]
    basis = BasisFilterResult(passed=[], unresolved=[],
                              resolved=fin, degraded=[])
    summary, dropouts = build_funnel(universe=[r.ticker for r in fin], basis=basis,
                                     scored=None, score_threshold=4.0, crosshits_min_dimensions=2)
    assert all(d.severity_bucket == SeverityBucket.BENIGN for d in dropouts)
    assert all(d.sector_wide is False for d in dropouts)


def test_sector_wide_fires_for_normal_sector():
    # 6 Industrials margin-dropped (denominator reached = 6, all dropped) -> REVIEW.
    ind = [_resolved(f"I{i}", sector="Industrials", basis_reason="gross_margin")
           for i in range(6)]
    basis = BasisFilterResult(passed=[], unresolved=[], resolved=ind, degraded=[])
    summary, dropouts = build_funnel(universe=[r.ticker for r in ind], basis=basis,
                                     scored=None, score_threshold=4.0, crosshits_min_dimensions=2)
    assert all(d.sector_wide is True for d in dropouts)
    assert all(d.severity_bucket == SeverityBucket.REVIEW for d in dropouts)


def test_sector_wide_denominator_excludes_pre_margin_drops():
    # Industrials: 4 volume-drops (never reached margin) + 1 margin-drop.
    # reached = 1 (the margin-drop only) -> below MIN_SIZE -> BENIGN.
    recs = [_resolved(f"V{i}", sector="Industrials", basis_reason="avg_volume")
            for i in range(4)]
    recs.append(_resolved("M0", sector="Industrials", basis_reason="gross_margin"))
    basis = BasisFilterResult(passed=[], unresolved=[], resolved=recs, degraded=[])
    summary, dropouts = build_funnel(universe=[r.ticker for r in recs], basis=basis,
                                     scored=None, score_threshold=4.0, crosshits_min_dimensions=2)
    margin_drop = next(d for d in dropouts if d.ticker == "M0")
    assert margin_drop.sector_wide is False  # MIN_SIZE floor on reached-denominator protects it
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/screener/test_funnel.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_funnel'`.

- [ ] **Step 3: Implement `Dropout`, `FunnelStage`, `FunnelSummary`, `build_funnel`**

In `app/screener/funnel.py` anhängen:

```python
@dataclass(frozen=True)
class Dropout:
    ticker: str
    stage: Stage
    reason_code: ReasonCode
    severity_bucket: SeverityBucket
    is_large_cap: bool            # market_cap_eur >= LARGE_CAP_VOLUME_EUR (descriptive floor)
    sector_wide: bool
    market_cap_eur: float | None
    gics_sector: str | None


@dataclass(frozen=True)
class FunnelStage:
    stage: Stage
    entered: int
    dropped: int
    remaining: int
    ran: bool = True


@dataclass
class FunnelSummary:
    stages: list[FunnelStage]
    review_flags: int
    pass_through_count: int
    provenance: dict[str, Any] | None = field(default=None)

    def stage(self, stage: Stage) -> FunnelStage:
        for s in self.stages:
            if s.stage == stage:
                return s
        raise KeyError(stage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stages": [
                {"stage": s.stage.value, "entered": s.entered, "dropped": s.dropped,
                 "remaining": s.remaining, "ran": s.ran}
                for s in self.stages
            ],
            "review_flags": self.review_flags,
            "pass_through_count": self.pass_through_count,
            "provenance": self.provenance,
        }


def _is_large_cap(market_cap_eur: float | None) -> bool:
    return market_cap_eur is not None and market_cap_eur >= LARGE_CAP_VOLUME_EUR


def _compute_sector_wide(resolved: list[ScreenerRecord]) -> set[str]:
    """Return the set of sectors flagged sector_wide for GATE_GROSS_MARGIN.

    Denominator = records that REACHED the margin gate = basis-passed
    + gross_margin drops + revenue_growth drops (short-circuit order:
    volume->market_cap->gross_margin->revenue_growth, so volume/market_cap
    drops never reached margin). Margin-free sectors are excluded outright.
    """
    reached: dict[str, int] = {}
    margin_drops: dict[str, int] = {}
    for r in resolved:
        sector = r.gics_sector
        if sector in SECTORS_WITHOUT_GROSS_MARGIN:
            continue
        reason = r.filter_failed_reason
        reached_gate = (
            r.filter_passed_basis is True
            or reason in ("gross_margin", "revenue_growth")
        )
        if reached_gate:
            reached[sector] = reached.get(sector, 0) + 1
        if reason == "gross_margin":
            margin_drops[sector] = margin_drops.get(sector, 0) + 1
    flagged: set[str] = set()
    for sector, n in reached.items():
        m = margin_drops.get(sector, 0)
        if n >= SECTOR_WIDE_MIN_SIZE and n > 0 and (m / n) >= SECTOR_WIDE_FRACTION:
            flagged.add(sector)
    return flagged


def _make_dropout(record: ScreenerRecord, stage: Stage, reason_code: ReasonCode,
                  sector_wide_sectors: set[str]) -> Dropout:
    sector_wide = (reason_code == ReasonCode.GATE_GROSS_MARGIN
                   and record.gics_sector in sector_wide_sectors)
    severity = _severity(reason_code, market_cap_eur=record.market_cap_eur,
                         sector_wide=sector_wide)
    return Dropout(
        ticker=record.ticker, stage=stage, reason_code=reason_code,
        severity_bucket=severity, is_large_cap=_is_large_cap(record.market_cap_eur),
        sector_wide=sector_wide, market_cap_eur=record.market_cap_eur,
        gics_sector=record.gics_sector,
    )


def build_funnel(
    universe: list[str],
    basis: "BasisFilterResult",
    scored: list[ScreenerRecord] | None,
    *,
    score_threshold: float,
    crosshits_min_dimensions: int,
    provenance: dict[str, Any] | None = None,
) -> tuple[FunnelSummary, list[Dropout]]:
    from app.screener.dimensions import is_crosshit  # local import avoids cycle

    n_universe = len(universe)
    dropouts: list[Dropout] = []
    sector_wide_sectors = _compute_sector_wide(basis.resolved)

    # --- Resolution ---
    for t in basis.degraded:
        dropouts.append(Dropout(t, Stage.RESOLUTION, ReasonCode.RESOLUTION_DEGRADED_DICT,
                                SeverityBucket.REVIEW, False, False, None, None))
    for t in basis.unresolved:
        if t in basis.degraded:
            continue
        dropouts.append(Dropout(t, Stage.RESOLUTION, ReasonCode.RESOLUTION_UNRESOLVED,
                                SeverityBucket.BENIGN, False, False, None, None))
    n_resolved = len(basis.resolved)

    # --- Basis gates ---
    basis_drops = [r for r in basis.resolved if r.filter_passed_basis is False]
    for r in basis_drops:
        rc = _BASIS_REASON[r.filter_failed_reason]
        dropouts.append(_make_dropout(r, Stage.BASIS_GATES, rc, sector_wide_sectors))
    n_basis_passed = len(basis.passed)

    # --- EDGAR gates (pass-throughs are NOT drops) ---
    edgar_drops = [r for r in basis.passed if r.filter_passed_edgar is False]
    for r in edgar_drops:
        rc = _EDGAR_REASON[r.filter_failed_reason]
        dropouts.append(_make_dropout(r, Stage.EDGAR_GATES, rc, sector_wide_sectors))
    pass_through = [r for r in basis.passed if r.edgar_skipped]
    n_edgar_remaining = n_basis_passed - len(edgar_drops)

    stages = [
        FunnelStage(Stage.UNIVERSE, n_universe, 0, n_universe),
        FunnelStage(Stage.RESOLUTION, n_universe, len(basis.unresolved), n_resolved),
        FunnelStage(Stage.BASIS_GATES, n_resolved, len(basis_drops), n_basis_passed),
        FunnelStage(Stage.EDGAR_GATES, n_basis_passed, len(edgar_drops), n_edgar_remaining),
    ]

    # --- Scoring + Crosshits (only if scoring ran) ---
    if scored is None:
        stages.append(FunnelStage(Stage.SCORING, n_edgar_remaining, 0, n_edgar_remaining, ran=False))
        stages.append(FunnelStage(Stage.CROSSHITS, n_edgar_remaining, 0, n_edgar_remaining, ran=False))
    else:
        not_scored = [r for r in scored if r.gemini_dimensions is None]
        for r in not_scored:
            dropouts.append(_make_dropout(r, Stage.SCORING, ReasonCode.SCORE_NOT_SCORED,
                                          sector_wide_sectors))
        successfully_scored = [r for r in scored if r.gemini_dimensions is not None]
        crosshits = [r for r in successfully_scored
                     if is_crosshit(r, score_threshold, crosshits_min_dimensions)]
        below = [r for r in successfully_scored
                 if not is_crosshit(r, score_threshold, crosshits_min_dimensions)]
        for r in below:
            dropouts.append(_make_dropout(r, Stage.CROSSHITS, ReasonCode.SCORE_BELOW_THRESHOLD,
                                          sector_wide_sectors))
        stages.append(FunnelStage(Stage.SCORING, n_edgar_remaining, len(not_scored),
                                  len(successfully_scored)))
        stages.append(FunnelStage(Stage.CROSSHITS, len(successfully_scored), len(below),
                                  len(crosshits)))

    review_flags = sum(1 for d in dropouts if d.severity_bucket == SeverityBucket.REVIEW)
    summary = FunnelSummary(stages=stages, review_flags=review_flags,
                            pass_through_count=len(pass_through), provenance=provenance)
    return summary, dropouts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/screener/test_funnel.py -v`
Expected: PASS (alle, inkl. Reconciliation, Dry-Run, sector_wide).

- [ ] **Step 5: Commit**

```bash
git add app/screener/funnel.py tests/screener/test_funnel.py
git commit -m "Add build_funnel with stage counts, reconciliation, reached-margin sector_wide"
```

---

## Task 6: `funnel_artifacts.py` — JSON + CSV schreiben

**Files:**
- Create: `app/output/funnel_artifacts.py`
- Test: `tests/output/test_funnel_artifacts.py`

- [ ] **Step 1: Write the failing test**

`tests/output/test_funnel_artifacts.py` (neu):

```python
import csv
import json

from app.output.funnel_artifacts import write_funnel_artifacts
from app.screener.funnel import (
    Dropout, FunnelStage, FunnelSummary, ReasonCode, SeverityBucket, Stage,
)


def _summary():
    stages = [FunnelStage(Stage.UNIVERSE, 3, 0, 3),
              FunnelStage(Stage.RESOLUTION, 3, 1, 2)]
    return FunnelSummary(stages=stages, review_flags=1, pass_through_count=0,
                         provenance={"stoxx_tier": "wikipedia"})


def _dropout():
    return Dropout("VOL", Stage.BASIS_GATES, ReasonCode.GATE_VOLUME,
                   SeverityBucket.REVIEW, True, False, 5e9, "Technology")


def test_writes_json_and_csv(tmp_path):
    paths = write_funnel_artifacts(_summary(), [_dropout()], tmp_path, "2026-06")
    names = {p.name for p in paths}
    assert names == {"2026-06-funnel_summary.json", "2026-06-dropouts.csv"}

    js = json.loads((tmp_path / "Universum" / "2026-06-funnel_summary.json").read_text("utf-8"))
    assert js["review_flags"] == 1
    assert js["provenance"]["stoxx_tier"] == "wikipedia"

    rows = list(csv.DictReader((tmp_path / "Universum" / "2026-06-dropouts.csv").read_text("utf-8").splitlines()))
    assert rows[0]["ticker"] == "VOL"
    assert rows[0]["reason_code"] == "GATE_VOLUME"
    assert rows[0]["severity_bucket"] == "REVIEW"
    assert rows[0]["is_large_cap"] == "True"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/output/test_funnel_artifacts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.output.funnel_artifacts'`.

- [ ] **Step 3: Implement the writer**

`app/output/funnel_artifacts.py` (neu):

```python
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from app.screener.funnel import Dropout, FunnelSummary

logger = logging.getLogger(__name__)

_CSV_FIELDS = [
    "ticker", "stage", "reason_code", "severity_bucket",
    "is_large_cap", "sector_wide", "market_cap_eur", "gics_sector",
]


def write_funnel_artifacts(
    summary: FunnelSummary,
    dropouts: list[Dropout],
    output_dir: Path,
    run_month: str,
) -> list[Path]:
    out = output_dir / "Universum"
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / f"{run_month}-funnel_summary.json"
    json_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")

    csv_path = out / f"{run_month}-dropouts.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for d in dropouts:
            writer.writerow({
                "ticker": d.ticker,
                "stage": d.stage.value,
                "reason_code": d.reason_code.value,
                "severity_bucket": d.severity_bucket.value,
                "is_large_cap": d.is_large_cap,
                "sector_wide": d.sector_wide,
                "market_cap_eur": d.market_cap_eur,
                "gics_sector": d.gics_sector,
            })

    logger.info("funnel: wrote %s (%d dropouts, %d review-flags)",
                json_path.name, len(dropouts), summary.review_flags)
    return [json_path, csv_path]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/output/test_funnel_artifacts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/output/funnel_artifacts.py tests/output/test_funnel_artifacts.py
git commit -m "Add funnel artifact writer (funnel_summary.json + dropouts.csv)"
```

---

## Task 7: `report_header.py` — Header aus `FunnelSummary`

**Files:**
- Create: `app/output/report_header.py`
- Test: `tests/output/test_report_header.py`

- [ ] **Step 1: Write the failing test**

`tests/output/test_report_header.py` (neu):

```python
from app.output.report_header import render_header
from app.screener.funnel import FunnelStage, FunnelSummary, Stage


def _summary():
    stages = [
        FunnelStage(Stage.UNIVERSE, 2100, 0, 2100),
        FunnelStage(Stage.RESOLUTION, 2100, 100, 2000),
        FunnelStage(Stage.BASIS_GATES, 2000, 1500, 500),
        FunnelStage(Stage.EDGAR_GATES, 500, 10, 490),
        FunnelStage(Stage.SCORING, 490, 5, 485),
        FunnelStage(Stage.CROSSHITS, 485, 400, 85),
    ]
    return FunnelSummary(stages=stages, review_flags=3, pass_through_count=12,
                         provenance={"stoxx_tier": "ishares-b", "sp500_count": 503,
                                     "sp400_count": 400, "stoxx600_count": 600})


def test_header_contains_key_facts():
    out = render_header(_summary(), run_month="2026-06")
    assert "2026-06" in out
    assert "Review-Flags: 3" in out
    assert "ishares-b" in out
    assert "Crosshit" in out             # threshold plaintext
    assert "| Stufe |" in out            # funnel table header
    assert "yfinance" in out and "SEC EDGAR" in out


def test_header_graceful_without_provenance():
    s = _summary()
    s.provenance = None
    out = render_header(s, run_month="2026-06")
    assert "nicht erfasst" in out        # graceful fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/output/test_report_header.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the renderer**

`app/output/report_header.py` (neu):

```python
from __future__ import annotations

from app.screener.funnel import FunnelSummary, Stage

_STAGE_LABEL = {
    Stage.UNIVERSE: "Universum",
    Stage.RESOLUTION: "Resolution",
    Stage.BASIS_GATES: "Basis-Gates",
    Stage.EDGAR_GATES: "EDGAR-Gates",
    Stage.SCORING: "Scoring",
    Stage.CROSSHITS: "Crosshits",
}


def render_header(summary: FunnelSummary, run_month: str) -> str:
    prov = summary.provenance or {}
    stoxx_tier = prov.get("stoxx_tier", "nicht erfasst")
    universe_size = summary.stage(Stage.UNIVERSE).entered

    lines = [
        f"## Lauf-Übersicht {run_month}",
        "",
        f"- **Stichtag:** {run_month} · **Universum:** {universe_size} "
        f"(S&P 500 / S&P 400 / STOXX 600)",
        f"- **STOXX-Quellstufe:** {stoxx_tier}",
        "- **Datenbasis:** yfinance (Kurs/Vol/Fundamentals) · "
        "SEC EDGAR (Filings; DEF-14A/Form-4 nur US-Filer)",
        "",
        "| Stufe | rein | raus | übrig |",
        "|---|---|---|---|",
    ]
    for s in summary.stages:
        raus = str(s.dropped) if s.ran else "—"
        rein = str(s.entered) if s.ran else "—"
        uebrig = str(s.remaining)
        lines.append(f"| {_STAGE_LABEL[s.stage]} | {rein} | {raus} | {uebrig} |")
    lines += [
        "",
        f"**Review-Flags: {summary.review_flags}** (Aufschlüsselung in "
        f"`{run_month}-dropouts.csv`)",
        "",
        "> Jede Aktie wird auf mehreren Fisher-Dimensionen 0–5 bewertet. "
        "Crosshit = ≥2 Dimensionen ≥4.0 — kein Einzelausreißer, sondern über "
        "mehrere unabhängige Achsen bestätigte Qualität.",
        "",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/output/test_report_header.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/output/report_header.py tests/output/test_report_header.py
git commit -m "Add report header renderer (funnel table, review-flags, threshold plaintext)"
```

---

## Task 8: Crosshits-Header-Injektion

**Files:**
- Modify: `app/output/crosshits_generator.py:16-38,62-73`
- Test: `tests/output/test_crosshits_generator.py`

- [ ] **Step 1: Write the failing test**

In `tests/output/test_crosshits_generator.py` ergänzen:

```python
def test_header_injected_after_title(tmp_path):
    from app.output.crosshits_generator import generate
    records = []
    path = generate(records, _run_record(), tmp_path,
                    score_threshold=4.0, min_dimensions=2,
                    header="## Lauf-Übersicht 2026-06\n\nHEADER_MARKER\n")
    text = path.read_text("utf-8")
    assert "HEADER_MARKER" in text
    title_idx = text.index("# Universum")
    header_idx = text.index("HEADER_MARKER")
    schwelle_idx = text.index("*Schwelle")
    assert title_idx < header_idx < schwelle_idx  # header between title and threshold note
```

(Falls `_run_record`-Helper im Test fehlt: aus den bestehenden Tests derselben Datei wiederverwenden.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/output/test_crosshits_generator.py::test_header_injected_after_title -v`
Expected: FAIL — `TypeError: generate() got an unexpected keyword argument 'header'`.

- [ ] **Step 3: Add the optional header parameter**

In `app/output/crosshits_generator.py` `generate`-Signatur (Zeile 16-24) ergänzen:

```python
def generate(
    records: list[ScreenerRecord],
    run_record: RunRecord,
    output_dir: Path,
    *,
    score_threshold: float = 4.0,
    min_dimensions: int = 2,
    cap: int = 50,
    header: str | None = None,
) -> Path:
```

`_build_body`-Aufruf (Zeile 34) ersetzen:

```python
    body = _build_body(crosshits, run_month, score_threshold, min_dimensions, header)
```

`_build_body`-Signatur + Kopf (Zeile 62-73) ersetzen:

```python
def _build_body(
    crosshits: list[dict],
    run_month: str,
    score_threshold: float,
    min_dimensions: int,
    header: str | None = None,
) -> str:
    lines = [f"# Universum {run_month} — Crosshits", ""]
    if header:
        lines += [header, ""]
    lines += [
        f"*Schwelle: Score ≥{score_threshold} in ≥{min_dimensions} Dimensionen*",
        "",
    ]
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `uv run python -m pytest tests/output/test_crosshits_generator.py -v`
Expected: PASS — der neue Test grün, bestehende unverändert (header=None → Output wie zuvor).

- [ ] **Step 5: Commit**

```bash
git add app/output/crosshits_generator.py tests/output/test_crosshits_generator.py
git commit -m "Add optional header injection to crosshits generator"
```

---

## Task 9: Verdrahtung in Runner + Dry-Run + Provenienz-Loader

**Files:**
- Modify: `app/screener/runner.py:122-189`
- Modify: `app/main.py:43-79`
- Test: `tests/screener/test_runner.py`

- [ ] **Step 1: Write the failing test**

In `tests/screener/test_runner.py` ergänzen. Nutze den **vorhandenen** Helper `_full_mock_suite()` (Zeile 469 — gibt `(yfinance, edgar, gemini, tracker)` als MagicMocks zurück, `tracker.finish()` → `RunRecord(run_id="2026-05-13T...")`):

```python
def test_run_screener_writes_funnel_artifacts(tmp_path):
    from app.screener.runner import run_screener
    yfinance, edgar, gemini, tracker = _full_mock_suite()

    _, _, paths = run_screener(
        tickers=["AAPL"],
        yfinance=yfinance,
        edgar=edgar,
        gemini=gemini,
        run_tracker=tracker,
        output_dir=tmp_path,
    )

    names = {p.name for p in paths}
    assert "2026-05-funnel_summary.json" in names
    assert "2026-05-dropouts.csv" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/screener/test_runner.py::test_run_screener_writes_funnel_artifacts -v`
Expected: FAIL — keine funnel-Dateien in den Pfaden.

- [ ] **Step 3: Add provenance loader + wire run_screener**

In `app/screener/runner.py` Imports ergänzen (oben):

```python
import json
from datetime import datetime, timezone
```

Helper nach den Imports einfügen:

```python
def _load_provenance() -> dict | None:
    path = Path(__file__).parent.parent.parent / "data" / "universe_provenance.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("provenance: could not read %s", path)
        return None
```

`run_screener` (Zeile 177-189) ersetzen:

```python
    from app.output.funnel_artifacts import write_funnel_artifacts
    from app.output.report_header import render_header
    from app.screener.funnel import build_funnel

    basis = run_basis_filter(tickers, yfinance)
    edgar_passed = run_edgar_filter(basis.passed, edgar)
    scored = run_gemini_scoring(edgar_passed, gemini, run_tracker)
    run_record = run_tracker.finish()
    run_month = run_record.run_id[:7]

    summary, dropouts = build_funnel(
        universe=tickers, basis=basis, scored=scored,
        score_threshold=threshold, crosshits_min_dimensions=min_dims,
        provenance=_load_provenance(),
    )
    funnel_paths = write_funnel_artifacts(summary, dropouts, output_dir, run_month)
    header = render_header(summary, run_month)

    paths = [
        generate_dimensions(scored, run_record, output_dir, score_threshold=threshold, cap=cap),
        generate_crosshits(scored, run_record, output_dir, score_threshold=threshold,
                           min_dimensions=min_dims, cap=cap, header=header),
        generate_changes(scored, run_record, output_dir, score_threshold=threshold, cap=cap),
        *funnel_paths,
    ]

    logger.info("run_screener: complete — %d records, %d output files", len(scored), len(paths))
    return scored, run_record, paths
```

- [ ] **Step 4: Wire dry-run preview to also emit funnel artifacts**

`run_filter_preview` (Zeile 133-152) Signatur + Körper ersetzen:

```python
def run_filter_preview(
    tickers: list[str],
    yfinance: YFinanceClient,
    edgar: EdgarClient,
    *,
    output_dir: Path | None = None,
    run_month: str | None = None,
) -> FilterReport:
    """Free ($0) filters-only preview: basis + EDGAR filters, no Gemini, no
    run-tracker. Emits funnel artifacts (stages through EDGAR) when output_dir
    is given — for cold-run visibility."""
    basis = run_basis_filter(tickers, yfinance)
    records = basis.passed
    _evaluate_edgar(records, edgar)
    apply_edgar_filters(records)
    report = build_filter_report(records, edgar)
    report.yfinance_unresolved = basis.unresolved
    report.log(logger)
    logger.info(
        "filter_preview: %d gc-drops, %d skipped",
        len(report.going_concern_drops),
        report.total_skipped(),
    )
    if output_dir is not None:
        from app.output.funnel_artifacts import write_funnel_artifacts
        from app.screener.funnel import build_funnel
        month = run_month or datetime.now(timezone.utc).strftime("%Y-%m")
        summary, dropouts = build_funnel(
            universe=tickers, basis=basis, scored=None,
            score_threshold=settings.crosshits_score_threshold,
            crosshits_min_dimensions=settings.crosshits_min_dimensions,
            provenance=_load_provenance(),
        )
        write_funnel_artifacts(summary, dropouts, output_dir, month)
    return report
```

Import von `settings` in `run_filter_preview` sicherstellen: `from app.config import settings` steht bereits lokal in `run_screener`; für `run_filter_preview` denselben lokalen Import am Funktionsanfang ergänzen.

- [ ] **Step 4b: Fix existing tests broken by the signature/path changes**

Zwei Bestandstests in `tests/screener/test_runner.py` brechen durch die additiven Änderungen und müssen mitgezogen werden (Verhalten ist bewusst erweitert, nicht verändert):

1. `test_run_screener_returns_records_run_record_and_paths` (Zeile ~502): `run_screener` gibt jetzt **5** Pfade zurück (3 Markdown + funnel_summary.json + dropouts.csv). Assertion ersetzen:

```python
    assert len(paths) == 5  # 3 markdown + funnel_summary.json + dropouts.csv
```

2. `test_run_filter_preview_has_no_gemini_parameter` (Zeile ~446): `run_filter_preview` hat jetzt zusätzlich `output_dir` + `run_month` (keyword-only). Die Gemini-Invariante bleibt; die exakte Param-Menge anpassen:

```python
    assert "gemini" not in params           # structurally cannot score — unchanged invariant
    assert set(params) == {"tickers", "yfinance", "edgar", "output_dir", "run_month"}
```

- [ ] **Step 5: Pass output_dir from the dry-run endpoint**

In `app/main.py` Dry-Run-Block (Zeile 49-52) ersetzen:

```python
    if dry_run:
        output_dir = Path(settings.output_dir)
        report = run_filter_preview(tickers, yfinance, edgar, output_dir=output_dir)
        logger.info("monthly run: free dry-run (filters only, $0) — funnel artifacts written, no Gemini/GitHub")
        return {"dry_run": True, **report.to_dict()}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run python -m pytest tests/screener/test_runner.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/screener/runner.py app/main.py tests/screener/test_runner.py
git commit -m "Wire funnel build + artifacts into run_screener and dry-run preview"
```

---

## Task 10: `build_universe.py` — STOXX-Provenienz-Sidecar

**Files:**
- Modify: `scripts/build_universe.py:417-464`
- Test: `tests/scripts/test_build_universe_provenance.py` (neu)

- [ ] **Step 1: Write the failing test**

`tests/scripts/test_build_universe_provenance.py` (neu) — testet die reine Tier-Rückgabe ohne Netz, indem die Sub-Fetcher gemockt werden:

```python
from unittest.mock import patch

import scripts.build_universe as bu


def test_fetch_stoxx600_reports_wikipedia_tier():
    with patch.object(bu, "_fetch_stoxx600_wikipedia", return_value=["ASML.AS", "SAP.DE"]):
        tickers, tier = bu.fetch_stoxx600()
    assert tier == "wikipedia"
    assert tickers == ["ASML.AS", "SAP.DE"]


def test_fetch_stoxx600_falls_back_to_hardcoded_tier():
    with patch.object(bu, "_fetch_stoxx600_wikipedia", return_value=[]), \
         patch.object(bu, "_fetch_stoxx600_ishares", return_value=[]):
        tickers, tier = bu.fetch_stoxx600()
    assert tier == "hardcoded-fallback"
    assert tickers == list(bu.STOXX_FALLBACK)
```

> Hinweis: `_fetch_stoxx600_ishares` muss die gegriffene Option (`ishares-b`/`ishares-c`) selbst zurückgeben können — siehe Step 3. Falls die ishares-Funktion separat getestet werden soll, mock ihre internen URL-Fetches; für diesen Plan reicht der Wikipedia/Fallback-Pfad als Tier-Beweis.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/scripts/test_build_universe_provenance.py -v`
Expected: FAIL — `fetch_stoxx600()` gibt aktuell nur `list` zurück (`ValueError: not enough values to unpack`).

- [ ] **Step 3: Make `fetch_stoxx600` return the tier**

In `scripts/build_universe.py` `fetch_stoxx600()` (Zeile 417-441) ersetzen — Rückgabe wird `tuple[list[str], str]`:

```python
def fetch_stoxx600() -> tuple[list[str], str]:
    tickers = _fetch_stoxx600_wikipedia()
    if tickers:
        return tickers, "wikipedia"

    ishares = _fetch_stoxx600_ishares()
    if ishares:
        tickers, label = ishares  # _fetch_stoxx600_ishares returns (tickers, "ishares-b"|"ishares-c")
        return tickers, label

    logger.warning(
        "All STOXX 600 sources failed. Using hardcoded fallback (%d tickers). "
        "Universe will cover only major European components.",
        len(STOXX_FALLBACK),
    )
    return list(STOXX_FALLBACK), "hardcoded-fallback"
```

`_fetch_stoxx600_ishares()` (Zeile 389-414) anpassen, sodass es bei Erfolg `(tickers, label)` zurückgibt, sonst `None`. Die Erfolgs-Rückgabe (innerhalb der Options-Schleife) ersetzen:

```python
        logger.info("STOXX 600 fetched via iShares Option %s: %d tickers", label, len(tickers))
        return tickers, f"ishares-{label.lower()}"
```

und am Funktionsende (alle Optionen fehlgeschlagen):

```python
    return None
```

Den Rückgabetyp der Funktion auf `tuple[list[str], str] | None` setzen.

- [ ] **Step 4: Write the sidecar in `main()`**

`main()` (Zeile 448-464) ersetzen:

```python
def main() -> None:
    sp500 = fetch_sp500()
    sp400 = fetch_sp400()
    stoxx, stoxx_tier = fetch_stoxx600()

    combined = sorted(set(sp500 + sp400 + stoxx))

    logger.info("--- Summary ---")
    logger.info("S&P 500:      %d tickers", len(sp500))
    logger.info("S&P 400:      %d tickers", len(sp400))
    logger.info("STOXX 600:    %d tickers (tier=%s)", len(stoxx), stoxx_tier)
    logger.info("Total unique: %d tickers", len(combined))

    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    out_path = data_dir / "universe.json"
    out_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    logger.info("Written to %s", out_path)

    provenance = {
        "stoxx_tier": stoxx_tier,
        "sp500_count": len(sp500),
        "sp400_count": len(sp400),
        "stoxx600_count": len(stoxx),
        "total_unique": len(combined),
    }
    prov_path = data_dir / "universe_provenance.json"
    prov_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    logger.info("Provenance written to %s", prov_path)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/scripts/test_build_universe_provenance.py -v`
Expected: PASS. (Falls `tests/scripts/__init__.py` fehlt und der Import scheitert: leere Datei anlegen.)

- [ ] **Step 6: Commit**

```bash
git add scripts/build_universe.py tests/scripts/test_build_universe_provenance.py
git commit -m "Emit STOXX source tier + per-source counts to universe_provenance.json sidecar"
```

---

## Task 11: Voller Test-Lauf + Coverage-Gate

**Files:** keine Code-Änderung (nur Verifikation).

- [ ] **Step 1: Run the full suite**

Run: `uv run python -m pytest`
Expected: PASS, Coverage ≥ 90 % (zentral in `pyproject.toml` konfiguriert). Falls neue Module unter Threshold: gezielte Tests aus Tasks 4–10 ergänzen (kein Netz).

- [ ] **Step 2: Confirm no logic drift (instrumentation-only invariant)**

Run: `uv run python -m pytest tests/screener/test_filters.py tests/output/test_crosshits_generator.py tests/output/test_dimensions_generator.py -v`
Expected: PASS, unverändert — beweist, dass Gate-/Render-Verhalten gleich blieb.

- [ ] **Step 3: Commit (falls Test-Ergänzungen nötig waren)**

```bash
git add tests/
git commit -m "Top up funnel test coverage to threshold"
```

---

## Acceptance-Gates (nach Code-Tasks, NUR mit Stephans Go)

> Diese Schritte sind **kein** Auto-Run. Erst nach Stephans explizitem Go, sequenziell.

- [ ] **Gate A — $0 Cold-Dry-Run.** Caches purgen (`universe_cache` + `dev_edgar_cache`), dann `POST /run/monthly?dry_run=true`. `funnel_summary.json` + `dropouts.csv` + Review-Flag-Liste an Stephan zeigen. Prüfen: `RESOLUTION_DEGRADED_DICT` ~0 (Cache-Bypass-Verifikation), Stufen-Counts plausibel.
- [ ] **Gate B — Paid-Acceptance-Run** (separates Gate, nach A): voller `run_screener`, Scoring/Crosshit-Stufen ergänzt, Kosten im Auge.
- [ ] **Gate C — Live-`build_universe`-Lauf** (Phase-2-Vorbereitung, optional hier): erzeugt `universe_provenance.json` mit echtem Tier; Rohausgabe inspizieren.

Kein Push/Merge ohne Stephans Go. Phase 2 (`universe_membership.json`, Membership-Severity, Region-Breakdown) ist **nicht** Teil dieses Plans.
