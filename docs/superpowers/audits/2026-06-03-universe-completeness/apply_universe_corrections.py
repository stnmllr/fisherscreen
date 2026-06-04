"""STUFE B — apply the verified universe.json delta from the completeness audit.

Surgical, assertion-guarded, count-decomposed. Sources every change from
unresolved35_classified.csv (the VERIFIED classification). Fails loud on any
unexpected state (new ticker already present, old ticker absent, dup, count
mismatch) so a silent wrong edit is impossible.

Run: uv run python docs/superpowers/audits/2026-06-03-universe-completeness/apply_universe_corrections.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
UNIVERSE = ROOT / "data" / "universe.json"

# 13 WRONG_TICKER -> SILENTLY EXCLUDED: replace old with verified correct ticker.
CORRECT: dict[str, str] = {
    "AKERBP.OL": "AKRBP.OL",
    "ASMI.AS": "ASM.AS",
    "ATCOa.ST": "ATCO-A.ST",
    "BDEV.L": "BTRW.L",
    "DSM.SW": "DSFIR.AS",
    "EFGI.PA": "EFGN.SW",
    "ERICb.ST": "ERIC-B.ST",
    "FLTR.IR": "FLTR.L",
    "HMB.ST": "HM-B.ST",
    "ICP.L": "ICG.L",
    "INDV.L": "INDV",
    "INP.L": "INVP.L",
    "TEV": "TEVA",
}
# 5 BENIGN dups: correct ticker ALREADY in universe -> just delete the broken one.
DELETE_BENIGN = ["ELUXb.ST", "LIN.L", "NGG.L", "SKFb.ST", "TEL2b.ST"]
# 12 DELISTED -> prune.
PRUNE_DELISTED = ["DLG.L", "LUN.ST", "MAN.DE", "MOR.DE", "MRW.L", "NEOEN.PA",
                  "SMDS.L", "SOW.DE", "SWMA.ST", "TPG.L", "UN01.DE", "VAR1.DE"]
# 5 UNCLEAR: deliberately UNTOUCHED (surface loud via the Stufe-A aggregate).
UNTOUCHED = ["AMS.VI", "RIGN.SW", "ROL.L", "SANO.HE", "SCHA.OL"]

orig = json.loads(UNIVERSE.read_text(encoding="utf-8"))
u = set(orig)
assert len(orig) == len(u), "universe has duplicates pre-edit"
N0 = len(orig)

# --- assertion guards: prove every assumed state before mutating -------------
for old, new in CORRECT.items():
    assert old in u, f"CORRECT: old ticker {old} not in universe"
    assert new not in u, f"CORRECT: new ticker {new} ALREADY in universe (would dup)"
for t in DELETE_BENIGN:
    assert t in u, f"DELETE_BENIGN: {t} not in universe"
for t in PRUNE_DELISTED:
    assert t in u, f"PRUNE: {t} not in universe"
for t in UNTOUCHED:
    assert t in u, f"UNTOUCHED: {t} not in universe"
# benign correct-forms must indeed already be present (that's WHY they're benign)
BENIGN_CORRECT = {"ELUXb.ST": "ELUX-B.ST", "LIN.L": "LIN", "NGG.L": "NG.L",
                  "SKFb.ST": "SKF-B.ST", "TEL2b.ST": "TEL2-B.ST"}
for broken, correct in BENIGN_CORRECT.items():
    assert correct in u, f"BENIGN sanity: {correct} (for {broken}) NOT in universe — would lose the name!"

# --- apply --------------------------------------------------------------------
new_set = set(u)
for old, new in CORRECT.items():
    new_set.discard(old)
    new_set.add(new)
for t in DELETE_BENIGN + PRUNE_DELISTED:
    new_set.discard(t)

result = sorted(new_set)
N1 = len(result)

# --- decomposition + invariants ----------------------------------------------
expected = N0 - len(DELETE_BENIGN) - len(PRUNE_DELISTED)  # corrections net 0
assert N1 == expected, f"count mismatch: {N1} != expected {expected}"
assert len(result) == len(set(result)), "result has duplicates"
# nothing unintended changed: symmetric diff must equal exactly our edits
added = set(result) - u
removed = u - set(result)
assert added == set(CORRECT.values()), f"unexpected additions: {added ^ set(CORRECT.values())}"
assert removed == set(CORRECT) | set(DELETE_BENIGN) | set(PRUNE_DELISTED), \
    f"unexpected removals: {removed}"
for t in UNTOUCHED:
    assert t in result, f"UNTOUCHED {t} disappeared"

print("=== universe.json delta decomposition ===")
print(f"  start                         {N0}")
print(f"  - benign dup deletions        -{len(DELETE_BENIGN)}  {DELETE_BENIGN}")
print(f"  - delisted prunes             -{len(PRUNE_DELISTED)} {PRUNE_DELISTED}")
print(f"  ± 13 in-place corrections      0  (remove old, add verified correct)")
print(f"  = final                       {N1}")
print(f"  UNTOUCHED (5 UNCLEAR)            {UNTOUCHED}")
print(f"\n  additions ({len(added)}): {sorted(added)}")
print(f"  removals  ({len(removed)}): {sorted(removed)}")

# --- write (same format as build_universe.py: sorted, indent=2) --------------
UNIVERSE.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(f"\nwrote {UNIVERSE} (N={N1})")
