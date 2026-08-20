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
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict

MISSING: Final[str] = "—"

# Both tables on this site are wider than a phone: the 7-column peer table
# needs about 532px even at the 12px mobile size, against 343px usable on a
# 375px screen. A table that overflows a plain <section> drags the whole
# page into sideways scrolling, so every table goes into this container and
# scrolls inside it instead. The matching rules live in `assets.SITE_CSS`.
TABLE_SCROLL_CLASS: Final[str] = "table-scroll"


class _ScrollTableRenderer(RendererHTML):
    """Puts every table markdown-it emits into the same scroll container.

    The table plugin is on, so a pipe table in free prose becomes a
    `<table>` without ever passing `table_html` — and an unwrapped table
    drags the whole page into sideways scrolling on a phone.

    Hooking the table tokens rather than post-processing the rendered
    string is the point: a regex over finished HTML would also match
    `&lt;table&gt;` coming from escaped prose, while a token only exists
    where the parser actually saw a table.

    RendererHTML turns every public method into the rule for the token of
    the same name, so these two replace the default table rendering.
    `_SCROLL_OPEN` / `_SCROLL_CLOSE` are defined further down, next to
    `scrollable_table`, because they need `attrs`.
    """

    def table_open(
        self,
        tokens: Sequence[Token],
        idx: int,
        options: OptionsDict,
        env: EnvType,
    ) -> str:
        return _SCROLL_OPEN + self.renderToken(tokens, idx, options, env)

    def table_close(
        self,
        tokens: Sequence[Token],
        idx: int,
        options: OptionsDict,
        env: EnvType,
    ) -> str:
        rendered = self.renderToken(tokens, idx, options, env)
        # renderToken ends a block with a newline. That newline separates
        # this block from the next one, so it stays outside the container
        # instead of sitting inside it as a stray text node.
        closing_tag = rendered.rstrip("\n")
        return closing_tag + _SCROLL_CLOSE + rendered[len(closing_tag) :]


# MarkdownIt("commonmark") hat html=True -> rohes <script> geht UNGEFILTERT durch.
# "gfm-like" wirft ModuleNotFoundError: linkify-it-py ist nicht installiert.
# (Der gfm-like-Fehler kommt erst beim render(), nicht beim Konstruieren —
#  ein Wechsel des Presets fiele also erst auf einem echten Dossier auf.)
_MD: Final = MarkdownIt(
    "commonmark", {"html": False}, renderer_cls=_ScrollTableRenderer
).enable("table")

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
    table plugin is on for pipe tables appearing in free prose. Those get
    the same scroll container as the built ones, via
    `_ScrollTableRenderer` — see there for why a token rule and not a
    regex over the result.

    Returns "" for absent or blank input; the caller decides what an empty
    section looks like. The parser's trailing newline is stripped so the
    result composes inside `tag()` without stray whitespace.
    """
    if text is None:
        return ""
    return _MD.render(text).strip()


# The container's two halves. All three table paths use these, so the
# wrapper cannot drift between them: `_ScrollTableRenderer` has to open and
# close it separately because markdown-it emits a table token by token and
# never hands it over as one finished string.
# `tabindex="0"` because a scroll container that only a mouse wheel or a
# finger can move is unreachable by keyboard.
_SCROLL_OPEN: Final[str] = "<div" + attrs(class_=TABLE_SCROLL_CLASS, tabindex="0") + ">"
_SCROLL_CLOSE: Final[str] = "</div>"


def scrollable_table(table_markup: str) -> str:
    """Put one already-built `<table>` into its horizontal scroll container.

    For the two paths that build their table as a whole string — the peer
    table and the overview table. A wrapper on only one of them leaves the
    other page scrolling sideways as before.

    Empty markup stays empty: an empty wrapper is still a box on the page.
    """
    if not table_markup:
        return ""
    return _SCROLL_OPEN + table_markup + _SCROLL_CLOSE


def table_html(rows: Sequence[Sequence[str]], **kw: str | None) -> str:
    """Render pre-split rows; the first row is the header.

    The result is wrapped by `scrollable_table`, so every caller of this
    function gets the scroll container without asking for it.

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
    return scrollable_table(tag("table", head + tag("tbody", lines), **kw))
