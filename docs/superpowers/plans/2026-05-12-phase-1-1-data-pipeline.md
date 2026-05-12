# Phase 1.1 — Data Pipeline + Basisfilter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the yfinance service, Firestore service, TTL cache wrapper, ScreenerRecord model, and four basis filters so that `run_basis_filter(tickers, client)` reduces ~2100 tickers to ~400 locally without real API calls in tests.

**Architecture:** Three layers: service layer (`YFinanceClientImpl`, `FirestoreClientImpl`), cache wrapper (`CachedYFinanceClient`), screener layer (`ScreenerRecord` + filters + runner). All layers accept Protocol types via DI — unit tests mock at the service boundary using `MagicMock`, no real network calls.

**Tech Stack:** Python 3.12, yfinance, google-cloud-firestore, pydantic (via pydantic-settings), pytest

---

## Prerequisites (manual, before Task 1)

Complete these before touching any code:

1. GCP project `fisherscreen-prod` exists
2. Run locally: `gcloud auth application-default login`
3. Firestore API enabled in `fisherscreen-prod`
4. Add to `.env`: `FISHERSCREEN_GCP_PROJECT_ID=fisherscreen-prod`

---

## Feature Branch

All commits go to `feature/phase-1-1-data-pipeline`. Create it first:

```
git checkout -b feature/phase-1-1-data-pipeline
```

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `pyproject.toml` | modify | Add google-cloud-firestore dependency |
| `app/config.py` | modify | Add `ticker_collection` setting |
| `app/models/__init__.py` | create | Package marker |
| `app/models/screener_record.py` | create | ScreenerRecord Pydantic model with all phase fields + `from_yfinance_info()` |
| `app/services/yfinance_client.py` | modify | Add `YFinanceClientImpl` below existing Protocol |
| `app/services/firestore_client.py` | modify | Add `FirestoreClientImpl` below existing Protocol |
| `app/services/cached_yfinance_client.py` | create | TTL-based cache wrapper implementing `YFinanceClient` Protocol |
| `app/screener/__init__.py` | create | Package marker |
| `app/screener/filters.py` | create | Four filter functions + `apply_basis_filters()` |
| `app/screener/runner.py` | create | `run_basis_filter()` entry point |
| `tests/models/__init__.py` | create | Package marker |
| `tests/models/test_screener_record.py` | create | Tests for ScreenerRecord model and `from_yfinance_info()` |
| `tests/services/__init__.py` | create | Package marker |
| `tests/services/test_yfinance_client.py` | create | Tests for YFinanceClientImpl (mocked yfinance) |
| `tests/services/test_firestore_client.py` | create | Tests for FirestoreClientImpl (mocked google.cloud.firestore) |
| `tests/services/test_cached_yfinance_client.py` | create | Tests for cache hit/miss/TTL expiry |
| `tests/screener/__init__.py` | create | Package marker |
| `tests/screener/test_filters.py` | create | Tests for each filter + `apply_basis_filters()` |
| `tests/screener/test_runner.py` | create | Tests for `run_basis_filter()` |

---

## Task 1: Dependency + config field

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing test for new config field**

Add to the bottom of `tests/test_config.py`:

```python
def test_reads_ticker_collection(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_TICKER_COLLECTION", "prod_ticker_cache")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.ticker_collection == "prod_ticker_cache"


def test_ticker_collection_defaults_to_dev():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.ticker_collection == "dev_ticker_cache"
```

- [ ] **Step 2: Run test to confirm it fails**

```
uv run python -m pytest tests/test_config.py -v
```

Expected: FAIL — `AttributeError: 'FisherScreenSettings' object has no attribute 'ticker_collection'`

- [ ] **Step 3: Add google-cloud-firestore dependency**

```
uv add google-cloud-firestore
```

Expected: `pyproject.toml` and `uv.lock` updated; `uv sync` runs automatically.

- [ ] **Step 4: Add ticker_collection to config**

Replace the full content of `app/config.py` with:

```python
from pydantic_settings import BaseSettings


class FisherScreenSettings(BaseSettings):
    gcp_project_id: str = ""
    edgar_user_agent: str = ""  # must be set via FISHERSCREEN_EDGAR_USER_AGENT; validated in edgar_client
    gemini_token_cap: int = 500_000
    apify_api_key: str = ""
    github_token: str = ""
    ticker_collection: str = "dev_ticker_cache"

    model_config = {
        "env_prefix": "FISHERSCREEN_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = FisherScreenSettings()
```

