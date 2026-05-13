# Phase 1.3 — Gemini Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Gemini Flash Lite scoring per ticker to the screener pipeline, with hard cost guardrails (token caps, run cost tracking in Firestore, GCP budget alerts).

**Architecture:** GeminiClientImpl builds a structured prompt from ScreenerRecord fields (including 4 new financial ratio fields populated from yfinance info) and calls `gemini-2.0-flash-lite`, returning per-dimension Fisher scores (1–5) as JSON. CachedGeminiClient wraps it with 30-day TTL in Firestore `dev_gemini_scores`. RunTracker accumulates token counts across the run and writes a RunRecord to `dev_screener_runs` at the end. scorer.py enforces the 3.000-ticker hard cap and per-ticker token budget.

**Tech Stack:** `google-genai` Python SDK (new API: `from google import genai`), `gemini-2.0-flash-lite`, existing FirestoreClient + pydantic-settings patterns.

---

## Files

| File | Aktion |
|------|--------|
| `app/config.py` | Modify — 3 neue Settings |
| `app/models/screener_record.py` | Modify — 4 Finanz-Ratios + 2 Gemini-Felder, entferne `gemini_score` |
| `app/models/run_record.py` | Create — RunRecord Pydantic-Modell |
| `app/services/gemini_client.py` | Create — GeminiClient Protocol + GeminiClientImpl |
| `app/services/cached_gemini_client.py` | Create — 30d-TTL-Cache |
| `app/screener/run_tracker.py` | Create — Token-Akkumulator + Firestore-Write |
| `app/screener/scorer.py` | Create — `run_gemini_scoring()` mit Hard-Cap + Token-Budget |
| `app/screener/compose.py` | Modify — `build_gemini_pipeline()` + `build_run_tracker()` |
| `tests/test_config.py` | Modify — 6 neue Tests |
| `tests/models/test_screener_record.py` | Modify — Tests für neue Felder |
| `tests/models/test_run_record.py` | Create |
| `tests/services/test_gemini_client.py` | Create |
| `tests/services/test_cached_gemini_client.py` | Create |
| `tests/screener/test_run_tracker.py` | Create |
| `tests/screener/test_scorer.py` | Create |
| `tests/screener/test_compose.py` | Modify |
| `docs/infra/budget-alerts.md` | Create — gcloud-Schritte + Console-Steps |
| `infra/budget_stop.py` | Create — Cloud Function Code |
| `infra/requirements.txt` | Create — Cloud Function deps |

---

### Task 1: Config — Gemini Settings

**Files:**
- Modify: `app/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py — append:

def test_reads_gemini_api_key(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_GEMINI_API_KEY", "api-key-xyz")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_api_key == "api-key-xyz"

def test_gemini_api_key_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("FISHERSCREEN_GEMINI_API_KEY", raising=False)
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_api_key == ""

def test_reads_gemini_score_collection(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_GEMINI_SCORE_COLLECTION", "prod_gemini_scores")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_score_collection == "prod_gemini_scores"

def test_gemini_score_collection_defaults_to_dev():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_score_collection == "dev_gemini_scores"

def test_reads_screener_runs_collection(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_SCREENER_RUNS_COLLECTION", "prod_screener_runs")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.screener_runs_collection == "prod_screener_runs"

def test_screener_runs_collection_defaults_to_dev():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.screener_runs_collection == "dev_screener_runs"
```

- [ ] **Step 2: Run tests — verify FAIL**

```
uv run python -m pytest tests/test_config.py -k "gemini_api_key or gemini_score or screener_runs" -v
```
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement**

```python
# app/config.py — full replacement:
from pydantic_settings import BaseSettings


class FisherScreenSettings(BaseSettings):
    gcp_project_id: str = ""
    edgar_user_agent: str = ""  # must be set via FISHERSCREEN_EDGAR_USER_AGENT; validated in EdgarClientImpl
    gemini_token_cap: int = 500_000
    gemini_api_key: str = ""
    gemini_score_collection: str = "dev_gemini_scores"
    screener_runs_collection: str = "dev_screener_runs"
    apify_api_key: str = ""
    github_token: str = ""
    ticker_collection: str = "dev_ticker_cache"
    edgar_collection: str = "dev_edgar_cache"

    model_config = {
        "env_prefix": "FISHERSCREEN_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = FisherScreenSettings()
```

- [ ] **Step 4: Run — verify PASS**

```
uv run python -m pytest tests/test_config.py -v
```
Expected: all tests pass including new ones.

- [ ] **Step 5: Commit**

```
git add app/config.py tests/test_config.py
git commit -m "Add gemini_api_key, gemini_score_collection, screener_runs_collection settings"
```

---

### Task 2: ScreenerRecord — Financial Ratios + Gemini Fields

**Files:**
- Modify: `app/models/screener_record.py`
- Modify: `tests/models/test_screener_record.py`

**Context:** The existing `gemini_score: float | None = None` field is a composite score — removed because CLAUDE.md says "Kein Composite-Scoring in Tool A". Replace with `gemini_dimensions: dict[str, int] | None = None` and `gemini_summary: str | None = None`. Also add 4 financial ratio fields populated from yfinance info (these keys are already available in the yfinance `info` dict returned by `get_ticker_info()`).

- [ ] **Step 1: Write failing tests**

