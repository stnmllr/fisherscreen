"""Tests for the Firestore cache of the EDGAR annual series.

Two of these guard failure modes a cache is especially good at hiding: an
extract written by an older extraction that still looks valid, and a jitter
re-rolled on every read so the same entry is alternately fresh and stale.
"""

from datetime import datetime, timedelta, timezone
from random import Random

import pytest

from app.errors import DataSourceError
from app.services.cached_edgar_annual_series import CachedEdgarAnnualSeries
from app.services.edgar_annual_series_client import (
    EXTRACTION_SCHEMA,
    NO_CONCEPT,
    AnnualSeriesRecord,
    ConceptCoverage,
    record_to_dict,
)

_NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def _coverage(years=(2023, 2024, 2025)):
    return ConceptCoverage(
        concept="Revenues",
        unit="USD",
        years=tuple(years),
        values=tuple(float(y) for y in years),
        contiguous=len(years),
        restatements=0,
        naive_fy_count=1,
    )


def _record(cik="0000320193", reason=None):
    return AnnualSeriesRecord(
        cik=cik,
        entity="Apple Inc.",
        concepts={
            "revenue": _coverage(),
            "operating_income": _coverage(),
            "net_income": _coverage(),
        },
        reason=reason,
    )


class _FakeStore:
    def __init__(self, seed=None):
        self.docs = dict(seed or {})
        self.writes = []

    def get(self, collection, document_id):
        return self.docs.get((collection, document_id))

    def set(self, collection, document_id, data):
        self.docs[(collection, document_id)] = data
        self.writes.append((document_id, data))

    def delete(self, collection, document_id):  # pragma: no cover - unused
        self.docs.pop((collection, document_id), None)


class _FakeClient:
    def __init__(self, record=None, error=None):
        self.record = record
        self.error = error
        self.calls = []

    def get_annual_series(self, cik):
        self.calls.append(cik)
        if self.error:
            raise self.error
        return self.record or _record(cik)


def _cache(client, store, **kw):
    kw.setdefault("rng", Random(0))
    kw.setdefault("now", lambda: _NOW)
    return CachedEdgarAnnualSeries(client, store, "series", **kw)


# --- basic behaviour -------------------------------------------------------


def test_a_miss_fetches_and_writes_through():
    client, store = _FakeClient(), _FakeStore()
    record = _cache(client, store).get_annual_series("320193")

    assert client.calls == ["0000320193"]
    assert record.concepts["revenue"].years == (2023, 2024, 2025)
    assert store.writes[0][0] == "0000320193"


def test_the_cik_is_padded_so_one_issuer_is_one_document():
    """GOOG and GOOGL share an issuer. Keyed loosely, the same series would be
    fetched and stored twice."""
    client, store = _FakeClient(), _FakeStore()
    cache = _cache(client, store)
    cache.get_annual_series("320193")
    cache.get_annual_series("0000320193")

    assert client.calls == ["0000320193"]  # second call served from cache
    assert len(store.docs) == 1


def test_a_fresh_hit_does_not_call_the_client():
    payload = record_to_dict(_record())
    payload["_expires_at"] = (_NOW + timedelta(days=100)).isoformat()
    store = _FakeStore({("series", "0000320193"): payload})
    client = _FakeClient()

    record = _cache(client, store).get_annual_series("0000320193")

    assert client.calls == []
    assert record.entity == "Apple Inc."
    assert record.concepts["revenue"].years == (2023, 2024, 2025)


def test_an_expired_entry_is_refetched():
    payload = record_to_dict(_record())
    payload["_expires_at"] = (_NOW - timedelta(days=1)).isoformat()
    store = _FakeStore({("series", "0000320193"): payload})
    client = _FakeClient()

    _cache(client, store).get_annual_series("0000320193")

    assert client.calls == ["0000320193"]


# --- the two failure modes a cache hides -----------------------------------


def test_an_extract_from_an_older_extraction_is_a_miss():
    """The dangerous case: it is inside its TTL and looks perfectly valid, but
    it was produced by different logic. Serving it would let a warm cache mask
    a behaviour change — which has already cost this project one verification."""
    payload = record_to_dict(_record())
    payload["schema"] = EXTRACTION_SCHEMA - 1
    payload["_expires_at"] = (_NOW + timedelta(days=300)).isoformat()
    store = _FakeStore({("series", "0000320193"): payload})
    client = _FakeClient()

    _cache(client, store).get_annual_series("0000320193")

    assert client.calls == ["0000320193"]


def test_the_expiry_is_written_once_and_not_re_rolled_on_read():
    """Jitter belongs to the write. Re-rolled per read, the same entry would be
    alternately fresh and stale."""
    client, store = _FakeClient(), _FakeStore()
    cache = _cache(client, store)
    cache.get_annual_series("320193")
    written = store.docs[("series", "0000320193")]["_expires_at"]

    for _ in range(5):
        cache.get_annual_series("320193")

    assert store.docs[("series", "0000320193")]["_expires_at"] == written
    assert client.calls == ["0000320193"]