- [ ] **Step 5: Run full test suite and verify green**

```
uv run python -m pytest -v
```

Expected: all existing tests + 2 new config tests pass. Coverage ≥ 90%.

- [ ] **Step 6: Commit**

```
git add pyproject.toml uv.lock app/config.py tests/test_config.py
git commit -m "Add google-cloud-firestore dep and ticker_collection config"
```

---

## Task 2: ScreenerRecord model

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/screener_record.py`
- Create: `tests/models/__init__.py`
- Create: `tests/models/test_screener_record.py`

- [ ] **Step 1: Create package markers**

Create `app/models/__init__.py` — empty file.
Create `tests/models/__init__.py` — empty file.

- [ ] **Step 2: Write failing tests**

Create `tests/models/test_screener_record.py`:

```python
from datetime import datetime, timezone
from app.models.screener_record import ScreenerRecord


def test_minimal_construction():
    record = ScreenerRecord(ticker="AAPL")
    assert record.ticker == "AAPL"
    assert record.market_cap is None
    assert record.filter_passed_basis is None
    assert record.has_restatement is None
    assert record.gemini_score is None


def test_screened_at_defaults_to_now():
    before = datetime.now(timezone.utc)
    record = ScreenerRecord(ticker="AAPL")
    after = datetime.now(timezone.utc)
    assert before <= record.screened_at <= after


def test_from_yfinance_info_full():
    info = {
        "shortName": "Apple Inc.",
        "currency": "USD",
        "marketCap": 3_000_000_000_000,
        "averageVolume": 60_000_000,
        "currentPrice": 195.0,
        "bid": 194.9,
        "ask": 195.1,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "cik": "0000320193",
    }
    record = ScreenerRecord.from_yfinance_info("AAPL", info)
    assert record.ticker == "AAPL"
    assert record.name == "Apple Inc."
    assert record.currency == "USD"
    assert record.market_cap == 3_000_000_000_000
    assert record.avg_daily_volume == 60_000_000
    assert record.price == 195.0
    assert record.bid == 194.9
    assert record.ask == 195.1
    assert record.gics_sector == "Technology"
    assert record.gics_industry == "Consumer Electronics"
    assert record.cik == "0000320193"


def test_from_yfinance_info_falls_back_to_regular_market_price():
    info = {"regularMarketPrice": 50.0}
    record = ScreenerRecord.from_yfinance_info("XYZ", info)
    assert record.price == 50.0


def test_from_yfinance_info_missing_fields_give_none():
    record = ScreenerRecord.from_yfinance_info("EMPTY", {})
    assert record.ticker == "EMPTY"
    assert record.name is None
    assert record.market_cap is None
    assert record.price is None


def test_record_is_mutable():
    record = ScreenerRecord(ticker="AAPL")
    record.filter_passed_basis = True
    assert record.filter_passed_basis is True


def test_edgar_defaults():
    record = ScreenerRecord(ticker="AAPL")
    assert record.has_active_enforcement is False
    assert record.edgar_skipped is False
```

- [ ] **Step 3: Run tests to confirm they fail**

```
uv run python -m pytest tests/models/ -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 4: Implement ScreenerRecord**

Create `app/models/screener_record.py`:

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

    # EDGAR fields (populated in Phase 1.2)
    cik: str | None = None
    has_restatement: bool | None = None
    has_going_concern: bool | None = None
    has_active_enforcement: bool = False
    edgar_skipped: bool = False

    # Score fields (populated in Phase 1.3)
    gemini_score: float | None = None

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
            market_cap=info.get("marketCap"),
            avg_daily_volume=info.get("averageVolume"),
            price=info.get("currentPrice") or info.get("regularMarketPrice"),
            bid=info.get("bid"),
            ask=info.get("ask"),
            gics_sector=info.get("sector"),
            gics_industry=info.get("industry"),
            cik=info.get("cik"),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```
uv run python -m pytest tests/models/ -v
```

Expected: all 7 tests pass.

- [ ] **Step 6: Run full suite to verify coverage still holds**

```
uv run python -m pytest -v
```

Expected: all tests pass, coverage ≥ 90%.

- [ ] **Step 7: Commit**

```
git add app/models/ tests/models/
git commit -m "Add ScreenerRecord model with from_yfinance_info() classmethod"
```

---

## Task 3: FirestoreClientImpl