```python
# tests/models/test_screener_record.py — append:

def test_from_yfinance_info_populates_financial_ratios():
    info = {
        "revenueGrowth": 0.12,
        "operatingMargins": 0.25,
        "returnOnEquity": 0.18,
        "debtToEquity": 45.0,
    }
    record = ScreenerRecord.from_yfinance_info("TEST", info)
    assert record.revenue_growth_yoy == 0.12
    assert record.operating_margin == 0.25
    assert record.return_on_equity == 0.18
    assert record.debt_to_equity == 45.0

def test_financial_ratios_default_to_none_when_missing():
    record = ScreenerRecord.from_yfinance_info("TEST", {})
    assert record.revenue_growth_yoy is None
    assert record.operating_margin is None
    assert record.return_on_equity is None
    assert record.debt_to_equity is None

def test_gemini_dimension_fields_default_to_none():
    record = ScreenerRecord(ticker="TEST")
    assert record.gemini_dimensions is None
    assert record.gemini_summary is None

def test_gemini_dimensions_can_be_set():
    dims = {"growth": 4, "profitability": 3, "management": 4, "innovation": 5, "resilience": 3}
    record = ScreenerRecord(ticker="TEST", gemini_dimensions=dims, gemini_summary="Good company")
    assert record.gemini_dimensions["growth"] == 4
    assert record.gemini_summary == "Good company"
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/models/test_screener_record.py -k "financial_ratio or gemini_dimension" -v
```

- [ ] **Step 3: Implement**

Replace the full `app/models/screener_record.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ScreenerRecord(BaseModel):
    # Identity
    ticker: str
    name: str | None = None
    currency: str | None = None

    # Market data (from yfinance info)
    market_cap: float | None = None
    avg_daily_volume: float | None = None
    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    gics_sector: str | None = None
    gics_industry: str | None = None

    # Financial ratios (from yfinance info — populated in run_basis_filter)
    revenue_growth_yoy: float | None = None   # info['revenueGrowth']
    operating_margin: float | None = None      # info['operatingMargins']
    return_on_equity: float | None = None      # info['returnOnEquity']
    debt_to_equity: float | None = None        # info['debtToEquity']

    # EDGAR fields (populated in Phase 1.2)
    cik: str | None = None
    has_restatement: bool | None = None
    has_going_concern: bool | None = None
    has_active_enforcement: bool = False
    edgar_skipped: bool = False

    # Gemini scoring (populated in Phase 1.3)
    gemini_dimensions: dict[str, int] | None = None  # {"growth": 3, "profitability": 4, ...}
    gemini_summary: str | None = None

    # Filter tracking
    filter_passed_basis: bool | None = None
    filter_passed_edgar: bool | None = None
    filter_failed_reason: str | None = None

    # Metadata
    screened_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def from_yfinance_info(cls, ticker: str, info: dict[str, Any]) -> ScreenerRecord:
        return cls(
            ticker=ticker,
            name=info.get("shortName"),
            currency=info.get("currency"),
            market_cap=info.get("marketCap") or None,
            avg_daily_volume=info.get("averageVolume") or None,
            price=info.get("currentPrice") or info.get("regularMarketPrice"),
            bid=info.get("bid") or None,
            ask=info.get("ask") or None,
            gics_sector=info.get("sector"),
            gics_industry=info.get("industry"),
            cik=info.get("cik"),
            revenue_growth_yoy=info.get("revenueGrowth"),
            operating_margin=info.get("operatingMargins"),
            return_on_equity=info.get("returnOnEquity"),
            debt_to_equity=info.get("debtToEquity"),
        )
```

- [ ] **Step 4: Run full model test suite — verify PASS**

```
uv run python -m pytest tests/models/ -v
```
Expected: all tests pass (including previously passing ones — `gemini_score` was never tested, removing it is safe).

- [ ] **Step 5: Commit**

```
git add app/models/screener_record.py tests/models/test_screener_record.py
git commit -m "Add financial ratio fields and gemini_dimensions to ScreenerRecord, remove composite gemini_score"
```

---

### Task 3: RunRecord Model

**Files:**
- Create: `app/models/run_record.py`
- Create: `tests/models/test_run_record.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/models/test_run_record.py
import pytest
from app.models.run_record import COST_PER_1M_INPUT_USD, COST_PER_1M_OUTPUT_USD, RunRecord


def test_run_record_defaults():
    record = RunRecord(run_id="2026-05-13T10:00:00+00:00")
    assert record.tickers_processed == 0
    assert record.tickers_skipped == 0
    assert record.tokens_in_total == 0
    assert record.tokens_out_total == 0
    assert record.estimated_cost_usd == 0.0
    assert record.status == "success"
    assert record.completed_at is None


def test_compute_cost_zero_tokens():
    record = RunRecord(run_id="test")
    assert record.compute_cost() == 0.0


def test_compute_cost_input_tokens_only():
    record = RunRecord(run_id="test", tokens_in_total=1_000_000)
    assert record.compute_cost() == pytest.approx(COST_PER_1M_INPUT_USD)


def test_compute_cost_output_tokens_only():
    record = RunRecord(run_id="test", tokens_out_total=1_000_000)
    assert record.compute_cost() == pytest.approx(COST_PER_1M_OUTPUT_USD)


def test_compute_cost_realistic_run():
    # 400 tickers × avg 1500 input + 200 output tokens
    record = RunRecord(run_id="test", tokens_in_total=600_000, tokens_out_total=80_000)
    expected = (
        (600_000 / 1_000_000 * COST_PER_1M_INPUT_USD)
        + (80_000 / 1_000_000 * COST_PER_1M_OUTPUT_USD)
    )
    assert record.compute_cost() == pytest.approx(expected)


def test_model_dump_serializes_datetimes_as_strings():
    record = RunRecord(run_id="test", status="partial")
    data = record.model_dump(mode="json")
    assert data["run_id"] == "test"
    assert data["status"] == "partial"
    assert isinstance(data["started_at"], str)
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/models/test_run_record.py -v
```

- [ ] **Step 3: Implement**

```python
# app/models/run_record.py
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

COST_PER_1M_INPUT_USD = 0.10
COST_PER_1M_OUTPUT_USD = 0.40


class RunRecord(BaseModel):
    run_id: str
    tickers_processed: int = 0
    tickers_skipped: int = 0
    tokens_in_total: int = 0
    tokens_out_total: int = 0
    estimated_cost_usd: float = 0.0
    status: str = "success"  # "success" | "partial" | "aborted"
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def compute_cost(self) -> float:
        return (
            (self.tokens_in_total / 1_000_000 * COST_PER_1M_INPUT_USD)
            + (self.tokens_out_total / 1_000_000 * COST_PER_1M_OUTPUT_USD)
        )
```

