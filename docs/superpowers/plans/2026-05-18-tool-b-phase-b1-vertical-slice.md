# Tool B Phase B.1 — Vertical Slice: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One `uv run python -m app.deepdive deepdive NOVO-B.CO` produces a complete, decision-useful 15-Fisher-point Markdown dossier at `output/Watchlist/NOVO-B.CO_YYYY-MM-DD.md` from a single CLI call.

**Architecture:** Six-stage in-process pipeline (ADR-lookup → EDGAR-pull → filing-parse → quant-join → Gemini-synthesis → dossier). Trusted sources only (10-K/20-F + yfinance), no subagent isolation. Builds on the B.0 skeleton (`app/deepdive/` package, `DeepDiveError`, `load_adr_table`, argparse CLI). Service-Layer DI throughout (Protocol + compose builders, mocked in unit tests — no real network). Local-FS caches for filings (ADR-4) and multi-year quant (ADR-5a).

**Tech Stack:** Python 3.12, pydantic v2 (`extra="forbid"`), `html2text` (NEW dep — see Task 4 note), `google-genai` (Gemini Pro, `response_schema`), `tenacity` (reuse Tool-A retry), stdlib `json`/`re`/`pathlib`, pytest with DI mocks (`uv run python -m pytest`).

**Reference:** Spec `docs/superpowers/specs/2026-05-18-tool-b-phase-b1-design.md` (E1–E5, ADR-5, §4 pipeline, §5 data model, §6 render, §7 tasks). Master `docs/superpowers/brainstorm/2026-05-18-tool-b-master.md`.

**Constraints (CLAUDE.md):** Local invocation always `uv run python -m <module>` (SOPRA-EPDR blocks `.exe` shims); tests `uv run python -m pytest` (dev is a default group — no `--extra`); 90% coverage enforced centrally; `from __future__ import annotations` + full type hints; English code/commits (imperative); no `except Exception: pass`, fail loud; no real network in unit tests; never commit to `main`. `app/services/*` is omitted from coverage; **`app/deepdive/*` and `app/models/*` are NOT — they need tests to 90%**.

---

### Task 0: Branch + new dependency

**Files:** Modify `pyproject.toml`

- [ ] **Step 1: Create the branch**

```bash
git checkout main
git checkout -b feature/tool-b-b1-vertical-slice
git branch --show-current
```
Expected: `feature/tool-b-b1-vertical-slice`

- [ ] **Step 2: Add the `html2text` dependency**

Spec E1 mandates `html2text` for HTML→text (deliberate, discussed in brainstorm — lightweight, deterministic; rejected `unstructured` as too heavy). In `pyproject.toml`, add to the `[project] dependencies` list (after `"lxml>=6.1.0",`):

```toml
    "html2text>=2024.2.26",
```

- [ ] **Step 3: Sync and verify import**

Run: `uv sync`
Then: `uv run python -c "import html2text; print(html2text.__name__)"`
Expected: `html2text`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "Add html2text dependency for Tool B filing parser (spec E1)"
```

---

### Task 1: `DeepDiveRecord` data model

**Files:**
- Create: `app/models/deep_dive_record.py`
- Test: `tests/models/test_deep_dive_record.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/models/test_deep_dive_record.py`:

```python
import pytest
from pydantic import ValidationError

from app.models.deep_dive_record import (
    DeepDiveRecord,
    FisherPoint,
    PointInTimeQuant,
    QuantSnapshot,
    SourceCoverage,
)


def _valid_point(**over):
    base = dict(number=1, title="Marktpotential", rating=4,
                confidence="🟢", reasoning="Solide.", sources=["20-F §4"])
    base.update(over)
    return FisherPoint(**base)


def test_fisher_point_minimal_valid():
    p = _valid_point()
    assert p.number == 1 and p.rating == 4 and p.sources == ["20-F §4"]


def test_fisher_point_rejects_extra_field():
    with pytest.raises(ValidationError):
        FisherPoint(number=1, title="x", rating=3, confidence="🟡",
                    reasoning="r", sources=["x"], bogus=1)


def test_fisher_point_rating_out_of_range_rejected():
    with pytest.raises(ValidationError):
        _valid_point(rating=6)
    with pytest.raises(ValidationError):
        _valid_point(rating=0)


def test_fisher_point_confidence_must_be_marker():
    with pytest.raises(ValidationError):
        _valid_point(confidence="high")


def test_fisher_point_sources_not_empty():
    with pytest.raises(ValidationError):
        _valid_point(sources=[])


def test_fisher_point_reasoning_word_cap_70():
    with pytest.raises(ValidationError):
        _valid_point(reasoning=" ".join(["w"] * 71))


def test_fisher_point_inference_only_caps_confidence_to_yellow():
    # sources == ['Inferenz'] must force confidence != 🟢 (ADR-5c / spec §5)
    p = _valid_point(sources=["Inferenz"], confidence="🟢")
    assert p.confidence == "🟡"


def test_fisher_point_inference_only_keeps_red():
    p = _valid_point(sources=["Inferenz"], confidence="🔴")
    assert p.confidence == "🔴"


def test_quant_snapshot_defaults_allow_missing_optional():
    qs = QuantSnapshot(point_in_time=PointInTimeQuant(ticker="NOVO-B.CO"))
    assert qs.historical_series is None
    assert qs.trend_metrics is None
    assert qs.gemini_dimensions is None


def test_deep_dive_record_roundtrip_and_forbid_extra():
    rec = DeepDiveRecord(
        ticker="NOVO-B.CO", adr_ticker="NVO", cik="0000353278",
        form_type="20-F", filing_sections={"20-F_item5": "text"},
        section_flags={}, quant_snapshot=QuantSnapshot(
            point_in_time=PointInTimeQuant(ticker="NOVO-B.CO")),
        synthesis=[_valid_point(number=n) for n in range(1, 16)],
        source_coverage=SourceCoverage(),
    )
    assert len(rec.synthesis) == 15
    assert rec.generated_at is not None
    with pytest.raises(ValidationError):
        DeepDiveRecord(**{**rec.model_dump(), "nope": 1})


