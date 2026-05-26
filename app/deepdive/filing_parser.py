from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

import html2text

from app.deepdive.anchor_resolver import AnchorMatch, resolve_anchors

logger = logging.getLogger(__name__)

_FORM_ITEMS: dict[str, list[str]] = {
    "10-K": ["1", "1A", "7", "7A", "8"],
    "20-F": ["4", "5", "18"],
}
_TRUNCATION_MARKER = "[... section truncated for token budget]"
_CHARS_PER_TOKEN = 4  # heuristic cap (no Gemini call in this stage)


@dataclass
class SectionFlag:
    extraction: str        # "ok" (anchor path) | "fallback_used" (pattern path)
    missing: bool          # True when no body was extracted (absent from sections)
    truncated: bool
    anchor_id: str | None  # set for extraction == "ok" only

    def __post_init__(self) -> None:
        # ok+missing is contradictory: a section cleanly located via its anchor
        # cannot also be absent.
        assert not (self.extraction == "ok" and self.missing), (
            "SectionFlag: extraction='ok' excludes missing=True"
        )


@dataclass
class ParsedFiling:
    sections: dict[str, str] = field(default_factory=dict)
    section_flags: dict[str, SectionFlag] = field(default_factory=dict)


def _section_token_cap() -> int:
    return int(os.environ.get("FISHERSCREEN_DEEPDIVE_SECTION_TOKEN_CAP", "50000"))


def _to_text(raw: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0
    return h.handle(raw)


def parse_filing(raw_document: str, form_type: str) -> ParsedFiling:
    """Extract the target SEC items for the form type.

    Primary path: DOM-anchor tracing (resolve_anchors). Fallback: today's
    html2text pattern-matching, used for filings with no usable SEC-item
    anchor-links (e.g. ASML's iXBRL without ITEM-prefixed TOC anchors).
    """
    items = _FORM_ITEMS[form_type]
    anchors = resolve_anchors(raw_document)
    expected = {i.upper() for i in items}
    hits = [a for a in anchors if a.item_label in expected]

    if hits:
        return _extract_via_anchors(raw_document, form_type, items, anchors, hits)

    logger.warning(
        "filing parser: no SEC-item anchor-links found for %s; falling back to "
        "pattern-matching for items %s",
        form_type,
        items,
    )
    return _extract_via_pattern_fallback(raw_document, form_type, items)


def _extract_via_anchors(
    raw: str,
    form_type: str,
    items: list[str],
    all_anchors: list[AnchorMatch],
    hits: list[AnchorMatch],
) -> ParsedFiling:
    result = ParsedFiling()
    cap_chars = _section_token_cap() * _CHARS_PER_TOKEN
    hit_by_label = {h.item_label: h for h in hits}

    for item in items:
        key = f"{form_type}_item{item}"
        label = item.upper()
        if label not in hit_by_label:
            # Anchor-path partial coverage: this expected item has no anchor hit.
            # Only observed synthetically (partial-coverage wilderness). The
            # schema's only non-"ok" extraction is "fallback_used", so this
            # renders "fallback_used+missing".
            result.section_flags[key] = SectionFlag(
                extraction="fallback_used",
                missing=True,
                truncated=False,
                anchor_id=None,
            )
            logger.warning("filing parser: section %s missing (no anchor)", key)
            continue
        anchor = hit_by_label[label]
        # Next anchor in document order (any item, not just the next expected
        # item). Implements N4-decision (a) Drop: intermediate items terminate
        # the previous body and are not themselves extracted.
        next_anchor = next(
            (a for a in all_anchors if a.dom_position > anchor.dom_position),
            None,
        )
        html_slice = _slice_aligned(
            raw,
            anchor.anchor_id,
            next_anchor.anchor_id if next_anchor else None,
        )
        body = _to_text(html_slice).strip()
        truncated = False
        if len(body) > cap_chars:
            body = body[:cap_chars] + "\n" + _TRUNCATION_MARKER
            truncated = True
            logger.warning("filing parser: section %s truncated", key)
        result.sections[key] = body
        result.section_flags[key] = SectionFlag(
            extraction="ok",
            missing=False,
            truncated=truncated,
            anchor_id=anchor.anchor_id,
        )
    return result


def _slice_aligned(raw: str, anchor_a: str, anchor_b: str | None) -> str:
    """Slice raw HTML between two anchor IDs, aligned to the opening '<' of the
    containing tag. Starting mid-tag would emit a literal id="..." in the
    html2text output."""
    pa_id = raw.find(f'id="{anchor_a}"')
    if pa_id < 0:
        return ""
    tag_start = raw.rfind("<", max(0, pa_id - 200), pa_id)
    slice_start = tag_start if tag_start >= 0 else pa_id
    if anchor_b is None:
        return raw[slice_start:]
    pb_id = raw.find(f'id="{anchor_b}"')
    if pb_id < 0 or pb_id <= pa_id:
        return raw[slice_start:]
    tag_end = raw.rfind("<", max(0, pb_id - 200), pb_id)
    slice_end = tag_end if tag_end >= 0 else pb_id
    return raw[slice_start:slice_end]


# --- Fallback path: today's pattern-matching logic, bodies byte-identical. ---
#
# Known limitation: table-formatted item headings in some older filings are not
# matched (html2text renders them as table cells). DOM-aware parsing is the
# anchor path above; this fallback is for filings without usable anchor-links.
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


def _extract_via_pattern_fallback(
    raw: str, form_type: str, items: list[str]
) -> ParsedFiling:
    """Today's logic, unchanged (byte-identical bodies). Every item gets a flag
    with extraction='fallback_used'; found sections missing=False (+truncated if
    capped), not-found sections missing=True ('fallback_used+missing')."""
    text = _to_text(raw)
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
            result.section_flags[key] = SectionFlag(
                extraction="fallback_used",
                missing=True,
                truncated=False,
                anchor_id=None,
            )
            logger.warning("filing parser: section %s missing", key)
            continue

        if len(tier) > 1:
            logger.warning(
                "filing parser: section %s has %d candidate anchors — "
                "chose the first; verify in dossier",
                key,
                len(tier),
            )
        chosen[item] = tier[0]

    ordered = sorted(chosen.values())
    for item in items:
        key = f"{form_type}_item{item}"
        if item not in chosen:
            continue
        pos = chosen[item]
        later = [p for p in ordered if p > pos]
        end = later[0] if later else len(text)
        body = text[pos:end].strip()
        truncated = False
        if len(body) > cap_chars:
            body = body[:cap_chars] + "\n" + _TRUNCATION_MARKER
            truncated = True
            logger.warning("filing parser: section %s truncated", key)
        result.sections[key] = body
        result.section_flags[key] = SectionFlag(
            extraction="fallback_used",
            missing=False,
            truncated=truncated,
            anchor_id=None,
        )
    return result
