# Phase 1.2 — EDGAR Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `EdgarClientImpl` with restatement and going-concern detection, a 7-day Firestore cache wrapper, EDGAR filter step, and a runner function that reduces the ~400-ticker basis-filtered set by removing companies with non-reliance on financials (8-K Item 4.02) or going-concern disclosures ("raise substantial doubt" in 10-K/10-Q).

**Architecture:** `EdgarClientImpl` uses sync `httpx` + `time.sleep(0.5)` rate limiting. Two real HTTP calls per CIK: `submissions.json` (restatement check) and EFTS full-text search (going-concern check). `has_active_enforcement` is a logged stub returning `False`. `CachedEdgarClient` wraps the impl with 7-day TTL caching in Firestore `dev_edgar_cache`, keyed by CIK; both signals are fetched and stored together in one Firestore document to minimize API calls. `run_edgar_filter` in `runner.py` populates EDGAR fields on existing `ScreenerRecord`s, then calls `apply_edgar_filters`. The `ScreenerRecord.cik` field (already populated from yfinance) is the key — records without a CIK are marked `edgar_skipped=True` and passed through without penalization.

**Tech Stack:** Python 3.12, httpx (already in `pyproject.toml`), google-cloud-firestore, pydantic, pytest

---

## Prerequisites

None — `httpx` and `google-cloud-firestore` are already in `pyproject.toml`. `FISHERSCREEN_EDGAR_USER_AGENT` must be set in `.env` before running integration tests.

## Feature Branch

All commits go to `feature/phase-1-2-edgar-signals`. Create it from `main`:

```
git checkout main
git checkout -b feature/phase-1-2-edgar-signals
```

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | modify | Add `edgar_collection` setting |
| `tests/test_config.py` | modify | Tests for `edgar_collection` default + env override |
| `app/services/edgar_client.py` | replace | Update `EdgarClient` Protocol (use `cik` not `ticker`); add `EdgarClientImpl` |
| `tests/services/test_edgar_client.py` | create | Tests for `EdgarClientImpl` (mock httpx + time) |
| `app/services/cached_edgar_client.py` | create | 7-day TTL Firestore cache wrapper, shared fetch per CIK |
| `tests/services/test_cached_edgar_client.py` | create | Tests for cache hit / miss / TTL expiry / shared-fetch |
| `app/screener/filters.py` | modify | Add `apply_edgar_filters()` |
| `tests/screener/test_filters.py` | modify | Tests for EDGAR filter logic (appended at bottom) |
| `app/screener/runner.py` | modify | Add `run_edgar_filter()` |
| `tests/screener/test_runner.py` | modify | Tests for `run_edgar_filter()` (appended at bottom) |
| `app/screener/compose.py` | modify | Add `build_edgar_pipeline()` |
| `tests/screener/test_compose.py` | modify | Test EDGAR pipeline wiring (appended at bottom) |

---

## Task 1: Config field `edgar_collection`

