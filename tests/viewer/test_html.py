"""Tests for the HTML escaping choke point.

Everything that reaches a page passes through these three functions.
Dossier prose is Gemini output and Stef's hand-written notes — untrusted
input by construction, since nothing validates it between generator and
browser.
"""
from app.viewer.html import attrs, esc, md_to_html, table_html, tag


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
# The dossier body is Gemini prose plus Stef's notes. Only three structures
# occur there; everything else must survive as visible text, never as markup.


def test_md_to_html_returns_empty_string_for_none():
    """Callers decide what an absent section looks like, so None yields no
    markup at all instead of the em dash `esc` would produce."""
    assert md_to_html(None) == ""


def test_md_to_html_returns_empty_string_for_blank_text():
    assert md_to_html("   \n\n  ") == ""


def test_md_to_html_nests_two_space_indented_bullets():
    """The generator's insider block encodes owner -> transactions as
    indentation; flattening it would merge two levels of meaning."""
    assert md_to_html("- a\n  - b") == "<ul><li>a<ul><li>b</li></ul></li></ul>"


def test_md_to_html_renders_flat_bullets_side_by_side():
    assert md_to_html("- a\n- b") == "<ul><li>a</li><li>b</li></ul>"


def test_md_to_html_treats_deeper_indentation_as_second_level():
    """Only two levels exist; a four-space bullet is still a child, not a
    dropped line."""
    assert md_to_html("- a\n    - b") == "<ul><li>a<ul><li>b</li></ul></li></ul>"


def test_md_to_html_keeps_orphan_child_bullet_visible():
    """An indented bullet with no parent above it is malformed input; it
    becomes a top-level item so its text cannot vanish."""
    assert md_to_html("  - lonely") == "<ul><li>lonely</li></ul>"


def test_md_to_html_escapes_bullet_text():
    assert md_to_html("- <b>x</b>") == "<ul><li>&lt;b&gt;x&lt;/b&gt;</li></ul>"


def test_md_to_html_splits_paragraphs_on_blank_line():
    assert md_to_html("first\n\nsecond") == "<p>first</p>\n<p>second</p>"


def test_md_to_html_keeps_paragraph_and_following_list_apart():
    assert md_to_html("intro\n- a") == "<p>intro</p>\n<ul><li>a</li></ul>"


def test_md_to_html_escapes_script_tag():
    """Dossier prose is untrusted model output — the single reason this
    renderer escapes instead of passing markup through."""
    rendered = md_to_html("<script>alert(1)</script>")

    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered


def test_md_to_html_does_not_interpret_emphasis():
    """No bold/italic/link support: interpreting a stray `*` would silently
    swallow characters the dossier actually wrote."""
    assert md_to_html("**bold** and *em*") == "<p>**bold** and *em*</p>"


def test_md_to_html_does_not_interpret_pipe_table():
    """Peer tables reach the page pre-split via `dossier.peer_table`; a pipe
    line in free text stays text."""
    rendered = md_to_html("| a | b |")

    assert "<table>" not in rendered
    assert "| a | b |" in rendered


def test_md_to_html_does_not_treat_dash_without_space_as_bullet():
    assert md_to_html("-5% Umsatz") == "<p>-5% Umsatz</p>"


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
