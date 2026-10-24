"""RunManager: start the deep-dive CLI as a subprocess, log it, track its status.

One run at a time. Two files per run under the runs directory:
``<run_id>.json`` (metadata, written at start and at end) and ``<run_id>.log``
(stdout + stderr of the CLI). No database — a single user, readable with ``type``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from app.deepdive.preflight import is_valid_symbol
from app.errors import DeepDiveError, RunBusyError

logger = logging.getLogger(__name__)

RATIONALE_MAX = 200  # same limit as peer_preflight._RATIONALE_MAX
PEER_COUNT = 3
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_COMMAND: tuple[str, ...] = (sys.executable, "-m", "app.deepdive")
RESTART_NOTE = "Dienst wurde neu gestartet"

_DOSSIER_LINE = re.compile(r"^Dossier written to: (?P<path>.+?)\s*$", re.MULTILINE)
# Publish status lines of the CLI (Task 2); keyed on the prefix only, the
# reason after "NOT published:" may be empty.
_PUBLISHED_LINE = re.compile(r"^Published to: ", re.MULTILINE)
_NOT_PUBLISHED_WARNING = re.compile(r"^WARNING: dossier NOT published:", re.MULTILINE)
# Timestamp + ticker, optional collision suffix. No path separators possible,
# so a run_id from a URL can never leave the runs directory.
_RUN_ID = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_[A-Z0-9][A-Z0-9.\-=]{0,19}(_\d{1,3})?$"
)

_EXIT_TEXTS: dict[int, str] = {
    0: "ok",
    1: "Ticker/Peers nicht auflösbar",
    2: "Datenquelle nicht erreichbar",
    3: "Gemini-Fehler",
}

RunStatus = Literal["running", "ok", "failed"]


def exit_code_text(code: int | None) -> str:
    """Human text for a CLI exit code (mapping from app/deepdive/__main__.py)."""
    if code is None:
        return "kein Exit-Code"
    return _EXIT_TEXTS.get(code, f"unerwarteter Fehler (Exit {code})")


def is_valid_run_id(run_id: str) -> bool:
    return bool(_RUN_ID.match(run_id))


@dataclass(frozen=True)
class RunRequest:
    ticker: str
    peers: list[str]
    rationale: str | None = None
    no_cache: bool = False
    no_insider: bool = False
    site: bool = False
    no_publish: bool = False
    quant_only_ack: bool = False


@dataclass
class RunRecord:
    run_id: str
    ticker: str
    peers: list[str]
    rationale: str | None
    flags: dict[str, bool]
    quant_only_ack: bool
    started_at: str
    finished_at: str | None
    exit_code: int | None
    status: RunStatus
    dossier_path: str | None
    log_path: str
    note: str | None = None
    exit_text: str | None = None
    argv: list[str] = field(default_factory=list)
    # True: pushed to the dossier repo; False: publish failed; None: unknown /
    # not attempted (also old records without the field).
    published: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


def build_cli_args(request: RunRequest) -> list[str]:
    """CLI arguments built from the fields — never from a joined string.

    ``--opt=value`` keeps a value that starts with ``-`` (a rationale such as
    "-- Pharma") from being read as an option by argparse.
    """
    args = ["deepdive", request.ticker, f"--peers={','.join(request.peers)}"]
    if request.rationale:
        args.append(f"--peer-rationale={request.rationale}")
    if request.no_cache:
        args.append("--no-cache")
    if request.no_insider:
        args.append("--no-insider")
    if request.site:
        args.append("--site")
    if request.no_publish:
        args.append("--no-publish")
    return args


def _validate(request: RunRequest) -> None:
    symbols = [request.ticker, *request.peers]
    bad = [s for s in symbols if not is_valid_symbol(s)]
    if bad:
        raise DeepDiveError(f"ungültige Symbole: {', '.join(bad)}")
    if len(request.peers) != PEER_COUNT:
        raise DeepDiveError(f"genau {PEER_COUNT} Peers nötig")
    if request.rationale is not None and len(request.rationale) > RATIONALE_MAX:
        raise DeepDiveError(f"Begründung länger als {RATIONALE_MAX} Zeichen")


def _now() -> datetime:
    return datetime.now().astimezone()


class RunManager:
    def __init__(
        self,
        runs_dir: Path,
        *,
        base_command: list[str] | None = None,
        cwd: Path | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._runs_dir = Path(runs_dir)
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._base_command = list(base_command or DEFAULT_BASE_COMMAND)
        self._cwd = cwd or REPO_ROOT
        self._clock = clock
        self._lock = threading.Lock()
        self._current: RunRecord | None = None
        self._watcher: threading.Thread | None = None
        self._mark_orphans_failed()

    # -- public API -------------------------------------------------------

    def start(self, request: RunRequest) -> RunRecord:
        _validate(request)
        with self._lock:
            if self._current is not None:
                raise RunBusyError(
                    f"Lauf {self._current.run_id} läuft noch — ein Lauf zur Zeit"
                )
            started = self._clock()
            run_id = self._new_run_id(started, request.ticker)
            log_path = self._runs_dir / f"{run_id}.log"
            argv = [*self._base_command, *build_cli_args(request)]
            record = RunRecord(
                run_id=run_id,
                ticker=request.ticker,
                peers=list(request.peers),
                rationale=request.rationale,
                flags={
                    "no_cache": request.no_cache,
                    "no_insider": request.no_insider,
                    "site": request.site,
                },
                quant_only_ack=request.quant_only_ack,
                started_at=started.isoformat(timespec="seconds"),
                finished_at=None,
                exit_code=None,
                status="running",
                dossier_path=None,
                log_path=str(log_path),
                argv=argv,
            )
            env = {
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                # stdout goes to a file: without this Python writes cp1252 on
                # Windows and the CLI's "✗" lines die with UnicodeEncodeError.
                "PYTHONIOENCODING": "utf-8",
            }
            with log_path.open("wb") as log_file:
                proc = subprocess.Popen(
                    argv,
                    cwd=str(self._cwd),
                    env=env,
                    # Never waits for input. Note: on Windows NUL reports
                    # isatty() True, so the CLI's is_tty is not reliably False
                    # here — harmless, because --peers wins over the prompt.
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                )
            self._write(record)
            self._current = record
            logger.info("deep-dive run %s started (pid %s)", run_id, proc.pid)
            self._watcher = threading.Thread(
                target=self._wait, args=(proc, record), daemon=True
            )
            self._watcher.start()
            return record

    def is_busy(self) -> bool:
        with self._lock:
            return self._current is not None

    def join(self, timeout: float | None = None) -> None:
        """Wait for the watcher thread of the last run (tests, shutdown)."""
        watcher = self._watcher
        if watcher is not None:
            watcher.join(timeout)

    def get(self, run_id: str) -> RunRecord | None:
        path = self._json_path(run_id)
        if path is None or not path.is_file():
            return None
        return self._read(path)

    def list(self, limit: int = 20) -> list[RunRecord]:
        records = [
            r for p in self._runs_dir.glob("*.json") if (r := self._read(p)) is not None
        ]
        records.sort(key=lambda r: (r.started_at, r.run_id), reverse=True)
        return records[:limit]

    def tail(self, run_id: str, max_bytes: int = 16_000) -> str:
        if not is_valid_run_id(run_id):
            return ""
        path = self._runs_dir / f"{run_id}.log"
        if not path.is_file():
            return ""
        with path.open("rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - max_bytes))
            data = fh.read()
        return data.decode("utf-8", errors="replace")

    # -- internals --------------------------------------------------------

    def _wait(self, proc: subprocess.Popen[bytes], record: RunRecord) -> None:
        exit_code = proc.wait()
        record.exit_code = exit_code
        record.exit_text = exit_code_text(exit_code)
        record.finished_at = self._clock().isoformat(timespec="seconds")
        record.status = "ok" if exit_code == 0 else "failed"
        record.dossier_path = self._parse_dossier(record.run_id)
        record.published = self._parse_published(record.run_id)
        with self._lock:
            self._write(record)
            self._current = None
        logger.info(
            "deep-dive run %s finished: exit %s (%s)",
            record.run_id,
            exit_code,
            record.exit_text,
        )

    def _parse_dossier(self, run_id: str) -> str | None:
        matches = _DOSSIER_LINE.findall(self.tail(run_id, max_bytes=1_000_000))
        return matches[-1] if matches else None

    def _parse_published(self, run_id: str) -> bool | None:
        log = self.tail(run_id, max_bytes=1_000_000)
        if _NOT_PUBLISHED_WARNING.search(log):
            return False
        if _PUBLISHED_LINE.search(log):
            return True
        return None

    def _new_run_id(self, started: datetime, ticker: str) -> str:
        base = f"{started.strftime('%Y-%m-%dT%H-%M-%S')}_{ticker}"
        run_id, n = base, 1
        while (self._runs_dir / f"{run_id}.json").exists():
            n += 1
            run_id = f"{base}_{n}"
        return run_id

    def _json_path(self, run_id: str) -> Path | None:
        if not is_valid_run_id(run_id):
            return None
        return self._runs_dir / f"{run_id}.json"

    def _write(self, record: RunRecord) -> None:
        path = self._runs_dir / f"{record.run_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, path)

    def _read(self, path: Path) -> RunRecord | None:
        try:
            return RunRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("unreadable run record %s skipped: %s", path.name, exc)
            return None

    def _mark_orphans_failed(self) -> None:
        """The service is a single instance: a 'running' record found at
        construction belongs to a process this service no longer owns."""
        for path in self._runs_dir.glob("*.json"):
            record = self._read(path)
            if record is None or record.status != "running":
                continue
            record.status = "failed"
            record.note = RESTART_NOTE
            record.exit_text = RESTART_NOTE
            self._write(record)
            logger.warning("orphaned run %s marked failed", record.run_id)


__all__ = [
    "RunManager",
    "RunRecord",
    "RunRequest",
    "build_cli_args",
    "exit_code_text",
    "is_valid_run_id",
]
