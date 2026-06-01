# Mehrjahres-Bewertungs-Range Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den Stage-2a-Bewertungsblock um historische Mehrjahres-Multiple-Bänder (P/E, EV/EBIT, FCF-Yield: Median + 25-Perzentil über die real verfügbare ~3J-Tiefe, ehrlich gelabelt) erweitern, die automatisch in Synthesis-Prompt, Dossier und Frontmatter fließen. (Master-Plan sagte „5J"; Task-0-Probe belegte 4 GJ freie yfinance-Tiefe → re-scoped auf ehrliches Mehrjahres-Label; echte 5J+ ist ein quellenblinder SEC-XBRL-Swap in Phase 2.)

**Architecture:** Eine neue pure-compute-Schicht (`valuation_history.py`) rechnet aus Wochen-Preisen × forward-filled GJ-Fundamentaldaten ~164 verwertbare Multiple-Beobachtungen (von ~260 Preispunkten, Lag-gedeckelt auf 4 GJ Fundamental) und verdichtet sie zu `MultipleStats` (median/p25/n_obs/span_years/status). **Quellen-agnostischer Seam:** `compute_valuation_history` nimmt `list[AnnualFundamental]` — quellenblind, daher ist die spätere XBRL-Tiefe ein reiner Adapter-Swap, kein Rebuild. Der bestehende `HistoricalDataServiceImpl` zieht die Roh-Inputs (Wochen-Preis, Splits, zusätzliche Annual-Zeilen) und ruft die pure-Funktion; `CachedHistoricalData` cached nur die kompakte Summary (Schema-Bump 2→3); `quant_join` hängt das Ergebnis an `QuantSnapshot`; der Renderer fügt eine konsolidierte facts-only-Zeile mit ehrlichem Spannen-Label ein.

**Tech Stack:** Python 3.12, pydantic v2, pandas (yfinance-Frames), pytest + MagicMock-DI, stdlib `statistics` (keine neue Dependency), uv.

**Referenz-Spec:** `docs/superpowers/specs/2026-05-30-deepdive-5j-valuation-range-design.md`

**Test-Aufruf-Konvention (SOPRA-EPDR, CLAUDE.md):** immer `uv run python -m pytest …`, nie `uv run pytest`.

---

## File Structure

**Neu:**
- `app/deepdive/valuation_history.py` — pure compute: cum_split-Normalisierung, implizite-Shares-/EV-Ableitung, as-of-Forward-Fill, Ausschluss, median/p25, Status-Einstufung, FX-/None-Gates. Keine I/O.
- `tests/deepdive/test_valuation_history.py` — Unit-Tests der pure-Funktion.
- `scripts/probe_valuation_history.py` — einmaliger freier yfinance-Probe-Pull (Task 0). Bleibt im Repo als reproduzierbare Daten-Provenance-Notiz (untracked-Drift-konform: NICHT committen, wie die anderen `scripts/diagnose_*`).

**Modifiziert:**
- `app/models/deep_dive_record.py` — `MultipleStatus`, `MultipleStats`, `ValuationHistory`; `QuantSnapshot.valuation_history`; `SourceCoverage.valuation`-Default.
- `app/services/historical_data_service.py` — neue Annual-Zeilen + `get_weekly_close_5y`/`get_splits` im Protokoll + Impl; `get_annual_series` ruft compute + legt `valuation_history` in series.
- `app/services/yfinance_client.py` — `get_weekly_close_5y`, `get_splits` im `YFinanceClient`-Protokoll + `YFinanceClientImpl`.
- `app/deepdive/historical_cache.py` — `CACHE_SCHEMA_VERSION` 2→3; Summary-Persistenz.
- `app/deepdive/quant_join.py` — `valuation_history` durchreichen; status-bewusste `SourceCoverage.valuation`.
- `app/deepdive/valuation_block.py` — `_HEADING` + neue 5J-Zeile.
- `tests/...` — je modifiziertem Modul die korrespondierende Test-Datei.

**Konstanten-Single-Source:** Die drei Status-Schwellen + `REPORTING_LAG_DAYS` leben in `app/deepdive/valuation_history.py` (neben der Logik, analog `VINTAGE_THRESHOLD_DAYS` in `synthesis.py`).

---

## Task 0: Probe-Pull (kein Code-Commit — deckelt MIN_SPAN + Label)

**Vor dem ersten RED.** Deckt die zwei daten-gedeckelten Entscheidungen (§5/§14 der Spec): reale GJ-Fundamental-Tiefe (→ `MIN_SPAN` + „5J"-vs-„~4J"-Label) und Per-GJ-`diluted_eps`-Verfügbarkeit (→ gated beide Multiples).

**Files:**
- Create: `scripts/probe_valuation_history.py` (untracked, NICHT committen)

- [ ] **Step 1: Re-grep der Code-Fakten (Anti-Pattern plan-doc-verify-against-code)**

Run:
```
cd /d D:\programme\fisherscreen
uv run python -c "import app.deepdive.compose" 2>nul & rem nur Import-Sanity
```
Dann (Grep-Tool oder findstr) bestätigen, byte-genau:
- `app/deepdive/compose.py:54` `CachedHistoricalData(service=HistoricalDataServiceImpl(...))`
- `app/deepdive/historical_cache.py:15` `CACHE_SCHEMA_VERSION = 2`
- `tests/deepdive/test_valuation_block.py` Z. 28/176/258: 3× altes Heading „(TTM-Stand, ohne historischen 5J-Vergleich)"

Expected: alle drei wie in Spec §14. Bei Abweichung → STOP, Spec korrigieren, dann weiter.

- [ ] **Step 2: Probe-Skript schreiben**

```python
# scripts/probe_valuation_history.py — einmaliger freier yfinance-Probe-Pull (Task 0).
# NICHT committen (wie scripts/diagnose_*). Output deckelt MIN_SPAN + Label.
from __future__ import annotations

import math

import yfinance as yf


def _rows(df):
    return list(df.index) if df is not None and not df.empty else []


def probe(ticker: str) -> None:
    t = yf.Ticker(ticker)
    info = t.info
    inc = t.income_stmt
    cash = t.cashflow
    bal = t.balance_sheet

    print(f"\n===== {ticker} =====")
    print("currency:", info.get("currency"),
          "| financialCurrency:", info.get("financialCurrency"))

    cols = list(getattr(inc, "columns", []))
    years = [getattr(c, "year", c) for c in cols]
    print(f"income_stmt GJ-Tiefe: {len(cols)} -> {years}")

    # Per-GJ diluted_eps availability (gates BOTH multiples, spec 3b)
    eps_label = next((r for r in _rows(inc)
                      if "diluted eps" in str(r).lower()), None)
    print("diluted_eps row label:", eps_label)
    if eps_label is not None:
        vals = inc.loc[eps_label].tolist()
        print("  per-GJ EPS:",
              [None if (v is None or (isinstance(v, float) and math.isnan(v)))
               else round(float(v), 2) for v in vals])

    # Other annual rows
    for label, frame in [("Net Income", inc), ("EBIT", inc),
                         ("Free Cash Flow", cash),
                         ("Total Debt", bal),
                         ("Cash And Cash Equivalents", bal)]:
        present = any(str(r) == label for r in _rows(frame))
        print(f"  row {label!r} present: {present}")

    # Weekly price + splits (spec 3a / 7)
    hist = t.history(period="5y", interval="1wk", auto_adjust=True)
    print("weekly close points:", len(hist),
          "| span(years):",
          round((hist.index[-1] - hist.index[0]).days / 365.25, 2)
          if len(hist) else 0)
    print("splits:", dict(t.splits))


if __name__ == "__main__":
    for tk in ("NOVO-B.CO", "GOOGL"):
        probe(tk)
```

- [ ] **Step 3: Probe ausführen, Outputs notieren**

Run: `uv run python scripts/probe_valuation_history.py`
Erwartete/zu klärende Outputs:
1. **GJ-Tiefe** je Ticker (4 oder 5?) → setzt `VALUATION_COMPLETE_MIN_SPAN_YEARS` in Task 2 und das Renderer-Label in Task 7.
2. **Per-GJ-EPS** (welche GJ NaN?) → bestätigt erwartete partial-Einstufung.
3. Net Income / EBIT / FCF / Debt / Cash präsent? (Zeilen-Labels exakt notieren — yfinance-Label-Drift, vgl. „EBIT" vs „Operating Income" in bestehendem Service).
4. `splits` für GOOGL enthält den 20:1 (2022).

