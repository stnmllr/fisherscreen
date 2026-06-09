# Symbol-Kontaminations-Korrektur (0a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Index-Quellen liefern für ~23 Titel Reuters-RIC-Mnemonics statt Yahoo-Symbole (`BNPP.PA` statt `BNP.PA`), die als Nicht-EQUITY ohne `market_cap`/`volume` auflösen, ans Volumen-Gate leaken und vom None-Guard auf BENIGN maskiert werden; `build_universe` korrigiert sie über eine verifizierte, ISIN-verankerte Map auf ihr Yahoo-Äquivalent (oder droppt echte Leichen) und dedupliziert.

**Architecture:** Zwei Phasen. (1) Eine Live-Diagnose-Probe (`scripts/diagnose_symbol_contaminants.py`, $0) enumeriert über das **ganze** Universum alle Nicht-EQUITY-Symbole und unterstützt die **ISIN-verankerte** Kuration der Korrektur-Tabelle — abgenommen von Stephan (Gate). (2) `build_universe` bekommt die abgenommene Map als Konstante + eine reine `_apply_symbol_corrections`-Funktion (vor dem Dedup), und `data/universe.json` wird mit derselben Funktion offline regeneriert (committeter Diff). Acceptance am Funnel-Cold-Dry-Run.

**Tech Stack:** Python 3.12, yfinance (über `yfinance_client`-Wrapper), pytest (offline DI-Mocks). cmd.exe; Tests via `uv run python -m pytest`. Spec: `docs/superpowers/specs/2026-06-06-symbol-contamination-correction-design.md`.

> **Disziplin (alle Tasks):** 0a ist ein **Symptom-Patch** (statische Map der heute bekannten Kontaminanten); Schutz vor künftiger Re-Kontamination ist **0b**. **Kein** algorithmisches Raten des Kandidaten — **ISIN ist der Anker**, die Probe/Stephan verifizieren. Kein Push/Merge ohne Stephans Go. Nach jedem Subagent `git status`/`git log` prüfen. Reconciliation muss nach 0a weiter aufgehen.

---

## File Structure

**Neu:**
- `scripts/diagnose_symbol_contaminants.py` — Live-Probe (enumerate + verify-Modus). Diagnose-Skript (wie `trigger_cold_dry_run.py`), aber die **reine** Klassifikations-/ISIN-Logik ist ausgelagert und unit-getestet.
- `scripts/apply_corrections_to_universe.py` — Einmal-Regenerierung von `data/universe.json` über die gemeinsame `_apply_symbol_corrections`-Funktion.
- `tests/scripts/test_symbol_classify.py` — Tests der reinen Probe-Helfer (`classify_info`, `isin_matches`).
- `tests/scripts/test_symbol_corrections.py` — Tests der Korrektur-Funktion + Konstanten-Invarianten.
- `docs/superpowers/audits/2026-06-06-0a-symbol-contaminants/correction_table.md` — **Gate-Artefakt:** abgenommene `{kontaminiert → korrekt | DROP}`-Tabelle + INCONCLUSIVE-Liste (von Schritt-1-Probe + Stephan).

**Modifiziert:**
- `scripts/build_universe.py` — `SYMBOL_CORRECTIONS`, `SYMBOL_DROP`, `_apply_symbol_corrections`, Aufruf in `main()` vor `sorted(set(...))`.
- `app/services/yfinance_client.py` — kleine Wrapper-Erweiterung `get_isin(ticker)` (service-layer-konform; Anker für ISIN-Verifikation, später wiederverwendbar für den Root-Cause-Fix).
- `data/universe.json` — regeneriert (committeter Diff).
- `CLAUDE.md` — Universum-Count nach Dedup aktualisieren; Composition-Abweichung notieren.

---

## Task 1: `get_isin` im yfinance-Wrapper

**Files:**
- Modify: `app/services/yfinance_client.py`
- Test: `tests/services/test_yfinance_client.py`

- [ ] **Step 1: Write the failing test**

In `tests/services/test_yfinance_client.py` ergänzen:

