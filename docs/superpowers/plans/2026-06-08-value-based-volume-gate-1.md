# Value-Based Volume Gate (Punkt 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the share-count volume floor (`avg_daily_volume ≥ 100k`) with an EUR daily-trading-value floor (`avg_daily_volume × price_eur ≥ threshold`) so high-priced low-share-count but liquid stocks (Lindt etc.) are no longer wrongly excluded — with London-pence normalization, a NO_PRICE resolution divert, a fail-loud uncalibrated-threshold sentinel, and a calibration gate that sets the threshold on clean numbers.

**Architecture:** (A) minor-unit (GBp→GBP ÷100) normalization at `ScreenerRecord` construction; (B) `fx_rate` carried on the record at resolution; (C) `NO_PRICE` added to 0b's resolution divert; (D) `passes_volume_filter` computes `avg_daily_volume × price × fx_rate`, raises on the sentinel threshold and on missing inputs (invariant violation), never silently drops. The threshold is a fail-loud sentinel until a calibration gate (re-run the value probe on pence-fixed code, enumerate the rescued set, approve the number) replaces it.

**Tech Stack:** Python 3.12, pydantic, pytest (offline DI-mocks). cmd.exe; tests via `uv run python -m pytest`. Spec: `docs/superpowers/specs/2026-06-08-value-based-volume-gate-1-design.md`.

> **Disziplin:** **Erster survivor-ändernder Fix** — Acceptance = „das Richtige hat sich geändert". Strikt das Volumen-Gate; Folge-Gate-Fates (gross_margin/rev_growth) = Punkt 2/3, nicht vermischen. Kalibrierung **nie** auf hand-korrigierten Zahlen (Probe ist Schiedsrichter). Kein Push/Merge ohne Stephans Go. Nach jedem Subagent `git status`/`git log`.

---

## File Structure

**Modifiziert:**
- `app/models/screener_record.py` — `_MINOR_UNIT` map; pence/price normalization + `price or None`; `fx_rate` field.
- `app/screener/runner.py` — set `record.fx_rate` (OK branch); `NO_PRICE` divert.
- `app/screener/filters.py` — `MIN_AVG_DAILY_VALUE_EUR` sentinel; `_avg_daily_value_eur`; raising `passes_volume_filter`.
- `app/errors.py` — (reuse existing `FilterConfigError`; no change unless missing).
- Tests: `tests/models/test_screener_record.py`, `tests/screener/test_runner.py`, `tests/screener/test_filters.py`, `tests/screener/test_funnel.py`, `tests/screener/conftest.py` (new — calibration fixture).
- `scripts/diagnose_value_floor_calibration.py` — re-run at GATE A (already committed; pence-fix flows through `from_yfinance_info`).

---

## Task 0: Consumer audit of price/currency (Step-0, no code)

**Confirms the GBp normalization won't double-apply or break a far reader.**

- [ ] **Step 1: Grep the contracts**

Run: `git -C "D:/programme/fisherscreen" grep -n "\.price\b\|\.currency\b\|GBp\|currentPrice\|regularMarketPrice" -- "app/*.py" "app/**/*.py"`

- [ ] **Step 2: Confirm no existing GBp/pence handling**

For each hit, confirm none already divides price by 100 or special-cases "GBp" (almost certainly none — the bug exists because no one handles GBp). Confirm `price`/`currency` consumers (deepdive, valuation, etc.) will benefit from (not break on) a normalized major-unit price + ISO currency. If any consumer already compensates for pence, STOP and report (else double ÷100). Record the finding.

---

## Task 1: Minor-unit (pence) normalization at construction

**Files:**
- Modify: `app/models/screener_record.py`
- Test: `tests/models/test_screener_record.py`

- [ ] **Step 1: Write the failing test**

In `tests/models/test_screener_record.py` add:

