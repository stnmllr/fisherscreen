import json

import pytest

from app.errors import FilterConfigError
from app.screener.industry_group_map import load_industry_group_map


def _write(tmp_path, payload):
    p = tmp_path / "gics_industry_group_map.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_loads_valid_map(tmp_path):
    p = _write(
        tmp_path,
        {
            "_meta": {"purpose": "ignored"},
            "map": {"Railroads": "Transportation", "Steel": "Materials"},
        },
    )
    m = load_industry_group_map(p)
    assert m == {"Railroads": "Transportation", "Steel": "Materials"}


def test_meta_is_ignored(tmp_path):
    p = _write(
        tmp_path,
        {"_meta": {"vintage": "2026-06"}, "map": {"Gold": "Materials"}},
    )
    m = load_industry_group_map(p)
    assert "_meta" not in m
    assert m == {"Gold": "Materials"}


def test_missing_file_returns_empty_dict(tmp_path):
    # FAIL-SAFE: absent map -> no group rollup -> relative arm dormant by construction.
    assert load_industry_group_map(tmp_path / "absent.json") == {}


def test_invalid_json_raises(tmp_path):
    p = tmp_path / "gics_industry_group_map.json"
    p.write_text("not valid json {{{", encoding="utf-8")
    with pytest.raises(FilterConfigError):
        load_industry_group_map(p)


def test_missing_map_key_raises(tmp_path):
    p = _write(tmp_path, {"_meta": {"x": 1}})
    with pytest.raises(FilterConfigError):
        load_industry_group_map(p)


def test_map_not_dict_raises(tmp_path):
    p = _write(tmp_path, {"map": ["Railroads", "Transportation"]})
    with pytest.raises(FilterConfigError):
        load_industry_group_map(p)


def test_non_str_value_raises(tmp_path):
    p = _write(tmp_path, {"map": {"Railroads": 123}})
    with pytest.raises(FilterConfigError):
        load_industry_group_map(p)


def test_non_str_key_rejected_via_top_level_not_dict(tmp_path):
    # JSON object keys are always strings, so a non-str KEY can only arrive when the
    # whole payload is not a JSON object. Guard the top level too.
    p = tmp_path / "gics_industry_group_map.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(FilterConfigError):
        load_industry_group_map(p)
