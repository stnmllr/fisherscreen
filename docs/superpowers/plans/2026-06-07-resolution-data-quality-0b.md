# Resolution Data-Quality Classification (0b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Symbols that resolve with missing/unusable core data (no/zero market_cap, no currency, no FX rate, no volume) currently leak to the basis gates and are silently masked BENIGN; 0b classifies them **in the resolution, before any gate**, as data-quality REVIEW via a reason-branch — one mechanism, two REVIEW reason codes, zero remaining silent BENIGN paths.

**Architecture:** `_resolve_market_cap_eur` returns `(value, ResolveReason)` instead of bare `None`; `run_basis_filter` branches on the reason (+ raw volume) to divert records into `no_symbol_data` (RESOLUTION_NO_SYMBOL_DATA) or `fx_unavailable` (RESOLUTION_FX_UNAVAILABLE), keeping only gateable records in `resolved`. The funnel adds the two REVIEW codes as resolution-stage dropouts; `basis_gates.entered` stays derived from `resolution.remaining` so reconciliation remains a real check, not a tautology.

**Tech Stack:** Python 3.12, pydantic, dataclasses, pytest (offline DI-mocks). cmd.exe; tests via `uv run python -m pytest`. Spec: `docs/superpowers/specs/2026-06-07-resolution-data-quality-0b-design.md`.

> **Disziplin:** Echte Logik-Änderung (Resolution), aber **survivor-neutral** (verschiebt nur Bucket BENIGN→REVIEW + Gate→Resolution; divertierte Records waren immer Nicht-Survivor). Eigener TDD + Cold-Run-Acceptance. Kein Push/Merge ohne Stephans Go. Nach jedem Subagent `git status`/`git log`. Reconciliation muss weiter aufgehen.

---

## File Structure

**Modifiziert:**
- `app/screener/runner.py` — `ResolveReason` enum; `_resolve_market_cap_eur` → `(value, reason)`; `BasisFilterResult` + `no_symbol_data`/`fx_unavailable`; `run_basis_filter` divert.
- `app/models/screener_record.py` — `resolution_detail: str | None = None` (carries the _resolve-derived sub-reason forward; no downstream re-derivation).
- `app/screener/funnel.py` — `ReasonCode` + 2 codes; `_ALWAYS_REVIEW` + 2; `Dropout` + `detail`; `_make_dropout` + `detail` param; `build_funnel` resolution dropouts + count.
- `app/output/funnel_artifacts.py` — `detail` CSV column (additive, trailing).
- Tests: `tests/screener/test_runner.py`, `tests/screener/test_funnel.py`, `tests/output/test_funnel_artifacts.py`.

---

## Task 0: Blast-radius audit (Step-0, no code change)

**Verifies the two silent contract changes are contained before touching anything.**

- [ ] **Step 1: Re-grep the two contracts**

Run: `git -C "D:/programme/fisherscreen" grep -n "\.resolved\b" -- "*.py"`
Run: `git -C "D:/programme/fisherscreen" grep -n "_resolve_market_cap_eur" -- "*.py"`

- [ ] **Step 2: Confirm the expected (contained) consumer set**

Expected `.resolved` readers — ONLY these; if anything in `app/output/` (dimensions/crosshits/changes), `app/deepdive/`, or scoring appears, STOP and report (it expects the old "all resolved" semantics):
- `app/screener/funnel.py` (3×: `_compute_sector_wide`, `n_resolved`, `basis_drops`)
- `tests/screener/test_runner.py` (1 assertion)

Expected `_resolve_market_cap_eur` callers — ONLY `app/screener/runner.py:92` (the match in `scripts/audit_funnel.py` is a doc comment, not a call). If any other caller exists, STOP and report.

- [ ] **Step 3: Record the finding (no commit)**

State in the task report: "resolved read only by funnel + 1 test; _resolve called only at runner.py:92 → narrowing contained." Proceed only if confirmed.

---

## Task 1: Resolution-layer reason-branch + divert

**Files:**
- Modify: `app/models/screener_record.py`
- Modify: `app/screener/runner.py`
- Test: `tests/screener/test_runner.py`

- [ ] **Step 1: Add `resolution_detail` to the record**

In `app/models/screener_record.py`, in the `# Filter tracking` block (next to `filter_failed_reason`), add:

