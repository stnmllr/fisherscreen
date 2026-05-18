import json

import pytest

from app.deepdive.adr_table import load_adr_table
from app.errors import DeepDiveError


def test_load_seed_has_novo():
    entries = load_adr_table()
    assert entries["NOVO-B.CO"] == {
        "adr_ticker": "NVO",
        "cik": "0000353278",
        "form_type": "20-F",
    }


def test_missing_file_raises(tmp_path):
    with pytest.raises(DeepDiveError, match="not found"):
        load_adr_table(tmp_path / "nope.json")


def test_invalid_json_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(DeepDiveError, match="not valid JSON"):
        load_adr_table(bad)


def test_missing_entries_key_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(json.dumps({"version": 1}), encoding="utf-8")
    with pytest.raises(DeepDiveError, match="entries"):
        load_adr_table(bad)


def test_bad_cik_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(
        json.dumps(
            {"version": 1, "entries": {"X.CO": {"adr_ticker": "X", "cik": "353278", "form_type": "20-F"}}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(DeepDiveError, match="10-digit"):
        load_adr_table(bad)


def test_bad_form_type_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(
        json.dumps(
            {"version": 1, "entries": {"X.CO": {"adr_ticker": "X", "cik": "0000000001", "form_type": "8-K"}}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(DeepDiveError, match="form_type"):
        load_adr_table(bad)


def test_entry_not_object_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(
        json.dumps({"version": 1, "entries": {"X.CO": "nope"}}),
        encoding="utf-8",
    )
    with pytest.raises(DeepDiveError, match="must be an object"):
        load_adr_table(bad)


def test_entries_not_object_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    with pytest.raises(DeepDiveError, match="'entries' must be an object"):
        load_adr_table(bad)


def test_empty_adr_ticker_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(
        json.dumps(
            {"version": 1, "entries": {"X.CO": {"adr_ticker": "", "cik": "0000000001", "form_type": "20-F"}}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(DeepDiveError, match="adr_ticker"):
        load_adr_table(bad)
