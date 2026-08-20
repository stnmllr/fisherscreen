"""Minimal HTML building blocks — the single escaping choke point.

No template engine: the site is a handful of static pages, so elements are
built as strings. The trade-off is that escaping is not automatic, so every
value must go through `esc` here. Rule for callers: `inner` of `tag` is
already-built markup, everything else is data and must be escaped.

The one exception is Markdown, which is parsed by markdown-it-py: the
dossier format is model-generated and drifts, so a hand-rolled subset
parser would quietly mis-render what it has not seen. `md_to_html` is the
single place that library is used.
"""
from __future__ import annotations

import html
from typing import Final, Sequence

from markdown_it import MarkdownIt

MISSING: Final[str] = "—"

# MarkdownIt("commonmark") hat html=True -> rohes <script> geht UNGEFILTERT durch.
# "gfm-like" wirft ModuleNotFoundError: linkify-it-py ist nicht installiert.
# (Der gfm-like-Fehler kommt erst beim render(), nicht beim Konstruieren —
#  ein Wechsel des Presets fiele also erst auf einem echten Dossier auf.)
_MD: Final = MarkdownIt("commonmark", {"html": False}).enable("table")

# Only the ones this site actually emits; an unknown name stays a normal
# element rather than being guessed at.
_VOID_ELEMENTS: Final[frozenset[str]] = frozenset({"meta", "link", "br", "hr"})


def esc(value: object | None) -> str:
    """Escape any value for HTML text or attribute context.

    None renders as an em dash: a missing value is shown as missing, never
    as the literal "None" and never silently as an empty cell.
    """
    if value is None:
        return MISSING
    return html.escape(str(value), quote=True)


def _attr_name(keyword: str) -> str:
    """`class_` -> `class`, `data_sort` -> `data-sort`.

    Trailing underscore first (keyword collision), then underscores to
    hyphens (HTML attribute spelling).
    """
    return keyword.rstrip("_").replace("_", "-")


def attrs(**kw: str | None) -> str:
    """Render attributes, skipping None values, with a leading space.

    None means "attribute not present" — `title=None` must not turn into a
    tooltip reading "—". An empty string is kept: `data-sort=""` is the
    sort script's documented "no sortable value" marker.
    """
    return "".join(
        f' {_attr_name(keyword)}="{esc(value)}"'
        for keyword, value in kw.items()
        if value is not None
    )


def tag(name: str, inner: str = "", /, **kw: str | None) -> str:
    """Render one element. `inner` is markup and is NOT escaped.

    Positional-only so an attribute named `inner` stays possible and so
    call sites read as `tag("td", cell, class_="num")`.
    """
    if name in _VOID_ELEMENTS:
        return f"<{name}{attrs(**kw)}>"
    return f"<{name}{attrs(**kw)}>{inner}</{name}>"


def md_to_html(text: str | None) -> str:
    """Render a dossier body's Markdown to HTML via markdown-it-py.

    The input is Gemini-generated Markdown and Stef's hand-written notes, so
    the set of constructs that occur is not fixed — a renderer that only
    knows the structures seen so far degrades silently when the generator
    drifts. A CommonMark parser (plus tables) covers the whole format
    instead of betting on a subset.

    Untrusted input, therefore `html=False`: raw HTML in the source is
    escaped by the parser rather than passed through, and link targets go
    through its scheme validation. This function and `esc` are the only
    escaping choke points on the page.

    Peer tables still reach the page pre-split through `table_html`; the
    table plugin is on for pipe tables appearing in free prose.

    Returns "" for absent or blank input; the caller decides what an empty
    section looks like. The parser's trailing newline is stripped so the
    result composes inside `tag()` without stray whitespace.
    """
    if text is None:
        return ""
    return _MD.render(text).strip()


def table_html(rows: Sequence[Sequence[str]], **kw: str | None) -> str:
    """Render pre-split rows; the first row is the header.

    Returns "" for no rows at all: an empty table frame would claim a
    comparison the dossier never contained.
    """
    if not rows:
        return ""
    header, *body = rows
    head = tag("thead", tag("tr", "".join(tag("th", esc(cell)) for cell in header)))
    lines = "".join(
        tag("tr", "".join(tag("td", esc(cell)) for cell in row)) for row in body
    )
    return tag("table", head + tag("tbody", lines), **kw)