```python
    resolution_detail: str | None = None  # 0b: sub-reason when diverted (NO_RAW_MC|NO_CURRENCY|NO_VOLUME|NO_FX)
```

- [ ] **Step 2: Write the failing tests**

In `tests/screener/test_runner.py` add (reuse the existing `_FunnelYF`-style pattern; define a configurable fake):

```python
from app.screener.runner import ResolveReason, _resolve_market_cap_eur


class _CfgYF:
    """Configurable per-ticker yfinance fake for 0b divert tests."""
    def __init__(self, infos):
        self._infos = infos
    def get_ticker_info(self, ticker):
        return self._infos[ticker]
    def get_fx_rate(self, currency):
        if currency == "NOFX":
            raise DataSourceError("fx down")
        return 1.0


def _info(**kw):
    base = {"shortName": "X", "quoteType": "EQUITY", "marketCap": 5e9,
            "averageVolume": 5e5, "currency": "EUR", "grossMargins": 0.5,
            "revenueGrowth": 0.1, "sector": "Technology"}
    base.update(kw)
    return base


def test_resolve_reason_branches():
    fx = {}
    # OK
    r = ScreenerRecord.from_yfinance_info("OK", _info())
    assert _resolve_market_cap_eur(r, _CfgYF({}), fx)[1] == ResolveReason.OK
    # NO_RAW_MC (marketCap 0 -> None at construction)
    r = ScreenerRecord.from_yfinance_info("Z", _info(marketCap=0))
    assert _resolve_market_cap_eur(r, _CfgYF({}), fx)[1] == ResolveReason.NO_RAW_MC
    # NO_CURRENCY (mc present, currency missing)
    r = ScreenerRecord.from_yfinance_info("Z", _info(currency=None))
    assert _resolve_market_cap_eur(r, _CfgYF({}), fx)[1] == ResolveReason.NO_CURRENCY
    # NO_FX (mc + currency present, rate fails)
    r = ScreenerRecord.from_yfinance_info("Z", _info(currency="NOFX"))
    assert _resolve_market_cap_eur(r, _CfgYF({}), {})[1] == ResolveReason.NO_FX


def test_resolve_mc_first_precedence():
    # mc missing AND currency missing -> NO_RAW_MC (mc checked first, reproducible)
    r = ScreenerRecord.from_yfinance_info("Z", _info(marketCap=None, currency=None))
    assert _resolve_market_cap_eur(r, _CfgYF({}), {})[1] == ResolveReason.NO_RAW_MC


def test_divert_no_symbol_data_and_fx():
    infos = {
        "OK":  _info(),                         # gateable
        "ATO": _info(marketCap=7.28e8),         # real small-cap -> NOT diverted, gated
        "NOMC": _info(marketCap=0),             # -> NO_SYMBOL_DATA / NO_RAW_MC
        "NOCUR": _info(currency=None),          # -> NO_SYMBOL_DATA / NO_CURRENCY
        "NOVOL": _info(averageVolume=0),        # -> NO_SYMBOL_DATA / NO_VOLUME
        "NOFX": _info(currency="NOFX"),         # -> FX_UNAVAILABLE
    }
    res = run_basis_filter(list(infos), _CfgYF(infos))
    nsd = {r.ticker: r.resolution_detail for r in res.no_symbol_data}
    assert nsd == {"NOMC": "NO_RAW_MC", "NOCUR": "NO_CURRENCY", "NOVOL": "NO_VOLUME"}
    assert [r.ticker for r in res.fx_unavailable] == ["NOFX"]
    # ATO real small-cap is gateable, NOT diverted (anti-over-fire)
    assert "ATO" in [r.ticker for r in res.resolved]
    assert "ATO" not in [r.ticker for r in res.no_symbol_data]
    # OK gateable
    assert "OK" in [r.ticker for r in res.resolved]
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run python -m pytest tests/screener/test_runner.py -k "resolve or divert" -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'ResolveReason'`.

- [ ] **Step 4: Implement ResolveReason + the reason-returning resolver**

In `app/screener/runner.py` add near the top (after imports, before `BasisFilterResult`):

