"""Read-only DOM probe: are TOC anchor-links present + integral in the cache?

For each cache filing:
  * count TOC anchor-link entries that point at "Item N" / "ITEM N"
  * count body anchor targets (<a name="..."> + id="..." on heading elements)
  * resolve each TOC href against the body target IDs -> match rate
  * report orphan TOC hrefs (point at nothing) and orphan body targets
  * describe the convention used per filing (which tag carries the ID,
    where the href points, etc.)

NO production code is modified. NO cache files are written.
"""

from __future__ import annotations

import io
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from bs4 import BeautifulSoup, Tag  # noqa: E402

CACHE = Path(__file__).resolve().parents[1] / "cache" / "filings"

TARGETS = [
    ("GOOGL 10-K", "10-K", CACHE / "0001652044" / "0001652044-26-000018.txt"),
    ("KO 10-K", "10-K", CACHE / "0000021344" / "0001628280-26-010047.txt"),
    ("NOVO 20-F", "20-F", CACHE / "0000353278" / "0000353278-26-000012.txt"),
    ("ASML 20-F", "20-F", CACHE / "0000937966" / "0001628280-26-011378.txt"),
]

# Heuristic: a TOC link is an <a href="#xxx"> whose visible text mentions
# "Item N" / "ITEM N" with a digit (and optional letter suffix like 1A).
_ITEM_TEXT_RE = re.compile(r"\bITEM\s+\d+[A-Z]?\b", re.IGNORECASE)
# A heading-like element is anything whose plain text starts with "Item N" or
# is short and contains "Item N" as a likely header (not a body sentence).
_ITEM_HEADING_TEXT_RE = re.compile(r"^\s*ITEM\s+\d+[A-Z]?\b", re.IGNORECASE)


def collect_toc_hrefs(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Return [(href_target_id, link_text), ...] for <a href="#...">Item N...</a>."""
    out: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not href.startswith("#"):
            continue
        text = a.get_text(" ", strip=True)
        if not _ITEM_TEXT_RE.search(text):
            continue
        target = href[1:]  # strip leading '#'
        out.append((target, text))
    return out


def collect_body_targets(soup: BeautifulSoup) -> dict[str, str]:
    """Return {target_id: short_excerpt_of_owner_or_neighbor} for every id /
    <a name> in the document. We don't pre-filter to 'heading-like' here —
    we want to know whether the TOC href *resolves* at all."""
    out: dict[str, str] = {}
    # name= attribute on <a name="..."> (older convention)
    for a in soup.find_all("a", attrs={"name": True}):
        tid = a.get("name", "")
        if not tid:
            continue
        # Look at the parent element's text as a hint of what the anchor wraps
        parent = a.parent
        excerpt = ""
        if parent is not None:
            excerpt = parent.get_text(" ", strip=True)[:80]
        out[tid] = f"<a name>  parent_text={excerpt!r}"
    # id= attribute (modern convention)
    for el in soup.find_all(attrs={"id": True}):
        tid = el.get("id", "")
        if not tid:
            continue
        # don't overwrite an existing <a name> entry if any, but record id too
        if tid in out:
            # both conventions point at the same id -> mark
            out[tid] += "  +id_also"
            continue
        excerpt = el.get_text(" ", strip=True)[:80]
        out[tid] = f"id on <{el.name}>  text={excerpt!r}"
    return out


def heading_like_targets(targets: dict[str, str]) -> dict[str, str]:
    """Subset whose excerpt text looks like 'Item N ...' — i.e. the anchor
    appears to wrap or precede a heading."""
    out: dict[str, str] = {}
    for tid, info in targets.items():
        text_match = re.search(r"text=['\"]([^'\"]*)['\"]", info) or re.search(
            r"parent_text=['\"]([^'\"]*)['\"]", info
        )
        text = text_match.group(1) if text_match else ""
        if _ITEM_HEADING_TEXT_RE.match(text):
            out[tid] = info
    return out


def diagnose(label: str, form: str, path: Path) -> None:
    print("\n" + "=" * 78)
    print(f"  {label}    file: {path.name}    raw: {path.stat().st_size:,} bytes")
    print("=" * 78)
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml") if "lxml" in sys.modules or True else BeautifulSoup(raw, "html.parser")
    # Try lxml first; fallback to html.parser if not installed
    try:
        soup = BeautifulSoup(raw, "lxml")
        parser_used = "lxml"
    except Exception:
        soup = BeautifulSoup(raw, "html.parser")
        parser_used = "html.parser"
    print(f"  parser: {parser_used}")

    toc_hrefs = collect_toc_hrefs(soup)
    body_targets = collect_body_targets(soup)
    heading_targets = heading_like_targets(body_targets)

    print(f"\n  TOC <a href='#...'>Item N...</a> entries: {len(toc_hrefs)}")
    print(f"  Body anchor-target IDs (any tag/<a name>):  {len(body_targets)}")
    print(f"  Body anchor-targets that look heading-like: {len(heading_targets)}")

    # Sample of first 5 TOC hrefs
    print("\n  First 5 TOC entries (href -> visible text):")
    for tid, text in toc_hrefs[:5]:
        print(f"    #{tid:<40} -> {text!r}")

    # Reference integrity
    matched = [(tid, text) for (tid, text) in toc_hrefs if tid in body_targets]
    orphans = [(tid, text) for (tid, text) in toc_hrefs if tid not in body_targets]
    quote = (
        f"{len(matched)}/{len(toc_hrefs)} TOC hrefs resolved"
        + (f" ({len(matched) * 100 // max(len(toc_hrefs),1)}%)" if toc_hrefs else "")
    )
    print(f"\n  Reference integrity: {quote}")
    if orphans:
        print("  First 3 orphan TOC hrefs (no body target):")
        for tid, text in orphans[:3]:
            print(f"    #{tid:<40} -> {text!r}")

    # Of matched: how many point to a heading-like target?
    matched_to_heading = [
        (tid, text) for (tid, text) in matched if tid in heading_targets
    ]
    print(
        f"  Of matched: {len(matched_to_heading)}/{len(matched)} point at a "
        f"heading-like element (text starts with 'Item N')"
    )
    # Sample non-heading-like matches
    matched_non_heading = [
        (tid, text) for (tid, text) in matched if tid not in heading_targets
    ]
    if matched_non_heading:
        print("  First 3 matched-but-NOT-heading-like targets (TOC -> body excerpt):")
        for tid, text in matched_non_heading[:3]:
            print(f"    #{tid:<40}  TOC={text!r}")
            print(f"      body: {body_targets[tid][:140]}")

    # Convention sampling: where do the matched IDs sit?
    # Look at the parent tag types for the matched IDs.
    tag_kinds: Counter = Counter()
    name_vs_id_counter: Counter = Counter()
    for tid, _text in matched[:50]:  # sample
        info = body_targets.get(tid, "")
        if info.startswith("<a name>"):
            name_vs_id_counter["<a name>"] += 1
        else:
            name_vs_id_counter[info.split("  ")[0]] += 1  # 'id on <p>' etc.
    print(f"\n  Convention (first 50 matched targets, by carrier tag):")
    for kind, n in name_vs_id_counter.most_common():
        print(f"    {kind:<30}  {n}")


if __name__ == "__main__":
    for label, form, path in TARGETS:
        if not path.exists():
            print(f"\nMISSING: {label} -> {path}")
            continue
        diagnose(label, form, path)
