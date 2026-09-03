"""Tests for the static assets.

The Fisher pages must read as the same toolbox as the macro dashboard, so
the design tokens are pinned by value here: a silent drift of --navy or
--accent would make two sites that claim to be one look like two.
"""

from app.viewer.assets import SITE_CSS, SORT_JS
from app.viewer.html import TABLE_SCROLL_CLASS

_MACRO_DASHBOARD_TOKENS = (
    "--paper:#f4f3ef",
    "--card:#ffffff",
    "--ink:#16233a",
    "--ink-soft:#5b6675",
    "--line:#e3e1da",
    "--navy:#16233a",
    "--accent:#8a2f2b",
    "--green:#1e7d4f",
    "--yellow:#c08c0e",
    "--red:#b3362b",
    "--grey:#9aa1ab",
)


def test_css_pins_the_macro_dashboard_tokens():
    for token in _MACRO_DASHBOARD_TOKENS:
        assert token in SITE_CSS, token


def test_css_has_no_webfont_import():
    """The page must look right opened offline by double click, so fonts are
    stacks with fallbacks instead of a remote @import."""
    assert "@import" not in SITE_CSS
    assert "'IBM Plex Mono',monospace" in SITE_CSS
    assert "'Spectral',serif" in SITE_CSS


def test_css_has_no_dark_theme():
    assert "prefers-color-scheme" not in SITE_CSS
    assert "theme-toggle" not in SITE_CSS


def test_css_carries_the_shared_layout_and_component_rules():
    assert "main{max-width:1240px" in SITE_CSS
    assert ".kpi.green{border-left-color:var(--green)}" in SITE_CSS
    assert ".pill.red{background:var(--red)}" in SITE_CSS
    assert "th{background:var(--navy)" in SITE_CSS


def test_css_keeps_both_macro_dashboard_breakpoints():
    assert "@media(max-width:900px)" in SITE_CSS
    assert "@media(max-width:700px)" in SITE_CSS


def test_sort_js_is_a_standalone_file_not_an_inline_snippet():
    """Served as its own file so the pages need no script-src 'unsafe-inline'."""
    assert "<script" not in SORT_JS
    assert "data-sort" in SORT_JS


_DETAIL_PAGE_RULES = (
    ".point-grid{",
    ".point.muted{",
    ".point.absent{",
    ".dot.green{",
    ".dot.yellow{",
    ".dot.red{",
    ".dot.na{",
    ".kpi.hero ",
    ".range-line{",
    ".extras{",
    ".peer-note{",
    ".hd-badges{",
    "details{",
    "dl.kv{",
)


def test_css_styles_every_class_the_detail_page_emits():
    """A class without a rule renders as unstyled markup; the detail page
    would silently lose its layout while every test still passes."""
    for rule in _DETAIL_PAGE_RULES:
        assert rule in SITE_CSS, rule


def test_point_grid_uses_the_specified_card_width():
    assert "repeat(auto-fill,minmax(280px,1fr))" in SITE_CSS


def test_section_headings_keep_their_top_margin():
    """The detail page wraps every block in a <section>, which makes each
    h2 a first-child — the shared `h2:first-child{margin-top:0}` rule would
    otherwise collapse the spacing between all sections at once."""
    assert "section>h2:first-child{margin-top:26px}" in SITE_CSS
    assert "main>section:first-child>h2{margin-top:0}" in SITE_CSS


def test_css_lets_wide_tables_scroll_instead_of_the_page():
    """Both tables are wider than a phone viewport (the 7-column peer table
    needs ~532px at 12px against 343px usable on a 375px screen). Without
    these rules the overflow moves the whole page, not just the table."""
    assert f".{TABLE_SCROLL_CLASS}{{" in SITE_CSS
    assert "overflow-x:auto" in SITE_CSS
    assert "max-width:100%" in SITE_CSS
    assert f".{TABLE_SCROLL_CLASS} table{{min-width:max-content}}" in SITE_CSS
