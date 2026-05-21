"""TOC-anchor-link resolver for SEC EDGAR filings (10-K, 20-F).

Returns all `<a href="#...">`-targets in a raw iXBRL filing whose adjacent
text starts with `ITEM N` (within 80 characters of the anchor target),
sorted by document position. Caller falls back to heuristic parsing if
the result is empty.

Stage 1 of Punkt 5 (filing-parser-anchor-tracing). Plan-Doc:
`docs/superpowers/plans/punkt-5-filing-parser.md`.
"""
from __future__ import annotations

import re
import warnings
from collections import defaultdict
from dataclasses import dataclass

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from bs4.element import Tag

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_ITEM_RE = re.compile(r"^.{0,80}?\bITEM\s+(\d+[A-Z]?)\b", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class AnchorMatch:
    item_label: str
    anchor_id: str
    dom_position: int
    next_text_excerpt: str


def _read_next_text(el: Tag, max_chars: int = 250) -> str:
    buf: list[str] = []
    chars = 0
    cur = el
    own = el.get_text(" ", strip=True)
    if own:
        buf.append(own)
        chars += len(own)
    while chars < max_chars:
        sib = cur.find_next_sibling() if isinstance(cur, Tag) else None
        if sib is None:
            par = cur.parent if isinstance(cur, Tag) else None
            if par is None:
                break
            cur = par
            continue
        cur = sib
        if isinstance(cur, Tag):
            t = cur.get_text(" ", strip=True)
            if t:
                buf.append(t)
                chars += len(t) + 1
    return " ".join(buf)[:max_chars]


def resolve_anchors(raw_html: str) -> list[AnchorMatch]:
    """Return all anchor-link targets whose next-text starts with 'ITEM N',
    sorted by document position. Empty list if no usable anchor-links found
    (caller should fall back to heuristic parser)."""
    soup = BeautifulSoup(raw_html, "lxml-xml")
    by_href: dict[str, list[str]] = defaultdict(list)
    for a in soup.find_all("a", href=True):
        h = a.get("href", "")
        if h.startswith("#"):
            t = a.get_text(" ", strip=True)
            if t:
                by_href[h[1:]].append(t)
    matches: list[AnchorMatch] = []
    for tid in by_href.keys():
        target = soup.find(attrs={"id": tid}) or soup.find("a", attrs={"name": tid})
        if target is None:
            continue
        excerpt = _read_next_text(target, 250)
        m = _ITEM_RE.match(excerpt)
        if not m:
            continue
        # Position-Lookup mirrors the symmetric Target-Lookup above
        # (id OR name). Plan-Doc snippet had id-only; the name fallback
        # is required for HTML4 <a name="..."> convention coverage.
        pos = raw_html.find(f'id="{tid}"')
        if pos < 0:
            pos = raw_html.find(f'name="{tid}"')
        if pos < 0:
            continue
        matches.append(
            AnchorMatch(
                item_label=m.group(1).upper(),
                anchor_id=tid,
                dom_position=pos,
                next_text_excerpt=excerpt,
            )
        )
    matches.sort(key=lambda m: m.dom_position)
    return matches