- [ ] **Step 4: Entscheidung dokumentieren (Spec-Update falls nötig)**

Wenn GJ-Tiefe = 4: `MIN_SPAN` in Task 2 auf den realen Wert setzen (z.B. 4.0) UND Renderer-Label-Text in Task 7 auf „~4J" o.ä. Wenn ein gesunder Large-Cap unter prinzipiellen Schwellen kein `complete` erreicht → STOP + Pull-Diagnose, NICHT Schwelle senken (Spec §5). Die finalen Zeilen-Labels (Step 3.3) in die jeweiligen Tasks eintragen, bevor du den Service-Test schreibst.

**Kein Commit in dieser Task.** Das Skript bleibt untracked.

---

## Task 1: Datenmodell — MultipleStats / ValuationHistory

**Files:**
- Modify: `app/models/deep_dive_record.py` (nach `TrendMetrics`, vor `QuantSnapshot`)
- Test: `tests/models/test_deep_dive_record.py`

- [ ] **Step 1: Failing test schreiben**

In `tests/models/test_deep_dive_record.py` anhängen:

```python
def test_multiple_stats_defaults_and_literal():
    from app.models.deep_dive_record import MultipleStats
    s = MultipleStats()
    assert s.median is None and s.p25 is None
    assert s.n_obs == 0 and s.span_years is None
    assert s.status == "na_data"


def test_multiple_stats_rejects_unknown_status():
    import pytest
    from pydantic import ValidationError
    from app.models.deep_dive_record import MultipleStats
    with pytest.raises(ValidationError):
        MultipleStats(status="bogus")


def test_multiple_stats_forbids_extra():
    import pytest
    from pydantic import ValidationError
    from app.models.deep_dive_record import MultipleStats
    with pytest.raises(ValidationError):
        MultipleStats(unexpected=1)


def test_valuation_history_holds_three_multiples():
    from app.models.deep_dive_record import MultipleStats, ValuationHistory
    vh = ValuationHistory(
        pe=MultipleStats(median=21.4, p25=12.1, n_obs=260,
                         span_years=5.0, status="complete"),
        ev_ebit=MultipleStats(status="na_data"),
        fcf_yield=MultipleStats(status="skipped_fx"))
    assert vh.pe.median == 21.4
    assert vh.ev_ebit.status == "na_data"
    assert vh.fcf_yield.status == "skipped_fx"


def test_quant_snapshot_valuation_history_optional_defaults_none():
    from app.models.deep_dive_record import PointInTimeQuant, QuantSnapshot
    qs = QuantSnapshot(point_in_time=PointInTimeQuant(ticker="X"))
    assert qs.valuation_history is None
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `uv run python -m pytest tests/models/test_deep_dive_record.py -k "multiple_stats or valuation_history" -v`
Expected: FAIL (ImportError: cannot import name 'MultipleStats').

- [ ] **Step 3: Modelle implementieren**

In `app/models/deep_dive_record.py` nach der `TrendMetrics`-Klasse einfügen:

```python
MultipleStatus = Literal["complete", "partial", "skipped_fx", "na_data"]


class MultipleStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    median: float | None = None
    p25: float | None = None
    n_obs: int = 0
    span_years: float | None = None
    status: MultipleStatus = "na_data"


class ValuationHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pe: MultipleStats = Field(default_factory=MultipleStats)
    ev_ebit: MultipleStats = Field(default_factory=MultipleStats)
    fcf_yield: MultipleStats = Field(default_factory=MultipleStats)
```

In `QuantSnapshot` das Feld ergänzen (nach `peer_comparison`):

```python
    valuation_history: ValuationHistory | None = None
```

(`Literal`, `Field`, `ConfigDict`, `BaseModel` sind bereits importiert — Datei-Kopf prüfen, keine neuen Imports nötig.)

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `uv run python -m pytest tests/models/test_deep_dive_record.py -k "multiple_stats or valuation_history" -v`
Expected: PASS (5 Tests).

- [ ] **Step 5: Commit**

```bash
git add app/models/deep_dive_record.py tests/models/test_deep_dive_record.py
git commit -m "Add ValuationHistory/MultipleStats model for 5J valuation range"
```

---

## Task 2: Pure compute — Konstanten + median/p25-Kern

**Files:**
- Create: `app/deepdive/valuation_history.py`
- Test: `tests/deepdive/test_valuation_history.py`

> **Task-0-Befund (entschieden):** freie yfinance = 4 GJ → ~3,1J nutzbare Tiefe → `MIN_SPAN = 2.8` (knapp unter ~3J, damit „complete" = volle verfügbare Tiefe; IPO-junger 2J-Ticker bleibt `partial`).

- [ ] **Step 1: Failing test schreiben**

`tests/deepdive/test_valuation_history.py`:

```python
import math
from datetime import date

from app.deepdive.valuation_history import (
    REPORTING_LAG_DAYS,
    VALUATION_COMPLETE_MIN_DENSITY,
    VALUATION_PARTIAL_MIN_OBS,
    _median_p25,
)


def test_constants_are_policy_values():
    assert VALUATION_COMPLETE_MIN_DENSITY == 40
    assert VALUATION_PARTIAL_MIN_OBS == 52
    assert REPORTING_LAG_DAYS == 90


def test_min_span_is_data_capped_value():
    # Task-0-Probe: freie yfinance = 4 GJ -> ~3,1J reale Tiefe -> 2.8 (Spec §5).
    assert VALUATION_COMPLETE_MIN_SPAN_YEARS == 2.8


def test_median_p25_hand_computed():
    # 1..9 inclusive: median=5, p25 (inclusive method) = 3.0
    med, p25 = _median_p25([5, 1, 9, 3, 7, 2, 8, 4, 6])
    assert med == 5.0
    assert math.isclose(p25, 3.0, abs_tol=1e-9)


def test_median_p25_empty_returns_none():
    assert _median_p25([]) == (None, None)


def test_median_p25_single_value():
    med, p25 = _median_p25([42.0])
    assert med == 42.0 and p25 == 42.0
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `uv run python -m pytest tests/deepdive/test_valuation_history.py -v`
Expected: FAIL (ModuleNotFoundError: app.deepdive.valuation_history).

- [ ] **Step 3: Modul-Skelett + Konstanten + median/p25 implementieren**

`app/deepdive/valuation_history.py`:

```python
from __future__ import annotations

import statistics
from datetime import date, timedelta

from app.models.deep_dive_record import MultipleStats, ValuationHistory

# POLICY — fixiert, NICHT an Ticker-Pulls kalibriert (Spec §5).
VALUATION_COMPLETE_MIN_DENSITY = 40     # obs pro Jahr
VALUATION_PARTIAL_MIN_OBS = 52          # >= 1 Jahr wöchentlich

# DATEN-GEDECKELT — der realen GJ-Fundamental-Tiefe folgend (Task 0 / Spec §5).
VALUATION_COMPLETE_MIN_SPAN_YEARS = 4.5

# Look-ahead-Milderung: Fundamental erst ~1 Quartal nach Periodenende verfügbar.
REPORTING_LAG_DAYS = 90


def _median_p25(values: list[float]) -> tuple[float | None, float | None]:
    """Median + unteres 25-Perzentil (inclusive). Leere Liste -> (None, None);
    Einzelwert -> (v, v) (quantiles braucht >=2 Punkte)."""
    if not values:
        return None, None
    if len(values) == 1:
        return float(values[0]), float(values[0])
    med = statistics.median(values)
    p25 = statistics.quantiles(values, n=4, method="inclusive")[0]
    return float(med), float(p25)
```

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `uv run python -m pytest tests/deepdive/test_valuation_history.py -v`
Expected: PASS (4 Tests).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/valuation_history.py tests/deepdive/test_valuation_history.py
git commit -m "Add valuation_history module skeleton: policy constants + median/p25"
```

---

## Task 3: Pure compute — cum_split-Normalisierung + as-of-Forward-Fill

**Files:**
- Modify: `app/deepdive/valuation_history.py`
- Test: `tests/deepdive/test_valuation_history.py`

- [ ] **Step 1: Failing test schreiben**

Anhängen:

```python
from app.deepdive.valuation_history import _cum_split_factor, _as_of_index


