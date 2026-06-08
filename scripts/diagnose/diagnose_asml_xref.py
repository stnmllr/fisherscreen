"""Follow-up to diagnose_asml_structure.py (Punkt 5, Stage 4a).

Closes the one residual gap in the structure probe: its cross-ref detector keyed
on the literal phrase 'Item <n>', which a Form-20-F cross-reference table using
bare numbers or SEC item *titles* (no 'Item' word) would evade. Three checks on
ASML only:

  A. Total internal <a href="#"> anchors -- does ASML have ANY anchored nav,
     and what do its TOC link texts say? (PROJEKTSTAND claims only chapter
     anchors, no SEC-item anchors -- verify.)
  B. 'cross reference' / 'Form 20-F' phrasing -- is there an Item->section map?
  C. SEC item canonical titles as anchored headings -- 'Information on the
     Company' (item 4), 'Operating and Financial Review' (item 5), 'Financial
     Statements' (item 18): do they appear as headings, and are they anchor
     targets (id referenced by some #href)?

If all three are negative, ASML's SEC items are locatable only by semantic
judgement (which ASML chapter == which SEC item), not by any structural marker.
Read-only. NOT committed.
"""

from __future__ import annotations

import io
import re
import sys
import warnings
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
ASML = REPO_ROOT / "cache" / "filings" / "0000937966" / "0001628280-26-011378.txt"

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning  # noqa: E402
from bs4.element import Tag  # noqa: E402

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# SEC 20-F canonical item titles (item -> distinctive title phrase).
SEC_TITLES = {
    "4": "information on the company",
    "5": "operating and financial review",
    "18": "financial statements",
}


def hr(t: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {t}")
    print("=" * 78)


def referenced_ids(soup: BeautifulSoup) -> set[str]:
    ids: set[str] = set()
    for a in soup.find_all("a", href=True):
        h = a.get("href", "")
        if h.startswith("#"):
            ids.add(h[1:])
    return ids


def is_anchor_target(el: Tag, ref_ids: set[str]) -> str | None:
    """Return the anchored id if el or a near ancestor is an anchor target."""
    cur: object = el
    for _ in range(6):
        if not isinstance(cur, Tag):
            break
        tid = cur.get("id")
        if tid and tid in ref_ids:
            return tid
        cur = cur.parent
    return None


def main() -> None:
    raw = ASML.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml-xml")
    low = raw.lower()

    # --- A. internal anchors ------------------------------------------------
    hr("[A] INTERNAL ANCHOR INVENTORY (ASML)")
    internal = [a for a in soup.find_all("a", href=True)
                if a.get("href", "").startswith("#")]
    targets = Counter(a.get("href", "")[1:] for a in internal)
    print(f"  total internal <a href='#'> links: {len(internal)}")
    print(f"  distinct anchor targets:           {len(targets)}")
    ref_ids = set(targets)
    resolvable = sum(1 for tid in ref_ids
                     if soup.find(attrs={"id": tid}) is not None
                     or soup.find("a", attrs={"name": tid}) is not None)
    print(f"  of those, targets that resolve to a DOM id: {resolvable}")
    print("\n  sample of distinct TOC/nav link texts (first 25):")
    seen = []
    for a in internal:
        t = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        if t and t not in seen:
            seen.append(t)
        if len(seen) >= 25:
            break
    for t in seen:
        print(f"    {t[:90]!r}")

    # --- B. cross-reference phrasing ---------------------------------------
    hr("[B] 'CROSS REFERENCE' / 'FORM 20-F' PHRASING (ASML)")
    for phrase in ("cross reference", "cross-reference", "form 20-f", "20-f cross"):
        n = low.count(phrase)
        print(f"  occurrences of {phrase!r}: {n}")
        if n:
            idx = low.find(phrase)
            print(f"    first context: {raw[max(0, idx-60):idx+90]!r}")

    # --- C. SEC canonical item titles as anchored headings ------------------
    hr("[C] SEC ITEM TITLES AS ANCHORED HEADINGS (ASML)")
    for item, title in SEC_TITLES.items():
        title_re = re.compile(re.escape(title), re.IGNORECASE)
        nodes = soup.find_all(string=title_re)
        print(f"\n  item {item} title {title!r}: {len(nodes)} text node(s)")
        anchored = 0
        shown = 0
        for s in nodes:
            carrier = s.parent if isinstance(s.parent, Tag) else None
            if carrier is None:
                continue
            tid = is_anchor_target(carrier, ref_ids)
            if tid:
                anchored += 1
            if shown < 5:
                snip = re.sub(r"\s+", " ", str(s)).strip()[:70]
                style = ""
                cur: object = carrier
                for _ in range(4):
                    if isinstance(cur, Tag) and cur.get("style"):
                        style = cur.get("style", "")
                        break
                    cur = cur.parent if isinstance(cur, Tag) else None
                fw = re.search(r"font-weight:\s*([^;]+)", style)
                fs = re.search(r"font-size:\s*([^;]+)", style)
                print(f"    {snip!r:<60} weight={fw.group(1) if fw else '-'!s:<6} "
                      f"size={fs.group(1) if fs else '-'!s:<7} "
                      f"anchored={'#' + tid if tid else 'NO'}")
                shown += 1
        print(f"    -> {anchored}/{len(nodes)} occurrences are anchor targets")


if __name__ == "__main__":
    if not ASML.exists():
        print(f"MISSING: {ASML}")
        sys.exit(1)
    main()
