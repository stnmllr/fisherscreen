# Gemini Score Cache TTL — Fresh Numbers Every Monthly Run — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every monthly Tool-A run re-score with current numbers by shrinking the Gemini score cache TTL below the monthly cadence (configurable, default 2 days).

**Architecture:** The Gemini score cache (`dev_gemini_scores`) currently has a hardcoded 30-day TTL, which exceeds the ~28–31-day monthly interval, so a monthly run reuses the previous month's scores instead of re-scoring. We make the TTL a constructor parameter on `CachedGeminiClient`, fed from a new config field, and default it to 2 days. yfinance (24 h) and EDGAR (7 d) TTLs already expire before each monthly run and are left untouched.

**Tech Stack:** Python 3.12, pydantic-settings, pytest. Run tests with `uv run python -m pytest` (never bare `pytest`/`python`).

---

### Task 1: Add configurable TTL field to settings

**Files:**
- Modify: `app/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_gemini_score_cache_ttl_days_default_is_2():
    from app.config import FisherScreenSettings

    settings = FisherScreenSettings()
    assert settings.gemini_score_cache_ttl_days == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_config.py::test_gemini_score_cache_ttl_days_default_is_2 -v`
Expected: FAIL — `AttributeError: 'FisherScreenSettings' object has no attribute 'gemini_score_cache_ttl_days'`

- [ ] **Step 3: Add the field**

In `app/config.py`, add the field next to the existing Tool-B cache TTL fields (after line `historical_cache_ttl_days: int = 90`):

```python
    gemini_score_cache_ttl_days: int = 2  # < monthly cadence so each monthly run re-scores fresh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_config.py::test_gemini_score_cache_ttl_days_default_is_2 -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "Add configurable gemini_score_cache_ttl_days setting (default 2d)"
```

---

### Task 2: Make CachedGeminiClient TTL configurable via constructor

**Files:**
- Modify: `app/services/cached_gemini_client.py`
- Test: `tests/services/test_cached_gemini_client.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/services/test_cached_gemini_client.py` (it already imports `datetime, timedelta, timezone`, `MagicMock`, `CachedGeminiClient`):

```python
def _cached_age_days(days: float) -> dict:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return {
        "dimensions": {"growth": 3, "profitability": 3, "management": 3, "innovation": 3, "resilience": 3},
        "evidence": {"growth": "cached evidence"},
        "weakest_dimension": "resilience",
        "data_gaps": [],
        "_cached_at": dt.isoformat(),
    }


def test_entry_older_than_default_ttl_is_stale_and_rescored():
    """A 5-day-old entry is stale under the 2-day default (was fresh under old 30d)."""
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _result(growth=4)
    mock_fs = MagicMock()
    mock_fs.get.return_value = _cached_age_days(5)

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    result = client.score_ticker("AAPL", _record())

    mock_gemini.score_ticker.assert_called_once()
    assert result.dimensions["growth"] == 4


def test_ttl_days_constructor_param_is_honored():
    """With ttl_days=10, a 5-day-old entry is fresh → served from cache, no Gemini call."""
    mock_gemini = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = _cached_age_days(5)

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col", ttl_days=10)
    result = client.score_ticker("AAPL", _record())

    mock_gemini.score_ticker.assert_not_called()
    assert result.dimensions["growth"] == 3
    assert result.tokens_in == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/services/test_cached_gemini_client.py::test_entry_older_than_default_ttl_is_stale_and_rescored tests/services/test_cached_gemini_client.py::test_ttl_days_constructor_param_is_honored -v`
Expected: FAIL — first test fails because the 5-day entry is still "fresh" under the hardcoded 30-day TTL (Gemini not called); second fails with `TypeError: __init__() got an unexpected keyword argument 'ttl_days'`.

- [ ] **Step 3: Make the TTL configurable**

In `app/services/cached_gemini_client.py`:

