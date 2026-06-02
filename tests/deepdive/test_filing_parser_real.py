"""Real-filing validation tests for the anchor-tracing filing parser.

Stage 2 of Punkt 5 (filing-parser-anchor-tracing). Runs `parse_filing`
against the four authoritative cache filings under `cache/filings/<CIK>/...`
and asserts the SectionFlag schema from the Stage-2 verification table.
Plan-Doc: `docs/superpowers/plans/punkt-5-filing-parser.md`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.deepdive.filing_parser import (
    _CHARS_PER_TOKEN,
    _FORM_ITEMS,
    _TRUNCATION_MARKER,
    _anypos_re,
    _linestart_re,
    _section_token_cap,
    _to_text,
    _toc_re,
    parse_filing,
)

# Every test here parses the never-committed authoritative cache filings under
# cache/filings/ (ADR-4: "never commit cached EDGAR filings"; .gitignore). Those are
# absent in CI's fresh checkout, so this whole module is integration: excluded in CI
# (-m "not integration") and run locally where the deep-dive cache is populated.
pytestmark = pytest.mark.integration

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache" / "filings"

_ITEM_HEADING = re.compile(r"^[\s\S]{0,300}?\bITEM\s+(\d+[A-Z]?)\b", re.IGNORECASE)


class _LegacyResult:
    def __init__(self) -> None:
        self.sections: dict[str, str] = {}


def _legacy_parse_filing(raw_document: str, form_type: str) -> _LegacyResult:
    """Frozen copy of the pre-Stage-2 parse_filing body extraction (sections
    only). Reference for the ASML fallback regress guard — must produce bodies
    byte-identical to today's parser."""
    items = _FORM_ITEMS[form_type]
    text = _to_text(raw_document)
    cap_chars = _section_token_cap() * _CHARS_PER_TOKEN
    result = _LegacyResult()

    chosen: dict[str, int] = {}
    for item in items:
        toc = _toc_re(item)
        linestarts = [
            m.start()
            for m in _linestart_re(item).finditer(text)
            if not toc.match(text[m.start() : m.start() + 80])
        ]
        if linestarts:
            tier = linestarts
        else:
            tier = [
                m.start()
                for m in _anypos_re(item).finditer(text)
                if not toc.match(text[m.start() : m.start() + 80])
            ]
        if not tier:
            continue
        chosen[item] = tier[0]

    if not chosen:
        return result
    ordered = sorted(chosen.values())
    for item in items:
        key = f"{form_type}_item{item}"
        if item not in chosen:
            continue
        pos = chosen[item]
        later = [p for p in ordered if p > pos]
        end = later[0] if later else len(text)
        body = text[pos:end].strip()
        if len(body) > cap_chars:
            body = body[:cap_chars] + "\n" + _TRUNCATION_MARKER
        result.sections[key] = body
    return result


def test_ko_10k_anchor_extraction():
    raw = (CACHE_DIR / "0000021344" / "0001628280-26-010047.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    parsed = parse_filing(raw, "10-K")
    flags = parsed.section_flags

    # All 5 SEC items extracted via the anchor path.
    for item in ("1", "1A", "7", "7A", "8"):
        key = f"10-K_item{item}"
        assert key in flags
        assert flags[key].extraction == "ok"
        assert flags[key].missing is False

    # Item 8 is large enough to trigger the truncation cap.
    assert flags["10-K_item8"].truncated is True
    # Others are not truncated.
    for item in ("1", "1A", "7", "7A"):
        assert flags[f"10-K_item{item}"].truncated is False

    # Bodies start with the expected ITEM heading (within 300-char tolerance).
    for item in ("1", "1A", "7", "7A", "8"):
        body = parsed.sections[f"10-K_item{item}"]
        m = _ITEM_HEADING.match(body)
        assert m is not None, f"item {item} body does not start with ITEM heading"
        assert m.group(1).upper() == item.upper()

    # Item 1 body has substantial content (not a TOC fragment).
    assert len(parsed.sections["10-K_item1"]) > 5_000


def test_googl_10k_anchor_extraction():
    raw = (CACHE_DIR / "0001652044" / "0001652044-26-000018.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    parsed = parse_filing(raw, "10-K")
    flags = parsed.section_flags

    for item in ("1", "1A", "7", "7A", "8"):
        assert flags[f"10-K_item{item}"].extraction == "ok"
        assert flags[f"10-K_item{item}"].missing is False

    # GOOGL §8 is ~152K chars — under the 200K cap, NOT truncated.
    assert flags["10-K_item8"].truncated is False

    for item in ("1", "1A", "7", "7A", "8"):
        body = parsed.sections[f"10-K_item{item}"]
        m = _ITEM_HEADING.match(body)
        assert m is not None, f"item {item} body does not start with ITEM heading"
        assert m.group(1).upper() == item.upper()


def test_novo_20f_anchor_extraction():
    raw = (CACHE_DIR / "0000353278" / "0000353278-26-000012.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    parsed = parse_filing(raw, "20-F")
    flags = parsed.section_flags

    for item in ("4", "5", "18"):
        assert flags[f"20-F_item{item}"].extraction == "ok"
        assert flags[f"20-F_item{item}"].missing is False
        assert flags[f"20-F_item{item}"].truncated is False

    for item in ("4", "5", "18"):
        body = parsed.sections[f"20-F_item{item}"]
        m = _ITEM_HEADING.match(body)
        assert m is not None, f"item {item} body does not start with ITEM heading"
        assert m.group(1).upper() == item.upper()


def test_asml_20f_fallback_regress_guard():
    raw = (CACHE_DIR / "0000937966" / "0001628280-26-011378.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    parsed_new = parse_filing(raw, "20-F")

    # Stage 2: ASML falls into the fallback path (0 SEC-item anchor coverage).
    for item in ("4", "5"):
        flag = parsed_new.section_flags[f"20-F_item{item}"]
        assert flag.extraction == "fallback_used"
        assert flag.missing is True  # → renders "fallback_used+missing"
        assert f"20-F_item{item}" not in parsed_new.sections

    f18 = parsed_new.section_flags["20-F_item18"]
    assert f18.extraction == "fallback_used"
    assert f18.missing is False
    assert f18.truncated is True  # → renders "fallback_used+truncated"

    # Body byte-identical to today's parser (fallback must not change behavior).
    legacy = _legacy_parse_filing(raw, "20-F")
    assert parsed_new.sections["20-F_item18"] == legacy.sections["20-F_item18"]