```python
from enum import Enum


class ResolveReason(str, Enum):
    OK = "OK"
    NO_RAW_MC = "NO_RAW_MC"      # raw market_cap missing or 0 (collapsed to None at construction)
    NO_CURRENCY = "NO_CURRENCY"  # market_cap present but currency missing -> uninterpretable
    NO_FX = "NO_FX"             # mc + currency present, FX rate unavailable (infra, systemic)
```

Replace `_resolve_market_cap_eur` (lines 56-73) with the reason-returning version (mc-first precedence, Guardrail 4):

```python
def _resolve_market_cap_eur(
    record: ScreenerRecord,
    yfinance: YFinanceClient,
    fx_cache: dict[str, float],
) -> tuple[float | None, ResolveReason]:
    if record.market_cap is None:
        return None, ResolveReason.NO_RAW_MC
    if record.currency is None:
        return None, ResolveReason.NO_CURRENCY
    currency = record.currency
    if currency not in fx_cache:
        try:
            fx_cache[currency] = yfinance.get_fx_rate(currency)
        except DataSourceError:
            logger.warning("ticker=%s FX rate unavailable for currency=%s", record.ticker, currency)
            fx_cache[currency] = None  # type: ignore[assignment]
    rate = fx_cache[currency]
    if rate is None:
        return None, ResolveReason.NO_FX
    return record.market_cap * rate, ResolveReason.OK
```

- [ ] **Step 5: Extend BasisFilterResult + wire the divert**

Replace the `BasisFilterResult` dataclass body (add two fields; update docstring):

```python
@dataclass
class BasisFilterResult:
    """Result of the basis filter stage.

    `passed` survived the basis filters. `resolved` are the **gateable** records
    (constructed AND with usable core data); diverted data-quality records are NOT
    here. `unresolved`/`degraded` failed yfinance resolution. `no_symbol_data` and
    `fx_unavailable` are records diverted in resolution (0b) before any gate.
    """

    passed: list[ScreenerRecord] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    resolved: list[ScreenerRecord] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    no_symbol_data: list[ScreenerRecord] = field(default_factory=list)
    fx_unavailable: list[ScreenerRecord] = field(default_factory=list)
```

In `run_basis_filter`, add the two divert lists at the top of the function (next to `records`/`unresolved`/`degraded`):

```python
    no_symbol_data: list[ScreenerRecord] = []
    fx_unavailable: list[ScreenerRecord] = []
```

Replace the resolve+append block inside the loop (currently lines 90-93: build record, set market_cap_eur, append) with:

```python
            info = yfinance.get_ticker_info(ticker)
            record = ScreenerRecord.from_yfinance_info(ticker, info)
            record.market_cap_eur, reason = _resolve_market_cap_eur(record, yfinance, fx_cache)
            # 0b: divert unusable-data records out of the gate path (symbol-data first,
            # then FX). 0 already collapsed to None at construction (or None pattern).
            if reason == ResolveReason.NO_RAW_MC:
                record.resolution_detail = "NO_RAW_MC"
                no_symbol_data.append(record)
            elif reason == ResolveReason.NO_CURRENCY:
                record.resolution_detail = "NO_CURRENCY"
                no_symbol_data.append(record)
            elif record.avg_daily_volume is None:
                record.resolution_detail = "NO_VOLUME"
                no_symbol_data.append(record)
            elif reason == ResolveReason.NO_FX:
                record.resolution_detail = "NO_FX"
                fx_unavailable.append(record)
            else:
                records.append(record)
```

Update the `return BasisFilterResult(...)` to include the new lists:

```python
    if no_symbol_data or fx_unavailable:
        logger.warning(
            "resolution data-quality: %d no_symbol_data, %d fx_unavailable (diverted to REVIEW)",
            len(no_symbol_data), len(fx_unavailable),
        )

    return BasisFilterResult(
        passed=apply_basis_filters(records),
        unresolved=unresolved,
        resolved=records,
        degraded=sorted(degraded),
        no_symbol_data=no_symbol_data,
        fx_unavailable=fx_unavailable,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run python -m pytest tests/screener/test_runner.py -v --no-cov`
Expected: PASS (new + existing; the existing `test_basis_result_splits_degraded_from_unresolved` still holds — its GOOD ticker has full data → gateable).

- [ ] **Step 7: Commit**

