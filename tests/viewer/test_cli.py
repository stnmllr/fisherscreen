"""Tests for the viewer CLI.

The CLI is thin on purpose, so what is tested here is exactly what it
decides on its own: where it reads and writes by default, what it prints,
and how it ends. Phase 1 has no deploy step — a generator that uploads
without being asked would be a surprise, and the upload happens outside.
"""

from pathlib import Path

import pytest

from app.config import settings
from app.viewer.__main__ import build_parser, main

DOSSIER_TEXT = """---
ticker: {ticker}
form_type: 10-K
generated_at: '{generated_at}'
quant_date: '2026-01-01'
---

# Deep Dive: {ticker} Corporation ({ticker})
"""


def write_dossier(directory: Path, ticker: str, day: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{ticker}_{day}.md").write_text(
        DOSSIER_TEXT.format(ticker=ticker, generated_at=f"{day}T00:00:00+00:00"),
        encoding="utf-8",
    )


@pytest.fixture
def watchlist(tmp_path: Path) -> Path:
    """Two runs of one ticker, one run of another, one foreign file."""
    directory = tmp_path / "Watchlist"
    write_dossier(directory, "FICO", "2026-06-18")
    write_dossier(directory, "FICO", "2026-07-01")
    write_dossier(directory, "MSCI", "2026-07-01")
    (directory / "ADYEN_OnePager_Executive_Summary_2026-07-02.md").write_text(
        "prose only", encoding="utf-8"
    )
    return directory


def run(watchlist: Path, out: Path) -> int:
    return main(["--in", str(watchlist), "--out", str(out)])


def test_input_defaults_to_the_watchlist_directory():
    args = build_parser().parse_args([])

    assert args.input_dir == Path(settings.output_dir) / "Watchlist"


def test_output_defaults_to_the_site_directory():
    args = build_parser().parse_args([])

    assert args.output_dir == Path(settings.output_dir) / "site"


def test_there_is_no_deploy_flag():
    """Phase 1 writes files and nothing else."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--deploy"])


def test_successful_run_returns_zero(tmp_path, watchlist):
    assert run(watchlist, tmp_path / "site") == 0


def test_successful_run_writes_the_site(tmp_path, watchlist):
    out = tmp_path / "site"
    run(watchlist, out)

    assert (out / "index.html").exists()
    assert (out / "ticker" / "FICO.html").exists()


def test_success_line_reports_path_and_counts(tmp_path, watchlist, capsys):
    """Two tickers out of three parsed dossiers, one unreadable file — the
    numbers have to say so, otherwise a silently dropped file looks like a
    file that was never there."""
    out = tmp_path / "site"
    run(watchlist, out)
    printed = capsys.readouterr().out.strip()

    assert printed.count("\n") == 0
    assert str(out / "index.html") in printed
    assert "tickers: 2" in printed
    assert "dossiers read: 3" in printed
    assert "files skipped: 1" in printed


def test_missing_input_directory_returns_one_and_explains(tmp_path, capsys):
    exit_code = main(["--in", str(tmp_path / "nope"), "--out", str(tmp_path / "site")])

    assert exit_code == 1
    assert capsys.readouterr().out.startswith("ERROR: ")


def test_missing_input_directory_writes_nothing(tmp_path):
    """A failed build must not leave a half-written site that looks
    current."""
    out = tmp_path / "site"
    main(["--in", str(tmp_path / "nope"), "--out", str(out)])

    assert not out.exists()
