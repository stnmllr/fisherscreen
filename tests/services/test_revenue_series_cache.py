from datetime import datetime, timezone, timedelta

import pytest

from app.services.revenue_series_cache import (
    CachedRevenueSeries,
    ttl_jitter_offset_days,
)


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


# --- TTL 120 d +/- 30 d, jitter derived from the ticker ----------------------

_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _cache_at(fs, ttl_days=120, jitter_days=30):
    return CachedRevenueSeries(
        _FakeYF(_frame([150, 140, 130, 100])),
        fs,
        "dev_revenue_series",
        ttl_days=ttl_days,
        ttl_jitter_days=jitter_days,
        now=lambda: _NOW,
    )


def _doc(age_days: float) -> dict:
    return {
        "revenues": [1.0, 2.0, 3.0, 4.0],
        "_cached_at": (_NOW - timedelta(days=age_days)).isoformat(),
    }


def test_default_ttl_is_120_days_with_30_days_jitter():
    cache = CachedRevenueSeries(_FakeYF(_frame([1])), _FakeFirestore(), "c")
    assert cache._ttl_days == 120
    assert cache._jitter_days == 30


def test_jitter_offset_is_bounded():
    offsets = [ttl_jitter_offset_days(f"T{i}", 30) for i in range(2000)]
    assert all(-30 <= o <= 30 for o in offsets)


def test_jitter_offset_spreads_across_the_window():
    # ~1,000 entries were written on one day; the offsets must spread them out
    offsets = [ttl_jitter_offset_days(f"T{i}", 30) for i in range(2000)]
    assert min(offsets) < -25 and max(offsets) > 25
    assert sum(1 for o in offsets if o < 0) == pytest.approx(1000, abs=150)


def test_jitter_offset_is_deterministic_per_ticker():
    # a hash, not hash(): str hashing is salted per process
    assert ttl_jitter_offset_days("AAPL", 30) == ttl_jitter_offset_days("AAPL", 30)
    assert ttl_jitter_offset_days("AAPL", 30) != ttl_jitter_offset_days("MSFT", 30)


def test_zero_jitter_is_a_flat_ttl():
    assert ttl_jitter_offset_days("AAPL", 0) == 0.0


def test_freshness_follows_the_tickers_jittered_ttl():
    offset = ttl_jitter_offset_days("AAA", 30)
    fs = _FakeFirestore({"AAA": _doc(120 + offset - 0.5)})
    cache = _cache_at(fs)
    assert cache.get_revenue_series("AAA") == [1.0, 2.0, 3.0, 4.0]
    assert cache._yfinance.calls == 0

    fs = _FakeFirestore({"AAA": _doc(120 + offset + 0.5)})
    cache = _cache_at(fs)
    assert cache.get_revenue_series("AAA") == [100.0, 130.0, 140.0, 150.0]
    assert cache._yfinance.calls == 1


def test_freshness_is_stable_across_reads():
    # no randomness at read time: the same entry never flips between reads
    offset = ttl_jitter_offset_days("AAA", 30)
    cache = _cache_at(_FakeFirestore({"AAA": _doc(120 + offset - 0.5)}))
    for _ in range(20):
        cache.get_revenue_series("AAA")
    assert cache._yfinance.calls == 0


def test_same_day_entries_expire_on_different_days():
    # the 2026-06-22 backfill: one write day must not mean one expiry day
    tickers = [f"T{i}" for i in range(200)]
    fs = _FakeFirestore({t: _doc(120) for t in tickers})
    cache = _cache_at(fs)
    for t in tickers:
        cache.get_revenue_series(t)
    assert 0 < cache._yfinance.calls < len(tickers)


def test_jitter_must_stay_below_the_ttl():
    with pytest.raises(ValueError):
        _cache_at(_FakeFirestore(), ttl_days=30, jitter_days=30)


def test_missing_or_invalid_cached_at_is_stale():
    for doc in (
        {"revenues": [1.0, 2.0, 3.0, 4.0]},
        {"revenues": [1.0, 2.0, 3.0, 4.0], "_cached_at": "not-a-date"},
    ):
        cache = _cache_at(_FakeFirestore({"AAA": doc}))
        cache.get_revenue_series("AAA")
        assert cache._yfinance.calls == 1


def test_naive_cached_at_is_read_as_utc():
    offset = ttl_jitter_offset_days("AAA", 30)
    naive = (_NOW - timedelta(days=120 + offset - 0.5)).replace(tzinfo=None)
    doc = {"revenues": [1.0, 2.0, 3.0, 4.0], "_cached_at": naive.isoformat()}
    cache = _cache_at(_FakeFirestore({"AAA": doc}))
    cache.get_revenue_series("AAA")
    assert cache._yfinance.calls == 0
