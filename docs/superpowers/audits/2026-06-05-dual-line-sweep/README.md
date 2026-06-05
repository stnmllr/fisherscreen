# Dual-line sweep — is the Roche illiquid-line defect systematic or n=1?

**Date:** 2026-06-05 · **Verdict: essentially n=1.** Roche is the only genuine
fixable dual-line defect (`RO.SW → ROP.SW`) in the entire volume-gate-death
candidate set. Every other illiquid name is single-class or has only illiquid
siblings (share-count artifacts of high nominal share prices). No broader swap
program is warranted.

## Question

The Roche investigation showed the universe anchors the **illiquid bearer** line
`RO.SW` (avgVol 36k < 100k gate). Is that a one-off or a class? Two hypotheses:

- **A SELECTION:** universe anchors an illiquid share class while a *liquid*
  sibling class has a resolving Yahoo symbol → fixable swap.
- **B/share-count:** the liquid line has no resolving symbol (true coverage gap),
  OR all share classes are genuinely illiquid (share-count artifact of a high
  nominal price), OR there is only one class → legitimately out.

## Method (two steps, reproducible)

- **Step 1 — `build_candidate_set.py` (offline).** Candidate = resolves in
  yfinance ∧ numeric `averageVolume < 100_000`. Built from the 2026-06-03 audit's
  `re_resolution.json` ∩ current `universe.json` (1332). **27 candidates.**
  Reconciled byte-exact to the pipeline's `avg_volume` drop set (51 = 27 numeric-
  illiquid + 24 None-volume).
- **Step 2 — `classify_dual_line.py` (OpenFIGI + yfinance).** Per candidate:
  OpenFIGI `/mapping` TICKER+exchCode → clean identity; OpenFIGI `/search` by
  issuer (normalised-name match) → sibling share classes; derive each sibling's
  home-exchange Yahoo symbol and **TEST it in yfinance** (ground truth) for
  resolution + liquidity. Buckets: `A_SELECTION` (liquid sibling found),
  `SINGLE_LINE` (sole class), `MULTI_NO_LIQUID` (siblings exist, all <100k),
  `MULTI_NO_HOME` / `NEEDS_MANUAL`.

## Result (27 candidates)

| Bucket | n | Names |
|---|---|---|
| **A_SELECTION** | **1** | `RO.SW → ROP.SW` |
| MULTI_NO_LIQUID | 1 | LISN.SW (Lindt: PS `LISP.SW` exists, avgVol 3.5k, still <100k) |
| NEEDS_MANUAL | 1 | MAERSK-B.CO (OpenFIGI ticker is `MAERSKB`, dash broke identity) |
| SINGLE_LINE | 24 | rest |

### The one Bucket-A swap proposal (NOT applied)

`RO.SW` (bearer, avgVol 36,420) **→ `ROP.SW`** (Roche participation cert /
Genussschein, the liquid SMI line: yfinance shortName "ROCHE PS", 324.6 CHF,
**avgVol 1,018,486**, SIX/EBS). Verified live 2026-06-05. This is the swap that
reverses the earlier (wrong) "Roche has no liquid symbol" conclusion — see
`../../known-data-limitations.md`.

**What the swap fixes vs doesn't (local effect-verification through production
code, 2026-06-05):** `ROP.SW` now PASSES the volume gate (1.02M ≥ 100k), the
gross-margin gate (0.74), and market-cap. **But Roche still drops at
`revenue_growth` (TTM −0.4% < 0)** — the exact `MIN_REVENUE_GROWTH=0.0`
brittleness on a TTM snapshot (the separate filter-design ticket: Nestlé −2.2%,
Novartis −0.7%, …). So the swap **corrects the anchored line** (the bearer could
*never* pass volume; the participation line now faces only legitimate fundamental
gates) but does **not by itself surface Roche** until TTM revenue growth turns
positive or the revenue-growth gate is softened. The swap is correct as a data
fix on its own merit; surfacing Roche is gated on the revenue-growth ticket.

### Hand-adjudicated (instrument edge cases — verified, no new Bucket-A)

- **MAERSK-B.CO** — NEEDS_MANUAL was an identity-lookup miss (OpenFIGI ticker
  `MAERSKB`). Resolved by hand: `MAERSK-A.CO` avgVol 8,027 < `MAERSK-B.CO` 18,475
  → the candidate is already the more-liquid of the two A/B classes; both <100k
  (Maersk shares ~12,000 DKK). **No Bucket-A.** Effectively MULTI_NO_LIQUID.
- **SIX2.DE (Sixt)** — reported SINGLE_LINE, but Sixt has a preferred `SIX3.DE`.
  Verified by hand: `SIX3.DE` avgVol 32,129 < `SIX2.DE` 63,498 → preferred is
  *less* liquid; both <100k. **No Bucket-A.** (The instrument missed the sibling
  because Step 2 reads only the first search page — see caveat.)

## Honest caveats

- **Single search page.** Step 2 reads one `/search` page (100 results) per
  candidate to stay under OpenFIGI's anonymous rate limit. A sibling share class
  ranked beyond the first 100 listings is missed → a candidate can be reported
  `SINGLE_LINE` when a low-ranked sibling exists (this is what happened to Sixt).
  The miss is biased toward *low-listing-count* siblings, which are the *less*
  liquid ones — i.e. unlikely to be the more-liquid sibling a Bucket-A needs. The
  realistic dual-class-prone names (German Stamm/Vorzug: Sixt, Covestro; Nordic
  A/B: Maersk; Swiss PS: Lindt) were **hand-verified** → no additional Bucket-A.
- **Earlier masking bug, fixed.** A first hardened run silently classified all 27
  as SINGLE_LINE because rate-limit (429) search failures were indistinguishable
  from genuinely-empty searches. Fixed: `/mapping`+`/search` now back off on 429
  and a hard search failure routes to `NEEDS_MANUAL`, never `SINGLE_LINE`. The
  reported run hit 8 × 429 backoffs, all recovered within retries (0 hard search
  failures → the SINGLE_LINE results rest on successful searches).
- **yfinance `.isin` is unreliable** here (returned Roche *Bobois* for `RO.SW`);
  identity is taken from OpenFIGI TICKER+exchCode mapping instead.

## Artifacts

`build_candidate_set.py` · `candidate_set.csv` · `classify_dual_line.py` ·
`dual_line_classification.csv` · `dual_line_evidence.json`

## Next (separate go-point, not in this run)

Apply `RO.SW → ROP.SW` in `universe.json` + cold re-verification (purge both
caches, cold dry-run) — the cache layer would otherwise mask the change, per
`[[universe-completeness-degraded-dict-masking-closed]]`. Bucket-A swaps are NOT
applied in this sweep.
