"""Tests for the HTML escaping choke point.

Everything that reaches a page passes through these three functions.
Dossier prose is Gemini output and Stef's hand-written notes — untrusted
input by construction, since nothing validates it between generator and
browser.
"""
import pytest
from markdown_it import MarkdownIt

from app.viewer.html import (
    TABLE_SCROLL_CLASS,
    attrs,
    esc,
    md_to_html,
    scrollable_table,
    table_html,
    tag,
)


def test_esc_renders_missing_value_as_dash():
    """None is an absence, not the string "None"."""
    assert esc(None) == "—"


def test_esc_neutralises_markup_and_quotes():
    escaped = esc('<a href="x">')

    assert "<" not in escaped
    assert ">" not in escaped
    assert '"' not in escaped


def test_esc_stringifies_non_strings():
    assert esc(42) == "42"


def test_esc_keeps_empty_string_empty():
    """An empty cell is not a missing cell — only None gets the dash."""
    assert esc("") == ""


def test_attrs_drops_none_valued_attributes():
    """A None title must vanish, not render as `title="—"` on hover."""
    assert attrs(title=None) == ""


def test_attrs_renders_leading_space_and_quotes():
    assert attrs(title="hi") == ' title="hi"'


def test_attrs_escapes_quote_in_value():
    rendered = attrs(title='say "hi"')

    assert rendered.count('"') == 2
    assert "&quot;" in rendered


def test_attrs_maps_python_names_to_html_names():
    """`class` and `data-sort` are not valid keyword names."""
    assert attrs(class_="kpi") == ' class="kpi"'
    assert attrs(data_sort="12.5") == ' data-sort="12.5"'


def test_attrs_keeps_empty_string_value():
    """`data-sort=""` is the documented "sorts last" marker, not an absence."""
    assert attrs(data_sort="") == ' data-sort=""'


def test_tag_wraps_inner_markup():
    assert tag("td", "x") == "<td>x</td>"


def test_tag_renders_attributes_and_empty_body():
    assert tag("div", class_="card") == '<div class="card"></div>'


def test_tag_does_not_escape_inner_markup():
    """`inner` is already-built HTML; escaping it again would print tags as
    text. Data must be escaped by the caller via esc()."""
    assert tag("tr", tag("td", esc("<b>"))) == "<tr><td>&lt;b&gt;</td></tr>"


def test_tag_leaves_void_element_unclosed():
    """`<meta></meta>` is invalid; void elements have no closing tag."""
    assert tag("meta", charset="utf-8") == '<meta charset="utf-8">'


# --- md_to_html -----------------------------------------------------------
# The dossier body is Gemini prose plus Stef's notes — Markdown whose exact
# shape drifts between generator versions. It is parsed as CommonMark, so
# the assertions below pin structure and escaping, not a hand-built subset.
# The parser puts each block-level tag on its own line; that whitespace is
# incidental, the nesting it surrounds is not.

NESTED_UL = "<ul>\n<li>a\n<ul>\n<li>b</li>\n</ul>\n</li>\n</ul>"


def test_md_to_html_returns_empty_string_for_none():
    """Callers decide what an absent section looks like, so None yields no
    markup at all instead of the em dash `esc` would produce."""
    assert md_to_html(None) == ""


def test_md_to_html_returns_empty_string_for_blank_text():
    assert md_to_html("   \n\n  ") == ""


def test_md_to_html_nests_two_space_indented_bullets():
    """The generator's insider block encodes owner -> transactions as
    indentation; flattening it would merge two levels of meaning."""
    assert md_to_html("- a\n  - b") == NESTED_UL


def test_md_to_html_renders_flat_bullets_side_by_side():
    assert md_to_html("- a\n- b") == "<ul>\n<li>a</li>\n<li>b</li>\n</ul>"


def test_md_to_html_treats_deeper_indentation_as_second_level():
    """A four-space bullet is a child, not a dropped line — and not a code
    block either, which is what a naive indentation rule would make of it."""
    assert md_to_html("- a\n    - b") == NESTED_UL