- [ ] **Step 4: Run — verify PASS**

```
uv run python -m pytest tests/models/ -v
```

- [ ] **Step 5: Commit**

```
git add app/models/run_record.py tests/models/test_run_record.py
git commit -m "Add RunRecord model for screener run cost tracking"
```

---

### Task 4: GeminiClientImpl

**Files:**
- Create: `app/services/gemini_client.py`
- Create: `tests/services/test_gemini_client.py`

**Context:** Uses `google-genai` SDK (NOT the old `google-generativeai`). The module-level `_genai` alias is what tests will patch. The five Fisher scoring dimensions are: growth, profitability, management, innovation, resilience. Scores are integers 1–5, clamped if Gemini returns out-of-range values. Prompt uses financial ratio fields now on ScreenerRecord.

- [ ] **Step 1: Install dependency**

```
uv add google-genai
```

- [ ] **Step 2: Write failing tests**

```python
# tests/services/test_gemini_client.py
import json
from unittest.mock import MagicMock, patch

import pytest

from app.errors import GeminiError
from app.models.screener_record import ScreenerRecord
from app.services.gemini_client import DIMENSIONS, GeminiClientImpl, GeminiScoreResult


def _record(**kwargs) -> ScreenerRecord:
    defaults = {
        "ticker": "TEST",
        "name": "Test Corp",
        "gics_sector": "Technology",
        "gics_industry": "Software",
        "market_cap": 1_000_000_000,
        "revenue_growth_yoy": 0.15,
        "operating_margin": 0.25,
        "return_on_equity": 0.20,
        "debt_to_equity": 30.0,
    }
    return ScreenerRecord(**{**defaults, **kwargs})


def _mock_token_resp(count: int) -> MagicMock:
    r = MagicMock()
    r.total_tokens = count
    return r


def _mock_generate_resp(
    dims: dict,
    summary: str = "Solid company",
    tokens_in: int = 500,
    tokens_out: int = 80,
) -> MagicMock:
    r = MagicMock()
    r.text = json.dumps({"dimensions": dims, "summary": summary})
    r.usage_metadata.prompt_token_count = tokens_in
    r.usage_metadata.candidates_token_count = tokens_out
    return r


def _valid_dims() -> dict:
    return {"growth": 4, "profitability": 3, "management": 4, "innovation": 5, "resilience": 3}


@patch("app.services.gemini_client._genai")
def test_raises_on_empty_api_key(mock_genai):
    with pytest.raises(GeminiError, match="API key"):
        GeminiClientImpl(api_key="")


@patch("app.services.gemini_client._genai")
def test_score_ticker_returns_valid_result(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.return_value = _mock_generate_resp(_valid_dims())

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())

    assert isinstance(result, GeminiScoreResult)
    assert result.dimensions == _valid_dims()
    assert result.tokens_in == 500
    assert result.tokens_out == 80


@patch("app.services.gemini_client._genai")
def test_raises_when_prompt_exceeds_token_limit(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(9999)

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="too large"):
        impl.score_ticker("TEST", _record(), max_input_tokens=3000)


@patch("app.services.gemini_client._genai")
def test_raises_on_invalid_json_response(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    bad = MagicMock()
    bad.text = "not-json"
    mock_client.models.generate_content.return_value = bad

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="invalid JSON"):
        impl.score_ticker("TEST", _record())


@patch("app.services.gemini_client._genai")
def test_clamps_out_of_range_dimension_scores(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.return_value = _mock_generate_resp(
        {"growth": 10, "profitability": 0, "management": 3, "innovation": 3, "resilience": 3}
    )

    impl = GeminiClientImpl(api_key="key")
    result = impl.score_ticker("TEST", _record())
    assert result.dimensions["growth"] == 5
    assert result.dimensions["profitability"] == 1


@patch("app.services.gemini_client._genai")
def test_wraps_api_exception_in_gemini_error(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    mock_client.models.generate_content.side_effect = RuntimeError("network failure")

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="API call failed"):
        impl.score_ticker("TEST", _record())


@patch("app.services.gemini_client._genai")
def test_raises_on_missing_dimension_in_response(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(500)
    incomplete = {"growth": 4, "profitability": 3}  # missing 3 dimensions
    mock_client.models.generate_content.return_value = _mock_generate_resp(incomplete)

    impl = GeminiClientImpl(api_key="key")
    with pytest.raises(GeminiError, match="dimension"):
        impl.score_ticker("TEST", _record())


@patch("app.services.gemini_client._genai")
def test_score_ticker_handles_none_financial_ratios(mock_genai):
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.count_tokens.return_value = _mock_token_resp(400)
    mock_client.models.generate_content.return_value = _mock_generate_resp(_valid_dims())

    impl = GeminiClientImpl(api_key="key")
    record = _record(revenue_growth_yoy=None, operating_margin=None, market_cap=None)
    result = impl.score_ticker("TEST", record)
    assert result.dimensions == _valid_dims()
```

- [ ] **Step 3: Run — verify FAIL**

```
uv run python -m pytest tests/services/test_gemini_client.py -v
```

- [ ] **Step 4: Implement**

