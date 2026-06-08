"""Comprehensive read-only Stage-2 simulator.

Answers three questions in one run:

  Schritt 1 — Token-Budget:
    Per filing, simulate Stage-2 anchor-based section extraction.
    Aggregate body lengths to synthesis-prompt token estimate.
    Compare against today's actual parser output.

  N1 — Slice vs full-context html2text diff:
    For three stichproben (KO §1A, GOOGL §7, NOVO §4): compare
    html2text(html_slice) against substring(html2text(full_html)).
    Report char-diff and visualize if material.

  N3 — Body[0:200] pattern probe:
    Dump first 200 chars of each section body. Test against
    candidate validator pattern.

No code committed. No production paths touched.
"""

from __future__ import annotations

import io
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import html2text  # noqa: E402
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning  # noqa: E402

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from app.deepdive.filing_parser import parse_filing  # noqa: E402  (for "today")

CACHE = Path(__file__).resolve().parents[1] / "cache" / "filings"
CHARS_PER_TOKEN = 4

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

# Static estimates of non-section overhead in the synthesis prompt (from
# inspecting synthesis.py + valuation_block + quant snapshot).
_SYSTEM_PROMPT_CHARS = 2_500  # _SYSTEM_PROMPT in synthesis.py
_FISHER_POINTS_LIST_CHARS = 1_500  # the 15 point titles
_QUANT_SNAPSHOT_JSON_CHARS = 5_000  # model_dump_json typical
_VALUATION_BLOCK_CHARS = 3_000  # render_valuation_block typical
_FORWARD_CONSENSUS_CHARS = 500  # appended in valuation block
_HEADER_SLOT_CHARS = 30  # per section: "### 10-K §N\n"
_BASE_OVERHEAD = (
    _SYSTEM_PROMPT_CHARS + _FISHER_POINTS_LIST_CHARS + _QUANT_SNAPSHOT_JSON_CHARS
    + _VALUATION_BLOCK_CHARS + _FORWARD_CONSENSUS_CHARS
)


def make_h2t() -> html2text.HTML2Text:
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0
    return h


def to_text(html: str) -> str:
    return make_h2t().handle(html)


