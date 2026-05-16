from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.run_record import RunRecord

client = TestClient(app)


def _mock_run_result(paths: list[Path] | None = None) -> tuple[list, RunRecord, list[Path]]:
    records: list = []
    run_record = RunRecord(run_id="2026-05-13T08:00:00+00:00", tickers_processed=1, status="success")
    if paths is None:
        paths = [Path("output/Universum/2026-05-Dimensions.md")]
    return records, run_record, paths


def test_health_endpoint_returns_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_monthly_run_endpoint_exists() -> None:
    with (
        patch("app.main.build_screener_pipeline"),
        patch("app.main.build_edgar_pipeline"),
        patch("app.main.build_gemini_pipeline"),
        patch("app.main.build_run_tracker"),
        patch("app.main.build_github_client"),
        patch("app.main.run_screener", return_value=_mock_run_result()),
        patch("app.main._load_universe", return_value=["AAPL"]),
    ):
        resp = client.post("/run/monthly")
    assert resp.status_code == 200


def test_monthly_run_returns_run_record_json() -> None:
    with (
        patch("app.main.build_screener_pipeline"),
        patch("app.main.build_edgar_pipeline"),
        patch("app.main.build_gemini_pipeline"),
        patch("app.main.build_run_tracker"),
        patch("app.main.build_github_client"),
        patch("app.main.run_screener", return_value=_mock_run_result()),
        patch("app.main._load_universe", return_value=["AAPL"]),
    ):
        resp = client.post("/run/monthly")
    data = resp.json()
    assert "run_id" in data
    assert "status" in data


def test_monthly_run_commit_message_includes_skip_ci(tmp_path: Path) -> None:
    output_file = tmp_path / "2026-05-Dimensions.md"
    output_file.write_text("# test content", encoding="utf-8")

    mock_github = MagicMock()

    with (
        patch("app.main.build_screener_pipeline"),
        patch("app.main.build_edgar_pipeline"),
        patch("app.main.build_gemini_pipeline"),
        patch("app.main.build_run_tracker"),
        patch("app.main.build_github_client", return_value=mock_github),
        patch("app.main.run_screener", return_value=_mock_run_result(paths=[output_file])),
        patch("app.main._load_universe", return_value=["AAPL"]),
    ):
        resp = client.post("/run/monthly")

    assert resp.status_code == 200
    assert mock_github.push_file.called
    _, _, commit_message = mock_github.push_file.call_args[0]
    assert "[skip ci]" in commit_message