```python
# app/services/gemini_client.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from google import genai as _genai
from google.genai import types as _types

from app.errors import GeminiError

if TYPE_CHECKING:
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)

DIMENSIONS = ["growth", "profitability", "management", "innovation", "resilience"]
_DEFAULT_MODEL = "gemini-2.0-flash-lite"


@dataclass
class GeminiScoreResult:
    dimensions: dict[str, int]
    summary: str
    tokens_in: int
    tokens_out: int


class GeminiClient(Protocol):
    def score_ticker(
        self,
        ticker: str,
        record: ScreenerRecord,
        max_input_tokens: int = 3000,
        max_output_tokens: int = 1000,
    ) -> GeminiScoreResult: ...


class GeminiClientImpl:
    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        if not api_key:
            raise GeminiError("Gemini API key not set — configure FISHERSCREEN_GEMINI_API_KEY")
        self._client = _genai.Client(api_key=api_key)
        self._model = model

    def score_ticker(
        self,
        ticker: str,
        record: ScreenerRecord,
        max_input_tokens: int = 3000,
        max_output_tokens: int = 1000,
    ) -> GeminiScoreResult:
        prompt = _build_prompt(ticker, record)
        try:
            token_resp = self._client.models.count_tokens(model=self._model, contents=prompt)
        except Exception as exc:
            raise GeminiError(f"Token count failed for {ticker}: {exc}") from exc
        if token_resp.total_tokens > max_input_tokens:
            raise GeminiError(
                f"ticker={ticker} prompt too large: {token_resp.total_tokens} > {max_input_tokens} tokens"
            )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=max_output_tokens,
                ),
            )
        except Exception as exc:
            raise GeminiError(f"Gemini API call failed for {ticker}: {exc}") from exc
        return _parse_response(ticker, response)


def _build_prompt(ticker: str, record: ScreenerRecord) -> str:
    def fmt(val: float | None, pct: bool = False) -> str:
        if val is None:
            return "n/a"
        return f"{val:.1%}" if pct else f"{val:.2f}"

    market_cap_str = f"${record.market_cap:,.0f}" if record.market_cap is not None else "n/a"
    lines = [
        f"You are evaluating {record.name or ticker} ({ticker}), "
        f"a {record.gics_sector or 'unknown sector'} / "
        f"{record.gics_industry or 'unknown industry'} company, "
        "for alignment with Phil Fisher's investment principles.",
        "",
        "Available financial data:",
        f"- Market Cap: {market_cap_str}",
        f"- Revenue Growth (YoY): {fmt(record.revenue_growth_yoy, pct=True)}",
        f"- Operating Margin: {fmt(record.operating_margin, pct=True)}",
        f"- Return on Equity: {fmt(record.return_on_equity, pct=True)}",
        f"- Debt to Equity: {fmt(record.debt_to_equity)}",
        "",
        "Score each dimension from 1 (very weak) to 5 (very strong) "
        "based on the data above and your knowledge of this company.",
        "",
        "Return ONLY valid JSON:",
        '{"dimensions": {"growth": <1-5>, "profitability": <1-5>, '
        '"management": <1-5>, "innovation": <1-5>, "resilience": <1-5>}, '
        '"summary": "<1-2 sentences>"}',
    ]
    return "\n".join(lines)


def _parse_response(ticker: str, response: object) -> GeminiScoreResult:
    try:
        data = json.loads(response.text)  # type: ignore[attr-defined]
    except (json.JSONDecodeError, AttributeError) as exc:
        raise GeminiError(f"Gemini returned invalid JSON for {ticker}: {exc}") from exc
    raw = data.get("dimensions", {})
    dimensions: dict[str, int] = {}
    for dim in DIMENSIONS:
        val = raw.get(dim)
        if not isinstance(val, (int, float)):
            raise GeminiError(f"Missing or invalid dimension '{dim}' for {ticker}")
        dimensions[dim] = max(1, min(5, int(val)))
    tokens_in = getattr(getattr(response, "usage_metadata", None), "prompt_token_count", 0) or 0
    tokens_out = getattr(getattr(response, "usage_metadata", None), "candidates_token_count", 0) or 0
    return GeminiScoreResult(
        dimensions=dimensions,
        summary=str(data.get("summary", "")),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
```

- [ ] **Step 5: Run — verify PASS**

```
uv run python -m pytest tests/services/test_gemini_client.py -v
```

- [ ] **Step 6: Commit**

```
git add app/services/gemini_client.py tests/services/test_gemini_client.py pyproject.toml uv.lock
git commit -m "Add GeminiClientImpl with token counting and structured Fisher dimension scoring"
```

---

### Task 5: CachedGeminiClient

**Files:**
- Create: `app/services/cached_gemini_client.py`
- Create: `tests/services/test_cached_gemini_client.py`

**Context:** Same TTL-cache pattern as `CachedEdgarClient` (7d) and `CachedYFinanceClient` (24h), but with 30-day TTL. Cache key = ticker symbol. Cache hit returns `tokens_in=0, tokens_out=0` (no API call was made). The `GeminiClient` Protocol is only imported under `TYPE_CHECKING` to avoid circular imports.

- [ ] **Step 1: Write failing tests**

```python
# tests/services/test_cached_gemini_client.py
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.screener_record import ScreenerRecord
from app.services.cached_gemini_client import CachedGeminiClient
from app.services.gemini_client import GeminiScoreResult


def _record() -> ScreenerRecord:
    return ScreenerRecord(ticker="AAPL", name="Apple Inc.", gics_sector="Technology")


def _result(growth: int = 4) -> GeminiScoreResult:
    return GeminiScoreResult(
        dimensions={"growth": growth, "profitability": 3, "management": 4, "innovation": 5, "resilience": 3},
        summary="Strong company",
        tokens_in=500,
        tokens_out=80,
    )


def _fresh_cached(growth: int = 3) -> dict:
    return {
        "dimensions": {"growth": growth, "profitability": 3, "management": 4, "innovation": 4, "resilience": 3},
        "summary": "Cached",
        "_cached_at": datetime.now(timezone.utc).isoformat(),
    }


def _stale_cached() -> dict:
    stale_dt = datetime.now(timezone.utc) - timedelta(days=31)
    return {
        "dimensions": {"growth": 1, "profitability": 1, "management": 1, "innovation": 1, "resilience": 1},
        "summary": "Old",
        "_cached_at": stale_dt.isoformat(),
    }


def test_returns_cached_result_when_fresh():
    mock_gemini = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = _fresh_cached(growth=3)

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    result = client.score_ticker("AAPL", _record())

    mock_gemini.score_ticker.assert_not_called()
    assert result.dimensions["growth"] == 3
    assert result.tokens_in == 0
    assert result.tokens_out == 0


def test_calls_gemini_when_no_cache():
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _result(growth=4)
    mock_fs = MagicMock()
    mock_fs.get.return_value = None

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    result = client.score_ticker("AAPL", _record())

    mock_gemini.score_ticker.assert_called_once()
    assert result.dimensions["growth"] == 4
    assert result.tokens_in == 500


def test_calls_gemini_when_cache_is_stale():
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _result(growth=4)
    mock_fs = MagicMock()
    mock_fs.get.return_value = _stale_cached()

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    result = client.score_ticker("AAPL", _record())

    mock_gemini.score_ticker.assert_called_once()
    assert result.dimensions["growth"] == 4


def test_writes_to_firestore_after_api_call():
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _result()
    mock_fs = MagicMock()
    mock_fs.get.return_value = None

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    client.score_ticker("AAPL", _record())

    mock_fs.set.assert_called_once()
    written = mock_fs.set.call_args[0][2]
    assert "dimensions" in written
    assert "_cached_at" in written


def test_does_not_write_to_firestore_on_cache_hit():
    mock_gemini = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = _fresh_cached()

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    client.score_ticker("AAPL", _record())

    mock_fs.set.assert_not_called()


def test_is_fresh_returns_false_when_cached_at_missing():
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _result()
    mock_fs = MagicMock()
    mock_fs.get.return_value = {"dimensions": {}, "summary": ""}  # no _cached_at

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    client.score_ticker("AAPL", _record())

    mock_gemini.score_ticker.assert_called_once()
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/services/test_cached_gemini_client.py -v
```