```python
def test_get_isin_returns_isin_string():
    client = YFinanceClientImpl()
    with patch("app.services.yfinance_client.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.isin = "FR0000131104"
        assert client.get_isin("BNP.PA") == "FR0000131104"


def test_get_isin_returns_none_when_absent_or_dash():
    client = YFinanceClientImpl()
    with patch("app.services.yfinance_client.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.isin = "-"   # yfinance sentinel for "no isin"
        assert client.get_isin("ZZZZ") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/services/test_yfinance_client.py::test_get_isin_returns_isin_string -v --no-cov`
Expected: FAIL — `AttributeError: 'YFinanceClientImpl' object has no attribute 'get_isin'`.

- [ ] **Step 3: Implement**

Add to the `YFinanceClient` Protocol (the `...`-method block near the top):

```python
    def get_isin(self, ticker: str) -> str | None: ...
```

Add to `YFinanceClientImpl`:

```python
    def get_isin(self, ticker: str) -> str | None:
        """Best-effort ISIN from yfinance. Returns None when absent ('-' sentinel)
        or on any failure — ISIN is a verification aid, never load-bearing alone."""
        try:
            isin = yf.Ticker(ticker).isin
        except Exception as exc:
            raise DataSourceError(f"yfinance isin failed for {ticker}: {exc}") from exc
        if not isin or isin == "-":
            return None
        return str(isin).strip().upper()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/services/test_yfinance_client.py -v --no-cov`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```
git add app/services/yfinance_client.py tests/services/test_yfinance_client.py
git commit -m "Add get_isin to yfinance client wrapper (ISIN verification aid)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Reine Probe-Helfer (classify + isin_matches)

**Files:**
- Create: `scripts/diagnose_symbol_contaminants.py` (helpers only in this task)
- Test: `tests/scripts/test_symbol_classify.py`

- [ ] **Step 1: Write the failing test**

`tests/scripts/test_symbol_classify.py` (new):

```python
from scripts.diagnose_symbol_contaminants import classify_info, isin_matches


def test_equity_info_is_equity():
    assert classify_info({"quoteType": "EQUITY", "marketCap": 1e9}) == "EQUITY"


def test_non_equity_is_contaminant():
    assert classify_info({"quoteType": "MUTUALFUND", "shortName": "3734810"}) == "CONTAMINANT"


def test_empty_or_missing_quotetype_is_inconclusive():
    assert classify_info({}) == "INCONCLUSIVE"
    assert classify_info({"marketCap": 1e9}) == "INCONCLUSIVE"   # no quoteType
    assert classify_info({"quoteType": None}) == "INCONCLUSIVE"


def test_isin_matches_normalizes_and_compares():
    assert isin_matches("fr0000131104", "FR0000131104 ") is True
    assert isin_matches("FR0000131104", "FR0000120271") is False


