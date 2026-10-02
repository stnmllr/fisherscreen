# tests/output/test_dimensions_generator.py
from datetime import datetime, timezone
from pathlib import Path

import frontmatter
import pytest

from app.models.run_record import RunRecord
from app.models.screener_record import ScreenerRecord
from app.output.dimensions_generator import generate
from app.screener.dimensions import DIMENSIONS


def _record(ticker: str, **dim_scores) -> ScreenerRecord:
    dims = {
        "growth": 3,
        "profitability": 3,
        "management": 3,
        "innovation": 3,
        "resilience": 3,
    }
    dims.update(dim_scores)
    return ScreenerRecord(
        ticker=ticker,
        name=f"{ticker} Corp",
        gics_sector="Technology",
        gemini_dimensions=dims,
    )


def _run_record(run_id: str = "2026-05-13T08:00:00+00:00") -> RunRecord:
    return RunRecord(run_id=run_id)


def test_generate_creates_file_in_output_dir(tmp_path):
    records = [_record("AAPL", growth=4)]
    path = generate(records, _run_record(), tmp_path)
    assert path.exists()


def test_generate_filename_uses_run_year_month(tmp_path):
    path = generate(
        [_record("AAPL")], _run_record("2026-05-13T08:00:00+00:00"), tmp_path
    )
    assert path.name == "2026-05-Dimensions.md"


def test_generate_creates_universum_subdirectory(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    assert path.parent == tmp_path / "Universum"


def test_frontmatter_has_required_top_level_keys(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    post = frontmatter.load(str(path))
    for key in (
        "run_id",
        "generated_at",
        "universum_size",
        "score_threshold",
        "cap_per_dimension",
        "dimensions",
        "crosshits",
    ):
        assert key in post.metadata, f"Missing frontmatter key: {key}"


def test_frontmatter_universum_size_matches_record_count(tmp_path):
    records = [_record("AAPL"), _record("MSFT"), _record("NVDA")]
    path = generate(records, _run_record(), tmp_path)
    post = frontmatter.load(str(path))
    assert post.metadata["universum_size"] == 3


def test_frontmatter_dimensions_has_all_five_dimensions(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    post = frontmatter.load(str(path))
    dims = post.metadata["dimensions"]
    for dim in DIMENSIONS:
        assert dim in dims, f"Missing dimension in frontmatter: {dim}"


def test_frontmatter_dimension_tickers_only_includes_qualifying_tickers(tmp_path):
    records = [
        _record("PASS", growth=4),  # qualifies: growth >= 4
        _record("FAIL", growth=3),  # does not qualify
    ]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0)
    post = frontmatter.load(str(path))
    growth_tickers = post.metadata["dimensions"]["growth"]["tickers"]
    assert "PASS" in growth_tickers
    assert "FAIL" not in growth_tickers


def test_frontmatter_dimension_qualifying_count_is_correct(tmp_path):
    records = [_record(f"T{i}", growth=4) for i in range(5)] + [
        _record("LOW", growth=3)
    ]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0)
    post = frontmatter.load(str(path))
    assert post.metadata["dimensions"]["growth"]["qualifying_count"] == 5


def test_cap_limits_tickers_in_frontmatter(tmp_path):
    records = [_record(f"T{i}", growth=5) for i in range(60)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, cap=50)
    post = frontmatter.load(str(path))
    assert len(post.metadata["dimensions"]["growth"]["tickers"]) == 50


def test_markdown_body_contains_all_five_dimension_sections(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    post = frontmatter.load(str(path))
    body = post.content
    for dim in DIMENSIONS:
        assert dim.capitalize() in body or dim in body.lower()


def test_management_section_renders_na_explanation(tmp_path):
    path = generate([_record("AAPL", management=5)], _run_record(), tmp_path)
    body = frontmatter.load(str(path)).content
    assert "Governance wird upstream im EDGAR-Gate geprüft" in body
    assert "kein Merit-Score" in body


def test_innovation_section_renders_na_explanation(tmp_path):
    path = generate([_record("AAPL", innovation=5)], _run_record(), tmp_path)
    body = frontmatter.load(str(path)).content
    assert "keine R&D-Daten" in body
    assert "verschoben auf Deep Dive" in body


def test_merit_sections_still_list_top_tickers(tmp_path):
    path = generate(
        [_record("GROW", growth=5)], _run_record(), tmp_path, score_threshold=4.0
    )
    body = frontmatter.load(str(path)).content
    assert "GROW" in body


def test_records_without_gemini_dimensions_are_excluded(tmp_path):
    records = [
        _record("SCORED", growth=5),
        ScreenerRecord(ticker="UNSCORED"),  # gemini_dimensions is None
    ]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0)
    post = frontmatter.load(str(path))
    growth_tickers = post.metadata["dimensions"]["growth"]["tickers"]
    assert "SCORED" in growth_tickers
    assert "UNSCORED" not in growth_tickers


def test_generate_overwrites_existing_file(tmp_path):
    (tmp_path / "Universum").mkdir()
    existing = tmp_path / "Universum" / "2026-05-Dimensions.md"
    existing.write_text("old content", encoding="utf-8")
    generate([_record("AAPL")], _run_record(), tmp_path)
    assert "old content" not in existing.read_text(encoding="utf-8")


def test_frontmatter_crosshits_includes_tickers_qualifying_in_two_dimensions(tmp_path):
    records = [
        _record("MULTI", growth=5, profitability=5),  # qualifies in 2 dims → crosshit
        _record("SINGLE", growth=5),  # only 1 dim → not a crosshit
    ]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0)
    post = frontmatter.load(str(path))
    crosshit_tickers = [entry["ticker"] for entry in post.metadata["crosshits"]]
    assert "MULTI" in crosshit_tickers
    assert "SINGLE" not in crosshit_tickers


