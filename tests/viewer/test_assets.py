"""Tests for the static assets.

The Fisher pages must read as the same toolbox as the macro dashboard, so
the design tokens are pinned by value here: a silent drift of --navy or
--accent would make two sites that claim to be one look like two.
"""
from app.viewer.assets import SITE_CSS, SORT_JS

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
