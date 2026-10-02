from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.errors import DataSourceError


def _make_client(yfinance_mock, firestore_mock):
    from app.services.cached_yfinance_client import CachedYFinanceClient

    return CachedYFinanceClient(
        yfinance=yfinance_mock,
        firestore=firestore_mock,
        collection="dev_ticker_cache",
    )


def test_cache_miss_fetches_from_yfinance_and_stores():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = None  # cache miss
    mock_yf.get_ticker_info.return_value = {"shortName": "Apple", "marketCap": 3e12}

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("AAPL")

    mock_yf.get_ticker_info.assert_called_once_with("AAPL")
    mock_fs.set.assert_called_once()
    stored_data = mock_fs.set.call_args[0][2]
    assert "_cached_at" in stored_data
    assert result["shortName"] == "Apple"
    assert "_cached_at" not in result


def test_cache_hit_returns_cached_data_without_calling_yfinance():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    mock_fs.get.return_value = {
        "shortName": "Apple",
        "marketCap": 3e12,
        "_cached_at": fresh_ts,
    }

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("AAPL")

    mock_yf.get_ticker_info.assert_not_called()
    assert result["shortName"] == "Apple"
    assert "_cached_at" not in result


def test_expired_cache_refetches_from_yfinance():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    mock_fs.get.return_value = {
        "shortName": "Apple (stale)",
        "_cached_at": stale_ts,
    }
    mock_yf.get_ticker_info.return_value = {
        "shortName": "Apple (fresh)",
        "marketCap": 3e12,
    }

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("AAPL")

    mock_yf.get_ticker_info.assert_called_once_with("AAPL")
    assert result["shortName"] == "Apple (fresh)"


def test_get_historical_delegates_to_yfinance_without_cache():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_yf.get_historical.return_value = "some_dataframe"

    client = _make_client(mock_yf, mock_fs)
    result = client.get_historical("AAPL", "1mo")

    mock_yf.get_historical.assert_called_once_with("AAPL", "1mo")
    mock_fs.get.assert_not_called()
    assert result == "some_dataframe"


def test_get_financials_delegates_to_yfinance_without_cache():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_yf.get_financials.return_value = {"Revenue": 394e9}

    client = _make_client(mock_yf, mock_fs)
    result = client.get_financials("AAPL")

    mock_yf.get_financials.assert_called_once_with("AAPL")
    mock_fs.get.assert_not_called()
    assert result == {"Revenue": 394e9}


def test_yfinance_error_propagates_on_cache_miss():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = None
    mock_yf.get_ticker_info.side_effect = DataSourceError(
        "yfinance failed for AAPL: network error"
    )

    client = _make_client(mock_yf, mock_fs)

    with pytest.raises(DataSourceError, match="yfinance failed"):
        client.get_ticker_info("AAPL")

    mock_fs.set.assert_not_called()


def test_get_forward_estimates_delegates_to_yfinance_without_cache():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    sentinel = object()
    mock_yf.get_forward_estimates.return_value = sentinel

    client = _make_client(mock_yf, mock_fs)
    result = client.get_forward_estimates("AAPL")

    mock_yf.get_forward_estimates.assert_called_once_with("AAPL")
    mock_fs.get.assert_not_called()
    assert result is sentinel


def test_get_fx_rate_delegates_to_yfinance_without_cache():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_yf.get_fx_rate.return_value = 0.92

    client = _make_client(mock_yf, mock_fs)
    result = client.get_fx_rate("USD")

    mock_yf.get_fx_rate.assert_called_once_with("USD")
    mock_fs.get.assert_not_called()
    assert result == 0.92


def test_missing_cached_at_field_triggers_refetch():
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = {"shortName": "Apple"}  # no _cached_at
    mock_yf.get_ticker_info.return_value = {
        "shortName": "Apple Fresh",
        "marketCap": 3e12,
    }

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("AAPL")

    mock_yf.get_ticker_info.assert_called_once_with("AAPL")
    assert result["shortName"] == "Apple Fresh"


# --------------------------------------------------------------------------
# Minor-unit cache vintage — bypass path 1 of 3 (24 h TTL)
# --------------------------------------------------------------------------