def test_deep_dive_record_form_type_literal():
    with pytest.raises(ValidationError):
        DeepDiveRecord(
            ticker="X", adr_ticker=None, cik="0000000001", form_type="8-K",
            filing_sections={}, section_flags={},
            quant_snapshot=QuantSnapshot(point_in_time=PointInTimeQuant(ticker="X")),
            synthesis=[], source_coverage=SourceCoverage(),
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/models/test_deep_dive_record.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.deep_dive_record'`

- [ ] **Step 3: Write the model**

Create `app/models/deep_dive_record.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Confidence = Literal["🟢", "🟡", "🔴"]


class FisherPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1, le=15)
    title: str
    rating: int = Field(ge=1, le=5)
    confidence: Confidence
    reasoning: str
    sources: list[str] = Field(min_length=1)

    @field_validator("reasoning")
    @classmethod
    def _reasoning_word_cap(cls, v: str) -> str:
        if len(v.split()) > 70:
            raise ValueError("reasoning exceeds 70-word cap")
        return v

    @model_validator(mode="after")
    def _inference_only_caps_confidence(self) -> FisherPoint:
        # ADR-5c / spec §5: sources == ['Inferenz'] => never 🟢 (cap at 🟡).
        if self.sources == ["Inferenz"] and self.confidence == "🟢":
            object.__setattr__(self, "confidence", "🟡")
        return self


class PointInTimeQuant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    name: str | None = None
    currency: str | None = None
    market_cap: float | None = None
    market_cap_eur: float | None = None
    price: float | None = None
    gics_sector: str | None = None
    gics_industry: str | None = None
    gross_margin: float | None = None
    revenue_growth_yoy: float | None = None
    operating_margin: float | None = None
    return_on_equity: float | None = None
    debt_to_equity: float | None = None


class HistoricalSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    financial_currency: str | None = None
    years: list[int] = Field(default_factory=list)
    revenue: list[float | None] = Field(default_factory=list)
    gross_margin: list[float | None] = Field(default_factory=list)
    operating_margin: list[float | None] = Field(default_factory=list)
    shares_outstanding: list[float | None] = Field(default_factory=list)
    buyback_cashflow: list[float | None] = Field(default_factory=list)


class TrendMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revenue_cagr_5y: float | None = None
    operating_margin_slope_5y: float | None = None
    dilution_pct_5y: float | None = None
    buyback_intensity_5y: float | None = None


class QuantSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point_in_time: PointInTimeQuant
    historical_series: HistoricalSeries | None = None
    trend_metrics: TrendMetrics | None = None
    gemini_dimensions: dict[str, Any] | None = None


class SourceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quant_pit_source: str = "unknown"          # "tool-a-cache" | "live-yfinance"
    gemini_dims: str = "absent"                # "present" | "absent (nicht im letzten Monatslauf)"
    historical: str = "absent"                 # "complete" | "partial (<5J)" | "absent"
    currency_note: str | None = None           # financialCurrency != listing currency
    edgar: str = "unknown"                     # e.g. "20-F via ADR"
    soft: str = "folgt B.3"
    sprache: str = "folgt B.4"
    insider: str = "folgt B.2"


class DeepDiveRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    adr_ticker: str | None
    cik: str
    form_type: Literal["10-K", "20-F"]
    filing_sections: dict[str, str]
    section_flags: dict[str, str]
    quant_snapshot: QuantSnapshot
    synthesis: list[FisherPoint]
    source_coverage: SourceCoverage
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/models/test_deep_dive_record.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add app/models/deep_dive_record.py tests/models/test_deep_dive_record.py
git commit -m "Add DeepDiveRecord model with inference-only confidence cap"
```

---

### Task 2: ADR resolver service

**Files:**
- Create: `app/deepdive/adr_resolver.py`
- Test: `tests/deepdive/test_adr_resolver.py`

Builds on B.0 `app/deepdive/adr_table.py::load_adr_table` (returns `dict[ticker → {adr_ticker, cik, form_type}]`).

- [ ] **Step 1: Write the failing tests**

Create `tests/deepdive/test_adr_resolver.py`:

```python
import pytest

from app.deepdive.adr_resolver import ADRResolver, ResolvedTicker
from app.errors import DeepDiveError


def _resolver(table=None):
    if table is None:
        table = {"NOVO-B.CO": {"adr_ticker": "NVO", "cik": "0000353278", "form_type": "20-F"}}
    return ADRResolver(table=table)


def test_resolves_eu_adr_entry():
    r = _resolver().resolve("NOVO-B.CO")
    assert r == ResolvedTicker(ticker="NOVO-B.CO", adr_ticker="NVO",
                               cik="0000353278", form_type="20-F")


def test_is_case_insensitive_on_ticker():
    assert _resolver().resolve("novo-b.co").cik == "0000353278"


def test_us_ticker_passthrough_when_not_in_table():
    # US ticker absent from ADR table -> passthrough, 10-K, no adr_ticker.
    r = _resolver().resolve("AAPL")
    assert r.adr_ticker is None
    assert r.form_type == "10-K"
    assert r.ticker == "AAPL"
    assert r.cik == ""  # CIK resolution for US passthrough is B.1-3's edgar concern


def test_unknown_eu_ticker_raises_actionable_error():
    with pytest.raises(DeepDiveError, match="not in the ADR table"):
        _resolver().resolve("SAP.DE")


def test_di_mockable_via_injected_table():
    r = ADRResolver(table={"X.CO": {"adr_ticker": "X", "cik": "0000000001",
                                    "form_type": "20-F"}})
    assert r.resolve("X.CO").adr_ticker == "X"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/deepdive/test_adr_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.deepdive.adr_resolver'`

- [ ] **Step 3: Write the resolver**

Create `app/deepdive/adr_resolver.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.errors import DeepDiveError

# Heuristic from negative-filters-status.md §3.1 / Master ADR-1: a "." in the
# ticker marks a non-US listing (e.g. NOVO-B.CO, SAP.DE). US tickers have none.
_EU_MARKER = "."


@dataclass(frozen=True)
class ResolvedTicker:
    ticker: str
    adr_ticker: str | None
    cik: str
    form_type: str


class ADRResolver:
    """Static ADR-table resolver (Master ADR-1). Dynamic resolution is B.2."""

    def __init__(self, table: dict[str, dict[str, str]]) -> None:
        self._table = {k.upper(): v for k, v in table.items()}

    def resolve(self, ticker: str) -> ResolvedTicker:
        key = ticker.upper()
        entry = self._table.get(key)
        if entry is not None:
            return ResolvedTicker(
                ticker=ticker,
                adr_ticker=entry["adr_ticker"],
                cik=entry["cik"],
                form_type=entry["form_type"],
            )
        if _EU_MARKER in ticker:
            raise DeepDiveError(
                f"Ticker {ticker} is not in the ADR table and looks non-US "
                f"(contains '{_EU_MARKER}'). Add an entry to data/adr_table.json "
                f"or pick a US-listed ticker. Dynamic ADR resolution is Phase B.2."
            )
        # US passthrough: 10-K, CIK resolved later by the EDGAR client (B.1-3).
        return ResolvedTicker(ticker=ticker, adr_ticker=None, cik="", form_type="10-K")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_adr_resolver.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/adr_resolver.py tests/deepdive/test_adr_resolver.py
git commit -m "Add ADR resolver with US passthrough and actionable EU error"
```

---

### Task 3: Filing fetcher + local filing cache (ADR-4)

**Files:**
- Modify: `app/services/edgar_client.py` (add `get_latest_annual_filing` to Protocol + Impl)
- Create: `app/deepdive/filing_cache.py`
- Test: `tests/services/test_edgar_client.py` (append), `tests/deepdive/test_filing_cache.py`

EDGAR submissions API: `https://data.sec.gov/submissions/CIK{cik10}.json` → `filings.recent` has parallel arrays `form`, `accessionNumber`, `primaryDocument`, `filingDate`. The primary document URL is `https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodashes}/{primaryDocument}`.

- [ ] **Step 1: Write the failing edgar tests (append to `tests/services/test_edgar_client.py`)**

```python
@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_latest_annual_filing_returns_text_for_20f(mock_httpx, mock_time):
    submissions = MagicMock()
    submissions.status_code = 200
    submissions.json.return_value = {
        "filings": {"recent": {
            "form": ["6-K", "20-F", "20-F"],
            "accessionNumber": ["0000-24-1", "0000353278-25-000020", "0000353278-24-000010"],
            "primaryDocument": ["a.htm", "novo-20f.htm", "old.htm"],
            "filingDate": ["2025-05-01", "2025-02-05", "2024-02-07"],
        }}
    }
    doc = MagicMock()
    doc.status_code = 200
    doc.text = "<html><body>ITEM 5. OPERATING REVIEW ...</body></html>"
    mock_httpx.get.side_effect = [submissions, doc]

    client = _make_client()
    result = client.get_latest_annual_filing("0000353278", "20-F")
    assert result.accession_number == "0000353278-25-000020"
    assert "OPERATING REVIEW" in result.document_text
    # newest 20-F chosen (first matching form in recent[] which is newest-first)
    doc_url = mock_httpx.get.call_args_list[1][0][0]
    assert "000035327825000020" in doc_url
    assert "novo-20f.htm" in doc_url


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_latest_annual_filing_missing_form_raises(mock_httpx, mock_time):
    submissions = MagicMock()
    submissions.status_code = 200
    submissions.json.return_value = {
        "filings": {"recent": {"form": ["6-K"], "accessionNumber": ["x"],
                               "primaryDocument": ["a.htm"], "filingDate": ["2025-01-01"]}}
    }
    mock_httpx.get.return_value = submissions
    client = _make_client()
    with pytest.raises(DataSourceError, match="no 10-K filing found"):
        client.get_latest_annual_filing("0000000001", "10-K")


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_latest_annual_filing_doc_fetch_failure_raises(mock_httpx, mock_time):
    submissions = MagicMock()
    submissions.status_code = 200
    submissions.json.return_value = {
        "filings": {"recent": {"form": ["10-K"], "accessionNumber": ["0001-25-1"],
                               "primaryDocument": ["k.htm"], "filingDate": ["2025-01-01"]}}
    }
    bad = MagicMock()
    bad.status_code = 404
    mock_httpx.get.side_effect = [submissions, bad]
    client = _make_client()
    with pytest.raises(DataSourceError, match="404"):
        client.get_latest_annual_filing("0000000001", "10-K")
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run python -m pytest tests/services/test_edgar_client.py -k latest_annual -v`
Expected: FAIL — `AttributeError: ... has no attribute 'get_latest_annual_filing'`

- [ ] **Step 3: Extend `app/services/edgar_client.py`**

Add the import + dataclass near the top (after `logger = logging.getLogger(__name__)`):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RawFiling:
    accession_number: str
    document_text: str
```

Add to the `EdgarClient` Protocol:

```python
    def get_latest_annual_filing(self, cik: str, form_type: str) -> RawFiling: ...
```

Add this method to `EdgarClientImpl` (uses the existing rate-limited `self._get` for JSON; add a raw text getter — note `self._get` returns `.json()`, so add a sibling for text):

```python
    def _get_text(self, url: str) -> str:
        time.sleep(self._RATE_LIMIT_SECONDS)
        try:
            resp = httpx.get(url, headers=self._headers, timeout=60)
        except Exception as exc:
            raise DataSourceError(f"EDGAR HTTP request failed: {exc}") from exc
        if resp.status_code != 200:
            raise DataSourceError(f"EDGAR returned {resp.status_code} for {url}")
        return resp.text

    def get_latest_annual_filing(self, cik: str, form_type: str) -> RawFiling:
        padded = cik.zfill(10)
        data = self._get(f"{self._SEC_BASE}/submissions/CIK{padded}.json")
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        for form, accession, primary in zip(forms, accessions, primary_docs):
            if form == form_type:
                cik_int = str(int(cik))
                acc_nodash = accession.replace("-", "")
                url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{cik_int}/{acc_nodash}/{primary}"
                )
                text = self._get_text(url)
                return RawFiling(accession_number=accession, document_text=text)
        raise DataSourceError(
            f"no {form_type} filing found for CIK {padded} in recent submissions"
        )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run python -m pytest tests/services/test_edgar_client.py -k latest_annual -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing filing-cache tests**

Create `tests/deepdive/test_filing_cache.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.deepdive.filing_cache import CachedFilingFetcher
from app.services.edgar_client import RawFiling


def _fetcher(tmp_path, ttl_days=30):
    edgar = MagicMock()
    edgar.get_latest_annual_filing.return_value = RawFiling("acc-1", "FILING TEXT")
    return CachedFilingFetcher(edgar=edgar, cache_dir=tmp_path, ttl_days=ttl_days), edgar


def test_miss_fetches_and_writes_cache(tmp_path):
    fetcher, edgar = _fetcher(tmp_path)
    r = fetcher.get("0000353278", "20-F")
    assert r.document_text == "FILING TEXT"
    edgar.get_latest_annual_filing.assert_called_once_with("0000353278", "20-F")
    assert (tmp_path / "0000353278" / "acc-1.txt").exists()


def test_hit_skips_edgar(tmp_path):
    fetcher, edgar = _fetcher(tmp_path)
    fetcher.get("0000353278", "20-F")
    fetcher.get("0000353278", "20-F")
    assert edgar.get_latest_annual_filing.call_count == 1


def test_expired_cache_refetches(tmp_path):
    fetcher, edgar = _fetcher(tmp_path, ttl_days=30)
    fetcher.get("0000353278", "20-F")
    meta = tmp_path / "0000353278" / "_meta.json"
    stale = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    meta.write_text(f'{{"20-F": {{"_cached_at": "{stale}", "accession": "acc-1"}}}}',
                    encoding="utf-8")
    fetcher.get("0000353278", "20-F")
    assert edgar.get_latest_annual_filing.call_count == 2


def test_no_cache_flag_bypasses_cache(tmp_path):
    fetcher, edgar = _fetcher(tmp_path)
    fetcher.get("0000353278", "20-F")
    fetcher.get("0000353278", "20-F", use_cache=False)
    assert edgar.get_latest_annual_filing.call_count == 2
```

- [ ] **Step 6: Run to verify fail**

Run: `uv run python -m pytest tests/deepdive/test_filing_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.deepdive.filing_cache'`

- [ ] **Step 7: Write `app/deepdive/filing_cache.py`**

```python
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.edgar_client import RawFiling

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient

logger = logging.getLogger(__name__)


class CachedFilingFetcher:
    """Local-FS filing cache (Master ADR-4). cache/filings/<cik>/<accession>.txt
    with a per-cik _meta.json holding {form_type: {_cached_at, accession}}."""

    def __init__(self, edgar: EdgarClient, cache_dir: Path, ttl_days: int = 30) -> None:
        self._edgar = edgar
        self._cache_dir = Path(cache_dir)
        self._ttl_days = ttl_days

    def get(self, cik: str, form_type: str, use_cache: bool = True) -> RawFiling:
        cik_dir = self._cache_dir / cik
        meta_path = cik_dir / "_meta.json"
        if use_cache and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            entry = meta.get(form_type)
            if entry and self._fresh(entry["_cached_at"]):
                doc = cik_dir / f"{entry['accession']}.txt"
                if doc.exists():
                    logger.info("filing cache hit: cik=%s form=%s", cik, form_type)
                    return RawFiling(entry["accession"], doc.read_text(encoding="utf-8"))

        filing = self._edgar.get_latest_annual_filing(cik, form_type)
        if use_cache:
            cik_dir.mkdir(parents=True, exist_ok=True)
            (cik_dir / f"{filing.accession_number}.txt").write_text(
                filing.document_text, encoding="utf-8"
            )
            meta = {}
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta[form_type] = {
                "_cached_at": datetime.now(timezone.utc).isoformat(),
                "accession": filing.accession_number,
            }
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
        return filing

    def _fresh(self, cached_at: str) -> bool:
        ts = datetime.fromisoformat(cached_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).days < self._ttl_days
```

- [ ] **Step 8: Run to verify pass**

Run: `uv run python -m pytest tests/deepdive/test_filing_cache.py tests/services/test_edgar_client.py -v`
Expected: PASS (all)

- [ ] **Step 9: Commit**

```bash
git add app/services/edgar_client.py app/deepdive/filing_cache.py tests/services/test_edgar_client.py tests/deepdive/test_filing_cache.py
git commit -m "Add EDGAR annual-filing fetch and local-FS filing cache (ADR-4)"
```

---

### Task 4: Filing parser (hybrid, spec E1)

**Files:**
- Create: `app/deepdive/filing_parser.py`
- Test: `tests/deepdive/test_filing_parser.py`

