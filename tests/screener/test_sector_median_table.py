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


def test_invalid_json_raises(tmp_path):
    p = tmp_path / "sector_median_table.json"
    p.write_text("not valid json {{{", encoding="utf-8")
    with pytest.raises(FilterConfigError, match="unreadable"):
        load_sector_median_table(p)


def test_top_level_not_dict_raises(tmp_path):
    p = tmp_path / "sector_median_table.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(FilterConfigError, match="missing 'entries'"):
        load_sector_median_table(p)


def test_missing_entries_key_raises(tmp_path):
    p = _write(tmp_path, {"schema_version": SECTOR_TABLE_SCHEMA_VERSION, "n_min": 5, "counts": {}})
    with pytest.raises(FilterConfigError, match="missing 'entries'"):
        load_sector_median_table(p)


def test_bad_n_min_type_raises(tmp_path):
    p = _write(tmp_path, {"schema_version": SECTOR_TABLE_SCHEMA_VERSION, "n_min": "five",
                          "entries": {}, "counts": {}})
    with pytest.raises(FilterConfigError, match="bad entries/counts/n_min types"):
        load_sector_median_table(p)


def test_bool_n_min_rejected(tmp_path):
    p = _write(tmp_path, {"schema_version": SECTOR_TABLE_SCHEMA_VERSION, "n_min": True,
                          "entries": {}, "counts": {}})
    with pytest.raises(FilterConfigError, match="bad entries/counts/n_min types"):
        load_sector_median_table(p)
