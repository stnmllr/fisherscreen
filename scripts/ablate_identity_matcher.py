r"""Diagnose (one-off): where does the recovery on cache/identity_name_corpus.json
come from?

Reimplements the PREVIOUS normalisation to establish the baseline, then adds one
rule of the new pipeline at a time. Purpose is attribution, not tuning: the spec
quotes measured per-rule contributions (+1.3 diacritics, +17.7 punctuation,
+24.0 legal forms, +2.6 leading forms, +3.8 token multiset), and this says
whether the implementation reproduces them or overshoots somewhere.

Percentages are over the whole 90-entry corpus, which is the denominator the
spec's corridor uses (the 11 entries without an OpenFIGI line are the ~12 points
attributed to the mapping fix in spec section 3).

Aufruf (cmd.exe):
  uv run python scripts\ablate_identity_matcher.py
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path
from typing import Callable

from app.deepdive.eu_adr_resolution import (
    _drop_legal_forms,
    _drop_listing_descriptors,
    _tokenise,
    issuer_tokens,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "cache" / "identity_name_corpus.json"

_OLD_LEGAL_FORMS = (
    " AG", " SA", " S.A.", " N.V.", " NV", " PLC", " SE", " SPA", " S.P.A.",
    " ASA", " AB", " OYJ", " A/S", " HOLDING", " GROUP", " INC", " LTD",
    " LIMITED", " COMPANY", " HLDG", " HLDGS",
)


def old_norm(name: str) -> str:
    n = (name or "").upper()
    for legal in _OLD_LEGAL_FORMS:
        n = n.replace(legal, " ")
    return "".join(n.split())


def old_issuer_name(figi_name: str) -> str:
    n = (figi_name or "").upper().strip()
    if "-" in n:
        head, _, tail = n.rpartition("-")
        if head and tail and " " not in tail:
            return head.strip()
    return n


def baseline(ref: str, line: str) -> bool:
    """What the code did before this change."""
    return old_norm(old_issuer_name(line)) == old_norm(ref)


def _upper_only(name: str) -> list[str]:
    """Old-style folding: uppercase, split on whitespace, nothing else."""
    return (name or "").upper().split()


def no_diacritics(ref: str, line: str) -> bool:
    """Baseline + NFKD, still on the old space-only splitting."""

    def fold(name: str) -> str:
        decomposed = unicodedata.normalize("NFKD", (name or "").upper())
        return old_norm("".join(c for c in decomposed if not unicodedata.combining(c)))

    return fold(old_issuer_name(line)) == fold(ref)


def punctuation_only(ref: str, line: str) -> bool:
    """Baseline + NFKD + punctuation, old legal-form catalog, trailing only."""
    return _tokens_with(ref, _OLD_TRAILING) == _tokens_with(line, _OLD_TRAILING)


_OLD_TRAILING = "old"
_NEW_TRAILING = "new"


def _tokens_with(name: str, catalog: str) -> tuple[str, ...]:
    import app.deepdive.eu_adr_resolution as eu

    forms = eu._LEGAL_FORMS
    if catalog == _OLD_TRAILING:
        forms = tuple(
            sorted(
                (tuple(t.text for t in _tokenise(s)) for s in _OLD_LEGAL_FORMS),
                key=len,
                reverse=True,
            )
        )
    saved = eu._LEGAL_FORMS
    eu._LEGAL_FORMS = forms
    try:
        tokens = _drop_listing_descriptors(_tokenise(name))
        return tuple(_drop_legal_forms([t.text for t in tokens]))
    finally:
        eu._LEGAL_FORMS = saved


def full_strict(ref: str, line: str) -> bool:
    return issuer_tokens(ref) == issuer_tokens(line)


def full_multiset(ref: str, line: str) -> bool:
    left, right = issuer_tokens(ref), issuer_tokens(line)
    return bool(left) and (left == right or sorted(left) == sorted(right))


STAGES: tuple[tuple[str, Callable[[str, str], bool]], ...] = (
    ("0 baseline (code before this change)", baseline),
    ("1 + NFKD diacritics", no_diacritics),
    ("2 + punctuation/descriptors, OLD form catalog", punctuation_only),
    ("3 + extended form catalog, both edges (strict)", full_strict),
    ("4 + token multiset (production)", full_multiset),
)


def main() -> int:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    pairs = {t: v for t, v in corpus.items() if v.get("line")}
    total = len(corpus)

    previous: set[str] = set()
    for label, rule in STAGES:
        hit = {t for t, v in pairs.items() if rule(v["ref"], v["line"])}
        delta = (len(hit) - len(previous)) / total * 100
        print(
            f"{label:<48} {len(hit):>3}/{total}  {len(hit) / total:>6.1%}  "
            f"({delta:+.1f} Punkte)"
        )
        for ticker in sorted(hit - previous):
            print(f"      + {ticker}")
        for ticker in sorted(previous - hit):
            print(f"      - {ticker}  (REGRESSION)")
        previous = hit
    return 0


if __name__ == "__main__":
    sys.exit(main())