```python
def test_gbp_pence_normalized_to_gbp_major_unit():
    info = {"shortName": "Games Workshop", "currency": "GBp",
            "currentPrice": 18980.0, "marketCap": 6_271_815_680, "averageVolume": 93552}
    r = ScreenerRecord.from_yfinance_info("GAW.L", info)
    assert r.currency == "GBP"            # ISO, not the GBp pseudo-code
    assert r.price == 189.80             # pence -> pounds (/100)
    assert r.market_cap == 6_271_815_680  # marketCap UNCHANGED (was already GBP)


def test_non_minor_unit_currency_untouched():
    info = {"shortName": "X", "currency": "EUR", "currentPrice": 58.44,
            "marketCap": 41_857_323_008, "averageVolume": 7309}
    r = ScreenerRecord.from_yfinance_info("FER.AS", info)
    assert r.currency == "EUR" and r.price == 58.44


def test_price_zero_collapses_to_none():
    info = {"shortName": "X", "currency": "EUR", "currentPrice": 0,
            "regularMarketPrice": 0, "marketCap": 5e9, "averageVolume": 5e5}
    assert ScreenerRecord.from_yfinance_info("Z", info).price is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/models/test_screener_record.py -k "pence or minor_unit or price_zero" -v --no-cov`
Expected: FAIL (price 18980 not 189.80; currency "GBp" not "GBP").

- [ ] **Step 3: Implement**

In `app/models/screener_record.py`, add a module-level constant (after the imports, before the class):

```python
# Minor-unit quote normalization: some exchanges quote price in a minor unit while
# marketCap is in the major unit. London (GBp = pence) is the live case; ZAc (SA cents),
# ILA (Israeli agorot) are the same class — add when a listing actually appears.
_MINOR_UNIT: dict[str, tuple[str, int]] = {"GBp": ("GBP", 100)}
```

Replace the head of `from_yfinance_info` (currency + price extraction + the `return cls(...)` lines for currency/price) so it normalizes BEFORE constructing:

```python
    @classmethod
    def from_yfinance_info(cls, ticker: str, info: dict[str, Any]) -> ScreenerRecord:
        """Create record from yfinance info dict. Gemini scoring fields default to None — set by scorer."""
        currency = info.get("currency")
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        # Normalize minor-unit quotes (e.g. London pence) to the major unit + ISO currency,
        # so price is consistent for every consumer and the FX lookup hits a real ISO code.
        # marketCap is already in the major unit — only price is rescaled.
        minor = _MINOR_UNIT.get(currency or "")
        if minor is not None:
            iso, divisor = minor
            currency = iso
            if price is not None:
                price = price / divisor
        return cls(
            ticker=ticker,
            name=info.get("shortName"),
            currency=currency,
            market_cap=info.get("marketCap") or None,
            avg_daily_volume=info.get("averageVolume") or None,
            price=price or None,
```
Keep the remaining `return cls(...)` fields (bid, ask, gics_sector, …) exactly as they are.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/models/test_screener_record.py -v --no-cov`
Expected: PASS (incl. any existing record tests — the change is additive for non-GBp).

- [ ] **Step 5: Commit**

```
git add app/models/screener_record.py tests/models/test_screener_record.py
git commit -m "Punkt1: normalize minor-unit (GBp pence) price to major unit at construction

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Carry fx_rate on the record at resolution

**Files:**
- Modify: `app/models/screener_record.py`, `app/screener/runner.py`
- Test: `tests/screener/test_runner.py`

- [ ] **Step 1: Write the failing test**

In `tests/screener/test_runner.py` add (reuse the `_CfgYF`/`_info` helpers from the 0b tests):

```python
def test_fx_rate_carried_on_resolved_record():
    infos = {"OK": _info(currency="USD")}
    res = run_basis_filter(["OK"], _CfgYF(infos))
    rec = res.resolved[0]
    assert rec.fx_rate == 1.0   # _CfgYF.get_fx_rate returns 1.0 for non-NOFX
```

