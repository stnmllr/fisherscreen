from unittest.mock import MagicMock

import pytest

from app.errors import FisherScreenError, GeminiError
from app.models.screener_record import ScreenerRecord
from app.screener.run_tracker import RunTracker
from app.screener.scorer import MAX_TICKERS_PER_RUN, run_gemini_scoring
from app.services.gemini_client import GeminiScoreResult


def _record(ticker: str = "TEST") -> ScreenerRecord:
    return ScreenerRecord(ticker=ticker, name="Test Corp", gics_sector="Technology")


def _score_result() -> GeminiScoreResult:
    return GeminiScoreResult(
        dimensions={"growth": 4, "profitability": 3, "management": 4, "innovation": 5, "resilience": 3},
        summary="Good",
        tokens_in=500,
        tokens_out=80,
    )


def _mock_tracker() -> RunTracker:
    mock_fs = MagicMock()
    return RunTracker(firestore=mock_fs, collection="col")


def test_raises_when_ticker_count_exceeds_hard_cap():
    records = [_record(f"T{i}") for i in range(MAX_TICKERS_PER_RUN + 1)]
    mock_gemini = MagicMock()
    with pytest.raises(FisherScreenError, match="Too many tickers"):
        run_gemini_scoring(records, mock_gemini, _mock_tracker())


def test_hard_cap_exactly_at_limit_does_not_raise():
    records = [_record(f"T{i}") for i in range(MAX_TICKERS_PER_RUN)]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _score_result()
    result = run_gemini_scoring(records, mock_gemini, _mock_tracker())
    assert len(result) == MAX_TICKERS_PER_RUN


def test_populates_gemini_dimensions_on_success():
    records = [_record()]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _score_result()
    run_gemini_scoring(records, mock_gemini, _mock_tracker())
    assert records[0].gemini_dimensions == _score_result().dimensions
    assert records[0].gemini_summary == "Good"


def test_skips_ticker_on_gemini_error_and_continues():
    records = [_record("FAIL"), _record("OK")]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.side_effect = [GeminiError("api down"), _score_result()]
    result = run_gemini_scoring(records, mock_gemini, _mock_tracker())
    assert result[0].gemini_dimensions is None
    assert result[1].gemini_dimensions is not None


def test_records_tokens_in_tracker_on_success():
    records = [_record()]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = _score_result()
    tracker = _mock_tracker()
    run_gemini_scoring(records, mock_gemini, tracker)
    assert tracker._tokens_in == 500
    assert tracker._tokens_out == 80
    assert tracker._tickers_processed == 1


def test_records_skip_in_tracker_on_gemini_error():
    records = [_record()]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.side_effect = GeminiError("failed")
    tracker = _mock_tracker()
    run_gemini_scoring(records, mock_gemini, tracker)
    assert tracker._tickers_skipped == 1
    assert tracker._tickers_processed == 0


def test_returns_all_records_including_skipped():
    records = [_record("A"), _record("B")]
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.side_effect = [GeminiError("err"), _score_result()]
    result = run_gemini_scoring(records, mock_gemini, _mock_tracker())
    assert len(result) == 2


def test_empty_input_returns_empty_list():
    mock_gemini = MagicMock()
    assert run_gemini_scoring([], mock_gemini, _mock_tracker()) == []