def test_the_jitter_spreads_expiries_across_a_quarter():
    """A backfill writes on one day; without jitter every entry expires on one
    day and a single monthly run carries the whole refetch."""
    expiries = set()
    for n in range(40):
        client, store = _FakeClient(record=_record(cik=str(n))), _FakeStore()
        _cache(client, store, rng=Random(n)).get_annual_series(str(n))
        expiries.add(store.writes[0][1]["_expires_at"])

    days = sorted((datetime.fromisoformat(e) - _NOW).days for e in expiries)
    assert len(expiries) > 30  # not all on one day
    assert 400 - 60 <= days[0] and days[-1] <= 400 + 60


# --- negative results ------------------------------------------------------


def test_a_missing_concept_is_cached_with_the_short_ttl():
    """Around 90 titles would otherwise pull a multi-MB document every month to
    rediscover that nothing usable is in it."""
    client, store = _FakeClient(record=_record(reason=NO_CONCEPT)), _FakeStore()
    _cache(client, store).get_annual_series("320193")

    expires = datetime.fromisoformat(store.writes[0][1]["_expires_at"])
    assert (expires - _NOW).days == 60


def test_a_404_becomes_a_cached_negative_not_an_exception():
    """No XBRL facts at all is a statement about the issuer, so it is held —
    unlike a transient failure."""
    client = _FakeClient(error=DataSourceError("EDGAR returned 404 for ..."))
    store = _FakeStore()

    record = _cache(client, store).get_annual_series("320193")

    assert record.reason == NO_CONCEPT
    assert not record.usable
    assert store.writes, "the negative verdict was not persisted"


def test_a_transient_failure_is_neither_cached_nor_swallowed():
    """A 503 says something about the API, never about the title. Caching it
    would freeze a network hiccup into a 60-day verdict."""
    client = _FakeClient(error=DataSourceError("EDGAR returned 503 for ..."))
    store = _FakeStore()

    with pytest.raises(DataSourceError, match="503"):
        _cache(client, store).get_annual_series("320193")

    assert store.writes == []


# --- round trip ------------------------------------------------------------


def test_values_survive_firestore_turning_tuples_into_lists():
    """Firestore has no tuples and returns arrays as lists. Reading back a
    document written by a real store must still yield the same record."""
    payload = record_to_dict(_record())
    payload["_expires_at"] = (_NOW + timedelta(days=100)).isoformat()
    # what a real Firestore read looks like: every sequence a plain list
    payload["concepts"]["revenue"]["years"] = [2023, 2024, 2025]
    payload["concepts"]["revenue"]["values"] = [2023.0, 2024.0, 2025.0]
    store = _FakeStore({("series", "0000320193"): payload})

    record = _cache(_FakeClient(), store).get_annual_series("0000320193")

    assert record.concepts["revenue"].years == (2023, 2024, 2025)
    assert record.concepts["revenue"].values == (2023.0, 2024.0, 2025.0)


# --- the monthly run reads, it never fetches -------------------------------


def _lookup(store, client=None, **kw):
    return _cache(client or _FakeClient(), store, **kw).read_annual_series("320193")


def _stored(expires_in_days, schema=None):
    payload = record_to_dict(_record())
    payload["_expires_at"] = (_NOW + timedelta(days=expires_in_days)).isoformat()
    if schema is not None:
        payload["schema"] = schema
    return _FakeStore({("series", "0000320193"): payload})


def test_a_fresh_entry_reads_as_fresh():
    result = _lookup(_stored(100))
    assert result.status == "fresh"
    assert result.record.entity == "Apple Inc."


def test_an_expired_entry_is_used_and_flagged_stale_not_refetched():
    """A ten-year steadiness does not change because the newest year is
    missing. Refetching inside the monthly run would cost ~1.06 s per title and
    make the 1800s deadline a matter of luck."""
    client = _FakeClient()
    store = _stored(-30)

    result = _cache(client, store).read_annual_series("320193")

    assert result.status == "stale"
    assert result.record is not None
    assert client.calls == []  # the decisive assertion: no SEC request


def test_the_read_path_never_touches_the_client_even_on_a_miss():
    client = _FakeClient()
    store = _FakeStore()

    result = _cache(client, store).read_annual_series("320193")

    assert result.status == "missing"
    assert result.record is None
    assert client.calls == []
    assert store.writes == []


def test_an_older_extraction_reads_as_missing_not_stale():
    """Old-but-right may be reused; old-and-produced-by-other-rules may not.
    Serving it would score ten years of wrong series."""
    result = _lookup(_stored(300, schema=EXTRACTION_SCHEMA - 1))

    assert result.status == "missing"
    assert result.record is None


def test_the_backfill_path_still_refetches_what_the_read_path_tolerates():
    """The two paths differ on purpose: only the backfill goes to the network."""
    client = _FakeClient()
    store = _stored(-30)

    _cache(client, store).get_annual_series("320193")

    assert client.calls == ["0000320193"]
