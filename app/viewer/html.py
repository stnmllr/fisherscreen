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
from typing import Final

logger = logging.getLogger(__name__)

MISSING: Final[str] = "—"

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
