from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import app.deepdive_ui.__main__ as ui_main
from app.config import FisherScreenSettings
from app.deepdive_ui.runs import REPO_ROOT


def _cfg(tmp_path: Path, **overrides: Any) -> FisherScreenSettings:
    values: dict[str, Any] = {
        "deepdive_ui_runs_dir": str(tmp_path / "runs"),
        "gcp_project_id": "proj",
    }
    values.update(overrides)
    return FisherScreenSettings(_env_file=None, **values)


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        ui_main.main(["--help"])
    assert exc.value.code == 0
    assert "deep-dive UI" in capsys.readouterr().out


def test_resolve_runs_dir_relative_to_repo_root(tmp_path: Path) -> None:
    assert ui_main.resolve_runs_dir(_cfg(tmp_path, deepdive_ui_runs_dir="runs")) == (
        REPO_ROOT / "runs"
    )
    assert ui_main.resolve_runs_dir(_cfg(tmp_path)) == tmp_path / "runs"


def test_peers_lookup_uses_fresh_client_per_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[str] = []

    class FakeFirestore:
        def __init__(self, project_id: str) -> None:
            created.append(project_id)

        def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
            return {"collection": collection, "id": document_id}

    monkeypatch.setattr(ui_main, "FirestoreClientImpl", FakeFirestore)
    lookup = ui_main.build_peers_lookup(_cfg(tmp_path))
    assert lookup("NVO") == {"collection": "dev_deepdive_peers", "id": "NVO"}
    lookup("LLY")
    assert created == ["proj", "proj"]


def test_main_wires_app_and_runs_uvicorn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, Any] = {}
    monkeypatch.setattr(ui_main, "build_preflight_runner", lambda: "preflight")
    monkeypatch.setattr(ui_main, "configure_logging", lambda: None)

    def fake_run(app: Any, host: str, port: int) -> None:
        calls.update(app=app, host=host, port=port)

    monkeypatch.setattr(ui_main.uvicorn, "run", fake_run)
    cfg = _cfg(tmp_path, deepdive_ui_root_path="/deepdive")
    assert ui_main.main(["--port", "9999"], cfg) == 0
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9999
    assert calls["app"].root_path == "/deepdive"
    assert (tmp_path / "runs").is_dir()