(`_CfgYF.get_fx_rate` returns 1.0 except for "NOFX"; ensure the helper exists from Task-0b tests — if not, reuse the configurable fake there.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/screener/test_runner.py::test_fx_rate_carried_on_resolved_record -v --no-cov`
Expected: FAIL (`AttributeError: 'ScreenerRecord' object has no attribute 'fx_rate'`).

- [ ] **Step 3: Implement**

In `app/models/screener_record.py`, in the FX block (next to `market_cap_eur`), add:
```python
    fx_rate: float | None = None  # currency->EUR rate, carried from resolution (Punkt 1: value-gate primitive)
```

In `app/screener/runner.py` `run_basis_filter`, in the `else:` (OK) branch of the divert chain — where the record is appended to `records` — set the rate from the fx_cache before appending:
```python
            else:
                record.fx_rate = fx_cache.get(record.currency)
                records.append(record)
```
(For an OK record, `_resolve_market_cap_eur` has populated `fx_cache[currency]` with the real rate; EUR returns 1.0 via `get_fx_rate`. This is the authoritative carried primitive.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/screener/test_runner.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add app/models/screener_record.py app/screener/runner.py tests/screener/test_runner.py
git commit -m "Punkt1: carry fx_rate primitive on resolved record (value-gate input)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: NO_PRICE resolution divert (0b sibling)

**Files:**
- Modify: `app/screener/runner.py`
- Test: `tests/screener/test_runner.py`

- [ ] **Step 1: Write the failing test**

In `tests/screener/test_runner.py` add:

```python
def test_divert_no_price():
    infos = {
        "NOPX": _info(currentPrice=0, regularMarketPrice=0),  # price 0 -> None
        "NOPX2": _info(currentPrice=None, regularMarketPrice=None),
        "OK": _info(),
    }
    res = run_basis_filter(list(infos), _CfgYF(infos))
    nsd = {r.ticker: r.resolution_detail for r in res.no_symbol_data}
    assert nsd == {"NOPX": "NO_PRICE", "NOPX2": "NO_PRICE"}
    assert "OK" in [r.ticker for r in res.resolved]   # real price -> gated, not diverted


def test_divert_precedence_volume_before_price():
    # missing BOTH vol and price -> NO_VOLUME wins (precedence mc->cur->vol->price)
    infos = {"Z": _info(averageVolume=0, currentPrice=0, regularMarketPrice=0)}
    res = run_basis_filter(["Z"], _CfgYF(infos))
    assert res.no_symbol_data[0].resolution_detail == "NO_VOLUME"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/screener/test_runner.py -k "no_price or precedence" -v --no-cov`
Expected: FAIL (NOPX lands in `resolved` or errors, not `no_symbol_data`).

- [ ] **Step 3a: Keep existing OK-record fakes gateable (price now load-bearing)**

The `NO_PRICE` divert will divert ANY record without a price. The existing test fakes
`_FunnelYF` (its GOOD info dict) and `_info()` base currently have **no** `currentPrice` → their
"OK" records would wrongly divert as NO_PRICE and break existing tests. Add a price to both, in
`tests/screener/test_runner.py`:
- In `_FunnelYF.get_ticker_info`'s returned dict (the GOOD branch), add `"currentPrice": 100.0,`.
- In the `_info()` helper's `base` dict, add `"currentPrice": 100.0,`.

(Real resolvable equities always have a price; the fakes were just incomplete.)

- [ ] **Step 3b: Implement the divert**

In `app/screener/runner.py` `run_basis_filter`, in the divert chain, add a `NO_PRICE` branch AFTER the `avg_daily_volume is None` (NO_VOLUME) branch and BEFORE the `NO_FX` branch:
```python
            elif record.price is None:
                record.resolution_detail = "NO_PRICE"
                no_symbol_data.append(record)
```
(price=0 already collapsed to None in Task 1, so this single `is None` check covers it. Precedence: NO_RAW_MC → NO_CURRENCY → NO_VOLUME → NO_PRICE → NO_FX → else.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/screener/test_runner.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add app/screener/runner.py tests/screener/test_runner.py
git commit -m "Punkt1: NO_PRICE resolution divert (0b sibling; price now load-bearing)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Value-gate with fail-loud sentinel + raising guard

**Files:**
- Modify: `app/screener/filters.py`
- Test: `tests/screener/test_filters.py`, `tests/screener/conftest.py` (new), `tests/screener/test_funnel.py`

- [ ] **Step 1: Add the calibration test fixture (so gate-invoking tests work with the sentinel)**

Create `tests/screener/conftest.py`:
```python
import pytest

import app.screener.filters as filters


@pytest.fixture(autouse=True)
def _calibrated_value_floor(monkeypatch):
    """Gate-invoking tests run with a deterministic value floor; the production
    constant stays a fail-loud sentinel until the calibration gate sets it. A test
    that needs the sentinel sets it back to None explicitly."""
    monkeypatch.setattr(filters, "MIN_AVG_DAILY_VALUE_EUR", 1_000_000.0)
```

- [ ] **Step 2: Write the failing tests**

In `tests/screener/test_filters.py` replace the existing volume-filter tests with value-based ones (and add sentinel/guard tests):
```python
import pytest

import app.screener.filters as filters
from app.errors import FilterConfigError
from app.models.screener_record import ScreenerRecord
from app.screener.filters import passes_volume_filter


def _rec(vol=500_000.0, price=100.0, fx=1.0):
    return ScreenerRecord(ticker="X", avg_daily_volume=vol, price=price, fx_rate=fx)


def test_value_floor_passes_high_value():
    # 500k shares x 100 x 1.0 = 50M >= 1M -> pass
    assert passes_volume_filter(_rec()) is True


def test_value_floor_fails_low_value():
    # 5k shares x 100 x 1.0 = 0.5M < 1M -> fail
    assert passes_volume_filter(_rec(vol=5_000)) is False


def test_lindt_class_few_shares_high_price_passes():
    # 175 shares x 95_600 x 1.07 ~= 17.9M >= 1M -> pass (the whole point)
    assert passes_volume_filter(_rec(vol=175, price=95_600, fx=1.07)) is True


def test_uncalibrated_sentinel_raises(monkeypatch):
    monkeypatch.setattr(filters, "MIN_AVG_DAILY_VALUE_EUR", None)
    with pytest.raises(FilterConfigError, match="not calibrated"):
        passes_volume_filter(_rec())


def test_missing_input_raises_not_silent_drop():
    # An uncomputable value at the gate is an invariant violation (divert should
    # have caught it) -> raise, never silent BENIGN drop.
    with pytest.raises(FilterConfigError, match="value uncomputable"):
        passes_volume_filter(_rec(fx=None))
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run python -m pytest tests/screener/test_filters.py -v --no-cov`
Expected: FAIL (passes_volume_filter still uses share count / MIN_AVG_DAILY_VOLUME).

- [ ] **Step 4: Implement**

In `app/screener/filters.py`:
- Add `from app.errors import FilterConfigError` at the top.
- Replace `MIN_AVG_DAILY_VOLUME: float = 100_000` with:
```python
# Fail-loud sentinel: None until the calibration gate sets the approved EUR value floor.
# A real run with the sentinel RAISES (impossible to ship an uncalibrated guess).
MIN_AVG_DAILY_VALUE_EUR: float | None = None
```
- Replace `passes_volume_filter` with:
```python
def _avg_daily_value_eur(record: ScreenerRecord) -> float | None:
    """Average daily traded value in EUR = shares/day x price x fx. None if any
    input is missing (an invariant violation at the gate — resolution diverts these)."""
    if record.avg_daily_volume is None or record.price is None or record.fx_rate is None:
        return None
    return record.avg_daily_volume * record.price * record.fx_rate


def passes_volume_filter(record: ScreenerRecord) -> bool:
    if MIN_AVG_DAILY_VALUE_EUR is None:
        raise FilterConfigError(
            "MIN_AVG_DAILY_VALUE_EUR not calibrated (sentinel) — run the calibration gate"
        )
    value = _avg_daily_value_eur(record)
    if value is None:
        raise FilterConfigError(
            f"ticker={record.ticker} value uncomputable at volume gate "
            "(invariant violation: vol/price/fx_rate missing — resolution should have diverted)"
        )
    return value >= MIN_AVG_DAILY_VALUE_EUR
```

- [ ] **Step 5: Add the severity-follows-metric test (funnel)**

In `tests/screener/test_funnel.py` add:
```python
def test_large_cap_volume_drop_is_review_regardless_of_metric():
    # _severity(GATE_VOLUME) keys on market_cap_eur, not the gate metric -> a large-cap
    # failing the value floor stays REVIEW (keeps FER/1COV visible, not masked BENIGN).
    from app.screener.funnel import _severity, ReasonCode, SeverityBucket, LARGE_CAP_VOLUME_EUR
    assert _severity(ReasonCode.GATE_VOLUME, market_cap_eur=LARGE_CAP_VOLUME_EUR + 1,
                     sector_wide=False) == SeverityBucket.REVIEW
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run python -m pytest tests/screener/test_filters.py tests/screener/test_funnel.py -v --no-cov`
Expected: PASS. Then run the whole screener suite to catch gate-ripple: `uv run python -m pytest tests/screener/ -v --no-cov` → PASS (the conftest fixture supplies a value floor for run_basis_filter/run_screener tests; records reaching the gate have price+fx_rate from the mocks + Task 2).

> If a run_basis_filter/run_screener test record reaches the gate WITHOUT price or fx_rate (mock lacks currentPrice), the raising guard will surface it — fix that test's mock to include `currentPrice` (real data has it), do NOT weaken the guard.

- [ ] **Step 7: Commit**

```
git add app/screener/filters.py tests/screener/test_filters.py tests/screener/test_funnel.py tests/screener/conftest.py
git commit -m "Punkt1: value-based volume gate with fail-loud sentinel + raising guard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Full suite + no-drift

**Files:** none.

- [ ] **Step 1: Full suite**

Run: `uv run python -m pytest`
Expected: PASS, coverage ≥ 90 %. (Gate-invoking tests use the conftest floor; the prod constant is still the sentinel — correct, uncalibrated.)

- [ ] **Step 2: No-drift on 0a/0b surfaces**

Run: `uv run python -m pytest tests/scripts/ tests/output/ -q --no-cov`
Expected: PASS (Punkt 1 changed resolution/record/filters, not build_universe corrections nor the artifact schema).

- [ ] **Step 3: Commit (only if top-ups needed)**

```
git add tests/
git commit -m "Punkt1: top up coverage"
```

---

## GATE A — Calibration (re-run probe on pence-fixed code → approve threshold) — Stephans Go

> **Kein Code-Task. Erst nach Stephans Go.** Cmd.exe. $0 (warm cache from the last cold-run, OR purge+re-run for a fully clean pass — the probe computes value itself via the now-pence-fixed `from_yfinance_info`).

- [ ] **Step 1 — Re-run the calibration probe (clean, pence-fixed):**
```
uv run python scripts\diagnose_value_floor_calibration.py
```
Now GAW/FLTR/AZN (GBp) show real values (÷100). Bring Stephan: the clean distribution, the 22 REVIEW values, the 5 BENIGN values.

- [ ] **Step 2 — Enumerate the rescued / stay-out set EXACTLY (recount, not assume):**
  - Rescued set is LARGER than the 22 — it includes the wrongly-BENIGN-dropped (VCT/RCO/DIA).
  - Of the 5 GATE_VOLUME-BENIGN: LANV + CTG.L are micro by market_cap (CTG.L value is pence-inflated → real micro) → stay out. ⇒ **3 rescued (VCT/RCO/DIA), DIA threshold-borderline** (in at €1M, out at €2M). NOT "4 of 5".
  - Separate REVIEW / BENIGN / broken cleanly; build the survivor-split prognosis (rescued → which pass follow-on gross_margin/rev_growth) from the clean numbers.

- [ ] **Step 3 — Propose threshold, get Stephan's approval:** liquidity-economics anchor, distribution-validated, **≥ ~€0.9M** (so FER/1COV broken-avgVol stay REVIEW-visible), ~€1M region (lower edge of the natural gap). Record the approved number + the predicted split in `docs/superpowers/audits/2026-06-08-1-value-floor/calibration.md`.

---

## Task 6: Wire the approved threshold

**Files:**
- Modify: `app/screener/filters.py`
- Test: `tests/screener/test_filters.py`

- [ ] **Step 1: Replace the sentinel with the approved number**

In `app/screener/filters.py` set `MIN_AVG_DAILY_VALUE_EUR` to the GATE-A-approved value (from `calibration.md`), e.g.:
```python
MIN_AVG_DAILY_VALUE_EUR: float | None = 1_000_000.0  # GATE-A approved (see audits/.../calibration.md)
```

- [ ] **Step 2: Add a test pinning the production constant is calibrated (not the sentinel)**

In `tests/screener/test_filters.py` add:
```python
def test_production_threshold_is_calibrated():
    # Guards against shipping the sentinel.
    assert filters.MIN_AVG_DAILY_VALUE_EUR is not None
    assert filters.MIN_AVG_DAILY_VALUE_EUR >= 900_000  # >= broken-avgVol floor (FER/1COV stay REVIEW)
```

- [ ] **Step 3: Run tests**

Run: `uv run python -m pytest tests/screener/test_filters.py -v --no-cov` → PASS.

- [ ] **Step 4: Commit**

```
git add app/screener/filters.py tests/screener/test_filters.py
git commit -m "Punkt1: wire GATE-A-approved EUR value floor (replace sentinel)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## GATE B — Acceptance Cold-Dry-Run (bidirectional, survivor-changing) — Stephans Go

> **Kein Code-Task. Erst nach Stephans Go.** Cmd.exe; caches cold.

- [ ] **Step 1 — Purge + local cold dry-run (wie Gate A/0b):**
```
uv run python scripts\purge_ticker_cache_all.py --apply
uv run python scripts\purge_edgar_cache_all.py --apply
```
Server (Terminal A): `uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8080`
Trigger (Terminal B): `uv run python scripts\trigger_cold_dry_run.py http://localhost:8080`

- [ ] **Step 2 — Bidirectional acceptance (Menge + Postcondition, NICHT eine Zahl):**
  - **Survivor STEIGT** (688 → 688+M) — first survivor-changing fix; M = the rescued subset that also passes the follow-on gates, **as predicted at GATE A** (reconcile against the prognosis).
  - **The 22 leave GATE_VOLUME-REVIEW** except the broken-avgVol ones (FER.AS/1COV.DE) which **stay GATE_VOLUME REVIEW** (correct — value floor inherits avgVol; severity keys on market_cap_eur → REVIEW, visible not masked).
  - **No junk slips:** only micro (LANV-class) + broken stay under the floor; verify with `scripts/diagnose_value_floor_calibration.py` / `diagnose_volume_review.py` over the new dropouts.
  - **NO_PRICE diverts** (if any appear) = find, not defect (divert set may grow past 3).
  - **Reconciliation holds**; the value-gate raised nowhere (no invariant violation in the live run).
  - Follow-on fates (gross_margin/rev_growth) of rescued names = Punkt 2/3, **noted not mixed**.

- [ ] **Step 3 — Server stop; report the before/after + the survivor split to Stephan.**

---

## Abschluss

Punkt 1 rehabilitiert echt-liquide hochpreisige Titel + härtet die Daten (pence, NO_PRICE). Danach ist die Tier-A-Sequenz (0a→0b→1) komplett → **gebündelter Remote-PR** {Instrument + 0a + 0b + 1} = ein sauberer Prod-Deploy. Punkt 2/3 (gross_margin sektor-relativ; rev_growth gescort) = Tier B, eigener Spec + Go. Kein Push/Merge ohne Stephans Go.
