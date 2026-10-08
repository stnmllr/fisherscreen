from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from app.errors import DataSourceError
from app.screener.prior_run import check_prior_run


def _tracker(prior: object = None, error: Exception | None = None) -> MagicMock:
    tracker = MagicMock()
    if error is not None:
        tracker.latest_prior_run.side_effect = error
    else:
        tracker.latest_prior_run.return_value = prior
    return tracker


def test_no_prior_run_yields_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert check_prior_run(_tracker(prior=None)) is None
    assert not caplog.records


def test_successful_prior_run_yields_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    prior = {"run_id": "2026-10-01T03:00:00+00:00", "status": "success"}
    with caplog.at_level(logging.WARNING):
        assert check_prior_run(_tracker(prior=prior)) is None
    assert not caplog.records


@pytest.mark.parametrize("status", ["running", "aborted", "partial"])
def test_incomplete_prior_run_yields_warning_block(
    status: str, caplog: pytest.LogCaptureFixture
) -> None:
    prior = {"run_id": "2026-10-01T03:00:00+00:00", "status": status}
    with caplog.at_level(logging.WARNING):
        warning = check_prior_run(_tracker(prior=prior))

    assert warning is not None
    assert warning.startswith("> ⚠️ **Vorlauf unvollständig:**")
    assert "2026-10-01T03:00:00+00:00" in warning
    assert f"`{status}`" in warning
    assert "Cloud Logging" in warning
    assert all(line.startswith(">") for line in warning.splitlines())
    assert any(
        r.levelno == logging.WARNING and status in r.getMessage()
        for r in caplog.records
    )


def test_running_status_explains_crash() -> None:
    prior = {"run_id": "2026-10-01T03:00:00+00:00", "status": "running"}
    warning = check_prior_run(_tracker(prior=prior))
    assert warning is not None
    assert "abgestürzt" in warning


def test_read_failure_yields_distinct_unchecked_block(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tracker = _tracker(error=DataSourceError("Firestore get_latest failed: down"))
    with caplog.at_level(logging.WARNING):
        warning = check_prior_run(tracker)

    assert warning is not None
    assert warning.startswith("> ⚠️ **Vorlauf nicht geprüft:**")
    assert "unvollständig" not in warning
    assert any(
        r.levelno == logging.WARNING and "down" in r.getMessage()
        for r in caplog.records
    )


@pytest.mark.parametrize(
    "prior",
    [
        {"run_id": "2026-10-01T03:00:00+00:00"},
        {"run_id": "2026-10-01T03:00:00+00:00", "status": "weird"},
        "not-a-dict",
    ],
)
def test_unreadable_prior_doc_yields_unchecked_block(prior: object) -> None:
    warning = check_prior_run(_tracker(prior=prior))
    assert warning is not None
    assert warning.startswith("> ⚠️ **Vorlauf nicht geprüft:**")


def test_other_exceptions_propagate() -> None:
    with pytest.raises(RuntimeError):
        check_prior_run(_tracker(error=RuntimeError("called after start")))
