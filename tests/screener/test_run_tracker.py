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
    record = tracker.finish()
    mock_fs.set.assert_called_once()
    collection_arg, run_id_arg, payload_arg = mock_fs.set.call_args[0]
    assert collection_arg == "dev_screener_runs"
    assert run_id_arg == record.run_id
    assert payload_arg["tickers_processed"] == 1
    assert payload_arg["status"] == "success"


def test_finish_sets_status():
    tracker, _ = _tracker()
    record = tracker.finish(status="partial")
    assert record.status == "partial"


def test_mark_truncated_then_finish_derives_partial():
    tracker, _ = _tracker()
    tracker.mark_truncated()
    record = tracker.finish()
    assert record.status == "partial"


def test_finish_without_truncation_derives_success():
    tracker, _ = _tracker()
    record = tracker.finish()
    assert record.status == "success"


def test_explicit_status_wins_over_truncation_flag():
    tracker, _ = _tracker()
    tracker.mark_truncated()
    record = tracker.finish(status="aborted")
    assert record.status == "aborted"


def test_explicit_partial_honored_without_truncation():
    tracker, _ = _tracker()
    record = tracker.finish(status="partial")
    assert record.status == "partial"


def test_finish_sets_completed_at():
    tracker, _ = _tracker()
    record = tracker.finish()
    assert record.completed_at is not None
    assert record.completed_at >= record.started_at


def test_run_id_is_iso_timestamp_string():
    from datetime import datetime

    tracker, _ = _tracker()
    record = tracker.finish()
    datetime.fromisoformat(record.run_id)  # raises ValueError if not valid ISO format


def test_start_writes_running_doc_under_run_id():
    tracker, mock_fs = _tracker(collection="dev_screener_runs")
    tracker.start()
    mock_fs.set.assert_called_once()
    collection_arg, run_id_arg, payload_arg = mock_fs.set.call_args[0]
    assert collection_arg == "dev_screener_runs"
    assert payload_arg["status"] == "running"
    assert payload_arg["run_id"] == run_id_arg
    assert payload_arg["completed_at"] is None


def test_finish_overwrites_start_doc_with_same_id():
    tracker, mock_fs = _tracker()
    tracker.start()
    record = tracker.finish()
    start_call, finish_call = mock_fs.set.call_args_list
    assert start_call[0][1] == finish_call[0][1] == record.run_id
    assert finish_call[0][2]["status"] == "success"


def test_start_twice_raises():
    tracker, _ = _tracker()
    tracker.start()
    with pytest.raises(RuntimeError, match="start"):
        tracker.start()


def test_start_after_finish_raises():
    tracker, _ = _tracker()
    tracker.finish()
    with pytest.raises(RuntimeError, match="start"):
        tracker.start()


def test_start_propagates_firestore_failure():
    from app.errors import DataSourceError

    tracker, mock_fs = _tracker()
    mock_fs.set.side_effect = DataSourceError("Firestore set failed: down")
    with pytest.raises(DataSourceError):
        tracker.start()


def test_latest_prior_run_reads_newest_doc_by_run_id():
    tracker, mock_fs = _tracker(collection="dev_screener_runs")
    mock_fs.get_latest.return_value = {"run_id": "2026-10-01", "status": "partial"}
    assert tracker.latest_prior_run() == {"run_id": "2026-10-01", "status": "partial"}
    mock_fs.get_latest.assert_called_once_with("dev_screener_runs", order_by="run_id")


def test_latest_prior_run_after_start_raises():
    # After start() the newest doc is this run's own marker, not the prior run.
    tracker, _ = _tracker()
    tracker.start()
    with pytest.raises(RuntimeError, match="before start"):
        tracker.latest_prior_run()


def test_finished_property_reflects_finish():
    tracker, _ = _tracker()
    assert tracker.finished is False
    tracker.finish()
    assert tracker.finished is True


def test_mark_failed_after_finish_overwrites_doc_as_aborted():
    tracker, mock_fs = _tracker(collection="dev_screener_runs")
    tracker.record_ticker(tokens_in=10, tokens_out=2)
    record = tracker.finish()
    aborted = tracker.mark_failed_after_finish("DataSourceError: push failed")

    assert mock_fs.set.call_count == 2
    collection_arg, run_id_arg, payload_arg = mock_fs.set.call_args[0]
    assert collection_arg == "dev_screener_runs"
    assert run_id_arg == record.run_id
    assert payload_arg["status"] == "aborted"
    assert payload_arg["failure_reason"] == "DataSourceError: push failed"
    assert payload_arg["tickers_processed"] == 1
    assert aborted.status == "aborted"


def test_mark_failed_before_finish_raises():
    tracker, _ = _tracker()
    with pytest.raises(RuntimeError, match="finish"):
        tracker.mark_failed_after_finish("boom")


def test_finish_record_has_no_failure_reason():
    tracker, mock_fs = _tracker()
    tracker.finish()
    assert mock_fs.set.call_args[0][2]["failure_reason"] is None
