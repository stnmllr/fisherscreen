"""Tests for the anchor-resolver helper module.

Stage 1 of Punkt 5 (filing-parser-anchor-tracing). Tests the pure-function
module `app.deepdive.anchor_resolver.resolve_anchors`. Plan-Doc:
`docs/superpowers/plans/punkt-5-filing-parser.md`.

Real-filing tests run against the four authoritative cache filings under
`cache/filings/<CIK>/...`. Synthetic tests cover edge cases.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.deepdive.anchor_resolver import resolve_anchors

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache" / "filings"


def test_anchor_resolver_ko_10k_full_coverage():
    raw = (CACHE_DIR / "0000021344" / "0001628280-26-010047.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    result = resolve_anchors(raw)
    expected_items = {"1", "1A", "1B", "1C", "2", "3", "4", "5",
                      "6", "7", "7A", "8", "9", "9A", "9B", "9C",
                      "10", "11", "12", "13", "14", "15", "16"}
    found_items = {m.item_label.upper() for m in result}
    assert expected_items <= found_items, (
        f"missing: {expected_items - found_items}"
    )
    item_1a = next(m for m in result if m.item_label.upper() == "1A")
    assert re.match(
        r"^.{0,80}?\bITEM\s+1A\b", item_1a.next_text_excerpt, re.I | re.DOTALL
    )


def test_anchor_resolver_googl_10k_with_page_header_prefix():
    raw = (CACHE_DIR / "0001652044" / "0001652044-26-000018.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    result = resolve_anchors(raw)
    expected_items = {"1", "1A", "1B", "1C", "2", "3", "4", "5",
                      "6", "7", "7A", "8", "9A", "9B", "9C",
                      "10", "11", "12", "13", "14", "15", "16"}
    found_items = {m.item_label.upper() for m in result}
    assert expected_items <= found_items, (
        f"missing: {expected_items - found_items}"
    )
    item_1a = next(m for m in result if m.item_label.upper() == "1A")
    assert "Table of Contents" in item_1a.next_text_excerpt
    assert "ITEM 1A" in item_1a.next_text_excerpt.upper()


def test_anchor_resolver_novo_20f_bare_number_style():
    raw = (CACHE_DIR / "0000353278" / "0000353278-26-000012.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    result = resolve_anchors(raw)
    items = {m.item_label.upper() for m in result}
    assert {"4", "5", "18"} <= items
    item_4 = next(m for m in result if m.item_label.upper() == "4")
    assert re.match(
        r"^.{0,80}?\bITEM\s+4\b",
        item_4.next_text_excerpt,
        re.I | re.DOTALL,
    )


def test_anchor_resolver_asml_20f_no_sec_item_anchors():
    raw = (CACHE_DIR / "0000937966" / "0001628280-26-011378.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    result = resolve_anchors(raw)
    sec_items = {m.item_label.upper() for m in result} & {"4", "5", "18"}
    assert sec_items == set(), (
        f"unexpected SEC-item anchors found: {sec_items}"
    )


def test_anchor_resolver_empty_html():
    assert resolve_anchors("") == []


def test_anchor_resolver_no_internal_anchors():
    html = "<html><body><p>No anchors at all</p></body></html>"
    assert resolve_anchors(html) == []


def test_anchor_resolver_old_a_name_convention():
    html = (
        "<html><body>"
        '<a href="#sec1">Item 1.</a>'
        '<a name="sec1"></a>'
        "<p>ITEM 1. BUSINESS overview text</p>"
        "</body></html>"
    )
    result = resolve_anchors(html)
    assert len(result) == 1
    assert result[0].item_label == "1"


def test_anchor_resolver_target_with_direct_text():
    html = (
        "<html><body>"
        '<a href="#sec1">Item 1.</a>'
        '<div id="sec1">ITEM 1. BUSINESS overview text</div>'
        "</body></html>"
    )
    result = resolve_anchors(html)
    assert len(result) == 1
    assert result[0].item_label == "1"
    assert "ITEM 1" in result[0].next_text_excerpt.upper()


def test_anchor_resolver_href_without_matching_target():
    html = (
        "<html><body>"
        '<a href="#nonexistent">Item 1.</a>'
        "<p>ITEM 1. some text without anchor target</p>"
        "</body></html>"
    )
    assert resolve_anchors(html) == []


def test_anchor_resolver_single_quote_id_position_mismatch():
    # BS4 finds the target (re-serialising attribute quotes as double-quote),
    # but the raw_html keeps the original single-quotes. Both id="..." and
    # name="..." position-lookups miss → match is discarded. Defensive guard
    # against attribute-quote / entity edge cases in non-canonical HTML.
    html = (
        "<html><body>"
        "<a href='#sec1'>Item 1.</a>"
        "<div id='sec1'>ITEM 1. BUSINESS overview text</div>"
        "</body></html>"
    )
    assert resolve_anchors(html) == []
