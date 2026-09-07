"""Tests for the price-taker marking (Tool A, September 2026).

The marking is a label, never a filter: nothing here may change a score or drop
a title. What it must do is be right about which titles it names.
"""

import json

import pytest

from app.errors import FilterConfigError
from app.screener.price_takers import (
    PriceTakerTable,
    is_price_taker,
    load_price_takers,
)


def _write(tmp_path, payload):
    path = tmp_path / "price_takers.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --- classification --------------------------------------------------------


def test_a_listed_industry_marks_the_title():
    table = PriceTakerTable(industries=frozenset({"Gold"}), tickers=frozenset())
    assert is_price_taker("NEM", "Gold", table)


def test_an_unlisted_industry_does_not():
    table = PriceTakerTable(industries=frozenset({"Gold"}), tickers=frozenset())
    assert not is_price_taker("FICO", "Software - Application", table)


def test_a_ticker_override_marks_a_title_whose_industry_is_shared():
    """MU and NVDA are both 'Semiconductors' in yfinance. The industry cannot go
    on the list without dragging NVDA in, so MU is named directly."""
    table = PriceTakerTable(industries=frozenset(), tickers=frozenset({"MU"}))
    assert is_price_taker("MU", "Semiconductors", table)
    assert not is_price_taker("NVDA", "Semiconductors", table)


def test_a_missing_industry_is_not_a_price_taker():
    """yfinance can return no industry at all. Absence of evidence is not a
    label -- the title is left unmarked rather than guessed at."""
    table = PriceTakerTable(industries=frozenset({"Gold"}), tickers=frozenset())
    assert not is_price_taker("XYZ", None, table)


def test_matching_is_exact_not_substring():
    """'Gold' must not swallow 'Goldsmiths & Jewellery'. A grob list is fine;
    a fuzzy one silently mislabels."""
    table = PriceTakerTable(industries=frozenset({"Gold"}), tickers=frozenset())
    assert not is_price_taker("XYZ", "Goldsmiths & Jewellery", table)


# --- loader ----------------------------------------------------------------


def test_the_committed_table_loads_and_carries_both_arms():
    table = load_price_takers()
    assert "Gold" in table.industries
    assert "MU" in table.tickers


def test_loader_reads_both_lists(tmp_path):
    path = _write(tmp_path, {"industries": ["Gold"], "tickers": ["MU"]})
    table = load_price_takers(path)
    assert table == PriceTakerTable(
        industries=frozenset({"Gold"}), tickers=frozenset({"MU"})
    )


def test_a_missing_file_fails_loud(tmp_path):
    """Deliberately NOT fail-safe, unlike the industry-group map. A missing
    rollup there leaves an arm dormant and visibly does nothing; a missing table
    here would print 'nein' next to every title in a monthly report -- a silent
    claim that nothing is a price taker."""
    with pytest.raises(FilterConfigError, match="price_takers"):
        load_price_takers(tmp_path / "absent.json")


def test_unreadable_json_fails_loud(tmp_path):
    path = tmp_path / "price_takers.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(FilterConfigError, match="unreadable"):
        load_price_takers(path)


def test_a_missing_key_fails_loud(tmp_path):
    path = _write(tmp_path, {"industries": ["Gold"]})
    with pytest.raises(FilterConfigError, match="tickers"):
        load_price_takers(path)


def test_a_non_list_arm_fails_loud(tmp_path):
    path = _write(tmp_path, {"industries": "Gold", "tickers": []})
    with pytest.raises(FilterConfigError, match="industries"):
        load_price_takers(path)


def test_a_non_string_entry_fails_loud(tmp_path):
    path = _write(tmp_path, {"industries": ["Gold", 7], "tickers": []})
    with pytest.raises(FilterConfigError, match="non-string"):
        load_price_takers(path)


def test_meta_block_is_ignored_not_rejected(tmp_path):
    path = _write(
        tmp_path, {"_meta": {"note": "grob"}, "industries": ["Gold"], "tickers": []}
    )
    assert load_price_takers(path).industries == frozenset({"Gold"})
