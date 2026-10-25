from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.deepdive_ui.runs import (
    RESTART_NOTE,
    RunManager,
    RunRecord,
    RunRequest,
    build_cli_args,
    exit_code_text,
    is_valid_run_id,
)
from app.errors import DeepDiveError, RunBusyError

FAKE = Path(__file__).with_name("fake_deepdive.py")


def _request(**overrides: object) -> RunRequest:
    base: dict[str, object] = {"ticker": "NOVO-B.CO", "peers": ["LLY", "PFE", "MRK"]}
    base.update(overrides)
    return RunRequest(**base)  # type: ignore[arg-type]


def _manager(tmp_path: Path, *fake_opts: str) -> RunManager:
    return RunManager(
        tmp_path / "runs",
        base_command=[sys.executable, str(FAKE), *fake_opts],
        cwd=tmp_path,
    )


def _finished(manager: RunManager, run_id: str) -> RunRecord:
    manager.join(timeout=30)
    record = manager.get(run_id)
    assert record is not None
    return record


def test_build_cli_args_from_fields_only() -> None:
    args = build_cli_args(
        _request(rationale="-- Big Pharma", no_cache=True, no_insider=True, site=True)
    )
    assert args == [
        "deepdive",
        "NOVO-B.CO",
        "--peers=LLY,PFE,MRK",
        "--peer-rationale=-- Big Pharma",
        "--no-cache",
        "--no-insider",
        "--site",
    ]


def test_build_cli_args_no_publish() -> None:
    assert build_cli_args(_request(no_publish=True))[-1] == "--no-publish"
    assert "--no-publish" not in build_cli_args(_request())


@pytest.mark.parametrize(
    ("line", "published"),
    [
        ("Published to: dossiers/Watchlist/FAKE_2026-10-24.md", True),
        ("WARNING: dossier NOT published: push rejected", False),
        ("WARNING: dossier NOT published: ", False),
        ("Dossier not published (--no-publish)", None),
        ("Dossier not published (no dossier repo configured)", None),
        (None, None),
    ],
)
def test_published_parsed_from_status_line(
    tmp_path: Path, line: str | None, published: bool | None
) -> None:
    opts = ["--status-line", line] if line else []
    manager = _manager(tmp_path, *opts)
    record = manager.start(_request())
    assert _finished(manager, record.run_id).published is published


def test_old_record_without_published_loads_as_none(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    old = {
        "run_id": "2026-10-24T20-31-07_NOVO-B.CO",
        "ticker": "NOVO-B.CO",
        "peers": ["LLY", "PFE", "MRK"],
        "rationale": None,
        "flags": {},
        "quant_only_ack": False,
        "started_at": "2026-10-24T20:31:07+02:00",
        "finished_at": "2026-10-24T20:40:00+02:00",
        "exit_code": 0,
        "status": "ok",
        "dossier_path": "x.md",
        "log_path": "x.log",
    }
    (runs / f"{old['run_id']}.json").write_text(json.dumps(old), encoding="utf-8")
    manager = RunManager(runs, base_command=[sys.executable, str(FAKE)], cwd=tmp_path)
    record = manager.get(old["run_id"])
    assert record is not None and record.published is None


def test_build_cli_args_minimal() -> None:
    assert build_cli_args(_request()) == [
        "deepdive",
        "NOVO-B.CO",
        "--peers=LLY,PFE,MRK",
    ]


@pytest.mark.parametrize(
    ("code", "text"),
    [
        (0, "ok"),
        (1, "Ticker/Peers nicht auflösbar"),
        (2, "Datenquelle nicht erreichbar"),
        (3, "Gemini-Fehler"),
        (9, "unerwarteter Fehler (Exit 9)"),
        (None, "kein Exit-Code"),
    ],
)
def test_exit_code_text(code: int | None, text: str) -> None:
    assert exit_code_text(code) == text


@pytest.mark.parametrize(
    ("run_id", "ok"),
    [
        ("2026-10-24T20-31-07_NOVO-B.CO", True),
        ("2026-10-24T20-31-07_NOVO-B.CO_2", True),
        ("2026-10-24T20-31-07_^GSPC", False),
        ("../../etc/passwd", False),
        ("2026-10-24T20-31-07_A/../B", False),
        ("2026-10-24T20-31-07_A\\B", False),
    ],
)
def test_is_valid_run_id(run_id: str, ok: bool) -> None:
    assert is_valid_run_id(run_id) is ok


def test_successful_run_writes_log_and_json(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    record = manager.start(_request(rationale="Pharma", no_insider=True))
    assert record.status == "running"
    assert record.run_id.endswith("_NOVO-B.CO")
    assert is_valid_run_id(record.run_id)
    started = json.loads(
        (tmp_path / "runs" / f"{record.run_id}.json").read_text(encoding="utf-8")
    )
    assert started["status"] == "running"

    done = _finished(manager, record.run_id)
    assert done.status == "ok"
    assert done.exit_code == 0
    assert done.exit_text == "ok"
    assert done.finished_at is not None
    assert done.dossier_path == "output/Watchlist/FAKE_2026-10-24.md"
    assert manager.is_busy() is False

    log = manager.tail(record.run_id)
    assert "✗ Peer XYZ nicht gefunden" in log  # utf-8 survives the file redirect
    assert "stderr line" in log  # stderr merged into the same log
    # No STDIN_TTY assertion: on Windows DEVNULL is the NUL character device,
    # which isatty() reports as a TTY. Harmless — --peers wins over the
    # interactive path in peer_preflight.resolve_peers, and NUL reads are EOF.
    assert "STDIN_TTY " in log
    assert '"PYTHONUNBUFFERED": "1"' in log
    argv_line = next(line for line in log.splitlines() if line.startswith("ARGV "))
    assert json.loads(argv_line[5:]) == [
        "deepdive",
        "NOVO-B.CO",
        "--peers=LLY,PFE,MRK",
        "--peer-rationale=Pharma",
        "--no-insider",
    ]


@pytest.mark.parametrize("code", [1, 2, 3, 7])
def test_failed_run_status(tmp_path: Path, code: int) -> None:
    manager = _manager(tmp_path, "--exit", str(code), "--no-dossier")
    record = manager.start(_request())
    done = _finished(manager, record.run_id)
    assert done.status == "failed"
    assert done.exit_code == code
    assert done.exit_text == exit_code_text(code)
    assert done.dossier_path is None


def test_second_start_while_running_is_busy(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    manager = _manager(tmp_path, "--wait-for", str(gate))
    first = manager.start(_request())
    assert manager.is_busy() is True
    with pytest.raises(RunBusyError):
        manager.start(_request(ticker="NVO"))
    gate.write_text("go", encoding="utf-8")
    done = _finished(manager, first.run_id)
    assert done.status == "ok"
    # Free again after the first run ended.
    second = manager.start(_request(ticker="NVO"))
    assert _finished(manager, second.run_id).status == "ok"


def test_same_second_run_ids_do_not_collide(tmp_path: Path) -> None:
    fixed = datetime(2026, 10, 24, 20, 31, 7, tzinfo=timezone.utc)
    manager = RunManager(
        tmp_path / "runs",
        base_command=[sys.executable, str(FAKE)],
        cwd=tmp_path,
        clock=lambda: fixed,
    )
    first = manager.start(_request())
    manager.join(timeout=30)
    second = manager.start(_request())
    manager.join(timeout=30)
    assert first.run_id == "2026-10-24T20-31-07_NOVO-B.CO"
    assert second.run_id == "2026-10-24T20-31-07_NOVO-B.CO_2"


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"ticker": "--site"},
        {"peers": ["LLY", "PFE", "-x"]},
        {"peers": ["LLY", "PFE"]},
        {"rationale": "x" * 201},
    ],
)
def test_start_validates_again(tmp_path: Path, request_kwargs: dict) -> None:
    manager = _manager(tmp_path)
    with pytest.raises(DeepDiveError):
        manager.start(_request(**request_kwargs))
    assert list((tmp_path / "runs").iterdir()) == []


