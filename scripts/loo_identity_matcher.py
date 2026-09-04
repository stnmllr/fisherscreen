r"""Diagnose (one-off): leave-one-out over the discretionary rules of the new
issuer normalisation.

The spec fixes the rule LIST; several details inside it were judgement calls
(which legal forms beyond the ones named, whether a bare hyphen-attached share
class letter counts as a listing descriptor, whether legal forms are stripped
at the leading edge too). This prints what each of those is worth on
cache/identity_name_corpus.json, so the report can say where the recovery comes
from instead of quoting one total.

Attribution only. Nothing here changes behaviour.

Aufruf (cmd.exe):
  uv run python scripts\loo_identity_matcher.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import app.deepdive.eu_adr_resolution as eu

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "cache" / "identity_name_corpus.json"

# Legal forms the spec names explicitly (section 1.4) plus the ones that were
# already in the catalog before this change. Everything else is a judgement call.
_SPEC_NAMED = {
    ("AG",), ("SA",), ("NV",), ("PLC",), ("SE",), ("SPA",), ("ASA",), ("AB",),
    ("OYJ",), ("AS",), ("HOLDING",), ("GROUP",), ("INC",), ("LTD",),
    ("LIMITED",), ("COMPANY",), ("HLDG",), ("HLDGS",),
    ("AKTIENGESELLSCHAFT",), ("SOCIETE", "ANONYME"), ("SOCIETA", "PER", "AZIONI"),
    ("NAAMLOZE", "VENNOOTSCHAP"), ("PUBLIC", "LIMITED", "COMPANY"), ("SGPS",),
    ("PUBL",),
}


def measure(label: str, corpus: dict) -> int:
    pairs = {t: v for t, v in corpus.items() if v.get("line")}
    hit = {
        t for t, v in pairs.items() if eu.same_issuer_identity(v["ref"], v["line"])
    }
    print(f"  {label:<52} {len(hit):>3}/{len(corpus)}  {len(hit) / len(corpus):>6.1%}")
    return len(hit)


def main() -> int:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))

    print("=== voll ===")
    full = measure("alle Regeln (production)", corpus)

    print("\n=== leave-one-out (Differenz = exklusiver Beitrag) ===")

    saved_forms = eu._LEGAL_FORMS
    eu._LEGAL_FORMS = tuple(f for f in saved_forms if f in _SPEC_NAMED)
    n = measure("ohne die selbst ergaenzten Rechtsformen", corpus)
    print(f"      -> exklusiver Beitrag: {full - n} Titel "
          f"({(full - n) / len(corpus) * 100:+.1f} Punkte)")
    eu._LEGAL_FORMS = saved_forms

    saved_class = eu._is_share_class_letter
    eu._is_share_class_letter = lambda token, left, right: (
        len(token.text) == 1
        and token.text.isalpha()
        and (left in eu._CLASS_WORDS or right in eu._CLASS_WORDS)
    )
    n = measure("ohne blanke Klassenbuchstaben nach Bindestrich", corpus)
    print(f"      -> exklusiver Beitrag: {full - n} Titel "
          f"({(full - n) / len(corpus) * 100:+.1f} Punkte)")
    eu._is_share_class_letter = saved_class

    saved_drop = eu._drop_legal_forms

    def trailing_only(tokens):
        kept = list(tokens)
        stripping = True
        while stripping:
            stripping = False
            for form in eu._LEGAL_FORMS:
                size = len(form)
                if len(kept) > size and tuple(kept[-size:]) == form:
                    del kept[-size:]
                    stripping = True
                    break
        return kept

    eu._drop_legal_forms = trailing_only
    n = measure("ohne fuehrende Rechtsformen (nur Suffix)", corpus)
    print(f"      -> exklusiver Beitrag: {full - n} Titel "
          f"({(full - n) / len(corpus) * 100:+.1f} Punkte)")
    eu._drop_legal_forms = saved_drop

    saved_same = eu.same_issuer_identity
    eu.same_issuer_identity = lambda left, right: bool(
        eu.issuer_tokens(left)
    ) and eu.issuer_tokens(left) == eu.issuer_tokens(right)
    n = measure("ohne Token-Multiset-Arm (nur strikte Gleichheit)", corpus)
    print(f"      -> exklusiver Beitrag: {full - n} Titel "
          f"({(full - n) / len(corpus) * 100:+.1f} Punkte)")
    eu.same_issuer_identity = saved_same

    saved_desc = eu._LISTING_DESCRIPTORS
    eu._LISTING_DESCRIPTORS = frozenset()
    n = measure("ohne Notierungs-Deskriptoren komplett", corpus)
    print(f"      -> exklusiver Beitrag: {full - n} Titel "
          f"({(full - n) / len(corpus) * 100:+.1f} Punkte)")
    eu._LISTING_DESCRIPTORS = saved_desc

    saved_translit = eu._TRANSLITERATIONS
    eu._TRANSLITERATIONS = {}
    n = measure("ohne Transliteration (Oe)", corpus)
    print(f"      -> exklusiver Beitrag: {full - n} Titel "
          f"({(full - n) / len(corpus) * 100:+.1f} Punkte)")
    eu._TRANSLITERATIONS = saved_translit

    return 0


if __name__ == "__main__":
    sys.exit(main())
