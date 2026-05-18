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


# Known limitation: table-formatted item headings in some older filings are not
# matched (html2text renders them as table cells). DOM-aware parsing is a B.2
# refactor (spec E1).
def _linestart_re(item: str) -> re.Pattern[str]:
    # A genuine item heading starts a line (filings put headings in their own
    # block; html2text renders that as a line start). Mid-sentence cross-
    # references ("as discussed in Item 5 above") are NOT line-start, so this
    # filters them out. \b stops "1" matching inside "1A" and "7" inside "7A".
    return re.compile(
        rf"^[ \t]*ITEM\s+{re.escape(item)}\b\s*[.:\-—]?",
        re.IGNORECASE | re.MULTILINE,
    )


def _anypos_re(item: str) -> re.Pattern[str]:
    return re.compile(rf"\bITEM\s+{re.escape(item)}\b\s*[.:\-—]?", re.IGNORECASE)


def _toc_re(item: str) -> re.Pattern[str]:
    # Table-of-contents entry: "Item 5 ........ 42" — anchor, a dotted leader
    # (>=2 literal dots), then a 1-4 digit page number. Requiring real dots
    # avoids misflagging a heading whose body starts with a number
    # ("Item 7. 2023 was a strong year").
    return re.compile(
        rf"ITEM\s+{re.escape(item)}\b[ \t]*\.{{2,}}[ .\t]*\d{{1,4}}\b",
        re.IGNORECASE,
    )


def parse_filing(raw_document: str, form_type: str) -> ParsedFiling:
    items = _FORM_ITEMS[form_type]
    text = _to_text(raw_document)
    cap_chars = _section_token_cap() * _CHARS_PER_TOKEN
    result = ParsedFiling()

    chosen: dict[str, int] = {}
    for item in items:
        key = f"{form_type}_item{item}"
        toc = _toc_re(item)

        linestarts = [
            m.start()
            for m in _linestart_re(item).finditer(text)
            if not toc.match(text[m.start() : m.start() + 80])
        ]
        if linestarts:
            tier = linestarts
        else:
            tier = [
                m.start()
                for m in _anypos_re(item).finditer(text)
                if not toc.match(text[m.start() : m.start() + 80])
            ]

        if not tier:
            result.section_flags[key] = "missing"
            logger.warning("filing parser: section %s missing", key)
            continue

        if len(tier) > 1:
            result.section_flags[key] = "ambiguous"
            logger.warning(
                "filing parser: section %s has %d candidate anchors — "
                "chose the first; verify in dossier",
                key,
                len(tier),
            )
        chosen[item] = tier[0]

    if not chosen:
        return result

    ordered = sorted(chosen.values())
    for item in items:
        key = f"{form_type}_item{item}"
        if item not in chosen:
            continue
        pos = chosen[item]
        later = [p for p in ordered if p > pos]
        end = later[0] if later else len(text)
        body = text[pos:end].strip()
        if len(body) > cap_chars:
            body = body[:cap_chars] + "\n" + _TRUNCATION_MARKER
            result.section_flags[key] = "truncated"  # truncated is the actionable flag
            logger.warning("filing parser: section %s truncated", key)
        result.sections[key] = body
    return result