**Files:**
- Modify: `app/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Append to the bottom of `tests/test_config.py`:

```python
def test_reads_edgar_collection(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_EDGAR_COLLECTION", "prod_edgar_cache")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.edgar_collection == "prod_edgar_cache"


def test_edgar_collection_defaults_to_dev():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.edgar_collection == "dev_edgar_cache"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
uv run python -m pytest tests/test_config.py -v
```

Expected: FAIL — `AttributeError: 'FisherScreenSettings' object has no attribute 'edgar_collection'`

- [ ] **Step 3: Add `edgar_collection` to config**

Replace the full content of `app/config.py`:

```python
from pydantic_settings import BaseSettings


class FisherScreenSettings(BaseSettings):
    gcp_project_id: str = ""
    edgar_user_agent: str = ""  # must be set via FISHERSCREEN_EDGAR_USER_AGENT; validated in EdgarClientImpl
    gemini_token_cap: int = 500_000
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

- [ ] **Step 4: Run tests to verify they pass**

```
uv run python -m pytest tests/test_config.py -v
```

Expected: all config tests pass.

- [ ] **Step 5: Run full suite**

```
uv run python -m pytest -v
```

Expected: all tests pass, coverage ≥ 90%.

- [ ] **Step 6: Commit**

```
git add app/config.py tests/test_config.py
git commit -m "Add edgar_collection config field"
```

---

## Task 2: `EdgarClientImpl`

**Files:**
- Replace: `app/services/edgar_client.py`
- Create: `tests/services/test_edgar_client.py`

The existing file has only a Protocol stub. This task replaces it with a complete implementation. The Protocol is also updated: parameter names change from `ticker` to `cik`, and `get_earnings_call_transcripts` is removed (transcripts are not an EDGAR data source — they belong to a future Tool B phase).

- [ ] **Step 1: Write failing tests**

Create `tests/services/test_edgar_client.py`:

```python
import pytest
from unittest.mock import MagicMock, patch

from app.errors import DataSourceError


def _make_client(user_agent="Test Agent <test@example.com>"):
    from app.services.edgar_client import EdgarClientImpl
    return EdgarClientImpl(user_agent=user_agent)


def test_init_raises_when_user_agent_empty():
    from app.services.edgar_client import EdgarClientImpl
    with pytest.raises(DataSourceError, match="user agent"):
        EdgarClientImpl(user_agent="")


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_restatement_returns_true_when_8k_item_4_02_found(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-K"],
                "filingDate": ["2025-03-15", "2025-02-01"],
                "items": ["4.02", ""],
            }
        }
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_restatement("320193", years=3) is True


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_restatement_returns_false_when_no_4_02(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "filingDate": ["2025-03-15"],
                "items": ["1.01"],
            }
        }
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_restatement("320193") is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_restatement_ignores_filings_outside_date_window(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "filingDate": ["2010-01-01"],  # well outside the 3-year window
                "items": ["4.02"],
            }
        }
    }
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_restatement("320193", years=3) is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_restatement_returns_false_for_empty_filings(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"filings": {"recent": {}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_restatement("320193") is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_returns_true_when_hits_found(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"hits": {"total": {"value": 2}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_going_concern("320193") is True


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_has_going_concern_returns_false_when_no_hits(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"hits": {"total": {"value": 0}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    assert client.has_going_concern("320193") is False


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_raises_data_source_error_on_non_200(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    with pytest.raises(DataSourceError, match="403"):
        client.has_restatement("320193")


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_get_raises_data_source_error_on_network_failure(mock_httpx, mock_time):
    mock_httpx.get.side_effect = Exception("connection refused")

    client = _make_client()
    with pytest.raises(DataSourceError, match="HTTP request failed"):
        client.has_restatement("320193")


@patch("app.services.edgar_client.time")
@patch("app.services.edgar_client.httpx")
def test_cik_is_zero_padded_to_10_digits_in_url(mock_httpx, mock_time):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"filings": {"recent": {}}}
    mock_httpx.get.return_value = mock_resp

    client = _make_client()
    client.has_restatement("320193")

    call_url = mock_httpx.get.call_args[0][0]
    assert "CIK0000320193" in call_url


def test_has_active_enforcement_returns_false_and_logs_warning(caplog):
    import logging
    client = _make_client()
    with caplog.at_level(logging.WARNING):
        result = client.has_active_enforcement("320193")
    assert result is False
    assert "not implemented" in caplog.text
```

- [ ] **Step 2: Run tests to confirm they fail**

```
uv run python -m pytest tests/services/test_edgar_client.py -v
```

Expected: FAIL — `ImportError: cannot import name 'EdgarClientImpl'`

- [ ] **Step 3: Implement `EdgarClientImpl`**

Replace the full content of `app/services/edgar_client.py`:

```python
import logging
import time
from datetime import date, timedelta
from typing import Any, Protocol

import httpx

from app.errors import DataSourceError

logger = logging.getLogger(__name__)


class EdgarClient(Protocol):
    def has_restatement(self, cik: str, years: int = 3) -> bool: ...
    def has_going_concern(self, cik: str, months: int = 24) -> bool: ...
    def has_active_enforcement(self, cik: str) -> bool: ...


class EdgarClientImpl:
    _SEC_BASE = "https://data.sec.gov"
    _EFTS_BASE = "https://efts.sec.gov"
    _RATE_LIMIT_SECONDS = 0.5

    def __init__(self, user_agent: str) -> None:
        if not user_agent:
            raise DataSourceError(
                "EDGAR user agent not set — configure FISHERSCREEN_EDGAR_USER_AGENT"
            )
        self._headers = {"User-Agent": user_agent}

    def _get(self, url: str) -> dict[str, Any]:
        time.sleep(self._RATE_LIMIT_SECONDS)
        try:
            resp = httpx.get(url, headers=self._headers, timeout=30)
        except Exception as exc:
            raise DataSourceError(f"EDGAR HTTP request failed: {exc}") from exc
        if resp.status_code != 200:
            raise DataSourceError(f"EDGAR returned {resp.status_code} for {url}")
        return resp.json()

    def has_restatement(self, cik: str, years: int = 3) -> bool:
        padded = cik.zfill(10)
        url = f"{self._SEC_BASE}/submissions/CIK{padded}.json"
        data = self._get(url)
        cutoff = (date.today() - timedelta(days=years * 365)).isoformat()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        items_list = recent.get("items", [])
        for form, filing_date, items in zip(forms, dates, items_list):
            if form == "8-K" and filing_date >= cutoff and "4.02" in str(items):
                return True
        return False

    def has_going_concern(self, cik: str, months: int = 24) -> bool:
        padded = cik.zfill(10)
        startdt = (date.today() - timedelta(days=months * 30)).isoformat()
        url = (
            f"{self._EFTS_BASE}/LATEST/search-index"
            f"?q=%22raise+substantial+doubt%22"
            f"&forms=10-K,10-Q"
            f"&dateRange=custom&startdt={startdt}"
            f"&entity={padded}"
        )
        data = self._get(url)
        return data.get("hits", {}).get("total", {}).get("value", 0) > 0

    def has_active_enforcement(self, cik: str) -> bool:
        logger.warning(
            "has_active_enforcement not implemented — returning False for cik=%s", cik
        )
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run python -m pytest tests/services/test_edgar_client.py -v
```

Expected: all 11 tests pass.

- [ ] **Step 5: Run full suite**

```
uv run python -m pytest -v
```

Expected: all tests pass, coverage ≥ 90%.

- [ ] **Step 6: Commit**

```
git add app/services/edgar_client.py tests/services/test_edgar_client.py
git commit -m "Add EdgarClientImpl with restatement, going-concern, and enforcement stub"
```

---

## Task 3: `CachedEdgarClient`

**Files:**
- Create: `app/services/cached_edgar_client.py`
- Create: `tests/services/test_cached_edgar_client.py`

The cache stores both signals together in one Firestore document per CIK: `{has_restatement, has_going_concern, _cached_at}`. Both `has_restatement` and `has_going_concern` call `_fetch_and_cache()`, which checks whether a fresh entry exists before hitting the EDGAR API. This means the second method call for a CIK is always a cache read — no extra API call. TTL: 7 days.

- [ ] **Step 1: Write failing tests**

Create `tests/services/test_cached_edgar_client.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock


def _make_client(edgar_mock, firestore_mock):
    from app.services.cached_edgar_client import CachedEdgarClient
    return CachedEdgarClient(
        edgar=edgar_mock,
        firestore=firestore_mock,
        collection="dev_edgar_cache",
    )


def test_cache_miss_fetches_both_signals_and_stores():
    mock_edgar = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = None
    mock_edgar.has_restatement.return_value = False
    mock_edgar.has_going_concern.return_value = True

    client = _make_client(mock_edgar, mock_fs)
    result = client.has_going_concern("0000320193")

    assert result is True
    mock_edgar.has_restatement.assert_called_once_with("0000320193")
    mock_edgar.has_going_concern.assert_called_once_with("0000320193")
    mock_fs.set.assert_called_once()
    stored = mock_fs.set.call_args[0][2]
    assert stored["has_going_concern"] is True
    assert stored["has_restatement"] is False
    assert "_cached_at" in stored


def test_cache_hit_returns_cached_data_without_calling_edgar():
    mock_edgar = MagicMock()
    mock_fs = MagicMock()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    mock_fs.get.return_value = {
        "has_restatement": True,
        "has_going_concern": False,
        "_cached_at": fresh_ts,
    }

    client = _make_client(mock_edgar, mock_fs)
    assert client.has_restatement("0000320193") is True
    mock_edgar.has_restatement.assert_not_called()


def test_expired_cache_refetches_from_edgar():
    mock_edgar = MagicMock()
    mock_fs = MagicMock()
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    mock_fs.get.return_value = {
        "has_restatement": False,
        "has_going_concern": False,
        "_cached_at": stale_ts,
    }
    mock_edgar.has_restatement.return_value = True
    mock_edgar.has_going_concern.return_value = False

    client = _make_client(mock_edgar, mock_fs)
    result = client.has_restatement("0000320193")

    mock_edgar.has_restatement.assert_called_once()
    assert result is True


def test_second_method_call_reuses_freshly_written_cache():
    # First call: cache miss → fetches from Edgar, writes to Firestore
    # Second call: Firestore now returns the fresh data → no second Edgar call
    mock_edgar = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = None  # will be updated after first set
    mock_edgar.has_restatement.return_value = False
    mock_edgar.has_going_concern.return_value = False

    call_count = {"n": 0}
    def get_side_effect(collection, key):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return None  # first call: cache miss
        fresh_ts = datetime.now(timezone.utc).isoformat()
        return {"has_restatement": False, "has_going_concern": False, "_cached_at": fresh_ts}

    mock_fs.get.side_effect = get_side_effect

    client = _make_client(mock_edgar, mock_fs)
    client.has_restatement("0000320193")
    client.has_going_concern("0000320193")

    # Edgar should have been called exactly once for each signal (from the first fetch)
    assert mock_edgar.has_restatement.call_count == 1
    assert mock_edgar.has_going_concern.call_count == 1


def test_has_active_enforcement_delegates_to_edgar_without_caching():
    mock_edgar = MagicMock()
    mock_edgar.has_active_enforcement.return_value = False
    mock_fs = MagicMock()

    client = _make_client(mock_edgar, mock_fs)
    result = client.has_active_enforcement("0000320193")

    mock_edgar.has_active_enforcement.assert_called_once_with("0000320193")
    mock_fs.get.assert_not_called()
    assert result is False


def test_missing_cached_at_triggers_refetch():
    mock_edgar = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = {
        "has_restatement": False,
        "has_going_concern": False,
        # no _cached_at — malformed cache entry
    }
    mock_edgar.has_restatement.return_value = True
    mock_edgar.has_going_concern.return_value = False

    client = _make_client(mock_edgar, mock_fs)
    result = client.has_restatement("0000320193")

    mock_edgar.has_restatement.assert_called_once()
    assert result is True
```

- [ ] **Step 2: Run tests to confirm they fail**

```
uv run python -m pytest tests/services/test_cached_edgar_client.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.cached_edgar_client'`

- [ ] **Step 3: Implement `CachedEdgarClient`**

Create `app/services/cached_edgar_client.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient
    from app.services.firestore_client import FirestoreClient

_TTL_SECONDS = 7 * 24 * 3600  # 7 days


class CachedEdgarClient:
    def __init__(
        self,
        edgar: EdgarClient,
        firestore: FirestoreClient,
        collection: str,
    ) -> None:
        self._edgar = edgar
        self._firestore = firestore
        self._collection = collection

    def _fetch_and_cache(self, cik: str) -> dict[str, Any]:
        cached = self._firestore.get(self._collection, cik)
        if cached and self._is_fresh(cached):
            return cached
        data: dict[str, Any] = {
            "has_restatement": self._edgar.has_restatement(cik),
            "has_going_concern": self._edgar.has_going_concern(cik),
            "_cached_at": datetime.now(timezone.utc).isoformat(),
        }
        self._firestore.set(self._collection, cik, data)
        return data

    def has_restatement(self, cik: str, years: int = 3) -> bool:
        return self._fetch_and_cache(cik)["has_restatement"]

    def has_going_concern(self, cik: str, months: int = 24) -> bool:
        return self._fetch_and_cache(cik)["has_going_concern"]

    def has_active_enforcement(self, cik: str) -> bool:
        return self._edgar.has_active_enforcement(cik)

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
uv run python -m pytest tests/services/test_cached_edgar_client.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run full suite**

```
uv run python -m pytest -v
```

Expected: all tests pass, coverage ≥ 90%.

- [ ] **Step 6: Commit**

```
git add app/services/cached_edgar_client.py tests/services/test_cached_edgar_client.py
git commit -m "Add CachedEdgarClient with 7-day TTL Firestore caching"
```

---

## Task 4: EDGAR filters

**Files:**
- Modify: `app/screener/filters.py`
- Modify: `tests/screener/test_filters.py`

Filter order: `restatement` → `going_concern` → `enforcement`. Records with `edgar_skipped=True` are passed through with `filter_passed_edgar=None` (unknown, not penalized). `has_active_enforcement` is always `False` in the current stub but the filter checks it for forward compatibility.

- [ ] **Step 1: Write failing tests**

Append to the bottom of `tests/screener/test_filters.py`:

```python
# --- apply_edgar_filters ---


def _edgar_record(**kwargs) -> ScreenerRecord:
    defaults = {
        "ticker": "TEST",
        "cik": "0000320193",
        "market_cap": 500_000_000,
        "avg_daily_volume": 200_000,
        "price": 50.0,
        "has_restatement": False,
        "has_going_concern": False,
        "has_active_enforcement": False,
        "edgar_skipped": False,
        "filter_passed_basis": True,
    }
    return ScreenerRecord(**{**defaults, **kwargs})


def test_apply_edgar_filters_passes_clean_record():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record()
    result = apply_edgar_filters([record])
    assert len(result) == 1
    assert result[0].filter_passed_edgar is True


def test_apply_edgar_filters_fails_on_restatement():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record(has_restatement=True)
    result = apply_edgar_filters([record])
    assert result == []
    assert record.filter_passed_edgar is False
    assert record.filter_failed_reason == "restatement"


def test_apply_edgar_filters_fails_on_going_concern():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record(has_going_concern=True)
    result = apply_edgar_filters([record])
    assert result == []
    assert record.filter_passed_edgar is False
    assert record.filter_failed_reason == "going_concern"


def test_apply_edgar_filters_fails_on_active_enforcement():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record(has_active_enforcement=True)
    result = apply_edgar_filters([record])
    assert result == []
    assert record.filter_passed_edgar is False
    assert record.filter_failed_reason == "enforcement"


def test_apply_edgar_filters_passes_through_skipped_records():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record(edgar_skipped=True)
    result = apply_edgar_filters([record])
    assert len(result) == 1
    assert result[0].filter_passed_edgar is None


def test_apply_edgar_filters_checks_restatement_before_going_concern():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record(has_restatement=True, has_going_concern=True)
    apply_edgar_filters([record])
    assert record.filter_failed_reason == "restatement"


def test_apply_edgar_filters_returns_empty_for_empty_input():
    from app.screener.filters import apply_edgar_filters
    assert apply_edgar_filters([]) == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```
uv run python -m pytest tests/screener/test_filters.py -v -k "edgar"
```

Expected: FAIL — `ImportError: cannot import name 'apply_edgar_filters'`

- [ ] **Step 3: Implement `apply_edgar_filters`**

Append to the bottom of `app/screener/filters.py`:

```python

def apply_edgar_filters(records: list[ScreenerRecord]) -> list[ScreenerRecord]:
    passed = []
    for record in records:
        if record.edgar_skipped:
            record.filter_passed_edgar = None
            passed.append(record)
            continue
        if record.has_restatement:
            record.filter_passed_edgar = False
            record.filter_failed_reason = "restatement"
            continue
        if record.has_going_concern:
            record.filter_passed_edgar = False
            record.filter_failed_reason = "going_concern"
            continue
        if record.has_active_enforcement:
            record.filter_passed_edgar = False
            record.filter_failed_reason = "enforcement"
            continue
        record.filter_passed_edgar = True
        passed.append(record)
    logger.info("edgar_filter: %d/%d records passed", len(passed), len(records))
    return passed
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run python -m pytest tests/screener/test_filters.py -v
```

Expected: all filter tests pass (existing basis tests + 7 new EDGAR tests).

- [ ] **Step 5: Run full suite**

```
uv run python -m pytest -v
```

Expected: all tests pass, coverage ≥ 90%.

- [ ] **Step 6: Commit**

```
git add app/screener/filters.py tests/screener/test_filters.py
git commit -m "Add apply_edgar_filters() with restatement/going-concern/enforcement checks"
```

---

## Task 5: EDGAR runner

**Files:**
- Modify: `app/screener/runner.py`
- Modify: `tests/screener/test_runner.py`

`run_edgar_filter` takes records already processed by `run_basis_filter` (they have `filter_passed_basis=True`). It populates the three EDGAR fields on each record, then calls `apply_edgar_filters`. Per-ticker `DataSourceError` marks the record as `edgar_skipped=True` (pass-through) instead of crashing the whole run. Records without a CIK are skipped immediately without calling the EDGAR client.

- [ ] **Step 1: Write failing tests**

Append to the bottom of `tests/screener/test_runner.py`:

```python
# --- run_edgar_filter ---


def _passing_basis_record(ticker="TEST", cik="0000320193") -> "ScreenerRecord":
    from app.models.screener_record import ScreenerRecord
    return ScreenerRecord(
        ticker=ticker,
        cik=cik,
        market_cap=500_000_000,
        avg_daily_volume=200_000,
        price=50.0,
        filter_passed_basis=True,
    )


def _clean_edgar_mock() -> MagicMock:
    mock = MagicMock()
    mock.has_restatement.return_value = False
    mock.has_going_concern.return_value = False
    mock.has_active_enforcement.return_value = False
    return mock


def test_run_edgar_filter_passes_clean_records():
    from app.screener.runner import run_edgar_filter
    record = _passing_basis_record()
    result = run_edgar_filter([record], _clean_edgar_mock())
    assert len(result) == 1
    assert result[0].filter_passed_edgar is True


def test_run_edgar_filter_skips_records_without_cik():
    from app.screener.runner import run_edgar_filter
    mock_edgar = MagicMock()
    record = _passing_basis_record(cik=None)
    record.cik = None

    result = run_edgar_filter([record], mock_edgar)

    mock_edgar.has_restatement.assert_not_called()
    assert len(result) == 1
    assert result[0].edgar_skipped is True
    assert result[0].filter_passed_edgar is None


def test_run_edgar_filter_skips_on_data_source_error():
    from app.screener.runner import run_edgar_filter
    mock_edgar = MagicMock()
    mock_edgar.has_restatement.side_effect = DataSourceError("network error")
    record = _passing_basis_record()

    result = run_edgar_filter([record], mock_edgar)

    assert len(result) == 1
    assert result[0].edgar_skipped is True
    assert result[0].filter_passed_edgar is None


def test_run_edgar_filter_excludes_restatement_records():
    from app.screener.runner import run_edgar_filter
    mock_edgar = _clean_edgar_mock()
    mock_edgar.has_restatement.return_value = True
    record = _passing_basis_record()

    result = run_edgar_filter([record], mock_edgar)

    assert result == []
    assert record.filter_passed_edgar is False
    assert record.filter_failed_reason == "restatement"


def test_run_edgar_filter_processes_multiple_records():
    from app.screener.runner import run_edgar_filter

    def restatement_side_effect(cik, **_):
        return cik == "0000111111"

    mock_edgar = _clean_edgar_mock()
    mock_edgar.has_restatement.side_effect = restatement_side_effect
    good = _passing_basis_record("GOOD", cik="0000320193")
    bad = _passing_basis_record("BAD", cik="0000111111")

    result = run_edgar_filter([good, bad], mock_edgar)

    assert len(result) == 1
    assert result[0].ticker == "GOOD"


def test_run_edgar_filter_continues_after_individual_error():
    from app.screener.runner import run_edgar_filter

    def restatement_side_effect(cik, **_):
        if cik == "0000111111":
            raise DataSourceError("timeout")
        return False

    mock_edgar = _clean_edgar_mock()
    mock_edgar.has_restatement.side_effect = restatement_side_effect
    error_record = _passing_basis_record("ERR", cik="0000111111")
    good_record = _passing_basis_record("GOOD", cik="0000320193")

    result = run_edgar_filter([error_record, good_record], mock_edgar)

    assert len(result) == 2  # error_record is edgar_skipped, still passes through
    tickers = {r.ticker for r in result}
    assert "GOOD" in tickers
    assert "ERR" in tickers
    assert error_record.edgar_skipped is True


def test_run_edgar_filter_returns_empty_for_empty_input():
    from app.screener.runner import run_edgar_filter
    assert run_edgar_filter([], MagicMock()) == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```
uv run python -m pytest tests/screener/test_runner.py -v -k "edgar"
```

Expected: FAIL — `ImportError: cannot import name 'run_edgar_filter'`

- [ ] **Step 3: Implement `run_edgar_filter`**

Replace the full content of `app/screener/runner.py`:

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.errors import DataSourceError
from app.models.screener_record import ScreenerRecord
from app.screener.filters import apply_basis_filters, apply_edgar_filters

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient
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
        except (DataSourceError, ValidationError) as exc:
            logger.warning("ticker=%s data fetch failed: %s", ticker, exc)
    logger.info("runner: fetched %d/%d records", len(records), len(tickers))
    return apply_basis_filters(records)


def run_edgar_filter(
    records: list[ScreenerRecord],
    edgar: EdgarClient,
) -> list[ScreenerRecord]:
    for record in records:
        if record.cik is None:
            logger.warning("ticker=%s has no CIK — skipping EDGAR check", record.ticker)
            record.edgar_skipped = True
            continue
        try:
            record.has_restatement = edgar.has_restatement(record.cik)
            record.has_going_concern = edgar.has_going_concern(record.cik)
            record.has_active_enforcement = edgar.has_active_enforcement(record.cik)
        except DataSourceError as exc:
            logger.warning("ticker=%s EDGAR fetch failed: %s — skipping", record.ticker, exc)
            record.edgar_skipped = True
    logger.info("runner: EDGAR lookup complete for %d records", len(records))
    return apply_edgar_filters(records)
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run python -m pytest tests/screener/test_runner.py -v
```

Expected: all runner tests pass (5 existing + 7 new EDGAR tests).

- [ ] **Step 5: Run full suite**

```
uv run python -m pytest -v
```

Expected: all tests pass, coverage ≥ 90%.

- [ ] **Step 6: Commit**

```
git add app/screener/runner.py tests/screener/test_runner.py
git commit -m "Add run_edgar_filter() with per-ticker error recovery and CIK-skip"
```

---

## Task 6: Composition root

**Files:**
- Modify: `app/screener/compose.py`
- Modify: `tests/screener/test_compose.py`

`build_edgar_pipeline()` is the only place that instantiates `EdgarClientImpl` and its `CachedEdgarClient` wrapper. It reads `edgar_user_agent`, `gcp_project_id`, and `edgar_collection` from settings. The Firestore client is a fresh instance separate from the one in `build_screener_pipeline()`.

- [ ] **Step 1: Write failing test**

Append to the bottom of `tests/screener/test_compose.py`:

```python
def test_build_edgar_pipeline_wires_components():
    from unittest.mock import patch
    with (
        patch("app.screener.compose.EdgarClientImpl") as mock_edgar_cls,
        patch("app.screener.compose.FirestoreClientImpl") as mock_fs_cls,
        patch("app.screener.compose.CachedEdgarClient") as mock_cached_cls,
        patch("app.screener.compose.settings") as mock_settings,
    ):
        mock_settings.edgar_user_agent = "Test Agent <test@example.com>"
        mock_settings.gcp_project_id = "test-project"
        mock_settings.edgar_collection = "dev_edgar_cache"

        result = compose_module.build_edgar_pipeline()

        mock_edgar_cls.assert_called_once_with(user_agent="Test Agent <test@example.com>")
        mock_fs_cls.assert_called_once_with(project_id="test-project")
        mock_cached_cls.assert_called_once_with(
            edgar=mock_edgar_cls.return_value,
            firestore=mock_fs_cls.return_value,
            collection="dev_edgar_cache",
        )
        assert result == mock_cached_cls.return_value
```

- [ ] **Step 2: Run test to confirm it fails**

```
uv run python -m pytest tests/screener/test_compose.py -v -k "edgar"
```

Expected: FAIL — `AttributeError: module 'app.screener.compose' has no attribute 'build_edgar_pipeline'`

- [ ] **Step 3: Implement `build_edgar_pipeline`**

Replace the full content of `app/screener/compose.py`:

```python
from app.config import settings
from app.services.cached_edgar_client import CachedEdgarClient
from app.services.cached_yfinance_client import CachedYFinanceClient
from app.services.edgar_client import EdgarClientImpl
from app.services.firestore_client import FirestoreClientImpl
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
```

- [ ] **Step 4: Run test to verify it passes**

```
uv run python -m pytest tests/screener/test_compose.py -v
```

Expected: both compose tests pass.

- [ ] **Step 5: Run full suite with coverage**

```
uv run python -m pytest -v
```

Expected: all tests pass. Note the final coverage number — should be ≥ 90%.

- [ ] **Step 6: Commit**

```
git add app/screener/compose.py tests/screener/test_compose.py
git commit -m "Add build_edgar_pipeline() composition root for EDGAR client wiring"
```

---

## Self-Review

### Spec coverage

| Spec requirement | Task |
|---|---|
| `edgar_client.py` (real): `has_restatement` via submissions.json 8-K Item 4.02 | Task 2 |
| `edgar_client.py` (real): `has_going_concern` via EFTS full-text "raise substantial doubt" | Task 2 |
| `edgar_client.py`: `has_active_enforcement` = stub + logger warning | Task 2 |
| Rate-limiting: `time.sleep(0.5)` between every EDGAR HTTP call | Task 2 |
| User-Agent header validated at init time | Task 2 |
| Caching: EDGAR signals per CIK in `dev_edgar_cache` with 7-day TTL | Task 3 |
| Both signals cached together in one Firestore document | Task 3 |
| EDGAR lookup only runs on basis-filtered set (~400 records), never on all 2100 | Task 5 |
| Records without CIK → `edgar_skipped=True`, passed through | Tasks 4 + 5 |
| Per-ticker `DataSourceError` → `edgar_skipped=True`, run continues | Task 5 |
| `apply_edgar_filters`: filter order restatement → going_concern → enforcement | Task 4 |
| `filter_passed_edgar = None` for skipped records (not penalized) | Tasks 4 + 5 |
| `edgar_collection` config field consumed by composition root | Tasks 1 + 6 |
| No real EDGAR HTTP calls in unit tests | All tasks — httpx mocked throughout |

All spec requirements covered. ✓

### Placeholder scan

No TBDs, no TODOs, no "similar to Task N" references. All steps include complete code. ✓

### Type consistency

- `EdgarClient` Protocol defined in Task 2: `has_restatement(cik: str, years: int = 3)`, `has_going_concern(cik: str, months: int = 24)`, `has_active_enforcement(cik: str)` — called identically in Tasks 3, 5, 6. ✓
- `CachedEdgarClient` returned by `build_edgar_pipeline()` satisfies `EdgarClient` Protocol structurally — used as `EdgarClient` in `run_edgar_filter()`. ✓
- `ScreenerRecord` fields `has_restatement`, `has_going_concern`, `has_active_enforcement`, `edgar_skipped`, `filter_passed_edgar`, `filter_failed_reason` — all present in Phase 1.1 model, names match exactly in Tasks 4 and 5. ✓
- `apply_edgar_filters` imported in `runner.py` from `app.screener.filters` — added in Task 4, imported in Task 5. ✓