Form-type sections (spec E1): **10-K** → items `1, 1A, 7, 7A, 8`; **20-F** → items `4, 5, 18`. Anchor regex case-insensitive, tolerant of `Item 5.` / `ITEM 5` / `Item 5 —` / `Item 5:`. Section = text between anchor N and the next recognized anchor. Per-section token cap via `FISHERSCREEN_DEEPDIVE_SECTION_TOKEN_CAP` (default 50000; token≈4 chars heuristic, no Gemini call here) → truncate with marker. Missing anchor → `section_flags[key] = "missing"`, not a crash.

- [ ] **Step 1: Write the failing tests**

Create `tests/deepdive/test_filing_parser.py`:

```python
from app.deepdive.filing_parser import parse_filing

_20F = """<html><body>
<p>ITEM 3. KEY INFORMATION risk text</p>
<p>Item 4. Information on the Company — business overview alpha</p>
<p>Item 5: Operating and Financial Review beta gamma</p>
<p>Item 18. Financial Statements delta</p>
<p>Item 19. Exhibits ignore</p>
</body></html>"""

_10K = """<html><body>
ITEM 1. BUSINESS one
ITEM 1A. RISK FACTORS two
ITEM 7. MANAGEMENT DISCUSSION three
ITEM 7A. MARKET RISK four
ITEM 8. FINANCIAL STATEMENTS five
ITEM 9. CONTROLS ignore
</body></html>"""


def test_parses_20f_target_sections():
    parsed = parse_filing(_20F, "20-F")
    assert set(parsed.sections) == {"20-F_item4", "20-F_item5", "20-F_item18"}
    assert "business overview alpha" in parsed.sections["20-F_item4"]
    assert "beta gamma" in parsed.sections["20-F_item5"]
    assert parsed.section_flags == {}


def test_parses_10k_target_sections():
    parsed = parse_filing(_10K, "10-K")
    assert set(parsed.sections) == {
        "10-K_item1", "10-K_item1A", "10-K_item7", "10-K_item7A", "10-K_item8"}
    assert "three" in parsed.sections["10-K_item7"]


def test_missing_section_is_flagged_not_crash():
    parsed = parse_filing("<html><body>Item 4. only this</body></html>", "20-F")
    assert "20-F_item4" in parsed.sections
    assert parsed.section_flags["20-F_item5"] == "missing"
    assert parsed.section_flags["20-F_item18"] == "missing"


def test_oversize_section_truncated_with_marker(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_DEEPDIVE_SECTION_TOKEN_CAP", "5")
    big = "Item 4. " + ("word " * 200) + "Item 5. tail Item 18. end"
    parsed = parse_filing(f"<html><body>{big}</body></html>", "20-F")
    assert "[... section truncated for token budget]" in parsed.sections["20-F_item4"]
    assert parsed.section_flags["20-F_item4"] == "truncated"


def test_toc_false_positive_skipped():
    # A table-of-contents line "Item 5 .... 42" before the real heading must not
    # end Item 4 prematurely; the real Item 5 body comes later.
    html = ("<html><body>Item 4. real four body. "
            "Item 5 ........ 42 "  # TOC dotted leader
            "Item 4. (continued) still four "
            "Item 5. real five body Item 18. eighteen</body></html>")
    parsed = parse_filing(html, "20-F")
    assert "real five body" in parsed.sections["20-F_item5"]
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run python -m pytest tests/deepdive/test_filing_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.deepdive.filing_parser'`

- [ ] **Step 3: Write `app/deepdive/filing_parser.py`**

```python
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

import html2text

logger = logging.getLogger(__name__)

_FORM_ITEMS: dict[str, list[str]] = {
    "10-K": ["1", "1A", "7", "7A", "8"],
    "20-F": ["4", "5", "18"],
}
_TRUNCATION_MARKER = "[... section truncated for token budget]"
_CHARS_PER_TOKEN = 4  # heuristic cap (no Gemini call in this stage)


@dataclass
class ParsedFiling:
    sections: dict[str, str] = field(default_factory=dict)
    section_flags: dict[str, str] = field(default_factory=dict)


def _section_token_cap() -> int:
    return int(os.environ.get("FISHERSCREEN_DEEPDIVE_SECTION_TOKEN_CAP", "50000"))


def _to_text(raw: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0
    return h.handle(raw)


def _anchor_re(item: str) -> re.Pattern[str]:
    # Tolerant: "Item 5." / "ITEM 5" / "Item 5 —" / "Item 5:" — escape "1A" etc.
    return re.compile(rf"\bITEM\s+{re.escape(item)}\b\s*[.:\-—]?", re.IGNORECASE)


def parse_filing(raw_document: str, form_type: str) -> ParsedFiling:
    items = _FORM_ITEMS[form_type]
    text = _to_text(raw_document)
    cap_chars = _section_token_cap() * _CHARS_PER_TOKEN
    result = ParsedFiling()

    # Collect every anchor occurrence for every target item, in document order.
    hits: list[tuple[int, str]] = []
    for item in items:
        for m in _anchor_re(item).finditer(text):
            hits.append((m.start(), item))
    hits.sort(key=lambda t: t[0])

    # For each item, take the LAST anchor whose slice (to the next anchor of any
    # target item) is non-trivial — skips short TOC dotted-leader false hits.
    starts: list[int] = [h[0] for h in hits]
    chosen: dict[str, tuple[int, int]] = {}
    for idx, (pos, item) in enumerate(hits):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
        body = text[pos:end]
        if len(body.strip()) < 40:  # TOC line / dotted leader — ignore
            continue
        chosen[item] = (pos, end)  # later real hit overwrites earlier

    for item in items:
        key = f"{form_type}_item{item}"
        if item not in chosen:
            result.section_flags[key] = "missing"
            logger.warning("filing parser: section %s missing", key)
            continue
        pos, end = chosen[item]
        body = text[pos:end].strip()
        if len(body) > cap_chars:
            body = body[:cap_chars] + "\n" + _TRUNCATION_MARKER
            result.section_flags[key] = "truncated"
            logger.warning("filing parser: section %s truncated", key)
        result.sections[key] = body
    return result
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run python -m pytest tests/deepdive/test_filing_parser.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/filing_parser.py tests/deepdive/test_filing_parser.py
git commit -m "Add hybrid filing parser with form-type switch and token cap"
```

---

### Task 5: Multi-year historical service + cache (ADR-5a)

**Files:**
- Create: `app/services/historical_data_service.py`
- Create: `app/deepdive/historical_cache.py`
- Test: `tests/services/test_historical_data_service.py`, `tests/deepdive/test_historical_cache.py`

Reuses `YFinanceClient` (B.0/Tool-A). yfinance `Ticker(t).income_stmt` / `.cashflow` / `.balance_sheet` return pandas DataFrames (rows = line items, columns = period-end dates). The service extracts up to 5 annual points into plain lists; graceful when partial (≥3 years → ok, else flag). Currency from `info.get("financialCurrency")`.

- [ ] **Step 1: Write the failing service tests**

Create `tests/services/test_historical_data_service.py`:

```python
from unittest.mock import MagicMock

import pandas as pd

from app.services.historical_data_service import HistoricalDataServiceImpl


def _yf_with_frames():
    yf = MagicMock()
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31"),
            pd.Timestamp("2022-12-31"), pd.Timestamp("2021-12-31"),
            pd.Timestamp("2020-12-31")]
    income = pd.DataFrame(
        {c: v for c, v in zip(cols, [
            {"Total Revenue": 1000, "Gross Profit": 800, "Operating Income": 400},
            {"Total Revenue": 900, "Gross Profit": 700, "Operating Income": 350},
            {"Total Revenue": 800, "Gross Profit": 600, "Operating Income": 300},
            {"Total Revenue": 700, "Gross Profit": 520, "Operating Income": 250},
            {"Total Revenue": 600, "Gross Profit": 450, "Operating Income": 200},
        ])}
    )
    cash = pd.DataFrame({c: {"Repurchase Of Capital Stock": -50} for c in cols})
    bal = pd.DataFrame({c: {"Share Issued": 2000} for c in cols})
    yf.get_annual_statements.return_value = (income, cash, bal)
    yf.get_ticker_info.return_value = {"financialCurrency": "DKK"}
    return yf


def test_extracts_five_year_series():
    svc = HistoricalDataServiceImpl(yfinance=_yf_with_frames())
    s = svc.get_annual_series("NOVO-B.CO")
    assert s["financial_currency"] == "DKK"
    assert s["years"] == [2024, 2023, 2022, 2021, 2020]
    assert s["revenue"] == [1000, 900, 800, 700, 600]
    assert s["shares_outstanding"] == [2000, 2000, 2000, 2000, 2000]
    assert s["buyback_cashflow"] == [-50, -50, -50, -50, -50]


def test_partial_series_when_fewer_years():
    yf = _yf_with_frames()
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31")]
    yf.get_annual_statements.return_value = (
        pd.DataFrame({c: {"Total Revenue": 100, "Gross Profit": 80,
                          "Operating Income": 40} for c in cols}),
        pd.DataFrame({c: {"Repurchase Of Capital Stock": 0} for c in cols}),
        pd.DataFrame({c: {"Share Issued": 1} for c in cols}),
    )
    svc = HistoricalDataServiceImpl(yfinance=yf)
    s = svc.get_annual_series("X")
    assert len(s["years"]) == 2
    assert s["complete"] is False  # <3 years


def test_empty_frames_yield_empty_series_no_crash():
    yf = MagicMock()
    yf.get_annual_statements.return_value = (
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    yf.get_ticker_info.return_value = {}
    svc = HistoricalDataServiceImpl(yfinance=yf)
    s = svc.get_annual_series("X")
    assert s["years"] == []
    assert s["complete"] is False
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run python -m pytest tests/services/test_historical_data_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Add `get_annual_statements` to `app/services/yfinance_client.py`**

Add to the `YFinanceClient` Protocol:

```python
    def get_annual_statements(self, ticker: str) -> Any: ...
```

Add to `YFinanceClientImpl`:

```python
    def get_annual_statements(self, ticker: str) -> Any:
        # Returns (income_stmt, cashflow, balance_sheet) DataFrames.
        try:
            t = yf.Ticker(ticker)
            return (t.income_stmt, t.cashflow, t.balance_sheet)
        except Exception as exc:
            raise DataSourceError(
                f"yfinance statements failed for {ticker}: {exc}"
            ) from exc
```

- [ ] **Step 4: Write `app/services/historical_data_service.py`**

```python
from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_MIN_COMPLETE_YEARS = 3
_MAX_YEARS = 5


class HistoricalDataService(Protocol):
    def get_annual_series(self, ticker: str) -> dict[str, Any]: ...


def _row(df: Any, label: str) -> dict[Any, float | None]:
    if df is None or getattr(df, "empty", True) or label not in df.index:
        return {}
    return df.loc[label].to_dict()


class HistoricalDataServiceImpl:
    """ADR-5a: live multi-year quant from yfinance. Graceful on partial data."""

    def __init__(self, yfinance: Any) -> None:
        self._yf = yfinance

    def get_annual_series(self, ticker: str) -> dict[str, Any]:
        income, cash, bal = self._yf.get_annual_statements(ticker)
        info = self._yf.get_ticker_info(ticker)

        cols = list(getattr(income, "columns", []))[:_MAX_YEARS]
        years = [c.year for c in cols]

        rev = _row(income, "Total Revenue")
        gp = _row(income, "Gross Profit")
        oi = _row(income, "Operating Income")
        bb = _row(cash, "Repurchase Of Capital Stock")
        sh = _row(bal, "Share Issued")

        def col(d: dict[Any, float | None], c: Any) -> float | None:
            v = d.get(c)
            return None if v is None else float(v)

        def margin(num: dict, c: Any) -> float | None:
            r, n = col(rev, c), col(num, c)
            if r in (None, 0) or n is None:
                return None
            return n / r

        series = {
            "financial_currency": info.get("financialCurrency"),
            "years": years,
            "revenue": [col(rev, c) for c in cols],
            "gross_margin": [margin(gp, c) for c in cols],
            "operating_margin": [margin(oi, c) for c in cols],
            "shares_outstanding": [col(sh, c) for c in cols],
            "buyback_cashflow": [col(bb, c) for c in cols],
            "complete": len(years) >= _MIN_COMPLETE_YEARS,
        }
        if not series["complete"]:
            logger.warning(
                "historical: %s only %d years (<%d) — flagged partial",
                ticker, len(years), _MIN_COMPLETE_YEARS,
            )
        return series
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run python -m pytest tests/services/test_historical_data_service.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Write the failing historical-cache tests**