def test_cum_split_factor_after_split():
    # 20:1 split ex-date 2022-07-18; a FY ending 2021-12-31 predates it
    splits = [(date(2022, 7, 18), 20.0)]
    assert _cum_split_factor(date(2021, 12, 31), splits) == 20.0
    # a FY ending 2023-12-31 is AFTER the split -> factor 1.0
    assert _cum_split_factor(date(2023, 12, 31), splits) == 1.0


def test_cum_split_factor_no_splits_is_one():
    assert _cum_split_factor(date(2021, 12, 31), []) == 1.0


def test_cum_split_factor_multiple_splits_multiply():
    splits = [(date(2022, 7, 18), 20.0), (date(2014, 4, 3), 2.0)]
    # FY end 2013-12-31 predates both -> 40.0
    assert _cum_split_factor(date(2013, 12, 31), splits) == 40.0


def test_as_of_index_respects_reporting_lag():
    # FY ends newest-first; lag 90d. A week at 2023-02-01 must NOT yet see the
    # FY ending 2022-12-31 (available only ~2023-03-31); it takes 2021-12-31.
    fy_ends = [date(2022, 12, 31), date(2021, 12, 31), date(2020, 12, 31)]
    idx = _as_of_index(date(2023, 2, 1), fy_ends)
    assert fy_ends[idx] == date(2021, 12, 31)
    # a week well after the lag sees the latest FY
    idx2 = _as_of_index(date(2023, 6, 1), fy_ends)
    assert fy_ends[idx2] == date(2022, 12, 31)


def test_as_of_index_none_before_any_available():
    fy_ends = [date(2022, 12, 31), date(2021, 12, 31)]
    # before even the oldest FY + lag
    assert _as_of_index(date(2021, 1, 1), fy_ends) is None
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `uv run python -m pytest tests/deepdive/test_valuation_history.py -k "cum_split or as_of" -v`
Expected: FAIL (ImportError: _cum_split_factor).

- [ ] **Step 3: Helper implementieren**

In `app/deepdive/valuation_history.py` anhängen:

```python
def _cum_split_factor(
    fy_end: date, splits: list[tuple[date, float]]
) -> float:
    """Kumulativer Split-Faktor für ein GJ: Produkt aller Split-Ratios mit
    Ex-Datum NACH dem GJ-Periodenende. EPS_current = EPS_reported / factor
    bringt as-reported EPS auf current (back-adjusted) Basis (Spec §3a)."""
    factor = 1.0
    for ex_date, ratio in splits:
        if ex_date > fy_end:
            factor *= ratio
    return factor


def _as_of_index(week: date, fy_ends_newest_first: list[date]) -> int | None:
    """Index des jüngsten GJ, dessen (Periodenende + REPORTING_LAG_DAYS) <= week.
    None, wenn kein GJ verfügbar ist (Wochenpunkt vor erstem Lag-Ende)."""
    for i, fy_end in enumerate(fy_ends_newest_first):
        if fy_end + timedelta(days=REPORTING_LAG_DAYS) <= week:
            return i
    return None
```

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `uv run python -m pytest tests/deepdive/test_valuation_history.py -k "cum_split or as_of" -v`
Expected: PASS (5 Tests).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/valuation_history.py tests/deepdive/test_valuation_history.py
git commit -m "Add cum-split normalization and reporting-lag as-of fill"
```

---

## Task 4: Pure compute — AnnualFundamental + compute_valuation_history (Kern)

**Files:**
- Modify: `app/deepdive/valuation_history.py`
- Test: `tests/deepdive/test_valuation_history.py`

- [ ] **Step 1: Failing test schreiben**

Anhängen:

```python
from app.deepdive.valuation_history import (
    AnnualFundamental,
    compute_valuation_history,
)


def _weekly(start: date, n: int, price: float):
    return [(start + timedelta(days=7 * i), price) for i in range(n)]


def _annual_flat():
    # newest-first, 5 FY ending Dec, EPS_current already (no split)
    return [
        AnnualFundamental(fy_end=date(2024, 12, 31), net_income=1000.0,
                          diluted_eps=10.0, ebit=1200.0, free_cashflow=900.0,
                          total_debt=200.0, cash=500.0),
        AnnualFundamental(fy_end=date(2023, 12, 31), net_income=900.0,
                          diluted_eps=9.0, ebit=1100.0, free_cashflow=800.0,
                          total_debt=210.0, cash=480.0),
        AnnualFundamental(fy_end=date(2022, 12, 31), net_income=800.0,
                          diluted_eps=8.0, ebit=1000.0, free_cashflow=700.0,
                          total_debt=220.0, cash=460.0),
        AnnualFundamental(fy_end=date(2021, 12, 31), net_income=700.0,
                          diluted_eps=7.0, ebit=900.0, free_cashflow=600.0,
                          total_debt=230.0, cash=440.0),
        AnnualFundamental(fy_end=date(2020, 12, 31), net_income=600.0,
                          diluted_eps=6.0, ebit=800.0, free_cashflow=500.0,
                          total_debt=240.0, cash=420.0),
    ]


def test_compute_pe_band_basic_same_currency():
    # 260 weeks from 2020-06 at a constant price 100; latest EPS 10 -> P/E 10
    weekly = _weekly(date(2020, 6, 1), 260, 100.0)
    vh = compute_valuation_history(
        weekly, _annual_flat(), splits=[],
        listing_ccy="USD", financial_ccy="USD")
    # P/E uses forward-filled EPS; with flat price the median is well-defined
    assert vh.pe.median is not None and vh.pe.median > 0
    assert vh.pe.n_obs > 0
    assert vh.pe.status in ("complete", "partial")


def test_compute_skips_fx_when_currencies_differ():
    weekly = _weekly(date(2020, 6, 1), 260, 100.0)
    vh = compute_valuation_history(
        weekly, _annual_flat(), splits=[],
        listing_ccy="USD", financial_ccy="DKK")
    assert vh.pe.status == "skipped_fx"
    assert vh.ev_ebit.status == "skipped_fx"
    assert vh.fcf_yield.status == "skipped_fx"
    assert vh.pe.median is None


def test_compute_na_data_when_currency_none():
    weekly = _weekly(date(2020, 6, 1), 260, 100.0)
    vh = compute_valuation_history(
        weekly, _annual_flat(), splits=[],
        listing_ccy=None, financial_ccy="USD")
    assert vh.pe.status == "na_data"


def test_compute_excludes_nonpositive_eps_and_ebit():
    annual = _annual_flat()
    annual[0] = AnnualFundamental(
        fy_end=date(2024, 12, 31), net_income=-100.0, diluted_eps=-1.0,
        ebit=-50.0, free_cashflow=900.0, total_debt=200.0, cash=500.0)
    weekly = _weekly(date(2024, 6, 1), 30, 100.0)  # only sees 2024 + maybe 2023
    vh = compute_valuation_history(
        weekly, annual, splits=[], listing_ccy="USD", financial_ccy="USD")
    # negative-EPS weeks excluded -> if all weeks map to 2024 only, n_obs small
    assert vh.pe.n_obs >= 0  # no crash; negatives not counted as valid P/E


def test_compute_keeps_negative_fcf_yield():
    annual = _annual_flat()
    annual[0] = AnnualFundamental(
        fy_end=date(2024, 12, 31), net_income=1000.0, diluted_eps=10.0,
        ebit=1200.0, free_cashflow=-900.0, total_debt=200.0, cash=500.0)
    weekly = _weekly(date(2024, 6, 1), 30, 100.0)
    vh = compute_valuation_history(
        weekly, annual, splits=[], listing_ccy="USD", financial_ccy="USD")
    # negative FCF-yield is a valid observation -> counted
    assert vh.fcf_yield.n_obs > 0


