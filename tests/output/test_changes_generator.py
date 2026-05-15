# tests/output/test_changes_generator.py
from pathlib import Path

import frontmatter
import pytest

from app.models.run_record import RunRecord
from app.models.screener_record import ScreenerRecord
from app.output.changes_generator import generate


def _record(ticker: str, **dim_scores) -> ScreenerRecord:
    dims = {"growth": 3, "profitability": 3, "management": 3, "innovation": 3, "resilience": 3}
    dims.update(dim_scores)
    return ScreenerRecord(ticker=ticker, gemini_dimensions=dims)


def _run_record(run_id: str = "2026-05-13T08:00:00+00:00") -> RunRecord:
    return RunRecord(run_id=run_id)


def _write_prior_dimensions(output_dir: Path, month: str, tickers_per_dim: dict) -> Path:
    """Write a prior Dimensions.md with the given tickers per dimension."""
    universum = output_dir / "Universum"
    universum.mkdir(parents=True, exist_ok=True)
    prior = universum / f"{month}-Dimensions.md"
    dim_data = {
        dim: {"qualifying_count": len(tickers), "tickers": tickers}
        for dim, tickers in tickers_per_dim.items()
    }
    metadata = {
        "run_id": f"{month}-01T08:00:00+00:00",
        "generated_at": f"{month}-01T08:42:00+00:00",
        "universum_size": 10,
        "score_threshold": 4.0,
        "cap_per_dimension": 50,
        "dimensions": dim_data,
        "crosshits": [],
    }
    post = frontmatter.Post("# Prior month body")
    post.metadata.update(metadata)
    prior.write_text(frontmatter.dumps(post), encoding="utf-8")
    return prior


def test_generate_creates_file(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    assert path.exists()


def test_generate_filename(tmp_path):
    path = generate([_record("AAPL")], _run_record("2026-05-13T08:00:00+00:00"), tmp_path)
    assert path.name == "2026-05-Changes.md"


def test_no_prior_month_produces_first_run_message(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    assert "Erster verfügbarer Run" in path.read_text(encoding="utf-8")


def test_new_ticker_in_dimension_is_highlighted(tmp_path):
    prior_dims = {
        "growth": ["OLD"], "profitability": [], "management": [],
        "innovation": [], "resilience": [],
    }
    _write_prior_dimensions(tmp_path, "2026-04", prior_dims)
    records = [_record("NEW", growth=5), _record("OLD", growth=4)]
    path = generate(records, _run_record("2026-05-13T08:00:00+00:00"), tmp_path, score_threshold=4.0)
    content = path.read_text(encoding="utf-8")
    assert "NEW" in content


def test_removed_ticker_from_dimension_is_highlighted(tmp_path):
    prior_dims = {
        "growth": ["GONE"], "profitability": [], "management": [],
        "innovation": [], "resilience": [],
    }
    _write_prior_dimensions(tmp_path, "2026-04", prior_dims)
    records = [_record("STAYS", growth=4)]  # GONE is not in current records
    path = generate(records, _run_record("2026-05-13T08:00:00+00:00"), tmp_path, score_threshold=4.0)
    content = path.read_text(encoding="utf-8")
    assert "GONE" in content


def test_gap_in_history_uses_most_recent_prior_file(tmp_path):
    prior_dims = {"growth": ["X"], "profitability": [], "management": [], "innovation": [], "resilience": []}
    _write_prior_dimensions(tmp_path, "2026-03", prior_dims)  # March — April missing
    path = generate([_record("Y", growth=4)], _run_record("2026-05-13T08:00:00+00:00"), tmp_path, score_threshold=4.0)
    content = path.read_text(encoding="utf-8")
    assert "2026-03" in content  # references March as comparison base


def test_corrupt_frontmatter_falls_back_to_no_prior(tmp_path):
    universum = tmp_path / "Universum"
    universum.mkdir()
    (universum / "2026-04-Dimensions.md").write_text("not valid frontmatter at all", encoding="utf-8")
    path = generate([_record("AAPL")], _run_record("2026-05-13T08:00:00+00:00"), tmp_path)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Erster verfügbarer Run" in content


def test_no_changes_produces_unchanged_message(tmp_path):
    prior_dims = {
        "growth": ["AAPL"], "profitability": [], "management": [],
        "innovation": [], "resilience": [],
    }
    _write_prior_dimensions(tmp_path, "2026-04", prior_dims)
    records = [_record("AAPL", growth=4)]  # same as prior
    path = generate(records, _run_record("2026-05-13T08:00:00+00:00"), tmp_path, score_threshold=4.0)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Keine Änderungen" in content