- [ ] **Step 3: Implement**

```python
# app/services/cached_gemini_client.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.gemini_client import GeminiScoreResult

if TYPE_CHECKING:
    from app.models.screener_record import ScreenerRecord
    from app.services.firestore_client import FirestoreClient
    from app.services.gemini_client import GeminiClient

_TTL_SECONDS = 30 * 24 * 3600  # 30 days


class CachedGeminiClient:
    def __init__(self, gemini: GeminiClient, firestore: FirestoreClient, collection: str) -> None:
        self._gemini = gemini
        self._firestore = firestore
        self._collection = collection

    def score_ticker(
        self,
        ticker: str,
        record: ScreenerRecord,
        max_input_tokens: int = 3000,
        max_output_tokens: int = 1000,
    ) -> GeminiScoreResult:
        cached = self._firestore.get(self._collection, ticker)
        if cached and self._is_fresh(cached):
            return GeminiScoreResult(
                dimensions=cached["dimensions"],
                summary=cached.get("summary", ""),
                tokens_in=0,
                tokens_out=0,
            )
        result = self._gemini.score_ticker(ticker, record, max_input_tokens, max_output_tokens)
        self._firestore.set(self._collection, ticker, {
            "dimensions": result.dimensions,
            "summary": result.summary,
            "_cached_at": datetime.now(timezone.utc).isoformat(),
        })
        return result

    def _is_fresh(self, cached: dict[str, Any]) -> bool:
        raw = cached.get("_cached_at")
        if not raw:
            return False
        cached_at = datetime.fromisoformat(raw)
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - cached_at).total_seconds() < _TTL_SECONDS
```

- [ ] **Step 4: Run — verify PASS**

```
uv run python -m pytest tests/services/test_cached_gemini_client.py -v
```

- [ ] **Step 5: Commit**

```
git add app/services/cached_gemini_client.py tests/services/test_cached_gemini_client.py
git commit -m "Add CachedGeminiClient with 30-day TTL Firestore caching"
```

---

### Task 6: RunTracker

**Files:**
- Create: `app/screener/run_tracker.py`
- Create: `tests/screener/test_run_tracker.py`

**Context:** Accumulates token counts across all tickers in a run. Called by the scorer after each ticker. `finish()` computes cost using the same constants defined in `RunRecord` and writes to Firestore. Uses the run_id = ISO timestamp at construction time.

- [ ] **Step 1: Write failing tests**

```python
# tests/screener/test_run_tracker.py
import pytest
from unittest.mock import MagicMock

from app.models.run_record import COST_PER_1M_INPUT_USD
from app.screener.run_tracker import RunTracker


def _tracker(collection: str = "col") -> tuple[RunTracker, MagicMock]:
    mock_fs = MagicMock()
    return RunTracker(firestore=mock_fs, collection=collection), mock_fs


def test_initial_state_produces_zero_record():
    tracker, _ = _tracker()
    record = tracker.finish()
    assert record.tickers_processed == 0
    assert record.tickers_skipped == 0
    assert record.tokens_in_total == 0
    assert record.estimated_cost_usd == 0.0


def test_record_ticker_accumulates_tokens():
    tracker, _ = _tracker()
    tracker.record_ticker(tokens_in=1000, tokens_out=200)
    tracker.record_ticker(tokens_in=800, tokens_out=150)
    record = tracker.finish()
    assert record.tickers_processed == 2
    assert record.tokens_in_total == 1800
    assert record.tokens_out_total == 350


def test_record_skip_increments_skipped_count():
    tracker, _ = _tracker()
    tracker.record_skip()
    tracker.record_skip()
    record = tracker.finish()
    assert record.tickers_skipped == 2
    assert record.tickers_processed == 0


def test_finish_computes_cost_from_input_tokens():
    tracker, _ = _tracker()
    tracker.record_ticker(tokens_in=1_000_000, tokens_out=0)
    record = tracker.finish()
    assert record.estimated_cost_usd == pytest.approx(COST_PER_1M_INPUT_USD)


def test_finish_writes_to_firestore():
    tracker, mock_fs = _tracker(collection="dev_screener_runs")
    tracker.record_ticker(tokens_in=500, tokens_out=100)
    tracker.finish()
    mock_fs.set.assert_called_once()
    collection_arg = mock_fs.set.call_args[0][0]
    assert collection_arg == "dev_screener_runs"


def test_finish_sets_status():
    tracker, _ = _tracker()
    record = tracker.finish(status="partial")
    assert record.status == "partial"


def test_finish_sets_completed_at():
    tracker, _ = _tracker()
    record = tracker.finish()
    assert record.completed_at is not None


def test_run_id_is_iso_timestamp_string():
    tracker, _ = _tracker()
    record = tracker.finish()
    assert "T" in record.run_id  # ISO format contains T separator
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/screener/test_run_tracker.py -v
```

