import pytest

from app.deepdive.filing_parser import SectionFlag, _slice_aligned, parse_filing

_20F = """<html><body>
<p>ITEM 3. KEY INFORMATION risk text</p>
<p>Item 4. Information on the Company — business overview alpha</p>
<p>Item 5: Operating and Financial Review beta gamma</p>
<p>Item 18. Financial Statements delta</p>
<p>Item 19. Exhibits ignore</p>
</body></html>"""

_10K = """<html><body>
ITEM 1. BUSINESS one
ITEM 1A. RISK FACTORS two
ITEM 7. MANAGEMENT DISCUSSION three
ITEM 7A. MARKET RISK four
ITEM 8. FINANCIAL STATEMENTS five
ITEM 9. CONTROLS ignore
</body></html>"""


def test_parses_20f_target_sections():
    parsed = parse_filing(_20F, "20-F")
    assert set(parsed.sections) == {"20-F_item4", "20-F_item5", "20-F_item18"}
    assert "business overview alpha" in parsed.sections["20-F_item4"]
    assert "beta gamma" in parsed.sections["20-F_item5"]
    # Synthetic fixtures have no <a href="#…"> anchors → fallback path.
    assert all(
        f.extraction == "fallback_used" for f in parsed.section_flags.values()
    )
    assert all(not f.missing for f in parsed.section_flags.values())


def test_parses_10k_target_sections():
    parsed = parse_filing(_10K, "10-K")
    assert set(parsed.sections) == {
        "10-K_item1", "10-K_item1A", "10-K_item7", "10-K_item7A", "10-K_item8"}
    assert "three" in parsed.sections["10-K_item7"]


def test_missing_section_is_flagged_not_crash():
    parsed = parse_filing("<html><body>Item 4. only this</body></html>", "20-F")
    assert "20-F_item4" in parsed.sections
    for item in ("5", "18"):
        flag = parsed.section_flags[f"20-F_item{item}"]
        assert flag.extraction == "fallback_used"
        assert flag.missing is True
        assert f"20-F_item{item}" not in parsed.sections


def test_oversize_section_truncated_with_marker(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_DEEPDIVE_SECTION_TOKEN_CAP", "5")
    big = "Item 4. " + ("word " * 200) + "Item 5. tail Item 18. end"
    parsed = parse_filing(f"<html><body>{big}</body></html>", "20-F")
    assert "[... section truncated for token budget]" in parsed.sections["20-F_item4"]
    flag = parsed.section_flags["20-F_item4"]
    assert flag.truncated is True
    assert flag.extraction == "fallback_used"
    assert flag.missing is False


def test_toc_false_positive_skipped():
    # A table-of-contents line "Item 5 .... 42" before the real heading must not
    # end Item 4 prematurely; the real Item 5 body comes later.
    html = ("<html><body>Item 4. real four body. "
            "Item 5 ........ 42 "  # TOC dotted leader
            "Item 4. (continued) still four "
            "Item 5. real five body Item 18. eighteen</body></html>")
    parsed = parse_filing(html, "20-F")
    assert "real five body" in parsed.sections["20-F_item5"]


def test_cross_reference_does_not_override_real_heading():
    html = ("<html><body>"
            "<p>Item 4. business review alpha</p>"
            "<p>Item 5. operating review beta</p>"
            "<p>Item 18. financial statements gamma. "
            "As discussed in Item 5 above, revenue grew strongly.</p>"
            "</body></html>")
    parsed = parse_filing(html, "20-F")
    assert "operating review beta" in parsed.sections["20-F_item5"]
    assert "revenue grew strongly" not in parsed.sections["20-F_item5"]
    assert "revenue grew strongly" in parsed.sections["20-F_item18"]
    assert parsed.section_flags["20-F_item5"].extraction == "fallback_used"
    assert parsed.section_flags["20-F_item5"].missing is False


def test_section_flag_forbids_ok_missing():
    # Schema invariant: a section located via its anchor cannot also be missing.
    with pytest.raises(AssertionError):
        SectionFlag(extraction="ok", missing=True, truncated=False, anchor_id=None)


def test_anchor_path_partial_coverage_marks_unanchored_items_missing():
    # One expected item has an anchor (anchor path is taken) but the others do
    # not → those render "fallback_used+missing" without running the pattern
    # matcher. Partial-coverage wilderness (synthetic-only per plan).
    html = (
        '<html><body>'
        '<a href="#s1">Item 1.</a>'
        '<div id="s1"><p>ITEM 1. BUSINESS overview alpha beta gamma</p></div>'
        '</body></html>'
    )
    parsed = parse_filing(html, "10-K")
    assert parsed.section_flags["10-K_item1"].extraction == "ok"
    assert parsed.section_flags["10-K_item1"].missing is False
    assert "BUSINESS overview" in parsed.sections["10-K_item1"]
    for item in ("1A", "7", "7A", "8"):
        flag = parsed.section_flags[f"10-K_item{item}"]
        assert flag.extraction == "fallback_used"
        assert flag.missing is True
        assert f"10-K_item{item}" not in parsed.sections


def test_fallback_ambiguous_item_picks_first_candidate():
    # Two non-TOC "Item 4." headings → ambiguous; the fallback picks the first
    # and flags fallback_used (no separate ambiguous flag in the new schema).
    html = (
        "<html><body>"
        "<p>Item 4. first business section alpha</p>"
        "<p>Item 4. second occurrence beta</p>"
        "<p>Item 5. operating review</p>"
        "<p>Item 18. financials</p>"
        "</body></html>"
    )
    parsed = parse_filing(html, "20-F")
    flag = parsed.section_flags["20-F_item4"]
    assert flag.extraction == "fallback_used"
    assert flag.missing is False
    assert "first business section" in parsed.sections["20-F_item4"]


def test_slice_aligned_returns_empty_when_anchor_a_absent():
    assert _slice_aligned("<html>no ids here</html>", "missing", None) == ""


def test_slice_aligned_slices_to_end_when_anchor_b_unfindable():
    raw = '<div id="a">body content</div><div>tail</div>'
    result = _slice_aligned(raw, "a", "nonexistent")
    assert result.startswith('<div id="a">')
    assert "tail" in result