**Files:**
- Modify: `app/services/firestore_client.py`
- Create: `tests/services/__init__.py`
- Create: `tests/services/test_firestore_client.py`

- [ ] **Step 1: Create package marker**

Create `tests/services/__init__.py` — empty file.

- [ ] **Step 2: Write failing tests**

Create `tests/services/test_firestore_client.py`:

```python
from unittest.mock import MagicMock, patch
import pytest
from app.errors import DataSourceError


@patch("app.services.firestore_client.firestore")
def test_get_returns_dict_when_document_exists(mock_firestore_module):
    mock_db = MagicMock()
    mock_firestore_module.Client.return_value = mock_db
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"ticker": "AAPL", "marketCap": 3e12}
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

    from app.services.firestore_client import FirestoreClientImpl
    client = FirestoreClientImpl(project_id="test-project")
    result = client.get("dev_ticker_cache", "AAPL")

    assert result == {"ticker": "AAPL", "marketCap": 3e12}


@patch("app.services.firestore_client.firestore")
def test_get_returns_none_when_document_missing(mock_firestore_module):
    mock_db = MagicMock()
    mock_firestore_module.Client.return_value = mock_db
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

    from app.services.firestore_client import FirestoreClientImpl
    client = FirestoreClientImpl(project_id="test-project")
    result = client.get("dev_ticker_cache", "UNKNOWN")

    assert result is None


@patch("app.services.firestore_client.firestore")
def test_set_calls_firestore_set(mock_firestore_module):
    mock_db = MagicMock()
    mock_firestore_module.Client.return_value = mock_db

    from app.services.firestore_client import FirestoreClientImpl
    client = FirestoreClientImpl(project_id="test-project")
    client.set("dev_ticker_cache", "AAPL", {"marketCap": 3e12})

    mock_db.collection.return_value.document.return_value.set.assert_called_once_with(
        {"marketCap": 3e12}
    )


@patch("app.services.firestore_client.firestore")
def test_delete_calls_firestore_delete(mock_firestore_module):
    mock_db = MagicMock()
    mock_firestore_module.Client.return_value = mock_db

    from app.services.firestore_client import FirestoreClientImpl
    client = FirestoreClientImpl(project_id="test-project")
    client.delete("dev_ticker_cache", "AAPL")

    mock_db.collection.return_value.document.return_value.delete.assert_called_once()


@patch("app.services.firestore_client.firestore")
def test_get_raises_data_source_error_on_failure(mock_firestore_module):
    mock_db = MagicMock()
    mock_firestore_module.Client.return_value = mock_db
    mock_db.collection.return_value.document.return_value.get.side_effect = Exception(
        "network error"
    )

    from app.services.firestore_client import FirestoreClientImpl
    client = FirestoreClientImpl(project_id="test-project")

    with pytest.raises(DataSourceError, match="Firestore get failed"):
        client.get("dev_ticker_cache", "AAPL")


@patch("app.services.firestore_client.firestore")
def test_init_raises_data_source_error_when_adc_missing(mock_firestore_module):
    mock_firestore_module.Client.side_effect = Exception("ADC not found")

    from app.services.firestore_client import FirestoreClientImpl

    with pytest.raises(DataSourceError, match="ADC not configured"):
        FirestoreClientImpl(project_id="test-project")
```

- [ ] **Step 3: Run tests to confirm they fail**

```
uv run python -m pytest tests/services/test_firestore_client.py -v
```

Expected: FAIL — `ImportError: cannot import name 'FirestoreClientImpl'`

- [ ] **Step 4: Implement FirestoreClientImpl**

Replace the full content of `app/services/firestore_client.py`:

```python
from typing import Any, Protocol

from google.cloud import firestore

from app.errors import DataSourceError


class FirestoreClient(Protocol):
    def get(self, collection: str, document_id: str) -> dict[str, Any] | None: ...
    def set(self, collection: str, document_id: str, data: dict[str, Any]) -> None: ...
    def delete(self, collection: str, document_id: str) -> None: ...


class FirestoreClientImpl:
    def __init__(self, project_id: str) -> None:
        try:
            self._db = firestore.Client(project=project_id)
        except Exception as exc:
            raise DataSourceError(f"ADC not configured or Firestore unreachable: {exc}") from exc

    def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        try:
            doc = self._db.collection(collection).document(document_id).get()
        except Exception as exc:
            raise DataSourceError(f"Firestore get failed: {exc}") from exc
        if not doc.exists:
            return None
        return doc.to_dict()

    def set(self, collection: str, document_id: str, data: dict[str, Any]) -> None:
        try:
            self._db.collection(collection).document(document_id).set(data)
        except Exception as exc:
            raise DataSourceError(f"Firestore set failed: {exc}") from exc

    def delete(self, collection: str, document_id: str) -> None:
        try:
            self._db.collection(collection).document(document_id).delete()
        except Exception as exc:
            raise DataSourceError(f"Firestore delete failed: {exc}") from exc
```

