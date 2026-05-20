"""Tests for the preventive output/-write guard installed in tests/conftest.py.

See conftest.py module docstring for the invariant being enforced and the
rationale (established 2026-05-20 as preventive, not reactive — no test in
the suite violated the rule at time of installation)."""
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent


def test_guard_allows_write_to_tmp_path(tmp_path):
    """Baseline: tmp_path writes are unaffected by the guard. This test must
    pass trivially even before the guard is implemented — without it, the
    suite would have problems orthogonal to what the guard is solving for."""
    target = tmp_path / "sample.md"
    target.write_text("ok", encoding="utf-8")
    assert target.exists()


def test_guard_blocks_path_write_text_to_output_dir():
    """Path.write_text into <repo>/output/ raises AssertionError, message
    mentions the forbidden path."""
    target = _REPO_ROOT / "output" / "_guard_block_path_write_text.md"
    try:
        with pytest.raises(AssertionError, match=r"output"):
            target.write_text("nope", encoding="utf-8")
    finally:
        if target.exists():
            target.unlink()


def test_guard_blocks_builtins_open_write_to_output_dir():
    """builtins.open(..., 'w') into <repo>/output/ raises AssertionError."""
    target = _REPO_ROOT / "output" / "_guard_block_builtins_open.md"
    try:
        with pytest.raises(AssertionError, match=r"output"):
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("nope")
    finally:
        if target.exists():
            target.unlink()


def test_guard_blocks_path_open_write_to_output_dir():
    """Path.open(..., 'w') into <repo>/output/ raises AssertionError."""
    target = _REPO_ROOT / "output" / "_guard_block_path_open.md"
    try:
        with pytest.raises(AssertionError, match=r"output"):
            with target.open("w", encoding="utf-8") as fh:
                fh.write("nope")
    finally:
        if target.exists():
            target.unlink()