def find_all_item_anchors(soup: BeautifulSoup) -> list[tuple[str, str, str]]:
    """Return [(item_label, anchor_id, body_text_first_200chars)] in document
    order, for anchors whose next-text starts with 'ITEM N'."""
    # Aggregate hrefs
    by_href: dict[str, list[str]] = defaultdict(list)
    for a in soup.find_all("a", href=True):
        h = a.get("href", "")
        if h.startswith("#"):
            t = a.get_text(" ", strip=True)
            if t:
                by_href[h[1:]].append(t)

    found: list[tuple[str, str, str, int]] = []
    seen: set[str] = set()
    # Determine doc-order positions by finding the id in the original document
    for tid in by_href.keys():
        if tid in seen:
            continue
        seen.add(tid)
        target = soup.find(attrs={"id": tid}) or soup.find("a", attrs={"name": tid})
        if target is None:
            continue
        # Read next text (own + following siblings)
        buf, chars, cur = [], 0, target
        own = target.get_text(" ", strip=True)
        if own:
            buf.append(own)
            chars += len(own)
        while chars < 250:
            sib = cur.find_next_sibling()
            if sib is None:
                par = cur.parent
                if par is None:
                    break
                cur = par
                continue
            cur = sib
            t = cur.get_text(" ", strip=True)
            if t:
                buf.append(t)
                chars += len(t) + 1
        nxt = " ".join(buf)[:250]
        # Tolerate any short page-header prefix (incl. periods like "Inc.").
        m = re.match(
            r"^.{0,80}?\bITEM\s+(\d+[A-Z]?)\b",
            nxt,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            item_label = m.group(1).upper()
            found.append((item_label, tid, nxt, 0))  # pos filled below
    return [(lbl, tid, nxt) for (lbl, tid, nxt, _) in found]


def _tag_start_of(raw_html: str, id_attr_pos: int) -> int:
    """Walk back from a position of id="..." to the '<' that opens the
    containing tag, so the slice starts at a well-formed tag boundary."""
    tag_start = raw_html.rfind("<", max(0, id_attr_pos - 200), id_attr_pos)
    return tag_start if tag_start >= 0 else id_attr_pos


def slice_html_between(raw_html: str, anchor_a: str, anchor_b: str | None) -> str:
    """Find string positions of two anchors in raw HTML and slice between,
    aligning each cut to the opening '<' of the containing tag."""
    pa_id = raw_html.find(f'id="{anchor_a}"')
    if pa_id < 0:
        return ""
    slice_start = _tag_start_of(raw_html, pa_id)
    if anchor_b is None:
        return raw_html[slice_start:]
    pb_id = raw_html.find(f'id="{anchor_b}"')
    if pb_id < 0 or pb_id <= pa_id:
        return raw_html[slice_start:]
    slice_end = _tag_start_of(raw_html, pb_id)
    return raw_html[slice_start:slice_end]


def estimate_tokens(chars: int) -> int:
    return chars // CHARS_PER_TOKEN


def main_token_budget(label: str, form: str, path: Path, expected: list[str]) -> dict:
    """Per filing: simulate Stage-2 extraction + measure synthesis-prompt size."""
    print("\n" + "=" * 78)
    print(f"  TOKEN BUDGET  -  {label}")
    print("=" * 78)
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml-xml")

    # 1) Find ALL item anchors in doc order (for boundary slicing)
    anchors = find_all_item_anchors(soup)
    # Re-order by document position via raw_html.find
    positioned = []
    for lbl, tid, nxt in anchors:
        pos = raw.find(f'id="{tid}"')
        if pos >= 0:
            positioned.append((pos, lbl, tid, nxt))
    positioned.sort(key=lambda x: x[0])
    if positioned:
        print(f"  Item anchors found in doc order: {len(positioned)} "
              f"(first 8 item-labels: {[p[1] for p in positioned[:8]]})")
    else:
        print(f"  Item anchors found: 0  →  FALLBACK PATH (will match today's parser)")

    # 2) Per expected item: slice + html2text + measure
    expected_set = {e.upper() for e in expected}
    per_section: dict[str, dict] = {}
    for i, (pos, lbl, tid, nxt) in enumerate(positioned):
        if lbl not in expected_set:
            continue
        # find next anchor in doc order (any item, to keep section boundary tight)
        next_tid = positioned[i + 1][2] if (i + 1) < len(positioned) else None
        html_slice = slice_html_between(raw, tid, next_tid)
        text = to_text(html_slice)
        per_section[lbl] = {
            "anchor_id": tid,
            "html_slice_chars": len(html_slice),
            "body_chars": len(text),
            "body_prefix_200": text[:200],
        }

    # 3) Compare against today's parser output
    todays = parse_filing(raw, form)
    todays_chars = sum(len(b) for b in todays.sections.values())
    todays_per_item = {
        k.replace(f"{form}_item", ""): {
            "flag": todays.section_flags.get(k, "ok"),
            "chars": len(v),
            "prefix_200": v[:200],
        }
        for k, v in todays.sections.items()
    }

    # 4) Aggregate
    stage2_total_body_chars = sum(s["body_chars"] for s in per_section.values())
    n_sections = len(per_section)
    sections_header_overhead = n_sections * _HEADER_SLOT_CHARS
    stage2_prompt_chars = (
        _BASE_OVERHEAD + stage2_total_body_chars + sections_header_overhead
    )
    stage2_prompt_tokens = estimate_tokens(stage2_prompt_chars)

    todays_prompt_chars = _BASE_OVERHEAD + todays_chars + n_sections * _HEADER_SLOT_CHARS
    todays_prompt_tokens = estimate_tokens(todays_prompt_chars)

    # 5) Output
    print(f"\n  Per-section body lengths (Stage 2 simulated):")
    print(f"    {'item':<6} {'flag (today)':<24} {'today_chars':>12} {'stage2_chars':>14}")
    for e in expected:
        e_norm = e.upper()
        today = todays_per_item.get(e, {"flag": "(missing)", "chars": 0})
        st2 = per_section.get(e_norm, {"body_chars": 0})
        flag = today["flag"]
        if e_norm not in per_section:
            flag_st2 = "FALLBACK (no anchor)"
            st2_chars_disp = f"{today['chars']:>12,} (=today)"
        else:
            flag_st2 = "ok"
            st2_chars_disp = f"{st2['body_chars']:>12,}"
        print(
            f"    {e:<6} {flag:<24} {today['chars']:>12,}  {st2_chars_disp}"
        )

    fallback_used = (n_sections == 0)
    print(f"\n  Aggregated section bodies:")
    print(f"    Today:     {todays_chars:>12,} chars  ({estimate_tokens(todays_chars):>8,} tokens approx)")
    if fallback_used:
        print(f"    Stage 2:   = today (anchor-tracing returned 0 items, fallback path)")
    else:
        print(f"    Stage 2:   {stage2_total_body_chars:>12,} chars  ({estimate_tokens(stage2_total_body_chars):>8,} tokens approx)")
        delta = stage2_total_body_chars - todays_chars
        print(f"    Delta:     {delta:+13,} chars  ({delta/max(todays_chars,1)*100:+.1f}%)")

    print(f"\n  Synthesis-prompt total (base overhead {_BASE_OVERHEAD:,} chars + sections):")
    print(f"    Today:     {todays_prompt_chars:>12,} chars  →  {todays_prompt_tokens:>8,} tokens estimate")
    if not fallback_used:
        print(f"    Stage 2:   {stage2_prompt_chars:>12,} chars  →  {stage2_prompt_tokens:>8,} tokens estimate")

    print(f"\n  Gemini Pro 1M-token context: {stage2_prompt_tokens:,} / 1,000,000 = "
          f"{stage2_prompt_tokens/10_000:.2f}% of context window")

    headroom = 1_000_000 - stage2_prompt_tokens
    verdict = (
        "im Budget" if stage2_prompt_tokens < 400_000 else
        "knapp"     if stage2_prompt_tokens < 800_000 else
        "ÜBER BUDGET"
    )
    print(f"  Verdict: {verdict}  (headroom {headroom:,} tokens)")

    return {
        "label": label,
        "fallback": fallback_used,
        "per_section": per_section,
        "todays_per_item": todays_per_item,
        "stage2_prompt_tokens": stage2_prompt_tokens,
        "todays_prompt_tokens": todays_prompt_tokens,
        "raw_html": raw,
        "positioned_anchors": positioned,
    }


def n1_slice_vs_fullcontext(probe_label: str, item: str, result: dict) -> None:
    """Compare html2text(slice) vs substring(html2text(full)) for the same
    DOM region. Diff in chars + visualize first divergent area."""
    print("\n" + "-" * 78)
    print(f"  N1 PROBE — {probe_label} item {item}")
    print("-" * 78)
    section_data = result["per_section"].get(item.upper())
    if section_data is None:
        print(f"  Skipped (no anchor for item {item})")
        return
    raw = result["raw_html"]
    anchor_id = section_data["anchor_id"]
    # Find next anchor in doc order, then build a properly-aligned slice via
    # the same alignment function we use for the budget probe.
    positioned = result["positioned_anchors"]
    pos = raw.find(f'id="{anchor_id}"')
    next_tid = None
    for p, lbl, tid, _ in positioned:
        if p > pos:
            next_tid = tid
            break
    html_slice = slice_html_between(raw, anchor_id, next_tid)
    text_from_slice = to_text(html_slice)

    # Now locate the same region in the full html2text by searching for the
    # ITEM-heading pattern (robust to leading boundary noise like '* * *').
    full_text = to_text(raw)
    m = re.search(r"ITEM\s+\d+[A-Z]?(?:\.|\s)", text_from_slice, re.IGNORECASE)
    if m is None:
        print(f"  WARNING: no ITEM heading in slice text (slice may be malformed)")
        return
    anchor_text = text_from_slice[m.start(): m.start() + 60]
    needle_pos = full_text.find(anchor_text)
    if needle_pos < 0:
        # try a shorter needle
        anchor_text = text_from_slice[m.start(): m.start() + 30]
        needle_pos = full_text.find(anchor_text)
    if needle_pos < 0:
        print(f"  WARNING: ITEM heading found in slice but not in full text.")
        print(f"  Slice ITEM line: {anchor_text!r}")
        return
    # Compare from ITEM heading onward, length = remaining slice from ITEM
    slice_from_item = text_from_slice[m.start():]
    full_substring_from_item = full_text[needle_pos: needle_pos + len(slice_from_item)]

    print(f"  slice-html2text (from ITEM hdr) chars: {len(slice_from_item):,}")
    print(f"  full-substring  (from ITEM hdr) chars: {len(full_substring_from_item):,}")

    # First divergent position from ITEM-heading onward
    n = min(len(slice_from_item), len(full_substring_from_item))
    div_pos = next(
        (i for i in range(n) if slice_from_item[i] != full_substring_from_item[i]),
        n,
    )
    print(f"  first divergence position (from ITEM hdr): {div_pos:,} / {n:,}")
    if div_pos < n:
        print(f"    slice text at div pos: {slice_from_item[div_pos:div_pos+80]!r}")
        print(f"    full  text at div pos: {full_substring_from_item[div_pos:div_pos+80]!r}")
    else:
        print(f"    BYTE-IDENTICAL from ITEM heading onward (length {n:,})")

    common = sum(
        1 for i in range(n) if slice_from_item[i] == full_substring_from_item[i]
    )
    pct = common * 100 / max(n, 1)
    print(f"  byte-equal up to min-length: {common:,}/{n:,} ({pct:.2f}%)")


def n3_body_prefix_pattern(results: list[dict]) -> None:
    """Dump body[0:200] for every successfully-anchored section + test against
    candidate validator pattern."""
    print("\n" + "=" * 78)
    print("  N3 BODY-PREFIX PATTERN PROBE")
    print("=" * 78)
    # Tighter candidate per N3 nachschärfung: up to 300 chars of noise prefix
    # (handles `* * *`, table-render noise, page-header), then ITEM N word-
    # boundary. Number-suffix optional (NOVO 20-F uses `ITEM 4`, not `ITEM 4.`).
    pattern = re.compile(
        r"^[\s\S]{0,300}?\bITEM\s+\d+[A-Z]?\b",
        re.IGNORECASE,
    )
    print(f"  Candidate pattern: r{pattern.pattern!r}")
    print()
    for r in results:
        label = r["label"]
        if r["fallback"]:
            print(f"  {label}: FALLBACK (no anchor-extracted bodies to test)")
            continue
        for item, sd in r["per_section"].items():
            prefix = sd["body_prefix_200"][:120]
            m = bool(pattern.match(sd["body_prefix_200"]))
            mark = "OK " if m else "FAIL"
            print(f"  [{mark}] {label} §{item:<3}: {prefix!r}")


if __name__ == "__main__":
    results = []
    for label, form, path, expected in TARGETS:
        if not path.exists():
            print(f"\nMISSING: {label}")
            continue
        r = main_token_budget(label, form, path, expected)
        results.append(r)

    # N1: probe specific stichproben
    print("\n\n")
    print("#" * 78)
    print("# N1 — Slice vs full-context html2text diff (3 stichproben)")
    print("#" * 78)
    by_label = {r["label"]: r for r in results}
    if "KO 10-K" in by_label:
        n1_slice_vs_fullcontext("KO 10-K", "1A", by_label["KO 10-K"])
    if "GOOGL 10-K" in by_label:
        n1_slice_vs_fullcontext("GOOGL 10-K", "7", by_label["GOOGL 10-K"])
    if "NOVO 20-F" in by_label:
        n1_slice_vs_fullcontext("NOVO 20-F", "4", by_label["NOVO 20-F"])

    # N3
    print("\n\n")
    print("#" * 78)
    print("# N3 — Body[0:200] pattern probe")
    print("#" * 78)
    n3_body_prefix_pattern(results)
