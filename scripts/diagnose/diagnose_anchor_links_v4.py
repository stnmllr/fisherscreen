"""V4: target-side classification — answer the only question that matters.

For each filing: of the resolved internal anchors, how many land on body
text that BEGINS with 'ITEM N' (the real section heading we need)?
This sidesteps the TOC-link-text variability (GOOGL labels by title
only, KO labels by 'Item N. Title', NOVO labels by 'ITEM N Title').

Additionally for ASML: explicit search for whether the SEC 20-F items
(4, 5, 18) have ANY anchor target whose body text starts with 'Item 4'
or 'Item 5' or 'Item 18'.

Read-only. No production code change.
"""

from __future__ import annotations

import io
import re
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning  # noqa: E402
from bs4.element import Tag  # noqa: E402

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

CACHE = Path(__file__).resolve().parents[1] / "cache" / "filings"

TARGETS = [
    ("GOOGL 10-K", "10-K", CACHE / "0001652044" / "0001652044-26-000018.txt",
     ["1", "1A", "7", "7A", "8"]),
    ("KO 10-K",    "10-K", CACHE / "0000021344" / "0001628280-26-010047.txt",
     ["1", "1A", "7", "7A", "8"]),
    ("NOVO 20-F",  "20-F", CACHE / "0000353278" / "0000353278-26-000012.txt",
     ["4", "5", "18"]),
    ("ASML 20-F",  "20-F", CACHE / "0000937966" / "0001628280-26-011378.txt",
     ["4", "5", "18"]),
]


def text_after(el: Tag | None, max_chars: int = 200) -> str:
    if el is None:
        return ""
    buf: list[str] = []
    chars = 0
    own = el.get_text(" ", strip=True)
    if own:
        buf.append(own)
        chars += len(own)
    cur = el
    while chars < max_chars:
        sib = cur.find_next_sibling() if isinstance(cur, Tag) else None
        if sib is None:
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


def find_target(soup: BeautifulSoup, tid: str) -> Tag | None:
    el = soup.find(attrs={"id": tid})
    if el is not None:
        return el
    return soup.find("a", attrs={"name": tid})


def diagnose(label: str, form: str, path: Path, expected_items: list[str]) -> None:
    print("\n" + "=" * 78)
    print(f"  {label}    expected items needed: {expected_items}")
    print("=" * 78)
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml-xml")

    # All distinct internal hrefs
    by_href: dict[str, list[str]] = defaultdict(list)
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if href.startswith("#"):
            txt = a.get_text(" ", strip=True)
            if txt:
                by_href[href[1:]].append(txt)

    # For each href: target + next-text
    target_classification: list[tuple[str, str, str]] = []
    for tid, fragments in by_href.items():
        toc_text = " ".join(fragments)
        target = find_target(soup, tid)
        if target is None:
            continue
        next_text = text_after(target, 200)
        target_classification.append((tid, toc_text, next_text))

    print(f"\n  Distinct internal hrefs that resolve: {len(target_classification)}")

    # Per expected item: find ANY resolved target whose next-text begins with
    # "Item {N}" or "ITEM {N}" (with optional letter suffix, with various
    # whitespace conventions).
    print(f"\n  Per-item resolution attempt (target next-text starts with 'Item {{N}}'):")
    coverage: dict[str, str] = {}
    for item in expected_items:
        # \s in regex matches \xa0 too in Python
        pat = re.compile(
            rf"^\s*ITEM\s+{re.escape(item)}(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        hits = [
            (tid, toc, nxt)
            for (tid, toc, nxt) in target_classification
            if pat.search(nxt)
        ]
        if hits:
            tid, toc, nxt = hits[0]
            coverage[item] = "YES"
            print(f"    item {item:<3}: FOUND target #{tid}")
            print(f"             TOC text fragments: {toc[:80]!r}")
            print(f"             target next-text:   {nxt[:160]!r}")
            if len(hits) > 1:
                print(f"             (... {len(hits) - 1} additional matching targets)")
        else:
            coverage[item] = "no"
            print(f"    item {item:<3}: NOT FOUND in any resolved anchor target")

    yes = sum(1 for v in coverage.values() if v == "YES")
    print(f"\n  Per-item coverage summary: {yes}/{len(expected_items)} items have a usable anchor")

    # Convention sample for items that did resolve
    found_targets: Counter = Counter()
    for item in expected_items:
        if coverage[item] != "YES":
            continue
        pat = re.compile(
            rf"^\s*ITEM\s+{re.escape(item)}(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        for tid, toc, nxt in target_classification:
            if pat.search(nxt):
                target = find_target(soup, tid)
                if isinstance(target, Tag):
                    empty = not target.get_text(strip=True)
                    found_targets[
                        f"<{target.name}> {'(empty anchor)' if empty else '(text-bearing)'}"
                    ] += 1
                break
    if found_targets:
        print(f"\n  Carrier convention for found anchors:")
        for k, n in found_targets.most_common():
            print(f"    {k:<48}  {n}")


if __name__ == "__main__":
    for label, form, path, items in TARGETS:
        if not path.exists():
            print(f"\nMISSING: {label} -> {path}")
            continue
        diagnose(label, form, path, items)