```
git add app/models/screener_record.py app/screener/runner.py tests/screener/test_runner.py
git commit -m "0b: reason-branch resolver + divert no_symbol_data/fx_unavailable in resolution

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Funnel — two REVIEW codes, detail field, resolution dropouts

**Files:**
- Modify: `app/screener/funnel.py`
- Test: `tests/screener/test_funnel.py`

- [ ] **Step 1: Write the failing tests**

In `tests/screener/test_funnel.py` add (reuse existing `_resolved` helper + `BasisFilterResult`):

```python
from app.screener.funnel import ReasonCode, SeverityBucket, _severity


def test_resolution_data_quality_codes_always_review():
    # mc=None must not trip is_large_cap / tripwire — severity path is None-safe.
    for rc in (ReasonCode.RESOLUTION_NO_SYMBOL_DATA, ReasonCode.RESOLUTION_FX_UNAVAILABLE):
        assert _severity(rc, market_cap_eur=None, sector_wide=False) == SeverityBucket.REVIEW


def _dq_record(ticker, detail):
    r = ScreenerRecord(ticker=ticker, gics_sector="Technology", market_cap_eur=None)
    r.resolution_detail = detail
    return r


def test_funnel_diverts_count_as_resolution_review_and_reconcile():
    vol = _resolved("VOL", basis_reason="avg_volume")   # a real basis drop
    ok = _resolved("OK")                                  # basis-passed
    nsd = _dq_record("NSD", "NO_RAW_MC")
    fxu = _dq_record("FXU", "NO_FX")
    basis = BasisFilterResult(passed=[ok], unresolved=[], resolved=[vol, ok],
                              degraded=[], no_symbol_data=[nsd], fx_unavailable=[fxu])
    summary, dropouts = build_funnel(universe=["VOL", "OK", "NSD", "FXU"], basis=basis,
                                     scored=None, score_threshold=4.0, crosshits_min_dimensions=2)
    by = {d.ticker: d for d in dropouts}
    assert by["NSD"].reason_code == ReasonCode.RESOLUTION_NO_SYMBOL_DATA
    assert by["NSD"].severity_bucket == SeverityBucket.REVIEW
    assert by["NSD"].detail == "NO_RAW_MC"
    assert by["FXU"].reason_code == ReasonCode.RESOLUTION_FX_UNAVAILABLE
    # Guardrail 1: basis_gates.entered derived from resolution.remaining (not independent)
    assert summary.stage(Stage.BASIS_GATES).entered == summary.stage(Stage.RESOLUTION).remaining
    # resolution drops include the diverts
    assert summary.stage(Stage.RESOLUTION).dropped == 2  # NSD + FXU (unresolved empty)
    # reconciliation: universe == all drops + edgar-remaining (dry-run)
    assert len(dropouts) + summary.stage(Stage.EDGAR_GATES).remaining == 4


def test_diverts_do_not_shift_sector_wide():
    # A diverted record in a sector must not change that sector's reached-margin denominator.
    ind = [_resolved(f"I{i}", sector="Industrials", basis_reason="gross_margin") for i in range(6)]
    nsd = _dq_record("NSD", "NO_RAW_MC")
    nsd.gics_sector = "Industrials"
    basis = BasisFilterResult(passed=[], unresolved=[], resolved=ind, degraded=[],
                              no_symbol_data=[nsd], fx_unavailable=[])
    summary, dropouts = build_funnel(universe=[r.ticker for r in ind] + ["NSD"], basis=basis,
                                     scored=None, score_threshold=4.0, crosshits_min_dimensions=2)
    margin = [d for d in dropouts if d.reason_code == ReasonCode.GATE_GROSS_MARGIN]
    assert all(d.sector_wide is True for d in margin)  # 6/6 industrials, unaffected by the divert
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/screener/test_funnel.py -k "resolution or divert or sector_wide" -v --no-cov`
Expected: FAIL — `AttributeError: RESOLUTION_NO_SYMBOL_DATA` (not in ReasonCode yet).

- [ ] **Step 3: Add the codes + detail + resolution dropouts**

In `app/screener/funnel.py`:

Add to `ReasonCode` (after `RESOLUTION_UNRESOLVED`):

```python
    RESOLUTION_NO_SYMBOL_DATA = "RESOLUTION_NO_SYMBOL_DATA"
    RESOLUTION_FX_UNAVAILABLE = "RESOLUTION_FX_UNAVAILABLE"
