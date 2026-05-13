import pytest
from unittest.mock import MagicMock

from app.models.run_record import COST_PER_1M_INPUT_USD
from app.screener.run_tracker import RunTracker


def _tracker(collection: str = "col") -> tuple[RunTracker, MagicMock]:
    mock_fs = MagicMock()
    return RunTracker(firestore=mock_fs, collection=collection), mock_fs


def test_initial_state_produces_zero_record():
    tracker, _ = _tracker()
    record = tracker.finish()
    assert record.tickers_processed == 0
    assert record.tickers_skipped == 0
    assert record.tokens_in_total == 0
    assert record.estimated_cost_usd == 0.0


def test_record_ticker_accumulates_tokens():
    tracker, _ = _tracker()
    tracker.record_ticker(tokens_in=1000, tokens_out=200)
    tracker.record_ticker(tokens_in=800, tokens_out=150)
    record = tracker.finish()
    assert record.tickers_processed == 2
    assert record.tokens_in_total == 1800
    assert record.tokens_out_total == 350


def test_record_skip_increments_skipped_count():
    tracker, _ = _tracker()
    tracker.record_skip()
    tracker.record_skip()
    record = tracker.finish()
    assert record.tickers_skipped == 2
    assert record.tickers_processed == 0


def test_finish_computes_cost_from_input_tokens():
    tracker, _ = _tracker()
    tracker.record_ticker(tokens_in=1_000_000, tokens_out=0)
    record = tracker.finish()
    assert record.estimated_cost_usd == pytest.approx(COST_PER_1M_INPUT_USD)


def test_finish_writes_to_firestore():
    tracker, mock_fs = _tracker(collection="dev_screener_runs")
    tracker.record_ticker(tokens_in=500, tokens_out=100)
    tracker.finish()
    mock_fs.set.assert_called_once()
    collection_arg = mock_fs.set.call_args[0][0]
    assert collection_arg == "dev_screener_runs"


def test_finish_sets_status():
    tracker, _ = _tracker()
    record = tracker.finish(status="partial")
    assert record.status == "partial"


def test_finish_sets_completed_at():
    tracker, _ = _tracker()
    record = tracker.finish()
    assert record.completed_at is not None


def test_run_id_is_iso_timestamp_string():
    tracker, _ = _tracker()
    record = tracker.finish()
    assert "T" in record.run_id  # ISO format contains T separator