Create `tests/deepdive/test_historical_cache.py`:

```python
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.deepdive.historical_cache import CachedHistoricalData


def _series():
    return {"financial_currency": "DKK", "years": [2024, 2023, 2022],
            "revenue": [1, 2, 3], "gross_margin": [0.8, 0.8, 0.8],
            "operating_margin": [0.4, 0.4, 0.4], "shares_outstanding": [9, 9, 9],
            "buyback_cashflow": [-1, -1, -1], "complete": True}


def _cd(tmp_path, ttl=90):
    svc = MagicMock()
    svc.get_annual_series.return_value = _series()
    return CachedHistoricalData(service=svc, cache_dir=tmp_path, ttl_days=ttl), svc


def test_miss_fetches_and_persists(tmp_path):
    cd, svc = _cd(tmp_path)
    assert cd.get_annual_series("NOVO-B.CO")["years"] == [2024, 2023, 2022]
    svc.get_annual_series.assert_called_once_with("NOVO-B.CO")
    payload = json.loads((tmp_path / "NOVO-B.CO.json").read_text(encoding="utf-8"))
    assert "_cached_at" in payload
    assert payload["financial_currency"] == "DKK"
    assert payload["series"]["years"] == [2024, 2023, 2022]


def test_fresh_hit_skips_service(tmp_path):
    cd, svc = _cd(tmp_path)
    cd.get_annual_series("X")
    cd.get_annual_series("X")
    assert svc.get_annual_series.call_count == 1


def test_expired_refetches(tmp_path):
    cd, svc = _cd(tmp_path, ttl=90)
    cd.get_annual_series("X")
    p = tmp_path / "X.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["_cached_at"] = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    p.write_text(json.dumps(data), encoding="utf-8")
    cd.get_annual_series("X")
    assert svc.get_annual_series.call_count == 2


def test_use_cache_false_bypasses(tmp_path):
    cd, svc = _cd(tmp_path)
    cd.get_annual_series("X")
    cd.get_annual_series("X", use_cache=False)
    assert svc.get_annual_series.call_count == 2
```

- [ ] **Step 7: Run to verify fail**

Run: `uv run python -m pytest tests/deepdive/test_historical_cache.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 8: Write `app/deepdive/historical_cache.py`**

```python
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CachedHistoricalData:
    """ADR-5a local-FS cache: cache/yfinance_historical/<TICKER>.json with an
    embedded _cached_at timestamp (Tool-A pattern), default 90-day TTL."""

    def __init__(self, service: Any, cache_dir: Path, ttl_days: int = 90) -> None:
        self._svc = service
        self._dir = Path(cache_dir)
        self._ttl_days = ttl_days

    def get_annual_series(self, ticker: str, use_cache: bool = True) -> dict[str, Any]:
        path = self._dir / f"{ticker}.json"
        if use_cache and path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if self._fresh(payload.get("_cached_at", "")):
                logger.info("historical cache hit: %s", ticker)
                return payload["series"]

        series = self._svc.get_annual_series(ticker)
        if use_cache:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({
                    "_cached_at": datetime.now(timezone.utc).isoformat(),
                    "financial_currency": series.get("financial_currency"),
                    "series": series,
                }),
                encoding="utf-8",
            )
        return series

    def _fresh(self, cached_at: str) -> bool:
        if not cached_at:
            return False
        ts = datetime.fromisoformat(cached_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).days < self._ttl_days
```

- [ ] **Step 9: Run to verify pass**

Run: `uv run python -m pytest tests/deepdive/test_historical_cache.py tests/services/test_historical_data_service.py -v`
Expected: PASS (all)

- [ ] **Step 10: Commit**

```bash
git add app/services/historical_data_service.py app/services/yfinance_client.py app/deepdive/historical_cache.py tests/services/test_historical_data_service.py tests/deepdive/test_historical_cache.py
git commit -m "Add multi-year historical service and local cache (ADR-5a)"
```

---

### Task 5a: Trend metrics (pure functions)

**Files:**
- Create: `app/deepdive/trend_metrics.py`
- Test: `tests/deepdive/test_trend_metrics.py`

No external calls. Series are newest-first (year[0] is most recent), matching the historical service output.

- [ ] **Step 1: Write the failing tests**

Create `tests/deepdive/test_trend_metrics.py`:

```python
import math

from app.deepdive.trend_metrics import (
    compute_buyback_intensity,
    compute_cagr,
    compute_dilution_pct,
    compute_margin_slope,
)


def test_cagr_basic_newest_first():
    # newest-first: [1464.1, 1000] over span 1 -> ~46.41%
    assert math.isclose(compute_cagr([1464.1, 1000.0]), 0.4641, abs_tol=1e-4)


def test_cagr_five_years():
    # 1000 -> 2000 over 4 year-steps
    assert math.isclose(compute_cagr([2000, 1500, 1300, 1100, 1000]),
                         2 ** (1 / 4) - 1, abs_tol=1e-6)


def test_cagr_none_when_insufficient_or_nonpositive():
    assert compute_cagr([100]) is None
    assert compute_cagr([]) is None
    assert compute_cagr([100, 0]) is None
    assert compute_cagr([100, None]) is None


def test_margin_slope_positive_trend_newest_first():
    # improving margins newest-first [0.5,0.4,0.3] -> positive slope per year
    s = compute_margin_slope([0.5, 0.4, 0.3])
    assert s is not None and s > 0


def test_margin_slope_none_when_too_few_points():
    assert compute_margin_slope([0.5]) is None
    assert compute_margin_slope([0.5, None]) is None


def test_dilution_pct_newest_vs_oldest():
    # shares grew 100 -> 110 (oldest->newest) = +10%
    assert math.isclose(compute_dilution_pct([110, 105, 100]), 0.10, abs_tol=1e-9)


def test_dilution_negative_means_buybacks():
    assert compute_dilution_pct([90, 95, 100]) < 0


def test_dilution_none_on_bad_input():
    assert compute_dilution_pct([100]) is None
    assert compute_dilution_pct([0, 100]) is None


def test_buyback_intensity_sum_over_marketcap():
    # cashflow repurchase entries are negative; intensity = |sum| / mcap
    assert math.isclose(
        compute_buyback_intensity([-50, -50, -50], market_cap=1000),
        150 / 1000, abs_tol=1e-9)


def test_buyback_intensity_none_when_no_mcap():
    assert compute_buyback_intensity([-50], market_cap=None) is None
    assert compute_buyback_intensity([], market_cap=1000) is None
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run python -m pytest tests/deepdive/test_trend_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `app/deepdive/trend_metrics.py`**

```python
from __future__ import annotations


def _clean(series: list[float | None]) -> list[float] | None:
    if not series or any(v is None for v in series):
        return None
    return [float(v) for v in series]  # type: ignore[arg-type]


def compute_cagr(revenue_newest_first: list[float | None]) -> float | None:
    s = _clean(revenue_newest_first)
    if s is None or len(s) < 2:
        return None
    newest, oldest = s[0], s[-1]
    if newest <= 0 or oldest <= 0:
        return None
    span = len(s) - 1
    return (newest / oldest) ** (1 / span) - 1


def compute_margin_slope(margin_newest_first: list[float | None]) -> float | None:
    s = _clean(margin_newest_first)
    if s is None or len(s) < 2:
        return None
    # x = years ascending oldest->newest (reverse of input order)
    ys = list(reversed(s))
    n = len(ys)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def compute_dilution_pct(shares_newest_first: list[float | None]) -> float | None:
    s = _clean(shares_newest_first)
    if s is None or len(s) < 2:
        return None
    newest, oldest = s[0], s[-1]
    if oldest == 0:
        return None
    return (newest - oldest) / oldest


def compute_buyback_intensity(
    buyback_cashflow_newest_first: list[float | None],
    market_cap: float | None,
) -> float | None:
    s = _clean(buyback_cashflow_newest_first)
    if s is None or not s or not market_cap:
        return None
    return abs(sum(s)) / market_cap
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run python -m pytest tests/deepdive/test_trend_metrics.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/trend_metrics.py tests/deepdive/test_trend_metrics.py
git commit -m "Add pure trend-metric functions (CAGR, slope, dilution, buyback)"
```

---

### Task 6: Quant join (Stage 4)

**Files:**
- Create: `app/deepdive/quant_join.py`
- Test: `tests/deepdive/test_quant_join.py`

Assembles `QuantSnapshot` + populates the quant part of `SourceCoverage`. Order (spec §4): **4a** point-in-time from Firestore `dev_ticker_cache` (miss → live `get_ticker_info` + marker), **4b** historical (sequential after 4a), **4c** trend metrics. Tool-A Gemini dims from Firestore `dev_gemini_scores`; absent → leave `None` + marker (ADR-5c, no live re-derivation).

- [ ] **Step 1: Write the failing tests**

Create `tests/deepdive/test_quant_join.py`:

```python
from unittest.mock import MagicMock

from app.deepdive.quant_join import build_quant_snapshot


def _deps(pit_cache=None, dims=None):
    firestore = MagicMock()
    firestore.get.side_effect = lambda coll, doc: (
        pit_cache if coll == "dev_ticker_cache" else dims
    )
    yfinance = MagicMock()
    yfinance.get_ticker_info.return_value = {
        "shortName": "Novo", "currency": "DKK", "marketCap": 3e11,
        "sector": "Healthcare", "grossMargins": 0.84}
    historical = MagicMock()
    historical.get_annual_series.return_value = {
        "financial_currency": "DKK", "years": [2024, 2023, 2022, 2021, 2020],
        "revenue": [5, 4, 3, 2, 1], "gross_margin": [0.84] * 5,
        "operating_margin": [0.45, 0.44, 0.43, 0.42, 0.41],
        "shares_outstanding": [100, 101, 102, 103, 104],
        "buyback_cashflow": [-10] * 5, "complete": True}
    return firestore, yfinance, historical


def test_pit_from_cache_when_present():
    fs, yf, hist = _deps(pit_cache={"shortName": "Novo Cached",
                                    "marketCap": 2.9e11, "currency": "DKK"},
                          dims={"dimensions": {"growth": 5}, "summary": "s"})
    qs, cov = build_quant_snapshot(
        "NOVO-B.CO", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.point_in_time.name == "Novo Cached"
    assert cov.quant_pit_source == "tool-a-cache"
    yf.get_ticker_info.assert_not_called()
    assert qs.gemini_dimensions == {"growth": 5}
    assert cov.gemini_dims == "present"


def test_pit_live_fallback_when_cache_miss():
    fs, yf, hist = _deps(pit_cache=None, dims=None)
    qs, cov = build_quant_snapshot(
        "NOVO-B.CO", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.point_in_time.name == "Novo"
    assert cov.quant_pit_source == "live-yfinance"
    assert qs.gemini_dimensions is None
    assert "nicht im letzten Monatslauf" in cov.gemini_dims


def test_trend_metrics_computed():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1000}, dims=None)
    qs, _ = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert qs.trend_metrics is not None
    assert qs.trend_metrics.revenue_cagr_5y is not None
    assert qs.trend_metrics.dilution_pct_5y < 0  # shares shrank 104->100


def test_currency_note_when_financial_currency_differs():
    fs, yf, hist = _deps(pit_cache={"currency": "USD", "marketCap": 1},
                          dims=None)
    qs, cov = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert cov.currency_note is not None
    assert "DKK" in cov.currency_note and "USD" in cov.currency_note


def test_partial_historical_flagged():
    fs, yf, hist = _deps(pit_cache={"marketCap": 1}, dims=None)
    hist.get_annual_series.return_value = {
        "financial_currency": "DKK", "years": [2024, 2023], "revenue": [2, 1],
        "gross_margin": [0.8, 0.8], "operating_margin": [0.4, 0.4],
        "shares_outstanding": [9, 9], "buyback_cashflow": [0, 0],
        "complete": False}
    _, cov = build_quant_snapshot(
        "X", firestore=fs, yfinance=yf, historical=hist,
        pit_collection="dev_ticker_cache", dims_collection="dev_gemini_scores")
    assert cov.historical.startswith("partial")
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run python -m pytest tests/deepdive/test_quant_join.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `app/deepdive/quant_join.py`**

```python
from __future__ import annotations

