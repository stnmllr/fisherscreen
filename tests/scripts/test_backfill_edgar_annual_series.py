"""Tests for the annual-series backfill.

The two behaviours worth pinning: CIKs are deduplicated before anything is
fetched, and a single transient failure does not abandon the other six hundred.
"""

from scripts.backfill_edgar_annual_series import (
    backfill,
    is_us_ticker,
    resolve_ciks,
)


class _FakeEdgar:
    def __init__(self, mapping):
        self.mapping = mapping
        self.asked = []

    def get_cik(self, ticker):
        self.asked.append(ticker)
        return self.mapping.get(ticker)


class _Record:
    def __init__(self, usable):
        self.usable = usable


class _FakeCache:
    def __init__(self, usable=(), failing=()):
        self.usable = set(usable)
        self.failing = set(failing)
        self.seen = []

    def get_annual_series(self, cik):
        self.seen.append(cik)
        if cik in self.failing:
            raise RuntimeError("EDGAR returned 503")
        return _Record(cik in self.usable)


# --- resolution ------------------------------------------------------------


def test_two_tickers_of_one_issuer_become_one_cik():
    """GOOG and GOOGL share an issuer and a document. Without the dedupe the
    backfill fetches and writes the same series twice."""
    edgar = _FakeEdgar({"GOOG": "1652044", "GOOGL": "1652044", "FAST": "815556"})

    ciks, unresolved = resolve_ciks(["GOOG", "GOOGL", "FAST"], edgar)

    assert ciks == ["0001652044", "0000815556"]
    assert unresolved == []


def test_non_us_tickers_are_skipped_before_a_lookup_is_attempted():
    """A suffixed ticker is never in company_tickers.json; asking would spend a
    request to learn nothing."""
    edgar = _FakeEdgar({"FAST": "815556"})

    ciks, unresolved = resolve_ciks(["ADYEN.AS", "FAST", "EDV.L"], edgar)

    assert ciks == ["0000815556"]
    assert edgar.asked == ["FAST"]
    assert unresolved == []


def test_a_us_ticker_without_a_cik_is_reported_not_dropped():
    edgar = _FakeEdgar({"FAST": "815556"})

    ciks, unresolved = resolve_ciks(["FAST", "BLD"], edgar)

    assert ciks == ["0000815556"]
    assert unresolved == ["BLD"]


def test_cik_padding_matches_the_cache_key():
    edgar = _FakeEdgar({"AAPL": "320193"})
    ciks, _ = resolve_ciks(["AAPL"], edgar)
    assert ciks == ["0000320193"]


def test_us_ticker_detection():
    assert is_us_ticker("BRK-B")
    assert not is_us_ticker("ANTO.L")


# --- the run itself --------------------------------------------------------


def test_every_cik_is_pulled_once_and_counted_by_outcome():
    cache = _FakeCache(usable=["1", "2"])

    stats = backfill(["1", "2", "3"], cache, log_every=100)

    assert cache.seen == ["1", "2", "3"]
    assert stats.warmed == 2
    assert stats.negative == 1
    assert stats.failed == []


def test_one_transient_failure_does_not_abandon_the_rest():
    """At 600+ titles a network hiccup is normal. Aborting after 500 would cost
    more than a second invocation, so it is counted and named instead."""
    cache = _FakeCache(usable=["1", "3"], failing=["2"])

    stats = backfill(["1", "2", "3"], cache, log_every=100)

    assert cache.seen == ["1", "2", "3"]
    assert stats.warmed == 2
    assert len(stats.failed) == 1
    assert "503" in stats.failed[0]


def test_a_failed_title_is_left_uncached_so_a_rerun_retries_it():
    """The failure is a statement about the API. It must not become a stored
    verdict, and the resolved count must still show it was attempted."""
    cache = _FakeCache(failing=["2"])

    stats = backfill(["2"], cache, log_every=100)

    assert stats.resolved == 1
    assert stats.warmed == 0
    assert stats.negative == 0
    assert stats.failed
