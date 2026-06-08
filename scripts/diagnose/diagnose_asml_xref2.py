"""Final micro-probe (Punkt 5, Stage 4a) -- the pivotal question.

ASML HAS a 'Form 20-F cross reference table' (confirmed by diagnose_asml_xref.py:
25x 'form 20-f', explicit 'Reference is made to the Form 20-F cross reference
table above'). The table maps SEC items -> ASML content by *title*. The single
question that decides the Stage-4 gate: does the cross-ref-table ROW for an SEC
item carry an <a href='#...'> (e.g. on a page number) that lands on the body
section? If yes -> a usable marker may exist (-> 4b). If no -> the table maps to
page numbers only, unusable for DOM-anchor-tracing -> honest 'no marker'.

For the item-4 and item-5 title nodes: dump the enclosing row/table, every
<a href> in that row (internal + external), and where internal ones land.

Read-only. NOT committed.
"""

from __future__ import annotations

import io
import re
import sys
import warnings
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
ASML = REPO_ROOT / "cache" / "filings" / "0000937966" / "0001628280-26-011378.txt"

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning  # noqa: E402
from bs4.element import Tag  # noqa: E402

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

PHRASES = {
    "4": "information on the company",
    "5": "operating and financial review and prospects",
}


def text_after_id(soup: BeautifulSoup, tid: str, max_chars: int = 140) -> str:
    target = soup.find(attrs={"id": tid}) or soup.find("a", attrs={"name": tid})
    if target is None:
        return "<id not found>"
    txt = target.get_text(" ", strip=True) if isinstance(target, Tag) else ""
    cur: object = target
    while len(txt) < max_chars and isinstance(cur, Tag):
        sib = cur.find_next_sibling()
        if sib is None:
            cur = cur.parent
            continue
        cur = sib
        if isinstance(cur, Tag):
            t = cur.get_text(" ", strip=True)
            if t:
                txt = (txt + " " + t) if txt else t
    return re.sub(r"\s+", " ", txt)[:max_chars]


def ancestor(el: Tag, *names: str) -> Tag | None:
    cur: object = el.parent
    for _ in range(12):
        if not isinstance(cur, Tag):
            return None
        if cur.name in names:
            return cur
        cur = cur.parent
    return None


def main() -> None:
    raw = ASML.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml-xml")

    for item, phrase in PHRASES.items():
        print("\n" + "=" * 78)
        print(f"  ITEM {item}: '{phrase}'")
        print("=" * 78)
        node = soup.find(string=re.compile(re.escape(phrase), re.IGNORECASE))
        if node is None:
            print("  not found")
            continue
        carrier = node.parent if isinstance(node.parent, Tag) else None
        if carrier is None:
            print("  no carrier tag")
            continue

        row = ancestor(carrier, "tr")
        table = ancestor(carrier, "table")
        scope = row or table or carrier
        scope_name = "tr" if row else ("table" if table else carrier.name)
        print(f"  carrier: <{carrier.name}> style={carrier.get('style', '')[:80]!r}")
        print(f"  enclosing scope: <{scope_name}>")
        print(f"  scope text: {re.sub(r'%s' % chr(92) + 's+', ' ', scope.get_text(' ', strip=True))[:200]!r}")

        anchors = scope.find_all("a", href=True)
        internal = [a for a in anchors if a.get("href", "").startswith("#")]
        external = [a for a in anchors if not a.get("href", "").startswith("#")]
        print(f"  <a href> in scope: {len(anchors)} "
              f"({len(internal)} internal, {len(external)} external)")
        for a in internal[:6]:
            href = a.get("href", "")
            atext = re.sub(r"\s+", " ", a.get_text(" ", strip=True))[:30]
            lands = text_after_id(soup, href[1:], 120)
            print(f"    internal {href!r} (link text {atext!r})")
            print(f"      lands on: {lands!r}")
        for a in external[:4]:
            print(f"    external {a.get('href')!r} text={a.get_text(' ', strip=True)[:40]!r}")
        if not anchors:
            print("  -> NO <a href> anywhere in the enclosing row/table")

        # Is this table the Form 20-F cross-ref table?
        if table is not None:
            ttxt = table.get_text(" ", strip=True).lower()
            other_titles = sum(t in ttxt for t in (
                "risk factors", "legal proceedings", "quantitative and qualitative",
                "financial statements", "directors, senior management"))
            print(f"  enclosing <table> contains {other_titles} other SEC-item titles "
                  f"(>=3 => this is the Form-20-F cross-ref table)")


if __name__ == "__main__":
    if not ASML.exists():
        print(f"MISSING: {ASML}")
        sys.exit(1)
    main()
