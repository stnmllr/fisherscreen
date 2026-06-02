from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock


def _make_client(edgar_mock, firestore_mock):
    from app.services.cached_edgar_client import CachedEdgarClient
    return CachedEdgarClient(
        edgar=edgar_mock,
        firestore=firestore_mock,
        collection="dev_edgar_cache",
    )


def test_cache_miss_fetches_both_signals_and_stores():
    mock_edgar = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = None
    mock_edgar.has_restatement.return_value = False
    mock_edgar.has_going_concern.return_value = True

    client = _make_client(mock_edgar, mock_fs)
    result = client.has_going_concern("0000320193")

    assert result is True
    mock_edgar.has_restatement.assert_called_once_with("0000320193")
    mock_edgar.has_going_concern.assert_called_once_with("0000320193")
    mock_fs.set.assert_called_once()
    stored = mock_fs.set.call_args[0][2]
    assert stored["has_going_concern"] is True
    assert stored["has_restatement"] is False
    assert "_cached_at" in stored


def test_cache_hit_returns_cached_data_without_calling_edgar():
    mock_edgar = MagicMock()
    mock_fs = MagicMock()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    mock_fs.get.return_value = {
        "has_restatement": True,
        "has_going_concern": False,
        "_cached_at": fresh_ts,
    }

    client = _make_client(mock_edgar, mock_fs)
    assert client.has_restatement("0000320193") is True
    mock_edgar.has_restatement.assert_not_called()


def test_expired_cache_refetches_from_edgar():
    mock_edgar = MagicMock()
    mock_fs = MagicMock()
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    mock_fs.get.return_value = {
        "has_restatement": False,
        "has_going_concern": False,
        "_cached_at": stale_ts,
    }
    mock_edgar.has_restatement.return_value = True
    mock_edgar.has_going_concern.return_value = False

    client = _make_client(mock_edgar, mock_fs)
    result = client.has_restatement("0000320193")

    mock_edgar.has_restatement.assert_called_once()
    assert result is True


def test_second_method_call_reuses_freshly_written_cache():
    # First call: cache miss → fetches from Edgar, writes to Firestore
    # Second call: Firestore now returns the fresh data → no second Edgar call
    mock_edgar = MagicMock()
    mock_fs = MagicMock()
    mock_edgar.has_restatement.return_value = False
    mock_edgar.has_going_concern.return_value = False

    call_count = {"n": 0}
    def get_side_effect(collection, key):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return None  # first call: cache miss
        fresh_ts = datetime.now(timezone.utc).isoformat()
        return {"has_restatement": False, "has_going_concern": False, "_cached_at": fresh_ts}

    mock_fs.get.side_effect = get_side_effect

    client = _make_client(mock_edgar, mock_fs)
    client.has_restatement("0000320193")
    client.has_going_concern("0000320193")

    # Edgar should have been called exactly once for each signal (from the first fetch)
    assert mock_edgar.has_restatement.call_count == 1
    assert mock_edgar.has_going_concern.call_count == 1


def test_has_active_enforcement_delegates_to_edgar_without_caching():
    mock_edgar = MagicMock()
    mock_edgar.has_active_enforcement.return_value = False
    mock_fs = MagicMock()

    client = _make_client(mock_edgar, mock_fs)
    result = client.has_active_enforcement("0000320193")

    mock_edgar.has_active_enforcement.assert_called_once_with("0000320193")
    mock_fs.get.assert_not_called()
    assert result is False


def test_going_concern_hit_delegates_to_edgar_without_caching():
    mock_edgar = MagicMock()
    sentinel = object()
    mock_edgar.going_concern_hit.return_value = sentinel
    mock_fs = MagicMock()

    client = _make_client(mock_edgar, mock_fs)
    result = client.going_concern_hit("0000320193")

    mock_edgar.going_concern_hit.assert_called_once_with("0000320193", 24)
    mock_fs.get.assert_not_called()
    assert result is sentinel


def test_missing_cached_at_triggers_refetch():
    mock_edgar = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = {
        "has_restatement": False,
        "has_going_concern": False,
        # no _cached_at — malformed cache entry
    }
    mock_edgar.has_restatement.return_value = True
    mock_edgar.has_going_concern.return_value = False

    client = _make_client(mock_edgar, mock_fs)
    result = client.has_restatement("0000320193")

    mock_edgar.has_restatement.assert_called_once()
    assert result is True