def test_md_to_html_keeps_orphan_child_bullet_visible():
    """An indented bullet with no parent above it is malformed input; it
    becomes a top-level item so its text cannot vanish."""
    assert md_to_html("  - lonely") == "<ul>\n<li>lonely</li>\n</ul>"


def test_md_to_html_escapes_bullet_text():
    assert md_to_html("- <b>x</b>") == "<ul>\n<li>&lt;b&gt;x&lt;/b&gt;</li>\n</ul>"


def test_md_to_html_splits_paragraphs_on_blank_line():
    assert md_to_html("first\n\nsecond") == "<p>first</p>\n<p>second</p>"


def test_md_to_html_keeps_paragraph_and_following_list_apart():
    assert md_to_html("intro\n- a") == "<p>intro</p>\n<ul>\n<li>a</li>\n</ul>"


def test_md_to_html_escapes_script_tag():
    """Dossier prose is untrusted model output — the single reason this
    renderer escapes instead of passing markup through."""
    rendered = md_to_html("<script>alert(1)</script>")

    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered


def test_md_to_html_keeps_lone_pipe_line_as_text():
    """A pipe line without a delimiter row is not a table in any Markdown
    dialect; peer tables reach the page pre-split via `dossier.peer_table`
    anyway, so a stray pipe in prose must stay readable text."""
    rendered = md_to_html("| a | b |")

    assert "<table>" not in rendered
    assert "| a | b |" in rendered


def test_md_to_html_does_not_treat_dash_without_space_as_bullet():
    assert md_to_html("-5% Umsatz") == "<p>-5% Umsatz</p>"


def test_md_to_html_renders_emphasis():
    """A real Markdown parser is the point of the switch: `**` is emphasis in
    the dossier's own source format, so it renders as emphasis instead of
    being shown as punctuation."""
    rendered = md_to_html("**bold** and *em*")

    assert rendered == "<p><strong>bold</strong> and <em>em</em></p>"


def test_md_to_html_renders_pipe_table_in_free_text():
    """Pins `.enable("table")`. Peer tables arrive pre-split via
    `table_html`, but Stef's notes are free text and may contain a table;
    without the plugin it would degrade into pipe-littered prose."""
    rendered = md_to_html("| a | b |\n| --- | --- |\n| 1 | 2 |")

    assert "<table>" in rendered
    assert "<th>a</th>" in rendered
    assert "<td>1</td>" in rendered


def test_md_to_html_wraps_pipe_table_in_scroll_container():
    """The third table path. `table_html` and the overview table are
    wrapped, but `.enable("table")` lets a pipe table in Stef's hand-written
    notes reach the page past `table_html` — unwrapped, it drags the whole
    phone page into sideways scrolling."""
    rendered = md_to_html("| a | b |\n| --- | --- |\n| 1 | 2 |")

    assert "<table>" in rendered
    assert rendered.startswith(
        f'<div class="{TABLE_SCROLL_CLASS}" tabindex="0"><table>'
    )
    assert rendered.endswith("</table></div>")


def test_md_to_html_wraps_each_table_exactly_once():
    """Counter-check against double wrapping: two tables give two
    containers, one each, and no container inside a container."""
    two_tables = "| a |\n| --- |\n| 1 |\n\ntext\n\n| b |\n| --- |\n| 2 |"

    rendered = md_to_html(two_tables)

    assert rendered.count("<table") == 2
    assert rendered.count(TABLE_SCROLL_CLASS) == 2
    assert "<div" not in rendered.split("<table", 1)[1].split("</table>", 1)[0]


def test_md_to_html_does_not_wrap_escaped_table_text():
    """Proves the wrapper hangs off the table tokens, not off a string
    search: prose that only looks like a table tag stays plain text. A
    regex over the finished HTML would wrap this escaped literal."""
    rendered = md_to_html(r"Ein \<table\> ist kein Element.")

    assert TABLE_SCROLL_CLASS not in rendered
    assert "&lt;table&gt;" in rendered


