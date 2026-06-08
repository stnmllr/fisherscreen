"""Read-only structural-marker investigation for ASML 20-F (Punkt 5, Stage 4a).

Background: under the Stage-1 anchor resolver (app/deepdive/anchor_resolver.py),
ASML's SEC items 4/5/18 have 0 usable TOC-anchor coverage -- no <a href="#id">
whose target body text starts with "ITEM N". The prior probe
(diagnose_anchor_links_v4.py) keyed on "target text starts with ITEM N" and
therefore could only see hypothesis 0. This script asks the Stage-4 question:
does ANY OTHER structural marker let us *unambiguously* locate the start of
SEC item 4, 5, or 18?

Hypotheses tested (Stage-4 plan + one the prior anchor probe structurally
could not see):
  0. Anchor baseline   -- reproduce the 0/3 finding via production resolve_anchors
                          (NOVO 20-F as working control)
  X. Cross-ref table   -- Form-20-F cross-reference table whose Item rows carry
                          <a href="#..."> to ASML's own chapters (target heading
                          is the chapter title, NOT "ITEM N" -> invisible to the
                          Stage-1 resolver). THE key remaining hypothesis.
  1. CSS classes       -- heading-like class on the Item-N carrier element
  2. XBRL tags         -- ix:nonNumeric / ix:nonFraction concept tagging a section
  3. Inline styling    -- font-weight / font-size distinguishing the Item-N heading
  4. HTML5 headings    -- <h1>..<h6>
  5. Tables / thead    -- table structure around Item-N

A marker is USABLE only if it (a) matches item 4, 5, or 18 AND (b) is specific
enough that it does not also fire on dozens of unrelated places (else it cannot
bound a section). "Several hypotheses, none unambiguous" and "no marker" are
both legitimate Stage-4 outcomes -- this script does not invent one.

Read-only. No production code modified. Output read by humans. NOT committed.
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
sys.path.insert(0, str(REPO_ROOT))

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning  # noqa: E402
from bs4.element import Tag  # noqa: E402

from app.deepdive.anchor_resolver import resolve_anchors  # noqa: E402

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

CACHE = REPO_ROOT / "cache" / "filings"
ASML = CACHE / "0000937966" / "0001628280-26-011378.txt"
NOVO = CACHE / "0000353278" / "0000353278-26-000012.txt"

TARGET_ITEMS = ["4", "5", "18"]

# Heading candidate: a text node that *begins* with "Item N" (the real heading
# we would need). \b after the number rejects "Item 4A", "Item 50", "Item 180".
ITEM_START_RE = re.compile(r"^\s*item\s+(4|5|18)\b", re.IGNORECASE)
# Any mention anywhere (to characterise references vs headings).
ITEM_ANY_RE = re.compile(r"\bitem\s+(4|5|18)\b", re.IGNORECASE)
# Any "Item <number>" at all -- to locate the cross-reference table.
ITEM_GENERIC_RE = re.compile(r"\bitem\s+\d+", re.IGNORECASE)


def describe(el: object) -> str:
    if not isinstance(el, Tag):
        return repr(el)[:80]
    parts = [f"<{el.name}"]
    tid = el.get("id")
    if tid:
        parts.append(f" id={tid!r}")
    cls = el.get("class")
    if cls:
        parts.append(f" class={cls!r}")
    style = el.get("style")
    if style:
        parts.append(f" style={style[:90]!r}")
    parts.append(">")
    return "".join(parts)


def ancestor_chain(el: Tag, depth: int = 4) -> str:
    chain = []
    cur: object = el
    for _ in range(depth):
        if not isinstance(cur, Tag):
            break
        chain.append(describe(cur))
        cur = cur.parent
    return "  >  ".join(chain)


def nearest_row(el: Tag) -> tuple[str, list[str], str]:
    """Walk up to the nearest <tr>/<table>; return (tag, internal #hrefs, text)."""
    cur: object = el
    for _ in range(10):
        cur = cur.parent if isinstance(cur, Tag) else None
        if cur is None:
            break
        if cur.name in ("tr", "table"):
            hrefs = [
                a.get("href", "")
                for a in cur.find_all("a", href=True)
                if a.get("href", "").startswith("#")
            ]
            return cur.name, hrefs, cur.get_text(" ", strip=True)[:240]
    return "", [], ""


def text_after_id(soup: BeautifulSoup, tid: str, max_chars: int = 160) -> str:
    target = soup.find(attrs={"id": tid}) or soup.find("a", attrs={"name": tid})
    if target is None:
        return "<target id not found>"
    buf: list[str] = []
    chars = 0
    cur: object = target
    own = target.get_text(" ", strip=True) if isinstance(target, Tag) else ""
    if own:
        buf.append(own)
        chars += len(own)
    while chars < max_chars and isinstance(cur, Tag):
        sib = cur.find_next_sibling()
        if sib is None:
            cur = cur.parent
            continue
        cur = sib
        if isinstance(cur, Tag):
            t = cur.get_text(" ", strip=True)
            if t:
                buf.append(t)
                chars += len(t) + 1
    return " ".join(buf)[:max_chars]


def hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


# ---------------------------------------------------------------------------

def section0_anchor_baseline(label: str, raw: str) -> None:
    hr(f"[0] ANCHOR BASELINE (production resolve_anchors) -- {label}")
    matches = resolve_anchors(raw)
    by_item = {m.item_label: m for m in matches}
    print(f"  total anchor-matches in filing: {len(matches)}")
    print(f"  distinct item labels matched:   "
          f"{sorted({m.item_label for m in matches}, key=lambda x: (len(x), x))}")
    print(f"\n  target items {TARGET_ITEMS}:")
    for item in TARGET_ITEMS:
        m = by_item.get(item)
        if m:
            print(f"    item {item:<3}: COVERED  anchor_id={m.anchor_id!r} "
                  f"pos={m.dom_position}")
            print(f"             excerpt: {m.next_text_excerpt[:120]!r}")
        else:
            print(f"    item {item:<3}: NOT covered by any anchor-match")


def sectionX_crossref(label: str, soup: BeautifulSoup) -> None:
    hr(f"[X] CROSS-REFERENCE TABLE + ITEM-HEADING HUNT -- {label}")

    starts = soup.find_all(string=ITEM_START_RE)
    anys = soup.find_all(string=ITEM_ANY_RE)
    print(f"  text nodes STARTING with 'Item 4/5/18': {len(starts)}")
    print(f"  text nodes mentioning 'Item 4/5/18' anywhere: {len(anys)}")

    # Locate the cross-reference table: a <table> with >=3 generic "Item N".
    tables = soup.find_all("table")
    print(f"  total <table> elements: {len(tables)}")
    xref_tables = []
    for t in tables:
        txt = t.get_text(" ", strip=True)
        items_in_table = {m.group(0).lower() for m in ITEM_GENERIC_RE.finditer(txt)}
        if len(items_in_table) >= 5:
            xref_tables.append((t, len(items_in_table)))
    print(f"  candidate cross-ref tables (>=5 distinct 'Item N'): {len(xref_tables)}")
    for t, n in xref_tables[:3]:
        internal = [a.get("href", "") for a in t.find_all("a", href=True)
                    if a.get("href", "").startswith("#")]
        print(f"    table with {n} distinct items, {len(internal)} internal #-anchors"
              f"  {describe(t)}")
        if internal:
            print(f"      sample hrefs: {internal[:5]}")

    # Per target item: every text node starting with 'Item N', its carrier and row.
    for item in TARGET_ITEMS:
        pat = re.compile(rf"^\s*item\s+{item}\b", re.IGNORECASE)
        hits = [s for s in starts if pat.match(str(s))]
        print(f"\n  --- item {item}: {len(hits)} heading-like text node(s) ---")
        for s in hits[:6]:
            carrier = s.parent if isinstance(s.parent, Tag) else None
            snippet = re.sub(r"\s+", " ", str(s)).strip()[:70]
            print(f"    text={snippet!r}")
            if carrier is not None:
                print(f"      carrier chain: {ancestor_chain(carrier, 3)}")
                in_link = carrier.find_parent("a", href=True)
                if in_link is not None:
                    print(f"      INSIDE <a href={in_link.get('href')!r}>")
                row_tag, row_hrefs, row_text = nearest_row(carrier)
                if row_tag:
                    print(f"      nearest <{row_tag}> internal-anchors={row_hrefs[:4]}")
                    print(f"      row text: {row_text[:150]!r}")
                    for h in row_hrefs[:2]:
                        if h.startswith("#"):
                            tgt = text_after_id(soup, h[1:], 120)
                            print(f"        -> href {h} target lands on: {tgt!r}")
        if len(hits) > 6:
            print(f"    ... ({len(hits) - 6} more)")


def section1_css(label: str, soup: BeautifulSoup) -> None:
    hr(f"[1] CSS-CLASS marker hypothesis -- {label}")
    classes: Counter = Counter()
    for el in soup.find_all(class_=True):
        cls = el.get("class")
        if isinstance(cls, list):
            for c in cls:
                classes[c] += 1
        elif cls:
            classes[cls] += 1
    print(f"  distinct class values: {len(classes)}")
    heading_like = [(c, n) for c, n in classes.items()
                    if re.search(r"hdg|head|title|section|chapter|item|h[1-6]\b",
                                 c, re.IGNORECASE)]
    if heading_like:
        print(f"  heading-suggestive class names ({len(heading_like)}):")
        for c, n in sorted(heading_like, key=lambda x: -x[1])[:15]:
            print(f"    {c!r:<40} x{n}")
    else:
        print("  no class names matching hdg/head/title/section/chapter/item/h1-6")
    print(f"  top-10 classes overall: {classes.most_common(10)}")


def section2_xbrl(label: str, soup: BeautifulSoup) -> None:
    hr(f"[2] XBRL-TAG marker hypothesis -- {label}")
    ix = soup.find_all(lambda t: isinstance(t, Tag)
                       and t.name.lower() in ("nonnumeric", "nonfraction"))
    print(f"  ix:nonNumeric/nonFraction elements: {len(ix)}")
    names: Counter = Counter()
    asml_custom = []
    for el in ix:
        nm = el.get("name", "")
        names[nm] += 1
        if nm.lower().startswith("asml"):
            asml_custom.append(nm)
        # does any ix tag *wrap* an "Item 4/5/18" heading?
        if ITEM_START_RE.match(el.get_text(" ", strip=True)):
            print(f"  !! ix tag wraps Item heading: name={nm!r} "
                  f"text={el.get_text(' ', strip=True)[:60]!r}")
    print(f"  distinct concept names: {len(names)}")
    print(f"  custom asml:* concepts: {len(set(asml_custom))} "
          f"{sorted(set(asml_custom))[:8]}")
    section_like = [(n, c) for n, c in names.items()
                    if re.search(r"item|section|heading", n, re.IGNORECASE)]
    print(f"  section/item-like concept names: {section_like[:10] or 'none'}")


def section3_inline_style(label: str, soup: BeautifulSoup) -> None:
    hr(f"[3] INLINE-STYLE marker hypothesis -- {label}")
    starts = soup.find_all(string=ITEM_START_RE)
    print(f"  inspecting style of {min(len(starts), 8)} Item-N heading carriers:")
    seen = 0
    for s in starts:
        carrier = s.parent if isinstance(s.parent, Tag) else None
        if carrier is None:
            continue
        # climb to nearest styled ancestor
        styled = carrier
        for _ in range(4):
            if isinstance(styled, Tag) and styled.get("style"):
                break
            styled = styled.parent if isinstance(styled, Tag) else carrier
        style = styled.get("style", "") if isinstance(styled, Tag) else ""
        fw = re.search(r"font-weight:\s*([^;]+)", style)
        fs = re.search(r"font-size:\s*([^;]+)", style)
        print(f"    {str(s).strip()[:40]!r:<44} "
              f"weight={fw.group(1) if fw else '-'!s:<8} "
              f"size={fs.group(1) if fs else '-'}")
        seen += 1
        if seen >= 8:
            break


def section4_html5(label: str, soup: BeautifulSoup) -> None:
    hr(f"[4] HTML5-HEADING hypothesis -- {label}")
    h = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    print(f"  <h1>..<h6> elements: {len(h)}")
    for el in h[:8]:
        print(f"    <{el.name}> {el.get_text(' ', strip=True)[:70]!r}")


def run(label: str, path: Path) -> None:
    print("\n\n" + "#" * 78)
    print(f"#  {label}   ({path.stat().st_size:,} bytes)")
    print("#" * 78)
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml-xml")
    section0_anchor_baseline(label, raw)
    sectionX_crossref(label, soup)
    section1_css(label, soup)
    section2_xbrl(label, soup)
    section3_inline_style(label, soup)
    section4_html5(label, soup)


if __name__ == "__main__":
    for label, path in [("ASML 20-F", ASML), ("NOVO 20-F (control)", NOVO)]:
        if not path.exists():
            print(f"MISSING: {label} -> {path}")
            continue
        run(label, path)
