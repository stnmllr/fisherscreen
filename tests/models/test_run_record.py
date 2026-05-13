import pytest

from app.models.run_record import COST_PER_1M_INPUT_USD, COST_PER_1M_OUTPUT_USD, RunRecord


def test_run_record_defaults():
    record = RunRecord(run_id="2026-05-13T10:00:00+00:00")
    assert record.tickers_processed == 0
    assert record.tickers_skipped == 0
    assert record.tokens_in_total == 0
    assert record.tokens_out_total == 0
    assert record.estimated_cost_usd == 0.0
    assert record.status == "success"
    assert record.completed_at is None


def test_compute_cost_zero_tokens():
    record = RunRecord(run_id="test")
    assert record.compute_cost() == 0.0


def test_compute_cost_input_tokens_only():
    record = RunRecord(run_id="test", tokens_in_total=1_000_000)
    assert record.compute_cost() == pytest.approx(COST_PER_1M_INPUT_USD)


def test_compute_cost_output_tokens_only():
    record = RunRecord(run_id="test", tokens_out_total=1_000_000)
    assert record.compute_cost() == pytest.approx(COST_PER_1M_OUTPUT_USD)


def test_compute_cost_realistic_run():
    # 400 tickers x avg 1500 input + 200 output tokens
    record = RunRecord(run_id="test", tokens_in_total=600_000, tokens_out_total=80_000)
    expected = (
        (600_000 / 1_000_000 * COST_PER_1M_INPUT_USD)
        + (80_000 / 1_000_000 * COST_PER_1M_OUTPUT_USD)
    )
    assert record.compute_cost() == pytest.approx(expected)


def test_model_dump_serializes_datetimes_as_strings():
    record = RunRecord(run_id="test", status="partial")
    data = record.model_dump(mode="json")
    assert data["run_id"] == "test"
    assert data["status"] == "partial"
    assert isinstance(data["started_at"], str)
