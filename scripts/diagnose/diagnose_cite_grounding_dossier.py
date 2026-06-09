"""Stage-5 acceptance probe: are the §-cites in a Tool-B dossier grounded?

Read-only. For each dossier (old + new) this:
  * extracts every filing-section cite  [10-K §N] / [20-F §N]  from the body
  * re-parses the *cached* filing with the production parser
  * feeds each cite through the production validator `_validate_sources`
    against the freshly re-parsed sections (= exactly the sections that were
    sent to Gemini for the new dossiers — parse_filing is deterministic)
  * a cite is GROUNDED iff the production validator keeps it (does not
    collapse the single-source list to ["Inferenz"])

Acceptance gate (Stage 5): GOOGL/KO/NOVO new dossiers = 100% grounded.
ASML new dossier = no regress vs the old dossier (>= old grounded ratio).

This is interpretation (A) — structural grounding: every surviving §-cite
points to a section that was genuinely extracted (present + correct ITEM
heading). F8-class substantive hallucination (claim not in an otherwise-valid
section) is explicitly out of scope for Punkt 5.

SOPRA-EPDR: uv run python scripts/diagnose_cite_grounding_dossier.py
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.deepdive.filing_parser import parse_filing  # noqa: E402
from app.deepdive.synthesis import _validate_sources  # noqa: E402

CACHE = ROOT / "cache" / "filings"
WATCH = ROOT / "output" / "Watchlist"

# Capture the full inner cite incl. the 20-F sub-paragraph form "§5 D"
# (space before the letter) and the 10-K standalone-subitem form "§1A".
_CITE_RE = re.compile(r"\[((?:10-K|20-F)\s*§\s*\d+\s*[A-Z]?)\]", re.IGNORECASE)
_LABEL_RE = re.compile(r"(?:10-K|20-F)\s*§\s*(\d+)\s*([A-Z])?", re.IGNORECASE)
_OTHER_MARKER_RE = re.compile(r"\[([^\]\d§][^\]]*)\]")  # [Inferenz], [Quant-Snapshot], ...

# dossier file -> (cik, accession, form_type)
FILINGS = {
    "KO": ("0000021344", "0001628280-26-010047", "10-K"),
    "GOOGL": ("0001652044", "0001652044-26-000018", "10-K"),
    "NOVO-B.CO": ("0000353278", "0000353278-26-000012", "20-F"),
    "ASML": ("0000937966", "0001628280-26-011378", "20-F"),
}

# (label, dossier filename, ticker-key into FILINGS, role)
DOSSIERS = [
    ("KO   neu", "KO_2026-05-26.md", "KO", "new"),
    ("GOOGL alt", "GOOGL_2026-05-20.md", "GOOGL", "old"),
    ("GOOGL neu", "GOOGL_2026-05-26.md", "GOOGL", "new"),
    ("NOVO  alt", "NOVO-B.CO_2026-05-19.md", "NOVO-B.CO", "old"),
    ("NOVO  neu", "NOVO-B.CO_2026-05-26.md", "NOVO-B.CO", "new"),
    ("ASML  alt", "ASML_2026-05-20.md", "ASML", "old"),
    ("ASML  neu", "ASML_2026-05-26.md", "ASML", "new"),
]


def _body(md: str) -> str:
    """Strip YAML frontmatter so flags like `10-K_item1: ok` are not scanned."""
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end >= 0:
            return md[end + 4 :]
    return md


_parsed_cache: dict[str, object] = {}


def _parse(ticker: str):
    cik, acc, form = FILINGS[ticker]
    if ticker not in _parsed_cache:
        raw = (CACHE / cik / f"{acc}.txt").read_text(encoding="utf-8", errors="replace")
        _parsed_cache[ticker] = (parse_filing(raw, form), form)
    return _parsed_cache[ticker]


def main() -> int:
    results: dict[str, float] = {}
    for label, fname, ticker, role in DOSSIERS:
        path = WATCH / fname
        if not path.exists():
            print(f"\n{label}: dossier not found ({fname}) — skipped")
            continue
        body = _body(path.read_text(encoding="utf-8", errors="replace"))
        parsed, form = _parse(ticker)
        sent_keys = set(parsed.sections.keys())

        inner_cites = _CITE_RE.findall(body)  # e.g. "20-F §5 D", "10-K §1A"
        total = len(inner_cites)
        grounded = 0
        ungrounded: list[str] = []
        per_item: dict[str, int] = {}
        for inner in inner_cites:
            cite_str = f"[{inner}]"
            lm = _LABEL_RE.search(inner)
            label_n = (lm.group(1) + (lm.group(2) or "")).upper()
            per_item[label_n] = per_item.get(label_n, 0) + 1
            # Feed the exact original cite string to the production validator,
            # which keys 20-F sub-paragraphs (§5 D) onto the parent item5 via
            # its numeric fallback and 10-K subitems (§1A) onto item1A directly.
            kept = _validate_sources([cite_str], form, sent_keys, parsed.sections)
            if kept != ["Inferenz"]:
                grounded += 1
            else:
                ungrounded.append(cite_str)

        markers: dict[str, int] = {}
        for m in _OTHER_MARKER_RE.findall(body):
            key = m.strip()
            markers[key] = markers.get(key, 0) + 1

        pct = (grounded / total * 100) if total else 100.0
        results[label] = pct
        print("\n" + "=" * 70)
        print(f"  {label}   ({fname})")
        print("=" * 70)
        print(f"  §-cites total           : {total}")
        print(f"  §-cites grounded        : {grounded}  ({pct:.1f}%)")
        print(f"  §-cite distribution     : "
              f"{', '.join(f'§{k}×{v}' for k, v in sorted(per_item.items()))}")
        if ungrounded:
            print(f"  UNGROUNDED cites        : {ungrounded}")
        inf = markers.get("Inferenz", 0)
        print(f"  [Inferenz] markers      : {inf}")
        other = {k: v for k, v in markers.items() if k != "Inferenz"}
        print(f"  other markers           : "
              f"{', '.join(f'{k}×{v}' for k, v in sorted(other.items()))}")

    # ---- acceptance gate ----
    print("\n" + "#" * 70)
    print("  ACCEPTANCE GATE")
    print("#" * 70)
    gate_ok = True
    for lbl in ("GOOGL neu", "KO   neu", "NOVO  neu"):
        pct = results.get(lbl)
        ok = pct is not None and pct >= 100.0
        gate_ok = gate_ok and ok
        print(f"  {lbl}: {pct:.1f}% grounded  -> {'PASS' if ok else 'FAIL'}")
    asml_new = results.get("ASML  neu")
    asml_old = results.get("ASML  alt")
    if asml_new is not None and asml_old is not None:
        ok = asml_new >= asml_old
        print(f"  ASML  neu vs alt: {asml_new:.1f}% vs {asml_old:.1f}%  "
              f"-> {'NO REGRESS' if ok else 'REGRESS'}")
        gate_ok = gate_ok and ok
    print("\n  " + ("ALL CHECKS PASS" if gate_ok else "GATE FAILED — investigate"))
    return 0 if gate_ok else 1


if __name__ == "__main__":
    sys.exit(main())
