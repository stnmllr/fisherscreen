from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.screener_record import ScreenerRecord
from app.services.cached_gemini_client import CachedGeminiClient
from app.services.gemini_client import GeminiScoreResult


def _record() -> ScreenerRecord:
    return ScreenerRecord(ticker="AAPL", name="Apple Inc.", gics_sector="Technology")


def _result(growth: int = 4) -> GeminiScoreResult:
    return GeminiScoreResult(
        dimensions={"growth": growth, "profitability": 3, "management": 4, "innovation": 5, "resilience": 3},
        summary="Strong company",
        tokens_in=500,
        tokens_out=80,
    )


def _fresh_cached(growth: int = 3) -> dict:
    return {
        "dimensions": {"growth": growth, "profitability": 3, "management": 4, "innovation": 4, "resilience": 3},
        "summary": "Cached",
        "_cached_at": datetime.now(timezone.utc).isoformat(),
    }


def _stale_cached() -> dict:
    stale_dt = datetime.now(timezone.utc) - timedelta(days=31)
    return {
        "dimensions": {"growth": 1, "profitability": 1, "management": 1, "innovation": 1, "resilience": 1},
        "summary": "Old",
        "_cached_at": stale_dt.isoformat(),
    }


def test_returns_cached_result_when_fresh():
    mock_gemini = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = _fresh_cached(growth=3)

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    result = client.score_ticker("AAPL", _record())

    mock_gemini.score_ticker.assert_not_called()
    assert result.dimensions["growth"] == 3
    assert result.tokens_in == 0
    assert result.tokens_out == 0


def test_calls_gemini_when_no_cache():
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _result(growth=4)
    mock_fs = MagicMock()
    mock_fs.get.return_value = None

    record = _record()
    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    result = client.score_ticker("AAPL", record)

    mock_gemini.score_ticker.assert_called_once_with("AAPL", record, 3000, 1000)
    assert result.dimensions["growth"] == 4
    assert result.tokens_in == 500


def test_calls_gemini_when_cache_is_stale():
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _result(growth=4)
    mock_fs = MagicMock()
    mock_fs.get.return_value = _stale_cached()

    record = _record()
    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    result = client.score_ticker("AAPL", record)

    mock_gemini.score_ticker.assert_called_once_with("AAPL", record, 3000, 1000)
    assert result.dimensions["growth"] == 4


def test_writes_to_firestore_after_api_call():
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _result()
    mock_fs = MagicMock()
    mock_fs.get.return_value = None

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    client.score_ticker("AAPL", _record())

    mock_fs.set.assert_called_once()
    written = mock_fs.set.call_args[0][2]
    assert "dimensions" in written
    assert "summary" in written
    assert "_cached_at" in written


def test_does_not_write_to_firestore_on_cache_hit():
    mock_gemini = MagicMock()
    mock_fs = MagicMock()
    mock_fs.get.return_value = _fresh_cached()

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    client.score_ticker("AAPL", _record())

    mock_fs.set.assert_not_called()


def test_is_fresh_returns_false_when_cached_at_missing():
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _result()
    mock_fs = MagicMock()
    mock_fs.get.return_value = {"dimensions": {}, "summary": ""}  # no _cached_at

    client = CachedGeminiClient(gemini=mock_gemini, firestore=mock_fs, collection="col")
    client.score_ticker("AAPL", _record())

    mock_gemini.score_ticker.assert_called_once()