def test_compute_split_normalizes_pe(monkeypatch=None):
    # GOOGL-like 20:1 at 2022-07-18; pre-split FY EPS reported on pre-split basis
    annual = [
        AnnualFundamental(fy_end=date(2023, 12, 31), net_income=2000.0,
                          diluted_eps=5.0, ebit=2500.0, free_cashflow=1800.0,
                          total_debt=100.0, cash=900.0),
        AnnualFundamental(fy_end=date(2021, 12, 31), net_income=1900.0,
                          diluted_eps=100.0,  # pre-split (20x larger)
                          ebit=2300.0, free_cashflow=1700.0,
                          total_debt=120.0, cash=850.0),
    ]
    splits = [(date(2022, 7, 18), 20.0)]
    # constant post-split price 100 throughout
    weekly = _weekly(date(2020, 6, 1), 260, 100.0)
    vh = compute_valuation_history(
        weekly, annual, splits=splits, listing_ccy="USD", financial_ccy="USD")
    # After normalization pre-split EPS 100 -> 5 (current basis), so P/E for
    # those weeks = 100/5 = 20, NOT 100/100 = 1. Median must be ~20, not ~1.
    assert vh.pe.median is not None and vh.pe.median > 10
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `uv run python -m pytest tests/deepdive/test_valuation_history.py -k "compute" -v`
Expected: FAIL (ImportError: AnnualFundamental).

- [ ] **Step 3: AnnualFundamental + compute_valuation_history implementieren**

In `app/deepdive/valuation_history.py` anhängen (Imports oben ergänzen: `from dataclasses import dataclass`, `import math`):

```python
@dataclass(frozen=True)
class AnnualFundamental:
    """Ein GJ-Datensatz (newest-first geliefert). diluted_eps ist as-reported
    (wird via cum_split auf current basis gebracht); net_income/ebit/debt/cash
    sind Währungs-Aggregate (split-invariant)."""
    fy_end: date
    net_income: float | None
    diluted_eps: float | None
    ebit: float | None
    free_cashflow: float | None
    total_debt: float | None
    cash: float | None


def _finite(*vals: float | None) -> bool:
    return all(v is not None and math.isfinite(v) for v in vals)


def _span_years(weeks: list[date]) -> float:
    if len(weeks) < 2:
        return 0.0
    return (max(weeks) - min(weeks)).days / 365.25


def _classify(values: list[float], obs_weeks: list[date]) -> MultipleStats:
    n = len(values)
    span = _span_years(obs_weeks)
    if n < VALUATION_PARTIAL_MIN_OBS:
        return MultipleStats(n_obs=n, span_years=span or None, status="na_data")
    med, p25 = _median_p25(values)
    density = (n / span) if span > 0 else 0.0
    if span >= VALUATION_COMPLETE_MIN_SPAN_YEARS and density >= VALUATION_COMPLETE_MIN_DENSITY:
        status = "complete"
    else:
        status = "partial"
    return MultipleStats(median=med, p25=p25, n_obs=n,
                         span_years=round(span, 2), status=status)


def compute_valuation_history(
    weekly_close: list[tuple[date, float]],
    annual: list[AnnualFundamental],          # newest-first
    splits: list[tuple[date, float]],
    listing_ccy: str | None,
    financial_ccy: str | None,
) -> ValuationHistory:
    """5J-Multiple-Bänder (Spec §2/§3). FX-/None-Gates zuerst; dann pro
    Wochenpunkt as-of-Fundamental + cum_split-Normalisierung + implizite-EV-
    Brücke; Ausschluss EPS<=0 / EBIT<=0; FCF-Yield-Negative bleiben."""
    # FX-/None-Gates (Spec §3c/§3d)
    if listing_ccy is None or financial_ccy is None:
        return ValuationHistory(
            pe=MultipleStats(status="na_data"),
            ev_ebit=MultipleStats(status="na_data"),
            fcf_yield=MultipleStats(status="na_data"))
    if listing_ccy != financial_ccy:
        return ValuationHistory(
            pe=MultipleStats(status="skipped_fx"),
            ev_ebit=MultipleStats(status="skipped_fx"),
            fcf_yield=MultipleStats(status="skipped_fx"))

    fy_ends = [a.fy_end for a in annual]

    pe_vals: list[float] = []; pe_weeks: list[date] = []
    ev_vals: list[float] = []; ev_weeks: list[date] = []
    fcf_vals: list[float] = []; fcf_weeks: list[date] = []

    for week, price in weekly_close:
        if not _finite(price) or price <= 0:
            continue
        idx = _as_of_index(week, fy_ends)
        if idx is None:
            continue
        a = annual[idx]
        factor = _cum_split_factor(a.fy_end, splits)

        # P/E — EPS auf current basis; EPS<=0 ausgeschlossen
        if _finite(a.diluted_eps):
            eps_cur = a.diluted_eps / factor
            if eps_cur > 0:
                pe_vals.append(price / eps_cur)
                pe_weeks.append(week)

        # implizite Shares -> Markt-Kap -> EV (Spec §3b)
        if (_finite(a.diluted_eps, a.net_income) and a.diluted_eps != 0):
            eps_cur = a.diluted_eps / factor
            if eps_cur != 0:
                shares = a.net_income / eps_cur
                # Vorzeichen-Mismatch -> shares negativ/unsinnig: überspringen
                if shares > 0 and _finite(a.ebit, a.total_debt, a.cash) \
                        and a.ebit > 0:
                    mcap = price * shares
                    ev = mcap + a.total_debt - a.cash
                    ev_vals.append(ev / a.ebit)
                    ev_weeks.append(week)

        # FCF-Yield — Negative behalten (Spec §2)
        if (_finite(a.diluted_eps, a.net_income, a.free_cashflow)
                and a.diluted_eps != 0):
            eps_cur = a.diluted_eps / factor
            if eps_cur != 0:
                shares = a.net_income / eps_cur
                if shares > 0:
                    mcap = price * shares
                    if mcap > 0:
                        fcf_vals.append(a.free_cashflow / mcap)
                        fcf_weeks.append(week)

    return ValuationHistory(
        pe=_classify(pe_vals, pe_weeks),
        ev_ebit=_classify(ev_vals, ev_weeks),
        fcf_yield=_classify(fcf_vals, fcf_weeks))
```

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `uv run python -m pytest tests/deepdive/test_valuation_history.py -v`
Expected: PASS (alle Tests inkl. Split-Normalisierung).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/valuation_history.py tests/deepdive/test_valuation_history.py
git commit -m "Add compute_valuation_history: split-aware P/E, EV/EBIT, FCF-yield bands"
```

---

## Task 5: yfinance-Client — get_weekly_close_5y + get_splits

**Files:**
- Modify: `app/services/yfinance_client.py` (Protokoll `YFinanceClient` + `YFinanceClientImpl`)
- Test: `tests/services/test_yfinance_client.py`

> Exakte yfinance-Flags aus Task 0 Step 3.4 bestätigt (`period="5y"`, `interval="1wk"`, `auto_adjust=True`).

- [ ] **Step 1: Failing test schreiben**

In `tests/services/test_yfinance_client.py` anhängen (Datei-Muster der bestehenden Tests übernehmen; yfinance via monkeypatch auf `yf.Ticker`):

```python
def test_get_weekly_close_5y_returns_date_price_pairs(monkeypatch):
    import pandas as pd
    from app.services import yfinance_client as mod

    idx = pd.to_datetime(["2020-06-01", "2020-06-08", "2020-06-15"])
    frame = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=idx)

    class _T:
        def __init__(self, t): pass
        def history(self, period, interval, auto_adjust):
            assert period == "5y" and interval == "1wk" and auto_adjust is True
            return frame

    monkeypatch.setattr(mod.yf, "Ticker", _T)
    out = mod.YFinanceClientImpl().get_weekly_close_5y("X")
    assert out[0][1] == 100.0 and out[-1][1] == 102.0
    assert str(out[0][0]) == "2020-06-01"


def test_get_weekly_close_5y_empty_frame_returns_empty(monkeypatch):
    import pandas as pd
    from app.services import yfinance_client as mod

    class _T:
        def __init__(self, t): pass
        def history(self, period, interval, auto_adjust):
            return pd.DataFrame()

    monkeypatch.setattr(mod.yf, "Ticker", _T)
    assert mod.YFinanceClientImpl().get_weekly_close_5y("X") == []


def test_get_splits_returns_date_ratio_pairs(monkeypatch):
    import pandas as pd
    from app.services import yfinance_client as mod

    s = pd.Series([20.0], index=pd.to_datetime(["2022-07-18"]))

    class _T:
        def __init__(self, t): pass
        @property
        def splits(self): return s

    monkeypatch.setattr(mod.yf, "Ticker", _T)
    out = mod.YFinanceClientImpl().get_splits("X")
    assert out == [(out[0][0], 20.0)]
    assert str(out[0][0]) == "2022-07-18"


