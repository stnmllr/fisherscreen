"""V3: aggregate internal-anchor hrefs and classify by RESOLUTION TARGET.

Lesson from v2:
  * TOC entries are split into multiple parallel <a href="#X"> tags
    (one for the item number, one for the title, one for the page).
    Aggregate by href; combined visible text is the row label.
  * For ASML, the main TOC may use a totally different convention.
    Classify ALL internal hrefs by what their RESOLUTION TARGET looks
    like — don't filter by TOC-link text.

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
    ("GOOGL 10-K", "10-K", CACHE / "0001652044" / "0001652044-26-000018.txt"),
    ("KO 10-K",    "10-K", CACHE / "0000021344" / "0001628280-26-010047.txt"),
    ("NOVO 20-F",  "20-F", CACHE / "0000353278" / "0000353278-26-000012.txt"),
    ("ASML 20-F",  "20-F", CACHE / "0000937966" / "0001628280-26-011378.txt"),
]

_ITEM_HEADING_RE = re.compile(r"^\s*(?:ITEM\s+)?\d+[A-Z]?\b", re.IGNORECASE)


def text_after_target(el: Tag | None, max_chars: int = 250) -> str:
    """Read forward from el (own text + following siblings + parent's next
    sibling chain) until we accumulate max_chars of text."""
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
    soup = BeautifulSoup(raw, "lxml-xml")

    # 1) Aggregate internal anchors by href target
    by_href: dict[str, list[str]] = defaultdict(list)
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not href.startswith("#"):
            continue
        text = a.get_text(" ", strip=True)
        if text:
            by_href[href[1:]].append(text)

    print(f"\n  Distinct internal-anchor hrefs: {len(by_href)}")

    # 2) For each href: combined text; classify resolution target
    resolved_count = 0
    aggregated: list[tuple[str, str, Tag | None]] = []
    for tid, fragments in by_href.items():
        combined = " ".join(fragments)
        target = find_resolution_target(soup, tid)
        if target is not None:
            resolved_count += 1
        aggregated.append((tid, combined, target))

    print(f"  Of which resolve to a target ID/<a name>: {resolved_count}/{len(by_href)}")

    # 3) Item-relevant hrefs: combined text mentions "Item N" or "ITEM N"
    item_re = re.compile(r"\b(?:ITEM\s+)?\d+[A-Z]?\b", re.IGNORECASE)
    item_hrefs = [
        (tid, combined, target)
        for (tid, combined, target) in aggregated
        if (
            "item" in combined.lower()
            or _ITEM_HEADING_RE.match(combined)
        )
    ]
    print(f"\n  Item-relevant hrefs (TOC text mentions 'Item' or item-no): "
          f"{len(item_hrefs)}")

    # Show first 8 item-relevant TOC rows
    print(f"\n  First 8 item-relevant TOC rows:")
    for tid, combined, target in item_hrefs[:8]:
        target_kind = "MISSING" if target is None else f"<{target.name}>"
        print(f"    #{tid:<42}  text={combined[:80]!r:<82}  -> {target_kind}")

    # 4) Resolution + heading-likeness for item-relevant
    res_count = 0
    heading_like = 0
    traces: list[str] = []
    for tid, combined, target in item_hrefs:
        if target is None:
            continue
        res_count += 1
        following = text_after_target(target, 250)
        is_heading = bool(_ITEM_HEADING_RE.match(following))
        if is_heading:
            heading_like += 1
        if len(traces) < 6:
            traces.append(
                f"    #{tid:<42}  TOC text: {combined[:70]!r}\n"
                f"      target=<{target.name}>  is_heading={is_heading}\n"
                f"      next-text: {following[:170]!r}"
            )
    print(f"\n  Resolution: {res_count}/{len(item_hrefs)} item-relevant TOC rows "
          f"land on a target.")
    print(f"  Of those: {heading_like}/{res_count} point at heading-like content "
          f"('Item N ...' or 'N. <UPPER>...')")
    print("\n  First 6 item-relevant traces (TOC -> target -> next-text):")
    for trace in traces:
        print(trace)

    # 5) Convention summary: target tag kind for item-relevant resolved
    conv: Counter = Counter()
    for tid, combined, target in item_hrefs:
        if target is None:
            conv["UNRESOLVED"] += 1
        elif isinstance(target, Tag):
            empty = not target.get_text(strip=True)
            conv[f"<{target.name} id=> ({'empty-anchor' if empty else 'text-bearing'})"] += 1
    print(f"\n  Convention (item-relevant hrefs by target carrier):")
    for kind, n in conv.most_common():
        print(f"    {kind:<48}  {n}")


if __name__ == "__main__":
    for label, form, path in TARGETS:
        if not path.exists():
            print(f"\nMISSING: {label} -> {path}")
            continue
        diagnose(label, form, path)
