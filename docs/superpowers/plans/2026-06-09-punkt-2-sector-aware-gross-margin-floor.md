# Punkt 2 — Sektor-bewusster gross_margin-Floor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ersetze den flachen `gross_margin >= 0.30`-Knock-out durch (1) einen sichtbaren Definiertheits-Ausschluss (`FRAMEWORK/METRIK_NA`) für Firmen ohne echte Bruttomargen-Metrik (Banken/Versicherer/REITs) und (2) einen monotonen sektor-bewussten Dual-Arm-Floor, der strukturell niedrigmargige Sektoren auf branchen-normaler Marge rettet — ohne je einen aktuellen Survivor zu droppen.

**Architecture:** Reine, testbare Logik-Module (`app/screener/`) für Definiertheits-Prädikat, Wasserfall-Form-Klassifikator, Sektor-Bucket-Resolver und Dual-Arm-Gate; ein vintage-gestempelter, versions-kontrollierter Sektor-Median-Referenz-Table (Loader nach ADR-Muster, fail-safe-Sentinel solange abwesend); ein $0-Gate-A-Kalibrierungs-Block als **Korrektheits-Kette A1→A2→A3** (Definiertheit klären → Table auf bereinigtem Universum bauen → k kalibrieren); Aktivierung des Rettungs-Arms erst durch Committen des kalibrierten Tables (Gate-B Cold-Run).

**Tech Stack:** Python 3.12, FastAPI, pydantic, pytest (DI-Mocks, 90 % Coverage-Floor), uv, yfinance (via Service-Layer), Firestore-Cache. Aufruf-Konvention lokal: `uv run python -m pytest`, `uv run python scripts\<name>.py` (SOPRA-EPDR, cmd.exe).

**Spec:** `docs/superpowers/specs/2026-06-09-punkt-2-sector-aware-gross-margin-floor-design.md`. Leitprinzip: das Gate ist ein **struktureller Viabilitäts-Floor**, kein Relativ-Qualitäts-Screen ([[adaptive-stat-swallows-judgment]]).

---

## Phasen-Übersicht & Reihenfolge

| Phase | Inhalt | Abhängigkeit |
|---|---|---|
| **0** | Reine Logik-Module (Prädikat, Wasserfall-Klassifikator, Bucket-Resolver) — TDD | — |
| **A** | Gate-A Kalibrierung, **Kette A1→A2→A3** ($0, Skripte) | braucht Phase 0 |
| **B** | Mechanismus 1: METRIK_NA-Divert (Default `.info`-only) — TDD | braucht Phase 0 |
| **C** | Mechanismus 2: Sektor-Median-Table-Loader + Dual-Arm-Gate (fail-safe-Sentinel) — TDD | braucht Phase 0 |
| **D** | Funnel-/Artefakt-Verdrahtung für METRIK_NA + Reconciliation-Tests | braucht B, C |
| **E** | Kalibrierte Werte committen + Gate-B Cold-Run-Akzeptanz | braucht A, B, C, D + **Stephans Go** |
| **CT** | Kontingente Tasks (nur falls Gate-A sie auslöst) | braucht A-Ergebnis |

**Harte Ordnungsregel (Intra-Gate-A, nicht-verhandelbar):** A1 → A2 → A3. A2 (Table-Bau) läuft auf dem **post-A1-, METRIK_NA-bereinigten** Universum — sonst kontaminieren die ausgeschlossenen Financials/REITs die Sektor-Mediane (am schärfsten in gemischten rolled-up-Buckets), und ein zu niedriger Median macht den `k × Median`-Arm zu lasch. A3 (k) hängt am bereinigten Table. Das ist das Intra-Gate-A-Gegenstück zum Universe-Ordering (Punkt 2 vor Punkt 3).

**Phasen 0/B/C/D mergen vor Kalibrierung** (Mechanismus 2 ist fail-safe-dormant ohne Table; Mechanismus 1 relabelt nur bereits-gedroppte Financials → monoton). Phase E aktiviert den Rettungs-Arm.

---

## Datei-Struktur (neu / geändert)

**Neu (reine Logik, coverage-pflichtig):**
- `app/screener/metric_definedness.py` — Definiertheits-Prädikat (Default `.info`-only) + Wasserfall-Form-Klassifikator.
- `app/screener/sector_buckets.py` — Bucket-Resolver (feinster GICS-Knoten mit n_min, Roll-up) + Sektor-Median-Table-Typ.
- `app/screener/sector_median_table.py` — validierender Loader (ADR-Muster), vintage-/schema-gestempelt.

**Neu (Daten / Skripte):**
- `data/sector_median_table.json` — vintage-gestempelter Referenz-Table (von Gate-A A2 erzeugt, in Phase E committet).
- `scripts/diagnose_gross_margin_definedness.py` — Gate-A A1.
- `scripts/diagnose_sector_median_table.py` — Gate-A A2.
- `scripts/diagnose_k_calibration.py` — Gate-A A3.

**Geändert:**
- `app/screener/filters.py` — METRIK_NA-Divert in `_get_fail_reason`; Dual-Arm in `passes_gross_margin_filter`; neue Sentinel-Konstanten.
- `app/screener/funnel.py` — neuer `ReasonCode.FRAMEWORK_METRIK_NA` + `_BASIS_REASON`-Eintrag.
- `app/screener/compose.py` — `build_sector_median_table()`-Factory.
- `app/screener/runner.py` — Table in `apply_basis_filters` injizieren (sofern Signatur-Durchreichung; s. Task C4).

**Tests (spiegeln Source):**
- `tests/screener/test_metric_definedness.py`, `tests/screener/test_sector_buckets.py`, `tests/screener/test_sector_median_table.py`, Erweiterungen in `tests/screener/test_filters.py` und `tests/screener/test_funnel.py`.

---

# Phase 0 — Reine Logik-Module (TDD)