1. Delete the module constant `_TTL_SECONDS = 30 * 24 * 3600  # 30 days` (line 13).
2. Replace the class docstring's "within 30-day TTL" wording and the constructor + `_is_fresh` so the TTL comes from a constructor parameter. The class becomes:

```python
class CachedGeminiClient:
    """Firestore-backed cache wrapper for GeminiClient.

    A fresh cache entry (within the configurable TTL, default 2 days) is returned
    with tokens_in=0 and tokens_out=0 to signal that no Gemini API call was made,
    keeping cost accounting accurate at the call site. The TTL is kept below the
    monthly run cadence so each monthly run re-scores with current numbers.
    """

    def __init__(
        self,
        gemini: GeminiClient,
        firestore: FirestoreClient,
        collection: str,
        ttl_days: int = 2,
    ) -> None:
        self._gemini = gemini
        self._firestore = firestore
        self._collection = collection
        self._ttl_seconds = ttl_days * 24 * 3600
```

3. In `_is_fresh`, change the final comparison from `_TTL_SECONDS` to `self._ttl_seconds`:

```python
        return (datetime.now(timezone.utc) - cached_at).total_seconds() < self._ttl_seconds
```

- [ ] **Step 4: Run the new + existing tests to verify they pass**

Run: `uv run python -m pytest tests/services/test_cached_gemini_client.py -v`
Expected: PASS for all (the two new tests plus the 9 existing ones — `_fresh_cached()` (now) is still fresh under 2d, `_stale_cached()` (31d) is still stale).

- [ ] **Step 5: Commit**

```bash
git add app/services/cached_gemini_client.py tests/services/test_cached_gemini_client.py
git commit -m "Make CachedGeminiClient TTL configurable via constructor (default 2d)"
```

---

### Task 3: Wire the configured TTL through the compose layer

**Files:**
- Modify: `app/screener/compose.py:38-45`

- [ ] **Step 1: Pass the config value into the client**

In `app/screener/compose.py`, update `build_gemini_pipeline` to pass the new setting:

```python
def build_gemini_pipeline() -> GeminiClient:
    gemini = GeminiClientImpl(api_key=settings.gemini_api_key, model=settings.gemini_model)
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    return CachedGeminiClient(
        gemini=gemini,
        firestore=firestore,
        collection=settings.gemini_score_collection,
        ttl_days=settings.gemini_score_cache_ttl_days,
    )
```

- [ ] **Step 2: Verify compose still imports/constructs cleanly**

Run: `uv run python -m pytest -q -k "compose or gemini"`
Expected: PASS (no constructor mismatch).

- [ ] **Step 3: Commit**

```bash
git add app/screener/compose.py
git commit -m "Wire gemini_score_cache_ttl_days through build_gemini_pipeline"
```

---

### Task 4: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire suite**

Run: `uv run python -m pytest -q`
Expected: PASS, coverage threshold (90%) reached. (~1007 passed.)

- [ ] **Step 2: If green, the branch is ready for PR to main.**

No further code changes. Open PR `feature/gemini-score-cache-fresh-monthly` → `main` after explicit go.

---

## Notes / out of scope

- yfinance (`cached_yfinance_client`, 24 h) and EDGAR (`cached_edgar_client`, 7 d) TTLs are left unchanged — both already expire before each monthly run, so those numbers are already fresh. Touching them adds cost/risk for no benefit (YAGNI).
- **Operational consequence (separate from this branch):** with a 2-day Gemini TTL, every scheduled monthly run is now a cold-scoring run (~20–23 min). Pair this with the Cloud Scheduler `--max-retry-attempts=0` change and a Cloud Run request timeout of 3600 s so a long run pushes exactly once and is never retried into a double-run. Tracked as an infra task, not part of this code change.
- A test/dress-rehearsal run within the TTL window before the 1st (i.e. on 30 Jun with a 2-day TTL) would still be reused on 01 Jul. That is the accepted trade-off of option (i); full per-run freshness regardless of timing was option (ii) and was not chosen.