- [ ] **Step 3: Implement**

```python
# app/screener/run_tracker.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.models.run_record import COST_PER_1M_INPUT_USD, COST_PER_1M_OUTPUT_USD, RunRecord

if TYPE_CHECKING:
    from app.services.firestore_client import FirestoreClient

logger = logging.getLogger(__name__)


class RunTracker:
    def __init__(self, firestore: FirestoreClient, collection: str) -> None:
        self._firestore = firestore
        self._collection = collection
        self._run_id = datetime.now(timezone.utc).isoformat()
        self._tickers_processed = 0
        self._tickers_skipped = 0
        self._tokens_in = 0
        self._tokens_out = 0
        self._started_at = datetime.now(timezone.utc)

    def record_ticker(self, tokens_in: int, tokens_out: int) -> None:
        self._tickers_processed += 1
        self._tokens_in += tokens_in
        self._tokens_out += tokens_out

    def record_skip(self) -> None:
        self._tickers_skipped += 1

    def finish(self, status: str = "success") -> RunRecord:
        completed_at = datetime.now(timezone.utc)
        cost = (
            (self._tokens_in / 1_000_000 * COST_PER_1M_INPUT_USD)
            + (self._tokens_out / 1_000_000 * COST_PER_1M_OUTPUT_USD)
        )
        record = RunRecord(
            run_id=self._run_id,
            tickers_processed=self._tickers_processed,
            tickers_skipped=self._tickers_skipped,
            tokens_in_total=self._tokens_in,
            tokens_out_total=self._tokens_out,
            estimated_cost_usd=cost,
            status=status,
            started_at=self._started_at,
            completed_at=completed_at,
        )
        self._firestore.set(self._collection, self._run_id, record.model_dump(mode="json"))
        logger.info(
            "run=%s status=%s tickers=%d skipped=%d tokens_in=%d tokens_out=%d cost=$%.4f",
            self._run_id,
            status,
            self._tickers_processed,
            self._tickers_skipped,
            self._tokens_in,
            self._tokens_out,
            cost,
        )
        return record
```

- [ ] **Step 4: Run — verify PASS**

```
uv run python -m pytest tests/screener/test_run_tracker.py -v
```

- [ ] **Step 5: Commit**

```
git add app/screener/run_tracker.py tests/screener/test_run_tracker.py
git commit -m "Add RunTracker for per-run token accumulation and cost logging"
```

---

### Task 7: scorer.py — `run_gemini_scoring()`

**Files:**
- Create: `app/screener/scorer.py`
- Create: `tests/screener/test_scorer.py`

**Context:** Hard cap of 3.000 tickers enforced BEFORE any API calls — raises `FisherScreenError` immediately. Per-ticker `GeminiError` (token too large, API failure, parse failure) is caught and logged as WARNING; the ticker is skipped and run continues. Returns ALL records (including skipped), so Phase 1.4 can see which tickers have `gemini_dimensions=None`.

- [ ] **Step 1: Write failing tests**

```python
# tests/screener/test_scorer.py
from unittest.mock import MagicMock

import pytest

from app.errors import FisherScreenError, GeminiError
from app.models.screener_record import ScreenerRecord
from app.screener.run_tracker import RunTracker
from app.screener.scorer import MAX_TICKERS_PER_RUN, run_gemini_scoring
from app.services.gemini_client import GeminiScoreResult


def _record(ticker: str = "TEST") -> ScreenerRecord:
    return ScreenerRecord(ticker=ticker, name="Test Corp", gics_sector="Technology")


def _score_result() -> GeminiScoreResult:
    return GeminiScoreResult(
        dimensions={"growth": 4, "profitability": 3, "management": 4, "innovation": 5, "resilience": 3},
        summary="Good",
        tokens_in=500,
        tokens_out=80,
    )


def _mock_tracker() -> RunTracker:
    mock_fs = MagicMock()
    return RunTracker(firestore=mock_fs, collection="col")


def test_raises_when_ticker_count_exceeds_hard_cap():
    records = [_record(f"T{i}") for i in range(MAX_TICKERS_PER_RUN + 1)]
    mock_gemini = MagicMock()
    with pytest.raises(FisherScreenError, match="Too many tickers"):
        run_gemini_scoring(records, mock_gemini, _mock_tracker())


def test_hard_cap_exactly_at_limit_does_not_raise():
    records = [_record(f"T{i}") for i in range(MAX_TICKERS_PER_RUN)]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _score_result()
    run_gemini_scoring(records, mock_gemini, _mock_tracker())


def test_populates_gemini_dimensions_on_success():
    records = [_record()]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _score_result()
    run_gemini_scoring(records, mock_gemini, _mock_tracker())
    assert records[0].gemini_dimensions == _score_result().dimensions
    assert records[0].gemini_summary == "Good"


def test_skips_ticker_on_gemini_error_and_continues():
    records = [_record("FAIL"), _record("OK")]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.side_effect = [GeminiError("api down"), _score_result()]
    result = run_gemini_scoring(records, mock_gemini, _mock_tracker())
    assert result[0].gemini_dimensions is None
    assert result[1].gemini_dimensions is not None


def test_records_tokens_in_tracker_on_success():
    records = [_record()]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _score_result()
    tracker = _mock_tracker()
    run_gemini_scoring(records, mock_gemini, tracker)
    assert tracker._tokens_in == 500
    assert tracker._tokens_out == 80
    assert tracker._tickers_processed == 1


def test_records_skip_in_tracker_on_gemini_error():
    records = [_record()]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.side_effect = GeminiError("failed")
    tracker = _mock_tracker()
    run_gemini_scoring(records, mock_gemini, tracker)
    assert tracker._tickers_skipped == 1
    assert tracker._tickers_processed == 0


def test_returns_all_records_including_skipped():
    records = [_record("A"), _record("B")]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.side_effect = [GeminiError("err"), _score_result()]
    result = run_gemini_scoring(records, mock_gemini, _mock_tracker())
    assert len(result) == 2


def test_empty_input_returns_empty_list():
    mock_gemini = MagicMock()
    assert run_gemini_scoring([], mock_gemini, _mock_tracker()) == []
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/screener/test_scorer.py -v
```

