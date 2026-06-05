"""Apply the dual-line sweep's single Bucket-A swap: RO.SW -> ROP.SW.

RO.SW is the illiquid Roche BEARER line (avgVol 36,420 < 100k volume gate). ROP.SW
is the liquid Roche PARTICIPATION certificate / Genussschein (the SMI line: "Roche
Holding AG", avgVol 1,018,486, SIX). Verified live 2026-06-05; see
../../known-data-limitations.md and README.md.

Surgical, assertion-guarded, count-decomposed (same pattern as
apply_universe_corrections.py). Net 0 to the universe count (one out, one in).
Fails loud on any unexpected state so a silent wrong edit is impossible.

Run: uv run python docs/superpowers/audits/2026-06-05-dual-line-sweep/apply_roche_swap.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
UNIVERSE = ROOT / "data" / "universe.json"

OLD = "RO.SW"   # illiquid bearer line
NEW = "ROP.SW"  # liquid participation certificate (Genussschein)

orig = json.loads(UNIVERSE.read_text(encoding="utf-8"))
u = set(orig)
assert len(orig) == len(u), "universe has duplicates pre-edit"
N0 = len(orig)

# --- guards: prove assumed state before mutating -----------------------------
assert OLD in u, f"{OLD} not in universe (nothing to swap)"
assert NEW not in u, f"{NEW} ALREADY in universe (would dup)"

# --- apply --------------------------------------------------------------------
new_set = set(u)
new_set.discard(OLD)
new_set.add(NEW)
result = sorted(new_set)
N1 = len(result)

# --- invariants: ONLY this one swap, nothing else changed --------------------
assert N1 == N0, f"count changed: {N1} != {N0} (swap must be net 0)"
assert len(result) == len(set(result)), "result has duplicates"
added = set(result) - u
removed = u - set(result)
assert added == {NEW}, f"unexpected additions: {added}"
assert removed == {OLD}, f"unexpected removals: {removed}"

print("=== Roche swap delta ===")
print(f"  start  {N0}")
print(f"  - {OLD}  (illiquid bearer, avgVol 36,420)")
print(f"  + {NEW}  (liquid participation, avgVol 1,018,486)")
print(f"  = final {N1}  (net 0)")
print(f"  additions: {sorted(added)}")
print(f"  removals : {sorted(removed)}")

# same format as build_universe.py: sorted, indent=2
UNIVERSE.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(f"\nwrote {UNIVERSE} (N={N1})")
