import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.deepdive.historical_cache import CachedHistoricalData


def _series():
    return {
        "financial_currency": "DKK",
        "years": [2024, 2023, 2022],
        "revenue": [1, 2, 3],
        "gross_margin": [0.8, 0.8, 0.8],
        "operating_margin": [0.4, 0.4, 0.4],
        "ebit": [0.4, 0.8, 1.2],
        "interest_expense": [0.05, 0.04, 0.03],
        "shares_outstanding": [9, 9, 9],
        "buyback_cashflow": [-1, -1, -1],
        "complete": True,
        "net_income": [1, 2, 3],
        "diluted_eps": [0.1, 0.2, 0.3],
        "free_cashflow": [1, 1, 1],
        "total_debt": [9, 9, 9],
        "cash": [5, 5, 5],
    }


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


def test_corrupt_cache_treated_as_miss(tmp_path):
    cd, svc = _cd(tmp_path)
    cd.get_annual_series("X")
    (tmp_path / "X.json").write_text("{ corrupt", encoding="utf-8")
    cd.get_annual_series("X")
    assert svc.get_annual_series.call_count == 2


def test_v2_cache_hit_skips_service(tmp_path):
    """Round-trip: first call writes a v2-tagged cache, second call hits.
    Asserts (a) service called exactly once and (b) the persisted payload
    declares a schema_version key — without the tag, a future code reload
    would treat it as v1 and refetch, defeating the cache."""
    cd, svc = _cd(tmp_path)
    cd.get_annual_series("X")
    cd.get_annual_series("X")

    assert svc.get_annual_series.call_count == 1
    persisted = json.loads((tmp_path / "X.json").read_text(encoding="utf-8"))
    assert "schema_version" in persisted


def test_write_includes_schema_version(tmp_path):
    """Direct write-path inspection: the persisted payload carries the current
    schema_version as an integer. Pre-implementation rot surfaces via KeyError."""
    cd, svc = _cd(tmp_path)
    cd.get_annual_series("X")
    persisted = json.loads((tmp_path / "X.json").read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 4


def test_pre_v2_cache_treated_as_miss(tmp_path):
    """Pre-v2 cache files (no schema_version, may miss ebit/interest_expense)
    must be treated as cache miss and lazy-refreshed with current schema."""
    from app.deepdive.historical_cache import CACHE_SCHEMA_VERSION

    cd, svc = _cd(tmp_path)
    pre_v2_payload = {
        "_cached_at": datetime.now(timezone.utc).isoformat(),
        "financial_currency": "DKK",
        "series": {
            "financial_currency": "DKK",
            "years": [2024, 2023, 2022],
            "revenue": [1, 2, 3],
            "gross_margin": [0.8, 0.8, 0.8],
            "operating_margin": [0.4, 0.4, 0.4],
            "shares_outstanding": [9, 9, 9],
            "buyback_cashflow": [-1, -1, -1],
            "complete": True,
        },
    }
    (tmp_path / "X.json").write_text(json.dumps(pre_v2_payload), encoding="utf-8")

    cd.get_annual_series("X")

    svc.get_annual_series.assert_called_once_with("X")
    refreshed = json.loads((tmp_path / "X.json").read_text(encoding="utf-8"))
    assert refreshed.get("schema_version") == CACHE_SCHEMA_VERSION


def test_schema_version_is_four():
    """v4 = minor-unit normalization (GBp -> GBP). The cached payload holds a
    *derived* ValuationHistory computed under the old currency semantics, so no
    per-field vintage tell exists — the version is the only lever."""
    from app.deepdive.historical_cache import CACHE_SCHEMA_VERSION

    assert CACHE_SCHEMA_VERSION == 4


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
    assert refreshed["schema_version"] == 4


def test_v3_cache_treated_as_miss_despite_being_fresh(tmp_path):
    """The minor-unit vintage gate for this cache: a v3 payload is a pre-
    normalization ValuationHistory (London multiples computed from pence prices, or
    honestly skipped_fx). It must be refetched even though its _cached_at is fresh —
    the 90-day TTL alone would keep serving the old numbers for months."""
    cd, svc = _cd(tmp_path)
    v3_payload = {
        "_cached_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 3,
        "financial_currency": "GBP",
        "series": _series(),
    }
    (tmp_path / "X.json").write_text(json.dumps(v3_payload), encoding="utf-8")

    cd.get_annual_series("X")

    svc.get_annual_series.assert_called_once_with("X")
    refreshed = json.loads((tmp_path / "X.json").read_text(encoding="utf-8"))
    assert refreshed["schema_version"] == 4


def test_newer_than_current_schema_version_also_treated_as_miss(tmp_path):
    """Mismatch semantics are `!=`, not `<`: a payload written by a newer code
    version is a miss too, so a rollback cannot silently read a future schema."""
    cd, svc = _cd(tmp_path)
    future_payload = {
        "_cached_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 99,
        "financial_currency": "DKK",
        "series": _series(),
    }
    (tmp_path / "X.json").write_text(json.dumps(future_payload), encoding="utf-8")

    cd.get_annual_series("X")

    svc.get_annual_series.assert_called_once_with("X")


def test_valuation_history_summary_roundtrips(tmp_path):
    # service returns a ValuationHistory object under series["valuation_history"];
    # cache write must serialize it, cache read must reconstruct it.
    from app.models.deep_dive_record import MultipleStats, ValuationHistory

    cd, svc = _cd(tmp_path)
    series = dict(_series())
    series["valuation_history"] = ValuationHistory(
        pe=MultipleStats(
            median=21.4, p25=12.1, n_obs=164, span_years=3.1, status="complete"
        )
    )
    svc.get_annual_series.return_value = series
    cd.get_annual_series("X")  # writes
    out = cd.get_annual_series("X")  # fresh hit -> reads back
    assert svc.get_annual_series.call_count == 1
    vh = out["valuation_history"]
    assert isinstance(vh, ValuationHistory)
    assert vh.pe.median == 21.4 and vh.pe.status == "complete"
