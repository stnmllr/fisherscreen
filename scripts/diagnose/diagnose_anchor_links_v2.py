"""V2: read-only DOM probe with tighter heading-resolution.

Improvements over v1:
  * lxml-xml parser (these are iXBRL documents, not strict HTML)
  * Don't pre-filter TOC hrefs to 'Item N' visible-text — capture ALL
    <a href="#..."> entries to see what GOOGL/ASML actually have
  * For each resolved target ID: read the next 200 chars of body text
    starting at the target element (i.e. element + following siblings).
    This handles the modern convention where <div id="..."> is empty
    and the heading sits in the immediately following element.
  * Classify each resolved target as 'heading-like' (next-text starts
    with 'Item N' / number-then-uppercase-words) or not.

NO production code is modified. NO cache files are written.
"""

from __future__ import annotations

import io
import re
import sys
import warnings
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning  # noqa: E402
from bs4.element import Tag  # noqa: E402

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

CACHE = Path(__file__).resolve().parents[1] / "cache" / "filings"

TARGETS = [
    ("GOOGL 10-K", "10-K", CACHE / "0001652044" / "0001652044-26-000018.txt"),
    ("KO 10-K",    "10-K", CACHE / "0000021344" / "0001628280-26-010047.txt"),
    ("NOVO 20-F",  "20-F", CACHE / "0000353278" / "0000353278-26-000012.txt"),
    ("ASML 20-F",  "20-F", CACHE / "0000937966" / "0001628280-26-011378.txt"),
]

# Item header patterns:
#   "Item 1", "Item 1A", "ITEM 4", or bare "4. Information on the Company"
#   (ASML-style: number + uppercase title without "Item" prefix).
_ITEM_HEADING_RE = re.compile(
    r"^\s*(?:ITEM\s+)?\d+[A-Z]?\b", re.IGNORECASE
)
# Loose: any TOC link visible-text that mentions an item number — to also
# catch ASML's bare-number style if it exists.
_ITEM_TEXT_LOOSE_RE = re.compile(
    r"\b(?:ITEM\s+)?\d+[A-Z]?\.?\s+(?:[A-Z][A-Za-z]+)", re.IGNORECASE
)


def text_after_target(el: Tag | None, max_chars: int = 200) -> str:
    """Return up to max_chars of plain text starting at `el` and following
    siblings. If `el` itself has text, return that first. Otherwise advance
    forward through siblings until we accumulate something readable."""
    if el is None:
        return ""
    buf: list[str] = []
    chars = 0
    own = el.get_text(" ", strip=True) if isinstance(el, Tag) else ""
    if own:
        buf.append(own)
        chars += len(own)
    cur = el
    while chars < max_chars:
        sib = cur.find_next_sibling() if isinstance(cur, Tag) else None
        if sib is None:
            # walk up and try parent's next sibling
            parent = cur.parent if isinstance(cur, Tag) else None
            if parent is None:
                break
            cur = parent
            continue
        cur = sib
        if isinstance(cur, Tag):
            t = cur.get_text(" ", strip=True)
            if t:
                buf.append(t)
                chars += len(t) + 1
    return " ".join(buf)[:max_chars]


def find_resolution_target(soup: BeautifulSoup, tid: str) -> Tag | None:
    """Locate an element with id=tid OR an <a name=tid>."""
    el = soup.find(attrs={"id": tid})
    if el is not None:
        return el
    a = soup.find("a", attrs={"name": tid})
    return a


def diagnose(label: str, form: str, path: Path) -> None:
    print("\n" + "=" * 78)
    print(f"  {label}    file: {path.name}    raw: {path.stat().st_size:,} bytes")
    print("=" * 78)
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        soup = BeautifulSoup(raw, "lxml-xml")
        parser_used = "lxml-xml"
    except Exception:
        soup = BeautifulSoup(raw, "lxml")
        parser_used = "lxml"
    print(f"  parser: {parser_used}")

    all_href_anchors = soup.find_all("a", href=True)
    internal_hrefs = [
        a for a in all_href_anchors
        if a.get("href", "").startswith("#")
    ]
    print(f"\n  Total <a href='#...'> internal anchors: {len(internal_hrefs)}")

    # Of these: which have visible text mentioning an item number?
    item_text_hrefs = [
        a for a in internal_hrefs
        if _ITEM_TEXT_LOOSE_RE.search(a.get_text(" ", strip=True))
    ]
    print(f"  Of which mention an item number (loose):  {len(item_text_hrefs)}")

    # If no item-text-hrefs but many internal hrefs exist: show 5 examples
    # to understand what's going on.
    if not item_text_hrefs and internal_hrefs:
        print("\n  No item-mentioning hrefs found despite internal anchors.")
        print("  First 5 internal-href visible texts (for inspection):")
        for a in internal_hrefs[:5]:
            t = a.get_text(" ", strip=True)[:80]
            href = a.get("href", "")
            print(f"    href={href:<50} text={t!r}")

    # For item-text-hrefs: resolve and inspect resolution target
    if item_text_hrefs:
        resolved = 0
        heading_like = 0
        first_five_traces: list[str] = []
        for a in item_text_hrefs:
            tid = a.get("href", "")[1:]
            tag_text = a.get_text(" ", strip=True)
            target = find_resolution_target(soup, tid)
            if target is None:
                continue
            resolved += 1
            following = text_after_target(target, 200)
            is_heading = bool(_ITEM_HEADING_RE.match(following))
            if is_heading:
                heading_like += 1
            if len(first_five_traces) < 5:
                first_five_traces.append(
                    f"    #{tid:<40}  TOC={tag_text!r}\n"
                    f"      target tag=<{target.name}>  is_heading={is_heading}\n"
                    f"      following text: {following[:160]!r}"
                )
        print(f"\n  Resolved: {resolved}/{len(item_text_hrefs)} item-text hrefs")
        print(
            f"  Heading-like target (next-text starts 'Item N' or 'N <UPPER>'): "
            f"{heading_like}/{resolved}"
        )
        print("\n  First 5 item-text href traces (TOC -> target):")
        for trace in first_five_traces:
            print(trace)

    # Convention inspection: where do item-text hrefs land? Tag distribution.
    if item_text_hrefs:
        from collections import Counter
        conv: Counter = Counter()
        for a in item_text_hrefs:
            tid = a.get("href", "")[1:]
            target = find_resolution_target(soup, tid)
            if target is None:
                conv["UNRESOLVED"] += 1
            elif isinstance(target, Tag):
                conv[f"<{target.name} id=> (empty-anchor pattern)" if not target.get_text(strip=True) else f"<{target.name} id=> (text-bearing)"] += 1
            else:
                conv["other"] += 1
        print(f"\n  Convention (item-text hrefs by target carrier):")
        for kind, n in conv.most_common():
            print(f"    {kind:<48}  {n}")


if __name__ == "__main__":
    for label, form, path in TARGETS:
        if not path.exists():
            print(f"\nMISSING: {label} -> {path}")
            continue
        diagnose(label, form, path)