def test_orphaned_running_record_marked_failed(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    orphan = {
        "run_id": "2026-10-24T20-31-07_NVO",
        "ticker": "NVO",
        "peers": ["LLY", "PFE", "MRK"],
        "rationale": None,
        "flags": {"no_cache": False, "no_insider": False, "site": False},
        "quant_only_ack": False,
        "started_at": "2026-10-24T20:31:07+02:00",
        "finished_at": None,
        "exit_code": None,
        "status": "running",
        "dossier_path": None,
        "log_path": str(runs / "2026-10-24T20-31-07_NVO.log"),
        "unknown_future_field": 1,
    }
    (runs / "2026-10-24T20-31-07_NVO.json").write_text(
        json.dumps(orphan), encoding="utf-8"
    )
    manager = RunManager(runs, base_command=[sys.executable, str(FAKE)], cwd=tmp_path)
    record = manager.get("2026-10-24T20-31-07_NVO")
    assert record is not None
    assert record.status == "failed"
    assert record.note == RESTART_NOTE
    assert manager.is_busy() is False


def test_list_newest_first_with_limit_and_skips_garbage(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    for i in range(3):
        run_id = f"2026-10-2{i}T10-00-00_T{i}"
        (runs / f"{run_id}.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "ticker": f"T{i}",
                    "peers": ["A", "B", "C"],
                    "rationale": None,
                    "flags": {},
                    "quant_only_ack": False,
                    "started_at": f"2026-10-2{i}T10:00:00+02:00",
                    "finished_at": None,
                    "exit_code": 0,
                    "status": "ok",
                    "dossier_path": None,
                    "log_path": "",
                }
            ),
            encoding="utf-8",
        )
    (runs / "broken.json").write_text("{not json", encoding="utf-8")
    manager = RunManager(runs, base_command=[sys.executable, str(FAKE)], cwd=tmp_path)
    assert [r.ticker for r in manager.list()] == ["T2", "T1", "T0"]
    assert [r.ticker for r in manager.list(limit=2)] == ["T2", "T1"]


def test_get_and_tail_reject_unknown_and_traversal(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    assert manager.get("../secret") is None
    assert manager.get("2026-10-24T20-31-07_NOPE") is None
    assert manager.tail("../secret") == ""
    assert manager.tail("2026-10-24T20-31-07_NOPE") == ""
    manager.join()  # no run started: a no-op


def test_tail_returns_only_the_end_and_replaces_bad_bytes(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    run_id = "2026-10-24T20-31-07_NVO"
    (tmp_path / "runs" / f"{run_id}.log").write_bytes(b"A" * 100 + b"\xff" + b"END")
    tail = manager.tail(run_id, max_bytes=4)
    assert tail == "�END"