- [ ] **Step 5: Run tests to verify they pass**

```
uv run python -m pytest tests/services/test_firestore_client.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 6: Run full suite**

```
uv run python -m pytest -v
```

Expected: all tests pass. `app/services/` is excluded from coverage — threshold still met.

- [ ] **Step 7: Commit**

```
git add app/services/firestore_client.py tests/services/
git commit -m "Add FirestoreClientImpl with ADC error handling"
```

---

## Task 4: YFinanceClientImpl

**Files:**
- Modify: `app/services/yfinance_client.py`
- Create: `tests/services/test_yfinance_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/services/test_yfinance_client.py`:

```python
from unittest.mock import MagicMock, patch
import pytest
from app.errors import DataSourceError


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_returns_info_dict(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = {"shortName": "Apple Inc.", "marketCap": 3_000_000_000_000}
    mock_yf.Ticker.return_value = mock_ticker

    from app.services.yfinance_client import YFinanceClientImpl
    client = YFinanceClientImpl()
    result = client.get_ticker_info("AAPL")

    mock_yf.Ticker.assert_called_once_with("AAPL")
    assert result["shortName"] == "Apple Inc."
    assert result["marketCap"] == 3_000_000_000_000


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_raises_data_source_error_on_empty(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = {}
    mock_yf.Ticker.return_value = mock_ticker

    from app.services.yfinance_client import YFinanceClientImpl
    client = YFinanceClientImpl()

    with pytest.raises(DataSourceError, match="empty info"):
        client.get_ticker_info("BADTICKER")


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_raises_data_source_error_on_exception(mock_yf):
    mock_yf.Ticker.side_effect = Exception("network error")

    from app.services.yfinance_client import YFinanceClientImpl
    client = YFinanceClientImpl()

    with pytest.raises(DataSourceError, match="yfinance failed"):
        client.get_ticker_info("AAPL")


@patch("app.services.yfinance_client.yf")
def test_get_historical_returns_dataframe(mock_yf):
    import pandas as pd
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame({"Close": [100.0, 101.0]})
    mock_yf.Ticker.return_value = mock_ticker

    from app.services.yfinance_client import YFinanceClientImpl
    client = YFinanceClientImpl()
    result = client.get_historical("AAPL", "1mo")

    mock_ticker.history.assert_called_once_with(period="1mo")
    assert len(result) == 2


@patch("app.services.yfinance_client.yf")
def test_get_financials_returns_dict(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.financials = {"Revenue": 394_000_000_000}
    mock_yf.Ticker.return_value = mock_ticker

    from app.services.yfinance_client import YFinanceClientImpl
    client = YFinanceClientImpl()
    result = client.get_financials("AAPL")

    assert result == {"Revenue": 394_000_000_000}
```

- [ ] **Step 2: Run tests to confirm they fail**

```
uv run python -m pytest tests/services/test_yfinance_client.py -v
```

Expected: FAIL — `ImportError: cannot import name 'YFinanceClientImpl'`

- [ ] **Step 3: Implement YFinanceClientImpl**

Replace the full content of `app/services/yfinance_client.py`:

```python
from typing import Any, Protocol

import yfinance as yf

from app.errors import DataSourceError


class YFinanceClient(Protocol):
    def get_ticker_info(self, ticker: str) -> dict[str, Any]: ...
    def get_historical(self, ticker: str, period: str) -> Any: ...
    def get_financials(self, ticker: str) -> dict[str, Any]: ...


class YFinanceClientImpl:
    def get_ticker_info(self, ticker: str) -> dict[str, Any]:
        try:
            data = yf.Ticker(ticker).info
        except Exception as exc:
            raise DataSourceError(f"yfinance failed for {ticker}: {exc}") from exc
        if not data:
            raise DataSourceError(f"yfinance returned empty info for {ticker}")
        return data

    def get_historical(self, ticker: str, period: str) -> Any:
        try:
            return yf.Ticker(ticker).history(period=period)
        except Exception as exc:
            raise DataSourceError(f"yfinance history failed for {ticker}: {exc}") from exc

    def get_financials(self, ticker: str) -> dict[str, Any]:
        try:
            return yf.Ticker(ticker).financials
        except Exception as exc:
            raise DataSourceError(f"yfinance financials failed for {ticker}: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run python -m pytest tests/services/test_yfinance_client.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Run full suite**

```
uv run python -m pytest -v
```

Expected: all tests pass, coverage ≥ 90%.

- [ ] **Step 6: Commit**

```
git add app/services/yfinance_client.py tests/services/test_yfinance_client.py
git commit -m "Add YFinanceClientImpl with DataSourceError wrapping"
```

---

## Task 5: CachedYFinanceClient

**Files:**
- Create: `app/services/cached_yfinance_client.py`
- Create: `tests/services/test_cached_yfinance_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/services/test_cached_yfinance_client.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock


def _make_client(yfinance_mock, firestore_mock):
    from app.services.cached_yfinance_client import CachedYFinanceClient
    return CachedYFinanceClient(
        yfinance=yfinance_mock,
        firestore=firestore_mock,
        collection="dev_ticker_cache",
    )


def test_cache_miss_fetches_from_yfinance_and_stores():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = None  # cache miss
    mock_yf.get_ticker_info.return_value = {"shortName": "Apple", "marketCap": 3e12}

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("AAPL")

    mock_yf.get_ticker_info.assert_called_once_with("AAPL")
    mock_fs.set.assert_called_once()
    stored_data = mock_fs.set.call_args[0][2]
    assert "_cached_at" in stored_data
    assert result["shortName"] == "Apple"
    assert "_cached_at" not in result


def test_cache_hit_returns_cached_data_without_calling_yfinance():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    mock_fs.get.return_value = {
        "shortName": "Apple",
        "marketCap": 3e12,
        "_cached_at": fresh_ts,
    }

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("AAPL")

    mock_yf.get_ticker_info.assert_not_called()
    assert result["shortName"] == "Apple"
    assert "_cached_at" not in result


def test_expired_cache_refetches_from_yfinance():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    mock_fs.get.return_value = {
        "shortName": "Apple (stale)",
        "_cached_at": stale_ts,
    }
    mock_yf.get_ticker_info.return_value = {"shortName": "Apple (fresh)", "marketCap": 3e12}

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("AAPL")

    mock_yf.get_ticker_info.assert_called_once_with("AAPL")
    assert result["shortName"] == "Apple (fresh)"


def test_get_historical_delegates_to_yfinance_without_cache():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_yf.get_historical.return_value = "some_dataframe"

    client = _make_client(mock_yf, mock_fs)
    result = client.get_historical("AAPL", "1mo")

    mock_yf.get_historical.assert_called_once_with("AAPL", "1mo")
    mock_fs.get.assert_not_called()
    assert result == "some_dataframe"


def test_get_financials_delegates_to_yfinance_without_cache():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_yf.get_financials.return_value = {"Revenue": 394e9}

    client = _make_client(mock_yf, mock_fs)
    result = client.get_financials("AAPL")

    mock_yf.get_financials.assert_called_once_with("AAPL")
    assert result == {"Revenue": 394e9}


def test_missing_cached_at_field_triggers_refetch():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = {"shortName": "Apple"}  # no _cached_at
    mock_yf.get_ticker_info.return_value = {"shortName": "Apple Fresh", "marketCap": 3e12}

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("AAPL")

    mock_yf.get_ticker_info.assert_called_once_with("AAPL")
    assert result["shortName"] == "Apple Fresh"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
uv run python -m pytest tests/services/test_cached_yfinance_client.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.cached_yfinance_client'`

- [ ] **Step 3: Implement CachedYFinanceClient**

Create `app/services/cached_yfinance_client.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.firestore_client import FirestoreClient
    from app.services.yfinance_client import YFinanceClient

_TTL_SECONDS = 24 * 3600  # 24 hours


class CachedYFinanceClient:
    def __init__(
        self,
        yfinance: YFinanceClient,
        firestore: FirestoreClient,
        collection: str,
    ) -> None:
        self._yfinance = yfinance
        self._firestore = firestore
        self._collection = collection

    def get_ticker_info(self, ticker: str) -> dict[str, Any]:
        cached = self._firestore.get(self._collection, ticker)
        if cached and self._is_fresh(cached):
            return {k: v for k, v in cached.items() if k != "_cached_at"}
        data = self._yfinance.get_ticker_info(ticker)
        self._firestore.set(
            self._collection,
            ticker,
            {**data, "_cached_at": datetime.now(timezone.utc).isoformat()},
        )
        return data

    def get_historical(self, ticker: str, period: str) -> Any:
        return self._yfinance.get_historical(ticker, period)

    def get_financials(self, ticker: str) -> dict[str, Any]:
        return self._yfinance.get_financials(ticker)

    def _is_fresh(self, cached: dict[str, Any]) -> bool:
        cached_at_str = cached.get("_cached_at")
        if not cached_at_str:
            return False
        cached_at = datetime.fromisoformat(cached_at_str)
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - cached_at).total_seconds() < _TTL_SECONDS
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run python -m pytest tests/services/test_cached_yfinance_client.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run full suite**

```
uv run python -m pytest -v
```

Expected: all tests pass, coverage ≥ 90%.

- [ ] **Step 6: Commit**

```
git add app/services/cached_yfinance_client.py tests/services/test_cached_yfinance_client.py
git commit -m "Add CachedYFinanceClient with 24h TTL Firestore caching"
```

---

## Task 6: Basis filters

**Files:**
- Create: `app/screener/__init__.py`
- Create: `app/screener/filters.py`
- Create: `tests/screener/__init__.py`
- Create: `tests/screener/test_filters.py`

- [ ] **Step 1: Create package markers**

Create `app/screener/__init__.py` — empty file.
Create `tests/screener/__init__.py` — empty file.

- [ ] **Step 2: Write failing tests**

Create `tests/screener/test_filters.py`:

```python
import pytest
from app.models.screener_record import ScreenerRecord
from app.screener.filters import (
    apply_basis_filters,
    passes_liquidity_filter,
    passes_market_cap_filter,
    passes_penny_stock_filter,
    passes_volume_filter,
)


def _record(**kwargs) -> ScreenerRecord:
    defaults = {
        "ticker": "TEST",
        "market_cap": 500_000_000,
        "avg_daily_volume": 200_000,
        "price": 50.0,
        "bid": 49.8,
        "ask": 50.2,
    }
    return ScreenerRecord(**{**defaults, **kwargs})


# --- market cap ---

def test_market_cap_passes_above_threshold():
    assert passes_market_cap_filter(_record(market_cap=300_000_001)) is True


def test_market_cap_fails_at_threshold():
    assert passes_market_cap_filter(_record(market_cap=299_999_999)) is False


def test_market_cap_fails_when_none():
    assert passes_market_cap_filter(_record(market_cap=None)) is False


# --- volume ---

def test_volume_passes_above_threshold():
    assert passes_volume_filter(_record(avg_daily_volume=100_001)) is True


def test_volume_fails_below_threshold():
    assert passes_volume_filter(_record(avg_daily_volume=99_999)) is False


def test_volume_fails_when_none():
    assert passes_volume_filter(_record(avg_daily_volume=None)) is False


# --- penny stock ---

def test_penny_stock_passes_at_one_dollar():
    assert passes_penny_stock_filter(_record(price=1.0)) is True


def test_penny_stock_fails_below_one_dollar():
    assert passes_penny_stock_filter(_record(price=0.99)) is False


def test_penny_stock_fails_when_price_none():
    assert passes_penny_stock_filter(_record(price=None)) is False


# --- liquidity (bid-ask spread) ---

def test_liquidity_passes_tight_spread():
    # spread = (50.1 - 49.9) / 50.0 = 0.4%
    assert passes_liquidity_filter(_record(bid=49.9, ask=50.1)) is True


def test_liquidity_fails_wide_spread():
    # spread = (55.0 - 45.0) / 50.0 = 20%
    assert passes_liquidity_filter(_record(bid=45.0, ask=55.0)) is False


def test_liquidity_fails_when_bid_is_none():
    assert passes_liquidity_filter(_record(bid=None, ask=50.0)) is False


def test_liquidity_fails_when_ask_is_none():
    assert passes_liquidity_filter(_record(bid=49.9, ask=None)) is False


def test_liquidity_fails_when_bid_is_zero():
    assert passes_liquidity_filter(_record(bid=0.0, ask=50.0)) is False


# --- apply_basis_filters ---

def test_apply_basis_filters_returns_only_passing_records():
    passing = _record(ticker="GOOD")
    failing = _record(ticker="SMALL", market_cap=100_000)

    result = apply_basis_filters([passing, failing])

    assert len(result) == 1
    assert result[0].ticker == "GOOD"
    assert result[0].filter_passed_basis is True


def test_apply_basis_filters_sets_failed_reason():
    record = _record(ticker="SMALL", market_cap=100_000)
    apply_basis_filters([record])
    assert record.filter_failed_reason == "market_cap"


def test_apply_basis_filters_checks_filters_in_order():
    # fails both market_cap and volume — reason should be market_cap (first checked)
    record = _record(ticker="DOUBLE_FAIL", market_cap=100_000, avg_daily_volume=10)
    apply_basis_filters([record])
    assert record.filter_failed_reason == "market_cap"


def test_apply_basis_filters_returns_empty_for_all_failures():
    records = [_record(ticker="PENNY", price=0.50)]
    assert apply_basis_filters(records) == []
```

- [ ] **Step 3: Run tests to confirm they fail**

```
uv run python -m pytest tests/screener/test_filters.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.screener'`

- [ ] **Step 4: Implement filters**

Create `app/screener/filters.py`:

```python
import logging

from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)

MIN_MARKET_CAP_USD: float = 300_000_000
MIN_AVG_DAILY_VOLUME: float = 100_000
MIN_PRICE_USD: float = 1.0
MAX_BID_ASK_SPREAD_PCT: float = 0.05


def passes_market_cap_filter(record: ScreenerRecord) -> bool:
    if record.market_cap is None:
        logger.warning("ticker=%s market_cap missing", record.ticker)
        return False
    return record.market_cap >= MIN_MARKET_CAP_USD


def passes_volume_filter(record: ScreenerRecord) -> bool:
    if record.avg_daily_volume is None:
        logger.warning("ticker=%s avg_daily_volume missing", record.ticker)
        return False
    return record.avg_daily_volume >= MIN_AVG_DAILY_VOLUME


def passes_penny_stock_filter(record: ScreenerRecord) -> bool:
    if record.price is None:
        logger.warning("ticker=%s price missing", record.ticker)
        return False
    return record.price >= MIN_PRICE_USD


def passes_liquidity_filter(record: ScreenerRecord) -> bool:
    if not record.bid or not record.ask:
        logger.warning("ticker=%s bid/ask missing or zero", record.ticker)
        return False
    mid = (record.bid + record.ask) / 2
    spread_pct = (record.ask - record.bid) / mid
    return spread_pct <= MAX_BID_ASK_SPREAD_PCT


def _get_fail_reason(record: ScreenerRecord) -> str | None:
    if not passes_market_cap_filter(record):
        return "market_cap"
    if not passes_volume_filter(record):
        return "avg_volume"
    if not passes_penny_stock_filter(record):
        return "penny_stock"
    if not passes_liquidity_filter(record):
        return "liquidity"
    return None


def apply_basis_filters(records: list[ScreenerRecord]) -> list[ScreenerRecord]:
    passed = []
    for record in records:
        reason = _get_fail_reason(record)
        if reason:
            record.filter_failed_reason = reason
        else:
            record.filter_passed_basis = True
            passed.append(record)
    logger.info("basis_filter: %d/%d records passed", len(passed), len(records))
    return passed
```

- [ ] **Step 5: Run tests to verify they pass**

```
uv run python -m pytest tests/screener/test_filters.py -v
```

Expected: all 19 tests pass.

- [ ] **Step 6: Run full suite**

```
uv run python -m pytest -v
```

Expected: all tests pass, coverage ≥ 90%.

- [ ] **Step 7: Commit**

```
git add app/screener/ tests/screener/test_filters.py
git commit -m "Add four basis filters with apply_basis_filters()"
```

---

## Task 7: Screener runner

**Files:**
- Create: `app/screener/runner.py`
- Create: `tests/screener/test_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/screener/test_runner.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.errors import DataSourceError
from app.screener.runner import run_basis_filter


def _make_yf_mock(info: dict) -> MagicMock:
    mock = MagicMock()
    mock.get_ticker_info.return_value = info
    return mock


_PASSING_INFO = {
    "shortName": "Big Corp",
    "currency": "USD",
    "marketCap": 500_000_000,
    "averageVolume": 200_000,
    "currentPrice": 50.0,
    "bid": 49.8,
    "ask": 50.2,
}


def test_run_returns_passing_records():
    mock_yf = _make_yf_mock(_PASSING_INFO)
    result = run_basis_filter(["BIGC"], mock_yf)

    assert len(result) == 1
    assert result[0].ticker == "BIGC"
    assert result[0].filter_passed_basis is True


def test_run_skips_tickers_with_data_source_errors():
    mock_yf = MagicMock()
    mock_yf.get_ticker_info.side_effect = DataSourceError("network error")

    result = run_basis_filter(["FAIL"], mock_yf)

    assert result == []


def test_run_processes_multiple_tickers():
    mock_yf = MagicMock()

    def side_effect(ticker):
        if ticker == "GOOD":
            return _PASSING_INFO
        return {**_PASSING_INFO, "currentPrice": 0.50}  # penny stock

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["GOOD", "PENY"], mock_yf)

    assert len(result) == 1
    assert result[0].ticker == "GOOD"


def test_run_returns_empty_for_empty_ticker_list():
    mock_yf = MagicMock()
    result = run_basis_filter([], mock_yf)
    assert result == []


def test_run_continues_after_individual_data_source_error():
    mock_yf = MagicMock()

    def side_effect(ticker):
        if ticker == "FAIL":
            raise DataSourceError("bad ticker")
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["FAIL", "GOOD"], mock_yf)

    assert len(result) == 1
    assert result[0].ticker == "GOOD"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
uv run python -m pytest tests/screener/test_runner.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.screener.runner'`

- [ ] **Step 3: Implement the runner**

Create `app/screener/runner.py`:

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.errors import DataSourceError
from app.models.screener_record import ScreenerRecord
from app.screener.filters import apply_basis_filters

if TYPE_CHECKING:
    from app.services.yfinance_client import YFinanceClient

logger = logging.getLogger(__name__)


def run_basis_filter(
    tickers: list[str],
    yfinance: YFinanceClient,
) -> list[ScreenerRecord]:
    records: list[ScreenerRecord] = []
    for ticker in tickers:
        try:
            info = yfinance.get_ticker_info(ticker)
            records.append(ScreenerRecord.from_yfinance_info(ticker, info))
        except DataSourceError as exc:
            logger.warning("ticker=%s data fetch failed: %s", ticker, exc)
    logger.info("runner: fetched %d/%d records", len(records), len(tickers))
    return apply_basis_filters(records)
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run python -m pytest tests/screener/test_runner.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Run full suite with coverage**

```
uv run python -m pytest -v
```

Expected: all tests pass. Note the final coverage number — should be ≥ 90%.

- [ ] **Step 6: Commit**

```
git add app/screener/runner.py tests/screener/test_runner.py
git commit -m "Add run_basis_filter() screener runner"
```

---

## Self-Review

### Spec coverage

| Spec requirement | Task |
|---|---|
| `yfinance_client.py` (real) — Ticker-Info, Historical, Financials | Task 4 |
| `firestore_client.py` (real) — get/set/delete mit TTL-Metadaten | Tasks 3 + 5 |
| Datenmodell `ScreenerRecord` (Pydantic, alle Felder für Basisfilter + EDGAR + Score) | Task 2 |
| Caching-Strategie: yfinance-Daten per Ticker mit TTL 24h in `dev_ticker_cache` | Task 5 |
| Basisfilter: Market Cap | Task 6 |
| Basisfilter: Durchschnittsvolumen | Task 6 |
| Basisfilter: Penny Stock (< $1) | Task 6 |
| Basisfilter: Liquidität (Bid-Ask) | Task 6 |
| Abhängigkeit `google-cloud-firestore` + Config-Feld | Task 1 |
| Fehler früh und klar wenn ADC fehlt | Task 3 (`DataSourceError("ADC not configured")`) |
| Kein echter Netzwerk-Call in Unit-Tests | All tasks — MagicMock throughout |

All spec requirements covered. ✓

### Placeholder scan

No TBDs, no TODOs, no "similar to Task N" references. All steps include complete code. ✓

### Type consistency

- `ScreenerRecord` defined in Task 2, used in Tasks 6 + 7 — field names (`market_cap`, `avg_daily_volume`, `price`, `bid`, `ask`, `filter_passed_basis`, `filter_failed_reason`) consistent throughout.
- `YFinanceClient` Protocol (Task 4): `get_ticker_info(ticker: str) -> dict[str, Any]` — called identically in Task 5 (`CachedYFinanceClient`) and Task 7 (runner).
- `FirestoreClient` Protocol (Task 3): `get/set/delete` signatures — used identically in Task 5. ✓