import logging
from typing import Any

from app.models.deep_dive_record import (
    HistoricalSeries,
    PointInTimeQuant,
    QuantSnapshot,
    SourceCoverage,
    TrendMetrics,
)
from app.deepdive.trend_metrics import (
    compute_buyback_intensity,
    compute_cagr,
    compute_dilution_pct,
    compute_margin_slope,
)

logger = logging.getLogger(__name__)


def _pit_from_info(ticker: str, info: dict[str, Any]) -> PointInTimeQuant:
    return PointInTimeQuant(
        ticker=ticker,
        name=info.get("shortName"),
        currency=info.get("currency"),
        market_cap=info.get("marketCap") or None,
        price=info.get("currentPrice") or info.get("regularMarketPrice"),
        gics_sector=info.get("sector"),
        gics_industry=info.get("industry"),
        gross_margin=info.get("grossMargins"),
        revenue_growth_yoy=info.get("revenueGrowth"),
        operating_margin=info.get("operatingMargins"),
        return_on_equity=info.get("returnOnEquity"),
        debt_to_equity=info.get("debtToEquity"),
    )


def build_quant_snapshot(
    ticker: str,
    *,
    firestore: Any,
    yfinance: Any,
    historical: Any,
    pit_collection: str,
    dims_collection: str,
) -> tuple[QuantSnapshot, SourceCoverage]:
    cov = SourceCoverage()

    # 4a — point-in-time (cache, else live)
    cached = firestore.get(pit_collection, ticker)
    if cached:
        info = {k: v for k, v in cached.items() if k != "_cached_at"}
        cov.quant_pit_source = "tool-a-cache"
    else:
        logger.warning("quant: %s not in %s — live yfinance fallback",
                        ticker, pit_collection)
        info = yfinance.get_ticker_info(ticker)
        cov.quant_pit_source = "live-yfinance"
    pit = _pit_from_info(ticker, info)

    # 4b — multi-year historical (sequential after 4a)
    raw = historical.get_annual_series(ticker)
    hist = HistoricalSeries(
        financial_currency=raw.get("financial_currency"),
        years=raw.get("years", []),
        revenue=raw.get("revenue", []),
        gross_margin=raw.get("gross_margin", []),
        operating_margin=raw.get("operating_margin", []),
        shares_outstanding=raw.get("shares_outstanding", []),
        buyback_cashflow=raw.get("buyback_cashflow", []),
    )
    cov.historical = "complete" if raw.get("complete") else (
        f"partial (<5J, {len(hist.years)}J)")
    fc = raw.get("financial_currency")
    if fc and pit.currency and fc != pit.currency:
        cov.currency_note = (
            f"financialCurrency {fc} != Listing-Währung {pit.currency}")

    # 4c — trend metrics
    trends = TrendMetrics(
        revenue_cagr_5y=compute_cagr(hist.revenue),
        operating_margin_slope_5y=compute_margin_slope(hist.operating_margin),
        dilution_pct_5y=compute_dilution_pct(hist.shares_outstanding),
        buyback_intensity_5y=compute_buyback_intensity(
            hist.buyback_cashflow, pit.market_cap),
    )

    # Tool-A Gemini dims (secondary, ADR-5c) — no live re-derivation
    dims_doc = firestore.get(dims_collection, ticker)
    if dims_doc and dims_doc.get("dimensions"):
        gemini_dimensions: dict[str, Any] | None = dims_doc["dimensions"]
        cov.gemini_dims = "present"
    else:
        gemini_dimensions = None
        cov.gemini_dims = "absent (nicht im letzten Monatslauf)"

    snapshot = QuantSnapshot(
        point_in_time=pit,
        historical_series=hist,
        trend_metrics=trends,
        gemini_dimensions=gemini_dimensions,
    )
    return snapshot, cov
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run python -m pytest tests/deepdive/test_quant_join.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/quant_join.py tests/deepdive/test_quant_join.py
git commit -m "Add Stage-4 quant join with cache/live fallback and coverage markers"
```

---

### Task 7: Fisher points constant + Gemini synthesis (Stage 5)

**Files:**
- Create: `app/deepdive/fisher_points.py`
- Create: `app/services/gemini_deepdive_client.py`
- Create: `app/deepdive/synthesis.py`
- Test: `tests/deepdive/test_fisher_points.py`, `tests/services/test_gemini_deepdive_client.py`, `tests/deepdive/test_synthesis.py`

- [ ] **Step 1: Write the failing fisher-points test**

Create `tests/deepdive/test_fisher_points.py`:

```python
from app.deepdive.fisher_points import FISHER_POINTS


def test_fifteen_points_numbered_1_to_15():
    assert [n for n, _ in FISHER_POINTS] == list(range(1, 16))


def test_titles_are_nonempty_strings():
    assert all(isinstance(t, str) and t for _, t in FISHER_POINTS)


def test_point_14_15_are_openness_and_integrity():
    titles = dict(FISHER_POINTS)
    assert "Offenheit" in titles[14]
    assert "Integrität" in titles[15]
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run python -m pytest tests/deepdive/test_fisher_points.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `app/deepdive/fisher_points.py`** (titles from V3 §14)

```python
from __future__ import annotations

from typing import Final

FISHER_POINTS: Final[tuple[tuple[int, str], ...]] = (
    (1, "Marktpotential für mehrjährige Umsatzzuwächse"),
    (2, "Management-Determination für neue Produkte/Services"),
    (3, "F&E-Effektivität relativ zur Größe"),
    (4, "Überdurchschnittliche Vertriebsorganisation"),
    (5, "Lohnende Gewinnmargen"),
    (6, "Maßnahmen zur Margen-Erhaltung/-Verbesserung"),
    (7, "Hervorragende Personal- und Arbeitsbeziehungen"),
    (8, "Hervorragende Beziehungen unter den Führungskräften"),
    (9, "Ausreichende Tiefe des Managements"),
    (10, "Kostenanalyse und Buchhaltungs-Kontrolle"),
    (11, "Branchenspezifische Wettbewerbsvorteile"),
    (12, "Kurz- vs. langfristiger Profit-Outlook"),
    (13, "Wachstum ohne signifikante Eigenkapital-Verwässerung"),
    (14, "Offenheit des Managements auch in schlechten Zeiten"),
    (15, "Unanfechtbare Integrität des Managements"),
)
```

- [ ] **Step 4: Write the failing gemini-deepdive-client tests**

Create `tests/services/test_gemini_deepdive_client.py`:

```python
import json
from unittest.mock import MagicMock, patch

import pytest

from app.errors import GeminiError
from app.services.gemini_deepdive_client import GeminiDeepDiveClient


def _client(model="gemini-2.5-pro"):
    with patch("app.services.gemini_deepdive_client._genai") as g:
        c = GeminiDeepDiveClient(api_key="k", model=model)
        return c, g


def test_raises_without_api_key():
    with pytest.raises(GeminiError, match="API key"):
        GeminiDeepDiveClient(api_key="", model="gemini-2.5-pro")


def test_token_cap_exceeded_raises_no_generate():
    c, g = _client()
    c._client.models.count_tokens.return_value = MagicMock(total_tokens=999)
    with pytest.raises(GeminiError, match="prompt too large"):
        c.synthesize("sys", "user", max_input_tokens=10)
    c._client.models.generate_content.assert_not_called()


def test_returns_parsed_json_on_success():
    c, g = _client()
    c._client.models.count_tokens.return_value = MagicMock(total_tokens=5)
    resp = MagicMock()
    resp.text = json.dumps({"points": [{"number": 1}]})
    resp.usage_metadata = MagicMock(prompt_token_count=5, candidates_token_count=3)
    c._client.models.generate_content.return_value = resp
    out = c.synthesize("sys", "user", max_input_tokens=100)
    assert out["points"] == [{"number": 1}]


def test_invalid_json_raises_geminierror():
    c, g = _client()
    c._client.models.count_tokens.return_value = MagicMock(total_tokens=5)
    resp = MagicMock()
    resp.text = "not json"
    c._client.models.generate_content.return_value = resp
    with pytest.raises(GeminiError, match="invalid JSON"):
        c.synthesize("sys", "user", max_input_tokens=100)


def test_safety_filtered_empty_text_raises():
    c, g = _client()
    c._client.models.count_tokens.return_value = MagicMock(total_tokens=5)
    resp = MagicMock()
    resp.text = None
    c._client.models.generate_content.return_value = resp
    with pytest.raises(GeminiError, match="empty response"):
        c.synthesize("sys", "user", max_input_tokens=100)
```

- [ ] **Step 5: Run to verify fail**

Run: `uv run python -m pytest tests/services/test_gemini_deepdive_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 6: Write `app/services/gemini_deepdive_client.py`** (reuses Tool-A retry pattern)

```python
from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from google import genai as _genai
from google.genai import types as _types
from google.genai.errors import ClientError, ServerError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.errors import GeminiError

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    return (isinstance(exc, ServerError) and exc.code == 503) or (
        isinstance(exc, ClientError) and exc.code == 429
    )


_RETRY = dict(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, exp_base=4),
    reraise=True,
)


class DeepDiveSynthesizer(Protocol):
    def synthesize(
        self, system_prompt: str, user_prompt: str, max_input_tokens: int
    ) -> dict[str, Any]: ...


class GeminiDeepDiveClient:
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise GeminiError(
                "Gemini API key not set — configure FISHERSCREEN_GEMINI_API_KEY"
            )
        self._client = _genai.Client(api_key=api_key)
        self._model = model

    def synthesize(
        self, system_prompt: str, user_prompt: str, max_input_tokens: int
    ) -> dict[str, Any]:
        full = f"{system_prompt}\n\n{user_prompt}"
        try:
            tok = self._count_tokens(full)
        except Exception as exc:
            raise GeminiError(f"token count failed: {exc}") from exc
        if tok.total_tokens > max_input_tokens:
            logger.warning(
                "deepdive prompt too large: %d > %d tokens",
                tok.total_tokens, max_input_tokens,
            )
            raise GeminiError(
                f"prompt too large: {tok.total_tokens} > {max_input_tokens} tokens"
            )
        try:
            resp = self._generate(system_prompt, user_prompt)
        except Exception as exc:
            raise GeminiError(f"Gemini API call failed: {exc}") from exc
        text = getattr(resp, "text", None)
        if not text:
            raise GeminiError("Gemini returned empty response (safety-filtered?)")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise GeminiError(f"Gemini returned invalid JSON: {exc}") from exc

    @retry(**_RETRY)
    def _count_tokens(self, prompt: str) -> Any:
        return self._client.models.count_tokens(model=self._model, contents=prompt)

    @retry(**_RETRY)
    def _generate(self, system_prompt: str, user_prompt: str) -> Any:
        return self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=_types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
            ),
        )
