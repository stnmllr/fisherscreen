from datetime import datetime, timezone, timedelta
from app.services.revenue_series_cache import CachedRevenueSeries


class _FakeFirestore:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.sets = {}

    def get(self, collection, doc_id):
        return self.docs.get(doc_id)

    def set(self, collection, doc_id, data):
        self.sets[doc_id] = data
        self.docs[doc_id] = data

    def delete(self, collection, doc_id):
        self.docs.pop(doc_id, None)


class _FakeYF:
    def __init__(self, series):
        self._series = series
        self.calls = 0

    def get_annual_statements(self, ticker):
        self.calls += 1
        return [self._series]  # a stand-in DataFrame consumed by extract_revenue_series


import pandas as pd


def _frame(values_newest_first):
    return pd.DataFrame(
        {c: [v] for c, v in enumerate(values_newest_first)},
        index=["Total Revenue"],
    )


def test_fresh_cache_hit_skips_fetch():
    fs = _FakeFirestore(
        {
            "AAA": {
                "revenues": [100.0, 130.0, 140.0, 150.0],
                "_cached_at": datetime.now(timezone.utc).isoformat(),
            }
        }
    )
    yf = _FakeYF(_frame([150, 140, 130, 100]))
    cache = CachedRevenueSeries(yf, fs, "dev_revenue_series", ttl_days=400)
    assert cache.get_revenue_series("AAA") == [100.0, 130.0, 140.0, 150.0]
    assert yf.calls == 0


def test_stale_cache_refetches_and_persists():
    old = (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()
    fs = _FakeFirestore({"AAA": {"revenues": [1.0], "_cached_at": old}})
    yf = _FakeYF(_frame([150, 140, 130, 100]))
    cache = CachedRevenueSeries(yf, fs, "dev_revenue_series", ttl_days=400)
    out = cache.get_revenue_series("AAA")
    assert out == [100.0, 130.0, 140.0, 150.0]
    assert yf.calls == 1
    assert "AAA" in fs.sets


def test_empty_fetch_not_persisted():
    fs = _FakeFirestore({})
    yf = _FakeYF(pd.DataFrame())  # extract_revenue_series -> []
    cache = CachedRevenueSeries(yf, fs, "dev_revenue_series", ttl_days=400)
    assert cache.get_revenue_series("AAA") == []
    assert "AAA" not in fs.sets  # not cached -> retried next run
