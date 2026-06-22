# Ticket: Robust 20-F item segmenter — harden the anchor-link fallback so filings without ITEM-prefixed TOC anchors still get section-grounded citations

**Opened:** 2026-06-22
**Priority:** non-blocking; surfaced by the Phase 1.6 acceptance gate, not a regression. Schedule after Phase 1 close.
**Status:** open

## Context

The Phase 1.6 acceptance gate (three real Watchlist deep-dives, 2026-06-18 —
see `docs/superpowers/diagnostic-reports/2026-06-18-phase-1-acceptance.md`)
surfaced a **filing-specific** parser gap on **ASML.AS**:

- The deep-dive mechanism worked end-to-end (CIK resolution → `20-F` detection →
  peer-quant all ✓).
- But **all 15 Fisher points rendered with `[Inferenz]`** instead of
  filing-grounded section markers (`[20-F §N]`).

### Root cause

The filing parser has two paths (`app/deepdive/filing_parser.py:58-76`):

1. **Primary — DOM-anchor tracing** (`anchor_resolver.resolve_anchors`):
   finds TOC anchor-link targets whose next text starts with `ITEM N`
   (`app/deepdive/anchor_resolver.py:59-91`), then slices each section between
   consecutive anchors.
2. **Fallback — pattern matching** (`_extract_via_pattern_fallback`): used when
   no usable `ITEM`-prefixed anchor-links exist.

**ASML's specific 20-F is iXBRL without `ITEM`-prefixed TOC anchors**, so the
primary path returns zero hits → fallback path → `item4/item5 missing,
item18 truncated`. Because the honest-label guard cannot verify the model's
section citations against a cleanly parsed filing, it **conservatively downgrades
every point to `[Inferenz]`**. The guard is working correctly (better `[Inferenz]`
than a fabricated `[20-F §N]` citation) — this is a *parser coverage* gap, not a
guard bug.

### Scope: format variance, not a 20-F-wide defect

**NOVO-B.CO's 20-F parsed cleanly** in the same run (anchor-links present →
`[20-F §4/§5/§18]` markers). So this is **per-filer format variance** in how
20-F documents structure their item navigation, not a defect across all 20-F
filings. The US 10-K path (FICO) was likewise fully grounded.

## Target state (this ticket)

Harden the fallback so filers in ASML's format variant get filing-grounded
section extraction instead of blanket `[Inferenz]`:

- **Option 1 — Strengthen the pattern fallback:** make `_extract_via_pattern_fallback`
  locate `ITEM N` / `PART N` headings via text-pattern matching (regardless of
  anchor presence) and slice sections on those heading positions. Lowest-risk,
  reuses the existing fallback seam.
- **Option 2 — Anchor-free structural segmentation:** segment iXBRL 20-F bodies
  on heading structure (heading tags / bold runs / known 20-F item taxonomy)
  rather than TOC anchors, so the primary path no longer depends on
  `ITEM`-prefixed anchor IDs.

Either way, the guard logic stays unchanged — the goal is to give it a parsed
filing it *can* verify against, so legitimate citations survive as `[20-F §N]`.

## Acceptance

- [ ] A 20-F in ASML's variant (no ITEM-prefixed TOC anchors) yields non-empty,
      correctly-bounded sections for the expected items (item4/5/7/18…) — verified
      against the real ASML 20-F fixture.
- [ ] A re-run of the ASML deep-dive produces ≥1 point with a real `[20-F §N]`
      marker (i.e. not all 15 on `[Inferenz]`), with the cited section text
      actually matching the filing.
- [ ] **Regression guard:** NOVO-B.CO's 20-F (clean anchor path) still parses via
      the primary path and keeps its `[20-F §4/§5/§18]` markers — the fallback
      change must not steal filings that the anchor path handles correctly.
- [ ] FICO's 10-K (anchor path) unchanged.
- [ ] Honest-label guard behavior unchanged: still downgrades to `[Inferenz]`
      when (and only when) a citation cannot be verified against the parsed filing.

## Related

- Parser: `app/deepdive/filing_parser.py` (`parse_filing`, `_extract_via_anchors`,
  `_extract_via_pattern_fallback`); anchors: `app/deepdive/anchor_resolver.py`.
- Honest-label / `[Inferenz]` downgrade lives in the synthesis path
  (`app/deepdive/synthesis.py`).
- Acceptance evidence: `docs/superpowers/diagnostic-reports/2026-06-18-phase-1-acceptance.md`.
- Anchor-tracing origin: Punkt 5 (filing-parser-anchor-tracing), Plan-Doc
  `2026-05-27-phase-1-pareto-b2.md`.
