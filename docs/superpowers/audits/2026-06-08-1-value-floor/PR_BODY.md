## Summary

Bundled funnel-transparency + universe/gate correctness stack (Tier A). One PR = one prod deploy.
All four initiatives are independently GATE-verified via $0 cold-dry-runs with cache purge; the
reconciliation invariant holds at every stage.

- **Funnel instrumentation (Phase 1)** — pure transparency: `funnel_summary.json` + `dropouts.csv`
  + report header. Every funnel exit gets a `reason_code` + `severity_bucket`. No gate/score logic
  changed. Reconciliation invariant `|Universum| == Σ Drops + remaining` enforced by test.
- **0a — RIC-symbol contaminants** — index source emitted Reuters RICs (e.g. `BNPP.PA` → MUTUALFUND
  junk) instead of Yahoo symbols; verified, provenance-anchored (Wikipedia build-revision)
  `SYMBOL_CORRECTIONS`(20)+`SYMBOL_DROP`(2) in `build_universe.py`; `universe.json` 1332→1322.
- **0b — resolution data-quality classification** — any symbol resolving with missing/zero
  market_cap, missing currency, missing/zero volume, or unavailable FX is diverted **in resolution,
  before any gate**, as REVIEW (`RESOLUTION_NO_SYMBOL_DATA` / `RESOLUTION_FX_UNAVAILABLE`) instead
  of silently masking BENIGN at a gate. Survivor-neutral.
- **Punkt 1 — value-based volume gate** — share-count floor (`avg_daily_volume ≥ 100k`) → EUR
  daily-trading-value floor (`avg_daily_volume × price × fx_rate ≥ €1M/day`). Includes London-pence
  (GBp→GBP ÷100) normalization at construction, `fx_rate` carried as a record primitive, a
  `NO_PRICE` resolution divert (price now load-bearing), and a fail-loud uncalibrated-threshold
  sentinel + raising guard (never a silent drop). Threshold €1M structurally anchored (empty
  €0.89M–€2.45M liquidity band; absolute trading minimum, drift-robust).

## Verification

- **Full suite:** 802 passed, 97.3% coverage. No drift on scripts/output/deepdive.
- **0a GATE-2:** 0 contaminants remaining, 12 firms rehabilitated, reconciliation holds.
- **0b GATE:** diverts == {ML.PA, RNL.PA, GLB.IR}, zero remaining masked-BENIGN, survivor 688
  unchanged (survivor-neutral), `1322 = 8 + 618 + 8 + 688`.
- **Punkt 1 GATE-A:** threshold €1M approved on the clean (pence-fixed) survivor histogram (688
  survivors, min €2.45M, none below €2M); reversibility triggers documented.
- **Punkt 1 GATE-B (cold-run):** edgar-survivor **688 → 698 (+10, bit-exact vs prognosis)**; the 10
  predicted survivors all present; 13 rescued-but-low-quality fall at gross_margin/rev_growth
  (Punkt-2/3 input, not mixed); GATE_VOLUME 27→6 (the 4 + 2 bidirectional finds BPOST/ONTEX =
  share-floor passers with <€1M value, small-caps, no survivor effect); value-gate raised nowhere;
  `going_concern_drops=0`; `1322 = 8 + 608 + 8 + 698`.

Artifacts: `docs/superpowers/audits/2026-06-06-0a-symbol-contaminants/`,
`docs/superpowers/audits/2026-06-07-0b-resolution-data-quality/`,
`docs/superpowers/audits/2026-06-08-1-value-floor/`.

## Test Plan

- [ ] CI `test` check green (required before merge)
- [ ] Merge triggers Cloud Run prod deploy (`deploy.yml`) — manual merge click is the last safety bar
- [ ] First scheduled/triggered prod run produces funnel telemetry (real market-data drift, FX edges,
      pence-fix against the full universe)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