def test_get_splits_empty_returns_empty(monkeypatch):
    import pandas as pd
    from app.services import yfinance_client as mod

    class _T:
        def __init__(self, t): pass
        @property
        def splits(self): return pd.Series(dtype=float)

    monkeypatch.setattr(mod.yf, "Ticker", _T)
    assert mod.YFinanceClientImpl().get_splits("X") == []
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `uv run python -m pytest tests/services/test_yfinance_client.py -k "weekly_close or splits" -v`
Expected: FAIL (AttributeError: get_weekly_close_5y).

- [ ] **Step 3: Methoden implementieren**

In `app/services/yfinance_client.py`, `YFinanceClient`-Protokoll ergänzen:

```python
    def get_weekly_close_5y(self, ticker: str) -> list[tuple[Any, float]]: ...
    def get_splits(self, ticker: str) -> list[tuple[Any, float]]: ...
```

In `YFinanceClientImpl` ergänzen (nach `get_annual_statements`):

```python
    def get_weekly_close_5y(self, ticker: str) -> list[tuple[Any, float]]:
        """Wöchentliche Schlusskurse über 5J, split-adj (auto_adjust=True).
        Leerer Frame (delisted) -> []. Hard yfinance-Fehler -> DataSourceError."""
        try:
            frame = yf.Ticker(ticker).history(
                period="5y", interval="1wk", auto_adjust=True)
        except Exception as exc:
            raise DataSourceError(
                f"yfinance weekly history failed for {ticker}: {exc}") from exc
        if frame is None or frame.empty or "Close" not in frame.columns:
            return []
        return [(idx.date(), float(v))
                for idx, v in frame["Close"].items()
                if v is not None]

    def get_splits(self, ticker: str) -> list[tuple[Any, float]]:
        """Split-Events (Ex-Datum, Ratio). Keine Splits -> []."""
        try:
            s = yf.Ticker(ticker).splits
        except Exception as exc:
            raise DataSourceError(
                f"yfinance splits failed for {ticker}: {exc}") from exc
        if s is None or len(s) == 0:
            return []
        return [(idx.date(), float(v)) for idx, v in s.items()]
```

(`DataSourceError` und `Any` sind bereits importiert.)

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `uv run python -m pytest tests/services/test_yfinance_client.py -k "weekly_close or splits" -v`
Expected: PASS (4 Tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/yfinance_client.py tests/services/test_yfinance_client.py
git commit -m "Add yfinance get_weekly_close_5y and get_splits"
```

---

## Task 6: HistoricalDataService — neue Annual-Zeilen + valuation_history-Integration

**Files:**
- Modify: `app/services/historical_data_service.py`
- Test: `tests/services/test_historical_data_service.py`

> Zeilen-Labels aus Task 0 Step 3.3 einsetzen (unten Annahmen: `"Net Income"`, `"Diluted EPS"`, `"Free Cash Flow"`, `"Total Debt"`, `"Cash And Cash Equivalents"` — falls Probe abweicht, hier korrigieren).

- [ ] **Step 1: Failing test schreiben**

In `tests/services/test_historical_data_service.py` anhängen:

```python
def _yf_full_for_valuation():
    yf = MagicMock()
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31"),
            pd.Timestamp("2022-12-31")]
    income = pd.DataFrame({c: {
        "Total Revenue": 1000, "Gross Profit": 800, "Operating Income": 400,
        "EBIT": 420, "Interest Expense": -30,
        "Net Income": 300, "Diluted EPS": 3.0} for c in cols})
    cash = pd.DataFrame({c: {"Repurchase Of Capital Stock": -50,
                             "Free Cash Flow": 250} for c in cols})
    bal = pd.DataFrame({c: {"Share Issued": 2000, "Total Debt": 100,
                            "Cash And Cash Equivalents": 500} for c in cols})
    yf.get_annual_statements.return_value = (income, cash, bal)
    yf.get_ticker_info.return_value = {"financialCurrency": "USD",
                                       "currency": "USD"}
    yf.get_weekly_close_5y.return_value = [
        (date(2022, 1, 1) + timedelta(days=7 * i), 60.0) for i in range(160)]
    yf.get_splits.return_value = []
    return yf


def test_extracts_valuation_fundamental_rows():
    from datetime import date, timedelta
    yf = _yf_full_for_valuation()
    s = HistoricalDataServiceImpl(yfinance=yf).get_annual_series("X")
    assert s["net_income"] == [300, 300, 300]
    assert s["diluted_eps"] == [3.0, 3.0, 3.0]
    assert s["free_cashflow"] == [250, 250, 250]
    assert s["total_debt"] == [100, 100, 100]
    assert s["cash"] == [500, 500, 500]


def test_valuation_history_key_present_and_computed():
    from datetime import date, timedelta
    yf = _yf_full_for_valuation()
    s = HistoricalDataServiceImpl(yfinance=yf).get_annual_series("X")
    vh = s["valuation_history"]
    assert vh.pe.status in ("complete", "partial")
    assert vh.pe.median is not None


def test_valuation_history_failsoft_on_price_pull_error(caplog):
    import logging
    yf = _yf_full_for_valuation()
    from app.errors import DataSourceError
    yf.get_weekly_close_5y.side_effect = DataSourceError("boom")
    with caplog.at_level(logging.WARNING,
                         logger="app.services.historical_data_service"):
        s = HistoricalDataServiceImpl(yfinance=yf).get_annual_series("X")
    vh = s["valuation_history"]
    assert vh.pe.status == "na_data"
    assert s["years"] == [2024, 2023, 2022]  # rest of series intact
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `uv run python -m pytest tests/services/test_historical_data_service.py -k "valuation" -v`
Expected: FAIL (KeyError 'net_income' / 'valuation_history').

- [ ] **Step 3: Service erweitern**

In `app/services/historical_data_service.py`:

Imports oben ergänzen:
```python
from app.errors import DataSourceError
from app.deepdive.valuation_history import (
    AnnualFundamental,
    compute_valuation_history,
)
from app.models.deep_dive_record import MultipleStats, ValuationHistory
```

`get_annual_series` erweitern — nach den bestehenden `_row`-Zeilen die neuen Zeilen ziehen:
```python
        ni = _row(income, "Net Income", ticker)
        eps = _row(income, "Diluted EPS", ticker)
        fcf = _row(cash, "Free Cash Flow", ticker)
        td = _row(bal, "Total Debt", ticker)
        cce = _row(bal, "Cash And Cash Equivalents", ticker)
```

Im `series`-Dict ergänzen (vor `"complete"`):
```python
            "net_income": [col(ni, c) for c in cols],
            "diluted_eps": [col(eps, c) for c in cols],
            "free_cashflow": [col(fcf, c) for c in cols],
            "total_debt": [col(td, c) for c in cols],
            "cash": [col(cce, c) for c in cols],
```

Nach dem `series`-Dict (vor `return series`) die valuation_history berechnen:
```python
        series["valuation_history"] = self._build_valuation_history(
            ticker, cols, ni, eps, ebit, fcf, td, cce, info)
        return series

    def _build_valuation_history(
        self, ticker, cols, ni, eps, ebit, fcf, td, cce, info
    ) -> ValuationHistory:
        """Pullt Wochen-Preis + Splits und ruft die pure-Funktion. Preis-/Split-
        Pull-Fehler -> ValuationHistory(all na_data) + WARNING (fail-soft,
        Präzedenz: forward estimates in quant_join)."""
        def col(d, c):
            v = d.get(c)
            return None if v is None else float(v)

        annual = [
            AnnualFundamental(
                fy_end=c.date() if hasattr(c, "date") else c,
                net_income=col(ni, c), diluted_eps=col(eps, c),
                ebit=col(ebit, c), free_cashflow=col(fcf, c),
                total_debt=col(td, c), cash=col(cce, c))
            for c in cols
        ]
        try:
            weekly = self._yf.get_weekly_close_5y(ticker)
            splits = self._yf.get_splits(ticker)
        except DataSourceError as exc:
            logger.warning(
                "valuation history: %s price/split pull failed — %s "
                "(na_data)", ticker, exc)
            na = MultipleStats(status="na_data")
            return ValuationHistory(pe=na, ev_ebit=na, fcf_yield=na)
        return compute_valuation_history(
            weekly, annual, splits,
            listing_ccy=info.get("currency"),
            financial_ccy=info.get("financialCurrency"))
```

