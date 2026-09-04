r"""Hand-Check (one-off): run the new issuer normalisation over the offline
name corpus and over the counter-basket.

This is NOT the acceptance test — that is the third census run. It is the
sanity check that what was implemented is what was measured: how many of the
90 corpus pairs the rules now reconcile, which ones they still miss, and
whether the three pairs that MUST NOT match still refuse to.

Also prints the stump survey required by the spec: the shortest normalised
names and any collision between two different issuers.

Aufruf (cmd.exe):
  uv run python scripts\handcheck_identity_matcher.py
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

from app.deepdive.eu_adr_resolution import (
    issuer_tokens,
    norm_issuer,
    same_issuer_identity,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "cache" / "identity_name_corpus.json"
CENSUS = REPO_ROOT / "cache" / "eu_sec_source_census_v2.json"

# The census notes quote the OpenFIGI identity that was actually resolved, which
# is a far wider stump survey than the 90-entry corpus: ~400 real EU issuer
# names instead of 180.
_NAME_IN_NOTE = re.compile(
    r"Kein SEC-Hard-Scuttlebutt: (.+?) (?:ist kein SEC-Registrant"
    r"|hat keine US-Notierung|\(US-Linie)"
)

# Pairs that must NEVER match. All three were observed for real: the first is
# the documented variant-ladder false hit, the other two are data-source errors
# where the guard correctly refused (both get an override entry instead).
COUNTER_BASKET = (
    ("ROCHE HOLDING AG", "ROCHE BOBOIS SA-UNSPON ADR"),
    ("BT Group plc", "BRITANNIA GROUP PLC"),
    ("Beacon Hill CBO III Ltd", "GLANBIA PLC"),
)


def main() -> int:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    pairs = {t: v for t, v in corpus.items() if v.get("line")}

    matched = [t for t, v in pairs.items() if same_issuer_identity(v["ref"], v["line"])]
    missed = [t for t in pairs if t not in matched]

    print(f"=== Korpus: {len(corpus)} Eintraege, {len(pairs)} mit OpenFIGI-Linie ===")
    print(
        f"  matched : {len(matched)}/{len(pairs)} "
        f"({len(matched) / len(pairs):.1%} der Paare, "
        f"{len(matched) / len(corpus):.1%} des Korpus)"
    )
    print(f"  missed  : {len(missed)}")
    print(f"  ohne Linie (kein OpenFIGI-Treffer): {len(corpus) - len(pairs)}")

    print("\n--- weiterhin ohne Match ---")
    for ticker in missed:
        entry = pairs[ticker]
        print(f"  {ticker:<12} {norm_issuer(entry['ref']):<34} != {norm_issuer(entry['line'])}")
        print(f"               ref={entry['ref']!r}")
        print(f"               line={entry['line']!r}")

    print("\n=== Gegenkorb (darf NICHT matchen) ===")
    leaks = 0
    for left, right in COUNTER_BASKET:
        verdict = same_issuer_identity(left, right)
        leaks += bool(verdict)
        print(f"  {'LECK' if verdict else 'ok  '}  {left!r} vs {right!r}")
        print(f"          {norm_issuer(left)!r} vs {norm_issuer(right)!r}")

    norms: dict[str, list[str]] = collections.defaultdict(list)
    for ticker, entry in corpus.items():
        for side in ("ref", "line"):
            name = entry.get(side)
            if name:
                norms[norm_issuer(name)].append(f"{ticker}.{side}")
    census_names = 0
    if CENSUS.exists():
        census = json.loads(CENSUS.read_text(encoding="utf-8"))
        for ticker, entry in census.items():
            found = _NAME_IN_NOTE.search(entry.get("detail") or "")
            if found:
                census_names += 1
                norms[norm_issuer(found.group(1))].append(f"{ticker}.census")

    print(
        f"\n=== Stumpf-Erhebung ueber {len(norms)} normalisierte Namen "
        f"(Korpus + {census_names} aus dem Zensus) ==="
    )
    for norm in sorted(norms, key=lambda n: (len(n), n))[:20]:
        print(f"  {len(norm):>2}  {norm:<16} {sorted(set(norms[norm]))}")

    print("\n--- Kollisionen (gleicher Norm, verschiedene Ticker) ---")
    collisions = 0
    for norm, sources in sorted(norms.items()):
        tickers = {s.split(".")[0] for s in sources}
        if len(tickers) > 1:
            collisions += 1
            print(f"  {norm!r}: {sorted(tickers)}")
    if not collisions:
        print("  keine")

    print("\n--- Token-Multiset-Arm allein (ohne strikte Gleichheit) ---")
    for ticker, entry in pairs.items():
        left, right = issuer_tokens(entry["ref"]), issuer_tokens(entry["line"])
        if left != right and sorted(left) == sorted(right):
            print(f"  {ticker:<12} {left} <-> {right}")

    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
