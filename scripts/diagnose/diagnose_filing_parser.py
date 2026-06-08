"""Read-only diagnostic for Punkt-5 filing-parser issues.

Loads the cached ASML 20-F + GOOGL 10-K, runs the same html2text + regexes
as app.deepdive.filing_parser, and prints empirical evidence:

  * how many line-start anchors per item
  * how many any-position anchors per item
  * the 200-char window around each candidate
  * what text precedes "missing" items (so we can see why no anchor matched)

No production code is modified. No fix is proposed. Output is read by humans.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Import the production parser so we look at the SAME regexes.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.deepdive.filing_parser import (  # noqa: E402
    _FORM_ITEMS,
    _anypos_re,
    _linestart_re,
    _to_text,
    _toc_re,
)

CACHE_ROOT = Path(__file__).resolve().parents[1] / "cache" / "filings"

TARGETS = [
    ("GOOGL 10-K", "10-K", CACHE_ROOT / "0001652044" / "0001652044-26-000018.txt"),
    ("KO 10-K",    "10-K", CACHE_ROOT / "0000021344" / "0001628280-26-010047.txt"),
    ("ASML 20-F",  "20-F", CACHE_ROOT / "0000937966" / "0001628280-26-011378.txt"),
    ("NOVO 20-F",  "20-F", CACHE_ROOT / "0000353278" / "0000353278-26-000012.txt"),
]


def show_candidates(text: str, form_type: str, item: str, max_show: int = 8) -> None:
    toc = _toc_re(item)
    linestart_all = list(_linestart_re(item).finditer(text))
    anypos_all = list(_anypos_re(item).finditer(text))

    linestart_after_toc = [
        m for m in linestart_all if not toc.match(text[m.start() : m.start() + 80])
    ]
    anypos_after_toc = [
        m for m in anypos_all if not toc.match(text[m.start() : m.start() + 80])
    ]

    print(f"\n  --- item {item} ---")
    print(
        f"    line-start hits: {len(linestart_all)} total, "
        f"{len(linestart_after_toc)} after TOC-filter"
    )
    print(
        f"    any-pos hits:    {len(anypos_all)} total, "
        f"{len(anypos_after_toc)} after TOC-filter"
    )

    candidates = linestart_after_toc if linestart_after_toc else anypos_after_toc
    used_tier = "line-start" if linestart_after_toc else "any-pos fallback"
    print(f"    tier used: {used_tier}, kept candidates: {len(candidates)}")

    if not candidates:
        # Show raw line-starts before TOC filter (so we see what html2text
        # produced where item should be).
        if linestart_all:
            print("    (line-start matches BEFORE TOC filter:)")
            for m in linestart_all[:max_show]:
                snip = text[m.start() : m.start() + 120].replace("\n", "\\n")
                print(f"      pos={m.start():>8} -> {snip!r}")
        if anypos_all:
            print("    (any-pos matches BEFORE TOC filter, first 5:)")
            for m in anypos_all[:5]:
                snip = text[m.start() : m.start() + 120].replace("\n", "\\n")
                print(f"      pos={m.start():>8} -> {snip!r}")
        if not linestart_all and not anypos_all:
            # truly nothing matches — try to find ANY mention of "Item N" w/o regex
            naive = list(
                re.finditer(rf"item\s+{re.escape(item)}", text, re.IGNORECASE)
            )
            print(
                f"    naive case-insensitive 'item {item}' anywhere: {len(naive)}"
            )
            for m in naive[:5]:
                snip = text[m.start() : m.start() + 120].replace("\n", "\\n")
                print(f"      pos={m.start():>8} -> {snip!r}")
    else:
        for m in candidates[:max_show]:
            snip = text[m.start() : m.start() + 120].replace("\n", "\\n")
            print(f"      pos={m.start():>8} -> {snip!r}")
        if len(candidates) > max_show:
            print(f"      ... ({len(candidates) - max_show} more)")


def diagnose(label: str, form_type: str, path: Path) -> None:
    print("\n" + "=" * 78)
    print(f"  {label}    file: {path.name}    raw bytes: {path.stat().st_size:,}")
    print("=" * 78)
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = _to_text(raw)
    print(
        f"  after html2text: {len(text):,} chars  "
        f"({len(text.splitlines()):,} lines)"
    )
    for item in _FORM_ITEMS[form_type]:
        show_candidates(text, form_type, item)


if __name__ == "__main__":
    for label, form, path in TARGETS:
        if not path.exists():
            print(f"  MISSING: {label} -> {path}")
            continue
        diagnose(label, form, path)