def test_fresh_but_unnormalised_document_is_a_miss_and_refetches():
    """A document written before minor-unit normalization carries the minor-unit
    currency code; freshness alone is not enough to serve it.

    CachedYFinanceClient persists the raw dict verbatim with no schema marker, so
    the stored currency IS the vintage tell. Without this check a London title would
    keep serving pence prices under a "GBp" label for up to 24 h after the deploy —
    and again after every Tool A run that refills the cache from an old vintage."""
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    mock_fs.get.return_value = {
        "shortName": "GSK plc",
        "currency": "GBp",
        "currentPrice": 1500.0,
        "marketCap": 60_000_000_000,
        "_cached_at": fresh_ts,
    }
    mock_yf.get_ticker_info.return_value = {
        "shortName": "GSK plc",
        "currency": "GBP",
        "currentPrice": 15.0,
        "marketCap": 60_000_000_000,
    }

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("GSK.L")

    mock_yf.get_ticker_info.assert_called_once_with("GSK.L")
    assert result["currency"] == "GBP"
    assert result["currentPrice"] == 15.0
    mock_fs.set.assert_called_once()  # the normalized payload replaces the old one
    assert mock_fs.set.call_args[0][2]["currency"] == "GBP"


def test_fresh_normalised_document_is_served_without_touching_the_client():
    """The companion contract: normalization must not turn every cache hit into a
    fetch. A post-change London payload (ISO code) is served from cache as before."""
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    mock_fs.get.return_value = {
        "shortName": "GSK plc",
        "currency": "GBP",
        "currentPrice": 15.0,
        "marketCap": 60_000_000_000,
        "_cached_at": fresh_ts,
    }

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("GSK.L")

    mock_yf.get_ticker_info.assert_not_called()
    mock_fs.set.assert_not_called()
    assert result["currentPrice"] == 15.0
    assert "_cached_at" not in result


# --------------------------------------------------------------------------
# Missing market cap — a fresh document must not pin a transient Yahoo gap
# --------------------------------------------------------------------------


def _fresh_ts():
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def test_fresh_document_without_usable_market_cap_is_a_miss_and_refetches():
    """September 2026: 29 of 32 NO_RAW_MC titles resolved fine a month later — the
    gap was transient. A 24 h cache that keeps serving the gap would turn every
    retry into the same bad answer."""
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = {
        "shortName": "Gap Corp",
        "currency": "EUR",
        "marketCap": 0,
        "currentPrice": 10.0,
        "_cached_at": _fresh_ts(),
    }
    mock_yf.get_ticker_info.return_value = {
        "shortName": "Gap Corp",
        "currency": "EUR",
        "marketCap": 5e9,
        "currentPrice": 10.0,
    }

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("GAP.PA")

    mock_yf.get_ticker_info.assert_called_once_with("GAP.PA")
    assert result["marketCap"] == 5e9
    mock_fs.set.assert_called_once()
    assert mock_fs.set.call_args[0][2]["marketCap"] == 5e9


def test_fresh_document_with_derivable_market_cap_is_served_from_cache():
    """shares x price is a usable cap — such a document is a hit, not a refetch."""
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = {
        "shortName": "Michelin",
        "currency": "EUR",
        "marketCap": 0,
        "sharesOutstanding": 713_302_016,
        "currentPrice": 33.02,
        "_cached_at": _fresh_ts(),
    }

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("ML.PA")

    mock_yf.get_ticker_info.assert_not_called()
    mock_fs.set.assert_not_called()
    assert result["sharesOutstanding"] == 713_302_016


def test_refetched_payload_still_without_market_cap_is_returned_and_stored():
    """The refetch is the self-heal, not a gate: if Yahoo still has no cap the
    payload is returned (the runner diverts it) and stored as usual."""
    mock_yf = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = {"shortName": "Gap", "_cached_at": _fresh_ts()}
    mock_yf.get_ticker_info.return_value = {"shortName": "Gap", "marketCap": None}

    client = _make_client(mock_yf, mock_fs)
    result = client.get_ticker_info("GAP.PA")

    mock_yf.get_ticker_info.assert_called_once_with("GAP.PA")
    assert result == {"shortName": "Gap", "marketCap": None}
    mock_fs.set.assert_called_once()
