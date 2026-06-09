"""Intermediate-Items follow-up diagnosis (Punkt 5 / post-Stage-5).

Read-only. Extends the Stage-5 drop-wirkung probe with the question the
string-presence probe could not answer:

  For each intermediate item (10-K §3/§1C/§9-§14, 20-F §6/§7/§10/§16) that the
  N4-drop excludes from the synthesis prompt, is the dropped material
  SUBSTANTIVE, or merely an "incorporated by reference to the proxy statement"
  cross-reference (10-K Part III) -- i.e. content that was never in the filing
  body regardless of parser?

Per filing it prints:
  1. which ITEM-N headings the LEGACY last-item tail actually absorbed
     (the structural drop surface), with a short context snippet each;
  2. for each management-cluster theme, a 3-way classification (verfuegbar /
     DROP-tail / F8-aussen) PLUS, for DROP-tail, whether the legacy-tail context
     is incorporation-by-reference boilerplate or substantive prose.

SOPRA-EPDR: uv run python scripts/diagnose_intermediate_items.py
"""

from __future__ import annotations

import importlib.util
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.deepdive.filing_parser import _FORM_ITEMS, parse_filing  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_t_real", ROOT / "tests" / "deepdive" / "test_filing_parser_real.py"
)
_t_real = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_t_real)
_legacy_parse_filing = _t_real._legacy_parse_filing

CACHE = ROOT / "cache" / "filings"

FILINGS = {
    "KO": ("0000021344", "0001628280-26-010047", "10-K", "10-K_item8"),
    "GOOGL": ("0001652044", "0001652044-26-000018", "10-K", "10-K_item8"),
    "NOVO-B.CO": ("0000353278", "0000353278-26-000012", "20-F", "20-F_item18"),
    "ASML": ("0000937966", "0001628280-26-011378", "20-F", "20-F_item18"),
}

# Intermediate (non-expected) items per form, with Fisher relevance note.
INTERMEDIATE_ITEMS = {
    "10-K": [
        ("1C", "Cybersecurity (P14/P15 robustness)"),
        ("3", "Legal Proceedings (P15 integrity)"),
        ("9", "Changes/Disagreements w/ Accountants (P10)"),
        ("9A", "Controls and Procedures (P10)"),
        ("10", "Directors/Exec Officers/Governance (P8/P9)"),
        ("11", "Executive Compensation (P8/P9)"),
        ("12", "Security Ownership (P8 dual-class)"),
        ("13", "Related-Party Transactions (P15)"),
        ("14", "Principal Accountant Fees (P10)"),
    ],
    "20-F": [
        ("6", "Directors/Senior Mgmt/Compensation/Employees (P7/P8/P9)"),
        ("7", "Major Shareholders & Related Party (P8/P15)"),
        ("8", "Financial Information / Legal (P15)"),
        ("10", "Additional Information / Governance (P8)"),
        ("16", "Audit cmte / Ethics / Cyber (P10/P15)"),
    ],
}

# Management-cluster themes: terms whose presence/absence we trace.
THEMES = {
    "10-K": [
        ("Executive Compensation (§11)", ["executive compensation"]),
        ("Compensation tables/figures", ["summary compensation table", "compensation committee"]),
        ("Related-Party Transactions (§13)", ["related part", "related person transaction"]),
        ("Directors/Governance (§10)", ["board of directors", "corporate governance", "directors of the registrant"]),
        ("Security Ownership (§12)", ["security ownership", "beneficial owner"]),
        ("Legal Proceedings (§3)", ["legal proceedings"]),
        ("Cybersecurity (§1C)", ["cybersecurity"]),
    ],
    "20-F": [
        ("Compensation/Remuneration (§6B)", ["remuneration", "compensation of directors"]),
        ("Board practices (§6C)", ["board practices", "audit committee"]),
        ("Related-Party (§7B)", ["related part"]),
        ("Major shareholders (§7A)", ["major shareholder"]),
    ],
}

INCORP_RE = re.compile(
    r"incorporated\s+(?:herein\s+)?by\s+reference|"
    r"will\s+be\s+(?:set\s+forth|included|contained)\s+in.{0,40}proxy|"
    r"information\s+required\s+by\s+(?:this\s+)?item.{0,80}proxy",
    re.IGNORECASE | re.DOTALL,
)


def _ctx(text: str, term: str, width: int = 140) -> str | None:
    m = re.search(re.escape(term), text, re.IGNORECASE)
    if not m:
        return None
    s = max(0, m.start() - width)
    e = min(len(text), m.end() + width)
    snippet = re.sub(r"\s+", " ", text[s:e]).strip()
    return f"...{snippet}..."


def _item_headings_in(body: str, form: str) -> list[tuple[str, str]]:
    """Find intermediate ITEM-N headings (line-start) inside a parsed body."""
    found = []
    for item, note in INTERMEDIATE_ITEMS[form]:
        pat = re.compile(rf"^[ \t#*]*ITEM\s+{re.escape(item)}\b[ \t]*[.:\-—]", re.IGNORECASE | re.MULTILINE)
        m = pat.search(body)
        if m:
            line = re.sub(r"\s+", " ", body[m.start(): m.start() + 90]).strip()
            found.append((f"§{item} ({note})", line))
    return found


def main() -> None:
    for ticker, (cik, acc, form, last_key) in FILINGS.items():
        raw = (CACHE / cik / f"{acc}.txt").read_text(encoding="utf-8", errors="replace")
        new = parse_filing(raw, form)
        legacy = _legacy_parse_filing(raw, form)
        new_union = "\n".join(new.sections.values())
        legacy_last = legacy.sections.get(last_key, "")

        print("\n" + "=" * 78)
        print(f"  {ticker}  ({form})   legacy {last_key} tail = {len(legacy_last):,} chars")
        print("=" * 78)

        print("\n  -- intermediate ITEM-headings absorbed in the legacy tail --")
        headings = _item_headings_in(legacy_last, form)
        if not headings:
            print("    (none detected as line-start headings)")
        for label, line in headings:
            print(f"    {label}")
            print(f"        heading: {line[:80]}")

        # Is Part III (10-K) / equivalent incorporated by reference?
        incorp = INCORP_RE.search(legacy_last)
        print("\n  -- incorporation-by-reference check (legacy tail) --")
        if incorp:
            s = max(0, incorp.start() - 90)
            e = min(len(legacy_last), incorp.end() + 90)
            print("    FOUND:", re.sub(r"\s+", " ", legacy_last[s:e]).strip()[:240])
        else:
            print("    none found in legacy tail")

        print("\n  -- management-cluster theme classification --")
        for theme, terms in THEMES[form]:
            in_new = any(re.search(re.escape(t), new_union, re.I) for t in terms)
            in_tail = any(re.search(re.escape(t), legacy_last, re.I) for t in terms)
            if in_new:
                verdict = "verfuegbar (im neu-Prompt)"
                ctx = None
            elif in_tail:
                verdict = "DROP-tail (nur legacy tail)"
                ctx = next((_ctx(legacy_last, t) for t in terms if _ctx(legacy_last, t)), None)
            else:
                verdict = "F8-aussen (in keinem Prompt)"
                ctx = None
            print(f"    {theme:<40} -> {verdict}")
            if ctx:
                print(f"        ctx: {ctx[:200]}")


if __name__ == "__main__":
    main()