- [ ] **Step 3: Implement**

```python
# app/screener/scorer.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.errors import FisherScreenError, GeminiError
from app.models.screener_record import ScreenerRecord

if TYPE_CHECKING:
    from app.screener.run_tracker import RunTracker
    from app.services.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

MAX_TICKERS_PER_RUN = 3_000
MAX_INPUT_TOKENS_PER_TICKER = 3_000
MAX_OUTPUT_TOKENS_PER_TICKER = 1_000


def run_gemini_scoring(
    records: list[ScreenerRecord],
    gemini: GeminiClient,
    run_tracker: RunTracker,
) -> list[ScreenerRecord]:
    if len(records) > MAX_TICKERS_PER_RUN:
        raise FisherScreenError(
            f"Too many tickers for Gemini scoring: {len(records)} > {MAX_TICKERS_PER_RUN}. "
            "Run basis + EDGAR filters first."
        )
    for record in records:
        try:
            result = gemini.score_ticker(
                record.ticker,
                record,
                max_input_tokens=MAX_INPUT_TOKENS_PER_TICKER,
                max_output_tokens=MAX_OUTPUT_TOKENS_PER_TICKER,
            )
            record.gemini_dimensions = result.dimensions
            record.gemini_summary = result.summary
            run_tracker.record_ticker(result.tokens_in, result.tokens_out)
        except GeminiError as exc:
            logger.warning("ticker=%s gemini scoring skipped: %s", record.ticker, exc)
            run_tracker.record_skip()
    logger.info("scorer: gemini scoring complete for %d records", len(records))
    return records
```

- [ ] **Step 4: Run — verify PASS**

```
uv run python -m pytest tests/screener/test_scorer.py -v
```

- [ ] **Step 5: Commit**

```
git add app/screener/scorer.py tests/screener/test_scorer.py
git commit -m "Add run_gemini_scoring() with 3000-ticker hard cap and per-ticker token budget guard"
```

---

### Task 8: compose.py — `build_gemini_pipeline()` + `build_run_tracker()`

**Files:**
- Modify: `app/screener/compose.py`
- Modify: `tests/screener/test_compose.py`

**Context:** Follow the exact same wiring pattern as `build_edgar_pipeline()`. Both new functions create a fresh `FirestoreClientImpl` (same pattern as existing builders — no shared firestore instance). The test patches at the `app.screener.compose` module level.

- [ ] **Step 1: Write failing tests**

```python
# tests/screener/test_compose.py — append (keep existing tests, add these):
from unittest.mock import patch
import app.screener.compose as compose_module


def test_build_gemini_pipeline_wires_components():
    with (
        patch("app.screener.compose.GeminiClientImpl") as mock_gemini_cls,
        patch("app.screener.compose.FirestoreClientImpl") as mock_fs_cls,
        patch("app.screener.compose.CachedGeminiClient") as mock_cached_cls,
        patch("app.screener.compose.settings") as mock_settings,
    ):
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gcp_project_id = "test-project"
        mock_settings.gemini_score_collection = "dev_gemini_scores"

        result = compose_module.build_gemini_pipeline()

        mock_gemini_cls.assert_called_once_with(api_key="test-key")
        mock_fs_cls.assert_called_once_with(project_id="test-project")
        mock_cached_cls.assert_called_once_with(
            gemini=mock_gemini_cls.return_value,
            firestore=mock_fs_cls.return_value,
            collection="dev_gemini_scores",
        )
        assert result == mock_cached_cls.return_value


def test_build_run_tracker_wires_components():
    with (
        patch("app.screener.compose.FirestoreClientImpl") as mock_fs_cls,
        patch("app.screener.compose.RunTracker") as mock_tracker_cls,
        patch("app.screener.compose.settings") as mock_settings,
    ):
        mock_settings.gcp_project_id = "test-project"
        mock_settings.screener_runs_collection = "dev_screener_runs"

        result = compose_module.build_run_tracker()

        mock_fs_cls.assert_called_once_with(project_id="test-project")
        mock_tracker_cls.assert_called_once_with(
            firestore=mock_fs_cls.return_value,
            collection="dev_screener_runs",
        )
        assert result == mock_tracker_cls.return_value
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/screener/test_compose.py -k "build_gemini or build_run_tracker" -v
```

- [ ] **Step 3: Implement**

Full replacement of `app/screener/compose.py`:

```python
# app/screener/compose.py
from app.config import settings
from app.screener.run_tracker import RunTracker
from app.services.cached_edgar_client import CachedEdgarClient
from app.services.cached_gemini_client import CachedGeminiClient
from app.services.cached_yfinance_client import CachedYFinanceClient
from app.services.edgar_client import EdgarClientImpl
from app.services.firestore_client import FirestoreClientImpl
from app.services.gemini_client import GeminiClientImpl
from app.services.yfinance_client import YFinanceClient, YFinanceClientImpl


def build_screener_pipeline() -> YFinanceClient:
    yfinance = YFinanceClientImpl()
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    return CachedYFinanceClient(
        yfinance=yfinance,
        firestore=firestore,
        collection=settings.ticker_collection,
    )


def build_edgar_pipeline() -> CachedEdgarClient:
    edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    return CachedEdgarClient(
        edgar=edgar,
        firestore=firestore,
        collection=settings.edgar_collection,
    )


def build_gemini_pipeline() -> CachedGeminiClient:
    gemini = GeminiClientImpl(api_key=settings.gemini_api_key)
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    return CachedGeminiClient(
        gemini=gemini,
        firestore=firestore,
        collection=settings.gemini_score_collection,
    )


def build_run_tracker() -> RunTracker:
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    return RunTracker(
        firestore=firestore,
        collection=settings.screener_runs_collection,
    )
```

