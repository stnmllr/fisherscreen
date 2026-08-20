"""Minimal HTML building blocks — the single escaping choke point.

No template engine: the site is a handful of static pages, and a
dependency-free build keeps the generator runnable anywhere the repo runs.
The trade-off is that escaping is not automatic, so every value must go
through `esc` here. Rule for callers: `inner` of `tag` is already-built
markup, everything else is data and must be escaped.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Final, Sequence

logger = logging.getLogger(__name__)

MISSING: Final[str] = "—"

# `- text`, optionally indented. Two spaces or more make it a child item —
# the dossier generator indents by two, but a hand-edited note may use four
# and means the same thing.
_BULLET_RE: Final[re.Pattern[str]] = re.compile(r"^(?P<indent> *)- (?P<text>.*)$")
_NESTED_INDENT: Final[int] = 2

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


def _list_items(lines: list[str]) -> list[tuple[str, list[str]]]:
    """`["- a", "  - b"]` -> `[("a", ["b"])]`.

    An indented bullet without a parent above it cannot be attached to
    anything; it becomes a top-level item rather than being dropped.
    """
    items: list[tuple[str, list[str]]] = []
    matches = (_BULLET_RE.match(line) for line in lines)
    for match in (m for m in matches if m is not None):
        text = match.group("text").strip()
        nested = len(match.group("indent")) >= _NESTED_INDENT
        if nested and items:
            items[-1][1].append(text)
            continue
        if nested:
            logger.debug("viewer: indented bullet without parent: %r", text)
        items.append((text, []))
    return items


def _list_html(lines: list[str]) -> str:
    """Render one run of bullet lines as a one- or two-level `<ul>`."""
    rendered = []
    for text, children in _list_items(lines):
        inner = esc(text)
        if children:
            inner += tag("ul", "".join(tag("li", esc(child)) for child in children))
        rendered.append(tag("li", inner))
    return tag("ul", "".join(rendered))


def _paragraph(lines: list[str]) -> str:
    return tag("p", esc("\n".join(line.strip() for line in lines)))


def md_to_html(text: str | None) -> str:
    """Render the three Markdown structures a dossier body actually uses.

    Supported, and nothing else: two-level `- ` bullet lists (the insider
    block's owner/transaction nesting is meaning, not decoration) and
    blank-line-separated paragraphs. Emphasis, links and pipe tables are
    NOT interpreted — they are escaped and shown as written, because
    guessing at an unsupported construct silently rewrites what the dossier
    said. Peer tables reach the page pre-split through `table_html`.

    This is the single switch point for Markdown rendering: if a real
    Markdown library (e.g. markdown-it-py) is ever approved as a
    dependency, only this function changes — no call site does.

    Returns "" for absent or blank input; the caller decides what an empty
    section looks like.
    """
    if text is None:
        return ""
    blocks: list[str] = []
    buffer: list[str] = []
    buffer_is_list = False

    def flush() -> None:
        nonlocal buffer, buffer_is_list
        if buffer:
            blocks.append(_list_html(buffer) if buffer_is_list else _paragraph(buffer))
        buffer = []

    for line in text.splitlines():
        is_bullet = _BULLET_RE.match(line) is not None
        if not line.strip():
            flush()
            continue
        if is_bullet != buffer_is_list:
            flush()
            buffer_is_list = is_bullet
        buffer.append(line)
    flush()
    return "\n".join(blocks)


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
