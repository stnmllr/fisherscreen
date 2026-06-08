"""Stage-5 Step 5.3: body-length comparison (legacy vs anchor parser) and the
two-stage drop-wirkung probe with source distinction.

Read-only. Per filing:
  * per-section body lengths: legacy (pre-Stage-2, F2-tail-absorbing) parser
    vs the anchor parser, plus total sent chars + estimated input tokens
  * three-way classification for curated intermediate-item themes that appear
    in the *old* dossier's reasoning:
      - "verfuegbar"  : term is in a NEW sent section  -> no drop
      - "DROP-tail"   : term is NOT in any new section but IS in the legacy
                        last-item body (10-K §8 / 20-F §18) -> tail-absorption
                        gave it to the old model; the clean parser excludes it
                        -> Intermediate-Items follow-up ticket
      - "F8-aussen"   : term in neither -> model outside-knowledge -> F8 backlog

SOPRA-EPDR: uv run python scripts/diagnose_drop_wirkung.py
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

from app.deepdive.filing_parser import (  # noqa: E402
    _CHARS_PER_TOKEN,
    _FORM_ITEMS,
    parse_filing,
)

# Load _legacy_parse_filing (frozen pre-Stage-2 parser) from the test module.
_spec = importlib.util.spec_from_file_location(
    "_t_real", ROOT / "tests" / "deepdive" / "test_filing_parser_real.py"
)
_t_real = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_t_real)
_legacy_parse_filing = _t_real._legacy_parse_filing

CACHE = ROOT / "cache" / "filings"

# ticker -> (cik, accession, form, last_item_key)
FILINGS = {
    "KO": ("0000021344", "0001628280-26-010047", "10-K", "10-K_item8"),
    "GOOGL": ("0001652044", "0001652044-26-000018", "10-K", "10-K_item8"),
    "NOVO-B.CO": ("0000353278", "0000353278-26-000012", "20-F", "20-F_item18"),
    "ASML": ("0000937966", "0001628280-26-011378", "20-F", "20-F_item18"),
}

# Curated intermediate-item / tail themes drawn from the OLD dossiers' reasoning.
THEMES = {
    "GOOGL": [
        ("Antitrust/Legal (§3/§11-Territory)", ["antitrust", "Department of Justice"]),
        ("Executive Compensation (§11)", ["executive compensation", "compensation committee"]),
        ("Related-Party Transactions (§13)", ["related part"]),
        ("Dual-class governance (§12/Cover)", ["Class B", "supervoting", "super-voting"]),
    ],
    "NOVO-B.CO": [
        ("Iran disclosure (§16B)", ["Iran"]),
        ("Critical Audit Matter (§18 audit report)", ["Critical Audit Matter"]),
        ("Management/Board turnover (§6)", ["Doustdar"]),
        ("Layoffs ~9,000 (transformation)", ["9,000", "9.000"]),
    ],
    "ASML": [
        ("Mistral AI investment", ["Mistral"]),
        ("High-NA roadmap", ["High-NA", "High NA"]),
        ("Net reduction ~1,700 positions", ["1,700", "1.700"]),
        ("Zeiss supplier ecosystem", ["Zeiss"]),
        ("EUV monopoly", ["EUV"]),
    ],
}


def _contains(text: str, term: str) -> bool:
    return re.search(re.escape(term), text, re.IGNORECASE) is not None


def main() -> None:
    for ticker, (cik, acc, form, last_key) in FILINGS.items():
        raw = (CACHE / cik / f"{acc}.txt").read_text(encoding="utf-8", errors="replace")
        new = parse_filing(raw, form)
        legacy = _legacy_parse_filing(raw, form)

        print("\n" + "=" * 74)
        print(f"  {ticker}  ({form})")
        print("=" * 74)
        print(f"  {'section':<16}{'legacy len':>12}{'anchor len':>12}   flag")
        for item in _FORM_ITEMS[form]:
            key = f"{form}_item{item}"
            llen = len(legacy.sections.get(key, ""))
            nlen = len(new.sections.get(key, ""))
            flag = new.section_flags.get(key)
            fstr = ""
            if flag is not None:
                parts = [flag.extraction]
                if flag.missing:
                    parts.append("missing")
                if flag.truncated:
                    parts.append("truncated")
                fstr = "+".join(parts)
            print(f"  {key:<16}{llen:>12,}{nlen:>12,}   {fstr}")

        legacy_total = sum(len(v) for v in legacy.sections.values())
        new_total = sum(len(v) for v in new.sections.values())
        print(f"  {'TOTAL sent':<16}{legacy_total:>12,}{new_total:>12,}")
        print(f"  est. input tokens (chars/{_CHARS_PER_TOKEN}):"
              f"  legacy ~{legacy_total // _CHARS_PER_TOKEN:,}"
              f"   anchor ~{new_total // _CHARS_PER_TOKEN:,}")

        # ---- drop-wirkung three-way classification ----
        new_union = "\n".join(new.sections.values())
        legacy_last = legacy.sections.get(last_key, "")
        print(f"\n  drop-wirkung (legacy last-item = {last_key}, "
              f"{len(legacy_last):,} chars):")
        for theme, terms in THEMES.get(ticker, []):
            in_new = [t for t in terms if _contains(new_union, t)]
            in_legacy_last = [t for t in terms if _contains(legacy_last, t)]
            if in_new:
                verdict = f"verfuegbar (kein Drop) — in neu-Prompt: {in_new}"
            elif in_legacy_last:
                verdict = f"DROP-tail — nur im legacy {last_key}: {in_legacy_last}"
            else:
                verdict = "F8-aussen (Modell-Aussenwissen, in keinem Prompt)"
            print(f"    - {theme:<42} -> {verdict}")


if __name__ == "__main__":
    main()