# --- md_to_html: the parser configuration is a security boundary ----------
# Dossier prose is Gemini output; nothing validates it between generator and
# browser. The tests below pin the two options that make that safe.


def test_md_to_html_escapes_raw_html_attribute_injection():
    """`html=False` is what neutralises this — the escaping is the parser's,
    not a caller's."""
    rendered = md_to_html("<img src=x onerror=alert(1)>")

    assert "<img" not in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered


def test_md_to_html_does_not_link_javascript_url():
    """A `javascript:` target fails the parser's link validation, so the
    construct stays visible text rather than becoming a clickable payload."""
    rendered = md_to_html("[klick](javascript:alert(1))")

    assert "javascript:" not in rendered.split(">", 1)[0]
    assert "<a " not in rendered
    assert "href=" not in rendered
    assert "[klick](javascript:alert(1))" in rendered


def test_md_to_html_links_ordinary_url():
    """Counterpart to the test above: link handling is validated, not
    switched off, so a normal source URL in the prose still works."""
    rendered = md_to_html("[k](https://example.com)")

    assert rendered == '<p><a href="https://example.com">k</a></p>'


def test_markdownit_default_config_would_pass_raw_html_through():
    """Guard against a later "cleanup" of the `{"html": False}` option.

    `MarkdownIt("commonmark")` alone is NOT safe for untrusted input: the
    CommonMark preset sets `html=True`, and raw HTML then reaches the page
    verbatim. This test documents the exact failure that option prevents.
    """
    unsafe = MarkdownIt("commonmark").render("<script>alert(1)</script>")

    assert "<script>alert(1)</script>" in unsafe
    assert "&lt;script&gt;" not in unsafe


def test_markdownit_gfm_like_preset_is_unusable_without_linkify():
    """The other trap: `gfm-like` looks like the natural preset for the
    table support, but it enables linkify, and `linkify-it-py` is not a
    dependency. Construction succeeds — it only fails at render time, i.e.
    on a real dossier rather than at import.
    """
    md = MarkdownIt("gfm-like")

    with pytest.raises(ModuleNotFoundError):
        md.render("harmloser text")


# --- table_html -----------------------------------------------------------


def test_table_html_uses_first_row_as_header():
    rendered = table_html([["Ticker", "P/E"], ["FICO", "37.9"]])

    assert "<thead><tr><th>Ticker</th><th>P/E</th></tr></thead>" in rendered
    assert "<tbody><tr><td>FICO</td><td>37.9</td></tr></tbody>" in rendered


def test_table_html_escapes_cells():
    rendered = table_html([["h"], ["<script>alert(1)</script>"]])

    assert "<script>alert" not in rendered
    assert "&lt;script&gt;" in rendered


def test_table_html_returns_empty_string_without_rows():
    """No rows means no table — an empty frame would suggest a peer
    comparison that was never made."""
    assert table_html([]) == ""


def test_table_html_renders_header_only_table():
    """A table whose body rows are missing still states its columns rather
    than disappearing."""
    rendered = table_html([["Ticker"]])

    assert "<th>Ticker</th>" in rendered
    assert "<tbody></tbody>" in rendered


def test_table_html_wraps_the_table_in_a_scroll_container():
    """A bare table pushes its overflow onto the page. The wrapper keeps the
    sideways scrolling inside the table, and `tabindex` makes that scroll
    reachable by keyboard."""
    rendered = table_html([["Ticker", "P/E"], ["FICO", "37.9"]])

    assert rendered.startswith(f'<div class="{TABLE_SCROLL_CLASS}" tabindex="0">')
    assert rendered.endswith("</table></div>")


def test_scrollable_table_stays_empty_for_empty_markup():
    """The wrapper never invents a box: a caller with nothing to show gets
    nothing, not an empty bordered frame on the page."""
    assert scrollable_table("") == ""


def test_table_html_returns_no_scroll_container_without_rows():
    """The empty case stays empty — an empty wrapper is still a box on the
    page suggesting a comparison that was never made."""
    assert TABLE_SCROLL_CLASS not in table_html([])
