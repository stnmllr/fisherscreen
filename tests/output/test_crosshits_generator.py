from pathlib import Path

import pytest

from app.models.run_record import RunRecord
from app.models.screener_record import ScreenerRecord
from app.output.crosshits_generator import generate


def _record(ticker: str, **dim_scores) -> ScreenerRecord:
    dims = {"growth": 3, "profitability": 3, "management": 3, "innovation": 3, "resilience": 3}
    dims.update(dim_scores)
    return ScreenerRecord(ticker=ticker, name=f"{ticker} Corp", gics_sector="Technology", gemini_dimensions=dims)


def _run_record() -> RunRecord:
    return RunRecord(run_id="2026-05-13T08:00:00+00:00")


def test_generate_creates_file(tmp_path):
    path = generate([_record("AAPL", growth=5, profitability=4)], _run_record(), tmp_path)
    assert path.exists()


def test_generate_filename(tmp_path):
    path = generate([_record("AAPL", growth=5, profitability=4)], _run_record(), tmp_path)
    assert path.name == "2026-05-Crosshits.md"


def test_generate_writes_to_universum_subdir(tmp_path):
    path = generate([_record("AAPL", growth=5, profitability=4)], _run_record(), tmp_path)
    assert path.parent == tmp_path / "Universum"


def test_ticker_with_two_qualifying_dims_is_a_crosshit(tmp_path):
    records = [_record("AAPL", growth=4, profitability=4)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2)
    assert "AAPL" in path.read_text(encoding="utf-8")


def test_ticker_with_one_qualifying_dim_is_not_a_crosshit(tmp_path):
    records = [_record("SOLO", growth=5, profitability=3)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2)
    content = path.read_text(encoding="utf-8")
    assert "SOLO" not in content or "Keine Crosshits" in content


def test_empty_crosshits_produces_informative_message(tmp_path):
    records = [_record("LOW", growth=2, profitability=2)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2)
    assert "Keine Crosshits" in path.read_text(encoding="utf-8")


def test_crosshits_sorted_by_dimension_count_desc(tmp_path):
    records = [
        _record("THREE", growth=4, profitability=4, management=4),
        _record("TWO", growth=4, profitability=4),
    ]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2)
    content = path.read_text(encoding="utf-8")
    assert content.index("THREE") < content.index("TWO")


def test_cap_limits_crosshits_output(tmp_path):
    records = [_record(f"T{i}", growth=5, profitability=5) for i in range(60)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2, cap=10)
    content = path.read_text(encoding="utf-8")
    table_rows = [l for l in content.splitlines() if l.startswith("| ") and "---" not in l and "#" not in l]
    assert len(table_rows) <= 10


def test_records_without_gemini_dimensions_are_excluded(tmp_path):
    records = [
        _record("SCORED", growth=5, profitability=5),
        ScreenerRecord(ticker="UNSCORED"),
    ]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2)
    assert "UNSCORED" not in path.read_text(encoding="utf-8")


def test_header_injected_after_title(tmp_path):
    from app.output.crosshits_generator import generate
    records = []
    path = generate(records, _run_record(), tmp_path,
                    score_threshold=4.0, min_dimensions=2,
                    header="## Lauf-Übersicht 2026-06\n\nHEADER_MARKER\n")
    text = path.read_text("utf-8")
    assert "HEADER_MARKER" in text
    title_idx = text.index("# Universum")
    header_idx = text.index("HEADER_MARKER")
    schwelle_idx = text.index("*Schwelle")
    assert title_idx < header_idx < schwelle_idx  # header between title and threshold note
