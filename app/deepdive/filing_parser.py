from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

import html2text

logger = logging.getLogger(__name__)

_FORM_ITEMS: dict[str, list[str]] = {
    "10-K": ["1", "1A", "7", "7A", "8"],
    "20-F": ["4", "5", "18"],
}
_TRUNCATION_MARKER = "[... section truncated for token budget]"
_CHARS_PER_TOKEN = 4  # heuristic cap (no Gemini call in this stage)


@dataclass
class ParsedFiling:
    sections: dict[str, str] = field(default_factory=dict)
    section_flags: dict[str, str] = field(default_factory=dict)


def _section_token_cap() -> int:
    return int(os.environ.get("FISHERSCREEN_DEEPDIVE_SECTION_TOKEN_CAP", "50000"))


def _to_text(raw: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0
    return h.handle(raw)


def _anchor_re(item: str) -> re.Pattern[str]:
    # Tolerant: "Item 5." / "ITEM 5" / "Item 5 —" / "Item 5:". The \b after the
    # item stops "1" matching inside "1A" and "7" inside "7A".
    return re.compile(rf"\bITEM\s+{re.escape(item)}\b\s*[.:\-—]?", re.IGNORECASE)


def parse_filing(raw_document: str, form_type: str) -> ParsedFiling:
    items = _FORM_ITEMS[form_type]
    text = _to_text(raw_document)
    cap_chars = _section_token_cap() * _CHARS_PER_TOKEN
    result = ParsedFiling()

    # Collect every anchor occurrence for every target item, in document order.
    hits: list[tuple[int, str]] = []
    for item in items:
        for m in _anchor_re(item).finditer(text):
            hits.append((m.start(), item))
    hits.sort(key=lambda t: t[0])
    starts = [pos for pos, _ in hits]

    # For each item take the LAST anchor: a table-of-contents entry for an item
    # (e.g. "Item 5 ...... 42") appears near the top, before the real section,
    # so the highest-position anchor is the real heading. The section body runs
    # to the next target anchor of any item.
    chosen: dict[str, tuple[int, int]] = {}
    for idx, (pos, item) in enumerate(hits):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
        chosen[item] = (pos, end)  # later anchor overwrites the earlier (TOC) one

    for item in items:
        key = f"{form_type}_item{item}"
        if item not in chosen:
            result.section_flags[key] = "missing"
            logger.warning("filing parser: section %s missing", key)
            continue
        pos, end = chosen[item]
        body = text[pos:end].strip()
        if len(body) > cap_chars:
            body = body[:cap_chars] + "\n" + _TRUNCATION_MARKER
            result.section_flags[key] = "truncated"
            logger.warning("filing parser: section %s truncated", key)
        result.sections[key] = body
    return result