def test_frontmatter_dimension_tickers_sorted_by_score_descending(tmp_path):
    records = [
        _record("LOW", growth=4),
        _record("HIGH", growth=5),
    ]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0)
    post = frontmatter.load(str(path))
    tickers = post.metadata["dimensions"]["growth"]["tickers"]
    assert tickers.index("HIGH") < tickers.index("LOW")


def _crosshit_entries(path: Path) -> dict[str, dict]:
    post = frontmatter.load(str(path))
    return {entry["ticker"]: entry for entry in post.metadata["crosshits"]}


def test_frontmatter_crosshits_ignore_sentinel_axes(tmp_path):
    # management/innovation are sentinel-3 axes — they must never carry merit.
    records = [_record("SENT", management=5, innovation=5, growth=5)]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2
    )
    assert "SENT" not in _crosshit_entries(path)


@pytest.mark.parametrize("min_dimensions, expected", [(2, True), (3, False)])
def test_frontmatter_crosshits_honour_min_dimensions(
    tmp_path, min_dimensions, expected
):
    records = [_record("TWO", growth=5, profitability=5, resilience=3)]
    path = generate(
        records,
        _run_record(),
        tmp_path,
        score_threshold=4.0,
        min_dimensions=min_dimensions,
    )
    assert ("TWO" in _crosshit_entries(path)) is expected


def test_frontmatter_crosshits_exclude_measured_steadiness_below_threshold(tmp_path):
    record = _record("WOBBLY", growth=5, profitability=5, resilience=5)
    record.steadiness = 3.5
    record.steadiness_reason = None
    path = generate(
        [record], _run_record(), tmp_path, score_threshold=4.0, min_dimensions=3
    )
    assert "WOBBLY" not in _crosshit_entries(path)


def test_frontmatter_crosshits_keep_unmeasured_steadiness_sentinel(tmp_path):
    record = _record("NOHIST", growth=5, profitability=5, resilience=5)
    record.steadiness = 3.0
    record.steadiness_reason = "insufficient history"
    path = generate(
        [record], _run_record(), tmp_path, score_threshold=4.0, min_dimensions=3
    )
    assert "NOHIST" in _crosshit_entries(path)


def test_frontmatter_crosshit_dimensions_list_only_merit_axes(tmp_path):
    records = [
        _record(
            "ALL",
            growth=5,
            profitability=4,
            resilience=5,
            management=5,
            innovation=5,
        )
    ]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2
    )
    entry = _crosshit_entries(path)["ALL"]
    assert entry["dimensions"] == ["growth", "profitability", "resilience"]
    assert entry["avg_score"] == pytest.approx(4.67)


def test_frontmatter_crosshits_ranked_by_dims_then_fives_then_avg(tmp_path):
    # Threshold 3: NO_FIVE and ONE_FIVE tie on avg (4.0); the count of fives
    # must break the tie, independent of input order.
    records = [
        _record("NO_FIVE", growth=4, profitability=4, resilience=2),
        _record("ONE_FIVE", growth=5, profitability=3, resilience=2),
        _record("THREE_DIMS", growth=3, profitability=3, resilience=3),
    ]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=3.0, min_dimensions=2
    )
    order = list(_crosshit_entries(path))
    assert order == ["THREE_DIMS", "ONE_FIVE", "NO_FIVE"]


def test_frontmatter_qualifying_count_is_pre_cap(tmp_path):
    records = [_record(f"T{i}", growth=5) for i in range(60)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, cap=50)
    post = frontmatter.load(str(path))
    assert post.metadata["dimensions"]["growth"]["qualifying_count"] == 60