### Task 0.1: Definiertheits-Prädikat (Default `.info`-only)

**Files:**
- Create: `app/screener/metric_definedness.py`
- Test: `tests/screener/test_metric_definedness.py`

- [ ] **Step 1: Failing test**

```python
# tests/screener/test_metric_definedness.py
from app.models.screener_record import ScreenerRecord
from app.screener.metric_definedness import is_gross_margin_undefined_info_only


def _rec(gm):
    return ScreenerRecord(ticker="T", gross_margin=gm)


def test_none_margin_is_undefined():
    assert is_gross_margin_undefined_info_only(_rec(None)) is True


def test_zero_margin_is_undefined():
    assert is_gross_margin_undefined_info_only(_rec(0.0)) is True


def test_negative_margin_is_undefined_info_only():
    # .info-only default cannot distinguish structural-undefined from real-negative;
    # Gate-A A1 verifies the gm<=0 basket holds no real industrial negative-marger.
    assert is_gross_margin_undefined_info_only(_rec(-0.05)) is True


def test_positive_margin_is_defined():
    assert is_gross_margin_undefined_info_only(_rec(0.20)) is False
```

- [ ] **Step 2: Run, verify fail** — `uv run python -m pytest tests/screener/test_metric_definedness.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# app/screener/metric_definedness.py
"""Metric-definedness predicate + waterfall-shape discriminator for the
gross_margin gate (Punkt 2). The .info-only predicate is the runtime DEFAULT;
the waterfall classifier is used by the Gate-A calibration probe and becomes the
runtime predicate only if Gate-A finds a non-empty edge (spec §6 Property A)."""
from __future__ import annotations

from app.models.screener_record import ScreenerRecord


def is_gross_margin_undefined_info_only(record: ScreenerRecord) -> bool:
    """Runtime DEFAULT definedness predicate (.info-only, no fetch).
    gm is None or <= 0 => treat as structurally undefined => METRIK_NA."""
    gm = record.gross_margin
    return gm is None or gm <= 0.0
```

- [ ] **Step 4: Run, verify pass.**

- [ ] **Step 5: Commit** — `git add app/screener/metric_definedness.py tests/screener/test_metric_definedness.py && git commit -m "Add .info-only gross-margin definedness predicate (Punkt 2)"`

---

### Task 0.2: Wasserfall-Form-Klassifikator (für Gate-A; kontingenter Runtime)

**Files:**
- Modify: `app/screener/metric_definedness.py`
- Test: `tests/screener/test_metric_definedness.py`

Semantik: Diskriminator liest die **Form** des Wasserfalls, NICHT die Zeilen-Präsenz. Drei Verdikte:
`DEFINED` (echter Umsatz→COGS→Gross-Profit-Wasserfall, Fisher-tauglich), `UNDEFINED` (keine echte
COGS-Struktur → METRIK_NA, egal welche gm-Zahl), `DEFINED_NEGATIVE` (echter Wasserfall, aber COGS > Umsatz
→ reales Negativsignal → FAIL, nicht NA).

- [ ] **Step 1: Failing test** — die drei §8-Pin-Fälle plus Konsistenz:

```python
from app.screener.metric_definedness import classify_waterfall, WaterfallVerdict


def test_real_waterfall_is_defined():
    # Daten-/Indexhaus: rev>cor>0, gp == rev - cor, gp > 0
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=300.0,
                           gross_profit=700.0, cost_of_revenue_present=True)
    assert v is WaterfallVerdict.DEFINED


def test_bank_no_cost_of_revenue_row_is_undefined():
    # gm<=0 Bank: keine echte COGS-Zeile -> UNDEFINED (Null-Kante)
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=None,
                           gross_profit=None, cost_of_revenue_present=False)
    assert v is WaterfallVerdict.UNDEFINED


def test_spurious_positive_insurer_is_undefined():
    # Versicherer/REIT: gp ~ rev, cor ~ 0 (claims woanders gebucht) -> UNDEFINED trotz gm>0 (Positiv-Kante)
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=0.0,
                           gross_profit=995.0, cost_of_revenue_present=True)
    assert v is WaterfallVerdict.UNDEFINED


def test_real_industrial_negative_marger_is_defined_negative():
    # echter Wasserfall, aber unter Selbstkosten: cor>rev -> FAIL, nicht NA
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=1100.0,
                           gross_profit=-100.0, cost_of_revenue_present=True)
    assert v is WaterfallVerdict.DEFINED_NEGATIVE


def test_inconsistent_waterfall_is_undefined():
    # gp weicht stark von rev-cor ab -> Struktur nicht vertrauenswürdig -> UNDEFINED
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=300.0,
                           gross_profit=200.0, cost_of_revenue_present=True)
    assert v is WaterfallVerdict.UNDEFINED
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** (append to `metric_definedness.py`):

```python
from enum import Enum


class WaterfallVerdict(str, Enum):
    DEFINED = "DEFINED"                     # real revenue->COGS->gross-profit waterfall
    UNDEFINED = "UNDEFINED"                 # no real COGS structure -> METRIK_NA
    DEFINED_NEGATIVE = "DEFINED_NEGATIVE"   # real waterfall, COGS>revenue -> FAIL (not NA)


# Relative tolerance for the consistency check gp == revenue - cost_of_revenue.
_WATERFALL_REL_TOL = 0.02
# A cost-of-revenue this small relative to revenue means there is no genuine COGS
# (bank/insurer/REIT signature: "revenue" is net interest/premium/rent, gp ~ rev).
_MIN_COR_FRACTION = 0.01


