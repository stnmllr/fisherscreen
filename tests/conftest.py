"""Preventive output/-write guard + shared mock fixtures.

Established as preventive invariant on 2026-05-20. At time of installation,
no test in the suite violated this rule (verified by full-suite run with
output/ diffed pre/post — 469 tests, zero output/ delta). Goal: keep it
that way as new tests are added, especially by sub-agents or external
contributors who may not know the convention.

Opt-in for legitimate cases: @pytest.mark.allow_output_write (rare, e.g.
end-to-end integration smoke tests). Caller owns cleanup."""
import builtins
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).parent.parent.resolve()
_OUTPUT_DIR = (_REPO_ROOT / "output").resolve()
_WRITE_MODE_CHARS = frozenset("wax+")


def _is_forbidden_output_write(path_arg) -> bool:
    try:
        target = Path(path_arg).resolve()
    except (TypeError, ValueError, OSError):
        return False
    return target.is_relative_to(_OUTPUT_DIR)


def _block_message(path_arg) -> str:
    return (
        f"Test wrote to forbidden path: {path_arg}\n"
        f"Use tmp_path instead, or mark the test with "
        f"@pytest.mark.allow_output_write if writing to the real output/ "
        f"is intentional (rare, e.g. integration smoke)."
    )


@pytest.fixture(autouse=True)
def _output_write_guard(request, monkeypatch):
    if request.node.get_closest_marker("allow_output_write") is not None:
        yield
        return

    orig_open = builtins.open
    orig_path_open = Path.open
    orig_write_text = Path.write_text
    orig_write_bytes = Path.write_bytes

    def guarded_open(file, mode="r", *args, **kwargs):
        if any(c in mode for c in _WRITE_MODE_CHARS) and _is_forbidden_output_write(file):
            raise AssertionError(_block_message(file))
        return orig_open(file, mode, *args, **kwargs)

    def guarded_path_open(self, mode="r", *args, **kwargs):
        if any(c in mode for c in _WRITE_MODE_CHARS) and _is_forbidden_output_write(self):
            raise AssertionError(_block_message(self))
        return orig_path_open(self, mode, *args, **kwargs)

    def guarded_write_text(self, *args, **kwargs):
        if _is_forbidden_output_write(self):
            raise AssertionError(_block_message(self))
        return orig_write_text(self, *args, **kwargs)

    def guarded_write_bytes(self, *args, **kwargs):
        if _is_forbidden_output_write(self):
            raise AssertionError(_block_message(self))
        return orig_write_bytes(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes)
    yield


@pytest.fixture
def mock_yfinance():
    return MagicMock()


@pytest.fixture
def mock_edgar():
    return MagicMock()


@pytest.fixture
def mock_gemini():
    return MagicMock()


@pytest.fixture
def mock_firestore():
    return MagicMock()