```

Add both to `_ALWAYS_REVIEW`:

```python
_ALWAYS_REVIEW = {
    ReasonCode.RESOLUTION_DEGRADED_DICT,
    ReasonCode.SCORE_NOT_SCORED,
    ReasonCode.RESOLUTION_NO_SYMBOL_DATA,
    ReasonCode.RESOLUTION_FX_UNAVAILABLE,
}
```

Add a `detail` field to `Dropout` (last field, defaulted — keeps existing positional constructors valid):

```python
    detail: str = ""
```

Add a `detail` param to `_make_dropout` and pass it through:

```python
def _make_dropout(record: ScreenerRecord, stage: Stage, reason_code: ReasonCode,
                  sector_wide_sectors: set[str], detail: str = "") -> Dropout:
    sector_wide = (reason_code == ReasonCode.GATE_GROSS_MARGIN
                   and record.gics_sector in sector_wide_sectors)
    severity = _severity(reason_code, market_cap_eur=record.market_cap_eur,
                         sector_wide=sector_wide)
    return Dropout(
        ticker=record.ticker, stage=stage, reason_code=reason_code,
        severity_bucket=severity, is_large_cap=_is_large_cap(record.market_cap_eur),
        sector_wide=sector_wide, market_cap_eur=record.market_cap_eur,
        gics_sector=record.gics_sector, detail=detail,
    )
```

In `build_funnel`, in the `# --- Resolution ---` block, AFTER the existing degraded/unresolved loops and BEFORE `n_resolved = len(basis.resolved)`, add the data-quality diverts (records → `_make_dropout`, exercising the None-safe severity path):

```python
    for r in basis.no_symbol_data:
        dropouts.append(_make_dropout(r, Stage.RESOLUTION, ReasonCode.RESOLUTION_NO_SYMBOL_DATA,
                                      sector_wide_sectors, detail=r.resolution_detail or ""))
    for r in basis.fx_unavailable:
        dropouts.append(_make_dropout(r, Stage.RESOLUTION, ReasonCode.RESOLUTION_FX_UNAVAILABLE,
                                      sector_wide_sectors, detail=r.resolution_detail or ""))
```

Update the RESOLUTION `FunnelStage` (currently `dropped=len(basis.unresolved)`) to include the diverts:

```python
        FunnelStage(Stage.RESOLUTION, n_universe,
                    len(basis.unresolved) + len(basis.no_symbol_data) + len(basis.fx_unavailable),
                    n_resolved),
```