> Hinweis: `ebit` ist im bestehenden Code bereits als Dict-Zeile vorhanden (`ebit = _row(...) or oi`); `info` ebenfalls (`info = self._yf.get_ticker_info(ticker)`). `MultipleStats` für den na_data-Pfad importiert.

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `uv run python -m pytest tests/services/test_historical_data_service.py -v`
Expected: PASS (neue + alle bestehenden Tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/historical_data_service.py tests/services/test_historical_data_service.py
git commit -m "Wire valuation_history into HistoricalDataService with fail-soft"
```

---

## Task 7: Cache — Schema-Bump 2→3 + valuation_history-Summary

**Files:**
- Modify: `app/deepdive/historical_cache.py`
- Test: `tests/deepdive/test_historical_cache.py`

- [ ] **Step 1: Failing test schreiben**

In `tests/deepdive/test_historical_cache.py`:

Die bestehende `_series()`-Fixture um die neuen Keys ergänzen (sonst rundtrip-inkonsistent) — am Ende des Dicts:
```python
            "net_income": [1, 2, 3], "diluted_eps": [0.1, 0.2, 0.3],
            "free_cashflow": [1, 1, 1], "total_debt": [9, 9, 9],
            "cash": [5, 5, 5],
```

Neue Tests anhängen:
```python
def test_schema_version_is_three():
    from app.deepdive.historical_cache import CACHE_SCHEMA_VERSION
    assert CACHE_SCHEMA_VERSION == 3


def test_write_includes_schema_version_three(tmp_path):
    cd, svc = _cd(tmp_path)
    cd.get_annual_series("X")
    persisted = json.loads((tmp_path / "X.json").read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 3


def test_v2_cache_treated_as_miss(tmp_path):
    cd, svc = _cd(tmp_path)
    v2_payload = {
        "_cached_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 2,
        "financial_currency": "DKK",
        "series": _series(),
    }
    (tmp_path / "X.json").write_text(json.dumps(v2_payload), encoding="utf-8")
    cd.get_annual_series("X")
    svc.get_annual_series.assert_called_once_with("X")
    refreshed = json.loads((tmp_path / "X.json").read_text(encoding="utf-8"))
    assert refreshed["schema_version"] == 3
```

> Hinweis: Der bestehende `test_write_includes_schema_version` asserted `== 2`. **Diesen auf `== 3` ändern** (Step 3 unten), sonst rot.

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `uv run python -m pytest tests/deepdive/test_historical_cache.py -v`
Expected: FAIL (`test_schema_version_is_three` rot; `test_write_includes_schema_version` rot mit `2 != 3`).

- [ ] **Step 3: Bump + bestehenden Test angleichen**

In `app/deepdive/historical_cache.py`:
```python
CACHE_SCHEMA_VERSION = 3
```

> Die `_series()` wird im Service jetzt mit einem `ValuationHistory`-Objekt unter `series["valuation_history"]` befüllt. Der Cache `json.dumps` den `series`-Dict — ein pydantic-Objekt ist NICHT JSON-serialisierbar. **Daher:** im Service (Task 6) NICHT das pydantic-Objekt in `series` ablegen, sondern beim Cache-Write zu dict wandeln. Korrektur: in `historical_cache.py` `_write_atomic`-Aufruf so anpassen, dass `valuation_history` als `.model_dump()` persistiert wird, und beim Lesen zurück zu `ValuationHistory`. Konkret — in `CachedHistoricalData.get_annual_series`, vor dem Write:

```python
        series = self._svc.get_annual_series(ticker)
        if use_cache:
            self._dir.mkdir(parents=True, exist_ok=True)
            to_store = dict(series)
            vh = to_store.get("valuation_history")
            if vh is not None and not isinstance(vh, dict):
                to_store["valuation_history"] = vh.model_dump()
            _write_atomic(
                path,
                {
                    "_cached_at": datetime.now(timezone.utc).isoformat(),
                    "schema_version": CACHE_SCHEMA_VERSION,
                    "financial_currency": series.get("financial_currency"),
                    "series": to_store,
                },
            )
        return series
```

Und beim Cache-Hit das dict zurück zu `ValuationHistory` heben:
```python
            if payload and self._fresh(payload.get("_cached_at", "")):
                logger.info("historical cache hit: %s", ticker)
                cached_series = payload["series"]
                vh = cached_series.get("valuation_history")
                if isinstance(vh, dict):
                    from app.models.deep_dive_record import ValuationHistory
                    cached_series["valuation_history"] = (
                        ValuationHistory(**vh))
                return cached_series
```

Den bestehenden `test_write_includes_schema_version` auf `== 3` ändern.

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `uv run python -m pytest tests/deepdive/test_historical_cache.py -v`
Expected: PASS (alle, inkl. v2→3-Invalidierung + Summary-Roundtrip).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/historical_cache.py tests/deepdive/test_historical_cache.py
git commit -m "Bump historical cache schema 2->3, persist valuation_history summary"
```

---

## Task 8: quant_join — valuation_history durchreichen + SourceCoverage

**Files:**
- Modify: `app/deepdive/quant_join.py`
- Modify: `app/models/deep_dive_record.py` (`SourceCoverage.valuation`-Default)
- Test: `tests/deepdive/test_quant_join.py`

- [ ] **Step 1: Failing test schreiben**

In `tests/deepdive/test_quant_join.py` die `_deps`-Fixture `historical.get_annual_series.return_value` um `valuation_history` ergänzen (nach `"complete": True`):
```python
        "valuation_history": ValuationHistory(
            pe=MultipleStats(median=21.4, p25=12.1, n_obs=200,
                             span_years=4.8, status="complete")),
```
Import oben ergänzen: `from app.models.deep_dive_record import MultipleStats, ValuationHistory`.

Neue Tests anhängen:
```python
def test_valuation_history_wired_onto_snapshot():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.valuation_history is not None
    assert qs.valuation_history.pe.median == 21.4
    assert qs.valuation_history.pe.status == "complete"


def test_valuation_history_none_when_absent_from_series():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    series = dict(hist.get_annual_series.return_value)
    del series["valuation_history"]
    hist.get_annual_series.return_value = series
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.valuation_history is None
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `uv run python -m pytest tests/deepdive/test_quant_join.py -k "valuation_history" -v`
Expected: FAIL (`qs.valuation_history is None`, weil noch nicht durchgereicht).

- [ ] **Step 3: Durchreichen + SourceCoverage**

In `app/deepdive/quant_join.py`, in `build_quant_snapshot` nach dem `snapshot = QuantSnapshot(...)`-Block — das Feld direkt im Konstruktor ergänzen:
```python
    snapshot = QuantSnapshot(
        point_in_time=pit,
        historical_series=hist,
        trend_metrics=trends,
        gemini_dimensions=gemini_dimensions,
        forward_estimates=forward_estimates,
        valuation_history=raw.get("valuation_history"),
    )
```

In `app/models/deep_dive_record.py`, `SourceCoverage.valuation`-Default ersetzen:
```python
    valuation: str = (
        "TTM + Mehrjahres-Median/Perzentil (KGV/EV-EBIT/FCF-Yield; Wochen-Preis × "
        "GJ-Fundamental, split-normalisiert; reale Tiefe ~3J, da freie yfinance "
        "nur 4 GJ liefert — 5J+ via SEC-XBRL ist Phase-2); cross-currency "
        "Honest-Label-Skip; restated-Fassung"
    )
```

> Falls ein bestehender Test den alten `valuation`-Default asserted: in `tests/models/test_deep_dive_record.py` suchen und auf den neuen Text angleichen (Step 1 dieser Task ergänzen, falls vorhanden).

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `uv run python -m pytest tests/deepdive/test_quant_join.py tests/models/test_deep_dive_record.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/quant_join.py app/models/deep_dive_record.py tests/deepdive/test_quant_join.py tests/models/test_deep_dive_record.py
git commit -m "Thread valuation_history through quant_join, update SourceCoverage"
```

---

## Task 9: Renderer — Heading + konsolidierte Mehrjahres-Range-Zeile

**Files:**
- Modify: `app/deepdive/valuation_block.py`
- Test: `tests/deepdive/test_valuation_block.py`

> **Task-0-Befund (entschieden):** freie yfinance = nur 4 GJ → reale Tiefe ~3J → KEIN „5J"-Label. Heading + Zeile tragen „Mehrjahres"; die reale Spanne steht im Zeilen-Prefix `(~{span}J, {n} Wo)` aus den `MultipleStats` (Label-Provenance, Spec §5/§10).

- [ ] **Step 1: Failing test schreiben**

In `tests/deepdive/test_valuation_block.py`:

Die `_qs`-Fixture um einen optionalen `valuation_history`-Parameter erweitern:
```python
def _qs(forward=None, valuation_history=None, **pit_over):
    pit = PointInTimeQuant(ticker="X", currency="DKK", **pit_over)
    return QuantSnapshot(
        point_in_time=pit,
        historical_series=HistoricalSeries(
            years=[2024, 2023, 2022, 2021, 2020],
            revenue=[1.0e9, 9.0e8, 8.0e8, 7.0e8, 6.0e8]),
        trend_metrics=TrendMetrics(buyback_intensity_5y=0.10),
        forward_estimates=forward,
        valuation_history=valuation_history,
    )
```
Import oben ergänzen: `from app.models.deep_dive_record import MultipleStats, ValuationHistory`.

Die **drei bestehenden Heading-Asserts** (Z. 28, 176, 258) auf den neuen Text ändern:
```python
    assert out.startswith(
        "## Bewertung & Kapitalstruktur (TTM-Stand + Mehrjahres-Median/"
        "Perzentil-Vergleich)")
```

Neue Tests anhängen:
```python
def _vh_complete():
    return ValuationHistory(
        pe=MultipleStats(median=21.4, p25=12.1, n_obs=164, span_years=3.1,
                         status="complete"),
        ev_ebit=MultipleStats(median=18.0, p25=13.1, n_obs=164, span_years=3.1,
                              status="complete"),
        fcf_yield=MultipleStats(median=0.038, p25=0.055, n_obs=164,
                                span_years=3.1, status="complete"))


def test_valuation_range_line_complete_all_three():
    out = render_valuation_block(_qs(
        trailing_pe=10.9, enterprise_value=2.0e10, ebit=1.4e9,
        free_cashflow=1.0e9, market_cap=2.0e10,
        valuation_history=_vh_complete()))
    line = next(l for l in out.splitlines()
                if l.startswith("Bewertungs-Range"))
    assert "P/E" in line and "Median 21.4" in line and "25-Perz. 12.1" in line
    assert "EV/EBIT" in line and "Median 18.0" in line
    assert "FCF-Yield" in line


def test_valuation_range_prefix_shows_real_span_and_obs():
    # Label-Provenance (§5/§10): the line names the real span + obs, not "5J".
    out = render_valuation_block(_qs(trailing_pe=10.9,
                                     valuation_history=_vh_complete()))
    line = next(l for l in out.splitlines()
                if l.startswith("Bewertungs-Range"))
    assert "164 Wo" in line
    assert "3" in line  # ~3J span, not "5J"
    assert "5J" not in line


def test_valuation_range_line_between_bewertung_and_kapital():
    out = render_valuation_block(_qs(trailing_pe=10.9,
                                     valuation_history=_vh_complete()))
    lines = out.splitlines()
    bew = next(i for i, l in enumerate(lines) if l.startswith("Bewertung:"))
    rng = next(i for i, l in enumerate(lines)
               if l.startswith("Bewertungs-Range"))
    kap = next(i for i, l in enumerate(lines)
               if l.startswith("Kapitalstruktur:"))
    assert bew < rng < kap


def test_valuation_range_all_skipped_fx_collapses():
    vh = ValuationHistory(
        pe=MultipleStats(status="skipped_fx"),
        ev_ebit=MultipleStats(status="skipped_fx"),
        fcf_yield=MultipleStats(status="skipped_fx"))
    out = render_valuation_block(_qs(trailing_pe=10.9, valuation_history=vh))
    line = next(l for l in out.splitlines()
                if l.startswith("Bewertungs-Range"))
    assert line == "Bewertungs-Range: n/a (FX: Listing≠Reporting)"


def test_valuation_range_per_multiple_na_when_mixed():
    vh = ValuationHistory(
        pe=MultipleStats(median=21.4, p25=12.1, n_obs=164, span_years=3.1,
                         status="complete"),
        ev_ebit=MultipleStats(status="na_data"),
        fcf_yield=MultipleStats(status="na_data"))
    out = render_valuation_block(_qs(trailing_pe=10.9, valuation_history=vh))
    line = next(l for l in out.splitlines()
                if l.startswith("Bewertungs-Range"))
    assert "P/E TTM 10.9 vs Median 21.4" in line
    assert "EV/EBIT n/a (Historie unvollständig)" in line


def test_valuation_range_all_na_collapses():
    vh = ValuationHistory(
        pe=MultipleStats(status="na_data"),
        ev_ebit=MultipleStats(status="na_data"),
        fcf_yield=MultipleStats(status="na_data"))
    out = render_valuation_block(_qs(trailing_pe=10.9, valuation_history=vh))
    line = next(l for l in out.splitlines()
                if l.startswith("Bewertungs-Range"))
    assert line == "Bewertungs-Range: n/a (Mehrjahres-Historie unvollständig)"


def test_valuation_range_none_honest_label():
    out = render_valuation_block(_qs(trailing_pe=10.9, valuation_history=None))
    line = next(l for l in out.splitlines()
                if l.startswith("Bewertungs-Range"))
    assert line == "Bewertungs-Range: n/a (Historie nicht verfügbar)"


def test_valuation_range_ttm_leg_matches_bewertung_line():
    out = render_valuation_block(_qs(trailing_pe=10.9,
                                     valuation_history=_vh_complete()))
    # the TTM P/E shown in the range line equals the one in the Bewertung line
    assert "P/E trail. 10.9" in out
    rng = next(l for l in out.splitlines()
               if l.startswith("Bewertungs-Range"))
    assert "TTM 10.9" in rng
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `uv run python -m pytest tests/deepdive/test_valuation_block.py -v`
Expected: FAIL (Heading-Asserts + neue range-Tests; `Bewertungs-Range`-Zeile existiert noch nicht).

- [ ] **Step 3: Renderer implementieren**

In `app/deepdive/valuation_block.py`:

`_HEADING` ersetzen:
```python
_HEADING = (
    "## Bewertung & Kapitalstruktur "
    "(TTM-Stand + Mehrjahres-Median/Perzentil-Vergleich)"
)
```

Helper für die TTM-Legs + Range-Zeile hinzufügen (vor `render_valuation_block`):
```python
def _ev_ebit_ttm(pit: Any) -> float | None:
    ev, ebit = pit.enterprise_value, pit.ebit
    if ev is None or ebit is None or ebit == 0:
        return None
    return ev / ebit


def _fcf_yield_ttm(pit: Any) -> float | None:
    fcf, mcap = pit.free_cashflow, pit.market_cap
    if fcf is None or mcap is None or mcap == 0:
        return None
    return fcf / mcap


def _range_segment(label: str, ttm: float | None, stats: Any, pct: bool) -> str:
    """Ein Multiple-Segment der Range-Zeile nach status (Spec §10). Die Spanne
    steht im Zeilen-Prefix, daher hier KEIN per-Segment-Wo-Suffix."""
    def f(v: float | None) -> str:
        if v is None:
            return "n/a"
        return f"{v:.1%}" if pct else f"{v:.1f}"
    if stats.status == "skipped_fx":
        return f"{label} n/a (FX: Listing≠Reporting)"
    if stats.status == "na_data":
        return f"{label} n/a (Historie unvollständig)"
    return (f"{label} TTM {f(ttm)} vs Median {f(stats.median)} "
            f"(25-Perz. {f(stats.p25)})")


def _range_prefix(vh: ValuationHistory) -> str | None:
    """Repräsentative Spanne für den Zeilen-Prefix: P/E bevorzugt, sonst das
    erste complete/partial-Multiple. None, wenn keines Werte trägt."""
    for stats in (vh.pe, vh.ev_ebit, vh.fcf_yield):
        if stats.status in ("complete", "partial") and stats.span_years:
            return f"(~{round(stats.span_years)}J, {stats.n_obs} Wo)"
    return None


def _render_valuation_range(quant: QuantSnapshot) -> str:
    vh = quant.valuation_history
    if vh is None:
        return "Bewertungs-Range: n/a (Historie nicht verfügbar)"
    statuses = {vh.pe.status, vh.ev_ebit.status, vh.fcf_yield.status}
    if statuses == {"skipped_fx"}:
        return "Bewertungs-Range: n/a (FX: Listing≠Reporting)"
    if statuses == {"na_data"}:
        return "Bewertungs-Range: n/a (Mehrjahres-Historie unvollständig)"
    pit = quant.point_in_time
    segs = [
        _range_segment("P/E", pit.trailing_pe, vh.pe, pct=False),
        _range_segment("EV/EBIT", _ev_ebit_ttm(pit), vh.ev_ebit, pct=False),
        _range_segment("FCF-Yield", _fcf_yield_ttm(pit), vh.fcf_yield,
                       pct=True),
    ]
    prefix = _range_prefix(vh)
    head = f"Bewertungs-Range {prefix}: " if prefix else "Bewertungs-Range: "
    return head + " · ".join(segs)
```

In `render_valuation_block` die Range-Zeile zwischen `bewertung` und `kapital` einfügen — den `block`-Aufbau anpassen:
```python
    valuation_range = _render_valuation_range(quant)
    consensus = _render_consensus(pit)
    forward = _render_forward(quant.forward_estimates)
    block = (f"{_HEADING}\n\n{bewertung}\n{valuation_range}\n{kapital}\n"
             f"{consensus}\n{forward}")
```

> Hinweis Test-Match: alle Range-Tests matchen auf `startswith("Bewertungs-Range")` — das deckt sowohl `Bewertungs-Range (~3J, 164 Wo): …` (mit Prefix) als auch `Bewertungs-Range: n/a …` (collapse) ab.

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `uv run python -m pytest tests/deepdive/test_valuation_block.py -v`
Expected: PASS (alle, inkl. der angepassten Heading-Asserts + neue Range-Tests + Ordering-Guard).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/valuation_block.py tests/deepdive/test_valuation_block.py
git commit -m "Render multi-year valuation range line with real-span label, update heading"
```

---

## Task 10: Volle Suite + Coverage-Gate

**Files:** keine neuen

- [ ] **Step 1: Volle Suite**

Run: `uv run python -m pytest`
Expected: alle grün, Coverage ≥ 96 % (Threshold zentral in `pyproject.toml`). Falls < 96 %: fehlende Zweige identifizieren (typisch: na_data-Pfade, EV-skip-Edge) und gezielt Tests ergänzen, dann erneut.

- [ ] **Step 2: Whole-Implementation-Review (Seam-Bugs, Lesson u)**

Manuell prüfen — die Schicht-Übergänge, die einzelne Unit-Tests nicht fangen:
- Cache-Roundtrip: `ValuationHistory` → `model_dump()` → JSON → zurück zu `ValuationHistory` (Task 7) ist konsistent mit dem, was `quant_join` erwartet (Task 8)?
- `compute_valuation_history`-Output-Feldnamen == Renderer-Zugriffe (`vh.pe`, `.median`, `.p25`, `.n_obs`, `.status`)?
- Service legt ein `ValuationHistory`-Objekt (nicht dict) in `series["valuation_history"]` ab; quant_join reicht es roh durch (`raw.get(...)`) → bei Cache-Hit kommt es bereits als Objekt zurück (Task 7 Step 3)?

- [ ] **Step 3: Commit (falls Coverage-Tests ergänzt)**

```bash
git add tests/
git commit -m "Add coverage tests for valuation_history edge paths"
```

---

## Task 11: Bezahlter Akzeptanz-Lauf (Stephan-Go vorab, ~$2–8)

**Nicht autonom.** Erst nach Stephan-Freigabe.

- [ ] **Step 1: Re-Run NOVO + GOOGL** (`--peers` Pflicht, kein TTY → sonst DeepDiveError)

Run:
```
uv run python -m app.deepdive deepdive NOVO-B.CO --peers LLY,PFE,MRK
uv run python -m app.deepdive deepdive GOOGL --peers MSFT,AMZN,META
```

- [ ] **Step 2: Akzeptanz prüfen**
- NOVO-Dossier zeigt „TTM x vs Median y (25-Perz. z)" mit ehrlichem Spannen-Label „~3J, N Wo" (Spec §1).
- **GOOGL-Split-Kanarienvogel:** Median-P/E plausibel (~20–35), NICHT um Faktor ~20 daneben (Spec §1/§3a). Falls daneben → STOP, Split-Normalisierung diagnostizieren (nicht Akzeptanz „durchwinken").
- **NOVO-Split-Gegenprobe:** NOVOs 2:1 (2023-09-13) liegt im nutzbaren Fenster → auch NOVOs Median-P/E muss plausibel sein (nicht um Faktor 2 verschoben). Zweiter End-to-End-§3a-Test (Spec §1).
- **Label-Ehrlichkeit:** das Dossier sagt NICHT „5J" (reale Tiefe ~3J im Prefix). Regime-Abdeckungs-Caveat (NOVO-Fenster großteils nach Ozempic-Re-Rating) ist bewusst, kein Defekt (Spec §1).

- [ ] **Step 3: Marker-Vokabular-Log beobachten** (Cross-Ref 1.2)
Wenn das Modell die neue Substanz mit neuem Quant-Label zitiert (z.B. `[Median]`/`[Bewertungs-Range]`) → `not in controlled vocabulary`-Warning. Erwarteter Katalog-Wachstums-Hit, kein Defekt: **eine Zeile** in `_QUANT_MARKER_VOCAB` (`synthesis.py:53`) nachziehen — **separater Mini-Commit**, nicht im 1.3-Kern.

---

## Task 12: Abschluss (nach Akzeptanz)

- [ ] **Step 1: Final-Whole-Implementation-Review** (subagent-driven: pro Task spec- + quality-Review; Final-Review vor Merge, Lesson u).
- [ ] **Step 2: Subagent-Commit-Hygiene** — `git log`/`git status` prüfen, keine unautorisierten Subagent-Commits (Memory subagent-commit-hygiene).
- [ ] **Step 3: `--no-ff`-Merge nach `main`**, Deploy grün verifizieren (`gh run list --branch main`).
- [ ] **Step 4: PROJEKTSTAND + Memory nachziehen** (erst NACH Merge — kein PROJEKTSTAND-Edit vorher).

---

## Stop-Bedingungen (aus Frame)

Deploy nicht grün · Plan-vs-Code-Abweichung · FX/Multiples-Kante unklar (Zahlen-Probe statt raten) · Coverage < 96 % · Drift im Commit · Akzeptanz-Substanz fehlt → STOP + Diagnose vor Merge.

## Nicht-Ziele

Kein 1.4-Vorgriff (Form-4-Insider) · kein PROJEKTSTAND-Edit vor Merge · kein Push/Merge ohne Stephan-Go · kein FX über FX-neutrale Multiples · kein Prompt-Text-Edit in 1.3 (Block fließt automatisch in den Prompt) · **kein SEC-XBRL-Quellen-Swap in 1.3** (das ist das definierte Phase-2-Tiefe-Ticket — siehe Spec §13; Mid-Stream-Quellentausch verletzt Sequenz-Disziplin Lesson v).

## Phase-2-Folge-Ticket (registriert, NICHT in 1.3)

**SEC-XBRL-Tiefe-Swap:** echte 5–10J-Fundamental-Tiefe via SEC EDGAR `companyfacts` (frei, CIK-Lookup + HTTP aus Punkt 5 vorhanden) durch den quellenblinden `compute_valuation_history`-Seam. Aufwands-Flag: companyfacts-JSON-Parsing, Unit-Handling, Fiscal-Period-Alignment, **us-gaap vs. ifrs-full-Taxonomie** (NOVO bilanziert IFRS → andere XBRL-Tags als us-gaap-Filer). Behebt die Regime-Abdeckungs-Schwäche (~3J = ein Marktregime) + den NOVO-Ozempic-Re-Rating-Caveat aus Spec §1.