```

- [ ] **Step 7: Run to verify pass**

Run: `uv run python -m pytest tests/services/test_gemini_deepdive_client.py tests/deepdive/test_fisher_points.py -v`
Expected: PASS

- [ ] **Step 8: Write the failing synthesis tests**

Create `tests/deepdive/test_synthesis.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.deepdive.synthesis import run_synthesis
from app.errors import GeminiError
from app.models.deep_dive_record import PointInTimeQuant, QuantSnapshot


def _qs():
    return QuantSnapshot(point_in_time=PointInTimeQuant(ticker="NOVO-B.CO"))


def _good_points():
    pts = []
    for n in range(1, 16):
        pts.append({"number": n, "title": f"P{n}", "rating": 4,
                    "confidence": "🟢", "reasoning": "Solide Begründung.",
                    "sources": ["20-F §5"]})
    return {"points": pts}


def test_returns_15_fisher_points():
    syn = MagicMock()
    syn.synthesize.return_value = _good_points()
    pts = run_synthesis(
        ticker="NOVO-B.CO", form_type="20-F",
        sections={"20-F_item5": "rev"}, quant=_qs(),
        synthesizer=syn, max_input_tokens=200000)
    assert len(pts) == 15
    assert pts[0].number == 1


def test_hallucinated_section_downgraded_to_inference():
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["sources"] = ["20-F §99"]  # section never sent
    data["points"][0]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[0].sources == ["Inferenz"]
    assert pts[0].confidence == "🟡"  # capped by model validator


def test_inference_only_caps_confidence():
    syn = MagicMock()
    data = _good_points()
    data["points"][1]["sources"] = ["Inferenz"]
    data["points"][1]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[1].confidence == "🟡"


def test_wrong_point_count_raises():
    syn = MagicMock()
    bad = {"points": _good_points()["points"][:14]}
    syn.synthesize.return_value = bad
    with pytest.raises(GeminiError, match="expected 15"):
        run_synthesis(ticker="X", form_type="20-F",
                      sections={"20-F_item5": "x"}, quant=_qs(),
                      synthesizer=syn, max_input_tokens=200000)


def test_gemini_error_propagates():
    syn = MagicMock()
    syn.synthesize.side_effect = GeminiError("prompt too large")
    with pytest.raises(GeminiError, match="too large"):
        run_synthesis(ticker="X", form_type="20-F",
                      sections={"20-F_item5": "x"}, quant=_qs(),
                      synthesizer=syn, max_input_tokens=10)
```

- [ ] **Step 9: Run to verify fail**

Run: `uv run python -m pytest tests/deepdive/test_synthesis.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 10: Write `app/deepdive/synthesis.py`** (prompt build + post-hoc source validator)

```python
from __future__ import annotations

import logging
import re
from typing import Any

from app.deepdive.fisher_points import FISHER_POINTS
from app.errors import GeminiError
from app.models.deep_dive_record import FisherPoint, QuantSnapshot

logger = logging.getLogger(__name__)

_SECTION_CITE_RE = re.compile(r"(10-K|20-F)\s*§\s*(\w+)", re.IGNORECASE)

_SYSTEM_PROMPT = (
    "Du bewertest ein Unternehmen gegen Phil Fishers 15 Punkte. Für JEDEN der "
    "15 Punkte: rating 1-5, confidence einer von 🟢/🟡/🔴, reasoning 2-3 Sätze "
    "Prosa (max 70 Wörter), sources als Array von Markern. Marker sind genau: "
    "eine Filing-Section wie '20-F §5' oder '10-K §7' (NUR Sections die im "
    "Input wirklich vorkommen — erfinde KEINE), '[yfinance, 5J]' für Quant, "
    "oder 'Inferenz' wenn du mehrere Quellen ohne direkten Zitat-Pfad "
    "kombinierst. Bei reiner Inferenz ist confidence maximal 🟡. Punkte 14 und "
    "15 (Offenheit/Integrität) ohne Sprach-/Insider-Daten: confidence 🔴. "
    'Antworte NUR als JSON: {"points":[{"number":int,"title":str,"rating":int,'
    '"confidence":str,"reasoning":str,"sources":[str]}, ... 15 Einträge]}'
)


def _build_user_prompt(
    ticker: str, form_type: str, sections: dict[str, str], quant: QuantSnapshot
) -> str:
    titles = "\n".join(f"{n}. {t}" for n, t in FISHER_POINTS)
    sec_txt = "\n\n".join(
        f"### {k}\n{v}" for k, v in sections.items()
    ) or "(keine Filing-Sections extrahiert)"
    return (
        f"Ticker: {ticker} (Filing-Typ {form_type})\n\n"
        f"Fishers 15 Punkte:\n{titles}\n\n"
        f"Quant-Snapshot (JSON):\n{quant.model_dump_json()}\n\n"
        f"Filing-Sections:\n{sec_txt}"
    )


def run_synthesis(
    *,
    ticker: str,
    form_type: str,
    sections: dict[str, str],
    quant: QuantSnapshot,
    synthesizer: Any,
    max_input_tokens: int,
) -> list[FisherPoint]:
    system = _SYSTEM_PROMPT
    user = _build_user_prompt(ticker, form_type, sections, quant)
    data = synthesizer.synthesize(system, user, max_input_tokens)

    raw_points = data.get("points", [])
    if len(raw_points) != 15:
        raise GeminiError(
            f"synthesis returned {len(raw_points)} points, expected 15"
        )

    sent_keys = set(sections.keys())
    points: list[FisherPoint] = []
    for rp in raw_points:
        sources = list(rp.get("sources", []))
        validated = _validate_sources(sources, form_type, sent_keys)
        if validated != sources:
            logger.warning(
                "point %s: hallucinated section cite -> downgraded to Inferenz",
                rp.get("number"),
            )
            rp = {**rp, "sources": validated}
            if rp.get("confidence") == "🟢":
                rp["confidence"] = "🟡"
        points.append(FisherPoint(**rp))
    return points


def _validate_sources(
    sources: list[str], form_type: str, sent_keys: set[str]
) -> list[str]:
    """Any cited filing section not actually sent -> collapse to ['Inferenz']."""
    for s in sources:
        m = _SECTION_CITE_RE.search(s)
        if not m:
            continue
        item = m.group(2)
        key = f"{form_type}_item{item}"
        if key not in sent_keys:
            return ["Inferenz"]
    return sources
```

- [ ] **Step 11: Run to verify pass**

Run: `uv run python -m pytest tests/deepdive/test_synthesis.py -v`
Expected: PASS (5 tests)

- [ ] **Step 12: Commit**

```bash
git add app/deepdive/fisher_points.py app/services/gemini_deepdive_client.py app/deepdive/synthesis.py tests/deepdive/test_fisher_points.py tests/services/test_gemini_deepdive_client.py tests/deepdive/test_synthesis.py
git commit -m "Add Gemini deep-dive synthesis with post-hoc source validator"
```

---

### Task 8: Dossier generator (Stage 6)

**Files:**
- Create: `app/deepdive/dossier_generator.py`
- Test: `tests/deepdive/test_dossier_generator.py`

Render per spec §6: YAML frontmatter; `# Deep Dive: <name> (<ticker>)`; Executive Summary placeholder line; Bewertung line; **15 points each as a mini-block** (NOT a table); source_coverage section; empty "Stef's Notizen". Filename `output/Watchlist/<TICKER>_YYYY-MM-DD.md`. Uses the `frontmatter` lib (Tool-A idiom).

- [ ] **Step 1: Write the failing tests**

Create `tests/deepdive/test_dossier_generator.py`:

```python
import frontmatter

from app.deepdive.dossier_generator import generate_dossier
from app.models.deep_dive_record import (
    DeepDiveRecord, FisherPoint, PointInTimeQuant, QuantSnapshot, SourceCoverage)


def _record():
    pts = [FisherPoint(number=n, title=f"Punkt {n}", rating=4, confidence="🟢",
                       reasoning="Begründung.", sources=["20-F §5"])
           for n in range(1, 16)]
    return DeepDiveRecord(
        ticker="NOVO-B.CO", adr_ticker="NVO", cik="0000353278",
        form_type="20-F", filing_sections={"20-F_item5": "x"},
        section_flags={}, synthesis=pts,
        quant_snapshot=QuantSnapshot(point_in_time=PointInTimeQuant(
            ticker="NOVO-B.CO", name="Novo Nordisk")),
        source_coverage=SourceCoverage(edgar="20-F via ADR"))


def test_writes_file_with_date_name(tmp_path):
    p = generate_dossier(_record(), tmp_path)
    assert p.parent.name == "Watchlist"
    assert p.name.startswith("NOVO-B.CO_")
    assert p.name.endswith(".md")


def test_frontmatter_and_15_miniblocks(tmp_path):
    p = generate_dossier(_record(), tmp_path)
    post = frontmatter.loads(p.read_text(encoding="utf-8"))
    assert post["ticker"] == "NOVO-B.CO"
    assert post["form_type"] == "20-F"
    body = post.content
    for n in range(1, 16):
        assert f"### Punkt {n} —" in body
    assert "| # | Punkt |" not in body  # NOT a table
    assert "## Source Coverage" in body
    assert "20-F via ADR" in body
    assert "Stef's Notizen" in body


def test_each_point_renders_a_source_marker(tmp_path):
    p = generate_dossier(_record(), tmp_path)
    body = frontmatter.loads(p.read_text(encoding="utf-8")).content
    assert body.count("[20-F §5]") == 15
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run python -m pytest tests/deepdive/test_dossier_generator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `app/deepdive/dossier_generator.py`**

```python
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import frontmatter

from app.models.deep_dive_record import DeepDiveRecord

logger = logging.getLogger(__name__)

_STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}