def test_isin_matches_false_when_either_missing():
    assert isin_matches(None, "FR0000131104") is False
    assert isin_matches("FR0000131104", None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/scripts/test_symbol_classify.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.diagnose_symbol_contaminants'`.

- [ ] **Step 3: Implement the helpers**

Create `scripts/diagnose_symbol_contaminants.py` with (helpers first; the live `main()` is added in Task 3):

```python
"""Diagnose: enumerate non-EQUITY symbol contaminants across the universe and
support ISIN-anchored verification of correction candidates. $0 probe (yfinance
only). Diagnostic script — the pure helpers below are unit-tested; the live
main() is a probe like scripts/trigger_cold_dry_run.py.

PREREQUISITE for the live run: none ($0). Uses the yfinance_client wrapper.
"""
from __future__ import annotations

from typing import Any


def classify_info(info: dict[str, Any]) -> str:
    """EQUITY | CONTAMINANT | INCONCLUSIVE from a yfinance .info dict.

    - quoteType == 'EQUITY'        -> EQUITY (clean)
    - quoteType present & != EQUITY -> CONTAMINANT (e.g. MUTUALFUND)
    - quoteType missing/None/empty  -> INCONCLUSIVE (transient hiccup; retry/manual)
    """
    if not info:
        return "INCONCLUSIVE"
    quote_type = info.get("quoteType")
    if not quote_type:
        return "INCONCLUSIVE"
    return "EQUITY" if quote_type == "EQUITY" else "CONTAMINANT"


def isin_matches(a: str | None, b: str | None) -> bool:
    """True iff both ISINs are present and equal (normalized). Missing -> False
    (caller falls back to name-match + manual confirmation)."""
    if not a or not b:
        return False
    return a.strip().upper() == b.strip().upper()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/scripts/test_symbol_classify.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add scripts/diagnose_symbol_contaminants.py tests/scripts/test_symbol_classify.py
git commit -m "Add pure contaminant-classification + ISIN-match helpers for 0a probe

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Live-Probe-Modi (enumerate + verify)

**Files:**
- Modify: `scripts/diagnose_symbol_contaminants.py` (add live `main()` with two modes)

> No unit test for the live network code (it's a probe, like `trigger_cold_dry_run.py`). The pure helpers from Task 2 carry the tested logic.

- [ ] **Step 1: Add the live driver**

Append to `scripts/diagnose_symbol_contaminants.py`:

```python
import argparse
import csv
import json
import sys
import time

from app.errors import DataSourceError, DegradedDataError
from app.services.yfinance_client import YFinanceClientImpl


def _probe_one(client: YFinanceClientImpl, ticker: str, retries: int = 2) -> dict[str, Any]:
    """Return {ticker, status, quoteType, isin, shortName, longName}. Retries on
    INCONCLUSIVE with linear backoff so a yfinance hiccup is not baked as a verdict."""
    last: dict[str, Any] = {}
    for attempt in range(retries + 1):
        try:
            info = client.get_ticker_info(ticker)
        except DegradedDataError:
            return {"ticker": ticker, "status": "DEGRADED", "quoteType": None,
                    "isin": None, "shortName": None, "longName": None}
        except DataSourceError:
            info = {}
        status = classify_info(info)
        last = {"ticker": ticker, "status": status,
                "quoteType": info.get("quoteType"),
                "isin": None, "shortName": info.get("shortName"),
                "longName": info.get("longName")}
        if status != "INCONCLUSIVE":
            try:
                last["isin"] = client.get_isin(ticker)
            except DataSourceError:
                last["isin"] = None
            return last
        time.sleep(1.0 * (attempt + 1))  # linear backoff between retries
    return last


def _enumerate(client: YFinanceClientImpl, tickers: list[str]) -> list[dict[str, Any]]:
    rows = [_probe_one(client, t) for t in tickers]
    contaminants = [r for r in rows if r["status"] == "CONTAMINANT"]
    inconclusive = [r for r in rows if r["status"] == "INCONCLUSIVE"]
    print(f"probed={len(rows)} contaminant={len(contaminants)} "
          f"inconclusive={len(inconclusive)} "
          f"equity={sum(1 for r in rows if r['status']=='EQUITY')} "
          f"degraded={sum(1 for r in rows if r['status']=='DEGRADED')}", file=sys.stderr)
    return rows


def _verify(client: YFinanceClientImpl, proposal: dict[str, str]) -> None:
    """proposal: {contaminant_ticker: candidate_ticker}. Prints per pair whether the
    candidate is EQUITY and whether ISINs match (name shown for manual fallback)."""
    for bad, good in proposal.items():
        c = _probe_one(client, bad)
        g = _probe_one(client, good)
        match = isin_matches(c.get("isin"), g.get("isin"))
        print(json.dumps({
            "contaminant": bad, "candidate": good,
            "candidate_status": g["status"],
            "isin_contaminant": c.get("isin"), "isin_candidate": g.get("isin"),
            "isin_match": match,
            "name_contaminant": c.get("shortName"), "name_candidate": g.get("longName") or g.get("shortName"),
        }, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["enumerate", "verify"])
    parser.add_argument("--universe", default="data/universe.json")
    parser.add_argument("--proposal", help="JSON file {bad: good} for verify mode")
    parser.add_argument("--out", help="CSV output path for enumerate mode")
    args = parser.parse_args()

    client = YFinanceClientImpl()
    if args.mode == "enumerate":
        tickers = json.loads(open(args.universe, encoding="utf-8").read())
        rows = _enumerate(client, tickers)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["ticker", "status", "quoteType",
                                                  "isin", "shortName", "longName"])
                w.writeheader()
                w.writerows(rows)
            print(f"wrote {args.out}", file=sys.stderr)
    else:
        proposal = json.loads(open(args.proposal, encoding="utf-8").read())
        _verify(client, proposal)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-check it imports (no network)**

Run: `uv run python -c "import scripts.diagnose_symbol_contaminants as m; print(hasattr(m,'main'))"`
Expected: prints `True`. (No live run here — that is the GATE below.)

- [ ] **Step 3: Commit**

```
git add scripts/diagnose_symbol_contaminants.py
git commit -m "Add live enumerate/verify modes to symbol-contaminant probe

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## GATE 1 — Live-Probe + ISIN-verankerte Kuration (Stephans Abnahme, $0)

> **Kein Code-Task — ein Gate. Erst nach Stephans Go ausführen.** Cmd.exe.

- [ ] **Step 1 — Enumerate (live, $0):** (Audit-Verzeichnis zuerst anlegen)

```
mkdir docs\superpowers\audits\2026-06-06-0a-symbol-contaminants
uv run python scripts\diagnose_symbol_contaminants.py enumerate --out docs\superpowers\audits\2026-06-06-0a-symbol-contaminants\enumerate.csv
```
Erwartung: bestätigt **US sauber** (keine US-no-suffix CONTAMINANT) und listet die Kontaminanten (~23 erwartet). INCONCLUSIVEs gesondert.

- [ ] **Step 2 — Kandidaten ISIN-verankert kuratieren:** Pro CONTAMINANT die ISIN nachschlagen (Holdings/autoritativ), das Yahoo-Symbol mit **derselben ISIN** bestimmen, in `proposal.json` (`{bad: good}`) eintragen. Echte Leichen (z. B. `SKY.L`) NICHT mappen → später `SYMBOL_DROP`.

- [ ] **Step 3 — Verify (live, $0):**

```
uv run python scripts\diagnose_symbol_contaminants.py verify --proposal docs\superpowers\audits\2026-06-06-0a-symbol-contaminants\proposal.json
```
Erwartung: pro Paar `candidate_status=EQUITY` **und** `isin_match=true` (sonst Name-Fallback + manuelle Bestätigung).

- [ ] **Step 4 — Gate-Abschluss (blockierend):** Abgenommene Tabelle nach `docs\superpowers\audits\2026-06-06-0a-symbol-contaminants\correction_table.md` schreiben: jede Zeile `{kontaminiert, korrekt|DROP, isin, isin_match|name-fallback}`. **Null ungelöste INCONCLUSIVEs** — jedes ist korrigiert, gedroppt oder **namentlich aufgeschoben+gelistet**. Stephan gibt die Tabelle frei, **bevor** Task 4 sie hartkodiert. Aus der Tabelle: `N = #Twin-Kollaps + #DROP` und die erwartete Survivor-/REVIEW-Verschiebung notieren (für GATE 2).

---

## Task 4: Korrektur-Funktion + Konstanten (offline, TDD)

**Files:**
- Modify: `scripts/build_universe.py`
- Test: `tests/scripts/test_symbol_corrections.py`

- [ ] **Step 1: Write the failing test**

`tests/scripts/test_symbol_corrections.py` (new) — testet die **Mechanik** mit Fixture-Maps (unabhängig von den echten Werten):

```python
import scripts.build_universe as bu


def test_remap_then_set_collapses_twin():
    out = bu._apply_symbol_corrections(["BNPP.PA", "BNP.PA", "AAPL"],
                                       corrections={"BNPP.PA": "BNP.PA"}, drop=set())
    assert sorted(set(out)) == ["AAPL", "BNP.PA"]


def test_drop_removes_symbol():
    out = bu._apply_symbol_corrections(["SKY.L", "AAPL"], corrections={}, drop={"SKY.L"})
    assert out == ["AAPL"]


def test_unrelated_untouched():
    out = bu._apply_symbol_corrections(["AAPL", "MSFT"], corrections={"BNPP.PA": "BNP.PA"}, drop=set())
    assert out == ["AAPL", "MSFT"]


def test_idempotent():
    corr = {"BNPP.PA": "BNP.PA"}
    once = bu._apply_symbol_corrections(["BNPP.PA", "BNP.PA"], corrections=corr, drop=set())
    twice = bu._apply_symbol_corrections(once, corrections=corr, drop=set())
    assert sorted(set(once)) == sorted(set(twice))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/scripts/test_symbol_corrections.py -v --no-cov`
Expected: FAIL — `AttributeError: module 'scripts.build_universe' has no attribute '_apply_symbol_corrections'`.

- [ ] **Step 3: Implement function + empty constants**

In `scripts/build_universe.py` near the other module constants add:

```python
# Verified, ISIN-anchored corrections from GATE 1 (docs/.../0a-symbol-contaminants/
# correction_table.md). Populated in the next step from the approved table.
SYMBOL_CORRECTIONS: dict[str, str] = {}
SYMBOL_DROP: set[str] = set()


def _apply_symbol_corrections(
    tickers: list[str],
    corrections: dict[str, str] | None = None,
    drop: set[str] | None = None,
) -> list[str]:
    """Remap contaminated symbols to their verified Yahoo equivalent and drop dead
    listings. Pure: no dedup here (caller's sorted(set(...)) collapses remapped
    twins). Instrumentation-visible: logs each remap/drop."""
    corrections = SYMBOL_CORRECTIONS if corrections is None else corrections
    drop = SYMBOL_DROP if drop is None else drop
    out: list[str] = []
    for t in tickers:
        if t in drop:
            logger.info("symbol_correction: drop %s", t)
            continue
        if t in corrections:
            logger.info("symbol_correction: remap %s -> %s", t, corrections[t])
            out.append(corrections[t])
        else:
            out.append(t)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/scripts/test_symbol_corrections.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add scripts/build_universe.py tests/scripts/test_symbol_corrections.py
git commit -m "Add _apply_symbol_corrections mechanism (empty map, mechanism-tested)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Abgenommene Map einsetzen + Invarianten-Guards

**Files:**
- Modify: `scripts/build_universe.py` (fill `SYMBOL_CORRECTIONS` / `SYMBOL_DROP` from GATE 1)
- Test: `tests/scripts/test_symbol_corrections.py`

- [ ] **Step 1: Write the failing invariants test**

Append to `tests/scripts/test_symbol_corrections.py`:

```python
def test_corrections_are_injective():
    # No two contaminants map to the same target. A legitimate same-company
    # collision must be resolved as a DROP during curation, not a duplicate remap.
    values = list(bu.SYMBOL_CORRECTIONS.values())
    assert len(values) == len(set(values)), "duplicate correction targets"


def test_key_is_not_its_own_value():
    for k, v in bu.SYMBOL_CORRECTIONS.items():
        assert k != v


def test_drop_and_corrections_disjoint():
    assert not (set(bu.SYMBOL_CORRECTIONS) & bu.SYMBOL_DROP)


def test_known_contaminants_resolved():
    # Spot-anchors from the Gate-A evidence: these must be handled (remap or drop),
    # i.e. NOT pass through unchanged.
    for bad in ["BNPP.PA", "SASY.PA", "SOGN.PA", "SGOB.PA", "BOUY.PA", "ENX.AS", "CTS.DE"]:
        assert bad in bu.SYMBOL_CORRECTIONS or bad in bu.SYMBOL_DROP, bad
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/scripts/test_symbol_corrections.py::test_known_contaminants_resolved -v --no-cov`
Expected: FAIL (constants still empty).

- [ ] **Step 3: Populate the constants from the approved GATE 1 table**

In `scripts/build_universe.py` fill `SYMBOL_CORRECTIONS` and `SYMBOL_DROP` **verbatim from** `docs/superpowers/audits/2026-06-06-0a-symbol-contaminants/correction_table.md` (the Stephan-approved, ISIN-verified table). Example shape (REAL values come from the table, not from guesses):

```python
SYMBOL_CORRECTIONS = {
    "BNPP.PA": "BNP.PA",
    "SASY.PA": "SAN.PA",
    # ... every approved remap from correction_table.md ...
}
SYMBOL_DROP = {"SKY.L"}  # plus any other approved dead listings
```

> The values are **data produced by GATE 1**, not invented here. If GATE 1 listed a deferred INCONCLUSIVE, it is NOT added (it stays in the universe and is named in the GATE 2 acceptance exceptions).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/scripts/test_symbol_corrections.py -v --no-cov`
Expected: PASS (injective, disjoint, key≠value, known contaminants resolved).

- [ ] **Step 5: Commit**

```
git add scripts/build_universe.py tests/scripts/test_symbol_corrections.py
git commit -m "Populate verified ISIN-anchored symbol corrections from GATE 1 table

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: In `main()` verdrahten + Guard

**Files:**
- Modify: `scripts/build_universe.py` (`main()`)
- Test: `tests/scripts/test_build_universe_provenance.py` (reuse the file; add a main-path assertion via the function)

- [ ] **Step 1: Write the failing test**

Append to `tests/scripts/test_symbol_corrections.py`:

```python
def test_combined_pipeline_drops_keys_and_dedups():
    # Simulate main()'s combined list incl. a contaminant + its twin + a drop.
    combined_raw = ["BNPP.PA", "BNP.PA", "SKY.L", "AAPL"]
    corrected = sorted(set(bu._apply_symbol_corrections(combined_raw)))
    # No correction KEY survives; the twin collapsed; the drop is gone.
    assert not (set(bu.SYMBOL_CORRECTIONS) & set(corrected))
    assert "SKY.L" not in corrected
    assert "BNP.PA" in corrected and "AAPL" in corrected
```

- [ ] **Step 2: Run test to verify it fails (if main not yet wired) / passes function-level**

Run: `uv run python -m pytest tests/scripts/test_symbol_corrections.py::test_combined_pipeline_drops_keys_and_dedups -v --no-cov`
Expected: PASS at the function level already (this pins the contract). Proceed to wire `main()`.

- [ ] **Step 3: Wire into `main()`**

In `scripts/build_universe.py` `main()`, change the combine line from:

```python
    combined = sorted(set(sp500 + sp400 + stoxx))
```
to:

```python
    combined = sorted(set(_apply_symbol_corrections(sp500 + sp400 + stoxx)))
    # Guard: no contaminated key may survive into the universe.
    surviving = set(SYMBOL_CORRECTIONS) & set(combined)
    if surviving:
        raise RuntimeError(f"symbol_correction guard: contaminated keys survived: {sorted(surviving)}")
    logger.info("symbol_correction: %d corrections, %d drops applied",
                len(SYMBOL_CORRECTIONS), len(SYMBOL_DROP))
```

- [ ] **Step 4: Run the build_universe test file (no network — provenance tests mock fetchers)**

Run: `uv run python -m pytest tests/scripts/ -v --no-cov`
Expected: PASS (provenance tests still green; correction tests green).

- [ ] **Step 5: Commit**

```
git add scripts/build_universe.py tests/scripts/test_symbol_corrections.py
git commit -m "Apply symbol corrections before dedup in build_universe with survival guard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `data/universe.json` offline regenerieren

**Files:**
- Create: `scripts/apply_corrections_to_universe.py`
- Modify: `data/universe.json` (regenerated output, committed)

- [ ] **Step 1: Write the one-shot regenerator**

`scripts/apply_corrections_to_universe.py` (new):

```python
"""One-shot: apply the verified symbol corrections to data/universe.json in place.
Shared function with the live build (build_universe._apply_symbol_corrections), so
the committed universe.json and a future live rebuild agree exactly."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.build_universe import _apply_symbol_corrections

PATH = Path(__file__).parent.parent / "data" / "universe.json"


def main() -> None:
    tickers = json.loads(PATH.read_text(encoding="utf-8"))
    before = len(tickers)
    corrected = sorted(set(_apply_symbol_corrections(tickers)))
    PATH.write_text(json.dumps(corrected, indent=2), encoding="utf-8")
    print(f"universe.json: {before} -> {len(corrected)} (delta {before - len(corrected)})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `uv run python scripts\apply_corrections_to_universe.py`
Expected: prints `universe.json: 1332 -> <1332 − N>` where N matches the GATE 1 figure (`#Twin-Kollaps + #DROP`). If the delta ≠ the predicted N, STOP — the map is inconsistent with the prediction.

- [ ] **Step 3: Verify the diff by hand**

Run: `git -C "D:/programme/fisherscreen" diff --stat data/universe.json` and inspect the removed lines: every removed symbol must be a GATE 1 contaminant key or DROP; every contaminant's correct twin must remain present.

- [ ] **Step 4: Commit**

```
git add scripts/apply_corrections_to_universe.py data/universe.json
git commit -m "Regenerate universe.json with verified symbol corrections (offline, shared fn)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Volle Suite + No-Drift

**Files:** keine Code-Änderung.

- [ ] **Step 1: Full suite**

Run: `uv run python -m pytest`
Expected: PASS, Coverage ≥ 90 %. New scripts covered by their unit tests.

- [ ] **Step 2: Confirm no funnel/gate drift**

Run: `uv run python -m pytest tests/screener/ tests/output/ -q --no-cov`
Expected: PASS unchanged — 0a touches build_universe + a wrapper method, not the gates/funnel.

- [ ] **Step 3: Commit (only if test top-ups were needed)**

```
git add tests/
git commit -m "Top up 0a test coverage"
```

---

## GATE 2 — Acceptance Cold-Dry-Run (Funnel, vorher/nachher, $0) — Stephans Go

> **Kein Code-Task. Erst nach Stephans Go.** Cmd.exe. Caches kalt (CLAUDE.md/[[prod-logging-dormant-and-cache-masks-verification]]).

- [ ] **Step 1 — Purge + Cold-Dry-Run (lokal, wie Gate A):**

```
uv run python scripts\purge_ticker_cache_all.py --apply
uv run python scripts\purge_edgar_cache_all.py --apply
```
Server (Terminal A): `uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8080`
Trigger (Terminal B): `uv run python scripts\trigger_cold_dry_run.py http://localhost:8080`

- [ ] **Step 2 — Vorher/Nachher gegen die GATE-1-Prognose prüfen:**
  - **Universum:** `1332 − N` (Stufe `universe.entered`), N = GATE-1-Zahl.
  - **Survivor:** `687 + M` (Stufe `edgar_gates.remaining`) — `M > 0` belegt zurückgeholte Kandidaten.
  - **Leer-`market_cap`-Drops:** nur noch die 5 DEGRADED_DICT + namentlich gelistete aufgeschobene INCONCLUSIVEs (sonst null). Keine korrigierten Symbole mehr in BENIGN-`GATE_VOLUME` mit leerem market_cap.
  - **REVIEW-Verschiebung** entspricht der GATE-1-Prognose.
  - **Reconciliation** hält: `|Universum| == Σ Drops + übrig`.

- [ ] **Step 3 — Server stoppen** und Funnel-Zahlen an Stephan berichten.

---

## Task 9: CLAUDE.md nachziehen (nach GATE 2)

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1:** Den Universum-Wert (`~2.100`) durch den **echten Post-0a-Count** aus GATE 2 ersetzen und den TODO-Kommentar dazu entfernen/auflösen.
- [ ] **Step 2:** Composition-Abweichung **notieren** (CLAUDE.md sagt „S&P 500 + Russell 1000", real „S&P 500 + S&P 400" + STOXX 600) — als kurzer Hinweis/separates Cleanup-Ticket, **nicht** in 0a fixen.
- [ ] **Step 3: Commit**

```
git add CLAUDE.md
git commit -m "Update universe count post-0a-dedup; note S&P400-vs-Russell1000 composition discrepancy

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Abschluss

0a ist ein Symptom-Patch. **Vor** Merge/Push (Auto-Deploy nach Prod!) folgt laut Ticket **0b** (Resolution-Schutz) und **Punkt 1** (Volumen-Gate), dann ein gebündelter Remote-PR {Instrument + 0a + 0b + 1} = ein sauberer Prod-Deploy. Kein Push/Merge ohne Stephans Go.
