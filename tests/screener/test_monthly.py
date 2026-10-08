from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.models.run_record import RunRecord
from app.screener import monthly
from app.screener.monthly import run_monthly_pipeline

_RUN_ID = "2026-11-01T04:00:00+00:00"


def _run_result(paths: list[Path]) -> tuple[list, RunRecord, list[Path]]:
    return [], RunRecord(run_id=_RUN_ID, status="success"), paths


class _FakeReport:
    def to_dict(self) -> dict:
        return {"going_concern_drops": [], "edgar_skipped": {}}


@contextmanager
def _patched_builders(
    github: MagicMock | None = None, tracker: MagicMock | None = None
) -> Iterator[dict[str, MagicMock]]:
    """Patch every network-touching builder in the pipeline module."""
    targets = {
        "build_screener_pipeline": None,
        "build_edgar_pipeline": None,
        "build_revenue_series_cache": None,
        "build_edgar_annual_series": None,
        "build_run_tracker": tracker or MagicMock(),
        "build_github_client": github or MagicMock(),
        "_load_universe": ["AAPL", "MSFT"],
    }
    with ExitStack() as stack:
        mocks = {
            name: stack.enter_context(
                patch.object(monthly, name, return_value=value)
                if value is not None
                else patch.object(monthly, name)
            )
            for name, value in targets.items()
        }
        yield mocks


def test_full_run_returns_run_record_dump() -> None:
    with (
        _patched_builders(),
        patch.object(monthly, "run_screener", return_value=_run_result([])) as run,
    ):
        result = run_monthly_pipeline()

    assert result["run_id"] == _RUN_ID
    assert result["status"] == "success"
    assert run.call_args.kwargs["tickers"] == ["AAPL", "MSFT"]


def test_full_run_pushes_each_existing_output_and_skips_missing(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "2026-11-Dimensions.md"
    existing.write_text("# dims", encoding="utf-8")
    missing = tmp_path / "2026-11-Crosshits.md"
    github = MagicMock()

    with (
        _patched_builders(github=github),
        patch.object(
            monthly, "run_screener", return_value=_run_result([existing, missing])
        ),
    ):
        run_monthly_pipeline()

    github.push_file.assert_called_once()
    path_arg, content_arg, message_arg = github.push_file.call_args[0]
    assert path_arg == existing.as_posix()
    assert content_arg == "# dims"
    assert message_arg == "chore: monthly screener output 2026-11 [skip ci]"


def test_dry_run_returns_preview_and_skips_paid_pipeline() -> None:
    github = MagicMock()
    with (
        _patched_builders(github=github) as mocks,
        patch.object(
            monthly, "run_filter_preview", return_value=_FakeReport()
        ) as preview,
        patch.object(monthly, "run_screener") as run,
    ):
        result = run_monthly_pipeline(dry_run=True)

    assert result == {"dry_run": True, "going_concern_drops": [], "edgar_skipped": {}}
    preview.assert_called_once()
    run.assert_not_called()
    mocks["build_run_tracker"].assert_not_called()
    mocks["build_revenue_series_cache"].assert_not_called()
    github.push_file.assert_not_called()


def test_load_universe_reads_repo_data_file() -> None:
    tickers = monthly._load_universe()
    assert isinstance(tickers, list)
    assert len(tickers) > 1000
    assert all(isinstance(t, str) for t in tickers)


def test_full_run_reads_prior_status_before_writing_start_marker() -> None:
    calls: list[str] = []

    def fake_latest_prior_run() -> dict[str, str]:
        calls.append("read")
        return {"run_id": "2026-10-01T03:00:00+00:00", "status": "running"}

    tracker = MagicMock()
    tracker.latest_prior_run.side_effect = fake_latest_prior_run
    tracker.start.side_effect = lambda: calls.append("start")

    def fake_run_screener(**kwargs: object) -> tuple[list, RunRecord, list[Path]]:
        calls.append("screen")
        return _run_result([])

    with (
        _patched_builders(tracker=tracker),
        patch.object(monthly, "run_screener", side_effect=fake_run_screener) as run,
    ):
        run_monthly_pipeline()

    assert calls == ["read", "start", "screen"]
    warning = run.call_args.kwargs["prior_run_warning"]
    assert warning.startswith("> ⚠️ **Vorlauf unvollständig:**")
    assert "2026-10-01T03:00:00+00:00" in warning


def test_clean_prior_run_passes_no_warning() -> None:
    tracker = MagicMock()
    tracker.latest_prior_run.return_value = {"run_id": "x", "status": "success"}
    with (
        _patched_builders(tracker=tracker),
        patch.object(monthly, "run_screener", return_value=_run_result([])) as run,
    ):
        run_monthly_pipeline()

    assert run.call_args.kwargs["prior_run_warning"] is None
    tracker.start.assert_called_once()


def test_prior_status_read_failure_does_not_abort_run() -> None:
    from app.errors import DataSourceError

    tracker = MagicMock()
    tracker.latest_prior_run.side_effect = DataSourceError("Firestore down")
    with (
        _patched_builders(tracker=tracker),
        patch.object(monthly, "run_screener", return_value=_run_result([])) as run,
    ):
        result = run_monthly_pipeline()

    assert result["status"] == "success"
    assert run.call_args.kwargs["prior_run_warning"].startswith(
        "> ⚠️ **Vorlauf nicht geprüft:**"
    )
    tracker.start.assert_called_once()