def generate_dossier(record: DeepDiveRecord, output_dir: Path) -> Path:
    watch_dir = Path(output_dir) / "Watchlist"
    watch_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    out = watch_dir / f"{record.ticker}_{today}.md"

    pit = record.quant_snapshot.point_in_time
    name = pit.name or record.ticker
    cov = record.source_coverage

    lines: list[str] = [
        f"# Deep Dive: {name} ({record.ticker})",
        "",
        "## Executive Summary",
        "*[3 Sätze: Kern-These + Hauptrisiko + Empfehlung — von Gemini in B.1+ "
        "befüllt; B.1 Durchstich nutzt die 15 Mini-Blöcke als Substanz.]*",
        "",
        "## Bewertung",
        f"*Market Cap: {pit.market_cap or 'n/a'} {pit.currency or ''} · "
        f"Gross Margin: {pit.gross_margin or 'n/a'} · "
        f"Op. Margin: {pit.operating_margin or 'n/a'}*",
        "",
        "## Fishers 15 Punkte",
        "",
    ]
    for p in record.synthesis:
        marker = " ".join(f"[{s}]" for s in p.sources)
        lines += [
            f"### Punkt {p.number} — {p.title}",
            f"**Bewertung:** {_STARS.get(p.rating, '?')} · "
            f"**Confidence:** {p.confidence}",
            "",
            f"{p.reasoning} {marker}",
            "",
        ]

    lines += [
        "## Source Coverage",
        "",
        f"- EDGAR: {cov.edgar}",
        f"- Quant (Punkt-in-Zeit): {cov.quant_pit_source}",
        f"- Quant (Mehrjahres): {cov.historical}",
        f"- Tool-A-Dimensionen: {cov.gemini_dims}",
        f"- Währung: {cov.currency_note or 'konsistent'}",
        f"- Soft Scuttlebutt: {cov.soft}",
        f"- Sprach-/Tonalitätsanalyse: {cov.sprache}",
        f"- Insider-Transaktionen: {cov.insider}",
        "",
        "## Stef's Notizen",
        "",
        "*[Leer — Stef füllt manuell in Obsidian]*",
        "",
    ]

    post = frontmatter.Post("\n".join(lines))
    post.metadata.update({
        "ticker": record.ticker,
        "adr_ticker": record.adr_ticker,
        "cik": record.cik,
        "form_type": record.form_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "section_flags": record.section_flags,
    })
    out.write_text(frontmatter.dumps(post), encoding="utf-8")
    logger.info("dossier: wrote %s", out.name)
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run python -m pytest tests/deepdive/test_dossier_generator.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/dossier_generator.py tests/deepdive/test_dossier_generator.py
git commit -m "Add dossier generator with 15 mini-blocks and coverage section"
```

---

### Task 9: Pipeline + compose + CLI wiring (Stage orchestration, B.1-8)

**Files:**
- Create: `app/deepdive/pipeline.py`
- Modify: `app/config.py` (deep-dive settings)
- Modify: `app/deepdive/compose.py` (B.0 builders + new ones)
- Modify: `app/deepdive/__main__.py` (replace skeleton body)
- Test: `tests/deepdive/test_pipeline.py`, `tests/deepdive/test_compose.py` (append), `tests/deepdive/test_cli.py` (append), `tests/test_config.py` (append)

- [ ] **Step 1: Add deep-dive settings to `app/config.py`**

Add these fields to `FisherScreenSettings` (after `gemini_model`):

```python
    deepdive_gemini_model: str = "gemini-2.5-pro"
    deepdive_token_cap: int = 200_000
    filing_cache_ttl_days: int = 30
    historical_cache_ttl_days: int = 90
```

(`env_prefix = "FISHERSCREEN_"` already maps these to `FISHERSCREEN_DEEPDIVE_GEMINI_MODEL` etc.)

- [ ] **Step 2: Write the failing config test (append to `tests/test_config.py`)**

```python
def test_deepdive_settings_defaults():
    from app.config import FisherScreenSettings
    s = FisherScreenSettings()
    assert s.deepdive_gemini_model == "gemini-2.5-pro"
    assert s.deepdive_token_cap == 200_000
    assert s.filing_cache_ttl_days == 30
    assert s.historical_cache_ttl_days == 90
```

- [ ] **Step 3: Run to verify it passes after Step 1**

Run: `uv run python -m pytest tests/test_config.py -k deepdive -v`
Expected: PASS (1 test)

- [ ] **Step 4: Write the failing pipeline tests**

Create `tests/deepdive/test_pipeline.py`:

```python
from unittest.mock import MagicMock

import frontmatter

from app.deepdive.adr_resolver import ResolvedTicker
from app.deepdive.pipeline import run_deep_dive
from app.models.deep_dive_record import (
    PointInTimeQuant, QuantSnapshot, SourceCoverage)
from app.services.edgar_client import RawFiling


def _good_points():
    return {"points": [
        {"number": n, "title": f"P{n}", "rating": 4, "confidence": "🟢",
         "reasoning": "Begründung.", "sources": ["20-F §5"]}
        for n in range(1, 16)]}


def _deps():
    resolver = MagicMock()
    resolver.resolve.return_value = ResolvedTicker(
        "NOVO-B.CO", "NVO", "0000353278", "20-F")
    filings = MagicMock()
    filings.get.return_value = RawFiling("acc-1",
        "<html>Item 4. four Item 5. five Item 18. eighteen</html>")
    quant = MagicMock()
    quant.return_value = (
        QuantSnapshot(point_in_time=PointInTimeQuant(
            ticker="NOVO-B.CO", name="Novo Nordisk")),
        SourceCoverage(edgar="20-F via ADR"))
    synthesizer = MagicMock()
    synthesizer.synthesize.return_value = _good_points()
    return resolver, filings, quant, synthesizer


def test_pipeline_writes_dossier(tmp_path):
    resolver, filings, quant, synth = _deps()
    out = run_deep_dive(
        "NOVO-B.CO", output_dir=tmp_path, resolver=resolver,
        filing_fetcher=filings, build_quant=quant, synthesizer=synth,
        token_cap=200000, use_cache=True)
    assert out.exists()
    post = frontmatter.loads(out.read_text(encoding="utf-8"))
    assert post["ticker"] == "NOVO-B.CO"
    assert "### Punkt 1 —" in post.content
    resolver.resolve.assert_called_once_with("NOVO-B.CO")
    filings.get.assert_called_once_with("0000353278", "20-F", use_cache=True)


def test_pipeline_propagates_resolver_error(tmp_path):
    from app.errors import DeepDiveError
    resolver, filings, quant, synth = _deps()
    resolver.resolve.side_effect = DeepDiveError("not in ADR table")
    import pytest
    with pytest.raises(DeepDiveError, match="ADR table"):
        run_deep_dive("SAP.DE", output_dir=tmp_path, resolver=resolver,
                       filing_fetcher=filings, build_quant=quant,
                       synthesizer=synth, token_cap=200000, use_cache=True)
```

- [ ] **Step 5: Run to verify fail**

Run: `uv run python -m pytest tests/deepdive/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 6: Write `app/deepdive/pipeline.py`**

```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from app.deepdive.dossier_generator import generate_dossier
from app.deepdive.filing_parser import parse_filing
from app.deepdive.synthesis import run_synthesis
from app.models.deep_dive_record import DeepDiveRecord

logger = logging.getLogger(__name__)


def run_deep_dive(
    ticker: str,
    *,
    output_dir: Path,
    resolver: Any,
    filing_fetcher: Any,
    build_quant: Callable[..., tuple[Any, Any]],
    synthesizer: Any,
    token_cap: int,
    use_cache: bool,
) -> Path:
    logger.info("deepdive: start ticker=%s", ticker)

    # [1] ADR-Lookup
    resolved = resolver.resolve(ticker)

    # [2] EDGAR-Pull (local-FS cache, ADR-4)
    raw = filing_fetcher.get(resolved.cik, resolved.form_type, use_cache=use_cache)

    # [3] Filing-Parse
    parsed = parse_filing(raw.document_text, resolved.form_type)

    # [4] Quant-Join
    quant, coverage = build_quant(ticker)
    coverage.edgar = f"{resolved.form_type} via ADR"

    # [5] Gemini-Synthesis
    synthesis = run_synthesis(
        ticker=ticker,
        form_type=resolved.form_type,
        sections=parsed.sections,
        quant=quant,
        synthesizer=synthesizer,
        max_input_tokens=token_cap,
    )

    record = DeepDiveRecord(
        ticker=ticker,
        adr_ticker=resolved.adr_ticker,
        cik=resolved.cik,
        form_type=resolved.form_type,
        filing_sections=parsed.sections,
        section_flags=parsed.section_flags,
        quant_snapshot=quant,
        synthesis=synthesis,
        source_coverage=coverage,
    )

    # [6] Markdown-Output
    out = generate_dossier(record, output_dir)
    logger.info("deepdive: done ticker=%s -> %s", ticker, out.name)
    return out
```

- [ ] **Step 7: Run to verify pass**

Run: `uv run python -m pytest tests/deepdive/test_pipeline.py -v`
Expected: PASS (2 tests)

- [ ] **Step 8: Extend `app/deepdive/compose.py`** (keep B.0 exports, add builders)

Replace the file contents with:

```python
from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.deepdive.adr_resolver import ADRResolver
from app.deepdive.adr_table import load_adr_table
from app.deepdive.filing_cache import CachedFilingFetcher
from app.deepdive.historical_cache import CachedHistoricalData
from app.deepdive.quant_join import build_quant_snapshot
from app.screener.compose import build_github_client
from app.services.edgar_client import EdgarClientImpl
from app.services.firestore_client import FirestoreClientImpl
from app.services.gemini_deepdive_client import GeminiDeepDiveClient
from app.services.historical_data_service import HistoricalDataServiceImpl
from app.services.yfinance_client import YFinanceClientImpl

__all__ = [
    "build_adr_table",
    "build_github_client",
    "build_adr_resolver",
    "build_filing_fetcher",
    "build_quant_builder",
    "build_synthesizer",
]

_FILING_CACHE_DIR = Path("cache/filings")
_HISTORICAL_CACHE_DIR = Path("cache/yfinance_historical")


def build_adr_table() -> dict[str, dict[str, str]]:
    return load_adr_table()


def build_adr_resolver() -> ADRResolver:
    return ADRResolver(table=load_adr_table())


def build_filing_fetcher() -> CachedFilingFetcher:
    edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
    return CachedFilingFetcher(
        edgar=edgar,
        cache_dir=_FILING_CACHE_DIR,
        ttl_days=settings.filing_cache_ttl_days,
    )


def build_quant_builder():
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    yfinance = YFinanceClientImpl()
    historical = CachedHistoricalData(
        service=HistoricalDataServiceImpl(yfinance=yfinance),
        cache_dir=_HISTORICAL_CACHE_DIR,
        ttl_days=settings.historical_cache_ttl_days,
    )
    pit_collection = settings.ticker_collection
    dims_collection = settings.gemini_score_collection

    def _build(ticker: str):
        return build_quant_snapshot(
            ticker,
            firestore=firestore,
            yfinance=yfinance,
            historical=historical,
            pit_collection=pit_collection,
            dims_collection=dims_collection,
        )

    return _build


def build_synthesizer(model_override: str | None = None) -> GeminiDeepDiveClient:
    return GeminiDeepDiveClient(
        api_key=settings.gemini_api_key,
        model=model_override or settings.deepdive_gemini_model,
    )
```

- [ ] **Step 9: Update `tests/deepdive/test_compose.py`** (replace the GitHub-identity test block — `build_github_client` is still re-exported; add resolver builder check). Append:

```python
def test_build_adr_resolver_resolves_seed():
    from app.deepdive.compose import build_adr_resolver
    assert build_adr_resolver().resolve("NOVO-B.CO").adr_ticker == "NVO"
```

(The existing `test_build_adr_table_returns_seed` and `test_github_client_builder_is_reused_not_duplicated` remain valid — `build_github_client` is still imported from `app.screener.compose`.)

- [ ] **Step 10: Replace the body of `app/deepdive/__main__.py`** (keep `build_parser` exactly as B.0 built it; replace only `main`)

