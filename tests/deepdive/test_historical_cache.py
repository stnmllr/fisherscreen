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
