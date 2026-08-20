"""Tests for the HTML escaping choke point.

Everything that reaches a page passes through these three functions.
Dossier prose is Gemini output and Stef's hand-written notes — untrusted
input by construction, since nothing validates it between generator and
browser.
"""
from app.viewer.html import attrs, esc, tag


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