(`n_resolved = len(basis.resolved)` is unchanged; it remains the value fed to BOTH `resolution.remaining` and `basis_gates.entered` — Guardrail 1 holds by construction.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/screener/test_funnel.py -v --no-cov`
Expected: PASS (new + all existing funnel tests).

- [ ] **Step 5: Commit**

```
git add app/screener/funnel.py tests/screener/test_funnel.py
git commit -m "0b: funnel resolution data-quality codes (NO_SYMBOL_DATA, FX_UNAVAILABLE) + detail

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: dropouts.csv `detail` column (additive)

**Files:**
- Modify: `app/output/funnel_artifacts.py`
- Test: `tests/output/test_funnel_artifacts.py`

- [ ] **Step 1: Verify no strict-schema consumer of dropouts.csv**

Run: `git -C "D:/programme/fisherscreen" grep -rn "dropouts.csv\|dropouts\.csv\|DictReader" -- "*.py"`
Expected: consumers use `csv.DictReader` (key-based, tolerant of an added trailing column) or read the JSON summary (not the CSV). If any consumer indexes columns positionally or asserts an exact fieldname set, STOP and report. Record the finding.

- [ ] **Step 2: Write the failing test**

In `tests/output/test_funnel_artifacts.py`, extend the existing `_dropout()` to include the new field and assert the column:

```python
def test_dropouts_csv_has_detail_column(tmp_path):
    from app.screener.funnel import Dropout, Stage, ReasonCode, SeverityBucket
    d = Dropout("NSD", Stage.RESOLUTION, ReasonCode.RESOLUTION_NO_SYMBOL_DATA,
                SeverityBucket.REVIEW, False, False, None, "Technology", detail="NO_RAW_MC")
    paths = write_funnel_artifacts(_summary(), [d], tmp_path, "2026-06")
    import csv as _csv
    rows = list(_csv.DictReader((tmp_path / "Universum" / "2026-06-dropouts.csv").read_text("utf-8").splitlines()))
    assert "detail" in rows[0]
    assert rows[0]["detail"] == "NO_RAW_MC"
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run python -m pytest tests/output/test_funnel_artifacts.py::test_dropouts_csv_has_detail_column -v --no-cov`
Expected: FAIL — `KeyError: 'detail'` (column not written).

- [ ] **Step 4: Add the column**

In `app/output/funnel_artifacts.py`, append `"detail"` to `_CSV_FIELDS` (trailing) and to the `writer.writerow({...})` dict:

```python
_CSV_FIELDS = [
    "ticker", "stage", "reason_code", "severity_bucket",
    "is_large_cap", "sector_wide", "market_cap_eur", "gics_sector", "detail",
]
```
and in the row dict add `"detail": d.detail,`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/output/test_funnel_artifacts.py -v --no-cov`
Expected: PASS (new + existing — the existing test_writes_json_and_csv still passes; its `_dropout()` has detail="" by default).

> If the existing `_dropout()` helper constructs `Dropout(...)` with 8 positional args, it stays valid (detail defaults ""). If it asserts an exact column count, update it to include `detail`.

- [ ] **Step 6: Commit**

```
git add app/output/funnel_artifacts.py tests/output/test_funnel_artifacts.py
git commit -m "0b: add detail column to dropouts.csv (additive, sub-reason for NO_SYMBOL_DATA)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Full suite + no-drift

**Files:** keine Code-Änderung.

- [ ] **Step 1: Full suite**

Run: `uv run python -m pytest`
Expected: PASS, coverage ≥ 90 %.

- [ ] **Step 2: No-drift on the 0a/funnel surfaces**

Run: `uv run python -m pytest tests/scripts/ tests/output/ -q --no-cov`
Expected: PASS — 0b changed resolution + funnel wiring, not build_universe corrections nor the artifact schema beyond the additive column.

- [ ] **Step 3: Commit (only if top-ups were needed)**

```
git add tests/
git commit -m "0b: top up coverage"
```

---

## GATE — Acceptance Cold-Dry-Run (Funnel, $0) — Stephans Go

> **Kein Code-Task. Erst nach Stephans Go.** Cmd.exe; Caches kalt.

- [ ] **Step 1 — Purge + local cold dry-run (wie Gate A/2):**

```
uv run python scripts\purge_ticker_cache_all.py --apply
uv run python scripts\purge_edgar_cache_all.py --apply
```
Server (Terminal A): `uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8080`
Trigger (Terminal B): `uv run python scripts\trigger_cold_dry_run.py http://localhost:8080`

- [ ] **Step 2 — Acceptance = Menge + Postcondition (NICHT eine Zahl):**
  - **Mengen-Prognose:** Divert-Menge (RESOLUTION_NO_SYMBOL_DATA) **⊇ {ML.PA, RNL.PA, GLB.IR}**.
  - **Postcondition:** **null** `basis_gates`-BENIGN-Drops mit `market_cap_eur`=None **oder** `avg_daily_volume`=None verbleiben (prüfbar mit `scripts/diagnose_0a_acceptance.py`-Muster über die neue dropouts.csv).
  - **>3 Diverts = Fund, kein Defekt** (weitere bisher unsichtbare Maskierung; erwartbar ≥3).
  - **RESOLUTION_FX_UNAVAILABLE-Count:** sichtbar machen (0 auf sauberem Lauf erwartet; Nicht-Null = FX-Fix-Trigger, NICHT 0b-Defekt).
  - **Reconciliation hält**; **Survivor-Set unverändert** ggü. 0a-GATE-2 (688) — Divertierte waren immer Nicht-Survivor.

- [ ] **Step 3 — Server stoppen, Funnel-Zahlen an Stephan berichten.**

---

## Abschluss

0b generalisiert den Masking-Bug → null stille BENIGN-Pfade. Danach **Punkt 1** (Volumen-Gate wert- statt stückbasiert). Merge/Push bleibt gebündelt nach Punkt 1 (= ein Prod-Deploy). Kein Push/Merge ohne Stephans Go.
