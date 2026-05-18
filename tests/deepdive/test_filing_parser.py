from app.deepdive.filing_parser import parse_filing

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
    assert parsed.section_flags == {}


def test_parses_10k_target_sections():
    parsed = parse_filing(_10K, "10-K")
    assert set(parsed.sections) == {
        "10-K_item1", "10-K_item1A", "10-K_item7", "10-K_item7A", "10-K_item8"}
    assert "three" in parsed.sections["10-K_item7"]


def test_missing_section_is_flagged_not_crash():
    parsed = parse_filing("<html><body>Item 4. only this</body></html>", "20-F")
    assert "20-F_item4" in parsed.sections
    assert parsed.section_flags["20-F_item5"] == "missing"
    assert parsed.section_flags["20-F_item18"] == "missing"


def test_oversize_section_truncated_with_marker(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_DEEPDIVE_SECTION_TOKEN_CAP", "5")
    big = "Item 4. " + ("word " * 200) + "Item 5. tail Item 18. end"
    parsed = parse_filing(f"<html><body>{big}</body></html>", "20-F")
    assert "[... section truncated for token budget]" in parsed.sections["20-F_item4"]
    assert parsed.section_flags["20-F_item4"] == "truncated"


def test_toc_false_positive_skipped():
    # A table-of-contents line "Item 5 .... 42" before the real heading must not
    # end Item 4 prematurely; the real Item 5 body comes later.
    html = ("<html><body>Item 4. real four body. "
            "Item 5 ........ 42 "  # TOC dotted leader
            "Item 4. (continued) still four "
            "Item 5. real five body Item 18. eighteen</body></html>")
    parsed = parse_filing(html, "20-F")
    assert "real five body" in parsed.sections["20-F_item5"]