- [ ] **Step 4: Run full test suite — verify PASS**

```
uv run python -m pytest -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add app/screener/compose.py tests/screener/test_compose.py
git commit -m "Add build_gemini_pipeline() and build_run_tracker() composition roots"
```

---

### Task 9 [INFRA]: Budget Alerts + Cloud Function

**Files:**
- Create: `docs/infra/budget-alerts.md`
- Create: `infra/budget_stop.py`
- Create: `infra/requirements.txt`

**Context:** No Python unit tests for infra code. The Cloud Function disables the Cloud Scheduler job when billing exceeds $10/month. `SCHEDULER_JOB_NAME` is a placeholder (filled in Phase 2 after Cloud Scheduler job is created). The function handles the case where the env var is not set by logging and returning safely.

- [ ] **Step 1: Create Cloud Function**

```python
# infra/budget_stop.py
"""Cloud Function: pauses Cloud Scheduler job when billing budget is exceeded.

Triggered by Pub/Sub topic 'fisherscreen-budget-alerts'.
Deployment and setup: see docs/infra/budget-alerts.md

Environment variables:
  GCP_PROJECT_ID       — required, e.g. 'fisherscreen-prod'
  SCHEDULER_JOB_NAME  — set in Phase 2 after Cloud Scheduler job exists
  SCHEDULER_LOCATION  — defaults to 'europe-west3'
"""
import base64
import json
import os

from google.cloud import scheduler_v1

_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
_SCHEDULER_JOB = os.environ.get("SCHEDULER_JOB_NAME", "")
_SCHEDULER_LOCATION = os.environ.get("SCHEDULER_LOCATION", "europe-west3")


def stop_on_budget(event: dict, context: object) -> None:
    data = json.loads(base64.b64decode(event["data"]).decode("utf-8"))
    cost = float(data.get("costAmount", 0))
    budget = float(data.get("budgetAmount", 0))

    if cost < budget:
        print(f"Cost ${cost:.2f} below budget ${budget:.2f} — no action")
        return

    if not _SCHEDULER_JOB:
        print("SCHEDULER_JOB_NAME not set — skipping pause (configure in Phase 2)")
        return

    client = scheduler_v1.CloudSchedulerClient()
    job_name = f"projects/{_PROJECT_ID}/locations/{_SCHEDULER_LOCATION}/jobs/{_SCHEDULER_JOB}"
    client.pause_job(name=job_name)
    print(f"Paused '{_SCHEDULER_JOB}' — cost ${cost:.2f} exceeded budget ${budget:.2f}")
```

```
# infra/requirements.txt
google-cloud-scheduler==2.15.0
```

- [ ] **Step 2: Create budget alert documentation**

Create `docs/infra/budget-alerts.md`:

```markdown
# GCP Budget Alerts — Setup

Two alerts protect FisherScreen from unexpected Gemini costs:
- **$5/month** → email warning to stn.mueller@gmail.com
- **$10/month** → hard stop: Cloud Scheduler paused via Cloud Function

## Prerequisites

```cmd
gcloud config set project fisherscreen-prod
```

## Step 1: Create Pub/Sub topic (for $10 hard stop)

```cmd
gcloud pubsub topics create fisherscreen-budget-alerts --project=fisherscreen-prod
```

## Step 2: $5/month Email Alert (GCP Console)

GCP billing budget alerts require the Console or Billing API — no direct `gcloud billing budgets` command covers all options cleanly.

1. Open: GCP Console → Billing → Budgets & alerts → **Create budget**
2. Name: `FisherScreen $5 Warning`
3. Scope: Project `fisherscreen-prod`
4. Budget type: Specified amount → **$5.00**
5. Threshold: 100% of actual spend
6. Actions: ✅ **Email alerts to billing admins and users**
7. Save

## Step 3: $10/month Hard Stop Alert (Console + Pub/Sub)

1. Open: GCP Console → Billing → Budgets & alerts → **Create budget**
2. Name: `FisherScreen $10 Hard Stop`
3. Scope: Project `fisherscreen-prod`
4. Budget type: Specified amount → **$10.00**
5. Threshold: 100% of actual spend
6. Actions: Connect to Pub/Sub topic → `fisherscreen-budget-alerts`
7. Save

## Step 4: Deploy Cloud Function

```cmd
gcloud functions deploy fisherscreen-budget-stop ^
  --runtime=python312 ^
  --trigger-topic=fisherscreen-budget-alerts ^
  --entry-point=stop_on_budget ^
  --source=infra ^
  --region=europe-west3 ^
  --set-env-vars GCP_PROJECT_ID=fisherscreen-prod,SCHEDULER_LOCATION=europe-west3
```

Note: `SCHEDULER_JOB_NAME` is added in Phase 2 after the Cloud Scheduler job exists:

```cmd
gcloud functions deploy fisherscreen-budget-stop ^
  --update-env-vars SCHEDULER_JOB_NAME=fisherscreen-monthly
```

## Step 5: Verify

Test the function via GCP Console → Pub/Sub → topic `fisherscreen-budget-alerts`
→ **Publish message** with body:

```json
{"costAmount": 11.0, "budgetAmount": 10.0}
```

Check Cloud Function logs — should print `"Paused '...' — cost..."` or
`"SCHEDULER_JOB_NAME not set"` if Phase 2 is not yet deployed.

## Reactivation after hard stop

**Manual only.** GCP Console → Cloud Scheduler → select job → **Resume**.
Do not automate reactivation — investigate cost spike first.
```

- [ ] **Step 3: Run full test suite to confirm nothing broke**

```
uv run python -m pytest -v
```

- [ ] **Step 4: Commit**

```
git add docs/infra/budget-alerts.md infra/budget_stop.py infra/requirements.txt
git commit -m "Add GCP budget alert docs and Cloud Function for $10 monthly hard stop"
```