```python
from __future__ import annotations

import argparse
import logging
import sys

from app.deepdive.compose import (
    build_adr_resolver,
    build_filing_fetcher,
    build_quant_builder,
    build_synthesizer,
)
from app.deepdive.pipeline import run_deep_dive
from app.config import settings
from app.errors import DataSourceError, DeepDiveError, GeminiError
from pathlib import Path

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fisherscreen", description="FisherScreen CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    deepdive = subparsers.add_parser(
        "deepdive", help="Run a Tool B deep dive on one ticker"
    )
    deepdive.add_argument("ticker", help="Ticker symbol, e.g. NOVO-B.CO")
    deepdive.add_argument(
        "--model", default=None, help="Override the Gemini synthesis model"
    )
    deepdive.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore the local filing/historical caches",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        out = run_deep_dive(
            args.ticker,
            output_dir=Path(settings.output_dir),
            resolver=build_adr_resolver(),
            filing_fetcher=build_filing_fetcher(),
            build_quant=build_quant_builder(),
            synthesizer=build_synthesizer(args.model),
            token_cap=settings.deepdive_token_cap,
            use_cache=not args.no_cache,
        )
    except DeepDiveError as exc:
        logger.error("deepdive failed (ticker): %s", exc)
        print(f"ERROR: {exc}")
        return 1
    except DataSourceError as exc:
        logger.error("deepdive failed (data source): %s", exc)
        print(f"ERROR: {exc}")
        return 2
    except GeminiError as exc:
        logger.error("deepdive failed (gemini): %s", exc)
        print(f"ERROR: {exc}")
        return 3
    print(f"Dossier written to: {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 11: Update `tests/deepdive/test_cli.py`** — the B.0 skeleton test `test_deepdive_skeleton_returns_zero_and_prints_notice` is now obsolete (no more skeleton notice). Replace it with an end-to-end test (all services patched). Replace that one test function with:

```python
def test_deepdive_end_to_end_writes_dossier(tmp_path, monkeypatch):
    import frontmatter
    from unittest.mock import MagicMock
    from app.deepdive.adr_resolver import ResolvedTicker
    from app.models.deep_dive_record import (
        PointInTimeQuant, QuantSnapshot, SourceCoverage)
    from app.services.edgar_client import RawFiling
    import app.deepdive.__main__ as cli

    monkeypatch.setattr(cli.settings, "output_dir", str(tmp_path))
    resolver = MagicMock()
    resolver.resolve.return_value = ResolvedTicker(
        "NOVO-B.CO", "NVO", "0000353278", "20-F")
    fetcher = MagicMock()
    fetcher.get.return_value = RawFiling(
        "acc-1", "<html>Item 4. four Item 5. five Item 18. eighteen</html>")
    qb = MagicMock(return_value=(
        QuantSnapshot(point_in_time=PointInTimeQuant(ticker="NOVO-B.CO")),
        SourceCoverage()))
    synth = MagicMock()
    synth.synthesize.return_value = {"points": [
        {"number": n, "title": f"P{n}", "rating": 4, "confidence": "🟢",
         "reasoning": "r.", "sources": ["20-F §5"]} for n in range(1, 16)]}
    monkeypatch.setattr(cli, "build_adr_resolver", lambda: resolver)
    monkeypatch.setattr(cli, "build_filing_fetcher", lambda: fetcher)
    monkeypatch.setattr(cli, "build_quant_builder", lambda: qb)
    monkeypatch.setattr(cli, "build_synthesizer", lambda m: synth)

    rc = cli.main(["deepdive", "NOVO-B.CO"])
    assert rc == 0
    files = list((tmp_path / "Watchlist").glob("NOVO-B.CO_*.md"))
    assert len(files) == 1
    assert frontmatter.loads(files[0].read_text(encoding="utf-8"))["ticker"] == "NOVO-B.CO"


def test_deepdive_maps_deepdive_error_to_exit_1(monkeypatch):
    from unittest.mock import MagicMock
    import app.deepdive.__main__ as cli
    from app.errors import DeepDiveError
    bad = MagicMock()
    bad.resolve.side_effect = DeepDiveError("not in ADR table")
    monkeypatch.setattr(cli, "build_adr_resolver", lambda: bad)
    monkeypatch.setattr(cli, "build_filing_fetcher", lambda: MagicMock())
    monkeypatch.setattr(cli, "build_quant_builder", lambda: MagicMock())
    monkeypatch.setattr(cli, "build_synthesizer", lambda m: MagicMock())
    assert cli.main(["deepdive", "SAP.DE"]) == 1
```

Keep the existing `test_build_parser_*`, `test_deepdive_defaults`, `test_help_exits_zero`, `test_no_command_exits_two` tests unchanged — `build_parser` is unchanged.

- [ ] **Step 12: Run the affected suites**

Run: `uv run python -m pytest tests/deepdive/ tests/test_config.py -v`
Expected: PASS (all)

- [ ] **Step 13: Commit**

```bash
git add app/deepdive/pipeline.py app/config.py app/deepdive/compose.py app/deepdive/__main__.py tests/deepdive/test_pipeline.py tests/deepdive/test_compose.py tests/deepdive/test_cli.py tests/test_config.py
git commit -m "Wire deep-dive pipeline, compose builders, and CLI (B.1-8)"
```

---

### Task 10: Acceptance script (B.1-9, manual gate)

**Files:**
- Create: `scripts/acceptance_deepdive.py`

Not a unit test — a documented manual gate (mirrors `scripts/acceptance_basis_filter.py`). Real EDGAR + Firestore read + live yfinance + Gemini Pro.

- [ ] **Step 1: Write `scripts/acceptance_deepdive.py`**

```python
"""Acceptance gate for Tool B Phase B.1 (manual, NOT a unit test).

Runs a real deep dive on Novo Nordisk against live EDGAR + Firestore +
yfinance + Gemini Pro and writes the dossier. Stephan reads the dossier
and judges decision-usefulness (spec §1 exit criterion).

SOPRA-EPDR: invoke as a module, never the .exe shim (CLAUDE.md):
  uv run python -m scripts.acceptance_deepdive
or:
  uv run python scripts/acceptance_deepdive.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.config import settings
from app.deepdive.compose import (
    build_adr_resolver,
    build_filing_fetcher,
    build_quant_builder,
    build_synthesizer,
)
from app.deepdive.pipeline import run_deep_dive

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

_TICKER = "NOVO-B.CO"


def main() -> int:
    print(f"\nRunning real deep dive for {_TICKER} "
          f"(model={settings.deepdive_gemini_model}, "
          f"token_cap={settings.deepdive_token_cap})\n")
    try:
        out = run_deep_dive(
            _TICKER,
            output_dir=Path(settings.output_dir),
            resolver=build_adr_resolver(),
            filing_fetcher=build_filing_fetcher(),
            build_quant=build_quant_builder(),
            synthesizer=build_synthesizer(None),
            token_cap=settings.deepdive_token_cap,
            use_cache=True,
        )
    except Exception as exc:
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"\nDossier written: {out}")
    print("Manual gate: Stephan liest das Dossier und urteilt "
          "(entscheidungs-nützlich? / Synthesis-Struktur anders?).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify it imports clean (no execution — needs real credentials)**

Run: `uv run python -c "import scripts.acceptance_deepdive as a; print(a._TICKER)"`
Expected: `NOVO-B.CO`

- [ ] **Step 3: Commit**

```bash
git add scripts/acceptance_deepdive.py
git commit -m "Add manual acceptance script for B.1 Novo deep dive"
```

---

### Task 11: Full suite + coverage gate

- [ ] **Step 1: Run the entire suite**

Run: `uv run python -m pytest`
Expected: all PASS; coverage ≥ 90% (`Required test coverage of 90% reached`).

> If coverage < 90%, the gap is in new `app/deepdive/*` modules (services are coverage-omitted). Add the missing-line test — never lower the threshold. Likely spots: `pipeline.py` error branches, `dossier_generator.py` n/a-fallbacks.

- [ ] **Step 2: Commit only if Step 1 required test additions**

```bash
git add -A
git commit -m "Close coverage gaps in B.1 deep-dive pipeline"
```

---

## Self-Review

**1. Spec coverage** (spec `2026-05-18-tool-b-phase-b1-design.md` §7 tasks + E1–E5 + ADR-5):

| Spec item | Plan task |
|---|---|
| B.1-1 DeepDiveRecord (structured quant_snapshot, inference-cap) | Task 1 ✓ |
| B.1-2 ADR-Resolver (US passthrough, actionable error) | Task 2 ✓ |
| B.1-3 Filing-Fetcher (`get_latest_annual_filing`, ADR-4 cache) | Task 3 ✓ |
| B.1-4 Filing-Parser (E1 hybrid, form switch, token cap, flags) | Task 4 ✓ |
| B.1-5 Quant-Join (4a cache/live, 4b historical, ADR-5a cache) | Tasks 5 + 6 ✓ |
| B.1-5a Trend-Metriken (pure functions) | Task 5a ✓ |
| B.1-6 Gemini synthesis (E2 single call, response JSON, token cap, post-hoc validator, inference cap) | Task 7 ✓ |
| B.1-7 Dossier (mini-blocks, source_coverage, frontmatter) | Task 8 ✓ |
| B.1-8 CLI + composition root (E3 argparse, exit codes 0/1/2/3) | Task 9 ✓ |
| B.1-9 Acceptance script (manual gate) | Task 10 ✓ |
| ADR-5a local 90d historical cache `_cached_at` | Task 5 ✓ |
| ADR-5b structured quant_snapshot (4 sub-fields) | Task 1 + 6 ✓ |
| ADR-5c Tool-A dims secondary, absent→marker, no live re-derive | Task 6 ✓ |
| E1 `FISHERSCREEN_DEEPDIVE_SECTION_TOKEN_CAP` default 50000 | Task 4 ✓ |
| E2 `FISHERSCREEN_DEEPDIVE_TOKEN_CAP` 200000, model env | Task 9 (config) + 7 ✓ |
| E3 local invocation `python -m app.deepdive` | Header + Task 10 ✓ |
| Stage-4 4a→4b sequential | Task 6 (sequential in `build_quant_snapshot`) ✓ |

No gaps. (Executive-Summary/Bewertung Gemini-prose enrichment is explicitly a placeholder in B.1 per spec §6 — the 15 mini-blocks carry the substance for the B.1 acceptance; not a plan defect.)

**2. Placeholder scan:** No "TBD/TODO/implement later" in steps; every code step has complete code; every run step has an exact command + expected output. The dossier Executive-Summary literal `*[...]*` is intended rendered content per spec §6, not a plan placeholder. The Task-4 TOC test function name uses a valid underscore identifier (`test_toc_false_positive_skipped`).

**3. Type consistency:** `RawFiling(accession_number, document_text)` defined Task 3, used identically in Tasks 3/9 tests and `filing_cache`/`pipeline`. `ParsedFiling(sections, section_flags)` Task 4 → consumed in Task 9 pipeline. `QuantSnapshot/PointInTimeQuant/HistoricalSeries/TrendMetrics/FisherPoint/SourceCoverage` defined Task 1 → reused verbatim in Tasks 6/7/8/9. `ResolvedTicker(ticker, adr_ticker, cik, form_type)` Task 2 → used in Tasks 9 tests/pipeline. `build_quant_snapshot(...) -> (QuantSnapshot, SourceCoverage)` Task 6 → `build_quant_builder` closure Task 9 → `build_quant` param in `run_deep_dive` Task 9. `GeminiDeepDiveClient.synthesize(system, user, max_input_tokens)` Task 7 → called by `run_synthesis` Task 7 → `synthesizer` param Task 9. `run_deep_dive(...)` keyword signature identical across Task 9 impl, Task 9 tests, Task 10 script. `build_parser`/`main` Task 9 preserve the B.0 `build_parser` (unchanged) so B.0 parser tests still pass. Consistent.

---

*Ende des Plans.*