def classify_waterfall(
    total_revenue: float | None,
    cost_of_revenue: float | None,
    gross_profit: float | None,
    cost_of_revenue_present: bool,
) -> WaterfallVerdict:
    """Form-based discriminator. Reads the SHAPE of the income-statement waterfall,
    not the mere presence of a Cost-of-Revenue line (a presence test flips on the
    spurious-positive edge — see spec §3)."""
    if not cost_of_revenue_present or total_revenue is None or total_revenue <= 0:
        return WaterfallVerdict.UNDEFINED
    if cost_of_revenue is None or gross_profit is None:
        return WaterfallVerdict.UNDEFINED
    # No genuine COGS magnitude => not a real waterfall (claims/interest booked elsewhere).
    if abs(cost_of_revenue) < _MIN_COR_FRACTION * total_revenue:
        return WaterfallVerdict.UNDEFINED
    # Consistency: gross_profit must equal revenue - cost_of_revenue within tolerance.
    expected_gp = total_revenue - cost_of_revenue
    if abs(gross_profit - expected_gp) > _WATERFALL_REL_TOL * total_revenue:
        return WaterfallVerdict.UNDEFINED
    if gross_profit <= 0:
        return WaterfallVerdict.DEFINED_NEGATIVE
    return WaterfallVerdict.DEFINED
```

- [ ] **Step 4: Run, verify pass.**

- [ ] **Step 5: Commit** — `git commit -am "Add waterfall-shape margin discriminator (Punkt 2 Gate-A)"`

---

### Task 0.3: Sektor-Bucket-Resolver (feinster GICS-Knoten mit n_min, Roll-up)

**Files:**
- Create: `app/screener/sector_buckets.py`
- Test: `tests/screener/test_sector_buckets.py`

Interface stabil gegenüber der Taxonomie-Quelle: der Resolver nimmt eine **bereits ermittelte
GICS-Knoten-Kette** (feinste→gröbste) je Ticker und eine Populations-Zählung je Knoten; er wählt
den feinsten Knoten mit `n >= n_min`. Quelle der Kette (`.info` vs. Mapping-Layer) ist in Phase A
geklärt und außerhalb dieses reinen Resolvers (Task C1/CT-B verdrahten die Quelle).

- [ ] **Step 1: Failing test**

```python
# tests/screener/test_sector_buckets.py
from app.screener.sector_buckets import resolve_bucket


def test_picks_finest_node_meeting_n_min():
    # chain finest->coarsest; counts per node; n_min=5
    chain = ["Apparel Retail", "Retailing", "Consumer Discretionary"]
    counts = {"Apparel Retail": 3, "Retailing": 9, "Consumer Discretionary": 40}
    assert resolve_bucket(chain, counts, n_min=5) == "Retailing"


def test_rolls_up_to_sector_when_all_thin_below():
    chain = ["Apparel Retail", "Retailing", "Consumer Discretionary"]
    counts = {"Apparel Retail": 1, "Retailing": 2, "Consumer Discretionary": 40}
    assert resolve_bucket(chain, counts, n_min=5) == "Consumer Discretionary"


def test_returns_none_when_even_sector_too_thin():
    # fail-safe: no bucket clears n_min -> None -> relative arm will not fire
    chain = ["Apparel Retail", "Retailing", "Consumer Discretionary"]
    counts = {"Apparel Retail": 1, "Retailing": 2, "Consumer Discretionary": 3}
    assert resolve_bucket(chain, counts, n_min=5) is None


def test_empty_chain_returns_none():
    assert resolve_bucket([], {}, n_min=5) is None
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement**

```python
# app/screener/sector_buckets.py
"""Sector bucket resolution: pick the finest GICS node that clears a population
threshold n_min, rolling up finest->coarsest. Returns None when no node clears
n_min — the dual-arm gate then simply does not fire its relative arm (fail-safe
by construction, spec §4)."""
from __future__ import annotations


def resolve_bucket(
    node_chain: list[str],
    counts: dict[str, int],
    n_min: int,
) -> str | None:
    """node_chain is finest->coarsest (e.g. [sub_industry, industry, group, sector]).
    Returns the finest node with counts[node] >= n_min, else None."""
    for node in node_chain:
        if counts.get(node, 0) >= n_min:
            return node
    return None
```

- [ ] **Step 4: Run, verify pass.**

- [ ] **Step 5: Commit** — `git commit -am "Add sector bucket resolver with n_min roll-up (Punkt 2)"`

---

# Phase A — Gate-A Kalibrierung (Kette A1→A2→A3, $0)

> Skripte folgen dem Punkt-1-Diagnose-Muster: Docstring mit Invocation, `data/universe.json`
> (Liste von Ticker-Strings) laden, `build_screener_pipeline()` (warmer Cache) + `YFinanceClientImpl()`
> (roh), pro Ticker `get_ticker_info` → `ScreenerRecord.from_yfinance_info`, Befunde nach stdout +
> Artefakt-Markdown. Kein Gemini, $0. Aufruf: `uv run python scripts\<name>.py`.
> **Cold-Disziplin:** vor dem verbindlichen Lauf beide Caches purgen (s. Punkt-1-Ops-Skripte)
> — warme Caches maskieren ([[prod-logging-dormant-and-cache-masks-verification]]).

### Task A1 (Kette Schritt 1): Definiertheits-/Wasserfall-Probe

**Files:**
- Create: `scripts/diagnose_gross_margin_definedness.py`
- Output: `docs/superpowers/audits/2026-06-09-2-gross-margin-floor/calibration.md` (Abschnitt A1)

