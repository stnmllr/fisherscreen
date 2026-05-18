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


def test_corrupt_meta_treated_as_cache_miss(tmp_path):
    fetcher, edgar = _fetcher(tmp_path)
    fetcher.get("0000353278", "20-F")
    (tmp_path / "0000353278" / "_meta.json").write_text("{ corrupt", encoding="utf-8")
    fetcher.get("0000353278", "20-F")
    assert edgar.get_latest_annual_filing.call_count == 2
