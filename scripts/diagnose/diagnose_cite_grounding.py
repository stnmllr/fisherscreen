"""E3: verify whether dossier cites are grounded in the section body that was
actually sent to Gemini.

Read-only. For each chosen (filing, section_key, search_term) triple:
  * parse the cached filing with the production parser
  * look at the body that was actually under section_key
  * check whether the search_term appears in that body (case-insensitive)
  * also: where else in the document the term appears (for context)
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.deepdive.filing_parser import parse_filing, _to_text  # noqa: E402

CACHE = Path(__file__).resolve().parents[1] / "cache" / "filings"

CASES = [
    # (label, cik, accession, form, section_key, search_terms)
    (
        "GOOGL P2 [10-K §1] [10-K §7]: 'Other Bets', 'Waymo'",
        "0001652044",
        "0001652044-26-000018",
        "10-K",
        ["10-K_item1", "10-K_item7"],
        ["Other Bets", "Waymo", "Moonshots"],
    ),
    (
        "GOOGL P6 [10-K §1A] [10-K §7]: 'TPU', 'Nvidia', 'KI-Chips'",
        "0001652044",
        "0001652044-26-000018",
        "10-K",
        ["10-K_item1A", "10-K_item7"],
        ["TPU", "Nvidia", "AI accelerator", "in-house"],
    ),
    (
        "ASML P11 [20-F §18] [Marktkontext]: 'EUV', 'Zeiss', 'lithography'",
        "0000937966",
        "0001628280-26-011378",
        "20-F",
        ["20-F_item18"],
        ["EUV", "Zeiss", "lithography", "monopoly"],
    ),
]


def main() -> None:
    by_filing: dict[str, tuple] = {}
    for label, cik, acc, form, keys, terms in CASES:
        path = CACHE / cik / f"{acc}.txt"
        if path not in by_filing:
            raw = path.read_text(encoding="utf-8", errors="replace")
            parsed = parse_filing(raw, form)
            full_text = _to_text(raw)
            by_filing[path] = (parsed, full_text)
        parsed, full_text = by_filing[path]

        print("\n" + "=" * 78)
        print(f"  {label}")
        print(f"  file: {path.name}")
        print("=" * 78)
        for key in keys:
            body = parsed.sections.get(key, "")
            flag = parsed.section_flags.get(key, "ok")
            print(f"\n  --- section {key}  (flag={flag}, body_len={len(body):,}) ---")
            print(f"    body head: {body[:140]!r}")
            for term in terms:
                in_body = bool(
                    re.search(re.escape(term), body, re.IGNORECASE)
                )
                in_full = list(
                    re.finditer(re.escape(term), full_text, re.IGNORECASE)
                )
                verdict = (
                    "GROUNDED" if in_body
                    else ("NOT in section, but in full-text" if in_full else "NOT ANYWHERE")
                )
                print(
                    f"    term {term!r:30} in_body={str(in_body):5} "
                    f"in_full_doc_hits={len(in_full):>4}  --> {verdict}"
                )
                # If not in body but in doc, show where the first hit lives in
                # OTHER section bodies (which is the 'mis-labeled section' case).
                if in_full and not in_body:
                    first_pos = in_full[0].start()
                    # Find which section's body window contains first_pos
                    for k2, body2 in parsed.sections.items():
                        # We don't have explicit start/end positions stored, so
                        # check whether the term is in any OTHER section's body
                        if k2 == key:
                            continue
                        if re.search(re.escape(term), body2, re.IGNORECASE):
                            print(
                                f"        -> term also appears in section "
                                f"{k2} body (mis-labeled?)"
                            )


if __name__ == "__main__":
    main()