- [ ] **Step 1: Skript bauen.** Logik:
  1. Universum laden; pro Ticker `ScreenerRecord.from_yfinance_info`.
  2. **Korb bilden:** alle Financials/REITs (per `gics_sector`) + alle `gm <= 0` + die real-positiv-gm-Financials (die „~29").
  3. Für jeden Korb-Ticker `yf_raw.get_annual_statements(ticker)[0]` (income_stmt) holen; via `_row`-Muster `"Total Revenue"`, `"Cost Of Revenue"`, `"Gross Profit"` der jüngsten Spalte extrahieren; `cost_of_revenue_present = "Cost Of Revenue" in income.index`.
  4. `classify_waterfall(...)` aufrufen → Verdikt je Ticker.
  5. **Beide Kanten zählen:** (a) Null-Kante: gibt es einen `gm<=0`-Ticker mit `DEFINED_NEGATIVE` (= realer Industrie-Negativmarger, kein Financial)? (b) Positiv-Kante: gibt es einen `gm>0`-Financial/REIT mit `UNDEFINED` (= spuriös-positiv)?
  6. stdout + Markdown: Tabelle Ticker/sector/gm/.info/Verdikt; die beiden Kanten-Zählungen explizit; die finale METRIK_NA-Ausschlussmenge.

- [ ] **Step 2: Skript ausführen** (Stephans Go, cold): `uv run python scripts\diagnose_gross_margin_definedness.py`

- [ ] **Step 3: ENTSCHEIDUNG (Prädikat fixieren) — STOP-Gate.**
  - **Beide Kanten leer** → Default `.info`-only bleibt (Property A NICHT gekippt). Kein Runtime-income_stmt-Fetch. Phase B baut `.info`-only.
  - **Eine Kante nicht-leer** → Property A kippt → **CT-A aktivieren** (Wasserfall-Diskriminator in den Runtime-Basis-Filter). Zusätzlich, falls die Positiv-Kante NICHT rein strukturell trennt → schmaler Sub-Industry-Cross-Check (Property C, CT-A-Variante).
  - Befund + Entscheidung in `calibration.md` festhalten (honest-label).

---

### Task A2 (Kette Schritt 2): Sektor-Median-Table auf bereinigtem Universum

**Files:**
- Create: `scripts/diagnose_sector_median_table.py`
- Output: `data/sector_median_table.json` (Kandidat) + `calibration.md` (Abschnitt A2)

> **Reihenfolge-Pflicht:** läuft NACH A1; nutzt die A1-METRIK_NA-Ausschlussmenge → die Mediane werden
> NUR über Fisher-taugliche Titel gebildet (sonst kontaminieren gm=0/spuriös-positiv die Mediane).

- [ ] **Step 1: GICS-Nest-Vorbedingung prüfen.** Für eine Stichprobe (und aggregiert) prüfen, ob `.info` einen verlässlichen **verschachtelten** GICS-Baum trägt (mehr als nur `sector`+`industry`; ein wohldefinierter Parent je `industry`). Befund: trägt der Nest? Falls NEIN → **CT-B aktivieren** (Ticker→GICS-Knoten-Mapping-Layer); der Table-Bau bis dahin auf der gröbsten verlässlichen Ebene. Befund sichtbar in `calibration.md` (nicht stiller Sektor-Default).
- [ ] **Step 2: Knoten-Ketten + Counts bilden.** Pro Fisher-tauglichem Ticker die GICS-Knoten-Kette (feinste→Sektor) bestimmen (aus `.info` bzw. CT-B-Mapping); `counts` je Knoten über das bereinigte Universum aggregieren.
- [ ] **Step 3: n_min wählen + Buckets resolven.** `resolve_bucket(chain, counts, n_min)` je Ticker; n_min sanity-gecheckt an Within-Bucket-Streuung/Multimodalität (Within-Bucket-Histogramm je Knoten ausgeben; n_min so, dass Buckets unimodal genug sind).
- [ ] **Step 4: Median je Bucket** über `gross_margin` der bereinigten Titel; Table-JSON schreiben:

```json
{
  "schema_version": 1,
  "vintage": "2026-06",
  "n_min": 8,
  "entries": { "Retailing": 0.27, "Automobiles & Components": 0.18, "...": 0.0 }
}
```
- [ ] **Step 5: Befund** in `calibration.md` (Abschnitt A2): Nest-Verdikt, n_min, Buckets+Counts+Median, Multimodalitäts-Sanity.

---

### Task A3 (Kette Schritt 3): k-Kalibrierung

**Files:**
- Create: `scripts/diagnose_k_calibration.py`
- Output: `calibration.md` (Abschnitt A3) + finaler `k`-Wert

> Läuft NACH A2; nutzt den bereinigten Table.

- [ ] **Step 1: k-Sweep.** Für k ∈ {0.3, 0.4, 0.5, 0.6, 0.7}: pro Fisher-tauglichem Ticker `gm >= k × median(bucket)` auswerten (nur dort, wo `gm < 0.30`, d.h. der relative Arm überhaupt greift). Ausgeben: Sub-k-Band-Zusammensetzung je k.
- [ ] **Step 2: Akzeptanzkriterium prüfen** (gespiegelt von Mechanismus 1): **das Sub-k-Band muss von echten Kaputt-Margern dominiert und in gesunden Sektoren nahezu leer sein.** Die geretteten Niedrigmargen-Namen (erwartet: Colruyt/DIA/Maersk/NVR …) namentlich auflisten je k.
- [ ] **Step 3: k fixieren** — der größte k, der die erwarteten Rettungen hält und das Sub-k-Band sauber lässt. In `calibration.md` begründen (strukturell, nicht N-Namen-optimiert — Punkt-1-Disziplin). **Reversibilitäts-Trigger + Kanarienvögel** (unterste gerettete Margen-Titel je Bucket) namentlich notieren.

---

# Phase B — Mechanismus 1: METRIK_NA-Divert (Default `.info`-only, TDD)

### Task B1: `ReasonCode.FRAMEWORK_METRIK_NA` + Funnel-Mapping

**Files:**
- Modify: `app/screener/funnel.py` (ReasonCode-Enum + `_BASIS_REASON`)
- Test: `tests/screener/test_funnel.py`

- [ ] **Step 1: Failing test** — METRIK_NA-Dropout bekommt eigenen Eimer:

```python
def test_metrik_na_maps_to_framework_bucket():
    from app.screener.funnel import _BASIS_REASON, ReasonCode
    assert _BASIS_REASON["metric_na"] is ReasonCode.FRAMEWORK_METRIK_NA
```

- [ ] **Step 2: Run, verify fail** (KeyError / AttributeError).
- [ ] **Step 3: Implement** — in `funnel.py` ReasonCode erweitern und Mapping ergänzen:

```python
class ReasonCode(str, Enum):
    # ... bestehende ...
    GATE_GROSS_MARGIN = "GATE_GROSS_MARGIN"
    FRAMEWORK_METRIK_NA = "FRAMEWORK_METRIK_NA"   # Fisher-Raster nicht anwendbar (gm strukturell undefiniert)
    # ... rest ...

_BASIS_REASON: dict[str, ReasonCode] = {
    "avg_volume": ReasonCode.GATE_VOLUME,
    "market_cap": ReasonCode.GATE_MARKET_CAP,
    "metric_na": ReasonCode.FRAMEWORK_METRIK_NA,
    "gross_margin": ReasonCode.GATE_GROSS_MARGIN,
    "revenue_growth": ReasonCode.GATE_REVENUE_GROWTH,
}
```

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "Add FRAMEWORK_METRIK_NA reason code + funnel mapping (Punkt 2)"`

---

### Task B2: METRIK_NA-Divert in `_get_fail_reason` (vor gross_margin)

**Files:**
- Modify: `app/screener/filters.py`
- Test: `tests/screener/test_filters.py`

- [ ] **Step 1: Failing test** — eine undefinierte gm wird zu `metric_na`, NICHT `gross_margin`:

```python
def test_undefined_margin_diverts_to_metric_na_not_gross_margin():
    rec = _record(ticker="BANK", gross_margin=0.0)   # bank artifact
    apply_basis_filters([rec])
    assert rec.filter_failed_reason == "metric_na"

def test_negative_margin_diverts_to_metric_na_info_only():
    rec = _record(ticker="X", gross_margin=-0.1)
    apply_basis_filters([rec])
    assert rec.filter_failed_reason == "metric_na"

def test_low_but_defined_margin_still_fails_gross_margin():
    rec = _record(ticker="LOW", gross_margin=0.10)   # defined, below 30%, no rescue yet
    apply_basis_filters([rec])
    assert rec.filter_failed_reason == "gross_margin"
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** — in `filters.py` Prädikat importieren + Divert vor dem gross_margin-Check:

```python
from app.screener.metric_definedness import is_gross_margin_undefined_info_only

def _get_fail_reason(record: ScreenerRecord) -> str | None:
    if not passes_volume_filter(record):
        return "avg_volume"
    if not passes_market_cap_filter(record):
        return "market_cap"
    if is_gross_margin_undefined_info_only(record):
        return "metric_na"
    if not passes_gross_margin_filter(record):
        return "gross_margin"
    if not passes_revenue_growth_filter(record):
        return "revenue_growth"
    return None
```

> Hinweis: `passes_gross_margin_filter` behält den `None`-Guard (defensiv), wird aber für undefinierte gm
> nicht mehr erreicht. In Task C3 wird es zum Dual-Arm; der Divert bleibt davor.

- [ ] **Step 4: Run, verify pass.** Bestehende gross_margin-Tests bleiben grün (definierte Margen unberührt).
- [ ] **Step 5: Commit** — `git commit -am "Divert structurally-undefined gross margins to metric_na (Punkt 2 Mechanism 1)"`

---

# Phase C — Mechanismus 2: Dual-Arm-Floor (fail-safe-Sentinel, TDD)

### Task C1: Sektor-Median-Table-Typ + Sentinel-Konstanten

**Files:**
- Modify: `app/screener/filters.py` (Sentinel-Konstanten)
- Modify: `app/screener/sector_buckets.py` (Table-Typ + Median-Lookup)
- Test: `tests/screener/test_sector_buckets.py`

- [ ] **Step 1: Failing test** — Median-Lookup je Ticker über Resolver + Table:

```python
def test_sector_median_lookup_resolves_then_reads():
    from app.screener.sector_buckets import SectorMedianTable, bucket_median
    table = SectorMedianTable(entries={"Retailing": 0.27}, n_min=5,
                              counts={"Apparel Retail": 1, "Retailing": 9})
    chain = ["Apparel Retail", "Retailing", "Consumer Discretionary"]
    assert bucket_median(chain, table) == 0.27

def test_sector_median_none_when_no_bucket():
    from app.screener.sector_buckets import SectorMedianTable, bucket_median
    table = SectorMedianTable(entries={}, n_min=5, counts={})
    assert bucket_median([], table) is None
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** — in `sector_buckets.py`:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class SectorMedianTable:
    entries: dict[str, float]   # bucket node -> median gross margin
    n_min: int
    counts: dict[str, int]      # bucket node -> population count (for resolution)

def bucket_median(node_chain: list[str], table: SectorMedianTable) -> float | None:
    bucket = resolve_bucket(node_chain, table.counts, table.n_min)
    if bucket is None:
        return None
    return table.entries.get(bucket)
```

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "Add SectorMedianTable type + bucket median lookup (Punkt 2)"`

---

### Task C2: Validierender Table-Loader (ADR-Muster, vintage-/schema-gestempelt)

**Files:**
- Create: `app/screener/sector_median_table.py`
- Test: `tests/screener/test_sector_median_table.py`

- [ ] **Step 1: Failing test**

```python
# tests/screener/test_sector_median_table.py
import json
import pytest
from app.errors import FilterConfigError
from app.screener.sector_median_table import load_sector_median_table, SECTOR_TABLE_SCHEMA_VERSION


def _write(tmp_path, payload):
    p = tmp_path / "sector_median_table.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p

def test_loads_valid_table(tmp_path):
    p = _write(tmp_path, {"schema_version": SECTOR_TABLE_SCHEMA_VERSION, "vintage": "2026-06",
                          "n_min": 8, "entries": {"Retailing": 0.27}})
    table = load_sector_median_table(p)
    assert table.entries["Retailing"] == 0.27
    assert table.n_min == 8

def test_missing_file_returns_none_sentinel(tmp_path):
    # fail-safe: absent table => None => relative arm dormant (NOT an error)
    assert load_sector_median_table(tmp_path / "absent.json") is None

def test_schema_mismatch_raises(tmp_path):
    p = _write(tmp_path, {"schema_version": 999, "vintage": "2026-06", "n_min": 8, "entries": {}})
    with pytest.raises(FilterConfigError):
        load_sector_median_table(p)

def test_non_numeric_entry_raises(tmp_path):
    p = _write(tmp_path, {"schema_version": SECTOR_TABLE_SCHEMA_VERSION, "vintage": "2026-06",
                          "n_min": 8, "entries": {"Retailing": "high"}})
    with pytest.raises(FilterConfigError):
        load_sector_median_table(p)
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** (mirror `app/deepdive/adr_table.py`; absent file = fail-safe `None`, malformed = raise):

```python
# app/screener/sector_median_table.py
"""Validating loader for the pinned, vintage-stamped sector-median reference table
(Punkt 2 Mechanism 2). Absent file => None (fail-safe: relative arm stays dormant).
Malformed/version-mismatched file => FilterConfigError (fail loud)."""
from __future__ import annotations

import json
from pathlib import Path

from app.errors import FilterConfigError
from app.screener.sector_buckets import SectorMedianTable

SECTOR_TABLE_SCHEMA_VERSION = 1
_DEFAULT_PATH = Path("data/sector_median_table.json")


def load_sector_median_table(path: Path | None = None) -> SectorMedianTable | None:
    p = path or _DEFAULT_PATH
    if not p.exists():
        return None  # fail-safe sentinel
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FilterConfigError(f"sector_median_table unreadable: {exc}") from exc
    if not isinstance(data, dict) or "entries" not in data:
        raise FilterConfigError("sector_median_table: missing 'entries'")
    if data.get("schema_version") != SECTOR_TABLE_SCHEMA_VERSION:
        raise FilterConfigError(
            f"sector_median_table schema {data.get('schema_version')} != {SECTOR_TABLE_SCHEMA_VERSION}"
        )
    entries = data["entries"]
    counts = data.get("counts", {})
    n_min = data.get("n_min")
    if not isinstance(entries, dict) or not isinstance(n_min, int):
        raise FilterConfigError("sector_median_table: bad entries/n_min")
    for node, med in entries.items():
        if not isinstance(med, (int, float)):
            raise FilterConfigError(f"sector_median_table: non-numeric median for {node!r}")
    return SectorMedianTable(entries={k: float(v) for k, v in entries.items()},
                             n_min=n_min, counts={k: int(v) for k, v in counts.items()})
```

> Hinweis: A2 schreibt zusätzlich `counts` ins JSON (für den Runtime-Resolver) — Table-Schema deckt das ab.

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "Add validating sector-median table loader, fail-safe absent (Punkt 2)"`

---

### Task C3: Dual-Arm-Gate (absolut ODER `k × Median`, fail-safe)

**Files:**
- Modify: `app/screener/filters.py`
- Test: `tests/screener/test_filters.py`

- [ ] **Step 1: Failing test** — Dual-Arm + Fail-Safe + Determinismus:

```python
from app.screener.sector_buckets import SectorMedianTable

def test_absolute_arm_passes_high_margin():
    assert passes_gross_margin_filter(_record(gross_margin=0.45), table=None) is True

def test_no_table_relative_arm_dormant_below_30():
    # fail-safe: kein Table -> nur 30%-Arm -> low-margin faellt
    assert passes_gross_margin_filter(_record(gross_margin=0.18, gics_sector="Consumer Discretionary"),
                                      table=None) is False

def test_relative_arm_rescues_low_margin_in_low_margin_sector():
    table = SectorMedianTable(entries={"Consumer Discretionary": 0.20}, n_min=1,
                              counts={"Consumer Discretionary": 40})
    # k=0.5 -> bar = 0.10; gm 0.18 >= 0.10 -> rescued
    rec = _record(gross_margin=0.18, gics_sector="Consumer Discretionary")
    assert passes_gross_margin_filter(rec, table=table, k=0.5) is True

def test_relative_arm_does_not_rescue_real_tail():
    table = SectorMedianTable(entries={"Consumer Discretionary": 0.20}, n_min=1,
                              counts={"Consumer Discretionary": 40})
    rec = _record(gross_margin=0.05, gics_sector="Consumer Discretionary")  # < 0.5*0.20
    assert passes_gross_margin_filter(rec, table=table, k=0.5) is False

def test_determinism_independent_of_peer_membership():
    # same record + same pinned table -> same verdict regardless of run composition
    table = SectorMedianTable(entries={"Consumer Discretionary": 0.20}, n_min=1,
                              counts={"Consumer Discretionary": 40})
    rec = _record(gross_margin=0.18, gics_sector="Consumer Discretionary")
    assert passes_gross_margin_filter(rec, table=table, k=0.5) is True
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** — Dual-Arm; Knoten-Kette aus dem Record ableiten (Default `.info`: `[gics_industry, gics_sector]`; CT-B erweitert die Kette):

```python
from app.screener.sector_buckets import SectorMedianTable, bucket_median

# Fail-loud-Sentinel bis Gate-A A3 k setzt. None => relativer Arm feuert nicht (fail-safe).
GROSS_MARGIN_RELATIVE_K: float | None = None

def _node_chain(record: ScreenerRecord) -> list[str]:
    return [n for n in (record.gics_industry, record.gics_sector) if n]

def passes_gross_margin_filter(
    record: ScreenerRecord,
    table: SectorMedianTable | None = None,
    k: float | None = None,
) -> bool:
    gm = record.gross_margin
    if gm is None:
        logger.warning("ticker=%s gross_margin missing", record.ticker)
        return False
    if gm >= MIN_GROSS_MARGIN:          # absolute arm
        return True
    # relative arm — fail-safe: dormant without a pinned table or calibrated k
    if table is None or k is None:
        return False
    median = bucket_median(_node_chain(record), table)
    if median is None:                  # thin sector / no valid reference -> no rescue
        return False
    return gm >= k * median
```

- [ ] **Step 4: Run, verify pass.** `_get_fail_reason` muss `table`/`k` durchreichen (Task C4).
- [ ] **Step 5: Commit** — `git commit -am "Add dual-arm sector-aware gross-margin floor, fail-safe (Punkt 2 Mechanism 2)"`

---

### Task C4: Table/k durch `apply_basis_filters` → `_get_fail_reason` durchreichen + compose-Factory

**Files:**
- Modify: `app/screener/filters.py` (`_get_fail_reason`, `apply_basis_filters` Signatur)
- Modify: `app/screener/compose.py` (`build_sector_median_table`)
- Modify: `app/screener/runner.py` (Table/k an `apply_basis_filters` übergeben)
- Test: `tests/screener/test_filters.py`, `tests/screener/conftest.py`

- [ ] **Step 1: Failing test** — `apply_basis_filters` nimmt Table/k und rettet:

```python
def test_apply_basis_filters_rescues_with_table(monkeypatch):
    from app.screener import filters
    table = SectorMedianTable(entries={"Consumer Discretionary": 0.20}, n_min=1,
                              counts={"Consumer Discretionary": 40})
    rec = _record(ticker="MAERSK", gross_margin=0.18, gics_sector="Consumer Discretionary")
    result = filters.apply_basis_filters([rec], sector_table=table, relative_k=0.5)
    assert rec.filter_passed_basis is True
    assert result and result[0].ticker == "MAERSK"
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement.**
  - `_get_fail_reason(record, table, k)` reicht an `passes_gross_margin_filter(record, table, k)` durch.
  - `apply_basis_filters(records, sector_table=None, relative_k=None)` — Defaults erhalten Rückwärtskompatibilität (fail-safe). Übergibt an `_get_fail_reason`.
  - `compose.py`: `build_sector_median_table()` ruft `load_sector_median_table()`; `build` der Pipeline reicht Table + `filters.GROSS_MARGIN_RELATIVE_K` an den Runner-Call.
  - `runner.py`: `run_basis_filter` / `run_filter_preview` rufen `apply_basis_filters(records, sector_table=..., relative_k=...)`.
  - `tests/screener/conftest.py`: autouse-Fixture analog `_calibrated_value_floor` — Tests laufen mit `table=None, k=None` (fail-safe) sofern nicht explizit gesetzt; ein Test, der den Sentinel braucht, setzt ihn zurück.

- [ ] **Step 4: Run, verify pass.** Volle Suite: `uv run python -m pytest -m "not integration"` → grün, Coverage ≥ 90 %.
- [ ] **Step 5: Commit** — `git commit -am "Wire sector table + k through basis filter and compose (Punkt 2)"`

---

# Phase D — Funnel-/Artefakt-Verdrahtung + Reconciliation

### Task D1: METRIK_NA als eigener Funnel-Eimer + Reconciliation-Test

**Files:**
- Test: `tests/screener/test_funnel.py`, `tests/output/test_funnel_artifacts.py`
- Modify (falls nötig): `app/screener/funnel.py`

> `build_funnel` mappt `filter_failed_reason` bereits über `_BASIS_REASON` (Task B1 ergänzt). METRIK_NA
> erscheint damit automatisch als eigener Dropout/Eimer und serialisiert nach CSV/JSON. Dieser Task
> verifiziert das end-to-end + die Reconciliation.

- [ ] **Step 1: Failing test** — METRIK_NA-Dropout zählt korrekt, Reconciliation hält:

```python
def test_metrik_na_dropout_is_own_bucket_and_reconciles():
    bank = _resolved("BANK", sector="Financials", basis_reason="metric_na")
    hit = _resolved("HIT", dims={"growth": 4, "profitability": 4})
    basis = BasisFilterResult(passed=[hit], unresolved=[], resolved=[bank, hit], degraded=[])
    summary, dropouts = build_funnel(universe=["BANK", "HIT"], basis=basis, scored=[hit],
                                     score_threshold=4.0, crosshits_min_dimensions=2)
    codes = [d.reason_code for d in dropouts]
    from app.screener.funnel import ReasonCode
    assert ReasonCode.FRAMEWORK_METRIK_NA in codes
    assert len(dropouts) + summary.stage(Stage.CROSSHITS).remaining == 2
```

- [ ] **Step 2: Run, verify fail or pass.** (Erwartet grün, wenn `_resolved`-Helper `basis_reason` durchreicht; sonst Helper/Mapping anpassen.)
- [ ] **Step 3: Falls nötig implementieren** (Helper/Mapping). Keine Logikänderung an `build_funnel` erwartet außer dem B1-Mapping.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "Verify METRIK_NA funnel bucket + reconciliation (Punkt 2)"`

---

# Phase E — Kalibrierte Werte committen + Gate-B Cold-Run

> **Stephans Go erforderlich** (Cold-Run berührt yfinance live; kein Gemini, $0 — aber verbindlich).

### Task E1: Kalibrierten Table + k committen

**Files:**
- Add: `data/sector_median_table.json` (aus A2, finalisiert)
- Modify: `app/screener/filters.py` (`GROSS_MARGIN_RELATIVE_K` von `None` auf den A3-Wert setzen)

- [ ] **Step 1:** `data/sector_median_table.json` (A2-Output, `schema_version`/`vintage`/`n_min`/`counts`/`entries`) committen.
- [ ] **Step 2:** `GROSS_MARGIN_RELATIVE_K = <A3-Wert>` setzen (Sentinel-Aufhebung). Kommentar mit Begründung + Verweis auf `calibration.md` (analog Punkt-1-Wertgate).
- [ ] **Step 3:** Suite grün halten; ein Test pinnt, dass `load_sector_median_table()` (Default-Pfad) jetzt einen Table liefert (nicht None).
- [ ] **Step 4: Commit** — `git commit -am "Activate Punkt-2 rescue arm: commit calibrated sector-median table + k"`

---

### Task E2: Gate-B Cold-Run-Akzeptanz

**Files:**
- Output: `docs/superpowers/audits/2026-06-09-2-gross-margin-floor/gateB_acceptance.md`

- [ ] **Step 1:** Beide Caches cold-purgen (Punkt-1-Ops-Skripte).
- [ ] **Step 2:** Cold-Dry-Run ($0): `POST /run/monthly?dry_run=true` via `gcloud run services proxy` + Trigger-Skript (Punkt-1-Muster) — ODER lokal gegen kalten Cache.
- [ ] **Step 3: Akzeptanz prüfen (zweiseitig, monoton):**
  - Survivor-Delta **rein additiv** (§6 Property B) — falls A1 einen defined-positive-gm-Financial nach METRIK_NA umklassifiziert hat: additiv **+ expliziter kleiner Financials-Drop-Satz** (mit Grund), kein vermischtes Ledger.
  - Geretteten Niedrigmargen-Namen **namentlich** present (Colruyt/DIA/Maersk/NVR …).
  - `FRAMEWORK_METRIK_NA`-Eimer **sichtbar + korrekt**: die erwarteten Financials/REITs raus über METRIK_NA (nicht gross_margin) ∧ **kein** Fisher-tauglicher Capital-Markets-Titel fälschlich als METRIK_NA.
  - Reconciliation schließt (Summe Funnel-Eimer = Universum).
- [ ] **Step 4:** Befund in `gateB_acceptance.md`; bei Grün → bereit für PR (Stephans Merge/Deploy-Go; main-Push gesperrt, PR + grüner `test`-Check).

---

# Kontingente Tasks (NUR falls Gate-A sie auslöst)

### Task CT-A: Wasserfall-Diskriminator in den Runtime-Basis-Filter (falls Property A kippt)

**Auslöser:** A1 findet eine nicht-leere Kante (realer Industrie-Negativmarger bei gm≤0 ODER spuriös-positiver Financial/REIT).

**Ansatz (eigener Mini-Plan bei Auslösung, da Daten-/Fetch-Kopplung an Punkt 3):**
- `is_gross_margin_undefined_info_only` durch einen Pfad ersetzen, der für Verdacht-Ticker `get_annual_statements()[0]` zieht, `classify_waterfall(...)` ruft und `UNDEFINED → metric_na`, `DEFINED_NEGATIVE → gross_margin`(FAIL), `DEFINED → weiter` mappt. Fetch über den Service-Layer (`income_stmt`), gecacht; Cost-Cap-bewusst (nur Verdacht-Korb, nicht das ganze Universum).
- Funktioniert die Positiv-Kante NICHT rein strukturell → schmaler Sub-Industry-Cross-Check ergänzen (Property C-Kontingenz).
- Tests: die drei §8-Pin-Fälle jetzt end-to-end durch den Basis-Filter (gemockter income_stmt).

### Task CT-B: GICS-Knoten-Mapping-Layer (falls Nest nicht trägt)

**Auslöser:** A2 findet, dass `.info` keinen verlässlichen verschachtelten GICS-Baum trägt (Yahoo-Flach-Taxonomie, fehlende Industry-Group).

**Ansatz (eigener Mini-Plan bei Auslösung):**
- Ticker→GICS-Knoten-Mapping-Tabelle (versions-kontrolliertes Datenartefakt, ADR-Loader-Muster) als Taxonomie-Quelle für `_node_chain` / die A2-Knoten-Ketten.
- `_node_chain(record)` aus der Mapping-Tabelle statt aus `.info` speisen (Seam stabil — nur die Quelle wechselt).
- Tests: Resolver bekommt eine echte 4-Ebenen-Kette; Multimodalitäts-Auflösung verifiziert.

---

## Self-Review

**Spec-Coverage:** Mechanismus 1 → Phase B (+ Klassifikator Phase 0/CT-A). Mechanismus 2 → Phase 0.3/C. Gate-A-Kette 1→2→3 → Phase A (Reihenfolge explizit). §6-Properties A/B/C → A1-STOP-Gate / E2-Akzeptanz / CT-A. Gate-B → E2. Out-of-Scope (Mechanismus 3, Punkt 3) → nicht im Plan. ✓

**Placeholder-Scan:** Kontingente Tasks (CT-A/CT-B) sind bewusst als auslöser-gated mit definiertem Seam + Ansatz markiert, nicht als „später" — sie werden nur bei Evidenz voll ausgeplant ([[external-filter-cache-poisoning-scoping-sentinel]]: „beobachteter Defekt, nicht hypothetisierter"). Kalibrierungs-Werte (k, n_min, Table) sind evidenz-delegiert an Gate-A, nicht blind gesetzt. ✓

**Typ-Konsistenz:** `WaterfallVerdict`, `SectorMedianTable`, `resolve_bucket`/`bucket_median`, `passes_gross_margin_filter(record, table, k)`, `is_gross_margin_undefined_info_only`, `ReasonCode.FRAMEWORK_METRIK_NA`, Reason-String `"metric_na"` — durchgängig identisch verwendet. ✓
