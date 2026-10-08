from __future__ import annotations

import logging
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from app import monthly_job
from app.errors import DataSourceError


@pytest.fixture
def configure_logging() -> Iterator[MagicMock]:
    with patch.object(monthly_job, "configure_logging") as mock:
        yield mock


def _run(result: object = None, error: Exception | None = None, argv=None):
    with patch.object(monthly_job, "run_monthly_pipeline") as pipeline:
        if error is not None:
            pipeline.side_effect = error
        else:
            pipeline.return_value = result
        code = monthly_job.main([] if argv is None else argv)
    return code, pipeline


def test_success_status_exits_zero(configure_logging: MagicMock) -> None:
    code, pipeline = _run(result={"run_id": "r", "status": "success"})
    assert code == 0
    pipeline.assert_called_once_with(dry_run=False)
    configure_logging.assert_called_once()


@pytest.mark.parametrize("status", ["partial", "aborted", "running"])
def test_non_success_status_exits_one(
    status: str, configure_logging: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        code, _ = _run(result={"run_id": "r", "status": status})
    assert code == 1
    assert any(status in r.getMessage() for r in caplog.records)


def test_missing_status_exits_one(configure_logging: MagicMock) -> None:
    code, _ = _run(result={"run_id": "r"})
    assert code == 1


def test_exception_is_logged_with_traceback_and_exits_one(
    configure_logging: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        code, _ = _run(error=DataSourceError("GitHub push failed"))
    assert code == 1
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors
    assert errors[0].exc_info is not None
    assert "GitHub push failed" in str(errors[0].exc_info[1])


def test_dry_run_flag_runs_free_pipeline_and_exits_zero(
    configure_logging: MagicMock,
) -> None:
    code, pipeline = _run(
        result={"dry_run": True, "going_concern_drops": []}, argv=["--dry-run"]
    )
    assert code == 0
    pipeline.assert_called_once_with(dry_run=True)


def test_logging_configured_before_pipeline_runs(configure_logging: MagicMock) -> None:
    order: list[str] = []
    configure_logging.side_effect = lambda: order.append("logging")
    with patch.object(
        monthly_job,
        "run_monthly_pipeline",
        side_effect=lambda dry_run: order.append("pipeline") or {"status": "success"},
    ):
        monthly_job.main([])
    assert order == ["logging", "pipeline"]
