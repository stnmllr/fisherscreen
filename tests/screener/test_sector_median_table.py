import json
import pytest
from app.errors import FilterConfigError
from app.screener.sector_median_table import load_sector_median_table, SECTOR_TABLE_SCHEMA_VERSION


def _write(tmp_path, payload):
    p = tmp_path / "sector_median_table.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_loads_valid_table(tmp_path):
    p = _write(tmp_path, {"schema_version": SECTOR_TABLE_SCHEMA_VERSION, "vintage": "2026-06",
                          "n_min": 8, "entries": {"Retailing": 0.27},
                          "counts": {"Retailing": 9}})
    table = load_sector_median_table(p)
    assert table.entries["Retailing"] == 0.27
    assert table.n_min == 8
    assert table.counts["Retailing"] == 9


def test_missing_file_returns_none_sentinel(tmp_path):
    assert load_sector_median_table(tmp_path / "absent.json") is None


def test_schema_mismatch_raises(tmp_path):
    p = _write(tmp_path, {"schema_version": 999, "vintage": "2026-06", "n_min": 8,
                          "entries": {}, "counts": {}})
    with pytest.raises(FilterConfigError):
        load_sector_median_table(p)


def test_non_numeric_entry_raises(tmp_path):
    p = _write(tmp_path, {"schema_version": SECTOR_TABLE_SCHEMA_VERSION, "vintage": "2026-06",
                          "n_min": 8, "entries": {"Retailing": "high"}, "counts": {"Retailing": 9}})
    with pytest.raises(FilterConfigError):
        load_sector_median_table(p)


def test_entries_key_absent_from_counts_raises(tmp_path):
    # consistency: every entries bucket must also appear in counts
    p = _write(tmp_path, {"schema_version": SECTOR_TABLE_SCHEMA_VERSION, "vintage": "2026-06",
                          "n_min": 8, "entries": {"Retailing": 0.27}, "counts": {}})
    with pytest.raises(FilterConfigError):
        load_sector_median_table(p)
