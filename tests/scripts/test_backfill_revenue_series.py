"""Unit tests for the backfill_revenue_series script."""
from scripts.backfill_revenue_series import backfill


class _Cache:
    """Mock cache for testing."""

    def __init__(self):
        self.seen = []

    def get_revenue_series(self, ticker):
        self.seen.append(ticker)
        return [1.0, 2.0, 3.0, 4.0]


def test_backfill_iterates_all_tickers():
    """Test that backfill iterates through all tickers and calls get_revenue_series."""
    cache = _Cache()
    n = backfill(["AAA", "BBB", "CCC"], cache)
    assert n == 3
    assert cache.seen == ["AAA", "BBB", "CCC"]
