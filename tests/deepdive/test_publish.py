from pathlib import Path

import pytest

from app.deepdive.publish import publish_dossier
from app.errors import DataSourceError


class FakeGitHub:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self._error = error

    def push_file(self, path: str, content: str, commit_message: str) -> None:
        if self._error is not None:
            raise self._error
        self.calls.append((path, content, commit_message))


def _dossier(tmp_path: Path, name: str, text: str = "# x") -> Path:
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return f


def test_publish_dossier_pushes_to_watchlist_with_host_in_message(tmp_path):
    f = _dossier(tmp_path, "SU.PA_2026-10-24.md")
    gh = FakeGitHub()
    out = publish_dossier(
        f, github=gh, repo="stnmllr/fisherscreen-dossiers", host="tools-prod-01"
    )
    assert gh.calls == [
        (
            "Watchlist/SU.PA_2026-10-24.md",
            "# x",
            "Publish SU.PA deep dive 2026-10-24 (tools-prod-01)",
        )
    ]
    assert out == "stnmllr/fisherscreen-dossiers/Watchlist/SU.PA_2026-10-24.md"


def test_publish_dossier_propagates_data_source_error(tmp_path):
    f = _dossier(tmp_path, "SU.PA_2026-10-24.md")
    gh = FakeGitHub(error=DataSourceError("boom"))
    with pytest.raises(DataSourceError, match="boom"):
        publish_dossier(f, github=gh, repo="o/r", host="pc")


def test_publish_dossier_splits_ticker_and_date_at_last_underscore(tmp_path):
    f = _dossier(tmp_path, "NOVO-B.CO_2026-05-26.md")
    gh = FakeGitHub()
    publish_dossier(f, github=gh, repo="o/r", host="pc")
    assert gh.calls[0][2] == "Publish NOVO-B.CO deep dive 2026-05-26 (pc)"


def test_publish_dossier_reads_utf8(tmp_path):
    f = _dossier(tmp_path, "X_2026-01-01.md", "Größe – €")
    gh = FakeGitHub()
    publish_dossier(f, github=gh, repo="o/r", host="pc")
    assert gh.calls[0][1] == "Größe – €"
